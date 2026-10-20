#!/usr/bin/env python3
"""Download the wikitext of the award-list pages named in tools/award_pages.txt.

Run from the trophycase folder:  python3 tools/fetch_pages.py
Writes data-raw/award_pages.jsonl.gz  - {"title","page","text"} per page (missing pages get text "").
About 450 pages in batches of 20; takes ~2-4 minutes. Re-run safely: it starts over.
"""
import gzip, json, os, time, urllib.parse, urllib.request

API = "https://en.wikipedia.org/w/api.php"
UA = "TrophyCaseBot/0.1 (https://trophycase.fyi)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data-raw", "award_pages.jsonl.gz")
titles = [t.strip() for t in open(os.path.join(HERE, "award_pages.txt"), encoding="utf-8") if t.strip()]

def get(batch, tries=6):
    url = API + "?" + urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
        "format": "json", "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(batch)})
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip": raw = gzip.decompress(raw)
            d = json.loads(raw)
            if d.get("error", {}).get("code") == "maxlag": time.sleep(5 * (i + 1)); continue
            return d
        except Exception as e:
            print(f"  retry {i+1}: {e}", flush=True); time.sleep(5 * (i + 1))
    raise SystemExit("Wikipedia kept failing; try again later.")

got = 0
with gzip.open(OUT, "wt", encoding="utf-8") as out:
    for n in range(0, len(titles), 20):
        batch = titles[n:n + 20]
        q = get(batch).get("query", {})
        back = {}
        for m in q.get("normalized", []) + q.get("redirects", []):
            back[m["to"]] = back.get(m["from"], m["from"])
        for pg in q.get("pages", []):
            text = pg["revisions"][0]["slots"]["main"].get("content", "") if pg.get("revisions") else ""
            got += bool(text)
            out.write(json.dumps({"title": back.get(pg["title"], pg["title"]), "page": pg["title"], "text": text}, ensure_ascii=False) + "\n")
        print(f"{min(n + 20, len(titles))}/{len(titles)}", flush=True)
        time.sleep(1)
print(f"Done: {got} of {len(titles)} award pages -> data-raw/award_pages.jsonl.gz")
