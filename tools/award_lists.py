"""Award-first data: read Wikipedia award-list pages and return, for each award, its winners (by PFR id) and years.

award_winners(pages, title_to_pfr, name_to_pfrs, careers) -> {award_name: {pfr: set(years)}}, report
"""
import re, unicodedata
from collections import defaultdict

ROMAN = {}
def _r(n):
    s = ""
    for v, c in [(50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]:
        while n >= v: s += c; n -= v
    return s
for _n in range(1, 70): ROMAN[_r(_n)] = 1965 + _n

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)

def canon_title(t):
    t = t.split("#")[0].replace("_", " ").strip()
    return t[:1].upper() + t[1:] if t else t

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
SORTNAME = re.compile(r"\{\{\s*sortname\s*\|([^|}]*)\|([^|}]*)(?:\|([^|}]*))?[^}]*\}\}", re.I)
SEASON_LINK = re.compile(r"\[\[(\d{4}) (?:NFL|AFL|AAFC|All-America Football Conference|American Football League|college football|NCAA[^|\]]*) season")

class Resolver:
    def __init__(self, title_to_pfr, name_to_pfrs, careers):
        self.t = title_to_pfr; self.n = name_to_pfrs; self.c = careers
    def people(self, text, year=None):
        """pfr ids of players linked or sortname'd in text"""
        out = []
        for m in LINK.finditer(text):
            k = self.t.get(canon_title(m.group(1)))
            if k: out.append(k)
        for m in SORTNAME.finditer(text):
            tgt = (m.group(3) or "").strip()
            k = self.t.get(canon_title(tgt)) if tgt and not tgt.lower().startswith(("nolink", "dab")) else None
            if not k:
                k = self.by_name(f"{m.group(1).strip()} {m.group(2).strip()}", year)
            if k: out.append(k)
        seen = set(); res = []
        for k in out:
            if k not in seen: seen.add(k); res.append(k)
        return res
    def by_name(self, name, year=None):
        c = self.n.get(norm(name), [])
        if len(c) == 1: return c[0]
        if year and c:
            near = [k for k in c if k in self.c and self.c[k][0] - 6 <= year <= self.c[k][1] + 40]
            if len(near) == 1: return near[0]
        return None

def rows_of(text):
    return re.split(r"\n\|-[^\n]*", text)

def row_year(r):
    m = SEASON_LINK.search(r)
    if m: return int(m.group(1))
    m = re.search(r"\b(18[89]\d|19\d\d|20[0-2]\d)\b", re.sub(r"id=\d+|<ref.*?(</ref>|/>)", "", r, flags=re.S))
    return int(m.group(1)) if m else None

def strip_refs(t):
    t = re.sub(r"<ref[^>]*/>", "", t)
    return re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)

# ------------------------------------------------------------------ handlers
def single_list(text, R, award, out, season_from_sb=False, min_year=1900):
    text = strip_refs(text)
    for r in rows_of(text):
        if "[[" not in r and "sortname" not in r.lower(): continue
        y = row_year(r)
        if season_from_sb:
            m = re.search(r"\[\[Super Bowl ([LXVI]+)", r)
            if m and m.group(1) in ROMAN: y = ROMAN[m.group(1)]
        if not y or y < min_year: continue
        # winners are normally in the first cells; ignore links that sit in "runner-up"/notes columns
        cells = re.split(r"\|\||\n[|!]", r)
        ppl = []
        for c in cells[:4]:
            ppl += R.people(c, y)
            if ppl: break
        for k in ppl: out[award][k].add(y)

def team_page(text, R, year, first_name, second_name, out):
    """All-Pro / All-AFL season pages: First team / Second team columns, or selector codes (-1/-2) in older pages."""
    text = strip_refs(text)
    has_cols = re.search(r"!\s*First team", text, re.I) is not None
    for r in rows_of(text):
        if has_cols:
            cells = [c for c in re.split(r"\n\|", r) if c.strip()]
            if len(cells) >= 2:
                for k in R.people(cells[1], year): out[first_name][k].add(year)
            if len(cells) >= 3 and second_name:
                for k in R.people(cells[2], year): out[second_name][k].add(year)
        else:
            for line in re.split(r"\n", r):
                ppl = R.people(line, year)
                if not ppl: continue
                first = "'''" in line or re.search(r"-1\b", line) or (not re.search(r"-[23]\b", line) and re.search(r"\b[A-Z]{2,5}\b", line))
                for k in ppl:
                    out[first_name if first else (second_name or first_name)][k].add(year)

def pro_bowl(text, R, season, out):
    text = strip_refs(text)
    for line in text.split("\n"):
        if re.search(r"coach|referee|official|anthem|owner|commissioner|stadium|halftime|broadcast", line, re.I): continue
        for k in R.people(line, season): out["Pro Bowl"][k].add(season)

def all_america(text, R, year, out):
    text = strip_refs(text)
    for line in text.split("\n"):
        ppl = R.people(line, year)
        if not ppl: continue
        if line.lstrip().startswith("*"):
            if "'''" in line: name = "Consensus All-American"
            elif re.search(r"\(([^)]*)\)", line) and re.search(r"(AP|UPI|AFCA|FWAA|WC|NEA|SN|CP|INS|Time|FN|TSN|Camp|INS)(?:-1)?(?![-\d])", line): name = "All-American"
            else: continue
        elif "||" in line and re.search(r"\d+/\d+", line):
            name = "Consensus All-American"
        else:
            continue
        for k in ppl: out[name][k].add(year)

def by_heading_year(text, R, award, out):
    """Pages organised as ==1974== sections."""
    text = strip_refs(text)
    for m in re.finditer(r"\n==\s*(\d{4})\s*==(.*?)(?=\n==[^=]|\Z)", text, re.S):
        y = int(m.group(1))
        for line in m.group(2).split("\n"):
            if re.search(r"coach", line, re.I): continue
            for k in R.people(line, y): out[award][k].add(y)

def rookie_page(text, R, out):
    """AP NFL Rookie of the Year page: combined award, then ===Offensive=== and ===Defensive=== sections."""
    parts = re.split(r"\n===\s*(Offensive|Defensive)\s*===", text)
    single_list(parts[0], R, "NFL Rookie of the Year", out)
    for i in range(1, len(parts) - 1, 2):
        body = re.split(r"\n==[^=]", parts[i + 1])[0]
        single_list(body, R, f"NFL {parts[i]} Rookie of the Year", out)

def membership(text, R, award, out):
    text = strip_refs(text)
    for line in text.split("\n"):
        for k in R.people(line): out[award][k]  # touch, no year

# ------------------------------------------------------------------ registry
SINGLE = {
    "AP NFL Most Valuable Player": ("NFL MVP", {}),
    "AP NFL Offensive Player of the Year": ("NFL Offensive Player of the Year", {}),
    "AP NFL Defensive Player of the Year": ("NFL Defensive Player of the Year", {}),
    "AP NFL Offensive Rookie of the Year": ("NFL Offensive Rookie of the Year", {}),
    "AP NFL Defensive Rookie of the Year": ("NFL Defensive Rookie of the Year", {}),
    "AP NFL Comeback Player of the Year": ("NFL Comeback Player of the Year", {}),
    "Super Bowl Most Valuable Player Award": ("Super Bowl MVP", {"season_from_sb": True}),
    "Walter Payton NFL Man of the Year Award": ("Walter Payton Man of the Year", {}),
    "Bert Bell Award": ("Bert Bell Award", {}),
    "American Football League Most Valuable Player Award": ("AFL MVP", {}),
    "American Football League Rookies of the Year": ("AFL Rookie of the Year", {}),
    "List of Pro Football Hall of Fame inductees": ("Pro Football Hall of Fame", {"min_year": 1963}),
    "List of College Football Hall of Fame inductees (players, A–K)": ("College Football Hall of Fame", {"min_year": 1951}),
    "Heisman Trophy": ("Heisman Trophy", {}), "Maxwell Award": ("Maxwell Award", {}), "Walter Camp Award": ("Walter Camp Award", {}),
    "Outland Trophy": ("Outland Trophy", {}), "Lombardi Award": ("Lombardi Award", {}), "Chuck Bednarik Award": ("Chuck Bednarik Award", {}),
    "Bronko Nagurski Trophy": ("Bronko Nagurski Trophy", {}), "Butkus Award": ("Butkus Award", {}), "Davey O'Brien Award": ("Davey O'Brien Award", {}),
    "Doak Walker Award": ("Doak Walker Award", {}), "Fred Biletnikoff Award": ("Fred Biletnikoff Award", {}), "Jim Thorpe Award": ("Jim Thorpe Award", {}),
    "John Mackey Award": ("John Mackey Award", {}), "Lou Groza Award": ("Lou Groza Award", {}), "Ray Guy Award": ("Ray Guy Award", {}),
    "Johnny Unitas Golden Arm Award": ("Johnny Unitas Golden Arm Award", {}), "Dave Rimington Trophy": ("Rimington Trophy", {}),
    "Ted Hendricks Award": ("Ted Hendricks Award", {}), "Lott IMPACT Trophy": ("Lott IMPACT Trophy", {}), "Manning Award": ("Manning Award", {}),
    "Walter Payton Award": ("Walter Payton Award", {}), "Buck Buchanan Award": ("Buck Buchanan Award", {}),
    "Chicago Tribune Silver Football": ("Chicago Tribune Silver Football", {}), "Harlon Hill Trophy": ("Harlon Hill Trophy", {}),
    "PFWA All-Rookie Team": ("PFWA All-Rookie Team", {}),
}
MEMBERSHIP = {"NFL 100th Anniversary All-Time Team": "NFL 100th Anniversary All-Time Team",
              "NFL 75th Anniversary All-Time Team": "NFL 75th Anniversary All-Time Team",
              "American Football League All-Time Team": "AFL All-Time Team"}
for d in range(1920, 2020, 10): MEMBERSHIP[f"NFL {d}s All-Decade Team"] = f"NFL {d}s All-Decade Team"

KIND = {"NFL MVP": ("statue", "Individual"), "AFL MVP": ("statue", "Individual"), "Super Bowl MVP": ("statue", "Individual"),
        "Pro Football Hall of Fame": ("plaque", "Honors & Service"), "College Football Hall of Fame": ("plaque", "Honors & Service"),
        "Walter Payton Man of the Year": ("plaque", "Honors & Service"), "First-team All-Pro": ("statue", "Individual"),
        "Second-team All-Pro": ("star", "Selections"), "First-team All-AFL": ("statue", "Individual"), "Second-team All-AFL": ("star", "Selections"),
        "Pro Bowl": ("star", "Selections"), "Consensus All-American": ("statue", "Individual"), "All-American": ("star", "Selections"),
        "PFWA All-Rookie Team": ("star", "Selections")}
def kind_of(name):
    if name in KIND: return KIND[name]
    if "All-Decade" in name or "All-Time" in name: return ("star", "Selections") if "Decade" in name else ("statue", "Individual")
    return ("statue", "Individual")


def award_winners(pages, R):
    out = defaultdict(lambda: defaultdict(set))
    seen_pages = {}
    for p in pages:
        t, text = p["title"], p["text"]
        if not text: continue
        if p["page"] in seen_pages and t != seen_pages[p["page"]]: continue
        seen_pages[p["page"]] = t
        try:
            if p["page"] == "AP NFL Rookie of the Year":
                rookie_page(text, R, out)
            elif t in ("PFWA All-Rookie Team", "American Football League Rookies of the Year"):
                by_heading_year(text, R, "PFWA All-Rookie Team" if t.startswith("PFWA") else "AFL Rookie of the Year", out)
            elif t in SINGLE:
                award, kw = SINGLE[t]; single_list(text, R, award, out, **kw)
            elif t in MEMBERSHIP:
                membership(text, R, MEMBERSHIP[t], out)
            elif re.fullmatch(r"\d{4} All-Pro Team", t):
                team_page(text, R, int(t[:4]), "First-team All-Pro", "Second-team All-Pro", out)
            elif re.fullmatch(r"\d{4} All-AFL Team", t):
                team_page(text, R, int(t[:4]), "First-team All-AFL", "Second-team All-AFL", out)
            elif re.fullmatch(r"\d{4} Pro Bowl( Games)?", t):
                pro_bowl(text, R, int(t[:4]) - 1, out)
            elif re.fullmatch(r"\d{4} College Football All-America Team", t):
                all_america(text, R, int(t[:4]), out)
        except Exception as e:
            print("  failed on", t, e)
    return out
