#!/usr/bin/env python3
"""Build data/olympics.json + data/olympics-rooms/ (Olympic medalists, Summer and Winter) for Trophy Case.

Inputs, in data-raw/olympics/:
  list_pages.jsonl.gz   Wikipedia "List of Olympic medalists in ..." pages (tools/fetch_olympic_lists.py) - main source
  list_bio.json         Wikidata bios for the people those pages link to
  medals.json, bio.json Wikidata medal statements (tools/fetch_olympics.py) - second source, fills gaps
Also reads data/nfl.json, mlb.json, hoops.json (id clashes, people already on the site) and index.html (curated rooms).
Output: data/olympics.json (same compact layout as data/nfl.json, plus a 16th column: the room's summary line)
        data/olympics-rooms/<0-255>.json
"""
import gzip, json, os, re, sys, unicodedata, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data-raw", "olympics")
CUR = 2026

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", "", re.sub(r"[.'’\-]", " ", s)).split())
TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "þ": "th", "ð": "d", "ı": "i"})
def slug(s):
    s = unicodedata.normalize("NFKD", s.translate(TRANSLIT)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")
def canon_title(t):
    t = urllib.parse.unquote(t.split("#")[0]).replace("_", " ").strip()
    return t[:1].upper() + t[1:] if t else t

# ---------------------------------------------------------------- sports
SPORT = [  # (pattern on Wikidata sport label or list-page title, display sport)
    (r"swimm(?!ing pool)|open water|synchroni|artistic swimming", "Swimming"), (r"diving", "Diving"), (r"water polo", "Water Polo"),
    (r"athletics|track and field|marathon|1500 metres", "Track"), (r"gymnastics|trampoline|^gymnastics", "Gymnastics"),
    (r"shooting", "Shooting"), (r"archery", "Archery"), (r"fencing", "Fencing"), (r"boxing", "Boxing"), (r"wrestling", "Wrestling"),
    (r"judo", "Judo"), (r"taekwondo", "Taekwondo"), (r"karate", "Karate"), (r"weightlifting", "Weightlifting"),
    (r"canoe|kayak", "Canoeing"), (r"rowing", "Rowing"), (r"sailing|yachting", "Sailing"), (r"triathlon", "Triathlon"),
    (r"modern pentathlon", "Modern Pentathlon"), (r"equestrian|show jumping|eventing|dressage", "Equestrian"),
    (r"cycl|bmx|mountain bik", "Cycling"), (r"tennis(?! table)|ladies' singles|men's singles", "Tennis"), (r"table tennis", "Table Tennis"),
    (r"badminton", "Badminton"), (r"golf", "Golf"), (r"beach volleyball", "Beach Volleyball"), (r"volleyball", "Volleyball"),
    (r"handball", "Handball"), (r"field hockey", "Field Hockey"), (r"ice hockey", "Hockey"), (r"association football|football", "Soccer"),
    (r"rugby", "Rugby"), (r"basketball", "Basketball"), (r"baseball|softball", "Baseball"),
    (r"alpine skiing", "Alpine Skiing"), (r"cross-country skiing", "Cross-Country Skiing"), (r"ski jumping", "Ski Jumping"),
    (r"nordic combined", "Nordic Combined"), (r"freestyle skiing", "Freestyle Skiing"), (r"ski mountaineering", "Ski Mountaineering"),
    (r"nordic skiing", "Cross-Country Skiing"), (r"biathlon", "Biathlon"), (r"snowboard", "Snowboarding"),
    (r"speed skating|short.track", "Speed Skating"), (r"figure skating|pair skating|ice dance", "Figure Skating"),
    (r"bobsleigh|bobsled", "Bobsled"), (r"skeleton", "Skeleton"), (r"luge", "Luge"), (r"curling", "Curling"),
    (r"skateboard", "Skateboarding"), (r"surfing", "Surfing"), (r"climbing", "Climbing"), (r"breaking|breakdanc", "Breaking"),
    (r"polo", "Polo"), (r"tug of war", "Tug of War"), (r"art competition", "Art Competitions"), (r"lacrosse", "Lacrosse"),
]
def sport_of(label):
    for pat, s in SPORT:
        if re.search(pat, label or "", re.I): return s
    return (label or "Olympics").strip().title()

# ---------------------------------------------------------------- medals from Wikidata (second source)
MEDALS = defaultdict(list)       # key -> [(color, year, event, sport, games)]
bio = {}                          # key -> bio dict ; key = Wikipedia title when known, else "Q..."
WD_BIO = json.load(open(os.path.join(RAW, "bio.json"), encoding="utf-8"))
qid2key = {}
for q, b in WD_BIO.items():
    k = canon_title(b["wp"].split("/wiki/", 1)[1]) if b.get("wp") else q
    qid2key[q] = k; bio[k] = dict(b, qid=q)
def clean_event(ev):
    ev = re.sub(r"^.*?\d{4} (?:Summer|Winter) Olympics\s*[–-]\s*", "", ev or "")
    return ev.strip()
wd_rows = json.load(open(os.path.join(RAW, "medals.json"), encoding="utf-8"))
for r in wd_rows:
    k = qid2key.get(r["item"]) or r["item"]
    if not r["year"]: continue
    MEDALS[k].append((r["medal"], int(r["year"]), clean_event(r["event"]), sport_of(r["sport"] or r["event"]), r["games"], "wd"))

# ---------------------------------------------------------------- medals from the Wikipedia lists (main source)
LP = os.path.join(RAW, "list_pages.jsonl.gz")
list_stats = Counter()
if os.path.exists(LP):
    LB = json.load(open(os.path.join(RAW, "list_bio.json"), encoding="utf-8"))
    for t, b in LB.items(): bio.setdefault(canon_title(t), b)
    import olympic_lists
    NAME_IX = defaultdict(list)
    for t_, b_ in list(LB.items()) + [(k_, b_) for k_, b_ in bio.items() if not k_.startswith("Q")]:
        for nm_ in {b_.get("name", ""), re.sub(r"\s*\(.*?\)$", "", t_)}:
            if nm_ and canon_title(t_) not in NAME_IX[norm(nm_)]: NAME_IX[norm(nm_)].append(canon_title(t_))
    pages = [json.loads(line) for line in gzip.open(LP, "rt", encoding="utf-8")]
    TP = os.path.join(RAW, "list_templates.jsonl.gz")
    if os.path.exists(TP):   # athletics events live in templates, one per event
        pages += [dict(json.loads(line), sport="athletics") for line in gzip.open(TP, "rt", encoding="utf-8")]
    else:
        print("Athletics templates not downloaded yet: track and field relies on Wikidata medals only")
    for pg in pages:
        sp = sport_of(pg.get("sport") or re.sub(r"^List of Olympic medalists in ", "", pg["title"]))
        dflt = re.sub(r"^Template:Olympic medal(?:l)?ists in (?:the )?", "", pg["title"])
        dflt = dflt[:1].upper() + dflt[1:] if pg["title"].startswith("Template:") else ""
        for title, color, year, event, games in olympic_lists.medals(pg["text"], dflt):
            if title.startswith("name:"):
                c = NAME_IX.get(norm(title[5:]), [])
                if len(c) != 1: list_stats["unlinked_unmatched"] += 1; continue
                title = c[0]; list_stats["unlinked_matched"] += 1
            k = canon_title(title)
            if k not in LB and k not in bio: list_stats["not_a_known_athlete"] += 1; continue
            MEDALS[k].append((color, year, event, sp, games, "list"))
            list_stats["medals"] += 1
print("Medalist lists:", dict(list_stats) if list_stats else "not downloaded yet; Wikidata medals only")

# The lists are complete event by event, so where an athlete has list medals in a sport, their Wikidata medals in that
# sport are dropped; Wikidata only fills sports the lists don't cover. Exact repeats inside a source are removed too.
def ev_key(e): return norm(e)[:60]
for k, ms in MEDALS.items():
    list_sports = {m[3] for m in ms if m[5] == "list"}
    seen, keep = set(), []
    for m in ms:
        if m[5] == "wd" and m[3] in list_sports: continue
        kk = (m[0], m[1], ev_key(m[2]), m[5])
        if kk in seen: continue
        seen.add(kk); keep.append(m)
    MEDALS[k] = keep

# ---------------------------------------------------------------- birthplaces (same rules as football)
STATE_ABBR = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT","Delaware":"DE",
 "Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
 "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE",
 "Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH",
 "Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX",
 "Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"}
COUNTRY_FIX = {"People's Republic of China": "China", "Kingdom of the Netherlands": "Netherlands", "Union of Soviet Socialist Republics": "Soviet Union",
               "Republic of Ireland": "Ireland", "Georgia": "Georgia (country)", "Federal Republic of Germany": "Germany",
               "German Democratic Republic": "East Germany", "Socialist Federal Republic of Yugoslavia": "Yugoslavia", "Kingdom of Yugoslavia": "Yugoslavia"}
def place(b):
    if not b or not b.get("pobL") or not b.get("coord"): return None
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"])
    if not m: return None
    lon, lat = float(m.group(1)), float(m.group(2))
    town = re.sub(r",.*$", "", b["pobL"]).strip()
    st, ctry = b.get("stateL"), b.get("countryL")
    if st in STATE_ABBR: return f"{town}, {STATE_ABBR[st]}", st, round(lat, 3), round(lon, 3)
    if "Washington, D.C." in b["pobL"]: return "Washington, DC", "District of Columbia", round(lat, 3), round(lon, 3)
    if ctry and ctry != "United States":
        ctry = COUNTRY_FIX.get(ctry, ctry)
        return f"{town}, {ctry}", ctry, round(lat, 3), round(lon, 3)
    return None

# ---------------------------------------------------------------- people already on the site
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
i = html.index("const A = [") + len("const A = ")
CURATED, _ = json.JSONDecoder().raw_decode(html[i:])
cur_names = {norm(a["name"]) for a in CURATED}
taken = {a["id"] for a in CURATED}
on_site = defaultdict(set)   # name -> sports already covered by generated wings
for f_, sp in (("nfl.json", "Football"), ("mlb.json", "Baseball"), ("hoops.json", "Basketball"), ("nhl.json", "Hockey")):
    p = os.path.join(ROOT, "data", f_)
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        for r in d["rows"]: taken.add(r[0]); on_site[norm(r[1])].add(sp)

# ---------------------------------------------------------------- assemble
COLOR_ORDER = {"gold": 0, "silver": 1, "bronze": 2}
def games_name(g, y):
    g = g or ""
    m = re.match(r"(\d{4}) (Summer|Winter) Olympics", g)
    return f"the {m.group(1)} {m.group(2)} Olympics" if m else f"the {y} Olympics"
def compress_years(ys):
    ys = sorted(set(ys))
    if not ys: return ""
    out, s, q = [], ys[0], ys[0]
    for y in ys[1:]:
        if y != q + 1: out.append(f"{s}" if s == q else f"{s}–{q}"); s = y
        q = y
    out.append(f"{s}" if s == q else f"{s}–{q}")
    return ", ".join(out)

out, ids, stats = [], set(), Counter()
people = sorted(MEDALS.items(), key=lambda kv: (-len(kv[1]), kv[0]))
for k, ms in people:
    if not ms: continue
    b = bio.get(k, {})
    name = b.get("name") or re.sub(r"\s*\(.*?\)$", "", k if not k.startswith("Q") else "")
    if not name: stats["no_name"] += 1; continue
    nn = norm(name)
    sports = Counter(m[3] for m in ms)
    sport = sports.most_common(1)[0][0]
    if nn in cur_names: stats["curated"] += 1; continue
    if sport in on_site.get(nn, set()): stats["already_on_site"] += 1; continue   # e.g. NBA players' Olympic golds are in their basketball rooms
    years = sorted({m[1] for m in ms})
    y0, y1 = years[0], years[-1]
    sex = (b.get("sexL") or "").lower()
    poss = "her" if sex in ("female", "cisgender woman", "trans woman") else ("their" if sex == "non-binary" else "his")
    country = b.get("nocL") or b.get("countryL") or ""   # team country; birth country only when Wikidata has no team
    country = COUNTRY_FIX.get(country, country)
    awards = []
    for color in ("gold", "silver", "bronze"):
        ys = [m[1] for m in ms if m[0] == color]
        if ys:
            w = {"n": f"Olympic {color} medal", "k": "medal", "c": "International", "y": compress_years(ys)}
            if len(ys) > 1: w["x"] = len(ys)
            awards.append(w)
    g = Counter(m[0] for m in ms)
    pl = place(b)
    grp = "active" if y1 >= 2022 else "past"
    stats[grp] += 1
    if pl: stats["with_birthplace"] += 1
    base = slug(name) or "athlete"
    rid = base
    if rid in ids or rid in taken:
        rid = f"{base}-{y0}"; n = 2
        while rid in ids or rid in taken: rid = f"{base}-{y0}-{n}"; n += 1
    ids.add(rid)
    # Big moments: first medal, biggest Games, last medal
    ms_sorted = sorted(ms, key=lambda m: (m[1], COLOR_ORDER[m[0]]))
    first = ms_sorted[0]
    by_games = Counter((m[1], m[4]) for m in ms)
    stories = [[str(first[1]), f"First Olympic medal: {first[0]}", f"{name} won {first[0]} in {first[2] or first[3].lower()} at {games_name(first[4], first[1])}."]]
    (bg_y, bg_g), bg_n = by_games.most_common(1)[0]
    if bg_n > 1:
        golds = sum(1 for m in ms if (m[1], m[4]) == (bg_y, bg_g) and m[0] == "gold")
        stories.append([str(bg_y), f"{bg_n} medals in {bg_y}", f"{name} won {bg_n} medals at {games_name(bg_g, bg_y)}" + (f", {golds} of them gold." if golds else ".")])
    golds = [m for m in ms_sorted if m[0] == "gold"]
    if golds and golds[0] is not first and not (bg_n > 1 and golds[0][1] == bg_y):
        gm = golds[0]
        stories.append([str(gm[1]), "Olympic champion", f"{name} won gold in {gm[2] or gm[3].lower()} at {games_name(gm[4], gm[1])}."])
    last = ms_sorted[-1]
    if len(years) > 1 and len(stories) < 3:
        stories.append([str(last[1]), "Last Olympic medal", f"{name} won {last[0]} in {last[2] or last[3].lower()} at {games_name(last[4], last[1])}, {len(years)} Games after {poss} first medal." if False else
                        f"{name} won {last[0]} in {last[2] or last[3].lower()} at {games_name(last[4], last[1])}, {poss} last Olympic medal."])
    stories = sorted(stories[:3], key=lambda s: s[0])
    stat_rows = [["Olympic medals", str(len(ms))], ["Gold", str(g["gold"])], ["Silver", str(g["silver"])], ["Bronze", str(g["bronze"])],
                 ["Olympic Games with a medal", str(len(years))]]
    era = f"{y0}" if y0 == y1 else f"{y0}–{y1}"
    tally = ", ".join(f"{g[c]} {c}" for c in ("gold", "silver", "bronze") if g[c])
    who = {"Track": "Track and field athlete", "Swimming": "Swimmer", "Gymnastics": "Gymnast", "Shooting": "Shooter", "Rowing": "Rower",
           "Cycling": "Cyclist", "Boxing": "Boxer", "Wrestling": "Wrestler", "Fencing": "Fencer", "Diving": "Diver"}.get(sport, f"{sport} Olympian")
    line = f"{who}{' for ' + country if country else ''}, {era}. {len(ms)} Olympic medal{'s' if len(ms) != 1 else ''} ({tally})."
    wv = ["born"] if pl and pl[1] == "West Virginia" else []
    src = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(k.replace(' ', '_'))}" if not k.startswith("Q") else \
          (f"https://www.olympedia.org/athletes/{b['olympedia']}" if b.get("olympedia") else "")
    out.append({"id": rid, "name": name, "pos": "", "grp": grp, "sport": sport, "born": pl[0] if pl else "", "region": pl[1] if pl else "",
                "lat": pl[2] if pl else None, "lon": pl[3] if pl else None, "college": "—", "teams": [country] if country else [],
                "era": era, "awards": awards, "wv": wv, "src": src, "stories": stories, "stats": stat_rows, "line": line})

# ---------------------------------------------------------------- compact encode (+ column 15: line, column 16: sport index)
def table(vals):
    order = [v for v, _ in Counter(vals).most_common()]
    return order, {v: i for i, v in enumerate(order)}
T_team, T_team_i = table(t for r in out for t in r["teams"])
T_born, T_born_i = table(r["born"] for r in out)
T_reg, T_reg_i = table(r["region"] for r in out)
T_aw, T_aw_i = table((w["n"], w["k"], w["c"]) for r in out for w in r["awards"])
T_sp, T_sp_i = table(r["sport"] for r in out)
GRP = {"active": 0, "hof": 1, "past": 2}
rows_out = [[r["id"], r["name"], r["pos"], GRP[r["grp"]], T_born_i[r["born"]], T_reg_i[r["region"]], r["lat"], r["lon"], 0,
             [T_team_i[t] for t in r["teams"]], r["era"], None, [[T_aw_i[(w["n"], w["k"], w["c"])], w["y"], w.get("x", 0)] for w in r["awards"]],
             r["wv"], r["src"], r["line"], T_sp_i[r["sport"]]] for r in sorted(out, key=lambda r: (GRP[r["grp"]], r["name"]))]
doc = {"v": 2, "built": CUR, "sport": "Olympics", "sports": T_sp, "rooms": "olympics-rooms", "teams": T_team, "colleges": ["—"],
       "born": T_born, "regions": T_reg, "awards": [list(a) for a in T_aw], "rows": rows_out}
def shard(s_):
    h = 7
    for ch in s_: h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % 256
rooms_dir = os.path.join(ROOT, "data", "olympics-rooms"); os.makedirs(rooms_dir, exist_ok=True)
shards = defaultdict(dict)
for r in out: shards[shard(r["id"])][r["id"]] = [r["stories"], r["stats"]]
for k_ in range(256):
    json.dump(shards.get(k_, {}), open(os.path.join(rooms_dir, f"{k_}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
outp = os.path.join(ROOT, "data", "olympics.json")
json.dump(doc, open(outp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"Wrote {outp}: {len(rows_out)} medalists, {sum(len(MEDALS[k]) for k in MEDALS)} medals, {os.path.getsize(outp)/1e6:.1f} MB")
print("Groups:", dict(stats))
print("Sports:", Counter(r["sport"] for r in out).most_common(60))

# Site policy: no Russia-born athletes, no Russian awards (see tools/exclude_russia.py).
import subprocess as _sp, sys as _sys
_sp.run([_sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "exclude_russia.py")], check=True)
