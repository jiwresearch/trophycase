"""Parse Wikipedia "List of Olympic medalists in ..." wikitext into medals.

medals(text) yields (linked title, color, year, event, games) for every person linked in a medal cell.
Tables look like:  |[[Swimming at the 1988 Summer Olympics|1988 Seoul]]<br>{{DetailsLink|... – Women's 50 metre freestyle}}
                   |{{flagIOCmedalist|[[Kristin Otto]]|GDR|1988 Summer}}   <- gold, then silver, then bronze
Rows with no Games cell continue the row above (tied bronzes, or rowspan), so their cells fill the last columns.
"""
import re

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
COLORS = ("gold", "silver", "bronze")
NOT_PERSON = re.compile(r"Olympics|^\d{4}|national|team$|^List of|Games|^(?:File|Image|Category):", re.I)


def _cells(row):
    """Split a table row into [(cell text, rowspan)] (one per '|' line, or '||' separated)."""
    cells = []
    for line in row.split("\n"):
        st = line.strip()
        if not st.startswith("|") or st.startswith(("|}", "|-", "|+")):
            if cells and st and not st.startswith(("!", "{|", "|}", "|-")): cells[-1][0] += "\n" + st   # wrapped cell
            continue
        for part in re.split(r"\|\|", st[1:]):
            m = re.match(r'\s*((?:[a-z\-]+\s*=\s*(?:"[^"]*"|[^|\[{]*)\s*)+)\|(?!\|)(.*)$', part, re.S)
            attrs, body = (m.group(1), m.group(2)) if m else ("", part)
            rs = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
            cells.append([body, int(rs.group(1)) if rs else 1])
    return cells


QUOTES = re.compile("'{2,3}")
def _people(cell):
    """Linked people, plus 'name:<text>' for plain-text names on their own line (relay rosters often skip repeat links)."""
    out = []
    for m in LINK.finditer(cell):
        t = m.group(1).strip()
        if t and not NOT_PERSON.search(t): out.append(t[:1].upper() + t[1:])
    for part in re.split(r"<br\s*/?>|\n", cell):
        q = re.sub(r"\{\{[^{}]*\}\}|\[\[[^\]]*\]\]|\*|<[^>]+>", "", QUOTES.sub("", part)).strip(" ,;()")
        if re.fullmatch(r"[A-ZÀ-Þ][\w'’.\-]+(?: [\w'’.\-]+){1,3}", q) and not re.search(r"\d|none|awarded|team", q, re.I):
            out.append("name:" + q)
    return out


def _games(cell):
    m = re.search(r"(\d{4}) (Summer|Winter) Olympics", cell) or re.search(r"\b(18[89]\d|19\d\d|20[0-3]\d)\b", cell)
    if not m: return None
    year = int(m.group(1))
    season = m.group(2) if m.lastindex and m.lastindex >= 2 else ("Winter" if re.search(r"Winter", cell) else "Summer")
    return year, f"{year} {season} Olympics"


def medals(text, default_event=""):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    heading = default_event
    pos = 0
    for tm in re.finditer(r"\{\|(.*?)\n\|\}", text, re.S):
        before = text[pos:tm.start()]
        hs = re.findall(r"(?m)^=+\s*(.*?)\s*=+\s*$", before)
        if hs: heading = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", hs[-1]).strip()
        pos = tm.end()
        last = None      # (year, games, event)
        spans = {}       # column -> rows it still covers (from rowspan)
        for row in re.split(r"\n\|-[^\n]*", tm.group(1)):
            cells = _cells(row)
            if not cells: continue
            first = cells[0][0]
            g = _games(first) if (0 not in spans and not _people(first) and re.search(r"\d{4} (?:Summer|Winter) Olympics", first)
                                  and not re.search(r"sweep|multiple|statistic|leading|most |by nation|records?$", heading, re.I)) else None
            medal_like = lambda b: re.search(r"\[\[|\{\{\s*flag|none awarded|not awarded", b, re.I)
            if g:
                dm = re.search(r"\{\{\s*Details ?link\s*\|([^}|]+)", first, re.I)
                ev = dm.group(1).split(" – ")[-1].strip() if dm and " – " in dm.group(1) else ""
                last = (g[0], g[1], ev or heading)
                spans = {}
                mc = [c for c in cells[1:] if medal_like(c[0])]   # skip time/score columns
                slots = range(len(mc))
            elif last:
                mc = [c for c in cells if medal_like(c[0])]
                free = [c for c in range(3) if spans.get(c, 0) <= 0]
                slots = free[-len(mc):] if mc and len(mc) <= len(free) else free[:len(mc)]
            else:
                continue
            new_spans = {}
            for (body, rs), slot in zip(mc, slots):
                if rs > 1: new_spans[slot] = rs
                if 0 <= slot <= 2:
                    for p in _people(body): yield p, COLORS[slot], last[0], last[2], last[1]
            spans = {c: n - 1 for c, n in spans.items() if n - 1 > 0}
            spans.update({c: n - 1 for c, n in new_spans.items()})
