#!/usr/bin/env python3
"""Build data/nfl.json for Trophy Case from nflverse rosters (+ Wikidata if present).

Inputs (relative to repo root):
  data-raw/sr/<year>.csv        nflverse season rosters 1920-current
  data-raw/players.csv          nflverse player table (colleges for 1970+)
  data-raw/wd_bio.json          optional, from tools/fetch_wikidata.py
  data-raw/wd_awards.json       optional
  index.html                    read only, to skip athletes already curated there
Output: data/nfl.json (compact; expanded by the page at load time)
"""
import csv, glob, json, os, re, sys, unicodedata
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data-raw")
CUR_SEASON = max(int(os.path.basename(f)[:4]) for f in glob.glob(os.path.join(RAW, "sr", "*.csv")))

# ---------------- team names by (code, season) ----------------
def team_name(c, y):
    if c in ("ARZ",): c = "ARI"
    if c == "BLT": c = "BAL"
    if c == "CLV": c = "CLE"
    if c == "HST": c = "HOU"
    if c == "SL": return "St. Louis Rams"
    fixed = {
        "ATL": "Atlanta Falcons", "CAR": "Carolina Panthers", "DEN": "Denver Broncos", "GB": "Green Bay Packers",
        "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "NE": "New England Patriots", "NO": "New Orleans Saints",
        "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers",
        "TB": "Tampa Bay Buccaneers", "SD": "San Diego Chargers", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders",
        "RAI": "Los Angeles Raiders", "PHO": "Phoenix Cardinals", "NYT": "New York Titans", "TEX": "Dallas Texans",
        "COW": "Dallas Cowboys", "CHB": "Chicago Bears", "CHC": "Chicago Cardinals", "CHS": "Chicago Staleys",
        "DEC": "Decatur Staleys", "CHT": "Chicago Tigers", "AKR": "Akron Pros" , "CAN": "Canton Bulldogs",
        "COL": "Columbus Panhandles", "DAY": "Dayton Triangles", "HAM": "Hammond Pros", "MUN": "Muncie Flyers",
        "RI": "Rock Island Independents", "ROC": "Rochester Jeffersons", "TON": "Tonawanda Kardex",
        "LOU": "Louisville Colonels", "ECG": "Evansville Crimson Giants", "OOR": "Oorang Indians", "RAC": "Racine Legion",
        "TOL": "Toledo Maroons", "MIL": "Milwaukee Badgers", "DUL": "Duluth Eskimos", "KEN": "Kenosha Maroons",
        "FYJ": "Frankford Yellow Jackets", "POT": "Pottsville Maroons", "PRO": "Providence Steam Roller",
        "HAR": "Hartford Blues", "NEW": "Newark Tornadoes", "ORG": "Orange Tornadoes", "SI": "Staten Island Stapletons",
        "POR": "Portsmouth Spartans", "P-P": "Phil-Pitt Steagles", "C-P": "Card-Pitt", "DON": "Los Angeles Dons",
        "CHH": "Chicago Hornets", "NYB": "New York Bulldogs", "RAM": "Los Angeles Rams", "TEN": "Tennessee Titans" if y >= 1999 else "Tennessee Oilers",
        "ARI": "Arizona Cardinals", "NYG": "New York Giants", "DAL": "Dallas Cowboys" if y >= 1960 else "Dallas Texans",
        "CHI": "Chicago Bears", "NY": "New York Giants" if y >= 1925 else "New York Brickley Giants",
    }
    if c in fixed:
        if c == "AKR" and y == 1926: return "Akron Indians"
        if c == "COL" and y >= 1923: return "Columbus Tigers"
        if c == "DUL" and y <= 1925: return "Duluth Kelleys"
        if c == "RAC" and y == 1926: return "Racine Tornadoes"
        return fixed[c]
    if c == "BUF":
        if y >= 1946: return "Buffalo Bills"
        if y == 1926: return "Buffalo Rangers"
        return "Buffalo Bisons" if y in (1924, 1925, 1927, 1929) else "Buffalo All-Americans"
    if c == "CLE":
        if y >= 1946: return "Cleveland Browns"
        if y >= 1937: return "Cleveland Rams"
        if y in (1924, 1925, 1927): return "Cleveland Bulldogs"
        if y in (1920, 1921) and y == 1920: return "Cleveland Tigers"
        return "Cleveland Indians"
    if c == "DET":
        if y >= 1934: return "Detroit Lions"
        if y == 1928: return "Detroit Wolverines"
        if y in (1925, 1926): return "Detroit Panthers"
        return "Detroit Heralds" if y == 1920 else "Detroit Tigers"
    if c == "KC": return "Kansas City Chiefs" if y >= 1963 else ("Kansas City Cowboys" if y >= 1925 else "Kansas City Blues")
    if c == "LA":
        if y == 1926: return "Los Angeles Buccaneers"
        if y >= 2016 and y <= 2016: return "Los Angeles Rams"
        return "Los Angeles Rams"
    if c == "STL":
        if y >= 1995: return "St. Louis Rams"
        if y >= 1960: return "St. Louis Cardinals"
        return "St. Louis Gunners" if y == 1934 else "St. Louis All-Stars"
    if c == "BAL": return "Baltimore Ravens" if y >= 1996 else "Baltimore Colts"
    if c == "HOU": return "Houston Texans" if y >= 2002 else "Houston Oilers"
    if c == "MIA": return "Miami Dolphins" if y >= 1966 else "Miami Seahawks"
    if c == "MIN": return "Minnesota Vikings" if y >= 1961 else ("Minneapolis Red Jackets" if y >= 1929 else "Minneapolis Marines")
    if c == "CIN": return "Cincinnati Bengals" if y >= 1968 else ("Cincinnati Reds" if y >= 1933 else "Cincinnati Celts")
    if c == "WAS":
        if y >= 2022: return "Washington Commanders"
        if y >= 2020: return "Washington Football Team"
        if y >= 1937: return "Washington Redskins"
        return "Washington Senators"
    if c == "BOS":
        if y >= 1960: return "Boston Patriots"
        if y >= 1944: return "Boston Yanks"
        if y >= 1933: return "Boston Redskins"
        return "Boston Braves" if y == 1932 else "Boston Bulldogs"
    if c == "NYY": return "New York Yanks" if y >= 1950 else "New York Yankees"
    if c == "CHR": return "Los Angeles Chargers" if y == 1960 else "Chicago Rockets"
    if c == "OAK": return "Oakland Raiders"
    if c == "PIT": return "Pittsburgh Steelers" if y >= 1940 else "Pittsburgh Pirates"
    if c == "BRK": return "Brooklyn Lions" if y == 1926 else ("Brooklyn Tigers" if y == 1944 else "Brooklyn Dodgers")
    return c

# ---------------- champions ----------------
NFL_CH = {1920:"AKR",1921:"CHS",1922:"CAN",1923:"CAN",1924:"CLE",1925:"CHC",1926:"FYJ",1927:"NYG",1928:"PRO",1929:"GB",1930:"GB",1931:"GB",
 1932:"CHB",1933:"CHB",1934:"NYG",1935:"DET",1936:"GB",1937:"WAS",1938:"NYG",1939:"GB",1940:"CHB",1941:"CHB",1942:"WAS",1943:"CHB",1944:"GB",
 1945:"CLE",1946:"CHB",1947:"CHC",1948:"PHI",1949:"PHI",1950:"CLE",1951:"LA",1952:"DET",1953:"DET",1954:"CLE",1955:"CLE",1956:"NYG",1957:"DET",
 1958:"BAL",1959:"BAL",1960:"PHI",1961:"GB",1962:"GB",1963:"CHI",1964:"CLE",1965:"GB",1966:"GB",1967:"GB",1968:"BAL",1969:"MIN"}
AFL_CH = {1960:"HOU",1961:"HOU",1962:"TEX",1963:"SD",1964:"BUF",1965:"BUF",1966:"KC",1967:"OAK",1968:"NYJ",1969:"KC"}
AAFC_CH = {1946:"CLE",1947:"CLE",1948:"CLE",1949:"CLE"}
SB = {1966:"GB",1967:"GB",1968:"NYJ",1969:"KC",1970:"BAL",1971:"DAL",1972:"MIA",1973:"MIA",1974:"PIT",1975:"PIT",1976:"OAK",1977:"DAL",
 1978:"PIT",1979:"PIT",1980:"OAK",1981:"SF",1982:"WAS",1983:"RAI",1984:"SF",1985:"CHI",1986:"NYG",1987:"WAS",1988:"SF",1989:"SF",1990:"NYG",
 1991:"WAS",1992:"DAL",1993:"DAL",1994:"SF",1995:"DAL",1996:"GB",1997:"DEN",1998:"DEN",1999:"STL",2000:"BAL",2001:"NE",2002:"TB",2003:"NE",
 2004:"NE",2005:"PIT",2006:"IND",2007:"NYG",2008:"PIT",2009:"NO",2010:"GB",2011:"NYG",2012:"BLT",2013:"SEA",2014:"NE",2015:"DEN",2016:"NE",
 2017:"PHI",2018:"NE",2019:"KC",2020:"TB",2021:"LA",2022:"KC",2023:"KC",2024:"PHI",2025:"SEA"}
CANON = {"ARZ":"ARI","BLT":"BAL","CLV":"CLE","HST":"HOU","SL":"STL","NY":"NYG"}
def canon(c): return CANON.get(c, c)

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)

def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

# ---------------- read rosters ----------------
rows = []
for f in sorted(glob.glob(os.path.join(RAW, "sr", "*.csv"))):
    y = int(os.path.basename(f)[:4])
    for r in csv.DictReader(open(f, encoding="utf-8")):
        r["season"] = y
        rows.append(r)
print(f"{len(rows)} roster rows, seasons 1920-{CUR_SEASON}")

players_csv = {r["gsis_id"]: r for r in csv.DictReader(open(os.path.join(RAW, "players.csv"), encoding="utf-8")) if r["gsis_id"]}

# key: gsis_id when present; else name+dob mapped onto a gsis key when one exists for the same person
namedob_to_gsis = {}
for r in rows:
    if r["gsis_id"] and r["birth_date"]:
        namedob_to_gsis.setdefault((norm(r["full_name"]), r["birth_date"]), r["gsis_id"])
def key_of(r):
    if r["gsis_id"]: return "g:" + r["gsis_id"]
    nd = (norm(r["full_name"]), r["birth_date"])
    if r["birth_date"] and nd in namedob_to_gsis: return "g:" + namedob_to_gsis[nd]
    if r["birth_date"]: return "n:" + nd[0] + ":" + nd[1]
    return nodob_key[(nd[0], r["season"], r["team"])]

# rows with no birth date: chain seasons of the same name (gaps of up to 3 years) into one person,
# attaching to a dated player of the same name whose career touches that run
dated_runs = defaultdict(list)
for r in rows:
    if r["birth_date"] or r["gsis_id"]:
        nd = (norm(r["full_name"]), r["birth_date"])
        k = "g:" + r["gsis_id"] if r["gsis_id"] else ("g:" + namedob_to_gsis[nd] if nd in namedob_to_gsis else "n:" + nd[0] + ":" + nd[1])
        dated_runs[nd[0]].append((r["season"], k))
nodob_key = {}
by_name = defaultdict(list)
for r in rows:
    if not r["birth_date"] and not r["gsis_id"]:
        by_name[norm(r["full_name"])].append((r["season"], r["team"]))
for nm, lst in by_name.items():
    lst.sort()
    run, runs = [lst[0]], []
    for it in lst[1:]:
        if it[0] - run[-1][0] <= 3: run.append(it)
        else: runs.append(run); run = [it]
    runs.append(run)
    for run in runs:
        lo, hi = run[0][0], run[-1][0]
        near = [k for y, k in dated_runs.get(nm, []) if lo - 3 <= y <= hi + 3]
        k = Counter(near).most_common(1)[0][0] if near else f"t:{nm}:{lo}"
        for y, t in run: nodob_key[(nm, y, t)] = k

P = {}
seen_team_season = set()
for r in rows:
    k = key_of(r)
    p = P.setdefault(k, {"names": Counter(), "dob": "", "seasons": set(), "teams": [], "team_seasons": defaultdict(set),
                          "pos": Counter(), "jersey": "", "jy": 0, "college": "", "pfr": "", "gsis": "", "status_cur": "", "codes": set()})
    p["names"][r["full_name"]] += 1
    p["dob"] = p["dob"] or r["birth_date"]
    p["seasons"].add(r["season"])
    tn = team_name(r["team"], r["season"])
    if tn not in p["teams"]: p["teams"].append(tn)
    p["team_seasons"][tn].add(r["season"])
    p["codes"].add((canon(r["team"]), r["season"]))
    if r["position"]: p["pos"][r["position"]] += 1
    if r["jersey_number"] not in ("", "0") and r["season"] >= p["jy"]: p["jersey"], p["jy"] = r["jersey_number"], r["season"]
    if r["college"]: p["college"] = r["college"]
    if r["pfr_id"]: p["pfr"] = r["pfr_id"]
    if r["gsis_id"]: p["gsis"] = r["gsis_id"]
    if r["season"] == CUR_SEASON and r["status"] in ("ACT", "RES", "DEV", "INA", "EXE", "PUP", "NWT", "SUS"): p["status_cur"] = r["status"]

for p in P.values():
    pc = players_csv.get(p["gsis"])
    if pc:
        p["pfr"] = p["pfr"] or pc["pfr_id"]
        p["college"] = pc["college_name"] or p["college"]
        p["display"] = pc["display_name"]
        if pc.get("draft_year"): p["draft"] = (pc["draft_year"], pc["draft_round"], pc["draft_pick"], pc["draft_team"])
print(f"{len(P)} distinct players")

# ---------------- Wikidata (optional) ----------------
bio = {}
wd_awards = defaultdict(list)
bio_path = os.path.join(RAW, "wd_bio.json")
if os.path.exists(bio_path):
    bio = {k.split("/")[-1]: dict(v, pfr=k.split("/")[-1]) for k, v in json.load(open(bio_path)).items()}
    for a in json.load(open(os.path.join(RAW, "wd_awards.json"))):
        a["pfr"] = a["pfr"].split("/")[-1]
        wd_awards[a["pfr"]].append(a)
    print(f"Wikidata: {len(bio)} players, {sum(len(v) for v in wd_awards.values())} award rows")
hof_path = os.path.join(RAW, "wd_hof.json")
WD_HOF = json.load(open(hof_path)) if os.path.exists(hof_path) else {}
if WD_HOF: print(f"Hall of Fame list: {len(WD_HOF)}")
by_namedob = {}
for b in bio.values():
    if b.get("name") and b.get("dob"):
        by_namedob.setdefault((norm(b["name"]), b["dob"][:10]), b)

STATE_ABBR = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT","Delaware":"DE",
 "Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
 "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE",
 "Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH",
 "Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX",
 "Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"}

def place(b):
    """-> (born label, region, lat, lon) or None"""
    if not b or not b.get("pobL") or not b.get("coord"): return None
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"])
    if not m: return None
    lon, lat = float(m.group(1)), float(m.group(2))
    town = re.sub(r",.*$", "", b["pobL"]).strip()
    st, ctry = b.get("stateL"), b.get("countryL")
    if st in STATE_ABBR:
        return f"{town}, {STATE_ABBR[st]}", st, round(lat, 3), round(lon, 3)
    if b["pobL"] in ("Washington, D.C.",) or town == "Washington, D.C." or (ctry == "United States" and "Washington" in town and "D.C" in b["pobL"]):
        return "Washington, DC", "District of Columbia", round(lat, 3), round(lon, 3)
    if ctry and ctry != "United States":
        return f"{town}, {ctry}", ctry, round(lat, 3), round(lon, 3)
    if ctry == "United States" and st:
        return f"{town}, {st}", st, round(lat, 3), round(lon, 3)
    return None

# award label -> (display name, kind, shelf)
AWARD_MAP = [
    (r"^Pro Football Hall of Fame$", ("Pro Football Hall of Fame", "plaque", "Honors & Service")),
    (r"^College Football Hall of Fame$", ("College Football Hall of Fame", "plaque", "Honors & Service")),
    (r"^Canadian Football Hall of Fame$", ("Canadian Football Hall of Fame", "plaque", "Honors & Service")),
    (r"Sports Hall of Fame$|Athletic Hall of Fame$", None),  # keeps its own name, see below
    (r"^Super Bowl Most Valuable Player", ("Super Bowl MVP", "statue", "Individual")),
    (r"^National Football League Most Valuable Player|^AP NFL Most Valuable|^NFL Most Valuable", ("NFL MVP", "statue", "Individual")),
    (r"NFL Offensive Player of the Year", ("NFL Offensive Player of the Year", "statue", "Individual")),
    (r"NFL Defensive Player of the Year", ("NFL Defensive Player of the Year", "statue", "Individual")),
    (r"Offensive Rookie of the Year|^NFL Rookie of the Year", ("NFL Rookie of the Year", "statue", "Individual")),
    (r"Defensive Rookie of the Year", ("NFL Defensive Rookie of the Year", "statue", "Individual")),
    (r"Comeback Player of the Year", ("NFL Comeback Player of the Year", "statue", "Individual")),
    (r"^Walter Payton Man of the Year", ("Walter Payton Man of the Year", "plaque", "Honors & Service")),
    (r"^All-Pro$", ("First-team All-Pro", "statue", "Individual")),
    (r"^PFWA All-Rookie Team$", ("PFWA All-Rookie Team", "star", "Selections")),
    (r"^College Football All-America Team$", ("All-American", "statue", "Individual")),
    (r"^Purple Heart$|^Bronze Star Medal$|^Silver Star$|^Navy Cross$|^Distinguished Service Cross|^Medal of Honor$", "SELF_MEDAL"),
    (r"^Presidential Medal of Freedom$", ("Presidential Medal of Freedom", "medal", "Honors & Service")),
    (r"^(Heisman Trophy|Maxwell Award|Outland Trophy|Davey O'Brien Award|Doak Walker Award|Fred Biletnikoff Award|Chuck Bednarik Award|Jim Thorpe Award|Lombardi Award|Walter Camp Award|Butkus Award|Bert Bell Award|Bronko Nagurski Trophy|Johnny Unitas Golden Arm Award|Ray Guy Award|Lou Groza Award|Paul Hornung Award|Manning Award|Walter Payton Award|John Mackey Award|Dick Butkus Award|Chicago Tribune Silver Football|Jon Cornish Trophy|Lott IMPACT Trophy|Ted Hendricks Award|Rimington Trophy|Vince Lombardi Award)$", "SELF_STATUE"),
    (r"^Associated Press College Football Player of the Year$|^The Sporting News College Football Player of the Year$", "SELF_STATUE"),
]
def map_award(label):
    for pat, out in AWARD_MAP:
        if re.search(pat, label, re.I):
            if out is None: return (label, "plaque", "Honors & Service")
            if out == "SELF_MEDAL": return (label, "medal", "Honors & Service")
            if out == "SELF_STATUE": return (label, "statue", "Individual")
            return out
    return None

def compress_years(ys):
    ys = sorted(set(ys))
    if not ys: return ""
    out, s, p = [], ys[0], ys[0]
    for y in ys[1:]:
        if y != p + 1:
            out.append(f"{s}" if s == p else f"{s}–{p}"); s = y
        p = y
    out.append(f"{s}" if s == p else f"{s}–{p}")
    return ", ".join(out)

# ---------------- curated athletes (skip duplicates) ----------------
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
i = html.index("const A = [") + len("const A = ")
CUR, _ = json.JSONDecoder().raw_decode(html[i:])
cur_by_name = defaultdict(list)
for a in CUR:
    if a["sport"] == "Football": cur_by_name[norm(a["name"])].append(a)

# match the curated rooms' college names so hubs merge
COLLEGE_ALIAS = {"West Virginia": "West Virginia University", "Marshall": "Marshall University", "Penn State": "Penn State University",
                 "Pittsburgh": "University of Pittsburgh", "USC": "University of Southern California", "Southern California": "University of Southern California",
                 "Kent State": "Kent State University", "Miami (FL)": "University of Miami", "Mississippi Valley State University": "Mississippi Valley State"}

# ---------------- assemble ----------------
out = []
ids = set()
skipped_curated = []
stats = Counter()
for k, p in P.items():
    name = p.get("display") or p["names"].most_common(1)[0][0]
    seasons = sorted(p["seasons"])
    y0, y1 = seasons[0], seasons[-1]
    # curated duplicate?
    dup = None
    for a in cur_by_name.get(norm(name), []):
        m = re.findall(r"\d{4}", a["era"])
        nick = lambda t: t.split()[-1].lower()
        cur_nicks = {nick(t) for t in a["teams"] if "(" not in t}
        if m and int(m[0]) - 3 <= y1 and (a["era"].endswith("present") or int(m[-1]) + 3 >= y0) and (cur_nicks & {nick(t) for t in p["teams"]} or not a["teams"]):
            dup = a
    if dup:
        skipped_curated.append((name, dup["id"])); continue
    b = bio.get(p["pfr"]) if p["pfr"] else None
    if not b and p["dob"]: b = by_namedob.get((norm(name), p["dob"]))
    pl = place(b)
    awards = []
    # championships from rosters
    sb = [y for y in seasons if y in SB and (canon(SB[y]), y) in p["codes"]]
    nfl = [y for y in seasons if y in NFL_CH and (canon(NFL_CH[y]), y) in p["codes"]]
    afl = [y for y in seasons if y in AFL_CH and (AFL_CH[y], y) in p["codes"]]
    aafc = [y for y in seasons if y in AAFC_CH and (AAFC_CH[y], y) in p["codes"]]
    for nm, k2, ys in (("Super Bowl Champion", "ring", sb), ("NFL Championship", "cup", nfl), ("AFL Championship", "cup", afl), ("AAFC Championship", "cup", aafc)):
        if ys:
            w = {"n": nm, "k": k2, "c": "Championships", "y": compress_years(ys)}
            if len(ys) > 1: w["x"] = len(ys)
            awards.append(w)
    hof = False
    if b:
        got = defaultdict(list)
        for a in wd_awards.get(b["pfr"], []):
            m = map_award(a["award"])
            if m:
                t = int(a["t"]) if a["t"].isdigit() else None
                # Wikidata dates are sometimes wrong: drop pro-award years outside the career, college-award years after it began
                if t and m[1] == "statue" and m[0].startswith(("NFL", "Super Bowl", "First-team All-Pro")) and not (y0 <= t <= y1 + 1): t = "bad"
                elif t and m[2] == "Individual" and not m[0].startswith(("NFL", "Super Bowl", "First-team")) and t > y0: t = "bad"
                got[m].append(t)
        for (nm, k2, c), ys in got.items():
            yy = sorted({y for y in ys if isinstance(y, int)})
            if not yy and all(y == "bad" for y in ys): yy = []
            w = {"n": nm, "k": k2, "c": c, "y": compress_years(yy) if yy else ""}
            n = max(len(yy), 1)
            if n > 1: w["x"] = n
            awards.append(w)
            if nm == "Pro Football Hall of Fame": hof = True
    if not hof and p["pfr"] and p["pfr"] in WD_HOF:
        t = WD_HOF[p["pfr"]].get("t", "")
        awards.append({"n": "Pro Football Hall of Fame", "k": "plaque", "c": "Honors & Service", "y": t})
        hof = True
    grp = "active" if p["status_cur"] else ("hof" if hof else "past")
    stats[grp] += 1
    if pl: stats["with_birthplace"] += 1
    col = p["college"] or ""
    col = "; ".join(COLLEGE_ALIAS.get(c.strip(), c.strip()) for c in col.split(";")) if col else ""
    pos = p["pos"].most_common(1)[0][0] if p["pos"] else ""
    base = slug(name) or "player"
    pid = base
    if pid in ids or pid in {a["id"] for a in CUR}:
        pid = f"{base}-{y0}"
        n = 2
        while pid in ids: pid = f"{base}-{y0}-{n}"; n += 1
    ids.add(pid)
    wv = []
    if pl and pl[1] == "West Virginia": wv.append("born")
    if re.search(r"West Virginia Univ", col): wv.append("wvu")
    if re.search(r"^Marshall", col): wv.append("marshall")
    rec = {
        "id": pid, "name": name, "pos": pos, "grp": grp,
        "born": pl[0] if pl else "", "region": pl[1] if pl else "", "lat": pl[2] if pl else None, "lon": pl[3] if pl else None,
        "college": col or "—", "teams": p["teams"], "era": f"{y0}–present" if grp == "active" else (f"{y0}" if y0 == y1 else f"{y0}–{y1}"),
        "jersey": int(p["jersey"]) if p["jersey"].isdigit() else None, "awards": awards, "wv": wv,
        "src": b.get("wp") if b and b.get("wp") else (f"https://www.pro-football-reference.com/players/{p['pfr'][0]}/{p['pfr']}.htm" if p["pfr"] else ""),
    }
    out.append(rec)

# ---------------- compact encode ----------------
def table(vals):
    order = [v for v, _ in Counter(vals).most_common()]
    return order, {v: i for i, v in enumerate(order)}
T_team, T_team_i = table(t for r in out for t in r["teams"])
T_col, T_col_i = table(r["college"] for r in out)
T_born, T_born_i = table(r["born"] for r in out)
T_reg, T_reg_i = table(r["region"] for r in out)
T_aw, T_aw_i = table((w["n"], w["k"], w["c"]) for r in out for w in r["awards"])
GRP = {"active": 0, "hof": 1, "past": 2}
rows_out = []
for r in sorted(out, key=lambda r: (GRP[r["grp"]], r["name"])):
    rows_out.append([r["id"], r["name"], r["pos"], GRP[r["grp"]], T_born_i[r["born"]], T_reg_i[r["region"]], r["lat"], r["lon"],
                     T_col_i[r["college"]], [T_team_i[t] for t in r["teams"]], r["era"], r["jersey"],
                     [[T_aw_i[(w["n"], w["k"], w["c"])], w["y"], w.get("x", 0)] for w in r["awards"]], r["wv"], r["src"]])
doc = {"v": 1, "built": CUR_SEASON, "teams": T_team, "colleges": T_col, "born": T_born, "regions": T_reg,
       "awards": [list(a) for a in T_aw], "rows": rows_out}
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
outp = os.path.join(ROOT, "data", "nfl.json")
json.dump(doc, open(outp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"Wrote {outp}: {len(rows_out)} players, {os.path.getsize(outp)/1e6:.1f} MB")
print("Groups:", dict(stats))
print(f"Skipped {len(skipped_curated)} already curated:", skipped_curated[:40])
