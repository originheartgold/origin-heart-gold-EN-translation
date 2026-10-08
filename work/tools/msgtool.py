#!/usr/bin/env python3
"""msgtool - Pokémon HeartGold/SoulSilver (Gen IV) message tooling for the
起源心金 / Origin HeartGold English translation project.

Subcommands
  unpack         <rom.nds> <outdir>                        dump NitroFS + arm9/arm7/overlays/header
  extract        <rom.nds> <out_dir> --charmap C [...]     message NARC -> one JSON per bank
  insert         <rom.nds> <in_dir> <out.nds> --charmap C  JSON banks -> rebuilt ROM
  roundtrip      <rom.nds> --charmap C                     extract+rebuild in memory, assert identical NARC
  charmap-guess  ...                                       infer code->char pairs from known strings
  charmap-import <src> <out.tsv>                            convert pret charmap.txt / Xzonn CharTable.txt to TSV
  patch-preview  <patch.delta> <out.nds>                    build a partial target ROM from an xdelta patch WITHOUT the base ROM
  check-base     <rom.nds> [--patch P]                      hash a candidate base ROM, compare to known dumps, test-apply patch
  glyph          <rom.nds> <code> [...]                     ASCII-render glyphs from the font NARC (a/0/1/6)

Text representation (JSON "text" field)
  plain characters     via the charmap (several --charmap files may be stacked, later ones override)
  {NEWLINE}            0xE000
  {SCROLL}             0x25BC  (wait, clear box, reset cursor)            pret: \\r
  {CLEAR}              0x25BD  (wait, scroll up one line)          pret: \\f
  {VAR:XXXX:a,b,...}   0xFFFE command, XXXX = command id (hex), args decimal u16.
                       STRVAR commands are 0x01XX/0x03XX/0x04XX/0x34XX (low byte = var kind),
                       0x0200 YESNO, 0x0201 PAUSE, 0x0202 WAIT, 0x0203/0x0204 CURSOR_X/Y,
                       0x0205/0x0206 align center/right, 0xFF00 COLOR, 0xFF01 SIZE.
  {COMPRESSED}         at start of text: string is stored 9-bit packed (0xF100 header)
  {U+XXXX}             raw code unit with no (canonical) charmap entry
  0xFFFF terminator is implicit; "pad": k = k extra 0xFFFF units after it (kept for byte-exactness).
  A JSON string entry has "raw_hex" only when the text above cannot reproduce the
  original code units exactly; insert then uses raw_hex as long as "text" is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

MSG_NARC_PATH = "a/0/2/7"      # files/msgdata/msg.narc in pret/pokeheartgold
FONT_NARC_PATH = "a/0/1/6"     # graphic/font.narc

CODE_NEWLINE = 0xE000
CODE_SCROLL = 0x25BC
CODE_CLEAR = 0x25BD
CODE_CMD = 0xFFFE
CODE_END = 0xFFFF
CODE_COMPRESSED = 0xF100

SPECIAL_TAGS = {CODE_NEWLINE: "NEWLINE", CODE_SCROLL: "SCROLL", CODE_CLEAR: "CLEAR"}
TAG_TO_CODE = {v: k for k, v in SPECIAL_TAGS.items()}


# --------------------------------------------------------------------------------------
# Encryption (identical to pret/pokeheartgold tools/msgenc MessagesConverter.h)
# --------------------------------------------------------------------------------------

def _table_key(seed: int, index1: int) -> int:
    k = (seed * 0x2FD * index1) & 0xFFFF
    return k | (k << 16)


def _crypt_units(units: list[int], index1: int) -> list[int]:
    key = (0x91BD3 * index1) & 0xFFFF
    out = []
    for u in units:
        out.append(u ^ key)
        key = (key + 0x493D) & 0xFFFF
    return out


def decrypt_bank(data: bytes) -> tuple[int, list[list[int]], bytes]:
    """Return (seed, [code-unit lists], trailer bytes after the last string)."""
    count, seed = struct.unpack_from("<HH", data, 0)
    strings = []
    end = 4 + 8 * count
    expect = end
    for i in range(count):
        k = _table_key(seed, i + 1)
        off, ln = struct.unpack_from("<II", data, 4 + 8 * i)
        off ^= k
        ln ^= k
        if off != expect:
            raise ValueError(f"non-sequential string layout at entry {i} (off {off:#x}, expected {expect:#x})")
        if off + 2 * ln > len(data):
            raise ValueError(f"entry {i} overruns bank ({off:#x}+{2*ln:#x} > {len(data):#x})")
        units = list(struct.unpack_from(f"<{ln}H", data, off))
        strings.append(_crypt_units(units, i + 1))
        expect = off + 2 * ln
    return seed, strings, bytes(data[expect:])


def encrypt_bank(seed: int, strings: list[list[int]], trailer: bytes = b"") -> bytes:
    count = len(strings)
    table = bytearray()
    body = bytearray()
    pos = 4 + 8 * count
    for i, units in enumerate(strings):
        k = _table_key(seed, i + 1)
        table += struct.pack("<II", pos ^ k, len(units) ^ k)
        body += struct.pack(f"<{len(units)}H", *_crypt_units(units, i + 1))
        pos += 2 * len(units)
    return struct.pack("<HH", count, seed) + bytes(table) + bytes(body) + bytes(trailer)


# --------------------------------------------------------------------------------------
# 9-bit compressed strings (0xF100) - used for some trainer / Pokémon names
# --------------------------------------------------------------------------------------

def decompress_units(units: list[int]) -> tuple[list[int], int]:
    """units[0] must be 0xF100. Returns (codes, number of units consumed incl. header)."""
    p, bit, out = 1, 0, []
    while p < len(units):
        cur = (units[p] >> bit) & 0x1FF
        bit += 9
        if bit >= 15:
            p += 1
            bit -= 15
            if bit and p < len(units):
                cur |= (units[p] << (9 - bit)) & 0x1FF
        if cur == 0x1FF:
            break
        out.append(cur)
    consumed = p + (1 if bit else 0)
    return out, min(consumed, len(units))


def compress_codes(codes: list[int]) -> list[int]:
    """Inverse of decompress_units, matching the game data: 9-bit codes packed LSB-first into
    15-bit units, the last partial unit filled with 1-bits, then a 0xFFFF unit (which also
    supplies the 0x1FF end marker)."""
    for c in codes:
        if c >= 0x1FF:
            raise ValueError(f"code {c:#x} cannot be stored in a compressed (9-bit) string")
    out, acc, nbits = [CODE_COMPRESSED], 0, 0
    for v in codes:
        acc |= v << nbits
        nbits += 9
        while nbits >= 15:
            out.append(acc & 0x7FFF)
            acc >>= 15
            nbits -= 15
    if nbits:
        out.append((acc | (0x7FFF << nbits)) & 0x7FFF)
    out.append(CODE_END)
    return out


def stored_name_text(text: str, cm: "Charmap", compress: bool = True, max_units: int = 8) -> str:
    """The form in which a name is stored in a fixed-buffer name bank (trainer names, a027/0719).

    compress=True: '{COMPRESSED}' + text, as US stores its trainer names, when every code is < 0x1FF;
    otherwise (a Chinese fallback, a {VAR} tag) the plain text. compress=False: always the plain text.
    Raises ValueError if the stored units, incl. the 0xFFFF terminator, exceed max_units: the game
    copies these strings into u16[max_units] and drops a string that does not fit."""
    if text.startswith("{COMPRESSED}"):
        text = text[len("{COMPRESSED}"):]
    out = text
    units = None
    if compress:
        try:
            units = encode_text("{COMPRESSED}" + text, cm)
            out = "{COMPRESSED}" + text
        except ValueError:
            units = None
    if units is None:
        units = encode_text(text, cm)
    if len(units) > max_units:
        raise ValueError(f"{text!r} needs {len(units)} units as stored ({'compressed' if out != text else 'plain'}), "
                         f"the buffer holds {max_units}")
    return out


# --------------------------------------------------------------------------------------
# Charmap
# --------------------------------------------------------------------------------------

class Charmap:
    """code (u16) <-> text. TSV lines: 'XXXX<TAB>text[<TAB>anything]'; '#' starts a comment line.
    Escapes in text: \\t, \\\\, \\xXXXX not needed normally."""

    def __init__(self):
        self.dec: dict[int, str] = {}
        self.enc: dict[str, int] = {}
        self.maxlen = 1

    @classmethod
    def load(cls, paths) -> "Charmap":
        cm = cls()
        for p in paths:
            cm.add_file(p)
        return cm

    def add_file(self, path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 2 or not re.fullmatch(r"[0-9A-Fa-f]{4}", parts[0]):
                    continue
                self.set(int(parts[0], 16), parts[1].replace("\\t", "\t").replace("\\\\", "\\"))

    def set(self, code: int, text: str):
        """Later definitions of a code override earlier ones. If several codes share a
        text, the lowest code is the canonical encoding; the others decode as {U+XXXX}."""
        if not text or "{" in text or "}" in text:
            return
        old = self.dec.get(code)
        self.dec[code] = text
        if old is not None and old != text and self.enc.get(old) == code:
            others = [c for c, t in self.dec.items() if t == old]
            if others:
                self.enc[old] = min(others)
            else:
                del self.enc[old]
        if text not in self.enc or code < self.enc[text] or self.dec.get(self.enc[text]) != text:
            self.enc[text] = code
        self.maxlen = max(self.maxlen, len(text))

    def canonical(self, code: int) -> str | None:
        t = self.dec.get(code)
        if t is not None and self.enc.get(t) == code:
            return t
        return None


# --------------------------------------------------------------------------------------
# Decode / encode between code units and tagged text
# --------------------------------------------------------------------------------------

def _render_codes(codes, cm: Charmap, out: list[str]):
    for c in codes:
        if c in SPECIAL_TAGS:
            out.append("{" + SPECIAL_TAGS[c] + "}")
            continue
        t = cm.canonical(c)
        out.append(t if t is not None else "{U+%04X}" % c)


def decode_units(units: list[int], cm: Charmap) -> str:
    """Render code units (incl. terminator) to tagged text. Never fails; exactness is
    checked separately by re-encoding."""
    out: list[str] = []
    if units and units[0] == CODE_COMPRESSED:
        codes, _ = decompress_units(units)
        out.append("{COMPRESSED}")
        _render_codes(codes, cm, out)
        return "".join(out)
    i = 0
    n = len(units)
    while i < n:
        c = units[i]
        if c == CODE_END:
            break
        if c == CODE_CMD and i + 2 < n and i + 3 + units[i + 2] <= n:
            cmd, argc = units[i + 1], units[i + 2]
            args = units[i + 3:i + 3 + argc]
            out.append("{VAR:%04X%s}" % (cmd, (":" + ",".join(str(a) for a in args)) if args else ""))
            i += 3 + argc
            continue
        _render_codes([c], cm, out)
        i += 1
    return "".join(out)


_TAG_RE = re.compile(r"\{([^{}]*)\}")


def encode_text(text: str, cm: Charmap) -> list[int]:
    compressed = False
    if text.startswith("{COMPRESSED}"):
        compressed = True
        text = text[len("{COMPRESSED}"):]
    units: list[int] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            m = _TAG_RE.match(text, i)
            if not m:
                raise ValueError(f"unterminated tag at {i}: {text[i:i+20]!r}")
            tag = m.group(1)
            i = m.end()
            if tag in TAG_TO_CODE:
                units.append(TAG_TO_CODE[tag])
            elif re.fullmatch(r"U\+[0-9A-Fa-f]{1,4}", tag):
                units.append(int(tag[2:], 16))
            elif tag.startswith("VAR:"):
                parts = tag.split(":")
                cmd = int(parts[1], 16)
                args = [int(a, 0) for a in parts[2].split(",")] if len(parts) > 2 and parts[2] != "" else []
                units += [CODE_CMD, cmd, len(args)] + args
            else:
                raise ValueError(f"unknown tag {{{tag}}}")
            continue
        if ch == "\n" and "\n" not in cm.enc:
            units.append(CODE_NEWLINE)
            i += 1
            continue
        for L in range(min(cm.maxlen, n - i), 0, -1):
            code = cm.enc.get(text[i:i + L])
            if code is not None:
                units.append(code)
                i += L
                break
        else:
            raise ValueError(f"character {ch!r} (U+{ord(ch):04X}) not in charmap")
    if compressed:
        return compress_codes(units)
    return units + [CODE_END]


# --------------------------------------------------------------------------------------
# NARC (layout-preserving: keeps BTNF verbatim, 0xFF padding to 4 bytes like the originals)
# --------------------------------------------------------------------------------------

class Narc:
    def __init__(self, files, btnf=b"\x04\x00\x00\x00\x00\x00\x01\x00", pad_byte=0xFF, pad_last=True,
                 bom_ver=(0xFFFE, 0x0100), size_quirks=(0, 0)):
        self.files = list(files)
        # (NARC total-size field - real size, GMIF size field - real size): some tools
        # (e.g. the one that built v3 Cn) write inconsistent size fields; keep them for byte-exactness
        self.size_quirks = size_quirks
        self.btnf = btnf           # BTNF payload (without 8-byte section header)
        self.pad_byte = pad_byte
        self.pad_last = pad_last
        self.bom_ver = bom_ver

    @classmethod
    def parse(cls, data: bytes) -> "Narc":
        magic, bom, ver, total, hsize, nsec = struct.unpack_from("<4sHHIHH", data, 0)
        if magic != b"NARC":
            raise ValueError("not a NARC")
        pos = hsize
        sections = {}
        for _ in range(nsec):
            m, size = struct.unpack_from("<4sI", data, pos)
            sections[m] = (pos, size)
            pos += size
        bpos, _ = sections[b"BTAF"]
        count = struct.unpack_from("<I", data, bpos + 8)[0]
        entries = [struct.unpack_from("<II", data, bpos + 12 + 8 * i) for i in range(count)]
        npos, nsize = sections[b"BTNF"]
        gpos, gsize = sections[b"GMIF"]
        base = gpos + 8
        files = [bytes(data[base + a:base + b]) for a, b in entries]
        pad_byte = 0xFF
        for i in range(count - 1):
            if entries[i + 1][0] > entries[i][1]:
                pad_byte = data[base + entries[i][1]]
                break
        real_gsize = len(data) - gpos
        pad_last = bool(entries) and (real_gsize - 8) != entries[-1][1]
        return cls(files, bytes(data[npos + 8:npos + nsize]), pad_byte, pad_last, (bom, ver),
                   (total - len(data), gsize - real_gsize))

    def build(self) -> bytes:
        gmif = bytearray()
        btaf = bytearray()
        for i, f in enumerate(self.files):
            start = len(gmif)
            gmif += f
            btaf += struct.pack("<II", start, len(gmif))
            if i < len(self.files) - 1 or self.pad_last:
                while len(gmif) % 4:
                    gmif.append(self.pad_byte)
        btaf_sec = b"BTAF" + struct.pack("<II", 12 + len(btaf), len(self.files)) + bytes(btaf)
        btnf_sec = b"BTNF" + struct.pack("<I", 8 + len(self.btnf)) + self.btnf
        gmif_sec = b"GMIF" + struct.pack("<I", (8 + len(gmif) + self.size_quirks[1]) & 0xFFFFFFFF) + bytes(gmif)
        body = btaf_sec + btnf_sec + gmif_sec
        total = (16 + len(body) + self.size_quirks[0]) & 0xFFFFFFFF
        return struct.pack("<4sHHIHH", b"NARC", self.bom_ver[0], self.bom_ver[1], total, 16, 3) + body


# --------------------------------------------------------------------------------------
# Bank <-> JSON
# --------------------------------------------------------------------------------------

def bank_to_json(bank_no: int, data: bytes, cm: Charmap) -> dict:
    try:
        seed, strings, trailer = decrypt_bank(data)
    except Exception as e:  # undecodable bank: keep bytes verbatim
        return {"bank": bank_no, "error": str(e), "raw_bank_hex": data.hex()}
    out = {"bank": bank_no, "seed": seed, "strings": []}
    if trailer:
        out["trailer_hex"] = trailer.hex()
    for i, units in enumerate(strings):
        text = decode_units(units, cm)
        entry = {"id": i, "text": text}
        pad = 0
        if units and units[0] != CODE_COMPRESSED:
            while len(units) - pad >= 2 and units[len(units) - pad - 1] == CODE_END and units[len(units) - pad - 2] == CODE_END:
                pad += 1          # extra 0xFFFF fill after the terminator (v3 builds use fixed-size slots)
        try:
            exact = encode_text(text, cm) + [CODE_END] * pad == units
        except Exception:
            exact = False
        if not exact:
            entry["raw_hex"] = struct.pack(f"<{len(units)}H", *units).hex()
        elif pad:
            entry["pad"] = pad
        out["strings"].append(entry)
    return out


def json_to_bank(obj: dict, cm: Charmap) -> bytes:
    if "raw_bank_hex" in obj:
        return bytes.fromhex(obj["raw_bank_hex"])
    strings = []
    for e in obj["strings"]:
        if "raw_hex" in e:
            raw = bytes.fromhex(e["raw_hex"])
            units = list(struct.unpack(f"<{len(raw)//2}H", raw))
            if decode_units(units, cm) == e["text"]:
                strings.append(units)       # text untouched -> keep exact original units
                continue
        try:
            strings.append(encode_text(e["text"], cm) + [CODE_END] * int(e.get("pad", 0)))
        except ValueError as ex:
            raise ValueError(f"bank {obj['bank']} string {e['id']}: {ex}") from None
    return encrypt_bank(obj["seed"], strings, bytes.fromhex(obj.get("trailer_hex", "")))


# --------------------------------------------------------------------------------------
# ROM helpers
# --------------------------------------------------------------------------------------

def load_rom(path):
    import ndspy.rom
    return ndspy.rom.NintendoDSRom.fromFile(str(path))


def get_file(rom, name) -> bytes:
    return bytes(rom.files[rom.filenames.idOf(name)])


def set_file(rom, name, data: bytes):
    rom.files[rom.filenames.idOf(name)] = bytes(data)


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------

def cmd_unpack(a):
    rom = load_rom(a.rom)
    out = Path(a.outdir)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "header.bin").write_bytes(bytes(open(a.rom, "rb").read(0x200)))
    (out / "arm9.bin").write_bytes(bytes(rom.arm9))
    (out / "arm7.bin").write_bytes(bytes(rom.arm7))
    (out / "arm9ovltable.bin").write_bytes(bytes(rom.arm9OverlayTable))
    (out / "arm7ovltable.bin").write_bytes(bytes(rom.arm7OverlayTable))
    (out / "banner.bin").write_bytes(bytes(rom.iconBanner))
    ov = out / "overlay9"
    ov.mkdir(exist_ok=True)
    for oid, o in rom.loadArm9Overlays().items():
        (ov / f"overlay9_{oid:04d}.bin").write_bytes(bytes(rom.files[o.fileID]))
    n = 0
    for fid, f in enumerate(rom.files):
        try:
            name = rom.filenames.filenameOf(fid)
        except Exception:
            name = None
        if not name:
            continue
        p = out / "data" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(bytes(f))
        n += 1
    print(f"unpacked {n} files + arm9/arm7/overlays to {out}  (title {rom.name!r}, code {bytes(rom.idCode)!r})")


def _msg_narc(rom, path=None):
    return Narc.parse(get_file(rom, path or MSG_NARC_PATH))


def cmd_extract(a):
    cm = Charmap.load(a.charmap)
    rom = load_rom(a.rom)
    narc = _msg_narc(rom, a.narc)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    nraw = nunk = 0
    for bi, data in enumerate(narc.files):
        obj = bank_to_json(bi, data, cm)
        for e in obj.get("strings", []):
            nraw += "raw_hex" in e
            nunk += e["text"].count("{U+")
        with open(out / f"{bi:04d}.json", "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    meta = {"rom": str(a.rom), "narc": a.narc or MSG_NARC_PATH, "banks": len(narc.files),
            "narc_btnf_hex": narc.btnf.hex(), "pad_last": narc.pad_last, "charmaps": a.charmap}
    (out / "_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"extracted {len(narc.files)} banks to {out}; strings needing raw_hex: {nraw}; unknown-code tags: {nunk}")


def build_msg_narc(template: Narc, in_dir: Path, cm: Charmap) -> Narc:
    files = list(template.files)
    for p in sorted(in_dir.glob("[0-9]*.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        bi = obj["bank"]
        while bi >= len(files):
            files.append(b"")
        files[bi] = json_to_bank(obj, cm)
    return Narc(files, template.btnf, template.pad_byte, template.pad_last, template.bom_ver,
                template.size_quirks)


def cmd_insert(a):
    cm = Charmap.load(a.charmap)
    rom = load_rom(a.rom)
    narc = build_msg_narc(_msg_narc(rom, a.narc), Path(a.in_dir), cm)
    set_file(rom, a.narc or MSG_NARC_PATH, narc.build())
    rom.saveToFile(str(a.out))
    print(f"wrote {a.out}")


def cmd_roundtrip(a):
    cm = Charmap.load(a.charmap)
    rom = load_rom(a.rom)
    path = a.narc or MSG_NARC_PATH
    orig = get_file(rom, path)
    narc = Narc.parse(orig)
    assert narc.build() == orig, "NARC container rebuild is not byte-identical"
    with tempfile.TemporaryDirectory() as td:
        ns = argparse.Namespace(rom=a.rom, out_dir=td, charmap=a.charmap, narc=path)
        cmd_extract(ns)
        rebuilt = build_msg_narc(narc, Path(td), cm).build()
        # also exercise the "edited text" path: re-encode every exact string from text only
        for p in sorted(Path(td).glob("[0-9]*.json")):
            obj = json.loads(p.read_text(encoding="utf-8"))
            for e in obj.get("strings", []):
                if "raw_hex" not in e:
                    encode_text(e["text"], cm)
    if rebuilt != orig:
        n1 = Narc.parse(rebuilt)
        diff = [i for i, (x, y) in enumerate(zip(narc.files, n1.files)) if x != y]
        print(f"FAIL: rebuilt message NARC differs (banks {diff[:20]}...)")
        sys.exit(1)
    if a.rebuild_rom:
        set_file(rom, path, rebuilt)
        import ndspy.rom
        rom2 = ndspy.rom.NintendoDSRom(rom.save())
        assert get_file(rom2, path) == orig
    print(f"OK: message NARC round-trips byte-identically ({len(orig)} bytes, {len(narc.files)} banks)")


# ---- charmap-guess -------------------------------------------------------------------

_IGNORED = {CODE_END, CODE_NEWLINE, CODE_SCROLL, CODE_CLEAR}


def _strip_units(units):
    """Printable code units only (drops commands/control codes)."""
    if units and units[0] == CODE_COMPRESSED:
        units, _ = decompress_units(units)
    out, i = [], 0
    while i < len(units):
        c = units[i]
        if c == CODE_END:
            break
        if c == CODE_CMD and i + 2 < len(units):
            i += 3 + units[i + 2]
            continue
        if c not in _IGNORED:
            out.append(c)
        i += 1
    return out


def _parse_hex_units(s: str):
    s = s.strip()
    toks = s.replace(",", " ").split()
    if len(toks) == 1 and len(toks[0]) > 4:          # contiguous little-endian hex bytes
        raw = bytes.fromhex(toks[0])
        return list(struct.unpack(f"<{len(raw)//2}H", raw))
    return [int(t, 16) for t in toks]


def guess_charmap(pairs, known: Charmap | None = None):
    """pairs: iterable of (text, units). Returns (votes{code:{char:n}}, skipped[(text,units,reason)])."""
    votes: dict[int, dict[str, int]] = {}
    skipped = []
    for text, units in pairs:
        cu = _strip_units(units)
        chars = [c for c in text if c not in "\n\r"]
        if len(cu) != len(chars):
            skipped.append((text, units, f"length mismatch {len(chars)} chars vs {len(cu)} codes"))
            continue
        for code, ch in zip(cu, chars):
            votes.setdefault(code, {}).setdefault(ch, 0)
            votes[code][ch] += 1
    return votes, skipped


def cmd_charmap_guess(a):
    pairs = []
    if a.pairs:
        with open(a.pairs, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("#") or "\t" not in line:
                    continue
                text, hexs = line.split("\t", 1)
                pairs.append((text, _parse_hex_units(hexs)))
    if a.rom:
        if a.bank is None or not a.known:
            sys.exit("--rom requires --bank and --known")
        rom = load_rom(a.rom)
        _, strings, _ = decrypt_bank(_msg_narc(rom, a.narc).files[a.bank])
        with open(a.known, encoding="utf-8") as f:
            known_lines = [l.rstrip("\n") for l in f]
        for i, line in enumerate(known_lines):
            j = i + a.offset
            if line and 0 <= j < len(strings):
                pairs.append((line, strings[j]))
    base = Charmap.load(a.charmap) if a.charmap else None
    votes, skipped = guess_charmap(pairs, base)
    conflicts = agree = disagree = new = 0
    rows = []
    for code in sorted(votes):
        cands = sorted(votes[code].items(), key=lambda kv: -kv[1])
        best, n = cands[0]
        status = ""
        if len(cands) > 1:
            conflicts += 1
            status = "CONFLICT " + " ".join(f"{c}:{k}" for c, k in cands)
        if base is not None:
            have = base.dec.get(code)
            if have is None:
                new += 1
                status = (status + " NEW").strip()
            elif have == best:
                agree += 1
            else:
                disagree += 1
                status = (status + f" BASE={have}").strip()
        rows.append(f"{code:04X}\t{best}\t{n}\t{status}")
    out = open(a.out, "w", encoding="utf-8") if a.out else sys.stdout
    out.write("# code\tchar\tvotes\tstatus\n" + "\n".join(rows) + "\n")
    if a.out:
        out.close()
    print(f"pairs {len(pairs)}, used {len(pairs)-len(skipped)}, skipped {len(skipped)}; codes {len(votes)}, "
          f"conflicts {conflicts}" + (f", agree {agree}, disagree {disagree}, new {new}" if base else ""),
          file=sys.stderr)
    for t, u, why in skipped[:10]:
        print(f"  skipped {t!r}: {why}", file=sys.stderr)


# ---- charmap-import ------------------------------------------------------------------

def cmd_charmap_import(a):
    rows = {}
    with open(a.src, encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            m = re.match(r"^\s*([0-9A-Fa-f]{4})(=|\t)(.*)$", line)
            if not m:
                continue
            code, val = int(m.group(1), 16), m.group(3)
            if m.group(2) == "\t":
                val = val.split("\t")[0]
            if val.startswith("{") or val.startswith("\\") or val == "":
                continue            # commands / control codes are handled by tags
            if a.min is not None and code < a.min or a.max is not None and code > a.max:
                continue
            rows.setdefault(code, val)   # first definition wins (pret lists commands later)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(f"# imported from {os.path.basename(a.src)}; code<TAB>text\n")
        for code in sorted(rows):
            f.write(f"{code:04X}\t{rows[code]}\n")
    print(f"wrote {len(rows)} entries to {a.out}")


# ---- patch-preview / check-base ------------------------------------------------------

KNOWN_DUMPS = {
    # No-Intro (via libretro-database DAT), all 134217728 bytes
    "258cea3a62ac0d6eb04b5a0fd764d788": "Pokemon - HeartGold Version (USA) IPKE, CRC32 C180A0E9",
    "e3f7933aee8cc2694629293f16c1c0a8": "Pocket Monsters - HeartGold (Japan) IPKJ, CRC32 FC7D8F28",
    "80c1024a03aa2c1e3d66ba168db97739": "Pokemon - HeartGold Version (Europe, EN), CRC32 B64A5EFB",
    "5582a09af4fc2a9873712497c9cd425b": "Pokemon - Goldene Edition HeartGold (Germany) IPKD, CRC32 0A994C0C",
    "1f937c6376a25ff36358ca5819c83f5a": "Pokemon - Version Or HeartGold (France) IPKF, CRC32 533A6E55",
    "7aae450618f86f8d9e6f43aca52ac919": "Pokemon - Versione Oro HeartGold (Italy) IPKI, CRC32 2646AE79",
    "b101936ad60a33e3c06b72c6ea15a99a": "Pokemon - Edicion Oro HeartGold (Spain) IPKS, CRC32 0E3670CD",
    "7d4c656de7baabc455aacdec85b18ad5": "Pocket Monsters - HeartGold (Korea) IPKK, CRC32 23850525",
}


def _xdelta(args, **kw):
    exe = shutil.which("xdelta3")
    if not exe:
        sys.exit("xdelta3 not found in PATH")
    return subprocess.run([exe] + args, **kw)


def cmd_patch_preview(a):
    """Decode the patch against an all-0x00 and an all-0xFF fake source (checksums off).
    Bytes that differ between the two came from the (missing) base ROM; everything else
    is exact. Writes the 0x00 variant + a per-file completeness report."""
    size = a.source_size
    with tempfile.TemporaryDirectory(dir=a.tmp) as td:
        z, f = Path(td) / "z.bin", Path(td) / "f.bin"
        for p, b in ((z, b"\x00"), (f, b"\xff")):
            with open(p, "wb") as fh:
                chunk = b * (1 << 20)
                for _ in range(size >> 20):
                    fh.write(chunk)
        tz, tf = Path(td) / "tz.nds", Path(td) / "tf.nds"
        for src, dst in ((z, tz), (f, tf)):
            r = _xdelta(["-d", "-n", "-f", "-s", str(src), str(a.patch), str(dst)], capture_output=True)
            if r.returncode:
                sys.exit(r.stderr.decode(errors="replace"))
        dz, df = bytearray(tz.read_bytes()), tf.read_bytes()
    # Header fields copied from the base are unknown (0). Fill the ones every HGSS build shares
    # so ndspy/other tools can parse the preview. (arm7 size stays unknown if it came from base.)
    fixes = []
    for off, val in ((0x20, 0x4000), (0x24, 0x02000800), (0x28, 0x02000000), (0x34, 0x02380000), (0x38, 0x02380000)):
        if struct.unpack_from("<I", dz, off)[0] == 0 and struct.unpack_from("<I", df, off)[0] == 0xFFFFFFFF:
            struct.pack_into("<I", dz, off, val)
            fixes.append(f"{off:#x}={val:#x}")
    if dz[0:12] == bytes(12) and df[0:12] == b"\xff" * 12:
        dz[0:12] = b"POKEMON HG\0\0"
        fixes.append("title")
    if dz[12:15] == bytes(3):
        dz[12:15] = b"IPK"
    Path(a.out).write_bytes(dz)
    if fixes:
        print("filled standard header fields: " + ", ".join(fixes))
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom(bytes(dz))
    fat_off, fat_sz = struct.unpack_from("<II", dz, 0x48)
    report = {"patch": str(a.patch), "target_size": len(dz),
              "source_bytes_total": df.count(255) - dz.count(255), "files": {}}
    incomplete = []
    for fid in range(fat_sz // 8):
        s, e = struct.unpack_from("<II", dz, fat_off + 8 * fid)
        if e <= s:
            continue
        nsrc = df.count(255, s, e) - dz.count(255, s, e)
        try:
            name = rom.filenames.filenameOf(fid) or f"#{fid}"
        except Exception:
            name = f"overlay/#{fid}"
        if nsrc:
            incomplete.append((name, e - s, nsrc))
            report["files"][name] = {"size": e - s, "bytes_from_base": nsrc}
    for label, off, sz in (("arm9", *struct.unpack_from("<I", dz, 0x20), *struct.unpack_from("<I", dz, 0x2C)),
                           ("arm7", *struct.unpack_from("<I", dz, 0x30), *struct.unpack_from("<I", dz, 0x3C))):
        nsrc = df.count(255, off, off + sz) - dz.count(255, off, off + sz)
        if nsrc:
            report["files"][label] = {"size": sz, "bytes_from_base": nsrc}
    hdr_src = [i for i in range(0x200) if dz[i] != df[i]]
    report["header_bytes_from_base"] = hdr_src
    if a.report:
        Path(a.report).write_text(json.dumps(report, indent=1))
    print(f"wrote {a.out} ({len(dz)} bytes); {report['source_bytes_total']} bytes "
          f"({100*report['source_bytes_total']/len(dz):.2f}%) depend on the base ROM")
    print(f"header bytes taken from base (unknown, left 0): {len(hdr_src)}; files touched by base data: {len(incomplete)}")
    for name, sz, n in sorted(incomplete, key=lambda x: -x[2])[:15]:
        print(f"  {name:40s} {n:9d}/{sz} bytes from base")
    if MSG_NARC_PATH not in report["files"]:
        print(f"  {MSG_NARC_PATH} (messages) is COMPLETE")
    if FONT_NARC_PATH not in report["files"]:
        print(f"  {FONT_NARC_PATH} (font) is COMPLETE")


def cmd_check_base(a):
    data = Path(a.rom).read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    print(f"size   {len(data)}")
    print(f"title  {data[:12]!r}  code {data[12:16]!r}  rev {data[0x1E]}")
    print(f"CRC32  {zlib.crc32(data) & 0xFFFFFFFF:08X}")
    print(f"MD5    {md5}")
    print(f"SHA1   {hashlib.sha1(data).hexdigest()}")
    print(f"match  {KNOWN_DUMPS.get(md5, 'no known No-Intro HeartGold dump (trimmed? encrypted secure area? hacked?)')}")
    for p in a.patch or []:
        r = _xdelta(["-d", "-c", "-s", str(a.rom), str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"patch  {p}: {'APPLIES CLEANLY (adler32 verified)' if r.returncode == 0 else 'FAILS: ' + r.stderr.decode(errors='replace').strip()[:200]}")


# ---- glyph ----------------------------------------------------------------------------

def render_glyph(font: bytes, code: int):
    """Gen IV font: u32 hdr_size, u32 width_table_off, u32 num_glyphs, u8 max_w, u8 max_h,
    u8 tiles_w, u8 tiles_h. Glyph for code c is index c-1; 2bpp, tiles in row-major order,
    each tile row = 2 bytes; empirically pixel x (0..7 in tile) = 7 - (bitpair index LSB-first)."""
    hs, wo, cnt, mw, mh, tw, th = struct.unpack_from("<IIIBBBB", font, 0)
    gsz = 16 * tw * th
    g = font[hs + (code - 1) * gsz: hs + code * gsz]
    W, H = 8 * tw, 8 * th
    pix = [[0] * W for _ in range(H)]
    for t in range(tw * th):
        tx, ty = t % tw, t // tw
        for y in range(8):
            for x in range(8):
                b = g[t * 16 + y * 2 + x // 4] if t * 16 + y * 2 + x // 4 < len(g) else 0
                pix[ty * 8 + y][tx * 8 + 7 - x] = (b >> ((x % 4) * 2)) & 3
    width = font[wo + code - 1] if wo + code - 1 < len(font) else None
    return pix, width


def cmd_glyph(a):
    rom = load_rom(a.rom)
    font = Narc.parse(get_file(rom, FONT_NARC_PATH)).files[a.font]
    codes = [int(c, 16) for c in a.codes]
    pics = [render_glyph(font, c) for c in codes]
    print("   ".join(f"{c:04X} w={w}".ljust(16) for c, (_, w) in zip(codes, pics)))
    for y in range(len(pics[0][0])):
        print("   ".join("".join(" #+."[v] for v in p[y]) for p, _ in pics))


# --------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("unpack"); s.add_argument("rom"); s.add_argument("outdir"); s.set_defaults(fn=cmd_unpack)
    s = sp.add_parser("extract"); s.add_argument("rom"); s.add_argument("out_dir")
    s.add_argument("--charmap", action="append", required=True); s.set_defaults(fn=cmd_extract)
    s = sp.add_parser("insert"); s.add_argument("rom"); s.add_argument("in_dir"); s.add_argument("out")
    s.add_argument("--charmap", action="append", required=True); s.set_defaults(fn=cmd_insert)
    s = sp.add_parser("roundtrip"); s.add_argument("rom"); s.add_argument("--charmap", action="append", required=True)
    s.add_argument("--rebuild-rom", action="store_true", help="also re-save the whole ROM with ndspy and re-read")
    s.set_defaults(fn=cmd_roundtrip)
    s = sp.add_parser("charmap-guess", help="infer code->char from known strings")
    s.add_argument("--pairs", help="TSV: known_text<TAB>code units (hex u16s space-separated, or LE hex bytes)")
    s.add_argument("--rom"); s.add_argument("--bank", type=int)
    s.add_argument("--known", help="text file, line i = known text of string i (+offset) of --bank")
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--charmap", action="append", help="existing charmap(s) to compare against")
    s.add_argument("--out"); s.set_defaults(fn=cmd_charmap_guess)
    s = sp.add_parser("charmap-import"); s.add_argument("src"); s.add_argument("out")
    s.add_argument("--min", type=lambda x: int(x, 16)); s.add_argument("--max", type=lambda x: int(x, 16))
    s.set_defaults(fn=cmd_charmap_import)
    s = sp.add_parser("patch-preview"); s.add_argument("patch"); s.add_argument("out")
    s.add_argument("--report"); s.add_argument("--source-size", type=int, default=128 << 20)
    s.add_argument("--tmp", default=None); s.set_defaults(fn=cmd_patch_preview)
    s = sp.add_parser("check-base"); s.add_argument("rom"); s.add_argument("--patch", action="append")
    s.set_defaults(fn=cmd_check_base)
    s = sp.add_parser("glyph"); s.add_argument("rom"); s.add_argument("codes", nargs="+")
    s.add_argument("--font", type=int, default=0); s.set_defaults(fn=cmd_glyph)
    for name in ("extract", "insert", "roundtrip", "charmap-guess"):
        sp.choices[name].add_argument("--narc", default=None,
                                      help=f"message NARC path inside the ROM (default {MSG_NARC_PATH}; also pbr/msg.narc)")
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
