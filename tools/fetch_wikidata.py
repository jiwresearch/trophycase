#!/usr/bin/env python3
"""Pull birthplaces, awards and Wikipedia links for NFL players from Wikidata.

Run from the trophycase folder:  python3 tools/fetch_wikidata.py
Writes data-raw/wd_bio.json and data-raw/wd_awards.json. Standard library only.
Takes roughly 5-15 minutes; it queries one surname letter at a time to stay
under Wikidata's 60-second query limit, and retries on timeouts.
"""
import json, os, string, sys, time, urllib.parse, urllib.request

EP = "https://query.wikidata.org/sparql"
UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-raw")
os.makedirs(OUT, exist_ok=True)


def q(sparql, tries=5):
    data = urllib.parse.urlencode({"query": sparql, "format": "json"}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(EP, data=data, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:
            wait = 10 * (i + 1)
            print(f"  retry {i+1}/{tries} after error: {e} (waiting {wait}s)", flush=True)
            time.sleep(wait)
    raise SystemExit("Wikidata kept failing; try again in a few minutes.")


def v(row, k):
    return row[k]["value"] if k in row else None


# 1. Find the property id for "Pro-Football-Reference.com player ID" by its label.
props = q("""SELECT ?p ?l WHERE { ?p wikibase:propertyType wikibase:ExternalId ; rdfs:label ?l .
  FILTER(LANG(?l)="en") FILTER(CONTAINS(LCASE(?l),"pro-football-reference") || CONTAINS(LCASE(?l),"pro football reference")) }""")
cands = [(v(r, "p").rsplit("/", 1)[1], v(r, "l")) for r in props]
print("PFR properties found:", cands)
pick = [c for c in cands if "player" in c[1].lower()] or cands
if not pick:
    raise SystemExit("Could not find the Pro-Football-Reference property on Wikidata.")
PFR = pick[0][0]
print("Using", PFR, pick[0][1])

bio, awards = {}, []
letters = list(string.ascii_uppercase)
for L in letters:
    t0 = time.time()
    rows = q(f"""SELECT ?item ?pfr ?name ?dob ?pobL ?coord ?stateL ?countryL ?wp WHERE {{
  ?item wdt:{PFR} ?pfr . FILTER(STRSTARTS(?pfr, "{L}"))
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name)="en") }}
  OPTIONAL {{ ?item wdt:P569 ?dob }}
  OPTIONAL {{ ?item wdt:P19 ?pob . ?pob rdfs:label ?pobL FILTER(LANG(?pobL)="en")
    OPTIONAL {{ ?pob wdt:P625 ?coord }}
    OPTIONAL {{ ?pob wdt:P131* ?st . ?st wdt:P31 wd:Q35657 . ?st rdfs:label ?stateL FILTER(LANG(?stateL)="en") }}
    OPTIONAL {{ ?pob wdt:P17 ?c . ?c rdfs:label ?countryL FILTER(LANG(?countryL)="en") }} }}
  OPTIONAL {{ ?wp schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }}
}}""")
    for r in rows:
        k = v(r, "pfr")
        b = bio.setdefault(k, {"qid": v(r, "item").rsplit("/", 1)[1], "pfr": k})
        for f in ("name", "dob", "pobL", "coord", "stateL", "countryL", "wp"):
            if v(r, f) and not b.get(f):
                b[f] = v(r, f)
    arows = q(f"""SELECT ?pfr ?awL ?t WHERE {{
  ?item wdt:{PFR} ?pfr . FILTER(STRSTARTS(?pfr, "{L}"))
  ?item p:P166 ?s . ?s ps:P166 ?aw . ?aw rdfs:label ?awL FILTER(LANG(?awL)="en")
  OPTIONAL {{ ?s pq:P585 ?t }}
}}""")
    for r in arows:
        awards.append({"pfr": v(r, "pfr"), "award": v(r, "awL"), "t": (v(r, "t") or "")[:4]})
    print(f"{L}: {len(rows)} bio rows, {len(arows)} award rows ({time.time()-t0:.0f}s) - total players {len(bio)}", flush=True)
    time.sleep(2)

json.dump(bio, open(os.path.join(OUT, "wd_bio.json"), "w"))
json.dump(awards, open(os.path.join(OUT, "wd_awards.json"), "w"))
withpob = sum(1 for b in bio.values() if b.get("pobL"))
print(f"\nDone. {len(bio)} players, {withpob} with a birthplace, {len(awards)} award rows.")
print("Files: data-raw/wd_bio.json and data-raw/wd_awards.json")
