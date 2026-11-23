#!/usr/bin/env python3
"""Check data/puzzles.json before pushing. Run from the repo root: python3 tools/check_puzzles.py

Each entry: "YYYY-MM-DD": {"id": "<room id>", "clues": [five strings], "team": "<optional>", "college": "<optional>"}
"team" and "college" pick which team or college the solved screen links to; leave them out to use the first listed.
"""
import json, re, sys, datetime, glob

def athletes():
    out = {}
    for line in open("index.html", encoding="utf-8"):
        if line.startswith("const A = "):
            for a in json.loads(line[len("const A = "):].rstrip().rstrip(";")):
                out[a["id"]] = {"name": a["name"], "teams": a.get("teams", []), "colleges": re.split(r"\s*/\s*|;\s*", a.get("college", "")), "featured": True}
            break
    for f in sorted(glob.glob("data/*.json")):
        if f.endswith(("puzzles.json", "curated.json", "world-110m.json")):
            continue
        d = json.load(open(f, encoding="utf-8"))
        for r in d.get("rows", []):
            if r[0] not in out:
                out[r[0]] = {"name": r[1], "teams": [d["teams"][i] for i in r[9]], "colleges": d["colleges"][r[8]].split("; "), "featured": False}
    try:
        cur = json.load(open("data/curated.json", encoding="utf-8"))
    except FileNotFoundError:
        cur = {}
    for i, c in cur.items():
        if i not in out:
            print(f"  ERROR: data/curated.json has an entry for {i!r}, which is not a room"); continue
        if c.get("teams"): out[i]["teams"] = c["teams"]
        if len(c.get("stories", [])) >= 3: out[i]["featured"] = True
    return out

def main():
    P = json.load(open("data/puzzles.json", encoding="utf-8"))
    A = athletes()
    errs, warns, seen = [], [], {}
    dates = sorted(P)
    for d in dates:
        p = P[d]
        try:
            datetime.date.fromisoformat(d)
        except ValueError:
            errs.append(f"{d}: not a YYYY-MM-DD date"); continue
        a = A.get(p.get("id"))
        if not a:
            errs.append(f"{d}: no room with id {p.get('id')!r}"); continue
        if p["id"] in seen:
            errs.append(f"{d}: {p['id']} is already the answer on {seen[p['id']]}")
        seen[p["id"]] = d
        cl = p.get("clues")
        if not (isinstance(cl, list) and len(cl) == 5 and all(isinstance(c, str) and c.strip() for c in cl)):
            errs.append(f"{d}: needs exactly five written clues (the site falls back to automatic clues otherwise)")
        else:
            parts = [w for w in re.split(r"[^A-Za-z']+", a["name"]) if len(w) > 2 and w not in ("Jr", "Sr")]
            for i, c in enumerate(cl, 1):
                for w in parts:
                    if re.search(r"\b" + re.escape(w) + r"\b", c, re.I):
                        warns.append(f"{d}: clue {i} contains the name part {w!r}")
        for k, have in (("team", a["teams"]), ("college", a["colleges"])):
            if p.get(k) and p[k] not in have:
                errs.append(f"{d}: {k} {p[k]!r} is not one of {a['name']}'s: {have}")
        if not a["featured"]:
            warns.append(f"{d}: {a['name']} is not a featured room (no written stories)")
    for x, y in zip(dates, dates[1:]):
        try:
            gap = (datetime.date.fromisoformat(y) - datetime.date.fromisoformat(x)).days
            if gap > 1:
                warns.append(f"gap: no puzzle scheduled between {x} and {y} (those days use the automatic pick)")
        except ValueError:
            pass
    print(f"{len(dates)} puzzles scheduled" + (f", {dates[0]} to {dates[-1]}" if dates else ""))
    for w in warns: print("  warning:", w)
    for e in errs: print("  ERROR:", e)
    sys.exit(1 if errs else 0)

if __name__ == "__main__":
    main()
