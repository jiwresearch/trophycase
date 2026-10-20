#!/usr/bin/env python3
"""Pull every Pro Football Hall of Fame member that has a Pro-Football-Reference ID from Wikidata.
Run from the trophycase folder: python3 tools/fetch_hof.py  -> data-raw/wd_hof.json  (about 30 seconds)"""
import json, os, urllib.parse, urllib.request

EP = "https://query.wikidata.org/sparql"
UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-raw", "wd_hof.json")

def q(s):
    req = urllib.request.Request(EP, data=urllib.parse.urlencode({"query": s, "format": "json"}).encode(),
                                 headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["results"]["bindings"]

props = q("""SELECT ?p ?l WHERE { ?p wikibase:propertyType wikibase:ExternalId ; rdfs:label ?l . FILTER(LANG(?l)="en")
  FILTER(CONTAINS(LCASE(?l),"pro-football-reference") || CONTAINS(LCASE(?l),"pro football reference") || CONTAINS(LCASE(?l),"pro football hall of fame")) }""")
ids = {r["l"]["value"]: r["p"]["value"].rsplit("/", 1)[1] for r in props}
print("Properties:", ids)
pfr = next(v for k, v in ids.items() if "reference" in k.lower() and "player" in k.lower())
hofp = [v for k, v in ids.items() if "hall of fame" in k.lower()]
print("PFR:", pfr, "HOF id props:", hofp)
union = [f"{{ ?item wdt:{p} ?h }}" for p in hofp] + ['{ ?item wdt:P166 ?hf . ?hf rdfs:label "Pro Football Hall of Fame"@en }']
rows = q(f"""SELECT DISTINCT ?pfr ?name ?t WHERE {{ ?item wdt:{pfr} ?pfr . {' UNION '.join(union)}
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name)="en") }}
  OPTIONAL {{ ?item p:P166 ?s . ?s ps:P166 ?hf2 . ?hf2 rdfs:label "Pro Football Hall of Fame"@en . OPTIONAL {{ ?s pq:P585 ?t }} }} }}""")
out = {}
for r in rows:
    k = r["pfr"]["value"].split("/")[-1]
    out.setdefault(k, {"name": r.get("name", {}).get("value"), "t": ""})
    if r.get("t"): out[k]["t"] = r["t"]["value"][:4]
json.dump(out, open(OUT, "w"))
print(f"Done: {len(out)} Hall of Famers -> data-raw/wd_hof.json")
