#!/usr/bin/env python3
"""emu_dex - Pokedex helpers for emu_harness (from the Pokedex hunt agent, integrated).

Fill the Pokedex in RAM, open the list, move to a dex number (verified by reading the number off the screen),
open the detail tabs, and capture entry panels. Used by `emu_harness.py dex` (suite check).

Pokedex block (save array 6, general-block offset 0x13A8, 0x374 bytes, magic 0xBEEFCAFE): four 200-byte bit
arrays (bit = species - 1): caught +0x4, seen +0xCC, gender[0] +0x194, gender[1] +0x25C; +0x365 foreign
entries, +0x366 Pokedex obtained, +0x367 national (stubbed: getter 0x0202AA74 always returns 0). Editing the
dex in the battery save is undone by Continue (a write at 0x020D3944 restores it), so fill it in RAM in the
field. The list ('JOHTO POKeDEX') is in national order and shows No. 0001-0709 in the hack.

The digit reader needs templates of the game's digits. They are game graphics, so they are not stored in
git: build_templates() learns them from the first ten list entries (0001-0010) and caches them under the
harness output folder.
"""
import json
from pathlib import Path

import emu_harness as E

DEX = 0x13A8
CAUGHT, SEEN, G0, G1 = DEX + 4, DEX + 4 + 200, DEX + 4 + 400, DEX + 4 + 600
DEX_MAGIC = bytes.fromhex("fecaefbe")
TEMPLATES = E.DEF_OUT / "dex_digit_templates.json"      # outside git (game font pixels)
DIGIT_BG = {(232, 48, 48), (248, 152, 160)}
DIGIT_X, DIGIT_ROWS, DIGIT_WIDTH = 120, range(26, 38), {"1": 7}
TABS = {"area": (20, 178), "info": (70, 178), "size": (120, 178), "forms": (170, 178), "back": (228, 178)}


# ----------------------------------------------------------------------------- dex data
def _fill(data, base, n, caught, extra):
    if data[base + DEX:base + DEX + 4] != DEX_MAGIC:
        raise RuntimeError("Pokedex block not found (magic)")
    for sp in range(1, n + 1):
        i, k = (sp - 1) // 8, (sp - 1) % 8
        if caught:
            data[base + CAUGHT + i] |= 1 << k
        data[base + SEEN + i] |= 1 << k
        data[base + G0 + i] &= ~(1 << k)
        data[base + G1 + i] |= 1 << k
    for off, val in (extra or {}).items():
        data[base + off] = val


def fill_dex_ram(h, n=1025, caught=True, extra=None):
    """Mark species 1..n seen (both genders) and caught in the live save data (in the field)."""
    base = h.save + 0x10
    data = bytearray(h.read(base, 0x2000))
    _fill(data, 0, n, caught, extra)
    h.write(base + DEX, data[DEX:DEX + 0x374])


# ----------------------------------------------------------------------------- screen helpers
def top(h):
    return h.emu.screenshot().crop((0, 0, 256, 192))


def _col(img, x):
    return "".join("1" if img.getpixel((x, y)) not in DIGIT_BG else "0" for y in DIGIT_ROWS)


def build_templates(images_by_number):
    t = {}
    for n, img in images_by_number.items():
        img, x = img.convert("RGB"), DIGIT_X
        for ch in f"{n:04d}":
            w = DIGIT_WIDTH.get(ch, 8)
            t.setdefault(ch, [_col(img, x + i) for i in range(w)])
            x += w
    TEMPLATES.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES.write_text(json.dumps(t))
    return t


_T = None


def read_number(img):
    """The 4-digit dex number on the entry panel (x 120, rows 26-37), or None."""
    global _T
    if _T is None:
        _T = json.loads(TEMPLATES.read_text())
    img, x, s = img.convert("RGB"), DIGIT_X, ""
    for _ in range(4):
        cols = [_col(img, x + i) for i in range(8)]
        best, err = None, 99
        for ch, tc in _T.items():
            e = sum(a != b for c1, c2 in zip(tc, cols) for a, b in zip(c1, c2))
            if e < err:
                best, err = ch, e
        if err > 3:
            return None
        s += best
        x += len(_T[best])
    return int(s)


def number(h):
    return read_number(top(h))


def settle_top(h, min_frames=10, max_frames=150, every=4, stable=2):
    """Step until the top screen stops changing."""
    h.step(min_frames)
    prev, same = top(h).tobytes(), 0
    for _ in range(0, max_frames, every):
        h.step(every)
        cur = top(h).tobytes()
        same = same + 1 if cur == prev else 0
        if same >= stable:
            return True
        prev = cur
    return False


def settle_both(h, min_frames=20, max_frames=300, every=4, stable=2):
    """Like settle_top for both screens; a black (faded-out) top screen does not count as settled."""
    h.step(min_frames)
    for _ in range(0, max_frames, every):
        if h.emu.screenshot().convert("L").crop((0, 0, 256, 192)).getextrema()[1] >= 40:
            break
        h.step(every)
    prev, same = h.emu.screenshot().tobytes(), 0
    for _ in range(0, max_frames, every):
        h.step(every)
        cur = h.emu.screenshot().tobytes()
        same = same + 1 if cur == prev else 0
        if same >= stable:
            return True
        prev = cur
    return False


# ----------------------------------------------------------------------------- navigation
def open_dex_list(h, fill=True, n=1025):
    """In the field: fill the dex (RAM), open it, A to the list (cursor on No. 0001)."""
    if fill:
        fill_dex_ram(h, n=n)
    h.field_menu("pokedex")
    h.step(200)
    h.press("A", after=200)
    settle_top(h)
    if not TEMPLATES.exists():          # learn the digits from 0001..0010 (sequence trusted, one step each)
        imgs = {1: top(h)}
        for k in range(2, 11):
            h.press("RIGHT", frames=4)
            settle_top(h, min_frames=20)
            imgs[k] = top(h)
        build_templates(imgs)
        for _ in range(9):
            h.press("LEFT", frames=4)
            settle_top(h, min_frames=20)
    return number(h)


def press_until_change(h, key, max_frames=60, tries=3):
    """Press key until the shown dex number changes (a press during a scroll can be dropped)."""
    before = number(h)
    for _ in range(tries):
        h.press(key, frames=4)
        for _ in range(0, max_frames, 2):
            n = number(h)
            if n is not None and n != before:
                return n
            h.step(2)
    return None


def goto(h, target):
    """Move to dex number target with R (+15) and RIGHT/LEFT (+-1). Returns the number shown."""
    cur = number(h)
    while cur is not None and target - cur >= 15:
        n = press_until_change(h, "R")
        if n is None:
            break
        cur = n
    while cur is not None and cur < target:
        n = press_until_change(h, "RIGHT")
        if n is None:
            break
        cur = n
    while cur is not None and cur > target:
        n = press_until_change(h, "LEFT")
        if n is None:
            break
        cur = n
    return cur


def detail_page(h, tab):
    """From the list: open the entry's detail pages (A), pick a tab, return the full screenshot."""
    h.press("A", frames=4)
    settle_both(h)
    if tab != "area":
        h.touch(*TABS[tab], frames=8)
        settle_both(h)
    return h.emu.screenshot()


def back_to_list(h, max_frames=300):
    h.touch(*TABS["back"], frames=8)
    h.step(30)
    for _ in range(0, max_frames, 4):
        if number(h) is not None:
            break
        h.step(4)
    settle_top(h)


def capture_entries(h, first, last, outdir):
    """Save the entry panel (top screen) of dex numbers first..last as outdir/NNNN.png; each verified by
    reading the number back. Returns (captured numbers, errors)."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    done, errors = [], []
    cur = goto(h, first)
    while cur == first + len(done) and cur <= last:
        settle_top(h)
        img = top(h)
        if read_number(img) != cur:
            errors.append({"expected": cur, "read": read_number(img)})
        img.save(outdir / f"{cur:04d}.png")
        done.append(cur)
        if cur == last:
            break
        nxt = press_until_change(h, "RIGHT")
        if nxt is None:
            errors.append({"after": cur, "error": "end of list"})
            break
        cur = nxt
    return done, errors
