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

    def test_setup_cases_may_only_change_the_clock_and_rng(self):
        self.check(MINIMAL.format(id="t", extra='[setup]\nsteps = ["A"]\n[[case]]\nid = "a"\nstart = { map = 1, '
                                  'x = 1, y = 1 }'), "only clock and rng may change")

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



def runs_of(cn, en, case="a"):
    return [{"case": case, "lang": "cn", "observations": cn, "verdict": "observed"},
            {"case": case, "lang": "en", "observations": en, "verdict": "observed"}]


def status(p):
    return {r["obs"]: r["status"] for r in p["rows"]}


class Parity(unittest.TestCase):
    def scn(self, differ=None, fields=None):
        return {"cases": [{"id": "a"}], "parity": {"differ": differ or {}, "fields": fields or {}}}

    def test_equal_mismatch_declared(self):
        p = S.parity(self.scn({"dex": "text"}), runs_of({"x": 1, "y": [1], "dex": 1}, {"x": 1, "y": (2,), "dex": 2}))
        self.assertTrue(p["judged"])
        self.assertEqual(status(p), {"dex": S.DECLARED, "x": S.EQUAL, "y": S.MISMATCH})
        y = p["rows"][0]                                                  # mismatches first
        self.assertEqual(y["status"], S.MISMATCH)
        self.assertEqual((y["cn"], y["en"], y["diff"]), ([1], [2], [{"path": "0", "cn": 1, "en": 2}]))
        self.assertEqual(p["counts"], {S.EQUAL: 1, S.DECLARED: 1, S.MISMATCH: 1, S.UNAVAILABLE: 0})

    def test_no_expectations_needed_parity_alone_judges(self):
        runs = runs_of({"m": {"species": 25}}, {"m": {"species": 26}})
        self.assertEqual(S.scenario_verdict(runs, S.parity(self.scn(), runs)), "fail")
        runs = runs_of({"m": {"species": 25}}, {"m": {"species": 25}})
        self.assertEqual(S.scenario_verdict(runs, S.parity(self.scn(), runs)), "pass")

    def test_missing_on_one_rom_is_a_mismatch(self):
        p = S.parity(self.scn(), runs_of({"x": 1, "hook": [3]}, {"x": 1}))
        self.assertEqual(status(p)["hook"], S.MISMATCH)
        self.assertIsNone(p["rows"][0]["en"])

    def test_declared_but_equal_is_flagged(self):
        p = S.parity(self.scn({"x": "may differ"}), runs_of({"x": 1}, {"x": 1}))
        self.assertEqual(status(p), {"x": S.DECLARED})
        self.assertEqual(p["declared_but_equal"], ["x"])

    def test_field_level_parity(self):
        cn = {"mon": {"species": 25, "form": 0, "pid": 1}, "wild": {"steps": 9, "rows": [{"pid": 7, "frame": 1}]}}
        en = {"mon": {"species": 25, "form": 0, "pid": 2}, "wild": {"steps": 8, "rows": [{"pid": 7, "frame": 5}]}}
        fields = {"mon": ["species", "form"], "wild": ["rows.*.pid", "nope"]}
        p = S.parity(self.scn(fields=fields), runs_of(cn, en))
        self.assertEqual(status(p), {"mon": S.EQUAL, "wild": S.EQUAL})          # 'nope': missing on both
        en["wild"]["rows"][0]["pid"] = 8
        p = S.parity(self.scn(fields=fields), runs_of(cn, en))
        row = next(r for r in p["rows"] if r["obs"] == "wild")
        self.assertEqual(row["status"], S.MISMATCH)
        self.assertEqual(row["diff"], [{"path": "rows.*.pid", "cn": [7], "en": [8]}])

    def test_declared_sub_path(self):
        cn = {"dex": {"captured": [1, 2], "errors": [], "digests": {"p1": "aa"}}}
        en = {"dex": {"captured": [1, 2], "errors": [], "digests": {"p1": "bb"}}}
        p = S.parity(self.scn({"dex.digests": "text"}), runs_of(cn, en))
        self.assertEqual(status(p), {"dex": S.EQUAL, "dex.digests": S.DECLARED})
        en["dex"]["errors"] = ["panel 2"]
        p = S.parity(self.scn({"dex.digests": "text"}), runs_of(cn, en))
        self.assertEqual(status(p)["dex"], S.MISMATCH)
        self.assertEqual(p["rows"][0]["diff"], [{"path": "errors", "cn": [], "en": ["panel 2"]}])
        self.assertEqual(cn["dex"]["digests"], {"p1": "aa"})              # the run's own values are untouched

    def test_one_rom_or_failed_run(self):
        self.assertFalse(S.parity(self.scn(), runs_of({"x": 1}, {"x": 2}), langs=["cn"])["judged"])
        p = S.parity(self.scn(), runs_of({"x": 1}, None))
        self.assertEqual(status(p), {"*": S.UNAVAILABLE})
        self.assertEqual(p["counts"][S.MISMATCH], 0)

    def test_large_values_keep_only_the_differing_leaves(self):
        big = {str(i): "x" * 40 for i in range(80)}
        row = S.parity(self.scn(), runs_of({"d": big}, {"d": dict(big, **{"5": "y"})}))["rows"][0]
        self.assertNotIn("cn", row)
        self.assertEqual(row["diff"], [{"path": "5", "cn": "x" * 40, "en": "y"}])

    def test_leaf_diff(self):
        self.assertEqual(S.leaf_diff({"a": [1, 2], "b": 1}, {"a": [1, 3], "c": 1}),
                         [{"path": "a.1", "cn": 2, "en": 3}, {"path": "b", "cn": 1, "en": "(missing)"},
                          {"path": "c", "cn": "(missing)", "en": 1}])
        self.assertEqual(S.leaf_diff([1], [1, 2]), [{"path": "", "cn": [1], "en": [1, 2]}])


PARITY_FILE = MINIMAL + """
[parity.differ.msg]
why = "Chinese and English text"
cn = {{ len = 2 }}
en = {{ equals = 3, path = "pages" }}

[parity.differ]
"wild.letters" = "plain reason"

[parity.fields]
mon = ["species", "rows.*.pid"]
"""


class ParitySchema(unittest.TestCase):
    def bad(self, text, fragment):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(S.ScenarioError) as cm:
                S.load(write(d, text))
            self.assertIn(fragment, str(cm.exception))

    def test_declared_difference_with_per_rom_expectations(self):
        with tempfile.TemporaryDirectory() as d:
            scn = S.load(write(d, PARITY_FILE.format(id="t", extra="")))
        self.assertEqual(scn["parity"]["differ"], {"msg": "Chinese and English text", "wild.letters": "plain reason"})
        self.assertEqual(scn["parity"]["fields"], {"mon": ["species", "rows.*.pid"]})
        exp = scn["cases"][0]["expect"]
        note = "declared difference: Chinese and English text"
        self.assertIn({"obs": "msg", "lang": "cn", "len": 2, "note": note}, exp)
        self.assertIn({"obs": "msg.pages", "lang": "en", "equals": 3, "note": note}, exp)
        self.assertEqual([(r["obs"], r["pass"]) for r in S.judge(exp, {"msg": {"pages": 3}}, "en")],
                         [("msg.pages", True)])
        self.assertEqual([(r["obs"], r["pass"]) for r in S.judge(exp, {"msg": [1, 2, 3]}, "cn")], [("msg", False)])

    def test_parity_errors(self):
        m = MINIMAL.format
        self.bad(m(id="t", extra="[parity]\nsame = 1"), "unknown key(s) same")
        self.bad(m(id="t", extra="[parity.differ]\nx = 3"), "must be a table")
        self.bad(m(id="t", extra='[parity.differ.x]\nwhy = "w"\njp = { equals = 1 }'), "unknown key(s) jp")
        self.bad(m(id="t", extra='[parity.differ.x]\nwhy = "w"\ncn = { equals = 1, min = 2 }'), "exactly one check")
        self.bad(m(id="t", extra="[parity.differ.x]\ncn = { equals = 1 }"), "the reason")
        self.bad(m(id="t", extra='[parity.differ]\n"rows.*.pid" = "w"'), "without '*'")
        self.bad(m(id="t", extra="[parity.fields]\nmon = []"), "non-empty list")
        self.bad(m(id="t", extra='[parity.fields]\n"mon.x" = ["a"]'), "observation name")
        self.bad(m(id="t", extra='[parity]\nfields = { mon = ["a"] }\ndiffer = { "mon.b" = "w" }'), "not both")


class RngOption(unittest.TestCase):
    def load(self, extra):
        with tempfile.TemporaryDirectory() as d:
            return S.load(write(d, MINIMAL.format(id="t", extra=extra)))

    def bad(self, extra, fragment):
        with self.assertRaises(S.ScenarioError) as cm:
            self.load(extra)
        self.assertIn(fragment, str(cm.exception))

    def test_default_seed_explicit_seed_and_off(self):
        self.assertEqual(self.load("")["cases"][0]["rng"], E.DEFAULT_RNG_SEED)
        self.assertEqual(self.load("[start]\nrng = 0x1234")["cases"][0]["rng"], 0x1234)
        self.assertIsNone(self.load("[start]\nrng = false")["cases"][0]["rng"])
        scn = self.load('[start]\nrng = 7\n[[case]]\nid = "a"\nstart = { rng = 8 }\n[[case]]\nid = "b"')
        self.assertEqual([c["rng"] for c in scn["cases"]], [8, 7])

    def test_repin(self):
        scn = self.load('[start]\nrng_repin = [{ addr = 0x02247954, sig = "d8f5" }]')
        self.assertEqual(scn["cases"][0]["start"]["rng_repin"], [{"addr": 0x02247954, "sig": "d8f5"}])

    def test_rng_errors(self):
        self.bad("[start]\nrng = true", "32-bit seed")
        self.bad("[start]\nrng = 0x100000000", "32-bit seed")
        self.bad('[start]\nrng = "x"', "32-bit seed")
        self.bad("[start]\nrng = false\nrng_repin = [{ addr = 2 }]", "needs the RNG pinned")
        self.bad("[start]\nrng_repin = [{ sig = 'aa' }]", "ARM9 code address")
        self.bad("[start]\nrng_repin = [{ addr = 2, sig = 'xyz' }]", "hex code bytes")
        self.bad(f"[start]\nrng_repin = [{{ addr = {E.WILD_FINALIZE} }}]", "already hooked")
        self.bad('[start]\nrng_repin = [{ addr = 4 }]\n[[hook]]\nname = "h"\naddr = 4\nread = "r0"', "already hooked")
        self.bad("[start]\nrng_repin = [{ addr = 4 }, { addr = 4 }]", "duplicate address")

    def test_setup_cases_may_change_rng(self):
        scn = self.load('[setup]\nsteps = ["A"]\n[[case]]\nid = "a"\n'
                        'start = { rng = 5, clock = "2026-10-09T12:00:00" }')
        self.assertEqual(scn["cases"][0]["rng"], 5)

    def test_op_and_values(self):
        self.assertEqual(E.parse_op("rng:0x5EED0001"), ("rng", (0x5EED0001,)))
        self.assertEqual(E.mt_init(5489)[1], 1301868182)        # MT19937's reference initialisation (seed 5489)
        self.assertEqual(E.repin_value(0xFFFFFFFF, 1), (0xFFFFFFFF + E.REPIN_STRIDE) & 0xFFFFFFFF)
        self.assertNotEqual(E.repin_value(1, 1), E.repin_value(1, 2))

    def test_write_rng_checks_the_code_first(self):
        h = mock.Mock()
        h.read.side_effect = lambda a, n: bytes.fromhex(E.RNG_SIG[a])
        h.u32.return_value = 9
        self.assertEqual(E.write_rng(h, 9), 9)
        h.w32.assert_any_call(E.LCRNG_STATE, 9)
        h.w32.assert_any_call(E.MT_INDEX, E.MT_N)
        self.assertEqual(len(h.write.call_args[0][1]), 4 * E.MT_N)
        h.read.side_effect = lambda a, n: b"\0" * n
        with self.assertRaises(RuntimeError):
            E.write_rng(h, 9)


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
            self.assertEqual(status(doc["parity"]), {"mon": S.EQUAL})
            self.assertEqual(summary["failed_expectations"][0]["lang"], "en")
            self.assertEqual(list(summary)[:3], ["pass", "mismatches", "failed_expectations"])
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
