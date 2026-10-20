#!/usr/bin/env python3
"""Download the Wikipedia infobox (career highlights, awards, stats, draft) for every NFL player
that Wikidata links to a Wikipedia article.

Run from the trophycase folder:  python3 tools/fetch_wiki.py
Reads  data-raw/wd_bio.json  (from fetch_wikidata.py)
Writes data-raw/wiki_infobox.jsonl.gz  - one line per player: {"pfr", "title", "infobox", "hof"}
Takes ~15-25 minutes (about 550 requests of 50 pages, one at a time, per Wikipedia's API etiquette).
Safe to stop and re-run: it resumes where it left off.
"""
import gzip, json, os, sys, time, urllib.parse, urllib.request

API = "https://en.wikipedia.org/w/api.php"
UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data-raw")
OUT = os.path.join(ROOT, "wiki_infobox.jsonl.gz")
PART = OUT + ".part"

bio = json.load(open(os.path.join(ROOT, "wd_bio.json")))
want = {}
for k, b in bio.items():
    wp = b.get("wp")
    if wp and "/wiki/" in wp:
        want[urllib.parse.unquote(wp.split("/wiki/", 1)[1]).replace("_", " ")] = k.split("/")[-1]
titles = sorted(want)
done = set()
if os.path.exists(PART):
    for line in open(PART, encoding="utf-8"):
        try: done.add(json.loads(line)["title"])
        except Exception: pass
todo = [t for t in titles if t not in done]
print(f"{len(titles)} articles, {len(done)} already fetched, {len(todo)} to go", flush=True)


def infobox(text):
    """Return the first {{Infobox ...}} template (balanced braces), or ''."""
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


def get(batch, tries=6):
    params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
              "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(batch)}
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip": raw = gzip.decompress(raw)
                d = json.loads(raw)
            if "error" in d and d["error"].get("code") == "maxlag":
                time.sleep(5 * (i + 1)); continue
            return d
        except Exception as e:
            print(f"  retry {i+1}: {e}", flush=True); time.sleep(5 * (i + 1))
    raise SystemExit("Wikipedia kept failing; re-run later and it will resume.")


with open(PART, "a", encoding="utf-8") as out:
    for n in range(0, len(todo), 50):
        batch = todo[n:n + 50]
        d = get(batch)
        q = d.get("query", {})
        back = {}  # resolved title -> requested title
        for m in q.get("normalized", []) + q.get("redirects", []):
            back[m["to"]] = back.get(m["from"], m["from"])
        for pg in q.get("pages", []):
            req_title = back.get(pg["title"], pg["title"])
            if req_title not in want:
                req_title = back.get(back.get(pg["title"], ""), req_title)
            text = ""
            if pg.get("revisions"):
                text = pg["revisions"][0]["slots"]["main"].get("content", "")
            ib = infobox(text)
            cats_hof = "Pro Football Hall of Fame inductees" in text
            out.write(json.dumps({"title": req_title, "pfr": want.get(req_title, ""), "page": pg["title"],
                                  "infobox": ib, "hof": cats_hof}, ensure_ascii=False) + "\n")
        out.flush()
        if (n // 50) % 20 == 0:
            print(f"{min(n + 50, len(todo))}/{len(todo)}", flush=True)
        time.sleep(1)

with open(PART, "rb") as f, gzip.open(OUT, "wb") as g:
    g.write(f.read())
print(f"Done: {sum(1 for _ in open(PART, encoding='utf-8'))} infoboxes -> data-raw/wiki_infobox.jsonl.gz")
