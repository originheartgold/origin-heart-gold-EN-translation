"""Portable regression checks for diagnostic recipes at the strict save-core boundary."""
import unittest
from unittest.mock import Mock

import emu_harness as E


class LiveFlagProbes(unittest.TestCase):
    def test_native_out_of_array_probes_keep_address_and_bit_arithmetic(self):
        for flag in (1, 0xC9F, 0xCA0, 4461, 7286, 0x3FFF):
            for enabled in (False, True):
                with self.subTest(flag=flag, enabled=enabled):
                    h = Mock()
                    h.array.return_value = 0x02100000
                    h.u8.return_value = (1 << (flag % 8)) if enabled else (255 ^ (1 << (flag % 8)))
                    self.assertEqual(E.Harness.get_flag(h, flag), enabled)
                    h.array.assert_called_once_with(E.ARR_VARS_FLAGS)
                    h.u8.assert_called_once_with(0x02100000 + E.FLAGS_OFFSET + flag // 8)

    def test_zero_does_not_read_ram(self):
        h = Mock()
        self.assertFalse(E.Harness.get_flag(h, 0))
        h.array.assert_not_called()
        h.u8.assert_not_called()

    def test_invalid_flags_never_read(self):
        for flag in (-1, 0x4000, True, 1.5, "7286", None):
            with self.subTest(flag=flag):
                h = Mock()
                with self.assertRaises(ValueError):
                    E.Harness.get_flag(h, flag)
                h.array.assert_not_called()
                h.u8.assert_not_called()

    def test_probe_address_must_stay_in_main_ram(self):
        for array in (0x01FFF000, 0x023FFFFF):
            with self.subTest(array=array):
                h = Mock()
                h.array.return_value = array
                with self.assertRaisesRegex(RuntimeError, "outside main RAM"):
                    E.Harness.get_flag(h, 7286)
                h.u8.assert_not_called()

    def test_writes_retain_strict_saved_flag_bounds(self):
        for flag in (0, 0xCA0, 4461, 7286, 0x3FFF):
            with self.subTest(flag=flag):
                h = Mock()
                with self.assertRaises(ValueError):
                    E.Harness.set_flag(h, flag)
                h.array.assert_not_called()
                h.w8.assert_not_called()
