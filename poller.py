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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from html import escape
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
        r"\bbi\b|data platform", re.I)),
    ("Quant", 24, re.compile(r"quant", re.I)),
    ("SWE", 18, re.compile(
        r"software|\bswe\b|\bsde\b|developer|engineer|full.?stack|backend|back.?end|"
        r"front.?end|platform|infrastructure|mobile|\bios\b|android|security|cloud", re.I)),
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
    delays = [3, 8]
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
                wait = min(max(wait, int(ra.strip())), 15)
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


def src_workday(tenant, wd, site, pages=10):
    host = f"{tenant}.{wd}.myworkdayjobs.com"
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    out, total = [], 0
    for page in range(pages):
        data = http_json(api, {"appliedFacets": {}, "limit": 20,
                               "offset": page * 20, "searchText": "intern"})
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
        time.sleep(0.5)
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
        "title": f"Tier S: {r['title']} @ {r['company']}"[:240],
        "message": "\n".join(alert_lines(r)[1:5]),
        "priority": 5 if r["category"] != "SWE" else 4,
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
    msg["Subject"] = f"[Tier S] {r['title']} at {r['company']} (fit {r['score']})"
    msg["From"] = user
    msg["To"] = to
    lines = alert_lines(r)
    msg.set_content("\n".join(lines) + "\n\nApply early. Sent by your Internship Radar poller.")
    rows = "".join(f"<div style='margin:4px 0'>{escape(l)}</div>" for l in lines[1:5])
    msg.add_alternative(
        f"<div style='font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;font-size:15px'>"
        f"<div style='font-size:11px;font-weight:700;letter-spacing:1px;color:#c0392b'>TIER S, JUST OPENED</div>"
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
                "topic": topic, "title": f"+{len(extra)} more Tier S roles",
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
            if a and k.startswith(a):
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

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(run, jobs))

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
            # A config or filter change can expose old roles on a company board;
            # only treat a direct-source role as new if it was posted recently.
            age = age_days(it) if comp else None
            if age is not None and age > 3:
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

    if os.environ.get("TEST_ALERT") == "1":
        tier_s = [r for r in snapshot if r["tier"] == "S"]
        tier_s.sort(key=lambda r: -r["score"])
        if tier_s:
            t = dict(tier_s[0], title="TEST " + tier_s[0]["title"])
            failures += [f"test: {f}" for f in send_alerts([t], 1)]
            print("Sent test alert:", t["company"], t["title"])

    if new_roles:
        log = DATA / "new_roles.jsonl"
        lines = log.read_text().splitlines() if log.exists() else []
        lines += [json.dumps(r) for r in new_roles]
        log.write_text("\n".join(lines[-3000:]) + "\n")

    state["sources_ok"] = sorted(sources_ok)
    (DATA / "seen.json").write_text(json.dumps(state, separators=(",", ":")))

    failing = sorted(k for k, v in health.items() if not v["ok"])
    prev_failing = sorted(k for k, v in prev_health.get("sources", {}).items() if not v.get("ok"))
    if new_roles or failures or failing != prev_failing or event in ("push", "workflow_dispatch", "local"):
        (DATA / "health.json").write_text(json.dumps({
            "written_at": fmt_et(NOW), "event": event, "new_roles": len(new_roles),
            "alerted": len(to_alert), "alert_failures": failures,
            "failing_sources": failing, "sources": health}, indent=1))
    if event in ("push", "workflow_dispatch", "local"):
        snapshot.sort(key=lambda r: -r["score"])
        (DATA / "snapshot.json").write_text(json.dumps(snapshot[:150], indent=1))

    print(f"{len(jobs)} sources, {len(failing)} failing, {len(new_roles)} new roles, "
          f"{len(to_alert)} Tier S alerts, {len(failures)} alert failures")
    for r in new_roles[:20]:
        print(f"  [{r['tier']} {r['score']}] {r['company']}: {r['title']} ({r['location']})")


if __name__ == "__main__":
    main()
