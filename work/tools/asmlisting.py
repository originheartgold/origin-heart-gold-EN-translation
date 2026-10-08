#!/usr/bin/env python3
"""asmlisting - the committed disassembly snapshot of every armips fix (work/patches/<id>/<id>.listing).

A snapshot shows, for every `.area` of a fix's source, the address, the old bytes (the Chinese ROM) and the
new bytes (the source assembled alone over the Chinese ROM by armips), disassembled: Thumb or ARM as the
source assembles that area (`.thumb` / `.arm`), data areas (keyboard rows, window templates, strings, pointer
tables) as the values each statement writes, a native payload (`.incbin`) as size, SHA-256 and the labels
inside it. Code areas get up to 4 bytes of unchanged context on each side (6 where that is needed to show a
Thumb `bl` pair whole; cut where the fix changes other bytes), and code areas at most MERGE_GAP bytes apart
are shown as one section with the unchanged bytes between them; an `.org` block that only guards (the
overworld fix's read-only check of the whole routine) is shown as unchanged context; the words read by
absolute guards (`expect32_abs`) are listed. Old bytes are annotated only with the names of the hack's own
addresses (`.definelabel`), new bytes with every label (a code label before a `.definelabel` at the same
address). Nothing else of the ROM is in a snapshot: its old bytes are the
regions fix.toml already declares (`expect`), the bytes the guards already name, and a few context bytes.

Why: a review of a fix then reads the effect of an edit in the diff of one small text file, and a change to a
source, the include files, armips or the capstone disassembler that moves a byte shows up as a stale snapshot.
`check.py --full` regenerates every snapshot in memory and fails on any difference (the `listings` step).

    python3 work/tools/asmpatch.py listing [IDS...]            print the snapshots (default: every armips fix)
    python3 work/tools/asmpatch.py listing --write [IDS...]    write work/patches/<id>/<id>.listing
    python3 work/tools/asmpatch.py listing --check [IDS...]    exit 1 when a committed snapshot is stale

Needs armips (pinned, asmpatch.PINNED_VERSION), the Chinese ROM and capstone (pinned in
work/tools/requirements-dev.txt; another version may disassemble differently, so it is refused).
"""
from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REQUIREMENTS_DEV = TOOLS / "requirements-dev.txt"
SUFFIX = ".listing"
CONTEXT = 4                     # bytes of unchanged context before and after a code area
MERGE_GAP = 8                   # code areas at most this many bytes apart share one section
WRITE_CMD = "python3 work/tools/asmpatch.py listing --write"


class ListingError(Exception):
    pass


# --------------------------------------------------------------------------------------
# capstone
# --------------------------------------------------------------------------------------

def pinned_capstone() -> str:
    mo = re.search(r"^capstone==(\S+)", REQUIREMENTS_DEV.read_text(encoding="utf-8"), re.M)
    if not mo:
        raise ListingError("work/tools/requirements-dev.txt does not pin capstone (capstone==X.Y.Z)")
    return mo.group(1)


def capstone_version() -> str:
    """The installed capstone distribution's version; raises ListingError when it is missing or not the pin."""
    import importlib.metadata
    want = pinned_capstone()
    try:
        import capstone  # noqa: F401
        have = importlib.metadata.version("capstone")
    except (ImportError, importlib.metadata.PackageNotFoundError):
        raise ListingError(f"capstone is not installed (pip install -r work/tools/requirements-dev.txt, "
                           f"capstone {want})") from None
    if have != want:
        raise ListingError(f"capstone {have} is installed, but work/tools/requirements-dev.txt pins {want} (another "
                           f"version may disassemble differently): pip install -r work/tools/requirements-dev.txt")
    return have


_CS = {}


def _cs(mode):
    if mode not in _CS:
        import capstone
        _CS[mode] = capstone.Cs(capstone.CS_ARCH_ARM,
                                capstone.CS_MODE_THUMB if mode == "thumb" else capstone.CS_MODE_ARM)
    return _CS[mode]


def _hw(data, i):
    return data[i] | data[i + 1] << 8


def _bl_first(h):
    return h >> 11 == 0x1E                       # Thumb bl / blx: first halfword (offset high part)


def _bl_second(h):
    return h >> 11 in (0x1D, 0x1F)               # Thumb bl (0x1F) / blx (0x1D): second halfword


def _ram_word(v) -> bool:
    """A word that points into ITCM or main RAM: in ARM context, a literal pool entry rather than code."""
    return 0x01FF8000 <= v < 0x02400000


def disassemble(data: bytes, addr: int, mode: str, labels=None, literals=False) -> list:
    """(address, bytes text, instruction text) rows; bytes text: Thumb halfwords ("2305", "F026 FA78"), ARM
    words ("E92D47F0"). Bytes capstone does not decode are shown as .hword / .word. labels: {address: name}
    to name branch targets. literals (context only): an ARM word that points into RAM is shown as .word, as
    it is most likely a literal pool entry (capstone would decode it as a conditional data-processing op)."""
    rows, i = [], 0
    step = 2 if mode == "thumb" else 4
    md = _cs(mode)
    while i < len(data):
        if literals and mode == "arm" and len(data) - i >= 4 and _ram_word(struct.unpack_from("<I", data, i)[0]):
            v = struct.unpack_from("<I", data, i)[0]
            rows.append((addr + i, _hex(data[i:i + 4], mode), f".word 0x{v:08X}"))
            i += 4
            continue
        insn = next(md.disasm(data[i:], addr + i, count=1), None)
        if insn is None:
            n = min(step, len(data) - i)
            chunk = data[i:i + n]
            if n == 2:
                text = f".hword 0x{_hw(chunk, 0):04X}"
            elif n == 4:
                text = f".word 0x{struct.unpack('<I', chunk)[0]:08X}"
            else:
                text = ".byte " + ", ".join(f"0x{b:02X}" for b in chunk)
            rows.append((addr + i, _hex(chunk, mode), text))
            i += n
            continue
        text = f"{insn.mnemonic} {insn.op_str}".strip()
        mo = re.fullmatch(r"#0x([0-9a-f]+)", insn.op_str)
        if insn.mnemonic.startswith(("b", "cb")) and mo and labels:
            name = labels.get(int(mo.group(1), 16))
            if name:
                text += f"  ; {name}"
        rows.append((insn.address, _hex(bytes(insn.bytes), mode), text))
        i += insn.size
    return rows


def _hex(chunk: bytes, mode: str) -> str:
    if mode == "thumb" and len(chunk) % 2 == 0:
        return " ".join(f"{_hw(chunk, j):04X}" for j in range(0, len(chunk), 2))
    if mode == "arm" and len(chunk) % 4 == 0:
        return " ".join(f"{struct.unpack_from('<I', chunk, j)[0]:08X}" for j in range(0, len(chunk), 4))
    return " ".join(f"{b:02X}" for b in chunk)


# --------------------------------------------------------------------------------------
# assembling each fix alone
# --------------------------------------------------------------------------------------

@dataclass
class Assembled:
    """One fix assembled alone over the Chinese ROM: the staged images before and after, their load
    addresses, the armips listing text and the fix's source layout (fixes.lint_asm found=)."""
    fx: dict
    old: dict
    new: dict
    bases: dict
    listing: str
    layout: dict = field(default_factory=dict)

    def base(self, key):
        import asmpatch
        return asmpatch.base_of(key, self.bases)


def assemble_each(rom, fixes, armips) -> dict:
    """{fix id: Assembled} for every armips fix among `fixes`, each assembled alone (the snapshots and the
    US cross-checks show one fix's edit, whatever other fixes do; the fixes never overlap)."""
    import asmpatch
    import fixes as fixreg
    out = {}
    bases_all = fixreg.load_overlays()
    for fx in asmpatch.asm_fixes(fixes):
        _view, binaries, bases, layout = asmpatch.stage_inputs(rom, [fx])
        listings = {}
        new, _rows, _srows = asmpatch.assemble([fx], binaries, armips, bases, layout=layout, listings=listings)
        found = {}
        src = asmpatch._asm(fx)
        fixreg.lint_asm(src.read_text(encoding="utf-8"), fx, bases_all, name=src.name, found=found)
        out[fx["id"]] = Assembled(fx, dict(binaries), new, bases, listings.get(fx["id"], ""), found)
    return out


# --------------------------------------------------------------------------------------
# the armips listing: labels and the write statements
# --------------------------------------------------------------------------------------

_ROW_RE = re.compile(r"^([0-9A-F]{8}) (.*?)\s*; (.*) line (\d+)$")


def listing_rows(text: str) -> list:
    """(address, statement, source path, line) of every listed line."""
    out = []
    for line in text.splitlines():
        mo = _ROW_RE.match(line)
        if mo:
            out.append((int(mo.group(1), 16), mo.group(2).strip(), mo.group(3), int(mo.group(4))))
    return out


def labels_of(asm: Assembled) -> tuple:
    """(new, old, every): {address: name} of the fix source's labels, for the new bytes (every label; a code label
    wins over a .definelabel at the same address) and for the old bytes (only .definelabel names of the hack's
    own addresses, none inside data the fix appends). armips lists labels in lower case at their value; the
    source's spelling is restored. every: {address: [names]}, all of them."""
    import fixes as fixreg
    src = fixreg.asm_path(asm.fx)
    spelled, defined = {}, set()
    for name in re.findall(r"(?:^|\s)\.definelabel\s+(\w+)|^\s*(\w+):", src.read_text(encoding="utf-8"), re.M):
        n = name[0] or name[1]
        spelled[n.lower()] = n
        if name[0]:
            defined.add(n.lower())
    appended = [(a["start"], a["start"] + (a["size"] or 0)) for a in asm.layout.get("areas", []) if a["appended"]]
    new, old, every = {}, {}, {}
    for addr, stmt, _src, _n in listing_rows(asm.listing):
        if addr == 0xFFFFFFFF or not re.fullmatch(r"[\w@.]+:", stmt):
            continue
        low = stmt[:-1]
        name = spelled.get(low, low)
        every.setdefault(addr, []).append(name)
        if low in defined:
            new.setdefault(addr, name)
            if not any(a <= addr < b for a, b in appended):
                old.setdefault(addr, name)
        else:
            new[addr] = name if addr not in new or new[addr].lower() in defined else new[addr]
    return new, old, every


def write_rows(asm: Assembled, key: str) -> list:
    """(address, directive or "insn", source path, line) of every write statement armips listed in `key`."""
    import fixes as fixreg
    rows, cur = [], None
    for addr, stmt, src, n in listing_rows(asm.listing):
        low = stmt.lower()
        if low.startswith(".open"):
            mo = re.search(r'"([^"]+)"', stmt)
            cur = mo.group(1)[:-4] if mo else None
            continue
        if low.startswith(".close"):
            cur = None
            continue
        if cur != key or re.fullmatch(r"[\w@.]+:", stmt) or re.search(r"\bequ\b", low):
            continue
        mo = re.match(r"\.(\w+)", stmt)
        if mo:
            if mo.group(1).lower() in fixreg.ASM_WRITE_DIRECTIVES:
                rows.append((addr, mo.group(1).lower(), src, n))
            continue
        rows.append((addr, "insn", src, n))
    return rows


# --------------------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------------------

_SRC_LINES = {}


def _source_line(path: str, n: int) -> str:
    if path not in _SRC_LINES:
        try:
            _SRC_LINES[path] = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            _SRC_LINES[path] = []
    lines = _SRC_LINES[path]
    return lines[n - 1] if 0 < n <= len(lines) else ""


def _decode_units(units) -> str | None:
    import asmpatch
    cm = asmpatch.charmap()
    out = []
    for u in units:
        if u == 0xFFFF:
            out.append("|")
        elif u in cm.dec and len(cm.dec[u]) == 1:
            out.append(cm.dec[u])
        else:
            return None
    return '"' + "".join(out) + '"'


def _data_text(chunk: bytes, kind: str, labels: dict) -> str:
    """The values of one data statement: u16 (with the characters for a string or a key row), u32 (with the
    label a pointer names), or bytes."""
    if kind in ("u16", "chars") and len(chunk) % 2 == 0:
        units = [_hw(chunk, j) for j in range(0, len(chunk), 2)]
        text = " ".join(f"{u:04X}" for u in units)
        if kind == "chars":
            dec = _decode_units(units)
            if dec:
                text += f"  {dec}"
        return text
    if kind == "u32" and len(chunk) % 4 == 0:
        parts = []
        for j in range(0, len(chunk), 4):
            v = struct.unpack_from("<I", chunk, j)[0]
            name = labels.get(v) or (f"{labels[v - 1]}+1" if v - 1 in labels else None)
            parts.append(f"{v:08X}" + (f" ({name})" if name else ""))
        return " ".join(parts)
    return " ".join(f"{b:02X}" for b in chunk)


def _kind_of(directive: str, src: str, n: int, string_slot=False) -> str:
    line = _source_line(src, n)
    if string_slot or re.search(r"\.(string|stringn|str)\b", line, re.I):
        return "chars"
    if directive in ("halfword", "hword", "dh", "dcw"):
        return "chars" if re.search(r"\b(CH|FW)_\w+", line) else "u16"
    if directive in ("word", "dw", "dcd"):
        return "u32"
    return "u8"


def _in_string_slot(fx, key, off) -> bool:
    """`off` lies in a [[string]] slot (its old bytes are a string)."""
    for e in fx.get("string", []):
        start = int(e["offset"], 16)
        if e["file"] == key and start <= off < start + 2 * (e["max_units"] + 1):
            return True
    return False


def _region_of(fx, key, off, bases) -> str:
    import asmpatch
    for r in asmpatch.regions(fx, bases):
        if r.file == key and r.start <= off < r.end:
            return r.id
    return f"[[grow]] {key}" if key in asmpatch.grows(fx) else "?"


def _changed_offsets(old: bytes, new: bytes) -> set:
    n = min(len(old), len(new))
    out = {i for i in range(n) if old[i] != new[i]}
    return out | set(range(n, max(len(old), len(new))))


def _context(asm: Assembled, key: str, start: int, end: int, mode: str, changed: set) -> tuple:
    """[s, start) and [end, e) of unchanged context around a code area (file offsets)."""
    old = asm.old[key]
    s = max(0, start - CONTEXT)
    while any(o in changed for o in range(s, start)):
        s += 2 if mode == "thumb" else 4
    e = min(len(old), end + CONTEXT)
    while any(o in changed for o in range(end, e)):
        e -= 2 if mode == "thumb" else 4
    e = max(e, end)
    s = min(s, start)
    if mode == "thumb":
        if s < start and s >= 2 and _bl_second(_hw(old, s)) and _bl_first(_hw(old, s - 2)) and s - 2 not in changed:
            s -= 2
        if e > end and _bl_first(_hw(old, e - 2)):
            if e + 2 <= len(old) and e not in changed and e + 1 not in changed:
                e += 2
            else:
                e -= 2
    return s, e


def _lines(prefix, rows) -> list:
    return [f"{prefix}{a:08X}  {b:<{max(9, len(b))}s}  {t}".rstrip() for a, b, t in rows]


def _span(asm: Assembled, area: dict) -> tuple:
    """(file offset start, end) of an area; appended data ends where the grown file ends."""
    base = asm.base(area["file"])
    start = area["start"] - base
    end = min(len(asm.new[area["file"]]), start + area["size"]) if area["appended"] else start + area["size"]
    return start, end


def render_code(asm: Assembled, group: list, labels: tuple, changed: dict) -> list:
    """One section for code areas of one file and mode, at most MERGE_GAP bytes apart: context, each area's
    old and new instructions, the unchanged bytes between them."""
    new_labels, old_labels, _every = labels
    key, mode = group[0]["file"], group[0]["mode"]
    base = asm.base(key)
    old, new = asm.old[key], asm.new[key]
    spans = [_span(asm, a) for a in group]
    start, end = spans[0][0], spans[-1][1]
    regions = list(dict.fromkeys(_region_of(asm.fx, key, s0, asm.bases) for s0, _ in spans))
    appended = group[0]["appended"]
    if appended:
        what = f"appended {end - start} bytes ({key} 0x{len(old):X} -> 0x{len(new):X} bytes)"
    elif len(group) > 1:
        what = f"{len(group)} edits in {end - start} bytes"
    else:
        what = f"{end - start} byte{'' if end - start == 1 else 's'}"
    out = [f"== {key}+0x{start:X} (RAM 0x{base + start:08X}), {what}, {mode}: {', '.join(regions)}"]
    s, _ = (start, end) if appended else _context(asm, key, *spans[0], mode, changed[key])
    _, e = (start, end) if appended else _context(asm, key, *spans[-1], mode, changed[key])
    out += _lines("  ", disassemble(old[s:start], base + s, mode, old_labels, literals=True))
    for i, (a, b) in enumerate(spans):
        if i:
            gap = spans[i - 1][1]
            out += _lines("  ", disassemble(old[gap:a], base + gap, mode, old_labels, literals=True))
        if not appended and old[a:b] == new[a:b]:        # rewritten with the same instruction
            out += _lines("  ", disassemble(old[a:b], base + a, mode, old_labels))
            continue
        if not appended:
            out += _lines("- ", disassemble(old[a:b], base + a, mode, old_labels))
        out += _lines("+ ", disassemble(new[a:b], base + a, mode, new_labels))
    out += _lines("  ", disassemble(old[end:e], base + end, mode, old_labels, literals=True))
    return out


def render_area(asm: Assembled, area: dict, labels: tuple, changed: dict, writes: dict) -> list:
    """One section for a data area (or a code area alone: render_code)."""
    if "insn" in area["writes"]:
        return render_code(asm, [area], labels, changed)
    new_labels, old_labels, every = labels
    key, base = area["file"], asm.base(area["file"])
    old, new = asm.old[key], asm.new[key]
    start, end = _span(asm, area)
    appended = area["appended"]
    region = _region_of(asm.fx, key, start, asm.bases)
    if appended:
        what = f"appended {end - start} bytes ({key} 0x{len(old):X} -> 0x{len(new):X} bytes)"
    else:
        what = f"{end - start} byte{'' if end - start == 1 else 's'}"
    out = [f"== {key}+0x{start:X} (RAM 0x{area['start']:08X}), {what}, data: {region}"]
    slot = _in_string_slot(asm.fx, key, start)
    rows = [w for w in writes.get(key, []) if area["start"] <= w[0] < base + end]
    for i, (addr, d, src, n) in enumerate(rows):
        a = addr - base
        b = rows[i + 1][0] - base if i + 1 < len(rows) else end
        if b <= a:
            continue
        if d == "incbin":
            blob = new[a:b]
            inside = sorted((k, ", ".join(v)) for k, v in every.items() if addr <= k < base + b)
            mo = re.search(r'"([^"]+)"', _source_line(src, n))
            out.append(f"+ {addr:08X}  .incbin {Path(mo.group(1)).name if mo else '?'}: {len(blob)} bytes, "
                       f"sha256 {hashlib.sha256(blob).hexdigest()}; its labels:")
            out += [f"+   {k:08X}  {v}" for k, v in inside]
            continue
        if d in ("align", "fill", "skip") and len(set(new[a:b])) == 1 and (appended or a >= len(old)):
            out.append(f"+ {addr:08X}  {b - a} bytes of 0x{new[a]:02X} (.{d})")
            continue
        kind = _kind_of(d, src, n, slot and (b - a) % 2 == 0)
        if a < len(old) and not appended:
            if old[a:b] == new[a:b]:                     # rewritten with the same values
                out.append(f"  {addr:08X}  {_data_text(old[a:b], kind, old_labels)}")
                continue
            out.append(f"- {addr:08X}  {_data_text(old[a:b], kind, old_labels)}")
        out.append(f"+ {addr:08X}  {_data_text(new[a:b], kind, new_labels)}")
    return out


def _groups(asm: Assembled, areas: list) -> list:
    """Areas in address order, code areas of one file and mode at most MERGE_GAP bytes apart grouped."""
    out = []
    for a in areas:
        prev = out[-1][-1] if out else None
        if prev is not None and "insn" in a["writes"] and "insn" in prev["writes"] and not a["appended"] \
                and not prev["appended"] and a["file"] == prev["file"] and a["mode"] == prev["mode"] \
                and 0 <= a["start"] - (prev["start"] + prev["size"]) <= MERGE_GAP:
            out[-1].append(a)
        else:
            out.append([a])
    return out


def render(asm: Assembled, cs_version: str, armips_version: str) -> str:
    """The snapshot text of one fix."""
    fid = asm.fx["id"]
    labels = labels_of(asm)
    old_labels = labels[1]
    changed = {k: _changed_offsets(asm.old[k], asm.new[k]) for k in asm.old}
    writes = {k: write_rows(asm, k) for k in asm.old}
    src = Path(asm.fx["_path"]).parent / asm.fx["asm"]
    out = [f"; {fid} - disassembly snapshot of {src.name}: every edit, old -> new. Generated; do not edit.",
           f"; Regenerate: {WRITE_CMD} {fid}   (check.py --full fails when it is stale)",
           f"; Old: the Chinese ROM. New: {src.name} assembled alone over it by armips {armips_version}.",
           f"; Disassembly: capstone {cs_version} (UAL syntax). '  ' unchanged context, '- ' old, '+ ' new;",
           "; addresses are RAM addresses, Thumb bytes are halfwords, ARM bytes words; data rows are what one",
           "; statement writes (u16 rows of a string or key row with their characters, '|' = 0xFFFF end).",
           ""]
    areas = sorted(asm.layout.get("areas", []), key=lambda a: (a["file"], a["start"]))
    blocks = [("area", g[0]["file"], g[0]["start"], g) for g in _groups(asm, areas)]
    blocks += [("readonly", r["file"], r["start"], r) for r in asm.layout.get("readonly", [])]
    for kind, _key, _start, item in sorted(blocks, key=lambda b: (b[1], b[2], b[0] != "readonly")):
        if kind == "area":
            out += (render_code(asm, item, labels, changed) if len(item) > 1
                    else render_area(asm, item[0], labels, changed, writes))
        else:
            key, base = item["file"], asm.base(item["file"])
            lo = min(a for a, _ in item["reads"]) - base
            hi = max(a + n for a, n in item["reads"]) - base
            out.append(f"== {key}+0x{lo:X} (RAM 0x{base + lo:08X}), {hi - lo} bytes, {item['mode']}: read-only guard "
                       f"(the source checks these bytes and writes none of them)")
            out += _lines("  ", disassemble(asm.old[key][lo:hi], base + lo, item["mode"], old_labels))
        out.append("")
    absreads = sorted(set(asm.layout.get("abs", [])))
    if absreads:
        out.append("== read-only checks at absolute addresses (expect32_abs): the bytes there, unchanged")
        for key, _b, addr, n in absreads:
            base = asm.base(key)
            chunk = asm.old[key][addr - base:addr - base + n]
            out.append(f"  {addr:08X}  {_data_text(chunk, 'u32' if n == 4 else 'u8', old_labels)}")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def listing_path(fx) -> Path:
    return Path(fx["_path"]).parent / f"{fx['id']}{SUFFIX}"


def snapshots(assembled: dict, armips_version: str) -> dict:
    """{fix id: snapshot text}."""
    cs = capstone_version()
    return {fid: render(a, cs, armips_version) for fid, a in assembled.items()}


def stale(fixes, texts: dict) -> list:
    """Problems: an armips fix without its committed snapshot, or with one that differs from `texts`, and a
    snapshot file of a fix that has no armips source."""
    import asmpatch
    import fixes as fixreg
    probs = []
    asm_ids = {f["id"] for f in asmpatch.asm_fixes(fixes)}
    for fx in fixes:
        p = listing_path(fx)
        rel = p.relative_to(fixreg.REPO) if p.is_relative_to(fixreg.REPO) else p
        if fx["id"] not in asm_ids:
            if p.exists():
                probs.append(f"{rel}: {fx['id']} has no armips source, so it has no snapshot; remove the file")
            continue
        if fx["id"] not in texts:
            continue
        if not p.is_file():
            probs.append(f"{rel} is missing: {WRITE_CMD} {fx['id']}")
            continue
        have = p.read_text(encoding="utf-8").splitlines()
        want = texts[fx["id"]].splitlines()
        if have != want:
            n = next((i for i, (a, b) in enumerate(zip(have, want, strict=False)) if a != b), min(len(have), len(want)))
            got = have[n] if n < len(have) else "<end of file>"
            exp = want[n] if n < len(want) else "<end of file>"
            probs.append(f"{rel} is stale (line {n + 1}: committed {got!r}, now {exp!r}); after reviewing the "
                         f"change: {WRITE_CMD} {fx['id']}")
    return probs
