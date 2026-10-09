"""Tests for melonds.py (the ctypes wrapper of libmelonds_shim) and the Harness's melonDS adapter.

The library tests skip when the shim is not built (work/tools/melonds_shim/build.py); the boot test also needs
the Chinese ROM (work/rom/origin_v4.0.3_cn.nds). The adapter tests use a fake console and always run."""
import datetime
import unittest
from unittest import mock

import emu_harness as E
import melonds

HAVE_LIB = melonds.available()
ROM_CN = E.DEF_ROM_CN


class KeyLayout(unittest.TestCase):
    def test_bits_follow_the_core_order(self):
        # melonDS NDS::SetKeyMask: bits 0-9 = KEYINPUT (A B SELECT START RIGHT LEFT UP DOWN R L), 10-11 = X Y
        self.assertEqual(melonds.KEYS, E.KEYS)
        self.assertEqual([melonds.KEY_BITS[k] for k in melonds.KEYS], [1 << i for i in range(12)])

    def test_missing_library_is_reported(self):
        with self.assertRaisesRegex(FileNotFoundError, "build.py"):
            melonds.load_library("/nonexistent/libmelonds_shim.dylib")


@unittest.skipUnless(HAVE_LIB, "libmelonds_shim not built (work/tools/melonds_shim/build.py)")
class Library(unittest.TestCase):
    def test_abi_and_version(self):
        lib = melonds.load_library()
        self.assertEqual(lib.mds_abi_version(), melonds.ABI_VERSION)
        self.assertEqual(lib.mds_melonds_version(), b"1.1")

    def test_main_ram_roundtrip_and_mirror(self):
        with melonds.MelonDS() as m:
            m.write(0x02001000, b"\x12\x34\x56\x78")
            self.assertEqual(m.u32(0x02001000), 0x78563412)
            self.assertEqual(m.read_main_ram(0x1000, 4), b"\x12\x34\x56\x78")
            m.write_main_ram(0x2000, b"\xAB")
            self.assertEqual(m.u8(0x02002000), 0xAB)
            self.assertEqual(m.u8(0x02402000), 0xAB)     # 4 MB main RAM is mirrored
            m.w16(0x02003000, 0xBEEF)
            self.assertEqual(m.u16(0x02003000), 0xBEEF)

    def test_watch_arguments(self):
        with melonds.MelonDS() as m:
            with self.assertRaises(ValueError):
                m.watch(0x02000000, 0)
            m.watch(0x02000000, 4, read=True, write=True)
            self.assertEqual(m.watch_hits(), [])
            m.clear_watches()

    def test_regs_shape(self):
        with melonds.MelonDS() as m:
            r = m.regs()
            self.assertEqual(len(r["r"]), 16)
            self.assertEqual(set(r), {"r", "cpsr", "mode", "thumb", "abt", "svc", "irq", "und", "cur_instr",
                                      "halted"})
            self.assertEqual(m.exceptions()["data_aborts"], 0)


@unittest.skipUnless(HAVE_LIB and ROM_CN.is_file(), "needs libmelonds_shim and work/rom/origin_v4.0.3_cn.nds")
class Boot(unittest.TestCase):
    def test_boot_screenshot_savestate(self):
        with melonds.MelonDS() as m:
            m.load_rom(ROM_CN, rtc=datetime.datetime(2026, 10, 9, 12))
            m.run(30)
            self.assertEqual(m.frame, 30)
            self.assertEqual(m.read(0x027FFE0C, 4), b"IPKJ")        # game code in the header copy (main RAM)
            img = m.screenshot()
            self.assertEqual(img.size, (256, 384))
            state = m.save_state()
            m.run(20)
            after = m.read(0x02000000, 0x10000)
            m.load_state(state)
            m.run(20)
            self.assertEqual(m.read(0x02000000, 0x10000), after)    # emulation from a state is deterministic
            self.assertEqual(m.exceptions()["data_aborts"], 0)
            self.assertFalse(m.in_abort_mode())


@unittest.skipUnless(HAVE_LIB and ROM_CN.is_file(), "needs libmelonds_shim and work/rom/origin_v4.0.3_cn.nds")
class Determinism(unittest.TestCase):
    def test_two_consoles_on_a_dirty_heap_agree(self):
        """The core leaves some members uninitialised; the shim zeroes the console before construction, so a
        console made on a heap full of garbage (and of a destroyed console's state) runs like any other."""
        import ctypes
        import hashlib
        libc = ctypes.CDLL(None)
        libc.malloc.restype = ctypes.c_void_p
        libc.malloc.argtypes = [ctypes.c_size_t]
        libc.free.argtypes = [ctypes.c_void_p]
        blocks = []
        for n in (1 << 20, 4 << 20, 16 << 20) * 3:
            p = libc.malloc(n)
            ctypes.memset(p, 0xA5, n)
            blocks.append(p)
        with melonds.MelonDS() as old:
            old.load_rom(ROM_CN)
            old.run(60)
        for p in blocks:
            libc.free(p)
        runs = []
        consoles = [melonds.MelonDS(), melonds.MelonDS()]
        try:
            for m in consoles:
                m.load_rom(ROM_CN, rtc=datetime.datetime(2026, 10, 9, 12))
                first = hashlib.sha256(m.save_state()).hexdigest()
                m.run(200)
                runs.append((first, hashlib.sha256(m.save_state()).hexdigest()))
        finally:
            for m in consoles:
                m.close()
        self.assertEqual(runs[0], runs[1])

    def test_closed_console_refuses_calls(self):
        m = melonds.MelonDS()
        m.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            m.run(1)


class HangCases(unittest.TestCase):
    def test_save_case_arguments(self):
        import argparse

        import emu_hang
        a = argparse.Namespace(walk="left, RIGHT", goal="967,270", fault_pc=0x02024528)
        self.assertEqual(emu_hang.save_case(a), {"steps": ("LEFT", "RIGHT"), "goal": (967, 270),
                                                 "fault_pc": 0x02024528})
        with self.assertRaises(SystemExit):
            emu_hang.save_case(argparse.Namespace(walk="NORTH", goal=None, fault_pc=None))

    def test_judge_without_goal(self):
        import emu_hang
        case = {"steps": (), "goal": None, "fault_pc": None}
        hung = {"hung": True, "reached_goal": False, "abort": None}
        self.assertEqual(emu_hang.judge(hung, "hang", case), [])
        alive = {"hung": False, "reached_goal": True, "screen_changed": True, "exceptions": {"data_aborts": 0}}
        self.assertEqual(emu_hang.judge(alive, "pass", case), [])
        self.assertTrue(emu_hang.judge(alive, "hang", case))


class HangCaseTable(unittest.TestCase):
    def test_freeze_cases_are_hang_cases(self):
        import emu_hang
        import emu_layer
        for name in emu_layer.FREEZE_CASES:
            case = emu_hang.CASES[name]
            self.assertTrue(case["fault_pc"] and case["steps"] and case["goal"], name)
            self.assertEqual(len(case["sav_sha256"]), 64, name)

    def test_route22_walk_ends_beside_misty(self):
        import emu_hang
        case = emu_hang.CASES["follower_route22"]
        moves = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
        x, y = case["start"][1:]
        trail = []
        for d in case["steps"]:
            x, y = x + moves[d][0], y + moves[d][1]
            trail.append((x, y))
        self.assertEqual(trail[-1], case["goal"])
        self.assertIn((992, 267), trail)          # into Viridian City (x 992+) and back: Route 22 loads Misty
        self.assertEqual(trail[-2], (968, 270))   # beside Misty (969,270), then one step away
        self.assertEqual(case["flags"][1363], False)

    def test_prepare_save_teleports_with_height_and_flags(self):
        import struct
        import tempfile

        import binascii

        import emu_hang
        from test_emu_harness import SaveFileEdits
        path = SaveFileEdits()._save()
        sf = E.SaveFile(path)
        sf.set_flag(1363)
        data = bytearray(sf.data)             # a saved player object in slot 0 (test fixture bytes)
        a = sf.base + 0x2480
        struct.pack_into("<I", data, a, 0xC061)
        data[a + 8] = E.PLAYER_OBJ_ID
        end = sf.base + E.GENERAL_SIZE - 16
        struct.pack_into("<H", data, end + 14, binascii.crc_hqx(bytes(data[sf.base:end]), 0xFFFF))
        path.write_bytes(bytes(data))
        case = {"teleport": (27, 988, 267, "RIGHT"), "height": 10, "flags": {1363: False, 1302: True}}
        out = E.SaveFile(emu_hang.prepare_save(E, path, case, None, tempfile.mkdtemp()))
        self.assertEqual(out.location()["map"], 27)
        a = out.base + 0x2480
        self.assertEqual(struct.unpack_from("<6h", out.data, a + 0x20), (988, 10, 267, 988, 10, 267))
        self.assertEqual(struct.unpack_from("<i", out.data, a + 0x2C)[0], 10 * 8 * 0x1000)
        self.assertFalse(out.get_flag(1363))
        self.assertTrue(out.get_flag(1302))


class AbortRecord(unittest.TestCase):
    def test_r0_is_masked(self):
        import emu_hang
        ab = {"cpsr": 0x60000097, "abort_lr": 0x0202469E, "fault_pc": 0x02024696, "r": [0xB] + list(range(1, 16))}
        rec = emu_hang.abort_record(ab)
        self.assertIsNone(rec["r"][0])
        self.assertEqual(rec["r"][1], "0x00000001")
        self.assertEqual(rec["fault_pc"], "0x02024696")
        self.assertEqual(rec, emu_hang.abort_record(ab | {"r": [0x5] + list(range(1, 16))}))
        self.assertIn("r0_note", rec)


class FixScenariosBackend(unittest.TestCase):
    def test_pin_backend_overrides_a_stray_choice(self):
        import emu_fixes
        with mock.patch.dict("os.environ", {"EMU_HARNESS_EMULATOR": "melonds"}):
            with mock.patch("sys.stderr"):
                emu_fixes.pin_backend()
            self.assertEqual(E.default_emulator(), "desmume")
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("EMU_HARNESS_EMULATOR", None)
            emu_fixes.pin_backend()
            self.assertEqual(os.environ["EMU_HARNESS_EMULATOR"], "desmume")


class FakeMelon:
    """Just enough of melonds.MelonDS for the Harness adapter."""

    def __init__(self):
        self.ram = bytearray(0x100)
        self.held = set()
        self.mode = 0x1F
        self.r = list(range(16))
        self.aborts = 0

    def read(self, a, n):
        return bytes(self.ram[a:a + n])

    def u8(self, a):
        return self.ram[a]

    def u16(self, a):
        return int.from_bytes(self.ram[a:a + 2], "little")

    def u32(self, a):
        return int.from_bytes(self.ram[a:a + 4], "little")

    def w8(self, a, v):
        self.ram[a] = v

    def w16(self, a, v):
        self.ram[a:a + 2] = v.to_bytes(2, "little")

    def w32(self, a, v):
        self.ram[a:a + 4] = v.to_bytes(4, "little")

    def hold(self, k):
        self.held.add(k)

    def release(self, k):
        self.held.discard(k)

    def regs(self):
        return {"r": self.r, "cpsr": 0x60000000 | self.mode, "mode": self.mode, "abt": [0, 0x0202469E, 0]}

    def exceptions(self):
        return {"data_aborts": self.aborts, "first_data_abort_frame": 7, "prefetch_aborts": 0, "undefined": 0}


class Adapter(unittest.TestCase):
    def harness(self, fake):
        h = E.Harness.__new__(E.Harness)
        h.emulator = "melonds"
        h.melon = fake
        h.emu = mock.Mock()
        h.emu.memory = E._MelonMemory(fake)
        h.emu.input = E._MelonInput(fake)
        h.mem = h.emu.memory
        h.reg = E._MelonRegs(fake)
        h._keymask = lambda k: k
        h._keys = {k: k for k in E.KEYS}
        h.frame = 0
        h._per_frame = []
        h._hook_error = None
        h._held = set()
        return h

    def test_memory_and_keys(self):
        fake = FakeMelon()
        h = self.harness(fake)
        h.w32(0x10, 0x11223344)
        self.assertEqual(h.u32(0x10), 0x11223344)
        self.assertEqual(h.read(0x10, 2), b"\x44\x33")
        h.hold("A", "UP")
        self.assertEqual(fake.held, {"A", "UP"})
        h.release()
        self.assertEqual(fake.held, set())
        self.assertEqual(h.reg.pc, 15)

    def test_exec_hooks_are_refused(self):
        h = self.harness(FakeMelon())
        with self.assertRaisesRegex(NotImplementedError, "watch"):
            h.on_exec(0x02000000, lambda h: None)
        self.assertFalse(getattr(h, "_hooks", {}))

    def test_abort_state(self):
        fake = FakeMelon()
        h = self.harness(fake)
        self.assertIsNone(h.arm9_abort())
        fake.mode, fake.aborts = 0x17, 1
        fake.r[14] = 0x0202469E
        ab = h.arm9_abort()
        self.assertTrue(ab["in_abort_mode"])
        self.assertEqual(ab["fault_pc"], 0x02024696)     # the Rocket HQ NULL load (Thumb ldr r0,[r0])
        fake.mode = 0x1F                                  # left abort mode again: LR comes from the bank
        self.assertEqual(h.arm9_abort()["fault_pc"], 0x02024696)

    def test_melon_only_calls_say_so_on_desmume(self):
        h = E.Harness.__new__(E.Harness)
        with self.assertRaisesRegex(NotImplementedError, "--emulator melonds"):
            h.cpu_exceptions()

    def test_emulator_choice(self):
        with mock.patch.dict("os.environ", {"EMU_HARNESS_EMULATOR": "melonds"}):
            self.assertEqual(E.default_emulator(), "melonds")
        with mock.patch.dict("os.environ", {"EMU_HARNESS_EMULATOR": "nope"}):
            with self.assertRaises(ValueError):
                E.default_emulator()


if __name__ == "__main__":
    unittest.main()
