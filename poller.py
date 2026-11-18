#!/usr/bin/env python3
"""Internship Radar fast poller.

Runs on GitHub Actions every ~20 minutes. Checks company job boards directly
(Greenhouse, Lever, Ashby, Workday, Eightfold, Amazon) plus the Simplify and
vanshb03 trackers, scores every new matching role, and sends an instant phone
push + a separate email for each new Tier S role.

Standard library only, so a run finishes in well under a minute.
State lives in data/ and is committed back to the repo by the workflow.
"""
import datetime as dt
import json
import os
import re
import smtplib
import ssl
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from html import escape, unescape
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("RADAR_DATA_DIR", ROOT / "data"))
UA = "Mozilla/5.0 (X11; Linux x86_64) internship-radar-poller"
NOW = time.time()

# ---------------------------------------------------------------- filters ---

INTERN = re.compile(r"\bintern(ship)?s?\b|\bco-?op\b", re.I)
BAD = re.compile(
    r"\bmba\b|postdoc|new grad|"
    r"graduate program|full[- ]time|freshm|sophomore|first[- ]year|second[- ]year|"
    r"high school|\bexplore\b|\bstep\b|hardware|electrical|mechanical|silicon|asic|"
    r"fpga|analog|\brf\b|sales|marketing|recruit|legal|accounting|finance intern|"
    r"\bhr\b|human resources|supply chain|manufactur|\blaw\b|design intern|"
    r"product design|ux design|communications|policy intern|product manag|program manag|"
    r"project manag|\bpm intern|operations intern|business development",
    re.I,
)
# Grad-degree titles are dropped unless the title also opens the role to
# undergrads (e.g. "BS/MS", "Bachelor's or Master's").
GRAD_ONLY = re.compile(r"ph\.?\s?d|doctoral|master'?s|\bm\.?s\.?\b(?!\w)", re.I)
UNDERGRAD_OK = re.compile(r"\bb\.?s\b|\bb\.?a\b|bachelor|undergrad", re.I)
OFF_SEASON = re.compile(r"\b(fall|autumn|winter|spring)\b|summer\s*2026", re.I)
NON_US = re.compile(
    r"london|united kingdom|\buk\b|dublin|ireland|toronto|vancouver|montreal|canada|"
    r"bangalore|bengaluru|hyderabad|pune|india|singapore|tokyo|japan|sydney|australia|"
    r"paris|france|berlin|munich|germany|amsterdam|netherlands|zurich|switzerland|"
    r"tel aviv|israel|beijing|shanghai|shenzhen|china|hong kong|taiwan|taipei|seoul|"
    r"korea|mexico|brazil|warsaw|poland|madrid|spain|stockholm|sweden|emea|apac|latam|"
    r"copenhagen|denmark|oslo|lisbon|portugal|prague|bucharest|cairo|dubai|"
    r"belgrade|serbia|yerevan|armenia|romania|cluj|krakow|kraków|bulgaria|sofia|"
    r"vietnam|philippines|manila|indonesia|jakarta|malaysia|kuala lumpur|thailand|"
    r"bangkok|argentina|buenos aires|colombia|bogota|chile|santiago|costa rica|"
    r"nigeria|kenya|south africa|turkey|istanbul|\buae\b|saudi|riyadh|qatar|"
    r"new zealand|italy|milan|belgium|brussels|austria|vienna|finland|helsinki|"
    r"czech|hungary|budapest|greece|athens|edinburgh|estonia|tallinn",
    re.I,
)
US_HINT = re.compile(
    r"united states|\busa?\b|new york|nyc|california|\bca\b|washington|seattle|texas|"
    r"austin|illinois|chicago|massachusetts|boston|atlanta|georgia|denver|colorado|"
    r"virginia|new jersey|pennsylvania|remote",
    re.I,
)
PREFERRED_LOC = re.compile(
    r"new york|nyc|brooklyn|manhattan|jersey city|san francisco|bay area|palo alto|"
    r"mountain view|menlo park|sunnyvale|cupertino|san jose|santa clara|redwood city|"
    r"san mateo|saratoga|remote",
    re.I,
)

# First match wins. Points reflect the data science focus; SWE still counts
# (Tier S SWE roles alert) but ranks lower.
CATEGORIES = [
    ("Data Science", 40, re.compile(
        r"data scien|decision scien|product analy|experimentation|insights|"
        r"quantitative analy|statistic|econometric|causal", re.I)),
    ("ML/AI", 32, re.compile(
        r"machine learning|\bml\b|\bai\b|applied scien|research scien|deep learning|"
        r"\bnlp\b|computer vision|\bllm|genai|generative", re.I)),
    ("Analytics/Data", 28, re.compile(
        r"data analy|business analy|analytics|data engineer|business intelligence|"
        r"\bbi\b|data platform|data solutions|data architect|\bdata intern", re.I)),
    ("Quant", 24, re.compile(r"quant", re.I)),
    ("SWE", 18, re.compile(
        r"software|\bswe\b|\bsde\b|developer|engineer|full.?stack|backend|back.?end|"
        r"front.?end|platform|infrastructure|mobile|\bios\b|android|security|cloud|"
        r"technology (summer )?(analyst|intern)|\btech intern|application development", re.I)),
]
TIER_POINTS = {"S": 35, "A": 22, "B": 8}
PRODUCT_BONUS = re.compile(r"product|experiment|a/b|growth|consumer|user|ads|marketplace", re.I)
UNDERGRAD_BONUS = re.compile(r"undergrad|university|bachelor|\bbs\b|\bba\b|student|summer 2027", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def title_key(title):
    t = re.sub(r"summer|20\d\d|internships?|interns?|\(.*?\)", " ", title or "", flags=re.I)
    return norm(t)


def classify(title):
    for name, pts, rx in CATEGORIES:
        if rx.search(title):
            return name, pts
    return None, 0


def age_days(it):
    """Age of a posting in days when the board says so, else None."""
    if it.get("posted_ts"):
        return (NOW - it["posted_ts"]) / 86400
    m = re.search(r"(\d+)\+?\s*days?\s*ago", it.get("posted_text") or "", re.I)
    return int(m.group(1)) if m else None


def passes_filters(title, location):
    if not INTERN.search(title):
        return False
    if BAD.search(title):
        return False
    if GRAD_ONLY.search(title) and not UNDERGRAD_OK.search(title):
        return False
    if OFF_SEASON.search(title) and not re.search(r"summer\s*2027", title, re.I):
        return False
    if re.search(r"\b2026\b", title) and not re.search(r"\b2027\b", title):
        return False
    loc = location or ""
    if loc and NON_US.search(loc) and not US_HINT.search(loc):
        return False
    return classify(title)[0] is not None


def fit_score(title, location, tier):
    cat, pts = classify(title)
    score = pts + TIER_POINTS.get(tier, 8)
    loc = location or ""
    if PREFERRED_LOC.search(loc):
        score += 10
    elif loc:
        score += 4
    if PRODUCT_BONUS.search(title):
        score += 5
    if UNDERGRAD_BONUS.search(title):
        score += 5
    return min(score, 100), cat


# ------------------------------------------------------------------- http ---

def http_json(url, payload=None, headers=None, timeout=20):
    h = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if body else "GET")
    # Retry transient failures (timeouts, connection resets, 429 and 5xx) so a
    # single blip doesn't mark the source as failing in the digest.
    delays = [4, 12, 25]
    for attempt in range(len(delays) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == len(delays):
                raise
            wait = delays[attempt]
            ra = e.headers.get("Retry-After") if e.headers else None
            if ra and ra.strip().isdigit():
                wait = min(max(wait, int(ra.strip())), 30)
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            if attempt == len(delays):
                raise
            wait = delays[attempt]
        time.sleep(wait)


def iso_ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# ---------------------------------------------------------------- sources ---
# Each source returns a list of dicts: id, title, location, url, posted_ts,
# posted_text (optional), company (only for trackers).

def src_greenhouse(token):
    data = http_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    return [{
        "id": j["id"], "title": j.get("title", ""),
        "location": (j.get("location") or {}).get("name", ""),
        "url": j.get("absolute_url"),
        "posted_ts": iso_ts(j.get("first_published")),
    } for j in data.get("jobs", [])]


def src_lever(company):
    data = http_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
    out = []
    for j in data:
        cats = j.get("categories") or {}
        locs = cats.get("allLocations") or [cats.get("location", "")]
        out.append({
            "id": j["id"], "title": j.get("text", ""),
            "location": "; ".join(l for l in locs if l),
            "url": j.get("hostedUrl"),
            "posted_ts": (j.get("createdAt") or 0) / 1000 or None,
        })
    return out


def src_ashby(org):
    data = http_json(f"https://api.ashbyhq.com/posting-api/job-board/{org}")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [
            (s.get("location") or "") for s in (j.get("secondaryLocations") or [])]
        out.append({
            "id": j["id"], "title": j.get("title", ""),
            "location": "; ".join(l for l in locs if l),
            "url": j.get("jobUrl"), "posted_ts": iso_ts(j.get("publishedAt")),
        })
    return out


WD_FACETS = DATA / "workday_facets.json"
US_NAMES = {"united states of america", "united states", "usa", "us"}


def _wd_walk(facets):
    for f in facets or []:
        vals = f.get("values") or []
        if vals and isinstance(vals[0], dict) and "facetParameter" in vals[0]:
            yield from _wd_walk(vals)
        else:
            yield f


def _wd_pick_facets(facets):
    """Find the 'Intern' job-type value and the US country value, if the board has them."""
    applied = {}
    for f in _wd_walk(facets):
        param = f.get("facetParameter")
        for v in f.get("values") or []:
            d = (v.get("descriptor") or "").strip().lower()
            if param and d in US_NAMES and "loc" in param.lower() + (f.get("descriptor") or "").lower() + "country":
                applied.setdefault(param, [v["id"]])
            if param in ("workerSubType", "jobType", "Job_Type") and re.search(r"\bintern", d):
                applied.setdefault(param, []).append(v["id"])
    return applied


def src_workday(tenant, wd, site, pages=10):
    host = f"{tenant}.{wd}.myworkdayjobs.com"
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    hdr = {"Origin": f"https://{host}", "Referer": f"https://{host}/en-US/{site}",
           "Accept-Language": "en-US"}
    cache = load_json(WD_FACETS, {})
    applied = cache.get(tenant)
    if applied is None:
        first = http_json(api, {"appliedFacets": {}, "limit": 20, "offset": 0,
                                "searchText": "intern"}, hdr)
        applied = _wd_pick_facets(first.get("facets"))
        cache[tenant] = applied
        WD_FACETS.write_text(json.dumps(cache, indent=1))
        time.sleep(2)
    # With an Intern job-type filter we don't need the keyword (it matches loosely).
    has_intern = any(k in applied for k in ("workerSubType", "jobType", "Job_Type"))
    search = "" if has_intern else "intern"
    out, total = [], 0
    for page in range(pages):
        try:
            data = http_json(api, {"appliedFacets": applied, "limit": 20,
                                   "offset": page * 20, "searchText": search}, hdr)
        except urllib.error.HTTPError as e:
            if page == 0 and e.code in (400, 422) and applied:
                cache.pop(tenant, None)  # facet ids changed; relearn next run
                WD_FACETS.write_text(json.dumps(cache, indent=1))
            raise
        posts = data.get("jobPostings", [])
        for j in posts:
            path = j.get("externalPath", "")
            out.append({
                "id": path, "title": j.get("title", ""),
                "location": j.get("locationsText", ""),
                "url": f"https://{host}/en-US/{site}{path}",
                "posted_ts": None, "posted_text": j.get("postedOn", ""),
            })
        if page == 0:
            total = data.get("total") or 0  # Workday only reports total on page 1
        if len(posts) < 20 or (page + 1) * 20 >= total:
            break
        time.sleep(2)
    return out


def src_eightfold(host, domain):
    data = http_json(f"https://{host}/api/apply/v2/jobs?domain={domain}"
                     f"&query=intern&num=100&sort_by=timestamp")
    out = []
    for j in data.get("positions", []):
        locs = j.get("locations") or [j.get("location", "")]
        out.append({
            "id": j["id"], "title": j.get("name", ""),
            "location": "; ".join(l for l in locs if l),
            "url": j.get("canonicalPositionUrl") or f"https://{host}/careers?pid={j['id']}",
            "posted_ts": j.get("t_create"),
        })
    return out


def src_amazon():
    out = []
    for offset in (0, 100):
        data = http_json("https://www.amazon.jobs/en/search.json?base_query=intern"
                         f"&country=USA&sort=recent&result_limit=100&offset={offset}")
        for j in data.get("jobs", []):
            ts = None
            try:
                ts = dt.datetime.strptime(j.get("posted_date", ""), "%B %d, %Y").replace(
                    tzinfo=ET).timestamp()
            except ValueError:
                pass
            out.append({
                "id": j.get("id_icims") or j.get("id"), "title": j.get("title", ""),
                "location": j.get("normalized_location") or
                            f"{j.get('city', '')}, {j.get('state', '')}".strip(", "),
                "url": "https://www.amazon.jobs" + j.get("job_path", ""),
                "posted_ts": None, "posted_text": f"posted {j.get('posted_date', '')}",
                "_day_ts": ts,
            })
    return out


def src_google():
    # Google's careers page embeds results as a JS data blob (20 per page).
    base = ("https://www.google.com/about/careers/applications/jobs/results"
            "?location=United%20States&target_level=INTERN_AND_APPRENTICE&sort_by=date")
    out = []
    for page in range(1, 6):
        req = urllib.request.Request(f"{base}&page={page}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
        m = re.search(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(\[.*?\]), sideChannel", body, re.S)
        if not m:
            if page == 1:
                raise ValueError("Google page layout changed (no ds:1 data)")
            break
        data = json.loads(m.group(1))
        jobs = data[0] or []
        for j in jobs:
            locs = [l[0] for l in (j[9] or []) if l and l[0]]
            created = j[12][0] if len(j) > 12 and j[12] else None
            out.append({
                "id": j[0], "title": j[1], "location": "; ".join(locs),
                "url": f"https://www.google.com/about/careers/applications/jobs/results/{j[0]}",
                "posted_ts": created,
            })
        total = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
        if len(jobs) < 20 or len(out) >= total:
            break
    return out


# TikTok's API filters by city code, not country. These cover its US offices
# (San Jose, Seattle, LA, NYC, Austin, DC, SF, Chicago, San Diego, Miami,
# Houston, Atlanta, plus small data center sites).
TIKTOK_US_CITIES = ["CT_1103355", "CT_157", "CT_94", "CT_114", "CT_247", "CT_233",
                    "CT_75", "CT_221", "CT_203", "CT_223", "CT_1103554", "CT_100762",
                    "CT_2001643", "MDCY00038339", "MDCY00039300", "CT_1000001", "CT_2001826"]


def src_tiktok():
    out = []
    for offset in range(0, 2000, 100):
        data = http_json(
            "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts",
            {"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [],
             "location_code_list": TIKTOK_US_CITIES, "keyword": "intern", "limit": 100,
             "offset": offset},
            {"website-path": "tiktok", "Origin": "https://lifeattiktok.com",
             "Referer": "https://lifeattiktok.com/"})
        if data.get("code") not in (0, None):
            raise ValueError(f"TikTok API code {data.get('code')}: {data.get('message')}")
        posts = (data.get("data") or {}).get("job_post_list") or []
        for j in posts:
            parts, c = [], j.get("city_info")
            while c:
                parts.append(c.get("en_name") or "")
                c = c.get("parent")
            out.append({
                "id": j["id"], "title": j.get("title", ""),
                "location": ", ".join(p for p in parts if p),
                "url": f"https://lifeattiktok.com/search/{j['id']}",
                "posted_ts": None,
            })
        if len(posts) < 100:
            break
    return out


JS_CITY = {"NYC": "New York, NY", "CHI": "Chicago, IL", "ATX": "Austin, TX",
           "LDN": "London", "HKG": "Hong Kong", "SGP": "Singapore"}


def src_janestreet():
    data = http_json("https://www.janestreet.com/jobs/main.json")
    out = []
    for j in data:
        if j.get("availability") != "Summer Internship":
            continue
        out.append({
            # Jane Street titles omit "Intern"; add it so the filters see it.
            "id": j["id"], "title": f"{j.get('position', '').strip()} Intern",
            "location": JS_CITY.get(j.get("city"), j.get("city") or ""),
            "url": f"https://www.janestreet.com/join-jane-street/position/{j['id']}/",
            "posted_ts": None,
        })
    return out


def src_apple():
    import http.cookiejar
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = "https://jobs.apple.com"
    hdr = {"User-Agent": UA, "Accept": "application/json", "Origin": base,
           "Referer": f"{base}/en-us/search"}
    with op.open(urllib.request.Request(f"{base}/api/v1/CSRFToken", headers=hdr), timeout=20) as r:
        tok = r.headers.get("X-Apple-CSRF-Token") or ""
    if tok:
        hdr["X-Apple-CSRF-Token"] = tok
    hdr["Content-Type"] = "application/json"
    out = []
    for page in range(1, 6):
        # Apple lists internships under its Students team as evergreen postings
        # (e.g. "Machine Learning and AI Undergrad Internships"); the keyword is ignored.
        body = json.dumps({"query": "", "filters": {"locations": ["postLocation-USA"],
                                                    "teams": [{"team": "teamsAndSubTeams-STDNT"}]},
                           "page": page, "locale": "en-us", "sort": "newest",
                           "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"}}).encode()
        with op.open(urllib.request.Request(f"{base}/api/v1/search", data=body, headers=hdr,
                                            method="POST"), timeout=20) as r:
            res = json.loads(r.read().decode("utf-8"))["res"]
        rows = res.get("searchResults") or []
        for j in rows:
            pid = j.get("positionId") or j.get("id")
            slug = j.get("transformedPostingTitle") or ""
            locs = [l.get("name") or l.get("city") or "" for l in (j.get("locations") or [])]
            out.append({
                "id": pid, "title": j.get("postingTitle", ""),
                "location": "; ".join(l for l in locs if l) or "United States",
                "url": f"{base}/en-us/details/{pid}/{slug}",
                "posted_ts": iso_ts(j.get("postDateInGMT")),
            })
        if len(rows) < 20:
            break
        time.sleep(1)
    return out


def src_ibm():
    data = http_json("https://www-api.ibm.com/search/api/v2", {
        "appId": "careers", "scopes": ["careers2"],
        "query": {"bool": {"must": [{"simple_query_string": {
            "query": "intern", "fields": ["title^3", "description^2"]}}]}},
        "size": 100, "sort": [{"dcdate": "desc"}], "lang": "zz", "localeSelector": {},
        "sm": {"query": "intern", "lang": "zz"},
        "_source": ["_id", "title", "url", "dcdate", "field_keyword_19"]})
    out = []
    for h in (data.get("hits") or {}).get("hits", []):
        src = h.get("_source") or {}
        title = src.get("title", "")
        loc = src.get("field_keyword_19") or ""
        if isinstance(loc, list):
            loc = "; ".join(loc)
        if not loc and " - " in title:
            loc = title.rsplit(" - ", 1)[-1]
        out.append({"id": h.get("_id"), "title": title, "location": loc,
                    "url": src.get("url"), "posted_ts": None,
                    "posted_text": f"posted {src.get('dcdate', '')}"})
    return out


def src_bloomberg():
    req = urllib.request.Request(
        "https://bloomberg.avature.net/careers/SearchJobs/?search=intern&jobRecordsPerPage=100",
        headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    out, seen = [], set()
    pat = r'href="(https://bloomberg\.avature\.net/careers/JobDetail/[^"]+)"[^>]*>\s*([^<]{3,200}?)\s*<'
    for url, title in re.findall(pat, html):
        if url in seen or title.strip().lower() in ("apply", "apply now", "learn more"):
            continue
        seen.add(url)
        out.append({"id": url.rsplit("/", 1)[-1], "title": title.strip(),
                    "location": "", "url": url, "posted_ts": None})
    if not out:
        raise ValueError("Bloomberg careers page layout changed (no job links)")
    return out


BROWSER_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document", "sec-fetch-mode": "navigate", "sec-fetch-site": "none",
    "sec-fetch-user": "?1", "upgrade-insecure-requests": "1",
}


def get_text(url, headers=None, opener=None, timeout=30):
    h = dict(BROWSER_HDRS, Accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    for attempt in range(3):
        try:
            with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == 2:
                raise
        except (TimeoutError, urllib.error.URLError, ConnectionError):
            if attempt == 2:
                raise
        time.sleep(5 * (attempt + 1))


def src_microsoft():
    import http.cookiejar
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = "https://apply.careers.microsoft.com"
    get_text(f"{base}/careers?query=intern", opener=op)  # session cookie, else 429/403
    out = []
    for start in range(0, 50, 10):
        req = urllib.request.Request(
            f"{base}/api/pcsx/search?domain=microsoft.com&query=intern"
            f"&location=United%20States&start={start}&sort_by=timestamp",
            headers=dict(BROWSER_HDRS, Accept="application/json",
                         Referer=f"{base}/careers?query=intern"))
        with op.open(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8")).get("data") or {}
        pos = data.get("positions") or []
        for j in pos:
            out.append({
                "id": j["id"], "title": j.get("name", ""),
                "location": "; ".join(j.get("locations") or []),
                "url": base + (j.get("positionUrl") or f"/careers/job/{j['id']}"),
                "posted_ts": j.get("postedTs"),
            })
        if len(pos) < 10:
            break
        time.sleep(1)
    return out


META_TITLES = DATA / "meta_titles.json"


def src_meta():
    """Meta has no job API we can use, but its job sitemap lists every open role.
    A new URL there is a new role; we open only new pages to read the title."""
    sm = get_text("https://www.metacareers.com/jobs/sitemap.xml")
    ids = re.findall(r"<loc>https://www\.metacareers\.com/profile/job_details/(\d+)/?</loc>", sm)
    if not ids:
        raise ValueError("Meta sitemap layout changed (no job URLs)")
    cache = load_json(META_TITLES, None)
    if cache is None:
        # First run: remember what is already posted without opening 1,000+ pages.
        cache = {i: {"title": "", "location": ""} for i in ids}
    fetched = 0
    for i in ids:
        if i in cache or fetched >= 40:
            continue
        html = get_text(f"https://www.metacareers.com/profile/job_details/{i}/")
        title = re.search(r'property="og:title" content="([^"]*)"', html)
        loc = re.search(r'"locations?":\s*\[?"([^"\]]{3,80})', html)
        cache[i] = {"title": unescape(title.group(1)) if title else "",
                    "location": loc.group(1) if loc else ""}
        fetched += 1
        time.sleep(1)
    live = set(ids)
    cache = {k: v for k, v in cache.items() if k in live}
    META_TITLES.write_text(json.dumps(cache, separators=(",", ":")))
    return [{"id": i, "title": cache[i]["title"], "location": cache[i]["location"],
             "url": f"https://www.metacareers.com/profile/job_details/{i}/", "posted_ts": None}
            for i in ids if i in cache and cache[i]["title"]]


def src_twosigma():
    out, seen = [], set()
    for page in ("InternshipsAndEarlyCareers", "OpenRoles"):
        html = get_text(f"https://careers.twosigma.com/careers/{page}")
        pat = r'href="(https://careers\.twosigma\.com/careers/JobDetail/[^"]+)"[^>]*>\s*([^<]{3,200}?)\s*<'
        for url, title in re.findall(pat, html):
            if url in seen or title.strip().lower() in ("apply", "apply now", "learn more", "view job"):
                continue
            seen.add(url)
            slug_loc = url.split("/JobDetail/")[1].rsplit("/", 1)[0]
            m = re.match(r"(.*?-(?:United-States|United-Kingdom|Japan|China|India|Canada|Netherlands))-", slug_loc)
            slug_loc = m.group(1) if m else slug_loc
            out.append({"id": url.rsplit("/", 1)[-1], "title": unescape(title.strip()),
                        "location": slug_loc.replace("-", " "), "url": url, "posted_ts": None})
        time.sleep(1)
    if not out:
        raise ValueError("Two Sigma careers page layout changed (no job links)")
    return out


def src_oracle(host, site, keywords=("summer internship", "summer analyst", "intern"), pages=2):
    """Oracle Recruiting Cloud (e.g. JPMorgan Chase): public requisition search API.
    Its keyword search is loose ("intern" also hits "internal"), so it searches a few
    phrases sorted by relevance and lets passes_filters() sort out the rest."""
    out, seen = [], set()
    for kw in keywords:
        for page in range(pages):
            finder = (f"findReqs;siteNumber={site},keyword=%22{urllib.parse.quote(kw)}%22,"
                      f"limit=25,offset={page * 25},sortBy=RELEVANCY")
            data = http_json(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                             f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={finder}")
            items = data.get("items") or []
            reqs = (items[0].get("requisitionList") or []) if items else []
            for j in reqs:
                if j.get("Id") in seen:
                    continue
                seen.add(j.get("Id"))
                locs = [j.get("PrimaryLocation") or ""] + [
                    (x.get("Name") or "") for x in (j.get("secondaryLocations") or [])]
                out.append({
                    "id": j.get("Id"), "title": j.get("Title", ""),
                    "location": "; ".join(l for l in locs if l),
                    "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{j.get('Id')}",
                    "posted_ts": iso_ts(j.get("PostedDate")),
                })
            if len(reqs) < 25:
                break
            time.sleep(1)
    return out


def src_tracker(url):
    data = http_json(url, timeout=60)
    out = []
    for x in data:
        if not x.get("active", True) or not x.get("is_visible", True):
            continue
        terms = x.get("terms")
        if terms is not None:
            if not any("Summer 2027" in t for t in terms):
                continue
        elif x.get("season") != "Summer":
            continue
        deg = x.get("degrees") or []
        if deg and "Bachelor's" not in deg:
            continue
        out.append({
            "id": x.get("id") or x.get("url"), "title": x.get("title", ""),
            "company": x.get("company_name", ""),
            "location": "; ".join(x.get("locations") or []),
            "url": x.get("url"), "posted_ts": x.get("date_posted"),
        })
    return out


# ------------------------------------------------------------------ alerts ---

def fmt_et(ts):
    return dt.datetime.fromtimestamp(ts, ET).strftime("%b %d, %I:%M %p ET")


def alert_lines(r):
    return [
        f"{r['title']} at {r['company']}",
        f"Location: {r['location'] or 'not listed'}",
        f"Fit score: {r['score']} ({r['category']}, Tier {r['tier']})",
        f"Opened: {r['opened']}",
        f"Found: {fmt_et(r['detected_ts'])} via {r['source']}",
        f"Apply: {r['url']}",
    ]


def send_ntfy(r, topic, email=None):
    payload = {
        "topic": topic,
        "title": f"Tier {r['tier']}: {r['title']} @ {r['company']}"[:240],
        "message": "\n".join(alert_lines(r)[1:5]),
        "priority": (5 if r["tier"] == "S" else 4) - (1 if r["category"] == "SWE" else 0),
        "tags": ["rotating_light"],
        "click": r["url"],
        "actions": [{"action": "view", "label": "Open posting", "url": r["url"]}],
    }
    if email:
        payload["email"] = email
    headers = {}
    if os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['NTFY_TOKEN']}"
    base = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    try:
        http_json(base + "/", payload, headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        if "email" in payload:
            # push first, even if ntfy refuses the email part
            payload.pop("email")
            http_json(base + "/", payload, headers)
            raise RuntimeError(f"push sent, but email refused: {e.code} {detail}")
        raise RuntimeError(f"{e.code} {detail}")


def send_smtp(r, to):
    user = os.environ["SMTP_USER"].strip()
    pw = os.environ["SMTP_PASS"].replace(" ", "").strip()
    msg = EmailMessage()
    msg["Subject"] = f"[Tier {r['tier']}] {r['title']} at {r['company']} (fit {r['score']})"
    msg["From"] = user
    msg["To"] = to
    lines = alert_lines(r)
    msg.set_content("\n".join(lines) + "\n\nApply early. Sent by your Internship Radar poller.")
    rows = "".join(f"<div style='margin:4px 0'>{escape(l)}</div>" for l in lines[1:5])
    msg.add_alternative(
        f"<div style='font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;font-size:15px'>"
        f"<div style='font-size:11px;font-weight:700;letter-spacing:1px;color:#c0392b'>TIER {escape(r['tier'])}, JUST OPENED</div>"
        f"<h2 style='margin:6px 0 10px;font-size:18px'>{escape(r['title'])} at {escape(r['company'])}</h2>"
        f"{rows}<p><a href='{escape(r['url'])}' style='display:inline-block;background:#2F4FD8;"
        f"color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none'>Open posting</a></p></div>",
        subtype="html")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP_SSL(host, 465, context=ssl.create_default_context(), timeout=30) as s:
        s.login(user, pw)
        s.send_message(msg)


def send_alerts(roles, max_per_run):
    topic = os.environ.get("NTFY_TOPIC")
    email = os.environ.get("ALERT_EMAIL")
    smtp = bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS") and email)
    failures = []
    if not topic and not smtp:
        print("! No NTFY_TOPIC or SMTP secrets set; skipping alerts", file=sys.stderr)
        return ["no alert channel configured"] if roles else []
    for r in roles[:max_per_run]:
        try:
            if topic:
                # ntfy also sends the email unless SMTP is set up
                send_ntfy(r, topic, None if smtp else email)
            if smtp:
                send_smtp(r, email)
        except Exception as e:  # never let one alert kill the run
            failures.append(f"{r['company']} {r['title']}: {e}")
    extra = roles[max_per_run:]
    if extra and topic:
        try:
            http_json(os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/") + "/", {
                "topic": topic, "title": f"+{len(extra)} more Tier S/A roles",
                "message": "\n".join(f"{r['company']}: {r['title']}" for r in extra[:15]),
                "priority": 4})
        except Exception as e:
            failures.append(f"summary push: {e}")
    return failures


# -------------------------------------------------------------------- main ---

def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def build_jobs(cfg):
    jobs = []  # (label, company_cfg or None, callable)
    for c in cfg.get("company", []):
        name = norm(c["name"])
        if c.get("greenhouse"):
            jobs.append((f"greenhouse:{c['greenhouse']}", c, lambda t=c["greenhouse"]: src_greenhouse(t)))
        if c.get("lever"):
            jobs.append((f"lever:{c['lever']}", c, lambda t=c["lever"]: src_lever(t)))
        if c.get("ashby"):
            jobs.append((f"ashby:{c['ashby']}", c, lambda t=c["ashby"]: src_ashby(t)))
        if c.get("workday"):
            jobs.append((f"workday:{name}", c, lambda w=c["workday"]: src_workday(*w)))
        if c.get("oracle"):
            jobs.append((f"oracle:{name}", c, lambda o=c["oracle"]: src_oracle(*o)))
        if c.get("eightfold"):
            jobs.append((f"eightfold:{name}", c, lambda e=c["eightfold"]: src_eightfold(*e)))
        if c.get("amazon"):
            jobs.append(("amazon", c, src_amazon))
        if c.get("google"):
            jobs.append(("google", c, src_google))
        if c.get("tiktok"):
            jobs.append(("tiktok", c, src_tiktok))
        if c.get("janestreet"):
            jobs.append(("janestreet", c, src_janestreet))
        if c.get("apple"):
            jobs.append(("apple", c, src_apple))
        if c.get("ibm"):
            jobs.append(("ibm", c, src_ibm))
        if c.get("bloomberg"):
            jobs.append(("bloomberg", c, src_bloomberg))
        if c.get("microsoft"):
            jobs.append(("microsoft", c, src_microsoft))
        if c.get("meta"):
            jobs.append(("meta", c, src_meta))
        if c.get("twosigma"):
            jobs.append(("twosigma", c, src_twosigma))
    for label, url in (cfg.get("trackers") or {}).items():
        jobs.append((f"tracker:{label}", None, lambda u=url: src_tracker(u)))
    return jobs


def make_resolver(cfg):
    aliases = []
    for c in cfg.get("company", []):
        for n in [c["name"]] + c.get("names", []):
            aliases.append((norm(n), c))
    aliases.sort(key=lambda a: -len(a[0]))

    def resolve(company_name):
        k = norm(company_name)
        for a, c in aliases:
            # exact = true: alias must equal the tracker name (avoids e.g.
            # "Sierra" matching "Sierra Nevada Corporation")
            if a and (k == a if c.get("exact") else k.startswith(a)):
                return c
        return None
    return resolve


def main():
    cfg = tomllib.loads((ROOT / "companies.toml").read_text())
    DATA.mkdir(parents=True, exist_ok=True)
    state = load_json(DATA / "seen.json", {"keys": {}, "titles": {}, "sources_ok": []})
    prev_health = load_json(DATA / "health.json", {})
    sources_ok = set(state.get("sources_ok", []))
    resolve = make_resolver(cfg)
    event = os.environ.get("GITHUB_EVENT_NAME", "local")
    jobs = build_jobs(cfg)

    def run(job):
        label, comp, fn = job
        t0 = time.time()
        try:
            return label, comp, fn(), None, time.time() - t0
        except Exception as e:
            return label, comp, [], f"{type(e).__name__}: {e}"[:300], time.time() - t0

    def run_serial(js):
        out = []
        for i, j in enumerate(js):
            if i:
                time.sleep(3)
            out.append(run(j))
        return out

    serial = [j for j in jobs if j[0].startswith("workday:")]
    parallel = [j for j in jobs if not j[0].startswith("workday:")]
    with ThreadPoolExecutor(max_workers=16) as pool:
        wd_future = pool.submit(run_serial, serial)
        results = list(pool.map(run, parallel)) + wd_future.result()

    health, new_roles, snapshot, snap_keys = {}, [], [], set()
    for label, comp, items, err, secs in sorted(results, key=lambda r: r[0].startswith("tracker:")):
        # direct sources first, so a role found on the company's own board wins
        # over the same role later appearing on a tracker
        matched = 0
        silent = label not in sources_ok  # first successful run of a source: learn, don't alert
        for it in items:
            company_cfg = comp or resolve(it.get("company", ""))
            company = comp["name"] if comp else it.get("company", "")
            title, loc = it.get("title", ""), it.get("location", "")
            if not title or not it.get("url") or not passes_filters(title, loc):
                continue
            matched += 1
            tier = (company_cfg or {}).get("tier", "B")
            score, cat = fit_score(title, loc, tier)
            # promote = ["Data Science", ...] bumps those roles at a lower-tier
            # company to Tier A, so they alert while the company's other roles don't.
            if tier not in ("S", "A") and cat in (company_cfg or {}).get("promote", []):
                tier = "A"
                score, cat = fit_score(title, loc, tier)
            role = {
                "company": company, "title": title, "location": loc, "url": it["url"],
                "tier": tier, "score": score, "category": cat, "source": label,
                "posted_ts": it.get("posted_ts"), "detected_ts": NOW,
            }
            if it.get("posted_ts"):
                role["opened"] = fmt_et(it["posted_ts"])
                role["lag_min"] = round((NOW - it["posted_ts"]) / 60)
            else:
                role["opened"] = it.get("posted_text") or "time not listed"
            key = f"{label}:{it['id']}"
            tkey = f"{norm(company)}|{title_key(title)}"
            if tier in ("S", "A") and tkey not in snap_keys:
                snap_keys.add(tkey)
                snapshot.append(role)
            if key in state["keys"] or tkey in state["titles"]:
                state["keys"].setdefault(key, NOW)
                continue
            state["keys"][key] = NOW
            state["titles"][tkey] = NOW
            # A config or filter change can expose old roles; only treat a role as
            # new if it was posted recently (trackers get a longer window, since
            # they can add a role a few days after the company posts it).
            age = age_days(it)
            if age is not None and age > (3 if comp else 7):
                continue
            if not silent:
                new_roles.append(role)
        health[label] = {"ok": err is None, "fetched": len(items), "matched": matched,
                         "secs": round(secs, 1), **({"error": err} if err else {})}
        if err is None:
            sources_ok.add(label)

    new_roles.sort(key=lambda r: -r["score"])
    alert_tiers = set(cfg.get("alerts", {}).get("tiers", ["S"]))
    to_alert = [r for r in new_roles if r["tier"] in alert_tiers]
    failures = send_alerts(to_alert, int(cfg.get("alerts", {}).get("max_per_run", 8)))

    test_result = None
    if os.environ.get("TEST_ALERT") == "1" or (ROOT / ".test-alert").exists():
        tier_s = [r for r in snapshot if r["tier"] in alert_tiers]
        tier_s.sort(key=lambda r: -r["score"])
        if tier_s:
            t = dict(tier_s[0], title="TEST " + tier_s[0]["title"])
            test_fail = send_alerts([t], 1)
            failures += [f"test: {f}" for f in test_fail]
            test_result = f"sent {fmt_et(time.time())}: {t['company']} {t['title']}" + (
                f" (failed: {test_fail})" if test_fail else "")
        else:
            test_result = "no Tier S/A role in snapshot to use for a test"
        print("Test alert:", test_result)

    if new_roles:
        log = DATA / "new_roles.jsonl"
        lines = log.read_text().splitlines() if log.exists() else []
        lines += [json.dumps(r) for r in new_roles]
        log.write_text("\n".join(lines[-3000:]) + "\n")

    state["sources_ok"] = sorted(sources_ok)
    (DATA / "seen.json").write_text(json.dumps(state, separators=(",", ":")))

    failing = sorted(k for k, v in health.items() if not v["ok"])
    prev_failing = sorted(k for k, v in prev_health.get("sources", {}).items() if not v.get("ok"))
    stale = NOW - prev_health.get("written_ts", 0) > 3600  # hourly heartbeat
    if new_roles or failures or stale or test_result or failing != prev_failing or event in ("push", "workflow_dispatch", "local"):
        (DATA / "health.json").write_text(json.dumps({
            "written_at": fmt_et(NOW), "written_ts": round(NOW), "event": event,
            **({"test_alert": test_result} if test_result else {}), "new_roles": len(new_roles),
            "alerted": len(to_alert), "alert_failures": failures,
            "failing_sources": failing, "sources": health}, indent=1))
    if event in ("push", "workflow_dispatch", "local"):
        snapshot.sort(key=lambda r: -r["score"])
        (DATA / "snapshot.json").write_text(json.dumps(snapshot[:150], indent=1))

    print(f"{len(jobs)} sources, {len(failing)} failing, {len(new_roles)} new roles, "
          f"{len(to_alert)} alerts, {len(failures)} alert failures")
    for r in new_roles[:20]:
        print(f"  [{r['tier']} {r['score']}] {r['company']}: {r['title']} ({r['location']})")


if __name__ == "__main__":
    try:
        main()
        (DATA / "crash.json").unlink(missing_ok=True)
    except Exception:
        import traceback
        (DATA / "crash.json").write_text(json.dumps(
            {"at": fmt_et(time.time()), "error": traceback.format_exc()[-3000:]}, indent=1))
        raise
