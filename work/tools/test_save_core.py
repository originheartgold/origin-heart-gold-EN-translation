"""Regression tests for the Python boundary; no ROM, emulator or downloads."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import emu_harness as E
import save_core as C
import test_emu_harness as H
from test_emu_harness import _encrypted_mon


class Transport(unittest.TestCase):
    def worker(self, code, timeout=1):
        worker = C.Worker([sys.executable, '-u', '-c', code], timeout=timeout)
        self.addCleanup(worker.close)
        return worker

    def test_worker_reused_and_concurrent_calls_serialized(self):
        worker = self.worker('''import sys,json,os
for line in sys.stdin:
 r=json.loads(line); print(json.dumps(dict(version=1,id=r['id'],result=os.getpid())),flush=True)
''')
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: worker.request('pid'), range(30)))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(worker._id, 30)

    def test_deadline_includes_blocked_request_write(self):
        worker = self.worker('import time; time.sleep(10)', timeout=.05)
        with self.assertRaisesRegex(C.WorkerError, 'timed out'):
            worker.request('large', bytes(524288))
        self.assertIsNone(worker._proc)

    def test_crash_is_not_replayed_and_next_call_restarts(self):
        worker = self.worker('import sys; sys.stdin.readline(); sys.exit(7)')
        for attempt in range(2):
            with self.assertRaisesRegex(C.WorkerError, 'exited'):
                worker.request('crash')
            self.assertEqual(worker._id, attempt + 1)
            self.assertIsNone(worker._proc)

    def test_malformed_responses_discard_worker(self):
        packets = ['not JSON', '{"version":2,"id":1,"result":null}',
                   '{"version":1,"id":7,"result":null}',
                   '{"version":1,"id":1}', '{"version":1,"id":1,"error":null}',
                   '{"version":1,"id":1,"result":null}\n{}']
        for packet in packets:
            with self.subTest(packet=packet):
                worker = self.worker('import sys; sys.stdin.readline(); print(' + repr(packet) + ',flush=True)')
                with self.assertRaises(C.WorkerError):
                    worker.request('bad')
                self.assertIsNone(worker._proc)

    def test_truncated_response_and_output_flood(self):
        for code in ['import sys; sys.stdin.readline(); sys.stdout.write("{}")',
                     'import sys; sys.stdin.readline(); sys.stdout.write("x"*5000000); sys.stdout.flush()']:
            worker = self.worker(code)
            with self.assertRaises(C.WorkerError):
                worker.request('bad')
            self.assertIsNone(worker._proc)

    def test_structured_errors_keep_worker_usable(self):
        worker = self.worker('''import sys,json
for line in sys.stdin:
 r=json.loads(line); print(json.dumps(dict(version=1,id=r['id'],error=dict(code='invalid-input',message='no',operationIndex=2))),flush=True)
''')
        for _ in range(2):
            with self.assertRaises(C.CoreError) as error:
                worker.request('bad')
            self.assertEqual(error.exception.code, 'invalid-input')
            self.assertEqual(error.exception.operation_index, 2)
            self.assertIsNone(worker._proc.poll())

    def test_missing_worker_or_node_does_not_build(self):
        worker = C.Worker()
        self.addCleanup(worker.close)
        with patch.object(C.shutil, 'which', return_value=None), patch.object(C.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(C.WorkerError, 'Node.js'):
                worker.request('x')
            spawn.assert_not_called()
        with patch.object(C, 'WORKER', Path('/nonexistent/core/worker.mjs')), patch.object(C.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(C.WorkerError, 'not built'):
                worker.request('x')
            spawn.assert_not_called()

    def test_missing_compiled_core_does_not_start_a_build(self):
        worker = C.Worker()
        self.addCleanup(worker.close)
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / 'cli'
            cli.mkdir()
            script = cli / 'worker.mjs'
            script.write_text('// build absent')
            with patch.object(C, 'WORKER', script), patch.object(C.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(C.WorkerError, 'not built'):
                    worker.request('x')
                spawn.assert_not_called()

    def test_missing_or_invalid_build_manifest_never_starts_a_worker(self):
        worker = C.Worker()
        self.addCleanup(worker.close)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cli').mkdir()
            (root / 'dist').mkdir()
            script = root / 'cli' / 'worker.mjs'
            script.write_text('// build absent')
            (root / 'dist' / 'fixture.js').write_text('// compiled')
            manifests = [None, '{', 'null', '{}', json.dumps(dict(schema=1, protocol=2, buildId='a' * 64)),
                         json.dumps(dict(schema=True, protocol=1, buildId='a' * 64)),
                         json.dumps(dict(schema=1, protocol=1, buildId='Z' * 64))]
            for manifest in manifests:
                with self.subTest(manifest=manifest):
                    if manifest is not None:
                        (root / 'dist' / 'build-identity.json').write_text(manifest)
                    with patch.object(C, 'WORKER', script), patch.object(C.subprocess, 'Popen') as spawn:
                        with self.assertRaisesRegex(C.WorkerError, 'build identity'):
                            worker.request('x')
                        spawn.assert_not_called()

    def test_handshake_precedes_first_operation_and_only_runs_once_per_process(self):
        worker = self.worker('''import sys,json
for line in sys.stdin:
 r=json.loads(line)
 result=dict(schema=1,protocol=1,buildId='a'*64) if r['op']=='handshake' else r['id']
 print(json.dumps(dict(version=1,id=r['id'],result=result)),flush=True)
''')
        worker.expected_build = 'a' * 64
        self.assertEqual(worker.request('first'), 2)
        self.assertEqual(worker.request('second'), 3)
        worker.close()
        self.assertEqual(worker.request('after_restart'), 5)

    def test_failed_handshakes_never_send_requested_operation(self):
        for identity in [None, {}, dict(schema=1, protocol=2, buildId='a' * 64),
                         dict(schema=True, protocol=1, buildId='a' * 64),
                         dict(schema=1, protocol=True, buildId='a' * 64),
                         dict(schema=1, protocol=1, buildId='b' * 64)]:
            with self.subTest(identity=identity):
                worker = self.worker('import sys,json; r=json.loads(sys.stdin.readline()); print(json.dumps(dict(version=1,id=r["id"],result=' + repr(identity) + ')),flush=True)')
                worker.expected_build = 'a' * 64
                with self.assertRaisesRegex(C.WorkerError, 'handshake mismatch'):
                    worker.request('must_not_execute')
                self.assertEqual(worker._id, 1)
                self.assertIsNone(worker._proc)

    def test_handshake_timeout_and_old_worker_error_close_worker(self):
        for code in ['import time; time.sleep(10)', '''import sys,json
r=json.loads(sys.stdin.readline()); print(json.dumps(dict(version=1,id=r['id'],error=dict(code='invalid-input',message='Unknown operation'))),flush=True)
''']:
            worker = self.worker(code, timeout=.1)
            worker.expected_build = 'a' * 64
            with self.assertRaisesRegex(C.WorkerError, 'startup failed'):
                worker.request('must_not_execute')
            self.assertEqual(worker._id, 1)
            self.assertIsNone(worker._proc)

    def test_close_reaps_process_and_is_idempotent(self):
        worker = self.worker("import sys,json\nfor line in sys.stdin:\n r=json.loads(line); print(json.dumps(dict(version=1,id=r['id'],result=True)),flush=True)")
        self.assertTrue(worker.request('x'))
        process = worker._proc
        worker.close()
        self.assertIsNotNone(process.returncode)
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        worker.close()
        self.assertIsNone(worker._proc)

    def test_cast_memoryview_byte_count_checked_before_start(self):
        from array import array
        worker = C.Worker()
        self.addCleanup(worker.close)
        raw = memoryview(array('Q', [0] * 100000))
        self.assertEqual(len(raw), 100000)
        self.assertEqual(raw.nbytes, 800000)
        with self.assertRaisesRegex(ValueError, 'too large'):
            worker.request('x', raw)
        self.assertIsNone(worker._proc)

    def test_bounded_input_and_nonbytes_rejected(self):
        worker = C.Worker()
        self.addCleanup(worker.close)
        for bad in ('text', [1, 2, 3]):
            with self.assertRaises(TypeError):
                worker.request('x', bad)
        with self.assertRaises(ValueError):
            worker.request('x', bytes(1024 * 1024 + 1))
        self.assertIsNone(worker._proc)

    @unittest.skipUnless(hasattr(os, 'fork'), 'POSIX process ownership')
    def test_fork_child_owns_separate_worker(self):
        worker = self.worker('''import sys,json,os
for line in sys.stdin:
 r=json.loads(line); print(json.dumps(dict(version=1,id=r['id'],result=os.getpid())),flush=True)
''')
        parent_worker = worker.request('pid')
        reader, writer = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                os.close(reader)
                value = worker.request('pid')
                worker.close()
                os.write(writer, str(value).encode())
                os._exit(0)
            except BaseException:
                os._exit(1)
        os.close(writer)
        child_worker = int(os.read(reader, 30))
        os.close(reader)
        _, status = os.waitpid(child, 0)
        self.assertEqual(status, 0)
        self.assertNotEqual(parent_worker, child_worker)
        self.assertEqual(worker.request('pid'), parent_worker)

    @unittest.skipUnless(hasattr(os, 'fork'), 'POSIX process ownership')
    def test_fork_does_not_inherit_locked_transport(self):
        import select
        import signal
        worker = self.worker("import sys,json,os\nfor line in sys.stdin:\n r=json.loads(line); print(json.dumps(dict(version=1,id=r['id'],result=os.getpid())),flush=True)")
        worker.request('pid')
        reader, writer = os.pipe()
        worker._lock.acquire()
        child = os.fork()
        if child == 0:
            try:
                os.close(reader)
                worker.request('pid')
                worker.close()
                os.write(writer, b'ok')
                os._exit(0)
            except BaseException:
                os._exit(1)
        worker._lock.release()
        os.close(writer)
        try:
            ready, _, _ = select.select([reader], [], [], 3)
            if not ready:
                os.kill(child, signal.SIGKILL)
            _, status = os.waitpid(child, 0)
            self.assertTrue(ready, 'child inherited the parent transport lock')
            self.assertEqual(status, 0)
            self.assertEqual(os.read(reader, 2), b'ok')
        finally:
            os.close(reader)

    def test_timeout_restart_success_without_replaying_failed_request(self):
        worker = self.worker('import time; time.sleep(10)', timeout=.05)
        with self.assertRaises(C.WorkerError):
            worker.request('failed')
        worker.timeout = 1
        worker.command = [sys.executable, '-u', '-c', "import sys,json; r=json.loads(sys.stdin.readline()); print(json.dumps(dict(version=1,id=r['id'],result=r['op'])))"]
        self.assertEqual(worker.request('next'), 'next')
        self.assertEqual(worker._id, 2)


class SaveTransactions(unittest.TestCase):
    def setUp(self):
        self.path = H.SaveFileEdits()._save()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.path.parent))
        self.sf = E.SaveFile(self.path)

    def unchanged(self, method, *args):
        before = self.sf.data
        with self.assertRaises((ValueError, TypeError)):
            method(*args)
        self.assertEqual(self.sf.data, before)
        self.assertEqual(self.path.read_bytes(), before)

    def test_saved_flag_native_bounds_and_types(self):
        for flag in (-1, 0, 0xCA0, 0xCBF, 0xCC0, 0x4000, True, 1.5, '1', None):
            self.unchanged(self.sf.set_flag, flag)
        for value in (0, 1, 'yes', None):
            self.unchanged(self.sf.set_flag, 1, value)
        self.sf.set_flag(0xC9F)
        self.assertTrue(self.sf.get_flag(0xC9F))
        self.assertFalse(self.sf.get_flag(0))
        self.assertEqual(self.sf.data[self.sf.base + 0x1320:self.sf.base + 0x1324], bytes(4))

    def test_variable_bounds_and_types(self):
        for var in (0x3FFF, 0x4170, -1, True, 1.5):
            self.unchanged(self.sf.set_var, var, 7)
        for value in (-1, 65536, True, 1.5, '1'):
            self.unchanged(self.sf.set_var, 0x4000, value)
        for var in (0x4000, 0x416F):
            self.sf.set_var(var, 65535)
            self.assertEqual(self.sf.get_var(var), 65535)

    def test_bag_failure_rolls_back_and_keeps_order(self):
        self.sf.set_pocket('medicine', [(52, 2), (51, 3)])
        before = self.sf.data
        for bad in ([(50, 1), (51, -1)], [(0, 1)], [(1, True)], [(1, 1)] * 41):
            with self.assertRaises(ValueError):
                self.sf.set_pocket('medicine', bad)
            self.assertEqual(self.sf.data, before)
        self.assertEqual(self.sf.pocket('medicine'), [(52, 2), (51, 3)])

    def test_party_slot_and_activation_bounds(self):
        for slot in (-1, 1, 6, True, 1.5):
            self.unchanged(lambda s: self.sf.edit_party_mon(s, item=1), slot)
        for count in (0, 2, 6, 7, True, 1.5):
            self.unchanged(self.sf.set_party_count, count)
        self.sf.set_party_count(1)

    def test_multi_operation_failure_is_atomic(self):
        self.unchanged(self.sf.transaction, [dict(type='setVar', var=0x4000, value=123),
                                            dict(type='setFlag', flag=0xCA0, value=True)])
        self.assertEqual(self.sf.get_var(0x4000), 0)

    def test_noop_and_unrelated_regions_byte_exact(self):
        before = self.sf.data
        self.sf.transaction([])
        self.assertEqual(self.sf.data, before)
        self.sf.set_var(0x4000, 12)
        changed = {i for i, (a, b) in enumerate(zip(before, self.sf.data)) if a != b}
        self.assertLessEqual(changed, {self.sf.base + 0xEAC, self.sf.base + 0xEAD,
                                     self.sf.base + E.GENERAL_SIZE - 2, self.sf.base + E.GENERAL_SIZE - 1})
        self.assertIsInstance(self.sf.data, bytes)

    def test_party_results_never_alias_cached_inspection(self):
        import copy
        before = self.sf.party()
        inspection = copy.deepcopy(self.sf._inspect)
        data = self.sf.data
        returned = self.sf.party()[0]
        returned['party']['stats']['hp'] = 65535
        returned['party']['level'] = 100
        returned['pokerus']['raw'] = 255
        returned['nickname'][0] = 999
        returned['otName'][0] = 888
        returned['ot_name'][1] = 777
        returned['ivs'][0] = 31
        returned['evs'][0] = 252
        returned['moves'][0] = 999
        self.assertEqual(self.sf.party(), before)
        self.assertEqual(self.sf._inspect, inspection)
        self.assertEqual(self.sf.data, data)

    def test_output_refuses_seed_alias_overwrite_and_symlink(self):
        with self.assertRaises(ValueError):
            self.sf.write(self.path)
        out = self.path.with_name('output.sav')
        out.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            self.sf.write(out)
        self.assertEqual(out.read_bytes(), b'existing')
        alias = self.path.with_name('alias.sav')
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            self.sf.write(alias)

    def test_interrupted_write_leaves_no_destination_or_tempfile(self):
        out = self.path.with_name('output.sav')
        with patch.object(C.os, 'fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.sf.write(out)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_output_creation_race_keeps_other_writer(self):
        out = self.path.with_name('output.sav')
        real_link = os.link
        def racing_link(src, dst):
            Path(dst).write_bytes(b'racer')
            real_link(src, dst)
        with patch.object(C.os, 'link', side_effect=racing_link):
            with self.assertRaises(FileExistsError):
                self.sf.write(out)
        self.assertEqual(out.read_bytes(), b'racer')
        self.assertEqual(len(list(self.path.parent.iterdir())), 2)


class RecordBoundary(unittest.TestCase):
    def test_diagnostic_open_tail_matches_closed_tail(self):
        raw = _encrypted_mon(party=True)
        pid, _, checksum = struct.unpack_from('<IHH', raw)
        payload = struct.pack('<64H', *[word ^ key for word, key in zip(
            struct.unpack_from('<64H', raw, 8), H._prng_stream(checksum, 64))])
        tail = struct.pack('<50H', *[word ^ key for word, key in zip(
            struct.unpack_from('<50H', raw, 136), H._prng_stream(pid, 50))])
        expected = E.decode_party_pokemon(raw)
        for flags in (1, 2, 3):
            opened = struct.pack('<IHH', pid, flags, checksum) + (payload if flags & 2 else raw[8:136]) + (tail if flags & 1 else raw[136:])
            mon = E.decode_party_pokemon(opened)
            self.assertTrue(mon['checksum_ok'])
            for field in ('species', 'level', 'hp', 'stats', 'ivs', 'moves'):
                self.assertEqual(mon[field], expected[field])

    def test_recipe_effective_nature_override_and_nickname(self):
        import emu_fixes as fixes
        raw = _encrypted_mon(party=True)
        pid, _, checksum = struct.unpack_from('<IHH', raw)
        plain = bytearray(struct.pack('<64H', *[word ^ key for word, key in zip(
            struct.unpack_from('<64H', raw, 8), H._prng_stream(checksum, 64))]))
        order = H.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
        struct.pack_into('<I', plain, order.index('B') * 32 + 20, 25 << 25)
        struct.pack_into('<3H', plain, order.index('C') * 32, 123, 456, 65535)
        words = struct.unpack('<64H', plain)
        checksum = sum(words) & 65535
        changed = struct.pack('<IHH', pid, 0, checksum) + struct.pack('<64H', *[
            word ^ key for word, key in zip(words, H._prng_stream(checksum, 64))]) + raw[136:]
        self.assertEqual(E.decode_party_pokemon(changed)['nature'], 24)
        self.assertEqual(fixes.nickname(changed), [123, 456])

    def test_empty_slot_fixture_matches_independent_encryption(self):
        expected = bytes(8) + struct.pack('<64H', *H._prng_stream(0, 64)) + struct.pack('<50H', *H._prng_stream(0, 50))
        self.assertEqual(E._save_core.result_bytes(E._save_core.request('emptyPokemon')), expected)
        self.assertTrue(E.decode_pokemon(expected)['checksum_ok'])

    def test_hp_and_ot_recipe_mutations_preserve_other_fields(self):
        raw = _encrypted_mon(party=True)
        edited = E.encode_pokemon(raw, otId=0x12345678)
        self.assertEqual(E.decode_pokemon(edited)['ot_id'], 0x12345678)
        self.assertEqual(edited[136:], raw[136:])
        edited = E.encode_pokemon(edited, currentHp=0)
        self.assertEqual(E.decode_pokemon(edited)['hp'], 0)
        self.assertEqual(edited[:136], E.encode_pokemon(raw, otId=0x12345678)[:136])
        self.assertEqual(E.decode_pokemon(edited)['stats'], E.decode_pokemon(raw)['stats'])

    def test_friendship_and_status_fixture_fields(self):
        raw = _encrypted_mon(party=True)
        edited = E.encode_pokemon(raw, friendship=200, status=0x88)
        pid, _, checksum = struct.unpack_from('<IHH', edited)
        plain = struct.pack('<64H', *[w ^ k for w, k in zip(struct.unpack_from('<64H', edited, 8), H._prng_stream(checksum, 64))])
        a = H.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24].index('A') * 32
        self.assertEqual(plain[a + 0x0C], 200)
        tail = [w ^ k for w, k in zip(struct.unpack_from('<50H', edited, 136), H._prng_stream(pid, 50))]
        self.assertEqual(tail[0] | tail[1] << 16, 0x88)
        self.assertEqual(E.decode_pokemon(edited)['hp'], E.decode_pokemon(raw)['hp'])
        with self.assertRaises(ValueError):
            E.encode_pokemon(raw[:136], status=1)

    def test_native_stats_special_case_shedinja(self):
        values = E._save_core.request('calculateStats', base=[1, 90, 45, 40, 30, 30], level=50, ivs=[31] * 6,
                                      evs=[0] * 6, nature=0, species=292)
        self.assertEqual(values[0], 1)

    def test_live_invalid_party_counts_and_slots_do_not_write(self):
        from unittest.mock import Mock
        for count in (-1, 7, True):
            h = Mock()
            h.array.return_value = 0
            h.u32.side_effect = [6, count]
            with self.assertRaises(ValueError):
                E.Harness._party_count(h)
        for slot in (-1, 1, 6, True):
            h = Mock()
            h._party_count.return_value = 1
            with self.assertRaises(ValueError):
                E.Harness.edit_party_mon(h, slot, item=1)
            h.write.assert_not_called()

    def test_core_output_identity_is_reported(self):
        import hashlib
        raw = _encrypted_mon(party=True)
        result = C.request('patchPokemon', raw, changes={'item': 50}, tailPolicy='preserve')
        report = result['report']
        self.assertEqual(report['sourceSha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(report['outputSha256'], hashlib.sha256(C.result_bytes(result)).hexdigest())
        self.assertEqual(report['tailPolicy'], 'preserve')

    def test_invalid_records_rejected_and_diagnostic_read_does_not_repair(self):
        raw = bytearray(_encrypted_mon(party=True))
        raw[8] ^= 1
        self.assertFalse(E.decode_pokemon(raw)['checksum_ok'])
        before = bytes(raw)
        with self.assertRaises(ValueError):
            E.encode_pokemon(raw, item=50)
        self.assertEqual(bytes(raw), before)
        for length in (0, 8, 135, 137, 235, 237):
            with self.assertRaises(ValueError):
                E.encode_pokemon(bytes(length), item=50)

    def test_open_and_bad_egg_records_never_written(self):
        raw = _encrypted_mon(party=True)
        for flags in (1, 2, 3, 4, 8, 65535):
            value = bytearray(raw)
            struct.pack_into('<H', value, 4, flags)
            with self.assertRaises(ValueError):
                E.encode_pokemon(value, item=50)

    def test_partial_moves_and_exp_preserve_tail_and_other_slots(self):
        raw = E.encode_pokemon(_encrypted_mon(party=True), moves=[1, 2, 3, 4], pp=[10, 20, 30, 40])
        changed = E.encode_pokemon(raw, moves=[85], exp=999999)
        mon = E.decode_party_pokemon(changed)
        self.assertEqual(mon['moves'], [85, 2, 3, 4])
        self.assertEqual(mon['pp'], [10, 20, 30, 40])
        self.assertEqual(mon['exp'], 999999)
        self.assertEqual(changed[136:], raw[136:])
        self.assertEqual(E.encode_pokemon(changed), changed)

    def test_invalid_fixture_fields_rejected(self):
        raw = _encrypted_mon(party=True)
        for fields in ({'species': True}, {'form': 32}, {'item': -1}, {'ability': 65536},
                       {'moves': [1, 2, 3, 4, 5]}, {'moves': [1], 'pp': [300]},
                       {'exp': 2**32}, {'currentHp': -1}, {'unknown': 3}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                E.encode_pokemon(raw, **fields)

    def test_live_memory_validation_precedes_write(self):
        from unittest.mock import Mock
        for method, args in ((E.Harness.set_flag, (-1,)), (E.Harness.set_flag, (0xCA0,)),
                             (E.Harness.set_flag, (1, 1)), (E.Harness.set_var, (0x4170, 1)),
                             (E.Harness.set_var, (0x4000, 65536))):
            h = Mock()
            with self.assertRaises(ValueError):
                method(h, *args)
            h.write.assert_not_called()
            h.w8.assert_not_called()
            h.w16.assert_not_called()

    def test_live_save_array_pointer_and_index_are_bounded(self):
        from unittest.mock import Mock
        h = Mock()
        h.save = 0x02200000
        for index in (-1, 42, True, 1.5):
            with self.assertRaises(ValueError):
                E.Harness.array(h, index)
        for offset in (E.SAVE_TABLE - 0x10, 0xFFFFFFFF):
            h.u32.return_value = offset
            with self.assertRaises(RuntimeError):
                E.Harness.array(h, 2)
        h.u32.return_value = 0x90
        self.assertEqual(E.Harness.array(h, 2), 0x022000A0)
        for pointer in (0, 0x01FFFFFF, 0x023FFFF0):
            h.u32.return_value = pointer
            with self.assertRaises(RuntimeError):
                E.Harness.save.fget(h)

    def test_live_record_change_prevents_write(self):
        from unittest.mock import Mock
        h = Mock()
        h._party_count.return_value = 1
        h.array.return_value = 0
        h.read.side_effect = [_encrypted_mon(party=True), _encrypted_mon(seed=2, party=True)]
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            E.Harness.edit_party_mon(h, 0, item=50)
        h.write.assert_not_called()


class NativeGeneratorBoundary(unittest.TestCase):
    def harness(self, raw, requested_level=5):
        from unittest.mock import Mock
        h = Mock()
        h.array.return_value = 0x02200000
        h._party_count.return_value = 1
        h._find_generator.return_value = 0x02300000
        h.u32.side_effect = [requested_level, 1, 2]
        h.read.return_value = raw
        return h

    def test_valid_native_record_is_returned_without_a_record_write(self):
        raw = _encrypted_mon(species=1, party=True)
        h = self.harness(raw)
        mon = E.Harness.generate_pokemon(h, 1, level=5)
        self.assertEqual((mon['species'], mon['level'], mon['form'], mon['slot']), (1, 5, 0, 1))
        self.assertTrue(mon['checksum_ok'])
        self.assertEqual(h.generated_slot, 1)
        h.write.assert_not_called()

    def test_plaintext_payload_with_closed_flags_is_rejected_without_repair(self):
        encrypted = _encrypted_mon(species=1, party=True)
        checksum = struct.unpack_from('<H', encrypted, 6)[0]
        plain = struct.pack('<64H', *[word ^ key for word, key in zip(
            struct.unpack_from('<64H', encrypted, 8), H._prng_stream(checksum, 64))])
        malformed = encrypted[:8] + plain + encrypted[136:]
        self.assertEqual(sum(struct.unpack('<64H', plain)) & 65535, checksum)
        self.assertEqual(struct.unpack_from('<H', malformed, 4)[0], 0)
        h = self.harness(malformed)
        with self.assertRaisesRegex(RuntimeError, 'Native generator produced an invalid closed Pokemon.*No record was repaired'):
            E.Harness.generate_pokemon(h, 1, level=5)
        h.write.assert_not_called()
        self.assertEqual(h.read.return_value, malformed)

    def test_closed_but_wrong_native_identity_is_rejected(self):
        for raw, species, level, form in (
                (_encrypted_mon(species=2, party=True), 1, 5, 0),
                (_encrypted_mon(species=1, party=True), 1, 6, 0),
                (_encrypted_mon(species=1, form=1, party=True), 1, 5, 0)):
            h = self.harness(raw, requested_level=level)
            with self.assertRaisesRegex(RuntimeError, 'does not match the request'):
                E.Harness.generate_pokemon(h, species, level=level, form=form)
            h.write.assert_not_called()

    def test_open_native_record_is_rejected_without_repair(self):
        raw = bytearray(_encrypted_mon(species=1, party=True))
        struct.pack_into('<H', raw, 4, 2)
        h = self.harness(bytes(raw))
        with self.assertRaisesRegex(RuntimeError, 'invalid closed Pokemon'):
            E.Harness.generate_pokemon(h, 1, level=5)
        h.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
