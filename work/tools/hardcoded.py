#!/usr/bin/env python3
"""hardcoded - Chinese strings stored outside the message NARCs (arm9, overlays, other ROM files).

What is left here after the strings fix moved to armips (2026-10-08):
  * load() / `list`: the [[string]] entries of the enabled kind-'strings' fixes (work/patches/<fix>/fix.toml,
    read through fixes.py): zh, en, slot size, pointers, relocation limit. Translators edit `en` there, and
    the text checks (text_consumer_check.py, text_safety_check.py) read them. The bytes are written by the
    fix's armips source (outfit-chooser-strings.asm), applied by asmpatch.py like every code/data fix; the
    build refuses when the asm's strings and the entries' en differ.
  * RomView: arm9 / overlay / filesystem access by file key, shared with asmpatch.py; setting an overlay of
    another size also sets its ramSize in the y9 overlay table.
  * `scan`: the survey that looks for hack-charmap Chinese outside the message NARCs (it found the four
    outfit-chooser labels in overlay 58 and nothing else player-facing).
Notes: work/notes/hardcoded_text.md; overview: work/patches/FIXES.md.

[[string]] entries (schema: fixes.py)
    id          "<file>:<offset>"  e.g. "overlay58:0x6F0"
    file        "arm9" | "overlayNN"
    offset      hex offset of the slot (offset in the RAM image)
    zh          the Chinese the slot holds (the build checks it before assembling)
    en          English, or unset (= leave the Chinese alone); must equal the asm's .string literal
    max_units   characters that fit in place (the slot is max_units + 1 code units incl. the 0xFFFF end)
    pointers    optional: offsets (same file) of the 32-bit absolute pointers that reference the string
    reloc_max_units  optional: longest English allowed when relocated (the consumer's buffer, minus EOS)
    context, notes   free text

    python3 work/tools/hardcoded.py list                     # table of entries and status
    python3 work/tools/hardcoded.py scan ROM [--base US_ROM] [--code-only]
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

ZH_CHARMAP = str(TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv")
EXCLUDED = ("a/0/2/7", "battle/string/battle_string.narc")
END = 0xFFFF


class HardcodedError(Exception):
    pass


def load(fixes=None) -> dict:
    """The hardcoded-strings document {"strings": [...]} (each [[string]] entry plus "fix"): from the given
    active fixes, else from every enabled fix in work/patches."""
    if fixes is None:
        fixes = [f for f in fixreg.load_all() if f.get("enabled")]
    return fixreg.strings_config(fixes)


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
            old_len = len(self.rom.files[ov.fileID])
            self.rom.files[ov.fileID] = bytes(data)
            if len(data) != old_len:                 # grown (or shrunk): the y9 ramSize follows the file
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
    sub.add_parser("list")
    p = sub.add_parser("scan")
    p.add_argument("rom")
    p.add_argument("--base", help="USA ROM: skip files/members identical to it")
    p.add_argument("--code-only", action="store_true", help="arm9 and overlays only")
    a = ap.parse_args(argv)
    if a.cmd == "list":
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
