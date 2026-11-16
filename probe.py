import json, time, urllib.request, urllib.error, http.cookiejar, re
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
def req(url, payload=None, headers=None, opener=None):
    h = {"User-Agent": UA, "Accept": "application/json"}; h.update(headers or {})
    body = json.dumps(payload).encode() if payload is not None else None
    if body: h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=h, method="POST" if body else "GET")
    try:
        with (opener or urllib.request.build_opener()).open(r, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
WD = [("nvidia","wd5","NVIDIAExternalCareerSite"),("salesforce","wd12","External_Career_Site"),
      ("adobe","wd5","external_experienced"),("capitalone","wd12","Capital_One"),("snapchat","wd1","snap")]
INT = re.compile(r"\bintern", re.I)
def walk(f, path=""):
    for x in f:
        yield path + x.get("facetParameter",""), x
        if x.get("values") and isinstance(x["values"], list) and x["values"] and "facetParameter" in x["values"][0]:
            yield from walk(x["values"], path + x.get("facetParameter","") + ">")
for t,w,s in WD:
    api = f"https://{t}.{w}.myworkdayjobs.com/wday/cxs/{t}/{s}/jobs"
    code, txt = req(api, {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"})
    if code != 200: print(t, code, txt[:100]); continue
    d = json.loads(txt)
    print(f"\n{t}: total={d['total']}")
    us = None
    for p, f in walk(d.get("facets", [])):
        vals = f.get("values") or []
        names = [v.get("descriptor") for v in vals if "descriptor" in v]
        print("  facet", p, f.get("descriptor"), names[:8])
        for v in vals:
            if v.get("descriptor") in ("United States of America", "United States", "USA") and us is None:
                us = (f["facetParameter"], v["id"], v.get("count"))
    print("  US facet:", us)
    for st in ["intern", "intern 2027", "summer 2027 intern"]:
        af = {us[0]: [us[1]]} if us else {}
        code, txt = req(api, {"appliedFacets": af, "limit": 20, "offset": 0, "searchText": st})
        if code == 200:
            dd = json.loads(txt); titles = [j["title"] for j in dd["jobPostings"]]
            print(f"  search {st!r} US={bool(us)}: total={dd['total']} intern-titles on p1={sum(bool(INT.search(x)) for x in titles)}/20 posted={[j.get('postedOn') for j in dd['jobPostings'][:5]]}")
        else: print("  ", st, code)
        time.sleep(1)
    time.sleep(2)
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
req("https://jobs.apple.com/api/v1/CSRFToken", headers={"Referer":"https://jobs.apple.com/en-us/search"}, opener=op)
code, txt = req("https://jobs.apple.com/api/v1/search", {"query":"intern","filters":{"locations":["postLocation-USA"]},"page":1,"locale":"en-us","sort":"newest","format":{"longDate":"MMMM D, YYYY","mediumDate":"MMM D, YYYY"}}, {"Origin":"https://jobs.apple.com","Referer":"https://jobs.apple.com/en-us/search"}, op)
d = json.loads(txt)["res"]; print("\napple keys", list(d.keys()), d.get("totalRecords"))
for j in d.get("searchResults", [])[:4]: print(json.dumps(j)[:500])
code, txt = req("https://www-api.ibm.com/search/api/v2", {"appId":"careers","scopes":["careers2"],"query":{"bool":{"must":[{"simple_query_string":{"query":"intern","fields":["title^3","description^2"]}}]}},"size":5,"sort":[{"dcdate":"desc"}],"lang":"zz","localeSelector":{},"sm":{"query":"intern","lang":"zz"},"_source":["_id","title","url","description","field_keyword_17","field_keyword_08","field_keyword_18","field_keyword_19","dcdate"]})
print("\nibm", code); 
try:
    d=json.loads(txt); print(d["hits"]["total"]); [print(json.dumps(h)[:500]) for h in d["hits"]["hits"][:4]]
except Exception as e: print(txt[:300])
code, txt = req("https://bloomberg.avature.net/careers/SearchJobs/intern?jobRecordsPerPage=10", headers={"Accept":"text/html"})
print("\nbloomberg", code, len(txt)); print(re.findall(r'href="(https://bloomberg.avature.net/careers/JobDetail/[^"]+)"[^>]*>\s*([^<]{3,120})', txt)[:8])
