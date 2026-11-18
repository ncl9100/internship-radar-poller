"""One-off check of new custom sources. Prints a report; no alerts or state changes."""
import importlib.util, json, pathlib, time
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
TESTS = [
    ("JPMorgan", lambda: p.src_oracle("jpmc.fa.oraclecloud.com", "CX_1001")),
    ("JPMorgan CX_1002", lambda: p.src_oracle("jpmc.fa.oraclecloud.com", "CX_1002")),
    ("Visa (SR Visa)", lambda: p.src_smartrecruiters("Visa")),
    ("Visa (SR VisaInc)", lambda: p.src_smartrecruiters("VisaInc")),
]
for name, fn in TESTS:
    try:
        jobs = fn()
        passing = [f'{j["title"]} | {j["location"]}' for j in jobs if p.passes_filters(j["title"], j["location"])]
        print(json.dumps({"source": name, "ok": True, "fetched": len(jobs), "pass": len(passing),
                          "sample": passing[:6] or [j["title"] for j in jobs[:4]],
                          "url_example": jobs[0]["url"] if jobs else None,
                          "posted_example": jobs[0]["posted_ts"] if jobs else None}))
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            try: body = e.read().decode()[:200]
            except Exception: pass
        print(json.dumps({"source": name, "ok": False, "error": f"{type(e).__name__}: {e}"[:200], "body": body}))
    time.sleep(2)
