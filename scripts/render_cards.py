#!/usr/bin/env python3
"""Draw the profile README cards as animated SVGs into cards/, and write README.md.

Theme: a pixel-art night city, built around the avatar. The words come from
profile.json and the numbers from data/ (fetch_data.py).

Each card is shown through an <img> tag, so it can only use inline CSS/SMIL
animation and fonts embedded as data URIs: no scripts, no external requests.
The gaps between cards are drawn inside the SVGs, which is why README.md keeps
each row of cards on one line.

    python scripts/render_cards.py            animated cards
    STATIC=1 python scripts/render_cards.py   final frame only, for screenshots
"""
import base64
import datetime as dt
import hashlib
import json
import os
import random
from collections import Counter, defaultdict
from html import escape
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
PROFILE = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
CONTRIB = json.loads((ROOT / "data" / "contributions.json").read_text(encoding="utf-8"))
REPOS = json.loads((ROOT / "data" / "repos.json").read_text(encoding="utf-8"))
LANGS = json.loads((ROOT / "data" / "languages.json").read_text(encoding="utf-8"))
STATIC = bool(os.environ.get("STATIC"))

# Night palette. Accents come from the avatar: laptop violet, cap-logo green, shirt mustard.
SKY = ["#0B0A1C", "#100E28", "#151234", "#1B1740", "#221C4D"]
PANEL = "#13122A"
EDGE = "#2E2A5C"
INSET = "#0D0C1F"
TEXT = "#EDEBFF"
TEXT_SOFT = "#C3BFE3"
MUTED = "#8C88B0"
VIOLET = "#7B61FF"
LAVENDER = "#A99BFF"
GREEN = "#3DDC84"
MUSTARD = "#F2B83B"
ORANGE = "#FF8A4C"
RED = "#FF5A5F"
NIGHT = ["#0B0A1C", "#0E0C24", "#110F2B", "#151233", "#1A163E", "#251D55"]  # down to a violet horizon glow
FAR = "#100E27"
BUILDINGS = ["#231E4C", "#28225A", "#2E2763"]
WINDOW_OFF = "#17143A"
WINDOW_ON = [None, "#7A5E22", "#B8892E", "#F2B83B", "#FFE08A"]
CART = "#272250"
CART_DARK = "#1B1839"
ACCENTS = {"violet": VIOLET, "green": GREEN, "mustard": MUSTARD}

W = 880            # GitHub's README column at 100%
GAP = 12           # space between cards, drawn into each SVG
THIRD = W / 3

FACES = {
    # Tiny5 for running text and labels: Pixelify's small B, C and 5 read as G, O and S.
    "px": ("Tiny5", 400, "tiny5-400.woff2"),
    "px-med": ("Tiny5", 400, "tiny5-400.woff2"),
    "px-semi": ("Tiny5", 400, "tiny5-400.woff2"),
    # Pixelify Bold only for big display lines, where its letters are large enough to read.
    "px-bold": ("Pixelify Sans", 700, "pixel-700.woff2"),
    # Pixelify's 5 looks like an S, so big numbers use Jersey 10 (scoreboard style).
    "num": ("Jersey 10", 400, "jersey10-400.woff2"),
}


class Face:
    def __init__(self, key):
        self.family, self.weight, file = FACES[key]
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
    "@keyframes tw{0%,100%{opacity:1}50%{opacity:.15}}"
    ".in{opacity:0;animation:on .01s linear forwards}"
    ".cur{animation:blink 1.1s steps(1) infinite}"
    ".tw{animation:tw 3.2s steps(4) infinite}"
    "@media (prefers-reduced-motion:reduce){.in{animation:none;opacity:1}.cur,.tw{animation:none}}"
)
STATIC_CSS = ".in{animation:none!important;opacity:1!important}.cur,.tw{animation:none!important}"


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


def path(pts):
    return "M" + "L".join(f"{a:.2f} {b:.2f}" for a, b in pts) + "Z"


def notched(x, y, w, h, s):
    """A rectangle whose corners step in twice, like a window in an 8-bit game."""
    return path([
        (x + 2 * s, y), (x + w - 2 * s, y), (x + w - 2 * s, y + s), (x + w - s, y + s),
        (x + w - s, y + 2 * s), (x + w, y + 2 * s), (x + w, y + h - 2 * s), (x + w - s, y + h - 2 * s),
        (x + w - s, y + h - s), (x + w - 2 * s, y + h - s), (x + w - 2 * s, y + h), (x + 2 * s, y + h),
        (x + 2 * s, y + h - s), (x + s, y + h - s), (x + s, y + h - 2 * s), (x, y + h - 2 * s),
        (x, y + 2 * s), (x + s, y + 2 * s), (x + s, y + s), (x + 2 * s, y + s),
    ])


def pixels(rows, x, y, cell, fill, extra=""):
    """Draw a pixel icon from strings of '#' and '.'."""
    rects = "".join(
        f'<rect x="{x + c * cell:.1f}" y="{y + r * cell:.1f}" width="{cell}" height="{cell}"/>'
        for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "#"
    )
    return f'<g fill="{fill}"{extra}>{rects}</g>'


class Card:
    def __init__(self, w, h, label, left=0.0, right=0.0, bottom=GAP):
        self.w, self.h, self.label = w, h, label
        self.left, self.right, self.bottom = left, right, bottom
        self.parts, self.css, self.defs, self.faces = [], [], [], []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, face, size, fill, anchor=None, extra=""):
        f = F[face]
        if face not in self.faces:
            self.faces.append(face)
        a = f' text-anchor="{anchor}"' if anchor else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="\'{f.family}\', ui-monospace, monospace" '
            f'font-weight="{f.weight}" font-size="{size}" fill="{fill}"{a}{extra}>{escape(s)}</text>'
        )

    def frame(self, fill=PANEL, step=4, border=3):
        """Pixel window: a border in EDGE around a body in `fill`. Returns the body outline."""
        self.add(f'<path d="{notched(0, 0, self.w, self.h, step)}" fill="{EDGE}"/>')
        inner = notched(border, border, self.w - 2 * border, self.h - 2 * border, step - 1)
        self.add(f'<path d="{inner}" fill="{fill}"/>')
        return inner

    def svg(self):
        unique = {(F[k].family, F[k].weight): F[k] for k in self.faces}
        fonts = "".join(
            f"@font-face{{font-family:'{f.family}';font-style:normal;font-weight:{f.weight};"
            f"src:url(data:font/woff2;base64,{f.b64}) format('woff2')}}"
            for f in unique.values()
        )
        css = fonts + BASE_CSS + "".join(self.css) + (STATIC_CSS if STATIC else "")
        defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
        body = "".join(self.parts)
        if self.left:
            body = f'<g transform="translate({self.left:.3f} 0)">{body}</g>'
        tw, th = self.w + self.left + self.right, self.h + self.bottom
        label = escape(self.label)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw:.3f}" height="{th:.0f}" '
            f'viewBox="0 0 {tw:.3f} {th:.0f}" role="img" aria-label="{label}">'
            f"<title>{label}</title><style>{css}</style>{defs}{body}</svg>"
        )


def third(i):
    """Width and side padding for card i in a row of three, so the gaps match GAP."""
    w = THIRD - 2 * GAP / 3
    left = [0, GAP / 3, 2 * GAP / 3][i]
    return w, left, THIRD - w - left


NAMES = {}


def save(name, card):
    """Write a card under a content-hashed name. GitHub's raw CDN caches each URL for a few
    minutes and drops query strings, so a new name is the only way changes show up at once."""
    svg = card.svg()
    stem = name.removesuffix(".svg")
    NAMES[stem] = f"{stem}-{hashlib.sha1(svg.encode()).hexdigest()[:8]}.svg"
    (CARDS / NAMES[stem]).write_text(svg, encoding="utf-8")


def sky(card, clip, colors, height=None):
    """Banded night sky, dithered where bands meet, clipped to the card body."""
    w, h = card.w, height or card.h
    card.defs.append(f'<clipPath id="body"><path d="{clip}"/></clipPath>')
    band = 2 * round(h / len(colors) / 2)
    parts = []
    for i, c in enumerate(colors):
        top = i * band
        height = h - top if i == len(colors) - 1 else band
        parts.append(f'<rect x="0" y="{top}" width="{w:.1f}" height="{height}" fill="{c}"/>')
    for i in range(1, len(colors)):
        card.defs.append(
            f'<pattern id="dither{i}" width="4" height="4" patternUnits="userSpaceOnUse">'
            f'<rect width="2" height="2" fill="{colors[i]}"/><rect x="2" y="2" width="2" height="2" fill="{colors[i]}"/></pattern>'
        )
        parts.append(f'<rect x="0" y="{i * band - 6}" width="{w:.1f}" height="6" fill="url(#dither{i})"/>')
    card.add(f'<g clip-path="url(#body)">{"".join(parts)}</g>')


def stars(card, n, seed, avoid, bottom=None):
    rng = random.Random(seed)
    placed, tries = [], 0
    while len(placed) < n and tries < 4000:
        tries += 1
        x, y = rng.randrange(14, int(card.w) - 14, 2), rng.randrange(12, int(bottom or card.h) - 12, 2)
        if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in avoid):
            continue
        if any(abs(x - px) < 18 and abs(y - py) < 18 for px, py in placed):
            continue
        placed.append((x, y))
    out = []
    for i, (x, y) in enumerate(placed):
        color = TEXT if i % 3 else LAVENDER
        twinkle = f' class="tw" style="animation-delay:{(i * 0.37) % 3.2:.2f}s"' if i % 4 == 0 else ""
        if i % 7 == 0:  # a few bigger stars, drawn as a small plus
            out.append(pixels([".#.", "###", ".#."], x - 2, y - 2, 2, color, twinkle))
        else:
            out.append(f'<rect x="{x}" y="{y}" width="2" height="2" fill="{color}"{twinkle}/>')
    card.add("".join(out))


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


def weeks():
    """Days grouped into Sunday-first weeks: [[(weekday, date, count), ...], ...]."""
    first_sunday = DAYS[0][0] - dt.timedelta(days=(DAYS[0][0].weekday() + 1) % 7)
    out = defaultdict(list)
    for d, c in DAYS:
        out[(d - first_sunday).days // 7].append(((d.weekday() + 1) % 7, d, c))
    return [out[k] for k in sorted(out)]


# ---------------------------------------------------------------- hero ------

def portrait_cells(rows):
    im = Image.open(ROOT / "assets" / "avatar.png").convert("RGBA")
    im = im.crop(im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox())
    w, h = im.size
    step = h / rows
    cols = round(w / step)
    flat = Image.new("RGB", im.size, (20, 18, 42))
    flat.paste(im, mask=im.getchannel("A"))
    q = flat.quantize(colors=16, method=Image.Quantize.MAXCOVERAGE, kmeans=3, dither=Image.Dither.NONE)
    pal, qp, ap = q.getpalette(), q.load(), im.getchannel("A").load()
    cells = {}
    for r in range(rows):
        y0, y1 = int(r * step), min(h, int((r + 1) * step))
        for c in range(cols):
            x0, x1 = int(c * step), min(w, int((c + 1) * step))
            # vote over the middle of each block only, so neighbouring pixels don't bleed in
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
                cells[(r, c)] = "#%02x%02x%02x" % tuple(pal[idx * 3: idx * 3 + 3])
    return cells, cols


def sprite(card, cells, ox, oy, pitch):
    """The avatar as a sprite with a one-pixel violet outline, like a selected character."""
    cells = dict(cells)
    outline = {
        (r + dr, c + dc)
        for (r, c) in cells
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
    } - set(cells)
    for (r, c) in outline:
        cells[(r, c)] = VIOLET
    out = []
    for r in sorted({r for r, _ in cells}):
        row = sorted((c, col) for (rr, c), col in cells.items() if rr == r)
        i = 0
        while i < len(row):  # merge runs of one colour into a single rect
            c0, col = row[i]
            j = i
            while j + 1 < len(row) and row[j + 1] == (row[j][0] + 1, col):
                j += 1
            out.append(f'<rect x="{ox + c0 * pitch}" y="{oy + r * pitch}" width="{(j - i + 1) * pitch}" height="{pitch}" fill="{col}"/>')
            i = j + 1
    card.add(f'<g clip-path="url(#body)">{"".join(out)}</g>')


def hero():
    p = PROFILE
    h = 340
    card = Card(W, h, f'{p["name"]}. {p["role"]}. {p["tagline"]}')
    body = card.frame()
    sky(card, body, SKY[:4])

    rows, pitch = 60, 5
    cells, cols = portrait_cells(rows)
    ox, oy = W - 48 - cols * pitch, h - 3 - rows * pitch
    stars(card, 34, 11, avoid=[(24, 30, 520, 320), (ox - 16, oy - 16, W, h)])
    sprite(card, cells, ox, oy, pitch)

    x = 40
    card.text(x, 72, p["role"], "px-med", 17, LAVENDER)
    size = 88
    while F["px-bold"].width(p["name"], size) > 450:
        size -= 2
    card.text(x + 5, 160 + 5, p["name"], "px-bold", size, VIOLET)
    card.text(x, 160, p["name"], "px-bold", size, TEXT)

    tag = wrap(p["tagline"], "px", 18, 440)
    for i, line in enumerate(tag):
        card.text(x, 210 + i * 27, line, "px", 18, TEXT_SOFT)

    y = 210 + len(tag) * 27 + 22
    arrow = ["#...", "##..", "###.", "##..", "#..."]
    card.add(pixels(arrow, x, y - 12, 2, MUSTARD, ' class="cur"'))
    card.text(x + 16, y, p["website"]["label"], "px-med", 16, MUSTARD)
    save("hero.svg", card)


# ------------------------------------------------------------- skyline ------

def skyline():
    level = levels()
    wk = weeks()
    totals = [sum(c for *_, c in w) for w in wk]
    peak = max(range(len(wk)), key=lambda i: totals[i])
    h = 300
    ground = h - 42
    card = Card(
        W, h,
        f"Contributions over the last year drawn as a city: one building per week, taller for busier weeks, "
        f"and one lit window for each day with contributions. Busiest week: {totals[peak]} contributions.",
    )
    body = card.frame()
    sky(card, body, NIGHT, height=ground)
    stars(card, 46, 5, avoid=[(0, 0, 580, 80), (620, 0, W, 60)], bottom=ground - 24)

    # a far-off row of dark towers without windows, for depth
    rng, far, fx = random.Random(3), [], 4
    while fx < W:
        fw, fh = rng.randrange(14, 34, 2), rng.randrange(20, 92, 2)
        far.append(f'<rect x="{fx}" y="{ground - fh}" width="{fw}" height="{fh}"/>')
        fx += fw + rng.choice([0, 0, 2, 6])
    card.add(f'<g clip-path="url(#body)" fill="{FAR}">{"".join(far)}</g>')

    card.text(28, 46, "A year of commits, one building per week", "px-semi", 20, TEXT)
    card.add(f'<rect x="29" y="61" width="7" height="6" fill="{WINDOW_ON[3]}"/>')
    card.text(44, 68, "lit window = a day with contributions", "px", 14, MUTED)
    card.text(W - 28, 46, f"Updated {fmt_date(LAST)}", "num", 19, MUTED, anchor="end")

    x0, span = 26, W - 52
    pitch = span / len(wk)
    bw = 12
    peak_total = totals[peak] or 1
    buildings, lights = [], []
    for i, days in enumerate(wk):
        bh = 58 + 2 * round(totals[i] / peak_total * 62)
        bx = x0 + i * pitch + (pitch - bw) / 2
        by = ground - bh
        buildings.append(f'<rect x="{bx:.1f}" y="{by}" width="{bw}" height="{bh}" fill="{BUILDINGS[(i * 2 + i // 3) % 3]}"/>')
        if i % 5 == 2:  # a little rooftop box here and there
            buildings.append(f'<rect x="{bx + 3:.1f}" y="{by - 4}" width="5" height="4" fill="{BUILDINGS[(i + 1) % 3]}"/>')
        windows = []
        for weekday, _, c in days:
            wy = by + 6 + weekday * 7
            fill = WINDOW_ON[level(c)] if c else WINDOW_OFF
            (windows if c else buildings).append(f'<rect x="{bx + 3.5:.1f}" y="{wy}" width="5" height="4" fill="{fill}"/>')
        if windows:
            lights.append(f'<g class="in" style="animation-delay:{0.2 + i * 0.03:.2f}s">{"".join(windows)}</g>')
        if i == peak:
            buildings.append(f'<rect x="{bx + 5.5:.1f}" y="{by - 14}" width="1" height="14" fill="{MUTED}"/>')
            lights.append(f'<rect class="cur" x="{bx + 5:.1f}" y="{by - 17}" width="2" height="3" fill="{RED}"/>')
    card.add(f'<g clip-path="url(#body)">{"".join(buildings)}{"".join(lights)}'
             f'<rect x="0" y="{ground}" width="{W}" height="{h - ground}" fill="{INSET}"/>'
             f'<rect x="0" y="{ground}" width="{W}" height="2" fill="{EDGE}"/></g>')

    last_label = -10
    for i, days in enumerate(wk):
        firsts = [d for _, d, _ in days if d.day == 1]
        if firsts and i - last_label >= 3:
            card.text(x0 + i * pitch + 2, ground + 26, f"{firsts[0]:%b}", "px", 13, MUTED)
            last_label = i
    save("skyline.svg", card)


# --------------------------------------------------------------- stats ------

ICONS = {
    "coin": [
        "...####...", ".########.", ".###..###.", "###.##.###", "###.##.###",
        "###.##.###", "###.##.###", ".###..###.", ".########.", "...####...",
    ],
    "flame": [
        "....#.....", "....##....", "...###....", "...####.#.", "..#######.",
        ".####.###.", ".###...##.", ".###...##.", "..##..##..", "...####...",
    ],
    "calendar": [
        ".##....##.", "##########", "##########", "#........#", "#.#.#.#..#",
        "#........#", "#.#.#.#..#", "#........#", "##########", "..........",
    ],
    "trophy": [
        "##########", "#.######.#", "#.######.#", ".#.####.#.", "...####...",
        "....##....", "....##....", "...####...", "..######..", "..........",
    ],
    "briefcase": [
        "..........", "...####...", "...#..#...", "##########", "##########",
        "##########", "####..####", "##########", "##########", "..........",
    ],
    "rocket": [
        "....##....", "...####...", "...#..#...", "...#..#...", "...####...",
        "..######..", ".##.##.##.", ".#..##..#.", "....##....", "...#..#...",
    ],
    "stack": [
        "..........", "...####...", "...####...", "..........", ".########.",
        ".########.", "..........", "##########", "##########", "..........",
    ],
}


def stats():
    total = CONTRIB["total"]
    current, longest = streaks()
    active = sum(1 for _, c in DAYS if c)
    busiest_day, busiest = max(DAYS, key=lambda dc: dc[1])
    items = [
        ("coin", MUSTARD, f"{total:,}", "contributions in a year"),
        ("flame", ORANGE, f"{current} day" + ("" if current == 1 else "s"), f"streak now, best is {longest}"),
        ("calendar", LAVENDER, f"{active}/{len(DAYS)}", "days I contributed"),
        ("trophy", GREEN, f"{busiest}", f"busiest day, {fmt_date(busiest_day)}"),
    ]
    h = 120
    card = Card(
        W, h,
        f"{total:,} contributions in the last year. Current streak {current} days, longest {longest}. "
        f"{active} of {len(DAYS)} days with a contribution. Busiest day: {busiest} on {fmt_date(busiest_day)}.",
    )
    card.frame()
    cw = (W - 48) / 4
    for i, (icon, color, big, label) in enumerate(items):
        x = 24 + i * cw + 12
        card.add(pixels(ICONS[icon], x, 30, 3, color))
        card.text(x + 44, 60, big, "num", 44, TEXT)
        card.text(x, 93, label, "num", 19, MUTED)
        if i:
            dots = "".join(f'<rect x="{24 + i * cw - 6:.1f}" y="{y}" width="2" height="2"/>' for y in range(26, h - 22, 6))
            card.add(f'<g fill="{EDGE}">{dots}</g>')
    save("stats.svg", card)


# --------------------------------------------------- now / stack panels ------

def tile(tid):
    return next(t for t in PROFILE["tiles"] if t["id"] == tid)


HALF = W / 2 - GAP / 2   # card width in the half-and-half row


def language_shares():
    """Top languages by bytes of code across my public repos, from data/languages.json."""
    cfg = tile("stack")["languages"]
    langs = [(n, v) for n, v in LANGS.items() if n not in set(cfg["exclude"])]
    total = sum(v["bytes"] for _, v in langs) or 1
    return [(n, v["color"] or MUTED, v["bytes"] / total, v["repos"]) for n, v in langs[: cfg["top"]]]


def now_layout():
    entries = [tile("work"), tile("ship")]
    out, y = [], 30
    for t in entries:
        lines = wrap(t["text"], "px", 17, HALF - 70 - 28)
        out.append((t, y, lines))
        y += 50 + len(lines) * 23 + 22
    return out, y - 22 + 26


def stack_layout():
    t = tile("stack")
    rows, y = [], 0
    x, y = 24, 0
    for name in t["tools"]:
        cw = F["px"].width(name, 13) + 20
        if x + cw > HALF - 24:
            x, y = 24, y + 28
        rows.append((name, x, y, cw))
        x += cw + 6
    tools_top = 92 + (len(language_shares()) - 1) * 40 + 50
    return rows, tools_top, tools_top + 12 + y + 22 + 24


def row_height():
    return max(now_layout()[1], stack_layout()[2])


def now_panel():
    entries, _ = now_layout()
    card = Card(HALF, row_height(), " ".join(f'{t["label"]}: {t["text"]}' for t, _, _ in entries), right=GAP / 2)
    card.frame()
    for t, y, lines in entries:
        color = ACCENTS[t["color"]]
        card.add(pixels(ICONS[t["icon"]], 26, y, 3, color))
        card.text(70, y + 22, t["label"], "px-semi", 20, color)
        for k, line in enumerate(lines):
            card.text(70, y + 50 + k * 23, line, "px", 17, TEXT_SOFT)
    save("now.svg", card)


def stack_alt():
    langs = ", ".join(f"{n} {share * 100:.0f}%" for n, _, share, _ in language_shares())
    return f"Stack. Code in my public repos: {langs}. Tools: {', '.join(tile('stack')['tools'])}."


def stack_panel():
    t = tile("stack")
    w = HALF
    chips, tools_top, _ = stack_layout()
    card = Card(w, row_height(), stack_alt(), left=GAP / 2)
    card.frame()
    color = ACCENTS[t["color"]]
    card.add(pixels(ICONS[t["icon"]], 24, 30, 3, color))
    card.text(68, 52, t["label"], "px-semi", 20, color)
    card.text(w - 24, 52, "code in my public repos", "px", 13, MUTED, anchor="end")

    segments = 20
    seg_w = (w - 48 - (segments - 1) * 2) / segments
    for k, (name, lcolor, share, repos) in enumerate(language_shares()):
        y = 92 + k * 40
        card.add(f'<rect x="24" y="{y - 9}" width="8" height="8" fill="{lcolor}"/>')
        card.text(38, y, name, "px-med", 15, TEXT)
        pct = "<1%" if share < 0.01 else f"{share * 100:.0f}%"
        card.text(w - 24, y + 2, pct, "num", 24, TEXT, anchor="end")
        note = f"{repos} repo" + ("" if repos == 1 else "s")
        card.text(w - 24 - F["num"].width(pct, 24) - 10, y, note, "px", 12, MUTED, anchor="end")
        filled = max(1, round(share * segments))
        bar = "".join(
            f'<rect x="{24 + s * (seg_w + 2):.1f}" y="{y + 8}" width="{seg_w:.1f}" height="6" fill="{lcolor if s < filled else INSET}"/>'
            for s in range(segments)
        )
        card.add(f'<g class="in" style="animation-delay:{0.2 + k * 0.15:.2f}s">{bar}</g>')

    card.text(24, tools_top, "Tools", "px-med", 14, MUTED)
    for name, x, y, cw in chips:
        top = tools_top + 12 + y
        card.add(f'<path d="{notched(x, top, cw, 22, 2)}" fill="{INSET}"/>')
        card.text(x + 10, top + 15.5, name, "px", 13, TEXT)
    save("stack.svg", card)


# -------------------------------------------------------------- footer ------

LINK_ICONS = {
    "globe": [
        "...####...", ".##.##.##.", ".#..##..#.", "##########", "#...##...#",
        "#...##...#", "##########", ".#..##..#.", ".##.##.##.", "...####...",
    ],
    "card": [
        "..........", "##########", "#........#", "#.##.....#", "#.##.###.#",
        "#........#", "#.##.###.#", "#........#", "##########", "..........",
    ],
}


def link_button(link, i):
    w, left, right = third(i)
    h = 64
    card = Card(w, h, f'{link["label"]}: {link["detail"]}', left=left, right=right, bottom=0)
    card.frame()
    icon = LINK_ICONS.get(link["icon"]) or ICONS[link["icon"]]
    card.add(pixels(icon, 18, 17, 3, LAVENDER))
    card.text(60, 30, link["label"], "px-semi", 17, TEXT)
    size = 12
    while F["px"].width(link["detail"], size) > w - 60 - 40 and size > 9:
        size -= 0.5
    card.text(60, 48, link["detail"], "px", size, MUTED)
    arrow = ["#...", "##..", "###.", "##..", "#..."]
    card.add(pixels(arrow, w - 28, 22, 2, MUSTARD))
    save(f"link-{i}.svg", card)


# ------------------------------------------------------------ timeline ------

CAP = [
    "..........", "....##....", "..######..", "##########", "..######.#",
    "..#....#.#", "..######.#", ".........#", "..........", "..........",
]
DOWN = ["#######", ".#####.", "..###..", "...#..."]


def timeline_alt():
    return "My timeline. " + " ".join(f'{s["when"]}: {s["title"]}, {s["detail"]}.' for s in PROFILE["timeline"])


def timeline():
    """A level map: each stage of school and work is a node on a winding dotted path."""
    stages = PROFILE["timeline"]
    n = len(stages)
    h = 244
    card = Card(W, h, timeline_alt())
    card.frame()
    card.text(28, 46, "The road so far", "px-semi", 20, TEXT)

    xs = [96 + i * (W - 192) / (n - 1) for i in range(n)]
    ys = [128 if i % 2 == 0 else 104 for i in range(n)]

    # dotted path, drawn left to right like walking the map
    dots, t, reach = [], 0.2, [0.15]
    for i in range(n - 1):
        mid = (xs[i] + xs[i + 1]) / 2
        legs = [((xs[i], ys[i]), (mid, ys[i])), ((mid, ys[i]), (mid, ys[i + 1])), ((mid, ys[i + 1]), (xs[i + 1], ys[i + 1]))]
        color = VIOLET if i == n - 2 else LAVENDER
        for (x0, y0), (x1, y1) in legs:
            length = abs(x1 - x0) + abs(y1 - y0)
            for k in range(0, int(length), 8):
                f = k / length if length else 0
                x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
                if min(abs(x - xs[i]) + abs(y - ys[i]), abs(x - xs[i + 1]) + abs(y - ys[i + 1])) < 24:
                    continue
                dots.append(f'<rect class="in" style="animation-delay:{t:.2f}s" x="{x - 2:.1f}" y="{y - 2:.1f}" width="4" height="4" fill="{color}"/>')
                t += 0.012
        reach.append(t)
    card.add("".join(dots))

    for i, (s, x, y) in enumerate(zip(stages, xs, ys)):
        current = s.get("current", False)
        icon = CAP if s["kind"] == "school" else ICONS["briefcase"]
        body, ink = (VIOLET, TEXT) if current else (INSET, MUSTARD if s["kind"] == "school" else GREEN)
        node = (
            f'<path d="{notched(x - 18, y - 18, 36, 36, 4)}" fill="{EDGE}"/>'
            f'<path d="{notched(x - 15, y - 15, 30, 30, 3)}" fill="{body}"/>'
            + pixels(icon, x - 10, y - 10, 2, ink)
        )
        card.add(f'<g class="in" style="animation-delay:{reach[i]:.2f}s">{node}</g>')
        if current:
            card.add(pixels(DOWN, x - 10.5, y - 40, 3, MUSTARD, ' class="cur"'))

        card.text(x, 174, s["when"], "num", 18, MUTED, anchor="middle")
        size = 17
        while F["px-semi"].width(s["title"], size) > 160 and size > 12:
            size -= 0.5
        card.text(x, 196, s["title"], "px-semi", size, LAVENDER if current else TEXT, anchor="middle")
        size = 13
        while F["px"].width(s["detail"], size) > 160 and size > 10:
            size -= 0.5
        card.text(x, 216, s["detail"], "px", size, TEXT_SOFT, anchor="middle")
    save("timeline.svg", card)


# --------------------------------------------------------------- repos ------

def title(text, slug):
    # Sits on GitHub's own background, light or dark; this violet reads on both.
    card = Card(W, 60, text, bottom=4)
    card.text(2, 44, text, "px-bold", 30, VIOLET)
    save(f"title-{slug}.svg", card)


def repo_language(r, meta):
    want = r.get("language")
    if want:
        for lang in meta["languages"]:
            if lang["name"] == want:
                return lang
        return {"name": want, "color": MUTED}
    return meta["language"] or {"name": "", "color": MUTED}


def cartridge(w, h):
    """Outline of a game cartridge: stepped top-right corner, small notches elsewhere."""
    return path([
        (8, 0), (w - 30, 0), (w - 30, 6), (w - 24, 6), (w - 24, 12), (w - 18, 12), (w - 18, 18),
        (w - 12, 18), (w - 12, 24), (w - 6, 24), (w - 6, 30), (w, 30), (w, h - 8), (w - 4, h - 8),
        (w - 4, h - 4), (w - 8, h - 4), (w - 8, h), (8, h), (8, h - 4), (4, h - 4), (4, h - 8),
        (0, h - 8), (0, 8), (4, 8), (4, 4), (8, 4),
    ])


def repo_card(r, i):
    meta = REPOS[r["name"]]
    w, left, right = third(i)
    h = 244
    accent = [VIOLET, GREEN, MUSTARD][i % 3]
    card = Card(w, h, f'{r["name"]}: {r["description"]}', left=left, right=right)
    card.add(f'<path d="{cartridge(w, h)}" fill="{CART}"/>')

    lang = repo_language(r, meta)
    if lang["name"]:
        card.add(f'<rect x="16" y="15" width="8" height="8" fill="{lang["color"] or MUTED}"/>')
        card.text(30, 23, lang["name"], "px", 13, TEXT_SOFT)

    lx, ly, lw, lh = 12, 36, w - 24, h - 36 - 44
    card.add(f'<path d="{notched(lx, ly, lw, lh, 3)}" fill="{PANEL}"/>')
    card.add(f'<path d="{notched(lx, ly, lw, 38, 3)}" fill="{accent}"/><rect x="{lx}" y="{ly + 30}" width="{lw:.1f}" height="8" fill="{accent}"/>')
    size = 18
    while F["px-semi"].width(r["name"], size) > lw - 24 and size > 12:
        size -= 0.5
    card.text(lx + 12, ly + 25, r["name"], "px-semi", size, PANEL)
    for k, line in enumerate(wrap(r["description"], "px", 15, lw - 24)[:5]):
        card.text(lx + 12, ly + 62 + k * 20, line, "px", 15, TEXT_SOFT)

    ridges = "".join(f'<rect x="{18 + k * 7}" y="{h - 34}" width="3" height="20"/>' for k in range(7))
    card.add(f'<g fill="{CART_DARK}">{ridges}</g>')
    if meta["homepage"]:
        lw_ = F["px-med"].width("Live site", 13)
        card.add(f'<rect class="cur" x="{w - 16 - lw_ - 13:.1f}" y="{h - 27}" width="7" height="7" fill="{GREEN}"/>')
        card.text(w - 16, h - 20, "Live site", "px-med", 13, GREEN, anchor="end")
    elif meta["stars"]:
        card.text(w - 16, h - 20, f'{meta["stars"]} star' + ("" if meta["stars"] == 1 else "s"), "px", 13, MUTED, anchor="end")
    save(f'repo-{r["name"].lower()}.svg', card)


# -------------------------------------------------------------- README ------

def readme():
    p = PROFILE
    a = lambda s: escape(s, quote=True)
    current, longest = streaks()
    src = lambda stem: f"./cards/{NAMES[stem]}"
    work, ship, stack = tile("work"), tile("ship"), tile("stack")
    repos = "".join(
        f'<a href="{a(REPOS[r["name"]]["url"])}"><img src="{src("repo-" + r["name"].lower())}" width="33.333%" alt="{a(r["name"] + ": " + r["description"])}" /></a>'
        for r in p["repos"]
    )
    links = "".join(
        f'<a href="{a(l["url"])}"><img src="{src(f"link-{i}")}" width="33.333%" alt="{a(l["label"] + ": " + l["detail"])}" /></a>'
        for i, l in enumerate(p["links"][:3])
    )
    text = f"""<!-- Generated by scripts/render_cards.py. Edit profile.json, not this file.
     The cards are animated SVGs, refreshed every day by .github/workflows/refresh-cards.yml.
     File names carry a content hash so GitHub's image cache never shows an old card.
     Keep this block free of blank lines and each row of cards on one line: the gaps are inside the SVGs. -->
<div align="center">
<a href="{a(p["website"]["url"])}"><img src="{src("hero")}" width="100%" alt="{a(p["name"] + ". " + p["role"] + ". " + p["tagline"])}" /></a><br>
<img src="{src("skyline")}" width="100%" alt="Contributions over the last year drawn as a city: one building per week, one lit window per day with contributions" /><br>
<img src="{src("stats")}" width="100%" alt="{a(f"{CONTRIB['total']:,} contributions in the last year. Current streak {current} days, longest {longest}.")}" /><br>
<a href="{a(work["url"])}"><img src="{src("now")}" width="50%" alt="{a(work["label"] + ": " + work["text"] + " " + ship["label"] + ": " + ship["text"])}" /></a><a href="{a(stack["url"])}"><img src="{src("stack")}" width="50%" alt="{a(stack_alt())}" /></a><br>
<img src="{src("timeline")}" width="100%" alt="{a(timeline_alt())}" /><br>
<img src="{src("title-built")}" width="100%" alt="Things I've built" /><br>
{repos}<br>
{links}
</div>
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")


def main():
    CARDS.mkdir(exist_ok=True)
    for old in CARDS.glob("*.svg"):
        old.unlink()
    hero()
    skyline()
    stats()
    now_panel()
    stack_panel()
    timeline()
    title("Things I've built", "built")
    for i, r in enumerate(PROFILE["repos"]):
        repo_card(r, i)
    for i, link in enumerate(PROFILE["links"][:3]):
        link_button(link, i)
    readme()
    sizes = sorted((f.stat().st_size // 1024, f.name) for f in CARDS.glob("*.svg"))
    print("  ".join(f"{n} {kb}KB" for kb, n in sizes))


if __name__ == "__main__":
    main()
