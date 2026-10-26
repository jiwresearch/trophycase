"""Site policy: no athletes born in Russia, and no Russian awards.

Runs on the built data files (data/nfl.json, mlb.json, hoops.json and their
room folders), so it can be re-run after any rebuild. It is safe to run twice.

1. Athletes born in present-day Russia are removed (rooms included).
   Birthplace labels from older sources are checked by city: "Odesa, Russia"
   (Lahman's pre-1917 label) is Ukraine, so it stays and is relabelled
   "Odesa, Ukraine"; "Leningrad, Soviet Union" is Russia and goes.
2. Awards run by Russian or Soviet leagues, cups or the state are removed
   (Russian league/cup titles, VTB United League, USSR league, Gomelsky Cup,
   Honored Master of Sports of Russia, ...).
3. European club titles won with a Russian club are removed: EuroLeague,
   EuroLeague Women, EuroCup, EuroCup Women, FIBA EuroChallenge and the
   Women's Europe SuperCup, in the seasons a Russian club won them, for
   players who played for a Russian club. The finals MVP of those seasons
   goes too.

Run: python3 tools/exclude_russia.py
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 1. birthplaces --------------------------------------------------------
NOT_RUSSIA = {"Odesa"}                       # labelled "Russia" in old records, now Ukraine
RUSSIA_CITIES_OLD_LABEL = {"Leningrad"}       # labelled "Soviet Union" / "Russian Empire"
BIRTHPLACE_FIX = {                            # wrong birthplace in the source data
    "Ace Gutowsky": ("Komolty, OK", "Oklahoma"),  # Wikipedia: born in Komolty, Oklahoma
}
RELABEL = {                                   # old-country labels -> present-day country (keeps the map pin)
    "Odesa, Russia": ("Odesa, Ukraine", "Ukraine"),
    "Marijampolė, Russian Empire": ("Marijampolė, Lithuania", "Lithuania"),
}

def born_in_russia(born, region):
    city = born.split(",")[0].strip()
    if region == "Russia":
        return city not in NOT_RUSSIA
    if region in ("Soviet Union", "Russian Empire"):
        return city in RUSSIA_CITIES_OLD_LABEL
    return False

# ---- 2. Russian-run awards ---------------------------------------------------
RUSSIAN_AWARD = re.compile(r"\b(russia|russian|soviet|ussr|vtb)\b|gomelsky cup", re.I)

# ---- 3. European club titles won by Russian clubs (final year of season) ----
RU_WINS = {
    "el_men":   {1961, 1963, 1969, 1971, 2006, 2008, 2016, 2019},          # CSKA Moscow
    "el_women": {2003, 2005, 2007, 2008, 2009, 2010, 2013, 2016, 2017, 2018, 2019, 2021},
    "ec_men":   {2006, 2011, 2012, 2013, 2015},
    "ec_women": {2004, 2006, 2007, 2012, 2013, 2014, 2019},
    "sc_women": {2008, 2009, 2010, 2013, 2016, 2017, 2018, 2019},
    "echall":   {2004, 2005, 2013},
}
EL = r"euro ?league"
COMPS = [  # (regex on award name, competition key or None = decide by men/women)
    (re.compile(rf"^{EL} women (champion|winner|finals? mvp|final (four|eight) mvp)$", re.I), "el_women"),
    (re.compile(rf"^{EL} (champion|championship|winner|finals? mvp|final four mvp)$", re.I), "el"),
    (re.compile(r"^(euro ?cup|eurocup) women (champion|winner)$", re.I), "ec_women"),
    (re.compile(r"^(euro ?cup|uleb cup|uleb eurocup) (champion|winner|finals mvp)$", re.I), "ec"),
    (re.compile(r"^(fiba )?europe supercup( women)?( champion| winner| mvp)?", re.I), "sc_women"),
    (re.compile(r"^(fiba )?(eurochallenge|europe league)( champion| winner| final four mvp| finals mvp)$", re.I), "echall"),
]
WOMEN_TEAMS = re.compile(r"Mercury|Sparks|Lynx|Mystics|Liberty|Fever|\bSky\b|Storm|\bSun\b|Dream|Wings|Comets|Shock|Aces|"
                         r"Valkyries|Monarchs|Starzz|Miracle|Silver Stars|Sting|Rockers|Sol\b|Fire\b|Tempo")
RU_CLUB = re.compile(r"CSKA Moscow|Lokomotiv|UNICS|Unics|Zenit|UMMC|Ekaterinburg|Yekaterinburg|Dynamo Moscow|Khimki|Avtodor|"
                     r"Kursk|Orenburg|Nizhny|Spartak (Saint|St\.|Moscow|Primor|Leningrad|MR|M\.R|Vidno)|Enisey|Yenisey|"
                     r"Triumph|Sparta&K|Ural|Novosibirsk|Samara|Chevakata|Vologda|Arsenal Tula|Parma Perm|LenVo|"
                     r"Petersburg Lions|Runa Basket|BC Moscow|Dynamo (Saint|St\.|Moscow|Energia|Novosibirsk)|Krasny|Krasnye|"
                     r"Mineralnye|Rostov|Sibirtelecom|Euras|Nadežda|Nadezhda|Baltiyskaya")
NOT_RU_CLUB = re.compile(r"Sassari|Sofia|Zeniths|Subotica|Lebanon|Bucure|Tbilisi|Zagreb|Kyiv|Pleven|Levski|Bernau|Rural|CAUFA")

def years_of(s):
    out = []
    for a, b in re.findall(r"(\d{4})(?:\s*[–-]\s*(\d{4}))?", s or ""):
        a = int(a); b = int(b) if b else a
        out += range(a, b + 1)
    return out

def compress(ys):
    ys = sorted(set(ys)); parts = []; i = 0
    while i < len(ys):
        j = i
        while j + 1 < len(ys) and ys[j + 1] == ys[j] + 1: j += 1
        parts.append(str(ys[i]) if i == j else f"{ys[i]}–{ys[j]}"); i = j + 1
    return ", ".join(parts)

def shard(s_):
    h = 7
    for ch in s_: h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % 256

def remap(doc, key, col, rows, multi=False):
    """Drop unused entries from a lookup table and renumber rows (order kept)."""
    used = set()
    for r in rows:
        if multi: used.update(r[col])
        else: used.add(r[col])
    old = doc[key]; keep = [i for i in range(len(old)) if i in used]
    new_i = {o: n for n, o in enumerate(keep)}
    doc[key] = [old[i] for i in keep]
    for r in rows:
        r[col] = [new_i[i] for i in r[col]] if multi else new_i[r[col]]

def run(name, rooms_dir):
    path = os.path.join(ROOT, "data", name)
    doc = json.load(open(path, encoding="utf-8"))
    A, T, B, R = doc["awards"], doc["teams"], doc["born"], doc["regions"]
    ru_teams = {i for i, t in enumerate(T) if RU_CLUB.search(t) and not NOT_RU_CLUB.search(t)}
    removed_people, removed_awards, kept = [], 0, []
    for r in doc["rows"]:
        if r[1] in BIRTHPLACE_FIX and B[r[4]] != BIRTHPLACE_FIX[r[1]][0]:
            b, reg = BIRTHPLACE_FIX[r[1]]
            if b not in B: B.append(b)
            if reg not in R: R.append(reg)
            r[4], r[5], r[6], r[7] = B.index(b), R.index(reg), None, None
        if B[r[4]] in RELABEL:
            b, reg = RELABEL[B[r[4]]]
            if b not in B: B.append(b)
            if reg not in R: R.append(reg)
            r[4], r[5] = B.index(b), R.index(reg)
        if born_in_russia(B[r[4]], R[r[5]]) and B[r[4]] not in RELABEL:
            removed_people.append(r); continue
        women = any(WOMEN_TEAMS.search(T[i]) for i in r[9]) or any(re.search(r"WNBA|Women", A[a[0]][0]) for a in r[12])
        on_ru_club = bool(ru_teams & set(r[9]))
        new_aw = []
        for a in r[12]:
            nm = A[a[0]][0]
            if RUSSIAN_AWARD.search(nm) and not re.search(r"prussia", nm, re.I):
                removed_awards += 1; continue
            if on_ru_club:
                for rx, comp in COMPS:
                    if rx.search(nm):
                        if comp == "el": comp = "el_women" if women else "el_men"
                        if comp == "ec": comp = "ec_women" if women else "ec_men"
                        ys = years_of(a[1]) or years_of(nm)
                        if not ys: break
                        left = [y for y in ys if y not in RU_WINS[comp]]
                        if len(left) < len(ys):
                            removed_awards += len(ys) - len(left)
                            if not left: a = None
                            else: a = [a[0], compress(left), len(left) if len(left) > 1 else 0]
                        break
            if a is not None: new_aw.append(a)
        r[12] = new_aw
        kept.append(r)
    doc["rows"] = kept
    for key, col, multi in (("awards", 12, None), ("teams", 9, True), ("colleges", 8, False), ("born", 4, False), ("regions", 5, False)):
        if key == "awards":
            used = {a[0] for r in kept for a in r[12]}; old = doc["awards"]
            keep = [i for i in range(len(old)) if i in used]; ni = {o: n for n, o in enumerate(keep)}
            doc["awards"] = [old[i] for i in keep]
            for r in kept: r[12] = [[ni[a[0]], a[1], a[2]] for a in r[12]]
        else:
            remap(doc, key, col, kept, multi)
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    # rooms: drop removed people
    gone = {r[0] for r in removed_people}
    touched = 0
    for k in {shard(i) for i in gone}:
        p = os.path.join(ROOT, "data", rooms_dir, f"{k}.json")
        if not os.path.exists(p): continue
        s = json.load(open(p, encoding="utf-8"))
        n = len(s)
        for i in gone: s.pop(i, None)
        if len(s) != n:
            touched += 1
            json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{name}: removed {len(removed_people)} Russia-born athletes, {removed_awards} Russian award entries/years; "
          f"{len(kept)} athletes left")
    for r in removed_people: print(f"   - {r[1]} ({B[r[4]] if r[4] < len(B) else ''})")

if __name__ == "__main__":
    for name, rooms in (("nfl.json", "rooms"), ("mlb.json", "mlb-rooms"), ("hoops.json", "hoops-rooms")):
        if os.path.exists(os.path.join(ROOT, "data", name)): run(name, rooms)
