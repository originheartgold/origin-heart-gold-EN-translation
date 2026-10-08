#!/usr/bin/env python3
"""fixes - the registry of every change the build makes to the Chinese ROM besides the message text.

One folder per logical fix: work/patches/<fix-id>/fix.toml (read with the stdlib tomllib). build.py,
asmpatch.py, hardcoded.py and gfx.py read their patch entries only through this module, so a fix is switched on or
off in one place (`enabled`, or build.py --only/--without) and documents itself (why/what/decisions).
work/patches/FIXES.md is generated from these files:  python3 work/tools/fixes.py docs --out work/patches/FIXES.md

fix.toml
    id          = "namelen"                 must equal the folder name; [a-z0-9-]
    title       = "..."                     one line
    kind        = "code" | "data" | "strings" | "graphics" | "font"
                  code: instructions (immediates, branches); data: tables inside code files;
                  strings: hardcoded text outside the message NARCs; graphics: NARC members or tile data
                  inside code; font: glyphs in the font NARC
    enabled     = true | false              false: the build leaves this fix out unless --only names it
    decisions   = ["D-0858", ...]           decision-register ids (checked against decisions.jsonl)
    requires    = ["naming-keyboard", ...]  fixes that must be in the same build ("only makes sense with");
                                            not an apply order (stages run font, graphics, strings, code/data)
    why         = '''...'''                 the symptom in the untouched Chinese hack: player-facing first,
                                            then the technical cause
    what        = '''...'''                 old -> new behaviour
    evidence    = ["work/notes/....md: section", "CHANGELOG.md: ...", ...]
    asm         = "namelen.asm"             kinds code, data and strings only (required there): the armips source
                                            in the fix's folder that writes the new bytes (see asmpatch.py and
                                            work/notes/toolchain.md)
    [native]    source = "native.c"         kind code only: C code compiled into a payload that the asm places with
                headers = ["labels.h"]      `.incbin "../native/<fix-id>.bin"`. payload: the reviewed compiler
                payload = "payload.json"    output in the fix's folder ({source_sha256, base, code (hex), symbols});
                module = "text_speed_patch" module (one of NATIVE_MODULES) validates it (schema, source digest,
                                            the reviewed sha256 pin) and reproduces it with clang. The asm names
                                            every symbol with `.definelabel <name>, <address>` (Thumb bit clear);
                                            `check` compares them with payload.json.

  Entries (arrays of tables; a fix uses the ones of its kind):
    [[code]]      the regions a code/data fix may change (kinds code, data). Keys: id, file ("arm9" |
                  "overlayNN"), offset ("0x4E", file offset; arm9/overlays: offset in the RAM image), expect,
                  notes. expect: the original bytes of the region, as one halfword written 0x + 1-4 hex digits
                  ("0x2305") or a run of 2+ halfwords of exactly 4 hex digits each ("01DE 012B ..."); anything
                  else is refused (a bare "2320" is ambiguous). A large region (an overlay a fix rewrites in
                  many places) may give `length` (bytes) and `expect_sha1` (SHA-1 of its original bytes)
                  instead of expect; its source still guards every edit. The new bytes are not here: the fix's `asm`
                  writes them. The build checks expect before it assembles, the asm guards the same bytes
                  itself, and after assembling the build refuses any changed byte outside the fix's regions
                  and any region the asm left unchanged.
    [[string]]    hardcoded strings (kind strings). Keys: id ("<file>:<offset>"), file ("arm9" | "overlayNN"),
                  offset (the slot), zh (the Chinese the slot holds: max_units characters + its 0xFFFF end
                  fill the slot exactly), en (the English the fix's asm writes, or unset = keep the Chinese),
                  max_units, optional pointers (offsets of the 32-bit pointers to the slot), reloc_max_units
                  (longest English when relocated), context, notes. The asm writes the bytes (`.string` with
                  include/charmap.tbl); `check` requires its `.string` literals to be exactly the entries'
                  en values, and the build reads the result back against en. The entries also feed
                  translators and the text checks (text_consumer_check.py, text_safety_check.py).
    [[grow]]      an overlay, or the ARM9 ITCM block ("itcm", staged as itcm.bin at 0x01FF8000, at most up to
                  ITCM_LIMIT), the fix's asm may grow by appending (kinds code, data, strings). Keys: file
                  ("overlayNN" | "itcm"), max (bytes), notes. One fix per file; see asmpatch.py for the checks.
    [[graphics]]  graphics operations (kind graphics). Keys: op plus that op's fields, see gfx.py and
                  GRAPHICS_OPS below; notes.
    [[font]]      glyph restores (kind font). Keys: narc, fonts, codes, source ("usa"), notes.

work/patches/overlays.toml
    The RAM load address of every overlay a fix touches ([overlayNN] ram = 0x...), read from the y9 overlay
    table of the Chinese ROM by `fixes.py overlays --rom ROM`. Addresses only, no game data; FIXES.md uses it
    for RAM addresses, build.py checks it against the ROM it loads, and `check` checks every `.open` in a
    fix's asm against it (armips sources use RAM addresses: `.open "overlay49.bin", 0x021E4980`).

work/patches/include/
    Shared armips includes (guards.inc: the guard macros; charmap.inc: character-code constants;
    charmap.tbl: the armips table for `.string`, generated by `asmpatch.py tbl`).
    Not a fix; the only subfolder of work/patches without a fix.toml.

Every other direct subfolder of work/patches must be a fix (have a fix.toml); a fix may keep extra files
(assets, its .asm) inside its own folder.

Checks (`check`, and every load the build does): unknown keys, wrong types (also of list elements),
malformed halfwords, duplicate fix or entry ids, id != folder, folders without fix.toml, unknown decisions,
missing requires, dependency cycles, overlays without a RAM base, a code/data fix without its asm file, an
asm `.open` of a file the fix declares no region in or at the wrong load address, an asm `.create`/`.createfile`/
`.headersize`, a strings fix whose asm `.string` literals differ from its [[string]] en values, a [[grow]] of
a file the fix does not open, and two entries (in any fixes) touching the same bytes / NARC member / glyph /
grown overlay.

Blind spots of the overlap check: it compares entries only within one namespace and granularity:
  * code bytes are keyed by "arm9" / "overlayNN" (byte ranges);
  * NARC members by "<narc path>#<member>" (the whole member, whatever op touches it);
  * glyphs by "<font narc>#<font file>:glyph" (one code), so a [[graphics]] op that replaced a whole
    font member would not be seen to overlap a [[font]] glyph in it;
  * [[string]] entries are byte ranges in arm9 / overlays, like [[code]]; a [[grow]] is one key per overlay,
    so two fixes cannot grow the same overlay.
Today no fix is in these situations (font only in font-glyphs).

CLI
    python3 work/tools/fixes.py list
    python3 work/tools/fixes.py show <id>
    python3 work/tools/fixes.py check [--only IDS] [--without IDS]
    python3 work/tools/fixes.py docs --out work/patches/FIXES.md
    python3 work/tools/fixes.py overlays [--rom CN.nds]      regenerate work/patches/overlays.toml
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
REPO = WORK.parent
PATCHES_DIR = WORK / "patches"
OVERLAYS_TOML = "overlays.toml"
INCLUDE_DIR = "include"                 # work/patches/include: shared armips includes, not a fix
ARM9_BASE = 0x02000000
DECISIONS_JSONL = WORK / "translate" / "decisions" / "decisions.jsonl"
ROM_CN = WORK / "rom" / "origin_v4.0.3_cn.nds"

KINDS = ("font", "graphics", "strings", "data", "code")       # also the stage order of the build
ENTRY_TABLES = {"code": "code", "data": "code", "strings": "string", "graphics": "graphics", "font": "font"}
STRS, INTS = ("list", str), ("list", int)       # list element types
TABLES, TABLE_MAP = ("list", dict), ("dict", dict)   # [[entries]] and [name.<key>] sub-tables
TOP_KEYS = {"id": str, "title": str, "kind": str, "enabled": bool, "decisions": STRS, "requires": STRS,
            "why": str, "what": str, "evidence": STRS, "asm": str, "native": dict,
            "code": TABLES, "string": TABLES, "grow": TABLES, "graphics": TABLES, "font": TABLES}
REQUIRED_TOP = ("id", "title", "kind", "enabled", "decisions", "requires", "why", "what", "evidence")
ASM_KINDS = ("strings", "data", "code")  # kinds whose new bytes come from an armips source
# Python modules (work/tools/<name>.py) that validate a fix's native payload ([native] module = ...)
NATIVE_MODULES = ("text_speed_patch",)
NATIVE_KEYS = {"source": str, "headers": STRS, "payload": str, "module": str}
NATIVE_REQUIRED = ("source", "payload", "module")
ASM_DEFINELABEL_RE = re.compile(r"^\s*\.definelabel\s+(\w+)\s*,\s*(0x[0-9A-Fa-f]+)\s*(?:;.*)?$", re.I)
ASM_INCBIN_RE = re.compile(r'^\s*(?:\w+:\s*)?\.incbin\s+"([^"]+)"', re.I)
# The ARM9 ITCM autoload block (file key "itcm", staged as itcm.bin): its RAM address, and how far a fix may
# grow it: 0x01FFA000 is the text-speed release candidate's budget for native code (its MAX_PAYLOAD_SIZE), not
# a hardware boundary (ITCM is 32 KiB at 0x01FF8000; DTCM is the autoload section at 0x027E0000). A fix may
# only append to the block ([[grow]] itcm); [[code]] / [[string]] entries in it are refused, so its original
# bytes can only change with a new review.
ITCM_BASE = 0x01FF8000
ITCM_LIMIT = 0x01FFA000

CODE_KEYS = {"id": str, "file": str, "offset": str, "expect": str, "length": int, "expect_sha1": str,
             "notes": str}
CODE_REQUIRED = ("id", "file", "offset", "notes")         # plus expect, or length + expect_sha1
SHA1_RE = re.compile(r"[0-9a-f]{40}")
CODE_FILE_RE = re.compile(r"arm9|overlay\d+")   # [[code]] / [[string]] files; "itcm" only grows ([[grow]])
# `.open "<file>.bin", 0x<load address>` in a fix's asm (comments allowed after it)
ASM_OPEN_RE = re.compile(r'^\s*\.open\s+"([^"]+)"\s*,\s*(0x[0-9A-Fa-f]+)\s*(?:;.*)?$', re.I)
STRING_KEYS = {"id": str, "file": str, "offset": str, "zh": str, "en": str, "max_units": int,
               "pointers": STRS, "reloc_max_units": int, "context": str, "notes": str}
STRING_REQUIRED = ("id", "file", "offset", "zh", "max_units")
GROW_KEYS = {"file": str, "max": int, "notes": str}
GROW_REQUIRED = ("file", "max")
# `.string "..."` / `.stringn` / `.str` literals in an asm, optionally after a label (armips escapes: \\ \")
ASM_STRING_RE = re.compile(r'^\s*(?:\w+:\s*)?\.(?:stringn|string|str)\s+"((?:[^"\\]|\\.)*)"\s*(?:;.*)?$', re.I)
# any .string / .stringn / .str directive (to refuse the forms ASM_STRING_RE does not read)
ASM_STRING_DIRECTIVE_RE = re.compile(r'^\s*(?:\w+:\s*)?\.(?:stringn|string|str)\b', re.I)
ASM_LOADTABLE_RE = re.compile(r'^\s*\.loadtable\s+"\.\./include/charmap\.tbl"', re.I)
FONT_KEYS = {"narc": str, "fonts": INTS, "codes": STRS, "source": str, "notes": str}
FONT_REQUIRED = ("narc", "fonts", "codes", "source")

_NARC = {"narc": str, "also": STRS, "notes": str}
GRAPHICS_OPS = {   # op -> (allowed keys with types, required keys)
    "copy_us": ({**_NARC, "members": INTS}, ("narc", "members")),
    "tiles_from_file": ({**_NARC, "member": int, "src": str}, ("narc", "member", "src")),
    "tiles_from_png": ({**_NARC, "member": int, "src": str}, ("narc", "member", "src")),
    "tiles_from_us": ({**_NARC, "member": int, "tiles": ("list", INTS)}, ("narc", "member", "tiles")),
    "tile_range_from_png": ({**_NARC, "member": int, "first": int, "src": str, "width_tiles": int},
                            ("narc", "member", "first", "src")),
    "member_from_file": ({**_NARC, "files": TABLE_MAP, "member": int, "src": str, "expect_sha1": str}, ("narc",)),
    "code_from_us": ({"file": str, "offset": str, "us_file": str, "us_offset": str, "length": int,
                      "expect_sha1": str, "us_sha1": str, "notes": str},
                     ("file", "offset", "us_file", "us_offset", "length", "expect_sha1", "us_sha1")),
}

ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
DEC_RE = re.compile(r"D-\d{4}")
HEX_RE = re.compile(r"0x[0-9A-Fa-f]+")
HW_ONE = re.compile(r"0x[0-9A-Fa-f]{1,4}")
HW_RUN = re.compile(r"[0-9A-Fa-f]{4}")


class FixError(Exception):
    pass


# --------------------------------------------------------------------------------------
# loading and validation
# --------------------------------------------------------------------------------------

def load_all(root: Path = PATCHES_DIR, validate_all=True, decisions=None) -> list:
    """Every fix under root, sorted by id. Each fix is the parsed TOML dict plus "_path".
    Raises FixError listing every schema problem (validate_all) - the build never runs on a bad registry."""
    root = Path(root)
    if not root.is_dir():
        raise FixError(f"{root}: the fix registry folder does not exist")
    fixes, problems = [], []
    for d in sorted(x for x in root.iterdir()
                    if x.is_dir() and not x.name.startswith(".") and x.name != INCLUDE_DIR):
        if not (d / "fix.toml").is_file():
            problems.append(f"{d.name}/: folder without fix.toml (every folder under {root.name}/ is one fix)")
    for p in sorted(root.glob("*/fix.toml")):
        try:
            with open(p, "rb") as f:
                fx = tomllib.load(f)
        except tomllib.TOMLDecodeError as ex:
            problems.append(f"{p.relative_to(root)}: {ex}")
            continue
        fx["_path"] = p
        fixes.append(fx)
    if not fixes and not problems:
        problems.append(f"{root}: no */fix.toml found")
    if validate_all and not problems:
        problems += validate(fixes, decisions=decisions, overlay_bases=load_overlays(root))
        problems += lint_includes(root)
    if problems:
        raise FixError("work/patches is invalid:\n  " + "\n  ".join(problems))
    return sorted(fixes, key=lambda f: f.get("id", ""))


def _is(v, spec) -> bool:
    if isinstance(spec, tuple) and spec[0] == "dict":   # ("dict", value spec): a table of sub-tables
        return isinstance(v, dict) and all(_is(x, spec[1]) for x in v.values())
    if isinstance(spec, tuple):                     # ("list", element spec)
        return isinstance(v, list) and all(_is(x, spec[1]) for x in v)
    if spec is int:
        return isinstance(v, int) and not isinstance(v, bool)
    return isinstance(v, spec)


def _tname(spec) -> str:
    if isinstance(spec, tuple):
        return f"a {'list' if spec[0] == 'list' else 'table'} of {_tname(spec[1])}"
    return {"dict": "table", "str": "string"}.get(spec.__name__, spec.__name__)


def _entries(fx, table) -> list:
    """fx[table] when it is a list of tables, else [] (the wrong type is reported by _types)."""
    v = fx.get(table, [])
    return v if _is(v, TABLES) else []


def _types(where, obj, allowed, required, problems):
    for k in obj:
        if k not in allowed:
            problems.append(f"{where}: unknown key {k!r}")
        elif not _is(obj[k], allowed[k]):
            problems.append(f"{where}: {k!r} must be {_tname(allowed[k])}")
    for k in required:
        if k not in obj:
            problems.append(f"{where}: missing {k!r}")


def halfwords(v) -> list:
    """expect of a [[code]] entry: one halfword "0x2305" (0x + 1-4 hex
    digits) or a run of 2+ halfwords "01DE 012B ..." (exactly 4 hex digits each). Raises ValueError otherwise,
    e.g. for a bare "2320", which could be read as decimal or hex."""
    if not isinstance(v, str):
        raise ValueError(f"{v!r}: halfwords are written as a string")
    toks = v.split()
    if len(toks) == 1 and HW_ONE.fullmatch(toks[0]):
        return [int(toks[0], 16)]
    if len(toks) > 1 and all(HW_RUN.fullmatch(t) for t in toks):
        return [int(t, 16) for t in toks]
    raise ValueError(f"{v!r}: write one halfword as 0xNNNN or a run as 'NNNN NNNN ...' (4 hex digits each)")


def _validate_entries(fx, where, problems):
    kind = fx.get("kind")
    table = ENTRY_TABLES.get(kind)
    for t in ("code", "string", "graphics", "font"):
        if t in fx and t != table:
            problems.append(f"{where}: kind {kind!r} cannot have [[{t}]] entries")
    if "grow" in fx and kind not in ASM_KINDS:
        problems.append(f"{where}: [[grow]] only belongs to kinds {', '.join(ASM_KINDS)}")
    if table and not fx.get(table):
        problems.append(f"{where}: kind {kind!r} needs at least one [[{table}]] entry")
    for i, e in enumerate(_entries(fx, "code")):
        w = f"{where} [[code]] #{i} {e.get('id', '?')}"
        _types(w, e, CODE_KEYS, CODE_REQUIRED, problems)
        if "value" in e:
            problems.append(f"{w}: 'value' is gone: the fix's asm writes the new bytes; [[code]] keeps the "
                            f"region and its original bytes (expect)")
        if isinstance(e.get("offset"), str) and not HEX_RE.fullmatch(e["offset"]):
            problems.append(f"{w}: offset must be hex like '0x4E'")
        if isinstance(e.get("file"), str) and not CODE_FILE_RE.fullmatch(e["file"]):
            problems.append(f"{w}: file must be 'arm9' or 'overlayNN' (the ITCM block 'itcm' may only grow: [[grow]])")
        if "expect" in e and ("length" in e or "expect_sha1" in e):
            problems.append(f"{w}: give expect, or length + expect_sha1, not both")
        elif "expect" not in e:
            if "length" not in e or "expect_sha1" not in e:
                problems.append(f"{w}: missing 'expect' (or 'length' + 'expect_sha1' for a large region)")
            if _is(e.get("length"), int) and (e["length"] <= 0 or e["length"] % 2):
                problems.append(f"{w}: length must be a positive even number of bytes")
            if isinstance(e.get("expect_sha1"), str) and not SHA1_RE.fullmatch(e["expect_sha1"]):
                problems.append(f"{w}: expect_sha1 must be 40 lowercase hex digits")
        else:
            try:
                halfwords(e["expect"])
            except ValueError as ex:
                problems.append(f"{w}: {ex}")
    for i, e in enumerate(_entries(fx, "string")):
        w = f"{where} [[string]] #{i} {e.get('id', '?')}"
        _types(w, e, STRING_KEYS, STRING_REQUIRED, problems)
        if isinstance(e.get("offset"), str) and not HEX_RE.fullmatch(e["offset"]):
            problems.append(f"{w}: offset must be hex like '0x6F0'")
        if e.get("id") and e.get("file") and e.get("offset") and e["id"] != f"{e['file']}:{e['offset']}":
            problems.append(f"{w}: id must be '<file>:<offset>'")
        if isinstance(e.get("file"), str) and not CODE_FILE_RE.fullmatch(e["file"]):
            problems.append(f"{w}: file must be 'arm9' or 'overlayNN' (the ITCM block 'itcm' may only grow: [[grow]])")
        for ptr in e.get("pointers", []) if _is(e.get("pointers", []), STRS) else []:
            if not HEX_RE.fullmatch(ptr):
                problems.append(f"{w}: pointer {ptr!r} must be hex like '0x4E4'")
    grown = set()
    for i, g in enumerate(_entries(fx, "grow")):
        w = f"{where} [[grow]] #{i}"
        _types(w, g, GROW_KEYS, GROW_REQUIRED, problems)
        if isinstance(g.get("file"), str) and not re.fullmatch(r"overlay\d+|itcm", g["file"]):
            problems.append(f"{w}: file must be 'overlayNN' or 'itcm' (only an overlay or the ITCM block can grow)")
        limit = ITCM_LIMIT - ITCM_BASE if g.get("file") == "itcm" else 0x1000
        if _is(g.get("max"), int) and not 0 < g["max"] <= limit:
            problems.append(f"{w}: max must be 1..{limit} bytes")
        if g.get("file") in grown:
            problems.append(f"{w}: {g['file']} has more than one [[grow]]")
        grown.add(g.get("file"))
    for i, e in enumerate(_entries(fx, "graphics")):
        w = f"{where} [[graphics]] #{i}"
        op = e.get("op")
        if not isinstance(op, str) or op not in GRAPHICS_OPS:
            problems.append(f"{w}: unknown op {op!r}")
            continue
        allowed, required = GRAPHICS_OPS[op]
        _types(w, {k: v for k, v in e.items() if k != "op"}, allowed, required, problems)
        if op == "tiles_from_us" and _is(e.get("tiles"), ("list", INTS)) and \
                any(len(r) != 2 or r[0] > r[1] for r in e["tiles"]):
            problems.append(f"{w}: tiles must be [first, last] pairs")
        if op == "code_from_us":
            for k in ("offset", "us_offset"):
                if isinstance(e.get(k), str) and not HEX_RE.fullmatch(e[k]):
                    problems.append(f"{w}: {k} must be hex like '0x4C0A8'")
        if op == "member_from_file":
            files = e.get("files") if _is(e.get("files"), TABLE_MAP) else None
            if "files" not in e and not all(k in e for k in ("member", "src", "expect_sha1")):
                problems.append(f"{w}: member_from_file needs files or member/src/expect_sha1")
            for mb, spec in (files or {}).items():
                if not mb.isdigit() or not isinstance(spec, dict) or set(spec) != {"src", "expect_sha1"}:
                    problems.append(f"{w}: files.{mb} must be {{src, expect_sha1}}")
    for i, e in enumerate(_entries(fx, "font")):
        _types(f"{where} [[font]] #{i}", e, FONT_KEYS, FONT_REQUIRED, problems)
        for c in e.get("codes", []) if _is(e.get("codes", []), STRS) else []:
            if not HEX_RE.fullmatch(c):
                problems.append(f"{where} [[font]] #{i}: code {c!r} must be hex like '0x01AF'")


def asm_path(fx):
    """The fix's armips source (Path), or None when it has none."""
    if not isinstance(fx.get("asm"), str) or not fx.get("_path"):
        return None
    return fx["_path"].parent / fx["asm"]


def asm_opens(text: str) -> list:
    """(line number, file, base or None) of every `.open` in an armips source; base None = not a literal."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        code = line.split(";", 1)[0]
        if not re.match(r"\s*\.open(?:file)?\b", code, re.I):
            continue
        mo = ASM_OPEN_RE.match(line)
        out.append((n, mo.group(1), int(mo.group(2), 16)) if mo else (n, code.strip(), None))
    return out


def asm_strings(text: str) -> list:
    """(line number, text) of every `.string`/`.stringn`/`.str` literal in an armips source (escapes undone)."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        mo = ASM_STRING_RE.match(line)
        if mo:
            out.append((n, re.sub(r"\\(.)", r"\1", mo.group(1))))
    return out


def asm_string_forms(text: str) -> list:
    """(line number, line) of `.string`/`.stringn`/`.str` lines that are not one literal: multi-argument
    forms (`.string "a", 0`, `.string "a", "b"`) or a non-literal argument. The registry compares each
    literal with a [[string]] en, so a source writes one `.string "..."` per line."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if ASM_STRING_DIRECTIVE_RE.match(line) and not ASM_STRING_RE.match(line):
            out.append((n, line.strip()))
    return out


ASM_FORBIDDEN_RE = re.compile(r"\s*(\.create(?:file)?|\.headersize)\b", re.I)


def asm_forbidden(text: str) -> list:
    """(line number, directive) of directives a fix source may not use: .create/.createfile (a fix only
    patches the staged binaries) and .headersize (the load address is the one of its .open)."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        mo = ASM_FORBIDDEN_RE.match(line.split(";", 1)[0])
        if mo:
            out.append((n, mo.group(1).lower()))
    return out


# --------------------------------------------------------------------------------------
# asm lint: static rules for a fix's armips source (no armips, no ROM)
# --------------------------------------------------------------------------------------
#
# lint_asm() reads the source like armips does, as far as the rules need: it follows `.include` (for macros
# and `equ` constants), expands macro invocations (textual parameter substitution, as armips does), and
# classifies every statement as a write (an instruction or a data directive), a guard, or neither. A guard is
# an `.if` whose condition reads the file being patched: `readu8/16/32(outputname(), <address with org()>)`
# guards the bytes at the current address (expect16, expect32, expect16_at, ...); `filesize(outputname())`
# is the end guard (expect_end, appended data); a read at an absolute address (expect32_abs) is a read-only
# check and guards nothing. Rules, each reported as <fix>/<file>.asm:<line>:
#   header   line 1 is `; <fix-id> - <title>`, and the header (the leading comment lines up to the first `;`
#            line or code) names every decision of fix.toml, or the pending decision when it has none;
#   length   no line is longer than ASM_MAX_LINE characters;
#   area     every write is inside an `.area` (so it can never grow into the next code), each `.area` is the
#            first one after its `.org` (so its address is the .org's), and no write comes before an `.org`;
#   guard    the first write of every `.area` has a guard since its `.org` (an appended area: expect_end);
#   region   an `.area` that is not appended lies inside the regions fix.toml declares in the opened file
#            ([[code]] regions, [[string]] slots and pointer words), resolved statically from the `.org`
#            and `.area` expressions (numbers, `equ` constants, `.definelabel`s); an appended one (expect_end)
#            needs a [[grow]] of that file. An `.org` block without writes (read-only guards) may be anywhere.
# armips itself stays the authority on the bytes; these rules catch an unguarded or unbounded edit, or one
# outside fix.toml's regions, before anything is assembled.

ASM_MAX_LINE = 120
ASM_WRITE_DIRECTIVES = {
    "byte", "db", "dcb", "ascii", "asciiz", "halfword", "hword", "dh", "dcw", "word", "dw", "dcd", "doubleword",
    "dcq", "float", "double", "string", "stringn", "str", "strn", "sjis", "sjisn", "fill", "defs", "ds", "align",
    "skip", "incbin", "import", "importobj", "importlib", "pool"}
ASM_NEUTRAL_DIRECTIVES = {
    "nds", "gba", "psx", "ps2", "n64", "rsp", "arm", "thumb", "include", "open", "close", "org", "area", "endarea",
    "definelabel", "macro", "endmacro", "if", "ifdef", "ifndef", "elseif", "elseifdef", "elseifndef", "else",
    "endif", "error", "warning", "notice", "loadtable", "table", "erroronwarning", "relativeinclude", "sym", "func",
    "endfunc", "function", "endfunction", "headersize", "create", "createfile", "openfile"}
_LINT_LABEL_RE = re.compile(r"^\s*([A-Za-z_@.][\w@.]*):(?!:)\s*(.*)$")
_LINT_EQU_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s+equ\s+(.+?)\s*$", re.I)
_LINT_DIRECTIVE_RE = re.compile(r"^\s*\.([A-Za-z][\w.]*)\b\s*(.*?)\s*$")
_LINT_INCLUDE_RE = re.compile(r'^\s*\.include\s+"([^"]+)"', re.I)
_LINT_READ_RE = re.compile(r"\breadu?(?:8|16|32|64)\s*\(", re.I)


def _strip_comment(line: str) -> str:
    """The line without its `;` or `//` comment (quotes respected)."""
    quote, escaped = None, False
    for i, ch in enumerate(line):
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ";" or line.startswith("//", i):
            return line[:i]
    return line


def _split_args(text: str) -> list:
    """Macro / directive arguments: split at commas outside parentheses and quotes."""
    out, depth, quote, cur = [], 0, None, []
    for ch in text:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _call_args(text: str, start: int) -> str:
    """The text inside the parentheses that open at text[start - 1]."""
    depth = 1
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i]
    return text[start:]


def guard_kind(cond: str):
    """What an `.if` condition checks: "pos" (bytes at the current address), "end" (the file ends here),
    "abs" (bytes at an absolute address: a read-only check) or None (no read of the patched file)."""
    c = cond.lower().replace(" ", "")
    if "filesize(outputname())" in c and "org()" in c:
        return "end"
    kinds = set()
    for mo in _LINT_READ_RE.finditer(cond):
        args = _call_args(cond, mo.end()).lower().replace(" ", "")
        if args.startswith("outputname()"):
            kinds.add("pos" if "org()" in args else "abs")
    return "pos" if "pos" in kinds else ("abs" if kinds else None)


def eval_asm_expr(expr: str, names: dict, _depth=0):
    """Value of an armips expression of numbers, + - * / % << >> & | ^ ~ and names (`equ` / .definelabel,
    case-insensitive), or None when it cannot be resolved statically."""
    import ast
    if _depth > 20:
        return None
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return None
    ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: int(a / b), ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
           ast.LShift: lambda a, b: a << b, ast.RShift: lambda a, b: a >> b, ast.BitAnd: lambda a, b: a & b,
           ast.BitOr: lambda a, b: a | b, ast.BitXor: lambda a, b: a ^ b}

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.Name):
            v = names.get(n.id.lower())
            return eval_asm_expr(v, names, _depth + 1) if isinstance(v, str) else v
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd, ast.Invert)):
            v = ev(n.operand)
            return None if v is None else {ast.USub: -v, ast.UAdd: v}.get(type(n.op), ~v)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            a, b = ev(n.left), ev(n.right)
            if a is None or b is None or (isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod)) and b == 0):
                return None
            return ops[type(n.op)](a, b)
        return None
    return ev(tree.body)


def _merge(ranges) -> list:
    out = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def lint_asm(text: str, fx: dict, overlay_bases=None, name="fix.asm", include_root=None) -> list:
    """Static rules for one fix source (see above); problems as strings with file:line."""
    problems = []
    fid = fx.get("id", "?")
    where = f"{fid}/{name}"
    base_dir = Path(include_root) if include_root else (fx["_path"].parent if fx.get("_path") else PATCHES_DIR)
    lines = text.splitlines()
    # -- header ---------------------------------------------------------------------------------------
    header = []
    for line in lines:
        if not line.startswith(";") or line.strip() == ";":
            break
        header.append(line)
    if not lines or not re.match(rf";\s*{re.escape(fid)}\s+-\s+\S", lines[0]):
        problems.append(f"{where}:1: the source must start with a header comment '; {fid} - <title>. <decisions>'")
    head_text = "\n".join(header)
    decs = [d for d in fx.get("decisions", []) if isinstance(d, str)] if _is(fx.get("decisions"), STRS) else []
    missing = [d for d in decs if d not in head_text]
    if missing:
        problems.append(f"{where}:1: the header comment does not name {', '.join(missing)} "
                        f"(fix.toml decisions: name them in the leading comment lines)")
    if not decs and not DEC_RE.search(head_text):
        problems.append(f"{where}:1: fix.toml lists no decision, so the header comment must name the pending "
                        f"decision (a D-NNNN id)")
    # -- line length ----------------------------------------------------------------------------------
    for n, line in enumerate(lines, 1):
        if len(line) > ASM_MAX_LINE:
            problems.append(f"{where}:{n}: line is {len(line)} characters, more than {ASM_MAX_LINE} (wrap it)")
    # -- statements: includes, macros, equ ----------------------------------------------------------------
    names, macros = {}, {}

    def collect(src_lines, src_name, src_dir, seen):
        """Macro definitions and equ / .definelabel of an included file (statements are not linted)."""
        i = 0
        while i < len(src_lines):
            code = _strip_comment(src_lines[i])
            mo = _LINT_INCLUDE_RE.match(code)
            if mo:
                inc = _resolve_include(src_dir, mo.group(1))
                if inc is not None and inc not in seen:
                    seen.add(inc)
                    collect(inc.read_text(encoding="utf-8").splitlines(), inc.name, inc.parent, seen)
            i = _define(src_lines, i, src_name) + 1

    def _define(src_lines, i, src_name):
        """Record a macro (returns the index of its .endmacro), an equ or a .definelabel at line i."""
        code = _strip_comment(src_lines[i])
        mo = _LINT_DIRECTIVE_RE.match(code)
        if mo and mo.group(1).lower() == "macro":
            args = _split_args(mo.group(2))
            body, j = [], i + 1
            while j < len(src_lines) and not re.match(r"\s*\.endmacro\b", _strip_comment(src_lines[j]), re.I):
                body.append((src_name, j + 1, src_lines[j]))
                j += 1
            if args:
                macros[args[0].lower()] = ([a.lower() for a in args[1:]], body)
            return j
        if mo and mo.group(1).lower() == "definelabel":
            args = _split_args(mo.group(2))
            if len(args) == 2:
                names[args[0].lower()] = args[1]
        mo = _LINT_EQU_RE.match(code)
        if mo:
            names[mo.group(1).lower()] = mo.group(2)
        return i

    # -- the walk ----------------------------------------------------------------------------------
    regions = {}                        # file key -> merged [start, end) RAM ranges
    grown = {g.get("file") for g in _entries(fx, "grow")}
    rows = []
    try:
        rows = footprint(fx)
    except (KeyError, ValueError, TypeError):
        pass                            # malformed entries are reported by the schema checks
    state = {"file": None, "base": None, "block": None, "depth": 0, "area": None}

    def loc(stack):
        return " (" + ", ".join(f"macro line {s}:{n}" for s, n in stack) + ")" if stack else ""

    def ranges_for(key, base):
        if key not in regions:
            regions[key] = _merge((base + s, base + e) for r, s, e, _ in rows if r == key and s < 1 << 40)
        return regions[key]

    def statement(code, n, stack, depth=0):
        st = state
        mo = _LINT_LABEL_RE.match(code)
        if mo and not code.lstrip().startswith("."):
            code = mo.group(2)
        if not code.strip():
            return
        at = f"{where}:{n}{loc(stack)}"
        mo = _LINT_EQU_RE.match(code)
        if mo:
            names[mo.group(1).lower()] = mo.group(2)
            return
        mo = _LINT_DIRECTIVE_RE.match(code)
        if mo:
            d, rest = mo.group(1).lower(), mo.group(2)
            if d == "definelabel":
                args = _split_args(rest)
                if len(args) == 2:
                    names[args[0].lower()] = args[1]
            elif d == "open":
                mo2 = ASM_OPEN_RE.match(code)
                st["file"] = mo2.group(1)[:-4] if mo2 and mo2.group(1).endswith(".bin") else None
                st["base"] = int(mo2.group(2), 16) if mo2 else None
                st["block"] = None
            elif d == "close":
                st["file"] = st["base"] = st["block"] = None
            elif d == "org":
                if st["depth"]:
                    problems.append(f"{at}: .org inside an .area")
                st["block"] = {"addr": eval_asm_expr(rest, names), "expr": rest, "guarded": False,
                               "appended": False, "areas": 0}
            elif d == "orga":
                problems.append(f"{at}: .orga takes a file offset; write .org with the RAM address")
            elif d == "area":
                st["depth"] += 1
                if st["depth"] == 1:
                    blk = st["block"]
                    if blk is None:
                        problems.append(f"{at}: .area before any .org")
                    elif blk["areas"]:
                        problems.append(f"{at}: a second .area after one .org: start each .area with its own .org "
                                        f"(the lint checks the area's address range from the .org)")
                    else:
                        blk["areas"] = 1
                    args = _split_args(rest)
                    st["area"] = {"line": at, "size": eval_asm_expr(args[0], names) if args else None,
                                  "size_expr": args[0] if args else "", "written": False,
                                  "start": blk["addr"] if blk else None}
            elif d == "endarea":
                if st["depth"] == 0:
                    problems.append(f"{at}: .endarea without .area")
                else:
                    st["depth"] -= 1
                    if st["depth"] == 0:
                        st["area"] = None
            elif d in ("if", "elseif"):
                kind = guard_kind(rest)
                if kind in ("pos", "end") and st["block"] is not None:
                    st["block"]["guarded"] = True
                    st["block"]["appended"] |= kind == "end"
            elif d in ASM_WRITE_DIRECTIVES:
                write(at, n)
            elif d not in ASM_NEUTRAL_DIRECTIVES:
                problems.append(f"{at}: unknown directive .{d}: the lint does not know whether it writes "
                                f"(add it to fixes.ASM_WRITE_DIRECTIVES or ASM_NEUTRAL_DIRECTIVES)")
            return
        word = code.split(None, 1)
        if word and word[0].lower() in macros:
            if depth > 30:
                problems.append(f"{at}: macro nesting too deep")
                return
            params, body = macros[word[0].lower()]
            args = dict(zip(params, _split_args(word[1]) if len(word) > 1 else [], strict=False))
            subst = re.compile(r"(?<![\w@.])(" + "|".join(map(re.escape, args)) + r")(?![\w@])", re.I) \
                if args else None
            for src, bn, bline in body:
                b = _strip_comment(bline)
                if subst:
                    b = subst.sub(lambda m: args[m.group(1).lower()], b)
                statement(b, n, stack + [(src, bn)], depth + 1)
            return
        write(at, n)                                     # an instruction

    def write(at, n):
        st = state
        if st["depth"] == 0:
            problems.append(f"{at}: write outside an .area (wrap every edit in .area <size> / .endarea)")
            return
        area = st["area"]
        if area["written"]:
            return
        area["written"] = True
        blk = st["block"]
        if blk is None:
            return                                       # reported at the .area
        if not blk["guarded"]:
            problems.append(f"{area['line']}: the .area's first write (line {n}) has no guard since its .org "
                            f"(expect16 / expect32 / expect16_at / ... on the bytes it replaces, or expect_end "
                            f"for appended data)")
        key = st["file"]
        if key is None:
            return
        if blk["appended"]:
            if key not in grown:
                problems.append(f"{area['line']}: data appended to {key}.bin (expect_end), but fix.toml has no "
                                f"[[grow]] for {key}")
            return
        if blk["addr"] is None or area["size"] is None:
            what = f".org {blk['expr']}" if blk["addr"] is None else f".area {area['size_expr']}"
            problems.append(f"{area['line']}: cannot resolve {what} statically (use numbers, equ constants or "
                            f".definelabel), so the region check cannot run")
            return
        if st["base"] is None:
            return
        s, e = blk["addr"], blk["addr"] + area["size"]
        if not any(lo <= s and e <= hi for lo, hi in ranges_for(key, st["base"])):
            off = s - st["base"]
            problems.append(f"{area['line']}: .area {s:#010x}-{e:#010x} ({key}+{off:#x}, {area['size']} bytes) is "
                            f"not inside one region fix.toml declares in {key} ([[code]] regions, [[string]] slots "
                            f"and pointers)")

    collect(lines, name, base_dir, set())
    i = 0
    while i < len(lines):
        code = _strip_comment(lines[i])
        mo = _LINT_DIRECTIVE_RE.match(code)
        if mo and mo.group(1).lower() == "macro":
            i = _define(lines, i, name) + 1              # a definition: its body runs where it is invoked
            continue
        if mo and mo.group(1).lower() == "include":
            i += 1
            continue
        statement(code, i + 1, [])
        i += 1
    if state["depth"]:
        problems.append(f"{where}: an .area is not closed (.endarea missing)")
    return problems


def _resolve_include(src_dir: Path, rel: str):
    """An `.include` path: relative to the including file's folder (armips runs in <stage>/rom, next to
    <stage>/include, and the sources live one folder below work/patches, so `../include/x` resolves the same
    way); falls back to work/patches/include for synthetic test registries."""
    p = (Path(src_dir) / rel).resolve()
    if p.is_file():
        return p
    alt = PATCHES_DIR / INCLUDE_DIR / Path(rel).name
    return alt if rel.replace("\\", "/").startswith("../include/") and alt.is_file() else None


def lint_includes(root: Path = PATCHES_DIR) -> list:
    """Line length of the shared armips includes (work/patches/include/*.inc)."""
    out = []
    for p in sorted((Path(root) / INCLUDE_DIR).glob("*.inc")):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if len(line) > ASM_MAX_LINE:
                out.append(f"{INCLUDE_DIR}/{p.name}:{n}: line is {len(line)} characters, more than {ASM_MAX_LINE}")
    return out


def _validate_asm(fx, where, problems, overlay_bases):
    """asm only for kinds code/data/strings, and required there; the file exists in the fix's folder; every
    `.open` is '<file>.bin' of a file with a [[code]] region, [[string]] entry or [[grow]], at that file's load
    address; every such file is opened; a strings fix's `.string` literals are its [[string]] en values."""
    kind, asm = fx.get("kind"), fx.get("asm")
    if "native" in fx and kind != "code":
        problems.append(f"{where}: [native] only belongs to kind 'code'")
    if kind not in ASM_KINDS:
        if asm is not None:
            problems.append(f"{where}: 'asm' only belongs to kinds {', '.join(ASM_KINDS)}")
        return
    if not isinstance(asm, str):
        if asm is None:
            problems.append(f"{where}: kind {kind!r} needs asm = \"<file>.asm\" (its armips source)")
        return
    if "/" in asm or "\\" in asm or not asm.endswith(".asm"):
        problems.append(f"{where}: asm must be a .asm file name in the fix's own folder")
        return
    path = asm_path(fx)
    if path is None:
        return
    if not path.is_file():
        problems.append(f"{where}: asm file {asm} does not exist")
        return
    files = {e["file"] for t in ("code", "string", "grow") for e in _entries(fx, t) if isinstance(e.get("file"), str)}
    opened = set()
    text = path.read_text(encoding="utf-8")
    problems += lint_asm(text, fx, overlay_bases, name=asm)
    for n, d in asm_forbidden(text):
        problems.append(f"{fx['_path'].parent.name}/{asm}:{n}: {d} is not allowed in a fix source "
                        f"(it only patches the staged binaries at their load address)")
    for n, name, base in asm_opens(text):
        w = f"{fx['_path'].parent.name}/{asm}:{n}"
        if base is None:
            problems.append(f"{w}: write .open as '.open \"<file>.bin\", 0x<load address>' ({name})")
            continue
        key = name[:-4] if name.endswith(".bin") else None
        if key not in files:
            problems.append(f"{w}: opens {name!r}, but the fix declares no [[code]] / [[string]] / [[grow]] in it "
                            f"(expected one of {', '.join(sorted(f + '.bin' for f in files)) or 'none'})")
            continue
        opened.add(key)
        want = ARM9_BASE if key == "arm9" else ITCM_BASE if key == "itcm" else (overlay_bases or {}).get(key)
        if want is not None and base != want:
            problems.append(f"{w}: {name} opened at {base:#010x}, but its load address is {want:#010x}"
                            f"{'' if key == 'arm9' else ' (' + OVERLAYS_TOML + ')'}")
    for key in sorted(files - opened):
        problems.append(f"{where}: entries in {key}, but {asm} never opens {key}.bin")
    _validate_native(fx, where, text, problems)
    for n, line in asm_string_forms(text):
        problems.append(f"{fx['_path'].parent.name}/{asm}:{n}: write one literal per line, "
                        f'.string "<text>" (found: {line}); fixes.py compares each literal with a [[string]] en')
    if kind == "strings" or asm_strings(text):
        lits = sorted(lit for _, lit in asm_strings(text))
        want = sorted(e["en"] for e in _entries(fx, "string") if isinstance(e.get("en"), str) and e["en"])
        if lits != want:
            problems.append(f"{fx['_path'].parent.name}/{asm}: its .string literals {lits} differ from the "
                            f"[[string]] en values {want} in fix.toml (change both together)")
        if lits and not any(ASM_LOADTABLE_RE.match(line) for line in text.splitlines()):
            problems.append(f"{fx['_path'].parent.name}/{asm}: .string needs the game's character table: "
                            f'.loadtable "../include/charmap.tbl", "UTF-8"')


def native_payload(fx):
    """The fix's payload.json as parsed JSON (not validated: the [native] module does that), or None."""
    nat = fx.get("native")
    if not isinstance(nat, dict) or not isinstance(nat.get("payload"), str) or not fx.get("_path"):
        return None
    return json.loads((fx["_path"].parent / nat["payload"]).read_text(encoding="utf-8"))


def native_bin(fx) -> str:
    """Where the build stages a fix's payload bytes, relative to armips's working directory."""
    return f"../native/{fx['id']}.bin"


def _validate_native(fx, where, text, problems):
    """[native]: keys, files in the fix's folder, a known module; the asm includes the payload with
    `.incbin "../native/<id>.bin"` and names every payload symbol with `.definelabel` at its address
    (Thumb bit clear), and nothing else under those names."""
    nat = fx.get("native")
    if nat is None:
        if any(ASM_INCBIN_RE.match(line) for line in text.splitlines()):
            problems.append(f"{where}: its asm uses .incbin, but the fix has no [native] payload")
        return
    if not isinstance(nat, dict):
        return                                          # reported by the type check
    _types(f"{where} [native]", nat, NATIVE_KEYS, NATIVE_REQUIRED, problems)
    if isinstance(nat.get("module"), str) and nat["module"] not in NATIVE_MODULES:
        problems.append(f"{where}: [native] module {nat['module']!r} is unknown (known: {', '.join(NATIVE_MODULES)})")
    folder = fx["_path"].parent
    for name in [nat.get("source"), nat.get("payload")] + list(nat.get("headers") or []):
        if isinstance(name, str) and ("/" in name or not (folder / name).is_file()):
            problems.append(f"{where}: [native] file {name!r} is not in the fix's folder")
    incs = [mo.group(1) for line in text.splitlines() if (mo := ASM_INCBIN_RE.match(line))]
    if incs != [native_bin(fx)]:
        problems.append(f"{where}: its asm must include the payload once, as .incbin \"{native_bin(fx)}\" "
                        f"(found {incs})")
    try:
        payload = native_payload(fx)
        symbols = payload["symbols"]
        assert isinstance(symbols, dict) and all(isinstance(v, int) for v in symbols.values())
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        problems.append(f"{where}: [native] payload {nat.get('payload')!r} is missing or has no symbol table")
        return
    labels = {}
    for line in text.splitlines():
        mo = ASM_DEFINELABEL_RE.match(line)
        if mo and mo.group(1) in symbols:
            labels[mo.group(1)] = int(mo.group(2), 16)
    want = {k: v & ~1 for k, v in symbols.items()}
    if labels != want:
        bad = sorted(k for k in want if labels.get(k) != want[k])
        problems.append(f"{where}: its asm's .definelabel lines must give every payload symbol its address "
                        f"(payload.json, Thumb bit clear); wrong or missing: {', '.join(bad)}")


def validate(fixes, decisions=None, overlay_bases=None) -> list:
    """Schema and registry problems (list of strings; empty = valid). decisions: set of known D-ids, or
    None to read the register (skipped if it is missing). overlay_bases: {"overlayNN": ram} from
    overlays.toml; every overlay an entry touches needs one (None: not checked)."""
    problems = []
    if decisions is None:
        decisions = load_decision_ids()
    ids = {}
    for fx in fixes:
        path = fx.get("_path")
        where = f"{path.parent.name}/fix.toml" if path else f"fix {fx.get('id', '?')}"
        _types(where, {k: v for k, v in fx.items() if k != "_path"},
               TOP_KEYS, REQUIRED_TOP, problems)
        fid = fx.get("id")
        if isinstance(fid, str):
            if not ID_RE.fullmatch(fid):
                problems.append(f"{where}: id {fid!r} must be lowercase words joined by '-'")
            if path and path.parent.name != fid:
                problems.append(f"{where}: id {fid!r} differs from its folder name")
            if fid in ids:
                problems.append(f"{where}: duplicate fix id {fid!r} (also {ids[fid]})")
            ids[fid] = where
        if fx.get("kind") not in KINDS:
            problems.append(f"{where}: kind must be one of {', '.join(KINDS)}")
        for d in fx.get("decisions", []) if _is(fx.get("decisions"), STRS) else []:
            if not DEC_RE.fullmatch(d):
                problems.append(f"{where}: decision {d!r} is not a D-NNNN id")
            elif decisions and d not in decisions:
                problems.append(f"{where}: decision {d} is not in the decision register")
        for k in ("title", "why", "what"):
            if isinstance(fx.get(k), str) and not fx[k].strip():
                problems.append(f"{where}: {k} is empty")
        if isinstance(fx.get("title"), str) and "\n" in fx["title"]:
            problems.append(f"{where}: title must be one line")
        if isinstance(fx.get("evidence"), list) and not fx["evidence"]:
            problems.append(f"{where}: evidence is empty")
        _validate_entries(fx, where, problems)
        _validate_asm(fx, where, problems, overlay_bases)
    # entry ids unique across all fixes
    seen = {}
    for fx in fixes:
        for t in ("code", "string"):
            for e in _entries(fx, t):
                if not isinstance(e.get("id"), str):
                    continue                                # reported by the type check
                key = (t, e.get("id"))
                if key in seen:
                    problems.append(f"[[{t}]] id {e.get('id')!r} in both {seen[key]} and {fx.get('id')}")
                seen[key] = fx.get("id")
    # requires
    for fx in fixes:
        for r in fx.get("requires", []) if _is(fx.get("requires"), STRS) else []:
            if r not in ids:
                problems.append(f"{fx.get('id')}: requires unknown fix {r!r}")
            if r == fx.get("id"):
                problems.append(f"{fx.get('id')}: requires itself")
    if not problems:
        try:
            order(fixes)
        except FixError as ex:
            problems.append(str(ex))
        problems += overlaps([f for f in fixes if f.get("enabled")])
        if overlay_bases is not None:
            for fx in fixes:
                for key in sorted({r[0] for r in footprint(fx) if re.fullmatch(r"overlay\d+", r[0])}):
                    if key not in overlay_bases:
                        problems.append(f"{fx['id']}: {key} has no RAM base in {OVERLAYS_TOML} "
                                        f"(python3 work/tools/fixes.py overlays)")
    return problems


def load_decision_ids(path=DECISIONS_JSONL) -> set:
    p = Path(path)
    if not p.exists():
        return set()
    return {json.loads(line)["id"] for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}


# --------------------------------------------------------------------------------------
# overlay RAM bases (work/patches/overlays.toml)
# --------------------------------------------------------------------------------------

def load_overlays(root: Path = PATCHES_DIR) -> dict:
    """{"overlayNN": ram address} from <root>/overlays.toml ({} when the file is missing)."""
    p = Path(root) / OVERLAYS_TOML
    if not p.is_file():
        return {}
    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as ex:
        raise FixError(f"{p.name}: {ex}") from None
    out = {}
    for k, v in data.items():
        if not re.fullmatch(r"overlay\d+", k) or not isinstance(v, dict) or set(v) != {"ram"} or not _is(v["ram"], int):
            raise FixError(f"{p.name}: [{k}] must be an overlayNN table with only 'ram = 0x...'")
        out[k] = v["ram"]
    return out


def rom_overlay_bases(rom) -> dict:
    """{"overlayNN": ramAddress} of every overlay in an ndspy ROM's y9 table."""
    import ndspy.code
    table = ndspy.code.loadOverlayTable(rom.arm9OverlayTable, lambda i, f: bytes(rom.files[f]))
    return {f"overlay{i}": ov.ramAddress for i, ov in table.items()}


def check_overlay_bases(rom, root: Path = PATCHES_DIR):
    """Raise FixError when overlays.toml disagrees with the ROM's y9 overlay table."""
    rom_bases = rom_overlay_bases(rom)
    bad = [f"{k}: overlays.toml {v:#010x}, ROM {rom_bases.get(k, 0):#010x}"
           for k, v in sorted(load_overlays(root).items()) if rom_bases.get(k) != v]
    if bad:
        raise FixError("work/patches/overlays.toml does not match the ROM's overlay table:\n  " + "\n  ".join(bad))


def write_overlays(rom, fixes, root: Path = PATCHES_DIR) -> Path:
    """Write overlays.toml for the overlays the fixes touch, with the ROM's RAM bases."""
    rom_bases = rom_overlay_bases(rom)
    keys = sorted({r[0] for fx in fixes for r in footprint(fx) if re.fullmatch(r"overlay\d+", r[0])},
                  key=lambda k: int(k[7:]))
    lines = ["# RAM load address of every overlay a fix touches, from the y9 overlay table of the Chinese ROM.",
             "# Generated by `python3 work/tools/fixes.py overlays`; build.py checks it against the ROM it loads.", ""]
    for k in keys:
        lines += [f"[{k}]", f"ram = 0x{rom_bases[k]:08X}", ""]
    p = Path(root) / OVERLAYS_TOML
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _ram(file, off, bases):
    if file == "arm9":
        return 0x02000000 + off
    if file == "itcm":
        return ITCM_BASE + off
    return bases[file] + off if file in bases else None


# --------------------------------------------------------------------------------------
# what each entry touches (for the overlap check and the docs)
# --------------------------------------------------------------------------------------

def _int(v) -> int:
    return v if isinstance(v, int) else int(str(v), 0)


def region_length(e) -> int:
    """Bytes of a [[code]] region: its expect halfwords, or `length` for a SHA-1-pinned region."""
    return 2 * len(halfwords(e["expect"])) if "expect" in e else e["length"]


def footprint(fx) -> list:
    """(resource, start, end, label) rows: byte ranges in code files, whole NARC members, glyphs."""
    rows = []
    for e in fx.get("code", []):
        off = _int(e["offset"])
        rows.append((e["file"], off, off + region_length(e), e["id"]))
    for e in fx.get("string", []):
        off = _int(e["offset"])
        rows.append((e["file"], off, off + 2 * (e["max_units"] + 1), e["id"]))
        for p in e.get("pointers", []):
            rows.append((e["file"], _int(p), _int(p) + 4, f"{e['id']} pointer"))
    for g in fx.get("grow", []):
        rows.append((g["file"], 1 << 40, (1 << 40) + 1, f"{g['file']} growth"))   # appended at the overlay's end
    for e in fx.get("graphics", []):
        if e["op"] == "code_from_us":
            off = _int(e["offset"])
            rows.append((e["file"], off, off + e["length"], f"{e['op']} {e['file']}"))
            continue
        members = e.get("members") or ([e["member"]] if "member" in e else [int(k) for k in e.get("files", {})])
        for narc in [e["narc"]] + e.get("also", []):
            for mb in members:
                rows.append((f"{narc}#{mb}", 0, 1, f"{e['op']} {narc} #{mb}"))
    for e in fx.get("font", []):
        for fi in e["fonts"]:
            for c in e["codes"]:
                rows.append((f"{e['narc']}#{fi}:glyph", _int(c), _int(c) + 1, f"font {fi} {c}"))
    return rows


def overlaps(fixes) -> list:
    rows = sorted((r[0], r[1], r[2], r[3], fx["id"]) for fx in fixes for r in footprint(fx))
    problems = []
    for a, b in zip(rows, rows[1:], strict=False):
        if a[0] == b[0] and b[1] < a[2]:
            problems.append(f"overlap in {a[0]}: {a[4]} ({a[3]}, {a[1]:#x}-{a[2]:#x}) and "
                            f"{b[4]} ({b[3]}, {b[1]:#x}-{b[2]:#x})")
    return problems


# --------------------------------------------------------------------------------------
# selection and order
# --------------------------------------------------------------------------------------

def _ids(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = [v]
    return [x.strip() for item in v for x in str(item).split(",") if x.strip()]


def order(fixes) -> list:
    """Topological order of `fixes` by requires (a required fix first), ties by id. Raises on a cycle."""
    by = {f["id"]: f for f in fixes}
    deps = {f["id"]: sorted(r for r in f.get("requires", []) if r in by) for f in fixes}
    out, done, visiting = [], set(), []

    def visit(fid):
        if fid in done:
            return
        if fid in visiting:
            cyc = visiting[visiting.index(fid):] + [fid]
            raise FixError("dependency cycle: " + " -> ".join(cyc))
        visiting.append(fid)
        for d in deps[fid]:
            visit(d)
        visiting.pop()
        done.add(fid)
        out.append(by[fid])

    for fid in sorted(by):
        visit(fid)
    return out


def select(fixes, only=None, without=None, without_kinds=()) -> list:
    """The fixes a build applies, in order. Default: every enabled fix. only: exactly these ids (a
    disabled fix named here is applied too). without: drop these ids. without_kinds: drop every fix of
    these kinds (build.py's --no-glyphs/--no-graphics/--no-hardcoded). Raises FixError on unknown ids,
    or when a selected fix requires one that is not selected."""
    by = {f["id"]: f for f in fixes}
    only, without = _ids(only), _ids(without) or []
    unknown = [i for i in (only or []) + without if i not in by]
    if unknown:
        raise FixError(f"unknown fix id(s): {', '.join(unknown)} (python3 work/tools/fixes.py list)")
    active = set(only) if only is not None else {i for i, f in by.items() if f.get("enabled")}
    active -= set(without)
    active -= {i for i, f in by.items() if f["kind"] in without_kinds}
    problems = []
    for i in sorted(active):
        for r in by[i].get("requires", []):
            if r not in active:
                why = ("excluded by --without" if r in without else
                       "excluded by its kind" if by[r]["kind"] in without_kinds else
                       "not in --only" if only is not None else "disabled (enabled = false)")
                problems.append(f"fix {i!r} requires {r!r}, which is {why}; "
                                f"also leave out {i!r} (--without {i}) or include {r!r}")
    if problems:
        raise FixError("fix selection refused:\n  " + "\n  ".join(problems))
    probs = overlaps([by[i] for i in active])
    if probs:
        raise FixError("fix selection refused:\n  " + "\n  ".join(probs))
    return order([by[i] for i in active])


def active_fixes(only=None, without=None, without_kinds=(), root=PATCHES_DIR) -> list:
    return select(load_all(root), only, without, without_kinds)


# --------------------------------------------------------------------------------------
# views for the appliers (same shapes as the old registries)
# --------------------------------------------------------------------------------------

def _staged(fixes):
    """Fixes in build order: stage (KINDS order), then the given (topological) order."""
    return sorted(fixes, key=lambda f: KINDS.index(f["kind"]))


def code_entries_fixes(fixes) -> list:
    """The fixes among `fixes` that have an armips source (kinds strings, data, code), in build order."""
    return [fx for fx in _staged(fixes) if fx.get("kind") in ASM_KINDS]


def code_entries(fixes, all_enabled=False) -> list:
    """[[code]] regions as a flat list: the entry plus "enabled" (the fix's enabled flag, or True for every
    entry with all_enabled, i.e. `fixes` is a build's selection) and "fix"."""
    out = []
    for fx in _staged(fixes):
        on = True if all_enabled else fx.get("enabled", False)
        for e in fx.get("code", []):
            out.append(dict(e, enabled=bool(on), fix=fx["id"]))
    return out


def strings_config(fixes) -> dict:
    """[[string]] entries of `fixes` (plus "fix") as hardcoded.py's strings document {"strings": [...]}."""
    return {"strings": [dict(e, fix=fx["id"]) for fx in _staged(fixes) for e in fx.get("string", [])]}


def graphics_manifest(fixes) -> list:
    """[[graphics]] entries of `fixes` as gfx.py's manifest (each op plus "fix")."""
    return [dict(e, fix=fx["id"]) for fx in _staged(fixes) for e in fx.get("graphics", [])]


def font_spec(fixes):
    """(narc, fonts, codes) of the [[font]] entries of `fixes`, or None when no font fix is active."""
    ents = [e for fx in _staged(fixes) for e in fx.get("font", [])]
    if not ents:
        return None
    narcs = {e["narc"] for e in ents}
    if len(narcs) != 1 or any(e["source"] != "usa" for e in ents):
        raise FixError("font fixes: only USA-sourced glyphs in one font NARC are supported")
    fonts = sorted({fi for e in ents for fi in e["fonts"]})
    codes = sorted({_int(c) for e in ents for c in e["codes"]})
    return narcs.pop(), tuple(fonts), tuple(codes)


# --------------------------------------------------------------------------------------
# docs
# --------------------------------------------------------------------------------------

def _hw_short(v, n=4):
    hw = halfwords(v)
    s = " ".join(f"{h:04X}" for h in hw[:n])
    return s + (f" … ({len(hw)} halfwords)" if len(hw) > n else "")


def _ram_note(file, off, bases) -> str:
    ram = _ram(file, off, bases)
    return f" (RAM 0x{ram:08X})" if ram is not None else ""


def _touched(fx, bases=None) -> list:
    bases = bases or {}
    lines = []
    for e in fx.get("code", []):
        off = _int(e["offset"])
        ram = _ram_note(e["file"], off, bases)
        n = region_length(e)
        was = f"was `{_hw_short(e['expect'])}`" if "expect" in e else f"original SHA-1 `{e['expect_sha1']}`"
        lines.append(f"`{e['file']}+{e['offset']}`{ram} `{e['id']}`: {n} bytes, {was}")
    for e in fx.get("string", []):
        ptr = f", pointers {', '.join(e['pointers'])}" if e.get("pointers") else ""
        en = e.get("en")
        if not en:
            where = "unchanged"
        elif len(en) <= e["max_units"]:
            where = "in place"
        else:
            where = f"relocated, at most {e.get('reloc_max_units')} characters there"
        lines.append(f"`{e['file']}+{e['offset']}`{_ram_note(e['file'], _int(e['offset']), bases)} "
                     f"(slot of {e['max_units']} characters{ptr}): "
                     f"{e['zh']} → {en!r} ({where})")
    for g in fx.get("grow", []):
        lines.append(f"`{g['file']}`: may grow by up to {g['max']} bytes (appended at its end)")
    for e in fx.get("graphics", []):
        if e["op"] == "code_from_us":
            lines.append(f"`{e['file']}+{e['offset']}`{_ram_note(e['file'], _int(e['offset']), bases)}, "
                         f"{e['length']} bytes ← USA `{e['us_file']}+{e['us_offset']}` (`{e['op']}`)")
            continue
        members = e.get("members") or ([e["member"]] if "member" in e else [int(k) for k in e.get("files", {})])
        ms = ", ".join(f"#{mb}" for mb in members)
        src = e.get("src") or ("USA ROM" if e["op"] in ("copy_us", "tiles_from_us") else
                               ", ".join(sorted({v["src"] for v in e.get("files", {}).values()})))
        also = f" (+ {', '.join(f'`{a}`' for a in e['also'])})" if e.get("also") else ""
        lines.append(f"`{e['narc']}` {ms}{also}: `{e['op']}` from {src}")
    for e in fx.get("font", []):
        lines.append(f"`{e['narc']}` fonts {', '.join(map(str, e['fonts']))}: glyph + width of "
                     f"{', '.join(e['codes'])} from the {e['source'].upper()} ROM")
    return lines


def _paragraphs(text: str) -> str:
    """fix.toml prose is hard-wrapped; in Markdown an 'Old:'/'New:' line starts its own paragraph."""
    out = []
    for line in text.strip().splitlines():
        if line.startswith(("Old:", "New:")) and out and out[-1].strip():
            out.append("")
        out.append(line)
    return "\n".join(out)


def render_docs(fixes, overlay_bases=None) -> str:
    """FIXES.md. overlay_bases: {"overlayNN": ram} (default: overlays.toml next to the fixes)."""
    if overlay_bases is None:
        paths = [f["_path"] for f in fixes if f.get("_path")]
        overlay_bases = load_overlays(paths[0].parent.parent) if paths else {}
    order(fixes)                                  # raises on a cycle
    fixes = sorted(fixes, key=lambda f: (KINDS.index(f["kind"]), f["id"]))   # by build stage, then id
    out = ["# Fixes to the Chinese ROM", "",
           "<!-- Generated by `python3 work/tools/fixes.py docs --out work/patches/FIXES.md` from "
           "work/patches/*/fix.toml. Do not edit by hand. -->", "",
           "Besides the message text (`a/0/2/7`, `battle_string.narc`), the English build changes the untouched "
           "Chinese ROM (`origin_v4.0.3_cn.nds`) only through the fixes below. Each one lives in "
           "`work/patches/<id>/fix.toml`; a code, data or strings fix also has an armips source (`<id>.asm`, shown "
           "under the fix) that writes the new bytes, while fix.toml declares the regions it may change, their "
           "original bytes, the strings' Chinese and English and how far an overlay may grow, and the build "
           "refuses any other change (`work/notes/toolchain.md`). Each fix "
           "checks what it replaces before it writes: code, data, strings and "
           "`code_from_us`/`member_from_file` graphics check the exact bytes (or their SHA-1); `copy_us`, "
           "`tiles_from_file` and `tiles_from_us` check the bit depth and tile count; `tiles_from_png` checks "
           "that the image matches the sheet's tile grid, and `tile_range_from_png` that the range fits the "
           "sheet, both that every palette index is below the bit-depth limit; every replaced NARC member must "
           "keep its format, compression, bit depth, tile "
           "count and mapping; and the font fix checks the glyph size. Each fix can be left out of a build "
           "with `python3 work/tools/build.py --without <id>` (or built alone with `--only`). A fix whose "
           "`requires` names another fix only makes sense together with it; the build refuses to drop one without "
           "the other. Outside the message archives and these fixes, the only other bytes that differ from the "
           "Chinese ROM are container bookkeeping: the ROM header's layout fields, the FAT and the offset at 0x1000 "
           "where the RSA signature is stored move because ndspy rebuilds the ROM container around the changed "
           "files, not because of a fix.", "",
           "Stages (and the order of this list): font → graphics → hardcoded strings → data and code patches. "
           "Offsets are file offsets; for arm9 "
           "and overlays that is the offset in the RAM image, so RAM = load address + offset (arm9 0x02000000; "
           "overlays from the y9 table, recorded in `work/patches/overlays.toml`). Decisions are ids in the "
           "decision register: `python3 work/tools/decisions.py show <id>`.", "",
           "| Fix | Kind | Enabled | Requires | Title |", "|---|---|---|---|---|"]
    for fx in fixes:
        req = ", ".join(f"`{r}`" for r in fx.get("requires", [])) or "–"
        out.append(f"| [`{fx['id']}`](#{fx['id']}) | {fx['kind']} | {'yes' if fx['enabled'] else '**no**'} | "
                   f"{req} | {fx['title']} |")
    for fx in fixes:
        out += ["", f"## {fx['id']}", "", f"**{fx['title']}**", "",
                f"- Kind: {fx['kind']}",
                f"- Enabled: {'yes' if fx['enabled'] else 'no'}",
                f"- Requires: {', '.join(f'`{r}`' for r in fx.get('requires', [])) or 'nothing'}"]
        req_by = [f["id"] for f in fixes if fx["id"] in f.get("requires", [])]
        if req_by:
            out.append(f"- Required by: {', '.join(f'`{r}`' for r in req_by)}")
        out.append(f"- Decisions: {', '.join(fx.get('decisions', [])) or 'none'}")
        if fx.get("_path"):
            src = fx["_path"].resolve()
            out.append(f"- Source: `{src.relative_to(REPO).as_posix() if src.is_relative_to(REPO) else src}`")
        if fx.get("native"):
            nat = fx["native"]
            files = ", ".join(f"`{x}`" for x in [nat["source"]] + nat.get("headers", []))
            out.append(f"- Native code: {files}, compiled into `{nat['payload']}` (reviewed, checked by "
                       f"`work/tools/{nat['module']}.py`); the asm places it with `.incbin`")
        out += ["", "**Why (the Chinese hack):**", "", _paragraphs(fx["why"]), "",
                "**What (old → new):**", "", _paragraphs(fx["what"]), "", "**Evidence:**", ""]
        out += [f"- {ev}" for ev in fx["evidence"]]
        out += ["", "**Touches:**", ""]
        out += [f"- {t}" for t in _touched(fx, overlay_bases)]
        src = asm_path(fx)
        if src is not None and src.is_file():
            rel = src.resolve()
            rel = rel.relative_to(REPO).as_posix() if rel.is_relative_to(REPO) else rel.name
            out += ["", f"**Source** (`{rel}`, armips; the new bytes):", "", "<details>",
                    f"<summary>{src.name}</summary>", "", "```asm", src.read_text(encoding="utf-8").rstrip("\n"),
                    "```", "", "</details>"]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------
# TOML output (for gfx.py generator hints; tomllib only reads)
# --------------------------------------------------------------------------------------

def toml_str(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def toml_key(k: str) -> str:
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else toml_str(k)


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return toml_str(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{toml_key(k)} = {toml_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"cannot write {type(v).__name__} as TOML")


def toml_table(header: str, obj: dict, array=True) -> str:
    """One [[header]] (or [header]) table; nested dicts become [header.key...] subtables."""
    lines = [f"[[{header}]]" if array else f"[{header}]"]
    subs = []
    for k, v in obj.items():
        if isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            subs.append((k, v))
        else:
            lines.append(f"{toml_key(k)} = {toml_value(v)}")
    for k, v in subs:
        for k2, v2 in v.items():
            lines.append(f"[{header}.{toml_key(k)}.{toml_key(k2)}]")
            lines += [f"{toml_key(k3)} = {toml_value(v3)}" for k3, v3 in v2.items()]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------

def _summary(fx) -> str:
    n = {t: len(fx.get(t, [])) for t in ("code", "string", "graphics", "font")}
    parts = [f"{v} {k}" for k, v in n.items() if v]
    return ", ".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(PATCHES_DIR), help="fix folder root (default work/patches)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("show")
    p.add_argument("id")
    p = sub.add_parser("check")
    p.add_argument("--only")
    p.add_argument("--without")
    p = sub.add_parser("docs")
    p.add_argument("--out", help="write here instead of stdout")
    p = sub.add_parser("overlays", help="write overlays.toml (RAM bases of the overlays the fixes touch)")
    p.add_argument("--rom", default=str(ROM_CN))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "overlays":          # may run before overlays.toml exists or is complete
            fixes = load_all(Path(a.root), validate_all=False)
            import msgtool
            print(write_overlays(msgtool.load_rom(a.rom), fixes, Path(a.root)))
            return
        fixes = load_all(Path(a.root))
    except FixError as ex:
        sys.exit(str(ex))
    if a.cmd == "list":
        for fx in order(fixes):
            req = f"  requires {','.join(fx['requires'])}" if fx.get("requires") else ""
            print(f"{fx['id']:28s} {fx['kind']:8s} {'on ' if fx['enabled'] else 'OFF'}  "
                  f"{_summary(fx):22s} {fx['title']}{req}")
    elif a.cmd == "show":
        by = {f["id"]: f for f in fixes}
        if a.id not in by:
            sys.exit(f"unknown fix {a.id!r}")
        print(by[a.id]["_path"].read_text(encoding="utf-8"), end="")
    elif a.cmd == "check":
        try:
            act = select(fixes, a.only, a.without)
        except FixError as ex:
            sys.exit(str(ex))
        n_entries = sum(len(fx.get(t, [])) for fx in fixes for t in ("code", "string", "graphics", "font"))
        print(f"ok: {len(fixes)} fixes, {n_entries} entries; {len(act)} selected: "
              + ", ".join(f["id"] for f in act))
    elif a.cmd == "docs":
        text = render_docs(fixes, load_overlays(Path(a.root)))
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
            print(f"wrote {a.out} ({len(fixes)} fixes)")
        else:
            print(text, end="")


if __name__ == "__main__":
    main()
