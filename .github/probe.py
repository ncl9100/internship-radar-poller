"""One-off probe: Visa search endpoint shape. No alerts or state changes."""
import importlib.util, json, pathlib, urllib.request
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

def post(b):
    req = urllib.request.Request("https://search.visa.com/CAREERS/careers/jobs?lang=en_US",
                                 data=json.dumps(b).encode(), method="POST",
                                 headers={"User-Agent": p.UA, "Content-Type": "application/json",
                                          "Accept": "application/json",
                                          "Origin": "https://corporate.visa.com",
                                          "Referer": "https://corporate.visa.com/en/jobs/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

for b in [{}, {"from": 0, "size": 1000}, {"from": 0, "size": 2000, "query": ""},
          {"from": 0, "size": 1000, "filters": [{"key": "jobTitle", "value": "intern"}]}]:
    try:
        d = post(b)
        jobs = d.get("jobDetails") or []
        sample = jobs[0] if jobs else {}
        small = {k: (v if not isinstance(v, str) or len(v) < 120 else v[:120]) for k, v in sample.items()
                 if k != "jobDescription"}
        interns = [f'{j.get("jobTitle")} | {j.get("city")}, {j.get("country")}' for j in jobs
                   if p.INTERN.search(j.get("jobTitle") or "")]
        print(json.dumps({"body": b, "matched": d.get("recordsMatched"), "total": d.get("totalRecords"),
                          "got": len(jobs), "keys": small, "interns": len(interns), "intern_sample": interns[:8]}))
    except Exception as e:
        print(json.dumps({"body": b, "err": str(e)[:200]}))
