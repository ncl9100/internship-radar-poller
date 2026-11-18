"""One-off probe: JPMorgan finder variants and Visa endpoints. No alerts or state changes."""
import importlib.util, json, pathlib, time, urllib.request
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("poller", root / "poller.py")
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

H = ("https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
     "?onlyData=true&expand=requisitionList.secondaryLocations&finder=")
variants = {
    "raw_quoted": 'findReqs;siteNumber=CX_1001,keyword="intern",limit=25,offset=0,sortBy=POSTING_DATES_DESC',
    "raw_unquoted": 'findReqs;siteNumber=CX_1001,keyword=intern,limit=25,offset=0,sortBy=POSTING_DATES_DESC',
    "pct22": 'findReqs;siteNumber=CX_1001,keyword=%22intern%22,limit=25,offset=0,sortBy=POSTING_DATES_DESC',
    "pct22_summer_analyst": 'findReqs;siteNumber=CX_1001,keyword=%22summer%20analyst%22,limit=25,offset=0,sortBy=RELEVANCY',
    "pct22_1002": 'findReqs;siteNumber=CX_1002,keyword=%22intern%22,limit=25,offset=0,sortBy=POSTING_DATES_DESC',
}
for k, f in variants.items():
    try:
        d = p.http_json(H + f)
        it = (d.get("items") or [{}])[0]
        reqs = it.get("requisitionList") or []
        print(json.dumps({"v": k, "total": it.get("TotalJobsCount"), "kw": it.get("Keyword"),
                          "site": it.get("SiteNumber"), "titles": [r.get("Title") for r in reqs[:6]]}))
    except Exception as e:
        print(json.dumps({"v": k, "err": str(e)[:150]}))
    time.sleep(1)

for url in ["https://api.smartrecruiters.com/v1/companies/Visa/postings?limit=5",
            "https://search.visa.com/CAREERS/careers/jobs?q=intern&lang=en_US&from=0&size=20",
            "https://corporate.visa.com/en/jobs/?q=intern"]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": p.UA, "Accept": "application/json, text/html"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
        print(json.dumps({"url": url, "status": 200, "len": len(body), "head": body[:700]}))
    except Exception as e:
        print(json.dumps({"url": url, "err": str(e)[:150]}))
