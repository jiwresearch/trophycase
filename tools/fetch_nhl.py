#!/usr/bin/env python3
"""Download everything the hockey build needs: NHL/WHA (and PWHL) players from Wikidata,
each player's Wikipedia infobox, the award-list pages in tools/nhl_award_pages.txt, and every
Stanley Cup Final page (its champion roster gives each player's Cup years).

Run from the trophycase folder:  python3 tools/fetch_nhl.py
Writes data-raw/nhl/:
  wd_bio.json             {bbref id: {qid, league, name, dob, sex, pobL, coord, stateL, countryL, wp}}
  wd_awards.json          [{id, award, t}]  (backup source; the infobox and award lists come first)
  infobox.jsonl.gz        one line per player article: {title, id, page, infobox, cats}
  award_pages.jsonl.gz    {title, page, text} per award-list page
Standard library only. Takes roughly 10-20 minutes. Safe to re-run: finished steps are skipped
(delete a file in data-raw/nhl/ to redo that step).
"""
import gzip, json, os, string, time, urllib.parse, urllib.request

UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
SPARQL = "https://query.wikidata.org/sparql"
API = "https://en.wikipedia.org/w/api.php"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data-raw", "nhl")
os.makedirs(OUT, exist_ok=True)
P = lambda f: os.path.join(OUT, f)


def http(url, data=None, accept="application/json", tries=6, timeout=90):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip": raw = gzip.decompress(raw)
            d = json.loads(raw)
            if isinstance(d, dict) and d.get("error", {}).get("code") == "maxlag":
                time.sleep(5 * (i + 1)); continue
            return d
        except Exception as e:
            wait = 10 * (i + 1)
            print(f"  retry {i+1}/{tries} after error: {e} (waiting {wait}s)", flush=True)
            time.sleep(wait)
    raise SystemExit("The server kept failing; re-run later and finished steps will be skipped.")


def q(sparql):
    data = urllib.parse.urlencode({"query": sparql, "format": "json"}).encode()
    return http(SPARQL, data, "application/sparql-results+json")["results"]["bindings"]


def v(row, k):
    return row[k]["value"] if k in row else None


# ---------------------------------------------------------------- 1. Wikidata
if not os.path.exists(P("wd_bio.json")):
    props = q("""SELECT ?p ?l WHERE { ?p wikibase:propertyType wikibase:ExternalId ; rdfs:label ?l .
      FILTER(LANG(?l)="en") FILTER(CONTAINS(LCASE(?l),"hockey-reference") || CONTAINS(LCASE(?l),"hockey reference")
                                  || CONTAINS(LCASE(?l),"nhl.com player") || CONTAINS(LCASE(?l),"pwhl")) }""")
    cands = [(v(r, "p").rsplit("/", 1)[1], v(r, "l")) for r in props]
    print("Hockey properties:", cands)
    leagues = {}
    for pid, label in cands:
        l = label.lower()
        if "coach" in l or "college" in l or "team" in l or "referee" in l or "executive" in l: continue
        if "pwhl" in l: leagues.setdefault("PWHL", pid)
        elif "hockey" in l and "player" in l: leagues.setdefault("NHL", pid)
        elif "nhl.com" in l: leagues.setdefault("NHLCOM", pid)
    if "NHL" not in leagues: raise SystemExit("Could not find the Hockey Reference player property on Wikidata.")
    print("Using", leagues)
    bio, awards = {}, []
    for lg, prop in leagues.items():
        # PWHL ids are numeric, so one unfiltered pass ("" matches every id) instead of a-z
        for L in ([""] if lg == "PWHL" else string.ascii_lowercase):
            t0 = time.time()
            rows = q(f"""SELECT ?item ?id ?name ?dob ?sexL ?pobL ?coord ?stateL ?countryL ?wp WHERE {{
  ?item wdt:{prop} ?id . FILTER(STRSTARTS(LCASE(?id), "{L}"))
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name)="en") }}
  OPTIONAL {{ ?item wdt:P569 ?dob }}
  OPTIONAL {{ ?item wdt:P21 ?sex . ?sex rdfs:label ?sexL FILTER(LANG(?sexL)="en") }}
  OPTIONAL {{ ?item wdt:P19 ?pob . ?pob rdfs:label ?pobL FILTER(LANG(?pobL)="en")
    OPTIONAL {{ ?pob wdt:P625 ?coord }}
    OPTIONAL {{ ?pob wdt:P131* ?st . ?st wdt:P31 wd:Q35657 . ?st rdfs:label ?stateL FILTER(LANG(?stateL)="en") }}
    OPTIONAL {{ ?pob wdt:P17 ?c . ?c rdfs:label ?countryL FILTER(LANG(?countryL)="en") }} }}
  OPTIONAL {{ ?wp schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }}
}}""")
            for r in rows:
                k = f"{lg}:{v(r, 'id')}"
                b = bio.setdefault(k, {"qid": v(r, "item").rsplit("/", 1)[1], "id": v(r, "id"), "league": lg})
                for f in ("name", "dob", "sexL", "pobL", "coord", "stateL", "countryL", "wp"):
                    if v(r, f) and not b.get(f): b[f] = v(r, f)
            trows = q(f"""SELECT ?id ?teamL ?s ?e WHERE {{
  ?item wdt:{prop} ?id . FILTER(STRSTARTS(LCASE(?id), "{L}"))
  ?item p:P54 ?st . ?st ps:P54 ?team . ?team rdfs:label ?teamL FILTER(LANG(?teamL)="en")
  OPTIONAL {{ ?st pq:P580 ?s }} OPTIONAL {{ ?st pq:P582 ?e }} }}""")
            for r in trows:
                k = f"{lg}:{v(r, 'id')}"
                if k in bio: bio[k].setdefault("teams", []).append([v(r, "teamL"), (v(r, "s") or "")[:4], (v(r, "e") or "")[:4]])
            arows = q(f"""SELECT ?id ?awL ?t WHERE {{
  ?item wdt:{prop} ?id . FILTER(STRSTARTS(LCASE(?id), "{L}"))
  ?item p:P166 ?s . ?s ps:P166 ?aw . ?aw rdfs:label ?awL FILTER(LANG(?awL)="en")
  OPTIONAL {{ ?s pq:P585 ?t }} }}""")
            for r in arows:
                awards.append({"id": f"{lg}:{v(r, 'id')}", "award": v(r, "awL"), "t": (v(r, "t") or "")[:4]})
            print(f"{lg} {L}: {len(rows)} rows, {len(arows)} award rows ({time.time()-t0:.0f}s) - {len(bio)} players so far", flush=True)
            time.sleep(1)
    json.dump(bio, open(P("wd_bio.json"), "w"))
    json.dump(awards, open(P("wd_awards.json"), "w"))
    print(f"Wikidata done: {len(bio)} players, {sum(1 for b in bio.values() if b.get('pobL'))} with a birthplace.\n")
else:
    print("Wikidata: already done (data-raw/nhl/wd_bio.json)")

# ---------------------------------------------------------------- 2. infoboxes
def infobox(text):
    i = text.lower().find("{{infobox")
    if i < 0: return ""
    depth, j = 0, i
    while j < len(text) - 1:
        two = text[j:j + 2]
        if two == "{{": depth += 1; j += 2; continue
        if two == "}}":
            depth -= 1; j += 2
            if depth == 0: return text[i:j]
            continue
        j += 1
    return text[i:i + 20000]

def wiki_batch(titles):
    params = {"action": "query", "prop": "revisions|categories", "rvprop": "content", "rvslots": "main", "cllimit": "max",
              "clshow": "!hidden", "format": "json", "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(titles)}
    return http(API + "?" + urllib.parse.urlencode(params)).get("query", {})

if not os.path.exists(P("infobox.jsonl.gz")):
    bio = json.load(open(P("wd_bio.json")))
    want = {}
    for k, b in bio.items():
        wp = b.get("wp")
        if wp and "/wiki/" in wp:
            want.setdefault(urllib.parse.unquote(wp.split("/wiki/", 1)[1]).replace("_", " "), k)
    part = P("infobox.jsonl.part")
    done = set()
    if os.path.exists(part):
        for line in open(part, encoding="utf-8"):
            try: done.add(json.loads(line)["title"])
            except Exception: pass
    todo = [t for t in sorted(want) if t not in done]
    print(f"Infoboxes: {len(want)} articles, {len(done)} already fetched, {len(todo)} to go", flush=True)
    with open(part, "a", encoding="utf-8") as out:
        for n in range(0, len(todo), 50):
            batch = todo[n:n + 50]
            qd = wiki_batch(batch)
            back = {}
            for m in qd.get("normalized", []) + qd.get("redirects", []):
                back[m["to"]] = back.get(m["from"], m["from"])
            for pg in qd.get("pages", []):
                t = back.get(pg["title"], pg["title"])
                text = pg["revisions"][0]["slots"]["main"].get("content", "") if pg.get("revisions") else ""
                cats = [c["title"].split(":", 1)[-1] for c in pg.get("categories", [])
                        if "Hall of Fame" in c["title"] or "Olympic" in c["title"] or "medalists" in c["title"] or "Stanley Cup" in c["title"]]
                out.write(json.dumps({"title": t, "id": want.get(t, ""), "page": pg["title"], "infobox": infobox(text), "cats": cats},
                                     ensure_ascii=False) + "\n")
            out.flush()
            if (n // 50) % 10 == 0: print(f"  {min(n + 50, len(todo))}/{len(todo)}", flush=True)
            time.sleep(1)
    with open(part, "rb") as f, gzip.open(P("infobox.jsonl.gz"), "wb") as g:
        g.write(f.read())
    print("Infoboxes done.\n")
else:
    print("Infoboxes: already done (data-raw/nhl/infobox.jsonl.gz)")

# ---------------------------------------------------------------- 3. award lists
titles = [t.strip() for t in open(os.path.join(HERE, "nhl_award_pages.txt"), encoding="utf-8") if t.strip() and not t.startswith("#")]
titles += [f"{y} Stanley Cup Final" for y in range(1927, 2027) if y != 2005]   # no Cup in 2005 (lockout)
titles += [f"{y} Stanley Cup Finals" for y in range(1915, 1927)] + [f"{y} Stanley Cup playoffs" for y in range(1918, 1927)]
got = 0
with gzip.open(P("award_pages.jsonl.gz"), "wt", encoding="utf-8") as out:
    for n in range(0, len(titles), 20):
        batch = titles[n:n + 20]
        params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
                  "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(batch)}
        qd = http(API + "?" + urllib.parse.urlencode(params)).get("query", {})
        back = {}
        for m in qd.get("normalized", []) + qd.get("redirects", []):
            back[m["to"]] = back.get(m["from"], m["from"])
        for pg in qd.get("pages", []):
            text = pg["revisions"][0]["slots"]["main"].get("content", "") if pg.get("revisions") else ""
            got += bool(text)
            if not text: print("  missing page:", back.get(pg["title"], pg["title"]))
            out.write(json.dumps({"title": back.get(pg["title"], pg["title"]), "page": pg["title"], "text": text}, ensure_ascii=False) + "\n")
        time.sleep(1)
print(f"Award pages: {got} of {len(titles)} downloaded.")
print("\nAll done. Files are in data-raw/nhl/: wd_bio.json, wd_awards.json, infobox.jsonl.gz, award_pages.jsonl.gz")
