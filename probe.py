import json, urllib.request, http.cookiejar
UA = "Mozilla/5.0 (X11; Linux x86_64) internship-radar-poller"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
base = "https://jobs.apple.com"
hdr = {"User-Agent": UA, "Accept": "application/json", "Origin": base, "Referer": f"{base}/en-us/search"}
with op.open(urllib.request.Request(f"{base}/api/v1/CSRFToken", headers=hdr), timeout=20) as r:
    print("csrf hdrs", {k:v[:20] for k,v in r.headers.items() if 'csrf' in k.lower()})
    tok = r.headers.get("X-Apple-CSRF-Token") or ""
if tok: hdr["X-Apple-CSRF-Token"] = tok
hdr["Content-Type"] = "application/json"

for name, filt, q in [
  ("query-relevance", {"locations": ["postLocation-USA"]}, "intern"),
  ("students team", {"locations": ["postLocation-USA"], "teams": [{"team": "teamsAndSubTeams-STDNT"}]}, ""),
  ("students+itrshp", {"locations": ["postLocation-USA"], "teams": [{"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-ITRSHP"}]}, ""),
]:
    for sort in (["relevance"] if name=="query-relevance" else ["newest"]):
        body = json.dumps({"query": q, "filters": filt, "page": 1, "locale": "en-us", "sort": sort, "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"}}).encode()
        try:
            with op.open(urllib.request.Request(f"{base}/api/v1/search", data=body, headers=hdr, method="POST"), timeout=20) as r:
                res = json.loads(r.read())["res"]
            rows=res["searchResults"]
            print(name, sort, res.get("totalRecords"), [ (j["postingTitle"], j["postingDate"], j.get("team",{}).get("teamID"), j.get("team",{}).get("teamCode")) for j in rows[:8]])
        except Exception as e: print(name, e)
