#!/usr/bin/env python3
"""gfx - Nitro 2D graphics helpers and the graphics-patch stage for the English build.

Formats handled (enough for the [[graphics]] entries of the fixes in work/patches/):
  NCGR (RGCN) 4bpp/8bpp character data, NCLR (RLCN) palettes, NSCR (RCSN) screens,
  LZ10 (0x10) / LZ11 (0x11) compressed NARC members.

The build (work/tools/build.py, stage "graphics") calls apply_patches(); nothing here edits a ROM
in place. Every patch is data: the [[graphics]] entries of the kind-'graphics' fixes in
work/patches/<fix-id>/fix.toml (read through fixes.py; build.py applies the enabled ones, or the
--only/--without selection) plus the files they name. Overview: work/patches/FIXES.md.

Patch operations (one [[graphics]] table each; shown here as JSON objects):
  {"op": "copy_us", "narc": "a/0/0/8", "members": [219, ...], "also": [<more NARC paths>]}
        replace the member with the USA ROM's member of the same NARC index (bytes as-is).
        Checks: both are NCGR, same bpp and tile count, same compression.
  {"op": "tiles_from_file", "narc": ..., "member": 236, "src": "vendor/.../x.NCGR"}
        keep the hack's NCGR container, replace only its character data with the tiles of src.
        Checks: same bpp and tile count. Compression of the member is preserved (LZ10 re-packed).
  {"op": "tiles_from_png", "narc": ..., "member": 131, "src": "x.png"}
        indexed (mode "P") PNG, width/height = the NCGR's tile grid; pixel values are palette
        indices (must be < 16 for 4bpp). Tiles are read row-major.
  {"op": "tiles_from_us", "narc": ..., "member": 17, "tiles": [[first, last], ...]}
        copy only the listed tile ranges from the USA member (same bpp and tile count; compression kept).
  {"op": "tile_range_from_png", "narc": ..., "member": 10, "first": 0, "src": "x.png", "width_tiles": 4}
        replace only tiles first..first+n-1 with the tiles of an indexed PNG strip (width_tiles wide).
        For "also" copies only that tile range has to match the main NARC's member.
  {"op": "member_from_file", "narc": ..., "files": {"1": {"src": "generated/x.bin", "expect_sha1": "<12 hex>"}, ...}}
        replace each listed member with a generated file (any format), but only if the hack's member
        still has the SHA-1 the file was generated from. (Single-member form: "member", "src", "expect_sha1".)
  {"op": "code_from_us", "file": "overlay14", "offset": "0x4C0A8", "us_file": "overlay12", "us_offset": "0x36340",
   "length": 480, "expect_sha1": "<12 hex>", "us_sha1": "<12 hex>"}
        graphics stored as raw tile data inside code (arm9 / overlays, not in a NARC), e.g. the battle
        HP-box status icons: copy `length` bytes from the USA ROM's (decompressed) code file into the
        hack's code file. Offsets are hex strings, file offsets in the decompressed image (as in
        [[code]]). Checks: the hack's bytes
        and the USA bytes still have the recorded SHA-1s; the hack's overlay must be uncompressed.
  "also": the same operation is applied to each listed NARC too (e.g. the hack's per-costume
        copies data/clothes1/a068.narc and data/clothes2/a068.narc), after checking that the
        member there is byte-identical to the main NARC's member before patching.

CLI
  python3 work/tools/gfx.py check    [--rom CN.nds] [--us US.nds]      dry-run all patches
        checks replacement formats/sizes and audited runtime tile-map allocations
  python3 work/tools/gfx.py check-layouts BUILT.nds [--json REPORT]
        check regenerated screens, including costume copies, against layout_checks.json;
        recorded loader code must still match the audited load sizes
  python3 work/tools/gfx.py sheet    ROM OUT.png                       review sheet of the type/category
                                                                        graphics (battle, Pokedex, summary)
  python3 work/tools/gfx.py make-dex-type-list --out work/graphics/dex_type_list_en.png
        regenerate the English Pokedex type-label sheet (a/0/6/8 #131) from the USA ROM's battle
        type-icon letter pixels (and hg-engine's FAIRY icon), recoloured with the hack's label colours
  python3 work/tools/gfx.py make-naming-labels --out work/graphics/naming_labels_en.png
        regenerate the naming-keyboard tab/button labels (data/namein.narc #10 tiles 0..207)
  python3 work/tools/gfx.py make-dex-labels [--out work/graphics/generated]
        regenerate the English Pokedex header/button members (a/0/6/8 #1 #4 and their screens);
        prints the matching member_from_file [[graphics]] entry (TOML, for work/patches/gfx-dex-header/fix.toml)
  python3 work/tools/gfx.py make-title-subtitle [--out work/graphics/generated]
        regenerate the optional bilingual title subtitle (a/2/6/4 #0 #3 #8)
  python3 work/tools/gfx.py make-weather-banners [--hge DIR] [--out work/graphics/weather_en]
        English battle weather banners (battle/battle_graphics.narc #33-#49 odd)
  python3 work/tools/gfx.py make-trainer-card [--out work/graphics/generated]
        trainer card unit glyphs (a/0/4/9 #41 #47 #48)
  python3 work/tools/gfx.py make-linkcapture [--out work/graphics/generated]
        the hack's link/capture menu bar (data/linkcapture.narc #25 #26)
  python3 work/tools/gfx.py make-battle-panel-labels [--out work/graphics/generated] [--review PNG]
        the hack's battle info panel labels (battle/battle_graphics.narc #18): (B)EXIT (+)(+)SWAP
  python3 work/tools/gfx.py regenerate [--rom CN.nds] [--us US.nds] [--out work/graphics]
        run all the make-* generators above (build.py does this before the graphics stage). Their
        outputs (generated/, weather_en/, dex_type_list_en.png, naming_labels_en.png) contain
        Nintendo / hack art and are git-ignored: a fresh clone rebuilds them from the user's ROMs
  python3 work/tools/gfx.py audit    [--rom ROM.nds] [--us US.nds] --out DIR
        render every screen (NSCR) and cell (NCER) of each NARC with a changed NCGR and keep those that
        differ from the USA ROM (contact sheets for review by eye; run it on the built ROM to see what is
        still not English). Tiles stored inside code (e.g. the battle HP-box status icons in the battle
        overlay) are not covered: see graphics_inventory.md, "Graphics inside code"
  python3 work/tools/gfx.py scan     [--rom CN.nds] [--us US.nds] [--out DIR]
        list/render every changed or added NCGR (tiles identical to a US tile are dimmed): the
        starting point of work/notes/graphics_inventory.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
GRAPHICS = WORK / "graphics"
LAYOUTS = GRAPHICS / "layout_checks.json"
sys.path.insert(0, str(TOOLS))

import fixes as fixreg  # noqa: E402
import msgtool as m  # noqa: E402

ROM_CN = WORK / "rom" / "origin_v4.0.3_cn.nds"
ROM_US = WORK / "rom" / "Pokemon - HeartGold Version (USA).nds"


# ---------------------------------------------------------------------------------------------
# compression
# ---------------------------------------------------------------------------------------------

def lz11_decompress(b: bytes) -> bytes:
    size = b[1] | b[2] << 8 | b[3] << 16
    i = 4
    if size == 0:
        size = struct.unpack_from("<I", b, 4)[0]
        i = 8
    out = bytearray()
    while len(out) < size:
        flags = b[i]
        i += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if not flags & (0x80 >> bit):
                out.append(b[i])
                i += 1
                continue
            x = b[i] >> 4
            if x == 0:
                n = ((b[i] & 0xF) << 4 | b[i + 1] >> 4) + 0x11
                d = ((b[i + 1] & 0xF) << 8 | b[i + 2]) + 1
                i += 3
            elif x == 1:
                n = ((b[i] & 0xF) << 12 | b[i + 1] << 4 | b[i + 2] >> 4) + 0x111
                d = ((b[i + 2] & 0xF) << 8 | b[i + 3]) + 1
                i += 4
            else:
                n = x + 1
                d = ((b[i] & 0xF) << 8 | b[i + 1]) + 1
                i += 2
            for _ in range(n):
                out.append(out[-d])
    return bytes(out)


def unpack(b: bytes):
    """-> (plain bytes, compression tag None|'lz10'|'lz11')"""
    b = bytes(b)
    if b[:4] in (b"RGCN", b"RLCN", b"RCSN", b"RECN", b"RNAN"):
        return b, None
    if len(b) > 4 and b[0] == 0x10:
        import ndspy.lz10
        try:
            return bytes(ndspy.lz10.decompress(b)), "lz10"
        except Exception:
            pass
    if len(b) > 4 and b[0] == 0x11:
        try:
            return lz11_decompress(b), "lz11"
        except Exception:
            pass
    return b, None


def repack(b: bytes, comp):
    if comp is None:
        return b
    if comp == "lz10":
        import ndspy.lz10
        return bytes(ndspy.lz10.compress(b))
    if comp == "lz11":
        return lz11_compress(b)
    raise ValueError(f"re-compression {comp} not supported")


def lz11_compress(data: bytes) -> bytes:
    """Greedy LZ11 (0x11) compressor; lz11_decompress() round-trips it (checked by the caller's verify)."""
    n = len(data)
    out = bytearray([0x11, n & 0xFF, n >> 8 & 0xFF, n >> 16 & 0xFF]) if n < 1 << 24 else \
        bytearray([0x11, 0, 0, 0]) + struct.pack("<I", n)
    heads = {}
    i = 0
    while i < n:
        flag_pos = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if i >= n:
                break
            best_len, best_d = 0, 0
            if i + 3 <= n:
                for j in reversed(heads.get(data[i:i + 3], [])[-64:]):
                    d = i - j
                    if d > 0x1000:
                        break
                    ln = 3
                    mx = min(n - i, 0x10110)
                    while ln < mx and data[j + ln] == data[i + ln]:
                        ln += 1
                    if ln > best_len:
                        best_len, best_d = ln, d
                        if ln == mx:
                            break
            if best_len >= 3:
                flags |= 0x80 >> bit
                d = best_d - 1
                if best_len <= 0x10:
                    out += bytes([(best_len - 1) << 4 | d >> 8, d & 0xFF])
                elif best_len <= 0x110:
                    ln = best_len - 0x11
                    out += bytes([ln >> 4, (ln & 0xF) << 4 | d >> 8, d & 0xFF])
                else:
                    ln = best_len - 0x111
                    out += bytes([0x10 | ln >> 12, ln >> 4 & 0xFF, (ln & 0xF) << 4 | d >> 8, d & 0xFF])
                step = best_len
            else:
                out.append(data[i])
                step = 1
            for k in range(i, min(i + step, n - 2)):
                heads.setdefault(data[k:k + 3], []).append(k)
            i += step
        out[flag_pos] = flags
    while len(out) % 4:
        out.append(0)
    assert lz11_decompress(bytes(out)) == data
    return bytes(out)


def magic(b: bytes) -> str:
    return unpack(b)[0][:4].decode("latin1")


# ---------------------------------------------------------------------------------------------
# Nitro 2D containers
# ---------------------------------------------------------------------------------------------

def sections(b: bytes) -> dict:
    hsize, n = struct.unpack_from("<HH", b, 12)
    off, out = hsize, {}
    for _ in range(n):
        if off + 8 > len(b):
            break
        mg = b[off:off + 4].decode("latin1")
        sz = struct.unpack_from("<I", b, off + 4)[0]
        out[mg] = (off, sz)
        if sz == 0:
            break
        off += sz
    return out


def rgb555(v):
    return ((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31)


class NCLR:
    def __init__(self, b: bytes):
        b, _ = unpack(b)
        off, _ = sections(b)["TTLP"]
        self.depth, _, dsz, doff = struct.unpack_from("<IIII", b, off + 8)
        data = b[off + 8 + doff: off + 8 + doff + dsz]
        self.colors = [rgb555(struct.unpack_from("<H", data, i)[0]) for i in range(0, len(data) - 1, 2)]

    def row(self, k):
        return self.colors[16 * k:16 * (k + 1)]


class NCGR:
    """Character data. `tiles` are lists of 64 palette indices (row-major inside the 8x8 tile)."""

    def __init__(self, b: bytes):
        self.raw, self.comp = unpack(b)
        off, _ = sections(self.raw)["RAHC"]
        (self.h, self.w, depth, self.mapping, self.tiled, dsz, doff) = struct.unpack_from("<HHIIIII", self.raw, off + 8)
        self.bpp = 4 if depth == 3 else 8
        self.data_off = off + 8 + doff
        self.data_len = dsz
        data = self.raw[self.data_off:self.data_off + dsz]
        tsz = 32 if self.bpp == 4 else 64
        self.tiles = []
        for t in range(len(data) // tsz):
            d = data[t * tsz:(t + 1) * tsz]
            if self.bpp == 4:
                px = []
                for by in d:
                    px += [by & 15, by >> 4]
            else:
                px = list(d)
            self.tiles.append(px)

    def grid_width(self, default=32):
        n = len(self.tiles)
        if 0 < self.w < 0x100 and 0 < self.h < 0x100 and self.w * self.h == n:
            return self.w
        return default

    def tile_bytes(self, tiles=None) -> bytes:
        tiles = self.tiles if tiles is None else tiles
        out = bytearray()
        for px in tiles:
            if self.bpp == 4:
                for i in range(0, 64, 2):
                    out.append((px[i] & 15) | (px[i + 1] & 15) << 4)
            else:
                out += bytes(px)
        return bytes(out)

    def with_tiles(self, tiles) -> bytes:
        """Container bytes (re-compressed like the original) with the character data replaced."""
        assert len(tiles) == len(self.tiles), "tile count differs"
        data = self.tile_bytes(tiles)
        assert len(data) == self.data_len
        plain = self.raw[:self.data_off] + data + self.raw[self.data_off + self.data_len:]
        return repack(plain, self.comp)


class NSCR:
    def __init__(self, b: bytes):
        self.raw, self.comp = unpack(b)
        b = self.raw
        off, _ = sections(b)["NRCS"]
        self.w, self.h, _, dsz = struct.unpack_from("<HHII", b, off + 8)
        self.data_off, self.data_len = off + 0x14, dsz
        data = b[off + 0x14: off + 0x14 + dsz]
        self.ents = [struct.unpack_from("<H", data, i)[0] for i in range(0, len(data), 2)]

    def pos(self, k):
        """Pixel position of entry k. Screens wider than 256 px are stored as 256x256 blocks."""
        if self.w > 256:
            blk, r = divmod(k, 1024)
            return (blk * 32 + r % 32) * 8, (r // 32) * 8
        return (k % (self.w // 8)) * 8, (k // (self.w // 8)) * 8

    def with_entries(self, ents) -> bytes:
        assert len(ents) == len(self.ents)
        data = b"".join(struct.pack("<H", e) for e in ents)
        plain = self.raw[:self.data_off] + data + self.raw[self.data_off + self.data_len:]
        return repack(plain, self.comp)


def screen_cells(sc: NSCR, g: NCGR):
    """-> {k: (pal, 64 palette indices as displayed)} for every entry inside the screen."""
    out = {}
    for k, e in enumerate(sc.ents):
        x0, y0 = sc.pos(k)
        if y0 >= sc.h or x0 >= sc.w:
            continue
        ti, hf, vf = e & 0x3FF, e >> 10 & 1, e >> 11 & 1
        px = g.tiles[ti] if ti < len(g.tiles) else [0] * 64
        out[k] = (e >> 12, _flip(px, hf, vf))
    return out


def _flip(px, hf, vf):
    return [px[(7 - i // 8 if vf else i // 8) * 8 + (7 - i % 8 if hf else i % 8)] for i in range(64)]


def screen_to_image(sc: NSCR, g: NCGR):
    """-> rows of (pal, index) pixels"""
    img = [[(0, 0)] * sc.w for _ in range(sc.h)]
    for k, (pl, px) in screen_cells(sc, g).items():
        x0, y0 = sc.pos(k)
        for i, v in enumerate(px):
            img[y0 + i // 8][x0 + i % 8] = (pl, v)
    return img


def retile(g: NCGR, screens, pool):
    """Make each screen show its target image with the fewest tile changes.
    screens: list of (NSCR, target rows of (pal, index)); pool: tile indices that may be overwritten
    (never referenced elsewhere). Unchanged cells keep their tiles; a changed cell reuses any tile
    (with flips) that still holds the wanted pixels, else takes a tile from the pool.
    -> (new tiles, [new entry lists])"""
    tiles = [list(t) for t in g.tiles]
    want, keep = [], set()
    for sc, tgt in screens:
        w = {}
        for k, (pl, px) in screen_cells(sc, g).items():
            x0, y0 = sc.pos(k)
            tp = [tgt[y0 + i // 8][x0 + i % 8] for i in range(64)]
            tpx = [v for _, v in tp]
            tpal = {p for p, v in tp if v} or {pl}
            if len(tpal) > 1:
                raise ValueError(f"cell {k}: target mixes palettes {tpal}")
            w[k] = (tpal.pop(), tpx)
            if tpx == px:
                keep.add(sc.ents[k] & 0x3FF)
        want.append(w)
    free = [t for t in pool if t not in keep]
    lookup = {}

    def index(t):
        for hf in (0, 1):
            for vf in (0, 1):
                lookup.setdefault(tuple(_flip(tiles[t], hf, vf)), (t, hf, vf))

    for t in keep:
        index(t)
    out = []
    for (sc, _), w in zip(screens, want):
        ents = list(sc.ents)
        for k, (pl, px) in w.items():
            e = sc.ents[k]
            cur = _flip(tiles[e & 0x3FF], e >> 10 & 1, e >> 11 & 1) if (e & 0x3FF) in keep else None
            if cur == px:
                ents[k] = (e & 0x0FFF) | pl << 12
                continue
            hit = lookup.get(tuple(px))
            if hit is None:
                if not free:
                    raise ValueError("retile: tile pool exhausted")
                t = free.pop(0)
                tiles[t] = list(px)
                keep.add(t)
                index(t)
                hit = (t, 0, 0)
            t, hf, vf = hit
            ents[k] = t | hf << 10 | vf << 11 | pl << 12
        out.append(ents)
    return tiles, out


GRAY = [(0, 0, 0)] + [(int(255 * (i / 15) ** 0.8),) * 3 for i in range(1, 16)]


def render_tiles(g: NCGR, tw=None, pal=None, tiles=None):
    from PIL import Image
    tiles = g.tiles if tiles is None else tiles
    n = len(tiles)
    tw = tw or g.grid_width()
    tw = max(1, min(tw, n or 1))
    th = (n + tw - 1) // tw
    img = Image.new("RGB", (tw * 8, max(1, th) * 8), (40, 0, 40))
    pix = img.load()
    for t, px in enumerate(tiles):
        tx, ty = (t % tw) * 8, (t // tw) * 8
        for i, v in enumerate(px):
            c = (pal[v] if v < len(pal) else (255, 0, 255)) if pal else (GRAY[v] if g.bpp == 4 else (v, v, v))
            pix[tx + i % 8, ty + i // 8] = c
    return img


def render_obj(g: NCGR, parts, pal=None):
    """1D-mapped OBJ: parts = [(w_tiles, h_tiles), ...] laid out left to right."""
    from PIL import Image
    W = sum(p[0] for p in parts) * 8
    H = max(p[1] for p in parts) * 8
    img = Image.new("RGB", (W, H))
    t = x0 = 0
    for w, h in parts:
        img.paste(render_tiles(g, w, pal, g.tiles[t:t + w * h]), (x0, 0))
        x0 += w * 8
        t += w * h
    return img


def render_screen(sc: NSCR, g: NCGR, pal=None):
    from PIL import Image
    img = Image.new("RGB", (sc.w, sc.h))
    pix = img.load()
    for k, e in enumerate(sc.ents):
        ti, hf, vf, pl = e & 0x3FF, e >> 10 & 1, e >> 11 & 1, e >> 12
        x0, y0 = sc.pos(k)
        if y0 >= sc.h or x0 >= sc.w:
            break
        px = g.tiles[ti] if ti < len(g.tiles) else [0] * 64
        for i in range(64):
            x, y = i % 8, i // 8
            v = px[i]
            if hf:
                x = 7 - x
            if vf:
                y = 7 - y
            if pal:
                idx = pl * 16 + v if g.bpp == 4 else v
                c = pal[idx] if idx < len(pal) else (255, 0, 255)
            else:
                c = GRAY[v] if g.bpp == 4 else (v, v, v)
            pix[x0 + x, y0 + y] = c
    return img


# ---------------------------------------------------------------------------------------------
# patches
# ---------------------------------------------------------------------------------------------

def load_manifest(fixes=None):
    """The graphics operations to apply, in order: the [[graphics]] entries of the given active fixes, else
    of every enabled fix in work/patches (each op carries "fix" = its fix id)."""
    if fixes is None:
        fixes = [f for f in fixreg.load_all() if f.get("enabled")]
    return fixreg.graphics_manifest(fixes)


def validate_member_layout(before, after, label):
    """Replacing an asset must preserve the layout its existing consumers expect."""
    old, old_comp = unpack(before)
    new, new_comp = unpack(after)
    if (old[:4], old_comp) != (new[:4], new_comp):
        raise ValueError(f"{label}: graphics format/compression changed")
    if old[:4] == b"RGCN":
        a, b = NCGR(before), NCGR(after)
        if (a.bpp, len(a.tiles), a.mapping, a.tiled) != (b.bpp, len(b.tiles), b.mapping, b.tiled):
            raise ValueError(f"{label}: character depth/count/mapping changed")
    elif old[:4] == b"RCSN":
        a, b = NSCR(before), NSCR(after)
        if (a.w, a.h, a.data_len) != (b.w, b.h, b.data_len):
            raise ValueError(f"{label}: screen dimensions/entry count changed")
    elif old[:4] == b"RLCN":
        if len(NCLR(before).colors) != len(NCLR(after).colors):
            raise ValueError(f"{label}: palette colour count changed")
    elif old[:4] in (b"RECN", b"RNAN") and old != new:
        raise ValueError(f"{label}: sprite cells/animations changed; review their consumers first")


def validate_screen_tiles(screen, graphic, loaded_bytes, label):
    """Check the runtime-loaded part of an NCGR, rather than its file capacity."""
    tile_bytes = 32 if graphic.bpp == 4 else 64
    size = graphic.data_len if loaded_bytes == 0 else loaded_bytes
    if size <= 0 or size > graphic.data_len or size % tile_bytes:
        raise ValueError(f"{label}: invalid runtime character load size {size}")
    limit = size // tile_bytes
    highest = max((e & 0x3FF for e in screen.ents), default=-1)
    if highest >= limit:
        raise ValueError(f"{label}: screen references tile {highest}, but the runtime loads only "
                         f"tiles 0..{limit - 1} ({size} bytes)")
    return {"loaded_tiles": limit, "highest_tile": highest}


def check_layouts(get_file, code=None, rules=None, changed_screens=()):
    """Check all regenerated tile maps, including costume copies, against audited load sites."""
    rules = json.loads(LAYOUTS.read_text(encoding="utf-8")) if rules is None else rules
    narcs, rows = {}, []
    for rule in rules:
        if code is not None:
            for site in rule.get("load_sites", []):
                data = code.get(site["file"])[site["offset"]:site["offset"] + site["length"]]
                if hashlib.sha1(data).hexdigest()[:12] != site["expect_sha1"]:
                    raise ValueError(f"{rule['narc']}: audited graphics loader changed at "
                                     f"{site['file']}+{site['offset']:#x}; recheck its tile limit")
        for path in [rule["narc"]] + rule.get("also", []):
            if path not in narcs:
                narcs[path] = m.Narc.parse(get_file(path)).files
            files = narcs[path]
            g = NCGR(files[rule["graphic"]])
            for screen in rule["screens"]:
                label = f"{path} screen #{screen} / character #{rule['graphic']}"
                row = validate_screen_tiles(NSCR(files[screen]), g, rule["loaded_bytes"], label)
                rows.append({"narc": path, "graphic": rule["graphic"], "screen": screen, **row})
    covered = {(row["narc"], row["screen"]) for row in rows}
    missing = set(changed_screens) - covered
    if missing:
        raise ValueError(f"graphics screens have no audited runtime allocation: {sorted(missing)}")
    return rows


def read_indexed_png(path: Path, with_palette: bool = False):
    """Minimal reader for indexed (colour type 3, bit depth 1/2/4/8), non-interlaced PNGs -> (w, h, rows)
    (rows = one bytes object of palette indices per row), plus the palette as a list of (r, g, b) when
    `with_palette`. Pure Python so the build does not need Pillow."""
    import zlib
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, idat, hdr, plte = 8, b"", None, b""
    while pos < len(data):
        ln, typ = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    w, h, depth, ctype, _, _, interlace = hdr
    if depth not in (1, 2, 4, 8) or ctype != 3 or interlace != 0:
        raise ValueError(f"{path}: need an indexed non-interlaced PNG (got depth {depth}, type {ctype})")
    stride = (w * depth + 7) // 8
    raw = zlib.decompress(idat)
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - 1] if x else 0
            b = prev[x]
            c = prev[x - 1] if x else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if depth == 8:
            rows.append(bytes(line))
        else:
            per, mask = 8 // depth, (1 << depth) - 1
            rows.append(bytes((line[x // per] >> (8 - depth * (x % per + 1))) & mask for x in range(w)))
    if with_palette:
        return w, h, rows, [tuple(plte[k:k + 3]) for k in range(0, len(plte) - 2, 3)]
    return w, h, rows


def write_indexed_png(path: Path, w: int, h: int, pixels, palette):
    """Write an 8-bit indexed PNG (no Pillow needed). `pixels`: w*h palette indices, row-major;
    `palette`: (r, g, b) tuples, padded to 256 entries."""
    import zlib
    pixels = bytes(pixels)
    assert len(pixels) == w * h
    pal = [tuple(c) for c in palette][:256]
    pal += [(0, 0, 0)] * (256 - len(pal))

    def chunk(typ, body):
        return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + pixels[y * w:(y + 1) * w] for y in range(h))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", bytes(v for c in pal for v in c)) + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)
    return path


def png_tiles(path: Path, g: NCGR):
    w, h, rows = read_indexed_png(path)
    tw = g.grid_width(4)
    th = len(g.tiles) // tw
    if (w, h) != (tw * 8, th * 8):
        raise ValueError(f"{path}: size {(w, h)} != NCGR grid {(tw * 8, th * 8)}")
    lim = 16 if g.bpp == 4 else 256
    tiles = []
    for t in range(len(g.tiles)):
        x0, y0 = (t % tw) * 8, (t // tw) * 8
        tile = [rows[y0 + i // 8][x0 + i % 8] for i in range(64)]
        if max(tile) >= lim:
            raise ValueError(f"{path}: tile {t} uses palette index >= {lim}")
        tiles.append(tile)
    return tiles


def png_tile_strip(path: Path, width_tiles: int = 4):
    """All 8x8 tiles of an indexed PNG, row-major, grid `width_tiles` wide."""
    w, h, rows = read_indexed_png(path)
    if w != width_tiles * 8 or h % 8:
        raise ValueError(f"{path}: size {(w, h)} is not a {width_tiles}-tile-wide strip")
    return [[rows[(t // width_tiles) * 8 + i // 8][(t % width_tiles) * 8 + i % 8] for i in range(64)]
            for t in range((h // 8) * width_tiles)]


def _patched_member(op, member, cur: bytes, us_member, root: Path) -> bytes:
    kind = op["op"]
    if kind == "member_from_file":
        spec = op["files"][str(member)] if "files" in op else op
        got = hashlib.sha1(cur).hexdigest()[:12]
        if got != spec["expect_sha1"]:
            raise ValueError(f"{op['narc']} #{member}: hack member is {got}, expected {spec['expect_sha1']}; "
                             f"regenerate {spec['src']}")
        return (root / spec["src"]).read_bytes()
    g = NCGR(cur)
    if kind == "tiles_from_us":
        if us_member is None:
            raise ValueError("USA ROM has no such member")
        u = NCGR(us_member)
        if (u.bpp, len(u.tiles)) != (g.bpp, len(g.tiles)):
            raise ValueError("USA member differs in bpp/tile count")
        idx = [t for a, b in op["tiles"] for t in range(a, b + 1)]
        tiles = list(g.tiles)
        for t in idx:
            tiles[t] = u.tiles[t]
        return g.with_tiles(tiles)
    if kind == "tile_range_from_png":
        new = png_tile_strip(root / op["src"], op.get("width_tiles", 4))
        first = op["first"]
        if first + len(new) > len(g.tiles):
            raise ValueError(f"{op['src']}: tiles {first}..{first + len(new) - 1} outside the NCGR ({len(g.tiles)})")
        lim = 16 if g.bpp == 4 else 256
        if any(v >= lim for t in new for v in t):
            raise ValueError(f"{op['src']}: palette index >= {lim}")
        tiles = list(g.tiles)
        tiles[first:first + len(new)] = new
        return g.with_tiles(tiles)
    if kind == "copy_us":
        if us_member is None:
            raise ValueError("USA ROM has no such member")
        u = NCGR(us_member)
        if (u.bpp, len(u.tiles)) != (g.bpp, len(g.tiles)):
            raise ValueError(f"USA member differs in bpp/tile count ({u.bpp},{len(u.tiles)}) vs ({g.bpp},{len(g.tiles)})")
        if u.comp != g.comp:
            raise ValueError(f"compression differs ({u.comp} vs {g.comp})")
        return bytes(us_member)
    if kind == "tiles_from_file":
        s = NCGR((root / op["src"]).read_bytes())
        if (s.bpp, len(s.tiles)) != (g.bpp, len(g.tiles)):
            raise ValueError(f"{op['src']}: bpp/tile count ({s.bpp},{len(s.tiles)}) != ({g.bpp},{len(g.tiles)})")
        return g.with_tiles(s.tiles)
    if kind == "tiles_from_png":
        return g.with_tiles(png_tiles(root / op["src"], g))
    raise ValueError(f"unknown op {kind}")


class CodeView:
    """arm9 / overlay images of an ndspy ROM by key ("arm9", "overlayNN"); overlays decompressed on read.
    set() only writes uncompressed overlays (and arm9) and never changes a size."""

    def __init__(self, rom):
        self.rom = rom
        self._ovs = None

    @property
    def ovs(self):
        if self._ovs is None:
            import ndspy.code
            self._ovs = ndspy.code.loadOverlayTable(self.rom.arm9OverlayTable, lambda i, f: bytes(self.rom.files[f]))
        return self._ovs

    def _ov(self, key):
        if not key.startswith("overlay"):
            raise ValueError(f"unknown code file {key}")
        return self.ovs[int(key[7:])]

    def get(self, key) -> bytes:
        if key == "arm9":
            return bytes(self.rom.arm9)
        return bytes(self._ov(key).data)

    def set(self, key, data: bytes):
        old = self.get(key)
        if len(old) != len(data):
            raise ValueError(f"{key}: size change not allowed")
        if key == "arm9":
            self.rom.arm9 = bytes(data)
            return
        ov = self._ov(key)
        if ov.compressed:
            raise ValueError(f"{key}: compressed overlays are not supported")
        ov.data = bytes(data)
        self.rom.files[ov.fileID] = bytes(data)


def _apply_code_op(op, code, us_code):
    if code is None or us_code is None:
        raise ValueError(f"{op['op']}: no code access (pass code=/us_code= to apply_patches)")
    cur = bytearray(code.get(op["file"]))
    off, n = fixreg._int(op["offset"]), op["length"]
    us_off = fixreg._int(op["us_offset"])
    got = hashlib.sha1(bytes(cur[off:off + n])).hexdigest()[:12]
    if got != op["expect_sha1"]:
        raise ValueError(f"{op['file']}+{off:#x}: hack bytes are {got}, expected {op['expect_sha1']}")
    us = us_code.get(op["us_file"])[us_off:us_off + n]
    ug = hashlib.sha1(us).hexdigest()[:12]
    if ug != op["us_sha1"]:
        raise ValueError(f"{op['us_file']}+{us_off:#x}: USA bytes are {ug}, expected {op['us_sha1']}")
    cur[off:off + n] = us
    code.set(op["file"], bytes(cur))
    return {"code": op["file"], "offset": off, "length": n, "op": op["op"], "src": "usa " + op["us_file"],
            "notes": op.get("notes", ""), "sha1": hashlib.sha1(us).hexdigest()[:12]}


def verify_code_rows(code, report):
    """Re-read every code range the graphics stage wrote; raises on a mismatch."""
    n = 0
    for r in report:
        if "code" not in r:
            continue
        got = hashlib.sha1(code.get(r["code"])[r["offset"]:r["offset"] + r["length"]]).hexdigest()[:12]
        if got != r["sha1"]:
            raise AssertionError(f"graphics {r['code']}+{r['offset']:#x}: {got} != {r['sha1']}")
        n += 1
    return n


def apply_patches(get_file, set_file, get_us_file, manifest=None, root: Path = GRAPHICS, code=None, us_code=None,
                  layouts=None, check_layout=None):
    """Apply the manifest (default: every enabled fix's [[graphics]] entries). get_file/set_file work on the
    target ROM (path -> bytes), get_us_file on the USA ROM; code/us_code are CodeView-like objects for the
    code_* ops. The audited screen layouts (layout_checks.json) are checked for the default manifest, when
    `layouts` is given, or when check_layout is true (build.py: the selected fixes).
    Returns a report list (one row per patched member or code range)."""
    default_manifest = manifest is None
    manifest = load_manifest() if default_manifest else manifest
    if check_layout is None:
        check_layout = default_manifest or layouts is not None
    narcs, us_narcs, report = {}, {}, []

    def narc(path):
        if path not in narcs:
            narcs[path] = m.Narc.parse(get_file(path))
        return narcs[path]

    def us_narc(path):
        if path not in us_narcs:
            try:
                us_narcs[path] = m.Narc.parse(get_us_file(path))
            except Exception:
                us_narcs[path] = None
        return us_narcs[path]

    for op in manifest:
        if op["op"].startswith("code_"):
            row = _apply_code_op(op, code, us_code)
            if "fix" in op:
                row["fix"] = op["fix"]
            report.append(row)
            continue
        members = op.get("members", [op["member"]] if "member" in op else [int(k) for k in op.get("files", {})])
        main = op["narc"]
        for mb in members:
            orig = narc(main).files[mb]
            un = us_narc(main)
            us_member = un.files[mb] if un is not None and mb < len(un.files) else None
            new = _patched_member(op, mb, orig, us_member, root)
            validate_member_layout(orig, new, f"{main} #{mb}")
            for path in [main] + op.get("also", []):
                n = narc(path)
                before = n.files[mb]
                if path != main and n.files[mb] != orig:
                    if op["op"] != "tile_range_from_png":
                        raise ValueError(f"{path} #{mb} differs from {main} #{mb}; patch it separately")
                    # tile-range edits only need the edited range to match (the copies may differ elsewhere)
                    k = len(png_tile_strip(root / op["src"], op.get("width_tiles", 4)))
                    a, b = NCGR(orig), NCGR(n.files[mb])
                    if (a.bpp, a.tiles[op["first"]:op["first"] + k]) != (b.bpp, b.tiles[op["first"]:op["first"] + k]):
                        raise ValueError(f"{path} #{mb}: tiles {op['first']}+{k} differ from {main}; patch it separately")
                    n.files[mb] = _patched_member(op, mb, n.files[mb], us_member, root)
                else:
                    n.files[mb] = new
                validate_member_layout(before, n.files[mb], f"{path} #{mb}")
                report.append({"narc": path, "member": mb, "op": op["op"],
                               "src": op["files"][str(mb)]["src"] if "files" in op else op.get("src", "usa"),
                               "notes": op.get("notes", ""), "sha1": hashlib.sha1(n.files[mb]).hexdigest()[:12],
                               **({"fix": op["fix"]} if "fix" in op else {})})
    if check_layout:
        changed_screens = [(r["narc"], r["member"]) for r in report if "narc" in r
                           and unpack(narcs[r["narc"]].files[r["member"]])[0][:4] == b"RCSN"]
        check_layouts(lambda p: narcs[p].build() if p in narcs else get_file(p), code, rules=layouts,
                      changed_screens=changed_screens)
    for path, n in narcs.items():
        set_file(path, n.build())
    return report


# ---------------------------------------------------------------------------------------------
# review sheet / generators
# ---------------------------------------------------------------------------------------------

BATTLE_ICONS = {  # a/0/0/8 member -> label (vanilla slot; the hack's type ids map to the same members)
    219: "BEAUTY", 220: "CUTE", 221: "DRAGON", 222: "ELECTRIC", 223: "PSYCHIC", 224: "DARK", 225: "FIGHTING",
    226: "FIRE", 227: "FLYING", 228: "GHOST", 229: "GROUND", 230: "ICE", 231: "BUG", 232: "SMART", 233: "GRASS",
    234: "NORMAL", 235: "POISON", 236: "FAIRY (was ???)", 237: "ROCK", 238: "STEEL", 239: "TOUGH", 240: "COOL",
    241: "WATER", 244: "PHYSICAL", 245: "SPECIAL", 246: "STATUS"}
TYPE_ICON_PAL = 74          # a/0/0/8: 3 palettes of 16
DEX_ICONS = list(range(36, 53)) + [123]
DEX_TYPE_LIST, DEX_TYPE_LIST_PAL = 131, 130
DEX_TYPE_LIST_ORDER = ["NORMAL", "FIRE", "WATER", "GRASS", "ELECTRIC", "ROCK", "GROUND", "ICE", "FLYING",
                       "FIGHTING", "GHOST", "BUG", "POISON", "PSYCHIC", "STEEL", "DARK", "DRAGON", "FAIRY"]
NAME_TO_BATTLE = {"NORMAL": 234, "FIRE": 226, "WATER": 241, "GRASS": 233, "ELECTRIC": 222, "ROCK": 237,
                  "GROUND": 229, "ICE": 230, "FLYING": 227, "FIGHTING": 225, "GHOST": 228, "BUG": 231,
                  "POISON": 235, "PSYCHIC": 223, "STEEL": 238, "DARK": 224, "DRAGON": 221, "FAIRY": 236}


def _members(rom, path):
    return m.Narc.parse(m.get_file(rom, path)).files


def sheet(rom_path, out_png, pal_rows=None):
    """Render the battle/summary type + category icons (all 3 palette rows), the Pokédex type
    icons and the Pokédex type list of ROM to one PNG for review."""
    from PIL import Image, ImageDraw
    rom = m.load_rom(rom_path)
    b = _members(rom, "a/0/0/8")
    d = _members(rom, "a/0/6/8")
    pal = NCLR(b[TYPE_ICON_PAL])
    rows = []
    for mb, name in BATTLE_ICONS.items():
        g = NCGR(b[mb])
        ims = [render_obj(g, [(4, 2)], pal.row(r)) for r in range(3)]
        rows.append((f"a/0/0/8 #{mb} {name}", ims))
    for mb in DEX_ICONS:  # palette is chosen by code; show palette indices in grey
        rows.append((f"a/0/6/8 #{mb}", [render_obj(NCGR(d[mb]), [(4, 2), (2, 2)])]))
    lst = render_tiles(NCGR(d[DEX_TYPE_LIST]), 4, NCLR(d[DEX_TYPE_LIST_PAL]).row(0))
    sc = 3
    colw = 700
    H = sum(16 * sc + 6 for _ in rows) + 20
    S = Image.new("RGB", (colw + lst.width * sc + 40, max(H, lst.height * sc + 20)), (60, 72, 96))
    dr = ImageDraw.Draw(S)
    y = 4
    for label, ims in rows:
        dr.text((4, y + 16), label, fill=(255, 255, 160))
        x = 190
        for im in ims:
            S.paste(im.resize((im.width * sc, im.height * sc), Image.NEAREST), (x, y))
            x += im.width * sc + 8
        y += 16 * sc + 6
    dr.text((colw + 10, 4), "a/0/6/8 #131 (dex type list)", fill=(255, 255, 160))
    S.paste(lst.resize((lst.width * sc, lst.height * sc), Image.NEAREST), (colw + 10, 18))
    S.save(out_png)
    return out_png


def make_dex_type_list(us_path, cn_path, out_png, fairy_src=None):
    """Build the English version of the hack's Pokédex type-label sheet (a/0/6/8 #131, 4x40 tiles,
    one 32x16 label per 16-px row, 18 labels). Each English label is the USA battle type icon
    (same letters, same outline, same 32x16 box) recoloured with the colours of the hack's
    label in that row: letter -> 1 (white), letter shadow -> 6 (dark), border rows -> the label's
    border colour, box -> the label's fill colour. FAIRY letters come from hg-engine's FAIRY icon."""
    us = _members(m.load_rom(us_path), "a/0/0/8")
    cnrom = m.load_rom(cn_path)
    cn_d = _members(cnrom, "a/0/6/8")
    tgt = NCGR(cn_d[DEX_TYPE_LIST])
    tw = tgt.grid_width(4)
    W, H = tw * 8, len(tgt.tiles) // tw * 8

    def getpx(tiles, x, y, w=tw):
        return tiles[(y // 8) * w + x // 8][(y % 8) * 8 + x % 8]

    out = [[getpx(tgt.tiles, x, y) for x in range(W)] for y in range(H)]
    for k, name in enumerate(DEX_TYPE_LIST_ORDER):
        y0 = 16 * k
        border, fill = out[y0 + 2][1], out[y0 + 3][2]
        if name == "FAIRY" and fairy_src:
            src = NCGR(Path(fairy_src).read_bytes())
        else:
            src = NCGR(us[NAME_TO_BATTLE[name]])
        for y in range(16):
            for x in range(32):
                v = getpx(src.tiles, x, y, 4)
                if v == 0:
                    c = 0
                elif v == 15:
                    c = 1
                elif v == 14:
                    c = 6
                elif y in (1, 14):
                    c = border
                else:
                    c = fill
                out[y0 + y][x] = c
    pal = NCLR(cn_d[DEX_TYPE_LIST_PAL]).row(0)
    write_indexed_png(out_png, W, H, [v for row in out for v in row], pal)
    return out_png


# 4-px pixel letters in the style of the naming-screen tab labels (the hack's "ABC" tab and the
# USA "UPPER"/"lower" tabs): '#' = letter pixel; rows are 7 high (caps / ascenders), x-height 5.
TAB_FONT = {
    "Q": [".##.", "#..#", "#..#", "#..#", "#..#", "#.#.", ".#.#"],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "E": ["####", "#...", "#...", "###.", "#...", "#...", "####"],
    "a": ["....", "....", ".##.", "...#", ".###", "#..#", ".###"],
    "b": ["#...", "#...", "###.", "#..#", "#..#", "#..#", "###."],
    "c": ["....", "....", ".##.", "#..#", "#...", "#..#", ".##."],
}
NAMEIN_LABEL_TILES = 208          # tiles 0..207 of the naming-screen OBJ sheet: tab + BACK/OK labels
NAMEIN_TABS = {64: "QWE", 32: "abc"}  # first tile of the active tab cell -> label (dim cell = +16)
NAMEIN_TAB_COPY = {0: 64}           # tab 0 (page 0, opens first) shows the hack's own "ABC" tab art (tiles 64..95)


def draw_outlined(canvas, x0, y0, text, font=TAB_FONT, letter=7, edge=0xB, corner=4, gap=1):
    """Draw `text` into canvas (list of rows of palette indices) with the label style:
    letter pixels = `letter`, pixels orthogonally next to a letter = `edge`, diagonal-only = `corner`."""
    mask = set()
    x = x0
    for ch in text:
        rows = font[ch]
        for yy, r in enumerate(rows):
            for xx, c in enumerate(r):
                if c == "#":
                    mask.add((x + xx, y0 + yy))
        x += len(rows[0]) + gap
    for (px, py) in mask:
        canvas[py][px] = letter
    for py in range(len(canvas)):
        for px in range(len(canvas[0])):
            if (px, py) in mask:
                continue
            if any((px + dx, py + dy) in mask for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                canvas[py][px] = edge
            elif any((px + dx, py + dy) in mask for dx, dy in ((1, 1), (-1, -1), (1, -1), (-1, 1))):
                canvas[py][px] = corner
    return x - gap - x0


def make_naming_labels(us_path, cn_path, out_png):
    """English labels for the hack's (Japanese-layout) naming keyboard, OBJ sheet data/namein.narc #10
    (identical tiles 0..207 in a/0/3/1 #10 and data/clothes*/a031.narc #10):
      - the keyboard pages are rearranged by the naming-* code patches (fix naming-keyboard): page 0 (the
        page the screen opens on; was the pinyin page かな) is now ABC, page 2 (was the full-width ＡＢＣ
        page) is now a plain QWERTY page. So tab 0 gets the hack's own "ABC" tab art (copied from tab 2,
        NAMEIN_TAB_COPY), tab 2 -> "QWE" and tab 1 カナ (a-z/A-Z page) -> "abc", drawn in the tab-label
        style (white letters, dark edge, corner shading) into the hack's own boxes; the dim variant uses
        the hack's dim colour mapping (7->4, b->5, 4/6->3), 8 px to the right like the original;
      - tab 3 "1/♪" is already Latin and stays;
      - もどる / おわり buttons (tiles 128..207, same cell layout and palette row as the USA sheet) ->
        the USA BACK / OK tiles.
    Output: indexed PNG strip, 4 tiles wide, tiles 0..207 (32x32 cells read top to bottom)."""
    cn = m.Narc.parse(m.get_file(m.load_rom(cn_path), "data/namein.narc")).files
    us = m.Narc.parse(m.get_file(m.load_rom(us_path), "a/0/3/1")).files
    g, ug = NCGR(cn[10]), NCGR(us[10])
    tiles = [list(t) for t in g.tiles[:NAMEIN_LABEL_TILES]]
    tiles[128:208] = [list(t) for t in ug.tiles[128:208]]

    def cell_px(t0):
        return [[tiles[t0 + (y // 8) * 4 + x // 8][(y % 8) * 8 + x % 8] for x in range(32)] for y in range(32)]

    def put_px(t0, px):
        for y in range(32):
            for x in range(32):
                tiles[t0 + (y // 8) * 4 + x // 8][(y % 8) * 8 + x % 8] = px[y][x]

    for dst, src in NAMEIN_TAB_COPY.items():  # active cell (32 tiles incl. the dim cell at +16)
        tiles[dst:dst + 32] = [list(t) for t in g.tiles[src:src + 32]]
    dim_map = {7: 4, 0xB: 5, 4: 3, 6: 3}
    for t0, label in NAMEIN_TABS.items():
        act = cell_px(t0)
        for y in range(15, 24):             # clear the old lettering (box interior, cols 2..19)
            for x in range(2, 20):
                act[y][x] = 6
        w = sum(len(TAB_FONT[c][0]) for c in label) + len(label) - 1
        draw_outlined(act, 2 + (18 - w + 1) // 2, 16, label)
        put_px(t0, act)
        dim = cell_px(t0 + 16)
        for y in range(15, 24):
            for x in range(2, 20):
                dim[y][x + 8] = dim_map[act[y][x]]
        put_px(t0 + 16, dim)
    pal = NCLR(cn[1]).row(1)
    H = NAMEIN_LABEL_TILES // 4 * 8
    write_indexed_png(out_png, 32, H, [tiles[(y // 8) * 4 + x // 8][(y % 8) * 8 + x % 8]
                                       for y in range(H) for x in range(32)], pal)
    return out_png


# ---------------------------------------------------------------------------------------------
# Pokédex header / buttons (a/0/6/8)
# ---------------------------------------------------------------------------------------------

DEX = "a/0/6/8"
DEX_HDR_NCGR, DEX_HDR_SCREENS = 1, (0, 7, 8)          # pret: #1 on MAIN_0 with screens 0, 7 and 8
DEX_HDR_COLUMN_EDGE = 7   # overlay 7/8 column: the banner's dark column outline (screen 0 x 63) in overlay coordinates
# pret: #4 with the button screens 5-11; 69/70 (search page RESET START CANCEL / letter page OK CANCEL, labels are
# text) and 71 (list page, CRY/DETAILS greyed) are drawn with #4 too (ov5 loader 0x21F8338, members 11..92).
# Every screen that shows #4 must be listed, or retile() hands its tiles out as free (D-1505).
DEX_BTN_NCGR, DEX_BTN_SCREENS = 4, (5, 6, 9, 10, 11, 69, 70, 71)
DEX_BTN_US_SCREENS = (5, 6, 71)   # same geometry and palette rows as the USA screens: show the USA buttons
DEX_BTN_WORDS = ["AREA", "DATA", "SIZE", "FORMS", "BACK"]  # hack's 5-button area page 分布 详细 大小 样子 返回 (D-1542)


def _word_spans(img, rows, x0, x1, ink, min_gap):
    """Column spans [a, b) in x0..x1 that contain `ink` pixels in `rows`, split at gaps >= min_gap."""
    cols = [x for x in range(x0, x1) if any(img[y][x][1] in ink for y in rows)]
    spans = []
    for x in cols:
        if spans and x - spans[-1][1] < min_gap:
            spans[-1][1] = x + 1
        else:
            spans.append([x, x + 1])
    return spans


def make_dex_labels(us_path, cn_path, out_dir):
    """English Pokédex header and bottom buttons, drawn into the hack's own layout.

    Header (NCGR #1; screen 0 = top banner "全国 图鉴", screens 7/8 = the 80x24 region overlay
    "城都"/"全国" that the hack pastes over the first two characters):
      - overlay 7/8: the USA "JOHTO" / "NATIONAL" letters (from USA screens 7/8), right-aligned;
      - screen 0: the Chinese letters are removed and the USA "POKéDEX" plate part (USA screen 0,
        x 128..219) is placed right after the overlay (7 px further right than in the USA layout);
        the "NATIONAL ◀ ▶ JOHTO" switch row (y 120..135) is the USA one.
    Buttons (NCGR #4): screens 5/6/71 (list page) become the USA SEARCH/OPEN/QUIT and
      SEARCH/CRY/DETAILS/QUIT screens (same geometry); the hack's 5-button area page (screen 11)
      keeps its geometry with the USA letters AREA DATA SIZE FORMS BACK (D and T from the USA "DETAILS"); the search-page bars 69/70
      (labels are text) stay as they are, but their tiles must not be reused.
    Only tiles not referenced by the NCGR's own screens are overwritten (retile()).
    Writes <out_dir>/a068_<member>.bin for the changed members; returns {member: path}."""
    cnf = m.Narc.parse(m.get_file(m.load_rom(cn_path), DEX)).files
    usf = m.Narc.parse(m.get_file(m.load_rom(us_path), DEX)).files
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    def img(files, s, gi):
        return screen_to_image(NSCR(files[s]), NCGR(files[gi]))

    def pool(g, screens, unreferenced=True):
        # `screens` are all the screens pret draws with this NCGR, so any tile they stop using is free
        # (retile() never overwrites a tile an unchanged cell still shows); unreferenced tiles first.
        # unreferenced=False: tiles no screen shows are not free either - the code may copy them
        # directly (the search page's label windows copy #4 tiles 98/101 as their background, D-1505)
        used = set()
        for s in screens:
            sc = NSCR(cnf[s])
            for k in screen_cells(sc, g):
                used.add(sc.ents[k] & 0x3FF)
        free = [t for t in range(1, len(g.tiles)) if t not in used] if unreferenced else []
        return free + sorted(used - {0})

    def save(member, data):
        p = out_dir / f"a068_{member:04d}.bin"
        p.write_bytes(data)
        written[member] = p

    # --- header -------------------------------------------------------------------------------
    g = NCGR(cnf[DEX_HDR_NCGR])
    t0 = img(cnf, 0, DEX_HDR_NCGR)
    u0 = img(usf, 0, DEX_HDR_NCGR)
    for y in range(120, 136):                       # "NATIONAL ◀ ▶ JOHTO" switch row
        for x in range(40, 216):
            t0[y][x] = u0[y][x]
    for y in range(26, 47):                         # remove 全国 图鉴 (letters use colours 3/4/5)
        for x in range(58, 200):
            if t0[y][x][1] in (3, 4, 5):
                t0[y][x] = (t0[y][x][0], 1)
    for y in range(25, 52):                         # USA "POKéDEX" plate part, shifted right by 7
        for x in range(128, 220):
            t0[y][x + 7] = u0[y][x]
    targets = [(NSCR(cnf[0]), t0)]
    for s in (7, 8):                                # region overlay: 7 = JOHTO, 8 = NATIONAL
        t = img(cnf, s, DEX_HDR_NCGR)
        u = img(usf, s, DEX_HDR_NCGR)
        pl = t[1][10][0]
        # clean box: the overlay sits at (56, 24) over screen 0 (measured in the emulator), where the dark
        # column's outline is at overlay x 7 on every row but the last; red left of it, dark interior.
        # (Until 2026-10-05 the edge was at x 4, a 3-px dark block left of the column, D-1514.)
        ex = DEX_HDR_COLUMN_EDGE
        for y in range(0, 23):
            t[y][:ex + 1] = [(pl, 7)] * ex + [(pl, 8)]
            t[y][ex + 1:] = [(pl, 1)] * (len(t[y]) - ex - 1)
        for y in range(23, 24):
            for x in range(5, 80):
                if t[y][x][1] in (3, 4, 5):
                    t[y][x] = (pl, 1)
        ink = (3, 4, 5, 0xB)
        a, b = _word_spans(u, range(4, 22), 9, NSCR(usf[s]).w, ink, 4)[0]
        # "NATIONAL" is 81 px for a 73-px box: condense by dropping the middle column of the widest letters
        letters = [list(range(la, lb)) for la, lb in _word_spans(u, range(4, 22), a, b, ink, 1)]
        while sum(map(len, letters)) + len(letters) - 1 > 73:
            wl = max(letters, key=len)
            if len(wl) < 7:
                raise ValueError("overlay word does not fit")
            del wl[len(wl) // 2]
        cols = []
        for i, lc in enumerate(letters):
            cols += lc + ([None] if i < len(letters) - 1 else [])
        x0 = 78 - len(cols)
        for i, x in enumerate(cols):
            for y in range(4, 22):
                if x is not None and u[y][x][1] in ink:
                    t[y][x0 + i] = (pl, u[y][x][1])
        targets.append((NSCR(cnf[s]), t))
    tiles, ents = retile(g, targets, pool(g, DEX_HDR_SCREENS))
    save(DEX_HDR_NCGR, g.with_tiles(tiles))
    for (sc, _), e, s in zip(targets, ents, (0, 7, 8)):
        save(s, sc.with_entries(e))

    # --- buttons ------------------------------------------------------------------------------
    g = NCGR(cnf[DEX_BTN_NCGR])
    letters = {}
    # every letter is a USA one: the area page (screen 11, rows 12..19) and the list page's
    # SEARCH CRY DETAILS QUIT bar (screen 6, rows 22..29; D and T of "DETAILS" for the 详细 tab "DATA", D-1542)
    for s, y0, words in ((11, 12, ["AREA", "SIZE", "FORMS", "BACK"]), (6, 22, ["SEARCH", "CRY", "DETAILS", "QUIT"])):
        u = img(usf, s, DEX_BTN_NCGR)
        rows = range(y0, y0 + 8)
        spans = _word_spans(u, rows, 0, 256, (3,), 3)
        assert len(spans) == len(words), (s, spans)
        for (a, b), word in zip(spans, words):
            ls = _word_spans(u, rows, a, b, (3,), 1)
            assert len(ls) == len(word), (s, word, ls)
            for (la, lb), ch in zip(ls, word):
                letters.setdefault(ch, [[1 if u[y][x][1] == 3 else 0 for x in range(la, lb)] for y in rows])
    targets = []
    for s in DEX_BTN_SCREENS:
        if s in DEX_BTN_US_SCREENS:
            targets.append((NSCR(cnf[s]), img(usf, s, DEX_BTN_NCGR)))
            continue
        t = img(cnf, s, DEX_BTN_NCGR)
        if s == 11:
            for bi, word in enumerate(DEX_BTN_WORDS):
                bx = 12 + 48 * bi
                for y in range(11, 20):
                    bg = t[y][bx + 1]
                    for x in range(bx + 2, bx + 38):
                        t[y][x] = bg
                w = sum(len(letters[ch][0]) for ch in word) + len(word) - 1
                x = bx + (40 - w) // 2
                for ch in word:
                    gl = letters[ch]
                    for yy, row in enumerate(gl):
                        for xx, v in enumerate(row):
                            if v:
                                t[12 + yy][x + xx] = (t[12 + yy][x + xx][0], 3)
                    x += len(gl[0]) + 1
        targets.append((NSCR(cnf[s]), t))
    tiles, ents = retile(g, targets, pool(g, DEX_BTN_SCREENS, unreferenced=False))
    save(DEX_BTN_NCGR, g.with_tiles(tiles))
    for (sc, _), e, s in zip(targets, ents, DEX_BTN_SCREENS):
        if e != sc.ents:
            save(s, sc.with_entries(e))
    return written


# ---------------------------------------------------------------------------------------------
# Title subtitle (a/2/6/4): bilingual logo, removable as one manifest entry
# ---------------------------------------------------------------------------------------------

TITLE = "a/2/6/4"
TITLE_PAL, TITLE_SCREEN, TITLE_NCGR = 0, 3, 8   # logo layer: 8bpp NCGR #8 through screen #3, palette #0
TITLE_TEXT = "Origin HeartGold"
TITLE_POS = (146, 128)       # layer coordinates; the title shows the layer 10 px higher (screen x=146, y=118)
TITLE_FG, TITLE_SHADOW = 150, 240   # palette slots unused by #7, #8 and the intro frames #14-#163
TITLE_FG_RGB, TITLE_SHADOW_RGB = (31, 29, 20), (15, 10, 2)   # RGB555: gold, dark brown


def font_glyph(font: bytes, code: int):
    """(advance width, rows of 2-bit values: 0 none, 1 text, 2 shadow, 3 background) for a glyph code
    of a/0/1/6 font file (pret DecompressGlyphTile: each 8-px row is a little-endian u16, left pixel in
    the top bits)."""
    hs, wo, cnt, mw, mh, tw, th = struct.unpack_from("<IIIBBBB", font, 0)
    gsz = 16 * tw * th
    g = font[hs + (code - 1) * gsz: hs + code * gsz]
    px = [[0] * (8 * tw) for _ in range(8 * th)]
    for t in range(tw * th):
        tx, ty = (t % tw) * 8, (t // tw) * 8
        for r in range(8):
            v = struct.unpack_from("<H", g, t * 16 + r * 2)[0]
            for x in range(8):
                px[ty + r][tx + x] = (v >> (14 - 2 * x)) & 3
    return font[wo + code - 1], px


def render_font_text(text, font: bytes, charmap, fg, shadow):
    """-> rows of palette indices (None = transparent), advance-width layout like the text printer."""
    gl = [font_glyph(font, charmap.enc[ch]) for ch in text]
    w = sum(a for a, _ in gl)
    rows = [[None] * w for _ in range(len(gl[0][1]))]
    x = 0
    for adv, px in gl:
        for y, r in enumerate(px):
            for xx in range(adv):
                v = r[xx] if xx < len(r) else 0
                if v in (1, 2):
                    rows[y][x + xx] = fg if v == 1 else shadow
        x += adv
    return rows


def _nclr_with(raw: bytes, colors: dict) -> bytes:
    b, comp = unpack(raw)
    b = bytearray(b)
    off, _ = sections(bytes(b))["TTLP"]
    _, _, dsz, doff = struct.unpack_from("<IIII", b, off + 8)
    base = off + 8 + doff
    for i, (r, g, bl) in colors.items():
        assert 2 * i < dsz
        struct.pack_into("<H", b, base + 2 * i, r | g << 5 | bl << 10)
    return repack(bytes(b), comp)


def make_title_subtitle(cn_path, out_dir):
    """Bilingual title logo: "Origin HeartGold" in font 0 glyphs (gold, dark shadow) under 起源心金.
    Writes a264_0000.bin (palette + 2 colours), a264_0008.bin (logo tiles) and a264_0003.bin (logo
    screen) to out_dir; returns {member: path}."""
    rom = m.load_rom(cn_path)
    files = m.Narc.parse(m.get_file(rom, TITLE)).files
    font = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH)).files[0]
    cm = m.Charmap.load([str(TOOLS / "charmap_en.tsv")])
    g, sc = NCGR(files[TITLE_NCGR]), NSCR(files[TITLE_SCREEN])
    used = {v for t in g.tiles for v in t}
    assert TITLE_FG not in used and TITLE_SHADOW not in used
    tgt = screen_to_image(sc, g)
    text = render_font_text(TITLE_TEXT, font, cm, TITLE_FG, TITLE_SHADOW)
    x0, y0 = TITLE_POS
    for y, row in enumerate(text):
        for x, v in enumerate(row):
            if v is not None:
                tgt[y0 + y][x0 + x] = (tgt[y0 + y][x0 + x][0], v)
    shown = set()
    for k in screen_cells(sc, g):
        shown.add(sc.ents[k] & 0x3FF)
    pool = [t for t in range(1, len(g.tiles)) if t not in shown and not any(g.tiles[t])]
    tiles, (ents,) = retile(g, [(sc, tgt)], pool)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for mb, data in ((TITLE_PAL, _nclr_with(files[TITLE_PAL], {TITLE_FG: TITLE_FG_RGB, TITLE_SHADOW: TITLE_SHADOW_RGB})),
                     (TITLE_NCGR, g.with_tiles(tiles)), (TITLE_SCREEN, sc.with_entries(ents))):
        p = out_dir / f"a264_{mb:04d}.bin"
        p.write_bytes(data)
        out[mb] = p
    return out


# ---------------------------------------------------------------------------------------------
# Battle weather banners (battle/battle_graphics.narc, hack-added, hg-engine style)
# ---------------------------------------------------------------------------------------------

WEATHER_NARC = "battle/battle_graphics.narc"
# member -> (hg-engine PNG with the English label, or None, English label drawn with font 0 glyphs)
WEATHER_BANNERS = {
    33: ("8_346_sun", None), 35: ("8_349_rain", None), 37: ("8_351_sandstorm", None),
    39: ("8_353_hail", None), 41: ("8_355_fog", None),
    43: (None, "SNOW"), 45: (None, "DOWNPOUR"), 47: (None, "HARSH SUN"), 49: (None, "WINDS"),
}
WEATHER_LABEL_ROWS = range(27, 39)       # label band inside each 64x64 frame (2 frames per member)


def _read_png_rgb_indexed(path):
    """-> ((w, h), px with px[x, y] = palette index, palette as (r, g, b) tuples); no Pillow needed."""
    w, h, rows, pal = read_indexed_png(path, with_palette=True)

    class _Px:
        def __getitem__(self, xy):
            return rows[xy[1]][xy[0]]
    return (w, h), _Px(), pal


def make_weather_banners(cn_path, hge_dir, out_dir):
    """English weather banners, keeping the hack's art and colours; only the label band changes.
    SUN/RAIN/SAND/HAIL/FOG: the letters of hg-engine's English banners (rawdata/weather_icons);
    the hack's extra banners get font-0 lettering (text colour -> white, shadow -> dark grey).
    Writes <out_dir>/battle_graphics_<member>.png (indexed, the hack's palette); returns {member: path}."""
    rom = m.load_rom(cn_path)
    files = m.Narc.parse(m.get_file(rom, WEATHER_NARC)).files
    font = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH)).files[0]
    cm = m.Charmap.load([str(TOOLS / "charmap_en.tsv")])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for mb, (hge, label) in WEATHER_BANNERS.items():
        g = NCGR(files[mb])
        pal = NCLR(files[mb + 1]).colors
        W, H = 64, 128

        def near(c):
            return min(range(1, len(pal)), key=lambda j: sum((a - b) ** 2 for a, b in zip(pal[j], c)))
        white, dark = near((255, 255, 255)), near((65, 65, 65))
        img = [[g.tiles[(y // 8) * 8 + x // 8][(y % 8) * 8 + x % 8] for x in range(W)] for y in range(H)]
        for f0 in (0, 64):
            fill = img[f0 + 28][40]
            for y in WEATHER_LABEL_ROWS:            # erase the old label right of the slanted edge
                row = img[f0 + y]
                start = next((x for x in range(W) if row[x] == fill), W)
                for x in range(start, W):
                    if row[x] in (white, dark):
                        row[x] = fill
            if hge:
                (hw, hh), hp, hpal = _read_png_rgb_indexed(Path(hge_dir) / f"{hge}.png")
                for y in WEATHER_LABEL_ROWS:
                    for x in range(10, W):
                        c = hpal[hp[x, f0 + y]]
                        if c == (255, 255, 255):
                            img[f0 + y][x] = white
                        elif c == (66, 66, 66) and img[f0 + y][x] == fill:
                            img[f0 + y][x] = dark
            else:
                # compact space: 3 px instead of the font's advance
                x = 12
                for ch in label:
                    adv, px = font_glyph(font, cm.enc[ch])
                    if ch == " ":
                        x += 3
                        continue
                    for gy in range(3, 13):
                        for gx in range(adv):
                            v = px[gy][gx] if gx < len(px[gy]) else 0
                            if v in (1, 2) and x + gx < W:
                                img[f0 + 25 + gy][x + gx] = white if v == 1 else dark
                    x += adv
                if x > W:
                    raise ValueError(f"weather label {label!r} is {x - 12} px, too wide")
        p = out_dir / f"battle_graphics_{mb:04d}.png"
        write_indexed_png(p, W, H, [v for row in img for v in row], pal)
        written[mb] = p
    return written


# ---------------------------------------------------------------------------------------------
# Trainer card units (a/0/4/9 #41, screens #47 front / #48 back)
# ---------------------------------------------------------------------------------------------

TCARD = "a/0/4/9"
TCARD_NCGR = 41
# The hack dropped the USA format strings (bank 0717 has no "$…", date or W/L strings) and baked
# Chinese units next to the numbers instead. Each box (x0, y0, x1, y1) is restored to the USA
# background and gets the replacement text in font 0 (text colour 0x3E, shadow 0x3F).
TCARD_UNITS = {
    47: [((147, 48, 159, 61), ""),       # 元 after MONEY
         ((136, 72, 159, 87), ""),       # 只 after POKéDEX
         ((184, 148, 191, 158), "/"),    # 年  ADVENTURE STARTED yy/mm/dd
         ((208, 148, 215, 158), "/"),    # 月
         ((232, 148, 239, 158), "")],    # 日
    48: [((185, 13, 191, 21), "/"),      # 年  HALL OF FAME DEBUT
         ((209, 13, 215, 21), "/"),      # 月
         ((233, 13, 239, 21), ""),       # 日
         ((234, 54, 241, 61), ""),       # 回 TIMES LINKED
         ((131, 69, 139, 79), "W"),      # 胜 LINK BATTLES
         ((189, 69, 207, 79), "L"),      # 负
         ((234, 86, 241, 93), "")],      # 回 LINK TRADES
}


def make_trainer_card(us_path, cn_path, out_dir):
    rom = m.load_rom(cn_path)
    cnf = m.Narc.parse(m.get_file(rom, TCARD)).files
    usf = m.Narc.parse(m.get_file(m.load_rom(us_path), TCARD)).files
    font = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH)).files[0]
    cm = m.Charmap.load([str(TOOLS / "charmap_en.tsv")])
    g, ug = NCGR(cnf[TCARD_NCGR]), NCGR(usf[TCARD_NCGR])
    targets = []
    for s, boxes in TCARD_UNITS.items():
        sc = NSCR(cnf[s])
        t, u = screen_to_image(sc, g), screen_to_image(sc, ug)
        for (x0, y0, x1, y1), text in boxes:
            if all(t[y][x] == u[y][x] for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)):
                raise ValueError(f"trainer card screen {s}: box {(x0, y0, x1, y1)} holds no hack glyph")
            for y in range(y0, y1 + 1):
                t[y][x0:x1 + 1] = u[y][x0:x1 + 1]
            x = x0
            for ch in text:
                adv, px = font_glyph(font, cm.enc[ch])
                for gy in range(3, 13):
                    for gx in range(min(adv, len(px[gy]))):
                        v = px[gy][gx]
                        if v in (1, 2):
                            t[y0 + gy - 3][x + gx] = (t[y0 + gy - 3][x + gx][0], 0x3E if v == 1 else 0x3F)
                x += adv
        targets.append((sc, t))
    # #41 is drawn only through screens 47 and 48 (checked by rendering every screen of the NARC with
    # each NCGR: 49/50 use #42, 54/55/61 #44, 51-53 the big #43/#46), so any tile they stop using is free
    used = set()
    for sc, _ in targets:
        for k in screen_cells(sc, g):
            used.add(sc.ents[k] & 0x3FF)
    pool = [t for t in range(1, len(g.tiles)) if t not in used] + sorted(used - {0})
    tiles, ents = retile(g, targets, pool)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for mb, data in [(TCARD_NCGR, g.with_tiles(tiles))] + [(s, sc.with_entries(e)) for (sc, _), e, s in
                                                             zip(targets, ents, TCARD_UNITS)]:
        p = out_dir / f"a049_{mb:04d}.bin"
        p.write_bytes(data)
        out[mb] = p
    return out


# ---------------------------------------------------------------------------------------------
# Hack's link/capture menu bar (data/linkcapture.narc #26 through screen #25)
# ---------------------------------------------------------------------------------------------

LINKCAP = "data/linkcapture.narc"
LINKCAP_NCGR, LINKCAP_SCREEN = 26, 25
LINKCAP_LOADED_TILES = 48  # ov28 0x0225FE30: only 0x600 bytes of 4bpp character data are loaded
# (erase box x0, y0, x1, y1, background index, text, text x, text colour, shadow colour)
LINKCAP_LABELS = [
    ((12, 9, 58, 19), 4, "DETAILS", 16, 7, 8),     # align to tiles so the letters fit the runtime allocation
    ((162, 9, 191, 19), 4, "INFO", 162, 7, 8),      # (X):信息
    ((224, 9, 251, 19), 5, "EXIT", 228, 7, 9),      # (Y):退出
]


def make_linkcapture(cn_path, out_dir):
    rom = m.load_rom(cn_path)
    files = m.Narc.parse(m.get_file(rom, LINKCAP)).files
    font = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH)).files[0]
    cm = m.Charmap.load([str(TOOLS / "charmap_en.tsv")])
    g, sc = NCGR(files[LINKCAP_NCGR]), NSCR(files[LINKCAP_SCREEN])
    t = screen_to_image(sc, g)
    for (x0, y0, x1, y1), bg, text, tx, fg, sh in LINKCAP_LABELS:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                t[y][x] = (t[y][x][0], bg)
        w = sum(font_glyph(font, cm.enc[c])[0] for c in text)
        x = tx if tx is not None else x0 + (x1 - x0 + 1 - w) // 2
        for ch in text:
            adv, px = font_glyph(font, cm.enc[ch])
            for gy in range(3, 13):
                for gx in range(min(adv, len(px[gy]))):
                    if px[gy][gx] in (1, 2):
                        t[y0 + gy - 2][x + gx] = (t[y0 + gy - 2][x + gx][0], fg if px[gy][gx] == 1 else sh)
            x += adv
        if x > x1 + 2:
            raise ValueError(f"link-capture label {text!r} too wide")
    used = {sc.ents[k] & 0x3FF for k in screen_cells(sc, g)}
    allowed = set(range(1, LINKCAP_LOADED_TILES))
    pool = sorted(allowed - used) + sorted(allowed & used)
    tiles, (ents,) = retile(g, [(sc, t)], pool)
    validate_screen_tiles(NSCR(sc.with_entries(ents)), g, LINKCAP_LOADED_TILES * 32, "link-capture labels")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for mb, data in ((LINKCAP_NCGR, g.with_tiles(tiles)), (LINKCAP_SCREEN, sc.with_entries(ents))):
        p = out_dir / f"linkcapture_{mb:04d}.bin"
        p.write_bytes(data)
        out[mb] = p
    return out


# ---------------------------------------------------------------------------------------------
# Hack's in-battle field-info panel labels (battle/battle_graphics.narc #18, cells NCER #19.0/#19.1)
# ---------------------------------------------------------------------------------------------

BPANEL = "battle/battle_graphics.narc"
BPANEL_NCGR, BPANEL_NCER = 18, 19
# cell -> (erase from x, text, text x). The hack's button symbols stay exactly where they are: the (B)
# circle at x 2-9 of cell 0 and the two D-pad crosses (left/right and up/down arms lit red) at x 0-15 of
# cell 1; only the Chinese right of them is replaced. User-approved exception: the letters are font-0
# glyph pixels (text colour 3 = white, shadow 4 = grey, the hack's own label colours), packed by ink
# extent so each glyph's shadow column is the only gap, as in the game's text. Room: 22 px after the
# circle ("EXIT" = 22), 24 px after the crosses: "SWITCH" (34 px) and "Switch" (31 px) do not fit, so
# the switch label is "SWAP" (24 px). Other 24-px options: "NEXT"; "VIEW" (22).
BPANEL_LABELS = {0: (10, "EXIT", 10), 1: (16, "SWAP", 16)}
BPANEL_FG, BPANEL_SHADOW = 3, 4


def _cell_slots(objs, mapping):
    """-> {(x, y) in cell pixels: (tile index, pixel index)} for a 1D-mapped, unflipped 4bpp cell."""
    x0, y0 = min(o["x"] for o in objs), min(o["y"] for o in objs)
    out = {}
    for o in objs:
        assert not (o["hf"] or o["vf"])
        tw = o["w"] // 8
        for ty in range(o["h"] // 8):
            for tx in range(tw):
                t = (o["tile"] << mapping) + ty * tw + tx
                for i in range(64):
                    out[(o["x"] - x0 + tx * 8 + i % 8, o["y"] - y0 + ty * 8 + i // 8)] = (t, i)
    return out


def make_battle_panel_labels(cn_path, out_dir):
    """Ⓑ退出 / ✚✚切换 -> Ⓑ EXIT / ✚✚ SWAP in the hack's battle info panel. The hack's symbols, palette
    (#17), tile count and cells are kept; the letters are the ROM's font-0 glyph pixels placed by ink
    extent (each glyph's own shadow column separates it from the next). Writes battle_graphics_0018.bin."""
    rom = m.load_rom(cn_path)
    files = m.Narc.parse(m.get_file(rom, BPANEL)).files
    font = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH)).files[0]
    cm = m.Charmap.load([str(TOOLS / "charmap_en.tsv")])
    g = NCGR(files[BPANEL_NCGR])
    cells, mapping = ncer_cells(files[BPANEL_NCER])
    tiles = [list(t) for t in g.tiles]
    for c, (erase_x, text, tx) in BPANEL_LABELS.items():
        slots = _cell_slots(cells[c], mapping)
        W = max(x for x, _ in slots) + 1
        for (x, y), (t, i) in slots.items():
            if x >= erase_x:
                tiles[t][i] = 0
        x = tx
        for ch in text:
            _, px = font_glyph(font, cm.enc[ch])
            cols = [gx for gx in range(len(px[0])) if any(r[gx] in (1, 2) for r in px)]
            for gx in range(min(cols), max(cols) + 1):
                for gy in range(16):
                    v = px[gy][gx]
                    if v in (1, 2):
                        if (x, gy) not in slots:
                            raise ValueError(f"battle panel label {text!r} does not fit ({W} px cell)")
                        t, i = slots[(x, gy)]
                        tiles[t][i] = BPANEL_FG if v == 1 else BPANEL_SHADOW
                x += 1
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"battle_graphics_{BPANEL_NCGR:04d}.bin"
    p.write_bytes(g.with_tiles(tiles))
    return {BPANEL_NCGR: p}


def battle_panel_review(cn_path, new_member: bytes, out_png, scale=6):
    """Before/after sheet of the two label cells (hack palette #17), enlarged."""
    from PIL import Image
    rom = m.load_rom(cn_path)
    files = m.Narc.parse(m.get_file(rom, BPANEL)).files
    pal = NCLR(files[17]).colors
    cells, mapping = ncer_cells(files[BPANEL_NCER])
    bg = (24, 82, 148)   # palette colour 0 of #17, a stand-in for the panel behind the OBJs
    rows = []
    for g in (NCGR(files[BPANEL_NCGR]), NCGR(new_member)):
        row = []
        for c in BPANEL_LABELS:
            im = render_cell(cells[c], mapping, g, pal)
            px = im.load()
            for y in range(im.height):
                for x in range(im.width):
                    if px[x, y] == (40, 0, 40):
                        px[x, y] = bg
            row.append(im.resize((im.width * scale, im.height * scale), Image.NEAREST))
        rows.append(row)
    pad = 4 * scale
    W = pad + sum(i.width + pad for i in rows[0])
    H = pad + sum(max(i.height for i in r) + pad for r in rows)
    sheet = Image.new("RGB", (W, H), (32, 32, 32))
    y = pad
    for r in rows:
        x = pad
        for im in r:
            sheet.paste(im, (x, y))
            x += im.width + pad
        y += max(i.height for i in r) + pad
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_png)
    return out_png


def _manifest_src(p) -> str:
    """[[graphics]] "src" for a written file: relative to work/graphics when it lives there; for an
    --out elsewhere (e.g. a scratch directory) the absolute path, so printing the entry never fails."""
    p = Path(p).resolve()
    try:
        return p.relative_to(GRAPHICS.resolve()).as_posix()
    except ValueError:
        return str(p)


# Generated inputs of the [[graphics]] entries. They hold Nintendo / hack art, so they are git-ignored and rebuilt
# from the user's ROMs by regenerate() (called by build.py before the graphics stage). The generators
# are deterministic: the output is byte-identical on every run with the same ROMs.
GENERATED_OUTPUTS = ("generated", "weather_en", "dex_type_list_en.png", "naming_labels_en.png")


def regenerate(cn_path=ROM_CN, us_path=ROM_US, root: Path = GRAPHICS, log=None):
    """Run every make-* generator into `root` (default work/graphics), i.e. rebuild
    generated/*.bin, weather_en/*.png, dex_type_list_en.png and naming_labels_en.png.
    The hg-engine inputs come from <work/graphics>/vendor (kept in git). Returns the written paths."""
    root = Path(root)
    gen = root / "generated"
    vendor = GRAPHICS / "vendor" / "hg-engine"
    steps = [
        ("make-dex-type-list", lambda: [make_dex_type_list(us_path, cn_path, root / "dex_type_list_en.png",
                                                           vendor / "battle_gfx_8_236.NCGR")]),
        ("make-naming-labels", lambda: [make_naming_labels(us_path, cn_path, root / "naming_labels_en.png")]),
        ("make-dex-labels", lambda: list(make_dex_labels(us_path, cn_path, gen).values())),
        ("make-title-subtitle", lambda: list(make_title_subtitle(cn_path, gen).values())),
        ("make-weather-banners", lambda: list(make_weather_banners(cn_path, vendor / "weather_icons",
                                                                   root / "weather_en").values())),
        ("make-trainer-card", lambda: list(make_trainer_card(us_path, cn_path, gen).values())),
        ("make-linkcapture", lambda: list(make_linkcapture(cn_path, gen).values())),
        ("make-battle-panel-labels", lambda: list(make_battle_panel_labels(cn_path, gen).values())),
    ]
    written = []
    for name, run in steps:
        out = [Path(p) for p in run()]
        written += out
        if log:
            log(f"gfx {name}: {len(out)} file(s)")
    return written


def manifest_entry(narc, cn_files, written, note):
    return {"op": "member_from_file", "narc": narc,
            "files": {str(mb): {"src": _manifest_src(p),
                                "expect_sha1": hashlib.sha1(cn_files[mb]).hexdigest()[:12]}
                      for mb, p in sorted(written.items())},
            "notes": note}


def scan(cn_path, us_path, out_dir):
    """Changed/added NCGRs in the hack vs the USA ROM, rendered with US-identical tiles dimmed."""
    import ndspy.rom
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def fs(p):
        r = ndspy.rom.NintendoDSRom.fromFile(str(p))
        return {r.filenames.filenameOf(i): r.files[i] for i in range(len(r.files)) if r.filenames.filenameOf(i)}
    U, C = fs(us_path), fs(cn_path)
    rows = []
    for n in sorted(C):
        if n in U and U[n] == C[n]:
            continue
        try:
            cm = m.Narc.parse(C[n]).files
        except Exception:
            continue
        try:
            um = m.Narc.parse(U[n]).files if n in U else None
        except Exception:
            um = None
        for i, x in enumerate(cm):
            if um is not None and i < len(um) and um[i] == x:
                continue
            if magic(x) != "RGCN":
                continue
            try:
                g = NCGR(x)
            except Exception:
                continue
            ust = set()
            if um is not None and i < len(um) and magic(um[i]) == "RGCN":
                ust = {tuple(t) for t in NCGR(um[i]).tiles}
            new = [k for k, t in enumerate(g.tiles) if any(t) and tuple(t) not in ust]
            if not new:
                continue
            rows.append((n, i, len(g.tiles), len(new), um is None))
            img = render_tiles(g, g.grid_width(4 if len(g.tiles) <= 16 else 32))
            px = img.load()
            tw = img.width // 8
            newset = set(new)
            for k in range(len(g.tiles)):
                if k not in newset:
                    x0, y0 = (k % tw) * 8, (k // tw) * 8
                    for yy in range(8):
                        for xx in range(8):
                            r, gg, bb = px[x0 + xx, y0 + yy]
                            px[x0 + xx, y0 + yy] = (r // 4, gg // 4, bb // 4 + 30)
            img.save(out / f"{n.replace('/', '_')}__{i:04d}.png")
    (out / "scan.tsv").write_text("narc\tmember\ttiles\tnew_tiles\tnarc_added\n" +
                                  "\n".join("\t".join(map(str, r)) for r in rows) + "\n")
    return rows


# ---------------------------------------------------------------------------------------------
# NCER cells and the full audit (screens + cells rendered and compared with the USA ROM)
# ---------------------------------------------------------------------------------------------

OBJ_SIZES = {(0, 0): (8, 8), (0, 1): (16, 16), (0, 2): (32, 32), (0, 3): (64, 64), (1, 0): (16, 8), (1, 1): (32, 8),
             (1, 2): (32, 16), (1, 3): (64, 32), (2, 0): (8, 16), (2, 1): (8, 32), (2, 2): (16, 32), (2, 3): (32, 64)}


def ncer_cells(b: bytes):
    """-> (cells, mapping shift); each cell is a list of OAM dicts x y w h tile pal hf vf."""
    b, _ = unpack(b)
    off, _ = sections(b)["KBEC"]
    n, typ, doff, mapping = struct.unpack_from("<HHII", b, off + 8)
    base = off + 8 + doff
    esz = 16 if typ == 1 else 8
    cells = []
    for c in range(n):
        noam, _, ooff = struct.unpack_from("<HHI", b, base + c * esz)
        objs = []
        for k in range(noam):
            a0, a1, a2 = struct.unpack_from("<HHH", b, base + n * esz + ooff + k * 6)
            y, x = a0 & 0xFF, a1 & 0x1FF
            w, h = OBJ_SIZES.get((a0 >> 14, a1 >> 14), (8, 8))
            aff = a0 & 0x100
            objs.append({"x": x - 512 if x >= 256 else x, "y": y - 256 if y >= 128 else y, "w": w, "h": h,
                         "tile": a2 & 0x3FF, "pal": a2 >> 12,
                         "hf": bool(a1 >> 12 & 1) and not aff, "vf": bool(a1 >> 13 & 1) and not aff})
        cells.append(objs)
    return cells, mapping & 0xFF


def render_cell(objs, mapping, g: NCGR, pal=None):
    """One NCER cell drawn with NCGR g (1D mapping); None for an empty or oversized cell."""
    from PIL import Image
    if not objs:
        return None
    x0, y0 = min(o["x"] for o in objs), min(o["y"] for o in objs)
    W = max(o["x"] + o["w"] for o in objs) - x0
    H = max(o["y"] + o["h"] for o in objs) - y0
    if not (0 < W <= 512 and 0 < H <= 512):
        return None
    im = Image.new("RGB", (W, H), (40, 0, 40))
    px = im.load()
    for o in reversed(objs):
        tw, th = o["w"] // 8, o["h"] // 8
        start = o["tile"] << mapping if g.bpp == 4 else (o["tile"] << mapping) // 2
        for ty in range(th):
            for tx in range(tw):
                ti = start + ty * tw + tx
                t = g.tiles[ti] if ti < len(g.tiles) else [0] * 64
                for i, v in enumerate(t):
                    if not v:
                        continue
                    xx, yy = tx * 8 + i % 8, ty * 8 + i // 8
                    if o["hf"]:
                        xx = o["w"] - 1 - xx
                    if o["vf"]:
                        yy = o["h"] - 1 - yy
                    idx = o["pal"] * 16 + v if g.bpp == 4 else v
                    px[o["x"] - x0 + xx, o["y"] - y0 + yy] = (pal[idx] if pal and idx < len(pal) else GRAY[v & 15])
    return im


AUDIT_SKIP = ("a/0/0/4", "a/0/0/6", "a/0/1/8", "a/0/2/0", "a/0/5/8", "a/0/9/3", "a/1/0/9", "a/1/2/0", "a/1/7/9",
              "data/pokepic_f.narc", "data/pokepic_m.narc", "data/pokeicon.narc", "pbr/pokegra.narc",
              "extra/new_battle_bg.narc", "data/field_cutin.narc")   # sprite archives (no text)


def audit(rom_path, us_path, out_dir, max_cells=64):
    """Render every screen (NSCR) and cell (NCER) of each NARC that has a changed or added NCGR, with the
    nearest NCGR/NCLR of the same NARC, and keep only renders that differ from the USA ROM (costume copies
    data/clothesN/aXYZ.narc are compared with the ROM's own a/X/Y/Z instead). Writes contact sheets
    audit_NNN.png + audit_NNN.txt (labels) for review by eye. Also lists changed/added NCGRs (scan())."""
    import ndspy.rom
    from PIL import Image, ImageDraw
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def fs(p):
        r = ndspy.rom.NintendoDSRom.fromFile(str(p))
        return {r.filenames.filenameOf(i): r.files[i] for i in range(len(r.files)) if r.filenames.filenameOf(i)}
    U, C = fs(us_path), fs(rom_path)

    def mems(src, n):
        try:
            return m.Narc.parse(src[n]).files
        except Exception:
            return None

    def pick(ms, mags, i, kind, need=-1):
        c = [j for j, mg in enumerate(mags) if mg == kind and (kind != "RGCN" or len(NCGR(ms[j]).tiles) > need)]
        return min(c, key=lambda j: abs(j - i) + (0 if j < i else 0.5)) if c else None

    renders = []
    for n in sorted(C):
        if n in AUDIT_SKIP or (n in U and U[n] == C[n]):
            continue
        ms = mems(C, n)
        if ms is None:
            continue
        ref = mems(C, "a/" + "/".join(n.split("/")[-1][1:4])) if n.startswith("data/clothes") else mems(U, n) if n in U else None
        mags = []
        for x in ms:
            try:
                mags.append(magic(x))
            except Exception:
                mags.append("?")
        if not any(mg == "RGCN" and (ref is None or i >= len(ref) or ref[i] != ms[i]) for i, mg in enumerate(mags)):
            continue
        for i, mg in enumerate(mags):
            try:
                if mg == "RCSN":
                    sc = NSCR(ms[i])
                    gi = pick(ms, mags, i, "RGCN", max(e & 0x3FF for e in sc.ents))
                    if gi is None:
                        continue
                    pi = pick(ms, mags, gi, "RLCN")

                    def draw(f):
                        return render_screen(NSCR(f[i]), NCGR(f[gi]), NCLR(f[pi]).colors if pi is not None else None)
                    im = draw(ms)
                    try:
                        same = ref is not None and draw(ref).tobytes() == im.tobytes()
                    except Exception:
                        same = False
                    if not same:
                        renders.append((f"{n} scr{i} g{gi}", im))
                elif mg == "RECN":
                    gi = pick(ms, mags, i, "RGCN")
                    if gi is None:
                        continue
                    pi = pick(ms, mags, gi, "RLCN")
                    cells, mp = ncer_cells(ms[i])
                    g, pal = NCGR(ms[gi]), NCLR(ms[pi]).colors if pi is not None else None
                    try:
                        rcells, rmp = ncer_cells(ref[i])
                        rg, rpal = NCGR(ref[gi]), NCLR(ref[pi]).colors if pi is not None else None
                    except Exception:
                        rcells = None
                    for ci, c in enumerate(cells[:max_cells]):
                        im = render_cell(c, mp, g, pal)
                        if im is None:
                            continue
                        if rcells is not None and ci < len(rcells):
                            r = render_cell(rcells[ci], rmp, rg, rpal)
                            if r is not None and r.tobytes() == im.tobytes():
                                continue
                        renders.append((f"{n} cer{i}.{ci} g{gi}", im))
            except Exception as ex:
                print(f"skip {n} #{i}: {ex}", file=sys.stderr)
    W, H = 1100, 1500
    pages, x, y, rowh = [], 0, 0, 0
    page, labels = Image.new("RGB", (W, H), (90, 0, 90)), []
    for lab, im in renders:
        k = 2 if im.width <= 256 and im.height <= 128 else 1
        im = im.resize((im.width * k, im.height * k))
        w, h = min(im.width, W), min(im.height, H - 14)
        if x + w > W:
            x, y, rowh = 0, y + rowh + 4, 0
        if y + h + 14 > H:
            pages.append((page, labels))
            page, labels, x, y, rowh = Image.new("RGB", (W, H), (90, 0, 90)), [], 0, 0, 0
        page.paste(im.crop((0, 0, w, h)), (x, y + 12))
        ImageDraw.Draw(page).text((x + 1, y), lab, fill=(255, 255, 0))
        labels.append(lab)
        x, rowh = x + max(w, len(lab) * 6) + 8, max(rowh, h + 12)
    pages.append((page, labels))
    for k, (pg, labs) in enumerate(pages):
        pg.save(out / f"audit_{k:03d}.png")
        (out / f"audit_{k:03d}.txt").write_text("\n".join(labs) + "\n")
    return len(renders), len(pages)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--rom", default=str(ROM_CN))
    c.add_argument("--us", default=str(ROM_US))
    lc_check = sub.add_parser("check-layouts", help="check a built ROM's regenerated screen tile references")
    lc_check.add_argument("rom")
    lc_check.add_argument("--json", help="write the per-screen allocation report")
    s = sub.add_parser("sheet")
    s.add_argument("rom")
    s.add_argument("out")
    d = sub.add_parser("make-dex-type-list")
    d.add_argument("--us", default=str(ROM_US))
    d.add_argument("--rom", default=str(ROM_CN))
    d.add_argument("--fairy", default=str(GRAPHICS / "vendor" / "hg-engine" / "battle_gfx_8_236.NCGR"))
    d.add_argument("--out", default=str(GRAPHICS / "dex_type_list_en.png"))
    nl = sub.add_parser("make-naming-labels")
    nl.add_argument("--us", default=str(ROM_US))
    nl.add_argument("--rom", default=str(ROM_CN))
    nl.add_argument("--out", default=str(GRAPHICS / "naming_labels_en.png"))
    dx = sub.add_parser("make-dex-labels")
    dx.add_argument("--us", default=str(ROM_US))
    dx.add_argument("--rom", default=str(ROM_CN))
    dx.add_argument("--out", default=str(GRAPHICS / "generated"))
    ts = sub.add_parser("make-title-subtitle")
    ts.add_argument("--rom", default=str(ROM_CN))
    ts.add_argument("--out", default=str(GRAPHICS / "generated"))
    wb = sub.add_parser("make-weather-banners")
    wb.add_argument("--rom", default=str(ROM_CN))
    wb.add_argument("--hge", default=str(GRAPHICS / "vendor" / "hg-engine" / "weather_icons"))
    wb.add_argument("--out", default=str(GRAPHICS / "weather_en"))
    tc = sub.add_parser("make-trainer-card")
    tc.add_argument("--us", default=str(ROM_US))
    tc.add_argument("--rom", default=str(ROM_CN))
    tc.add_argument("--out", default=str(GRAPHICS / "generated"))
    lc = sub.add_parser("make-linkcapture")
    lc.add_argument("--rom", default=str(ROM_CN))
    lc.add_argument("--out", default=str(GRAPHICS / "generated"))
    bp = sub.add_parser("make-battle-panel-labels")
    bp.add_argument("--rom", default=str(ROM_CN))
    bp.add_argument("--out", default=str(GRAPHICS / "generated"))
    bp.add_argument("--review", help="also write a before/after PNG (needs Pillow)")
    rg = sub.add_parser("regenerate", help="run every make-* generator into work/graphics (what build.py does)")
    rg.add_argument("--us", default=str(ROM_US))
    rg.add_argument("--rom", default=str(ROM_CN))
    rg.add_argument("--out", default=str(GRAPHICS), help="root directory (default work/graphics)")
    au = sub.add_parser("audit")
    au.add_argument("--rom", default=str(ROM_CN))
    au.add_argument("--us", default=str(ROM_US))
    au.add_argument("--out", required=True)
    sc = sub.add_parser("scan")
    sc.add_argument("--rom", default=str(ROM_CN))
    sc.add_argument("--us", default=str(ROM_US))
    sc.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "check":
        rom, us = m.load_rom(a.rom), m.load_rom(a.us)
        rep = apply_patches(lambda p: m.get_file(rom, p), lambda p, b: None, lambda p: m.get_file(us, p),
                            code=CodeView(rom), us_code=CodeView(us))
        for r in rep:
            if "code" in r:
                print(f"{r['code'] + '+' + hex(r['offset']):<34} {r['op']:<16} {r['src']} ({r['length']} bytes)")
                continue
            print(f"{r['narc']:<28} #{r['member']:<4} {r['op']:<16} {r['src']}")
        print(f"{len(rep)} members OK (dry run)")
    elif a.cmd == "check-layouts":
        rom = m.load_rom(a.rom)
        rows = check_layouts(lambda p: m.get_file(rom, p), CodeView(rom))
        if a.json:
            Path(a.json).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        print(f"{len(rows)} screen/character bindings fit their audited runtime allocations")
    elif a.cmd == "sheet":
        print(sheet(a.rom, a.out))
    elif a.cmd == "make-dex-type-list":
        print(make_dex_type_list(a.us, a.rom, a.out, a.fairy))
    elif a.cmd == "make-naming-labels":
        print(make_naming_labels(a.us, a.rom, a.out))
    elif a.cmd == "make-dex-labels":
        cn = m.Narc.parse(m.get_file(m.load_rom(a.rom), DEX)).files
        e = manifest_entry(DEX, cn, make_dex_labels(a.us, a.rom, a.out),
                           "Pokedex header (JOHTO/NATIONAL POKeDEX) and bottom buttons; gfx.py make-dex-labels")
        e["also"] = ["data/clothes1/a068.narc", "data/clothes2/a068.narc"]
        print(fixreg.toml_table("graphics", e), end="")
    elif a.cmd == "make-title-subtitle":
        cn = m.Narc.parse(m.get_file(m.load_rom(a.rom), TITLE)).files
        print(fixreg.toml_table("graphics", manifest_entry(
            TITLE, cn, make_title_subtitle(a.rom, a.out),
            "OPTIONAL bilingual title: 'Origin HeartGold' under the logo; "
            "disable the fix (--without gfx-title-subtitle) to keep the Chinese-only logo; "
            "gfx.py make-title-subtitle")), end="")
    elif a.cmd == "make-weather-banners":
        for mb, p in make_weather_banners(a.rom, a.hge, a.out).items():
            print(p)
    elif a.cmd == "make-trainer-card":
        cn = m.Narc.parse(m.get_file(m.load_rom(a.rom), TCARD)).files
        e = manifest_entry(TCARD, cn, make_trainer_card(a.us, a.rom, a.out),
                           "trainer card: baked units 元 只 年月日 回 胜负 -> blank / '/' / W L; gfx.py make-trainer-card")
        e["also"] = ["data/clothes1/a049.narc", "data/clothes2/a049.narc"]
        print(fixreg.toml_table("graphics", e), end="")
    elif a.cmd == "make-linkcapture":
        cn = m.Narc.parse(m.get_file(m.load_rom(a.rom), LINKCAP)).files
        print(fixreg.toml_table("graphics", manifest_entry(
            LINKCAP, cn, make_linkcapture(a.rom, a.out),
            "hack's link/capture menu bar: 详细说明 (X):信息 (Y):退出 -> DETAILS INFO EXIT; "
            "gfx.py make-linkcapture")), end="")
    elif a.cmd == "make-battle-panel-labels":
        cn = m.Narc.parse(m.get_file(m.load_rom(a.rom), BPANEL)).files
        written = make_battle_panel_labels(a.rom, a.out)
        if a.review:
            print(battle_panel_review(a.rom, written[BPANEL_NCGR].read_bytes(), a.review), file=sys.stderr)
        print(fixreg.toml_table("graphics", manifest_entry(
            BPANEL, cn, written,
            "hack's battle info panel labels (B)退出 (+)(+)切换 -> (B)EXIT (+)(+)SWAP; "
            "font-0 letters, hack symbols/palette/cells kept (user-approved exception); "
            "gfx.py make-battle-panel-labels")), end="")
    elif a.cmd == "regenerate":
        for p in regenerate(a.rom, a.us, Path(a.out), log=lambda t: print(t, file=sys.stderr)):
            print(p)
    elif a.cmd == "audit":
        n, pages = audit(a.rom, a.us, a.out)
        print(f"{n} screens/cells differ from the USA ROM -> {pages} sheets in {a.out}")
    elif a.cmd == "scan":
        rows = scan(a.rom, a.us, a.out)
        print(f"{len(rows)} changed/added NCGRs with new tiles -> {a.out}")


if __name__ == "__main__":
    main()
