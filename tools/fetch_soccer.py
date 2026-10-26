#!/usr/bin/env python3
"""Download everything the soccer build needs, award-first:

1. The pages in tools/soccer_award_pages.txt: individual awards, World Cup / Women's World Cup / continental
   championship squads and finals, Champions League and Libertadores finals, MLS and NWSL honours.
2. Every person linked from those pages who is an association football player on Wikidata
   (birthplace, sex, clubs with years).
3. Each of those players' Wikipedia article: the infobox (clubs, caps, national team) and the Honours section,
   which is where club league titles and cups are listed.

Run from the trophycase folder:  python3 tools/fetch_soccer.py
Writes data-raw/soccer/: award_pages.jsonl.gz, bio.json, articles.jsonl.gz
Standard library only. Roughly 30-60 minutes. Safe to stop and re-run: finished steps are skipped and the article
step resumes where it stopped.
"""
import gzip, json, os, re, time, urllib.parse, urllib.request

UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
API = "https://en.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data-raw", "soccer")
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


def wiki_pages(titles):
    params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
              "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(titles)}
    q = http(API + "?" + urllib.parse.urlencode(params)).get("query", {})
    back = {}
    for m in q.get("normalized", []) + q.get("redirects", []):
        back[m["to"]] = back.get(m["from"], m["from"])
    for pg in q.get("pages", []):
        text = pg["revisions"][0]["slots"]["main"].get("content", "") if pg.get("revisions") else ""
        yield back.get(pg["title"], pg["title"]), pg["title"], text


# ---------------------------------------------------------------- 1. award, squad and final pages
if not os.path.exists(P("award_pages.jsonl.gz")):
    titles = [t.strip() for t in open(os.path.join(HERE, "soccer_award_pages.txt"), encoding="utf-8") if t.strip() and not t.startswith("#")]
    got, missing = 0, 0
    with gzip.open(P("award_pages.jsonl.gz.part"), "wt", encoding="utf-8") as out:
        for n in range(0, len(titles), 20):
            for req_t, page, text in wiki_pages(titles[n:n + 20]):
                if text: got += 1
                else: missing += 1
                out.write(json.dumps({"title": req_t, "page": page, "text": text}, ensure_ascii=False) + "\n")
            print(f"  pages {min(n + 20, len(titles))}/{len(titles)}", flush=True)
            time.sleep(1)
    if got < 150: raise SystemExit(f"Only {got} pages came back; nothing saved.")
    os.replace(P("award_pages.jsonl.gz.part"), P("award_pages.jsonl.gz"))
    print(f"Pages done: {got} downloaded, {missing} titles don't exist (fine: not every tournament has every page).\n")
else:
    print("Pages: already done")

# ---------------------------------------------------------------- 2. footballers linked from those pages
if not os.path.exists(P("bio.json")):
    links = set()
    for line in gzip.open(P("award_pages.jsonl.gz"), "rt", encoding="utf-8"):
        t = json.loads(line)["text"]
        for m in re.finditer(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]", t):
            x = m.group(1).strip()
            if x and ":" not in x and not re.search(r"^\d|national (football|soccer) team|F\.C\.|\bFC\b|\bCF\b|\bSC\b|Cup\b|League|Championship|Football|Association|Stadium|Olympics|^List of", x):
                links.add(x[:1].upper() + x[1:])
        for m in re.finditer(r"\{\{\s*(?:fs player|nat fs g player|nat fs player|football squad player)\s*\|[^}]*?\bname\s*=\s*\[\[([^\]|]+)", t, re.I):
            links.add(m.group(1).strip()[:1].upper() + m.group(1).strip()[1:])
    links = sorted(links)
    print(f"{len(links)} linked titles to check on Wikidata", flush=True)
    bio = {}
    for n in range(0, len(links), 150):
        vals = " ".join("<https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"), safe="") + ">" for t in links[n:n + 150])
        q = f"""SELECT ?art ?item ?name ?dob ?sexL ?pobL ?coord ?stateL ?countryL ?teamL ?s ?e WHERE {{
  VALUES ?art {{ {vals} }}
  ?art schema:about ?item . ?item wdt:P106 wd:Q937857 .
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name)="en") }}
  OPTIONAL {{ ?item wdt:P569 ?dob }}
  OPTIONAL {{ ?item wdt:P21 ?sex . ?sex rdfs:label ?sexL FILTER(LANG(?sexL)="en") }}
  OPTIONAL {{ ?item wdt:P19 ?pob . ?pob rdfs:label ?pobL FILTER(LANG(?pobL)="en")
    OPTIONAL {{ ?pob wdt:P625 ?coord }}
    OPTIONAL {{ ?pob wdt:P131* ?st . ?st wdt:P31 wd:Q35657 . ?st rdfs:label ?stateL FILTER(LANG(?stateL)="en") }}
    OPTIONAL {{ ?pob wdt:P17 ?c . ?c rdfs:label ?countryL FILTER(LANG(?countryL)="en") }} }}
  OPTIONAL {{ ?item p:P54 ?ts . ?ts ps:P54 ?team . ?team rdfs:label ?teamL FILTER(LANG(?teamL)="en")
    OPTIONAL {{ ?ts pq:P580 ?s }} OPTIONAL {{ ?ts pq:P582 ?e }} }}
}}"""
        rows = http(SPARQL, urllib.parse.urlencode({"query": q, "format": "json"}).encode(), "application/sparql-results+json")["results"]["bindings"]
        for r in rows:
            t = urllib.parse.unquote(r["art"]["value"].split("/wiki/", 1)[1]).replace("_", " ")
            b = bio.setdefault(t, {"qid": r["item"]["value"].rsplit("/", 1)[1], "teams": []})
            for f in ("name", "dob", "sexL", "pobL", "coord", "stateL", "countryL"):
                if f in r and not b.get(f): b[f] = r[f]["value"]
            if "teamL" in r:
                sp = [r["teamL"]["value"], r.get("s", {}).get("value", "")[:4], r.get("e", {}).get("value", "")[:4]]
                if sp not in b["teams"]: b["teams"].append(sp)
        if (n // 150) % 20 == 0: print(f"  checked {min(n + 150, len(links))}/{len(links)} - {len(bio)} footballers", flush=True)
        time.sleep(1)
    if len(bio) < 2000: raise SystemExit(f"Only {len(bio)} footballers matched; nothing saved.")
    json.dump(bio, open(P("bio.json"), "w"))
    print(f"Footballers done: {len(bio)}, {sum(1 for b in bio.values() if b.get('pobL'))} with a birthplace.\n")
else:
    print("Footballers: already done")

# ---------------------------------------------------------------- 3. each footballer's infobox + Honours section
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

def honours(text):
    m = re.search(r"(?im)^==\s*(Honours|Honors|Titles|Achievements|Honours and awards|Honors and awards|Career honours)\s*==\s*$", text)
    if not m: return ""
    rest = text[m.end():]
    e = re.search(r"(?m)^==[^=].*==\s*$", rest)
    return rest[:e.start() if e else len(rest)][:30000]

if not os.path.exists(P("articles.jsonl.gz")):
    bio = json.load(open(P("bio.json")))
    titles = sorted(bio)
    part = P("articles.jsonl.part")
    done = set()
    if os.path.exists(part):
        for line in open(part, encoding="utf-8"):
            try: done.add(json.loads(line)["title"])
            except Exception: pass
    todo = [t for t in titles if t not in done]
    print(f"Articles: {len(titles)} players, {len(done)} already fetched, {len(todo)} to go", flush=True)
    with open(part, "a", encoding="utf-8") as out:
        for n in range(0, len(todo), 50):
            for req_t, page, text in wiki_pages(todo[n:n + 50]):
                out.write(json.dumps({"title": req_t, "page": page, "infobox": infobox(text), "honours": honours(text)}, ensure_ascii=False) + "\n")
            out.flush()
            if (n // 50) % 20 == 0: print(f"  {min(n + 50, len(todo))}/{len(todo)}", flush=True)
            time.sleep(1)
    with open(part, "rb") as f, gzip.open(P("articles.jsonl.gz"), "wb") as g:
        g.write(f.read())
    print("Articles done.")
else:
    print("Articles: already done")
print("\nAll done. Files are in data-raw/soccer/: award_pages.jsonl.gz, bio.json, articles.jsonl.gz")
