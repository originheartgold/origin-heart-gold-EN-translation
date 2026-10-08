"""Tests for emu_reflection.py (the following-Pokemon reflection reproducer) and its tie to the fix
work/patches/bulbasaur-reflection-boundary. No emulator is started."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emu_reflection as R  # noqa: E402

FIX_ID = 'bulbasaur-reflection-boundary'
FIX_DIR = Path(__file__).resolve().parent.parent / 'patches' / FIX_ID
ROM_CN = Path(__file__).resolve().parent.parent / 'rom' / 'origin_v4.0.3_cn.nds'
OBJ = 0x022A2E08
GFX = 0x0233AAEC


class FakeMachine:
    """Just enough of the harness for Trace: registers, a frame counter and the words Trace reads."""
    def __init__(self, sprite, branch=R.BRANCH_ORIGINAL):
        self.frame = 10
        self.reg = SimpleNamespace(r0=0, lr=0)
        self.mem = {OBJ + 0x10: sprite, OBJ + 0x108: GFX, OBJ + 0x10C: 0}
        self.branch = branch
        self.hooks = {}

    def read(self, addr, n):
        if addr == R.RESOLVER:
            return R.RESOLVER_ORIGINAL[:n]
        if addr == R.BRANCH:
            return self.branch
        raise AssertionError(hex(addr))

    def u32(self, addr):
        return self.mem[addr]

    def on_exec(self, addr, fn):
        self.hooks[addr] = fn


def chain(trace, h, field, site=R.REFLECTION_RETURNS[0]):
    """One native call chain: resolver entry, pointer load, return, both getters, their assertions."""
    h.reg.r0, h.reg.lr = OBJ, site | 1
    trace.entry(h)
    h.reg.r0 = OBJ + R.FOLLOWER_FIELD
    trace.load(h, field - R.FOLLOWER_FIELD)
    result = h.mem[OBJ + field]
    h.reg.r0 = result
    trace.ret(h, site)
    for getter in (R.GETTER_HALF, R.GETTER_WORD):
        h.reg.r0, h.reg.lr = result, (site + R.GETTER_CALLER_DELTA[getter]) | 1
        trace.getter(h, getter)
        if result == 0:
            h.reg.lr = R.GETTER_ASSERT_LR[getter]
            trace.assertion(h)


def moves_ok():
    scene = R.SCENES['viridian']
    return [{'direction': d, 'position': [scene['map'], x, y], 'expected': [scene['map'], x, y]}
            for d, (x, y) in scene['steps']]


class OracleTests(unittest.TestCase):
    def traced(self, sprite, field, n=3, branch=R.BRANCH_ORIGINAL):
        h = FakeMachine(sprite, branch)
        trace = R.Trace(sprite)
        trace.active = True
        for _ in range(n):
            chain(trace, h, field)
            h.frame += 1
        return trace.report()

    def test_original_bulbasaur_chain_is_the_defect(self):
        rep = self.traced(428, 0x10C)
        self.assertEqual(rep['counts']['null_return'], 3)
        self.assertEqual(rep['counts']['assertion'], 6)
        self.assertEqual(R.failures('bulbasaur', 'original', rep, moves_ok(), '07dd'), [])
        self.assertTrue(R.failures('bulbasaur', 'fixed', rep, moves_ok(), '07dd'))

    def test_healthy_chain_passes_only_where_expected(self):
        fixed = self.traced(428, 0x108, branch=R.BRANCH_FIXED)
        self.assertEqual(R.failures('bulbasaur', 'fixed', fixed, moves_ok(), '07db'), [])
        self.assertTrue(R.failures('bulbasaur', 'original', fixed, moves_ok(), '07dd'))
        other = self.traced(432, 0x108)
        self.assertEqual(R.failures('charmander', 'original', other, moves_ok(), '07dd'), [])

    def test_no_vacuous_success(self):
        empty = R.Trace(428).report()
        for expect, branch in (('original', '07dd'), ('fixed', '07db')):
            self.assertTrue(R.failures('bulbasaur', expect, empty, moves_ok(), branch))
            self.assertTrue(R.failures('onix', expect, empty, moves_ok(), branch))

    def test_wrong_branch_movement_or_hook_error_fails(self):
        rep = self.traced(432, 0x108)
        self.assertTrue(R.failures('charmander', 'fixed', rep, moves_ok(), '07dd'))
        bad = moves_ok()
        bad[1]['position'] = [50, 0, 0]
        self.assertTrue(R.failures('charmander', 'original', rep, bad, '07dd'))
        self.assertTrue(R.failures('charmander', 'original', dict(rep, hook_errors=['x']), moves_ok(), '07dd'))

    def test_other_sprites_callers_and_unrelated_assertions_ignored(self):
        h = FakeMachine(428)
        trace = R.Trace(432)              # following Charmander: Bulbasaur's object is not traced
        trace.active = True
        chain(trace, h, 0x10C)
        self.assertNotIn('reflection_return', trace.counts)
        trace = R.Trace(428)
        trace.active = True
        h.reg.r0, h.reg.lr = OBJ, 0x021F9989   # another resolver caller (it checks NULL itself)
        trace.entry(h)
        self.assertIsNone(trace.current)
        h.reg.lr = 0x0200B1BD                  # an unrelated assertion
        trace.assertion(h)
        self.assertNotIn('assertion', trace.counts)

    def test_samples_bounded(self):
        rep = self.traced(428, 0x10C, n=50)
        self.assertEqual(rep['counts']['null_return'], 50)
        self.assertLessEqual(sum(s['event'] == 'null_return' for s in rep['samples']), R.SAMPLE_LIMIT)

    def test_cases(self):
        self.assertEqual(R.parse_cases('all'), list(R.CASES))
        for text in ('', 'nope', 'onix,onix'):
            with self.assertRaises(argparse.ArgumentTypeError):
                R.parse_cases(text)
        self.assertEqual(R.CASES['bulbasaur']['sprite'], 428)
        self.assertEqual(R.parse_scenes('all'), list(R.SCENES))
        with self.assertRaises(argparse.ArgumentTypeError):
            R.parse_scenes('nowhere')


class RunTests(unittest.TestCase):
    def test_refuses_existing_report_and_unknown_rom(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rom, sav = root / 'in.nds', root / 'in.sav'
            rom.write_bytes(b'not a rom')
            sav.write_bytes(b'save')
            args = SimpleNamespace(rom=str(rom), sav=str(sav), out=str(root / 'ev'), case='all', expect='fixed')
            with patch('builtins.print'):
                result = R.run(args, harness_factory=lambda *a, **k: self.fail('must not boot'))
            self.assertEqual(result, 1)
            report = json.loads((root / 'ev' / 'report.json').read_text())
            self.assertIn('error', report)
            self.assertTrue(report['inputs_unchanged'])
            with self.assertRaises(ValueError):
                R.run(args)


class AgainstTheFix(unittest.TestCase):
    """The harness's idea of the routine is the fix's: its [[code]] region and its asm guards."""

    def test_fix_region_is_the_lower_bound(self):
        import fixes as F
        fix = next(f for f in F.load_all() if f['id'] == FIX_ID)
        (region,) = fix['code']
        self.assertEqual((region['file'], int(region['offset'], 16)), ('overlay1', R.BRANCH - R.OV1_BASE))
        self.assertEqual(struct.pack('<H', int(region['expect'], 16)), R.BRANCH_ORIGINAL)
        self.assertEqual(R.resolver_bytes('fixed')[R.BRANCH - R.RESOLVER + 1], 0xDB)

    def test_asm_guards_are_the_resolver(self):
        asm = (FIX_DIR / f'{FIX_ID}.asm').read_text(encoding='utf-8')
        labels = dict(re.findall(r'^\.definelabel\s+(\w+),\s*(0x[0-9A-F]+)', asm, re.M | re.I))
        checked = 0
        for block in re.split(r'^\.org\s+', asm, flags=re.M)[1:]:
            name = block.split()[0]
            base = int(labels[name], 16)
            for kind, off, val in re.findall(r'^\s*expect(16|32)_at\s+(0x[0-9A-F]+),\s*(0x[0-9A-F]+)', block,
                                             re.M | re.I):
                size = int(kind) // 8
                at = base + int(off, 16) - R.RESOLVER
                self.assertEqual(R.RESOLVER_ORIGINAL[at:at + size], int(val, 16).to_bytes(size, 'little'),
                                 f'{name}+{off}')
                checked += size
        self.assertGreater(checked, 120)

    @unittest.skipUnless(ROM_CN.exists(), 'Chinese ROM not present')
    def test_resolver_is_the_chinese_roms(self):
        R.validate_rom(ROM_CN, 'original')
        with self.assertRaises(ValueError):
            R.validate_rom(ROM_CN, 'fixed')

    def test_assembled_fix_changes_one_byte(self):
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
        before = hc.RomView(rom).get('overlay1')
        A.apply(rom, [f for f in F.load_all() if f['id'] == FIX_ID], armips)
        after = hc.RomView(rom).get('overlay1')
        start = R.RESOLVER - R.OV1_BASE
        self.assertEqual(after[start:start + len(R.RESOLVER_ORIGINAL)], R.resolver_bytes('fixed'))
        self.assertEqual([i for i in range(len(before)) if before[i] != after[i]], [R.BRANCH - R.OV1_BASE + 1])


if __name__ == '__main__':
    unittest.main()
