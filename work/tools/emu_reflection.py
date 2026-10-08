"""Reproduce the following-Pokemon water-reflection NULL pointer (Bulbasaur, sprite 428) in disposable RAM.

The fix is work/patches/bulbasaur-reflection-boundary (overlay 1, one byte at 0x021F629A, D-2270).
The hack's overlay-1 routine ReflectionGfx_Get (0x021F61E8) picks the graphics object the water
reflection of a map object draws with: for sprite ids 428..1894 (the following Pokemon) the follower's own
pointer at object+0x108, otherwise the generic field at object+0x10C. Its lower bound is 'ble' after
'cmp r0, #428', so 428 itself (Bulbasaur, the first follower sprite) falls to +0x10C, which is NULL for a
follower. The two reflection callbacks pass that NULL on to the graphics getters 0x0202451C / 0x02024558:
they call the assertion handler (which returns in this build) and then read address 0xB6 / 0xB8.
DeSmuME reads it and goes on; melonDS 1.1 and hardware do not (address 0 is not readable there).

Each case: restore one baseline state (Continue from the supplied save), make the chosen species the
only party Pokemon in RAM, enter the scene with the game's own Warp command (a normal map entry: the
follower and its graphics are built natively) and walk four steps along the dry shore of a pond (SCENES:
the Viridian City pond; the Route 22 pond next to Misty). Read-only execution hooks follow resolver entry
-> pointer load -> return -> getter -> assertion for the follower's sprite. Nothing is written to the
ROM image, its code or the follower object; the input ROM and save files are never written.
--expect original: Bulbasaur must take the NULL path (every reflection call: a NULL return, two NULL getter
arguments, two assertions) and Charmander / Onix must not; --expect fixed: no case may.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

OV1_BASE = 0x021E4980
RESOLVER = 0x021F61E8               # ReflectionGfx_Get(map object r0) -> graphics object
BRANCH = 0x021F629A                 # ble/blt after cmp r0, #428
FOLLOWER_LOAD = 0x021F62A8          # ldr r0, [object + 0x108]
GENERIC_LOAD = 0x021F62C6           # ldr r0, [object + 0x108 + 4]
REFLECTION_RETURNS = (0x021FCC8C, 0x021FD19E)   # the two reflection callbacks, after their bl
GETTER_HALF, GETTER_WORD = 0x0202451C, 0x02024558
ASSERT = 0x02025B2C
# return address (Thumb bit set) of the getter's 'bl ASSERT' for a NULL argument
GETTER_ASSERT_LR = {GETTER_HALF: 0x02024527, GETTER_WORD: 0x02024563}
# where each getter returns to in a reflection callback: callback return site + this
GETTER_CALLER_DELTA = {GETTER_HALF: 6, GETTER_WORD: 0x14}
FOLLOWER_FIELD = 0x108
# The resolver from push to the literal pool as the Chinese ROM has it (test_emu_reflection checks it
# against the ROM and the fix's [[code]] region).
RESOLVER_ORIGINAL = bytes.fromhex(
    "10b5041c68f6f4f8f82836dc49da62280cdc612803db44d0622842d046e00028"
    "01dc3ed042e015283bd03fe0b02801dc37d03be0011cb139182937d849187944"
    "c988090409148f44580058005800580058006200620062006200620062005800"
    "58006200620062006200620062005800580058005800580058001a4a904208dc"
    "0fdaf92801dc0cd010e0511e884208d00ce0511c884201dc03d007e0911c8842"
    "04d1201c68f67cf9406810bd6b218900884207dd0c49884204dc201c68f670f9"
    "006810bd0949884206dbc91d884203dc201c6cf6bfff10bd201c68f661f94068"
    "10bdc046030100006607000006010000")
BRANCH_ORIGINAL = bytes.fromhex("07dd")     # ble 0x021F62AC: 428 takes the generic field
BRANCH_FIXED = bytes.fromhex("07db")        # blt 0x021F62AC: 428 takes the follower field
SAMPLE_LIMIT = 12
# Where the follower walks next to reflecting water: map, start (x, y, facing), then the steps and where each
# must end. viridian: the dry strip north of the Viridian City pond. route22: the north shore of the Route 22
# pond, west of Misty and her Pokemon (a bug report places a freeze on Route 22 'next to Misty'; that spot is
# only inferred, the report's screenshot is not available).
SCENES = {
    "viridian": {"map": 50, "start": (1017, 260, "DOWN"),
                 "steps": (("DOWN", (1017, 261)), ("RIGHT", (1018, 261)), ("RIGHT", (1019, 261)),
                           ("LEFT", (1018, 261)))},
    "route22": {"map": 27, "start": (962, 270, "RIGHT"),
                "steps": (("RIGHT", (963, 270)), ("RIGHT", (964, 270)), ("RIGHT", (965, 270)),
                          ("LEFT", (964, 270)))},
}
CASES = {
    "bulbasaur": {"species": 1, "sprite": 428},
    "charmander": {"species": 4, "sprite": 432},
    "onix": {"species": 95, "sprite": 524},
}


def parse_scenes(value):
    names = list(SCENES) if value == "all" else value.split(",")
    if not names or any(n not in SCENES for n in names) or len(set(names)) != len(names):
        raise argparse.ArgumentTypeError("choose all or unique comma-separated scenes: " + ",".join(SCENES))
    return names


def parse_cases(value):
    names = list(CASES) if value == "all" else value.split(",")
    if not names or any(n not in CASES for n in names) or len(set(names)) != len(names):
        raise argparse.ArgumentTypeError("choose all or unique comma-separated cases: " + ",".join(CASES))
    return names


def add_arguments(parser):
    parser.add_argument("--rom", required=True, help="local original or fixed Origin v4.0.3 ROM")
    parser.add_argument("--sav", required=True, help="local raw battery save with a healthy, non-Egg lead "
                        "(work/build/memcheck/market.sav); imported without changing the file")
    parser.add_argument("--out", required=True, help="new evidence directory (must not already contain report.json)")
    parser.add_argument("--case", default="all", help="all or comma-separated " + ",".join(CASES))
    parser.add_argument("--scene", default="all", help="all or comma-separated " + ",".join(SCENES))
    parser.add_argument("--expect", required=True, choices=("original", "fixed"),
                        help="original: Bulbasaur must show the NULL path; fixed: no case may")


def file_identity(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest.hexdigest()}


def resolver_bytes(expect):
    """The resolver, push through literal pool, as the original or the fixed ROM has it."""
    data = bytearray(RESOLVER_ORIGINAL)
    if expect == "fixed":
        data[BRANCH - RESOLVER:BRANCH - RESOLVER + 2] = BRANCH_FIXED
    return bytes(data)


def validate_rom(path, expect):
    """Reject unfamiliar code before emulation: overlay 1's load address and the whole resolver."""
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(str(path))
    ov = rom.loadArm9Overlays([1])[1]
    if ov.ramAddress != OV1_BASE:
        raise ValueError(f"overlay 1 loads at {ov.ramAddress:#x}, not {OV1_BASE:#x}")
    got = bytes(ov.data[RESOLVER - OV1_BASE:RESOLVER - OV1_BASE + len(RESOLVER_ORIGINAL)])
    if got != resolver_bytes(expect):
        raise ValueError("overlay 1 reflection resolver differs from the expected " + expect + " routine")


class Trace:
    """Follows one reflection call chain at a time; bounded samples, exact counters.
    Hook callbacks never raise (the harness would stop the run); errors are collected instead."""

    def __init__(self, sprite):
        self.sprite = sprite
        self.counts = Counter()
        self.samples = []
        self.errors = []
        self.fields = Counter()
        self.branches = Counter()
        self.current = None      # resolver call in progress (target sprite, reflection caller)
        self.returned = None     # its result, until both getters consumed it
        self.pending = None      # (frame, assertion LR) expected after a NULL getter argument
        self.active = False

    def _sample(self, kind, h, **data):
        self.counts[kind] += 1
        if self.counts[kind] <= SAMPLE_LIMIT:
            self.samples.append({"event": kind, "frame": h.frame, **data})

    def _guard(self, fn, h):
        try:
            fn(h)
        except Exception as exc:
            if len(self.errors) < SAMPLE_LIMIT:
                self.errors.append(f"{type(exc).__name__}: {exc}")

    def install(self, h):
        h.on_exec(RESOLVER, lambda m: self._guard(self.entry, m))
        h.on_exec(FOLLOWER_LOAD, lambda m: self._guard(lambda x: self.load(x, 0), m))
        h.on_exec(GENERIC_LOAD, lambda m: self._guard(lambda x: self.load(x, 4), m))
        for ret in REFLECTION_RETURNS:
            h.on_exec(ret, lambda m, ret=ret: self._guard(lambda x: self.ret(x, ret), m))
        for getter in GETTER_ASSERT_LR:
            h.on_exec(getter, lambda m, g=getter: self._guard(lambda x: self.getter(x, g), m))
        h.on_exec(ASSERT, lambda m: self._guard(self.assertion, m))

    @staticmethod
    def remove(h):
        for addr in (RESOLVER, FOLLOWER_LOAD, GENERIC_LOAD, *REFLECTION_RETURNS, *GETTER_ASSERT_LR, ASSERT):
            h.on_exec(addr, None)

    def entry(self, h):
        self.current = None
        # Other overlays load over the same addresses: only overlay 1's resolver counts.
        if h.read(RESOLVER, 16) != RESOLVER_ORIGINAL[:16]:
            return
        caller = h.reg.lr & ~1
        obj = h.reg.r0
        if caller not in REFLECTION_RETURNS or not 0x02000000 <= obj < 0x023FFE00:
            return
        sprite = h.u32(obj + 0x10)
        self.counts["reflection_calls_any_sprite"] += 1
        if sprite != self.sprite:
            return
        branch = h.read(BRANCH, 2).hex()
        self.branches[branch] += 1
        self.current = {"object": obj, "caller": caller, "branch": branch,
                        "follower_ptr": h.u32(obj + FOLLOWER_FIELD), "generic_ptr": h.u32(obj + FOLLOWER_FIELD + 4)}
        self.returned = None
        if self.active:
            self.counts["resolver"] += 1

    def load(self, h, extra):
        c = self.current
        if c is None or h.reg.r0 != c["object"] + FOLLOWER_FIELD:
            return
        c["field"] = FOLLOWER_FIELD + extra
        c["selected"] = h.u32(c["object"] + FOLLOWER_FIELD + extra)

    def ret(self, h, site):
        c, self.current = self.current, None
        if c is None or c["caller"] != site or not self.active:
            return
        if "field" not in c:
            self.errors.append("reflection return without an observed pointer load")
            return
        if h.reg.r0 != c["selected"]:
            self.errors.append("returned pointer differs from the loaded field")
        self.fields[hex(c["field"])] += 1
        self.returned = {"site": site, "frame": h.frame, "pointer": h.reg.r0, "seen": set()}
        data = {"object": f"0x{c['object']:08x}", "field": hex(c["field"]), "returned": f"0x{h.reg.r0:08x}",
                "follower_ptr": f"0x{c['follower_ptr']:08x}", "generic_ptr": f"0x{c['generic_ptr']:08x}",
                "branch": c["branch"], "site": f"0x{site:08x}"}
        self._sample("reflection_return", h, **data)
        if h.reg.r0 == 0:
            self._sample("null_return", h, **data)
        if not 0x02000000 <= c["follower_ptr"] < 0x02400000:
            self.errors.append("the follower's own graphics pointer is not in main RAM")

    def getter(self, h, addr):
        r = self.returned
        if r is None or r["frame"] != h.frame or not self.active:
            return
        if (h.reg.lr & ~1) != r["site"] + GETTER_CALLER_DELTA[addr]:
            return
        if h.reg.r0 != r["pointer"]:
            self.errors.append("getter did not receive the resolver's result")
        r["seen"].add(addr)
        if r["seen"] == set(GETTER_ASSERT_LR):
            self.returned = None
        self.counts["getter"] += 1
        if h.reg.r0 == 0:
            self._sample("null_getter", h, getter=f"0x{addr:08x}")
            self.pending = (h.frame, GETTER_ASSERT_LR[addr])
        else:
            self.pending = None

    def assertion(self, h):
        if self.active and self.pending == (h.frame, h.reg.lr):
            self._sample("assertion", h, lr=f"0x{h.reg.lr:08x}")
        self.pending = None

    def report(self):
        return {"counts": dict(self.counts), "fields": dict(self.fields), "branches": dict(self.branches),
                "samples": self.samples, "hook_errors": self.errors}


def failures(name, expect, trace, moves, branch):
    """Everything that keeps a case from passing; empty means it passed."""
    reasons = []
    want_branch = (BRANCH_ORIGINAL if expect == "original" else BRANCH_FIXED).hex()
    if branch != want_branch:
        reasons.append(f"loaded branch {branch} differs from expected {want_branch}")
    if set(trace["branches"]) - {want_branch}:
        reasons.append(f"branch bytes seen at resolver entry: {trace['branches']}")
    if trace["hook_errors"]:
        reasons.append("hook errors")
    for m in moves:
        if m["position"] != m["expected"]:
            reasons.append(f"{m['direction']} step ended at {m['position']}, expected {m['expected']}")
    counts = trace["counts"]
    returns = counts.get("reflection_return", 0)
    if not returns:
        reasons.append("no reflection call for the follower observed")
    if counts.get("getter", 0) != 2 * returns:
        reasons.append(f"{counts.get('getter', 0)} getter calls for {returns} reflection returns")
    nulls = counts.get("null_return", 0)
    bad = name == "bulbasaur" and expect == "original"
    want_field = hex(FOLLOWER_FIELD + 4) if bad else hex(FOLLOWER_FIELD)
    if set(trace["fields"]) - {want_field}:
        reasons.append(f"fields read: {trace['fields']}, expected only {want_field}")
    if bad:
        if (not nulls or nulls != returns or counts.get("null_getter", 0) != 2 * nulls
                or counts.get("assertion", 0) != 2 * nulls):
            reasons.append("original defect not observed: every reflection call a NULL return, with two NULL getter "
                           "calls and two assertions each")
    elif nulls or counts.get("null_getter", 0) or counts.get("assertion", 0):
        reasons.append("NULL reflection pointer or assertion observed")
    return reasons


def run_case(h, E, scene, case, name, scene_name, expect, row):
    """One species in one scene, from the baseline state; fills row."""
    h.load_state(h.baseline)
    lead = h.party()[0]
    if lead.get("bad_egg") or not lead.get("checksum_ok", True):
        raise RuntimeError("baseline lead is not a valid Pokemon")
    h.edit_party_mon(0, species=case["species"], form=0)
    h.w32(h.array(E.ARR_PARTY) + 4, 1)
    x, y, facing = scene["start"]
    h.warp(scene["map"], x, y, E.DIRS[facing])
    h.step(60)
    party = h.party()
    row["party"] = [{"species": p["species"], "level": p.get("level")} for p in party]
    if len(party) != 1 or party[0]["species"] != case["species"]:
        raise RuntimeError(f"party is {row['party']}, expected one species {case['species']}")
    if h.position() != (scene["map"], x, y):
        raise RuntimeError(f"warp ended at {h.position()}")
    tag = f"{scene_name}_{name}"
    row["screens"] = [str(h.screenshot(tag + "_start"))]
    trace = Trace(case["sprite"])
    trace.install(h)
    trace.active = True
    moves = []
    try:
        for direction, (tx, ty) in scene["steps"]:
            if not h.step_dir(direction):      # a first press may only turn the player
                h.step_dir(direction)
            h.step(30)
            moves.append({"direction": direction, "position": list(h.position()),
                          "expected": [scene["map"], tx, ty]})
    finally:
        Trace.remove(h)
    row["screens"].append(str(h.screenshot(tag + "_end")))
    branch = h.read(BRANCH, 2).hex()
    row.update(moves=moves, branch=branch, trace=trace.report())
    row["failures"] = failures(name, expect, row["trace"], moves, branch)
    row["passed"] = not row["failures"]


def run(args, harness_factory=None):
    """Return 0 only when every requested case meets its expectation."""
    names = parse_cases(args.case) if isinstance(args.case, str) else args.case
    scene_arg = getattr(args, "scene", "all")
    scenes = parse_scenes(scene_arg) if isinstance(scene_arg, str) else scene_arg
    rom, sav, out = Path(args.rom).resolve(), Path(args.sav).resolve(), Path(args.out).resolve()
    if (out / "report.json").exists():
        raise ValueError("refusing to overwrite an existing report.json; choose a new --out")
    identity = {"rom": file_identity(rom), "save": file_identity(sav)}
    out.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "expect": args.expect, "inputs": identity, "cases": [], "passed": False,
              "setup": "One imported battery save; baseline restored before each case; the lead's species set in RAM "
                       "and the party cut to that one Pokemon; the game's Warp command to each scene; "
                       "read-only hooks. No code, object or pointer is written."}
    try:
        validate_rom(rom, args.expect)
        if harness_factory is None:
            from emu_harness import Harness
            harness_factory = Harness
        import emu_harness as E
        with harness_factory(rom, sav=sav, out=out / "screens") as h:
            h.boot_to_menu()
            h.continue_game()
            h.press("B", after=30)
            h.baseline = out / "baseline.dst"
            h.save_state(h.baseline)
            for scene_name in scenes:
                scene = SCENES[scene_name]
                for name in names:
                    case = CASES[name]
                    row = {"name": name, "scene": scene_name, "target": dict(case), "passed": False}
                    report["cases"].append(row)
                    try:
                        run_case(h, E, scene, case, name, scene_name, args.expect, row)
                    except Exception as exc:
                        row["failures"] = [f"{type(exc).__name__}: {exc}"]
                        break
        report["passed"] = len(report["cases"]) == len(names) * len(scenes) and all(r["passed"] for r in report["cases"])
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["inputs_unchanged"] = all(file_identity(p) == identity[k] for k, p in (("rom", rom), ("save", sav)))
        report["passed"] = report["passed"] and report["inputs_unchanged"]
        temporary = out / "report.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(out / "report.json")
    print(json.dumps({"passed": report["passed"], "report": str(out / "report.json"),
                      "cases": [{"name": r["name"], "scene": r["scene"], "passed": r["passed"],
                                 "counts": r.get("trace", {}).get("counts"),
                                 "fields": r.get("trace", {}).get("fields"),
                                 "failures": r.get("failures")} for r in report["cases"]]}))
    return 0 if report["passed"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ValueError, OSError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
