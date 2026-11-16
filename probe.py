import importlib.util, tomllib, time
spec = importlib.util.spec_from_file_location("p", "poller.py"); p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
cfg = tomllib.loads(open("companies.toml").read())
for label, c, fn in p.build_jobs(cfg):
    if not c or c.get("tier") != "S": continue
    t = time.time()
    try:
        rows = fn()
        m = [(p.fit_score(r["title"], r["location"], "S")[0], r["title"], r["location"][:40]) for r in rows if r.get("url") and p.passes_filters(r["title"], r["location"])]
        m.sort(reverse=True)
        print(f"\n=== {label} OK {time.time()-t:.1f}s fetched={len(rows)} matched={len(m)}")
        for x in m[:5]: print("   ", x)
        if rows: print("    url:", rows[0]["url"])
    except Exception as e:
        print(f"\n=== {label} FAIL {time.time()-t:.1f}s {type(e).__name__}: {str(e)[:200]}")
