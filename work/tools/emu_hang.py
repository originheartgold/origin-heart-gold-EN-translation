"""emu_hang - walk from a battery save and check whether the game freezes (melonDS backend by default).

    <venv>/bin/python work/tools/emu_harness.py [--emulator melonds] hang --case CASE \
        --rom R --sav S --expect hang|pass [--species N] [--out DIR]
    <venv>/bin/python work/tools/emu_harness.py hang --case save --rom R --sav S --walk LEFT,RIGHT,... \
        [--goal X,Y] [--fault-pc 0x...] --expect hang|pass

melonDS 1.1 emulates the ARM9 protection unit, so a NULL read the hack makes is a data abort there (and on
hardware) and the game hangs in the abort handler; DeSmuME reads address 0 and goes on. A case may first edit a
copy of the save (teleport for Continue, party lead species and count), then boots it, picks Continue and walks
its steps one tile at a time. It stops at the goal, on an ARM9 abort, or when a step fails (an event took over),
then watches the game for a while (Harness.hang_report) and judges:
    hang   the ARM9 sits in abort mode (melonDS), or a black screen never changes, and the goal was not reached
    pass   the goal was reached, no data abort happened and the screen still changes
Cases:
    rocket_hq          D-2043: player A's save, Rocket HQ B1F, east from (13,4) to the camera ambush at (23,4)
    follower_viridian  the lead Pokemon (--species, default 1 Bulbasaur) follows the player along the Viridian City
                       pond (the Bulbasaur reflection scene); player B's outdoor save, teleported for Continue
    save               any save as it is: Continue, then the --walk steps (none: only watch the field). The goal
                       is --goal (x,y after the last step) or, without it, every step moving. An abort while
                       Continue loads the map counts as a hang (no step is walked). Reproductions of the
                       Bulbasaur fixture saves: work/notes/melonds_backend.md
The input ROM and save are never written. Evidence: <out>/<case>_<rom>_<emulator>/report.json and screenshots.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

CASES = {
    # work/notes/rocket_hq_freeze_repro_20261008.md: player A's save at (13,4), walking east towards the camera
    # ambush at (23,4). Fixed by work/patches/overworld-texture-frame-bounds.
    "rocket_hq": {"sav_sha256": "ee32cbb4ecba965b4de02b5bd7ed3dba33d85a6f18fc8c2b154fcc357b97978b",
                  "start": (247, 13, 4), "steps": ("RIGHT",) * 10, "goal": (23, 4), "fault_pc": 0x02024696},
    # The dry strip north of the Viridian City pond (map 50), the scene of the Bulbasaur follower reflection NULL
    # pointer: the reflection's graphics getter 0x0202451C reads address 0xB6 (abort at 0x02024528). Player B's
    # hash-named save stands outdoors (map 29), so the save teleport works; a teleport from an indoor save
    # (memcheck/full_bag_6mons.sav, map 500) leaves the player unable to move on outdoor maps.
    "follower_viridian": {"sav_sha256": "0886514dc87289d886c53ff2834052ab8acabf911c3da1c93ace8bb597ebc9eb",
                          "teleport": (50, 1017, 260, "DOWN"), "species": 1, "party_count": 1,
                          "start": (50, 1017, 260), "steps": ("DOWN", "RIGHT", "RIGHT", "LEFT"), "goal": (1018, 261),
                          "fault_pc": 0x02024528},
}
RTC = datetime.datetime(2026, 10, 9, 12, 0, 0)


def add_arguments(p):
    p.add_argument("--case", default="rocket_hq", choices=sorted(CASES) + ["save"])
    p.add_argument("--rom", required=True)
    p.add_argument("--sav", required=True, help="the battery save (never written); the named cases check its SHA-256")
    p.add_argument("--walk", default="", help="case save: comma list of UP/DOWN/LEFT/RIGHT, one tile each")
    p.add_argument("--goal", help="case save: x,y the last step must reach (default: every step moves)")
    p.add_argument("--fault-pc", type=lambda v: int(v, 0), help="case save, expect hang: the faulting instruction")
    p.add_argument("--expect", choices=("hang", "pass"), required=True)
    p.add_argument("--species", type=int, help="party lead species for cases that set one (follower_viridian)")
    p.add_argument("--out", default=None, help="evidence folder (default <work>/build/harness/hang)")
    p.add_argument("--watch-frames", type=int, default=240)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def prepare_save(eh, sav, case, species, folder):
    """The save to boot: the input itself, or an edited copy in `folder` (teleport, party lead and count)."""
    if "teleport" not in case and "species" not in case:
        return sav
    sf = eh.SaveFile(sav)
    if "teleport" in case:
        m, x, y, d = case["teleport"]
        sf.place_player(m, x, y, d)
    if "species" in case:
        sf.edit_party_mon(0, species=species or case["species"], form=0)
        sf.set_party_count(case.get("party_count", 6))
    return sf.write(Path(folder) / "edited.sav")


def save_case(a):
    """The `save` case from --walk / --goal / --fault-pc."""
    steps = tuple(d.strip().upper() for d in a.walk.split(",") if d.strip())
    bad = [d for d in steps if d not in ("UP", "DOWN", "LEFT", "RIGHT")]
    if bad:
        raise SystemExit(f"--walk: unknown direction(s) {bad}")
    goal = tuple(int(v) for v in a.goal.split(",")) if a.goal else None
    if goal is not None and len(goal) != 2:
        raise SystemExit("--goal takes x,y")
    return {"steps": steps, "goal": goal, "fault_pc": a.fault_pc}


def walk_case(h, case, watch_frames=240):
    """Run one case on a booted Harness standing in the field; returns the report dict (no judgement)."""
    steps = []
    if case.get("start") and h.position() != tuple(case["start"]):
        raise RuntimeError(f"the field starts at {h.position()}, the case expects {tuple(case['start'])}")
    early = h.arm9_abort() if h.emulator == "melonds" else None     # e.g. while Continue loaded the map
    for d in case["steps"] if not early else ():
        ok = h.step_dir(d)
        pos = h.position()
        abort = h.arm9_abort() if h.emulator == "melonds" else None
        steps.append({"dir": d, "moved": ok, "position": list(pos), "frame": h.frame, "abort": abort is not None})
        if abort or not ok:
            break
    h.screenshot("after_walk")
    rep = h.hang_report(watch_frames, probe_key="B")
    h.screenshot("after_watch")
    rep["steps"] = steps
    rep["abort_before_walking"] = early is not None
    done = not early and len(steps) == len(case["steps"]) and all(s["moved"] for s in steps)
    if case.get("goal") is None:
        rep["reached_goal"] = done
    else:
        rep["reached_goal"] = bool(done and steps and tuple(steps[-1]["position"][1:]) == tuple(case["goal"]))
    return rep


def judge(rep, expect, case):
    ab = rep.get("abort")
    if expect == "hang":
        problems = [] if rep["hung"] else ["the game did not hang"]
        if rep["reached_goal"] and case["steps"]:
            problems.append(f"reached the goal {case.get('goal') or 'after every step'}")
        if ab and case.get("fault_pc") and ab["fault_pc"] != case["fault_pc"]:
            problems.append(f"aborted at {ab['fault_pc']:#010x}, not {case['fault_pc']:#010x}")
    else:
        problems = []
        if not rep["reached_goal"]:
            problems.append(f"did not reach {case.get('goal') or 'the end of the walk'}")
        if rep["hung"]:
            problems.append("the game hung")
        if rep.get("exceptions", {}).get("data_aborts"):
            problems.append(f"{rep['exceptions']['data_aborts']} data abort(s)")
        if not rep["screen_changed"]:
            problems.append("the screen did not change while watching")
    return problems


R0_NOTE = ("R0 is not recorded: after an aborted load melonDS writes an uninitialised local of the core into the "
           "destination register (T_LDR_IMM), so it differs between processes (work/notes/melonds_backend.md)")


def abort_record(ab):
    """Harness.arm9_abort() for report.json: addresses in hex, R0 masked (see R0_NOTE)."""
    return ab | {k: f"{ab[k]:#010x}" for k in ("cpsr", "abort_lr", "fault_pc")} | {
        "r": [None] + [f"{v:#010x}" for v in ab["r"][1:]], "r0_note": R0_NOTE}


def run(a):
    import emu_harness as eh
    case = CASES[a.case] if a.case != "save" else save_case(a)
    emulator = os.environ.get("EMU_HARNESS_EMULATOR") or "melonds"
    rom, sav = Path(a.rom).resolve(), Path(a.sav).resolve()
    have = sha256(sav)
    if case.get("sav_sha256") and have != case["sav_sha256"]:
        raise SystemExit(f"{sav}: SHA-256 {have}, the case needs {case['sav_sha256']}")
    species = (a.species if a.species is not None else case.get("species")) if "species" in case else None
    tag = (f"{a.case}" if a.case != "save" else f"save_{sav.stem}") + (f"_sp{species}" if species is not None else "")
    out = (Path(a.out or eh.DEF_OUT / "hang") / f"{tag}_{rom.stem}_{emulator}").resolve()
    tmp = tempfile.mkdtemp(prefix="emu_hang_")
    try:
        boot_sav = prepare_save(eh, sav, case, species, tmp)
        with eh.Harness(rom, boot_sav, out=out, emulator=emulator, rtc=RTC) as h:
            h.boot_to_menu()
            h.continue_game()
            h.press("B", after=30)
            h.screenshot("start")
            party = [p["species"] for p in h.party()]
            rep = walk_case(h, case, a.watch_frames)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    problems = judge(rep, a.expect, case)
    rep.update({"case": a.case, "emulator": emulator, "expect": a.expect, "ok": not problems, "problems": problems,
                "rom": {"path": str(rom), "sha256": sha256(rom)}, "sav": {"path": str(sav), "sha256": have},
                "rtc": RTC.isoformat(), "party": party})
    if rep.get("abort"):
        rep["abort"] = abort_record(rep["abort"])
    (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    print(f"RESULT {tag} {emulator} {rom.name}: {'OK' if not problems else 'FAIL'} (expect {a.expect}; "
          f"hung={rep['hung']}, goal={rep['reached_goal']}, last={rep['steps'][-1]['position'] if rep['steps'] else None}"
          + (f", fault_pc={rep['abort']['fault_pc']}" if rep.get("abort") else "") + ")"
          + ("" if not problems else " - " + "; ".join(problems)))
    print(f"report {out / 'report.json'}")
    return 0 if not problems else 1
