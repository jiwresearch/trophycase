#!/usr/bin/env python3
"""Build data/mlb.json + data/mlb-rooms/ for Trophy Case from the SABR Lahman Baseball Database.

Inputs (relative to repo root):
  data-raw/lahman/*.csv      SABR Lahman Baseball Database, comma-delimited version
                             (People, Appearances, Teams, AwardsPlayers, AllstarFull, HallOfFame,
                              Batting, CollegePlaying; Pitching and Schools used when present)
  data-raw/geo/us_cities.csv US place coordinates (github.com/kelvins/US-Cities-Database)
  geonamescache (pip)        world city coordinates
  data/nfl.json              read only: reuses its birthplace coordinates, avoids room-id clashes
  index.html                 read only: skips athletes already curated there
Output: data/mlb.json (same compact format as data/nfl.json) and data/mlb-rooms/<0-255>.json

The Lahman database is (c) SABR, licensed CC BY-SA 3.0. The site credits it.
"""
import csv, glob, json, os, re, unicodedata
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data-raw", "lahman")

def R(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        alt = [f for f in glob.glob(os.path.join(RAW, "*.csv")) if os.path.basename(f).lower() == name.lower()]
        if not alt: return None
        p = alt[0]
    with open(p, encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]

def I(v):
    try: return int(float(v))
    except (TypeError, ValueError): return 0

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", "", re.sub(r"[.'’\-]", " ", s)).split())

def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")

people = {p["playerID"]: p for p in R("People.csv")}
apps = R("Appearances.csv")
teams = R("Teams.csv")
awards_raw = R("AwardsPlayers.csv")
allstar = R("AllstarFull.csv")
hof_raw = R("HallOfFame.csv")
batting = R("Batting.csv")
pitching = R("Pitching.csv")            # optional
college_raw = R("CollegePlaying.csv")
schools = R("Schools.csv")              # optional
print(f"Lahman: {len(people)} people, {len(apps)} appearance rows, pitching={'yes' if pitching else 'no'}, schools={'yes' if schools else 'no'}")

ALLSTAR_LG = {"NOS", "SAS", "WES", "EAS", "NNN", "NNS"}  # Negro League all-star squads, not clubs
NEGRO_LG = {"NNL", "NN2", "NAL", "ECL", "ANL", "EWL", "NSL", "NAC", "IND", "EIC", "WIC", "INT"}
team_info = {}
for t in teams:
    if t["franchID"] == "ANA" and I(t["yearID"]) >= 2016: t["name"] = "Los Angeles Angels"  # Lahman still says "of Anaheim"
    team_info[(I(t["yearID"]), t["teamID"])] = t
CUR_SEASON = max(I(t["yearID"]) for t in teams)

# ---------------- players and their seasons ----------------
P = {}
for a in apps:
    if a["lgID"] in ALLSTAR_LG: continue
    pid, y, tid = a["playerID"], I(a["yearID"]), a["teamID"]
    t = team_info.get((y, tid))
    if not t: continue
    p = P.setdefault(pid, {"seasons": set(), "teams": [], "team_seasons": defaultdict(set), "pos": Counter(), "codes": set(), "lgs": set()})
    p["seasons"].add(y); p["codes"].add((y, tid)); p["lgs"].add(a["lgID"])
    nm = t["name"]
    if nm not in p["team_seasons"]: p["teams"].append(nm)
    p["team_seasons"][nm].add(y)
    for col, ab in (("G_p", "P"), ("G_c", "C"), ("G_1b", "1B"), ("G_2b", "2B"), ("G_3b", "3B"), ("G_ss", "SS"), ("G_dh", "DH")):
        p["pos"][ab] += I(a[col])
    lf, cf, rf, of = I(a["G_lf"]), I(a["G_cf"]), I(a["G_rf"]), I(a["G_of"])
    if lf + cf + rf: p["pos"]["LF"] += lf; p["pos"]["CF"] += cf; p["pos"]["RF"] += rf
    else: p["pos"]["OF"] += of
for p in P.values():
    p["teams"].sort(key=lambda n: min(p["team_seasons"][n]))
print(f"{len(P)} players with major league appearances, 1871-{CUR_SEASON}")

# ---------------- titles from team seasons ----------------
def title_name(t):
    if t["lgID"] in NEGRO_LG: return "Negro League World Series Champion"
    return "World Series Champion"
def pennant_name(t):
    if t["lgID"] in NEGRO_LG: return "Negro League Pennant"
    return {"AL": "American League Pennant", "NL": "National League Pennant"}.get(t["lgID"], "League Pennant")

# ---------------- awards ----------------
# awardID -> (display name, kind, shelf); None = not shown (weekly/monthly, fan-vote web awards)
AW = {
    "Most Valuable Player": ("MVP", "statue", "Individual"),
    "Cy Young Award": ("Cy Young Award", "statue", "Individual"),
    "Rookie of the Year": ("Rookie of the Year", "statue", "Individual"),
    "World Series MVP": ("World Series MVP", "statue", "Individual"),
    "ALCS MVP": ("ALCS MVP", "statue", "Individual"),
    "NLCS MVP": ("NLCS MVP", "statue", "Individual"),
    "All-Star Game MVP": ("All-Star Game MVP", "statue", "Individual"),
    "Babe Ruth Award": ("Babe Ruth Award", "statue", "Individual"),
    "Gold Glove": ("Gold Glove", "glove", "Individual"),
    "Platinum Glove": ("Platinum Glove", "glove", "Individual"),
    "Silver Slugger": ("Silver Slugger", "statue", "Individual"),
    "Triple Crown": ("Triple Crown", "statue", "Individual"),
    "Pitching Triple Crown": ("Pitching Triple Crown", "statue", "Individual"),
    "Comeback Player of the Year": ("Comeback Player of the Year", "statue", "Individual"),
    "Reliever of the Year Award": ("Reliever of the Year", "statue", "Individual"),
    "Reliever of the Year": ("Reliever of the Year", "statue", "Individual"),
    "Hank Aaron Award": ("Hank Aaron Award", "statue", "Individual"),
    "Outstanding DH Award": ("Outstanding DH Award", "statue", "Individual"),
    "All-MLB Team - First Team": ("All-MLB First Team", "star", "Selections"),
    "All-MLB Team - Second Team": ("All-MLB Second Team", "star", "Selections"),
    "TSN All-Star": ("Sporting News All-Star", "star", "Selections"),
    "Baseball Magazine All-Star": ("Baseball Magazine All-Star", "star", "Selections"),
    "TSN Player of the Year": ("Sporting News Player of the Year", "statue", "Individual"),
    "TSN Major League Player of the Year": ("Sporting News Player of the Year", "statue", "Individual"),
    "TSN Pitcher of the Year": ("Sporting News Pitcher of the Year", "statue", "Individual"),
    "TSN Rookie of the Year": ("Sporting News Rookie of the Year", "statue", "Individual"),
    "TSN Rookie Player of the Year": ("Sporting News Rookie of the Year", "statue", "Individual"),
    "TSN Rookie Pitcher of the Year": ("Sporting News Rookie of the Year", "statue", "Individual"),
    "TSN Fireman of the Year": ("Sporting News Reliever of the Year", "statue", "Individual"),
    "TSN Reliever of the Year": ("Sporting News Reliever of the Year", "statue", "Individual"),
    "TSN Comeback Player of the Year": ("Sporting News Comeback Player of the Year", "statue", "Individual"),
    "MLB Players Choice Player of the Year": ("Players Choice Player of the Year", "statue", "Individual"),
    "MLB Players Choice Outstanding Player": ("Players Choice Outstanding Player", "statue", "Individual"),
    "MLB Players Choice Outstanding Pitcher": ("Players Choice Outstanding Pitcher", "statue", "Individual"),
    "MLB Players Choice Outstanding Rookie": ("Players Choice Outstanding Rookie", "statue", "Individual"),
    "MLB Players Choice Comeback Player": ("Players Choice Comeback Player", "statue", "Individual"),
    "Roberto Clemente Award": ("Roberto Clemente Award", "plaque", "Honors & Service"),
    "Lou Gehrig Memorial Award": ("Lou Gehrig Memorial Award", "plaque", "Honors & Service"),
    "Hutch Award": ("Hutch Award", "plaque", "Honors & Service"),
    "Branch Rickey Award": ("Branch Rickey Award", "plaque", "Honors & Service"),
    "MLB Players Choice Man of the Year": ("Players Choice Man of the Year", "plaque", "Honors & Service"),
    "MLB Players Curt Flood Award": ("Curt Flood Award", "plaque", "Honors & Service"),
    "Bob Feller Act of Valor Award - HOF Player": ("Bob Feller Act of Valor Award", "medal", "Honors & Service"),
    "Bob Feller Act of Valor Award - MLB Player": ("Bob Feller Act of Valor Award", "medal", "Honors & Service"),
    "Bob Feller Act of Valor Award - Patriot Award": ("Bob Feller Act of Valor Award", "medal", "Honors & Service"),
}
AWARDS = defaultdict(lambda: defaultdict(set))   # pid -> (name,kind,shelf) -> years
skipped_aw = Counter()
for a in awards_raw:
    m = AW.get(a["awardID"])
    if not m: skipped_aw[a["awardID"]] += 1; continue
    AWARDS[a["playerID"]][m].add(I(a["yearID"]))
for a in allstar:
    nm = "Negro Leagues All-Star" if a["lgID"] in ALLSTAR_LG else "All-Star"
    AWARDS[a["playerID"]][(nm, "star", "Selections")].add(I(a["yearID"]))
HOF = {}
for h in hof_raw:
    if h["inducted"] == "Y":
        HOF.setdefault(h["playerID"], I(h.get("yearid") or h.get("yearID")))

# ---------------- career stats ----------------
BAT = defaultdict(Counter)
for b in batting:
    c = BAT[b["playerID"]]
    for k in ("G", "AB", "H", "HR", "RBI", "SB", "R", "BB", "2B", "3B"): c[k] += I(b[k])
PIT = defaultdict(Counter)
for r in pitching or []:
    c = PIT[r["playerID"]]
    for k in ("W", "L", "G", "GS", "SV", "IPouts", "ER", "SO", "SHO", "CG"): c[k] += I(r[k])

def fmt(n): return f"{n:,}"
def career_stats(pid, pos):
    b, pt = BAT.get(pid, Counter()), PIT.get(pid, Counter())
    bat = []
    if b["AB"] or b["G"]:
        bat = [["Games", fmt(b["G"])], ["Hits", fmt(b["H"])], ["Home runs", fmt(b["HR"])], ["RBI", fmt(b["RBI"])]]
        if b["AB"] >= 100: bat.insert(1, ["Batting average", f"{b['H'] / b['AB']:.3f}".lstrip("0")])
        if b["SB"] >= 50: bat.append(["Stolen bases", fmt(b["SB"])])
    pit = []
    if pt["G"]:
        ip = pt["IPouts"] / 3
        pit = [["Win–loss", f"{pt['W']}–{pt['L']}"]]
        if pt["IPouts"] >= 30: pit.append(["ERA", f"{9 * pt['ER'] / ip:.2f}"])
        pit += [["Strikeouts", fmt(pt["SO"])], ["Innings", fmt(round(ip))]]
        if pt["SV"] >= 20: pit.append(["Saves", fmt(pt["SV"])])
        if pt["SHO"] >= 10: pit.append(["Shutouts", fmt(pt["SHO"])])
    if pos == "P":
        if pit: return pit[:6]
        g = sum(P[pid]["pos"].values()) if pid in P else 0
        return [["Games pitched", fmt(P[pid]["pos"]["P"])]] if pid in P else []
    if pit and pt["G"] >= 50 and b["AB"] >= 1000:   # true two-way career
        return bat[:4] + pit[:2]
    return bat[:6]

# ---------------- colleges ----------------
SCHOOL = {s["schoolID"]: s["schoolName"] for s in (schools or [])}
SCHOOL_FALLBACK = {"wvirginia": "West Virginia University", "marshall": "Marshall University"}
COLLEGE_ALIAS = {"West Virginia University": "West Virginia University", "University of Pittsburgh": "University of Pittsburgh",
                 "Pennsylvania State University": "Penn State University", "University of Southern California": "University of Southern California"}
COLL = defaultdict(list)
for c in college_raw:
    sid = c["schoolID"]
    nm = SCHOOL.get(sid) or SCHOOL.get(re.sub(r"\d{4}$", "", sid)) or SCHOOL_FALLBACK.get(sid)
    if not nm: continue
    nm = COLLEGE_ALIAS.get(nm, nm)
    if nm not in COLL[c["playerID"]]: COLL[c["playerID"]].append(nm)

# ---------------- birthplaces ----------------
STATE_NAME = {"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware",
 "FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana",
 "ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska",
 "NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio",
 "OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas",
 "UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia"}
COUNTRY = {"USA": "United States", "D.R.": "Dominican Republic", "P.R.": "Puerto Rico", "CAN": "Canada", "México": "Mexico",
           "West Germany": "Germany", "U.S. Virgin Islands": "United States Virgin Islands", "England": "United Kingdom",
           "Scotland": "United Kingdom", "Wales": "United Kingdom", "Northern Ireland": "United Kingdom", "Curaçao": "Curaçao",
           "Russia": "Russia", "Czechoslovakia": "Czech Republic", "Viet Nam": "Vietnam", "South Korea": "South Korea"}
ISO = {"Dominican Republic": "DO", "Puerto Rico": "PR", "Canada": "CA", "Mexico": "MX", "Venezuela": "VE", "Cuba": "CU", "Japan": "JP",
       "Panama": "PA", "Ireland": "IE", "United Kingdom": "GB", "Australia": "AU", "Germany": "DE", "Colombia": "CO", "South Korea": "KR",
       "Taiwan": "TW", "Curaçao": "CW", "Nicaragua": "NI", "United States Virgin Islands": "VI", "Netherlands": "NL", "Italy": "IT",
       "Bahamas": "BS", "Russia": "RU", "France": "FR", "Aruba": "AW", "Sweden": "SE", "Jamaica": "JM", "Brazil": "BR", "Spain": "ES",
       "Poland": "PL", "Norway": "NO", "Czech Republic": "CZ", "China": "CN", "Portugal": "PT", "Philippines": "PH", "Honduras": "HN",
       "Austria": "AT", "Belgium": "BE", "Denmark": "DK", "Switzerland": "CH", "Greece": "GR", "Lithuania": "LT", "Latvia": "LV",
       "South Africa": "ZA", "Peru": "PE", "Guam": "GU", "Belize": "BZ", "Hungary": "HU", "Israel": "IL", "Finland": "FI",
       "Saudi Arabia": "SA", "Afghanistan": "AF", "American Samoa": "AS", "Singapore": "SG", "Indonesia": "ID", "Vietnam": "VN",
       "Hong Kong": "HK", "Slovakia": "SK", "Ukraine": "UA", "Croatia": "HR", "Bermuda": "BM", "Brazil ": "BR", "Argentina": "AR",
       "Guatemala": "GT", "El Salvador": "SV", "Costa Rica": "CR", "Venezuela ": "VE", "Barbados": "BB", "Trinidad and Tobago": "TT",
       "Belarus": "BY", "Lebanon": "LB", "New Zealand": "NZ", "Iran": "IR", "Turkey": "TR", "India": "IN", "Ecuador": "EC", "Chile": "CL"}

GEO_US, GEO_W, GEO_LABEL = {}, {}, {}
def key(s):
    s = norm(s)
    s = re.sub(r"^(st|ste) ", "saint ", s)
    s = re.sub(r"^ft ", "fort ", s); s = re.sub(r"^mt ", "mount ", s)
    s = re.sub(r" (city|township|village|borough)$", "", s)
    return s
nfl = json.load(open(os.path.join(ROOT, "data", "nfl.json"), encoding="utf-8"))
for r in nfl["rows"]:
    lab = nfl["born"][r[4]]
    if lab and r[6] is not None: GEO_LABEL.setdefault(lab, (r[6], r[7]))
for lab, (la, lo) in GEO_LABEL.items():
    m = re.match(r"(.+), ([A-Z]{2})$", lab)
    if m: GEO_US.setdefault((key(m.group(1)), m.group(2)), (la, lo))
gp = os.path.join(ROOT, "data-raw", "geo", "us_cities.csv")
if os.path.exists(gp):
    for c in csv.DictReader(open(gp, encoding="utf-8")):
        GEO_US.setdefault((key(c["CITY"]), c["STATE_CODE"]), (round(float(c["LATITUDE"]), 3), round(float(c["LONGITUDE"]), 3)))
try:
    import geonamescache
    gc = geonamescache.GeonamesCache()
    for c in sorted(gc.get_cities().values(), key=lambda c: -c.get("population", 0)):
        for nm in [c["name"]] + [a for a in c.get("alternatenames", []) if a and len(a) < 40][:12]:
            GEO_W.setdefault((key(nm), c["countrycode"]), (round(c["latitude"], 3), round(c["longitude"], 3)))
except ImportError:
    print("geonamescache not installed: foreign birthplaces get no map pin")

geo_stats = Counter()
def place(p):
    city, st, ctry = p["birthCity"], p["birthState"], p["birthCountry"]
    if not city and not st: return None
    if ctry in ("USA", ""):
        if st not in STATE_NAME: return None
        lab = f"{city}, {st}" if city else ""
        ll = GEO_LABEL.get(lab) or GEO_US.get((key(city), st))
        if not ll and city:
            ll = GEO_US.get((key(re.sub(r"\s*\(.*\)", "", city)), st))
        geo_stats["us_pin" if ll else "us_nopin"] += 1
        return (lab or STATE_NAME[st], STATE_NAME[st]) + (ll or (None, None))
    country = COUNTRY.get(ctry, ctry)
    shown = ctry if ctry in ("England", "Scotland", "Wales", "Northern Ireland") else country
    lab = f"{city}, {shown}" if city else shown
    ll = GEO_LABEL.get(lab)
    iso = ISO.get(country)
    if not ll and iso and city:
        ll = GEO_W.get((key(city), iso)) or (GEO_W.get((key(st), iso)) if st else None)
    geo_stats["world_pin" if ll else "world_nopin"] += 1
    return (lab, country) + (ll or (None, None))

# ---------------- stories ----------------
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
def the(team): return team if team.startswith("the ") else "the " + team
def team_in(p, y):
    best = [t for t, ys in p["team_seasons"].items() if y in ys]
    return best[0] if best else p["teams"][-1]
def franchise_of(p, nm):
    for (y, tid) in p["codes"]:
        t = team_info[(y, tid)]
        if t["name"] == nm: return t["franchID"]
    return nm
def expand(ys): return sorted(ys)
def compress_years(ys):
    ys = sorted(set(ys))
    if not ys: return ""
    out, s, q = [], ys[0], ys[0]
    for y in ys[1:]:
        if y != q + 1: out.append(f"{s}" if s == q else f"{s}–{q}"); s = y
        q = y
    out.append(f"{s}" if s == q else f"{s}–{q}")
    return ", ".join(out)

def make_story(p, pid, name, aw_years, y0):
    cands = []
    pe = people[pid]
    t0 = p["teams"][0]
    d = pe.get("debut", "")
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
    if m and int(m.group(1)) == y0:
        when = f"on {MONTHS[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}"
        cands.append((y0, f"Debuts with {the(t0)}", f"{name} played his first major league game for {the(t0)} {when}.", 1))
    else:
        cands.append((y0, f"Breaks in with {the(t0)}", f"{name} played his first major league season with {the(t0)} in {y0}.", 1))
    for nm, head, txt in (("World Series Champion", "Wins the World Series", "{name} and {team} won the {y} World Series."),
                          ("Negro League World Series Champion", "Wins the Negro League World Series", "{name} and {team} won the Negro League World Series in {y}.")):
        ys = aw_years.get(nm)
        if ys:
            y = ys[0]; more = f" It was the first of {len(ys)}." if len(ys) > 1 else ""
            cands.append((y, head, txt.format(name=name, team=the(team_in(p, y)), y=y) + more, 8)); break
    else:
        for nm in ("American League Pennant", "National League Pennant", "Negro League Pennant", "League Pennant"):
            ys = aw_years.get(nm)
            if ys:
                y = ys[0]; lg = "" if nm == "League Pennant" else nm.replace(" Pennant", " ")
                cands.append((y, "Wins the pennant", f"{name} and {the(team_in(p, y))} won the {y} {lg}pennant.".replace("  ", " "), 5)); break
    for nm, head, txt, pr, many in (
            ("MVP", "Named MVP", "{name} was voted his league's Most Valuable Player for {y}.", 9, " He won it {n} times in all."),
            ("Triple Crown", "Wins the Triple Crown", "{name} led his league in batting average, home runs and RBI in {y}.", 9, " He did it {n} times."),
            ("Cy Young Award", "Wins the Cy Young", "{name} won the Cy Young Award as the top pitcher of {y}.", 9, " He won it {n} times in all."),
            ("Pitching Triple Crown", "Pitching Triple Crown", "{name} led his league in wins, strikeouts and ERA in {y}.", 8, " He did it {n} times."),
            ("World Series MVP", "World Series MVP", "{name} was named Most Valuable Player of the {y} World Series.", 7, ""),
            ("Rookie of the Year", "Rookie of the Year", "{name} was named Rookie of the Year for {y}.", 5, ""),
            ("Gold Glove", "First Gold Glove", "{name} won his first Gold Glove for his defense in {y}.", 3, " He won {n} in all."),
            ("Silver Slugger", "First Silver Slugger", "{name} won his first Silver Slugger as the best hitter at his position in {y}.", 3, " He won {n} in all."),
            ("All-Star", "First All-Star team", "{name} was picked for his first All-Star team in {y}.", 3, " He made {n} All-Star teams in all."),
            ("Negro Leagues All-Star", "East-West All-Star", "{name} was picked for the Negro Leagues' all-star showcase in {y}.", 3, " He was picked {n} times in all.")):
        ys = aw_years.get(nm)
        if ys:
            t = txt.format(name=name, y=ys[0]) + (many.format(n=len(ys)) if len(ys) > 1 else "")
            cands.append((ys[0], head, t, pr))
    fr0 = franchise_of(p, t0)
    moved = [t for t in p["teams"][1:] if franchise_of(p, t) != fr0]
    if moved:
        t1 = moved[0]; y = min(p["team_seasons"][t1])
        k = len({yy for t in p["teams"] if franchise_of(p, t) == fr0 for yy in p["team_seasons"][t] if yy < y})
        if k:
            cands.append((y, f"Joins {the(t1)}", f"After {k} season{'s' if k != 1 else ''} with {the(t0)}, {name} moved on to {the(t1)} in {y}.", 2))
    if pid in HOF:
        y = HOF[pid]
        cands.append((y, "Enshrined in Cooperstown", f"{name} was inducted into the National Baseball Hall of Fame in {y}.", 10))
    top = sorted(cands, key=lambda c: -c[3])[:3]
    top.sort(key=lambda c: c[0])
    return [[str(c[0]), c[1], c[2]] for c in top]

POS_FULL = {"P": "Pitcher", "C": "Catcher", "1B": "First baseman", "2B": "Second baseman", "3B": "Third baseman", "SS": "Shortstop",
            "LF": "Left fielder", "CF": "Center fielder", "RF": "Right fielder", "OF": "Outfielder", "DH": "Designated hitter"}
LINE_ORDER = ["National Baseball Hall of Fame", "World Series Champion", "Negro League World Series Champion", "MVP", "Cy Young Award",
              "Triple Crown", "World Series MVP", "Rookie of the Year", "Gold Glove", "Silver Slugger", "All-Star", "Negro Leagues All-Star"]
def make_line(pos, teams_, era, awards):
    who = POS_FULL.get(pos, "Player")
    tl = " and ".join(teams_) if len(teams_) <= 2 else f"{teams_[0]}, {teams_[1]} and {len(teams_) - 2} other team{'s' if len(teams_) > 3 else ''}"
    aw = {w["n"]: w for w in awards}
    hl = []
    for n in LINE_ORDER:
        if n in aw:
            x = aw[n].get("x", 1)
            label = {"National Baseball Hall of Fame": "Hall of Famer", "World Series Champion": "World Series champion",
                     "Negro League World Series Champion": "Negro League World Series champion"}.get(n, n)
            hl.append(f"{x}× {label}" if x > 1 else label)
        if len(hl) == 3: break
    return f"{who} for the {tl}, {era}." + (" " + ", ".join(hl) + "." if hl else "")

# ---------------- curated rooms and NFL ids (avoid duplicates / clashes) ----------------
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
i = html.index("const A = [") + len("const A = ")
CUR, _ = json.JSONDecoder().raw_decode(html[i:])
cur_by_name = defaultdict(list)
for a in CUR:
    if a["sport"] == "Baseball": cur_by_name[norm(a["name"])].append(a)
taken = {a["id"] for a in CUR} | {r[0] for r in nfl["rows"]}

# ---------------- assemble ----------------
pre = []
for pid, p in P.items():
    pe = people.get(pid)
    if not pe: continue
    first = pe["nameFirst"] or ""
    name = f"{first} {pe['nameLast']}".strip() if first else (pe["nameLast"] or pid)
    seasons = sorted(p["seasons"]); y0, y1 = seasons[0], seasons[-1]
    aw_years = {}
    awards = []
    for (nm, k2, c), ys in AWARDS.get(pid, {}).items():
        aw_years[nm] = sorted(ys)
    # titles: everyone who appeared for the club that season
    ws, pen = defaultdict(list), defaultdict(list)
    for (y, tid) in sorted(p["codes"]):
        t = team_info[(y, tid)]
        if t["WSWin"] == "Y": ws[title_name(t)].append(y)
        elif t["LgWin"] == "Y": pen[pennant_name(t)].append(y)
    for nm, ys in ws.items():
        aw_years[nm] = ys; awards.append({"n": nm, "k": "ring", "c": "Championships", "y": compress_years(ys), **({"x": len(ys)} if len(ys) > 1 else {})})
    for nm, ys in pen.items():
        aw_years[nm] = ys; awards.append({"n": nm, "k": "cup", "c": "Championships", "y": compress_years(ys), **({"x": len(ys)} if len(ys) > 1 else {})})
    if pid in HOF:
        awards.append({"n": "National Baseball Hall of Fame", "k": "plaque", "c": "Honors & Service", "y": str(HOF[pid])})
    for (nm, k2, c), ys in AWARDS.get(pid, {}).items():
        w = {"n": nm, "k": k2, "c": c, "y": compress_years(ys)}
        if len(ys) > 1: w["x"] = len(ys)
        awards.append(w)
    pre.append((pid, p, name, y0, y1, aw_years, awards))

# most decorated first, so they get the plain room id when two players share a name
pre.sort(key=lambda t: (-sum(w.get("x", 1) for w in t[6]), t[3]))
out, ids, skipped_curated, stats = [], set(), [], Counter()
for pid, p, name, y0, y1, aw_years, awards in pre:
    dup = None
    for a in cur_by_name.get(norm(name), []):
        m = re.findall(r"\d{4}", a["era"])
        if m and int(m[0]) - 3 <= y1 and (a["era"].endswith("present") or int(m[-1]) + 3 >= y0): dup = a
    if dup: skipped_curated.append((name, dup["id"])); continue
    pe = people[pid]
    hof = pid in HOF
    grp = "active" if y1 == CUR_SEASON else ("hof" if hof else "past")
    stats[grp] += 1
    pl = place(pe)
    if pl and pl[2] is not None: stats["with_pin"] += 1
    if pl: stats["with_birthplace"] += 1
    pos = p["pos"].most_common(1)[0][0] if sum(p["pos"].values()) else ""
    col = "; ".join(COLL.get(pid, []))
    base = slug(name) or pid
    rid = base
    if rid in ids or rid in taken:
        rid = f"{base}-{y0}"; n = 2
        while rid in ids or rid in taken: rid = f"{base}-{y0}-{n}"; n += 1
    ids.add(rid)
    wv = []
    if pl and pl[1] == "West Virginia": wv.append("born")
    if re.search(r"West Virginia Univ", col): wv.append("wvu")
    if re.search(r"^Marshall|; Marshall", col): wv.append("marshall")
    era = f"{y0}–present" if grp == "active" else (f"{y0}" if y0 == y1 else f"{y0}–{y1}")
    rec = {"id": rid, "name": name, "pos": pos, "grp": grp,
           "born": pl[0] if pl else "", "region": pl[1] if pl else "", "lat": pl[2] if pl else None, "lon": pl[3] if pl else None,
           "college": col or "—", "teams": p["teams"], "era": era, "jersey": None, "awards": awards, "wv": wv,
           "src": pe.get("bbrefID", ""),
           "stories": make_story(p, pid, name, aw_years, y0), "stats": career_stats(pid, pos),
           "line": make_line(pos, p["teams"], era.replace("–present", " to now"), awards)}
    out.append(rec)

# ---------------- compact encode (same layout as data/nfl.json) ----------------
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
doc = {"v": 2, "built": CUR_SEASON, "sport": "Baseball", "rooms": "mlb-rooms",
       "srcfmt": "https://www.baseball-reference.com/players/{0}/{id}.shtml",
       "teams": T_team, "colleges": T_col, "born": T_born, "regions": T_reg, "awards": [list(a) for a in T_aw], "rows": rows_out}

def shard(s_):
    h = 7
    for ch in s_: h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % 256
rooms_dir = os.path.join(ROOT, "data", "mlb-rooms")
os.makedirs(rooms_dir, exist_ok=True)
shards = defaultdict(dict)
for r in out: shards[shard(r["id"])][r["id"]] = [r["stories"], r["stats"]]
for k_ in range(256):  # write all 256 (empty ones too) so updates copy cleanly over old files
    json.dump(shards.get(k_, {}), open(os.path.join(rooms_dir, f"{k_}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
outp = os.path.join(ROOT, "data", "mlb.json")
json.dump(doc, open(outp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"Wrote {outp}: {len(rows_out)} players, {os.path.getsize(outp)/1e6:.1f} MB; rooms "
      f"{sum(os.path.getsize(f) for f in glob.glob(os.path.join(rooms_dir, '*.json')))/1e6:.1f} MB")
print("Groups:", dict(stats), "| birthplace pins:", dict(geo_stats))
with_aw = sum(1 for r in out if r["awards"]); print(f"Players with at least one trophy: {with_aw} of {len(out)} ({100*with_aw/len(out):.0f}%)")
print("Award counts:", Counter(w["n"] for r in out for w in r["awards"]).most_common(40))
print("Not shown (weekly/monthly/fan awards):", sum(skipped_aw.values()), "rows")
print(f"Skipped {len(skipped_curated)} already curated:", skipped_curated)

# Site policy: no Russia-born athletes, no Russian awards (see tools/exclude_russia.py).
import subprocess as _sp, sys as _sys
_sp.run([_sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "exclude_russia.py")], check=True)
