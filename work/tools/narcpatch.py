#!/usr/bin/env python3
"""narcpatch - the NARC byte stage of the English build: the [[narc_bytes]] entries of the kind-'narc' fixes.

A kind-'narc' fix changes a few bytes inside a game-data NARC member (e.g. one record of the evolution table
a/0/3/4). It needs no armips and commits no game data: each entry carries only the bytes it replaces and the
bytes it writes (fix.toml, read through fixes.py):

    [[narc_bytes]]
    id = "boldore-evolution"
    narc = "a/0/3/4"                       NARC path in the ROM's file system
    member = 525                           member index
    offset = "0x0"                         byte offset inside the member (hex)
    expect = "0005 0000 020E"              the original bytes, as little-endian halfwords ([[code]] notation)
    new = "0004 0023 020E"                 the bytes written there (as many halfwords as expect)
    member_sha1 = "4cd8fb7ba6dc..."        SHA-1 of the whole original member (40 hex digits)
    notes = "..."

apply() refuses unless every member it touches still has member_sha1 (so its size and every byte are the
hack's) and the bytes at offset are expect; it then writes new and keeps every other byte and the member's
size. The entries of one member must agree on member_sha1; their byte ranges must not overlap (fixes.py's
overlap check: key "<narc>#<member>", byte ranges; a [[graphics]] op on the same member overlaps all of it).
verify() re-reads every patched member of the written ROM (its SHA-1 after the stage).
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import fixes as fixreg  # noqa: E402
import msgtool as m  # noqa: E402


class NarcPatchError(Exception):
    pass


def entry_bytes(v) -> bytes:
    """expect/new of a [[narc_bytes]] entry as bytes (halfwords, little-endian)."""
    hw = fixreg.halfwords(v)
    return struct.pack(f"<{len(hw)}H", *hw)


def apply(get_file, set_file, fixes) -> list:
    """Apply the [[narc_bytes]] entries of `fixes` (a build's selection). get_file/set_file: NARC path -> bytes
    on the target ROM. Returns one report row per entry; raises NarcPatchError before writing anything when an
    entry does not match the ROM."""
    entries = fixreg.narc_bytes_entries(fixes)
    narcs, rows = {}, []
    originals = {}                                  # (narc, member) -> member_sha1 of the untouched member
    for e in entries:
        key = (e["narc"], e["member"])
        if e["narc"] not in narcs:
            narcs[e["narc"]] = m.Narc.parse(get_file(e["narc"]))
        files = narcs[e["narc"]].files
        label = f"fix {e['fix']} [[narc_bytes]] {e['id']} ({e['narc']} #{e['member']})"
        if not 0 <= e["member"] < len(files):
            raise NarcPatchError(f"{label}: the NARC has {len(files)} members")
        if key not in originals:
            got = hashlib.sha1(files[e["member"]]).hexdigest()
            if got != e["member_sha1"]:
                raise NarcPatchError(f"{label}: member SHA-1 is {got}, expected {e['member_sha1']} "
                                     f"(not the hack's member; recheck the fix)")
            originals[key] = got
        elif originals[key] != e["member_sha1"]:
            raise NarcPatchError(f"{label}: member_sha1 differs from another entry of the same member")
        data = bytearray(files[e["member"]])
        off, old, new = fixreg._int(e["offset"]), entry_bytes(e["expect"]), entry_bytes(e["new"])
        if off + len(old) > len(data):
            raise NarcPatchError(f"{label}: bytes {off:#x}+{len(old)} run past the member ({len(data)} bytes)")
        if bytes(data[off:off + len(old)]) != old:
            raise NarcPatchError(f"{label}: bytes at {off:#x} are {data[off:off + len(old)].hex(' ')}, "
                                 f"expected {old.hex(' ')}")
        data[off:off + len(new)] = new
        files[e["member"]] = bytes(data)
        rows.append({"fix": e["fix"], "id": e["id"], "narc": e["narc"], "member": e["member"], "offset": off,
                     "old": old.hex(), "new": new.hex()})
    for path, n in narcs.items():
        set_file(path, n.build())
    for r in rows:
        r["sha1"] = hashlib.sha1(narcs[r["narc"]].files[r["member"]]).hexdigest()
    return rows


def verify(get_file, report) -> str:
    """Every member the stage patched is in the written ROM as the stage left it (SHA-1), with the new bytes."""
    narcs = {}
    for r in report:
        if r["narc"] not in narcs:
            narcs[r["narc"]] = m.Narc.parse(get_file(r["narc"]))
        data = narcs[r["narc"]].files[r["member"]]
        new = bytes.fromhex(r["new"])
        got = hashlib.sha1(data).hexdigest()
        if got != r["sha1"] or data[r["offset"]:r["offset"] + len(new)] != new:
            raise AssertionError(f"narc_bytes {r['narc']} #{r['member']} ({r['id']}): {got} != {r['sha1']}")
    return f"ok ({len(report)} entries, {len({(r['narc'], r['member']) for r in report})} members)"
