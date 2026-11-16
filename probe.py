import json, re, urllib.request, urllib.error, http.cookiejar
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
def mk(): return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def req(url, payload=None, headers=None, op=None, accept="application/json"):
    h = {"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}; h.update(headers or {})
    body = json.dumps(payload).encode() if payload is not None else None
    if body: h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method="POST" if body else "GET")
    try:
        with (op or mk()).open(r, timeout=25) as resp: return resp.status, resp.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")[:400]
    except Exception as e: return "ERR", str(e)[:200]
def show(name, res, pats=()):
    code, txt = res
    print(f"\n### {name}: {code} len={len(txt)}")
    try:
        d = json.loads(txt); print("  json:", json.dumps(d)[:700])
    except Exception:
        print("  text:", re.sub(r"\s+"," ",txt[:300]))
    for p in pats:
        m = re.findall(p, txt); print(f"  /{p[:50]}/ -> {len(m)} e.g. {m[:6]}")

# ---- Meta
op = mk()
show("meta jobsearch html", req("https://www.metacareers.com/jobsearch?q=intern&roles[0]=Internship", op=op, accept="text/html"),
     [r'/jobs/(\d{6,})', r'"title":"([^"]{5,120})"', r'"lsd","([^"]+)"|name="lsd" value="([^"]+)"'])
show("meta sitemap", req("https://www.metacareers.com/jobs/sitemap.xml", accept="application/xml"), [r'<loc>([^<]+)</loc>'])
show("meta jobs html", req("https://www.metacareers.com/jobs?q=intern", accept="text/html"), [r'/jobs/(\d{6,})', r'doc_id[^0-9]{0,10}(\d{10,})'])
# ---- Microsoft
show("ms gcs", req("https://gcsservices.careers.microsoft.com/search/api/v1/search?q=intern&lc=United%20States&l=en_us&pg=1&pgSz=20&o=Recent&flt=true",
     headers={"Origin":"https://jobs.careers.microsoft.com","Referer":"https://jobs.careers.microsoft.com/"}))
op = mk()
show("ms eightfold landing", req("https://apply.careers.microsoft.com/careers?query=intern", op=op, accept="text/html"), [r'csrf[^"]{0,20}"\s*content="([^"]+)"'])
show("ms pcsx", req("https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern&location=United%20States&start=0&sort_by=timestamp", op=op,
     headers={"Referer":"https://apply.careers.microsoft.com/careers?query=intern"}))
show("ms apply v2", req("https://apply.careers.microsoft.com/api/apply/v2/jobs?domain=microsoft.com&query=intern&location=United%20States&start=0&num=10&sort_by=timestamp", op=op,
     headers={"Referer":"https://apply.careers.microsoft.com/careers?query=intern"}))
# ---- Uber
show("uber api", req("https://www.uber.com/api/loadSearchJobsResults?localeCode=en",
     {"limit": 10, "page": 0, "params": {"query": "intern", "location": [{"country": "USA"}], "department": [], "team": [], "programAndPlatform": [], "lineOfBusinessName": []}},
     {"x-csrf-token": "x", "Origin": "https://www.uber.com", "Referer": "https://www.uber.com/us/en/careers/list/"}))
show("uber api2", req("https://www.uber.com/api/loadSearchJobsResults?localeCode=en",
     {"limit": 10, "page": 0, "params": {"query": "intern"}}, {"x-csrf-token": "x"}))
# ---- Citadel
show("citadel internships", req("https://www.citadel.com/careers/open-opportunities/students/internships/", accept="text/html"),
     [r'href="(https://www\.citadel\.com/careers/details/[^"]+)"', r'<h\d[^>]*>([^<]*[Ii]ntern[^<]*)</h'])
show("citadel sec internships", req("https://www.citadelsecurities.com/careers/open-opportunities/students/internships/", accept="text/html"),
     [r'href="(https://www\.citadelsecurities\.com/careers/details/[^"]+)"'])
show("citadel wp-json", req("https://www.citadel.com/wp-json/wp/v2/types"), [r'"(career[^"]*|job[^"]*|opportunit[^"]*)"'])
# ---- Two Sigma
show("twosigma avature", req("https://careers.twosigma.com/careers/SearchJobs/?jobRecordsPerPage=100", accept="text/html"),
     [r'href="(https://careers\.twosigma\.com/careers/JobDetail/[^"]+)"'])
show("twosigma students", req("https://www.twosigma.com/careers/students/", accept="text/html"), [r'href="([^"]*(?:JobDetail|jobs?/)[^"]*)"'])
