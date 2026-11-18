"""One-off probe of candidate direct sources. No alerts or state changes."""
import importlib.util, json, pathlib, time
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

TESTS = [
    ("Bank of America", "wd", ("ghr", "wd1", "Lateral-US")),
    ("Bank of America", "wd", ("ghr", "wd1", "campus")),
    ("BlackRock", "wd", ("blackrock", "wd1", "BlackRock_Professional")),
    ("BlackRock", "wd", ("blackrock", "wd1", "BlackRock_Campus")),
    ("The Trade Desk", "gh", "thetradedesk"),
    ("Fidelity Investments", "wd", ("fmr", "wd1", "FidelityCareers")),
    ("Five Rings", "gh", "fiveringsllc"), ("Five Rings", "gh", "fiverings"),
    ("Tower Research Capital", "gh", "towerresearchcapital"),
    ("AQR", "wd", ("aqr", "wd5", "External")), ("AQR", "gh", "aqr"),
    ("Wells Fargo", "wd", ("wd1", "wd1", "WellsFargoJobs")),
    ("Wells Fargo", "wd", ("wellsfargo", "wd1", "WellsFargoJobs")),
    ("Old Mission", "gh", "oldmissioncapital"), ("Old Mission", "gh", "oldmission"),
]

def run(kind, arg):
    if kind == "gh": return p.src_greenhouse(arg)
    if kind == "lever": return p.src_lever(arg)
    if kind == "ashby": return p.src_ashby(arg)
    return p.src_workday(*arg, pages=3)

for name, kind, arg in TESTS:
    try:
        jobs = run(kind, arg)
        interns = [j["title"] for j in jobs if p.INTERN.search(j.get("title", ""))]
        passing = [f'{j["title"]} | {j["location"][:40]}' for j in jobs
                   if p.passes_filters(j.get("title", ""), j.get("location", ""), True)]
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": True, "fetched": len(jobs),
                          "interns": len(interns), "pass": len(passing), "sample": (passing or interns)[:4]}))
    except Exception as e:
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": False, "error": str(e)[:120]}))
    time.sleep(1.5 if kind == "wd" else 0.3)
