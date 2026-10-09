"""Unit tests for emu_harness's pure parts (no emulator, no ROM, no save fixtures)."""
import binascii
import random
import struct
import tempfile
import unittest
from pathlib import Path

import emu_harness as E


# Independent synthetic fixture builder. Never asks the production writer to
# repair arbitrary bytes; encryption/checksum are test-only oracle operations.
BLOCK_ORDERS = ["".join(p) for p in __import__("itertools").permutations("ABCD")]


def _prng_stream(seed, n):
    out = []
    for _ in range(n):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        out.append(seed >> 16)
    return out


def _encrypted_mon(seed=1, species=201, item=0, form=0, party=False):
    pid = random.Random(seed).getrandbits(32)
    blocks = {letter: bytearray(32) for letter in "ABCD"}
    struct.pack_into("<HH", blocks["A"], 0, species, item)
    blocks["B"][0x18] = form << 3
    order = BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    plain = b"".join(blocks[letter] for letter in order)
    words = struct.unpack("<64H", plain)
    checksum = sum(words) & 0xFFFF
    raw = struct.pack("<IHH", pid, 0, checksum) + struct.pack("<64H", *[
        value ^ key for value, key in zip(words, _prng_stream(checksum, 64))])
    if party:
        tail = bytearray(100)
        tail[4] = 5
        struct.pack_into("<7H", tail, 6, 20, 20, 10, 10, 10, 10, 10)
        raw += struct.pack("<50H", *[value ^ key for value, key in zip(
            struct.unpack("<50H", tail), _prng_stream(pid, 50))])
    return raw


class PokemonCodec(unittest.TestCase):
    def test_moveset_pads(self):
        self.assertEqual(E.moveset([150], [40]), {"moves": [150, 0, 0, 0], "pp": [40, 0, 0, 0]})

    def test_roundtrip_and_checksum(self):
        for seed in range(30):
            raw = _encrypted_mon(seed, species=200 + seed, item=seed, form=seed % 28)
            mon = E.decode_pokemon(raw)
            self.assertTrue(mon["checksum_ok"])
            self.assertEqual((mon["species"], mon["item"], mon["form"]), (200 + seed, seed, seed % 28))

    def test_moves_roundtrip(self):
        raw = E.encode_pokemon(_encrypted_mon(4), moves=[85, 86, 87, 98], pp=[15, 20, 10, 30])
        self.assertTrue(E.decode_pokemon(raw)["checksum_ok"])
        order = BLOCK_ORDERS[((struct.unpack_from("<I", raw)[0] & 0x3E000) >> 13) % 24]
        checksum = struct.unpack_from("<H", raw, 6)[0]
        plain = struct.pack("<64H", *[w ^ k for w, k in zip(struct.unpack_from("<64H", raw, 8),
                                                              _prng_stream(checksum, 64))])
        b = 32 * order.index("B")
        self.assertEqual(struct.unpack_from("<4H", plain, b), (85, 86, 87, 98))
        self.assertEqual(tuple(plain[b + 8:b + 12]), (15, 20, 10, 30))

    def test_script_bytes(self):
        self.assertEqual(E.script_bytes(("TrainerBattle", 5, 0, 0, 0), ("End",)),
                         bytes.fromhex("d500" "0500" "0000" "00" "00" "0200"))

    def test_form_keeps_gender_bits(self):
        raw = _encrypted_mon(3)
        before = E.decode_pokemon(raw)
        after = E.decode_pokemon(E.encode_pokemon(raw, form=5))
        self.assertEqual(after["form"], 5)
        self.assertEqual(after["fateful"], before["fateful"])


class SlotWaits(unittest.TestCase):
    def test_closed_and_open_waits(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'waits'
            self.assertEqual(E.slot_wait_seconds(log), 0.0)
            log.write_text('wait 1 100.0\ngot 1 130.0\nwait 2 140.0\ngot 2 141.5\nwait 3 150.0\njunk\n')
            self.assertAlmostEqual(E.slot_wait_seconds(log, now=160.0), 30.0 + 1.5 + 10.0)


class MessageScript(unittest.TestCase):
    def test_wide_message_ids_use_native_external_command(self):
        from unittest.mock import Mock
        for msg_id in (0, 255, 256, 1093, 0x4000, 0xFFFF):
            with self.subTest(msg_id=msg_id):
                h = Mock()
                h.get_var.side_effect = [123, 0x5A5A]
                self.assertEqual(E.Harness.show_message(h, 718, msg_id), [])
                program = h.run_script.call_args.kwargs['program']
                expected = E.script_bytes(('LockAll',), ('SetVar', 0x8000, msg_id),
                                          ('MsgBoxExtern', 718, 0x8000), ('WaitButton',),
                                          ('CloseMsg',), ('SetVar', E.SENTINEL_VAR, 0x5A5A),
                                          ('ReleaseAll',), ('End',))
                self.assertEqual(program, expected)
                # Check the opcode/operands independently of script_bytes's
                # command-name mapping: 440, bank718, variable0x8000.
                self.assertEqual(program[8:14], struct.pack('<HHH', 440, 718, 0x8000))
                h.set_var.assert_called_with(E.SENTINEL_VAR, 123)

    def test_invalid_message_arguments_fail_before_emulator_mutation(self):
        from unittest.mock import Mock
        for bank, msg_id in ((718, -1), (718, 65536), (718, True),
                             (718, 1.5), (-1, 0), (0x4000, 0), (True, 0)):
            with self.subTest(bank=bank, msg_id=msg_id):
                h = Mock()
                with self.assertRaises(ValueError):
                    E.Harness.show_message(h, bank, msg_id)
                self.assertEqual(h.mock_calls, [])

    def test_completion_on_last_allowed_press_is_accepted(self):
        from unittest.mock import Mock
        h = Mock()
        h.get_var.side_effect = [123, 0, 0x5A5A]
        h.screenshot.return_value = 'page1.png'
        self.assertEqual(E.Harness.show_message(h, 718, 1093, max_pages=1), ['page1.png'])
        h.press.assert_called_once_with('A', after=150)
        h.set_var.assert_called_with(E.SENTINEL_VAR, 123)

    def test_exhaustion_and_script_failure_restore_sentinel(self):
        from unittest.mock import Mock
        h = Mock()
        h.get_var.side_effect = [123, 0, 0]
        with self.assertRaisesRegex(RuntimeError, 'did not complete'):
            E.Harness.show_message(h, 718, 1093, max_pages=1)
        h.screenshot.assert_called_once()
        h.press.assert_called_once_with('A', after=150)
        h.set_var.assert_called_with(E.SENTINEL_VAR, 123)
        h = Mock()
        h.get_var.return_value = 456
        h.run_script.side_effect = RuntimeError('injection failed')
        with self.assertRaisesRegex(RuntimeError, 'injection failed'):
            E.Harness.show_message(h, 718, 1093)
        h.screenshot.assert_not_called()
        h.set_var.assert_called_with(E.SENTINEL_VAR, 456)

    def test_invalid_page_budget_fails_before_mutation(self):
        from unittest.mock import Mock
        for pages in (0, -1, True, 1.5):
            h = Mock()
            with self.assertRaises(ValueError):
                E.Harness.show_message(h, 718, 1093, max_pages=pages)
            self.assertEqual(h.mock_calls, [])


class SaveFileEdits(unittest.TestCase):
    def _save(self, newest=0x40000):
        data = bytearray(524288)
        for counter, base in ((5, 0), (6, 0x40000)):
            if base != newest:
                counter = 4
            struct.pack_into("<II", data, base + 0x90, 6, 1)
            data[base + 0x98:base + 0x98 + 236] = _encrypted_mon(party=True)
            struct.pack_into("<IIIH", data, base + E.GENERAL_SIZE - 16, counter, E.GENERAL_SIZE, E.FOOTER_MAGIC, 0)
            crc = binascii.crc_hqx(bytes(data[base:base + E.GENERAL_SIZE - 16]), 0xFFFF)
            struct.pack_into("<H", data, base + E.GENERAL_SIZE - 2, crc)
            storage = base + E.STORAGE_OFF
            struct.pack_into("<IIIH", data, storage + E.STORAGE_SIZE - 16,
                             counter, E.STORAGE_SIZE, E.FOOTER_MAGIC, 1)
            crc = binascii.crc_hqx(data[storage:storage + E.STORAGE_SIZE - 16], 0xFFFF)
            struct.pack_into("<H", data, storage + E.STORAGE_SIZE - 2, crc)
        path = Path(tempfile.mkdtemp()) / "t.sav"
        path.write_bytes(bytes(data))
        return path

    def test_edits_newest_block_and_fixes_crc(self):
        path = self._save()
        sf = E.SaveFile(path)
        self.assertEqual(sf.base, 0x40000)
        sf.set_location(315, 17, 24)
        sf.set_flag(2423)
        out = path.with_name("o.sav")
        sf.write(out)
        again = E.SaveFile(out)
        self.assertEqual(again.base, 0x40000)
        self.assertEqual(again.location()["map"], 315)
        self.assertTrue(again.get_flag(2423))
        self.assertFalse(again.get_flag(2424))
        self.assertEqual(out.read_bytes()[:E.GENERAL_SIZE], path.read_bytes()[:E.GENERAL_SIZE])

    def test_place_player_moves_player_and_drops_npcs(self):
        path = self._save()
        data = bytearray(path.read_bytes())
        for slot, obj_id in ((0, E.PLAYER_OBJ_ID), (1, E.FOLLOWER_OBJ_ID), (2, 3)):
            a = 0x40000 + E.ARRAY_OFFSETS[E.ARR_MAP_OBJECTS] + E.MAP_OBJECT_SIZE * slot
            struct.pack_into("<I", data, a, 0xC061)
            data[a + 8] = obj_id
        crc = binascii.crc_hqx(data[0x40000:0x40000 + E.GENERAL_SIZE - 16], 0xFFFF)
        struct.pack_into("<H", data, 0x40000 + E.GENERAL_SIZE - 2, crc)
        path.write_bytes(data)
        sf = E.SaveFile(path)
        sf.place_player(315, 17, 24)
        objs = {o["id"]: o for o in sf.map_objects()}
        self.assertEqual(set(objs), {E.PLAYER_OBJ_ID, E.FOLLOWER_OBJ_ID})
        self.assertEqual((objs[E.PLAYER_OBJ_ID]["x"], objs[E.PLAYER_OBJ_ID]["z"]), (17, 24))


class Bag(unittest.TestCase):
    def test_set_pocket(self):
        path = SaveFileEdits()._save()
        sf = E.SaveFile(path)
        sf.set_pocket("medicine", [(50, 99)])
        sf.set_pocket("key", [(745, 1)])
        self.assertEqual(sf.pocket("medicine"), [(50, 99)])
        self.assertEqual(sf.pocket("key"), [(745, 1)])
        self.assertEqual(sf.pocket("items"), [])


class ExecutionHookFailures(unittest.TestCase):
    def harness(self):
        from unittest.mock import Mock
        h = E.Harness.__new__(E.Harness)
        h.emu = Mock()
        h.frame = 0
        h._per_frame = []
        h._hook_error = None
        return h

    def test_callback_failure_is_raised_after_cycle_and_stays_fatal(self):
        from unittest.mock import Mock
        h = self.harness()
        failure = AssertionError('bad printer state')
        callback = Mock(side_effect=failure)
        frame = Mock()
        h.on_frame(frame)
        h.on_exec(0x02020A1C, callback)
        hook = h.emu.memory.register_exec.call_args.args[1]
        h.emu.cycle.side_effect = lambda **kw: hook(0x02020A1C, 2)
        with self.assertRaisesRegex(RuntimeError, '0x02020a1c') as caught:
            h.step(3)
        self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual(h.emu.cycle.call_count, 1)
        frame.assert_not_called()
        # A caller cannot accidentally continue from a failed measurement.
        with self.assertRaises(RuntimeError):
            h.step(1)
        self.assertEqual(h.emu.cycle.call_count, 1)

    def test_first_callback_failure_wins_and_later_hooks_do_not_mutate_state(self):
        from unittest.mock import Mock
        h = self.harness()
        failure = ValueError('first failure')
        h.on_exec(0x02020A1C, Mock(side_effect=failure))
        first = h.emu.memory.register_exec.call_args.args[1]
        second_fn = Mock()
        h.on_exec(0x02002680, second_fn)
        second = h.emu.memory.register_exec.call_args.args[1]
        first(0, 2)  # must not throw across the C boundary
        second(0, 2)
        second_fn.assert_not_called()
        with self.assertRaises(RuntimeError) as caught:
            h.step()
        self.assertIs(caught.exception.__cause__, failure)
        h.emu.cycle.assert_not_called()

    def test_success_and_unregister_keep_native_hook_api(self):
        from unittest.mock import Mock
        h = self.harness()
        fn = Mock()
        h.on_exec(0x02020A1C, fn)
        hook = h.emu.memory.register_exec.call_args.args[1]
        h.emu.cycle.side_effect = lambda **kw: hook(0, 2)
        h.step(2)
        self.assertEqual(h.frame, 2)
        self.assertEqual(fn.call_count, 2)
        fn.assert_called_with(h)
        h.on_exec(0x02020A1C, None)
        h.emu.memory.register_exec.assert_called_with(0x02020A1C, None)


class HookOwnershipAndInput(unittest.TestCase):
    """Measurement hooks cannot be replaced silently; every press() is a real press edge."""

    def harness(self):
        from unittest.mock import Mock
        h = E.Harness.__new__(E.Harness)
        h.emu = Mock()
        h.frame = 0
        h._per_frame = []
        h._hook_error = None
        h._held = set()
        h._keys = {k: i for i, k in enumerate(E.KEYS)}
        h._keymask = lambda k: 1 << k
        h.emu.cycle.side_effect = lambda **kw: None
        return h

    def test_exclusive_hook_cannot_be_replaced_silently(self):
        h = self.harness()
        h.on_exec(0x02002680, lambda h: None, exclusive=True)
        with self.assertRaisesRegex(ValueError, "0x02002680"):
            h.on_exec(0x02002680, lambda h: None)
        h.on_exec(0x02002680, lambda h: None, replace=True)
        with self.assertRaises(ValueError):       # still exclusive after a deliberate replacement
            h.on_exec(0x02002680, lambda h: None)
        h.on_exec(0x02002680, None)                # unregistering releases the address
        h.on_exec(0x02002680, lambda h: None)

    def test_exclusive_registration_over_an_existing_hook_fails(self):
        h = self.harness()
        h.on_exec(0x0201B33C, lambda h: None)
        with self.assertRaises(ValueError):
            h.on_exec(0x0201B33C, lambda h: None, exclusive=True)
        h.on_exec(0x0201B33C, lambda h: None)      # ordinary hooks keep the old replace behaviour

    def test_press_after_release_in_the_same_frame_leaves_the_key_up_first(self):
        h = self.harness()
        h.hold("A")
        h.step(5)
        h.release()
        events = []
        h.emu.input.keypad_add_key.side_effect = lambda m: events.append(("down", h.frame))
        h.emu.input.keypad_rm_key.side_effect = lambda m: events.append(("up", h.frame))
        h.press("A", frames=2)
        self.assertEqual(events, [("down", 6), ("up", 8)])

    def test_pressing_a_held_key_is_an_error(self):
        h = self.harness()
        h.hold("A")
        with self.assertRaisesRegex(ValueError, "held"):
            h.press("A")
        h.press("B", after=1)                      # other keys can still be pressed while A is held
        self.assertEqual(h.frame, 7)


class ChildProcesses(unittest.TestCase):
    """Process hygiene helpers (no emulator): ps parsing for `cleanup`, timeout verdicts."""

    def test_parse_ps(self):
        out = "\n".join([
            "  101     1 04:00:01 /x/.venv/bin/python /x/work/tools/emu_harness.py calendar --child battle@k:day",
            "  102   100    00:10 /x/.venv/bin/python /x/work/tools/emu_harness.py sweeps --sweep trainers",
            "  103   100    00:01 python -m unittest work/tools/test_emu_harness.py",
            "  104   100    00:01 vim work/tools/emu_harness.py",
            "  105   100    00:01 /x/.venv/bin/python work/tools/emu_harness.py cleanup --kill",
            "  106   100    00:01 /x/.venv/bin/python work/tools/emu_harness.py suite"])
        rows = E.parse_ps(out, self_pid=106)
        self.assertEqual([r["pid"] for r in rows], [101, 102])
        self.assertEqual([r["orphan"] for r in rows], [True, False])

    def test_timeout_verdicts(self):
        self.assertEqual(E.child_error(E.ChildTimeout("timeout after 901 s"))["verdict"], "timeout")
        self.assertEqual(E.child_error(RuntimeError("child failed"))["verdict"], "error")
        self.assertTrue(E.timed_out({"verdict": "timeout"}))
        self.assertTrue(E.timed_out({"flee": {"verdict": "ok"}, "lose": {"verdict": "timeout", "error": "x"}}))
        self.assertFalse(E.timed_out({"flee": {"verdict": "ok"}, "lose": {"flag": 1}}))


if __name__ == "__main__":
    unittest.main()
