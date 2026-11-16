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
body = json.dumps({"query": "intern", "filters": {"locations": ["postLocation-USA"]}, "page": 1, "locale": "en-us", "sort": "newest", "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"}}).encode()
with op.open(urllib.request.Request(f"{base}/api/v1/search", data=body, headers=hdr, method="POST"), timeout=20) as r:
    res = json.loads(r.read())["res"]
rows = res["searchResults"]
print(len(rows), sorted(rows[0].keys()))
for j in rows[:20]:
    print({k: (j[k] if not isinstance(j[k], (dict,list)) else str(j[k])[:80]) for k in j if k not in ("jobSummary",)})
