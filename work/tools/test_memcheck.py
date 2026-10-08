"""Synthetic runtime gate tests; no emulator, dependencies or ROM fixtures."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import memcheck


def raw(**changes):
    data = dict(minspare={"19": [4000, 100, 600]}, fails=[], nullw=[], corrupt=None,
                frames=6000, armed=True, screenshots=[], script_completed=True, heap_checks=100, heap_table_errors=[])
    data.update(changes)
    return data


class IntegratedEvidenceTests(unittest.TestCase):
    def test_nonobject_child_evidence_is_incomplete_execution(self):
        import subprocess
        for value in ([], True, "passed", 1, None):
            process = subprocess.CompletedProcess([], 0, "MEMCHECK " + json.dumps(value) + "\n", "")
            with patch.object(memcheck.subprocess, "run", return_value=process):
                result = memcheck.run_child(["synthetic-worker"], 1)
            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["raw"])
            self.assertIn("JSON object", result["parse_error"])

    def test_rendering_requires_declared_later_checkpoint(self):
        scenario = {"script": "boot; shot open; shot later", "expected_rendering": {
            "later": {"profile": "bag_description_v1", "since": "open", "item": 232, "heap": 6}}}
        memcheck.validate_expectations(scenario)
        for baseline in ("later", "missing"):
            scenario["expected_rendering"]["later"]["since"] = baseline
            with self.assertRaises(ValueError):
                memcheck.validate_expectations(scenario)
        scenario["expected_rendering"] = {"missing": {"profile": "bag_description_v1", "since": "boot", "item": 232, "heap": 6}}
        with self.assertRaises(ValueError):
            memcheck.validate_expectations(scenario)


class StoredMoveTests(unittest.TestCase):
    @staticmethod
    def blob(identity=11, moves=(10, 20, 30, 40)):
        import struct
        words = list(range(64))
        offset = memcheck.MOVE_BLOCK_OFFSETS[(identity >> 13) & 31] // 2
        words[offset:offset+4] = moves
        checksum = sum(words) & 0xFFFF
        seed = checksum
        encrypted = []
        for word in words:
            seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
            encrypted.append(word ^ (seed >> 16))
        return struct.pack("<IHH64H", identity, 0, checksum, *encrypted)

    def fixture(self):
        party = {"status": "passed", "address": 0x2200000, "count": 2, "identities": [11, 22]}
        def checkpoint(frame, moves):
            slots = []
            for slot, identity in enumerate(party["identities"]):
                blob = self.blob(identity, moves if slot == 0 else (50, 60, 70, 80))
                slots.append(dict(memcheck.decode_stored_moves(blob), slot=slot,
                                  address=party["address"]+8+236*slot, boxed_hex=blob.hex()))
            return {"frame": frame, "party": party.copy(),
                    "moves": {"status": "passed", "party_address": party["address"], "slots": slots, "observed_frame": frame}}
        return ({"party_size": 2, "expected_move_order": {"after": {"relative_to": "before", "slot": 0, "order": [1,0,2,3]}}},
                {"checkpoints": {"before": checkpoint(10, (10,20,30,40)), "after": checkpoint(20, (20,10,30,40))}})

    def test_snapshot_rejects_unbounded_party_before_memory_read(self):
        class NoReads:
            def read_byte(self, address): raise AssertionError("unbounded read")
        for party in (None, {"status": "passed"},
                      {"status": "passed", "address": 0, "count": 1, "identities": [1]},
                      {"status": "passed", "address": 0x2200000, "count": 7, "identities": list(range(7))}):
            self.assertEqual(memcheck.read_move_snapshot(NoReads(), party)["status"], "incomplete")

    def test_failed_copy_retains_bounded_payload_for_review(self):
        blob = bytearray(self.blob()); blob[8] ^= 1
        base = 0x2200008
        class Memory:
            def read_byte(self, address): return blob[address-base]
        state = memcheck.read_move_snapshot(Memory(), {"status": "passed", "address": base-8,
                                                       "count": 1, "identities": [11]})
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["pending_slot"]["boxed_hex"], bytes(blob).hex())
        self.assertEqual(state["slots"], [])

    def test_decoder_all_native_shuffle_rows(self):
        for row in range(32):
            self.assertEqual(memcheck.decode_stored_moves(self.blob(row << 13))["moves"], [10,20,30,40])

    def test_decoder_rejects_checksum_flags_truncation(self):
        for offset in (4, 5, 6, 7, 8, 135):
            blob = bytearray(self.blob()); blob[offset] ^= 1
            with self.assertRaises(ValueError): memcheck.decode_stored_moves(bytes(blob))
        for blob in (b"", self.blob()[:-1], self.blob()+b"x", None):
            with self.assertRaises(ValueError): memcheck.decode_stored_moves(blob)

    def test_pass_and_unchanged_swap_is_failure(self):
        import copy
        sc, raw = self.fixture()
        self.assertEqual(memcheck.compare_move_runs(sc, raw, raw)[0], "passed")
        bad = copy.deepcopy(raw); bad["checkpoints"]["after"]["moves"] = dict(bad["checkpoints"]["before"]["moves"], observed_frame=20)
        self.assertEqual(memcheck.compare_move_runs(sc, raw, bad)[0], "failed")
        self.assertEqual(memcheck.compare_move_runs(sc, bad, bad)[0], "incomplete")
        self.assertEqual(memcheck.compare_move_runs({}, raw, raw), ("not_configured", [], {}))

    def test_rejects_missing_stale_wrong_owner_and_forged_decode(self):
        import copy
        sc, raw = self.fixture()
        edits = [lambda c: c.update(frame=10), lambda c: c.pop("moves"),
                 lambda c: c["moves"].update(observed_frame=10),
                 lambda c: c["moves"]["slots"][0].update(slot=False),
                 lambda c: c["moves"]["slots"][0].update(boxed_hex=" " + c["moves"]["slots"][0]["boxed_hex"]),
                 lambda c: c["moves"].update(party_address=0x2200010),
                 lambda c: c["moves"]["slots"][0].update(identity=22),
                 lambda c: c["moves"]["slots"][0].update(address=0x2200010),
                 lambda c: c["moves"]["slots"][0].update(moves=[999,10,30,40]),
                 lambda c: c["moves"]["slots"][0].update(boxed_hex="00"*136)]
        for edit in edits:
            bad = copy.deepcopy(raw); edit(bad["checkpoints"]["after"])
            self.assertEqual(memcheck.compare_move_runs(sc, raw, bad)[0], "incomplete")
        for bad in ({}, {"checkpoints": []}, {"checkpoints": {"before": [], "after": None}}):
            self.assertEqual(memcheck.compare_move_runs(sc, raw, bad)[0], "incomplete")

    def test_ambiguous_empty_or_identical_moves_cannot_pass(self):
        sc, raw = self.fixture()
        for moves in ((10,10,30,40), (0,20,30,40)):
            saved = raw["checkpoints"]["before"]["moves"]["slots"][0]
            blob = self.blob(11,moves); saved.update(memcheck.decode_stored_moves(blob), boxed_hex=blob.hex())
            self.assertEqual(memcheck.compare_move_runs(sc, raw, raw)[0], "incomplete")

    def test_closed_summary_requires_prior_owner_and_native_teardown(self):
        import copy
        sc, raw = self.fixture()
        sc["expected_move_order"]["after"]["summary_closed"] = True
        selected = raw["checkpoints"]["before"]["moves"]["slots"][0]
        raw["checkpoints"]["before"]["summary"] = {"status": "passed", "identity": selected["identity"], "address": selected["address"]}
        raw["checkpoints"]["after"]["summary"] = {"status": "incomplete", "context_address": None, "screen_address": None, "observed_frame": -1}
        self.assertEqual(memcheck.compare_move_runs(sc, raw, raw)[0], "passed")
        for field, value in (("context_address",0x2200000),("screen_address",0x2220000),("observed_frame",0),("status","passed")):
            bad = copy.deepcopy(raw); bad["checkpoints"]["after"]["summary"][field] = value
            self.assertEqual(memcheck.compare_move_runs(sc, raw, bad)[0], "incomplete")
        bad = copy.deepcopy(raw); bad["checkpoints"]["before"]["summary"]["identity"] = 99
        self.assertEqual(memcheck.compare_move_runs(sc, raw, bad)[0], "incomplete")
        bad = copy.deepcopy(raw); del bad["checkpoints"]["after"]["summary"]["context_address"]
        self.assertEqual(memcheck.compare_move_runs(sc, raw, bad)[0], "incomplete")

    def test_other_slots_and_other_pokemon_are_preserved(self):
        import copy
        sc, raw = self.fixture()
        for slot, moves in ((0,(20,10,40,30)),(1,(60,50,70,80))):
            bad = copy.deepcopy(raw)
            saved = bad["checkpoints"]["after"]["moves"]["slots"][slot]
            blob = self.blob(saved["identity"], moves)
            saved.update(memcheck.decode_stored_moves(blob), boxed_hex=blob.hex())
            self.assertEqual(memcheck.compare_move_runs(sc, raw, bad)[0], "failed")

    def test_manifest_rejects_invalid_move_expectations(self):
        import copy
        sc = {"script": "shot before; shot after", "party_size": 2,
              "expected_move_order": self.fixture()[0]["expected_move_order"]}
        memcheck.validate_expectations(sc)
        for field, value in (("slot",True),("slot",2),("order",[0,1,2,3]),("order",[True,0,2,3]),("relative_to","after")):
            bad = copy.deepcopy(sc); bad["expected_move_order"]["after"][field] = value
            with self.assertRaises(ValueError): memcheck.validate_expectations(bad)


class EmulatorIsolationTests(unittest.TestCase):
    def test_config_isolated_restored_and_removed_on_failure(self):
        import os
        for prior in (None, "/tmp/user-owned-config"):
            with patch.dict(os.environ):
                if prior is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = prior
                with self.assertRaisesRegex(RuntimeError, "initialization"):
                    with memcheck.isolated_emulator_config() as directory:
                        self.assertEqual(os.environ["XDG_CONFIG_HOME"], str(directory))
                        self.assertTrue(directory.is_dir())
                        (directory / "native-sidecar").write_text("fixture")
                        raise RuntimeError("initialization failed")
                self.assertEqual(os.environ.get("XDG_CONFIG_HOME"), prior)
                self.assertFalse(directory.parent.exists())

    def test_nested_workers_have_distinct_config_paths(self):
        import os
        with memcheck.isolated_emulator_config() as first:
            with memcheck.isolated_emulator_config() as second:
                self.assertNotEqual(first, second)
            self.assertEqual(os.environ["XDG_CONFIG_HOME"], str(first))


class SummarySelectionTests(unittest.TestCase):
    def fixture(self):
        party = {"status": "passed", "address": 0x2200000, "count": 2, "identities": [11, 22]}
        context, screen = 0x2210000, 0x2220000
        values = {context: party["address"], context+0x11: 1, context+0x13: 2, context+0x14: 1,
                  screen+0x23C: context, party["address"]+8+236: 22}
        class Memory:
            def read_long(self, address): return values[address]
            def read_byte(self, address): return values[address]
        return Memory(), values, party, context, screen

    def test_live_snapshot_and_owner_mode_count_slot_guards(self):
        mem, values, party, context, screen = self.fixture()
        self.assertEqual(memcheck.read_summary_snapshot(mem, context, 20, party, screen)["identity"], 22)
        for key, value in ((screen+0x23C, context+4), (context, party["address"]+4),
                           (context+0x11, 0), (context+0x13, 6), (context+0x14, 2)):
            old = values[key]; values[key] = value
            self.assertEqual(memcheck.read_summary_snapshot(mem, context, 20, party, screen)["status"], "incomplete")
            values[key] = old
        for invalid in (None, True, 0, 0x2240000, context+1):
            self.assertEqual(memcheck.read_summary_snapshot(mem, invalid, 20, party, screen)["status"], "incomplete")

    def test_freed_context_or_owner_invalidates_snapshot(self):
        from types import SimpleNamespace
        mem, values, party, context, screen = self.fixture()
        for released in (context, screen):
            probe = memcheck.Probe.__new__(memcheck.Probe)
            probe.R = SimpleNamespace(r0=released)
            probe.summary_screen, probe.summary_context, probe.summary_observed_frame = screen, context, 20
            probe._on_summary_free(0, 0)
            self.assertIsNone(probe.summary_context)
            self.assertEqual(probe.summary_observed_frame, -1)
            self.assertEqual(memcheck.read_summary_snapshot(mem, probe.summary_context, -1, party, probe.summary_screen)["status"], "incomplete")

    def test_resolver_entry_clears_previous_selection(self):
        from types import SimpleNamespace
        probe = memcheck.Probe.__new__(memcheck.Probe)
        probe.R = SimpleNamespace(r0=0x2220000)
        probe.summary_context, probe.summary_observed_frame = 0x2210000, 20
        probe._on_summary_enter(0, 0)
        self.assertIsNone(probe.summary_context)
        self.assertEqual(probe.summary_observed_frame, -1)

    def test_malformed_summary_evidence_is_incomplete(self):
        scenario = {"party_size": 2, "expected_summary_selection": {"switched": {"since": "skills", "slot": 1}}}
        for raw in ({"checkpoints": None}, {"checkpoints": {"switched": None}},
                    {"checkpoints": {"switched": {"summary": [], "party": None}}}):
            self.assertTrue(memcheck.summary_state_evidence(scenario, raw)["gaps"])

    def test_temporal_identity_and_regression_classification(self):
        import copy
        mem, values, party, context, screen = self.fixture()
        scenario = {"party_size": 2, "expected_summary_selection": {"switched": {"since": "skills", "slot": 1}}}
        raw = {"checkpoints": {"skills": {"frame": 10}, "switched": {"frame": 30, "party": party,
               "summary": memcheck.read_summary_snapshot(mem, context, 20, party, screen)}}}
        self.assertEqual(memcheck.compare_summary_runs(scenario, raw, raw)[0], "passed")
        for field, value in (("observed_frame", 10), ("observed_frame", 31), ("identity", 11),
                             ("slot", True), ("address", 0), ("screen_address", None)):
            bad = copy.deepcopy(raw); bad["checkpoints"]["switched"]["summary"][field] = value
            self.assertEqual(memcheck.compare_summary_runs(scenario, raw, bad)[0], "incomplete")
        bad = copy.deepcopy(raw); state = bad["checkpoints"]["switched"]["summary"]
        state.update(slot=0, identity=11, address=party["address"]+8)
        self.assertEqual(memcheck.compare_summary_runs(scenario, raw, bad)[0], "failed")
        self.assertEqual(memcheck.compare_summary_runs(scenario, bad, bad)[0], "incomplete")
        self.assertEqual(memcheck.compare_summary_runs({}, raw, raw), ("not_configured", [], {}))


class MemcheckTests(unittest.TestCase):
    def setUp(self):
        (memcheck.WORK / "build").mkdir(parents=True, exist_ok=True)

    def test_clean_and_shared(self):
        self.assertEqual(memcheck.compare_runs(raw(), raw())[0], "passed")
        status, findings = memcheck.compare_runs(raw(fails=[[19, 400, 2]]), raw(fails=[[19, 400, 9]]))
        self.assertEqual(status, "passed")
        self.assertEqual(findings[0]["category"], "baseline_shared")

    def test_different_allocations_do_not_cancel(self):
        self.assertEqual(memcheck.compare_runs(raw(fails=[[19, 400, 2]]), raw(fails=[[19, 401, 2]]))[0], "failed")

    def test_nullwrite_pc_and_failure_kind(self):
        for en in (raw(nullw=[[100, 2]]), raw(fails=[[1, 2, 3]])):
            self.assertEqual(memcheck.compare_runs(raw(nullw=[[101, 2]]), en)[0], "failed")

    def test_corruption_normalizes_addresses_only(self):
        z = raw(corrupt=[2, "heap 19 (021ABCDE): free block 1 at 021FFFFF has a bad header"])
        e = raw(corrupt=[8, "heap 19 (022ABCDE): free block 1 at 022FFFFF has a bad header"])
        self.assertEqual(memcheck.compare_runs(z, e)[0], "passed")
        e["corrupt"][1] = e["corrupt"][1].replace("free", "used")
        self.assertEqual(memcheck.compare_runs(z, e)[0], "failed")

    def test_incomplete_evidence_and_chinese_only(self):
        for z, e in ((raw(), raw(armed=False)), (raw(), raw(minspare={})),
                     (raw(fails=[[1, 2, 3]]), raw())):
            self.assertEqual(memcheck.compare_runs(z, e)[0], "incomplete")

    def test_negative_spare_is_not_failure(self):
        self.assertEqual(memcheck.compare_runs(raw(), raw(minspare={"19": [-1, 100, 600]}))[0], "passed")

    def test_timeout_validation(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.assertRaises(argparse.ArgumentTypeError):
                memcheck.positive_seconds(value)

    def test_timeout_retains_partial_diagnostics(self):
        code = 'import time; print(\'MEMCHECK {"frames": 600}\', flush=True); time.sleep(5)'
        result = memcheck.run_child([sys.executable, "-c", code], .1)
        self.assertEqual(result["status"], "timeout")
        self.assertIsNone(result["returncode"])
        self.assertEqual(result["raw"]["frames"], 600)

    def test_missing_save_and_all_skipped(self):
        with tempfile.TemporaryDirectory(dir=memcheck.WORK / "build") as tmp:
            args = argparse.Namespace(scenario="all", rom=__file__, ref=__file__, out=tmp,
                                      saves=tmp, json=None, timeout=1, warn=4096, verbose=False)
            with patch.object(memcheck, "capabilities", return_value={}), patch.object(memcheck, "_check_code"), patch.object(memcheck, "static_loads", return_value=([], [])):
                self.assertEqual(memcheck.cmd_run(args), 2)
            result = json.loads((Path(tmp) / "report.json").read_text())
            self.assertEqual(result["counts"]["executed"], 0)
            self.assertGreater(result["counts"]["incomplete"], 0)

    def test_invalid_selection(self):
        with tempfile.TemporaryDirectory(dir=memcheck.WORK / "build") as tmp:
            args = argparse.Namespace(scenario="unknown", rom=__file__, ref=__file__, out=tmp,
                                      saves=tmp, json=None, timeout=1, warn=4096, verbose=False)
            self.assertEqual(memcheck.cmd_run(args), 2)
            self.assertTrue(json.loads((Path(tmp) / "report.json").read_text())["errors"])


class SparseMemory:
    def __init__(self):
        self.data = {}
        self.reads = 0
    def put(self, address, value, width=4):
        for i, byte in enumerate(value.to_bytes(width, "little")):
            self.data[address+i] = byte
    def read(self, address, width):
        self.reads += 1
        if not memcheck.RAM[0] <= address <= memcheck.RAM[1]-width:
            raise AssertionError("out-of-RAM read")
        return sum(self.data.get(address+i, 0) << (8*i) for i in range(width))
    def read_byte(self, address): return self.read(address, 1)
    def read_short(self, address): return self.read(address, 2)
    def read_long(self, address): return self.read(address, 4)
    def __getitem__(self, key): raise AssertionError("bulk RAM access forbidden")


def snapshot_reference(memory):
    """Original snapshot walker, independent of native read accessors."""
    import struct
    lo, hi = memcheck.RAM
    snapshot = bytearray(hi-lo)
    for address, value in memory.data.items(): snapshot[address-lo] = value
    u32 = lambda a: struct.unpack_from("<I", snapshot, a-lo)[0]
    u16 = lambda a: struct.unpack_from("<H", snapshot, a-lo)[0]
    handles, idxs, count = u32(memcheck.HEAP_INFO), u32(memcheck.HEAP_INFO+16), u16(memcheck.HEAP_INFO+20)
    live = set()
    for hid in range(count):
        h = u32(handles+4*snapshot[idxs+hid-lo])
        if lo <= h < hi and u32(h) == 0x45585048: live.add((hid,h))
    for hid,h in sorted(live):
        st,en = u32(h+24),u32(h+28)
        if not lo <= st < en <= hi: return f"heap {hid} ({h:08X}): bad bounds"
        for head,want,kind in ((36,memcheck.FREE_SIG,"free"),(44,0x5544,"used")):
            p,prev,n = u32(h+head),0,0
            while p and n < 8192:
                if not st <= p < en-16 or u16(p) != want:
                    return f"heap {hid} ({h:08X}): {kind} block {n} at {p:08X} has a bad header"
                if u32(p+8) != prev:
                    return f"heap {hid} ({h:08X}): {kind} block at {p:08X} has a broken back link"
                prev,p,n = p,u32(p+12),n+1
    return None


class HeapWalkerTests(unittest.TestCase):
    def fixture(self):
        m = SparseMemory()
        handles, idxs, h, block = 0x02001000,0x02002000,0x02003000,0x02004000
        m.put(memcheck.HEAP_INFO, handles); m.put(memcheck.HEAP_INFO+16,idxs)
        m.put(memcheck.HEAP_INFO+20,2,2)
        m.put(idxs,0,1); m.put(idxs+1,1,1)
        m.put(handles,h); m.put(handles+4,h+0x100) # dead heap remains in RAM
        m.put(h,0x45585048); m.put(h+24,block); m.put(h+28,block+0x1000)
        m.put(h+36,block); m.put(block,memcheck.FREE_SIG,2)
        p = memcheck.Probe.__new__(memcheck.Probe)
        p.mem,p.armed,p.heap_checks,p.heap_table_errors = m,True,0,[]
        return p,m,h,block
    def test_snapshot_equivalence(self):
        for mutation in ("healthy","signature","backlink","bounds","used"):
            with self.subTest(mutation=mutation):
                p,m,h,b = self.fixture()
                if mutation == "signature": m.put(b,0x1234,2)
                if mutation == "backlink": m.put(b+8,b)
                if mutation == "bounds": m.put(h+28,b-1)
                if mutation == "used": m.put(h+36,0); m.put(h+44,b); m.put(b,0x5544,2)
                self.assertEqual(p.heap_walk(),snapshot_reference(m))
                self.assertLess(m.reads,50)
    def test_cycle_and_invalid_tables(self):
        p,m,h,b = self.fixture(); m.put(b+12,b)
        self.assertIn("cycle",p.heap_walk())
        p,m,h,b = self.fixture(); m.put(memcheck.HEAP_INFO+16,memcheck.RAM[1]-1)
        self.assertIsNone(p.heap_walk()); self.assertTrue(p.heap_table_errors)
        p.armed=False; p.heap_table_errors=[]; p.heap_walk()
        self.assertEqual(p.heap_table_errors,[])
    def test_unsafe_handle_and_no_heap_evidence(self):
        p,m,h,b=self.fixture(); m.put(0x02001000,memcheck.RAM[1]-1)
        self.assertIsNone(p.heap_walk()); self.assertTrue(p.heap_table_errors)
        self.assertEqual(memcheck.compare_runs(raw(),raw(heap_checks=0))[0],"incomplete")
        self.assertEqual(memcheck.compare_runs(raw(),raw(heap_table_errors=["bad table"]))[0],"incomplete")

class CheckpointTests(unittest.TestCase):
    def scenario(self):
        return {'script':'boot; shot info; shot skills', 'expected_checkpoints': {
            'skills': {'since':'info','loads':[{'narc':27,'bank':712,'heap':19}]}}}
    def evidence(self, frame=15, **changes):
        event={'narc':27,'bank':712,'heap':19,'frame':frame}
        result={'script_completed':True,'checkpoints':{
            'boot':{'frame':0},'info':{'frame':10},
            'skills':{'frame':20,'screenshot_captured':True,'message_loads':[event]}}}
        result.update(changes)
        return result
    def test_strict_temporal_window(self):
        for frame,expected in [(9,'incomplete'),(10,'incomplete'),(11,'passed'),(20,'passed'),(21,'incomplete')]:
            self.assertEqual(memcheck.checkpoint_coverage(self.scenario(),self.evidence(frame))['status'],expected)
    def test_missing_wrong_and_uncaptured(self):
        data=self.evidence();data['checkpoints']['skills']['message_loads'][0]['bank']=295
        self.assertEqual(memcheck.checkpoint_coverage(self.scenario(),data)['status'],'incomplete')
        for change in ({'checkpoints':{}},{'script_completed':False}):
            self.assertEqual(memcheck.checkpoint_coverage(self.scenario(),self.evidence(**change))['status'],'incomplete')
        data=self.evidence();data['checkpoints']['skills']['screenshot_captured']=False
        self.assertEqual(memcheck.checkpoint_coverage(self.scenario(),data)['status'],'incomplete')
    def test_unverified_and_known_warning(self):
        scenario=self.scenario();scenario['expected_checkpoints']={}
        self.assertEqual(memcheck.checkpoint_coverage(scenario,self.evidence())['status'],'incomplete')
        scenario=self.scenario();scenario['coverage_warnings']=['Battle moves checkpoint shows PARTY']
        self.assertIn('Battle moves checkpoint shows PARTY',memcheck.checkpoint_coverage(scenario,self.evidence())['gaps'])
    def test_report_distinguishes_scoped_pass_from_unasserted_actions(self):
        scenario=self.scenario()
        scenario['script'] += '; shot end'
        result=memcheck.checkpoint_coverage(scenario,self.evidence())
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['configured_checkpoints'],['skills'])
        self.assertEqual(result['unasserted_checkpoints'],['info','end'])
        scenario['expected_checkpoints']={}
        result=memcheck.checkpoint_coverage(scenario,self.evidence())
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['unasserted_checkpoints'],['info','skills','end'])
    def test_manifest_schema(self):
        memcheck.validate_expectations(self.scenario())
        for mutation in ('unknown','future','badkey','bool','warning','scope'):
            sc=self.scenario()
            if mutation=='unknown':sc['expected_checkpoints']={'unknown':sc['expected_checkpoints']['skills']}
            if mutation=='future':sc['expected_checkpoints']['skills']['since']='skills'
            if mutation=='badkey':sc['expected_checkpoints']['skills']['loads'][0]['extra']=0
            if mutation=='bool':sc['expected_checkpoints']['skills']['loads'][0]['heap']=True
            if mutation=='warning':sc['coverage_warnings']='unsupported'
            if mutation=='scope':sc['coverage_scope']=''
            with self.assertRaises(ValueError):memcheck.validate_expectations(sc)

class TextCopyTests(unittest.TestCase):
    def probe(self, capacity=114, units=120, destination=0x02004000):
        from types import SimpleNamespace
        p=memcheck.Probe.__new__(memcheck.Probe)
        p.mem=SparseMemory();p.mem.put(0x02004000,capacity,2)
        p.R=SimpleNamespace(r0=destination,r2=units,lr=0x0200b941)
        p._item_contexts=[];p.item_description_reads=[]
        p.frame=5400;p.text_copy_checks=0;p.text_rejections=[];p.text_probe_errors=[]
        return p
    def test_native_boundary_counts_terminator(self):
        for units,rejected in ((114,False),(115,True),(120,True)):
            p=self.probe(units=units);p._on_text_copy(0,0)
            self.assertEqual(bool(p.text_rejections),rejected)
            self.assertEqual(p.text_copy_checks,1)
    def test_unreadable_pointer_does_not_read_ram(self):
        for destination in (0,memcheck.RAM[1]-1):
            p=self.probe(destination=destination);p._on_text_copy(0,0)
            self.assertTrue(p.text_probe_errors);self.assertEqual(p.mem.reads,0)
    def test_new_rejection_even_when_memory_clean(self):
        p=self.probe();p._on_text_copy(0,0)
        z=raw(text_copy_checks=1,text_rejections=[],text_probe_errors=[])
        e=raw(text_copy_checks=1,text_rejections=p.text_rejections,text_probe_errors=[])
        self.assertEqual(memcheck.compare_runs(z,e)[0],'passed')
        status,findings,gaps=memcheck.compare_text_runs(z,e)
        self.assertEqual(status,'failed');self.assertEqual(findings[0]['kind'],'text_copy_rejected')
    def test_baseline_signatures_ignore_frame_destination(self):
        event={'caller':100,'capacity':114,'units':120,'frame':5,'destination':0x02004000}
        z=raw(text_copy_checks=1,text_rejections=[event])
        e=raw(text_copy_checks=1,text_rejections=[dict(event,frame=8,destination=0x02005000)])
        self.assertEqual(memcheck.compare_text_runs(z,e)[0],'passed')
        self.assertEqual(memcheck.compare_text_runs(z,e)[1][0]['category'],'baseline_shared')
        for key,value in (('caller',101),('units',121),('capacity',115)):
            other=raw(text_copy_checks=1,text_rejections=[dict(event,**{key:value})])
            self.assertEqual(memcheck.compare_text_runs(z,other)[0],'failed')
    def test_missing_checks_and_probe_errors_incomplete(self):
        clean=raw(text_copy_checks=1,text_rejections=[])
        for e in (raw(),raw(text_copy_checks=1,text_probe_errors=['invalid pointer'])):
            self.assertEqual(memcheck.compare_text_runs(clean,e)[0],'incomplete')

    def test_item_context_is_cleared_and_counts_remain_diagnostics(self):
        p=self.probe();p.R.r1=232;p.R.r2=6;p._on_item_description(0,0);p.R.r2=120
        p._on_text_copy(0,0)
        event=p.text_rejections[-1]
        self.assertEqual(event['item'],232)
        p._on_item_description_return(0,0);p._on_text_copy(0,0)
        self.assertNotIn('item',p.text_rejections[-1])
        z=raw(text_copy_checks=1,text_rejections=[event])
        e=raw(text_copy_checks=1,text_rejections=[dict(event,units=130)])
        self.assertEqual(memcheck.compare_text_runs(z,e)[0],'passed')
        e['text_rejections'][0]['item']=233
        self.assertEqual(memcheck.compare_text_runs(z,e)[0],'failed')
    def test_unaligned_destination_is_incomplete(self):
        p=self.probe(destination=0x02004001);p._on_text_copy(0,0)
        self.assertTrue(p.text_probe_errors);self.assertEqual(p.mem.reads,0)

class DescriptionCheckpointTests(unittest.TestCase):
    def scenario(self):
        return {'script':'boot; shot open', 'expected_checkpoints':{
            'open':{'since':'start','descriptions':[{'item':4,'heap':11}]}}}
    def evidence(self,frame=5,item=4,heap=11):
        return {'script_completed':True,'checkpoints':{'start':{'frame':0},'boot':{'frame':10},
            'open':{'frame':20,'screenshot_captured':True,'item_description_reads':[
                {'frame':frame,'item':item,'heap':heap,'destination':1}]}}}
    def test_start_includes_reads_during_boot(self):
        memcheck.validate_expectations(self.scenario())
        self.assertEqual(memcheck.checkpoint_coverage(self.scenario(),self.evidence())['status'],'passed')
    def test_temporal_wrong_item_heap_and_after_shot(self):
        for args in ({'frame':0},{'frame':21},{'item':232},{'heap':6}):
            self.assertEqual(memcheck.checkpoint_coverage(self.scenario(),self.evidence(**args))['status'],'incomplete')
        sc=self.scenario();sc['expected_checkpoints']['open']['since']='boot'
        self.assertEqual(memcheck.checkpoint_coverage(sc,self.evidence())['status'],'incomplete')
    def test_reads_recorded_without_rejection(self):
        p=TextCopyTests().probe(units=24);p.R.r1=4;p.R.r2=11
        p._on_item_description(0,0);p.R.r2=24;p._on_text_copy(0,0)
        self.assertEqual(p.text_rejections,[])
        self.assertEqual(p.item_description_reads[0]['item'],4)
        self.assertEqual(p.item_description_reads[0]['heap'],11)
    def test_invalid_and_empty_evidence_lists(self):
        for malformed in ({'since':'start','descriptions':[]},
                          {'since':'start','descriptions':[{'item':4,'heap':True}]},
                          {'since':'start','descriptions':[{'item':4}]},
                          {'since':'start','descriptions':'bad'}):
            sc=self.scenario();sc['expected_checkpoints']['open']=malformed
            with self.assertRaises(ValueError):memcheck.validate_expectations(sc)

    def test_reserved_bootstrap_checkpoint_names_rejected(self):
        for name in ('start','boot'):
            sc=self.scenario();sc['script']=f'boot; shot {name}; shot open'
            with self.assertRaisesRegex(ValueError,'reserved'):
                memcheck.validate_expectations(sc)


class PartyStateTests(unittest.TestCase):
    def scenario(self):
        return {'script': 'boot; shot menu; shot switched; shot end', 'party_size': 2,
                'expected_party_order': {'switched': {'relative_to': 'menu', 'order': [1, 0]},
                                         'end': {'relative_to': 'menu', 'order': [0, 1]}}}

    def evidence(self, swapped=True, restored=True):
        return {'checkpoints': {name: {'frame': frame, 'party': {
            'status': 'passed', 'address': 0x02200000, 'count': 2, 'identities': ids}}
            for name, frame, ids in [('menu', 10, [101, 202]),
                                    ('switched', 20, [202, 101] if swapped else [101, 202]),
                                    ('end', 30, [101, 202] if restored else [202, 101])]}}

    def test_exact_swap_and_restoration(self):
        status, findings, evidence = memcheck.compare_party_runs(self.scenario(), self.evidence(), self.evidence())
        self.assertEqual((status, findings), ('passed', []))
        self.assertFalse(any(v['gaps'] for v in evidence.values()))

    def test_missed_swap_is_english_regression(self):
        status, findings, _ = memcheck.compare_party_runs(self.scenario(), self.evidence(), self.evidence(swapped=False))
        self.assertEqual(status, 'failed')
        self.assertEqual(findings[0]['category'], 'english_regression')

    def test_shared_failed_restoration_is_incomplete(self):
        bad = self.evidence(restored=False)
        status, findings, _ = memcheck.compare_party_runs(self.scenario(), bad, bad)
        self.assertEqual(status, 'incomplete')
        self.assertEqual(findings[0]['category'], 'baseline_shared')

    def test_chinese_gap_cannot_prove_english_regression(self):
        status, findings, _ = memcheck.compare_party_runs(self.scenario(), {}, self.evidence(swapped=False))
        self.assertEqual(status, 'incomplete')
        self.assertFalse(any(f['category'] == 'english_regression' for f in findings))

    def test_invalid_snapshots_fail_closed(self):
        for change in ({'status': 'incomplete'}, {'count': 6}, {'identities': [1, 1]},
                       {'identities': [True, 2]}, {'address': 0x02400000}, {'error': 'unavailable'}):
            data = self.evidence()
            data['checkpoints']['switched']['party'].update(change)
            self.assertEqual(memcheck.compare_party_runs(self.scenario(), self.evidence(), data)[0], 'incomplete')

    def test_permutations_and_temporal_order_validated(self):
        for order in ([0, 0], [0], [False, 1], [0, 2]):
            scenario = self.scenario()
            scenario['expected_party_order']['switched']['order'] = order
            with self.assertRaises(ValueError):
                memcheck.validate_expectations(scenario)
        data = self.evidence()
        data['checkpoints']['switched']['frame'] = 10
        self.assertEqual(memcheck.compare_party_runs(self.scenario(), self.evidence(), data)[0], 'incomplete')

    def test_bounded_reader_does_not_touch_invalid_address(self):
        class Memory:
            def read_long(self, address):
                raise AssertionError('must not read')
        for address in (0, 0x02000001, 0x02400000 - 8, True):
            self.assertEqual(memcheck.read_party_snapshot(Memory(), address)['status'], 'incomplete')

    def test_reader_checks_capacity_count_duplicates_and_stride(self):
        class Memory:
            def __init__(self, values): self.values = values
            def read_long(self, address): return self.values[address]
        address = 0x02200000
        values = {address: 6, address+4: 2, address+8: 101, address+244: 202}
        self.assertEqual(memcheck.read_party_snapshot(Memory(values), address)['identities'], [101, 202])
        for key, value in ((address, 7), (address+4, 7), (address+244, 101)):
            changed = dict(values); changed[key] = value
            self.assertEqual(memcheck.read_party_snapshot(Memory(changed), address)['status'], 'incomplete')

    def test_unconfigured_explicit(self):
        self.assertEqual(memcheck.compare_party_runs({}, {}, {}), ('not_configured', [], {}))


if __name__ == "__main__":
    unittest.main()
