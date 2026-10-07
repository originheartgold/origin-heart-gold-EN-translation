#!/usr/bin/env python3
"""asmpatch - apply the code and data fixes by assembling their armips sources.

A fix of kind code or data (work/patches/<fix>/fix.toml) has an armips source, `asm = "<fix>.asm"`, that
writes the new bytes, and [[code]] entries that declare the regions it may change (file, offset, original
bytes `expect`). The build:

  1. reads the decompressed arm9 / overlay images it needs from the ROM through hardcoded.RomView (the same
     path the strings stage and the legacy Python engine use, so the ROM is written back identically) and
     checks every region's `expect` bytes;
  2. stages them as <stage>/rom/arm9.bin, <stage>/rom/overlayNN.bin next to a copy of work/patches/include
     (<stage>/include). armips resolves `.open` and `.include` paths against its working directory, which is
     <stage>/rom, so a source says `.open "arm9.bin", 0x02000000` and `.include "../include/guards.inc"`;
  3. runs armips once per fix, in build order (`armips -erroronwarning -temp <listing> <fix>.asm`). The
     source's own guards (guards.inc) check the original bytes again and stop armips, which then writes
     nothing; the listing shows every assembled line's address, and a byte written twice stops the build;
  4. after each run compares every staged file with its state before the run: a changed byte outside the
     fix's declared regions, a declared region left unchanged, a file that changed size, or a file that
     appeared or disappeared stops the build;
  5. writes the changed images back through RomView.

armips is not bundled. It is found as --armips PATH (build.py), else the ARMIPS environment variable, else
`armips` on PATH, and must report the pinned version (PINNED_VERSION). Build steps: work/notes/toolchain.md.

    python3 work/tools/asmpatch.py check [--rom ROM] [--only IDS] [--without IDS] [--armips PATH]
                                         # assemble the selected fixes against the Chinese ROM (nothing written)
    python3 work/tools/asmpatch.py listing <fix-id> [--rom ROM] [--armips PATH]
                                         # each region of one fix: old bytes -> new bytes
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import fixes as fixreg  # noqa: E402

PINNED_VERSION = "v0.11.0"
INCLUDE_DIR = fixreg.PATCHES_DIR / fixreg.INCLUDE_DIR
ENV_VAR = "ARMIPS"
TIMEOUT = 120


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
            p = shutil.which(cand) or (cand if Path(cand).is_file() else None)
            if not p:
                raise AsmError(f"armips from {how} not found or not executable: {cand}")
            return p
    p = shutil.which("armips")
    if not p:
        raise AsmError(f"armips {PINNED_VERSION} not found: put it on PATH, set {ENV_VAR}=/path/to/armips or pass "
                       f"--armips (build steps: work/notes/toolchain.md); build.py and hardcoded.py check can "
                       f"also run without it with --code-engine python")
    return p


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
# regions
# --------------------------------------------------------------------------------------

def regions(fx) -> list:
    """(file, start, end, entry id, expect bytes) of a fix's [[code]] entries."""
    out = []
    for e in fx.get("code", []):
        off = fixreg._int(e["offset"])
        hw = fixreg.halfwords(e["expect"])
        out.append((e["file"], off, off + 2 * len(hw), e["id"], b"".join(h.to_bytes(2, "little") for h in hw)))
    return out


def _hw_str(data: bytes) -> str:
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
_NO_WRITE = (".org", ".orga", ".skip", ".open", ".close", ".area", ".endarea", ".headersize")
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
    spans = {}
    for (f, a, low, src, n), nxt in zip(rows, rows[1:] + [(None, 0, None, "", 0)]):
        if low.startswith(_NO_WRITE) or nxt[0] != f or nxt[1] <= a:
            continue
        spans.setdefault(f, []).append((a, nxt[1], f"{Path(src).name}:{n}"))
    problems = []
    for f, ss in spans.items():
        ss.sort()
        for (a0, b0, w0), (a1, b1, w1) in zip(ss, ss[1:]):
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
# assemble
# --------------------------------------------------------------------------------------

def assemble(fixes, binaries: dict, armips: str, bases=None, include_dir=INCLUDE_DIR):
    """Assemble the code/data fixes among `fixes` (build order) over `binaries` {"arm9": bytes, "overlayNN":
    bytes}. Returns (new binaries, report rows); raises AsmError listing every problem.
    bases: {"overlayNN": load address} for the report's RAM column (optional)."""
    todo = fixreg.code_entries_fixes(fixes)
    bases = bases or {}
    problems = []
    for fx in todo:
        for key, start, end, eid, want in regions(fx):
            if key not in binaries:
                problems.append(f"fix {fx['id']}: region {eid}: {key} was not staged")
            elif binaries[key][start:end] != want:
                problems.append(f"fix {fx['id']}: region {eid}: {key}+{start:#x} is "
                                f"{_hw_str(binaries[key][start:end])}, expected {_hw_str(want)} (fix.toml expect)")
    if problems:
        raise AsmError("code/data fixes refused (the ROM does not hold the expected bytes):\n  " +
                       "\n  ".join(problems))
    cur = {k: bytes(v) for k, v in binaries.items()}
    rows = []
    with tempfile.TemporaryDirectory(prefix="asmpatch-") as td:
        stage = Path(td)
        shutil.copytree(include_dir, stage / "include")
        romdir = stage / "rom"
        romdir.mkdir()
        for k, v in cur.items():
            (romdir / _bin(k)).write_bytes(v)
        for fx in todo:
            src = _asm(fx)
            listing = stage / "listing.txt"
            try:
                r = subprocess.run([armips, "-erroronwarning", "-temp", str(listing), str(src)], cwd=romdir,
                                   capture_output=True, text=True, timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                raise AsmError(f"fix {fx['id']}: armips did not finish within {TIMEOUT} s") from None
            out = (r.stdout + r.stderr).strip()
            if r.returncode != 0:
                shown = src.relative_to(fixreg.REPO) if src.is_relative_to(fixreg.REPO) else src
                raise AsmError(f"fix {fx['id']}: armips failed on {shown} (exit {r.returncode}); nothing was "
                               f"written:\n" + "\n".join("  " + line for line in out.splitlines()))
            twice = double_writes(listing.read_text(encoding="utf-8-sig", errors="replace"))
            if twice:
                raise AsmError(f"fix {fx['id']}: the asm writes the same bytes more than once (the later write "
                               f"wins silently):\n  " + "\n  ".join(twice))
            names = {p.name for p in romdir.iterdir()}
            want_names = {_bin(k) for k in cur}
            if names != want_names:
                raise AsmError(f"fix {fx['id']}: armips created or removed files: "
                               f"{sorted(names ^ want_names)} (a fix only patches the staged binaries)")
            regs = regions(fx)
            touched = {r_[3]: False for r_ in regs}
            new = {}
            for k in cur:
                data = (romdir / _bin(k)).read_bytes()
                if len(data) != len(cur[k]):
                    problems.append(f"fix {fx['id']}: {_bin(k)} changed size {len(cur[k]):#x} -> {len(data):#x}")
                    continue
                if data == cur[k]:
                    continue
                mine = [r_ for r_ in regs if r_[0] == k]
                outside = []
                for o in _changed(cur[k], data):          # per byte: adjacent regions count as one
                    hit = [r_ for r_ in mine if r_[1] <= o < r_[2]]
                    for r_ in hit:
                        touched[r_[3]] = True
                    if not hit:
                        outside.append(o)
                for a, b in _ranges(outside):
                    ram = fixreg._ram(k, a, bases)
                    problems.append(f"fix {fx['id']}: {_bin(k)}+{a:#x}..{b:#x}"
                                    f"{f' (RAM 0x{ram:08X})' if ram is not None else ''} changed, outside "
                                    f"every region the fix declares in fix.toml")
                new[k] = data
            for eid, hit in touched.items():
                if not hit:
                    problems.append(f"fix {fx['id']}: region {eid} declared in fix.toml, but the asm left it unchanged")
            if problems:
                raise AsmError("code/data fixes refused:\n  " + "\n  ".join(problems))
            for key, start, end, eid, want in regs:
                data = new.get(key, cur[key])
                rows.append({"id": eid, "file": key, "offset": hex(start), "old": _hw_str(want),
                             "new": _hw_str(data[start:end]), "fix": fx["id"], "engine": "armips"})
            cur.update(new)
    return cur, rows


def staged_keys(fixes) -> list:
    """The files (arm9, overlayNN) the code/data fixes among `fixes` declare regions in."""
    keys = {r[0] for fx in fixreg.code_entries_fixes(fixes) for r in regions(fx)}
    return sorted(keys, key=lambda k: (k != "arm9", int(k[7:]) if k.startswith("overlay") else 0))


def apply(rom, fixes, armips: str, dry_run=False) -> dict:
    """Assemble the code/data fixes among `fixes` into an ndspy ROM. Returns {"code_patches": rows,
    "files": {key: sha1[:12]} of the changed files, "armips": {...}}; raises AsmError (nothing written)."""
    import hardcoded
    view = hardcoded.RomView(rom)
    keys = staged_keys(fixes)
    try:
        binaries = {k: view.get(k) for k in keys}
    except hardcoded.HardcodedError as ex:
        raise AsmError(str(ex)) from None
    bases = {k: view.base(k) for k in keys if k != "arm9"}
    new, rows = assemble(fixes, binaries, armips, bases)
    changed = {k: v for k, v in new.items() if v != binaries[k]}
    if not dry_run:
        for k, v in changed.items():
            view.set(k, v)
    return {"code_patches": rows, "files": {k: hashlib.sha1(v).hexdigest()[:12] for k, v in changed.items()},
            "armips": {"path": armips, "version": armips_version(armips)}}


# --------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--armips", help=f"armips executable (default: ${ENV_VAR}, then PATH)")
    ap.add_argument("--rom", default=str(fixreg.ROM_CN))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="assemble the selected code/data fixes against the ROM (dry run)")
    p.add_argument("--only")
    p.add_argument("--without")
    p = sub.add_parser("listing", help="old -> new bytes of one fix's regions")
    p.add_argument("id")
    a = ap.parse_args(argv)
    import msgtool as m
    try:
        armips = find_armips(a.armips)
        check_armips(armips)
        if a.cmd == "check":
            act = fixreg.active_fixes(a.only, a.without)
        else:
            act = [f for f in fixreg.load_all() if f["id"] == a.id]
            if not act:
                sys.exit(f"unknown fix {a.id!r}")
            if not fixreg.code_entries_fixes(act):
                sys.exit(f"fix {a.id!r} is not a code/data fix (no asm)")
        rom = m.load_rom(a.rom)
        fixreg.check_overlay_bases(rom)
        rep = apply(rom, act, armips, dry_run=True)
    except (AsmError, fixreg.FixError) as ex:
        sys.exit(str(ex))
    for r in rep["code_patches"]:
        print(f"  {r['fix']:18s} {r['id']:28s} {r['file']}+{r['offset']}: {r['old']} -> {r['new']}")
    print(f"ok: {len({r['fix'] for r in rep['code_patches']})} fixes, {len(rep['code_patches'])} regions "
          f"(armips {rep['armips']['version']})")


if __name__ == "__main__":
    main()
