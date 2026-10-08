#!/usr/bin/env python3
"""usref - check the USA-ROM claims of the fixes ([[us_ref]] in work/patches/<id>/fix.toml) against the USA ROM.

A fix's source or fix.toml that cites the USA ROM writes the address as `US arm9 0x020431D6` (RAM) or
`US overlay14+0x12BB4` (file offset; USA overlay numbers), and fix.toml states what is there in a [[us_ref]]:

    [[us_ref]]
    id = "namelen-us-player-script"
    claim = "US arm9 0x020431D6: script 'name player', the same call with mov r3, #7"
    file = "arm9"                   # USA ROM: "arm9", "overlayNN", or a NARC path ("a/1/5/2")
    address = "0x020431D6"          # RAM address; or offset = "0x12BB4" (offset in the file's RAM image)
    new = "namelen-player-script"   # what is there, one of:
                                    #   new    = a [[code]] region of this fix: the bytes the fix writes there
                                    #   expect = "B5F8 1C0D": the USA bytes themselves (a few cited halfwords)
                                    #   hack   = "arm9 0x02083814" / "overlay14+0x4BBC8", with length (bytes):
                                    #            the Chinese ROM's original bytes there
    # a NARC reference instead: members = [2, 3], lz10 = true (compare decompressed): the same members of the
    # Chinese ROM

Optional: calls = "0x020830D8" (the Thumb bl within 8 bytes after the compared bytes goes there: the same
call, not only the same immediate) and unique = true (the compared bytes occur once in the USA file).

`fixes.py check` (the fast registry step) refuses a citation without its [[us_ref]] and an address-looking
number after a mention of the USA ROM that is not written as a citation (fixes.us_citation_problems). This
module checks each claim against the bytes:

    python3 work/tools/usref.py [--us ROM] [--rom CN] [--armips PATH]     (check.py --full: the us-refs step)

It needs the USA ROM (work/rom/Pokemon - HeartGold Version (USA).nds) and, for `hack` and `new` claims, the
Chinese ROM and armips (a `new` claim assembles its fix alone). Only the cited bytes are in git (`expect`, a
few halfwords); `new` and `hack` claims compare the USA ROM with bytes that are already in the fix sources.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import fixes as fixreg  # noqa: E402

ROM_US = fixreg.WORK / "rom" / "Pokemon - HeartGold Version (USA).nds"


class UsRefError(Exception):
    pass


class CodeImages:
    """Read-only RAM images of an ndspy ROM's arm9 and overlays (decompressed: the USA ROM's code is), its NARC
    members and the load addresses: hardcoded.RomView.code / narc / base, with the images kept."""

    def __init__(self, rom):
        import hardcoded
        self.view = hardcoded.RomView(rom)
        self._img = {}

    def base(self, key) -> int:
        return self.view.base(key)

    def get(self, key) -> bytes:
        import hardcoded
        if key not in self._img:
            try:
                self._img[key] = self.view.code(key)
            except hardcoded.HardcodedError as ex:
                raise UsRefError(str(ex)) from None
        return self._img[key]

    def narc_members(self, path) -> list:
        return self.view.narc(path)


def _offset(images, key, e) -> int:
    if "address" in e:
        return fixreg._int(e["address"]) - images.base(key)
    return fixreg._int(e["offset"])


def _where(e) -> str:
    if "members" in e:
        return f"{e['file']} #{', #'.join(map(str, e['members']))}"
    return f"US {e['file']} {e['address']}" if "address" in e else f"US {e['file']}+{e['offset']}"


def check_ref(fx, e, us, cn=None, assembled=None) -> str:
    """Check one [[us_ref]]; returns a short 'ok' detail, raises UsRefError with what is wrong.
    us, cn: CodeImages of the USA and the Chinese ROM; assembled: asmlisting.Assembled of the fix (new)."""
    import asmpatch
    import ndspy.lz10
    if "members" in e:
        if cn is None:
            raise UsRefError("needs the Chinese ROM")
        a, b = us.narc_members(e["file"]), cn.narc_members(e["file"])
        bad = []
        for mb in e["members"]:
            if mb >= len(a) or mb >= len(b):
                bad.append(f"#{mb} missing")
                continue
            x, y = bytes(a[mb]), bytes(b[mb])
            if e.get("lz10"):
                try:
                    x, y = ndspy.lz10.decompress(x), ndspy.lz10.decompress(y)
                except (TypeError, ValueError) as ex:
                    bad.append(f"#{mb} is not LZ10 ({ex})")
                    continue
            if x != y:
                bad.append(f"#{mb} differs ({len(x)} vs {len(y)} bytes)")
        if bad:
            raise UsRefError(f"{e['file']}: " + "; ".join(bad))
        return f"{len(e['members'])} members equal to the Chinese ROM's" + (" (decompressed)" if e.get("lz10") else "")
    key = e["file"]
    data = us.get(key)
    off = _offset(us, key, e)
    if "expect" in e:
        want = b"".join(h.to_bytes(2, "little") for h in fixreg.halfwords(e["expect"]))
        what = "fix.toml expect"
    elif "hack" in e:
        if cn is None:
            raise UsRefError("needs the Chinese ROM")
        mo = fixreg.US_HACK_RE.fullmatch(e["hack"])
        hkey = mo.group(1)
        hoff = int(mo.group(2), 16) - cn.base(hkey) if mo.group(2) else int(mo.group(3), 16)
        want = cn.get(hkey)[hoff:hoff + e["length"]]
        what = f"the Chinese ROM at {e['hack']}"
        if len(want) != e["length"]:
            raise UsRefError(f"{e['hack']}: the Chinese {hkey} ends before {e['length']} bytes")
    else:
        if assembled is None:
            raise UsRefError("needs the fix assembled (armips and the Chinese ROM)")
        reg = next(r for r in asmpatch.regions(fx, assembled.bases) if r.id == e["new"])
        want = assembled.new[reg.file][reg.start:reg.end]
        what = f"the bytes {fx['id']} writes in {e['new']}"
    if off < 0 or off + len(want) > len(data):
        raise UsRefError(f"{_where(e)} is outside US {key} ({len(data):#x} bytes)")
    got = data[off:off + len(want)]
    if got != want:
        raise UsRefError(f"{_where(e)} holds {asmpatch.hw_str(got)}, not {asmpatch.hw_str(want)} ({what})")
    done = f"{len(want)} bytes = {what}"
    if e.get("unique"):
        n = data.count(want)
        if n != 1:
            raise UsRefError(f"{_where(e)}: its {len(want)} bytes occur {n} times in US {key}, so they do not "
                             f"identify this place (compare a longer span)")
        done += ", unique in the file"
    if "calls" in e:
        base = us.base(key)
        target = bl_target_after(data, off + len(want), base)
        if target is None:
            raise UsRefError(f"{_where(e)}: no Thumb bl within 8 bytes after the compared bytes")
        if target != fixreg._int(e["calls"]):
            raise UsRefError(f"{_where(e)}: the bl after it goes to 0x{target:08X}, not {e['calls']}")
        done += f", then bl {e['calls']}"
    return done


def bl_target_after(data: bytes, off: int, base: int, window=8):
    """The target of the first Thumb bl / blx pair that starts within `window` bytes at `off`, or None."""
    for i in range(off, min(off + window, len(data) - 3), 2):
        hi, lo = data[i] | data[i + 1] << 8, data[i + 2] | data[i + 3] << 8
        if hi >> 11 == 0x1E and lo >> 11 in (0x1F, 0x1D):
            disp = (hi & 0x7FF) << 12 | (lo & 0x7FF) << 1
            if disp & 0x400000:
                disp -= 0x800000
            target = base + i + 4 + disp
            return target & ~3 if lo >> 11 == 0x1D else target
    return None


def check_all(fixes, us_rom, cn_rom=None, assembled=None) -> tuple:
    """(rows, problems) for every [[us_ref]] of `fixes`; rows: (fix id, ref id, where, detail)."""
    us = CodeImages(us_rom)
    cn = CodeImages(cn_rom) if cn_rom is not None else None
    rows, probs = [], []
    for fx in fixes:
        for e in fx.get("us_ref", []):
            try:
                detail = check_ref(fx, e, us, cn, (assembled or {}).get(fx["id"]))
                rows.append((fx["id"], e["id"], _where(e), detail))
            except UsRefError as ex:
                probs.append(f"{fx['id']} [[us_ref]] {e['id']}: {ex}. Claim: {e['claim']!r}")
    return rows, probs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--us", default=str(ROM_US), help="USA HeartGold ROM")
    ap.add_argument("--rom", default=str(fixreg.ROM_CN), help="the Chinese ROM")
    ap.add_argument("--armips", help="armips executable (default: $ARMIPS, then PATH)")
    a = ap.parse_args(argv)
    import asmlisting
    import asmpatch
    import msgtool as m
    for what, path in (("the USA ROM", a.us), ("the Chinese ROM", a.rom)):
        if not Path(path).is_file():
            print(f"{what} {path} is missing; nothing was checked (CONTRIBUTING.md: Building the ROM)",
                  file=sys.stderr)
            return 2
    try:
        all_fixes = fixreg.load_all()
        cn = m.load_rom(a.rom)
        needs_asm = [f for f in all_fixes if any("new" in e for e in f.get("us_ref", []))]
        assembled = {}
        if needs_asm:
            armips = asmpatch.find_armips(a.armips)
            asmpatch.check_armips(armips)
            assembled = asmlisting.assemble_each(cn, needs_asm, armips)
        rows, probs = check_all(all_fixes, m.load_rom(a.us), cn, assembled)
    except (fixreg.FixError, asmpatch.AsmError) as ex:
        sys.exit(str(ex))
    for fid, rid, where, detail in rows:
        print(f"  ok  {fid:28s} {rid:34s} {where}: {detail}")
    for p in probs:
        print(f"  WRONG  {p}")
    print(f"{'wrong' if probs else 'ok'}: {len(rows)} USA claims verified" + (f", {len(probs)} wrong" if probs else ""))
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
