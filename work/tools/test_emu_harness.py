"""Unit tests for emu_harness's pure parts (no emulator, no ROM, no save fixtures)."""
import binascii
import json
import random
import struct
import tempfile
import unittest
from pathlib import Path

import emu_harness as E


def _encrypted_mon(seed=1, species=201, item=0, form=0):
    rnd = random.Random(seed)
    raw = bytearray(rnd.getrandbits(8) for _ in range(136))
    struct.pack_into("<IHH", raw, 0, rnd.getrandbits(32), 0, 0)
    return E.encode_pokemon(bytes(raw), species=species, item=item, form=form)


class PokemonCodec(unittest.TestCase):
    def test_roundtrip_and_checksum(self):
        for seed in range(30):
            raw = _encrypted_mon(seed, species=200 + seed, item=seed, form=seed % 28)
            mon = E.decode_pokemon(raw)
            self.assertTrue(mon["checksum_ok"])
            self.assertEqual((mon["species"], mon["item"], mon["form"]), (200 + seed, seed, seed % 28))

    def test_moves_roundtrip(self):
        raw = E.encode_pokemon(_encrypted_mon(4), moves=[85, 86, 87, 98], pp=[15, 20, 10, 30])
        self.assertTrue(E.decode_pokemon(raw)["checksum_ok"])
        order = E.BLOCK_ORDERS[((struct.unpack_from("<I", raw)[0] & 0x3E000) >> 13) % 24]
        checksum = struct.unpack_from("<H", raw, 6)[0]
        plain = struct.pack("<64H", *[w ^ k for w, k in zip(struct.unpack_from("<64H", raw, 8),
                                                              E._prng_stream(checksum, 64))])
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
            struct.pack_into("<IIIH", data, base + E.GENERAL_SIZE - 16, counter, E.GENERAL_SIZE, E.FOOTER_MAGIC, 0)
            crc = binascii.crc_hqx(bytes(data[base:base + E.GENERAL_SIZE - 16]), 0xFFFF)
            struct.pack_into("<H", data, base + E.GENERAL_SIZE - 2, crc)
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
        sf = E.SaveFile(path)
        for slot, obj_id in ((0, E.PLAYER_OBJ_ID), (1, E.FOLLOWER_OBJ_ID), (2, 3)):
            a = sf._a(E.ARR_MAP_OBJECTS, E.MAP_OBJECT_SIZE * slot)
            struct.pack_into("<I", sf.data, a, 0xC061)
            sf.data[a + 8] = obj_id
        sf.place_player(315, 17, 24)
        objs = {o["id"]: o for o in sf.map_objects()}
        self.assertEqual(set(objs), {E.PLAYER_OBJ_ID, E.FOLLOWER_OBJ_ID})
        self.assertEqual((objs[E.PLAYER_OBJ_ID]["x"], objs[E.PLAYER_OBJ_ID]["z"]), (17, 24))


class ScreenDiffAndBag(unittest.TestCase):
    def test_screen_diff(self):
        from PIL import Image
        a = Image.new("RGB", (10, 10), "white")
        b = a.copy()
        self.assertEqual(E.screen_diff(a, b)[0], 0)
        b.putpixel((0, 0), (0, 0, 0))
        self.assertAlmostEqual(E.screen_diff(a, b)[0], 0.01)
        self.assertEqual(E.screen_diff(a, b, box=(5, 5, 10, 10))[0], 0)

    def test_set_pocket(self):
        path = SaveFileEdits()._save()
        sf = E.SaveFile(path)
        sf.set_pocket("medicine", [(50, 99)])
        sf.set_pocket("key", [(745, 1)])
        self.assertEqual(sf.pocket("medicine"), [(50, 99)])
        self.assertEqual(sf.pocket("key"), [(745, 1)])
        self.assertEqual(sf.pocket("items"), [])


class SkittyScene(unittest.TestCase):
    """emu_skitty's pure parts (D-0582)."""

    def setUp(self):
        import emu_skitty
        self.S = emu_skitty

    def test_goto_and_after_battle_offset(self):
        S = self.S
        body = [E.script_bytes(("End",))] * 4
        battle = E.script_bytes(("LockAll",), ("TrainerBattle", 276, 277, 0, 0), ("CheckBattleWon", 0x800C),
                                ("CompareVarToValue", 0x800C, 0))
        tail = E.script_bytes(("SetVar", 16576, 1), ("ReleaseAll",), ("End",))
        lose = E.script_bytes(("End",))
        script5 = battle + E.script_bytes(("GoToIf", 1, len(tail))) + tail + lose
        header_len = 5 * 4 + 2
        offs, pos = [], header_len
        for chunk in body + [script5]:
            offs.append(pos)
            pos += len(chunk)
        header = b"".join(struct.pack("<i", o - (4 * k + 4)) for k, o in enumerate(offs)) + b"\x13\xfd"
        data = header + b"".join(body) + script5
        start = offs[4]
        target, s5 = S.after_battle_offset(data)
        self.assertEqual(s5, start)
        self.assertEqual(target, start + len(battle) + 7)
        g = S.goto_bytes(start, target)
        self.assertEqual(struct.unpack_from("<Hi", g), (22, target - start - 6))

    def test_species_for_sprite_and_text(self):
        import collections
        S = self.S
        table = {761: collections.Counter({300: 4}), 430: collections.Counter({3: 22, 9: 1})}
        self.assertEqual(S.species_for_sprite(table, 761), 300)
        self.assertEqual(S.species_for_sprite(table, 430), 3)
        self.assertIsNone(S.species_for_sprite(table, 902))
        lines = ["x"] * 49
        for i in S.SKITTY_LINES:
            lines[i] = "Go, Skitty!"
        for i in S.CRY_LINES:
            lines[i] = "Skitty: Skiiii-ty!"
        self.assertEqual(S.check_text(lines, "en"), [])
        lines[19], lines[5] = "Skitty: Gla... meo...", "What's wrong, Glameow?"
        self.assertEqual([i for i, _ in S.check_text(lines, "en")], [5, 19])
        zh = ["向尾喵"] * 49
        zh[48] = "卷尾猫"
        self.assertEqual(S.check_text(zh, "cn"), [])

    def test_battle_cries(self):
        ev = [{"t": "cry", "species": 300}, {"t": "trainer_battle"}, {"t": "cry", "species": 53},
              {"t": "msg"}, {"t": "cry", "species": 300}]
        self.assertEqual(self.S.battle_cries(ev), [53, 300])

    def _fake(self, lo, mem):
        class H:
            def read(self, addr, n):
                return bytes(mem[addr - lo:addr - lo + n])
        return H()

    def test_live_objects(self):
        S, lo = self.S, 0x02200000
        mem = bytearray(0x4000)
        base = 0x1004
        for k, (oid, spr, script) in enumerate([(1, 325, 3), (2, 761, 7), (3, 323, 4)]):
            a = base + k * S.MAP_OBJECT_SIZE
            struct.pack_into("<5I", mem, a, 0xC021, 0, oid, 16, spr)
            struct.pack_into("<2I", mem, a + 0x1C, 1163, script)
            struct.pack_into("<3i", mem, a + 0x64, 1396 + k, 4, 232)
        struct.pack_into("<5I", mem, 0x3000, 0xC021, 0, 9, 16, 1)   # a lone record: not in an array
        objs = S.live_objects(self._fake(lo, mem), 16, lo, lo + len(mem))
        self.assertEqual(sorted(objs), [1, 2, 3])
        self.assertEqual((objs[2]["sprite"], objs[2]["script"], objs[2]["x"]), (761, 7, 1397))
        self.assertEqual(S.live_objects(self._fake(lo, mem), 17, lo, lo + len(mem)), {})

    def test_find_parties(self):
        S, lo = self.S, 0x02200000
        mem = bytearray(0x4000)
        a = 0x200
        struct.pack_into("<2I", mem, a, 6, 3)
        for k, sp in enumerate((300, 113, 414)):
            mon = _encrypted_mon(10 + k, species=sp) + bytes(100)
            mem[a + 8 + 236 * k:a + 8 + 236 * (k + 1)] = mon
        struct.pack_into("<2I", mem, 0x2000, 6, 2)                    # count 2 but garbage: rejected
        got = S.find_parties(self._fake(lo, mem), lo, lo + len(mem))
        self.assertEqual([[m["species"] for m in p["mons"]] for p in got], [[300, 113, 414]])
        self.assertEqual(got[0]["addr"], hex(lo + a))


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


class Guide0107(unittest.TestCase):
    """emu_guide0107: the pure parts (registry, judges, Pokemon field decoder)."""

    def setUp(self):
        import emu_guide0107
        self.G = emu_guide0107

    def test_registry(self):
        for name, (fn, variants, judge) in self.G.CASES.items():
            self.assertTrue(callable(fn), name)
            self.assertEqual(variants is None, judge is None, name)
        self.assertTrue(set(self.G.SUITE_EXPECT) <= set(self.G.CASES))

    def test_judges(self):
        G = self.G
        monday = {h: {"groups": "AD" if 7 <= int(h) <= 18 else "EH", "scrcmd_522": int(h)} for h in G.MONDAY_HOURS}
        self.assertEqual(G.judge_monday(monday), "confirmed")
        monday["6"]["groups"] = "AD"
        self.assertEqual(G.judge_monday(monday), "contradicted")
        corner = {"real": {"field_back": False, "map_after": 342},
                  "canlose": {"field_back": True, "map_after": 342},
                  "whiteout": {"field_back": True, "map_after": 501}}
        self.assertEqual(G.judge_corner_kid(corner), "contradicted")
        corner["whiteout"]["map_after"] = 342          # a broken control makes the run inconclusive
        self.assertEqual(G.judge_corner_kid(corner), "blocked")
        koga = {"17": {"koga_visible": False}, "18": {"koga_visible": True, "koga_pos": [17, 10], "talk_msg": 12},
                "20": {"koga_visible": True}, "21": {"koga_visible": False}}
        self.assertEqual(G.judge_koga(koga), "confirmed")

    def test_mon_details(self):
        raw = bytearray(E.encode_pokemon(_encrypted_mon(7, species=18), moves=[28, 16, 98, 18]))
        raw += bytes(236 - len(raw))
        m = self.G.mon_details(bytes(raw))
        self.assertEqual((m["species"], m["moves"]), (18, [28, 16, 98, 18]))
        self.assertEqual(len(m["ivs"]), 6)


class Guide0813(unittest.TestCase):
    """emu_guide0813: the pure parts (registry, judges, helpers)."""

    def setUp(self):
        import emu_guide0813
        self.G = emu_guide0813

    def test_registry(self):
        G = self.G
        for name, (fn, variants, judge) in G.CASES.items():
            self.assertTrue(callable(fn), name)
            if judge is not None:
                self.assertIsNotNone(variants, name)
        self.assertTrue(set(G.SUITE_EXPECT) <= set(G.CASES))
        for c, vs in G.SUITE_VARIANTS.items():
            self.assertTrue(set(vs) <= set(G.CASES[c][1]), c)
        self.assertEqual(G.cmd_names()[2], "End")
        self.assertEqual(G.weekday_clock(4).isoweekday(), 4)        # Thursday
        self.assertEqual(G.weekday_clock(0).isoweekday() % 7, 0)    # Sunday

    def test_empty_mon(self):
        raw = self.G.empty_mon()
        self.assertEqual(len(raw), 236)
        m = E.decode_party_pokemon(raw)
        self.assertEqual(m["species"], 0)
        self.assertTrue(m["checksum_ok"])
        self.assertEqual(self.G.decrypted_blocks(raw), bytes(128))

    def test_judges(self):
        G = self.G
        died = {"gave_ribbon": True, "bad_ops": [{"op": 2009}], "window_after": True, "walks": True,
                "x_menu_opens": True, "save_prompt": True}
        ctrl = {"bad_ops": [], "save_prompt": True, "window_after": False}
        self.assertEqual(G.judge_ribbon({"arthur": died, "arthur_control": ctrl}), "contradicted")
        self.assertEqual(G.judge_ribbon({"arthur": dict(died, walks=False, x_menu_opens=False),
                                         "arthur_control": ctrl}), "confirmed")
        quiz = {"b": {"flag_287": False, "msgs": [3, 125], "menu_values": {"375": [3]}},
                "wrong": {"flag_287": False, "msgs": [125]}}
        self.assertEqual(G.judge_radio_quiz(quiz), "contradicted")
        quiz["b"].update(flag_287=True, msgs=[126])
        self.assertEqual(G.judge_radio_quiz(quiz), "confirmed")
        dance = {"tue01": {"movewarp": True}, "tue05": {"movewarp": False}, "mon22set": {"movewarp": False},
                 "daychange": {"movewarp_after": True, "flag_2741_after": False}}
        self.assertEqual(G.judge_dance(dance), "confirmed")
        wf = {"one": {"battle_menu": True, "both_teams_in_ram": [[1], [2]], "turn": "stuck: x"},
              "full": {"turn": "menu"}}
        self.assertEqual(G.judge_white_flute(wf), "contradicted")
        wf["full"]["turn"] = "stuck: y"                       # a broken control: inconclusive
        self.assertEqual(G.judge_white_flute(wf), "blocked")


class Calendar(unittest.TestCase):
    """emu_calendar: the pure parts (periods, buffer decoding, stats, registry)."""

    def setUp(self):
        import emu_calendar
        self.C = emu_calendar

    def test_periods(self):
        C = self.C
        self.assertEqual(C.periods_of(0), ("morning", "day", "night"))
        self.assertEqual(C.periods_of(1), ("morning",))
        self.assertEqual(C.periods_of(2), ("night",))
        self.assertEqual([C.wild_period(h) for h in (3, 4, 9, 10, 19, 20, 23)],
                         ["night", "morning", "morning", "day", "day", "night", "night"])
        self.assertEqual(C.battle_time("night"), (22, 0))
        self.assertEqual(C.battle_time("03:59"), (3, 59))

    def test_decode_buffer(self):
        buf = bytearray(0xC4)
        buf[0], buf[19] = 25, 50
        struct.pack_into("<H", buf, 0x2A, 720)
        struct.pack_into("<H", buf, 0x5A, 720 | 1 << 11)
        d = self.C.decode_buffer(bytes(buf))
        self.assertEqual((d["walk_rate"], d["slot11_level"]), (25, 50))
        self.assertEqual((d["slot11"]["morning"]["species"], d["slot11"]["night"]["form"]), (720, 1))
        self.assertEqual(d["slot11"]["day"]["species"], 0)

    def test_calc_stats(self):
        # Diancie (50/100/150/50/100/150) Lv17, Brave (2: +Atk -Spe), as observed in the emulator
        self.assertEqual(self.C.calc_stats([50, 100, 150, 50, 100, 150], 17, [13, 0, 18, 29, 8, 11],
                                           [0] * 6, 2), [46, 42, 59, 23, 40, 57])

    def test_registry(self):
        C = self.C
        for name, (fn, variants) in C.CASES.items():
            self.assertTrue(callable(fn), name)
        for v in C.BATTLES:
            name, _, period = v.partition(":")
            self.assertIn(name, C.ENTRIES)
            C.battle_time(period)


class HackBugs(unittest.TestCase):
    """emu_hackbugs: the pure parts (registry, judges, the fateful-bit edit through the codec)."""

    def setUp(self):
        import emu_hackbugs
        self.H = emu_hackbugs

    def test_registry(self):
        H = self.H
        for name, (fn, variants, judge, records) in H.CASES.items():
            self.assertTrue(callable(fn), name)
            self.assertTrue(records.startswith("D-"), name)
            if judge is not None:
                self.assertIsNotNone(variants, name)
        self.assertTrue(set(H.SUITE_EXPECT) <= set(H.CASES))
        for c, vs in H.SUITE_VARIANTS.items():
            self.assertTrue(set(vs) <= set(H.CASES[c][1]), c)

    def test_judges(self):
        H = self.H
        tut = {}
        for name, (_, _, _, _, _, _, m3, m4, _) in H.TUTORS.items():
            tut[name + "3"] = {"learned": [m3], "expected_move": m3, "fee_taken": 3 if name == "hans" else 1}
            tut[name + "4"] = {"learned": [m4], "expected_move": m4, "fee_taken": 0 if name == "hans" else 1}
        self.assertEqual(H.judge_tutor(tut), "confirmed")
        tut["hans4"]["fee_taken"] = 3
        self.assertEqual(json.loads(H.judge_tutor(tut))["hans"], "contradicted")
        mv = {"volttackle": {"hp_before": 190, "hp_after": 190}, "doubleedge": {"hp_before": 190, "hp_after": 186},
              "thunderbolt": {"hp_before": 190, "hp_after": 190},
              "blastburn": {"turns": [{"frames": 510, "result": "menu"}]},
              "hyperbeam": {"turns": [{"frames": 861, "result": "menu"}]},
              "flamethrower": {"turns": [{"frames": 612, "result": "menu"}]}, "lunardance": {"hp_after": 319}}
        self.assertEqual(json.loads(H.judge_move(mv)),
                         {"D-1311": "user survives", "D-1318": "no recharge", "D-1319": "no recoil"})
        mv["blastburn"]["turns"][0]["result"] = "field"     # Blissey KO'd: inconclusive
        for k in ("blastburn", "hyperbeam", "flamethrower"):
            mv[k]["turns"][0].setdefault("result", "menu")
        self.assertEqual(json.loads(H.judge_move(mv))["D-1318"], "unclear")
        gw = {"exit": {"samples": [{"pos": [96, 16384, 59693]}], "walks_after": False},
              "entrance": {"path_from_south_gate_to_33_16": None, "tile_33_16": [6, True], "pos": [96, 33, 17]}}
        self.assertEqual(H.judge_gatehouse_warp(gw), "confirmed")
        self.assertEqual(H.judge_crystal_onix({"tm13_crystal": {"learned": True}, "tm11_crystal": {"learned": False}}),
                         "contradicted")

    def test_set_fateful_roundtrip(self):
        H = self.H
        raw = E.encode_pokemon(bytes(236), species=492, moves=[33, 0, 0, 0])

        class FakeH:
            def __init__(self):
                self.mem = bytearray(8 + 236) + bytearray(236 * 6)

            def array(self, _):
                return 0

            def read(self, a, n):
                return bytes(self.mem[a:a + n])

            def write(self, a, b):
                self.mem[a:a + len(b)] = b
        h = FakeH()
        h.write(8, raw)
        H.set_fateful(h, 0)
        new = h.read(8, 236)
        self.assertEqual(H.fateful(new), 1)
        self.assertEqual(E.decode_party_pokemon(new)["species"], 492)
        self.assertTrue(E.decode_party_pokemon(new)["checksum_ok"])


class VerifyHelpers(unittest.TestCase):
    """emu_verify: message ids from traced rows, MsgLog filtering, static message references (no ROM run)."""

    def test_msg_ids_and_printed(self):
        import emu_verify as V

        class Tr:
            rows = [("NPCMsg", 10, 0, 1, bytes([7, 0, 0, 0])), ("GenderMsgBox", 13, 0, 2, bytes([5, 6, 0, 0])),
                    ("WaitButton", 16, 0, 3, b"\0\0\0\0"), ("NonNPCMsg", 18, 0, 4, bytes([200, 1, 0, 0]))]
        self.assertEqual(V.msg_ids(Tr.rows[0]), [7])
        self.assertEqual(V.msg_ids(Tr.rows[1]), [5, 6])
        self.assertEqual(V.msg_ids(Tr.rows[2]), [])
        self.assertEqual(V.printed(Tr()), [7, [5, 6], 200])

    def test_msglog_read(self):
        import emu_verify as V
        ml = V.MsgLog.__new__(V.MsgLog)
        ml.rows = [(27, 816, 0, 1), (27, 816, 0, 2), (16, 3, 5, 3), (27, 2, 4, 4), (27, 816, 5, 5)]
        self.assertEqual(ml.read(), [(816, 0), (2, 4), (816, 5)])
        self.assertEqual(ml.ids(816), [0, 5])
        self.assertEqual(ml.read(816, since=2), [(816, 5)])

    def test_cases_have_records(self):
        import emu_verify as V
        for name, (fn, variants, judge, records) in V.CASES.items():
            self.assertTrue(callable(fn), name)
            self.assertTrue(records.startswith("D-"), name)
        self.assertLessEqual(set(V.SUITE_EXPECT), set(V.CASES))


class TextReadBack(unittest.TestCase):
    """emu_text (glyph parser, expected lines) and emu_sweeps (matching, judges) without a ROM."""

    def font(self):
        import emu_text as T
        f = T.Font.__new__(T.Font)
        g = {"A": (1, (0b0110, 0b1001, 0b1111, 0b1001, 0)), "B": (2, (0b1111, 0b1011, 0b0110, 0)),
             "O": (3, (0b0110, 0b1001, 0b0110, 0)), "●": (4, (0b0110, 0b1001, 0b0110, 0)), " ": (5, (0, 0, 0))}
        f.glyphs = {}
        seen = set()
        for ch in ("A", "B", "O", " ", "●"):      # the same order as Font: letters before symbols
            code, cols = g[ch]
            if (len(cols), cols) in seen and ch != " ":
                continue
            seen.add((len(cols), cols))
            f.glyphs[code] = (ch, len(cols), cols)
        f.index = {}
        for ch, w, cols in f.glyphs.values():
            f.index.setdefault(cols[0], []).append((ch, w, cols))
        for k in f.index:
            f.index[k].sort(key=lambda x: (-x[1], x[0] == " "))
        return f

    def test_parse_line(self):
        import emu_text as T
        f = self.font()
        A, B, O, S = (0b0110, 0b1001, 0b1111, 0b1001, 0), (0b1111, 0b1011, 0b0110, 0), (0b0110, 0b1001, 0b0110, 0), (0, 0, 0)
        cols = list(A + S + B + O) + [0] * 6
        self.assertEqual(T.parse_line(cols, f), ("A BO", 15, 0))           # O, not the identical ●
        bad = list(A) + [0b1111111] + list(B) + [0] * 4                     # one column no glyph starts with
        text, right, unknown = T.parse_line(bad, f)
        self.assertEqual((text, unknown), ("A" + T.UNKNOWN + "B", 1))
        self.assertEqual(T.parse_line([0] * 8, f), ("", 0, 0))

    def test_expected_lines_and_compare(self):
        import emu_text as T
        en = "{VAR:010E:0,0} {VAR:0100:1,0}{NEWLINE}wants to battle!{SCROLL}{VAR:0102:2}{COLOR:1}x{CLEAR}y"
        pages = T.expected_lines(en, {0: "Youngster", 1: "Joey"})
        self.assertEqual(pages, [["Youngster Joey", "wants to battle!"], ["\x00x", "y"]])
        ok, d = T.compare(pages, ["Youngster Joey", "wants to battle!", "Pikachux", "Pikachux", "y"])
        self.assertTrue(ok, d)                                              # {CLEAR} repeats a line
        self.assertFalse(T.compare(pages, ["Youngster Joey", "wants to battle", "Pikachux", "y"])[0])

    def test_ability_field(self):
        raw = E.encode_pokemon(_encrypted_mon(7), ability=311)
        order = E.BLOCK_ORDERS[((struct.unpack_from("<I", raw)[0] & 0x3E000) >> 13) % 24]
        checksum = struct.unpack_from("<H", raw, 6)[0]
        plain = struct.pack("<64H", *[w ^ k for w, k in zip(struct.unpack_from("<64H", raw, 8),
                                                              E._prng_stream(checksum, 64))])
        self.assertEqual(struct.unpack_from("<H", plain, 32 * order.index("B") + 0x1A)[0], 311)
        self.assertTrue(E.decode_pokemon(raw)["checksum_ok"])

    def test_sweep_helpers(self):
        import emu_sweeps as S
        self.assertTrue(S._prefix_match("\x00 grew to Lv. \x00!", "Butterfly1 grew to L"))
        self.assertTrue(S._prefix_match("Should another move be forgotten", "Should another move be forg"))
        self.assertFalse(S._prefix_match("Should another move", "Shall"))
        self.assertEqual(S.ICON_TAIL.sub("", "What will Ditto do?          �"), "What will Ditto do?")
        self.assertEqual(S.parse_ids("3-5,9", [1, 3, 4, 5, 9, 10]), [3, 4, 5, 9])
        self.assertEqual([len(c) for c in S.chunks(list(range(10)), 3)], [4, 4, 2])
        self.assertTrue(set(S.SUITE_SUBSETS) <= set(S.SWEEPS))
        for name, (lead, foe, plan) in S.BATTLES.items():
            self.assertTrue(plan and len(lead) == 6 and len(foe) == 2, name)


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


class OpenPoints(unittest.TestCase):
    """emu_open's pure helpers: experience edit, padded movesets, battle message grouping, judges."""

    def test_exp_roundtrip(self):
        import emu_open as O
        raw = O.with_exp(_encrypted_mon(7, species=744), 15624)
        self.assertEqual(O.exp_of(raw), 15624)
        mon = E.decode_pokemon(raw)
        self.assertTrue(mon["checksum_ok"])
        self.assertEqual(mon["species"], 744)

    def test_moveset_pads(self):
        import emu_open as O
        self.assertEqual(O.moveset([150], [40]), {"moves": [150, 0, 0, 0], "pp": [40, 0, 0, 0]})

    def test_battle_events_and_judges(self):
        import emu_open as O

        class ML:
            rows = [(277, 1, 2179, 1), (27, 739, 150, 2), (277, 2, 99, 3),
                    (277, 1, 2180, 4), (27, 739, 55, 5), (277, 2, 74, 6),
                    (277, 1, 2179, 7), (27, 739, 449, 8), (277, 1, 293, 9),
                    (277, 1, 2179, 10), (27, 739, 449, 11), (277, 2, 74, 12)]
        events, reads = O.battle_events(ML())
        self.assertEqual([(e["side"], e["move"], e["effect"]) for e in events],
                         [("player", 150, "normal"), ("wild", 55, "super"), ("player", 449, "missed"),
                          ("player", 449, "super")])
        res = {"events": events, "expected_probe": ("super", "not_very"), "expected_judgment": ("super", "not_very")}
        self.assertEqual(O.judge_arceus(res), "plate_type")
        self.assertEqual(O.judge_rockruff({"after": {"species": 745, "form": 0}}), "midday")
        self.assertEqual(O.judge_rockruff({"after": {"species": 744, "form": 0}}), "no_evolution")


if __name__ == "__main__":
    unittest.main()
