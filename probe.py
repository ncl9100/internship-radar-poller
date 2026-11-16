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
    j = json.loads(m.group(1))[0][1]
    for i, v in enumerate(j):
        if i in (3, 4) or (isinstance(v, str) and len(v) > 300): continue
        print(i, json.dumps(v)[:300])
sec("google", google)
def tiktok():
    d = req("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts", {"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [], "location_code_list": [], "keyword": "data scientist intern", "limit": 3, "offset": 0}, {"website-path": "tiktok", "Origin": "https://lifeattiktok.com", "Referer": "https://lifeattiktok.com/"})
    print("count", d["data"].get("count"))
    for j in d["data"]["job_post_list"][:2]:
        print(json.dumps({k: v for k, v in j.items() if k not in ("description", "requirement")})[:1500])
sec("tiktok", tiktok)
def js():
    d = req("https://www.janestreet.com/jobs/main.json")
    for k in ("availability", "duration", "category", "city"): print(k, sorted({str(x.get(k)) for x in d})[:25])
    ints = [x for x in d if "intern" in json.dumps({k: x.get(k) for k in ("availability", "duration", "position")}).lower()]
    print("n intern", len(ints))
    for x in ints[:4]: print(json.dumps({k: (v[:60] if isinstance(v, str) else v) for k, v in x.items()}))
sec("jane street", js)
