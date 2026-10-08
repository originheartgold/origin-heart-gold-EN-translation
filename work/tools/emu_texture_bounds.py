"""Reproduce four Origin v4.0.3 texture bounds failures using disposable RAM.

This module imports no emulator until run(). It never writes the input ROM/save.
The native DeSmuME library tolerates the observed null load; read-only instruction
hooks distinguish the original defect from a guard that safely skips it.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import struct
from pathlib import Path

# The hack's arm9 routine ObjTex_SetTexture (work/patches/overworld-texture-frame-bounds): its bounds
# branch, the NULL load the original branch leads to, and its return, which the fix branches to instead.
ARM9_BASE = 0x02000000
ROUTINE = 0x02024654
BOUNDS = 0x0202467C
LOAD = 0x02024696
EPILOGUE = 0x020246D8
# The routine as the Chinese ROM has it, push through pop (test_emu_texture_bounds checks it against the
# ROM and against the fix's [[code]] region; asmpatch's armips guard checks the same bytes in the build).
ROUTINE_ORIGINAL = bytes.fromhex(
    "f8b5002804d08368002b01d0c61800e0002630883418002912d0081c3c300dd0"
    "0b1c3d331b789a4208d2423109884318405a1b1d011c5143581802e0002000e0"
    "0020006800250004070c6078002819dd002c0ad06078854207d2e0882118205a"
    "0a1d011c6943511800e00021ca780120104203d0301c3a1c00f006f860786d1c"
    "8542e5dbf8bd")
BRANCH_ORIGINAL = bytes.fromhex("08d2")   # bhs 0x02024690 (r0 = NULL, then the load)
BRANCH_FIXED = bytes.fromhex("2cd2")      # bhs 0x020246D8 (return)
SAMPLE_LIMIT = 12
CASES = {
    "rocket_hq": {"map": 247, "x": 17, "y": 4, "flag": 355, "index": 4},
    "five_island": {"map": 154, "x": 104, "y": 54, "flag": 2173, "index": 4},
    "seven_island": {"map": 163, "x": 245, "y": 104, "flag": 2198, "index": 11},
    "bell_tower": {"map": 340, "x": 15, "y": 17, "flag": 1140, "index": 15},
}


def parse_cases(value):
    names = list(CASES) if value == "all" else value.split(",")
    if not names or any(n not in CASES for n in names) or len(set(names)) != len(names):
        raise argparse.ArgumentTypeError("choose all or unique comma-separated cases: " + ",".join(CASES))
    return names


def add_arguments(parser):
    parser.add_argument("--rom", required=True, help="local original or guard-patched Origin v4.0.3 ROM")
    parser.add_argument("--sav", required=True, help="local raw battery save; imported without changing the file")
    parser.add_argument("--out", required=True, help="new evidence directory (must not already contain report.json)")
    parser.add_argument("--case", default="all", help="all or comma-separated " + ",".join(CASES))
    parser.add_argument("--expect", required=True, choices=("original", "fixed"))


def file_identity(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest.hexdigest()}


def validate_rom(path, expect):
    """Reject unfamiliar code before starting emulation (the whole routine, its return included).
    Reads the ARM9 straight from the ROM file: the build writes it uncompressed."""
    with path.open("rb") as stream:
        header = stream.read(0x200)
        if len(header) != 0x200:
            raise ValueError("truncated NDS header")
        offset, _, address, size = struct.unpack_from("<4I", header, 0x20)
        if (address != ARM9_BASE or offset < 0x200 or offset + size > path.stat().st_size
                or size < EPILOGUE - address + 2):
            raise ValueError("unsupported ARM9 address/size/bounds")
        stream.seek(offset + ROUTINE - address)
        if stream.read(len(ROUTINE_ORIGINAL)) != routine_bytes(expect):
            raise ValueError("ARM9 texture routine differs from the expected " + expect + " routine")


def routine_bytes(expect):
    """The whole routine, push through pop, as the original or the fixed ROM has it."""
    data = bytearray(ROUTINE_ORIGINAL)
    if expect == "fixed":
        data[BOUNDS - ROUTINE:BOUNDS - ROUTINE + 2] = BRANCH_FIXED
    return bytes(data)


class Trace:
    """Bounded samples, unbounded counters; callbacks never let exceptions escape ctypes."""
    def __init__(self, map_id):
        self.map_id = map_id
        self.valid = 0
        self.invalid = 0
        self.null = 0
        self.pairs = Counter()
        self.samples = []
        self.errors = []
        self.wrong_map = 0

    def observe(self, h, kind):
        try:
            location = h.location()
            if location["map"] != self.map_id:
                self.wrong_map += 1
                return
            if kind == "bounds":
                index, count = h.reg.r2, h.reg.r3
                if index < count:
                    self.valid += 1
                    return
                self.invalid += 1
                self.pairs[(index, count)] += 1
            elif h.reg.r0 == 0:
                self.null += 1
            else:
                return
            if len(self.samples) < SAMPLE_LIMIT:
                self.samples.append({"kind": kind, "frame": h.frame, "location": location,
                                     "registers": {f"r{i}": f"0x{getattr(h.reg, f'r{i}'):08x}"
                                                   for i in range(7)}})
        except Exception as exc:
            if len(self.errors) < SAMPLE_LIMIT:
                self.errors.append(f"{type(exc).__name__}: {exc}")

    def report(self):
        return {"valid_updates": self.valid, "invalid_requests": self.invalid,
                "null_loads": self.null, "wrong_map_hook_calls": self.wrong_map,
                "index_counts": [{"index": i, "count": c, "requests": n}
                                 for (i, c), n in sorted(self.pairs.items())],
                "samples": self.samples, "hook_errors": self.errors}


def failures(case, expect, start, end, trace, branch):
    reasons = []
    expected_branch = (BRANCH_ORIGINAL if expect == "original" else BRANCH_FIXED).hex()
    if branch != expected_branch:
        reasons.append(f"bounds branch {branch} differs from expected {expected_branch}")
    for label, loc in (("start", start), ("end", end)):
        if any(loc.get(k) != case[k] for k in ("map", "x", "y")):
            reasons.append(f"{label} location differs from requested map/position")
    if trace["hook_errors"] or trace["wrong_map_hook_calls"]:
        reasons.append("hook error or unexpected map during observation")
    expected = sum(row["requests"] for row in trace["index_counts"]
                   if row["index"] == case["index"] and row["count"] == 1)
    if not expected:
        reasons.append(f"no invalid index {case['index']} request against count 1")
    if trace["valid_updates"] <= 0:
        reasons.append("no valid texture updates observed")
    if expect == "original" and trace["null_loads"] <= 0:
        reasons.append("original defect not observed: no null load")
    if expect == "fixed" and trace["null_loads"] != 0:
        reasons.append("fixed ROM still executes null loads")
    return reasons


def run(args, harness_factory=None):
    """Return 0 only when every requested reproduction satisfies all assertions."""
    names = parse_cases(args.case) if isinstance(args.case, str) else args.case
    rom, sav, out = Path(args.rom).resolve(), Path(args.sav).resolve(), Path(args.out).resolve()
    if (out / "report.json").exists():
        raise ValueError("refusing to overwrite an existing report.json; choose a new --out")
    artifacts = [out / n for n in ("report.json", "report.json.tmp", "baseline.dst")]
    artifacts += [out / "screens" / (n + ".png") for n in names]
    if any(p.resolve() in (rom, sav) for p in artifacts):
        raise ValueError("output artifact would overwrite an input")
    identity = {"rom": file_identity(rom), "save": file_identity(sav)}
    out.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "expect": args.expect, "inputs": identity, "cases": [],
              "setup": "One imported battery save; baseline restored before each case; normal scripted warps and explicit RAM visibility flags. "
                       "No save export or input writes. Hooks count only settled target-map frames.",
              "emulator": "py-desmume (native library version printed at startup)", "passed": False}
    try:
        validate_rom(rom, args.expect)
        if harness_factory is None:
            from emu_harness import Harness
            harness_factory = Harness
        with harness_factory(rom, sav=sav, out=out / "screens") as h:
            h.boot_to_menu()
            h.continue_game()
            baseline = out / "baseline.dst"
            h.save_state(baseline)
            for name in names:
                case = CASES[name]
                row = {"name": name, "target": dict(case), "passed": False}
                report["cases"].append(row)
                try:
                    h.load_state(baseline)
                    before = h.get_flag(case["flag"])
                    h.set_flag(case["flag"], False)
                    row["setup_flags"] = [{"flag": case["flag"], "before": before, "after": False,
                                           "reason": "show candidate objects before normal map entry"}]
                    h.warp(case["map"], case["x"], case["y"], 0)
                    row["flag_after_warp"] = h.get_flag(case["flag"])
                    start = h.location()
                    branch = h.read(BOUNDS, 2).hex()
                    trace = Trace(case["map"])
                    try:
                        h.on_exec(BOUNDS, lambda machine: trace.observe(machine, "bounds"))
                        h.on_exec(LOAD, lambda machine: trace.observe(machine, "load"))
                        h.step(360)
                    finally:
                        h.on_exec(BOUNDS, None)
                        h.on_exec(LOAD, None)
                    end = h.location()
                    row.update(start=start, end=end, branch=branch, trace=trace.report())
                    row["failures"] = failures(case, args.expect, start, end, row["trace"], branch)
                    if row["flag_after_warp"]:
                        row["failures"].append("candidate hide flag was set again by map entry")
                    row["screenshot"] = str(h.screenshot(name))
                    row["passed"] = not row["failures"]
                except Exception as exc:
                    row["failures"] = [f"{type(exc).__name__}: {exc}"]
                    # A failed warp can leave script/menu state unsafe for later cases.
                    break
        report["passed"] = len(report["cases"]) == len(names) and all(r["passed"] for r in report["cases"])
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        # Make accidental writes visible in the result, even when setup fails.
        report["inputs_unchanged"] = all(file_identity(p) == identity[k] for k, p in (("rom", rom), ("save", sav)))
        report["passed"] = report["passed"] and report["inputs_unchanged"]
        temporary = out / "report.json.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(out / "report.json")
    print(json.dumps({"passed": report["passed"], "report": str(out / "report.json"),
                      "cases": [{"name": r["name"], "passed": r["passed"]} for r in report["cases"]]}))
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
