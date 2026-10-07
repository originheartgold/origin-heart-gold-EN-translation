#!/usr/bin/env python3
"""hardcoded - Chinese strings stored outside the message NARCs (arm9, overlays, other ROM files).

Source of truth: the fix registry work/patches/<fix-id>/fix.toml, read through fixes.py: the [[string]]
entries and [string_files] of kind-'strings' fixes (outfit-chooser-strings). Notes:
work/notes/hardcoded_text.md; overview: work/patches/FIXES.md.

The code and data fixes (name-length limits, the English naming keyboard, heap fixes ...) are armips
sources, work/patches/<fix>/<fix>.asm, applied by asmpatch.py (the build's default code engine). apply()
below still has the old Python code-patch applier ("code_patches": halfword expect -> value), kept only as the
legacy engine (build.py --code-engine python) that test_asmpatch.py compares the armips output against. Its
entries come from the frozen work/tools/legacy_code_patches.toml (the [[code]] values as of c99993d), not from
work/patches.

[[string]] entries
    id          "<file>:<offset>"  e.g. "overlay58:0x6F0"
    file        "arm9" | "overlayNN" | a ROM path ("a/0/4/1") | "path#member" (NARC member)
    offset      hex offset of the string inside that file (overlay/arm9: offset in the RAM image)
    zh          the Chinese text the slot holds now (checked before writing; the build refuses if the ROM
                does not hold exactly this)
    en          English, or null (= leave the Chinese alone)
    max_units   characters that fit in place (the slot is max_units + 1 code units incl. the 0xFFFF end)
    pointers    optional: offsets (same file) of the 32-bit absolute pointers that reference the string.
                Only with pointers can a longer string be relocated.
    reloc_max_units  optional: longest English allowed when relocated (the consumer's buffer, minus EOS)
    context, notes   free text

Writing rules (apply()):
  * len(en) <= max_units            -> written in place; the rest of the slot is filled with 0xFFFF.
  * else, pointers + reloc_max_units and the file is an uncompressed overlay with "grow_max" set in
    its fix's [string_files.<file>]: the string is appended to the overlay (the overlay grows; its y9 ramSize is
    updated) and every pointer is repointed; the old slot is filled with 0xFFFF. Refused if the overlay has
    .bss, if the growth passes grow_max, or if another overlay starts inside the grown range.
  * anything else is refused (SystemExit with the list of problems).

    python3 work/tools/hardcoded.py check [--rom ROM] [--only IDS] [--without IDS]
                                                             # dry run against the Chinese ROM
    python3 work/tools/hardcoded.py list                     # table of entries and status
    python3 work/tools/hardcoded.py scan ROM [--base US_ROM] [--all-files]
                                                             # look for hack-charmap Chinese outside the
                                                             # message NARCs (the survey that found them)
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import fixes as fixreg  # noqa: E402
import msgtool as m  # noqa: E402

CHARMAPS = [str(TOOLS / "charmap_en.tsv"), str(TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv")]
ZH_CHARMAP = str(TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv")
EXCLUDED = ("a/0/2/7", "battle/string/battle_string.narc")
END = 0xFFFF


class HardcodedError(Exception):
    pass


def _int(v) -> int:
    return v if isinstance(v, int) else int(str(v), 0)


def load(fixes=None) -> dict:
    """The hardcoded-strings document {"files": {...}, "strings": [...]}: from the given active fixes, else
    from every enabled fix in work/patches."""
    if fixes is None:
        fixes = [f for f in fixreg.load_all() if f.get("enabled")]
    return fixreg.strings_config(fixes)


# expect/value parsing: one definition, shared with the registry's validation
halfwords = fixreg.halfwords


def _hw_str(units) -> str:
    return hex(units[0]) if len(units) == 1 else " ".join(f"{u:04X}" for u in units)


LEGACY_CODE_PATCHES = TOOLS / "legacy_code_patches.toml"


def load_code_patches(fixes=None, path=LEGACY_CODE_PATCHES) -> list:
    """The legacy Python engine's code patches (id, file, offset, expect, value, fix, enabled), from the frozen
    legacy_code_patches.toml, in the order of the fixes (build stage, then requires) and of the file.
    fixes=None: every fix in work/patches, "enabled" = the fix's enabled flag. fixes = a build's selection:
    only those fixes' patches, all enabled. Raises HardcodedError when a selected code/data fix has no
    legacy patches (a fix added after the freeze exists only as armips source)."""
    import tomllib
    with open(path, "rb") as f:
        legacy = tomllib.load(f).get("code", [])
    by_fix = collections.OrderedDict()
    for e in legacy:
        by_fix.setdefault(e["fix"], []).append(e)
    all_enabled = fixes is not None
    if fixes is None:
        fixes = fixreg.load_all()
    out = []
    for fx in fixreg.code_entries_fixes(fixes):
        if fx["id"] not in by_fix:
            raise HardcodedError(f"fix {fx['id']}: no legacy Python code patches (it exists only as "
                                 f"{fx.get('asm')}); build with --code-engine armips")
        on = True if all_enabled else bool(fx.get("enabled"))
        out += [dict(e, enabled=on) for e in by_fix[fx["id"]]]
    return out


# --------------------------------------------------------------------------------------
# ROM access: one "image" per file key
# --------------------------------------------------------------------------------------

class RomView:
    """Read/modify arm9, overlays and filesystem files of an ndspy ROM by file key."""

    def __init__(self, rom):
        self.rom = rom
        self._ovs = None

    @property
    def ovs(self):
        if self._ovs is None:
            import ndspy.code
            self._ovs = ndspy.code.loadOverlayTable(self.rom.arm9OverlayTable, lambda i, f: bytes(self.rom.files[f]))
        return self._ovs

    def overlay(self, key):
        mo = re.fullmatch(r"overlay(\d+)", key)
        return self.ovs[int(mo.group(1))] if mo else None

    def base(self, key) -> int:
        if key == "arm9":
            return 0x02000000
        ov = self.overlay(key)
        return ov.ramAddress if ov else 0

    def get(self, key) -> bytes:
        if key == "arm9":
            return bytes(self.rom.arm9)
        ov = self.overlay(key)
        if ov is not None:
            if ov.compressed:
                raise HardcodedError(f"{key}: compressed overlays are not supported")
            return bytes(self.rom.files[ov.fileID])
        path, _, mem = key.partition("#")
        data = m.get_file(self.rom, path)
        if mem:
            return bytes(m.Narc.parse(data).files[int(mem)])
        return data

    def set(self, key, data: bytes):
        if key == "arm9":
            self.rom.arm9 = bytes(data)
            return
        ov = self.overlay(key)
        if ov is not None:
            self.rom.files[ov.fileID] = bytes(data)
            if len(data) != ov.ramSize:
                self._set_ram_size(int(key[7:]), len(data))
            return
        path, _, mem = key.partition("#")
        if mem:
            narc = m.Narc.parse(m.get_file(self.rom, path))
            narc.files[int(mem)] = bytes(data)
            data = narc.build()
        m.set_file(self.rom, path, data)

    def _set_ram_size(self, ov_id, size):
        t = bytearray(self.rom.arm9OverlayTable)
        for row in range(len(t) // 32):
            if struct.unpack_from("<I", t, row * 32)[0] == ov_id:
                struct.pack_into("<I", t, row * 32 + 8, size)
                self.rom.arm9OverlayTable = bytes(t)
                self.ovs[ov_id].ramSize = size
                return
        raise HardcodedError(f"overlay {ov_id} not in the overlay table")

    def table_ram_size(self, ov_id) -> int:
        t = bytes(self.rom.arm9OverlayTable)
        for row in range(len(t) // 32):
            if struct.unpack_from("<I", t, row * 32)[0] == ov_id:
                return struct.unpack_from("<I", t, row * 32 + 8)[0]
        raise HardcodedError(f"overlay {ov_id} not in the overlay table")


def _units(data, off, n):
    return list(struct.unpack_from(f"<{n}H", data, off))


def _pack(units):
    return struct.pack(f"<{len(units)}H", *units)


# --------------------------------------------------------------------------------------
# apply / verify
# --------------------------------------------------------------------------------------

def plan_file(key, entries, data: bytes, base: int, cm, file_cfg: dict, overlays=None, ov_self=None):
    """Return (new_data, report rows, problems) for one file. Pure function (testable without a ROM).
    overlays: list of (id, ram_start, ram_end) of the *other* overlays, for the growth overlap check."""
    out = bytearray(data)
    grow = bytearray()
    rows, problems = [], []
    grow_max = _int(file_cfg.get("grow_max", 0))
    for e in entries:
        off = _int(e["offset"])
        slot = _int(e["max_units"]) + 1
        try:
            zh_units = m.encode_text(e["zh"], cm)
        except ValueError as ex:
            problems.append(f"{e['id']}: zh does not encode: {ex}")
            continue
        if len(zh_units) > slot:
            problems.append(f"{e['id']}: zh is {len(zh_units)} units but max_units+1 is {slot}")
            continue
        if off + 2 * slot > len(data) or _units(data, off, len(zh_units)) != zh_units:
            problems.append(f"{e['id']}: ROM does not hold {e['zh']!r} at {off:#x} (source changed?)")
            continue
        if e.get("en") in (None, ""):
            continue
        try:
            units = m.encode_text(e["en"], cm)
        except ValueError as ex:
            problems.append(f"{e['id']}: en does not encode: {ex}")
            continue
        n = len(units) - 1
        if len(units) <= slot:
            out[off:off + 2 * slot] = _pack(units + [END] * (slot - len(units)))
            rows.append({"id": e["id"], "mode": "in-place", "addr": base + off, "units": len(units), "en": e["en"]})
            continue
        ptrs = [_int(p) for p in e.get("pointers", [])]
        rmax = _int(e.get("reloc_max_units", 0))
        if not ptrs or not rmax:
            problems.append(f"{e['id']}: {e['en']!r} is {n} characters; the slot holds {slot - 1} and the "
                            f"string cannot be relocated (no pointers known)")
            continue
        if n > rmax:
            problems.append(f"{e['id']}: {e['en']!r} is {n} characters; relocated strings may have at most {rmax}")
            continue
        if not grow_max or ov_self is None:
            problems.append(f"{e['id']}: {e['en']!r} needs relocation but {key} has no grow_max / is not an overlay")
            continue
        new_off = len(data) + len(grow)
        bad = [p for p in ptrs if struct.unpack_from("<I", data, p)[0] != base + off]
        if bad:
            problems.append(f"{e['id']}: pointer(s) {[hex(p) for p in bad]} do not point at {base + off:#x}")
            continue
        grow += _pack(units)
        for p in ptrs:
            struct.pack_into("<I", out, p, base + new_off)
        out[off:off + 2 * slot] = _pack([END] * slot)
        rows.append({"id": e["id"], "mode": "relocated", "addr": base + new_off, "units": len(units),
                     "en": e["en"], "pointers": [hex(p) for p in ptrs]})
    if grow:
        while len(grow) % 4:
            grow += b"\xff"
        if len(grow) > grow_max:
            problems.append(f"{key}: relocated strings need {len(grow)} bytes, grow_max is {grow_max}")
        if ov_self is not None and ov_self.get("bss", 0):
            problems.append(f"{key}: overlay has .bss ({ov_self['bss']} bytes); growing it would move .bss")
        lo, hi = base + len(data), base + len(data) + len(grow)
        for oid, s, e_ in overlays or []:
            # an overlay that overlaps the current image can never be loaded together with it; one that
            # overlaps only the grown tail could be, so refuse
            if s < hi and e_ > lo and not (s < base + len(data) and e_ > base):
                problems.append(f"{key}: grown range {lo:#x}-{hi:#x} overlaps overlay {oid} ({s:#x}-{e_:#x})")
        out += grow
    return bytes(out), rows, problems


def _group(entries):
    by = collections.OrderedDict()
    for e in entries:
        by.setdefault(e["file"], []).append(e)
    return by


def apply(rom, cm=None, cfg=None, code_patches=(), dry_run=False):
    """Write every [[string]] entry with en set. code_patches: legacy Python code patches to apply too
    (load_code_patches(); default none - the code/data fixes are applied by asmpatch.apply). Returns a
    report dict. Raises HardcodedError listing every problem; nothing is written if there is any problem."""
    cm = cm or m.Charmap.load(CHARMAPS)
    cfg = cfg if cfg is not None else load()
    code_patches = list(code_patches or ())
    view = RomView(rom)
    files_cfg = cfg.get("files", {})
    writes, rows, problems = {}, [], []
    for key, entries in _group(cfg.get("strings", [])).items():
        data = view.get(key)
        ov = view.overlay(key)
        others = None
        ov_self = None
        if ov is not None:
            ov_self = {"bss": ov.bssSize}
            others = [(i, o.ramAddress, o.ramAddress + o.ramSize + o.bssSize) for i, o in view.ovs.items()
                      if o is not ov]
        new, r, p = plan_file(key, entries, data, view.base(key), cm, files_cfg.get(key, {}), others, ov_self)
        for row in r:
            row["file"] = key
        rows += r
        problems += p
        if new != data:
            writes[key] = new
    patch_rows = []
    for cp in code_patches:
        if not cp.get("enabled"):
            continue
        key, off = cp["file"], _int(cp["offset"])
        data = bytearray(writes.get(key) or view.get(key))
        want, new = halfwords(cp["expect"]), halfwords(cp["value"])
        if len(want) != len(new):
            problems.append(f"code patch {cp['id']}: expect has {len(want)} halfwords, value {len(new)}")
            continue
        cur = _units(data, off, len(want))
        if cur != want:
            problems.append(f"code patch {cp['id']}: {key}+{off:#x} is {_hw_str(cur)}, expected {_hw_str(want)}")
            continue
        struct.pack_into(f"<{len(new)}H", data, off, *new)
        writes[key] = bytes(data)
        patch_rows.append({"id": cp["id"], "file": key, "offset": hex(off), "old": _hw_str(want),
                           "new": _hw_str(new), **({"fix": cp["fix"]} if "fix" in cp else {})})
    if problems:
        raise HardcodedError("hardcoded strings refused:\n  " + "\n  ".join(problems))
    if not dry_run:
        for key, data in writes.items():
            view.set(key, data)
    files = {k: hashlib.sha1(v).hexdigest()[:12] for k, v in writes.items()}
    return {"strings": rows, "code_patches": patch_rows, "files": files,
            "todo": sum(1 for e in cfg.get("strings", []) if not e.get("en"))}


def verify(rom, report, cm=None):
    """Re-read the written ROM: every English string is where the report says, pointers point at it,
    overlay table sizes match the files, and file hashes are what apply() produced."""
    cm = cm or m.Charmap.load(CHARMAPS)
    view = RomView(rom)
    for key, h in report["files"].items():
        data = view.get(key)
        got = hashlib.sha1(data).hexdigest()[:12]
        if got != h:
            raise HardcodedError(f"{key}: sha1 {got} != {h}")
        ov = view.overlay(key)
        if ov is not None and view.table_ram_size(int(key[7:])) != len(data):
            raise HardcodedError(f"{key}: overlay table ramSize != file size {len(data)}")
    for r in report["strings"]:
        data = view.get(r["file"])
        base = view.base(r["file"])
        want = m.encode_text(r["en"], cm)
        if _units(data, r["addr"] - base, len(want)) != want:
            raise HardcodedError(f"{r['id']}: English not found at {r['addr']:#x}")
        for p in r.get("pointers", []):
            if struct.unpack_from("<I", data, int(p, 16))[0] != r["addr"]:
                raise HardcodedError(f"{r['id']}: pointer {p} not repointed")
    for r in report["code_patches"]:
        want = halfwords(r["new"])
        if _units(view.get(r["file"]), int(r["offset"], 16), len(want)) != want:
            raise HardcodedError(f"code patch {r['id']}: {r['file']}+{r['offset']} is not {r['new']}")
    return f"ok ({len(report['strings'])} strings, {len(report['code_patches'])} code patches)"


# --------------------------------------------------------------------------------------
# scan (survey of the ROM for hack-charmap Chinese)
# --------------------------------------------------------------------------------------

def _bigrams():
    big = collections.Counter()
    for d in ("a027", "battle_string"):
        for f in sorted((WORK / "extract" / "v4" / d).glob("0*.json")):
            for s in json.loads(f.read_text(encoding="utf-8")).get("strings", []):
                t = s.get("text", "")
                big.update(a + b for a, b in zip(t, t[1:]))
    return big


def _is_han(c):
    return "一" <= c <= "鿿"


def plausible(text: str, big) -> bool:
    """Chinese-looking: at least one hanzi pair, >= 60 % of the (non-repeated) hanzi pairs are seen in the
    game's own message text at least twice."""
    t = re.sub(r"\{[^}]*\}", "?", text)
    pairs = [t[i:i + 2] for i in range(len(t) - 1) if _is_han(t[i]) and _is_han(t[i + 1]) and t[i] != t[i + 1]]
    if not pairs:
        return False
    good = sum(big[p] >= 2 for p in pairs)
    return good / len(pairs) >= 0.6


def scan_blob(data: bytes, cm_zh, big):
    """Yield (offset, units, text) for 0xFFFF-terminated runs of charmap codes that read as Chinese."""
    ok = lambda c: 1 <= c <= 0x1C9B or c == 0xE000  # noqa: E731
    tbl = bytes((49 if (h <= 0x1C or h == 0xE0) else 48) for h in range(256))
    for al in (0, 1):
        n = (len(data) - al) // 2
        if n < 3:
            continue
        hb = data[al + 1:al + 2 * n:2].translate(tbl)
        u = None
        for mo in re.finditer(rb"1{2,}", hb):
            a, b = mo.span()
            if b >= n:
                continue
            if u is None:
                u = struct.unpack_from(f"<{n}H", data, al)
            if u[b] != END:
                continue
            i = a
            while i < b and not ok(u[i]):
                i += 1
            seg = u[i:b]
            if not all(ok(c) for c in seg):
                continue
            if sum(1 for c in seg if 0x1FF <= c <= 0x1C9B) < 2:
                continue
            text = "".join("\\n" if c == 0xE000 else cm_zh.dec.get(c, "{%04X}" % c) for c in seg)
            if plausible(text, big):
                yield al + 2 * i, len(seg), text


def scan_rom(path, base_path=None, all_files=True):
    import ndspy.codeCompression
    import ndspy.lz10
    rom = m.load_rom(path)
    cm_zh = m.Charmap.load([ZH_CHARMAP])
    big = _bigrams()
    us_hashes = set()
    if base_path:
        us = m.load_rom(base_path)
        for f in us.files:
            us_hashes.add(hashlib.sha1(f).hexdigest())
            if f[:4] == b"NARC":
                try:
                    us_hashes.update(hashlib.sha1(x).hexdigest() for x in m.Narc.parse(f).files)
                except Exception:
                    pass
    view = RomView(rom)
    blobs = [("arm9", ndspy.codeCompression.decompress(bytes(rom.arm9)))]
    blobs += [(f"overlay{k}", o.data) for k, o in sorted(view.ovs.items())]
    ov_files = {o.fileID for o in view.ovs.values()}
    if all_files:
        for fid, d in enumerate(rom.files):
            name = rom.filenames.filenameOf(fid)
            if fid in ov_files or name in EXCLUDED or name is None:
                continue
            d = bytes(d)
            if hashlib.sha1(d).hexdigest() in us_hashes:
                continue
            blobs.append((name, d))
            if d[:4] == b"NARC":
                try:
                    members = m.Narc.parse(d).files
                except Exception:
                    members = []
                for i, x in enumerate(members):
                    if hashlib.sha1(x).hexdigest() in us_hashes:
                        continue
                    blobs.append((f"{name}#{i}", x))
                    if x[:1] == b"\x10" and len(x) > 4:
                        try:
                            blobs.append((f"{name}#{i}[lz10]", ndspy.lz10.decompress(x)))
                        except Exception:
                            pass
    for name, d in blobs:
        for off, n, text in scan_blob(bytes(d), cm_zh, big):
            yield name, off, n, text


# --------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="dry-run apply against the Chinese ROM")
    p.add_argument("--rom", default=str(WORK / "rom" / "origin_v4.0.3_cn.nds"))
    p.add_argument("--only", help="comma-separated fix ids (default: every enabled fix)")
    p.add_argument("--without", help="comma-separated fix ids to leave out")
    p.add_argument("--code-engine", choices=("armips", "python"), default="armips",
                   help="code/data fixes: assemble their armips sources (asmpatch.py, default) or apply the "
                        "legacy Python patches")
    p.add_argument("--armips", help="armips executable (default: $ARMIPS, then PATH)")
    sub.add_parser("list")
    p = sub.add_parser("scan")
    p.add_argument("rom")
    p.add_argument("--base", help="USA ROM: skip files/members identical to it")
    p.add_argument("--code-only", action="store_true", help="arm9 and overlays only")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        try:
            act = fixreg.active_fixes(a.only, a.without)
        except fixreg.FixError as ex:
            sys.exit(str(ex))
        import asmpatch
        rom = m.load_rom(a.rom)
        try:
            if a.code_engine == "python":
                rep = apply(rom, cfg=load(fixes=act), code_patches=load_code_patches(fixes=act), dry_run=True)
            else:
                rep = apply(rom, cfg=load(fixes=act), code_patches=[], dry_run=True)
                if fixreg.code_entries_fixes(act):
                    armips = asmpatch.find_armips(a.armips)
                    asmpatch.check_armips(armips)
                    rep["code_patches"] = asmpatch.apply(rom, act, armips, dry_run=True)["code_patches"]
        except (HardcodedError, asmpatch.AsmError) as ex:
            sys.exit(str(ex))
        for r in rep["strings"]:
            print(f"  {r['id']:20s} {r['mode']:9s} -> {r['addr']:#x}  {r['en']!r}")
        for r in rep["code_patches"]:
            print(f"  code patch {r['id']}: {r['file']}+{r['offset']} {r['old']} -> {r['new']}")
        print(f"ok: {len(rep['strings'])} strings would be written, {rep['todo']} still untranslated; "
              f"{len(rep['code_patches'])} code/data regions ({a.code_engine})")
    elif a.cmd == "list":
        for e in load()["strings"]:
            st = "todo" if not e.get("en") else "set"
            print(f"{e['id']:20s} {st:4s} max {e['max_units']:>2} {e['zh']!r:14s} -> {e.get('en')!r}  [{e.get('context', '')}]")
    elif a.cmd == "scan":
        n = 0
        for name, off, units, text in scan_rom(a.rom, a.base, not a.code_only):
            print(f"{name}\t{off:#x}\t{units}\t{text}")
            n += 1
        print(f"{n} candidate strings", file=sys.stderr)


if __name__ == "__main__":
    main()
