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
        # the prologue the scenario recognises is read from fix.toml's expect (halfwords, little-endian)
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
            F.select("gfx-jp-buttons")          # listed in UNCOVERED
        self.assertEqual(F.select("gfx-weather-banners"), {"battle-status": ["gfx-weather-banners"]})
        with self.assertRaises(ValueError):
            F.select("nonsense")

    def test_case_argument(self):
        import argparse
        self.assertEqual(F._case_arg("pcbox"), {"pcbox": ["pcbox-name-width"]})
        with self.assertRaises(argparse.ArgumentTypeError):
            F._case_arg("no-such-fix")

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


EN_TABS = F.APPROVED["naming-tabs"]["digest"]
OLD_CROPS = {"naming-tabs", "type-icon-summary", "type-icon-battle", "title-subtitle"}   # approved 2026-10-08
# Observations recorded on the 2026-10-08 runs (work/build/hard4/run2/fixes_report.json), trimmed.
NAMING = {
    "fixed": {"player": {"codes": [0x12B] * 7, "text": "A" * 7, "crops": {"naming-tabs": EN_TABS}},
              "nickname": {"codes": [0x12B] * 10, "text": "A" * 10},
              "max_len": {"namelen-player-script": [7], "namelen-rival-script": [7], "namelen-nickname-script": [10]},
              "ime_path_runs": 0},
    "no-namelen": {"player": {"codes": [0x12B] * 5, "text": "A" * 5, "crops": {"naming-tabs": EN_TABS}},
                   "nickname": {"codes": [0x12B] * 5, "text": "A" * 5},
                   "max_len": {"namelen-player-script": [5], "namelen-rival-script": [5],
                               "namelen-nickname-script": [5]}, "ime_path_runs": 0},
    "no-naming-keyboard": {"player": {"codes": [0x1DE] * 7, "text": " " * 7, "crops": {"naming-tabs": "cn"}},
                           "nickname": {"codes": [0x1DE] * 10, "text": " " * 10},
                           "max_len": {"namelen-player-script": [7], "namelen-rival-script": [7],
                                       "namelen-nickname-script": [10]}, "ime_path_runs": 24},
}
CN_NAMING = {"player": {"crops": {"naming-tabs": "cn"}}}


PCBOX_FIXED = {"name_window_width": 8, "ink_columns_x120_127": 1, "template": "x", "name_ink_pixels": 300,
               "name_ink_right": 120, "base_tiles": F.PCBOX_BASES["fixed"]}
PCBOX_ORIGINAL = {"name_window_width": 7, "ink_columns_x120_127": 0, "template": "x", "name_ink_pixels": 295,
                  "name_ink_right": 119, "base_tiles": F.PCBOX_BASES["original"]}


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
        # any other picture (e.g. a mirrored label) is neither the approved crop nor the Chinese one
        other = {"player": {"crops": {"naming-tabs": "f" * 64}}}
        self.assertEqual(judge("naming", other, CN_NAMING)[0], "unclear")

    def test_approved_digests(self):
        self.assertEqual(set(F.APPROVED) | set(F.PENDING), set(F.CROPS))
        self.assertFalse(set(F.APPROVED) & set(F.PENDING))
        for key, a in F.APPROVED.items():
            self.assertRegex(a["digest"], r"^[0-9a-f]{64}$", key)
            self.assertTrue(a["approved_by"])
            self.assertIn("work/build/", a["images"]) if key in OLD_CROPS else self.assertTrue(a["images"])
        self.assertLessEqual(OLD_CROPS, set(F.APPROVED))

    def test_crop_checks(self):
        """Every crop is judged in exactly one (scenario, fix), each pending crop names that fix, every box lies
        on the 256x384 screenshot."""
        keys = [k for k, _ in F.CROP_CHECKS.values()]
        self.assertEqual(sorted(keys), sorted(F.CROPS))
        for (sc, fx), (key, _) in F.CROP_CHECKS.items():
            self.assertIn(sc, F.COVERAGE[fx])
            if key in F.PENDING:
                self.assertEqual(F.PENDING[key]["fix"], fx)
                self.assertTrue(F.PENDING[key]["screen"])
        for key, (x0, y0, x1, y1) in F.CROPS.items():
            self.assertTrue(0 <= x0 < x1 <= 256 and 0 <= y0 < y1 <= 384, key)
        # every graphics fix without a scenario says why
        for fx in F.UNCOVERED:
            self.assertGreater(len(F.UNCOVERED[fx]), 80, fx)

    def test_new_graphics_coverage(self):
        self.assertEqual(set(F.UNCOVERED), {"gfx-battle-result-labels", "gfx-jp-buttons"})
        for fx, scs in F.COVERAGE.items():
            if fx.startswith("gfx-"):
                self.assertTrue(all((sc, fx) in F.CROP_CHECKS for sc in scs), fx)
        self.assertEqual(set(F.CLOCKS), {sc for (sc, fx), (key, _) in F.CROP_CHECKS.items() if key in F.PENDING})

    def test_pending_crop_judge(self):
        key = "weather-banner"
        self.assertIn(key, F.PENDING)
        judge = F.JUDGES[("battle-status", "gfx-weather-banners")]
        cn = {"banner": {"crops": {key: "c" * 64}, "unstable": []}}
        build = {"banner": {"crops": {key: "b" * 64}, "unstable": []}}
        self.assertEqual(judge("battle-status", build, cn)[0], "pending")
        self.assertEqual(judge("battle-status", cn, cn)[0], "original")
        self.assertEqual(judge("battle-status", build, None)[0], "unclear")
        moving = {"banner": {"crops": {key: "b" * 64}, "unstable": [key]}}
        self.assertEqual(judge("battle-status", moving, cn)[0], "unclear")
        rows = F.judge({"battle-status": ["gfx-weather-banners"]},
                       {("battle-status", "fixed"): build, ("battle-status", "cn"): cn,
                        ("battle-status", "no-gfx-weather-banners"): cn})
        self.assertTrue(rows[0]["pass"])
        self.assertTrue(rows[0]["pending_approval"])
        # a control that shows anything but the Chinese crop still fails
        rows = F.judge({"battle-status": ["gfx-weather-banners"]},
                       {("battle-status", "fixed"): build, ("battle-status", "cn"): cn,
                        ("battle-status", "no-gfx-weather-banners"): build})
        self.assertFalse(rows[0]["pass"])

    def test_approve(self):
        import json
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            digests = td / "crops.json"
            shutil.copyfile(F.CROP_DIGESTS, digests)
            run = td / "run"
            run.mkdir()
            row = {"fix": "gfx-weather-banners", "scenario": "battle-status", "pass": True, "pending_approval": True,
                   "fixed_rom": {"state": "pending", "evidence": {"digest": "b" * 64, "chinese_rom_digest": "c" * 64}}}
            (run / "fixes_report.json").write_text(json.dumps({"fixes": [row]}))
            done = F.approve(run, ["weather-banner"], "user, test", digests)
            self.assertEqual(done, {"weather-banner": "b" * 64})
            data = json.loads(digests.read_text())
            self.assertEqual(data["approved"]["weather-banner"]["digest"], "b" * 64)
            self.assertNotIn("weather-banner", data["pending"])
            with self.assertRaises(ValueError):          # no longer pending
                F.approve(run, ["weather-banner"], "user, test", digests)
            with self.assertRaises(ValueError):          # not in the run
                F.approve(run, ["yes-no"], "user, test", digests)

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
        self.assertEqual(F.judge_pcbox("pcbox", PCBOX_FIXED)[0], "fixed")
        self.assertEqual(F.judge_pcbox("pcbox", PCBOX_ORIGINAL)[0], "original")
        self.assertEqual(F.judge_pcbox("pcbox", dict(PCBOX_FIXED, ink_columns_x120_127=0))[0], "unclear")
        self.assertEqual(F.judge_pcbox("pcbox", dict(PCBOX_FIXED, base_tiles=F.PCBOX_BASES["original"]))[0],
                         "unclear")
        self.assertTrue(F.pair_pcbox(PCBOX_FIXED, PCBOX_ORIGINAL)[0])
        self.assertFalse(F.pair_pcbox(PCBOX_FIXED, PCBOX_FIXED)[0])

    def test_pcbox_bases_follow_the_asm(self):
        asm = (Path(F.WORK) / "patches" / "pcbox-name-width" / "pcbox-name-width.asm").read_text()
        import re
        old = [int(m, 16) for m in re.findall(r"window_was\s+(?:\d+,\s*){6}(0x[0-9A-F]+)", asm)][:9]
        new = [int(m, 16) for m in re.findall(r"^\s+window\s+(?:\d+,\s*){6}(0x[0-9A-F]+)", asm, re.M)][:9]
        self.assertEqual(old, F.PCBOX_BASES["original"])
        self.assertEqual(new, F.PCBOX_BASES["fixed"])

    def test_ivev_pair(self):
        fixed = {"iv_ev_distance": [32, 32, 32, 33, 31, 33]}
        self.assertTrue(F.pair_ivev(fixed, {"iv_ev_distance": [38, 38, 38, 39, 37, 39]})[0])
        self.assertFalse(F.pair_ivev(fixed, {"iv_ev_distance": [38, 38, 38, 39, 37, 38]})[0])

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

    def test_reflection(self):
        self.assertEqual(F.judge_reflection("reflection", {"expect": "fixed", "passed": True, "rc": 0})[0], "fixed")
        self.assertEqual(F.judge_reflection("reflection", {"expect": "original", "passed": True, "rc": 0})[0],
                         "original")
        self.assertEqual(F.judge_reflection("reflection", {"expect": "fixed", "passed": False, "rc": 1})[0],
                         "unclear")
        self.assertEqual(F.COVERAGE["bulbasaur-reflection-boundary"], ("reflection",))
        self.assertIn("reflection", F.EXTERNAL)

    def test_judge_rows(self):
        selection = {"pcbox": ["pcbox-name-width"]}
        results = {("pcbox", "fixed"): PCBOX_FIXED, ("pcbox", "no-pcbox-name-width"): PCBOX_ORIGINAL}
        rows = F.judge(selection, results)
        self.assertTrue(rows[0]["pass"])
        # a control that still shows the fix fails the row: the scenario would prove nothing
        results[("pcbox", "no-pcbox-name-width")] = results[("pcbox", "fixed")]
        self.assertFalse(F.judge(selection, results)[0]["pass"])
        # both judged right, but the cross-run check fails: the fixed name shows no more text
        results[("pcbox", "no-pcbox-name-width")] = dict(PCBOX_ORIGINAL, name_ink_pixels=400)
        rows = F.judge(selection, results)
        self.assertFalse(rows[0]["pass"])
        self.assertFalse(rows[0]["pair"]["ok"])
        # a crashed run is an error, not a pass
        rows = F.judge(selection, {("pcbox", "fixed"): {"error": "boom"}})
        self.assertEqual(rows[0]["fixed_rom"]["state"], "error")
        self.assertEqual(rows[0]["control"]["state"], "error")
        self.assertFalse(rows[0]["pass"])


class ControlProvenance(unittest.TestCase):
    """A reused control ROM must be the build of this tree without exactly its fix (and dependents)."""

    def make(self, td, fix, applied, rom_bytes=b"rom", report_sha=None):
        import hashlib
        import json
        controls = Path(td)
        (controls / f"no-{fix}.nds").write_bytes(rom_bytes)
        (controls / f"work-no-{fix}").mkdir()
        sha = report_sha or hashlib.sha1(rom_bytes).hexdigest()
        (controls / f"work-no-{fix}" / "build_report.json").write_text(
            json.dumps({"rom": {"sha1": sha}, "fixes": {"applied": applied}}))
        return controls

    def test_checks(self):
        import tempfile
        from unittest.mock import patch
        applied = ["gfx-naming-tabs", "msgload", "namelen", "naming-keyboard", "text-speed"]
        with patch.object(F, "text_sha1", return_value="t"):
            with tempfile.TemporaryDirectory() as td:
                c = self.make(td, "msgload", ["gfx-naming-tabs", "namelen", "naming-keyboard"])
                self.assertEqual(F.control_problems(c, "msgload", applied, "t"), [])
                self.assertIn("differs", F.control_problems(c, "msgload", applied, "other")[0])
            with tempfile.TemporaryDirectory() as td:     # text-speed (requires msgload) was left in
                c = self.make(td, "msgload", ["gfx-naming-tabs", "namelen", "naming-keyboard", "text-speed"])
                self.assertIn("extra ['text-speed']", F.control_problems(c, "msgload", applied, "t")[0])
            with tempfile.TemporaryDirectory() as td:     # the report belongs to another file
                c = self.make(td, "namelen", ["gfx-naming-tabs", "msgload", "naming-keyboard", "text-speed"],
                              report_sha="0" * 40)
                self.assertIn("rom.sha1 differs", F.control_problems(c, "namelen", applied, "t")[0])
            with tempfile.TemporaryDirectory() as td:
                self.assertIn("missing", F.control_problems(Path(td), "namelen", applied, "t")[0])


if __name__ == "__main__":
    unittest.main()
