#!/usr/bin/env python3
"""Read-only logical ROM boundary check against source-declared translation changes.

Reconstructs permitted fonts/graphics/hardcoded edits in memory, never saves a
ROM and never trusts a candidate build report. Message payloads are deliberately
left to the separate inventory/binary checks. This checks declared boundaries,
not whether the declared patches themselves preserve gameplay semantics.
"""
import argparse
import json
import hashlib
from pathlib import Path
import struct
import sys

import ndspy.fnt
import ndspy.rom

import asmpatch
import build
import fixes as fixreg
import gfx
import msgtool as m

MESSAGE_PATHS = frozenset(("a/0/2/7", "battle/string/battle_string.narc"))


def _expected_rom(source_path, us_path):
    rom = ndspy.rom.NintendoDSRom.fromFile(str(source_path))
    us = ndspy.rom.NintendoDSRom.fromFile(str(us_path))
    font, _ = build.restore_glyphs(m.get_file(rom, m.FONT_NARC_PATH),
                                 m.get_file(us, m.FONT_NARC_PATH))
    m.set_file(rom, m.FONT_NARC_PATH, font)
    gfx.apply_patches(lambda p: m.get_file(rom, p),
                      lambda p, data: m.set_file(rom, p, data),
                      lambda p: m.get_file(us, p),
                      code=gfx.CodeView(rom), us_code=gfx.CodeView(us))
    active = [f for f in fixreg.load_all() if f.get("enabled")]
    if asmpatch.asm_fixes(active):             # strings/code/data fixes: their armips sources
        asmpatch.apply(rom, active, _armips())
    return rom


class ToolchainError(Exception):
    """A tool is present but not the pinned one: the boundary cannot be derived as declared."""


def _armips():
    """The pinned armips. Missing: FileNotFoundError (a gap: the check is incomplete, like a missing ROM).
    Present but another version: ToolchainError (the check fails, like an unapproved US reference ROM)."""
    try:
        armips = asmpatch.find_armips()
    except asmpatch.AsmError as exc:
        raise FileNotFoundError(str(exc)) from None
    try:
        asmpatch.check_armips(armips)
    except asmpatch.AsmError as exc:
        raise ToolchainError(str(exc)) from None
    return armips


def _compare(expected, candidate, candidate_path):
    errors = []
    counts = {"files": len(expected.files), "files_compared": 0,
              "message_payloads_deferred": 0, "attributes_compared": 0}
    # Compare the entire named directory tree as well as every ID->path mapping.
    if ndspy.fnt.save(expected.filenames) != ndspy.fnt.save(candidate.filenames):
        errors.append("filesystem directory tree / file IDs differ")
    if len(expected.files) != len(candidate.files):
        errors.append("filesystem file count differs")
    for i, wanted in enumerate(expected.files):
        if i >= len(candidate.files):
            break
        path = expected.filenames.filenameOf(i)
        if path != candidate.filenames.filenameOf(i):
            errors.append(f"file ID {i}: path differs")
            continue
        if path in MESSAGE_PATHS:
            counts["message_payloads_deferred"] += 1
            baseline = m.Narc.parse(wanted)
            actual = m.Narc.parse(candidate.files[i])
            if len(baseline.files) != len(actual.files):
                errors.append(f"{path}: message archive member count differs")
            canonical = m.Narc(actual.files, baseline.btnf, baseline.pad_byte,
                               baseline.pad_last, baseline.bom_ver, baseline.size_quirks).build()
            if canonical != candidate.files[i]:
                errors.append(f"{path}: archive metadata, layout, or padding differs from source template")
            continue
        counts["files_compared"] += 1
        if wanted != candidate.files[i]:
            errors.append(f"file ID {i} ({path or 'unnamed overlay'}): differs from source-declared content")
    if counts["message_payloads_deferred"] != len(MESSAGE_PATHS):
        errors.append("expected two message archive paths were not found exactly once")
    # All remaining ndspy semantic attributes (including reserved/header bytes,
    # executable images, overlay tables, banner and signature) must agree.
    handled = {"files", "filenames", "pad200"}
    for key in sorted(set(vars(expected)) | set(vars(candidate))):
        if key in handled:
            continue
        counts["attributes_compared"] += 1
        if key not in vars(expected) or key not in vars(candidate) or getattr(expected, key) != getattr(candidate, key):
            errors.append(f"ROM attribute {key}: differs from source-declared content")
    a, b = bytes(expected.pad200), bytes(candidate.pad200)
    # ndspy writes a signature-offset word at absolute 0x1000 when serializing.
    # No other header padding is exempt; original hack's pointer may be junk.
    relative = 0x1000 - 0x200
    if len(a) < relative + 4 or len(b) < relative + 4:
        errors.append("ROM padding is too short to validate signature pointer")
    elif a[:relative] != b[:relative] or a[relative + 4:] != b[relative + 4:]:
        errors.append("ROM attribute pad200: bytes outside signature pointer differ")
    else:
        pointer = struct.unpack_from("<I", b, relative)[0]
        size = Path(candidate_path).stat().st_size
        signature = bytes(candidate.rsaSignature)
        if pointer < 0x4000 or pointer + len(signature) != size:
            errors.append("candidate signature pointer does not address the exact terminal signature")
        else:
            with Path(candidate_path).open("rb") as handle:
                handle.seek(pointer)
                if handle.read() != signature:
                    errors.append("candidate signature pointer content differs")
    return errors, counts


def check_boundary(source_path, candidate_path, us_path):
    """Return passed/failed/incomplete; missing prerequisites never become a pass."""
    result = {"status": "incomplete", "errors": [], "gaps": [], "counts": {},
              "scope": "logical ndspy components; unparsed physical gaps are not verified; message payload semantics require separate inventory/binary checks"}
    if sys.flags.optimize:
        result["errors"].append("optimized Python disables required source guards")
        result["status"] = "failed"
        return result
    for label, path in (("source", source_path), ("candidate", candidate_path), ("US reference", us_path)):
        if not Path(path).is_file():
            result["gaps"].append(f"missing {label} ROM: {path}")
    if result["gaps"]:
        return result
    donor_hash = hashlib.sha1()
    with Path(us_path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            donor_hash.update(chunk)
    if donor_hash.hexdigest() != build.US_SHA1:
        result["errors"].append("US reference SHA-1 differs from approved source")
        result["status"] = "failed"
        return result
    try:
        expected = _expected_rom(source_path, us_path)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        result["gaps"].append(f"missing boundary dependency: {type(exc).__name__}: {exc}")
        return result
    except ToolchainError as exc:
        result["errors"].append(f"wrong toolchain, cannot derive declared translation boundary: {exc}")
        result["status"] = "failed"
        return result
    except Exception as exc:
        result["errors"].append(f"cannot derive declared translation boundary: {type(exc).__name__}: {exc}")
        result["status"] = "failed"
        return result
    try:
        candidate = ndspy.rom.NintendoDSRom.fromFile(str(candidate_path))
        result["errors"], result["counts"] = _compare(expected, candidate, candidate_path)
    except Exception as exc:
        result["errors"].append(f"candidate boundary inspection failed: {type(exc).__name__}: {exc}")
    result["status"] = "failed" if result["errors"] else "passed"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=build.ROM_CN)
    parser.add_argument("--candidate", type=Path, default=build.OUT_ROM)
    parser.add_argument("--us", type=Path, default=build.ROM_US)
    args = parser.parse_args()
    result = check_boundary(args.source, args.candidate, args.us)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
