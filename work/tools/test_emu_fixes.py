"""Tests for emu_fixes (emu_harness.py fixes) that need no emulator and no ROM: the coverage list matches the fix
registry, every address is the one the fix's fix.toml declares, the judges tell 'fixed' from 'original' on
recorded observations, and the runner plans the right runs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emu_fixes as F  # noqa: E402
import fixes as fixreg  # noqa: E402

REGISTRY = {fx["id"]: fx for fx in fixreg.load_all()}
OVERLAYS = fixreg.load_overlays()


def region_ram(fix_id, region_id):
    """RAM address of a [[code]] region (arm9 at 0x02000000, overlays from overlays.toml)."""
    entry = next(e for e in REGISTRY[fix_id]["code"] if e["id"] == region_id)
    base = 0x02000000 if entry["file"] == "arm9" else OVERLAYS[entry["file"]]
    return base + int(entry["offset"], 16)


class Coverage(unittest.TestCase):
    def test_every_fix_is_covered_or_listed(self):
        self.assertEqual(set(F.COVERAGE) | set(F.UNCOVERED), set(REGISTRY))
        self.assertFalse(set(F.COVERAGE) & set(F.UNCOVERED))

    def test_every_scenario_exists_and_has_judges(self):
        for fix_id, scenarios in F.COVERAGE.items():
            for sc in scenarios:
                self.assertIn(sc, F.ALL_SCENARIOS, fix_id)
                self.assertIn((sc, fix_id), F.JUDGES)
        self.assertEqual(set(F.JUDGES), {(sc, fx) for fx, scs in F.COVERAGE.items() for sc in scs})
        for sc in F.ALL_SCENARIOS:
            self.assertTrue(F.scenario_fixes(sc), f"scenario {sc} judges no fix")

    def test_fix_toml_evidence_points_at_the_scenario(self):
        for fix_id, fx in REGISTRY.items():
            text = "\n".join(fx["evidence"])
            if fix_id in F.COVERAGE:
                self.assertIn(f"emu_harness.py fixes --case {fix_id}", text, fix_id)
                for sc in F.COVERAGE[fix_id]:
                    self.assertIn(f"scenario {sc}", text, fix_id)
            else:
                self.assertNotIn("emu_harness.py fixes", text, fix_id)


class Addresses(unittest.TestCase):
    """The hooked addresses are the patched instructions of fix.toml (or the call right after them)."""

    def test_naming_sites_follow_the_namelen_regions(self):
        regions = {e["id"] for e in REGISTRY["namelen"]["code"]}
        self.assertEqual({v[0] for v in F.NAMING_SITES.values()}, regions)
        for bl, (region, fixed, original) in F.NAMING_SITES.items():
            self.assertIn(bl - region_ram("namelen", region), (2, 4), region)    # movs r3 .. bl
            self.assertEqual(original, 5)
            self.assertEqual(fixed, 10 if "nickname" in region else 7)

    def test_site_of(self):
        self.assertEqual(F.site_of(0x02042864 + 4 + 1), 0x02042864)

    def test_ivev_hooks_are_the_calls_after_the_patched_movs(self):
        self.assertEqual(F.IVEV_IV_CALL, region_ram("ivev-panel", "ivev-panel-iv-x") + 2)
        self.assertEqual(F.IVEV_HEADER_CALL, region_ram("ivev-panel", "ivev-panel-iv-header-x") + 2)

    def test_naming_ime_path_follows_the_patched_branch(self):
        self.assertEqual(F.NAMING_IME_PATH, region_ram("naming-keyboard", "naming-ime-off") + 2)

    def test_pcbox_template_table(self):
        self.assertEqual(F.PCBOX_TEMPLATES, region_ram("pcbox-name-width", "pcbox-header-name-width"))

    def test_antipiracy_entries(self):
        got = {region_ram("antipiracy", e["id"]) for e in REGISTRY["antipiracy"]["code"]}
        self.assertEqual(set(F.ANTIPIRACY_ENTRIES), got)
        for e in REGISTRY["antipiracy"]["code"]:
            self.assertEqual(bytes.fromhex(e["expect"].replace(" ", "")),
                             bytes.fromhex("47F0E92DD080E24D"))
        # the expect halfwords, as bytes in memory, are the prologue the scenario recognises
        self.assertEqual(F.ANTIPIRACY_PROLOGUE, bytes.fromhex("f0472de980d04de2"))

    def test_outfit_overlay(self):
        self.assertEqual(F.OV58, OVERLAYS["overlay58"])
        offsets = {int(e["offset"], 16) for e in REGISTRY["outfit-chooser-strings"]["string"]}
        self.assertTrue(all(F.OV58_ORIGINAL_SLOTS[0] <= F.OV58 + o < F.OV58_ORIGINAL_SLOTS[1] for o in offsets))
        ptrs = {int(p, 16) for e in REGISTRY["outfit-chooser-strings"]["string"] for p in e["pointers"]}
        self.assertEqual(ptrs, {0x4E4, 0x7C0, 0x7C4, 0x7C8})

    def test_font_codes(self):
        _, fonts, codes = fixreg.font_spec([REGISTRY["font-glyphs"]])
        self.assertEqual(tuple(codes), F.FONT_CODES)
        self.assertLessEqual(set(F.FONT_RAM), set(fonts))


class Helpers(unittest.TestCase):
    def test_decode_and_codes(self):
        raw = bytes.fromhex("2b012c01ffff2d01")
        self.assertEqual(F.decode(raw), "AB")
        self.assertEqual(F.codes(raw), [0x12B, 0x12C])

    def test_column_distance(self):
        cols = [160, 161, 170, 171, 200, 201, 202, 240, 241, 245]
        self.assertEqual(F.column_distance(cols), (202, 245))
        self.assertIsNone(F.column_distance([1, 2, 3]))
        self.assertIsNone(F.column_distance([]))

    def test_select(self):
        self.assertEqual(F.select("pcbox"), {"pcbox": ["pcbox-name-width"]})
        self.assertEqual(F.select("namelen"), {"naming": ["namelen"], "newgame": ["namelen"]})
        self.assertEqual(set(F.select("all")), set(F.ALL_SCENARIOS))
        with self.assertRaises(ValueError):
            F.select("gfx-bag-labels")
        with self.assertRaises(ValueError):
            F.select("nonsense")

    def test_dependents(self):
        self.assertEqual(F.dependents("naming-keyboard"), ["gfx-naming-tabs", "naming-keyboard"])
        self.assertEqual(F.dependents("msgload"), ["msgload", "text-speed"])
        self.assertEqual(F.dependents("namelen"), ["namelen"])

    def test_plan(self):
        jobs = F.plan({"naming": ["namelen"], "pcbox": ["pcbox-name-width"]}, "fixed.nds", "cn.nds", "ctl")
        self.assertEqual([(s, label) for s, label, _ in jobs],
                         [("naming", "fixed"), ("naming", "cn"), ("naming", "no-namelen"),
                          ("pcbox", "fixed"), ("pcbox", "no-pcbox-name-width")])
        self.assertEqual(jobs[2][2], Path("ctl") / "no-namelen.nds")


# Observations recorded on the 2026-10-08 runs (work/build/hard4/run2/fixes_report.json), trimmed.
NAMING = {
    "fixed": {"player": {"codes": [0x12B] * 7, "text": "A" * 7, "crops": {"gfx-naming-tabs": "en"}},
              "nickname": {"codes": [0x12B] * 10, "text": "A" * 10},
              "max_len": {"namelen-player-script": [7], "namelen-rival-script": [7], "namelen-nickname-script": [10]},
              "ime_path_runs": 0},
    "no-namelen": {"player": {"codes": [0x12B] * 5, "text": "A" * 5, "crops": {"gfx-naming-tabs": "en"}},
                   "nickname": {"codes": [0x12B] * 5, "text": "A" * 5},
                   "max_len": {"namelen-player-script": [5], "namelen-rival-script": [5],
                               "namelen-nickname-script": [5]}, "ime_path_runs": 0},
    "no-naming-keyboard": {"player": {"codes": [0x1DE] * 7, "text": " " * 7, "crops": {"gfx-naming-tabs": "cn"}},
                           "nickname": {"codes": [0x1DE] * 10, "text": " " * 10},
                           "max_len": {"namelen-player-script": [7], "namelen-rival-script": [7],
                                       "namelen-nickname-script": [10]}, "ime_path_runs": 24},
}
CN_NAMING = {"player": {"crops": {"gfx-naming-tabs": "cn"}}}


class Judges(unittest.TestCase):
    def test_namelen(self):
        self.assertEqual(F.judge_namelen("naming", NAMING["fixed"])[0], "fixed")
        self.assertEqual(F.judge_namelen("naming", NAMING["no-namelen"])[0], "original")
        newgame = {"max_len": {"namelen-player-intro": [7], "namelen-rival-intro": [7]}}
        self.assertEqual(F.judge_namelen("newgame", newgame)[0], "fixed")
        newgame = {"max_len": {"namelen-player-intro": [5], "namelen-rival-intro": [5]}}
        self.assertEqual(F.judge_namelen("newgame", newgame)[0], "original")
        self.assertEqual(F.judge_namelen("newgame", {"max_len": {}})[0], "unclear")

    def test_namelen_needs_the_typed_names_too(self):
        obs = dict(NAMING["fixed"], nickname={"codes": [0x12B] * 5, "text": "A" * 5})
        self.assertEqual(F.judge_namelen("naming", obs)[0], "unclear")

    def test_naming_keyboard(self):
        self.assertEqual(F.judge_naming_keyboard("naming", NAMING["fixed"])[0], "fixed")
        self.assertEqual(F.judge_naming_keyboard("naming", NAMING["no-naming-keyboard"])[0], "original")
        # a default name ('Ash') after an empty entry still is the original keyboard
        obs = dict(NAMING["no-naming-keyboard"], player={"codes": [0x12B, 0x15D, 0x152], "text": "Ash"})
        self.assertEqual(F.judge_naming_keyboard("naming", obs)[0], "original")

    def test_crop_judge(self):
        judge = F.JUDGES[("naming", "gfx-naming-tabs")]
        self.assertEqual(judge("naming", NAMING["fixed"], CN_NAMING)[0], "fixed")
        self.assertEqual(judge("naming", NAMING["no-naming-keyboard"], CN_NAMING)[0], "original")
        self.assertEqual(judge("naming", NAMING["fixed"], None)[0], "unclear")

    def test_outfit(self):
        en = ["Outfit 1", "Outfit 2", "Outfit 3", "OK"]
        fixed = {"items": [{"text": t, "in_original_slots": t == "OK"} for t in en], "read_by_the_game": en}
        self.assertEqual(F.judge_outfit("newgame", fixed)[0], "fixed")
        zh = ["[05c5][0bfb]1", "[05c5][0bfb]2", "[05c5][0bfb]3", "[09b9][0bb8]"]
        original = {"items": [{"text": t, "in_original_slots": True} for t in zh], "read_by_the_game": zh}
        self.assertEqual(F.judge_outfit("newgame", original)[0], "original")
        self.assertEqual(F.judge_outfit("newgame", dict(fixed, read_by_the_game=[]))[0], "unclear")
        self.assertEqual(F.judge_outfit("newgame", {"error": "no chooser"})[0], "unclear")

    def test_pcbox(self):
        self.assertEqual(F.judge_pcbox("pcbox", {"name_window_width": 8, "ink_columns_x120_127": 1,
                                                 "template": "x"})[0], "fixed")
        self.assertEqual(F.judge_pcbox("pcbox", {"name_window_width": 7, "ink_columns_x120_127": 0,
                                                 "template": "x"})[0], "original")
        self.assertEqual(F.judge_pcbox("pcbox", {"name_window_width": 8, "ink_columns_x120_127": 0,
                                                 "template": "x"})[0], "unclear")

    def test_ivev(self):
        fixed = {"iv_x": [0x20], "header_x": [0x28], "iv_calls": 6, "iv_ev_distance": [32, 32, 32, 33, 31, 33]}
        original = {"iv_x": [0x1A], "header_x": [0x22], "iv_calls": 6, "iv_ev_distance": [38, 38, 38, 39, 37, 39]}
        self.assertEqual(F.judge_ivev("ivev", fixed)[0], "fixed")
        self.assertEqual(F.judge_ivev("ivev", original)[0], "original")
        # the hooked x without the pixels to match is not enough
        self.assertEqual(F.judge_ivev("ivev", dict(fixed, iv_ev_distance=original["iv_ev_distance"]))[0], "unclear")

    def test_antipiracy(self):
        def entries(code, body):
            return {"entries": {f"{e:#010x}": {"calls": 2, "returns": [v], "body_runs": 2 if body else 0,
                                               "code": [code]} for e, v in F.ANTIPIRACY_ENTRIES.items()}}
        self.assertEqual(F.judge_antipiracy("antipiracy", entries("0000a0e31eff2fe1", False))[0], "fixed")
        self.assertEqual(F.judge_antipiracy("antipiracy", entries("f0472de980d04de2", True))[0], "original")
        obs = entries("0000a0e31eff2fe1", False)
        del obs["entries"][f"{0x02263A64:#010x}"]
        self.assertEqual(F.judge_antipiracy("antipiracy", obs)[0], "unclear")      # an entry never reached

    def test_font(self):
        fixed = {"fonts": {"0": {"widths": [[6, 6, 6]]}, "1": {"widths": [[6, 6, 6]]}, "4": {"widths": [[7, 7, 7]]}}}
        original = {"fonts": {"0": {"widths": [[12] * 3]}, "1": {"widths": [[12] * 3]}, "4": {"widths": [[13] * 3]}}}
        self.assertEqual(F.judge_font("font", fixed)[0], "fixed")
        self.assertEqual(F.judge_font("font", original)[0], "original")
        self.assertEqual(F.judge_font("font", {"fonts": {"0": {"widths": []}, "1": {"widths": []},
                                                         "4": {"widths": []}}})[0], "unclear")

    def test_textspeed(self):
        def obs(n, f):
            return {"normal": {"last_text_change_frame": n}, "fast": {"last_text_change_frame": f}}
        self.assertEqual(F.judge_textspeed("textspeed", obs(28, 8))[0], "fixed")
        self.assertEqual(F.judge_textspeed("textspeed", obs(29, 30))[0], "original")
        self.assertEqual(F.judge_textspeed("textspeed", obs(28, 20))[0], "unclear")
        self.assertEqual(F.judge_textspeed("textspeed", obs(None, 8))[0], "unclear")

    def test_msgload(self):
        self.assertEqual(F.judge_msgload("msgload", {"status": "passed", "findings": []})[0], "fixed")
        crash = {"status": "failed", "findings": [{"category": "english_regression",
                                                   "signature": ["allocation", 19, 6448]}]}
        self.assertEqual(F.judge_msgload("msgload", crash)[0], "original")
        self.assertEqual(F.judge_msgload("msgload", {"status": "incomplete", "findings": []})[0], "unclear")

    def test_texture_bounds(self):
        self.assertEqual(F.judge_texture_bounds("texture-bounds", {"expect": "fixed", "passed": True, "rc": 0})[0],
                         "fixed")
        self.assertEqual(F.judge_texture_bounds("texture-bounds",
                                                {"expect": "original", "passed": True, "rc": 0})[0], "original")
        self.assertEqual(F.judge_texture_bounds("texture-bounds",
                                                {"expect": "fixed", "passed": False, "rc": 1})[0], "unclear")

    def test_judge_rows(self):
        selection = {"pcbox": ["pcbox-name-width"]}
        results = {("pcbox", "fixed"): {"name_window_width": 8, "ink_columns_x120_127": 2, "template": "x"},
                   ("pcbox", "no-pcbox-name-width"): {"name_window_width": 7, "ink_columns_x120_127": 0,
                                                      "template": "x"}}
        rows = F.judge(selection, results)
        self.assertTrue(rows[0]["pass"])
        # a control that still shows the fix fails the row: the scenario would prove nothing
        results[("pcbox", "no-pcbox-name-width")] = results[("pcbox", "fixed")]
        self.assertFalse(F.judge(selection, results)[0]["pass"])
        # a crashed run is an error, not a pass
        rows = F.judge(selection, {("pcbox", "fixed"): {"error": "boom"}})
        self.assertEqual(rows[0]["fixed_rom"]["state"], "error")
        self.assertEqual(rows[0]["control"]["state"], "error")
        self.assertFalse(rows[0]["pass"])


if __name__ == "__main__":
    unittest.main()
