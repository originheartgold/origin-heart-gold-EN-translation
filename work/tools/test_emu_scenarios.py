"""Unit tests for emu_scenarios (no emulator): schema validation, the op language, judging, the result format."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import emu_harness as E
import emu_scenarios as S

MINIMAL = '''id = "{id}"
description = "test"
steps = ["A", {{ observe = "where", position = true }}]
{extra}
'''


def write(d, text, name="t"):
    p = Path(d) / f"{name}.toml"
    p.write_text(text)
    return p


class ShippedScenarios(unittest.TestCase):
    def test_every_file_validates(self):
        scns = S.load_all()
        self.assertEqual({s["id"] for s in scns}, {"unown", "palpark", "arceus", "evolve", "dex"})

    def test_params_substituted_with_their_type(self):
        arceus = S.load(S.SCENARIO_DIR / "arceus.toml")
        flame = next(c for c in arceus["cases"] if c["id"] == "Flame")
        self.assertEqual(flame["steps"][0], "bagfirst:298")
        self.assertIn({"obs": "arceus.form", "equals": 10, "note": "the Gen 4 type number of the Plate's type"},
                      flame["expect"])
        self.assertEqual(arceus["setup"], {"steps": ["gen:493,50"]})

    def test_case_overrides_merge_over_the_top_level(self):
        evolve = S.load(S.SCENARIO_DIR / "evolve.toml")
        day = next(c for c in evolve["cases"] if c["id"] == "petilil_day")
        night = next(c for c in evolve["cases"] if c["id"] == "petilil_night")
        self.assertEqual(day["start"]["pockets"]["items"], [[80, 5]])
        self.assertEqual(night["start"]["pockets"]["items"], [])
        self.assertEqual(night["steps"][0], "gen:548,10,241")
        self.assertIn("after_stone", json.dumps(day["steps"]))


class SchemaErrors(unittest.TestCase):
    def check(self, text, fragment, name="t"):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(S.ScenarioError) as cm:
                S.load(write(d, text, name))
            self.assertIn(fragment, str(cm.exception))
            self.assertIn(f"{name}.toml", str(cm.exception))

    def test_ok(self):
        with tempfile.TemporaryDirectory() as d:
            scn = S.load(write(d, MINIMAL.format(id="t", extra="")))
            self.assertEqual([c["id"] for c in scn["cases"]], ["main"])

    def test_id_must_match_file(self):
        self.check(MINIMAL.format(id="other", extra=""), "id must equal the file name")

    def test_unknown_top_key(self):
        self.check(MINIMAL.format(id="t", extra="colour = 1"), "unknown key(s) colour")

    def test_bad_toml(self):
        self.check("id = ", "not valid TOML")

    def test_unknown_op(self):
        self.check('id = "t"\ndescription = "x"\nsteps = ["jump:3"]', "op 'jump:3': unknown op")

    def test_bad_op_args(self):
        self.check('id = "t"\ndescription = "x"\nsteps = ["gen:25"]', "takes 2-4 numbers")
        self.check('id = "t"\ndescription = "x"\nsteps = ["flag:5=2"]', "0 or 1")
        self.check('id = "t"\ndescription = "x"\nsteps = ["pocket:shoes"]', "unknown pocket")

    def test_partial_teleport(self):
        self.check(MINIMAL.format(id="t", extra="[start]\nmap = 3\nx = 1"), "needs all of map, x, y")

    def test_bad_clock(self):
        self.check(MINIMAL.format(id="t", extra='[start]\nclock = "noon"'), "not an ISO date-time")

    def test_observation_needs_one_kind(self):
        self.check('id = "t"\ndescription = "x"\nsteps = [{ observe = "a" }]', "exactly one observation kind")
        self.check('id = "t"\ndescription = "x"\nsteps = [{ observe = "a", party = 7 }]', "party slot 0..5")

    def test_expectation_needs_one_check(self):
        self.check(MINIMAL.format(id="t", extra='[[expect]]\nobs = "where"'), "exactly one check")
        self.check(MINIMAL.format(id="t", extra='[[expect]]\nobs = "where"\nequals = 1\nlang = "jp"'),
                   "both, cn or en")

    def test_unknown_param(self):
        self.check('id = "t"\ndescription = "x"\nsteps = ["gen:${sp},5"]', "unknown parameter ${sp}")

    def test_setup_cases_may_only_change_the_clock(self):
        self.check(MINIMAL.format(id="t", extra='[setup]\nsteps = ["A"]\n[[case]]\nid = "a"\nstart = { map = 1, '
                                  'x = 1, y = 1 }'), "only clock may change")

    def test_hook_read_spec(self):
        self.check(MINIMAL.format(id="t", extra='[[hook]]\nname = "h"\naddr = 1\nread = "r99x"'), "a register")

    def test_duplicate_case(self):
        self.check(MINIMAL.format(id="t", extra='[[case]]\nid = "a"\n[[case]]\nid = "a"'), "duplicate")

    def test_load_all_collects_every_error(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, MINIMAL.format(id="a", extra="x = 1"), "a")
            write(d, MINIMAL.format(id="zz", extra=""), "b")
            with self.assertRaises(S.ScenarioError) as cm:
                S.load_all(d)
            self.assertIn("a.toml", str(cm.exception))
            self.assertIn("b.toml", str(cm.exception))

    def test_default_false_runs_only_when_named(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, MINIMAL.format(id="a", extra=""), "a")
            write(d, MINIMAL.format(id="b", extra="").replace('description', 'default = false\ndescription'), "b")
            self.assertEqual([s["id"] for s in S.load_all(d)], ["a"])
            self.assertEqual([s["id"] for s in S.load_all(d, ["b"])], ["b"])
            with self.assertRaises(S.ScenarioError):
                S.load_all(d, ["c"])


class OpLanguage(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(E.parse_op("A"), ("press", ("A", 1, 40)))
        self.assertEqual(E.parse_op("DOWN*3/20"), ("press", ("DOWN", 3, 20)))
        self.assertEqual(E.parse_op("w120"), ("wait", (120,)))
        self.assertEqual(E.parse_op("t43,73/120"), ("touch", (43, 73, 120)))
        self.assertEqual(E.parse_op("hSELECT"), ("hold", ("SELECT",)))
        self.assertEqual(E.parse_op("s:party"), ("s", ("party",)))
        self.assertEqual(E.parse_op("gen:548,10,241"), ("gen", (548, 10, 241)))
        self.assertEqual(E.parse_op("give:0,@gen"), ("give", (0, "@gen")))
        self.assertEqual(E.parse_op("swap:0,@gen"), ("swap", (0, "@gen")))
        self.assertEqual(E.parse_op("var:0x40B5=3"), ("var", (0x40B5, 3)))
        self.assertEqual(E.parse_op("flag:2126=0"), ("flag", (2126, 0)))
        self.assertEqual(E.parse_op("bagfirst:298"), ("bagfirst", (298, 1, "items")))
        self.assertEqual(E.parse_op("prog:LockAll;SetVar,16565,3;End"),
                         ("prog", (("LockAll",), ("SetVar", 16565, 3), ("End",))))
        self.assertEqual(E.parse_op("clock:2026-10-09T18:00:00")[1][0].hour, 18)

    def test_errors(self):
        for op in ("", "Q", "gen:@gen,5", "warp:1,2", "menu:shop", "flag:3", "w", "s:"):
            with self.assertRaises(ValueError, msg=op):
                E.parse_op(op)

    def test_run_ops_parses_everything_first(self):
        h = mock.Mock()
        with self.assertRaises(ValueError):
            E.run_ops(h, ["A", "nonsense"])
        h.press.assert_not_called()

    def test_exec_resolves_gen_slot(self):
        h = mock.Mock(generated_slot=5)
        E.exec_op(h, *E.parse_op("give:0,@gen"))
        h.give_from_bag.assert_called_once_with(0, 5)
        E.exec_op(h, *E.parse_op("flag:7=1"))
        h.set_flag.assert_called_once_with(7, True)


class Judging(unittest.TestCase):
    OBS = {"after": {"species": 549, "form": 1}, "records": [146, 146], "rows": [{"f": 0}, {"f": 0}],
           "wild": {"summary": {"unown": {"count": 7, "all_final_A": True}}}, "pos": (109, 24, 46)}

    def judge(self, *expect, lang="cn"):
        return S.judge(list(expect), self.OBS, lang)

    def test_paths(self):
        self.assertEqual(S.get_path(self.OBS, "after.species"), 549)
        self.assertEqual(S.get_path(self.OBS, "rows.*.f"), [0, 0])
        self.assertEqual(S.get_path(self.OBS, "records.1"), 146)
        self.assertIs(S.get_path(self.OBS, "after.level"), S._MISSING)

    def test_operators(self):
        cases = [("equals", (109, 24, 46), "pos", True), ("equals", 548, "after.species", False),
                 ("in", [548, 549], "after.species", True), ("min", 6, "wild.summary.unown.count", True),
                 ("max", 6, "wild.summary.unown.count", False), ("set", [146], "records", True),
                 ("set", [141], "records", False), ("all", 0, "rows.*.f", True), ("len", 2, "records", True),
                 ("contains", 146, "records", True), ("min", 3, "records", False)]
        for op, want, path, ok in cases:
            row = self.judge({"obs": path, op: want})[0]
            self.assertEqual(row["pass"], ok, (op, want, path))
            self.assertEqual(set(row) - {"note"}, {"obs", "check", "want", "got", "pass"})

    def test_missing_observation_fails(self):
        row = self.judge({"obs": "nothing.here", "equals": 1})[0]
        self.assertFalse(row["pass"])
        self.assertEqual(row["note"], "observation missing")

    def test_lang_filter(self):
        self.assertEqual(self.judge({"obs": "pos", "equals": 1, "lang": "en"}), [])
        self.assertEqual(len(self.judge({"obs": "pos", "equals": 1, "lang": "en"}, lang="en")), 1)

    def test_baseline_created_then_compared(self):
        with tempfile.TemporaryDirectory() as d:
            exp = [{"obs": "after", "baseline": True}]
            first = S.judge(exp, self.OBS, "en", "dex", "main", d)[0]
            self.assertTrue(first["pass"])
            self.assertEqual(first["note"], "baseline created")
            self.assertTrue(S.judge(exp, self.OBS, "en", "dex", "main", d)[0]["pass"])
            changed = S.judge(exp, {"after": {"species": 1}}, "en", "dex", "main", d)[0]
            self.assertFalse(changed["pass"])
            self.assertTrue(S.judge(exp, {"after": {"species": 1}}, "cn", "dex", "main", d)[0]["pass"])

    def test_verdicts(self):
        self.assertEqual(S.run_verdict({"verdict": "timeout"}, []), "timeout")
        self.assertEqual(S.run_verdict({}, []), "observed")
        self.assertEqual(S.run_verdict({}, [{"pass": True}]), "pass")
        self.assertEqual(S.run_verdict({}, [{"pass": True}, {"pass": False}]), "fail")

    def test_parity_report(self):
        scn = {"cases": [{"id": "a"}], "parity": {"differ": {"dex": "text"}}}
        runs = [{"case": "a", "lang": "cn", "observations": {"x": 1, "y": [1], "dex": 1}},
                {"case": "a", "lang": "en", "observations": {"x": 1, "y": (2,), "dex": 2}}]
        p = S.parity(scn, runs)
        self.assertFalse(p["judged"])
        self.assertEqual(p["cases"]["a"], {"dex": "declared", "x": "same", "y": "differs"})


class ResultFormat(unittest.TestCase):
    def test_run_writes_per_scenario_results_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sdir = d / "scn"
            sdir.mkdir()
            (sdir / "s1.toml").write_text('''id = "s1"
description = "x"
refs = ["D-1"]
steps = ["gen:493,5", { observe = "mon", party = "@gen" }]
[setup]
steps = ["A"]
[[case]]
id = "a"
params = { f = 1 }
expect = [{ obs = "mon.form", equals = "${f}" }, { obs = "mon.form", equals = 9, lang = "en" }]
''')
            for lang in ("cn", "en"):
                (d / f"{lang}.nds").write_bytes(lang.encode())
            calls = []

            def fake_child(args, timeout=900):
                calls.append(args)
                case, lang = args[args.index("--case") + 1], args[args.index("--lang") + 1]
                if case == S.SETUP:
                    return {"case": case, "lang": lang, "observations": {}, "screenshots": [], "gen_slot": 5}
                self.assertEqual(args[args.index("--gen-slot") + 1], 5)
                return {"case": case, "lang": lang, "observations": {"mon": {"form": 1}}, "screenshots": [],
                        "seconds": 1.0, "gen_slot": 5}
            a = argparse.Namespace(only=None, lang="both", jobs=2, out=str(d / "run"), rom_cn=str(d / "cn.nds"),
                                   rom_en=str(d / "en.nds"), sav_dir=str(d), baselines=str(d / "b"), dir=str(sdir))
            with mock.patch.object(E, "run_child", fake_child), mock.patch("builtins.print"):
                rc = S.run(a)
            self.assertEqual(rc, 1)                      # the en-only expectation fails
            self.assertEqual(len(calls), 4)             # setup + case, per ROM
            summary = json.loads((d / "run" / "summary.json").read_text())
            self.assertFalse(summary["pass"])
            self.assertEqual(summary["scenarios"][0]["runs"], {"a/cn": "pass", "a/en": "fail"})
            self.assertEqual(set(summary["roms"]["cn"]), {"path", "sha256"})
            doc = json.loads((d / "run" / "s1.json").read_text())
            self.assertEqual(doc["refs"], ["D-1"])
            self.assertEqual([r["lang"] for r in doc["runs"]], ["cn", "en"])
            self.assertEqual(doc["parity"]["cases"]["a"], {"mon": "same"})
            self.assertEqual(len(doc["runs"][1]["expectations"]), 2)
            with mock.patch("sys.stderr"):
                self.assertEqual(S.run(a), 2)            # an existing run folder is not overwritten

    def test_schema_error_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bad.toml").write_text('id = "bad"\n')
            a = argparse.Namespace(only=None, lang="both", jobs=1, out=str(Path(d) / "run"), rom_cn="x", rom_en="y",
                                   sav_dir=d, baselines=d, dir=d)
            with mock.patch("sys.stderr"):
                self.assertEqual(S.run(a), 2)


if __name__ == "__main__":
    unittest.main()
