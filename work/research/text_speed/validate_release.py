"""Assert native menu, dialogue and memory behavior on a cold-boot release ROM.

Run from the worktree root. This uses original battery saves, never pre-change
emulator states. Output, private emulator settings and logs stay under work/build.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / 'work/build'
PROBE = ROOT / 'work/research/text_speed/native_probe.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--trainer-save', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(BUILD) or output == BUILD:
        parser.error('Output must be a subdirectory of this worktree work/build')
    output.mkdir(parents=True, exist_ok=True)
    rom = args.rom.resolve()
    identity = hashlib.sha256(rom.read_bytes()).hexdigest()
    summary = {'rom_sha256': identity, 'status': 'failed', 'modes': {}}
    page_pixels = {}
    try:
        for mode, x in enumerate((130, 177, 227)):
            name = ('normal', 'fast', 'instant')[mode]
            directory = output / name
            script = ('fieldboot; press X; wait 90; press RIGHT; wait 30; '
                      'press DOWN; wait 30; press DOWN; wait 30; press A; wait 300; shot open; '
                      f'touch {x} 152; wait 60; shot selected; '
                      'touch 149 180; wait 300; shot confirmed; '
                      'press A 6; wait 234; shot page1; '
                      'press A 6; wait 234; shot page2; '
                      'press A 6; wait 600; shot battle; wait 600; shot battle-ready')
            with (output / (name + '.log')).open('w') as log:
                subprocess.run([sys.executable, str(PROBE), str(directory), str(rom),
                                str(args.trainer_save.resolve()), script], cwd=ROOT,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
            report = json.loads((directory / 'report.json').read_text())
            assert report['rom_sha256'] == identity, 'wrong candidate executed'
            assert report['memory_status'] == 'passed', report
            shots = {row['name']: row for row in report['snapshots']}
            assert shots['open']['rows'][6] == {'count': 3, 'value': 0}, 'old-save default changed'
            assert shots['selected']['rows'][6]['value'] == mode, 'touch selection missed'
            assert shots['selected']['saved_options'] == shots['open']['saved_options'], 'selection committed early'
            expected = (shots['open']['saved_options'] & ~12) | (mode << 2)
            assert shots['confirmed']['saved_options'] == expected, 'confirm lost neighboring options'
            glyphs = [row for row in report['glyphs'] if row['font'] == 1
                      and shots['confirmed']['frame'] < row['frame'] <= shots['page1']['frame']]
            assert len(glyphs) == 54, f'expected trainer page, observed {len(glyphs)} glyphs'
            frames = [row['frame'] for row in glyphs]
            summary['modes'][name] = {'glyphs': len(glyphs), 'frame_span': max(frames) - min(frames),
                                      'saved_options': expected, 'heap_checks': report['heap_checks']}
            page_pixels[name] = Image.open(directory / 'page1.png').crop((8, 153, 236, 182)).tobytes()
            print(name, summary['modes'][name], flush=True)
        spans = [summary['modes'][name]['frame_span'] for name in ('normal', 'fast', 'instant')]
        assert spans[0] > spans[1] > spans[2], spans
        assert page_pixels['normal'] == page_pixels['fast'] == page_pixels['instant'], 'completed dialogue differs'
        assert hashlib.sha256(rom.read_bytes()).hexdigest() == identity, 'source ROM changed'
        summary['status'] = 'passed'
    finally:
        (output / 'report.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
