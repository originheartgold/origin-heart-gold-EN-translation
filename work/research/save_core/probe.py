#!/usr/bin/env python3
"""Reproduce save-core differences using invented bytes and optional read-only local saves.

Historical baseline probe for e084341, before shared-core migration. Its assertions
deliberately characterize old unsafe behavior; use current shared-core tests for
regressions. Run from the baseline repository root after compiling work/save-editor.
Prints metadata only.
This is a characterization probe, not a production adapter or a playable save creator.
"""
import argparse
import base64
import binascii
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/tools'))
import emu_harness as E


def crypt(data, seed):
    result = bytearray()
    for (word,) in struct.iter_unpack('<H', data):
        seed = (1103515245 * seed + 24691) % (2 ** 32)
        result.extend(struct.pack('<H', word ^ (seed >> 16)))
    return bytes(result)


def pokemon(selector=0, nature_override=None):
    # Independent fixture construction: never use either production encoder.
    logical = [bytearray(32) for _ in range(4)]
    struct.pack_into('<HH', logical[0], 0, 201, 7)
    struct.pack_into('<4H', logical[1], 0, 33, 44, 55, 66)
    logical[1][8:16] = bytes([10, 11, 12, 13, 1, 2, 3, 0])
    logical[1][24] = 5 << 3
    if nature_override is not None:
        struct.pack_into('<I', logical[1], 20, (nature_override + 1) << 25)
    order = list(itertools.permutations(range(4)))[selector % 24]
    plain = b''.join(logical[i] for i in order)
    checksum = sum(word for (word,) in struct.iter_unpack('<H', plain)) & 65535
    pid = (selector << 13) | 0x345
    tail = bytearray(100)
    tail[4] = 15
    return struct.pack('<IHH', pid, 0, checksum) + crypt(plain, checksum) + crypt(tail, pid)


def save(counters=(10, 9), divergent=False, capacity=6, count=1):
    data = bytearray(524288)
    for index, base in enumerate((0, 0x40000)):
        struct.pack_into('<II', data, base + 0x90, capacity, count)
        data[base + 0x98:base + 0x98 + 236] = pokemon()
        data[base + 0x78] = index if divergent else 0
        footer = base + 0xf7cc - 16
        struct.pack_into('<IIIHH', data, footer, counters[index], 0xf7cc, 0x20060623, 0,
                         binascii.crc_hqx(data[base:footer], 0xffff))
    return bytes(data)


class Bridge:
    def __enter__(self):
        self.process = subprocess.Popen(['node', str(Path(__file__).with_suffix('.mjs'))],
                                        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=True)
        return self

    def call(self, op, data, **fields):
        request = dict(op=op, bytes=base64.b64encode(data).decode(), **fields)
        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Research Node adapter exited without a response')
        return json.loads(line)

    def __exit__(self, *args):
        self.process.stdin.close()
        self.process.stdout.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if not args[0] and self.process.returncode:
            raise RuntimeError(f'Research adapter exit: {self.process.returncode}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saves', type=Path, help='Optional existing local directory, read-only')
    args = parser.parse_args()
    findings = {}
    with tempfile.TemporaryDirectory(prefix='save-core-probe-') as temp, Bridge() as bridge:
        path = Path(temp) / 'synthetic.sav'

        def loaded(data):
            path.write_bytes(data)
            return E.SaveFile(path)

        moves = [dict(id=i, pp=20 + n, ppUps=[1, 2, 3, 0][n]) for n, i in enumerate([85, 86, 87, 98])]
        for selector in range(32):
            raw = pokemon(selector)
            py = E.decode_party_pokemon(raw)
            ts = bridge.call('pokemon', raw)
            assert ts['ok'] and py['checksum_ok']
            assert (py['species'], py['form'], py['level']) == (201, 5, 15)
            assert (ts['result']['speciesId'], ts['result']['form'], ts['result']['party']['level']) == (201, 5, 15)
            py_edit = E.encode_pokemon(raw, moves=[m['id'] for m in moves], pp=[m['pp'] for m in moves])
            ts_edit = bridge.call('moves', raw, moves=moves)
            assert ts_edit['ok'] and base64.b64decode(ts_edit['result']['bytes']) == py_edit
        findings['all_shuffle_selectors'] = '32/32 decode and complete move-edit bytes agree'

        cases = {
            'ordinary': save(),
            'equal_identical': save((10, 10)),
            'equal_divergent': save((10, 10), divergent=True),
            'rollover': save((0xffffffff, 0)),
            'invalid_party_capacity': save(capacity=0),
            'invalid_party_count': save(count=7),
        }
        findings['save_selection'] = {}
        for name, data in cases.items():
            sf = loaded(data)
            findings['save_selection'][name] = {'python_base': hex(sf.base), 'typescript': bridge.call('save', data)}
        assert not findings['save_selection']['equal_divergent']['typescript']['ok']
        assert not findings['save_selection']['rollover']['typescript']['ok']

        corrupt = bytearray(pokemon())
        corrupt[8] ^= 1
        repaired = E.encode_pokemon(corrupt, item=8)
        findings['corrupt_pokemon'] = {
            'python_before_checksum_ok': E.decode_pokemon(corrupt)['checksum_ok'],
            'python_after_checksum_ok': E.decode_pokemon(repaired)['checksum_ok'],
            'typescript': bridge.call('moves', corrupt, moves=moves),
        }
        assert not findings['corrupt_pokemon']['python_before_checksum_ok']
        assert findings['corrupt_pokemon']['python_after_checksum_ok']
        assert not findings['corrupt_pokemon']['typescript']['ok']

        partial = E.encode_pokemon(pokemon(), moves=[85])
        findings['partial_moves'] = bridge.call('pokemon', partial)['result']['moves']
        assert [m['id'] for m in findings['partial_moves']] == [85, 44, 55, 66]

        import emu_calendar
        raw = pokemon(nature_override=24)
        findings['calendar_nature_override'] = {
            'python': emu_calendar.full_mon(raw)['nature'],
            'typescript': bridge.call('pokemon', raw)['result']['nature'],
        }
        assert findings['calendar_nature_override'] == {'python': 12, 'typescript': 24}

        findings['unbounded_mutations'] = {}
        for name, action in [
            ('flag_negative', lambda sf: sf.set_flag(-1)),
            ('flag_crosses_into_location', lambda sf: sf.set_flag(0xcc0)),
            ('var_before_array', lambda sf: sf.set_var(0x3fff, 1)),
            ('var_crosses_into_flags', lambda sf: sf.set_var(0x4170, 1)),
            ('party_slot_six', lambda sf: sf.edit_party_mon(6, species=201)),
        ]:
            sf = loaded(save())
            before = bytes(sf.data)
            action(sf)
            changed = [hex(i) for i, (a, b) in enumerate(zip(before, sf.data)) if a != b]
            assert changed
            findings['unbounded_mutations'][name] = {'accepted': True, 'first_offsets': changed[:6], 'changed_bytes': len(changed)}

        sf = loaded(save())
        sf.set_party_count(6)
        findings['party_count_increase'] = {'count': len(sf.party()), 'last_checksum_ok': sf.party()[-1]['checksum_ok']}
        assert not findings['party_count_increase']['last_checksum_ok']

        sf = loaded(save())
        sf.set_pocket('medicine', [(50, 99)])
        before = bytes(sf.data)
        try:
            sf.set_pocket('medicine', [(51, 2), (52, -1)])
        except struct.error as error:
            findings['pocket_failure'] = {'error': str(error), 'mutated_on_failure': bytes(sf.data) != before,
                                          'pocket_after': sf.pocket('medicine')}
        assert findings['pocket_failure']['mutated_on_failure']

        findings['typescript_unchecked_record_patch'] = bridge.call('patch-invalid', save())
        assert findings['typescript_unchecked_record_patch']['result']['recordError']
        findings['node_container_boundary'] = bridge.call('containers', save())
        assert findings['node_container_boundary']['result']['aliasesInput']
        assert findings['node_container_boundary']['result']['validUint8'] == 'desmume'
        assert findings['node_container_boundary']['result']['bufferDsv'] != 'desmume'

        elapsed = []
        for _ in range(100):
            begin = time.perf_counter()
            assert bridge.call('pokemon', pokemon())['ok']
            elapsed.append((time.perf_counter() - begin) * 1000)
        findings['bridge_record_roundtrip_ms'] = {'samples': len(elapsed), 'median': round(statistics.median(elapsed), 3),
                                                 'max': round(max(elapsed), 3)}

        save_elapsed = []
        data = save()
        for _ in range(20):
            begin = time.perf_counter()
            assert bridge.call('save', data)['ok']
            save_elapsed.append((time.perf_counter() - begin) * 1000)
        findings['bridge_full_save_inspection_ms'] = {
            'samples': len(save_elapsed), 'median': round(statistics.median(save_elapsed), 3),
            'max': round(max(save_elapsed), 3),
        }

        if args.saves:
            parity = []
            for file in sorted(args.saves.glob('*.sav')):
                original = file.read_bytes()
                digest = hashlib.sha256(original).hexdigest()
                sf = E.SaveFile(file)
                ts = bridge.call('save', original)
                assert ts['ok'] and ts['result']['base'] == sf.base
                count = 0
                for slot, py in enumerate(sf.party()):
                    start = sf.base + 0x98 + slot * 236
                    result = bridge.call('pokemon', original[start:start + 236])
                    assert result['ok']
                    mon = result['result']
                    assert py['checksum_ok'] and (py['pid'], py['species'], py['form'], py['level']) == (
                        mon['pid'], mon['speciesId'], mon['form'], mon['party']['level'])
                    count += 1
                assert hashlib.sha256(file.read_bytes()).hexdigest() == digest
                parity.append({'file': file.name, 'sha256': digest, 'records': count, 'unchanged': True})
            findings['local_read_only_parity'] = parity
    cold_elapsed = []
    for _ in range(10):
        begin = time.perf_counter()
        with Bridge() as bridge:
            assert bridge.call('pokemon', pokemon())['ok']
        cold_elapsed.append((time.perf_counter() - begin) * 1000)
    findings['bridge_cold_process_ms'] = {'samples': len(cold_elapsed), 'median': round(statistics.median(cold_elapsed), 3),
                                        'max': round(max(cold_elapsed), 3)}
    print(json.dumps(findings, indent=2))


if __name__ == '__main__':
    main()
