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
code, sm = req("https://www.metacareers.com/jobs/sitemap.xml", headers=H, accept="text/html,application/xml;q=0.9,*/*;q=0.8")
urls = re.findall(r'<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>', sm)
urls.sort(key=lambda x: x[1], reverse=True)
print("META newest lastmods:", [u[1] for u in urls[:5]], "oldest:", [u[1] for u in urls[-3:]])
for u, lm in urls[:4]:
    code, t = req(u, headers=H, accept="text/html")
    title = re.findall(r'<title[^>]*>([^<]*)</title>', t)
    og = re.findall(r'property="og:title" content="([^"]*)"', t)
    loc = re.findall(r'"locations?":\s*\[?"?([^"\]]{3,80})', t)[:3]
    jt = re.findall(r'"title":"([^"]{5,140})"', t)[:4]
    print("META job", code, len(t), u[-20:], "| title:", title[:1], "| og:", og[:1], "| jsontitle:", jt, "| loc:", loc)
code, txt = req("https://www.uber.com/us/en/careers/list/?query=intern", headers=H, accept="text/html")
blob = txt.replace('\\"', '"')
for pat in [r'"id":(\d{5,}),"title":"([^"]{5,140})"', r'"title":"([^"]{5,140})","id":(\d{5,})', r'"jobId":"?(\d+)', r'"(?:title|name)":"([^"]*Intern[^"]*)"']:
    m = re.findall(pat, blob); print("UBER", pat[:40], len(m), m[:6])
i = blob.find('"title":"'); print("UBER ctx", blob[max(0,i-300):i+300])
code, txt = req("https://careers.twosigma.com/", headers=H, accept="text/html")
print("TS links", sorted(set(re.findall(r'href="([^"]*(?:Search|Job|job|Career|careers)[^"]*)"', txt)))[:30])
for u in ["https://careers.twosigma.com/careers/SearchJobs", "https://careers.twosigma.com/careers/SearchJobs/?listFilterMode=1", "https://careers.twosigma.com/en_US/careers/SearchJobs"]:
    code, t = req(u, headers=H, accept="text/html")
    print("TS", u, code, len(t), re.findall(r'href="([^"]*JobDetail[^"]*)"[^>]*>\s*([^<]{3,120})', t)[:5])
