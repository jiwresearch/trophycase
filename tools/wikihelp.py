"""Shared helpers for the Wikipedia/Wikidata builds (taken from build_hoops.py)."""

import re, unicodedata, urllib.parse

CUR = 2026

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", "", re.sub(r"[.'’\-]", " ", s)).split())
def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")
def canon_title(t):
    t = urllib.parse.unquote(t.split("#")[0]).replace("_", " ").strip()
    return t[:1].upper() + t[1:] if t else t


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

