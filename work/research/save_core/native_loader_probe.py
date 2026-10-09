#!/usr/bin/env python3
"""Observe Origin's native save selection on private malformed-fixture copies.

Requires the existing local melonDS shim and ROM; no downloads or ROM builds.
The fixture builder is deliberately independent from the production save core.
All commands run from the repository root. Output belongs under ignored work/build.
"""
import argparse
import binascii
import datetime
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from melonds import MelonDS

GENERAL = 0xf7cc
STORAGE = 0xf800
STORAGE_SIZE = 0x18408
MIRROR = 0x40000
MARKERS = (111111, 222222)


def identity(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def fixture(seed, counters, storage_counters, corrupt=(), identical=False):
    data = bytearray(seed)
    # Use one intact seed generation for both; only test fields differ.
    for mirror in (0, MIRROR):
        data[mirror:mirror + GENERAL] = seed[:GENERAL]
        data[mirror + STORAGE:mirror + STORAGE + STORAGE_SIZE] = seed[STORAGE:STORAGE + STORAGE_SIZE]
    for index, mirror in enumerate((0, MIRROR)):
        struct.pack_into('<I', data, mirror + 0x78, MARKERS[0 if identical else index])
        for label, offset, size, counter in [('general', 0, GENERAL, counters[index]),
                                             ('storage', STORAGE, STORAGE_SIZE, storage_counters[index])]:
            footer = mirror + offset + size - 16
            struct.pack_into('<I', data, footer, counter)
            struct.pack_into('<H', data, footer + 14,
                             binascii.crc_hqx(data[mirror + offset:footer], 0xffff))
            if (label, index) in corrupt:
                data[mirror + offset + 42] ^= 1
    return bytes(data)


CASES = {
    'ordinary_first': ((10, 9), (10, 9), ()),
    'ordinary_second': ((9, 10), (9, 10), ()),
    'equal_divergent': ((10, 10), (10, 10), ()),
    'equal_identical': ((10, 10), (10, 10), ()),
    'rollover_first': ((0, 0xffffffff), (0, 0xffffffff), ()),
    'rollover_second': ((0xffffffff, 0), (0xffffffff, 0), ()),
    'newest_storage_counter_mismatch': ((10, 9), (8, 9), ()),
    'both_storage_counters_mismatch': ((10, 9), (8, 7), ()),
    'crossed_storage_counters': ((10, 9), (9, 10), ()),
    'newest_storage_corrupt': ((10, 9), (10, 9), (('storage', 0),)),
    'both_storage_corrupt': ((10, 9), (10, 9), (('storage', 0), ('storage', 1))),
    'newest_general_corrupt': ((10, 9), (10, 9), (('general', 0),)),
    'backup_general_corrupt': ((10, 9), (10, 9), (('general', 1),)),
    'backup_both_corrupt': ((10, 9), (10, 9), (('general', 1), ('storage', 1))),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--seed', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--case', choices=tuple(CASES))
    args = parser.parse_args()
    output = args.out.resolve()
    if not output.is_relative_to((Path.cwd() / 'work/build').resolve()):
        parser.error('--out must be under work/build')
    output.mkdir(parents=True, exist_ok=False)
    seed = args.seed.read_bytes()
    assert len(seed) == 524288
    before = [identity(args.rom), identity(args.seed)]
    rows = []
    for name, (counters, storage_counters, corrupt) in CASES.items():
        if args.case and name != args.case:
            continue
        data = fixture(seed, counters, storage_counters, corrupt, identical=name == 'equal_identical')
        row = {'case': name, 'general_counters': counters, 'storage_counters': storage_counters, 'corrupt': corrupt,
               'fixture_sha256': hashlib.sha256(data).hexdigest()}
        with MelonDS() as emu:
            emu.load_rom(args.rom.resolve(), sav=data, rtc=datetime.datetime(2026, 10, 9, 12))
            emu.run(2400)
            emu.press('START', after=700)
            snapshots = []
            for attempt in range(5):
                pointer = emu.u32(0x021d11b4)
                if 0x02000000 <= pointer <= 0x02400000 - 0x30000:
                    snapshots.append({'attempt': attempt, 'money': emu.u32(pointer + 0x10 + 0x78),
                                      'count': emu.u32(pointer + 0x10 + 0x94)})
                if snapshots and snapshots[-1]['money'] in MARKERS:
                    break
                emu.press('A', after=300)
            row['snapshots'] = snapshots
            row['marker'] = snapshots[-1]['money'] if snapshots and snapshots[-1]['money'] in MARKERS else None
            row['selected_mirror'] = None if row['marker'] is None else MARKERS.index(row['marker'])
            emu.screenshot().save(output / (name + '.png'))
        rows.append(row)
        print(json.dumps(row), flush=True)
        (output / 'report.json').write_text(json.dumps({'inputs': before, 'rows': rows}, indent=2) + '\n')
    after = [identity(args.rom), identity(args.seed)]
    assert after == before, 'Source ROM or seed changed'
    (output / 'report.json').write_text(json.dumps({'inputs': before, 'inputs_unchanged': True, 'rows': rows}, indent=2) + '\n')


if __name__ == '__main__':
    main()
