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


BROWSER = {"sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"', "sec-ch-ua-mobile": "?0",
           "sec-ch-ua-platform": '"Windows"', "sec-fetch-dest": "document", "sec-fetch-mode": "navigate",
           "sec-fetch-site": "none", "sec-fetch-user": "?1", "upgrade-insecure-requests": "1"}
op = mk()
show("meta browser hdrs", req("https://www.metacareers.com/jobs?q=intern", op=op, headers=BROWSER,
     accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"), [r'/jobs/(\d{6,})', r'"lsd"\s*,\s*\[\]\s*,\s*\{"token":"([^"]+)"', r'"LSD",\[\],\{"token":"([^"]+)"'])
show("meta root", req("https://www.metacareers.com/", op=op, headers=BROWSER, accept="text/html"), [r'"LSD",\[\],\{"token":"([^"]+)"'])
op = mk()
show("ms pcsx p0", req("https://apply.careers.microsoft.com/careers?query=intern", op=op, accept="text/html"))
for q in ["intern", "internship"]:
    code, txt = req(f"https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query={q}&location=United%20States&start=0&sort_by=timestamp", op=op, headers={"Referer":"https://apply.careers.microsoft.com/careers?query=intern"})
    try:
        d = json.loads(txt)["data"]; pos = d["positions"]
        print(f"\nMS {q}: count={d.get('count')} n={len(pos)} keys={list(d.keys())}")
        for p in pos[:12]: print("   ", p["name"], "|", p["locations"][:2], "|", p["postedTs"], "|", p["positionUrl"])
    except Exception as e: print("MS", q, code, txt[:200])
code, txt = req("https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern&location=United%20States&start=10&sort_by=timestamp", op=op, headers={"Referer":"https://apply.careers.microsoft.com/careers?query=intern"})
print("MS page2", code, [p["name"] for p in json.loads(txt)["data"]["positions"]][:5] if code==200 else txt[:100])
for u in ["https://www.uber.com/api/loadSearchJobsResults?localeCode=en-US", "https://www.uber.com/us/en/careers/api/loadSearchJobsResults", "https://www.uber.com/api/careers/loadSearchJobsResults?localeCode=en"]:
    show("uber "+u[22:70], req(u, {"limit": 10, "page": 0, "params": {"query": "intern", "location": [{"country": "USA"}]}}, {"x-csrf-token": "x", "Origin": "https://www.uber.com"}))
show("uber careers html", req("https://www.uber.com/us/en/careers/list/?query=intern", headers=BROWSER, accept="text/html"), [r'/careers/list/(\d{5,})', r'"(/api/[A-Za-z/]+)"'])
code, txt = req("https://www.twosigma.com/careers/students/", accept="text/html")
print("\ntwosigma hrefs", sorted(set(re.findall(r'href="(https?://[^"]*(?:career|job|greenhouse|lever|workday|avature|icims|taleo)[^"]*)"', txt)))[:25])
code, txt = req("https://www.twosigma.com/careers/", accept="text/html")
print("twosigma careers hrefs", sorted(set(re.findall(r'href="(https?://[^"]*(?:career|job|greenhouse|lever|workday|avature|icims|taleo)[^"]*)"', txt)))[:25])
