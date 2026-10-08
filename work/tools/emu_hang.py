"""emu_hang - walk from a battery save and check whether the game freezes (melonDS backend by default).

    <venv>/bin/python work/tools/emu_harness.py [--emulator melonds] hang --case CASE \
        --rom R --sav S --expect hang|pass [--species N] [--out DIR]

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
    p.add_argument("--case", default="rocket_hq", choices=sorted(CASES))
    p.add_argument("--rom", required=True)
    p.add_argument("--sav", required=True, help="the case's battery save (checked by SHA-256, never written)")
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


def walk_case(h, case, watch_frames=240):
    """Run one case on a booted Harness standing in the field; returns the report dict (no judgement)."""
    steps = []
    if h.position() != tuple(case["start"]):
        raise RuntimeError(f"the field starts at {h.position()}, the case expects {tuple(case['start'])}")
    for d in case["steps"]:
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
    rep["reached_goal"] = (len(steps) == len(case["steps"]) and steps[-1]["moved"]
                           and tuple(steps[-1]["position"][1:]) == tuple(case["goal"]))
    return rep


def judge(rep, expect, case):
    ab = rep.get("abort")
    if expect == "hang":
        problems = [] if rep["hung"] else ["the game did not hang"]
        if rep["reached_goal"]:
            problems.append(f"reached the goal {case['goal']}")
        if ab and case.get("fault_pc") and ab["fault_pc"] != case["fault_pc"]:
            problems.append(f"aborted at {ab['fault_pc']:#010x}, not {case['fault_pc']:#010x}")
    else:
        problems = []
        if not rep["reached_goal"]:
            problems.append(f"did not reach {case['goal']}")
        if rep["hung"]:
            problems.append("the game hung")
        if rep.get("exceptions", {}).get("data_aborts"):
            problems.append(f"{rep['exceptions']['data_aborts']} data abort(s)")
        if not rep["screen_changed"]:
            problems.append("the screen did not change while watching")
    return problems


def run(a):
    import emu_harness as eh
    case = CASES[a.case]
    emulator = os.environ.get("EMU_HARNESS_EMULATOR") or "melonds"
    rom, sav = Path(a.rom).resolve(), Path(a.sav).resolve()
    have = sha256(sav)
    if have != case["sav_sha256"]:
        raise SystemExit(f"{sav}: SHA-256 {have}, the case needs {case['sav_sha256']}")
    species = a.species if a.species is not None else case.get("species")
    tag = f"{a.case}" + (f"_sp{species}" if species is not None else "")
    out = Path(a.out or eh.DEF_OUT / "hang") / f"{tag}_{rom.stem}_{emulator}"
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
        ab = rep["abort"]
        rep["abort"] = ab | {k: f"{ab[k]:#010x}" for k in ("cpsr", "abort_lr", "fault_pc")} | {
            "r": [f"{v:#010x}" for v in ab["r"]]}
    (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    print(f"RESULT {tag} {emulator} {rom.name}: {'OK' if not problems else 'FAIL'} (expect {a.expect}; "
          f"hung={rep['hung']}, goal={rep['reached_goal']}, last={rep['steps'][-1]['position'] if rep['steps'] else None}"
          + (f", fault_pc={rep['abort']['fault_pc']}" if rep.get("abort") else "") + ")"
          + ("" if not problems else " - " + "; ".join(problems)))
    print(f"report {out / 'report.json'}")
    return 0 if not problems else 1
