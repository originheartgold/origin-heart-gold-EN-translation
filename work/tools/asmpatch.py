#!/usr/bin/env python3
"""asmpatch - apply the code, data and strings fixes by assembling their armips sources.

A fix of kind code, data or strings (work/patches/<fix>/fix.toml) has an armips source, `asm = "<fix>.asm"`,
that writes the new bytes. fix.toml declares what it may change:
  * [[code]] regions (kinds code, data): file, offset, original bytes `expect`; every region must change;
  * [[string]] entries (kind strings): the slot of the Chinese string (`zh`, max_units + 1 code units) must
    change, and its pointer words may change (a string too long for its slot is relocated); after assembling,
    the string each entry's pointers (or its slot) lead to must be exactly the entry's `en`;
  * [[grow]] (any of these kinds): an overlay, or the ARM9 ITCM block ("itcm"), that may grow by appending,
    up to `max` bytes; the ITCM block can only grow (no [[code]] or [[string]] in it);
  * [native] (kind code): a payload (reviewed compiler output) the asm places with `.incbin`.
The build:

  1. reads the decompressed arm9 / overlay images it needs from the ROM through RomView and checks every
     region's original bytes (`expect`, the encoded `zh`, the pointers' old targets);
  2. stages them as <stage>/rom/arm9.bin, <stage>/rom/itcm.bin (the ARM9 autoload section at 0x01FF8000,
     ndspy loadArm9), <stage>/rom/overlayNN.bin next to a copy of work/patches/include (<stage>/include) and
     each [native] fix's payload bytes as <stage>/native/<fix>.bin, after its module validated them. armips
     resolves `.open`, `.include` and `.loadtable` paths against its working
     directory, which is <stage>/rom, so a source says `.open "arm9.bin", 0x02000000` and
     `.include "../include/guards.inc"`;
  3. runs armips once per fix, in build order (`armips -erroronwarning -temp <listing> <fix>.asm`). The
     source's own guards (guards.inc) check the original bytes again and stop armips, which then writes
     nothing; the listing shows every assembled line's address, and a byte written twice stops the build;
  4. after each run compares every staged file with its state before the run: a changed byte outside the
     fix's declared regions, a required region left unchanged, a file that appeared or disappeared, or a size
     change stops the build. The one size change allowed is growth by appending, of an overlay the fix
     declares in [[grow]]: at most `max` bytes, the size stays a multiple of 4, the overlay has no .bss, and
     no other overlay starts in the grown range (one that overlaps the overlay itself is never loaded with
     it, so it does not count). Strings fixes are then read back against their fix.toml `en`;
  5. writes the changed images back through RomView, which also sets a grown overlay's ramSize in the y9
     overlay table; arm9 first, then itcm, whose write rebuilds the ARM9 file with ndspy. The rebuilt main
     section may differ from the assembled arm9.bin only in the two autoload-list words, and the other
     autoload sections (DTCM) must stay as they were; a grown ITCM block must stay a multiple of 4, without
     .bss, ending at or below fixes.ITCM_LIMIT. verify() reads the result back after the ROM is written.

armips is not bundled. It is found as --armips PATH (build.py), else the ARMIPS environment variable, else
`armips` on PATH, and must report the pinned version (PINNED_VERSION). Build steps: work/notes/toolchain.md.

Synthetic assembly (`synthetic`, check.py, CI): every armips source assembled without the ROM, over
zero-filled stand-ins of the binaries (sizes from work/patches/sizes.toml, the fix.toml `expect` bytes put in
their regions) with guards.inc's guards off (`-definelabel GUARDS_OFF 1`). It catches what armips alone
finds (syntax, unknown names, .area overflows, a .string outside the table) and the build's checks that do
not need the real bytes (a byte written twice, writes outside the declared regions, growth, the strings read
back); not wrong bytes. The stand-ins are SyntheticImages: assemble() turns the guards off only for those, and
refuses any source or include that names GUARDS_OFF or GUARDS_REAL; every other run passes
`-definelabel GUARDS_REAL 1`, which keeps the guards on, so a real build always assembles with its guards.

    python3 work/tools/asmpatch.py [--rom ROM] [--armips PATH] check [--only IDS] [--without IDS]
                                         # assemble the selected fixes against the Chinese ROM (nothing written)
    python3 work/tools/asmpatch.py [--rom ROM] [--armips PATH] listing [--write | --check] [IDS...]
                                         # the disassembly snapshots work/patches/<id>/<id>.listing
                                         # (asmlisting.py): print, write, or check them (default: every fix)
    python3 work/tools/asmpatch.py [--armips PATH] synthetic
                                         # assemble every armips fix without the ROM, guards off (above)
    python3 work/tools/asmpatch.py tbl [--out work/patches/include/charmap.tbl]
                                         # the armips table file for `.string` (from charmap_en.tsv)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import fixes as fixreg  # noqa: E402

PINNED_VERSION = "v0.11.0"
INCLUDE_DIR = fixreg.PATCHES_DIR / fixreg.INCLUDE_DIR
CHARMAP_TSV = TOOLS / "charmap_en.tsv"
CHARMAP_TBL = INCLUDE_DIR / "charmap.tbl"
# English (charmap_en.tsv) + the hack's Chinese table: encodes a [[string]]'s zh and en
CHARMAPS = [str(CHARMAP_TSV), str(TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv")]
ENV_VAR = "ARMIPS"
TIMEOUT = 120
END = 0xFFFF
GUARDS_OFF_ARGS = ("-definelabel", fixreg.GUARDS_OFF, "1")      # only for SyntheticImages (synthetic())
GUARDS_REAL_ARGS = ("-definelabel", fixreg.GUARDS_REAL, "1")    # every other run: the guards stay on


class AsmError(Exception):
    pass


# --------------------------------------------------------------------------------------
# the assembler
# --------------------------------------------------------------------------------------

def find_armips(explicit=None, env=None) -> str:
    """The armips executable: `explicit` (--armips), else $ARMIPS, else `armips` on PATH."""
    env = os.environ if env is None else env
    for how, cand in (("--armips", explicit), (f"${ENV_VAR}", env.get(ENV_VAR))):
        if cand:
            cand = str(cand)
            if os.sep in cand or (os.altsep and os.altsep in cand):
                # a path: absolute, because armips runs in the staging folder (another working directory)
                path = Path(cand).expanduser().resolve()
                p = str(path) if path.is_file() and os.access(path, os.X_OK) else None
            else:
                p = shutil.which(cand)                  # a bare name: looked up on PATH
            if not p:
                raise AsmError(f"armips from {how} not found or not executable: {cand}")
            return str(Path(p).resolve())
    p = shutil.which("armips")
    if not p:
        raise AsmError(f"armips {PINNED_VERSION} not found: put it on PATH, set {ENV_VAR}=/path/to/armips or pass "
                       f"--armips (build steps: work/notes/toolchain.md); without it, build.py can only build "
                       f"with --no-hardcoded --without gfx-naming-tabs (no strings, code or data fixes, and the "
                       f"naming-tab graphics need the naming keyboard)")
    return str(Path(p).resolve())


def armips_version(path) -> str:
    """The version armips prints in its usage banner when run without arguments ("v0.11.0")."""
    try:
        r = subprocess.run([str(path)], capture_output=True, text=True, timeout=30)
    except OSError as ex:
        raise AsmError(f"cannot run armips {path}: {ex}") from None
    except subprocess.TimeoutExpired:
        raise AsmError(f"armips {path} did not print its banner within 30 s") from None
    mo = re.search(r"armips assembler (v[0-9][^\s]*)", r.stdout + r.stderr)
    if not mo:
        raise AsmError(f"{path} does not look like armips (no 'armips assembler vX' banner)")
    return mo.group(1)


def check_armips(path) -> str:
    """Raise unless `path` is the pinned armips version; return the version."""
    v = armips_version(path)
    if v != PINNED_VERSION:
        raise AsmError(f"{path} is armips {v}; this build is pinned to {PINNED_VERSION} "
                       f"(work/notes/toolchain.md)")
    return v


# --------------------------------------------------------------------------------------
# character table (`.loadtable` + `.string` in a strings fix)
# --------------------------------------------------------------------------------------

_CM = None


def charmap():
    """The msgtool charmap that encodes [[string]] zh and en (English codes + the hack's Chinese table)."""
    global _CM
    if _CM is None:
        import msgtool as m
        _CM = m.Charmap.load(CHARMAPS)
    return _CM


def charmap_tbl(tsv=CHARMAP_TSV) -> str:
    """work/patches/include/charmap.tbl: the armips table file of the game's English charmap, for `.string`
    in a fix source (`.loadtable "../include/charmap.tbl", "UTF-8"`, then `.string "OK"` writes 0x0139
    0x0135 0xFFFF). Generated from work/tools/charmap_en.tsv (the Gen-4 font charmap from pret/pokeheartgold)
    by `python3 work/tools/asmpatch.py tbl`; test_asmpatch.py checks the file is current, so do not edit it by
    hand. The file holds table lines only (no comments: armips table files have no comment syntax).
    One line per character, `<code bytes>=<character>`; armips writes an entry's hex digits as bytes in the
    order given, so the u16 code is written little-endian (0x012B 'A' -> `2B01=A`). Where several codes share
    a character the lowest is used, as msgtool encodes it; `/FFFF` is the terminator `.string` appends."""
    import msgtool as m
    cm = m.Charmap.load([str(tsv)])
    lines = []
    for text, code in sorted(cm.enc.items(), key=lambda kv: kv[1]):
        if len(text) != 1 or text in "\r\n":
            raise ValueError(f"{tsv}: code {code:#06x} is {text!r}; the table holds single characters only")
        lines.append(f"{code & 0xFF:02X}{code >> 8:02X}={text}")
    lines.append(f"/{END & 0xFF:02X}{END >> 8:02X}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# regions
# --------------------------------------------------------------------------------------

# file, start, end (file offsets); id; expect: the original bytes (None: not known without the ROM's base, or a
# SHA-1-pinned region); required: the asm must change it ([[code]] regions, string slots) or may leave it
# (string pointers); sha1: the original bytes' SHA-1 of a large [[code]] region (length + expect_sha1)
Region = namedtuple("Region", "file start end id expect required sha1", defaults=(None,))


def base_of(key, bases):
    """The RAM load address of a staged file: arm9, itcm, or an overlay from `bases` (None when unknown)."""
    if key == "itcm":
        return fixreg.ITCM_BASE
    return fixreg.ARM9_BASE if key == "arm9" else (bases or {}).get(key)


def _pack_units(units) -> bytes:
    return struct.pack(f"<{len(units)}H", *units)


def _encode(text, what):
    import msgtool as m
    try:
        return m.encode_text(text, charmap())
    except ValueError as ex:
        raise AsmError(f"{what} does not encode: {ex}") from None


def regions(fx, bases=None) -> list:
    """The Regions a fix may change: its [[code]] entries, and for each [[string]] with an en its slot
    (expect = the encoded zh, which fills the slot: max_units + 1 code units) and its pointer words (expect =
    the slot's RAM address; None when `bases` lacks the file's load address)."""
    out = []
    for e in fx.get("code", []):
        off = fixreg._int(e["offset"])
        if "expect_sha1" in e:
            out.append(Region(e["file"], off, off + e["length"], e["id"], None, True, e["expect_sha1"]))
            continue
        hw = fixreg.halfwords(e["expect"])
        out.append(Region(e["file"], off, off + 2 * len(hw), e["id"],
                          b"".join(h.to_bytes(2, "little") for h in hw), True))
    for e in fx.get("string", []):
        if not e.get("en"):
            continue                                         # en unset: the Chinese stays
        off = fixreg._int(e["offset"])
        zh = _encode(e["zh"], f"fix {fx['id']}: {e['id']} zh")
        slot = e["max_units"] + 1
        if len(zh) != slot:
            raise AsmError(f"fix {fx['id']}: {e['id']}: zh is {len(zh)} code units with its end, the slot "
                           f"max_units + 1 is {slot}")
        out.append(Region(e["file"], off, off + 2 * slot, e["id"], _pack_units(zh), True))
        base = base_of(e["file"], bases)
        for ptr in e.get("pointers", []):
            p = fixreg._int(ptr)
            out.append(Region(e["file"], p, p + 4, f"{e['id']} pointer {ptr}",
                              None if base is None else struct.pack("<I", base + off), False))
    return out


def grows(fx) -> dict:
    """{file: max bytes} of a fix's [[grow]] entries."""
    return {g["file"]: g["max"] for g in fx.get("grow", [])}


def hw_str(data: bytes) -> str:
    """Halfwords as fix.toml writes them: one as 0xNNNN, several as 'NNNN NNNN ...'."""
    units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
    return hex(units[0]) if len(units) == 1 else " ".join(f"{u:04X}" for u in units)


def _changed(old: bytes, new: bytes) -> list:
    """Offsets where two equal-length byte strings differ."""
    out = []
    step = 4096
    for i in range(0, len(old), step):
        a, b = old[i:i + step], new[i:i + step]
        if a != b:
            out += [i + j for j in range(len(a)) if a[j] != b[j]]
    return out


def _ranges(offs) -> list:
    """[(start, end)] runs of consecutive offsets."""
    runs = []
    for o in offs:
        if runs and runs[-1][1] == o:
            runs[-1][1] = o + 1
        else:
            runs.append([o, o + 1])
    return [tuple(r) for r in runs]


_LISTING_RE = re.compile(r"^([0-9A-F]{8}) (.*?)\s*; (.*) line (\d+)$")
_NO_WRITE = (".org", ".orga", ".skip", ".open", ".close", ".area", ".endarea", ".headersize", ".loadtable", ".table")
_NUM = re.compile(r"(?:0x[0-9A-Fa-f]+|\d+)\s*$")


def double_writes(listing: str) -> list:
    """Bytes an armips source writes more than once, from its -temp listing. Each listed line covers
    [its address, the next listed line's address) of the open file, except moves (.org, .skip, ...).
    Labels (`name:`, also .definelabel) and equ lines are listed at their value, not at the current
    address, so they are dropped first. Spans are keyed by file offset (address - the base of the
    `.open` / `.headersize` in effect when the line is listed), so a re-.open at another base or a
    .headersize change compares the right bytes. Returns problem strings."""
    rows, cur, base = [], None, 0
    for line in listing.splitlines():
        mo = _LISTING_RE.match(line)
        if not mo:
            continue
        addr, text, src, n = int(mo.group(1), 16), mo.group(2).strip(), mo.group(3), int(mo.group(4))
        low = text.lower()
        if low.endswith(":") or re.search(r"\bequ\b", low) or low.startswith(".definelabel"):
            continue                                    # symbols: listed at their value
        if low.startswith((".open", ".openfile", ".create", ".createfile")):
            m2 = re.search(r'"([^"]+)"', text)
            cur = m2.group(1) if m2 else text
            num = _NUM.search(text)
            base = int(num.group(0).strip(), 0) if num else 0
            continue
        if cur is None:
            continue
        rows.append((cur, addr - base, low, src, n))    # the address under the base in effect now
        if low.startswith(".close"):
            cur = None
        elif low.startswith(".headersize"):
            num = _NUM.search(text)
            base = int(num.group(0).strip(), 0) if num else base
    if not rows:
        return []                                       # nothing listed in an opened file
    spans = {}
    for (f, a, low, src, n), nxt in zip(rows, rows[1:] + [(None, 0, None, "", 0)], strict=True):
        if low.startswith(_NO_WRITE) or nxt[0] != f or nxt[1] <= a:
            continue
        spans.setdefault(f, []).append((a, nxt[1], f"{Path(src).name}:{n}"))
    problems = []
    for f, ss in spans.items():
        ss.sort()
        for (_a0, b0, w0), (a1, b1, w1) in zip(ss, ss[1:], strict=False):
            if a1 < b0:
                problems.append(f"{f}+0x{a1:X}..0x{min(b0, b1):X} written twice ({w0} and {w1})")
    return problems


def _bin(key) -> str:
    return f"{key}.bin"


def _asm(fx) -> Path:
    p = fixreg.asm_path(fx)
    if p is None or not p.is_file():
        raise AsmError(f"fix {fx['id']}: armips source {fx.get('asm')!r} not found")
    return p


# --------------------------------------------------------------------------------------
# growth and strings
# --------------------------------------------------------------------------------------

def growth_problems(fid, key, orig_len, new_len, grow_max, base, layout) -> list:
    """Problems of growing `key` from orig_len to new_len bytes (the size before the build) by appending.
    layout: {"overlayNN": (ram, ramSize, bssSize)} of every overlay in the ROM (y9 table), and "itcm":
    (ram, size, bssSize) of the ITCM autoload section. The ITCM block may grow up to fixes.ITCM_LIMIT."""
    probs = []
    if key == "itcm":
        if new_len - orig_len > grow_max:
            probs.append(f"fix {fid}: itcm.bin grew by {new_len - orig_len} bytes, its [[grow]] max is {grow_max}")
        if new_len % 4:
            probs.append(f"fix {fid}: itcm.bin grew to {new_len:#x} bytes; keep it a multiple of 4")
        if fixreg.ITCM_BASE + new_len > fixreg.ITCM_LIMIT:
            probs.append(f"fix {fid}: itcm.bin would end at {fixreg.ITCM_BASE + new_len:#x}, past "
                         f"{fixreg.ITCM_LIMIT:#x} (the ITCM reserve)")
        if layout is None or "itcm" not in layout or layout["itcm"][2]:
            probs.append(f"fix {fid}: the ITCM section is unknown or has .bss; growing it would move the .bss")
        return probs
    if new_len - orig_len > grow_max:
        probs.append(f"fix {fid}: {_bin(key)} grew by {new_len - orig_len} bytes, its [[grow]] max is {grow_max}")
    if new_len % 4:
        probs.append(f"fix {fid}: {_bin(key)} grew to {new_len:#x} bytes; keep it a multiple of 4 (.align 4)")
    if layout is None or key not in layout or base is None:
        probs.append(f"fix {fid}: {_bin(key)} grew, but its overlay-table row is unknown (cannot check .bss "
                     f"and the overlays after it)")
        return probs
    _, _, bss = layout[key]
    if bss:
        probs.append(f"fix {fid}: {key} has .bss ({bss} bytes); growing it would move its .bss")
    lo, hi = base + orig_len, base + new_len
    for other, (s, size, b) in sorted(layout.items()):
        e = s + size + b
        # an overlay that overlaps the current image can never be loaded together with it; one that
        # overlaps only the grown tail could be, so refuse
        if other != key and s < hi and e > lo and not (s < base + orig_len and e > base):
            probs.append(f"fix {fid}: {key} grown range {lo:#x}-{hi:#x} overlaps {other} ({s:#x}-{e:#x})")
    return probs


def check_strings(fx, images: dict, orig_lens: dict, bases) -> tuple:
    """Read back a strings fix's [[string]] entries after assembling: the string the pointers lead to (or the
    slot, without pointers) must be exactly `en` with its 0xFFFF end; in place it must fit the slot
    (max_units), relocated it may have at most reloc_max_units characters. Returns (rows, problems)."""
    rows, probs = [], []
    for e in fx.get("string", []):
        if not e.get("en"):
            continue
        key, off = e["file"], fixreg._int(e["offset"])
        data, base = images[key], base_of(key, bases)
        ptrs = [fixreg._int(p) for p in e.get("pointers", [])]
        try:
            want = _encode(e["en"], f"fix {fx['id']}: {e['id']} en")
        except AsmError as ex:
            probs.append(str(ex))
            continue
        if ptrs:
            targets = {struct.unpack_from("<I", data, p)[0] for p in ptrs}
            if len(targets) != 1 or base is None:
                probs.append(f"fix {fx['id']}: {e['id']}: its pointers {', '.join(e['pointers'])} disagree "
                             f"({', '.join(hex(t) for t in sorted(targets))})")
                continue
            target = targets.pop() - base
        else:
            target = off
        got = (list(struct.unpack_from(f"<{len(want)}H", data, target))
               if 0 <= target <= len(data) - 2 * len(want) else None)
        if got != want:
            probs.append(f"fix {fx['id']}: {e['id']}: {_bin(key)}+{target:#x} does not hold fix.toml en "
                         f"{e['en']!r} with its end (the asm and fix.toml disagree)")
            continue
        n = len(want) - 1
        mode = "in-place" if target == off else "relocated"
        if mode == "in-place" and n > e["max_units"]:
            probs.append(f"fix {fx['id']}: {e['id']}: {e['en']!r} is {n} characters, the slot holds {e['max_units']}")
        if mode == "relocated" and n > e.get("reloc_max_units", 0):
            probs.append(f"fix {fx['id']}: {e['id']}: {e['en']!r} is {n} characters; relocated it may have at "
                         f"most reloc_max_units = {e.get('reloc_max_units', 0)}")
        row = {"id": e["id"], "mode": mode, "addr": (base or 0) + target, "units": len(want), "en": e["en"]}
        if mode == "relocated":
            row["pointers"] = [hex(p) for p in ptrs]
        rows.append(dict(row, file=key, fix=fx["id"]))
    return rows, probs


# --------------------------------------------------------------------------------------
# assemble
# --------------------------------------------------------------------------------------

def asm_fixes(fixes) -> list:
    """The fixes among `fixes` that have an armips source (kinds strings, data, code), in build order."""
    return fixreg.code_entries_fixes(fixes)


class SyntheticImages(dict):
    """Zero-filled stand-ins for the binaries (synthetic_inputs): the only images assemble() assembles with
    the guards off. apply() never sees them: it stages the ROM's own images."""


def guards_live_problems(fixes, include_dir=INCLUDE_DIR) -> list:
    """What could switch the guards off in a real build, checked before armips runs: GUARDS_OFF named in a fix's
    source, an `.include` that is not `.include "../include/<name>.inc"` (fixes.include_form_problems), and every
    file of the include folder (fixes.lint_include_dir: .inc and .tbl only, GUARDS_OFF only in guards.inc's
    `defined(GUARDS_OFF)`). The armips symbol file is checked after each real run as well (assemble)."""
    out = fixreg.lint_include_dir(include_dir)
    for fx in fixes:
        src = _asm(fx)
        lines = src.read_text(encoding="utf-8").splitlines()
        out += fixreg.guards_off_problems(lines, f"{fx['id']}/{src.name}")
        out += fixreg.include_form_problems(lines, f"{fx['id']}/{src.name}")
    return out


def guards_off_symbols(sym_text: str) -> list:
    """Lines of an armips -sym file that define GUARDS_OFF (armips writes labels lower-case, includes too)."""
    return [ln for ln in sym_text.splitlines()
            if len(ln.split()) >= 2 and ln.split()[1].lower() == fixreg.GUARDS_OFF.lower()]


def assemble(fixes, binaries: dict, armips: str, bases=None, include_dir=INCLUDE_DIR, layout=None, listings=None):
    """Assemble the armips fixes among `fixes` (build order) over `binaries` {"arm9": bytes, "overlayNN":
    bytes}. bases: {"overlayNN": load address} (string pointers and the report's RAM column); layout:
    {"overlayNN": (ram, ramSize, bssSize)} of every overlay in the ROM, needed when a fix grows one;
    listings: a dict that receives each fix's armips -temp listing text by fix id (asmlisting.py).
    binaries: SyntheticImages (synthetic_inputs) are assembled with the guards off and without the SHA-1
    regions' checks; any other mapping holds the real images and is assembled with the guards on.
    Returns (new binaries, code rows, string rows); raises AsmError listing every problem."""
    todo = asm_fixes(fixes)
    bases = bases or {}
    synthetic = isinstance(binaries, SyntheticImages)
    guards_args = list(GUARDS_OFF_ARGS if synthetic else GUARDS_REAL_ARGS)
    live = guards_live_problems(todo, include_dir)
    if live:
        raise AsmError("refused: a source or include could switch the guards off (GUARDS_OFF, an include "
                       "outside work/patches/include, or a file there the lint does not accept):\n  "
                       + "\n  ".join(live))
    problems = []
    regs_of = {}
    natives = {}
    for fx in todo:
        regs_of[fx["id"]] = regs = regions(fx, bases)
        if fx.get("native"):
            try:
                natives[fx["id"]] = native_bytes(fx)
            except (ValueError, OSError) as ex:
                problems.append(f"fix {fx['id']}: native payload refused: {ex}")
        for r in regs:
            if r.file not in binaries:
                problems.append(f"fix {fx['id']}: region {r.id}: {r.file} was not staged")
            elif r.sha1 is not None and not synthetic:
                got = hashlib.sha1(binaries[r.file][r.start:r.end]).hexdigest()
                if r.end > len(binaries[r.file]) or got != r.sha1:
                    problems.append(f"fix {fx['id']}: region {r.id}: {r.file}+{r.start:#x}..{r.end:#x} has SHA-1 "
                                    f"{got}, expected {r.sha1} (fix.toml expect_sha1)")
            elif r.expect is not None and binaries[r.file][r.start:r.end] != r.expect:
                problems.append(f"fix {fx['id']}: region {r.id}: {r.file}+{r.start:#x} is "
                                f"{hw_str(binaries[r.file][r.start:r.end])}, expected {hw_str(r.expect)} "
                                f"(fix.toml {'expect' if r.required and fx.get('code') else 'zh / pointer'})")
        for key in grows(fx):
            if key not in binaries:
                problems.append(f"fix {fx['id']}: [[grow]] {key} was not staged")
    if problems:
        raise AsmError("fixes refused (the ROM does not hold the expected bytes):\n  " + "\n  ".join(problems))
    cur = {k: bytes(v) for k, v in binaries.items()}
    rows, srows = [], []
    with tempfile.TemporaryDirectory(prefix="asmpatch-") as td:
        stage = Path(td)
        (stage / "include").mkdir()
        for p in Path(include_dir).iterdir():                # what lint_include_dir accepted, nothing else
            if p.is_file() and p.suffix in (".inc", ".tbl"):
                shutil.copyfile(p, stage / "include" / p.name)
        if natives:
            (stage / "native").mkdir()
            for fid, blob in natives.items():
                (stage / "native" / f"{fid}.bin").write_bytes(blob)      # the asm's .incbin
        romdir = stage / "rom"
        romdir.mkdir()
        for k, v in cur.items():
            (romdir / _bin(k)).write_bytes(v)
        for fx in todo:
            src = _asm(fx)
            listing, syms = stage / "listing.txt", stage / "syms.txt"
            sym_args = [] if synthetic else ["-sym", str(syms)]   # real run: prove GUARDS_OFF stayed undefined
            for stale in (listing, syms):                     # never read a previous fix's files
                stale.unlink(missing_ok=True)
            try:
                r = subprocess.run([armips, "-erroronwarning", *guards_args, *sym_args, "-temp", str(listing),
                                    str(src)], cwd=romdir, capture_output=True, text=True, timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                raise AsmError(f"fix {fx['id']}: armips did not finish within {TIMEOUT} s") from None
            except OSError as ex:
                raise AsmError(f"fix {fx['id']}: cannot run armips {armips}: {ex}") from None
            out = (r.stdout + r.stderr).strip()
            if r.returncode != 0:
                shown = src.relative_to(fixreg.REPO) if src.is_relative_to(fixreg.REPO) else src
                raise AsmError(f"fix {fx['id']}: armips failed on {shown} (exit {r.returncode}); nothing was "
                               f"written:\n" + "\n".join("  " + line for line in out.splitlines()))
            if not synthetic:
                if not syms.is_file():
                    raise AsmError(f"fix {fx['id']}: armips wrote no symbol file; cannot prove the guards were on")
                bad = guards_off_symbols(syms.read_text(encoding="utf-8", errors="replace"))
                if bad:
                    raise AsmError(f"fix {fx['id']}: {fixreg.GUARDS_OFF} was defined while assembling against the "
                                   f"ROM, so the guards were off; refused, nothing written: {'; '.join(bad)}")
            if not listing.is_file():
                raise AsmError(f"fix {fx['id']}: armips wrote no listing; cannot check its writes")
            listing_text = listing.read_text(encoding="utf-8-sig", errors="replace")
            if listings is not None:
                listings[fx["id"]] = listing_text
            twice = double_writes(listing_text)
            if twice:
                raise AsmError(f"fix {fx['id']}: the asm writes the same bytes more than once (the later write "
                               f"wins silently):\n  " + "\n  ".join(twice))
            names = {p.name for p in romdir.iterdir()}
            want_names = {_bin(k) for k in cur}
            if names != want_names:
                raise AsmError(f"fix {fx['id']}: armips created or removed files: "
                               f"{sorted(names ^ want_names)} (a fix only patches the staged binaries)")
            regs = regs_of[fx["id"]]
            may_grow = grows(fx)
            touched = {r_.id: False for r_ in regs}
            new = {}
            for k in cur:
                data = (romdir / _bin(k)).read_bytes()
                old = cur[k]
                if len(data) != len(old):
                    if k not in may_grow or len(data) < len(old):
                        problems.append(f"fix {fx['id']}: {_bin(k)} changed size {len(old):#x} -> {len(data):#x}"
                                        f"{'' if k in may_grow else ' (no [[grow]] for it in fix.toml)'}")
                        continue
                    problems += growth_problems(fx["id"], k, len(binaries[k]), len(data), may_grow[k],
                                                base_of(k, bases), layout)
                if data == old:
                    continue
                mine = [r_ for r_ in regs if r_.file == k]
                outside = []
                for o in _changed(old, data[:len(old)]):     # per byte: adjacent regions count as one
                    hit = [r_ for r_ in mine if r_.start <= o < r_.end]
                    for r_ in hit:
                        touched[r_.id] = True
                    if not hit:
                        outside.append(o)
                for a, b in _ranges(outside):
                    ram = fixreg._ram(k, a, bases)
                    problems.append(f"fix {fx['id']}: {_bin(k)}+{a:#x}..{b:#x}"
                                    f"{f' (RAM 0x{ram:08X})' if ram is not None else ''} changed, outside "
                                    f"every region the fix declares in fix.toml")
                new[k] = data
            for r_ in regs:
                if r_.required and not touched[r_.id] and not (synthetic and r_.sha1 is not None):
                    problems.append(f"fix {fx['id']}: region {r_.id} declared in fix.toml, but the asm left it "
                                    f"unchanged")
            if not problems and fx.get("string"):
                s_rows, s_probs = check_strings(fx, {**cur, **new}, {k: len(v) for k, v in binaries.items()}, bases)
                srows += s_rows
                problems += s_probs
            if problems:
                raise AsmError("fixes refused:\n  " + "\n  ".join(problems))
            for r_ in regs:
                if fx.get("code"):
                    data = new.get(r_.file, cur[r_.file])
                    if r_.sha1 is not None:                         # a large region: its SHA-1 before and after
                        old, now = f"sha1:{r_.sha1}", f"sha1:{hashlib.sha1(data[r_.start:r_.end]).hexdigest()}"
                    else:
                        old, now = hw_str(r_.expect), hw_str(data[r_.start:r_.end])
                    row = {"id": r_.id, "file": r_.file, "offset": hex(r_.start), "old": old, "new": now,
                           "fix": fx["id"], "engine": "armips"}
                    if r_.sha1 is not None:
                        row["length"] = r_.end - r_.start
                    rows.append(row)
            cur.update(new)
    return cur, rows, srows


def native_bytes(fx) -> bytes:
    """A fix's native payload bytes, validated by its [native] module (schema, source digest, reviewed pin)."""
    import importlib
    module = fx["native"]["module"]
    if module not in fixreg.NATIVE_MODULES:
        raise ValueError(f"unknown [native] module {module!r}")
    payload = importlib.import_module(module).load_payload()
    return bytes.fromhex(payload["code"])


def staged_keys(fixes) -> list:
    """The files (arm9, itcm, overlayNN) the armips fixes among `fixes` change: their [[code]] regions,
    [[string]] entries and [[grow]] files. In write-back order: arm9 before itcm (writing itcm rebuilds the
    ARM9 file around the main section), then the overlays."""
    keys = set()
    for fx in asm_fixes(fixes):
        keys |= {e["file"] for t in ("code", "string", "grow") for e in fx.get(t, [])}
    order = {"arm9": 0, "itcm": 1}
    return sorted(keys, key=lambda k: (order.get(k, 2), int(k[7:]) if k.startswith("overlay") else 0))


def arm9_bookkeeping(old: bytes, new: bytes, main_len: int, settings_offs: int) -> list:
    """Offsets where `new` (the ARM9 file ndspy wrote after the ITCM section grew) differs from `old` (the
    assembled arm9.bin) inside the main section, other than the two code-settings words ndspy rewrites
    (autoload list start and end, at settings_offs and settings_offs + 4)."""
    allowed = set(range(settings_offs, settings_offs + 8))
    return [o for o in _changed(old[:main_len], new[:main_len]) if o not in allowed]


def stage_inputs(rom, fixes) -> tuple:
    """(RomView, binaries, bases, layout) for assemble(): the images of the files the armips fixes among `fixes`
    change (staged_keys), their load addresses and the overlay layout of the ROM."""
    import hardcoded
    view = hardcoded.RomView(rom)
    keys = staged_keys(fixes)
    try:
        binaries = {k: view.get(k) for k in keys}
    except hardcoded.HardcodedError as ex:
        raise AsmError(str(ex)) from None
    bases = {k: view.base(k) for k in keys if k != "arm9"}
    layout = {f"overlay{i}": (o.ramAddress, o.ramSize, o.bssSize) for i, o in view.ovs.items()}
    if "itcm" in keys:
        sec = view.itcm_section()
        layout["itcm"] = (sec.ramAddress, len(sec.data), sec.bssSize)
    return view, binaries, bases, layout


def apply(rom, fixes, armips: str, dry_run=False) -> dict:
    """Assemble the armips fixes among `fixes` into an ndspy ROM. Returns {"code_regions": rows, "strings":
    rows, "files": {key: sha1[:12]} of the changed files, "armips": {...}}; raises AsmError (nothing written)."""
    view, binaries, bases, layout = stage_inputs(rom, fixes)
    new, rows, srows = assemble(fixes, binaries, armips, bases, layout=layout)
    changed = {k: v for k, v in new.items() if v != binaries[k]}
    final = dict(changed)
    autoload_before = [(s.ramAddress, bytes(s.data), s.bssSize) for s in rom.loadArm9().sections[1:]
                       if s.ramAddress != fixreg.ITCM_BASE] if "itcm" in changed else None
    if not dry_run:
        for k, v in changed.items():                        # staged_keys order: arm9, itcm, overlays
            view.set(k, v)
        if "itcm" in changed:
            # ndspy rebuilt the ARM9 file: only its autoload bookkeeping may differ from the assembled arm9.bin
            code = rom.loadArm9()
            main_len = len(code.sections[0].data)
            got = view.get("arm9")
            bad = arm9_bookkeeping(changed.get("arm9", binaries["arm9"]), got, main_len, code.codeSettingsOffs)
            if bad:
                raise AsmError(f"arm9: writing the grown ITCM section changed main-section bytes outside the "
                               f"autoload bookkeeping: {', '.join(f'+{a:#x}' for a, _ in _ranges(bad))}")
            after = [(s.ramAddress, bytes(s.data), s.bssSize) for s in code.sections[1:]
                     if s.ramAddress != fixreg.ITCM_BASE]
            if after != autoload_before:
                raise AsmError("arm9: writing the grown ITCM section changed another autoload section (DTCM)")
            final["arm9"] = got
            final["itcm"] = view.get("itcm")
    return {"code_regions": rows, "strings": srows,
            "files": {k: hashlib.sha1(v).hexdigest()[:12] for k, v in final.items()},
            "grown": {k: {"from": len(binaries[k]), "to": len(v)} for k, v in changed.items()
                      if len(v) != len(binaries[k])},
            "armips": {"path": armips, "version": armips_version(armips)}}


def synthetic_inputs(fixes, root=fixreg.PATCHES_DIR) -> tuple:
    """(SyntheticImages, bases, layout) for assemble() without the ROM: every file the armips fixes among
    `fixes` stage (staged_keys), zero-filled to its size in sizes.toml, with each region's fix.toml `expect`
    bytes (the encoded zh of a string slot, a pointer's old target) in place; the RAM bases from overlays.toml;
    the layout of the staged overlays and ITCM only (the build checks growth against every overlay)."""
    sizes, bases = fixreg.load_sizes(root), fixreg.load_overlays(root)
    keys = staged_keys(fixes)
    missing = [k for k in keys if k not in sizes]
    if missing:
        raise AsmError(f"{', '.join(missing)}: no size in work/patches/{fixreg.SIZES_TOML} (regenerate it with the "
                       f"ROM: python3 work/tools/fixes.py overlays)")
    images = {k: bytearray(sizes[k]["size"]) for k in keys}
    for fx in asm_fixes(fixes):
        for r in regions(fx, bases):
            if r.expect is not None and r.file in images:
                if r.end > len(images[r.file]):
                    raise AsmError(f"fix {fx['id']}: region {r.id} ends at {r.file}+{r.end:#x}, past its size in "
                                   f"{fixreg.SIZES_TOML} ({len(images[r.file]):#x})")
                images[r.file][r.start:r.end] = r.expect
    layout = {k: (bases.get(k), sizes[k]["size"], sizes[k]["bss"]) for k in keys if k.startswith("overlay")}
    if "itcm" in keys:
        layout["itcm"] = (fixreg.ITCM_BASE, sizes["itcm"]["size"], sizes["itcm"]["bss"])
    images = SyntheticImages({k: bytes(v) for k, v in images.items()})
    return images, {k: bases[k] for k in keys if k in bases}, layout


def synthetic(armips, all_fixes=None, root=fixreg.PATCHES_DIR) -> str:
    """Assemble every armips fix without the ROM (synthetic_inputs, guards off): the enabled ones together in
    build order, as the build does, then every disabled one alone. Raises AsmError; returns a summary."""
    all_fixes = fixreg.load_all(root) if all_fixes is None else all_fixes
    enabled = asm_fixes(fixreg.select(all_fixes))
    disabled = [fx for fx in asm_fixes(all_fixes) if fx not in enabled]
    n_regions = n_strings = 0
    for run in ([enabled] if enabled else []) + [[fx] for fx in disabled]:
        images, bases, layout = synthetic_inputs(run, root)
        _new, rows, srows = assemble(run, images, armips, bases, layout=layout)
        n_regions, n_strings = n_regions + len(rows), n_strings + len(srows)
    return (f"{len(enabled) + len(disabled)} armips fixes assembled without the ROM ({len(enabled)} enabled "
            f"together, {len(disabled)} disabled alone), guards off: {n_regions} code/data regions, "
            f"{n_strings} strings")


def verify(rom, report) -> str:
    """Re-read a written ROM against apply()'s report (build.py stage 5): every changed file has the SHA-1
    apply() produced, every overlay that grew has its new size and the same y9 ramSize, every string is
    where the report says and its pointers point at it, and every [[code]] region holds its new bytes."""
    import hardcoded
    import msgtool as m
    view = hardcoded.RomView(rom)
    for key, h in report.get("files", {}).items():
        data = view.get(key)
        got = hashlib.sha1(data).hexdigest()[:12]
        if got != h:
            raise AsmError(f"{key}: sha1 {got} != {h}")
    for key, g in report.get("grown", {}).items():
        size = len(view.get(key))
        if key == "itcm":
            if size != g["to"]:
                raise AsmError(f"itcm: grew {g['from']:#x} -> {g['to']:#x}, but the section is {size:#x} bytes")
            continue
        if size != g["to"] or view.table_ram_size(int(key[7:])) != size:
            raise AsmError(f"{key}: grew {g['from']:#x} -> {g['to']:#x}, but the file is {size:#x} bytes and its "
                           f"y9 ramSize {view.table_ram_size(int(key[7:])):#x}")
    for r in report.get("strings", []):
        data = view.get(r["file"])
        base = view.base(r["file"])
        want = m.encode_text(r["en"], charmap())
        off = r["addr"] - base
        if list(struct.unpack_from(f"<{len(want)}H", data, off)) != want:
            raise AsmError(f"{r['id']}: English not found at {r['addr']:#x}")
        for p in r.get("pointers", []):
            if struct.unpack_from("<I", data, int(p, 16))[0] != r["addr"]:
                raise AsmError(f"{r['id']}: pointer {p} not repointed")
    # "code_patches": the same rows in build reports written before 2026-10-08 (artifact_check reads them)
    code_rows = report.get("code_regions", report.get("code_patches", []))
    for r in code_rows:
        off = int(r["offset"], 16)
        if r["new"].startswith("sha1:"):
            got = hashlib.sha1(view.get(r["file"])[off:off + r["length"]]).hexdigest()
            if f"sha1:{got}" != r["new"]:
                raise AsmError(f"code region {r['id']}: {r['file']}+{r['offset']} has {got}, not {r['new']}")
            continue
        want = b"".join(h.to_bytes(2, "little") for h in fixreg.halfwords(r["new"]))
        if view.get(r["file"])[off:off + len(want)] != want:
            raise AsmError(f"code region {r['id']}: {r['file']}+{r['offset']} is not {r['new']}")
    return f"ok ({len(report.get('strings', []))} strings, {len(code_rows)} code regions)"


# --------------------------------------------------------------------------------------

def listing_cli(a, armips):
    """asmpatch.py listing: print, write or check the disassembly snapshots of the named fixes (default all)."""
    import asmlisting
    import msgtool as m
    all_fixes = fixreg.load_all()
    by_id = {f["id"]: f for f in all_fixes}
    for fid in a.ids:
        if fid not in by_id:
            sys.exit(f"unknown fix {fid!r}")
        if not asm_fixes([by_id[fid]]):
            sys.exit(f"fix {fid!r} has no armips source")
    chosen = [by_id[i] for i in a.ids] if a.ids else asm_fixes(all_fixes)
    try:
        asmlisting.capstone_version()
        rom = m.load_rom(a.rom)
        fixreg.check_overlay_bases(rom)
        texts = asmlisting.snapshots(asmlisting.assemble_each(rom, chosen, armips), armips_version(armips))
    except asmlisting.ListingError as ex:
        sys.exit(str(ex))
    if a.check:
        probs = asmlisting.stale(chosen if a.ids else all_fixes, texts)
        for p in probs:
            print(p)
        print(f"{'stale' if probs else 'ok'}: {len(texts)} snapshots" + (f", {len(probs)} problems" if probs else ""))
        return 1 if probs else 0
    for fid, text in texts.items():
        if a.write:
            path = asmlisting.listing_path(by_id[fid])
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(fixreg.REPO)}")
        else:
            print(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--armips", help=f"armips executable (default: ${ENV_VAR}, then PATH)")
    ap.add_argument("--rom", default=str(fixreg.ROM_CN))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="assemble the selected armips fixes against the ROM (dry run)")
    p.add_argument("--only")
    p.add_argument("--without")
    p = sub.add_parser("listing", help="the disassembly snapshots (asmlisting.py): print, --write or --check")
    p.add_argument("ids", nargs="*", help="fix ids (default: every armips fix)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true", help="write work/patches/<id>/<id>.listing")
    g.add_argument("--check", action="store_true", help="exit 1 when a committed snapshot is stale")
    sub.add_parser("synthetic", help="assemble every armips fix without the ROM, over zero-filled stand-ins, "
                                     "guards off (syntax, .area overflows, regions; not the bytes)")
    p = sub.add_parser("tbl", help="write the armips table file (charmap.tbl) from charmap_en.tsv")
    p.add_argument("--out", default=str(CHARMAP_TBL))
    a = ap.parse_args(argv)
    if a.cmd == "tbl":
        Path(a.out).write_text(charmap_tbl(), encoding="utf-8")
        print(f"wrote {a.out}")
        return
    import msgtool as m
    try:
        armips = find_armips(a.armips)
        check_armips(armips)
        if a.cmd == "listing":
            return listing_cli(a, armips)
        if a.cmd == "synthetic":
            print("ok: " + synthetic(armips))
            return 0
        act = fixreg.active_fixes(a.only, a.without)
        rom = m.load_rom(a.rom)
        fixreg.check_overlay_bases(rom)
        rep = apply(rom, act, armips, dry_run=True)
    except (AsmError, fixreg.FixError) as ex:
        sys.exit(str(ex))
    for r in rep["code_regions"]:
        print(f"  {r['fix']:22s} {r['id']:28s} {r['file']}+{r['offset']}: {r['old']} -> {r['new']}")
    for r in rep["strings"]:
        print(f"  {r['fix']:22s} {r['id']:28s} {r['mode']:9s} -> {r['addr']:#010x}  {r['en']!r}")
    print(f"ok: {len({r['fix'] for r in rep['code_regions'] + rep['strings']})} fixes, "
          f"{len(rep['code_regions'])} code/data regions, {len(rep['strings'])} strings "
          f"(armips {rep['armips']['version']})")


if __name__ == "__main__":
    sys.exit(main())
