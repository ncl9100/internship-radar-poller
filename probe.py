import json, re, urllib.request
def req(url, data=None, headers=None, raw=False):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json, text/html"}
    h.update(headers or {})
    b = json.dumps(data).encode() if data is not None else None
    if b: h["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=b, headers=h), timeout=25) as r:
        body = r.read().decode("utf-8", "replace"); return body if raw else json.loads(body)
def sec(n, f):
    print("\n=== " + n)
    try: f()
    except Exception as e: print("FAIL", type(e).__name__, e)
def google():
    body = req("https://www.google.com/about/careers/applications/jobs/results?q=intern&location=United%20States&target_level=INTERN_AND_APPRENTICE&sort_by=date", raw=True)
    m = re.search(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(\[.*?\]), sideChannel", body, re.S)
    data = json.loads(m.group(1)); print("top len", len(data), "data[1:]", json.dumps(data[1:])[:200])
    for j in data[0][:2]: print(json.dumps(j)[:1500])
    body2 = req("https://www.google.com/about/careers/applications/jobs/results?q=intern&location=United%20States&target_level=INTERN_AND_APPRENTICE&sort_by=date&page=2", raw=True)
    m2 = re.search(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(\[.*?\]), sideChannel", body2, re.S)
    print("page2 count", len(json.loads(m2.group(1))[0]) if m2 else "none")
    body3 = req("https://www.google.com/about/careers/applications/jobs/results?location=United%20States&target_level=INTERN_AND_APPRENTICE&sort_by=date", raw=True)
    m3 = re.search(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(\[.*?\]), sideChannel", body3, re.S)
    d3 = json.loads(m3.group(1)); print("no-q count", len(d3[0]), "meta", json.dumps(d3[1:])[:100], [j[1] for j in d3[0]])
sec("google", google)
def tiktok():
    d = req("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts", {"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [], "location_code_list": [], "keyword": "intern", "limit": 3, "offset": 0}, {"website-path": "tiktok", "Origin": "https://lifeattiktok.com", "Referer": "https://lifeattiktok.com/"})
    print("count no-loc", d["data"].get("count"))
    for j in d["data"]["job_post_list"][:2]: print(json.dumps(j)[:1500])
sec("tiktok", tiktok)
def js():
    d = req("https://www.janestreet.com/jobs/main.json")
    ints = [x for x in d if "intern" in (x.get("availability", "") + x.get("duration", "") + x.get("position", "")).lower()]
    print("avail values", sorted({x.get("availability") for x in d}), "dur", sorted({x.get("duration") for x in d})[:20])
    for x in ints[:3]: print(json.dumps({k: (v[:80] if isinstance(v, str) else v) for k, v in x.items()}))
sec("jane street", js)
def apple():
    body = req("https://jobs.apple.com/en-us/search?search=intern&sort=newest&location=united-states-USA", raw=True)
    i = body.find("__staticRouterHydrationData"); s = body[i:i+300000]
    k = s.find("searchResults"); print(s[k:k+1500])
sec("apple", apple)
