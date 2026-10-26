#!/usr/bin/env python3
"""Build data/hoops.json + data/hoops-rooms/ (basketball: NBA, ABA, WNBA) for Trophy Case.

Inputs (from tools/fetch_hoops.py, in data-raw/hoops/):
  wd_bio.json            players with a Basketball Reference NBA or WNBA id (Wikidata): birthplace, sex, Wikipedia link
  infobox.jsonl.gz       each player's Wikipedia infobox: teams and years, college, draft, honors, medals, stats
  award_pages.jsonl.gz   award-list pages; the Hall of Fame lists give induction years
Also reads data/nfl.json + data/mlb.json (birthplace pins, room-id clashes) and index.html (curated rooms).
Output: data/hoops.json (same compact layout as data/nfl.json) and data/hoops-rooms/<0-255>.json

Rule (same as football): a player's own Wikipedia page is the source for that player's honors;
the Hall of Fame lists add induction years.
"""
import gzip, json, os, re, sys, unicodedata, urllib.parse
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data-raw", "hoops")
sys.path.insert(0, os.path.dirname(__file__))
from wiki_awards import fields  # top-level infobox field splitter

CUR = 2026  # latest season end year in the data
bio = json.load(open(os.path.join(RAW, "wd_bio.json"), encoding="utf-8"))
IB = {}
for line in gzip.open(os.path.join(RAW, "infobox.jsonl.gz"), "rt", encoding="utf-8"):
    x = json.loads(line)
    IB[x["title"]] = x
PAGES = {}
for line in gzip.open(os.path.join(RAW, "award_pages.jsonl.gz"), "rt", encoding="utf-8"):
    x = json.loads(line); PAGES[x["title"]] = x["text"]
print(f"{len(bio)} players on Wikidata, {len(IB)} Wikipedia articles, {len(PAGES)} award pages")

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", "", re.sub(r"[.'’\-]", " ", s)).split())
def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")
def canon_title(t):
    t = urllib.parse.unquote(t.split("#")[0]).replace("_", " ").strip()
    return t[:1].upper() + t[1:] if t else t

# ---------------------------------------------------------------- wikitext -> text with plain years
def years_tpl(m):
    name, y, rest = m.group(1).lower().replace(" ", ""), int(m.group(2)), (m.group(3) or "").lower()
    if name in ("nbay", "nbayear", "abay", "abayear", "nbagl", "ncaay") or name.endswith("seasony"):
        return str(y + 1) if "end" in rest else (str(y) if "start" in rest else f"{y}–{str(y + 1)[2:]}")
    return str(y)
YEAR_TPL = re.compile(r"\{\{\s*([A-Za-z ]*?(?:y|year|fy|sg|season))\s*\|\s*(\d{4})\s*((?:\|[^{}]*)?)\}\}", re.I)

def plain(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = YEAR_TPL.sub(years_tpl, s)
    for _ in range(3):
        s = re.sub(r"\{\{\s*(?:small|nowrap|sup|abbr|awrap|nobr)\s*\|([^{}|]*)(?:\|[^{}]*)?\}\}", r"\1", s, flags=re.I)
        s = re.sub(r"\{\{\s*(?:ndash|snd|spaced ndash|en dash)\s*\}\}", "–", s, flags=re.I)
        s = re.sub(r"\{\{\s*(?:bk[wm]?|flagicon|flag)\s*\|([^{}|]*)(?:\|[^{}]*)?\}\}", r"\1", s, flags=re.I)
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&ndash;", "–").replace("&mdash;", "—")
    return re.sub(r"[ \t]+", " ", s).strip()

def years_in(s):
    """'1961–1974, 2014–15, 2009' -> [1961..1974, 2015, 2009]"""
    out = []
    for m in re.finditer(r"(\d{4})\s*[–-]\s*(\d{4}|\d{2})\b|(\d{4})", s):
        if m.group(3): out.append(int(m.group(3))); continue
        a, b = int(m.group(1)), m.group(2)
        if len(b) == 2:            # a season like 2014–15 counts as its end year
            out.append(int(str(a)[:2] + b) if int(b) != 0 else a + 1); continue
        b = int(b)
        out += list(range(a, b + 1)) if 0 <= b - a <= 40 else [a, b]
    return sorted({y for y in out if 1890 < y <= CUR + 1})

# ---------------------------------------------------------------- honors
AWARD_RULES = [  # (regex on the cleaned label, canonical name or None to keep the label, kind, shelf)
    (r"^NBA champion$|^NBA championship$", "NBA Champion", "ring", "Championships"),
    (r"^WNBA champion$|^WNBA championship$", "WNBA Champion", "ring", "Championships"),
    (r"^ABA champion$", "ABA Champion", "ring", "Championships"),
    (r"^(?:BAA|NBL) champion$", None, "ring", "Championships"),
    (r"^NCAA (?:Division I )?(?:national )?champion$|^NCAA championship$", "NCAA Champion", "cup", "Championships"),
    (r"^NBA Finals MVP$|^NBA Finals Most Valuable Player", "NBA Finals MVP", "statue", "Individual"),
    (r"^WNBA Finals MVP$|^WNBA Finals Most Valuable Player", "WNBA Finals MVP", "statue", "Individual"),
    (r"^NBA Most Valuable Player|^NBA MVP$", "NBA MVP", "statue", "Individual"),
    (r"^WNBA Most Valuable Player|^WNBA MVP$", "WNBA MVP", "statue", "Individual"),
    (r"^ABA Most Valuable Player|^ABA MVP$", "ABA MVP", "statue", "Individual"),
    (r"^NBA All-Star$", "NBA All-Star", "star", "Selections"),
    (r"^WNBA All-Star$", "WNBA All-Star", "star", "Selections"),
    (r"^ABA All-Star$", "ABA All-Star", "star", "Selections"),
    (r"^All-NBA First Team$", "All-NBA First Team", "statue", "Individual"),
    (r"^All-WNBA First Team$", "All-WNBA First Team", "statue", "Individual"),
    (r"^All-ABA First Team$", "All-ABA First Team", "statue", "Individual"),
    (r"^NBA Rookie of the Year", "NBA Rookie of the Year", "statue", "Individual"),
    (r"^WNBA Rookie of the Year", "WNBA Rookie of the Year", "statue", "Individual"),
    (r"^NBA Defensive Player of the Year", "NBA Defensive Player of the Year", "statue", "Individual"),
    (r"^WNBA Defensive Player of the Year", "WNBA Defensive Player of the Year", "statue", "Individual"),
    (r"^NBA scoring champion$|^NBA annual scoring champion", "NBA scoring champion", "statue", "Individual"),
    (r"retired by|jersey retired|number retired|No\. \d+ retired|honored by", None, "plaque", "Honors & Service"),
    (r"Hall of Fame", None, "plaque", "Honors & Service"),
    (r"Medal of Freedom|Medal of Honor", None, "medal", "Honors & Service"),
    (r"scoring champion|scoring leader|rebounding leader|assists leader|steals leader|blocks leader|statistical leader", None, "statue", "Individual"),
    (r"champion|winner|^NIT", None, "cup", "Championships"),
    (r"All-|Team$|All-Star|All-American|Anniversary|Greatest", None, "star", "Selections"),
    (r".", None, "statue", "Individual"),
]
SKIP_LABEL = re.compile(r"Parade|McDonald's|Mr\. Basketball|Miss Basketball|Jordan Brand|Nike Hoop Summit|Next Up Game|Rising Stars|"
                        r"Slam Dunk|Three-Point Contest|Skills Challenge|High School|Gatorade|^\W*$", re.I)
ORD = {"35th": "NBA 35th Anniversary Team", "50th": "50 Greatest Players in NBA History", "75th": "NBA 75th Anniversary Team",
       "25th": "NBA 25th Anniversary Team"}

def kind_of(label):
    for pat, canon, k, c in AWARD_RULES:
        if re.search(pat, label, re.I): return (canon or label, k, c)

def parse_highlights(raw):
    """-> list of (name, kind, shelf, years, count)"""
    out, section = [], "player"
    for line in raw.split("\n"):
        st = line.strip()
        hdr = re.match(r"^'''?(.+?)'''?\s*:?\s*$", st)
        if hdr or re.match(r"^;\s*", st):
            h = (hdr.group(1) if hdr else st).lower()
            section = "player" if "player" in h else ("skip" if re.search(r"coach|executive|assistant|manager|broadcast|owner", h) else "other")
            continue
        if not st.startswith("*") or section == "skip": continue
        txt = plain(st.lstrip("*").strip())
        if not txt: continue
        m = re.match(r"^(\d+)\s*[×x]\s+(.*)$", txt)
        count = int(m.group(1)) if m else 1
        if m: txt = m.group(2)
        label = re.split(r"\s*\(", txt, maxsplit=1)[0].strip(" –-,:")
        paren = txt[len(label):]
        label = re.sub(r"\s+", " ", label).strip()
        if not label or SKIP_LABEL.search(label): continue
        ys = years_in(paren) or years_in(label)
        label = re.sub(r"\s*\d{4}(–\d{2,4})?\s*$", "", label).strip() or label
        if re.search(r"anniversary team", label, re.I):
            ords = re.findall(r"\b(\d{2})th\b", paren)
            if ords:
                lg = "WNBA" if "WNBA" in label else "NBA"
                for o in ords:
                    nm = ORD.get(f"{o}th", f"NBA {o}th Anniversary Team") if lg == "NBA" else f"WNBA {o}th Anniversary Team"
                    out.append((nm, "star", "Selections", [], 1))
                continue
        k = kind_of(label)
        if not k: continue
        out.append((k[0], k[1], k[2], ys, max(count, len(ys)) if ys else count))
    return out

def parse_medals(raw):
    out, comp = [], "Olympic Games"
    for m in re.finditer(r"\{\{\s*Medal(Competition|Gold|Silver|Bronze)\s*\|((?:[^{}]|\{\{[^{}]*\}\})*)\}\}", raw or "", re.I):
        t = m.group(1).lower()
        if t == "competition":
            comp = plain(m.group(2)).split("|")[0].strip(); continue
        ys = years_in(plain(m.group(2).split("|")[0]))
        c = "Olympic" if re.search(r"Olympic", comp) and not re.search(r"Youth", comp) else comp
        nm = f"{c} {t} medal" if c != "Olympic" else f"Olympic {t} medal"
        nm = nm[0].upper() + nm[1:]
        out.append((nm, "medal", "International", ys[:1], 1))
    return out

# ---------------------------------------------------------------- Hall of Fame years
TITLE2KEY = {}
for k, b in bio.items():
    wp = b.get("wp")
    if wp and "/wiki/" in wp: TITLE2KEY.setdefault(canon_title(wp.split("/wiki/", 1)[1]), k)
for x in IB.values():   # titles that redirected to a different page name
    if x.get("page") and x.get("id"): TITLE2KEY.setdefault(x["page"], x["id"])
NAME2KEYS = defaultdict(list)
for k, b in bio.items(): NAME2KEYS[norm(b.get("name", ""))].append(k)

HOF_YEAR = {}
t = PAGES.get("List of players in the Naismith Memorial Basketball Hall of Fame", "")
for row in re.split(r"\n\|-", t):
    m = re.match(r"\s*\|\s*(\d{4})\s*\|\|", row)
    if not m: continue
    for sm in re.finditer(r"\{\{\s*sortname\s*\|([^|}]*)\|([^|}]*)(?:\|([^|}]*))?", row):
        k = TITLE2KEY.get(canon_title(sm.group(3))) if sm.group(3) else None
        if not k:
            c = NAME2KEYS.get(norm(f"{sm.group(1)} {sm.group(2)}"), [])
            k = c[0] if len(c) == 1 else None
        if k: HOF_YEAR.setdefault(k, int(m.group(1)))
W_HOF = {}
t = PAGES.get("Women's Basketball Hall of Fame", "")
year = None
for tok in re.finditer(r"(?m)^=+[^=\n]*?(\d{4})[^=\n]*=+\s*$|^\|\s*(\d{4})\s*$|\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]", t):
    if tok.group(1) or tok.group(2): year = int(tok.group(1) or tok.group(2)); continue
    k = TITLE2KEY.get(canon_title(tok.group(3)))
    if k and year and 1998 <= year <= CUR: W_HOF.setdefault(k, year)
print(f"Hall of Fame years: Naismith {len(HOF_YEAR)} players, Women's {len(W_HOF)}")

# ---------------------------------------------------------------- birthplaces (same rules as football)
STATE_ABBR = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT","Delaware":"DE",
 "Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
 "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE",
 "Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH",
 "Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX",
 "Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"}
COUNTRY_FIX = {"People's Republic of China": "China", "Kingdom of the Netherlands": "Netherlands", "Federal Republic of Yugoslavia": "Yugoslavia",
               "Socialist Federal Republic of Yugoslavia": "Yugoslavia", "Kingdom of Yugoslavia": "Yugoslavia", "Union of Soviet Socialist Republics": "Soviet Union",
               "Czechoslovakia": "Czechoslovakia", "Republic of Ireland": "Ireland", "State of Palestine": "Palestine", "Georgia": "Georgia (country)"}
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
    if ctry == "United States" and st: return f"{town}, {st}", st, round(lat, 3), round(lon, 3)
    return None

# ---------------------------------------------------------------- colleges, teams, positions
COLLEGE_ALIAS = {"West Virginia": "West Virginia University", "Marshall": "Marshall University", "Pittsburgh": "University of Pittsburgh",
                 "Pitt": "University of Pittsburgh", "Penn State": "Penn State University", "USC": "University of Southern California",
                 "Southern California": "University of Southern California", "Kent State": "Kent State University", "Miami (FL)": "University of Miami",
                 "Miami (Florida)": "University of Miami"}
def colleges(raw):
    out = []
    for part in re.split(r"<br\s*/?>|\n|;|\}\}\s*\{\{", raw or ""):
        p = plain(part)
        p = re.sub(r"\s*\(.*?\)\s*", "", p).strip(" ,–-*")
        if not p or re.search(r"^none$|^n/?a$|high school|academy$|^—$", p, re.I): continue
        p = COLLEGE_ALIAS.get(p, p)
        if p not in out: out.append(p)
    return out[:3]

POS = [("point guard", "PG"), ("shooting guard", "SG"), ("small forward", "SF"), ("power forward", "PF"), ("center", "C"), ("centre", "C"),
       ("guard", "G"), ("forward", "F")]
def position(raw):
    p = plain(raw or "").lower()
    first = re.split(r"\s*/\s*|\s*,\s*|\s+and\s+|\n", p)[0] if p else ""
    for k, ab in POS:
        if k in first: return ab
    return ""

def team_rows(f):
    rows = []
    for i in range(1, 40):
        tm, yr = f.get(f"team{i}"), f.get(f"years{i}")
        if not tm: continue
        name = plain(tm)
        name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
        if not name or len(name) > 60: continue
        ys = years_in(plain(yr or ""))
        rows.append((name, ys))
    return rows

# ---------------------------------------------------------------- stories
def ordinal(n): return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
def the(team): return team if team.lower().startswith("the ") else "the " + team
def compress_years(ys):
    ys = sorted(set(ys))
    if not ys: return ""
    out, s, q = [], ys[0], ys[0]
    for y in ys[1:]:
        if y != q + 1: out.append(f"{s}" if s == q else f"{s}–{q}"); s = y
        q = y
    out.append(f"{s}" if s == q else f"{s}–{q}")
    return ", ".join(out)

def make_story(name, poss, teams, team_years, draft, college, aw, y0, league):
    cands = []
    def team_at(y):
        for t in teams:
            if y in team_years.get(t, []): return t
        for t in teams:
            ys = team_years.get(t, [])
            if ys and min(ys) <= y <= max(ys): return t
        return teams[0] if teams else ""
    if draft:
        dy, rnd, pick, dteam = draft
        how = f" with the {ordinal(pick)} pick" if pick else (f" in round {rnd}" if rnd else "")
        col = f" out of {college}" if college else ""
        cands.append((dy, f"Drafted by {the(dteam)}", f"The {dteam} took {name}{how} in the {dy} {league} draft{col}.", 3))
    elif teams and y0:
        cands.append((y0, f"Breaks in with {the(teams[0])}", f"{name} played {poss} first pro season with {the(teams[0])} in {y0}.", 1))
    for nm, head, txt in (("NBA Champion", "Wins the NBA title", "{name} and {team} won the NBA championship in {y}."),
                          ("WNBA Champion", "Wins the WNBA title", "{name} and {team} won the WNBA championship in {y}."),
                          ("ABA Champion", "Wins the ABA title", "{name} and {team} won the ABA championship in {y}."),
                          ("NCAA Champion", "National champion", "{name} won a national championship in college in {y}.")):
        if nm in aw and aw[nm][0]:
            ys = aw[nm][0]; n = aw[nm][1]
            more = f" It was the first of {n}." if n > 1 else ""
            cands.append((ys[0], head, txt.format(name=name, team=the(team_at(ys[0])), y=ys[0]) + more, 8 if nm != "NCAA Champion" else 4));
            if nm != "NCAA Champion": break
    for nm, head, txt, pr, many in (
            ("NBA MVP", "Named NBA MVP", "{name} was voted the NBA's Most Valuable Player for {y}.", 9, " It was the first of {n}."),
            ("WNBA MVP", "Named WNBA MVP", "{name} was voted the WNBA's Most Valuable Player for {y}.", 9, " It was the first of {n}."),
            ("ABA MVP", "Named ABA MVP", "{name} was voted the ABA's Most Valuable Player for {y}.", 9, " It was the first of {n}."),
            ("NBA Finals MVP", "Finals MVP", "{name} was named Most Valuable Player of the {y} NBA Finals.", 7, " It was the first of {n}."),
            ("WNBA Finals MVP", "Finals MVP", "{name} was named Most Valuable Player of the {y} WNBA Finals.", 7, " It was the first of {n}."),
            ("Olympic gold medal", "Olympic gold", "{name} won Olympic gold in {y}.", 7, " It was the first of {n}."),
            ("NBA Rookie of the Year", "Rookie of the Year", "{name} was named the NBA's Rookie of the Year for {y}.", 5, ""),
            ("WNBA Rookie of the Year", "Rookie of the Year", "{name} was named the WNBA's Rookie of the Year for {y}.", 5, ""),
            ("NBA Defensive Player of the Year", "Defensive Player of the Year", "{name} was named the NBA's Defensive Player of the Year for {y}.", 6, " It was the first of {n}."),
            ("NBA scoring champion", "Scoring title", "{name} led the NBA in scoring in {y}.", 5, " It was the first of {n}."),
            ("NBA All-Star", "First All-Star Game", "{name} was picked for {poss} first NBA All-Star Game in {y}.", 3, " It was the first of {n}."),
            ("WNBA All-Star", "First All-Star Game", "{name} was picked for {poss} first WNBA All-Star Game in {y}.", 3, " It was the first of {n}."),
            ("ABA All-Star", "First All-Star Game", "{name} was picked for {poss} first ABA All-Star Game in {y}.", 3, " It was the first of {n}.")):
        if nm in aw and aw[nm][0]:
            ys, n = aw[nm]
            t = txt.format(name=name, y=ys[0], poss=poss) + (many.format(name=name, n=n) if n > 1 else "")
            cands.append((ys[0], head, t, pr))
    if len(teams) > 1 and team_years.get(teams[1]):
        t1 = teams[1]; y = min(team_years[t1])
        cands.append((y, f"Joins {the(t1)}", f"{name} moved from {the(teams[0])} to {the(t1)} in {y}.", 2))
    for nm, head in (("Naismith Memorial Basketball Hall of Fame", "Enshrined in Springfield"), ("Women's Basketball Hall of Fame", "Enters the Women's Hall of Fame")):
        if nm in aw:
            ys = aw[nm][0]
            where = "the Naismith Memorial Basketball Hall of Fame" if nm.startswith("Naismith") else "the Women's Basketball Hall of Fame"
            cands.append((ys[0] if ys else 9999, head, f"{name} was inducted into {where}{(' in ' + str(ys[0])) if ys else ''}.", 10))
    top = sorted(cands, key=lambda c: -c[3])[:3]
    top.sort(key=lambda c: c[0])
    return [[str(c[0]) if c[0] != 9999 else "Springfield", c[1], c[2]] for c in top]

LINE_ORDER = ["Naismith Memorial Basketball Hall of Fame", "Women's Basketball Hall of Fame", "NBA Champion", "WNBA Champion", "ABA Champion",
              "NBA MVP", "WNBA MVP", "ABA MVP", "NBA Finals MVP", "WNBA Finals MVP", "Olympic gold medal", "NBA Defensive Player of the Year",
              "All-NBA First Team", "All-WNBA First Team", "NBA All-Star", "WNBA All-Star", "ABA All-Star", "NCAA Champion"]
POS_FULL = {"PG": "Point guard", "SG": "Shooting guard", "SF": "Small forward", "PF": "Power forward", "C": "Center", "G": "Guard", "F": "Forward"}
def make_line(pos, teams, era, awards):
    who = POS_FULL.get(pos, "Player")
    tl = " and ".join(teams) if len(teams) <= 2 else f"{teams[0]}, {teams[1]} and {len(teams) - 2} other team{'s' if len(teams) > 3 else ''}"
    aw = {w["n"]: w for w in awards}
    hl = []
    for n in LINE_ORDER:
        if n in aw:
            x = aw[n].get("x", 1)
            label = {"Naismith Memorial Basketball Hall of Fame": "Hall of Famer", "Women's Basketball Hall of Fame": "Women's Hall of Famer",
                     "NBA Champion": "NBA champion", "WNBA Champion": "WNBA champion", "ABA Champion": "ABA champion",
                     "Olympic gold medal": "Olympic gold medalist", "NCAA Champion": "NCAA champion"}.get(n, n)
            hl.append(f"{x}× {label}" if x > 1 else label)
        if len(hl) == 3: break
    return (f"{who} for the {tl}, {era}." if tl else f"{who}, {era}.") + (" " + ", ".join(hl) + "." if hl else "")

# ---------------------------------------------------------------- curated rooms, ids used elsewhere
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
i = html.index("const A = [") + len("const A = ")
CURATED, _ = json.JSONDecoder().raw_decode(html[i:])
cur_by_name = defaultdict(list)
for a in CURATED:
    if a["sport"] == "Basketball": cur_by_name[norm(a["name"])].append(a)
taken = {a["id"] for a in CURATED}
GEO_LABEL = {}
for f_ in ("nfl.json", "mlb.json"):
    p = os.path.join(ROOT, "data", f_)
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8")); taken |= {r[0] for r in d["rows"]}

# ---------------------------------------------------------------- assemble
pre, stats = [], Counter()
by_title = {}
for k, b in bio.items():
    wp = b.get("wp")
    if not wp or "/wiki/" not in wp: stats["no_article"] += 1; continue
    t = canon_title(wp.split("/wiki/", 1)[1])
    x = IB.get(t)
    if not x or not re.match(r"\{\{\s*Infobox\s+(basketball|nba|wnba)", x["infobox"] or "", re.I): stats["no_basketball_infobox"] += 1; continue
    if t in by_title: continue  # one room per article
    by_title[t] = k
    f = fields(x["infobox"])
    name = plain(f.get("name", "")).split("\n")[0].strip() or b.get("name") or t
    if len(name) > 40 or not re.search(r"[A-Za-z]", name): name = b.get("name") or t
    name = re.sub(r"\s*\(.*?\)$", "", name)
    sex = (b.get("sexL") or "male").lower()
    poss = "her" if sex in ("female", "cisgender woman", "trans woman") else ("their" if sex == "non-binary" else "his")
    rows = team_rows(f)
    teams, team_years = [], {}
    for nm, ys in rows:
        if nm not in team_years: teams.append(nm); team_years[nm] = []
        team_years[nm] += ys
    cs = years_in(plain(f.get("career_start", ""))); ce_raw = plain(f.get("career_end", ""))
    ce = years_in(ce_raw)
    all_years = sorted({y for ys in team_years.values() for y in ys})
    y0 = cs[0] if cs else (all_years[0] if all_years else None)
    y1 = ce[-1] if ce else (all_years[-1] if all_years else None)
    if not y0: stats["no_years"] += 1; continue
    present = any(re.search(r"present", f.get(f"years{i_}", "") or "", re.I) for i_ in range(1, 40))
    if present and not ce: y1 = CUR
    active = not ce and not f.get("death_date") and (present or (y1 or 0) >= CUR - 1)
    awards_raw = parse_highlights(f.get("highlights", "") or f.get("highlights_and_awards", ""))
    awards_raw += parse_medals(f.get("medal_templates", "") or f.get("medaltemplates", ""))
    cats = x.get("cats", [])
    for cat, nm in (("Naismith Memorial Basketball Hall of Fame inductees", "Naismith Memorial Basketball Hall of Fame"),
                    ("FIBA Hall of Fame inductees", "FIBA Hall of Fame"),
                    ("National Collegiate Basketball Hall of Fame inductees", "National Collegiate Basketball Hall of Fame")):
        if cat in cats: awards_raw.append((nm, "plaque", "Honors & Service", [], 1))
    if k in HOF_YEAR: awards_raw.append(("Naismith Memorial Basketball Hall of Fame", "plaque", "Honors & Service", [HOF_YEAR[k]], 1))
    if k in W_HOF: awards_raw.append(("Women's Basketball Hall of Fame", "plaque", "Honors & Service", [W_HOF[k]], 1))
    merged = {}
    for nm, kd, c, ys, n in awards_raw:
        if re.search(r"Hall of Fame", nm) and not re.search(r"Naismith|Women's Basketball|FIBA|Collegiate", nm):
            pass
        w = merged.get(nm)
        if not w: merged[nm] = [kd, c, set(ys), n]
        else: w[2] |= set(ys); w[3] = max(w[3], n)
    awards, aw_years = [], {}
    for nm, (kd, c, ys, n) in merged.items():
        n = max(n, len(ys), 1)
        w = {"n": nm, "k": kd, "c": c, "y": compress_years(ys)}
        if n > 1: w["x"] = n
        awards.append(w); aw_years[nm] = (sorted(ys), n)
    hof = any(w["n"] in ("Naismith Memorial Basketball Hall of Fame", "Women's Basketball Hall of Fame") for w in awards)
    col = colleges(f.get("college", ""))
    dy = years_in(plain(f.get("draft_year", "")))
    draft = None
    dteam = plain(f.get("draft_team", "")); dteam = re.sub(r"\s*\(.*?\)\s*$", "", dteam)
    if dy and dteam and not re.search(r"undrafted", plain(f.get("draft_year", "")) + dteam, re.I):
        pk = re.findall(r"\d+", plain(f.get("draft_pick", ""))); rd = re.findall(r"\d+", plain(f.get("draft_round", "")))
        draft = (dy[0], int(rd[0]) if rd else None, int(pk[0]) if pk else None, dteam)
    league = "WNBA" if b["league"] == "WNBA" else ("ABA" if f.get("draft_league", "").strip().upper() == "ABA" else "NBA")
    pos = position(f.get("career_position") or f.get("position", ""))
    num = re.findall(r"\d+", plain(f.get("career_number") or f.get("number", "")))
    stats_ = []
    for i_ in range(1, 7):
        lab, val = plain(f.get(f"stat{i_}label", "")), plain(f.get(f"stat{i_}value", ""))
        if lab and val: stats_.append([lab, val])
    pre.append(dict(k=k, name=name, poss=poss, teams=teams, team_years=team_years, y0=y0, y1=y1, active=active, hof=hof, awards=awards,
                    aw_years=aw_years, college=col, draft=draft, league=league, pos=pos, jersey=int(num[0]) if num else None,
                    stats=stats_, place=place(b), wp=f"https://en.wikipedia.org/wiki/{urllib.parse.quote(t.replace(' ', '_'))}"))

pre.sort(key=lambda r: (-sum(w.get("x", 1) for w in r["awards"]), r["y0"]))
out, ids, skipped_curated = [], set(), []
for r in pre:
    dup = None
    for a in cur_by_name.get(norm(r["name"]), []):
        m = re.findall(r"\d{4}", a["era"])
        if m and int(m[0]) - 3 <= (r["y1"] or CUR) and (a["era"].endswith("present") or int(m[-1]) + 3 >= r["y0"]): dup = a
    if dup: skipped_curated.append((r["name"], dup["id"])); continue
    grp = "active" if r["active"] else ("hof" if r["hof"] else "past")
    stats[grp] += 1
    pl = r["place"]
    if pl: stats["with_birthplace"] += 1
    base = slug(r["name"]) or "player"
    rid = base
    if rid in ids or rid in taken:
        rid = f"{base}-{r['y0']}"; n = 2
        while rid in ids or rid in taken: rid = f"{base}-{r['y0']}-{n}"; n += 1
    ids.add(rid)
    col = "; ".join(r["college"])
    wv = []
    if pl and pl[1] == "West Virginia": wv.append("born")
    if re.search(r"West Virginia Univ", col): wv.append("wvu")
    if re.search(r"Marshall University", col): wv.append("marshall")
    era = f"{r['y0']}–present" if grp == "active" else (f"{r['y0']}" if r["y0"] == r["y1"] else f"{r['y0']}–{r['y1']}")
    stories = make_story(r["name"], r["poss"], r["teams"], r["team_years"], r["draft"], r["college"][0] if r["college"] else "",
                         r["aw_years"], r["y0"], r["league"])
    out.append({"id": rid, "name": r["name"], "pos": r["pos"], "grp": grp, "born": pl[0] if pl else "", "region": pl[1] if pl else "",
                "lat": pl[2] if pl else None, "lon": pl[3] if pl else None, "college": col or "—", "teams": r["teams"], "era": era,
                "jersey": r["jersey"], "awards": r["awards"], "wv": wv, "src": r["wp"], "stories": stories, "stats": r["stats"][:6],
                "line": make_line(r["pos"], r["teams"], era.replace("–present", " to now"), r["awards"])})

# ---------------------------------------------------------------- compact encode
def table(vals):
    order = [v for v, _ in Counter(vals).most_common()]
    return order, {v: i for i, v in enumerate(order)}
T_team, T_team_i = table(t for r in out for t in r["teams"])
T_col, T_col_i = table(r["college"] for r in out)
T_born, T_born_i = table(r["born"] for r in out)
T_reg, T_reg_i = table(r["region"] for r in out)
T_aw, T_aw_i = table((w["n"], w["k"], w["c"]) for r in out for w in r["awards"])
GRP = {"active": 0, "hof": 1, "past": 2}
rows_out = [[r["id"], r["name"], r["pos"], GRP[r["grp"]], T_born_i[r["born"]], T_reg_i[r["region"]], r["lat"], r["lon"],
             T_col_i[r["college"]], [T_team_i[t] for t in r["teams"]], r["era"], r["jersey"],
             [[T_aw_i[(w["n"], w["k"], w["c"])], w["y"], w.get("x", 0)] for w in r["awards"]], r["wv"], r["src"]]
            for r in sorted(out, key=lambda r: (GRP[r["grp"]], r["name"]))]
doc = {"v": 2, "built": CUR, "sport": "Basketball", "rooms": "hoops-rooms", "teams": T_team, "colleges": T_col, "born": T_born,
       "regions": T_reg, "awards": [list(a) for a in T_aw], "rows": rows_out}
def shard(s_):
    h = 7
    for ch in s_: h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % 256
rooms_dir = os.path.join(ROOT, "data", "hoops-rooms"); os.makedirs(rooms_dir, exist_ok=True)
shards = defaultdict(dict)
for r in out: shards[shard(r["id"])][r["id"]] = [r["stories"], r["stats"]]
for k_ in range(256):
    json.dump(shards.get(k_, {}), open(os.path.join(rooms_dir, f"{k_}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
outp = os.path.join(ROOT, "data", "hoops.json")
json.dump(doc, open(outp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"Wrote {outp}: {len(rows_out)} players, {os.path.getsize(outp)/1e6:.1f} MB")
print("Groups:", dict(stats))
print(f"Players with at least one trophy: {sum(1 for r in out if r['awards'])} of {len(out)}")
print("Top awards:", Counter(w["n"] for r in out for w in r["awards"]).most_common(30))
print(f"Skipped {len(skipped_curated)} already curated:", skipped_curated)

# Site policy: no Russia-born athletes, no Russian awards (see tools/exclude_russia.py).
import subprocess as _sp, sys as _sys
_sp.run([_sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "exclude_russia.py")], check=True)
