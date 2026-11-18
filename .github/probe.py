"""One-off probe of candidate direct sources for tracker-only companies. No alerts or state changes."""
import importlib.util, json, pathlib, time
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

TESTS = [
    ("Etsy", "gh", "etsy"), ("Retool", "ashby", "retool"), ("Retool", "gh", "retool"),
    ("Runway", "ashby", "runway"), ("Runway", "gh", "runwayml"),
    ("Thinking Machines Lab", "gh", "thinkingmachines"), ("Thinking Machines Lab", "ashby", "thinkingmachines"),
    ("Cognition", "ashby", "cognition"), ("Rippling", "ashby", "rippling"),
    ("Applied Intuition", "gh", "appliedintuition"), ("Sierra", "ashby", "sierra"),
    ("Decagon", "ashby", "decagon"), ("Mistral AI", "lever", "mistral"), ("Modal", "ashby", "modal"),
    ("Schonfeld", "gh", "schonfeld"), ("Hugging Face", "ashby", "huggingface"),
    ("Walmart", "wd", ("walmart", "wd5", "WalmartExternal")),
    ("Micron Technology", "wd", ("micron", "wd1", "External")),
    ("American Express", "ef", ("aexp.eightfold.ai", "aexp.com")),
    ("ServiceNow", "gh", "servicenow"), ("Wayfair", "lever", "wayfair"),
    ("Shopify", "ashby", "shopify"), ("Uber", "gh", "uber"),
]

def run(kind, arg):
    if kind == "gh": return p.src_greenhouse(arg)
    if kind == "lever": return p.src_lever(arg)
    if kind == "ashby": return p.src_ashby(arg)
    if kind == "ef": return p.src_eightfold(*arg)
    return p.src_workday(*arg, pages=3)

for name, kind, arg in TESTS:
    try:
        jobs = run(kind, arg)
        interns = [j["title"] for j in jobs if p.INTERN.search(j.get("title", ""))]
        passing = [j["title"] for j in jobs if p.passes_filters(j.get("title", ""), j.get("location", ""))]
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": True, "fetched": len(jobs),
                          "interns": len(interns), "pass": len(passing), "sample": (passing or interns)[:3]}))
    except Exception as e:
        print(json.dumps({"company": name, "source": f"{kind}:{arg}", "ok": False, "error": str(e)[:120]}))
    time.sleep(1.5 if kind == "wd" else 0.3)
