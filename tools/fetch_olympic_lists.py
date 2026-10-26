#!/usr/bin/env python3
"""Second Olympics source: Wikipedia's "List of Olympic medalists in ..." pages, plus Wikidata bios for
everyone those pages link to who has an Olympedia athlete id.

Why: Wikidata records only some medals on the athlete (Usain Bolt and Carl Lewis have none there, Simone Biles one).
The Wikipedia medalist lists are complete, event by event.

Run from the trophycase folder:  python3 tools/fetch_olympic_lists.py
Writes data-raw/olympics/:
  list_pages.jsonl.gz   {title, text} for every "List of Olympic medalists in ..." page
  list_bio.json         {wikipedia title: {qid, name, dob, sexL, pobL, coord, stateL, countryL, nocL, olympedia}}
Standard library only. About 10-20 minutes. Finished steps are skipped on a re-run.
"""
import gzip, json, os, re, time, urllib.parse, urllib.request

UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
API = "https://en.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-raw", "olympics")
os.makedirs(OUT, exist_ok=True)
P = lambda f: os.path.join(OUT, f)


def http(url, data=None, accept="application/json", tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip": raw = gzip.decompress(raw)
            d = json.loads(raw)
            if isinstance(d, dict) and d.get("error", {}).get("code") == "maxlag": time.sleep(5 * (i + 1)); continue
            return d
        except Exception as e:
            print(f"  retry {i+1}/{tries}: {e}", flush=True); time.sleep(10 * (i + 1))
    raise SystemExit("The server kept failing; re-run later and finished steps will be skipped.")


# ---------------------------------------------------------------- 1. medalist list pages
if not os.path.exists(P("list_pages.jsonl.gz")):
    titles, cont = [], {}
    while True:
        d = http(API + "?" + urllib.parse.urlencode({"action": "query", "list": "allpages", "apprefix": "List of Olympic medalists in ",
                                                       "apnamespace": 0, "apfilterredir": "nonredirects", "aplimit": "max", "format": "json", **cont}))
        titles += [p["title"] for p in d["query"]["allpages"]]
        if "continue" not in d: break
        cont = d["continue"]
    print(f"{len(titles)} medalist list pages", flush=True)
    if len(titles) < 30: raise SystemExit("Fewer list pages than expected; stopping before saving anything.")
    with gzip.open(P("list_pages.jsonl.gz.part"), "wt", encoding="utf-8") as out:
        for n in range(0, len(titles), 20):
            batch = titles[n:n + 20]
            d = http(API + "?" + urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                                           "format": "json", "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(batch)}))
            for pg in d.get("query", {}).get("pages", []):
                text = pg["revisions"][0]["slots"]["main"].get("content", "") if pg.get("revisions") else ""
                out.write(json.dumps({"title": pg["title"], "text": text}, ensure_ascii=False) + "\n")
            print(f"  pages {min(n + 20, len(titles))}/{len(titles)}", flush=True)
            time.sleep(1)
    os.replace(P("list_pages.jsonl.gz.part"), P("list_pages.jsonl.gz"))
else:
    print("List pages: already done")

# ---------------------------------------------------------------- 2. bios for every linked person with an Olympedia id
if not os.path.exists(P("list_bio.json")):
    links = set()
    for line in gzip.open(P("list_pages.jsonl.gz"), "rt", encoding="utf-8"):
        t = json.loads(line)["text"]
        for m in re.finditer(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]", t):
            x = m.group(1).strip()
            if x and ":" not in x and not re.search(r"\d{4} (Summer|Winter) Olympics|Olympics|^List of", x):
                links.add(x[:1].upper() + x[1:])
        for m in re.finditer(r"\{\{\s*sortname\s*\|[^|}]*\|[^|}]*\|([^|}]+)", t, re.I):
            x = m.group(1).strip()
            if x and not x.lower().startswith(("nolink", "dab")): links.add(x[:1].upper() + x[1:])
    links = sorted(links)
    print(f"{len(links)} linked titles to look up on Wikidata", flush=True)
    bio = {}
    for n in range(0, len(links), 200):
        vals = " ".join("<https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"), safe="") + ">" for t in links[n:n + 200])
        q = f"""SELECT ?art ?item ?name ?dob ?sexL ?pobL ?coord ?stateL ?countryL ?nocL ?oly WHERE {{
  VALUES ?art {{ {vals} }}
  ?art schema:about ?item . ?item wdt:P8286 ?oly .
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name)="en") }}
  OPTIONAL {{ ?item wdt:P569 ?dob }}
  OPTIONAL {{ ?item wdt:P21 ?sex . ?sex rdfs:label ?sexL FILTER(LANG(?sexL)="en") }}
  OPTIONAL {{ ?item wdt:P1532 ?noc . ?noc rdfs:label ?nocL FILTER(LANG(?nocL)="en") }}
  OPTIONAL {{ ?item wdt:P19 ?pob . ?pob rdfs:label ?pobL FILTER(LANG(?pobL)="en")
    OPTIONAL {{ ?pob wdt:P625 ?coord }}
    OPTIONAL {{ ?pob wdt:P131* ?st . ?st wdt:P31 wd:Q35657 . ?st rdfs:label ?stateL FILTER(LANG(?stateL)="en") }}
    OPTIONAL {{ ?pob wdt:P17 ?c . ?c rdfs:label ?countryL FILTER(LANG(?countryL)="en") }} }}
}}"""
        rows = http(SPARQL, urllib.parse.urlencode({"query": q, "format": "json"}).encode(), "application/sparql-results+json")["results"]["bindings"]
        for r in rows:
            t = urllib.parse.unquote(r["art"]["value"].split("/wiki/", 1)[1]).replace("_", " ")
            b = bio.setdefault(t, {"qid": r["item"]["value"].rsplit("/", 1)[1]})
            for f, key in (("name", "name"), ("dob", "dob"), ("sexL", "sexL"), ("pobL", "pobL"), ("coord", "coord"), ("stateL", "stateL"),
                           ("countryL", "countryL"), ("nocL", "nocL"), ("oly", "olympedia")):
                if f in r and not b.get(key): b[key] = r[f]["value"]
        if (n // 200) % 20 == 0: print(f"  bios {min(n + 200, len(links))}/{len(links)} - {len(bio)} athletes", flush=True)
        time.sleep(1)
    if len(bio) < 1000: raise SystemExit("Too few athletes matched on Wikidata; nothing saved.")
    json.dump(bio, open(P("list_bio.json"), "w"))
    print(f"Bios done: {len(bio)} athletes")
else:
    print("Bios: already done")

# ---------------------------------------------------------------- 3. athletics: its list pages pull each event's table in from a template
if not os.path.exists(P("list_templates.jsonl.gz")):
    names = set()
    for line in gzip.open(P("list_pages.jsonl.gz"), "rt", encoding="utf-8"):
        names |= set(re.findall(r"\{\{\s*(Olympic medalists in [^}|]+?)\s*\}\}", json.loads(line)["text"]))
    names = sorted(names)
    print(f"{len(names)} medalist templates (athletics)", flush=True)
    texts = []
    for n in range(0, len(names), 20):
        batch = ["Template:" + x for x in names[n:n + 20]]
        d = http(API + "?" + urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                                       "format": "json", "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(batch)}))
        for pg in d.get("query", {}).get("pages", []):
            text = pg["revisions"][0]["slots"]["main"].get("content", "") if pg.get("revisions") else ""
            texts.append({"title": pg["title"], "text": text})
        time.sleep(1)
    have = json.load(open(P("list_bio.json")))
    links = set()
    for x in texts:
        for m in re.finditer(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]", x["text"]):
            t = m.group(1).strip()
            if t and ":" not in t and "Olympics" not in t: links.add(t[:1].upper() + t[1:])
    links = sorted(t for t in links if t not in have)
    print(f"{len(texts)} templates downloaded; {len(links)} new people to look up", flush=True)
    for n in range(0, len(links), 200):
        vals = " ".join("<https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"), safe="") + ">" for t in links[n:n + 200])
        q = f"""SELECT ?art ?item ?name ?dob ?sexL ?pobL ?coord ?stateL ?countryL ?nocL ?oly WHERE {{
  VALUES ?art {{ {vals} }}
  ?art schema:about ?item . ?item wdt:P8286 ?oly .
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name)="en") }}
  OPTIONAL {{ ?item wdt:P569 ?dob }}
  OPTIONAL {{ ?item wdt:P21 ?sex . ?sex rdfs:label ?sexL FILTER(LANG(?sexL)="en") }}
  OPTIONAL {{ ?item wdt:P1532 ?noc . ?noc rdfs:label ?nocL FILTER(LANG(?nocL)="en") }}
  OPTIONAL {{ ?item wdt:P19 ?pob . ?pob rdfs:label ?pobL FILTER(LANG(?pobL)="en")
    OPTIONAL {{ ?pob wdt:P625 ?coord }}
    OPTIONAL {{ ?pob wdt:P131* ?st . ?st wdt:P31 wd:Q35657 . ?st rdfs:label ?stateL FILTER(LANG(?stateL)="en") }}
    OPTIONAL {{ ?pob wdt:P17 ?c . ?c rdfs:label ?countryL FILTER(LANG(?countryL)="en") }} }}
}}"""
        rows = http(SPARQL, urllib.parse.urlencode({"query": q, "format": "json"}).encode(), "application/sparql-results+json")["results"]["bindings"]
        for r in rows:
            t = urllib.parse.unquote(r["art"]["value"].split("/wiki/", 1)[1]).replace("_", " ")
            b = have.setdefault(t, {"qid": r["item"]["value"].rsplit("/", 1)[1]})
            for f, key in (("name", "name"), ("dob", "dob"), ("sexL", "sexL"), ("pobL", "pobL"), ("coord", "coord"), ("stateL", "stateL"),
                           ("countryL", "countryL"), ("nocL", "nocL"), ("oly", "olympedia")):
                if f in r and not b.get(key): b[key] = r[f]["value"]
        time.sleep(1)
    if sum(1 for x in texts if x["text"]) < 30: raise SystemExit("Too few templates came back; nothing saved.")
    json.dump(have, open(P("list_bio.json"), "w"))
    with gzip.open(P("list_templates.jsonl.gz"), "wt", encoding="utf-8") as out:
        for x in texts: out.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"Templates done; list_bio.json now has {len(have)} athletes", flush=True)
else:
    print("Templates: already done")
print("\nAll done: data-raw/olympics/list_pages.jsonl.gz, list_bio.json and list_templates.jsonl.gz")
