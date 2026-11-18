"""One-off check of direct job-board sources. Run by the probe workflow; prints a report."""
import importlib.util, json, sys, time, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

CONFIGURED = [  # sources now in companies.toml
    ("PayPal", "wd", ("paypal", "wd1", "jobs")),
    ("Block", "gh", "block"),
    ("Match Group", "lever", "matchgroup"),
    ("eBay", "wd", ("ebay", "wd5", "apply")),
    ("Disney", "wd", ("disney", "wd5", "disneycareer")),
    ("MongoDB", "gh", "mongodb"),
    ("Zillow", "wd", ("zillow", "wd5", "Zillow_Group_External")),
    ("Riot Games", "gh", "riotgames"),
    ("IMC Trading", "gh", "imc"),
    ("Verizon", "wd", ("verizon", "wd12", "verizon-careers")),
    ("Mastercard", "wd", ("mastercard", "wd1", "CorporateCareers")),
    ("Akuna Capital", "gh", "akunacapital"),
]
GUESSES = [  # candidate sources for companies still on trackers only
    ("Block", "gh", "square"), ("Snowflake", "ashby", "snowflake"), ("Snowflake", "gh", "snowflake"),
    ("Wayfair", "gh", "wayfair"), ("Wayfair", "gh", "wayfaircareers"),
    ("Expedia Group", "wd", ("expedia", "wd108", "search")),
    ("Intuit", "wd", ("intuit", "wd1", "Intuit")),
    ("NBCUniversal", "wd", ("nbcuniversal", "wd5", "NBCUniversal")),
    ("Electronic Arts", "wd", ("ea", "wd1", "EA")),
    ("Citi", "wd", ("citi", "wd5", "2")),
    ("New York Life", "wd", ("newyorklife", "wd1", "NYLCareers")),
    ("American Express", "wd", ("aexp", "wd5", "AmEx")),
    ("Visa", "wd", ("visa", "wd5", "Visa")),
    ("Optiver", "gh", "optiver"), ("Optiver", "gh", "optiverus"),
    ("Point72", "gh", "point72"), ("D. E. Shaw", "gh", "deshaw"),
    ("Susquehanna International Group", "wd", ("sig", "wd1", "SIG_External")),
    ("Tesla", "gh", "tesla"), ("Match Group", "gh", "hinge"),
]

def run(kind, arg):
    if kind == "gh": return p.src_greenhouse(arg)
    if kind == "lever": return p.src_lever(arg)
    if kind == "ashby": return p.src_ashby(arg)
    return p.src_workday(*arg, pages=3)

report = []
for group, items in (("configured", CONFIGURED), ("guess", GUESSES)):
    for name, kind, arg in items:
        try:
            jobs = run(kind, arg)
            interns = [j for j in jobs if p.INTERN.search(j.get("title", ""))]
            passing = [j["title"] for j in jobs if p.passes_filters(j.get("title", ""), j.get("location", ""))]
            report.append({"group": group, "company": name, "source": f"{kind}:{arg}", "ok": True,
                           "fetched": len(jobs), "intern_titles": len(interns), "pass_filters": len(passing),
                           "sample": passing[:3] or [j["title"] for j in interns[:2]]})
        except Exception as e:
            report.append({"group": group, "company": name, "source": f"{kind}:{arg}", "ok": False,
                           "error": f"{type(e).__name__}: {e}"[:160]})
        time.sleep(1.5 if kind == "wd" else 0.3)

for r in report:
    print(json.dumps(r))
