#!/usr/bin/env python3
"""emu_smoke - headless DeSmuME smoke test for the WIP ROM (needs py-desmume; not in the system python).

Setup (once; py-desmume ships a macOS arm64 wheel with libdesmume bundled):
    python3 -m venv <venv> && <venv>/bin/pip install py-desmume pillow
Run:
    <venv>/bin/python work/tools/emu_smoke.py [--rom work/build/origin_hg_v4.0.3_en_wip.nds]
        [--out work/build/screens] [--script "wait 600; shot boot; press A; wait 60; ..."]
        [--every N]      # additionally save a screenshot every N frames (exploration)

Script commands (separated by ';'):
    wait N              run N frames
    press KEY [N]       hold KEY (A B X Y L R START SELECT UP DOWN LEFT RIGHT) for N frames (default 6), then release
    mash KEY TIMES GAP  press KEY TIMES times, GAP frames apart
    touch X Y [N]       touch the bottom screen at (X, Y) for N frames
    shot NAME           save <out>/NAME.png (both screens, 256x384)
Nothing is written next to the ROM: the battery save goes to a temporary copy directory.
"""
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# No sound from any emulator this process starts: SDL's dummy audio driver opens no output device
# (the emulated sound chip still runs, so game timing is unchanged).
os.environ["SDL_AUDIODRIVER"] = "dummy"

WORK = Path(__file__).resolve().parent.parent
DEFAULT_SCRIPT = (
    "wait 2400; press START; wait 90; shot 01_title; press START; wait 400; shot 02_hack_notice_zh;"
    " mash A 58 60; wait 300; shot 03_intro_menu; touch 128 153 8; wait 240; shot 04_dialogue_1; press A; wait 180; shot 05_dialogue_2; press A; wait 180; shot 06_dialogue_3; mash A 12 90; shot 07_dialogue_later"
)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(WORK / "build" / "origin_hg_v4.0.3_en_wip.nds"))
    ap.add_argument("--out", default=str(WORK / "build" / "screens"))
    ap.add_argument("--script", default=DEFAULT_SCRIPT)
    ap.add_argument("--every", type=int, default=0)
    ap.add_argument("--prefix", default="")
    a = ap.parse_args(argv)

    from desmume.emulator import DeSmuME
    from desmume.controls import Keys, keymask

    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    keys = {k[4:]: getattr(Keys, k) for k in dir(Keys) if k.startswith("KEY_")}
    tmp = Path(tempfile.mkdtemp(prefix="emu_smoke_"))
    rom = tmp / Path(a.rom).name
    os.symlink(os.path.abspath(a.rom), rom)
    cwd = os.getcwd()
    os.chdir(tmp)
    emu = DeSmuME()
    emu.open(str(rom))
    frame = [0]

    def step(n):
        for _ in range(n):
            emu.cycle(with_joystick=False)
            frame[0] += 1
            if a.every and frame[0] % a.every == 0:
                emu.screenshot().save(out / f"{a.prefix}f{frame[0]:06d}.png")

    def press(k, n=6):
        emu.input.keypad_add_key(keymask(keys[k]))
        step(n)
        emu.input.keypad_rm_key(keymask(keys[k]))

    try:
        for cmd in [c.strip() for c in a.script.split(";") if c.strip()]:
            p = cmd.split()
            if p[0] == "wait":
                step(int(p[1]))
            elif p[0] == "press":
                press(p[1].upper(), int(p[2]) if len(p) > 2 else 6)
            elif p[0] == "mash":
                for _ in range(int(p[2])):
                    press(p[1].upper())
                    step(int(p[3]))
            elif p[0] == "touch":
                emu.input.touch_set_pos(int(p[1]), int(p[2]))
                step(int(p[3]) if len(p) > 3 else 6)
                emu.input.touch_release()
            elif p[0] == "shot":
                path = out / f"{a.prefix}{p[1]}.png"
                emu.screenshot().save(path)
                print(f"frame {frame[0]:6d}: {path}")
            else:
                sys.exit(f"unknown command {cmd!r}")
    finally:
        emu.destroy()
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
