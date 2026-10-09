"""Portable regression checks for diagnostic recipes at the strict save-core boundary."""
import struct
import unittest
from unittest.mock import Mock, patch

import emu_calendar as C
import emu_hackbugs as H
import emu_harness as E
from test_emu_harness import BLOCK_ORDERS, _encrypted_mon, _prng_stream


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


def ability_fixture():
    """Independent record with different vanilla and Origin ability fields."""
    raw = _encrypted_mon(7, party=True)
    pid, _, checksum = struct.unpack_from("<IHH", raw)
    plain = bytearray(struct.pack("<64H", *[
        word ^ key for word, key in zip(struct.unpack_from("<64H", raw, 8), _prng_stream(checksum, 64))]))
    order = BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    plain[32 * order.index("A") + 0x0D] = 1
    struct.pack_into("<H", plain, 32 * order.index("B") + 0x1A, 311)
    words = struct.unpack("<64H", plain)
    checksum = sum(words) & 0xFFFF
    return struct.pack("<IHH", pid, 0, checksum) + struct.pack("<64H", *[
        word ^ key for word, key in zip(words, _prng_stream(checksum, 64))]) + raw[136:]


class RecipeAbilities(unittest.TestCase):
    def test_party_and_battle_report_effective_16_bit_ability(self):
        raw = ability_fixture()
        h = Mock()
        h.u32.return_value = 1
        h.read.return_value = raw
        with patch.object(H.K, "find_parties", return_value=[{"addr": "0x02200100"}]), \
                patch.object(H.M, "party_raw", return_value=raw):
            own = H.mon(h)
            battle = H.battle_parties_raw(h)[0]["mons"][0]
        self.assertEqual(own["ability"], 311)
        self.assertEqual(battle["ability"], own["ability"])
        self.assertEqual(battle["vanilla_ability_byte"], 1)

    def test_trainer_report_preserves_vanilla_ability_bytes_diagnostic(self):
        trainer = {"species": 201, "form": 0, "level": 5, "iv": 0, "ivs": 0,
                   "hp_ivs": 0, "ability": 1, "moves": [33]}
        battle = {"species": 201, "form": 0, "level": 5, "ivs": [0] * 6,
                  "ability": 311, "vanilla_ability_byte": 1, "moves": [33, 0, 0, 0]}
        h = Mock()
        with patch.object(H, "rom_team", return_value=({}, [trainer])), \
                patch.object(H.M, "session") as session, patch.object(H.G, "lead"), \
                patch.object(H, "battle_parties_raw", return_value=[{"mons": [battle]}]):
            session.return_value.__enter__.return_value = h
            report = H.case_trainer("unused.nds", "unused-output", "146")
        self.assertEqual(report["ability_bytes"], [1])
        self.assertEqual(report["battle_party"][0]["ability"], 311)


class PersonalFitDiagnostics(unittest.TestCase):
    def setUp(self):
        self.mon = {"species": 1, "form": 1, "level": 17, "ivs": [13, 0, 18, 29, 8, 11],
                    "evs": [0] * 6, "nature": 2, "stats": [46, 42, 59, 23, 40, 57]}
        self.personal = [bytes(8), bytes([50, 100, 150, 50, 100, 150, 1, 2]), bytes(8)]
        self.data = {"personal": self.personal, "forms": {(1, 1): 2}}

    def fit(self):
        with patch.object(C, "rom_data", return_value=self.data):
            return C.personal_fit("unused.nds", self.mon)

    def test_blank_form_reports_reason_and_preserves_valid_candidate(self):
        fit = self.fit()
        self.assertEqual(fit[1], {"label": "base", "types": [1, 2], "match": True})
        self.assertFalse(fit[2]["match"])
        self.assertIn("Base stat", fit[2]["reason"])
        self.assertEqual(fit[2]["error_code"], "invalid-input")

    def test_invalid_total_evs_are_diagnostic_failures(self):
        self.mon["evs"] = [100] * 6
        fit = self.fit()
        self.assertTrue(all(not row["match"] and "510" in row["reason"] for row in fit.values()))

    def test_species_zero_is_a_diagnostic_failure(self):
        self.mon["species"] = 0
        fit = self.fit()
        self.assertFalse(fit[0]["match"])
        self.assertIn("Species ID", fit[0]["reason"])

    def test_valid_stat_mismatch_has_no_validation_error(self):
        self.mon["stats"][0] += 1
        self.assertEqual(self.fit()[1], {"label": "base", "types": [1, 2], "match": False})

    def test_transport_and_unexpected_core_errors_still_fail(self):
        for exc in (E._save_core.WorkerError("offline"), E._save_core.CoreError("other", "unexpected")):
            with self.subTest(error=type(exc).__name__), patch.object(C, "calc_stats", side_effect=exc):
                with self.assertRaises(type(exc)):
                    self.fit()

    def test_stat_calculator_itself_stays_strict(self):
        with self.assertRaises(E._save_core.CoreError):
            C.calc_stats([0] * 6, 17, [0] * 6, [0] * 6, 2)


if __name__ == "__main__":
    unittest.main()
