import argparse
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emu_texture_bounds as E  # noqa: E402
from emu_texture_bounds import (ARM9_BASE, BOUNDS, CASES, LOAD, ROUTINE, Trace, failures,  # noqa: E402
                                parse_cases, routine_bytes, run)

FIX_ID = 'overworld-texture-frame-bounds'
FIX_DIR = Path(__file__).resolve().parent.parent / 'patches' / FIX_ID
ROM_CN = Path(__file__).resolve().parent.parent / 'rom' / 'origin_v4.0.3_cn.nds'


def rom_fixture(expect='original'):
    data = bytearray(0x400 + 0x25000)
    struct.pack_into('<4I', data, 0x20, 0x400, ARM9_BASE, ARM9_BASE, 0x25000)
    start = 0x400 + ROUTINE - ARM9_BASE
    routine = routine_bytes(expect)
    data[start:start + len(routine)] = routine
    return bytes(data)


class FakeHarness:
    last = None
    fail_warp = False
    def __init__(self, rom, sav, out):
        type(self).last = self
        self.closed = False
        self.restores = 0
        self.out = out
        self.hooks = {}
        self.loc = dict(map=247, x=13, y=4)
        self.frame = 0
        self.fixed = rom.read_bytes()[0x400 + BOUNDS - ARM9_BASE] == 0x2c
        self.reg = SimpleNamespace(**{f'r{i}': 0 for i in range(7)})
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def boot_to_menu(self): pass
    def continue_game(self): pass
    def save_state(self, path): path.write_bytes(b'baseline')
    def load_state(self, path): self.restores += 1
    def get_flag(self, flag): return False
    def set_flag(self, flag, value): pass
    def warp(self, m, x, y, d):
        if self.fail_warp: raise RuntimeError('warp failed')
        self.loc = dict(map=m, x=x, y=y)
    def location(self): return self.loc.copy()
    def read(self, addr, n): return bytes.fromhex('2cd2' if self.fixed else '08d2')
    def on_exec(self, addr, callback): self.hooks[addr] = callback
    def step(self, frames):
        self.frame += frames
        case = next(c for c in CASES.values() if c['map'] == self.loc['map'])
        self.reg.r2, self.reg.r3 = 0, 1
        self.hooks[BOUNDS](self)
        self.reg.r2 = case['index']
        self.hooks[BOUNDS](self)
        if not self.fixed: self.hooks[LOAD](self)
    def screenshot(self, name): return self.out / (name + '.png')


class ReproducerTests(unittest.TestCase):
    def test_cases_reject_unknown_duplicate_and_empty(self):
        self.assertEqual(parse_cases('all'), list(CASES))
        for text in ('', 'nope', 'five_island,five_island', 'all,five_island'):
            with self.assertRaises(argparse.ArgumentTypeError): parse_cases(text)

    def test_no_vacuous_success_and_wrong_map_rejected(self):
        c = CASES['five_island']; loc = dict(map=154, x=104, y=54)
        empty = Trace(154).report()
        self.assertGreaterEqual(len(failures(c, 'fixed', loc, loc, empty, '2cd2')), 2)
        good = dict(empty, valid_updates=1, invalid_requests=1,
                    index_counts=[dict(index=4, count=1, requests=1)])
        self.assertFalse(failures(c, 'fixed', loc, loc, good, '2cd2'))
        self.assertTrue(failures(c, 'original', loc, loc, good, '08d2'))
        self.assertTrue(failures(c, 'fixed', loc, dict(map=247), good, '2cd2'))
        self.assertTrue(failures(c, 'fixed', loc, loc, dict(good, null_loads=1), '2cd2'))
        self.assertTrue(failures(c, 'fixed', loc, loc, good, '08d2'))

    def test_trace_is_map_filtered_and_bounded(self):
        h = SimpleNamespace(location=lambda: dict(map=247), frame=1,
                            reg=SimpleNamespace(**{f'r{i}': (4 if i == 2 else 1) for i in range(7)}))
        trace = Trace(154)
        trace.observe(h, 'bounds')
        self.assertEqual(trace.invalid, 0)
        self.assertEqual(trace.wrong_map, 1)
        h.location = lambda: dict(map=154)
        for _ in range(100): trace.observe(h, 'bounds')
        self.assertEqual(trace.invalid, 100)
        self.assertLessEqual(len(trace.samples), 12)

    def run_fake(self, root, fixed=False):
        rom, sav = root / 'input.nds', root / 'input.sav'
        rom.write_bytes(rom_fixture('fixed' if fixed else 'original'))
        sav.write_bytes(b'untouched-save')
        args = SimpleNamespace(rom=str(rom), sav=str(sav), out=str(root/'evidence'),
                               case='all', expect='fixed' if fixed else 'original')
        with patch('builtins.print'):
            result = run(args, harness_factory=FakeHarness)
        return result, json.loads((root/'evidence/report.json').read_text())

    def test_each_case_restored_and_original_fixed_observed(self):
        for fixed in (False, True):
            with self.subTest(fixed=fixed), tempfile.TemporaryDirectory() as directory:
                result, report = self.run_fake(Path(directory), fixed)
                self.assertEqual(result, 0)
                self.assertEqual(len(report['cases']), 4)
                self.assertTrue(report['inputs_unchanged'])
                self.assertEqual(FakeHarness.last.restores, 4)
                self.assertTrue(FakeHarness.last.closed)
                self.assertTrue(all(v is None for v in FakeHarness.last.hooks.values()))
                self.assertTrue(all(r['trace']['invalid_requests'] == 1 for r in report['cases']))

    def test_failure_writes_nonpassing_report_and_closes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(FakeHarness, 'fail_warp', True):
            result, report = self.run_fake(Path(directory))
            self.assertEqual(result, 1)
            self.assertIn('warp failed', report['cases'][0]['failures'][0])
            self.assertTrue(FakeHarness.last.closed)

    def test_unknown_signature_rejected_before_emulation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rom = root/'input.nds'; sav = root/'input.sav'
            rom.write_bytes(b'wrong'); sav.write_bytes(b'untouched')
            args = SimpleNamespace(rom=str(rom), sav=str(sav), out=str(root/'evidence'), case='all', expect='fixed')
            with patch('builtins.print'):
                result = run(args, harness_factory=lambda *a, **kw: self.fail('must not boot'))
            self.assertEqual(result, 1)
            self.assertIn('truncated', json.loads((root/'evidence/report.json').read_text())['error'])

    def test_changed_routine_rejected_before_emulation(self):
        """A ROM whose routine differs anywhere (here: the return) is refused, and the original is not
        accepted as fixed."""
        for data, expect in ((rom_fixture('fixed'), 'original'), (rom_fixture('original'), 'fixed')):
            with self.subTest(expect=expect), tempfile.TemporaryDirectory() as directory:
                rom = Path(directory) / 'input.nds'
                rom.write_bytes(data)
                with self.assertRaises(ValueError):
                    E.validate_rom(rom, expect)
        with tempfile.TemporaryDirectory() as directory:
            data = bytearray(rom_fixture('fixed'))
            data[0x400 + E.EPILOGUE - ARM9_BASE] ^= 1
            rom = Path(directory) / 'input.nds'
            rom.write_bytes(bytes(data))
            with self.assertRaises(ValueError):
                E.validate_rom(rom, 'fixed')


class AgainstTheFix(unittest.TestCase):
    """The harness's idea of the routine is the fix's: its [[code]] region and its asm guards."""

    def test_fix_region_is_the_bounds_branch(self):
        import fixes as F
        fix = next(f for f in F.load_all() if f['id'] == FIX_ID)
        (region,) = fix['code']
        self.assertEqual((region['file'], int(region['offset'], 16)), ('arm9', BOUNDS - ARM9_BASE))
        self.assertEqual(struct.pack('<H', int(region['expect'], 16)), E.BRANCH_ORIGINAL)

    def test_asm_guards_are_the_routine(self):
        asm = (FIX_DIR / f'{FIX_ID}.asm').read_text(encoding='utf-8')
        guards = re.findall(r'^\s*expect16_at\s+(0x[0-9A-F]+),\s*(0x[0-9A-F]+)', asm, re.M | re.I)
        data = b''.join(struct.pack('<H', int(v, 16)) for _, v in guards)
        self.assertEqual([int(o, 16) for o, _ in guards], list(range(0, len(E.ROUTINE_ORIGINAL), 2)))
        self.assertEqual(data, E.ROUTINE_ORIGINAL)
        self.assertEqual(E.BRANCH_FIXED, struct.pack('<H', 0xD200 | ((E.EPILOGUE - BOUNDS - 4) // 2)))

    @unittest.skipUnless(ROM_CN.exists(), 'Chinese ROM not present')
    def test_routine_is_the_chinese_roms(self):
        import ndspy.rom
        arm9 = ndspy.rom.NintendoDSRom.fromFile(str(ROM_CN)).loadArm9().save(compress=False)
        start = ROUTINE - ARM9_BASE
        self.assertEqual(arm9[start:start + len(E.ROUTINE_ORIGINAL)], E.ROUTINE_ORIGINAL)

    def test_assembled_fix_is_the_fixed_routine(self):
        import asmpatch as A
        import fixes as F
        try:
            armips = A.find_armips()
            A.check_armips(armips)
        except A.AsmError:
            self.skipTest('armips not found')
        if not ROM_CN.exists():
            self.skipTest('Chinese ROM not present')
        import hardcoded as hc
        import msgtool as m
        rom = m.load_rom(ROM_CN)
        before = hc.RomView(rom).get('arm9')
        A.apply(rom, [f for f in F.load_all() if f['id'] == FIX_ID], armips)
        after = hc.RomView(rom).get('arm9')
        start = ROUTINE - ARM9_BASE
        self.assertEqual(after[start:start + len(E.ROUTINE_ORIGINAL)], routine_bytes('fixed'))
        self.assertEqual([i for i in range(len(before)) if before[i] != after[i]], [BOUNDS - ARM9_BASE])


if __name__ == '__main__': unittest.main()
