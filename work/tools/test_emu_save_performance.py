"""Call-count and buffer-ownership regressions; no timing budgets or native inputs."""
import os
import shutil
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import emu_harness as E
import emu_open as O
import emu_skitty as K
import save_core as C
import test_emu_harness as H


def opened_record(flags, *, party=True):
    """Independent synthetic RAM state, using the test fixture's encryption oracle."""
    raw = bytearray(H._encrypted_mon(123, species=201, party=party))
    pid, _, checksum = struct.unpack_from('<IHH', raw)
    if flags & 2:
        words = struct.unpack_from('<64H', raw, 8)
        struct.pack_into('<64H', raw, 8, *[a ^ b for a, b in zip(words, H._prng_stream(checksum, 64))])
    if flags & 1 and party:
        words = struct.unpack_from('<50H', raw, 136)
        struct.pack_into('<50H', raw, 136, *[a ^ b for a, b in zip(words, H._prng_stream(pid, 50))])
    struct.pack_into('<H', raw, 4, flags)
    return bytes(raw)


class SaveRoundTrips(unittest.TestCase):
    def setUp(self):
        self.path = H.SaveFileEdits()._save()
        self.addCleanup(shutil.rmtree, self.path.parent)

    def test_edit_returns_current_inspection_in_one_round_trip(self):
        sf = E.SaveFile(self.path)
        source = self.path.read_bytes()
        with patch.object(C, 'request', wraps=C.request) as request:
            sf.set_flag(123)
            self.assertTrue(sf.get_flag(123))
            sf.set_var(0x4000, 456)
            self.assertEqual(sf.get_var(0x4000), 456)
            sf.set_location(109, 16, 14)
            self.assertEqual(sf.location()['map'], 109)
        self.assertEqual([c.args[0] for c in request.call_args_list], ['transactSave'] * 3)
        self.assertEqual(self.path.read_bytes(), source)

    def test_incomplete_response_does_not_publish_candidate_bytes(self):
        sf = E.SaveFile(self.path)
        before, inspection = sf.data, sf._inspect
        for result in ({'bytes': 'AA=='}, {'bytes': 'AA==', 'inspection': {}}):
            with patch.object(C, 'request', return_value=result):
                with self.assertRaises(KeyError):
                    sf.set_flag(1)
            self.assertIs(sf.data, before)
            self.assertIs(sf._inspect, inspection)

    def test_start_at_batches_teleport_flags_and_variables(self):
        h = Mock(emulator='melonds')
        h.location.return_value = {'map': 109}
        with patch.object(E, 'Harness', return_value=h), patch.object(C, 'request', wraps=C.request) as request:
            with E.start_at(109, 16, 14, sav=self.path, flags=range(1, 1001),
                            vars={0x4000: 5, 0x416F: 7}, emulator='melonds'):
                pass
        self.assertEqual([c.args[0] for c in request.call_args_list], ['inspectSave', 'transactSave'])
        self.assertEqual(len(request.call_args_list[1].kwargs['operations']), 1003)
        h.close.assert_called_once()

    def test_start_at_callback_observes_teleport_before_flags_and_vars(self):
        h = Mock(emulator='melonds')
        h.location.return_value = {'map': 109}
        snapshots = []

        def edit(sf):
            self.assertEqual(sf.location()['map'], 109)
            self.assertFalse(sf.get_flag(123))
            sf.set_var(0x4000, 9)
            snapshots.append(sf)

        with patch.object(E, 'Harness', return_value=h), patch.object(C, 'request', wraps=C.request) as request:
            with E.start_at(109, 16, 14, sav=self.path, flags=[123], vars={0x4000: 42}, edit=edit,
                            emulator='melonds'):
                self.assertTrue(snapshots[0].get_flag(123))
                self.assertEqual(snapshots[0].get_var(0x4000), 42)
        self.assertEqual([c.args[0] for c in request.call_args_list], ['inspectSave'] + ['transactSave'] * 3)

    def test_cmd_wild_batches_teleport_and_flags(self):
        h = MagicMock()
        h.__enter__.return_value = h
        h.location.return_value = {'map': 109}
        h.clock.return_value = {}
        args = SimpleNamespace(out=self.path.parent, sav=self.path, rom='synthetic.nds', flags='1,2,3,4',
                               map=109, x=16, y=14, walk='LEFT,RIGHT', clock=None, state=None,
                               tag='test', count=0, max_steps=0, json=None)
        with patch.object(E, 'Harness', return_value=h), patch.object(E, 'WildLog', return_value=Mock(rows=[])), \
                patch.object(C, 'request', wraps=C.request) as request, patch('builtins.print'):
            self.assertEqual(E.cmd_wild(args), 0)
        self.assertEqual([c.args[0] for c in request.call_args_list], ['inspectSave', 'transactSave'])
        self.assertEqual(len(request.call_args_list[1].kwargs['operations']), 5)


class RamScanFiltering(unittest.TestCase):
    def test_party_scan_rejects_thousands_of_bad_checksums_before_worker(self):
        corrupt = bytearray(opened_record(0))
        corrupt[8] ^= 1
        invalid = struct.pack('<II', 6, 1) + corrupt
        good = opened_record(0)
        ram = bytes(invalid) * 1500 + struct.pack('<II', 6, 1) + good
        h = Mock()
        h.read.return_value = ram
        with patch.object(C, 'request', wraps=C.request) as request:
            parties = K.find_parties(h, 0, len(ram))
        self.assertEqual(request.call_count, 1)
        self.assertEqual([p['addr'] for p in parties], [hex(len(invalid) * 1500)])
        self.assertEqual(parties[0]['mons'][0]['species'], 201)

    def test_party_at_exact_scan_end_and_open_ram_states(self):
        for flags in (0, 1, 2, 3):
            for count in (1, 6):
                with self.subTest(flags=flags, count=count):
                    ram = struct.pack('<II', 6, count) + opened_record(flags) * count
                    h = Mock()
                    h.read.return_value = ram
                    with patch.object(C, 'request', wraps=C.request) as request:
                        parties = K.find_parties(h, 0, len(ram))
                    self.assertEqual(len(parties), 1)
                    self.assertEqual(len(parties[0]['mons']), count)
                    self.assertEqual(request.call_count, count)

    def test_truncated_party_and_header_never_reach_worker(self):
        for ram in (struct.pack('<II', 6, 1) + opened_record(0)[:-1], struct.pack('<I', 6),
                    struct.pack('<II', 6, 6) + opened_record(0)):
            h = Mock()
            h.read.return_value = ram
            with patch.object(C, 'request', side_effect=AssertionError('unexpected RPC')):
                self.assertEqual(K.find_parties(h, 0, len(ram)), [])

    def test_pid_scan_filters_bad_and_truncated_records_preserving_open_copies(self):
        good = [opened_record(flags, party=False) for flags in (0, 1, 2, 3)]
        pid = struct.unpack_from('<I', good[0])[0]
        corrupt = bytearray(good[0])
        corrupt[8] ^= 1
        prefix = bytes(corrupt) * 1000
        ram = prefix + b''.join(good) + good[0][:-1]
        h = Mock()
        h.read.return_value = ram
        with patch.object(C, 'request', wraps=C.request) as request:
            copies = O.pid_copies(h, pid, 0, len(ram))
        self.assertEqual(copies, [len(prefix) + 136 * i for i in range(4)])
        self.assertEqual(request.call_count, 4)

    def test_checksum_filter_rejects_corrupt_open_payload(self):
        for flags in (2, 3):
            raw = bytearray(opened_record(flags))
            raw[8] ^= 1
            self.assertFalse(K.ram_pokemon_checksum_ok(bytes(raw)))


class PacketBuffers(unittest.TestCase):
    def test_partial_pipe_writes_share_one_packet_without_slicing_bytes(self):
        worker = C.Worker([sys.executable, '-u', '-c', '''import sys,json
for line in sys.stdin:
 r=json.loads(line); print(json.dumps(dict(version=1,id=r['id'],result=len(r['bytes']))),flush=True)
'''], timeout=5)
        self.addCleanup(worker.close)
        write = os.write
        owners = []

        def partial_write(fd, data):
            self.assertIsInstance(data, memoryview)
            owners.append(data.obj)
            return write(fd, data[:4096])

        with patch.object(C.os, 'write', side_effect=partial_write):
            self.assertEqual(worker.request('large', bytes(524288)), 699052)
        self.assertGreater(len(owners), 100)
        self.assertTrue(all(owner is owners[0] for owner in owners))


if __name__ == '__main__':
    unittest.main()
