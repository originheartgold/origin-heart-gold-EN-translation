"""Read-only source-ROM probe of cached native payload validation.

Run from the worktree root with an unpatched, demand-loaded English ROM path.
Mutations stay in memory; this never writes a ROM or changes the checked-in cache.
The observed result should become rejection after the validation gap is fixed.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import shutil
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'tools'))
import ndspy.rom
import text_speed_patch as speed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    args = parser.parse_args()
    original = ndspy.rom.NintendoDSRom.fromFile(str(args.rom))
    results = []
    for case in ('entry_infinite_loop', 'entry_symbol_redirected'):
        payload = speed.load_payload()
        if case == 'entry_infinite_loop':
            code = bytearray.fromhex(payload['code'])
            offset = (payload['symbols']['print_task'] & ~1) - payload['base']
            code[offset:offset + 2] = bytes.fromhex('fee7')  # Thumb branch to itself.
            payload['code'] = code.hex()
        else:
            payload['symbols']['print_task'] = 0x02020a1d  # Original NORMAL task.
        rom = copy.deepcopy(original)
        try:
            output = speed.WORK / 'build/text-speed/review/root-audit'
            output.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=output) as directory:
                cache = Path(directory)
                for name in ('native.c', 'labels.h'):
                    shutil.copy2(speed.ASSETS / name, cache / name)
                (cache / 'payload.json').write_text(json.dumps(payload))
                with patch.object(speed, 'ASSETS', cache):
                    report = speed.apply(rom)
                    result = speed.verify(rom, report)
            results.append({'case': case, 'rejected': False, 'verification': result})
        except (ValueError, AssertionError) as error:
            results.append({'case': case, 'rejected': True, 'reason': str(error)})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
