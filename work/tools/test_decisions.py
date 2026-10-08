#!/usr/bin/env python3
"""Tests for decisions.py (decision register).   Run:  python3 -m unittest -v work/tools/test_decisions.py

Everything runs on a mini workspace in a temp dir; the real register, banks and PROGRESS.md are only read
(the real PROGRESS.md is copied for the idempotency test)."""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decisions as D  # noqa: E402

REAL_PROGRESS = Path(__file__).resolve().parent.parent / "translate" / "PROGRESS.md"

MINI_PROGRESS = """# Translation progress

## Done
- B001 done. 小赤 → Nobody (progress log lines are not decisions)

## Decisions
- Names use mixed case (Bulbasaur, Poké Ball), not Gen 4 all-caps.
- Money: `$` before the amount, as in the US text.
- 精灵 / 口袋妖怪 → Pokémon; 训练家 → Trainer; 施主 → traveler.
- Shop menus: “Item{NEWLINE}$price”; 不买了 → “Nothing, thanks”; 先不打了 → “Not now”.
- **Team Rocket motto, house wording (B038/B039; reuse exactly).** Alternate speakers:
  - 为了防止世界被破坏 → Jessie: To keep the world from being wrecked!
  - 白洞,白色的明天在等着我们 → James: A white hole! A bright white future awaits!
- **Page layout:** write short paragraphs separated by blank lines, so `wrap` never leaves an orphan {SCROLL}.

## Character voice
For dialogue anywhere in the game.
- **Blue (小绿):** cocky and teasing. Short, punchy sentences.
- **Jessie / James:** theatrical and snarky. **Meowth:** Brooklyn-ish dub voice.

## Names decided
### Characters (trainer names 0719, use in dialogue too)
- 小赤 → Red
- 小银 / 银 → Silver
- 傲广 / 傲钦 → Ao Guang / Ao Qin (Four Dragon Kings)
- 小美 → Molly (Molly Hale, Movie 3)
### Locations
- 水都 → Alto Mare (the hack's island chain)
- 水绿号 → S.S. Aqua
### B034–B035 (Viridian)
- 金婆婆 → Granny Kin (rich old Rocket backer; invented)
- Badges (0354 #31–38): 灰色 Boulder, 蓝色 Cascade
- 水都群岛 → the Alto Mare Islands; 二之岛 → Two Island (= trainer 0719 #127)
### B040–B041 (Cerulean)
- 金婆婆 → Granny Kin (already used)
- 小美 (Silph coworker) → Mei

## Resolved by coordinator
- Scope: English only.
- 水绿号 (S.S. Aqua) leftovers: use "S.S. Anne" everywhere for consistency.

## Open questions
- a027/0248 #7, 0253 #16/#17: zh still says 水绿号 (S.S. Aqua); should these say S.S. Anne?
- 0719 #705 梨琳 (Elite Four): placeholder "Lorin". Check in game.
- B034/B035 routes: 0445 #151–242 are the Yellow romance route (male player).
"""

APPEND = """- 小豪 → Goh (Journeys)
"""


def mk_bank(narc, no, strings, category=None):
    b = {"narc": narc, "bank": no, "source": "test", "strings": []}
    if category:
        b["category"] = category
    for i, (zh, en, st) in enumerate(strings):
        b["strings"].append({"id": i, "zh": zh, "en": en, "status": st, "origin": "agent", "notes": ""})
    return b


BANK_A = [  # a027/0901 (dialogue: zh has {SCROLL})
    ("金婆婆『你好{SCROLL}再见", "Granny Kin: Hello!{SCROLL}Goodbye!", "draft"),              # 0 consistent
    ("我是金婆婆。", "I’m Granny Kin, dearie.", "reviewed"),                                    # 1 consistent
    ("金婆婆来了", "The old lady is here.", "draft"),                                           # 2 inconsistent
    ("金婆婆走了", None, "todo"),                                                               # 3 untranslated
    ("小赤和小银", "Red and Silver.", "draft"),                                                 # 4
    ("金婆婆！{SCROLL}哈哈", "GRANNY KIN!{SCROLL}Ha ha.", "draft"),                             # 5 caps
    ("欢迎来到水都群岛", "Welcome to the Alto Mare Islands!", "draft"),                         # 6 shadowed for 水都
    ("水都很美{SCROLL}是的", "Alto Mare is lovely.{SCROLL}Yes.", "draft"),                      # 7
    ("听说金婆婆在水都{SCROLL}是吗", "I heard Granny{NEWLINE}Kin is in Alto Mare.{SCROLL}Really?", "draft"),  # 8 spans break
    ("没有关系的句子{SCROLL}嗯", "Unrelated line.{SCROLL}Mm.", "draft"),                         # 9
]
BANK_B = [
    ("金婆婆的集团", "Granny Kin’s company.", "draft"),
    ("无关", "Nothing to see.", "draft"),
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dec_test_"))
        self.ws = self.tmp / "banks"
        (self.ws / "a027").mkdir(parents=True)
        self.save_bank(mk_bank("a027", 901, BANK_A))
        self.save_bank(mk_bank("a027", 902, BANK_B, category="dialogue"))
        self.reg = self.tmp / "decisions" / "decisions.jsonl"
        self.snap = self.tmp / "snapshots"
        self.progress = self.tmp / "PROGRESS.md"
        self.progress.write_text(MINI_PROGRESS, encoding="utf-8")
        os.environ["DECISIONS_TODAY"] = "2026-09-28"
        os.environ["DECISIONS_BY"] = "tester"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def save_bank(self, b):
        p = self.ws / b["narc"] / ("%04d.json" % b["bank"])
        p.write_text(json.dumps(b, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def bank(self, no):
        return json.loads((self.ws / "a027" / ("%04d.json" % no)).read_text(encoding="utf-8"))

    def run_cli(self, *args, expect_exit=False):
        out, err = io.StringIO(), io.StringIO()
        argv = ["--register", str(self.reg), "--ws", str(self.ws), "--snapshots", str(self.snap), *args]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                D.main(argv)
            except SystemExit as e:
                if not expect_exit:
                    raise AssertionError(f"exit {e.code}: {err.getvalue()} {out.getvalue()}") from None
                return out.getvalue(), err.getvalue(), e.code
        return (out.getvalue(), err.getvalue(), 0) if expect_exit else out.getvalue()

    def imp(self):
        return self.run_cli("import-progress", "--progress", str(self.progress))

    def recs(self):
        return D.load_register(self.reg)

    def find(self, **kw):
        hits = [r for r in self.recs() if all(r.get(k) == v for k, v in kw.items())]
        self.assertTrue(hits, f"no record with {kw}")
        return hits[0]


class TestMigration(Base):
    def test_import_and_idempotency(self):
        out = self.imp()
        self.assertIn("added", out)
        n1 = len(self.recs())
        out2 = self.imp()
        self.assertNotIn("added ", out2)
        self.assertEqual(len(self.recs()), n1)
        # PROGRESS grows (under an existing section, which shifts line numbers): only the new line is added
        txt = MINI_PROGRESS.replace("- 小美 → Molly (Molly Hale, Movie 3)\n",
                                    "- 小美 → Molly (Molly Hale, Movie 3)\n" + APPEND)
        self.progress.write_text(txt, encoding="utf-8")
        self.imp()
        recs = self.recs()
        self.assertEqual(len(recs), n1 + 1)
        goh = self.find(zh="小豪")
        self.assertEqual(goh["en"], "Goh")
        self.assertEqual(goh["confidence"], "high")      # "Journeys" = official source
        self.assertEqual(len({r["id"] for r in recs}), len(recs))
        self.imp()
        self.assertEqual(len(self.recs()), n1 + 1)

    def test_parsed_records(self):
        self.imp()
        recs = self.recs()
        # Done section ignored
        self.assertFalse([r for r in recs if r.get("en") == "Nobody"])
        red = self.find(zh="小赤")
        self.assertEqual((red["type"], red["subtype"], red["status"], red["source"]),
                         ("term", "character", "provisional", "agent:B009-B010"))
        self.assertIsInstance(red["origin_line"], int)
        self.assertEqual(MINI_PROGRESS.splitlines()[red["origin_line"] - 1], "- 小赤 → Red")
        self.assertEqual(self.find(zh="小银")["aliases"], ["银"])
        self.assertEqual(self.find(zh="傲钦")["en"], "Ao Qin")                 # parallel lists
        kin = self.find(zh="金婆婆", type="term")
        self.assertEqual(kin["confidence"], "low")                               # invented
        self.assertEqual(len(kin["mentions"]), 1)                                # "(already used)" merged
        self.assertEqual(self.find(zh="灰色")["en"], "Boulder")                   # label: zh en, zh en
        self.assertEqual(self.find(zh="灰色")["subtype"], "badge")
        self.assertIn("a027/0354#31-38", self.find(zh="灰色")["refs"])
        self.assertIn("a027/0719#127", self.find(zh="二之岛")["refs"])
        self.assertEqual(self.find(zh="水都群岛")["en"], "the Alto Mare Islands")
        # rules
        money = self.find(subtype="money")
        self.assertEqual(money["type"], "style")
        page = [r for r in recs if (r.get("en") or "").startswith("Page layout:")]
        self.assertEqual([r["type"] for r in page], ["layout"])
        self.assertEqual(self.find(zh="施主")["en"], "traveler")                  # all-pairs decision bullet
        self.assertEqual(self.find(zh="不买了")["en"], "Nothing, thanks")          # quoted pair inside a rule
        self.assertEqual(self.find(zh="白洞,白色的明天在等着我们")["subtype"], "catchphrase")
        # voices
        blue = self.find(type="voice", title="Blue")
        self.assertEqual(blue["zh"], "小绿")
        meowth = self.find(type="voice", title="Meowth")
        self.assertIn("Brooklyn", meowth["en"])
        # conflicts: 小美 Molly vs Mei
        molly, mei = self.find(zh="小美", en="Molly"), self.find(zh="小美", en="Mei")
        self.assertEqual((molly["status"], mei["status"]), ("needs-review", "needs-review"))
        self.assertIn(mei["id"], molly["conflicts_with"])
        # coordinator supersedes the agent rendering and resolves the question
        aqua = self.find(zh="水绿号", en="S.S. Aqua")
        anne = self.find(zh="水绿号", en="S.S. Anne")
        self.assertEqual((anne["source"], anne["status"]), ("coordinator", "accepted"))
        self.assertEqual((aqua["status"], aqua["superseded_by"]), ("superseded", anne["id"]))
        q = [r for r in recs if r["type"] == "question" and "水绿号" in r["en"]][0]
        self.assertEqual((q["status"], q["decision_id"]), ("resolved", anne["id"]))
        self.assertIn("a027/0253#16", q["refs"])
        self.assertIn("a027/0248#7", q["refs"])
        lorin = [r for r in recs if r["type"] == "question" and "梨琳" in r["en"]][0]
        self.assertEqual((lorin["status"], lorin["subtype"]), ("open", "verify-in-game"))
        route = [r for r in recs if r["type"] == "question" and "romance" in r["en"]][0]
        self.assertEqual(route["subtype"], "context-note")
        self.assertIn("a027/0445#151-242", route["refs"])
        scope = self.find(subtype="scope")
        self.assertEqual((scope["type"], scope["status"]), ("technical", "accepted"))

    def test_real_progress_idempotent(self):
        if not REAL_PROGRESS.exists():
            self.skipTest("no PROGRESS.md")
        copy = self.tmp / "REAL_PROGRESS.md"
        shutil.copy(REAL_PROGRESS, copy)
        self.run_cli("import-progress", "--progress", str(copy))
        recs = self.recs()
        self.assertGreater(len(recs), 300)
        self.assertTrue(all(r["type"] in D.TYPES and r["status"] in D.STATUSES for r in recs))
        self.assertTrue(all(r.get("origin_line") for r in recs))
        out = self.run_cli("import-progress", "--progress", str(copy))
        self.assertIn("skipped_hash", out)
        self.assertNotIn("added ", out)
        self.assertEqual(len(self.recs()), len(recs))


class TestEditing(Base):
    def test_add_set_resolve(self):
        rid = self.run_cli("add", "--type", "term", "--subtype", "character", "--zh", "小豪", "--en", "Goh",
                           "--ref", "a027/0901#1", "--source", "agent:B046").strip()
        self.assertEqual(rid, "D-0001")
        # same zh + same en -> existing id, nothing added
        again = self.run_cli("add", "--type", "term", "--zh", "小豪", "--en", "Goh").strip()
        self.assertEqual(again, "D-0001")
        self.assertEqual(len(self.recs()), 1)
        # same zh + other en -> refused unless --force
        _o, err, code = self.run_cli("add", "--type", "term", "--zh", "小豪", "--en", "Go", expect_exit=True)
        self.assertNotEqual(code, 0)
        self.run_cli("set", "D-0001", "status=accepted", "refs+=a027/0902#0", "confidence=high",
                     "--reason", "checked", "--by", "user")
        r = self.recs()[0]
        self.assertEqual(r["status"], "accepted")
        self.assertEqual(r["refs"], ["a027/0901#1", "a027/0902#0"])
        self.assertEqual([h["field"] for h in r["history"]], ["status", "refs", "confidence"])
        self.assertEqual(r["history"][0]["by"], "user")
        _o, _e, code = self.run_cli("set", "D-0001", "status=bogus", expect_exit=True)
        self.assertNotEqual(code, 0)
        qid = self.run_cli("add", "--type", "question", "--en", "Is 小豪 Goh?").strip()
        self.assertEqual(self.find(id=qid)["status"], "open")
        self.run_cli("resolve", qid, "--answer", "Yes", "--decision-id", "1")
        q = self.find(id=qid)
        self.assertEqual((q["status"], q["answer"], q["decision_id"]), ("resolved", "Yes", "D-0001"))
        listing = self.run_cli("list", "--type", "term")
        self.assertIn("D-0001", listing)
        self.assertNotIn(qid, listing)
        self.assertIn("Goh", self.run_cli("show", "D-0001"))
        self.assertIn("小豪 → Goh", self.run_cli("render-progress"))

    def test_set_redact_old(self):
        rid = self.run_cli("add", "--type", "content", "--en", "zh 秘密歌词 is a lyric; hum line").strip()
        self.run_cli("set", rid, "en=zh quotes a song line; hum line", "--redact-old", "--reason", "lyrics")
        r = self.find(id=rid)
        self.assertEqual(r["en"], "zh quotes a song line; hum line")
        self.assertEqual((r["history"][-1]["old"], r["history"][-1]["new"]),
                         (D.REDACTED, "zh quotes a song line; hum line"))
        self.assertNotIn("秘密歌词", json.dumps(self.recs(), ensure_ascii=False))


class TestWorkspace(Base):
    def setUp(self):
        super().setUp()
        self.imp()
        self.kin = self.find(zh="金婆婆", type="term")["id"]
        self.alto = self.find(zh="水都")["id"]

    def test_usages(self):
        wsdata = D.load_ws(self.ws)
        recs = self.recs()
        res = D.usages_for(D.by_id(recs, self.kin), wsdata, D.TermIndex(recs))
        self.assertEqual(res["total"], 7)
        self.assertEqual(len(res["untranslated"]), 1)
        self.assertEqual(sorted(r for r, _ in res["inconsistent"]), ["a027/0901#2"])
        self.assertIn("a027/0901#8", [r for r, _ in res["consistent"]])     # match across {NEWLINE}
        self.assertIn("a027/0901#5", [r for r, _ in res["consistent"]])     # all caps
        alto = D.usages_for(D.by_id(recs, self.alto), wsdata, D.TermIndex(recs))
        self.assertEqual(alto["shadowed"]["水都群岛"], 1)
        self.assertEqual(alto["total"], 2)
        out = self.run_cli("usages", self.kin)
        self.assertIn("possible inconsistencies: 1", out)

    def test_rename_dry_run_changes_nothing(self):
        before = {p: p.read_bytes() for p in self.ws.rglob("*.json")}
        reg_before = self.reg.read_bytes()
        out = self.run_cli("rename", self.kin, "--en", "Granny Gold", "--reason", "test", "--dry-run")
        self.assertIn("- Granny Kin: Hello!", out)
        self.assertIn("+ Granny Gold: Hello!", out)
        self.assertEqual(before, {p: p.read_bytes() for p in self.ws.rglob("*.json")})
        self.assertEqual(reg_before, self.reg.read_bytes())
        self.assertFalse(self.snap.exists())

    def test_rename_apply(self):
        out = self.run_cli("rename", self.kin, "--en", "Granny Gold", "--reason", "user prefers Gold")
        a, b = self.bank(901)["strings"], self.bank(902)["strings"]
        self.assertEqual(a[0]["en"], "Granny Gold: Hello!{SCROLL}Goodbye!")
        self.assertEqual(a[1]["en"], "I’m Granny Gold, dearie.")
        self.assertEqual(a[1]["status"], "draft")                               # reviewed -> draft
        self.assertIn(f"[{self.kin} rename 2026-09-28: Granny Kin → Granny Gold]", a[1]["notes"])
        self.assertEqual(a[5]["en"], "GRANNY GOLD!{SCROLL}Ha ha.")               # case preserved
        self.assertEqual(a[8]["en"], "I heard Granny Gold is in Alto Mare.{SCROLL}Really?")
        self.assertEqual(a[2]["en"], "The old lady is here.")                   # not found: untouched
        self.assertEqual(a[4]["notes"], "")                                     # unrelated
        self.assertEqual(b[0]["en"], "Granny Gold’s company.")
        self.assertEqual(b[1]["notes"], "")
        rec = self.find(id=self.kin)
        self.assertEqual(rec["en"], "Granny Gold")
        self.assertIn("Granny Kin", rec["alternatives"])
        self.assertEqual(rec["history"][-2]["reason"], "user prefers Gold")
        snaps = list(self.snap.glob("*.tgz"))
        self.assertEqual(len(snaps), 1)
        with tarfile.open(snaps[0]) as tf:
            names = tf.getnames()
            self.assertIn("translate/banks/a027/0901.json", names)
            old = json.load(tf.extractfile("translate/banks/a027/0901.json"))
            self.assertEqual(old["strings"][0]["en"], "Granny Kin: Hello!{SCROLL}Goodbye!")
        rw = list((self.reg.parent / "rewrap").glob("*.tsv"))
        self.assertEqual(len(rw), 1)
        txt = rw[0].read_text(encoding="utf-8")
        self.assertIn("a027/0901#8\tmatch spanned a line break", txt)
        self.assertIn("a027/0901#2\tzh has the term but the old English was not found", txt)
        self.assertIn("qa.py check a027/0901: 0 errors", out)

    def test_rename_qa_hook_reports_overflow(self):
        long = "Granny Goldilocks-Wellington-Smythe"
        res = D.do_rename(self.reg, self.ws, self.snap, self.kin, long, "test", "tester", out=io.StringIO())
        codes = {c for _r, c, _m in res["new_errors"]}
        self.assertIn("line_too_wide", codes)
        txt = Path(res["rewrap_file"]).read_text(encoding="utf-8")
        self.assertIn("line_too_wide", txt)
        self.assertIn("qa.py wrap", txt)

    def test_rename_shadowed_left_alone(self):
        self.run_cli("rename", self.alto, "--en", "Aquamare", "--reason", "test")
        a = self.bank(901)["strings"]
        self.assertEqual(a[7]["en"], "Aquamare is lovely.{SCROLL}Yes.")
        self.assertEqual(a[6]["en"], "Welcome to the Alto Mare Islands!")      # governed by 水都群岛

    def test_report_and_csv_import(self):
        out = self.run_cli("report")
        md = (self.reg.parent / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("## Needs your review", md)
        self.assertLess(md.index("## Needs your review"), md.index("## Terms"))
        self.assertIn("Granny Kin", md)
        self.assertIn("wrote", out)
        csv_path = self.reg.parent / "decisions.csv"
        rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig"))))
        kin_row = next(r for r in rows if r["id"] == self.kin)
        self.assertEqual(kin_row["usages"], "7")
        self.assertEqual(kin_row["consistent"], "5")
        red_id = self.find(zh="小赤")["id"]
        for r in rows:
            if r["id"] == self.kin:
                r["en"] = "Granny Gold"
            if r["id"] == red_id:
                r["status"] = "accepted"
                r["review_note"] = "fine"
        edited = self.tmp / "edited.csv"
        with open(edited, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=D.CSV_FIELDS)
            w.writeheader()
            w.writerows(rows)
        before = self.reg.read_bytes()
        dry = self.run_cli("import-csv", str(edited))
        self.assertIn("rename en", dry)
        self.assertIn("set    status", dry)
        self.assertIn("dry run", dry)
        self.assertEqual(before, self.reg.read_bytes())
        self.assertEqual(self.bank(901)["strings"][1]["en"], "I’m Granny Kin, dearie.")
        self.run_cli("import-csv", str(edited), "--apply", "--by", "user")
        self.assertEqual(self.bank(901)["strings"][1]["en"], "I’m Granny Gold, dearie.")
        self.assertEqual(self.find(id=self.kin)["en"], "Granny Gold")
        red = self.find(id=red_id)
        self.assertEqual(red["status"], "accepted")
        self.assertEqual(red["history"][-1]["by"], "user")
        self.assertTrue(red["review_notes"][0].endswith("fine"))
        # re-importing the same CSV only finds nothing new for en (already renamed)
        again = self.run_cli("import-csv", str(edited))
        self.assertNotIn("rename", again)


class TestParsingHelpers(unittest.TestCase):
    def test_split_en(self):
        self.assertEqual(D.split_en("Rayquaza Jr."), ("Rayquaza Jr.", ""))
        self.assertEqual(D.split_en("Snowball (official item)"), ("Snowball", "(official item)"))
        self.assertEqual(D.split_en("the (League) construction ban")[0], "the construction ban")
        self.assertEqual(D.split_en("“Idol” / “my idol”")[0], "Idol")
        self.assertEqual(D.split_en("Hurricane. Slot 542 is official")[0], "Hurricane")
        self.assertEqual(D.split_en("Silph Co.")[0], "Silph Co.")

    def test_refs(self):
        self.assertEqual(D.extract_refs("a027/0448 #75 and battle_string/0001 #4–7, 0476 #14/#19"),
                         ["a027/0448#75", "battle_string/0001#4-7", "a027/0476#14", "a027/0476#19"])

    def test_rename_text(self):
        self.assertEqual(D.rename_text("the Pokémon Academy’s gate", ["the Pokémon Academy"], "the Pokémon School")[0],
                         "the Pokémon School’s gate")
        self.assertEqual(D.rename_text("The Pokémon Academy!", ["the Pokémon Academy"], "the Pokémon School")[0],
                         "The Pokémon School!")
        self.assertEqual(D.rename_text("Kinetic Kin.", ["Kin"], "Gold")[0], "Kinetic Gold.")
        self.assertEqual(D.rename_text("Boss! The boss.", ["Boss"], "Chief")[0], "Chief! The chief.")



class RepoPathTest(unittest.TestCase):
    def test_rewrap_paths_are_repo_relative(self):
        inside = D.WORK / "translate" / "banks" / "a027" / "0091.json"
        self.assertEqual(D.repo_path(inside), "work/translate/banks/a027/0091.json")
        outside = Path(tempfile.gettempdir()) / "x.json"
        self.assertEqual(D.repo_path(outside), str(outside))


if __name__ == "__main__":
    unittest.main()
