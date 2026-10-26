#!/usr/bin/env python3
"""Build data/nhl.json + data/nhl-rooms/ (hockey: NHL and WHA) for Trophy Case.

Inputs (from tools/fetch_nhl.py, in data-raw/nhl/):
  wd_bio.json            players with a Hockey Reference id (Wikidata): birthplace, Wikipedia link, team spells with years
  wd_awards.json         Wikidata award statements (fills gaps: Stanley Cup years, Halls of Fame)
  infobox.jsonl.gz       each player's Wikipedia infobox: teams, position, draft, career years, Hall of Fame year, medals
  award_pages.jsonl.gz   NHL trophy pages, All-Star / All-Rookie teams, Hall of Fame members, Olympic ice hockey medalists,
                         and every Stanley Cup Final page (the engraved roster gives each player's Cup years)
Also reads data/*.json (id clashes) and index.html (curated rooms).
Output: data/nhl.json (same compact layout as data/nfl.json, 16th column = summary line) and data/nhl-rooms/<0-255>.json

Hockey infoboxes carry no honors list, so honors come from the award pages (award-first), with Wikidata as backup.
"""
import gzip, json, os, re, sys, urllib.parse
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
RAW = os.path.join(ROOT, "data-raw", "nhl")
sys.path.insert(0, HERE)
from wiki_awards import fields
from wikihelp import norm, canon_title, plain, years_in, place, compress_years, the, ordinal, CUR
import olympic_lists

TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "ı": "i"})
import unicodedata
def slug(s):
    s = unicodedata.normalize("NFKD", s.translate(TRANSLIT)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")

bio = json.load(open(os.path.join(RAW, "wd_bio.json"), encoding="utf-8"))
wd_aw = json.load(open(os.path.join(RAW, "wd_awards.json"), encoding="utf-8"))
IB = {}
for line in gzip.open(os.path.join(RAW, "infobox.jsonl.gz"), "rt", encoding="utf-8"):
    x = json.loads(line); IB[x["title"]] = x
PAGES = {}
for line in gzip.open(os.path.join(RAW, "award_pages.jsonl.gz"), "rt", encoding="utf-8"):
    x = json.loads(line); PAGES[x["title"]] = x["text"]
print(f"{len(bio)} players on Wikidata, {len(IB)} articles, {len(PAGES)} award pages")

# ---------------------------------------------------------------- who is who
TITLE2KEY, NAME2KEYS = {}, defaultdict(list)
for k, b in bio.items():
    if b.get("wp") and "/wiki/" in b["wp"]: TITLE2KEY.setdefault(canon_title(b["wp"].split("/wiki/", 1)[1]), k)
    if b.get("name"): NAME2KEYS[norm(b["name"])].append(k)
for x in IB.values():
    if x.get("page") and x.get("id"): TITLE2KEY.setdefault(canon_title(x["page"]), x["id"])
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
def key_of(title):
    """Wikipedia title -> player; also tries the title without its "(ice hockey)"-style suffix (old links that now redirect)."""
    k = TITLE2KEY.get(canon_title(title))
    if not k and "(" in title: k = TITLE2KEY.get(canon_title(re.sub(r"\s*\(.*\)\s*$", "", title)))
    return k
SORTNAME = re.compile(r"\{\{\s*sortname\s*\|([^|}]*)\|([^|}]*)((?:\|[^}]*)?)\}\}", re.I)
def people_in(text):
    out = []
    for m in re.finditer(r"\{\{\s*sortname\s*\|[^}]*\}\}|\[\[[^\]]+\]\]", text, re.I):
        tok = m.group(0)
        sm = SORTNAME.match(tok)
        if sm:
            rest = sm.group(3) or ""
            tgt = re.search(r"\|\s*(?!dab=|nolink)([^|=}]+?)\s*(?:\||$)", rest)
            dab = re.search(r"dab=([^|}]+)", rest)
            k = None
            if tgt: k = TITLE2KEY.get(canon_title(tgt.group(1)))
            if not k and dab: k = TITLE2KEY.get(canon_title(f"{sm.group(1).strip()} {sm.group(2).strip()} ({dab.group(1).strip()})"))
            if not k: k = TITLE2KEY.get(canon_title(f"{sm.group(1).strip()} {sm.group(2).strip()}"))
            if k: out.append(k)
            continue
        lm = LINK.match(tok)
        if lm:
            k = key_of(lm.group(1))
            if k: out.append(k)
    seen = set()
    return [k for k in out if not (k in seen or seen.add(k))]

def row_year(row):
    m = re.search(r"\{\{\s*(?:nhly|nhl ?year|nhlyear|nhl season)\s*\|\s*(\d{4})", row, re.I)
    if m: return int(m.group(1)) + 1
    m = re.search(r"\b(1[89]\d\d|20[0-3]\d)\s*[–-]\s*(\d{2})\b", row)
    if m: return int(m.group(1)) + 1
    m = re.search(r"\b(19[0-9]\d|20[0-3]\d)\b", row)
    return int(m.group(1)) if m else None

def strip_refs(t):
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    return re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", t, flags=re.S)

AW = defaultdict(lambda: defaultdict(set))       # key -> (name, kind, shelf) -> years
def give(k, award, y):
    if k and y: AW[k][award].add(y)

def table_award(title, award, per_column=None, min_year=1900):
    """Every person in a row gets the award for that row's season. per_column: names for 1st, 2nd... person (All-Star teams)."""
    t = strip_refs(PAGES.get(title, ""))
    if not t: print("  missing page:", title); return 0
    n = 0
    for tm in re.finditer(r"\{\|(.*?)\n\|\}", t, re.S):
        y = None
        for row in re.split(r"\n\|-[^\n]*", tm.group(1)):
            ry = row_year(row)
            if ry: y = ry
            if not y or y < min_year: continue
            ks = people_in(row)
            for i, k in enumerate(ks):
                a = per_column[min(i, len(per_column) - 1)] if per_column else award
                give(k, a, y); n += 1
    return n

S, I, H, Sel = "Championships", "Individual", "Honors & Service", "Selections"
counts = {}
for page, name in (("Hart Memorial Trophy", "Hart Trophy (NHL MVP)"), ("Vezina Trophy", "Vezina Trophy"), ("James Norris Memorial Trophy", "Norris Trophy"),
                   ("Calder Memorial Trophy", "Calder Trophy (Rookie of the Year)"), ("Conn Smythe Trophy", "Conn Smythe Trophy"),
                   ("Art Ross Trophy", "Art Ross Trophy"), ('Maurice "Rocket" Richard Trophy', "Rocket Richard Trophy"),
                   ("Ted Lindsay Award", "Ted Lindsay Award"), ("Frank J. Selke Trophy", "Selke Trophy"),
                   ("Lady Byng Memorial Trophy", "Lady Byng Trophy"), ("Bill Masterton Memorial Trophy", "Masterton Trophy"),
                   ("King Clancy Memorial Trophy", "King Clancy Trophy"), ("Mark Messier Leadership Award", "Mark Messier Leadership Award"),
                   ("William M. Jennings Trophy", "Jennings Trophy"), ("Hobey Baker Award", "Hobey Baker Award")):
    shelf = H if name in ("King Clancy Trophy", "Masterton Trophy", "Lady Byng Trophy", "Mark Messier Leadership Award") else I
    counts[name] = table_award(page, (name, "statue" if shelf == I else "plaque", shelf))
counts["All-Star Team"] = table_award("NHL All-Star Team", None, per_column=[("NHL First All-Star Team", "statue", I), ("NHL Second All-Star Team", "star", Sel)])
counts["All-Rookie"] = table_award("NHL All-Rookie Team", ("NHL All-Rookie Team", "star", Sel))
counts["PWHL Playoff MVP"] = table_award("Walter Cup", ("PWHL Playoff MVP", "statue", I), min_year=2024)   # the only people linked in that table are the MVPs

# Hall of Fame: members list (year rows), infobox hall_of_fame field, Wikidata
HOF = {}
t = strip_refs(PAGES.get("List of members of the Hockey Hall of Fame", ""))
for tm in re.finditer(r"\{\|(.*?)\n\|\}", t, re.S):
    y = None
    for row in re.split(r"\n\|-[^\n]*", tm.group(1)):
        m = re.search(r"\|\s*(?:rowspan=\"?\d+\"?\s*\|\s*)?(19[4-9]\d|20[0-3]\d)\b", row)
        if m: y = int(m.group(1))
        for k in people_in(row):
            if y: HOF.setdefault(k, y)

# Stanley Cup: the engraved roster on each Final page
CUP = defaultdict(set)
for title, text in PAGES.items():
    m = re.match(r"(\d{4}) Stanley Cup (Final|Finals|playoffs)$", title)
    if not m or not text: continue
    y = int(m.group(1))
    for tm in re.finditer(r"\{\{\s*Stanley Cup champion\s*\|", text):
        depth, j = 0, tm.start()
        while j < len(text) - 1:
            two = text[j:j + 2]
            if two == "{{": depth += 1; j += 2; continue
            if two == "}}":
                depth -= 1; j += 2
                if depth == 0: break
                continue
            j += 1
        block = text[tm.start():j]
        block = re.split(r"\|\s*non-players\s*=", block)[0]
        for k in people_in(block): CUP[k].add(y)
print(f"Stanley Cup rosters: {sum(len(v) for v in CUP.values())} Cup wins for {len(CUP)} players; Hall of Fame list: {len(HOF)} players")

# Olympic ice hockey medals (players who also have an Olympics-wing room get them here instead)
OLY = defaultdict(list)
for who, color, year, event, games in olympic_lists.medals(PAGES.get("List of Olympic medalists in ice hockey", "")):
    if who.startswith("name:"):
        c_ = NAME2KEYS.get(norm(who[5:]), []); k = c_[0] if len(c_) == 1 else None
    else:
        k = key_of(who)
    if k: OLY[k].append((color, year))

# Wikidata backup
WD_MAP = {"Stanley Cup": "CUP", "Hockey Hall of Fame": "HOF", "Lester Patrick Trophy": ("Lester Patrick Trophy", "plaque", H),
          "Lester B. Pearson Award": ("Ted Lindsay Award", "statue", I), "NHL Plus-Minus Award": ("NHL Plus-Minus Award", "statue", I),
          "Canada's Sports Hall of Fame": ("Canada's Sports Hall of Fame", "plaque", H), "IIHF Hall of Fame": ("IIHF Hall of Fame", "plaque", H),
          "United States Hockey Hall of Fame": ("U.S. Hockey Hall of Fame", "plaque", H), "Order of Canada": ("Order of Canada", "medal", H),
          "Officer of the Order of Canada": ("Order of Canada", "medal", H), "Member of the Order of Canada": ("Order of Canada", "medal", H)}
wd_by = defaultdict(list)
for a in wd_aw: wd_by[a["id"]].append(a)

# ---------------------------------------------------------------- players
POS = [("goal", "G"), ("defen", "D"), ("left wing", "LW"), ("right wing", "RW"), ("centre", "C"), ("center", "C"), ("wing", "W"), ("forward", "F")]
POS_FULL = {"G": "Goaltender", "D": "Defenceman", "LW": "Left wing", "RW": "Right wing", "C": "Centre", "W": "Winger", "F": "Forward"}
def position(raw):
    p = plain(raw or "").lower()
    for k, ab in POS:
        if k in p: return ab
    return ""
def list_items(raw):
    raw = re.sub(r"\{\{\s*(?:plain ?list|ubl|unbulleted list|flatlist|hlist)\s*\|", "\n", raw or "", flags=re.I)
    raw = re.sub(r"\}\}\s*$", "", raw.strip())
    out = []
    for part in re.split(r"\n\s*\*?|<br\s*/?>|^\s*\*", plain(raw.replace("\n*", "\n"))):
      for p in part.split("|"):
        p = re.sub(r"\s*\(.*?\)\s*", " ", p).strip(" *}{,\n|")
        if p and len(p) < 50 and not re.search(r"^(class|style)=|\[\[|\]\]", p) and p not in out: out.append(p)
    return out

html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
i = html.index("const A = [") + len("const A = ")
CURATED, _ = json.JSONDecoder().raw_decode(html[i:])
cur_names = {norm(a["name"]) for a in CURATED}
taken = {a["id"] for a in CURATED}
for f_ in ("nfl.json", "mlb.json", "hoops.json", "olympics.json"):
    p = os.path.join(ROOT, "data", f_)
    if os.path.exists(p): taken |= {r[0] for r in json.load(open(p, encoding="utf-8"))["rows"]}

pre, stats, done_titles = [], Counter(), set()
for k, b in bio.items():
    wp = b.get("wp")
    if not wp or "/wiki/" not in wp: stats["no_article"] += 1; continue
    t = canon_title(wp.split("/wiki/", 1)[1])
    x = IB.get(t)
    if not x or not re.match(r"\{\{\s*Infobox\s+ice hockey", x["infobox"] or "", re.I): stats["no_hockey_infobox"] += 1; continue
    if t in done_titles: continue
    done_titles.add(t)
    f = fields(x["infobox"])
    name = plain(f.get("name", "")).split("\n")[0].strip() or b.get("name") or t
    if len(name) > 40 or not re.search(r"[A-Za-z]", name): name = b.get("name") or t
    name = re.sub(r"\s*\(.*?\)$", "", name)
    cs = years_in(plain(f.get("career_start", ""))); ce = years_in(plain(f.get("career_end", "")))
    teams = list_items(f.get("played_for", "")) or list_items(f.get("former_teams", ""))
    cur_team = plain(f.get("team", "")).strip()
    if cur_team and cur_team not in teams: teams.append(cur_team)
    spells = defaultdict(list)
    for tn, s_, e_ in b.get("teams", []):
        if s_.isdigit(): spells[norm(tn)].append((int(s_), int(e_) if e_.isdigit() else None))
    team_years = {}
    for tn in teams:
        ys = []
        for s_, e_ in spells.get(norm(tn), []):
            ys += list(range(s_, (e_ or s_) + 1)) if (e_ or s_) - s_ < 30 else [s_]
        team_years[tn] = ys
    y0 = cs[0] if cs else min((y for ys in team_years.values() for y in ys), default=None)
    if not y0: stats["no_years"] += 1; continue
    active = not ce and not f.get("death_date") and y0 >= CUR - 25
    y1 = CUR if active else (ce[-1] if ce else max((y for ys in team_years.values() for y in ys), default=y0))
    teams.sort(key=lambda tn: min(team_years[tn]) if team_years[tn] else 9999)
    aw = {}
    def add(n, kd, c, ys, x_=None):
        w = aw.setdefault(n, [kd, c, set(), 0]); w[2] |= set(ys); w[3] = max(w[3], x_ or 0)
    cups = set(CUP.get(k, ()))
    hof_y = HOF.get(k) or (years_in(plain(f.get("hall_of_fame", "")))[:1] or [None])[0]
    for a in wd_by.get(k, []):
        m = WD_MAP.get(a["award"]); ty = int(a["t"]) if a["t"].isdigit() else None
        if m == "CUP":
            if ty and not cups and y0 <= ty <= y1 + 1: cups.add(ty)
        elif m == "HOF":
            hof_y = hof_y or ty or 0
        elif m:
            add(m[0], m[1], m[2], [ty] if ty else [])
    if not cups and "Stanley Cup champions" in x.get("cats", []): add("Stanley Cup", "ring", S, [], 1)
    if cups: add("Stanley Cup", "ring", S, cups)
    for (n, kd, c), ys in AW.get(k, {}).items():
        ys = {y for y in ys if (y0 - 1 <= y <= y1 + 1) or n == "Hobey Baker Award"}
        if ys: add(n, kd, c, ys)
    oly = set(OLY.get(k, []))
    comp = ""
    for m_ in re.finditer(r"\{\{\s*Medal(Olympic|Competition|Gold|Silver|Bronze)\s*(?:\|((?:[^{}]|\{\{[^{}]*\}\})*))?\}\}", f.get("medal_templates", ""), re.I):
        kind_ = m_.group(1).lower()
        if kind_ in ("olympic", "competition"): comp = "Olympic Games" if kind_ == "olympic" else plain(m_.group(2) or ""); continue
        if re.search(r"Olympic", comp) and not re.search(r"Youth", comp):
            yy = years_in(plain((m_.group(2) or "").split("|")[0]))
            if yy: oly.add((kind_, yy[0]))
    for color, yy in oly: add(f"Olympic {color} medal", "medal", "International", [yy])
    if hof_y is not None or "Hockey Hall of Fame inductees" in x.get("cats", []):
        add("Hockey Hall of Fame", "plaque", H, [hof_y] if hof_y else [])
    if "IIHF Hall of Fame inductees" in x.get("cats", []): add("IIHF Hall of Fame", "plaque", H, [])
    awards, aw_years = [], {}
    for n, (kd, c, ys, x_) in aw.items():
        ys = {y for y in ys if y}
        cnt = max(len(ys), x_, 1)
        w = {"n": n, "k": kd, "c": c, "y": compress_years(ys)}
        if cnt > 1: w["x"] = cnt
        awards.append(w); aw_years[n] = (sorted(ys), cnt)
    hof = "Hockey Hall of Fame" in aw
    dy = years_in(plain(f.get("draft_year", "")))
    dteam = re.sub(r"\s*\(.*?\)\s*$", "", plain(f.get("draft_team", "")))
    dpick = re.findall(r"(\d+)\w*\s+overall", plain(f.get("draft", "")))
    draft = (dy[0], int(dpick[0]) if dpick else None, dteam) if dy and dteam and not re.search(r"undrafted", plain(f.get("draft", "")), re.I) else None
    sex = (b.get("sexL") or "").lower()
    poss = "her" if sex in ("female", "cisgender woman", "trans woman") or f.get("sex", "").strip().lower() == "f" else "his"
    league = "PWHL" if b.get("league") == "PWHL" else "NHL"
    pre.append(dict(k=k, name=name, poss=poss, league=league, teams=teams, team_years=team_years, y0=y0, y1=y1, active=active, hof=hof, awards=awards, aw_years=aw_years,
                    draft=draft, pos=position(f.get("position", "")), place=place(b),
                    wp=f"https://en.wikipedia.org/wiki/{urllib.parse.quote(t.replace(' ', '_'))}"))

def make_story(r):
    name, aw, teams, ty = r["name"], r["aw_years"], r["teams"], r["team_years"]
    def team_at(y):
        for tn in teams:
            if y in ty.get(tn, []): return tn
        return teams[0] if teams else ""
    c = []
    if r["draft"]:
        dy, pk, dt = r["draft"]
        c.append((dy, f"Drafted by {the(dt)}", f"The {dt} took {name}{f' with the {ordinal(pk)} overall pick' if pk else ''} in the {dy} {r['league']} draft.", 3))
    elif teams:
        t0 = teams[0] if teams and r["y0"] in ty.get(teams[0], []) else ""
        c.append((r["y0"], "Career begins", f"{name}'s playing career began in {r['y0']}{' with ' + the(t0) if t0 else ''}.", 1))
    if "Stanley Cup" in aw and aw["Stanley Cup"][0]:
        ys, n = aw["Stanley Cup"]; tm = team_at(ys[0])
        c.append((ys[0], "Lifts the Stanley Cup", f"{name}{' and ' + the(tm) if tm else ''} won the Stanley Cup in {ys[0]}." + (f" It was the first of {n}." if n > 1 else ""), 8))
    for n_, head, txt, pr in (("Hart Trophy (NHL MVP)", "Named NHL MVP", "{name} won the Hart Trophy as the NHL's most valuable player for {y}.", 9),
                              ("Conn Smythe Trophy", "Playoff MVP", "{name} won the Conn Smythe Trophy as playoff MVP in {y}.", 8),
                              ("Vezina Trophy", "Top goaltender", "{name} won the Vezina Trophy as the NHL's best goaltender for {y}.", 7),
                              ("Norris Trophy", "Top defenceman", "{name} won the Norris Trophy as the NHL's best defenceman for {y}.", 7),
                              ("Art Ross Trophy", "Scoring title", "{name} led the NHL in points to win the Art Ross Trophy for {y}.", 6),
                              ("Calder Trophy (Rookie of the Year)", "Rookie of the Year", "{name} won the Calder Trophy as the NHL's top rookie for {y}.", 5),
                              ("Olympic gold medal", "Olympic gold", "{name} won Olympic gold in {y}.", 6),
                              ("PWHL Playoff MVP", "Playoff MVP", "{name} was named MVP of the {y} PWHL playoffs.", 8),
                              ("NHL First All-Star Team", "First All-Star Team", "{name} was named to the NHL's First All-Star Team for {y}.", 3)):
        if n_ in aw and aw[n_][0]:
            ys, n = aw[n_]
            c.append((ys[0], head, txt.format(name=name, y=ys[0]) + (f" It was the first of {n}." if n > 1 else ""), pr))
    if len(teams) > 1 and ty.get(teams[1]):
        y = min(ty[teams[1]]); c.append((y, f"Joins {the(teams[1])}", f"{name} moved from {the(teams[0])} to {the(teams[1])} in {y}.", 2))
    if "Hockey Hall of Fame" in aw:
        ys = aw["Hockey Hall of Fame"][0]
        c.append((ys[0] if ys else 9999, "Enshrined in Toronto", f"{name} was inducted into the Hockey Hall of Fame{' in ' + str(ys[0]) if ys else ''}.", 10))
    top = sorted(c, key=lambda z: -z[3])[:3]; top.sort(key=lambda z: z[0])
    return [[str(z[0]) if z[0] != 9999 else "Toronto", z[1], z[2]] for z in top]

LINE_ORDER = ["Hockey Hall of Fame", "Stanley Cup", "PWHL Playoff MVP", "Hart Trophy (NHL MVP)", "Conn Smythe Trophy", "Vezina Trophy", "Norris Trophy", "Art Ross Trophy",
              "Olympic gold medal", "Calder Trophy (Rookie of the Year)", "NHL First All-Star Team"]
LBL = {"Hockey Hall of Fame": "Hall of Famer", "Stanley Cup": "Stanley Cup champion", "Hart Trophy (NHL MVP)": "Hart Trophy winner",
       "Olympic gold medal": "Olympic gold medalist", "Calder Trophy (Rookie of the Year)": "Calder Trophy winner"}
def make_line(r, era):
    who = POS_FULL.get(r["pos"], "Player"); tm = r["teams"]
    if r["league"] == "PWHL" and who == "Defenceman": who = "Defender"
    tl = " and ".join(tm) if len(tm) <= 2 else f"{tm[0]}, {tm[1]} and {len(tm) - 2} other team{'s' if len(tm) > 3 else ''}"
    aw = {w["n"]: w for w in r["awards"]}; hl = []
    for n in LINE_ORDER:
        if n in aw:
            x = aw[n].get("x", 1); l = LBL.get(n, n); hl.append(f"{x}× {l}" if x > 1 else l)
        if len(hl) == 3: break
    return (f"{who} for the {tl}, {era}." if tl else f"{who}, {era}.") + (" " + ", ".join(hl) + "." if hl else "")

pre.sort(key=lambda r: (-sum(w.get("x", 1) for w in r["awards"]), r["y0"]))
out, ids = [], set()
for r in pre:
    if norm(r["name"]) in cur_names: stats["curated"] += 1; continue
    grp = "active" if r["active"] else ("hof" if r["hof"] else "past"); stats[grp] += 1
    pl = r["place"]
    if pl: stats["with_birthplace"] += 1
    base = slug(r["name"]) or "player"; rid = base
    if rid in ids or rid in taken:
        rid = f"{base}-{r['y0']}"; n = 2
        while rid in ids or rid in taken: rid = f"{base}-{r['y0']}-{n}"; n += 1
    ids.add(rid)
    era = f"{r['y0']}–present" if grp == "active" else (f"{r['y0']}" if r["y0"] == r["y1"] else f"{r['y0']}–{r['y1']}")
    cups = r["aw_years"].get("Stanley Cup", ([], 0))[1]
    st = [["Pro seasons", str(max(1, (r["y1"] - r["y0"] + 1)))]] + ([["Stanley Cups", str(cups)]] if cups else []) + \
         ([["Drafted", f"{r['draft'][0]}{', ' + ordinal(r['draft'][1]) + ' overall' if r['draft'][1] else ''}"]] if r["draft"] else [])
    out.append({"id": rid, "name": r["name"], "pos": r["pos"], "grp": grp, "born": pl[0] if pl else "", "region": pl[1] if pl else "",
                "lat": pl[2] if pl else None, "lon": pl[3] if pl else None, "college": "—", "teams": r["teams"], "era": era, "jersey": None,
                "awards": r["awards"], "wv": ["born"] if pl and pl[1] == "West Virginia" else [], "src": r["wp"],
                "stories": make_story(r), "stats": st, "line": make_line(r, era.replace("–present", " to now"))})

def table(vals):
    order = [v for v, _ in Counter(vals).most_common()]
    return order, {v: i for i, v in enumerate(order)}
T_team, T_team_i = table(t for r in out for t in r["teams"])
T_born, T_born_i = table(r["born"] for r in out)
T_reg, T_reg_i = table(r["region"] for r in out)
T_aw, T_aw_i = table((w["n"], w["k"], w["c"]) for r in out for w in r["awards"])
GRP = {"active": 0, "hof": 1, "past": 2}
rows_out = [[r["id"], r["name"], r["pos"], GRP[r["grp"]], T_born_i[r["born"]], T_reg_i[r["region"]], r["lat"], r["lon"], 0,
             [T_team_i[t] for t in r["teams"]], r["era"], r["jersey"], [[T_aw_i[(w["n"], w["k"], w["c"])], w["y"], w.get("x", 0)] for w in r["awards"]],
             r["wv"], r["src"], r["line"]] for r in sorted(out, key=lambda r: (GRP[r["grp"]], r["name"]))]
doc = {"v": 2, "built": CUR, "sport": "Hockey", "rooms": "nhl-rooms", "teams": T_team, "colleges": ["—"], "born": T_born, "regions": T_reg,
       "awards": [list(a) for a in T_aw], "rows": rows_out}
def shard(s_):
    h = 7
    for ch in s_: h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % 256
rooms_dir = os.path.join(ROOT, "data", "nhl-rooms"); os.makedirs(rooms_dir, exist_ok=True)
shards = defaultdict(dict)
for r in out: shards[shard(r["id"])][r["id"]] = [r["stories"], r["stats"]]
for k_ in range(256):
    json.dump(shards.get(k_, {}), open(os.path.join(rooms_dir, f"{k_}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
outp = os.path.join(ROOT, "data", "nhl.json")
json.dump(doc, open(outp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"Wrote {outp}: {len(rows_out)} players, {os.path.getsize(outp)/1e6:.1f} MB")
print("Groups:", dict(stats))
print("Award rows from the lists:", counts)
print("Top awards:", Counter(w["n"] for r in out for w in r["awards"]).most_common(25))

# Site policy: no Russia-born athletes, no Russian awards (see tools/exclude_russia.py).
import subprocess as _sp
_sp.run([sys.executable, os.path.join(HERE, "exclude_russia.py")], check=True)
