#!/usr/bin/env python3
"""emu_textfit - on-screen text-fit check: render translated strings in their real window on the English build
and decide from the pixels that they fit (`emu_harness.py textfit`, suite v2 step 4).

Selection (one of):
  --since REF   every string whose `en` differs between git REF and the working tree (default: the last
                release tag, `git describe --tags --abbrev=0`, else v1.0.0-rc5); a bank file that REF does not
                have counts as all new
  --refs LIST   bank#id list: a027/0060#27, 60#27 (a027), battle_string/0002#32
  --all         every string with English text (a full sweep)
  --limit N     an evenly spaced sample of N of the selection (smoke runs)

Windows (`window_for`): a string is rendered only where the window is known:
  field    a027 strings of QA category `dialogue`: the script message window (27x4 tiles at tile 2,19: text
           origin x 16, y 152, 216 x 32 px, 2 lines, font 1). Printed with the game's MsgBoxExtern from a
           field savestate (one per string), every wait of the printer screenshotted and A pressed.
  battle   battle_string banks 1 and 2: the battle message window (same geometry). A wild battle is started
           from the field; its first message (2#1) is replaced, after the battle's own expansion, by the
           string expanded with the fill-ins below; the battle advances the pages itself.
Everything else is listed as `unsupported` with its window type (menus, descriptions, names, Pokédex,
battle_string 0 = the battle's field-effect panel, battle_string 3 = the command menu labels, signposts,
dialogue whose Chinese also needs more than two lines per view), never skipped silently. Strings with no
printable text are `empty`.

Buffers: every {VAR:01KK:i} is filled with a real name of the matching kind (species, move, item, ...) that is
as wide as QA's typical estimate for that kind (--buffers max: the worst-case estimate); numbers with 8s.
Field: written into the script's MessageFormat buffers when the game expands the string (StringExpandPlaceholders
0x0200C738), so the ROM's own string is what prints. Battle: the battle expands with its own routine, so the
whole expanded string is written into its destination String after it (0x02225846).

Judge (`judge`, per string; every rule from the pixels of the views, read back with the ROM's font):
  pages      the number of printer waits seen equals the string's: one per {SCROLL} and {CLEAR}, plus the
             final one (field); battle: the distinct views
  lines      no text on a third line of a view (the printer draws it past the window; static from the
             structure, confirmed by the read-back)
  overflow   a line wider than the window: shown cut at the window edge (read back as a prefix of the line)
  text       a line read back differs from the expected text (wrong, missing or extra glyphs)
  ink        ink in the window's interior outside the text area, or in the last column of a line that the
             read-back could not check
  prompt     strings that wait with a prompt ({VAR:0200:..}): the last view's lines end by 195 px (the two
             prompt icons at x 211-228, in the battle and the field window alike; QA prompt_px). The icons are
             not read back (the field's last view is read up to 195 px)
Strings with SIZE codes (FF01) and the Chinese ROM are judged on pixels only (no read-back).

Reports: --out (default work/build/harness/textfit/run-<time>; never reused): summary.json
{pass, counts, failures, unsupported, errors, rows}, rows.jsonl (progress, one row per string), crops/ (the
window of every view of each failing string, EN, plus CN|EN pairs with --pairs).

    <venv>/bin/python work/tools/emu_harness.py textfit [--since v1.0.0-rc5 | --refs ... | --all] [--limit N]
        [--jobs 3] [--buffers typ|max] [--pairs] [--save fail|all]
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
REPO = WORK.parent
BANKS = WORK / "translate" / "banks"
BANKS_REL = "work/translate/banks"
DEFAULT_SINCE = "v1.0.0-rc5"          # the fallback when `git describe` finds no tag
CHARMAP_EN = TOOLS / "charmap_en.tsv"
CHARMAP_ZH = TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv"
UNKNOWN = "�"
LINE_H = 16
ROWMASK = 0x7FFE        # glyph rows 1-14 (rows 0 and 15 may hold a ruled line; only accents of capitals reach 0)
CLOCK = datetime.datetime(2026, 10, 9, 12)

# Windows measured on the English build (2026-10-09, both screenshots in emu_harness.md "Text fit"): text origin
# (x0, y0) = glyph column/row 0 of line 1; width = the window bitmap's width (the printer clips there); lines per
# view; interior = the white panel inside the frame (x 10-234, y 150-185), bg its colour.
_BOX = {"x0": 16, "y0": 152, "width": 216, "lines": 2, "bg": (248, 248, 248), "interior": (10, 150, 234, 185)}
WINDOWS = {
    "field": dict(_BOX, prompt_px=195, desc="script message window (DialogBox 27x4 tiles at 2,19), font 1"),
    "battle": dict(_BOX, prompt_px=195, desc="battle message window (ov12 bg1 2,19 27x4), font 1"),
}

# code (hack arm9; same bytes on both ROMs) -----------------------------------------------------------------
READ_INTO = 0x0200BB0C          # ReadMsgDataIntoString(MsgData *, id, String *dest); MsgData +4 narc, +6 bank
EXPAND = 0x0200C738             # StringExpandPlaceholders(MessageFormat *, String *dest, String *src)
# MessageFormat: +0 u32 count, +8 fields (8 bytes each, +4 String *); String: +0 u16 max, +2 u16 size,
# +4 u32 magic, +8 u16 data[] (StrAddChar 0x02026FDC keeps size + 1 < max)
STRING_MAGIC = 0xB6F8D2EC
BATTLE_AFTER_EXPAND = 0x02225846   # ov12: after the battle's own expansion (0x02225A3C); r6 = the dest String
BATTLE_SIG = "201c01f622f8"
CODE_SIGS = {READ_INTO: "18b581b0041c", EXPAND: "f8b5071c0e1c"}
NARC_A027 = 27
END, CMD = 0xFFFF, 0xFFFE

FIELD_STABLE = 10       # frames a field view must stay unchanged before it counts as a printer wait
BATTLE_STABLE = 12
POLL = 2
VIEW_BUDGET = 1500      # frames to wait for one view
BATTLE_BUDGET = 3000    # frames from the battle savestate to the end of the replaced message

# name pools for the buffer fill-ins: VAR kind (low byte of 0x01KK) -> a027 name bank
POOLS = {0x00: 232, 0x01: 232, 0x02: 232, 0x03: 232, 0x04: 183, 0x05: 711, 0x06: 739, 0x07: 739, 0x08: 219,
         0x09: 219, 0x0D: 219, 0x0E: 720, 0x0F: 724, 0x1C: 219}
POOLS_BATTLE = {0x00: 232, 0x02: 232, 0x0C: 232, 0x03: 724, 0x06: 711, 0x07: 739, 0x09: 219, 0x0E: 720}


# ============================================================================= selection

def parse_ref(s: str):
    """'a027/0060#27', '60#27' (a027) or 'battle_string/0002#32' -> (narc, bank, id)."""
    s = s.strip()
    m = re.fullmatch(r"(?:([a-z_0-9]+)/)?(\d+)#(\d+)", s)
    if not m:
        raise ValueError(f"bad ref {s!r}: use bank#id, a027/NNNN#id or battle_string/NNNN#id")
    return (m.group(1) or "a027", int(m.group(2)), int(m.group(3)))


def ref_str(ref) -> str:
    return "%s/%04d#%d" % ref


def bank_path(narc, bank, root=BANKS) -> Path:
    return Path(root) / narc / f"{bank:04d}.json"


@lru_cache(maxsize=None)
def load_bank(narc, bank, root=str(BANKS)):
    return json.loads(bank_path(narc, bank, root).read_text(encoding="utf-8"))


def _git(*args, cwd=REPO):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def latest_release_tag(cwd=REPO, fallback=DEFAULT_SINCE) -> str:
    """The latest tag reachable from HEAD (`git describe --tags --abbrev=0`), else `fallback`."""
    try:
        return _git("describe", "--tags", "--abbrev=0", cwd=cwd).strip() or fallback
    except (RuntimeError, OSError):
        return fallback


def diff_strings(old: dict | None, new: dict) -> list[int]:
    """ids of `new` whose en differs from `old` (a missing old bank: every id with English text)."""
    before = {e["id"]: e.get("en") for e in (old or {}).get("strings", [])}
    return [e["id"] for e in new["strings"]
            if e.get("en") is not None and (old is None or before.get(e["id"], None) != e.get("en"))]


def changed_refs(since=DEFAULT_SINCE, cwd=REPO, root=BANKS_REL):
    """(narc, bank, id) of every string whose en differs between git ref `since` and the working tree."""
    _git("rev-parse", "--verify", f"{since}^{{commit}}", cwd=cwd)
    files = _git("diff", "--name-only", since, "--", root, cwd=cwd).split()
    files += _git("ls-files", "--others", "--exclude-standard", "--", root, cwd=cwd).split()
    out = []
    for f in sorted(set(files)):
        m = re.fullmatch(re.escape(root) + r"/([a-z_0-9]+)/(\d{4})\.json", f)
        if not m:
            continue
        path = Path(cwd) / f
        if not path.exists():          # a deleted bank has nothing to render
            continue
        new = json.loads(path.read_text(encoding="utf-8"))
        try:
            old = json.loads(_git("show", f"{since}:{f}", cwd=cwd))
        except RuntimeError:
            old = None
        out += [(m.group(1), int(m.group(2)), i) for i in diff_strings(old, new)]
    return out


def all_refs(root=BANKS):
    out = []
    for p in sorted(Path(root).glob("*/*.json")):
        b = json.loads(p.read_text(encoding="utf-8"))
        out += [(b["narc"], b["bank"], e["id"]) for e in b["strings"] if e.get("en")]
    return out


def sample(refs, limit):
    """An evenly spaced, deterministic sample of `limit` refs (all of them when limit is None or larger)."""
    if not limit or limit >= len(refs):
        return list(refs)
    step = len(refs) / limit
    return [refs[int(k * step)] for k in range(limit)]


# ============================================================================= window mapping

@lru_cache(maxsize=None)
def _qa():
    import qa
    import textmetrics as tm
    return qa, tm, tm.load_config()


@lru_cache(maxsize=None)
def _hydrated(narc, bank, root=str(BANKS)):
    """The bank with the real zh where the workspace holds a redaction marker (zh_redact), for layout only."""
    import zh_redact
    qa, _, _ = _qa()
    try:
        hyd, _ = zh_redact.hydrate(load_bank(narc, bank, root), qa.EXTRACT_DIR)
    except Exception:
        hyd = load_bank(narc, bank, root)
    return hyd


def category(narc, bank, sid, root=str(BANKS)):
    qa, _, cfg = _qa()
    b = _hydrated(narc, bank, root)
    e = next((s for s in b["strings"] if s["id"] == sid), {})
    return e.get("category") or qa.string_categories(b, cfg).get(sid) or qa.bank_category(b, cfg)


def printable(en) -> bool:
    _, tm, _ = _qa()
    if not en:
        return False
    return bool(tm.visible_text(en).strip()) or any(
        (tm.var_cmd(v) >> 8) == 0x01 for k, v in tm.tokenize(en) if k == "var")


def window_for(narc, bank, sid, root=str(BANKS)):
    """-> (window, None) for a rendered string, ('unsupported', reason) or ('empty', reason)."""
    b = _hydrated(narc, bank, root)
    e = next((s for s in b["strings"] if s["id"] == sid), None)
    if e is None:
        return "unsupported", "no such string"
    if not printable(e.get("en")):
        return "empty", "no printable text"
    _, tm, _ = _qa()
    if narc == "battle_string":
        if bank in (1, 2):
            return "battle", None
        return "unsupported", {0: "window type battle_info (the battle's field-effect panel)",
                               3: "window type battle_menu (the command menu labels)"}.get(
            bank, f"window type battle_string/{bank:04d}")
    cat = category(narc, bank, sid, root)
    if narc == "a027" and cat == "dialogue":
        zh = e.get("zh") or ""
        if not zh.startswith("[zh redacted") and tm.page_lines(zh) > 2:
            return "unsupported", (f"window type dialogue_large (the Chinese also needs {tm.page_lines(zh)} "
                                   "lines per view: not the 2-line message window)")
        return "field", None
    return "unsupported", f"window type {cat}"


# ============================================================================= fill-ins and the expected views

def _width(text, font=1):
    _, tm, _ = _qa()
    w = 0
    for ch in text:
        cw = tm.char_width(ch, font)
        w += cw if cw is not None else 6
    return w


@lru_cache(maxsize=None)
def _pool(bank):
    names = []
    for e in load_bank("a027", bank)["strings"]:
        en = e.get("en") or ""
        if en and "{" not in en and en.strip() == en and len(en) > 1 and en.isprintable():
            names.append(en)
    return sorted(set(names), key=lambda n: (_width(n), n))


def filler(tag, narc="a027", mode="typ"):
    """Text for one {VAR:01KK:i}: a name of that kind as wide as QA's estimate (`mode` typ or max)."""
    _, tm, cfg = _qa()
    cmd = tm.var_cmd(tag)
    kind = cmd & 0xFF
    target = tm.var_width(tag, cfg, narc, mode)
    if (narc == "battle_string" and kind == 0x0F) or 0x32 <= kind <= 0x3B:
        return "8" * max(1, target // 6)
    bank = (POOLS_BATTLE if narc == "battle_string" else POOLS).get(kind, 219)
    names = _pool(bank)
    fit = [n for n in names if _width(n) <= target]
    return fit[-1] if fit else (names[0] if names else "X" * max(1, target // 6))


def fillers(en, narc="a027", mode="typ"):
    """{buffer index: text} for every string buffer the string uses."""
    _, tm, _ = _qa()
    out = {}
    for k, v in tm.tokenize(en or ""):
        if k == "var" and (tm.var_cmd(v) >> 8) == 0x01:
            args = tm.var_args(v)
            idx = args[0] if args else 0
            out.setdefault(idx, filler(v, narc, mode))
    return out


def expand(en, fill):
    """The string with every {VAR:01KK:i} replaced by fill[i] (other tags kept)."""
    _, tm, _ = _qa()

    def rep(m):
        tag = m.group(1)
        if tag.startswith("VAR:") and (tm.var_cmd(tag) >> 8) == 0x01:
            args = tm.var_args(tag)
            return fill.get(args[0] if args else 0, "")
        return m.group(0)
    return re.sub(r"\{([^{}]*)\}", rep, en or "")


def expected_views(text, lines=2, battle=False):
    """Simulate the printer on an expanded string. -> {views: [[row text]*lines], widths: [[px]], waits,
    lost: [{view, row, text}], size: bool, prompt: bool, cursor: bool}.
    {NEWLINE}: next row; {SCROLL} (0x25BC): wait, then the window is cleared before the next glyph (a
    trailing {SCROLL} leaves the view as it was); {CLEAR} (0x25BD): wait, scroll up one row, keep the row;
    the end of the string is one more wait (field: WaitButton); 0x0207 is a wait that keeps the view. Text on row >= lines is drawn past the window
    and never seen (`lost`). Control codes other than buffers print nothing; CURSOR_X (0x0203) moves x."""
    _, tm, _ = _qa()
    rows, widths = [""] * lines, [0] * lines
    y, x = 0, 0
    pending_clear = False
    views, vwidths, lost = [], [], []
    size = prompt = cursor = False
    waits = 0
    lost_row = {}

    def snap():
        views.append([r.rstrip(" ") for r in rows])
        vwidths.append(list(widths))

    for kind, val in tm.tokenize(text or ""):
        if kind == "layout":
            if val == "NEWLINE":
                y, x = y + 1, 0
            elif val == "SCROLL":
                waits += 1
                snap()
                pending_clear, y, x = True, 0, 0
            else:                                  # CLEAR: scroll one row up, stay on the current row
                waits += 1
                snap()
                if pending_clear:
                    rows, widths, pending_clear = [""] * lines, [0] * lines, False
                rows, widths = rows[1:] + [""], widths[1:] + [0]
                x = 0
            continue
        if kind == "var":
            cmd = tm.var_cmd(val)
            if cmd == 0xFF01:
                size = True
            elif cmd == 0x0200:
                prompt = True
            elif cmd == 0x0207:                    # waits for A like a page end, without clearing (seen in the
                waits += 1                         # field: 'The Bag is full...{VAR:0207}' shows two waits)
                snap()
            elif cmd == 0x0203:
                cursor = True
                args = tm.var_args(val)
                if args:
                    x = args[0]
            continue
        if kind != "text":
            continue
        if pending_clear:
            rows, widths, pending_clear = [""] * lines, [0] * lines, False
        if y < lines:
            if cursor and x > widths[y]:
                rows[y] += " "
            rows[y] += val
            x = max(x, widths[y]) + _width(val)
            widths[y] = x
        else:
            key = (len(views), y)
            lost_row[key] = lost_row.get(key, "") + val
            x += _width(val)
    waits += 1
    snap()
    lost = [{"view": v, "row": r, "text": t} for (v, r), t in lost_row.items()]
    if battle:                                     # the battle shows views; identical neighbours are one view
        keep = [k for k in range(len(views)) if k == 0 or views[k] != views[k - 1]]
        views, vwidths = [views[k] for k in keep], [vwidths[k] for k in keep]
        while len(views) > 1 and not any(views[-1]):
            views.pop()
            vwidths.pop()
    return {"views": views, "widths": vwidths, "waits": waits, "lost": lost, "size": size, "prompt": prompt,
            "cursor": cursor}


# ============================================================================= pixels: decoding a window

class Pixels:
    """Minimal image access for the decoder: get(x, y) -> colour. Wraps a PIL image (img.load()) or a 2D list
    (rows of colours; tests)."""

    def __init__(self, img=None, rows=None):
        if rows is not None:
            self.rows, self.w, self.h = rows, len(rows[0]), len(rows)
            self._get = lambda x, y: self.rows[y][x]
        else:
            img = img.convert("RGB")
            self.w, self.h = img.size
            px = img.load()
            self._get = lambda x, y: px[x, y]

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self._get(x, y)
        return None


def _charmap_en():
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
    """Ink columns (16-bit row masks, rows 1-14) of every decodable glyph of a font: glyphs {code: (char, width,
    cols)}. From the ROM (Font.from_rom) or given directly (tests)."""

    def __init__(self, glyphs):
        self.glyphs = glyphs
        self.index = {}
        for code, (ch, w, cols) in glyphs.items():
            self.index.setdefault(cols[0] if cols else 0, []).append((ch, w, cols))
        for k in self.index:        # longest first; the space last among equals
            self.index[k].sort(key=lambda g: (-g[1], g[0] == " "))
        self.space = next((g for g in glyphs.values() if g[0] == " "), None)

    @classmethod
    def from_rom(cls, rom_path, font_id=1):
        import msgtool as m
        rom = m.load_rom(str(rom_path))
        data = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH)).files[font_id]
        glyphs, seen = {}, set()
        # identical bitmaps (O and ●, ...): ASCII letters/digits first, then the Latin block (high codes)
        for code, ch in sorted(_charmap_en().items(), key=lambda kv: (not (kv[1].isascii() and kv[1].isalnum()),
                                                                       -kv[0])):
            pix, w = m.render_glyph(data, code)
            if not w or w > 16:
                continue
            cols = tuple(sum(1 << y for y in range(LINE_H) if pix[y][x] in (1, 2)) & ROWMASK for x in range(w))
            if (w, cols) in seen and ch != " ":
                continue
            if not any(cols) and ch != " ":
                continue
            seen.add((w, cols))
            glyphs[code] = (ch, w, cols)
        return cls(glyphs)


@lru_cache(maxsize=None)
def rom_font(rom_path, font_id=1):
    return Font.from_rom(rom_path, font_id)


def ink_columns(px: Pixels, x0, y0, width, bg):
    """Column masks (rows 1-14 of the 16 from y0) for x0 .. x0+width-1; ink = any colour but bg."""
    cols = []
    for x in range(x0, x0 + width):
        m = 0
        for y in range(LINE_H):
            c = px.get(x, y0 + y)
            if c is not None and c != bg:
                m |= 1 << y
        cols.append(m & ROWMASK)
    return cols


def parse_line(cols, f: Font):
    """Decode column masks into text: exact glyph matches only; a column that starts no glyph is U+FFFD.
    Returns (text, last ink column + 1, unknown count)."""
    end = max((i + 1 for i in range(len(cols)) if cols[i]), default=0)
    if end == 0:
        return "", 0, 0
    memo = {}

    def fits(x, gcols):
        return all((cols[x + i] if x + i < len(cols) else 0) == c for i, c in enumerate(gcols))

    def go(x):
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

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 4000))
    out, x, unknown = [], 0, 0
    while x < end:
        reach, text = go(x)
        out.append(text)
        if reach >= end:
            break
        x = reach
        if cols[x]:
            out.append(UNKNOWN)
            unknown += 1
            x += 1
            while x < end and go(x)[0] == x and cols[x]:
                x += 1
        else:
            out.append(" ")
            x += 1
    return "".join(out), end, unknown


def decode_view(px: Pixels, box, font: Font | None, limit=None):
    """One view of a window -> {rows: [{text, right, last_col, unknown}], ink_outside: n pixels, limit}.
    limit: read only the first `limit` px of each line (the view with the prompt icons at its right end)."""
    rows = []
    for k in range(box["lines"]):
        cols = ink_columns(px, box["x0"], box["y0"] + LINE_H * k, limit or box["width"], box["bg"])
        if font is not None:
            text, right, unknown = parse_line(cols, font)
        else:
            text, unknown = None, 0
            right = max((i + 1 for i in range(len(cols)) if cols[i]), default=0)
        rows.append({"text": text, "right": right, "last_col": bool(cols and cols[-1]), "unknown": unknown})
    x0, y0, x1, y1 = box["interior"]
    tx0, ty0 = box["x0"], box["y0"]
    tx1, ty1 = tx0 + box["width"] - 1, ty0 + LINE_H * box["lines"] - 1
    outside = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if (tx0 <= x <= tx1 and ty0 <= y <= ty1) or (x in (x0, x1) and y in (y0, y1)):
                continue                           # the text area; the panel's rounded corners
            c = px.get(x, y)
            if c is not None and c != box["bg"]:
                outside += 1
    return {"rows": rows, "ink_outside": outside, "limit": limit}


# ============================================================================= the judge

def norm(s):
    return re.sub(r" +", " ", s or "").strip(" ")


def _extends(a, b):
    """True when decoded view b continues a (the same rows, each a prefix of b's, more text)."""
    ta, tb = [norm(r["text"]) for r in a["rows"]], [norm(r["text"]) for r in b["rows"]]
    return ta != tb and all(y.startswith(x) for x, y in zip(ta, tb))


def merge_partial(views):
    """Drop views that a later view continues (a page captured during a pause of the printer)."""
    out = []
    for v in views:
        if out and out[-1]["rows"][0]["text"] is not None and _extends(out[-1], v):
            out[-1] = v
        else:
            out.append(v)
    return out


def _cut_prefix(got, line):
    """True when `got` is `line` cut at the window edge: a prefix, or a prefix plus the last glyph drawn only
    in part (read back as U+FFFD or as a narrower glyph)."""
    got = got.rstrip(" ")
    return line.startswith(got) or line.startswith(got.rstrip(UNKNOWN).rstrip(" ")) or \
        (len(got) > 1 and line.startswith(got[:-1]))


def judge(decoded, exp, box, readback=True, battle=False):
    """decoded: the views seen (decode_view rows); exp: expected_views(). Returns {verdict, reasons, pages,
    overflow_px, overflow_lines, max_right}. Every reason is {code, view, row, detail}."""
    reasons = []
    width = box["width"]
    readback = readback and not exp["size"] and all(r["text"] is not None for v in decoded for r in v["rows"])
    seen = decoded
    if battle:
        seen = [v for k, v in enumerate(seen)
                if k == 0 or [r["text"] for r in v["rows"]] != [r["text"] for r in seen[k - 1]["rows"]]]
        while len(seen) > 1 and not any(r["right"] for r in seen[-1]["rows"]):
            seen.pop()
    want = len(exp["views"]) if battle else exp["waits"]
    if readback and len(seen) > want:      # a view captured during a pause of the printer: the next one
        seen = merge_partial(seen)         # continues it (only then: a {CLEAR} view may extend the last one)
    if len(seen) != want:
        reasons.append({"code": "pages", "view": None, "row": None,
                        "detail": f"{len(seen)} views shown, the string has {want}"})
    overflow_px, overflow_lines = 0, 0
    for k, (vw, ew) in enumerate(zip(exp["views"], exp["widths"])):
        for r, w in enumerate(ew):
            if w > width:
                overflow_px = max(overflow_px, w - width)
                overflow_lines += 1
                shown = norm(seen[k]["rows"][r]["text"]) if readback and k < len(seen) else None
                reasons.append({"code": "overflow", "view": k + 1, "row": r + 1,
                                "detail": f"{w} px > {width} px: '{vw[r]}'"
                                + (f"; shown '{shown}'" if shown is not None else "")})
    for lo in exp["lost"]:
        overflow_lines += 1
        reasons.append({"code": "lines", "view": lo["view"] + 1, "row": lo["row"] + 1,
                        "detail": f"text on line {lo['row'] + 1} of a {box['lines']}-line window: '{lo['text']}'"})
    if readback and len(seen) == want:
        for k, vw in enumerate(exp["views"]):
            for r, line in enumerate(vw):
                got = norm(seen[k]["rows"][r]["text"])
                exp_line = norm(line)
                if got == exp_line:
                    continue
                limit = seen[k].get("limit") or width
                if exp["widths"][k][r] > min(limit, width) and _cut_prefix(got, exp_line):
                    continue                       # the cut is reported as overflow / prompt
                code = "text"
                detail = f"shown '{got}', expected '{exp_line}'"
                if got and _cut_prefix(got, exp_line):
                    detail += " (cut)"
                reasons.append({"code": code, "view": k + 1, "row": r + 1, "detail": detail})
    for k, v in enumerate(seen):
        if v["ink_outside"]:
            reasons.append({"code": "ink", "view": k + 1, "row": None,
                            "detail": f"{v['ink_outside']} ink pixels outside the text area"})
        if not readback:
            for r, row in enumerate(v["rows"]):
                if row["last_col"]:
                    reasons.append({"code": "ink", "view": k + 1, "row": r + 1,
                                    "detail": "ink in the window's last column (cut at the edge?)"})
    if exp["prompt"] and box.get("prompt_px") and seen:
        p = box["prompt_px"]
        for r, row in enumerate(seen[-1]["rows"]):
            w = exp["widths"][-1][r] if r < len(exp["widths"][-1]) else 0
            if w > p or row["right"] > p:
                reasons.append({"code": "prompt", "view": len(seen), "row": r + 1,
                                "detail": f"line is {max(w, row['right'])} px: runs under the prompt icons "
                                          f"(x {box['x0'] + p}-{box['x0'] + p + 17}; the line must end by {p} px)"})
    max_right = max((r["right"] for v in seen for r in v["rows"]), default=0)
    return {"verdict": "fail" if reasons else "pass", "reasons": reasons, "pages": len(seen), "pages_expected": want,
            "overflow_px": overflow_px, "overflow_lines": overflow_lines, "max_right": max_right,
            "readback": readback}


# ============================================================================= child: rendering on one ROM

def _encode(text, lang):
    import msgtool as m
    cm = _charmap(lang)
    return m.encode_text(text, cm)[:-1]


@lru_cache(maxsize=None)
def _charmap(lang):
    import msgtool as m
    return m.Charmap.load([str(CHARMAP_EN)] + ([str(CHARMAP_ZH)] if lang == "cn" else []))


def write_string(h, ptr, units):
    """Replace the contents of a game String (no reallocation): False when it does not fit or is no String."""
    mx, magic = h.u16(ptr), h.u32(ptr + 4)
    if magic != STRING_MAGIC or len(units) >= mx:        # size + terminator must fit the max units
        return False
    h.write(ptr + 8, b"".join(u.to_bytes(2, "little") for u in list(units) + [END]))
    h.w16(ptr + 2, len(units))
    return True


def _string_units(h, ptr):
    n = h.u16(ptr + 2)
    raw = h.read(ptr + 8, 2 * n)
    return [int.from_bytes(raw[i:i + 2], "little") for i in range(0, 2 * n, 2)]


def _inline_buffers(units, texts):
    """units with each buffer code {VAR:01KK:i,..} whose i is in texts replaced by texts[i] (code units)."""
    out, i = [], 0
    while i < len(units):
        if units[i] == CMD and i + 2 < len(units):
            cmd, argc = units[i + 1], units[i + 2]
            if cmd >> 8 == 0x01 and argc and units[i + 3] in texts:
                out += texts[units[i + 3]]
            else:
                out += units[i:i + 3 + argc]
            i += 3 + argc
        else:
            out.append(units[i])
            i += 1
    return out


def _buffer_indices(units):
    out, i = [], 0
    while i < len(units):
        if units[i] == CMD and i + 2 < len(units):
            cmd, argc = units[i + 1], units[i + 2]
            if cmd >> 8 == 0x01 and argc:
                out.append(units[i + 3])
            i += 3 + argc
        else:
            i += 1
    return out


class FieldRenderer:
    """Field message window: MsgBoxExtern from a field savestate, the MessageFormat buffers filled at
    StringExpandPlaceholders."""

    def __init__(self, h, state):
        import emu_harness as E
        self.h, self.E, self.state = h, E, state
        self.target = None
        h.check_code(CODE_SIGS)
        h.on_exec(READ_INTO, self._read)
        h.on_exec(EXPAND, self._expand)

    def _read(self, h):
        t = self.target
        if t and t["src"] is None:
            md = h.reg.r0
            if h.u16(md + 4) == NARC_A027 and h.u16(md + 6) == t["bank"] and (h.reg.r1 & 0xFFFF) == t["id"]:
                t["src"] = h.reg.r2

    def _expand(self, h):
        t = self.target
        if not t or t["src"] is None or h.reg.r2 != t["src"] or t["done"]:
            return
        t["done"] = True
        fmt = h.reg.r0
        count, fields = h.u32(fmt), h.u32(fmt + 8)
        units = _string_units(h, t["src"])
        inline = set()
        for idx in sorted(set(_buffer_indices(units))):
            text = t["fill"].get(idx)
            if text is None:
                continue
            if idx < count and write_string(h, h.u32(fields + 8 * idx + 4), _encode(text, t["lang"])):
                t["filled"].append(idx)
            else:
                inline.add(idx)
        if inline:     # more buffers than this MessageFormat has (phone calls use 10, 11): put the text in place
            new = _inline_buffers(units, {i: _encode(t["fill"][i], t["lang"]) for i in inline})
            if write_string(h, t["src"], new):
                t["inlined"] = sorted(inline)
            else:
                t["unfilled"] += sorted(inline)

    def render(self, ref, fill, lang, max_views):
        """-> (views as PIL images, info)."""
        h, E = self.h, self.E
        _, bank, sid = ref
        h.load_state(self.state)
        self.target = {"bank": bank, "id": sid, "src": None, "done": False, "fill": fill, "lang": lang,
                       "filled": [], "unfilled": [], "inlined": []}
        h.set_var(E.SENTINEL_VAR, 0)
        h.run_script(file=3, index=0, msg_bank=bank, program=E.message_script(bank, sid), settle=1)
        views, prev, same, waited = [], None, 0, 0
        while True:
            if h.get_var(E.SENTINEL_VAR) == 0x5A5A:
                break
            if len(views) > max_views:
                raise RuntimeError(f"more than {max_views} views")
            h.step(POLL)
            waited += POLL
            img = h.emu.screenshot()
            key = img.crop((16, 152, 232, 184)).tobytes()
            same = same + POLL if key == prev else 0
            prev = key
            if same >= FIELD_STABLE:
                views.append(img)
                h.press("A", after=2)
                same, prev, waited = 0, None, 0
            elif waited > VIEW_BUDGET:
                raise RuntimeError(f"view {len(views) + 1} did not settle in {VIEW_BUDGET} frames")
        info = {"filled": self.target["filled"], "inlined": self.target["inlined"],
                "unfilled": self.target["unfilled"], "read": self.target["src"] is not None}
        self.target = None
        return views, info


class BattleRenderer:
    """Battle message window: the first message of a wild battle replaced by the expanded string."""

    def __init__(self, h, state):
        self.h, self.state = h, state
        self.target = None
        h.on_exec(BATTLE_AFTER_EXPAND, self._after)

    def _after(self, h):
        t = self.target
        if not t:
            return
        if h.read(BATTLE_AFTER_EXPAND, len(BATTLE_SIG) // 2).hex() != BATTLE_SIG:
            return
        t["messages"] += 1
        if t["messages"] == 1:
            t["ok"] = write_string(h, h.reg.r6, t["units"])
            t["frame"] = h.frame

    def render(self, ref, units, max_views):
        h = self.h
        h.load_state(self.state)
        self.target = t = {"units": units, "messages": 0, "ok": None, "frame": None}
        views, prev, same, last = [], None, 0, None
        for _ in range(0, BATTLE_BUDGET, POLL):
            h.step(POLL)
            if t["messages"] >= 2:
                break
            if t["messages"] == 0:
                continue
            if t["ok"] is False:
                raise RuntimeError("the expanded string does not fit the battle's String buffer")
            img = h.emu.screenshot()
            key = img.crop((16, 152, 232, 184)).tobytes()
            same = same + POLL if key == prev else 0
            prev = key
            if same >= BATTLE_STABLE and key != last:
                views.append(img)
                last = key
                if len(views) > max_views:
                    raise RuntimeError(f"more than {max_views} views")
        else:
            raise RuntimeError(f"the replaced battle message did not end within {BATTLE_BUDGET} frames")
        self.target = None
        return views, {"frame": t["frame"]}


def _crop_sheet(views, path, title=None):
    from PIL import Image
    if not views:
        return None
    sheet = Image.new("RGB", (256, 52 * len(views)), "white")
    for k, img in enumerate(views):
        sheet.paste(img.crop((0, 140, 256, 192)), (0, 52 * k))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return str(path)


def item_plan(ref, mode="typ", lang="en"):
    """What to render for one ref: window, the fill-ins, the expanded text and the expected views."""
    narc, bank, sid = ref
    e = next(s for s in load_bank(narc, bank)["strings"] if s["id"] == sid)
    text = e["en"] if lang == "en" else next(s for s in _hydrated(narc, bank)["strings"] if s["id"] == sid)["zh"]
    fill = fillers(e["en"], narc, mode)
    expanded = expand(text, fill)
    battle = narc == "battle_string"
    return {"fill": fill, "expanded": expanded, "exp": expected_views(expanded, battle=battle)}


def cmd_child(a):
    """Render a batch of refs of one window on one ROM; one row per ref (also appended to --progress)."""
    import emu_harness as E
    items = json.loads(Path(a.items).read_text())
    out = Path(a.out).resolve()           # the DeSmuME backend changes the working directory
    a.rom, a.sav = str(Path(a.rom).resolve()), str(Path(a.sav).resolve())
    a.progress = a.progress and str(Path(a.progress).resolve())
    out.mkdir(parents=True, exist_ok=True)
    font = rom_font(str(a.rom)) if a.lang == "en" else None
    box = WINDOWS[a.window]
    rows = []
    prog = open(a.progress, "a") if a.progress else None
    with E.start_at(None, rom=a.rom, sav=a.sav, out=out, verbose=False, clock=CLOCK) as h:
        state = out / f"_{a.window}_{a.lang}_{os.getpid()}.dst"
        if a.window == "battle":
            h.run_script(program=E.script_bytes(("LockAll",), ("WildBattle", 19, 20, 0), ("ReleaseAll",),
                                                ("End",)), settle=1)
            h.save_state(state)
            r = BattleRenderer(h, state)
        else:
            h.save_state(state)
            r = FieldRenderer(h, state)
        try:
            for it in items:
                ref = tuple(it["ref"])
                t0 = time.time()
                row = {"ref": ref_str(ref), "window": a.window, "lang": a.lang}
                try:
                    plan = item_plan(ref, a.buffers, a.lang)
                    exp = plan["exp"]
                    max_views = (exp["waits"] if a.window == "field" else len(exp["views"])) + 4
                    if a.window == "battle":
                        units = [u for u in _encode(plan["expanded"], a.lang)]
                        units = _strip_prompt(units)
                        views, info = r.render(ref, units, max_views)
                    else:
                        views, info = r.render(ref, plan["fill"], a.lang, max_views)
                    decoded = [decode_view(Pixels(v), box, font, limit=box["prompt_px"] if (
                        exp["prompt"] and a.window == "field" and k == len(views) - 1) else None)
                        for k, v in enumerate(views)]
                    res = judge(decoded, exp, box, readback=font is not None, battle=a.window == "battle")
                    if info.get("unfilled"):
                        res["reasons"].append({"code": "buffers", "view": None, "row": None,
                                               "detail": f"buffers {info['unfilled']} could not be filled"})
                        res["verdict"] = "fail"
                    row.update(res, info=info, fill={str(k): v for k, v in plan["fill"].items()},
                               shown=[[r_["text"] for r_ in v["rows"]] for v in decoded],
                               expected=exp["views"], decoded=decoded)
                    if a.save == "all" or res["verdict"] != "pass" or a.lang == "cn":
                        row["crop"] = _crop_sheet(views, out / "crops" / f"{ref_str(ref).replace('/', '_')
                                                                          .replace('#', '_')}_{a.lang}.png")
                except Exception as e:      # this ref only: the next one starts from the savestate again
                    row.update(verdict="error", error=f"{type(e).__name__}: {e}"[-600:])
                row["seconds"] = round(time.time() - t0, 2)
                rows.append(row)
                if prog:
                    prog.write(json.dumps(row, ensure_ascii=False) + "\n")
                    prog.flush()
        finally:
            if prog:
                prog.close()
            try:
                state.unlink()
            except OSError:
                pass
    print("RESULT " + json.dumps({"rows": len(rows)}))
    return 0


def _strip_prompt(units):
    """Drop {VAR:0200:..} (the battle prompt wait) from encoded units: the replaced message has no prompt."""
    out, i = [], 0
    while i < len(units):
        if units[i] == CMD and i + 2 < len(units) and units[i + 1] == 0x0200:
            i += 3 + units[i + 2]
            continue
        out.append(units[i])
        i += 1
    return out


def add_child_arguments(p):
    p.add_argument("--rom", required=True)
    p.add_argument("--lang", choices=("cn", "en"), default="en")
    p.add_argument("--window", choices=tuple(WINDOWS), required=True)
    p.add_argument("--items", required=True, help="JSON list of {ref: [narc, bank, id]}")
    p.add_argument("--sav", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--progress")
    p.add_argument("--buffers", choices=("typ", "max"), default="typ")
    p.add_argument("--save", choices=("fail", "all"), default="fail")


# ============================================================================= parent

def add_arguments(p):
    import emu_harness as E
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--since", help=f"strings whose en changed since this git ref (default: the latest tag, "
                                       f"git describe --tags --abbrev=0; {DEFAULT_SINCE} when there is none)")
    sel.add_argument("--refs", help="comma/space list of bank#id, a027/NNNN#id, battle_string/NNNN#id")
    sel.add_argument("--all", action="store_true", help="every string with English text (full sweep)")
    sel.add_argument("--rejudge", metavar="RUN", help="judge the views read back in an earlier run's folder again "
                     "(after a judge change; no emulator); writes RUN/rejudge-<time>/summary.json")
    p.add_argument("--limit", type=int, help="an evenly spaced sample of N strings of the selection")
    p.add_argument("--windows", default=",".join(WINDOWS), help="render only these window types")
    p.add_argument("--buffers", choices=("typ", "max"), default="typ",
                   help="fill-in width per buffer kind: QA's typical (default) or worst-case estimate")
    p.add_argument("--jobs", type=int, default=3, help="child emulators in parallel (machine-wide cap "
                   "EMU_HARNESS_MAX_EMULATORS, default 6)")
    p.add_argument("--chunk", type=int, default=250, help="strings per child process (one boot each)")
    p.add_argument("--pairs", action="store_true", help="also render each failing string on the Chinese ROM "
                   "and save CN|EN pairs (context only; not judged)")
    p.add_argument("--save", choices=("fail", "all"), default="fail", help="window crops of failing (default) "
                   "or all strings")
    p.add_argument("--out", help="new folder for this run (default work/build/harness/textfit/run-<time>)")
    p.add_argument("--rom-en", default=str(E.DEF_ROM_EN))
    p.add_argument("--rom-cn", default=str(E.DEF_ROM_CN))
    p.add_argument("--sav", default=str(E.DEF_SAVES / "full_bag_6mons.sav"))


def select(a):
    if a.refs:
        refs = [parse_ref(s) for s in re.split(r"[,\s]+", a.refs) if s]
        how = "refs"
    elif a.all:
        refs, how = all_refs(), "all"
    else:
        since = a.since or latest_release_tag()
        refs, how = changed_refs(since), f"since {since}"
    refs = sorted(set(refs), key=lambda r: (r[0], r[1], r[2]))
    return sample(refs, a.limit), how, len(refs)


def plan_rows(refs, windows):
    """Split refs into {window: [refs]} and the rows of the strings that are not rendered."""
    todo, rows = {w: [] for w in WINDOWS}, []
    for ref in refs:
        try:
            w, why = window_for(*ref)
        except (FileNotFoundError, StopIteration) as e:
            w, why = "unsupported", f"no such string ({e})"
        if w in WINDOWS and w in windows:
            todo[w].append(ref)
        elif w in WINDOWS:
            rows.append({"ref": ref_str(ref), "window": w, "verdict": "not-rendered",
                         "reason": f"window {w} not selected (--windows)"})
        else:
            rows.append({"ref": ref_str(ref), "window": None, "verdict": w, "reason": why})
    return todo, rows


def _run_batches(a, groups, out, jobs):
    """groups: [(window, lang, rom, refs)]. Every group is cut into chunks of --chunk refs, one child process
    each (one boot, one emulator), all chunks in one pool of `jobs`. A child that dies is restarted for the refs
    it did not finish; the ref it was on becomes an error row. Returns the rows."""
    import concurrent.futures as cf

    import emu_harness as E
    tasks = [(w, lang, rom, k, refs[i:i + a.chunk]) for w, lang, rom, refs in groups
             for k, i in enumerate(range(0, len(refs), a.chunk))]

    def run(task):
        window, lang, rom, k, chunk = task
        rows, todo, attempt = [], list(chunk), 0
        while todo:
            attempt += 1
            tag = f"{window}_{lang}_{k:03d}_{attempt}"
            items, prog = out / "batches" / f"{tag}.json", out / "batches" / f"{tag}.jsonl"
            items.parent.mkdir(parents=True, exist_ok=True)
            items.write_text(json.dumps([{"ref": list(r)} for r in todo]))
            err = None
            try:
                E.run_child(["textfit-child", "--rom", rom, "--lang", lang, "--window", window, "--items", items,
                             "--sav", a.sav, "--out", out, "--progress", prog, "--buffers", a.buffers,
                             "--save", a.save], timeout=300 + 40 * len(todo))
            except Exception as e:
                err = str(e)[-800:]
            done = [json.loads(line) for line in prog.read_text().splitlines()] if prog.exists() else []
            rows += done
            todo = todo[len(done):]
            if todo and (err is None or attempt >= 2 + len(chunk) // 10):
                rows += [{"ref": ref_str(r), "window": window, "lang": lang, "verdict": "error",
                          "error": f"child ended before this string: {err or 'no error message'}"} for r in todo]
                break
            if todo:
                rows.append({"ref": ref_str(todo[0]), "window": window, "lang": lang, "verdict": "error",
                             "error": f"child died on this string: {err}"})
                todo = todo[1:]
        return rows

    results = []
    with cf.ThreadPoolExecutor(max(1, jobs)) as ex:
        for rows in ex.map(run, tasks):
            results += rows
    return results


def _pairs(out, en_rows, cn_rows):
    from PIL import Image
    cn = {r["ref"]: r for r in cn_rows}
    for r in en_rows:
        c = cn.get(r["ref"])
        if not (c and c.get("crop") and r.get("crop")):
            continue
        a_, b_ = Image.open(c["crop"]), Image.open(r["crop"])
        pair = Image.new("RGB", (512 + 8, max(a_.height, b_.height)), "white")
        pair.paste(a_, (0, 0))
        pair.paste(b_, (264, 0))
        p = Path(r["crop"]).with_name(Path(r["crop"]).stem.replace("_en", "") + "_pair.png")
        pair.save(p)
        r["pair"] = str(p)


def summarise(rows, how, selected, out, seconds, roms, args):
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    rendered = sum(counts.get(k, 0) for k in ("pass", "fail", "error"))
    unsupported = {}
    for r in rows:
        if r["verdict"] in ("unsupported", "empty", "not-rendered"):
            unsupported.setdefault(r["reason"], []).append(r["ref"])
    failures = [{"ref": r["ref"], "window": r["window"], "reasons": r["reasons"], "overflow_px": r["overflow_px"],
                 "overflow_lines": r["overflow_lines"], "pages": r["pages"], "pages_expected": r["pages_expected"],
                 "crop": r.get("crop"), "pair": r.get("pair")} for r in rows if r["verdict"] == "fail"]
    errors = [{"ref": r["ref"], "window": r["window"], "error": r.get("error")} for r in rows
              if r["verdict"] == "error"]
    summary = {"pass": not failures and not errors, "selection": how, "selected": selected,
               "counts": {"strings": len(rows), "rendered": rendered, **counts}, "failures": failures,
               "errors": errors, "unsupported": {k: {"count": len(v), "refs": v} for k, v in
                                                  sorted(unsupported.items(), key=lambda kv: -len(kv[1]))},
               "roms": roms, "args": args, "out": str(out), "seconds": seconds,
               "rows": sorted(rows, key=lambda r: (r["verdict"] != "fail", r["ref"]))}
    (Path(out) / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    return summary


def print_summary(s):
    for f in s["failures"]:
        print(f"FAIL  {f['ref']} [{f['window']}] " + "; ".join(
            f"{r['code']}" + (f" v{r['view']}" if r["view"] else "") + (f"l{r['row']}" if r["row"] else "")
            + f": {r['detail']}" for r in f["reasons"])[:400])
    for e in s["errors"]:
        print(f"ERROR {e['ref']} [{e['window']}] {str(e['error'])[:300]}")
    for why, v in s["unsupported"].items():
        print(f"NOT RENDERED {v['count']:5}  {why}")
    print(json.dumps({"pass": s["pass"], **s["counts"], "seconds": s["seconds"],
                      "summary": str(Path(s["out"]) / "summary.json")}))


def rejudge(a):
    """Judge the decoded views of an earlier run again with the current judge and the current bank text."""
    t0 = time.time()
    src = Path(a.rejudge).resolve()
    rows = []
    for p in sorted((src / "batches").glob("*.jsonl")):      # EN only: the CN pairs are in src/cn
        rows += [json.loads(line) for line in p.read_text().splitlines()]
    old = json.loads((src / "summary.json").read_text()) if (src / "summary.json").exists() else {}
    seen = {r["ref"] for r in rows}
    rows += [r for r in old.get("rows", []) if r["ref"] not in seen and r["verdict"] not in ("pass", "fail")]
    for r in rows:
        if r.get("decoded") is None or r.get("lang", "en") != "en":
            continue
        plan = item_plan(parse_ref(r["ref"]), a.buffers)
        box = WINDOWS[r["window"]]
        res = judge(r["decoded"], plan["exp"], box, readback=True, battle=r["window"] == "battle")
        if r.get("info", {}).get("unfilled"):
            res["reasons"].append({"code": "buffers", "view": None, "row": None,
                                   "detail": f"buffers {r['info']['unfilled']} could not be filled"})
            res["verdict"] = "fail"
        r.update(res, expected=plan["exp"]["views"])
        pair = r.get("crop") and Path(r["crop"]).with_name(Path(r["crop"]).stem.replace("_en", "") + "_pair.png")
        if pair and pair.exists():
            r["pair"] = str(pair)
    stale = sum(1 for r in rows if r["verdict"] in ("pass", "fail") and r.get("decoded") is None)
    out = src / time.strftime("rejudge-%Y%m%d-%H%M%S")
    out.mkdir()
    s = summarise(rows, f"rejudge of {src.name}" + (f" ({stale} rows without decoded views kept as they were)"
                                                     if stale else ""), old.get("selected", len(rows)), out,
                  round(time.time() - t0, 1), old.get("roms"), {"rejudge": str(src), "buffers": a.buffers})
    print_summary(s)
    return 0 if s["pass"] else 1


def run(a):
    import emu_harness as E
    if a.rejudge:
        return rejudge(a)
    t0 = time.time()
    out = (Path(a.out) if a.out else E.DEF_OUT / "textfit" / time.strftime("run-%Y%m%d-%H%M%S")).resolve()
    if (out / "summary.json").exists() or (out / "batches").exists():
        print(f"{out} already holds a run; choose a new --out", file=sys.stderr)
        return 2
    for rom in (a.rom_en,) + ((a.rom_cn,) if a.pairs else ()):
        if not Path(rom).exists():
            print(f"ROM not found: {rom}", file=sys.stderr)
            return 2
    try:
        refs, how, selected = select(a)
    except (ValueError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    windows = [w for w in a.windows.split(",") if w]
    todo, rows = plan_rows(refs, windows)
    print(json.dumps({"selection": how, "selected": selected, "sampled": len(refs),
                      "render": {w: len(v) for w, v in todo.items()}, "not_rendered": len(rows)}), flush=True)
    rows += _run_batches(a, [(w, "en", a.rom_en, refs_w) for w, refs_w in todo.items() if refs_w], out, a.jobs)
    if a.pairs:
        failed = [r for r in rows if r["verdict"] == "fail"]
        groups = [(w, "cn", a.rom_cn, [parse_ref(r["ref"]) for r in failed if r["window"] == w]) for w in WINDOWS]
        _pairs(out, failed, _run_batches(a, [g for g in groups if g[3]], out / "cn", a.jobs))
    roms = {"en": {"path": str(a.rom_en), "sha256": _sha256(a.rom_en)}}
    s = summarise(rows, how, selected, out, round(time.time() - t0, 1), roms,
                  {"buffers": a.buffers, "windows": windows, "limit": a.limit, "jobs": a.jobs})
    print_summary(s)
    return 0 if s["pass"] else 1


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================================= scenario observation

def observe(h, ref, lang, mode="typ"):
    """The `text_fit` observation of a scenario: render one a027 string in the field window on the running
    harness (standing in the field) and judge it. Returns {verdict, pages, codes} (codes: the failing rules)."""
    ref = parse_ref(ref) if isinstance(ref, str) else tuple(ref)
    state = Path(h.out) / f"_textfit_{os.getpid()}.dst"
    h.save_state(state)
    try:
        r = FieldRenderer(h, state)
        plan = item_plan(ref, mode, lang)
        views, info = r.render(ref, plan["fill"], lang, plan["exp"]["waits"] + 4)
        font = rom_font(str(h.rom)) if lang == "en" else None
        box = WINDOWS["field"]
        decoded = [decode_view(Pixels(v), box, font, limit=box["prompt_px"] if (
            plan["exp"]["prompt"] and k == len(views) - 1) else None) for k, v in enumerate(views)]
        res = judge(decoded, plan["exp"], WINDOWS["field"], readback=font is not None)
        h.on_exec(READ_INTO, None)
        h.on_exec(EXPAND, None)
        h.load_state(state)
    finally:
        try:
            state.unlink()
        except OSError:
            pass
    return {"verdict": res["verdict"], "pages": res["pages"], "codes": sorted({x["code"] for x in res["reasons"]})}
