"""One-off probe: JPMorgan reader and Visa search endpoint. No alerts or state changes."""
import importlib.util, json, pathlib, urllib.request
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

try:
    jobs = p.src_oracle("jpmc.fa.oraclecloud.com", "CX_1001")
    passing = [f'{j["title"]} | {j["location"]}' for j in jobs if p.passes_filters(j["title"], j["location"])]
    print(json.dumps({"src": "jpmorgan", "fetched": len(jobs), "pass": len(passing), "sample": passing[:10]}))
except Exception as e:
    print(json.dumps({"src": "jpmorgan", "err": str(e)[:200]}))

bodies = [
    {"query": "intern", "from": 0, "size": 20},
    {"q": "intern", "from": 0, "size": 20, "lang": "en_US"},
    {"keyword": "intern", "from": 0, "size": 20},
]
for b in bodies:
    try:
        req = urllib.request.Request("https://search.visa.com/CAREERS/careers/jobs?lang=en_US",
                                     data=json.dumps(b).encode(), method="POST",
                                     headers={"User-Agent": p.UA, "Content-Type": "application/json",
                                              "Accept": "application/json",
                                              "Origin": "https://corporate.visa.com",
                                              "Referer": "https://corporate.visa.com/en/jobs/"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
        print(json.dumps({"src": "visa", "body_sent": b, "len": len(body), "head": body[:900]}))
    except Exception as e:
        extra = ""
        if hasattr(e, "read"):
            try: extra = e.read().decode()[:300]
            except Exception: pass
        print(json.dumps({"src": "visa", "body_sent": b, "err": str(e)[:150], "resp": extra}))
