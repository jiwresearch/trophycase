#!/usr/bin/env python3
"""Download Olympic medalists from Wikidata for Trophy Case.

Run from the trophycase folder:  python3 tools/fetch_olympics.py
Writes data-raw/olympics/:
  medals.json   [{item, medal, event, sport, games, year}]   one row per medal won
  bio.json      {qid: {name, dob, sexL, pobL, coord, stateL, countryL, nocL, olympedia, wp}}
Standard library only. Takes roughly 10-20 minutes. Safe to re-run: finished steps are skipped
(delete a file in data-raw/olympics/ to redo that step).

How Wikidata records a medal: athlete -P1344 (participant in)-> event item, with the medal as a
P166 (award received) qualifier. The probe at the start prints how many medals that finds, so if
Wikidata's modeling ever changes the run stops early with a clear message instead of an empty file.
"""
import json, os, time, urllib.parse, urllib.request

UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
SPARQL = "https://query.wikidata.org/sparql"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-raw", "olympics")
os.makedirs(OUT, exist_ok=True)
P = lambda f: os.path.join(OUT, f)
MEDALS = {"Q15243387": "gold", "Q15889641": "silver", "Q15889643": "bronze"}


def q(sparql, tries=6):
    data = urllib.parse.urlencode({"query": sparql, "format": "json"}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(SPARQL, data=data, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:
            wait = 10 * (i + 1)
            print(f"  retry {i+1}/{tries} after error: {e} (waiting {wait}s)", flush=True)
            time.sleep(wait)
    raise SystemExit("Wikidata kept failing; re-run later and finished steps will be skipped.")


def v(row, k):
    return row[k]["value"] if k in row else None


# ---------------------------------------------------------------- 1. medals
if not os.path.exists(P("medals.json")):
    probe = q("""SELECT ?medal (COUNT(*) AS ?n) WHERE { ?item p:P1344 ?st . ?st pq:P166 ?medal .
      VALUES ?medal { wd:Q15243387 wd:Q15889641 wd:Q15889643 } } GROUP BY ?medal""")
    counts = {MEDALS[v(r, "medal").rsplit("/", 1)[1]]: int(v(r, "n")) for r in probe}
    print("Medal statements on Wikidata:", counts, flush=True)
    if sum(counts.values()) < 1000:
        raise SystemExit("Too few medals found; Wikidata may record them differently now. Stopping before downloading anything.")
    rows_out = []
    # one query per medal colour per Games decade keeps each under Wikidata's 60-second limit
    for mq, mname in MEDALS.items():
        for dec in range(1890, 2030, 10):
            t0 = time.time()
            rows = q(f"""SELECT ?item ?eventL ?sportL ?gamesL ?year WHERE {{
  VALUES ?gtype {{ wd:Q135976384 wd:Q137592217 wd:Q159821 wd:Q82414 }}
  ?games wdt:P31 ?gtype .
  OPTIONAL {{ ?games wdt:P585 ?d }} OPTIONAL {{ ?games wdt:P580 ?d2 }}
  BIND(YEAR(COALESCE(?d, ?d2)) AS ?year) FILTER(?year >= {dec} && ?year < {dec + 10})
  ?event wdt:P361+ ?games .
  ?item p:P1344 ?st . ?st ps:P1344 ?event ; pq:P166 wd:{mq} .
  OPTIONAL {{ ?event rdfs:label ?eventL FILTER(LANG(?eventL)="en") }}
  OPTIONAL {{ ?event wdt:P641 ?sport . ?sport rdfs:label ?sportL FILTER(LANG(?sportL)="en") }}
  OPTIONAL {{ ?games rdfs:label ?gamesL FILTER(LANG(?gamesL)="en") }}
}}""")
            for r in rows:
                rows_out.append({"item": v(r, "item").rsplit("/", 1)[1], "medal": mname, "event": v(r, "eventL") or "",
                                 "sport": v(r, "sportL") or "", "games": v(r, "gamesL") or "", "year": v(r, "year") or ""})
            print(f"{mname} {dec}s: {len(rows)} medals ({time.time()-t0:.0f}s) - {len(rows_out)} total", flush=True)
            time.sleep(1)
    # an event can sit under several "part of" chains; keep one row per athlete+event+medal
    seen, uniq = set(), []
    for r in rows_out:
        k = (r["item"], r["event"], r["medal"])
        if k not in seen: seen.add(k); uniq.append(r)
    if not uniq:
        raise SystemExit("The medal queries returned nothing even though the probe found medals; nothing was saved.")
    json.dump(uniq, open(P("medals.json"), "w"))
    print(f"Medals done: {len(uniq)} medals for {len({r['item'] for r in uniq})} athletes "
          f"(Wikidata probe counted {sum(counts.values())}; events without a Games link are skipped).\n")
else:
    print("Medals: already done (data-raw/olympics/medals.json)")

# ---------------------------------------------------------------- 2. athlete bios
if not os.path.exists(P("bio.json")):
    items = sorted({r["item"] for r in json.load(open(P("medals.json")))})
    bio = {}
    for n in range(0, len(items), 300):
        batch = " ".join(f"wd:{x}" for x in items[n:n + 300])
        rows = q(f"""SELECT ?item ?name ?dob ?sexL ?pobL ?coord ?stateL ?countryL ?nocL ?oly ?wp WHERE {{
  VALUES ?item {{ {batch} }}
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name)="en") }}
  OPTIONAL {{ ?item wdt:P569 ?dob }}
  OPTIONAL {{ ?item wdt:P21 ?sex . ?sex rdfs:label ?sexL FILTER(LANG(?sexL)="en") }}
  OPTIONAL {{ ?item wdt:P1532 ?noc . ?noc rdfs:label ?nocL FILTER(LANG(?nocL)="en") }}
  OPTIONAL {{ ?item wdt:P8286 ?oly }}
  OPTIONAL {{ ?item wdt:P19 ?pob . ?pob rdfs:label ?pobL FILTER(LANG(?pobL)="en")
    OPTIONAL {{ ?pob wdt:P625 ?coord }}
    OPTIONAL {{ ?pob wdt:P131* ?st . ?st wdt:P31 wd:Q35657 . ?st rdfs:label ?stateL FILTER(LANG(?stateL)="en") }}
    OPTIONAL {{ ?pob wdt:P17 ?c . ?c rdfs:label ?countryL FILTER(LANG(?countryL)="en") }} }}
  OPTIONAL {{ ?wp schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }}
}}""")
        for r in rows:
            k = v(r, "item").rsplit("/", 1)[1]
            b = bio.setdefault(k, {})
            for f, key in (("name", "name"), ("dob", "dob"), ("sexL", "sexL"), ("pobL", "pobL"), ("coord", "coord"), ("stateL", "stateL"),
                           ("countryL", "countryL"), ("nocL", "nocL"), ("oly", "olympedia"), ("wp", "wp")):
                if v(r, f) and not b.get(key): b[key] = v(r, f)
        if (n // 300) % 10 == 0: print(f"  bios {min(n + 300, len(items))}/{len(items)}", flush=True)
        time.sleep(1)
    json.dump(bio, open(P("bio.json"), "w"))
    print(f"Bios done: {len(bio)} athletes, {sum(1 for b in bio.values() if b.get('pobL'))} with a birthplace.")
else:
    print("Bios: already done (data-raw/olympics/bio.json)")
print("\nAll done. Files are in data-raw/olympics/: medals.json, bio.json")
