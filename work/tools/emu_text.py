#!/usr/bin/env python3
"""emu_text - read back the text a screen shows, with the ROM's own font (for the emu_* sweeps).

The game draws text with 2bpp glyphs from the font NARC a/0/1/6 (value 1 = text colour, 2 = shadow,
3 = window background, 0 = transparent) at a fixed origin, one 16-px row per line, advancing by the
width-table byte (letterSpacing 0, text_metrics.md section 1). So a line on screen can be decoded
exactly: take the 'ink' mask of the window (every pixel that is not the window background), and parse
it column by column into glyphs of the same font (exact match of every column of the glyph's advance).
No guessing is involved, so a decoded line is what the game printed:

- the text itself (compare it with the bank string: garble, a wrong string, a wrong buffer);
- the last ink column (the rendered width), and whether ink reaches the window's clip edge;
- columns that match no glyph (garbage tiles, overlapping text) come out as U+FFFD.

Only the English ROM's fonts are decoded (charmap_en.tsv; codes up to 0x1FF: Latin, digits,
punctuation, symbols). Chinese lines are captured for the CN|EN pairs but not decoded.

    import emu_text as T
    f = T.font(rom, 1)                                   # message font of that ROM (cached)
    lines = T.read_lines(img, T.BOXES["battle"], f)      # [{'text', 'right', 'clipped', 'unknown'}]
    T.expected_text(en, buffers)                         # bank string -> page/line structure
"""
import json
import re
from functools import lru_cache
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CHARMAP_EN = TOOLS / "charmap_en.tsv"
UNKNOWN = "\ufffd"
LINE_H = 16
ROWMASK = 0x7FFE        # glyph rows 1-14: rows 0 and 15 can hold a ruled line of a panel (summary pages);
                        # only accents of capitals (À, É, ...) reach row 0

# Text windows measured on the English build (screenshots in the harness output). x0/y0: where the game
# prints glyph column 0 / row 0 of line 1; width: the window's pixel width (text beyond it is not drawn);
# lines: rows per view; bg: the window background colour; screen: 'top' or 'bottom' (+192 in y).
BOXES = {
    # battle message window: ov12 AddWindow(bg1, 2, 19, 27, 4) -> x 16, y 152, 216 x 32 px (top screen)
    "battle": {"x0": 16, "y0": 152, "width": 216, "lines": 2, "font": 1, "bg": (248, 248, 248)},
}


# ----------------------------------------------------------------------------- font
def _charmap():
    dec = {}
    for line in CHARMAP_EN.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "\t" not in line:
            continue
        code, text = line.split("\t", 1)
        try:
            c = int(code, 16)
        except ValueError:
            continue
        if len(text) == 1 and c <= 0x1FF and c not in dec:
            dec[c] = text
    return dec


class Font:
    """Ink columns of every decodable glyph of one font of one ROM. cols: tuple of 16-bit row masks."""

    def __init__(self, rom_path, font_id):
        import msgtool as m
        rom = m.load_rom(str(rom_path))
        data = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH)).files[font_id]
        self.glyphs = {}            # code -> (char, width, cols)
        seen = {}
        # identical bitmaps (O and ●, ...): keep ASCII letters/digits first, then the Latin block (high codes)
        for code, ch in sorted(_charmap().items(), key=lambda kv: (not (kv[1].isascii() and kv[1].isalnum()),
                                                                   -kv[0])):
            pix, w = m.render_glyph(data, code)
            if not w or w > 16:
                continue
            cols = tuple(sum(1 << y for y in range(LINE_H) if pix[y][x] in (1, 2)) & ROWMASK for x in range(w))
            if (w, cols) in seen and ch != " ":
                continue
            if not any(cols) and ch != " ":        # blank glyphs (U+3000 etc.): gaps decode as spaces only
                continue
            seen[(w, cols)] = code
            self.glyphs[code] = (ch, w, cols)
        self.space = next((g for g in self.glyphs.values() if g[0] == " "), None)
        self.index = {}
        for code, (ch, w, cols) in self.glyphs.items():
            self.index.setdefault(cols[0], []).append((ch, w, cols))
        for k in self.index:        # longest first; the space last among equals
            self.index[k].sort(key=lambda g: (-g[1], g[0] == " "))

    def width(self, text):
        by_char = {}
        for ch, w, _ in self.glyphs.values():
            by_char.setdefault(ch, w)
        return sum(by_char.get(c, 0) for c in text)


@lru_cache(maxsize=None)
def font(rom_path, font_id=1):
    return Font(rom_path, font_id)


# ----------------------------------------------------------------------------- reading a screen
def band_bg(img, x0, y0, width):
    """The most common colour of a 16-px text band (the window background behind that line)."""
    from collections import Counter
    img = img.convert("RGB")
    c = Counter(img.crop((x0, y0, x0 + width, y0 + LINE_H)).getdata())
    return c.most_common(1)[0][0]


def ink_columns(img, x0, y0, width, bg, extra=8):
    """Column masks (rows 1-14 of the 16 from y0) for x0 .. x0+width+extra-1; ink = any colour but bg
    (bg None: the band's most common colour)."""
    img = img.convert("RGB")
    if bg is None:
        bg = band_bg(img, x0, y0, width)
    W, H = img.size
    px = img.load()
    cols = []
    for x in range(x0, x0 + width + extra):
        m = 0
        if 0 <= x < W:
            for y in range(LINE_H):
                if 0 <= y0 + y < H and px[x, y0 + y] != bg:
                    m |= 1 << y
        cols.append(m & ROWMASK)
    return cols


def parse_line(cols, f, limit=None):
    """Decode column masks into text. Exact glyph matches only; a column that starts no parse becomes U+FFFD
    (and is skipped). Returns (text, last ink column + 1, unknown count)."""
    limit = len(cols) if limit is None else limit
    end = max((i + 1 for i in range(limit) if cols[i]), default=0)
    if end == 0:
        return "", 0, 0
    memo = {}

    def fits(x, gcols):
        for i, c in enumerate(gcols):
            have = cols[x + i] if x + i < len(cols) else 0
            if have != c:
                return False
        return True

    def go(x):
        """(farthest column reached, text) of the best parse from x (exact glyph matches)."""
        if x >= end:
            return x, ""
        if x in memo:
            return memo[x]
        best = (x, "")
        for ch, w, gcols in f.index.get(cols[x], ()):
            if fits(x, gcols):
                r = go(x + w)
                if r[0] > best[0]:
                    best = (r[0], ch + r[1])
                    if best[0] >= end:
                        break
        memo[x] = best
        return best

    out, x, unknown = [], 0, 0
    while x < end:
        reach, text = go(x)
        out.append(text)
        if reach >= end:
            break
        x = reach
        if cols[x]:                       # no glyph starts here: unknown pixels; resync at the next column
            out.append(UNKNOWN)
            unknown += 1
            x += 1
            while x < end and go(x)[0] == x and cols[x]:
                x += 1
        else:
            x += 1
    text = "".join(out)
    return text.strip(" "), end, unknown


def read_lines(img, box, f, y_offset=0):
    """Decode every line of a text window. Returns [{'text', 'right', 'clipped', 'unknown'}] where right is
    the rendered width in px from x0 and clipped is True when ink reaches the window's last column."""
    rows = []
    for k in range(box["lines"]):
        y = box["y0"] + y_offset + box.get("pitch", LINE_H) * k
        cols = ink_columns(img, box["x0"], y, box["width"], tuple(box["bg"]) if box.get("bg") else None, extra=0)
        text, right, unknown = parse_line(cols, f)
        rows.append({"text": text, "right": right, "clipped": bool(cols and cols[-1]), "unknown": unknown})
    return rows


# ----------------------------------------------------------------------------- expected text
TAG = re.compile(r"\{[^}]*\}")


def expected_lines(en, buffers=None):
    """A bank string -> list of pages, each a list of line texts, with {VAR:01KK:i,..} replaced from
    buffers {i: text} (missing buffers stay as None markers: the line is then compared as a pattern).
    {NEWLINE} = next line, {SCROLL} = new page, {CLEAR} = scroll one line (treated as a new line);
    other control tags (colours, sizes, pauses) print nothing."""
    buffers = buffers or {}
    pages, line = [[]], ""
    for tok in re.split(r"(\{[^}]*\})", en or ""):
        if not tok:
            continue
        if tok == "{NEWLINE}" or tok == "{CLEAR}":
            pages[-1].append(line)
            line = ""
        elif tok == "{SCROLL}":
            pages[-1].append(line)
            pages.append([])
            line = ""
        elif tok.startswith("{VAR:01"):
            idx = int(tok.rstrip("}").split(":")[2].split(",")[0])
            line += buffers[idx] if idx in buffers else "\x00"
        elif tok.startswith("{"):
            continue
        else:
            line += tok
    pages[-1].append(line)
    return [[l.strip(" ") for l in p] for p in pages if any(x.strip() for x in p)]


def line_matches(expected, got):
    """expected may hold \\x00 for an unknown buffer (any text)."""
    if "\x00" not in expected:
        return expected == got
    pat = "^" + ".+?".join(re.escape(p) for p in expected.split("\x00")) + "$"
    return re.match(pat, got) is not None


def flat(pages):
    return [l for p in pages for l in p if l != ""]


def compare(expected_pages, shown_lines):
    """Compare the expected lines (all pages, in order) with the decoded lines of the captured pages
    (consecutive duplicates from {CLEAR} scrolling removed). Returns (ok, details)."""
    want = flat(expected_pages)
    got = []
    for l in shown_lines:
        if l and (not got or got[-1] != l):
            got.append(l)
    ok = len(want) == len(got) and all(line_matches(w, g) for w, g in zip(want, got))
    return ok, {"expected": [w.replace("\x00", "{…}") for w in want], "shown": got}


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False))
