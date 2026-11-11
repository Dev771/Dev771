#!/usr/bin/env python3
"""Draw the profile README cards as animated SVGs into cards/, and write README.md.

The words come from profile.json and the numbers from data/ (fetch_data.py).

Each card is shown through an <img> tag, so it can only use inline CSS animation
and fonts embedded as data URIs: no scripts, no external requests. The gaps
between cards are drawn inside the SVGs, which is why README.md keeps each row
of cards on one line.

    python scripts/render_cards.py            animated cards
    STATIC=1 python scripts/render_cards.py   final frame only, for screenshots
"""
import base64
import datetime as dt
import json
import os
from collections import Counter
from html import escape
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
PROFILE = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
CONTRIB = json.loads((ROOT / "data" / "contributions.json").read_text(encoding="utf-8"))
REPOS = json.loads((ROOT / "data" / "repos.json").read_text(encoding="utf-8"))
STATIC = bool(os.environ.get("STATIC"))

# Colours are taken from the avatar: laptop-screen violet, cap-logo green, shirt mustard.
PAPER = "#EEF0EB"
CELL = "#DCE1D8"
INK = "#1D2025"
INK_SOFT = "#3A3F46"
MUTED = "#5E6670"
PARTIAL = "#BCC3B8"
VIOLET = "#5B3CF0"
GREEN = "#178652"
MUSTARD = "#F2B83B"
TITLE = "#7A5FF2"
HEAT = [CELL, "#CEC6FA", "#A493F6", "#7A5FF2", "#4B2BD8"]
TILE_COLORS = {"violet": (VIOLET, "#FFFFFF"), "green": (GREEN, "#FFFFFF"), "mustard": (MUSTARD, INK)}

W = 880            # GitHub's README column at 100%
GAP = 12           # space between cards, drawn into each SVG
THIRD = W / 3      # a card in a row of three is exactly a third of the column
PAD = 24           # inner padding of the small cards

FACES = {
    "display": ("Newsreader Display", 400, "news-display.woff2", "Georgia, serif"),
    "text": ("Newsreader", 400, "news-text.woff2", "Georgia, serif"),
    "text-semi": ("Newsreader", 600, "news-text-600.woff2", "Georgia, serif"),
    "pixel": ("Pixelify Sans", 400, "pixel-400.woff2", "ui-monospace, monospace"),
    "pixel-semi": ("Pixelify Sans", 600, "pixel-600.woff2", "ui-monospace, monospace"),
}


class Face:
    def __init__(self, key):
        self.family, self.weight, file, self.fallback = FACES[key]
        path = ROOT / "fonts" / file
        font = TTFont(path)
        self.upem = font["head"].unitsPerEm
        self.cmap = font.getBestCmap()
        self.adv = font["hmtx"].metrics
        self.b64 = base64.b64encode(path.read_bytes()).decode()

    def width(self, s, size):
        space = self.cmap[32]
        return sum(self.adv[self.cmap.get(ord(ch), space)][0] for ch in s) * size / self.upem


F = {k: Face(k) for k in FACES}

BASE_CSS = (
    "text{font-variant-numeric:lining-nums}"
    "@keyframes on{to{opacity:1}}"
    "@keyframes blink{0%,55%{opacity:1}56%,100%{opacity:0}}"
    ".in{opacity:0;animation:on .01s linear forwards}"
    ".cur{animation:blink 1.1s steps(1) infinite}"
    "@media (prefers-reduced-motion:reduce){.in{animation:none;opacity:1}.cur{animation:none}.scan{display:none}}"
)
STATIC_CSS = ".in{animation:none!important;opacity:1!important}.cur{animation:none!important}.scan{display:none}"


def wrap(s, face, size, width):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and F[face].width(trial, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def notched(x, y, w, h, s):
    """A rectangle whose corners step in twice, like a box in an 8-bit game."""
    pts = [
        (x + 2 * s, y), (x + w - 2 * s, y), (x + w - 2 * s, y + s), (x + w - s, y + s),
        (x + w - s, y + 2 * s), (x + w, y + 2 * s), (x + w, y + h - 2 * s), (x + w - s, y + h - 2 * s),
        (x + w - s, y + h - s), (x + w - 2 * s, y + h - s), (x + w - 2 * s, y + h), (x + 2 * s, y + h),
        (x + 2 * s, y + h - s), (x + s, y + h - s), (x + s, y + h - 2 * s), (x, y + h - 2 * s),
        (x, y + 2 * s), (x + s, y + 2 * s), (x + s, y + s), (x + 2 * s, y + s),
    ]
    return "M" + "L".join(f"{a:.2f} {b:.2f}" for a, b in pts) + "Z"


class Card:
    def __init__(self, w, h, label, left=0.0, right=0.0, bottom=GAP):
        self.w, self.h, self.label = w, h, label
        self.left, self.right, self.bottom = left, right, bottom
        self.parts, self.css, self.faces = [], [], []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, face, size, fill, anchor=None, extra=""):
        f = F[face]
        if face not in self.faces:
            self.faces.append(face)
        a = f' text-anchor="{anchor}"' if anchor else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="\'{f.family}\', {f.fallback}" '
            f'font-weight="{f.weight}" font-size="{size}" fill="{fill}"{a}{extra}>{escape(s)}</text>'
        )

    def paper(self, fill=PAPER, step=5):
        self.add(f'<path d="{notched(0, 0, self.w, self.h, step)}" fill="{fill}"/>')

    def svg(self):
        fonts = "".join(
            f"@font-face{{font-family:'{F[k].family}';font-style:normal;font-weight:{F[k].weight};"
            f"src:url(data:font/woff2;base64,{F[k].b64}) format('woff2')}}"
            for k in self.faces
        )
        css = fonts + BASE_CSS + "".join(self.css) + (STATIC_CSS if STATIC else "")
        body = "".join(self.parts)
        if self.left:
            body = f'<g transform="translate({self.left:.3f} 0)">{body}</g>'
        tw, th = self.w + self.left + self.right, self.h + self.bottom
        label = escape(self.label)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw:.3f}" height="{th:.0f}" '
            f'viewBox="0 0 {tw:.3f} {th:.0f}" role="img" aria-label="{label}">'
            f"<title>{label}</title><style>{css}</style>{body}</svg>"
        )


def third(i):
    """Width and side padding for card i in a row of three, so the gaps match GAP."""
    w = THIRD - 2 * GAP / 3
    left = [0, GAP / 3, 2 * GAP / 3][i]
    return w, left, THIRD - w - left


def save(name, card):
    (CARDS / name).write_text(card.svg(), encoding="utf-8")


# ---------------------------------------------------------------- data ------

DAYS = [(dt.date.fromisoformat(d["date"]), d["count"]) for d in CONTRIB["days"]]
LAST = DAYS[-1][0]


def fmt_date(d, year=True):
    return f"{d.day} {d:%b}" + (f" {d.year}" if year else "")


def streaks():
    counts = [c for _, c in DAYS]
    i = len(counts) - 1
    if counts[i] == 0:  # today may simply not have started yet
        i -= 1
    current = 0
    while i >= 0 and counts[i] > 0:
        current += 1
        i -= 1
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    return current, longest


def levels():
    nonzero = sorted(c for _, c in DAYS if c)
    if not nonzero:
        return lambda c: 0
    q = [nonzero[int(len(nonzero) * p)] for p in (0.25, 0.5, 0.75)]
    return lambda c: 0 if c == 0 else 1 + sum(c > t for t in q)


# ---------------------------------------------------------------- hero ------

def portrait_cells(rows):
    im = Image.open(ROOT / "assets" / "avatar.png").convert("RGBA")
    im = im.crop(im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox())
    w, h = im.size
    step = h / rows
    cols = round(w / step)
    flat = Image.new("RGB", im.size, (238, 240, 235))
    flat.paste(im, mask=im.getchannel("A"))
    q = flat.quantize(colors=16, method=Image.Quantize.MAXCOVERAGE, kmeans=3, dither=Image.Dither.NONE)
    pal, qp, ap = q.getpalette(), q.load(), im.getchannel("A").load()
    cells = []
    for r in range(rows):
        y0, y1 = int(r * step), min(h, int((r + 1) * step))
        for c in range(cols):
            x0, x1 = int(c * step), min(w, int((c + 1) * step))
            # vote over the middle of each block only, so edges of neighbouring pixels don't bleed in
            ix0, ix1 = x0 + int((x1 - x0) * 0.2), max(x0 + int((x1 - x0) * 0.8), x0 + 1)
            iy0, iy1 = y0 + int((y1 - y0) * 0.2), max(y0 + int((y1 - y0) * 0.8), y0 + 1)
            votes, n = Counter(), 0
            for yy in range(iy0, iy1):
                for xx in range(ix0, ix1):
                    n += 1
                    if ap[xx, yy] > 128:
                        votes[qp[xx, yy]] += 1
            if n and sum(votes.values()) >= n / 2:
                idx = votes.most_common(1)[0][0]
                cells.append((r, c, "#%02x%02x%02x" % tuple(pal[idx * 3: idx * 3 + 3])))
    return cells, cols


def hero():
    p = PROFILE
    x = 52
    tag = wrap(p["tagline"], "text", 20, 430)
    link_y = 258 + len(tag) * 30 + 26
    h = max(400, link_y + 38)
    card = Card(W, h, f'{p["name"]}. {p["role"]}. {p["tagline"]}')
    card.paper()

    card.text(x, 78, p["role"], "pixel", 16, MUTED)
    size = 118
    while F["display"].width(p["name"], size) > 440:
        size -= 2
    name_w = F["display"].width(p["name"], size)
    card.text(x - 5, 200, p["name"], "display", size, INK)
    cw, ch = round(size * 0.34), round(size * 0.6)
    card.add(f'<rect class="cur" x="{x + name_w + size * 0.06:.1f}" y="{200 - ch}" width="{cw}" height="{ch}" fill="{VIOLET}"/>')

    for i, line in enumerate(tag):
        card.text(x, 258 + i * 30, line, "text", 20, INK_SOFT)

    label = p["website"]["label"]
    card.text(x, link_y, label, "pixel", 15, VIOLET)
    dots = "".join(
        f'<rect x="{x + k}" y="{link_y + 6}" width="2" height="2"/>'
        for k in range(0, int(F["pixel"].width(label, 15)), 4)
    )
    card.add(f'<g fill="{VIOLET}">{dots}</g>')

    rows, pitch = 60, 6
    cells, cols = portrait_cells(rows)
    ox, oy = W - 44 - cols * pitch, h - rows * pitch
    colors = sorted({col for *_, col in cells})
    cls = {col: f"p{i}" for i, col in enumerate(colors)}
    card.css.append("".join(f".{v}{{fill:{k}}}" for k, v in cls.items()))
    start, length = 0.3, 1.5
    for r in range(rows):
        rects = "".join(
            f'<rect x="{ox + c * pitch}" y="{oy + r * pitch}" width="{pitch - 1}" height="{pitch - 1}" class="{cls[col]}"/>'
            for rr, c, col in cells if rr == r
        )
        if rects:
            card.add(f'<g class="in" style="animation-delay:{start + r * length / rows:.3f}s">{rects}</g>')
    # A violet bar sweeps down the portrait one row at a time, just ahead of the rows drawing in.
    # SMIL rather than a CSS transform: Chrome doesn't move SVG shapes with transform keyframes reliably.
    ys = ";".join(str(oy + r * pitch) for r in range(rows))
    card.add(
        f'<rect class="scan" x="{ox - 6}" y="{oy}" width="{cols * pitch + 11}" height="{pitch - 1}" fill="{VIOLET}" opacity="0">'
        f'<animate attributeName="y" values="{ys}" calcMode="discrete" begin="{start}s" dur="{length}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0.85" begin="{start}s" dur="{length}s"/></rect>'
    )
    save("hero.svg", card)


# ------------------------------------------------------------- heatmap ------

def heatmap():
    level = levels()
    first_sunday = DAYS[0][0] - dt.timedelta(days=(DAYS[0][0].weekday() + 1) % 7)
    pos = [((d - first_sunday).days // 7, (d.weekday() + 1) % 7, d, c) for d, c in DAYS]
    ncols = pos[-1][0] + 1
    pitch, size = 15, 12
    grid_w = ncols * pitch - (pitch - size)
    x0, y0 = (W - grid_w) / 2, 104
    h = 252
    card = Card(W, h, f"Contribution graph for the last year, one square per day, ending {fmt_date(LAST)}")
    card.paper()
    card.text(x0 - 2, 72, "Twelve months, one square a day", "display", 34, INK)

    # legend, top right
    lx = x0 + grid_w
    card.text(lx, 70, "More", "pixel", 13, MUTED, anchor="end")
    lx -= F["pixel"].width("More", 13) + 8
    for i in reversed(range(5)):
        lx -= size
        card.add(f'<rect x="{lx:.1f}" y="{60}" width="{size}" height="{size}" fill="{HEAT[i]}"/>')
        lx -= 3
    card.text(lx - 5, 70, "Less", "pixel", 13, MUTED, anchor="end")

    for col in range(ncols):
        rects = "".join(
            f'<rect x="{x0 + col * pitch:.1f}" y="{y0 + row * pitch}" width="{size}" height="{size}" fill="{HEAT[level(c)]}"/>'
            for cc, row, _, c in pos if cc == col
        )
        card.add(f'<g class="in" style="animation-delay:{0.15 + col * 0.018:.3f}s">{rects}</g>')

    last_label = -10
    for col in range(ncols):
        firsts = [d for cc, _, d, _ in pos if cc == col and d.day == 1]
        if firsts and col - last_label >= 3:
            card.text(x0 + col * pitch, y0 + 7 * pitch + 20, f"{firsts[0]:%b}", "pixel", 13, MUTED)
            last_label = col
    save("heatmap.svg", card)


# ------------------------------------------------------------ activity ------

def months_back(n):
    y, m = LAST.year, LAST.month
    out = []
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def dotted_rule(card, x, y, w):
    dots = "".join(f'<rect x="{x + k}" y="{y}" width="2" height="2"/>' for k in range(0, int(w), 5))
    card.add(f'<g fill="{PARTIAL}">{dots}</g>')


def activity():
    total = CONTRIB["total"]
    current, longest = streaks()
    active = sum(1 for _, c in DAYS if c)
    busiest_day, busiest = max(DAYS, key=lambda dc: dc[1])
    months = months_back(12)
    sums = [sum(c for d, c in DAYS if (d.year, d.month) == ym) for ym in months]
    top = max(range(12), key=lambda i: sums[i])

    h = 340
    card = Card(
        W, h,
        f"{total:,} contributions in the last year. Current streak {current} days, longest {longest}. "
        f"{active} of {len(DAYS)} days with a contribution. Busiest day: {busiest} on {fmt_date(busiest_day)}.",
    )
    card.paper()
    card.text(48, 64, "Contributions in the last year", "pixel", 15, MUTED)
    card.text(44, 142, f"{total:,}", "display", 78, INK)

    # monthly bars, built from stacked blocks
    base, bx, span = 296, 48, 508
    bar_w, block, gap, max_blocks = 28, 8, 3, 12
    step = span / 12
    peak = max(sums) or 1
    for i, (ym, s) in enumerate(zip(months, sums)):
        x = bx + i * step + (step - bar_w) / 2
        n = 0 if s == 0 else max(1, round(s / peak * max_blocks))
        partial = i == 11 and LAST.day < 28
        fill = VIOLET if i == top else (PARTIAL if partial else INK)
        for j in range(n):
            y = base - (j + 1) * block - j * gap
            card.add(
                f'<rect class="in" style="animation-delay:{0.2 + i * 0.05 + j * 0.035:.3f}s" '
                f'x="{x:.1f}" y="{y}" width="{bar_w}" height="{block}" fill="{fill}"/>'
            )
        if i == top:
            card.text(x + bar_w / 2, base - n * (block + gap) - 6, f"{s:,}", "pixel", 13, VIOLET, anchor="middle")
        card.text(x + bar_w / 2, base + 24, dt.date(ym[0], ym[1], 1).strftime("%b"), "pixel", 13, MUTED, anchor="middle")

    # three numbers on the right
    rx, rw = 616, W - 48 - 616
    card.text(W - 48, 64, f"Updated {fmt_date(LAST)}", "pixel", 13, MUTED, anchor="end")
    big = 40

    unit = " day" if current == 1 else " days"
    card.text(rx, 132, f"{current}", "display", big, INK)
    card.text(rx + F["display"].width(str(current), big) + 2, 132, unit, "display", 26, INK)
    note = "current streak, the longest yet" if current >= longest else f"current streak; longest was {longest}"
    card.text(rx, 156, note, "text", 15, MUTED)
    dotted_rule(card, rx, 178, rw)

    card.text(rx, 226, f"{active}", "display", big, INK)
    card.text(rx + F["display"].width(str(active), big) + 6, 226, f"/ {len(DAYS)}", "display", 26, MUTED)
    card.text(rx, 250, "days with a contribution", "text", 15, MUTED)
    dotted_rule(card, rx, 272, rw)

    card.text(rx, 316, f"{busiest}", "display", big, INK)
    card.text(rx + F["display"].width(str(busiest), big) + 8, 316, f"on {fmt_date(busiest_day)}", "text", 15, MUTED)
    save("activity.svg", card)


# --------------------------------------------------------------- tiles ------

ICONS = {
    "briefcase": [
        "..........",
        "...####...",
        "...#..#...",
        "##########",
        "##########",
        "##########",
        "####..####",
        "##########",
        "##########",
        "..........",
    ],
    "rocket": [
        "....##....",
        "...####...",
        "...#..#...",
        "...#..#...",
        "...####...",
        "..######..",
        ".##.##.##.",
        ".#..##..#.",
        "....##....",
        "...#..#...",
    ],
    "stack": [
        "..........",
        "...####...",
        "...####...",
        "..........",
        ".########.",
        ".########.",
        "..........",
        "##########",
        "##########",
        "..........",
    ],
}


def tile(t, i):
    w, left, right = third(i)
    h = 232
    bg, fg = TILE_COLORS[t["color"]]
    card = Card(w, h, f'{t["label"]}: {t["text"]}', left=left, right=right)
    card.paper(bg, step=4)
    card.text(PAD, 46, t["label"], "pixel-semi", 18, fg)
    px = 4
    ix, iy = w - PAD - 10 * px, 24
    cells = "".join(
        f'<rect x="{ix + c * px:.1f}" y="{iy + r * px}" width="{px}" height="{px}"/>'
        for r, row in enumerate(ICONS[t["icon"]])
        for c, ch in enumerate(row)
        if ch == "#"
    )
    card.add(f'<g fill="{fg}">{cells}</g>')
    lines = wrap(t["text"], "text", 17, w - 2 * PAD)
    for k, line in enumerate(lines):
        card.text(PAD, h - 28 - (len(lines) - 1 - k) * 24, line, "text", 17, fg)
    save(f'tile-{t["id"]}.svg', card)


# --------------------------------------------------------------- repos ------

def title(text, slug):
    # This one sits on GitHub's own background, light or dark. A mid violet reads on both,
    # which is safer than a <picture> swap that follows the OS theme rather than GitHub's.
    card = Card(W, 68, text, bottom=4)
    card.text(2, 50, text, "display", 38, TITLE)
    save(f"title-{slug}.svg", card)


def repo_language(r, meta):
    want = r.get("language")
    if want:
        for lang in meta["languages"]:
            if lang["name"] == want:
                return lang
        return {"name": want, "color": MUTED}
    return meta["language"] or {"name": "", "color": MUTED}


def repo_card(r, i):
    meta = REPOS[r["name"]]
    w, left, right = third(i)
    h = 204
    card = Card(w, h, f'{r["name"]}: {r["description"]}', left=left, right=right)
    card.paper(step=4)
    inner = w - 2 * PAD
    size = 20
    while F["text-semi"].width(r["name"], size) > inner and size > 14:
        size -= 0.5
    card.text(PAD, 50, r["name"], "text-semi", size, INK)
    for k, line in enumerate(wrap(r["description"], "text", 15.5, inner)[:4]):
        card.text(PAD, 82 + k * 22, line, "text", 15.5, INK_SOFT)

    y = h - 26
    lang = repo_language(r, meta)
    if lang["name"]:
        card.add(f'<rect x="{PAD}" y="{y - 9}" width="9" height="9" fill="{lang["color"] or MUTED}"/>')
        card.text(PAD + 15, y, lang["name"], "pixel", 13, INK_SOFT)
    if meta["homepage"]:
        card.text(w - PAD, y, "Live site", "pixel", 13, GREEN, anchor="end")
        lw = F["pixel"].width("Live site", 13)
        card.add(f'<rect x="{w - PAD - lw - 13:.1f}" y="{y - 8}" width="7" height="7" fill="{GREEN}"/>')
    elif meta["stars"]:
        card.text(w - PAD, y, f'{meta["stars"]} star' + ("s" if meta["stars"] != 1 else ""), "pixel", 13, MUTED, anchor="end")
    save(f'repo-{r["name"].lower()}.svg', card)


# -------------------------------------------------------------- README ------

def readme():
    p = PROFILE
    a = lambda s: escape(s, quote=True)
    current, longest = streaks()
    tiles = "".join(
        f'<a href="{a(t["url"])}"><img src="./cards/tile-{t["id"]}.svg" width="33.333%" alt="{a(t["label"] + ": " + t["text"])}" /></a>'
        for t in p["tiles"]
    )
    repos = "".join(
        f'<a href="{a(REPOS[r["name"]]["url"])}"><img src="./cards/repo-{r["name"].lower()}.svg" width="33.333%" alt="{a(r["name"] + ": " + r["description"])}" /></a>'
        for r in p["repos"]
    )
    links = " &nbsp;/&nbsp; ".join(f'<a href="{a(l["url"])}">{escape(l["label"])}</a>' for l in p["links"])
    text = f"""<!-- Generated by scripts/render_cards.py. Edit profile.json, not this file.
     The cards are animated SVGs, refreshed every day by .github/workflows/refresh-cards.yml.
     Keep this block free of blank lines and each row of cards on one line: the gaps are inside the SVGs. -->
<div align="center">
<a href="{a(p["website"]["url"])}"><img src="./cards/hero.svg" width="100%" alt="{a(p["name"] + ". " + p["role"] + ". " + p["tagline"])}" /></a><br>
<img src="./cards/heatmap.svg" width="100%" alt="Contribution graph for the last year, one square per day" /><br>
<img src="./cards/activity.svg" width="100%" alt="{a(f"{CONTRIB['total']:,} contributions in the last year, by month. Current streak {current} days, longest {longest}.")}" /><br>
{tiles}<br>
<img src="./cards/title-building.svg" width="100%" alt="What I've been building" /><br>
{repos}
</div>

<p align="center">
{links}
</p>
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def main():
    CARDS.mkdir(exist_ok=True)
    hero()
    heatmap()
    activity()
    for i, t in enumerate(PROFILE["tiles"]):
        tile(t, i)
    title("What I've been building", "building")
    for i, r in enumerate(PROFILE["repos"]):
        repo_card(r, i)
    readme()
    sizes = sorted((f.stat().st_size // 1024, f.name) for f in CARDS.glob("*.svg"))
    print("  ".join(f"{n} {kb}KB" for kb, n in sizes))


if __name__ == "__main__":
    main()
