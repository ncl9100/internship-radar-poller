import json, re, sys, time, urllib.request, urllib.error, importlib.util
spec = importlib.util.spec_from_file_location("p", "poller.py"); p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
UA = p.UA
def req(url, data=None, headers=None, raw=False, method=None):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json, text/html"}
    h.update(headers or {})
    b = json.dumps(data).encode() if isinstance(data, (dict, list)) else data
    if b is not None and "Content-Type" not in h: h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=b, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=25) as resp:
        body = resp.read().decode("utf-8", "replace")
        return (body, resp.headers) if raw else json.loads(body)
DS = re.compile(r"data|analyt|machine learning|\bml\b|scien|quant", re.I)
def show(name, fn):
    print(f"\n=== {name}")
    try:
        t = time.time(); v = fn(); print(f"OK {time.time()-t:.1f}s", v if isinstance(v, str) else "")
    except Exception as e:
        print("FAIL", type(e).__name__, str(e)[:300])

# 1. Configured Tier S sources, with intern / DS-intern titles
import tomllib
cfg = tomllib.loads(open("companies.toml").read())
for label, c, fn in p.build_jobs(cfg):
    if not c or c.get("tier") != "S": continue
    def f(fn=fn):
        rows = fn(); interns = [r["title"] for r in rows if re.search(r"intern", r["title"], re.I)]
        ds = [t for t in interns if DS.search(t)]
        return f"fetched={len(rows)} intern={len(interns)} ds_intern={len(ds)} sample={ds[:4] or interns[:3]}"
    show(label, f)

# 2. Workday totals (is the 3-page cap cutting results?)
for c in cfg["company"]:
    if c.get("workday"):
        t, wd, site = c["workday"]
        show(f"workday total {c['name']}", lambda t=t, wd=wd, site=site: f"total={req(f'https://{t}.{wd}.myworkdayjobs.com/wday/cxs/{t}/{site}/jobs', {'appliedFacets': {}, 'limit': 20, 'offset': 0, 'searchText': 'intern'}).get('total')}")
        time.sleep(2)

# 3. Candidate direct sources for uncovered Tier S companies
def apple():
    body, h = req("https://jobs.apple.com/api/v1/CSRFToken", raw=True)
    tok = h.get("X-Apple-CSRF-Token")
    d = req("https://jobs.apple.com/api/v1/search", {"query": "intern", "filters": {"locations": ["postLocation-USA"]}, "page": 1, "locale": "en-us", "sort": "newest"}, {"X-Apple-CSRF-Token": tok or ""})
    res = d.get("res", d)
    return f"keys={list(d)[:6]} total={res.get('totalRecords')} sample={[x.get('postingTitle') for x in res.get('searchResults', [])[:4]]}"
show("apple", apple)
def apple_html():
    body, _ = req("https://jobs.apple.com/en-us/search?search=intern&sort=newest&location=united-states-USA", raw=True)
    return f"len={len(body)} hydration={'__staticRouterHydrationData' in body} titles={re.findall(r'postingTitle\":\"([^\"]+)', body)[:4]}"
show("apple html", apple_html)
def msft():
    d = req("https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern&location=United%20States&start=0&sort_by=timestamp")
    pos = (d.get("data") or {}).get("positions", [])
    return f"count={(d.get('data') or {}).get('count')} sample={[x.get('name') for x in pos[:4]]}"
show("microsoft pcsx", msft)
def msft_old():
    d = req("https://gcsservices.careers.microsoft.com/search/api/v1/search?q=intern&lc=United%20States&l=en_us&pg=1&pgSz=20&o=Recent")
    r = d["operationResult"]["result"]; return f"total={r.get('totalJobs')} sample={[j['title'] for j in r['jobs'][:4]]}"
show("microsoft gcs", msft_old)
def google():
    body, _ = req("https://www.google.com/about/careers/applications/jobs/results?q=intern&location=United%20States&target_level=INTERN_AND_APPRENTICE&sort_by=date", raw=True)
    m = re.search(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(\[.*?\]), sideChannel", body, re.S)
    if not m: return f"len={len(body)} no ds:1 blob"
    data = json.loads(m.group(1)); jobs = data[0]
    return f"jobs_on_page={len(jobs)} total={data[2] if len(data)>2 else '?'} sample={[j[1] for j in jobs[:4]]}"
show("google", google)
def uber():
    d = req("https://www.uber.com/api/loadSearchJobsResults?localeCode=en", {"params": {"query": "intern", "location": [], "department": [], "team": []}, "page": 0, "limit": 50}, {"x-csrf-token": "x"})
    r = d.get("data", {}); return f"total={r.get('totalResults')} sample={[x.get('title') for x in (r.get('results') or [])[:4]]}"
show("uber", uber)
def tiktok():
    d = req("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts", {"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [], "location_code_list": ["CT_1103355", "CT_157", "CT_1000001"], "keyword": "intern", "limit": 50, "offset": 0}, {"website-path": "tiktok", "Origin": "https://lifeattiktok.com", "Referer": "https://lifeattiktok.com/"})
    r = d.get("data", {}); return f"code={d.get('code')} total={r.get('count')} sample={[x.get('title') for x in (r.get('job_post_list') or [])[:4]]}"
show("tiktok", tiktok)
def janestreet():
    d = req("https://www.janestreet.com/jobs/main.json")
    ints = [x for x in d if "intern" in json.dumps(x).lower()]
    return f"total={len(d)} intern={len(ints)} keys={list(d[0])[:8] if d else []} sample={[x.get('position') for x in ints[:4]]}"
show("jane street", janestreet)
def citadel():
    body, _ = req("https://www.citadel.com/careers/open-opportunities/students/internships/", raw=True)
    return f"len={len(body)} titles={re.findall(r'<h2[^>]*>([^<]*[Ii]ntern[^<]*)</h2>', body)[:5]}"
show("citadel html", citadel)
def citadel_s():
    body, _ = req("https://www.citadelsecurities.com/careers/open-opportunities/students/internships/", raw=True)
    return f"len={len(body)} titles={re.findall(r'<h2[^>]*>([^<]*[Ii]ntern[^<]*)</h2>', body)[:5]}"
show("citadel securities html", citadel_s)
def twosigma():
    body, _ = req("https://careers.twosigma.com/careers/SearchJobs/intern", raw=True)
    return f"len={len(body)} titles={re.findall(r'class=\"[^\"]*title[^\"]*\"[^>]*>\s*<a[^>]*>([^<]+)', body)[:5]}"
show("two sigma avature", twosigma)
def meta():
    body, _ = req("https://www.metacareers.com/jobs?q=intern", raw=True)
    return f"len={len(body)} lsd={'\"LSD\"' in body} titles={re.findall(r'\"title\":\"([^\"]*Intern[^\"]*)', body)[:4]}"
show("meta html", meta)
