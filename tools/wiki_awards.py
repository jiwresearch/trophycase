"""Parse a Wikipedia 'Infobox NFL biography' into trophies, stats and draft facts for Trophy Case."""
import re

ROMAN = {}
def _roman(n):
    vals = [(50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    s = ""
    for v, r in vals:
        while n >= v: s += r; n -= v
    return s
for n in range(1, 70):
    ROMAN[_roman(n)] = 1965 + n  # Super Bowl I = 1966 season

YEAR_TPL = re.compile(r"\{\{\s*(?:nfl\s*year|nfly|nflyr|afl\s*year|afly|aafc\s*year|cfly|cfl\s*year|cfb\s*year|cfby|nfl\s*season|nfldraft|nfl\s*draft|ncaa\s*year|byy|ussy|year)\s*\|\s*(\d{4})[^{}]*\}\}", re.I)
SB_TPL = re.compile(r"\{\{\s*(?:sbwin|super\s*bowl\s*champion|sb|super\s*bowl)\s*\|([^{}]*)\}\}", re.I)


def plain(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = YEAR_TPL.sub(r"\1", s)
    s = SB_TPL.sub(lambda m: "Super Bowl champion (" + ", ".join(x.strip() for x in m.group(1).split("|") if x.strip() and "=" not in x) + ")", s)
    for _ in range(3):
        s = re.sub(r"\{\{\s*(?:small|nowrap|sup|abbr)\s*\|([^{}|]*)(?:\|[^{}]*)?\}\}", r"\1", s, flags=re.I)
        s = re.sub(r"\{\{\s*(?:ndash|snd|spaced ndash)\s*\}\}", "–", s, flags=re.I)
        s = re.sub(r"\{\{\s*(?:pro\s*bowl|probowl|pb)\s*\|([^{}]*)\}\}", lambda m: "Pro Bowl (" + ", ".join(re.findall(r"\d{4}", m.group(1))) + ")", s, flags=re.I)
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&ndash;", "–")
    return re.sub(r"[ \t]+", " ", s).strip()


def fields(ib):
    """Split infobox into {field: raw value} at top-level pipes."""
    out, depth, cur, i = {}, 0, "", 0
    body = ib[2:-2] if ib.startswith("{{") else ib
    parts = []
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["): depth += 1; cur += two; i += 2; continue
        if two in ("}}", "]]"): depth -= 1; cur += two; i += 2; continue
        if body[i] == "|" and depth == 0: parts.append(cur); cur = ""; i += 1; continue
        cur += body[i]; i += 1
    parts.append(cur)
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def years_in(s):
    ys = []
    for a, b in re.findall(r"(\d{4})\s*[–—-]\s*(\d{2,4})", s):
        a = int(a); b = int(b) if len(b) == 4 else int(str(a)[:2] + b)
        if 1900 < a <= b <= 2030 and b - a < 30: ys += list(range(a, b + 1))
    s2 = re.sub(r"(\d{4})\s*[–—-]\s*(\d{2,4})", " ", s)
    ys += [int(y) for y in re.findall(r"\b(19\d\d|20[0-3]\d)\b", s2)]
    if "Super Bowl" in s and re.search(r"\b50\b", s): ys.append(2015)
    for r in re.findall(r"\b([LXVI]{1,7})\b", s):
        if r in ROMAN and "Super Bowl" in s: ys.append(ROMAN[r])
    return sorted(set(ys))


# (pattern, display name, kind, shelf).  First match wins; order matters.
RULES = [
    (r"super bowl (?:mvp|most valuable)", "Super Bowl MVP", "statue", "Individual"),
    (r"super bowl champion|super bowl \(|^super bowl$|super bowl winner|won super bowl", "Super Bowl Champion", "ring", "Championships"),
    (r"\bnfl champion|nfl championship", "NFL Championship", "cup", "Championships"),
    (r"\bafl champion", "AFL Championship", "cup", "Championships"),
    (r"\baafc champion", "AAFC Championship", "cup", "Championships"),
    (r"grey cup", "Grey Cup", "cup", "Championships"),
    (r"national champion", "National Championship", "cup", "Championships"),
    (r"afl (?:most valuable player|mvp)", "AFL MVP", "statue", "Individual"),
    (r"bert bell award|jim thorpe trophy|pfwa .*player of the year", None, "statue", "Individual"),
    (r"pfwa all[- ]rookie", "PFWA All-Rookie Team", "star", "Selections"),
    (r"aafc (?:most valuable player|mvp)|(?:nfl|ap|league) (?:most valuable player|mvp)|^most valuable player|^mvp\b|nfl mvp", "NFL MVP", "statue", "Individual"),
    (r"offensive player of the year", "NFL Offensive Player of the Year", "statue", "Individual"),
    (r"defensive player of the year", "NFL Defensive Player of the Year", "statue", "Individual"),
    (r"offensive rookie of the year", "NFL Offensive Rookie of the Year", "statue", "Individual"),
    (r"defensive rookie of the year", "NFL Defensive Rookie of the Year", "statue", "Individual"),
    (r"afl comeback player of the year", "AFL Comeback Player of the Year", "statue", "Individual"),
    (r"comeback player of the year", "NFL Comeback Player of the Year", "statue", "Individual"),
    (r"afl rookie of the year", "AFL Rookie of the Year", "statue", "Individual"),
    (r"rookie of the year", "Rookie of the Year", "statue", "Individual"),
    (r"walter payton (?:nfl )?man of the year|nfl man of the year", "Walter Payton Man of the Year", "plaque", "Honors & Service"),
    (r"first[- ]team all[- ]pro|^all[- ]pro\b|^\d+× all[- ]pro", "First-team All-Pro", "statue", "Individual"),
    (r"second[- ]team all[- ]pro", "Second-team All-Pro", "star", "Selections"),
    (r"first[- ]team all[- ]afl|^all[- ]afl|^\d+× all[- ]afl", "First-team All-AFL", "statue", "Individual"),
    (r"second[- ]team all[- ]afl", "Second-team All-AFL", "star", "Selections"),
    (r"first[- ]team all[- ]aafc|all[- ]aafc", "All-AAFC", "statue", "Individual"),
    (r"pro bowl", "Pro Bowl", "star", "Selections"),
    (r"afl all[- ]star", "AFL All-Star", "star", "Selections"),
    (r"all[- ]decade team", None, "star", "Selections"),
    (r"anniversary (?:all[- ]time )?team|all[- ]time team", None, "statue", "Individual"),
    (r"(?:nfl|afl) (?:passing|rushing|receiving|scoring|sacks|interceptions) (?:yards |touchdowns )?leader|(?:passing|rushing|receiving) (?:yards|touchdowns|yardage) leader|interceptions leader|sacks leader|scoring leader|receptions leader", None, "medal", "Individual"),
    (r"heisman", "Heisman Trophy", "statue", "Individual"),
    (r"^first[- ]team all[- ]|^\d+× first[- ]team all[- ]", None, "star", "Selections"),
    (r"maxwell award|walter camp award|davey o'brien|doak walker|outland|lombardi award|bednarik|nagurski|butkus|biletnikoff|jim thorpe award|lou groza|ray guy|johnny unitas golden arm|manning award|john mackey|rimington|ted hendricks|lott (?:impact|trophy)|silver football|paul hornung|wuerffel", None, "statue", "Individual"),
    (r"unanimous all-american|consensus all-american", "Consensus All-American", "statue", "Individual"),
    (r"all-american", "All-American", "star", "Selections"),
    (r"pro football hall of fame", "Pro Football Hall of Fame", "plaque", "Honors & Service"),
    (r"college football hall of fame", "College Football Hall of Fame", "plaque", "Honors & Service"),
    (r"hall of fame|ring of honor|ring of fame|wall of honor|hall of honor", None, "plaque", "Honors & Service"),
    (r"no\. \d+ retired|number retired|jersey retired|retired by", None, "medallion", "Honors & Service"),
    (r"medal of honor|purple heart|bronze star|silver star|navy cross|distinguished service|presidential medal of freedom", None, "medal", "Honors & Service"),
]
COLLEGE = re.compile(r"\b(ACC|SEC|Big Ten|Big 12|Big Eight|Big Seven|Big Six|Big East|Pac-1[02]|Pac-8|Southwest Conference|SWC|MAC|WAC|Mountain West|Sun Belt|C-USA|Conference USA|AAC|American Athletic|Ivy|SoCon|Southern Conference|MVC|Missouri Valley|Atlantic Coast|Southeastern|Big Sky|Ohio Valley|Patriot League|CAA|MEAC|SWAC|NCAA|NAIA|college|Conference|Division I|I-AA|FCS)\b")
PRO_NAMES = {"NFL MVP", "NFL Offensive Player of the Year", "NFL Defensive Player of the Year", "NFL Offensive Rookie of the Year",
             "NFL Defensive Rookie of the Year", "NFL Comeback Player of the Year", "Rookie of the Year", "First-team All-Pro", "Second-team All-Pro", "Pro Bowl"}
SKIP = re.compile(r"record|^career|^\s*$|stats?\b|tied|first .* to|only player|most |longest|youngest|oldest|fastest|highest|lowest|consecutive", re.I)


def parse_highlights(raw):
    """-> list of {"n","k","c","y","x"} trophies."""
    raw = re.sub(r"<br\s*/?>", "\n* ", raw)
    lines = []
    for ln in raw.split("\n"):
        ln = ln.strip()
        if ln.startswith("*") or (not lines and ln and not ln.startswith(";")): lines.append(ln.lstrip("*").strip())
        elif ln.startswith(";"): lines.append("")
    out = {}
    for ln in lines:
        t = plain(ln).strip(" *•;,")
        if not t or len(t) > 220: continue
        mcount = re.match(r"^(\d+)\s*[×x]\s*", t)
        count = int(mcount.group(1)) if mcount else 0
        body = t[mcount.end():] if mcount else t
        name_part = re.split(r"\s*\(", body, 1)[0].strip()
        low = body.lower()
        rule = None
        for pat, disp, kind, shelf in RULES:
            if re.search(pat, low):
                rule = (disp, kind, shelf); break
        if not rule:
            continue
        if SKIP.search(name_part) and rule[0] not in ("NFL MVP", "Pro Bowl"):
            if not re.search(r"hall of fame|all[- ]decade|anniversary|retired|leader", low): continue
        disp, kind, shelf = rule
        if disp in PRO_NAMES and COLLEGE.search(body):
            disp, kind, shelf = None, "statue", "Individual"
        if disp is None:
            disp = re.sub(r"\s+", " ", name_part)[:70]
            disp = disp[:1].upper() + disp[1:]
            if re.search(r"retired", low):
                disp = re.sub(r"^.*?(No\. ?\d+).*?retired.*$", r"\1 retired", name_part, flags=re.I)
                m = re.search(r"([A-Z][A-Za-z.' ]+?)\s+(?:No\.|#)\s*\d+", name_part)
                disp = (m.group(1).strip() + " " if m else "") + re.sub(r".*?(No\.\s?\d+|#\d+).*", r"\1", name_part) + " retired"
        ys = years_in(body)
        n = count or max(len(ys), 1)
        key = (disp, kind, shelf)
        if key in out:
            prev = out[key]
            prev["ys"] = sorted(set(prev["ys"]) | set(ys)); prev["n"] = max(prev["n"], n, len(prev["ys"]))
        else:
            out[key] = {"ys": ys, "n": n}
    res = []
    for (disp, kind, shelf), v in out.items():
        res.append({"n": disp, "k": kind, "c": shelf, "ys": v["ys"], "x": v["n"]})
    return res


def parse(ib):
    f = fields(ib)
    for mk in ("module", "module2", "module3"):
        mv = f.get(mk, "")
        j = mv.lower().find("{{infobox")
        if j >= 0:
            for k, v in fields(mv[j:]).items():
                f.setdefault(k, v)
    hl = f.get("highlights", "") or f.get("highlights_and_awards", "") or f.get("awards", "")
    trophies = parse_highlights(hl)
    hof = f.get("hof", "") or f.get("pfhof", "") or f.get("hofyear", "")
    hofy = None
    if hof and plain(hof):
        m = re.search(r"(19|20)\d\d", plain(hof) + " " + f.get("hof_year", ""))
        hofy = int(m.group(0)) if m else None
        if not any(t["n"] == "Pro Football Hall of Fame" for t in trophies):
            trophies.append({"n": "Pro Football Hall of Fame", "k": "plaque", "c": "Honors & Service", "ys": [hofy] if hofy else [], "x": 1})
    if plain(f.get("collegehof", "")) and not any(t["n"] == "College Football Hall of Fame" for t in trophies):
        trophies.append({"n": "College Football Hall of Fame", "k": "plaque", "c": "Honors & Service", "ys": [], "x": 1})
    stats = []
    for i in range(1, 9):
        lab = f.get(f"statlabel{i}") or f.get(f"stat_label{i}") or f.get(f"stat{i}label")
        val = f.get(f"statvalue{i}") or f.get(f"stat_value{i}") or f.get(f"stat{i}value")
        if lab and val:
            lab, val = plain(lab), plain(val)
            if lab and val and len(lab) < 40 and len(val) < 20: stats.append([lab, val])
    draft = None
    dy, dr, dp = (plain(f.get(k, "")) for k in ("draftyear", "draftround", "draftpick"))
    if re.fullmatch(r"\d{4}", dy or ""):
        draft = [int(dy), int(dr) if (dr or "").isdigit() else None, int(dp) if (dp or "").isdigit() else None]
    col = plain(f.get("college", ""))
    col = re.split(r"\s*\(|\n|,|;| and ", col)[0].strip() if col else ""
    return {"trophies": trophies, "stats": stats, "draft": draft, "hofy": hofy, "position": plain(f.get("position", "")), "college": col}
