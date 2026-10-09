"""Tests for emu_layer (the emulator layer's report and approve step); no emulator, no ROM."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import emu_fixes as F
import emu_layer as L
import emu_scenarios as S

CROP_KEY, CROP_SC, CROP_FIX = "bag-hm", "bag", "gfx-bag-labels"
SHOT_KEY = F.CROP_CHECKS[(CROP_SC, CROP_FIX)][1]


def fake_hash(path):
    return "r" * 64


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data))


def fixes_run(d, digest="b" * 64, rom=None, passed=True):
    """A fixes run folder with one pending crop row and one plain passing row, with the crop images."""
    d = Path(d)
    obs = {}
    for label in ("fixed", "cn", f"no-{CROP_FIX}"):
        shot = d / CROP_SC / label / "shot.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"png")
        (shot.parent / f"shot_{CROP_KEY}_crop.png").write_bytes(b"png")
        obs[f"{CROP_SC}/{label}"] = {SHOT_KEY: {"screenshot": str(shot)}}
    rows = [{"fix": CROP_FIX, "scenario": CROP_SC, "pass": passed, "pending_approval": True,
             "fixed_rom": {"state": "pending", "evidence": {"digest": digest, "chinese_rom_digest": "c" * 64}},
             "control": {"state": "original"}},
            {"fix": "namelen", "scenario": "naming", "pass": True, "pending_approval": False,
             "fixed_rom": {"state": "fixed"}, "control": {"state": "original"}}]
    write_json(d / "fixes_report.json", {"pass": passed, "seconds": 12.0, "fixes": rows, "observations": obs,
                                         "uncovered": {"gfx-jp-buttons": "why"},
                                         "inputs": {"rom": rom or {"path": str(d / "en.nds"), "sha256": "r" * 64}}})
    (d / "en.nds").write_bytes(b"rom")
    return d


def scenarios_run(d, value=("x", "y"), approved_digest=None):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    (d / "en.nds").write_bytes(b"rom")
    key = "dex/main/en/dex.digests"
    digest = S.value_digest(list(value))
    write_json(d / "dex.json", {"runs": [{"case": "main", "lang": "en", "observations": {"dex": {"digests": list(value)}}},
                                         {"case": "main", "lang": "cn", "observations": {"dex": {"digests": ["z"]}}}]})
    for lang in ("cn", "en"):
        p = d / "dex" / lang / "main" / f"dex_{lang}" / "001.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
    write_json(d / "summary.json", {
        "pass": True, "mismatches": [], "failed_expectations": [], "errors": [], "seconds": 5,
        "roms": {"en": {"path": str(d / "en.nds"), "sha256": "r" * 64}},
        "pending_approval": [{"scenario": "dex", "case": "main", "lang": "en", "obs": "dex.digests", "key": key,
                              "digest": digest, "approved_digest": approved_digest, "note": "needs approval"}],
        "scenarios": [{"scenario": "dex", "verdict": "pass", "parity": {"equal": 1}, "runs": {"main/en": "pass"}}]})
    return d, key, digest


class Report(unittest.TestCase):
    def parts(self):
        return [{"part": "fixes", "pass": True, "seconds": 1, "run_dir": "/x/fixes",
                 "rows": [L._row("fixes", "pass", "a", "A"), L._row("fixes", "pending", "b", "B",
                                                                   approve={"kind": "crop", "key": "k"})]},
                {"part": "textfit", "pass": False, "seconds": 2, "run_dir": "/x/textfit",
                 "rows": [L._row("textfit", "pass", "c", "C"), L._row("textfit", "fail", "d", "D")]},
                {"part": "freeze", "pass": False, "seconds": 3, "run_dir": "/x/freeze", "rows": []}]

    def test_order_and_verdict(self):
        rep = L.build_report(self.parts(), {"seconds": 6})
        self.assertEqual([r["status"] for r in rep["rows"]], ["fail", "fail", "pending", "pass", "pass"])
        self.assertEqual([r["id"] for r in rep["rows"]][:2], ["d", "freeze"])   # failures in part order
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertEqual(rep["pending_approvals"], 1)
        self.assertEqual(list(rep)[:3], ["schema", "verdict", "pass"])
        self.assertEqual([p["part"] for p in rep["parts"]], ["fixes", "textfit", "freeze"])
        self.assertNotIn("rows", rep["parts"][0])
        self.assertEqual(rep["parts"][2]["counts"]["fail"], 1)       # a failed part always has a failing row
        self.assertEqual(L.exit_code(rep), 1)

    def test_pending_does_not_fail(self):
        parts = self.parts()[:1]
        rep = L.build_report(parts)
        self.assertTrue(rep["pass"])
        self.assertEqual(L.exit_code(rep), 0)
        self.assertEqual(rep["pending_approvals"], 1)

    def test_approve_commands(self):
        rows = [{"approve": {"kind": "crop", "key": "bag-hm"}}, {"approve": {"kind": "baseline", "key": "a/b/en/c"}}]
        cmds = L.approve_command(Path("R"), rows, python="py")
        self.assertEqual(cmds[0], 'py work/tools/emu_harness.py approve --from R --crops bag-hm --by "<who, date>"')
        self.assertIn("--baselines a/b/en/c", cmds[1])
        self.assertIn("--all-pending", cmds[2])

    def test_html_offline_relative(self):
        with tempfile.TemporaryDirectory() as td:
            img_cn, img_en = Path(td) / "runs" / "s" / "cn.png", Path(td) / "runs" / "s" / "en.png"
            img_cn.parent.mkdir(parents=True)
            parts = [{"part": "scenarios", "pass": False, "seconds": 1, "run_dir": str(Path(td) / "runs" / "s"),
                      "rows": [L._row("scenarios", "fail", "x", "MISMATCH <x>", "d",
                                      [{"label": "l", "cn": [str(img_cn)], "en": [str(img_en)]}]),
                               L._row("scenarios", "pending", "k", "baseline k", "",
                                      approve={"kind": "baseline", "key": "k", "digest": "d" * 64}),
                               L._row("scenarios", "pass", "p", "ok")]}]
            rep = L.build_report(parts, {"seconds": 1})
            _, html_path = L.write_report(rep, Path(td) / "report" / "1")
            page = html_path.read_text()
            self.assertNotIn("http://", page)
            self.assertNotIn("https://", page)
            self.assertIn('src="../../runs/s/cn.png"', page)
            self.assertIn('src="../../runs/s/en.png"', page)
            self.assertIn("MISMATCH &lt;x&gt;", page)
            self.assertLess(page.index("Failures (1)"), page.index("Pending approvals (1)"))
            self.assertLess(page.index("Pending approvals (1)"), page.index("<details>"))
            self.assertIn("--baselines k", page)
            saved = json.loads((Path(td) / "report" / "1" / "report.json").read_text())
            self.assertIn("--baselines k --by", saved["approve_commands"][0])


class Adapters(unittest.TestCase):
    def test_fixes(self):
        with tempfile.TemporaryDirectory() as td:
            part = L.part_fixes(fixes_run(td))
            self.assertTrue(part["pass"])
            self.assertEqual(part["counts"], {"fail": 0, "pending": 1, "pass": 1})
            pend = next(r for r in part["rows"] if r["status"] == "pending")
            self.assertEqual(pend["approve"]["key"], CROP_KEY)
            self.assertEqual(len(pend["images"][0]["cn"]), 1)
            self.assertEqual(len(pend["images"][0]["en"]), 1)
            self.assertIn("gfx-jp-buttons", part["note"])

    def test_missing_report_is_a_failure(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "textfit.log").write_text("Traceback: boom\n")
            part = L.part_textfit(Path(td) / "textfit", 3)
            self.assertFalse(part["pass"])
            self.assertIn("boom", part["rows"][0]["detail"])

    def test_textfit(self):
        with tempfile.TemporaryDirectory() as td:
            pair = Path(td) / "crops" / "a_pair.png"
            pair.parent.mkdir()
            pair.write_bytes(b"png")
            write_json(Path(td) / "summary.json", {
                "pass": False, "selection": "since v1", "seconds": 9,
                "counts": {"strings": 5, "rendered": 4, "pass": 3, "fail": 1},
                "failures": [{"ref": "a027/0115#39", "window": "field", "crop": None, "pair": str(pair),
                              "reasons": [{"code": "prompt", "view": 5, "row": 1, "detail": "198 px"}]}],
                "errors": [], "unsupported": {"window type ui": {"count": 1, "refs": ["x"]}}})
            part = L.part_textfit(td)
            self.assertEqual(part["counts"], {"fail": 1, "pending": 0, "pass": 1})
            fail = part["rows"][0]
            self.assertEqual(fail["codes"], ["prompt"])
            self.assertEqual(fail["images"][0]["paths"], [str(pair)])
            self.assertIn("window type ui 1", part["note"])

    def test_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            write_json(Path(td) / "freeze.json", {"pass": False, "seconds": 30, "cases": [
                {"case": "rocket_hq", "fix": "f", "refs": ["D-1"], "what": "w", "pass": True,
                 "build": {"ok": True, "hung": False, "reached_goal": True}, "cn": {"ok": True, "hung": True,
                                                                                   "fault_pc": "0x02024696"}},
                {"case": "follower_viridian", "fix": "g", "refs": ["D-2"], "what": "w", "pass": False,
                 "build": {"error": "no save"}, "cn": {"error": "no save"}}]})
            part = L.part_freeze(td)
            self.assertFalse(part["pass"])
            self.assertEqual([r["status"] for r in part["rows"]], ["pass", "fail"])
            self.assertIn("data abort at 0x02024696", part["rows"][0]["detail"])

    def test_scenarios(self):
        with tempfile.TemporaryDirectory() as td:
            d, key, digest = scenarios_run(td)
            part = L.part_scenarios(d)
            self.assertEqual(part["counts"], {"fail": 0, "pending": 1, "pass": 1})
            pend = part["rows"][0]
            self.assertEqual(pend["approve"]["key"], key)
            self.assertEqual(len(pend["images"][0]["cn"]), 1)


class Approve(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.d = Path(self.td.name)
        self.crops = self.d / "crops.json"
        write_json(self.crops, {"_doc": "d", "approved": {}, "pending": {CROP_KEY: {"fix": CROP_FIX, "screen": "s"}}})
        self.base = self.d / "baselines.json"

    def tearDown(self):
        self.td.cleanup()

    def approve(self, src, **kw):
        return L.approve(src, by=kw.pop("by", "user, 2026-10-09"), crops_path=self.crops, baselines_path=self.base,
                         rom_hash=kw.pop("rom_hash", fake_hash), **kw)

    def report_from(self, *parts):
        rep = L.build_report(list(parts))
        out = self.d / "report"
        L.write_report(rep, out)
        return out

    def test_crop_pending_to_approved(self):
        run = fixes_run(self.d / "fx")
        out = self.report_from(L.part_fixes(run))
        done = self.approve(out, crops=[CROP_KEY])
        self.assertEqual(done, [("crop", CROP_KEY, "b" * 64, self.crops)])
        data = json.loads(self.crops.read_text())
        self.assertEqual(data["approved"][CROP_KEY]["digest"], "b" * 64)
        self.assertEqual(data["approved"][CROP_KEY]["approved_by"], "user, 2026-10-09")
        self.assertNotIn(CROP_KEY, data["pending"])
        with self.assertRaises(L.ApproveError):          # a second time: not pending any more
            self.approve(out, crops=[CROP_KEY])

    def test_from_a_fixes_run_folder(self):
        run = fixes_run(self.d / "fx")
        self.assertEqual(self.approve(run, all_pending=True)[0][:2], ("crop", CROP_KEY))

    def test_refuses_stale_digest(self):
        run = fixes_run(self.d / "fx")
        out = self.report_from(L.part_fixes(run))
        rep = json.loads((run / "fixes_report.json").read_text())
        rep["fixes"][0]["fixed_rom"]["evidence"]["digest"] = "e" * 64      # the run says something else now
        write_json(run / "fixes_report.json", rep)
        before = self.crops.read_text()
        with self.assertRaises(L.ApproveError) as cm:
            self.approve(out, crops=[CROP_KEY])
        self.assertIn("stale", str(cm.exception))
        self.assertEqual(self.crops.read_text(), before)                     # nothing written

    def test_refuses_missing_evidence(self):
        run = fixes_run(self.d / "fx")
        out = self.report_from(L.part_fixes(run))
        (run / CROP_SC / "fixed" / f"shot_{CROP_KEY}_crop.png").unlink()
        with self.assertRaises(L.ApproveError) as cm:
            self.approve(out, crops=[CROP_KEY])
        self.assertIn("evidence missing", str(cm.exception))
        rep = json.loads((out / "report.json").read_text())
        rep["rows"][0]["approve"]["digest"] = None
        write_json(out / "report.json", rep)
        with self.assertRaises(L.ApproveError) as cm:
            self.approve(out, crops=[CROP_KEY])
        self.assertIn("no digest", str(cm.exception))

    def test_refuses_rebuilt_rom(self):
        run = fixes_run(self.d / "fx")
        out = self.report_from(L.part_fixes(run))
        with self.assertRaises(L.ApproveError) as cm:
            self.approve(out, crops=[CROP_KEY], rom_hash=lambda p: "0" * 64)
        self.assertIn("changed since the run", str(cm.exception))

    def test_refuses_unknown_and_empty(self):
        run = fixes_run(self.d / "fx")
        out = self.report_from(L.part_fixes(run))
        with self.assertRaises(L.ApproveError) as cm:
            self.approve(out, crops=["yes-no"])
        self.assertIn("not pending in", str(cm.exception))
        with self.assertRaises(L.ApproveError):
            self.approve(out)
        with self.assertRaises(L.ApproveError):
            self.approve(out, crops=[CROP_KEY], by=" ")

    def test_baseline_recorded_then_judged(self):
        d, key, digest = scenarios_run(self.d / "sc")
        out = self.report_from(L.part_scenarios(d))
        values = self.d / "values"
        done = self.approve(out, baselines=[key], values_dir=values)
        self.assertEqual(done, [("baseline", key, digest, self.base)])
        data = json.loads(self.base.read_text())
        self.assertEqual(data["approved"][key]["digest"], digest)
        self.assertEqual(data["approved"][key]["approved_by"], "user, 2026-10-09")
        self.assertTrue(data["_doc"])
        self.assertTrue(S.baseline_file(values, "dex", "main", "en", "dex.digests").is_file())
        # the next run judges against it: equal passes, a changed EN value needs approval again
        exp = [{"obs": "dex.digests", "baseline": True}]
        appr = S.load_approvals(self.base)["approved"]
        self.assertNotIn("pending", S.judge(exp, {"dex": {"digests": ["x", "y"]}}, "en", "dex", "main", None, appr)[0])
        again = S.judge(exp, {"dex": {"digests": ["x"]}}, "en", "dex", "main", values, appr)[0]
        self.assertTrue(again["pending"])
        self.assertTrue(again["diff"])
        with self.assertRaises(L.ApproveError) as cm:                       # approved already
            self.approve(out, baselines=[key])
        self.assertIn("already approved", str(cm.exception))

    def test_baseline_refuses_when_approvals_moved(self):
        d, key, digest = scenarios_run(self.d / "sc")
        out = self.report_from(L.part_scenarios(d))
        write_json(self.base, {"approved": {key: {"digest": "f" * 64}}})     # approved by someone since the run
        with self.assertRaises(L.ApproveError) as cm:
            self.approve(out, baselines=[key])
        self.assertIn("approved digest changed", str(cm.exception))

    def test_cmd_approve_prints_what_it_recorded(self):
        run = fixes_run(self.d / "fx")
        out = self.report_from(L.part_fixes(run))
        a = argparse.Namespace(run=str(out), crops=CROP_KEY, baselines=None, all_pending=False, by="user, today")
        with mock.patch.object(F, "CROP_DIGESTS", self.crops), mock.patch.object(L, "_sha256", fake_hash), \
                mock.patch.object(S, "APPROVALS", self.base), mock.patch("builtins.print") as pr:
            orig = L.approve
            with mock.patch.object(L, "approve", lambda *x, **k: orig(*x, **dict(k, rom_hash=fake_hash))):
                self.assertEqual(L.cmd_approve(a), 0)
        printed = " ".join(str(c.args[0]) for c in pr.call_args_list)
        self.assertIn(f"recorded crop {CROP_KEY}: approved digest {'b' * 64} by 'user, today'", printed)


class Freeze(unittest.TestCase):
    def test_find_save_by_sha(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.sav").write_bytes(b"one")
            (Path(td) / "b.sav").write_bytes(b"two")
            want = L._sha256(Path(td) / "b.sav")
            self.assertEqual(L.find_save(want, [td, "/nonexistent"]).name, "b.sav")
            self.assertIsNone(L.find_save("0" * 64, [td]))

    def test_missing_save_fails_the_case(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(L, "find_melonds", return_value="/lib"):
            rep = L.run_freeze(Path(td) / "freeze", "en.nds", "cn.nds", [td], 1, {})
            self.assertFalse(rep["pass"])
            self.assertIn("no save with SHA-256", rep["cases"][0]["build"]["error"])
            self.assertEqual(L.part_freeze(Path(td) / "freeze")["counts"]["fail"], len(L.FREEZE_CASES))

    def test_parts_and_pool(self):
        self.assertEqual(L.parse_parts("freeze,fixes"), ["fixes", "freeze"])
        with self.assertRaises(L.LayerError):
            L.parse_parts("fixes,nope")
        self.assertEqual(L.pool_env(2)["EMU_HARNESS_MAX_EMULATORS"], "2")


if __name__ == "__main__":
    unittest.main()
