import json, time, urllib.request, urllib.error, http.cookiejar
UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
def req(url, payload=None, headers=None, opener=None, ua=UA_BROWSER):
    h = {"User-Agent": ua, "Accept": "application/json"}
    h.update(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode(); h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=h, method="POST" if body else "GET")
    t = time.time()
    try:
        with (opener or urllib.request.build_opener()).open(r, timeout=20) as resp:
            txt = resp.read().decode("utf-8", "replace")
            return resp.status, txt, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200], time.time() - t
    except Exception as e:
        return "ERR", str(e)[:200], time.time() - t

def summarize(name, res):
    code, txt, secs = res
    info = ""
    try:
        d = json.loads(txt)
        if isinstance(d, dict):
            info = "keys=" + ",".join(list(d.keys())[:6])
            for k in ("total", "totalCount", "count"):
                if k in d: info += f" {k}={d[k]}"
            for k in ("jobPostings", "jobs", "positions", "searchResults", "res"):
                if k in d and isinstance(d[k], list):
                    info += f" n_{k}={len(d[k])}"
                    if d[k]: info += " first=" + json.dumps(d[k][0])[:160]
        elif isinstance(d, list): info = f"list n={len(d)}"
    except Exception:
        info = "nonjson " + txt[:120].replace("\n", " ")
    print(f"{name:40s} {code} {secs:.1f}s {info}", flush=True)

WD = [("nvidia","wd5","NVIDIAExternalCareerSite"),("salesforce","wd12","External_Career_Site"),
      ("adobe","wd5","external_experienced"),("capitalone","wd12","Capital_One"),
      ("snapchat","wd1","snap"),("walmart","wd5","WalmartExternal"),("twosigma","wd1","Careers"),
      ("ibm","wd5","IBM_Careers"), ("bloomberg","wd1","Bloomberg")]
WD_PAYLOAD = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"}

print("== workday: old UA, plain POST, back to back")
for t,w,s in WD[:3]:
    summarize(f"plain-oldUA {t}", req(f"https://{t}.{w}.myworkdayjobs.com/wday/cxs/{t}/{s}/jobs", WD_PAYLOAD, ua="Mozilla/5.0 (X11; Linux x86_64) internship-radar-poller"))
print("== workday: browser headers + session cookie, 2s apart")
for t,w,s in WD:
    cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    host = f"https://{t}.{w}.myworkdayjobs.com"
    c0 = req(f"{host}/en-US/{s}", headers={"Accept": "text/html"}, opener=op)
    hdr = {"Accept-Language": "en-US", "Origin": host, "Referer": f"{host}/en-US/{s}"}
    for ck in cj:
        if ck.name == "CALYPSO_CSRF_TOKEN": hdr["X-CALYPSO-CSRF-TOKEN"] = ck.value
    print(f"   landing {t}: {c0[0]} cookies={[c.name for c in cj]}")
    summarize(f"session {t}", req(f"{host}/wday/cxs/{t}/{s}/jobs", WD_PAYLOAD, hdr, op))
    time.sleep(2)

print("== workday: 10 rapid pages nvidia (current behavior)")
for p in range(4):
    summarize(f"nvidia page {p}", req("https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs", dict(WD_PAYLOAD, offset=p*20)))
    time.sleep(0.5)

print("== candidates")
for tok in ["wehrtyou","hudsonrivertrading","etsy","twosigma","citadel","citadelsecurities","shopify","snap","bloomberg","uber","capitalone"]:
    summarize(f"greenhouse {tok}", req(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs"))
for org in ["shopify","uber","snap"]:
    summarize(f"lever {org}", req(f"https://api.lever.co/v0/postings/{org}?mode=json&limit=5"))
    summarize(f"ashby {org}", req(f"https://api.ashbyhq.com/posting-api/job-board/{org}"))
summarize("eightfold microsoft", req("https://apply.careers.microsoft.com/api/apply/v2/jobs?domain=microsoft.com&query=intern&location=United%20States&start=0&num=10&sort_by=timestamp"))
summarize("eightfold microsoft pcsx", req("https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern&location=United%20States&start=0&sort_by=timestamp"))
summarize("uber api", req("https://www.uber.com/api/loadSearchJobsResults?localeCode=en", {"params":{"query":"intern","location":[{"country":"USA"}],"department":[],"team":[]},"page":0,"limit":10}, {"x-csrf-token":"x","Origin":"https://www.uber.com","Referer":"https://www.uber.com/us/en/careers/list/"}))
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
tok = req("https://jobs.apple.com/api/v1/CSRFToken", headers={"Referer":"https://jobs.apple.com/en-us/search"}, opener=op)
print("apple csrf", tok[0], tok[1][:80])
summarize("apple search", req("https://jobs.apple.com/api/role/search", {"query":"intern","filters":{"range":{"standardWeeklyHours":{"start":None,"end":None}},"locations":["postLocation-USA"]},"page":1,"locale":"en-us","sort":"newest"}, {"Origin":"https://jobs.apple.com","Referer":"https://jobs.apple.com/en-us/search","x-apple-csrf-token": ""}, op))
summarize("apple v1 search", req("https://jobs.apple.com/api/v1/search", {"query":"intern","filters":{"locations":["postLocation-USA"]},"page":1,"locale":"en-us","sort":"newest","format":{"longDate":"MMMM D, YYYY","mediumDate":"MMM D, YYYY"}}, {"Origin":"https://jobs.apple.com","Referer":"https://jobs.apple.com/en-us/search"}, op))
summarize("shopify careers json", req("https://www.shopify.com/careers.json"))
summarize("bloomberg avature", req("https://bloomberg.avature.net/careers/SearchJobs/intern?jobRecordsPerPage=10"))
summarize("ibm careers api", req("https://www-api.ibm.com/search/api/v2", {"appId":"careers","scopes":["careers2"],"query":{"bool":{"must":[{"simple_query_string":{"query":"intern","fields":["keywords^1","body^1","url^2","description^2","h1s_content^2","title^3","field_text_01"]}}]}},"size":10,"sort":[{"_score":"desc"},{"pageviews":"desc"}],"lang":"zz","localeSelector":{},"sm":{"query":"intern","lang":"zz"},"_source":["_id","title","url","description","language","entitled","field_keyword_17","field_keyword_08","field_keyword_18","field_keyword_19"]}))
