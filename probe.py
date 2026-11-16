import json, urllib.request, collections
H = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json", "website-path": "tiktok", "Origin": "https://lifeattiktok.com", "Referer": "https://lifeattiktok.com/"}
def q(body):
    r = urllib.request.Request("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts", json.dumps(body).encode(), H)
    return json.loads(urllib.request.urlopen(r, timeout=25).read())
base = {"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [], "location_code_list": [], "keyword": "intern", "limit": 100, "offset": 0}
us = collections.Counter(); n = 0
for off in range(0, 3200, 100):
    d = q(dict(base, offset=off)); posts = d["data"]["job_post_list"] or []
    for j in posts:
        chain, c = [], j.get("city_info")
        while c: chain.append((c["code"], c["en_name"])); c = c.get("parent")
        if any("United States" in x[1] for x in chain): us[chain[0]] += 1; n += 1
    if len(posts) < 100: break
print("US intern posts", n, us.most_common(30))
codes = [c for (c, _), _ in us.most_common(30)]
d = q(dict(base, location_code_list=codes)); print("with US city codes, count =", d["data"]["count"])
d = q(dict(base, location_code_list=["CN_6"])); print("CN_6 count", d["data"]["count"])
d = q(dict(base, recruitment_id_list=["202"])); print("recruit 202 count", d["data"]["count"])
print("first titles", [j["title"] for j in q(dict(base, location_code_list=codes, limit=5))["data"]["job_post_list"]])
