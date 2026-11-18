"""One-off probe of candidate direct sources. No alerts or state changes."""
import importlib.util, json, pathlib, time
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

T = [
 ("Zoox","lever","zoox"),("Affirm","gh","affirm"),("Mixpanel","gh","mixpanel"),("Faire","gh","faire"),
 ("Asana","gh","asana"),("Confluent","ashby","confluent"),("Toast","gh","toast"),("Samsara","gh","samsara"),
 ("Verkada","gh","verkada"),("Cloudflare","gh","cloudflare"),("CrowdStrike","wd",("crowdstrike","wd5","crowdstrikecareers")),
 ("Blackstone","wd",("blackstone","wd1","Blackstone_Careers")),("Twitter/X","gh","xcorp"),
 ("Dataminr","gh","dataminr"),("Moloco","gh","moloco"),("Opendoor","gh","opendoor"),("Coursera","gh","coursera"),
 ("Twilio","gh","twilio"),("Okta","gh","okta"),("PEAK6","gh","peak6"),("Trexquant","gh","trexquant"),
 ("WorldQuant","gh","worldquant"),("Grubhub","gh","grubhub"),("Unity","gh","unity3d"),
 ("Workday","wd",("workday","wd5","Workday")),("Autodesk","wd",("autodesk","wd1","Ext")),
 ("Vanguard","wd",("vanguard","wd5","vanguard_external")),("Nutanix","wd",("nutanix","wd1","Nutanix_Careers")),
 ("Aurora Innovation","gh","aurorainnovation"),("Rivian","gh","rivian"),
]

def run(kind, arg):
    if kind == "gh": return p.src_greenhouse(arg)
    if kind == "lever": return p.src_lever(arg)
    if kind == "ashby": return p.src_ashby(arg)
    return p.src_workday(*arg, pages=3)

for name, kind, arg in T:
    try:
        jobs = run(kind, arg)
        interns = [j["title"] for j in jobs if p.INTERN.search(j.get("title", ""))]
        passing = [f'{j["title"]} | {j["location"][:30]}' for j in jobs
                   if p.passes_filters(j.get("title", ""), j.get("location", ""), True)]
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": True, "fetched": len(jobs),
                          "interns": len(interns), "pass": len(passing),
                          "sample": (passing or interns or [j["title"] for j in jobs[:2]])[:2]}))
    except Exception as e:
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": False, "error": str(e)[:90]}))
    time.sleep(1.5 if kind == "wd" else 0.3)
