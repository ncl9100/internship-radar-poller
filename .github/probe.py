"""One-off probe of candidate direct sources. No alerts or state changes."""
import importlib.util, json, pathlib, time
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

T = [
 ("Nextdoor","gh","nextdoorcampus"),("Nextdoor","gh","nextdoor"),
 ("Whatnot","ashby","whatnot"),("Klaviyo","gh","klaviyocampus"),("Klaviyo","gh","klaviyo"),
 ("SoFi","gh","sofi"),("Upstart","gh","upstart"),
 ("Warner Bros. Discovery","wd",("warnerbros","wd5","global")),
 ("Paramount","wd",("paramount","wd5","paramountcareers")),
 ("FanDuel","gh","fanduel"),("Oscar Health","gh","oscar"),("Flatiron Health","gh","flatironhealth"),
 ("Peloton","gh","peloton"),("Squarespace","gh","squarespace"),("Grammarly","gh","grammarly"),
 ("Quora","ashby","quora"),("Quora","gh","quora"),("Roku","gh","roku"),("Roku","wd",("roku","wd5","rokucareers")),
 ("Yelp","gh","yelp"),("Yelp","lever","yelp"),("Hex","gh","hextechnologies"),("Amplitude","gh","amplitude"),
 ("Coupang","gh","coupang"),("Nuro","gh","nuro"),("Wealthfront","lever","wealthfront"),("Wealthfront","ashby","wealthfront"),
 ("Oracle","oracle",("eeho.fa.us2.oraclecloud.com","CX_45001")),
 ("Palo Alto Networks","wd",("paloaltonetworks","wd5","External")),("Atlassian","lever","atlassian"),
 ("Jump Trading","gh","jumptrading"),("DRW","gh","drweng"),("DRW","gh","drw"),
 ("Millennium","wd",("mlp","wd5","mlpcareers")),("Bridgewater","gh","bridgewater89"),("Bridgewater","gh","bridgewater"),
 ("OpenEvidence","ashby","openevidence"),("Mercor","ashby","mercor"),
 ("Physical Intelligence","ashby","physicalintelligence"),("Physical Intelligence","gh","physicalintelligence"),
 ("DraftKings","wd",("draftkings","wd1","DraftKings")),("Zocdoc","gh","zocdoc"),
 ("Chewy","wd",("chewy","wd5","chewycareers")),("HelloFresh","gh","hellofresh"),("Tatari","gh","tatari"),
 ("MoneyLion","gh","moneylion"),("Ro","ashby","ro"),("Ro","lever","ro"),
 ("PIMCO","wd",("pimco","wd1","pimco-careers")),("Prudential Financial","wd",("pru","wd5","Careers")),
 ("T. Rowe Price","wd",("troweprice","wd5","TRowePrice")),("Comcast","wd",("comcast","wd5","Comcast_Careers")),
 ("Ripple","gh","ripple"),("Chicago Trading Company","gh","chicagotrading"),("Virtu","gh","virtu"),
 ("Squarepoint","gh","squarepointcapital"),("BNY","wd",("bnymellon","wd1","BNY_External")),
 ("Fireworks AI","ashby","fireworks-ai"),("Fireworks AI","gh","fireworksai"),
]

def run(kind, arg):
    if kind == "gh": return p.src_greenhouse(arg)
    if kind == "lever": return p.src_lever(arg)
    if kind == "ashby": return p.src_ashby(arg)
    if kind == "oracle": return p.src_oracle(*arg)
    return p.src_workday(*arg, pages=3)

for name, kind, arg in T:
    try:
        jobs = run(kind, arg)
        interns = [j["title"] for j in jobs if p.INTERN.search(j.get("title", ""))]
        passing = [f'{j["title"]} | {j["location"][:30]}' for j in jobs
                   if p.passes_filters(j.get("title", ""), j.get("location", ""), True)]
        sample_any = [j["title"] for j in jobs[:2]]
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": True, "fetched": len(jobs),
                          "interns": len(interns), "pass": len(passing),
                          "sample": (passing or interns or sample_any)[:3]}))
    except Exception as e:
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": False, "error": str(e)[:100]}))
    time.sleep(1.5 if kind in ("wd", "oracle") else 0.3)
