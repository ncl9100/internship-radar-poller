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

H = dict(BROWSER)
for u in ["https://www.metacareers.com/jobs/sitemap.xml", "https://www.metacareers.com/jobsearch/sitemap.xml", "https://www.metacareers.com/sitemap.xml"]:
    show("meta "+u[28:], req(u, headers=H, accept="text/html,application/xml;q=0.9,*/*;q=0.8"), [r'<loc>([^<]+)</loc>'])
code, txt = req("https://www.metacareers.com/jobs?q=intern", headers=H, accept="text/html")
for kw in ["CareersJobSearch", "JobSearch", "doc_id", "queryID", "intern"]:
    idx = [m.start() for m in re.finditer(kw, txt)][:3]
    print("META", kw, len(re.findall(kw, txt)), [txt[max(0,i-120):i+160].replace("\n"," ") for i in idx[:2]])
code, txt = req("https://www.uber.com/us/en/careers/list/?query=intern", headers=H, accept="text/html")
print("\nUBER next data:", "__NEXT_DATA__" in txt, "self.__next_f" in txt)
for kw in ["intern", "Intern", "jobId", "/careers/list/", "api"]:
    idx = [m.start() for m in re.finditer(kw, txt)][:3]
    print("UBER", kw, len(re.findall(kw, txt)), [txt[max(0,i-100):i+140].replace("\n"," ") for i in idx[:2]])
code, txt = req("https://careers.twosigma.com/", headers=H, accept="text/html")
print("\nTWOSIGMA root", code, len(txt), sorted(set(re.findall(r'(?:href|src|action)="([^"]{5,140})"', txt)))[:40])
