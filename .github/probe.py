"""One-off check of Workday sources: shows chosen facets and sample titles."""
import importlib.util, json, pathlib, time
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
BOARDS = [("verizon","wd12","verizon-careers"),("disney","wd5","disneycareer"),("ebay","wd5","apply"),
          ("ebay","wd1","apply"),("visa","wd5","Visa"),("citi","wd5","2"),("expedia","wd108","search"),
          ("mastercard","wd1","CorporateCareers"),("zillow","wd5","Zillow_Group_External")]
for t, wd, site in BOARDS:
    host = f"{t}.{wd}.myworkdayjobs.com"; api = f"https://{host}/wday/cxs/{t}/{site}/jobs"
    hdr = {"Origin": f"https://{host}", "Referer": f"https://{host}/en-US/{site}", "Accept-Language": "en-US"}
    try:
        raw = p.http_json(api, {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"}, hdr)
        applied = p._wd_pick_facets(raw.get("facets"))
        facets = [(f.get("facetParameter"), f.get("descriptor"), [v.get("descriptor") for v in (f.get("values") or [])][:8]) for f in p._wd_walk(raw.get("facets"))]
        print(json.dumps({"board": f"{t}/{wd}/{site}", "raw_total": raw.get("total"),
              "raw_titles": [j["title"] for j in raw.get("jobPostings", [])[:6]], "applied": applied}))
        for f in facets: print("   facet", json.dumps(f)[:300])
        time.sleep(2)
        filt = p.http_json(api, {"appliedFacets": applied, "limit": 20, "offset": 0, "searchText": ""}, hdr)
        print("   filtered_total", filt.get("total"), [j["title"] for j in filt.get("jobPostings", [])[:6]])
    except Exception as e:
        print(json.dumps({"board": f"{t}/{wd}/{site}", "error": str(e)[:150]}))
    time.sleep(2)
