#!/usr/bin/env python3
"""Tests for textmetrics.py, qa.py and ws.py.   Run:  python3 -m unittest -v work/tools/test_qa.py"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qa  # noqa: E402
import textmetrics as tm  # noqa: E402
import ws  # noqa: E402


def bank(strings, category=None, narc="a027", no=999):
    b = {"narc": narc, "bank": no, "strings": []}
    if category:
        b["category"] = category
    for i, (zh, en) in enumerate(strings):
        b["strings"].append({"id": i, "zh": zh, "en": en, "status": "draft", "origin": "agent", "notes": ""})
    return b


def codes(issues, level=None):
    return sorted({i["code"] for i in issues if level is None or i["level"] == level})


class TestMetrics(unittest.TestCase):
    def test_tokenize(self):
        t = tm.tokenize("Hi {VAR:0101:0,0}!{NEWLINE}Ok\nyes{SCROLL}")
        self.assertEqual([k for k, _ in t], ["text", "var", "text", "layout", "text", "layout", "text", "layout"])
        self.assertEqual(tm.non_layout_tags("a{VAR:0200:0}{NEWLINE}"), ["VAR:0200:0"])

    def test_widths_vanilla(self):
        fs = tm.font_set("vanilla_us")
        self.assertEqual(tm.measure_lines("Hello", 1, widths=fs)[0]["px"], 6 + 6 + 4 + 4 + 6)
        self.assertEqual(tm.char_width(" ", 1, fs), 4)
        self.assertEqual(tm.char_width("i", 1, fs), 3)

    def test_widths_hack_font(self):
        fs = tm.font_set("hack_v4")
        self.assertEqual(tm.char_width("“", 1, fs), 12)          # CJK-width quote in the hack font
        self.assertIsNone(tm.char_width("Æ", 1, fs))             # glyph blanked in font 1
        self.assertEqual(tm.char_width("的", 1, fs), 12)          # hanzi fixed width

    def test_var_widths(self):
        self.assertEqual(tm.var_width("VAR:0200:0"), 0)          # YESNO prints nothing
        self.assertEqual(tm.var_width("VAR:0135:0,0"), 4 * 6)    # number kind 0x35 -> 4 digits
        lines = tm.measure_lines("{VAR:0203:100}ab", 1, widths=tm.font_set("vanilla_us"))
        self.assertEqual(lines[0]["px"], 112)                   # CURSOR_X sets x

    def test_page_model(self):
        self.assertEqual(tm.page_lines("a{NEWLINE}b"), 2)
        self.assertEqual(tm.page_lines("a{NEWLINE}b{NEWLINE}c"), 3)
        self.assertEqual(tm.page_lines("a{NEWLINE}b{SCROLL}c{NEWLINE}d"), 2)   # 0x25BC clears the box
        self.assertEqual(tm.page_lines("a{NEWLINE}b{CLEAR}c{CLEAR}d"), 2)      # 0x25BD scrolls, stays on line 2
        self.assertEqual(tm.page_lines("a{NEWLINE}b{CLEAR}c{NEWLINE}d"), 3)    # NEWLINE after a scroll overflows
        self.assertEqual(tm.page_lines("a{NEWLINE}b{NEWLINE}"), 2)             # trailing NEWLINE prints nothing
        big, norm = "{VAR:FF01:200}", "{VAR:FF01:100}"
        self.assertEqual(tm.page_lines(big + "Stop!" + norm), 2)                 # a 200% line fills the box
        self.assertEqual(tm.page_lines(big + "Stop,{NEWLINE}Gyarados!" + norm), 4)  # rc3 Misty crash
        self.assertEqual(tm.page_lines("Go!{SCROLL}" + big + "Win!{SCROLL}"), 2)  # Pokeathlon: own page
        self.assertEqual(tm.page_lines(big + "Hey!" + norm + "{SCROLL}a{NEWLINE}b"), 2)


class TestQA(unittest.TestCase):
    def run_one(self, zh, en, category="dialogue", font_set="vanilla_us"):
        return qa.check_bank(bank([(zh, en)], category), fset_name=font_set)

    def test_clean(self):
        iss = self.run_one("你好，{VAR:0101:0,0}！{NEWLINE}今天天气不错。", "Hello, {VAR:0101:0,0}!{NEWLINE}Nice weather today.")
        self.assertEqual(codes(iss, "error"), [])

    def test_size_span_split_over_pages(self):
        big, norm = "{VAR:FF01:200}", "{VAR:FF01:100}"
        iss = self.run_one(big + "小霞『暴鲤龙快住手！" + norm, big + "Misty: Stop," + norm + "{SCROLL}" + big + "Gyarados!" + norm)
        self.assertEqual(codes(iss, "error"), [])
        iss = self.run_one(big + "小霞『暴鲤龙快住手！" + norm, big + "Misty: Stop,{NEWLINE}Gyarados!" + norm)
        self.assertIn("too_many_lines", codes(iss, "error"))

    def test_tag_mismatch(self):
        iss = self.run_one("{VAR:0101:0,0}使用了{VAR:0106:1,0}！", "{VAR:0101:0,0} used a move!")
        self.assertIn("tag_mismatch", codes(iss, "error"))

    def test_tag_position(self):
        iss = self.run_one("要吗？{VAR:0200:0}", "{VAR:0200:0}Do you want it?")
        self.assertIn("tag_order", codes(iss, "error"))
        iss = self.run_one("{VAR:FF00:2}红{VAR:FF00:0}和蓝", "{VAR:FF00:0}Red{VAR:FF00:2} and blue")
        self.assertIn("tag_order", codes(iss, "error"))

    def test_cjk_and_fullwidth(self):
        iss = self.run_one("你好", "Hello 你")
        self.assertIn("cjk", codes(iss, "error"))
        iss = self.run_one("你好！", "Hello！")
        self.assertIn("fullwidth", codes(iss, "warning"))

    def test_unencodable_ascii_quote(self):
        iss = self.run_one("我的", "It's mine")
        self.assertIn("unencodable", codes(iss, "error"))
        self.assertEqual(codes(self.run_one("我的", "It’s mine"), "error"), [])

    def test_missing_glyph_hack_font(self):
        iss = self.run_one("甲", "Æon", font_set="hack_v4")
        self.assertIn("missing_glyph", codes(iss, "error"))
        self.assertNotIn("missing_glyph", codes(self.run_one("甲", "Æon"), "error"))

    def test_width(self):
        long = "This line is definitely much too long to fit in the box"
        self.assertIn("line_too_wide", codes(self.run_one("短", long), "error"))
        self.assertIn("line_too_wide", codes(self.run_one("短", long, "battle"), "error"))
        ok = "This line fits into the message box."
        self.assertNotIn("line_too_wide", codes(self.run_one("短", ok)))

    def test_width_needs_vanilla(self):
        # 35 x 6 px = 210 px + quotes: 222 px with the hack's 12 px “ ” (vanilla: 6 px each -> 216)
        en = "“" + "a" * 34 + "”"
        iss = self.run_one("短", en)
        self.assertEqual(codes(iss, "error"), [])
        self.assertIn("needs_vanilla_glyphs", codes(iss, "warning"))

    def test_lines(self):
        iss = self.run_one("甲{NEWLINE}乙", "one{NEWLINE}two{NEWLINE}three")
        self.assertIn("too_many_lines", codes(iss, "error"))
        iss = self.run_one("甲{NEWLINE}乙{NEWLINE}丙", "one{NEWLINE}two{NEWLINE}three")
        self.assertIn("too_many_lines", codes(iss, "warning"))      # zh has it too -> warning only

    def test_names(self):
        iss = qa.check_bank(bank([("妙蛙种子", "Bulbasaurus Rex")], "species"), fset_name="vanilla_us")
        self.assertIn("name_too_long", codes(iss, "error"))
        iss = qa.check_bank(bank([("妙蛙种子", "Bulba{NEWLINE}saur")], "species"), fset_name="vanilla_us")
        self.assertIn("layout_in_name", codes(iss, "error"))
        iss = qa.check_bank(bank([("妙蛙种子", "Ivysaur")], "species"), fset_name="vanilla_us")
        self.assertIn("glossary", codes(iss, "warning"))
        iss = qa.check_bank(bank([("妙蛙种子", "Bulbasaur")], "species"), fset_name="vanilla_us")
        self.assertEqual(iss, [])

    def test_trainer_name_buffer(self):
        # a027/0719 is stored {COMPRESSED}: <= 10 chars, codes < 0x1FF; Frontier Brains (707-711) plain <= 7
        def run(entries):
            b = {"narc": "a027", "bank": 719, "strings": [
                {"id": i, "zh": "名字", "en": en, "status": "draft", "origin": "agent", "notes": ""}
                for i, en in entries]}
            return qa.check_bank(b, fset_name="vanilla_us", glossary=False)
        self.assertEqual(run([(1, "Giovanni"), (2, "Kangaskhan"), (3, "Lt. Surge"), (707, "Palmer")]), [])
        self.assertIn("name_too_long", codes(run([(1, "Kangaskhans")]), "error"))
        self.assertIn("not_compressible", codes(run([(1, "Gio\nvanni")]), "error"))   # 0xE000 newline
        self.assertIn("name_tag", codes(run([(1, "{VAR:0103:0}")]), "error"))
        self.assertIn("name_too_long", codes(run([(708, "Argentaa")]), "error"))
        # Frontier trainer names (0026) are copied plain into u16[8]
        b = bank([("名字", "Thorton"), ("名字", "Thorntons")], narc="a027", no=26)
        self.assertEqual([i["id"] for i in qa.check_bank(b, fset_name="vanilla_us") if i["code"] == "name_too_long"], [1])

    def test_glossary_prose(self):
        iss = self.run_one("我抓到了妙蛙种子！", "I caught a frog!")
        self.assertIn("glossary", codes(iss, "warning"))
        self.assertNotIn("glossary", codes(self.run_one("我抓到了妙蛙种子！", "I caught a Bulbasaur!")))
        b = bank([("我抓到了妙蛙种子！", "I caught a frog!")], "dialogue")
        b["strings"][0]["qa_ignore"] = ["glossary:妙蛙种子"]
        self.assertEqual(qa.check_bank(b, fset_name="vanilla_us"), [])

    def test_numbers_currency(self):
        iss = self.run_one("给你１０００元", "Here you go.")
        self.assertIn("number_missing", codes(iss, "warning"))
        self.assertIn("currency", codes(iss, "warning"))
        self.assertEqual(codes(self.run_one("给你１０００元", "Here’s $1000."), "warning"), [])

    def test_route_template_requires_matching_explicit_identifiers(self):
        # Isolate the generic glossary entry from longer exact location entries.
        with patch.object(qa, "glossary_matcher", return_value=(re.compile("号道路"), {"号道路": ["Route N"]})):
            for zh, en in (("1号道路", "Route 1"), ("１２号道路", "Route 12"),
                           ("1号道路和12号道路", "Route 12 and Route 1"),
                           ("{VAR:FF00:1}1{VAR:FF00:0}号道路", "Route {VAR:FF00:1}1{VAR:FF00:0}."),
                           ("12号道路", "Route{NEWLINE}12")):
                with self.subTest(zh=zh, en=en):
                    self.assertNotIn("glossary", codes(self.run_one(zh, en)))
            for zh, en in (("1号道路", "Route 12"), ("12号道路", "Route 1"),
                           ("1号道路和12号道路", "Route 1"), ("1号道路", "Route N"),
                           ("1号道路", "Route 1st"), ("1号道路", "MyRoute 1"),
                           ("1号道路", "Route 1.5"), ("1号道路", "Route 1,500"),
                           ("1号道路", "Route 1{VAR:0132:0}"),
                           ("1号道路", "Route {VAR:0132:0}1"),
                           ("1.5号道路", "Route 5"),
                           ("{VAR:0132:0}1号道路", "Route 1"),
                           ("1{VAR:0132:0}号道路", "Route 1"),
                           ("{VAR:0134:0}号道路", "Route {VAR:0134:0}"),
                           ("1号道路和1号道路", "Route 1")):
                with self.subTest(zh=zh, en=en):
                    self.assertIn("glossary", codes(self.run_one(zh, en)))

    def test_count_noun_plurals_in_prose_only(self):
        for zh, en in (("树果", "Berries"), ("神奇糖果", "Rare Candies"), ("橘果", "Oran Berries")):
            self.assertNotIn("glossary", codes(self.run_one(zh, en)))
        self.assertIn("glossary", codes(self.run_one("神奇糖果", "Candies")))
        self.assertIn("glossary", codes(self.run_one("橘果", "Sitrus Berries")))
        self.assertIn("glossary", codes(self.run_one("橘果", "Oran Berries", category="items")))
        self.assertIn("glossary", codes(self.run_one("神奇糖果", "Rare Candies", category="items")))
        self.assertTrue(qa._count_noun_plural_matches("Oran Berry", "Two Oran Berries."))
        self.assertTrue(qa._count_noun_plural_matches("Oran Berry", "Oran{NEWLINE}Berries"))
        self.assertFalse(qa._count_noun_plural_matches("Oran Berry", "Two Sitrus Berries."))
        self.assertFalse(qa._count_noun_plural_matches("Oran Berry", "Oran BerriesExtra"))
        self.assertFalse(qa._count_noun_plural_matches("City", "Cities"))

    def test_empty(self):
        self.assertIn("empty", codes(self.run_one("你好", ""), "error"))

    def test_number_runs_do_not_merge_across_tags(self):
        for boundary in ("{NEWLINE}", "{CLEAR}", "{SCROLL}", "\n", "{VAR:0103:0}", "{VAR:FF00:1}"):
            with self.subTest(boundary=boundary):
                zh = "14" + boundary + "5500"
                self.assertNotIn("number_missing", codes(self.run_one(zh, "14 and 5500")))
                self.assertNotIn("number_missing", codes(self.run_one("14 and 5500", zh)))
                self.assertIn("number_missing", codes(self.run_one(zh, "14 and 500")))
        self.assertIn("number_missing", codes(self.run_one("14 14", "14")))
        self.assertIn("number_missing", codes(self.run_one("14", "{VAR:0134:14}")))
        self.assertNotIn("number_missing", codes(self.run_one("{VAR:0134:14}", "Nothing")))

    def test_spacing_keeps_rendered_placeholders(self):
        for en in ("{VAR:0103:0} wins!", "Hello {VAR:0103:0}",
                   "Hi {VAR:0103:0} there", "{VAR:0103:0} {VAR:0101:1}",
                   "{U+01AF} word", "word {U+01AF}"):
            with self.subTest(en=en):
                self.assertNotIn("whitespace", codes(self.run_one("你好", en)))

    def test_spacing_retains_real_defects_around_tags(self):
        for en in (" {VAR:0103:0} wins", "Hello {VAR:0103:0} ",
                   "Hi  {VAR:0103:0}", "{VAR:0103:0}  wins",
                   "{VAR:FF00:1} word", "word {VAR:0200:0}",
                   "one {VAR:FF00:1} two", "{COMPRESSED} word",
                   "word{NEWLINE} next", "word{SCROLL} next", "word{CLEAR} next"):
            with self.subTest(en=en):
                self.assertIn("whitespace", codes(self.run_one("你好", en)))

    def test_spacing_source_placeholders_do_not_hide_defects(self):
        self.assertIn("whitespace", codes(self.run_one("{VAR:0103:0} 好", " bad")))
        self.assertNotIn("whitespace", codes(self.run_one(" 好", " bad")))
        self.assertNotIn("whitespace", codes(self.run_one("你好", "{VAR:FF00:1}Good")))

    def test_currency_requires_an_amount_not_just_closing_brace(self):
        for zh in ("得到{NEWLINE}元气块！", "{VAR:FF00:1}元气块", "{VAR:0103:0}元气充足",
                   "2元气块", "{U+01AF}元"):
            with self.subTest(zh=zh):
                self.assertNotIn("currency", codes(self.run_one(zh, "Item.")))
        for zh in ("100元", "１００元", "100{VAR:FF00:1}元", "{VAR:0134:1}元",
                   "{VAR:0137:10}元", "100{NEWLINE}元"):
            with self.subTest(zh=zh):
                self.assertIn("currency", codes(self.run_one(zh, "Money.")))
                self.assertNotIn("currency", codes(self.run_one(zh, "$100")))

    def test_dex_category_char_spacing(self):
        # Pokédex category (D-1520): font px + 1 px per character <= 125
        ok = qa.check_bank(bank([("毒蛾精灵", "PoisonMoth Pokémon")], "dex_category"), fset_name="vanilla_us")
        self.assertEqual(codes(ok, "error"), [])
        bad = qa.check_bank(bank([("毒蛾精灵", "Poison Moth Pokémon")], "dex_category"), fset_name="vanilla_us")
        self.assertIn("line_too_wide", codes(bad, "error"))          # 107 px + 19 chars = 126

    def test_item_desc_frame_and_buffer(self):
        # 34 x 6 = 204 px: fits the window (215) but runs into the bag frame (200) -> warning only
        iss = qa.check_bank(bank([("甲", "a" * 34)], "item_desc"), fset_name="vanilla_us")
        self.assertEqual(codes(iss, "error"), [])
        self.assertIn("line_past_frame", codes(iss, "warning"))
        self.assertNotIn("line_past_frame", codes(qa.check_bank(bank([("甲", "a" * 33)], "item_desc"),
                                                                fset_name="vanilla_us")))
        # 114 stored units incl. terminator fit (D-1507); 115 show a blank panel
        fits = "{NEWLINE}".join(["iiii " * 7 + "iii"] * 3)                   # 3 x 38 chars, 2 breaks, end
        self.assertEqual(len(tm.visible_text(fits)) + 3, 117)
        fits = fits[:-3]                                                     # 111 + 2 + 1 = 114 units
        self.assertNotIn("too_many_units", codes(qa.check_bank(bank([("甲", fits)], "item_desc"))))
        over = fits + "x"
        self.assertIn("too_many_units", codes(qa.check_bank(bank([("甲", over)], "item_desc")), "error"))

    def test_battle_prompt_icons(self):
        # the view that ends with {VAR:0200:0} keeps its lines left of the prompt icons (195 px); other battle
        # lines may use the full 216 px; a moved break fixes it
        long = "Would you like to forfeit the match and"                           # 208 px
        iss = qa.check_bank(bank([("要放弃对战吗？{VAR:0200:0}", long + "{NEWLINE}quit now?{VAR:0200:0}")],
                                 narc="battle_string", no=2), fset_name="vanilla_us")
        self.assertIn("prompt_icon_overlap", codes(iss, "error"))
        ok = "Would you like to forfeit the{NEWLINE}match and quit now?{VAR:0200:0}"
        self.assertEqual(codes(qa.check_bank(bank([("要放弃对战吗？{VAR:0200:0}", ok)], narc="battle_string", no=2),
                                             fset_name="vanilla_us"), "error"), [])
        no_prompt = qa.check_bank(bank([("对战", long)], narc="battle_string", no=2), fset_name="vanilla_us")
        self.assertNotIn("prompt_icon_overlap", codes(no_prompt))
        # only the prompt's own view counts: an earlier page may be wider
        paged = long + "{SCROLL}Quit now?{VAR:0200:0}"
        self.assertNotIn("prompt_icon_overlap", codes(qa.check_bank(
            bank([("对战{SCROLL}吗？{VAR:0200:0}", paged)], narc="battle_string", no=2), fset_name="vanilla_us")))

    def test_battle_move_buffer_worst_case(self):
        # battle_string {VAR:0107} is a move name (up to 12 characters, 72 px): a line that fits only with a
        # short move name warns (seen in game: 'DragonBreath..' cut at the window edge)
        iss = qa.check_bank(bank([("{VAR:010C:0,0}想要学习{NEWLINE}{VAR:0107:1,0}……",
                                   "{VAR:010C:0,0} wants to learn {VAR:0107:1,0}...")], narc="battle_string", no=2),
                            fset_name="vanilla_us")
        self.assertIn("line_may_overflow", codes(iss, "warning"))
        self.assertEqual(codes(iss, "error"), [])

    def test_string_categories(self):
        cfg = tm.load_config()
        cfg = dict(cfg, string_categories={"a027/0999": {"0-1": "gear_map", "1": "gear_map_town"}})
        line = "A beautiful city that is enveloped"                   # 180 px
        b = bank([("甲", line), ("乙", line)])
        self.assertEqual(qa.string_categories(b, cfg), {0: "gear_map", 1: "gear_map_town"})
        iss = qa.check_bank(b, cfg, fset_name="vanilla_us")
        self.assertEqual([(i["id"], i["code"]) for i in iss if i["level"] == "error"], [(1, "line_too_wide")])

    def test_ui_relative(self):
        b = bank([("背包", "Bag"), ("宝可梦", "Pokémon Party Menu Screen")], "ui")
        iss = qa.check_bank(b, fset_name="vanilla_us")
        self.assertIn("wider_than_zh", codes(iss, "warning"))
        self.assertEqual(codes(iss, "error"), [])


class TestWrap(unittest.TestCase):
    def test_two_lines(self):
        out = qa.wrap("Hello there! Welcome to the world of Pokémon. I hope you enjoy it.", "你好{NEWLINE}欢迎")
        self.assertEqual(tm.layout_tags(out), ["NEWLINE"])
        for ln in tm.measure_lines(out, 1):
            self.assertLessEqual(ln["px"], 216)

    def test_paragraphs_follow_zh(self):
        zh = "你好！{SCROLL}这是专访！{CLEAR}可以吗？{VAR:0200:0}"
        out = qa.wrap("Hello!\n\nThis is an interview!\n\nCan you talk? {VAR:0200:0}", zh)
        self.assertEqual(out, "Hello!{SCROLL}This is an interview!{CLEAR}Can you talk? {VAR:0200:0}")

    def test_overflow_continuation(self):
        text = " ".join(["word"] * 60)
        page = qa.wrap(text, "甲{SCROLL}乙", mode="page")
        self.assertIn("{SCROLL}", page)
        self.assertLessEqual(tm.page_lines(page), 2)
        scroll = qa.wrap(text, "甲{CLEAR}乙", mode="scroll")
        self.assertNotIn("{SCROLL}", scroll)
        self.assertLessEqual(tm.page_lines(scroll), 2)
        auto = qa.wrap(text, "甲{NEWLINE}乙{CLEAR}丙{CLEAR}丁")
        self.assertIn("{CLEAR}", auto)
        self.assertNotIn("{SCROLL}", auto)

    def test_trailing_and_quotes(self):
        out = qa.wrap("It's \"fine\".", "好的。{NEWLINE}")
        self.assertEqual(out, "It’s “fine”.{NEWLINE}")

    def test_wrapped_passes_check(self):
        zh = "{VAR:0101:0,0}的{NEWLINE}攻击巨幅提高了！"
        en = qa.wrap("The opposing trainer's {VAR:0101:0,0}'s Attack rose drastically, and it keeps going!", zh,
                     "battle")
        iss = qa.check_bank(bank([(zh, en)], "battle"), fset_name="vanilla_us")
        self.assertEqual(codes(iss, "error"), [])

    def test_soft_limit_preferred(self):
        # item_desc wraps at the 200 px soft limit when three lines still suffice, else at 215 px
        en = "A device for catching wild Pokémon. It is thrown like a ball at the target. Okay."
        out = qa.wrap(en, "甲{NEWLINE}乙", "item_desc")
        self.assertTrue(all(ln["px"] <= 200 for ln in tm.measure_lines(out, 0)))
        en = "A device for catching wild Pokémon. It is thrown like a ball at the target. It is designed as a capsule system."
        out = qa.wrap(en, "甲{NEWLINE}乙", "item_desc")
        self.assertEqual(tm.page_lines(out), 3)
        self.assertTrue(max(ln["px"] for ln in tm.measure_lines(out, 0)) > 200)

    def test_reflow(self):
        zh = "甲{SCROLL}乙"
        once = qa.wrap("First part here.\n\nSecond part.", zh)
        again = qa.wrap(once, zh, reflow=True)
        self.assertEqual(once, again)


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.extract = root / "extract"
        self.wsdir = root / "ws"
        self.out = root / "build"
        nd = self.extract / "a027"
        nd.mkdir(parents=True)
        (nd / "_meta.json").write_text(json.dumps({"narc": "a/0/2/7"}))
        self.src = {"bank": 5, "seed": 123, "strings": [
            {"id": 0, "text": "你好{NEWLINE}世界"},
            {"id": 1, "text": "-----"},
            {"id": 2, "text": "再见"},
            {"id": 3, "text": "Debug text"},
        ]}
        (nd / "0005.json").write_text(json.dumps(self.src, ensure_ascii=False))

    def tearDown(self):
        self.tmp.cleanup()

    def load(self):
        return json.loads((self.wsdir / "a027" / "0005.json").read_text(encoding="utf-8"))

    def test_init_export_roundtrip(self):
        ws.main(["--ws", str(self.wsdir), "init", "--extract", str(self.extract)])
        b = self.load()
        e = {x["id"]: x for x in b["strings"]}
        self.assertEqual(e[0]["status"], "todo")
        self.assertIsNone(e[0]["en"])
        self.assertEqual((e[1]["en"], e[1]["origin"], e[1]["status"]), ("-----", "copy", "reviewed"))
        self.assertEqual((e[3]["en"], e[3]["status"]), ("Debug text", "draft"))
        # translate one, re-init must keep it
        e[0].update({"en": "Hello{NEWLINE}world", "status": "draft", "origin": "agent"})
        e[2].update({"en": "Bye's", "status": "draft", "origin": "agent"})   # unencodable ASCII '
        ws.save_json(self.wsdir / "a027" / "0005.json", b)
        ws.main(["--ws", str(self.wsdir), "init", "--extract", str(self.extract)])
        e = {x["id"]: x for x in self.load()["strings"]}
        self.assertEqual(e[0]["en"], "Hello{NEWLINE}world")
        counts, problems = ws.export(self.wsdir, self.extract, self.out, ("tm", "draft", "reviewed"))
        built = json.loads((self.out / "a027" / "0005.json").read_text(encoding="utf-8"))
        self.assertEqual(built["seed"], 123)
        self.assertEqual(built["strings"][0]["text"], "Hello{NEWLINE}world")
        self.assertEqual(built["strings"][2]["text"], "再见")          # unencodable -> fell back to zh
        self.assertTrue(any("unencodable" in p[3] for p in problems))
        self.assertTrue((self.out / "a027" / "_meta.json").exists())
        # status filter: only reviewed -> the draft falls back to zh
        ws.export(self.wsdir, self.extract, self.out, ("reviewed",))
        built = json.loads((self.out / "a027" / "0005.json").read_text(encoding="utf-8"))
        self.assertEqual(built["strings"][0]["text"], "你好{NEWLINE}世界")

    def test_export_compresses_trainer_names(self):
        import msgtool as m
        import build
        src = {"bank": 719, "seed": 7, "strings": [{"id": i, "text": "名"} for i in range(712)]}
        (self.extract / "a027" / "0719.json").write_text(json.dumps(src, ensure_ascii=False))
        ws.main(["--ws", str(self.wsdir), "init", "--extract", str(self.extract)])
        p = self.wsdir / "a027" / "0719.json"
        b = json.loads(p.read_text(encoding="utf-8"))
        names = {1: "Giovanni", 2: "Kangaskhan", 3: "Gold", 707: "Palmer"}
        for e in b["strings"]:
            if e["id"] in names:
                e.update({"en": names[e["id"]], "status": "draft", "origin": "agent"})
        ws.save_json(p, b)
        counts, problems = ws.export(self.wsdir, self.extract, self.out, ("draft",))
        built = json.loads((self.out / "a027" / "0719.json").read_text(encoding="utf-8"))
        t = {s["id"]: s["text"] for s in built["strings"]}
        self.assertEqual((t[1], t[2], t[3]), ("{COMPRESSED}Giovanni", "{COMPRESSED}Kangaskhan", "{COMPRESSED}Gold"))
        self.assertEqual(t[707], "Palmer")          # printed raw on the Frontier VS screen: stays plain
        self.assertEqual(t[0], "名")                 # untranslated Chinese stays plain
        self.assertEqual(counts["compressed"], 3)
        # the encoded bank passes the build's buffer check and decodes back to the English
        cm = m.Charmap.load([str(tm.CHARMAP_EN), str(Path(tm.CHARMAP_EN).parent / "charmaps" / "charmap_zh_xzonn_gen4.tsv")])
        data = m.json_to_bank(built, cm)
        self.assertTrue(build.verify_name_bank(data, tm.compressed_spec("a027", 719)).startswith("ok (3 compressed"))
        back = {s["id"]: s["text"] for s in m.bank_to_json(719, data, cm)["strings"]}
        self.assertEqual((back[1], back[707]), ("{COMPRESSED}Giovanni", "Palmer"))
        # a 9-10 character name that could not be packed would be dropped by the game: export refuses it
        b["strings"][4].update({"en": "Giovanni’s", "status": "draft"})
        b["strings"][708].update({"en": "Argentina", "status": "draft"})
        ws.save_json(p, b)
        _, problems = ws.export(self.wsdir, self.extract, self.out, ("draft",))
        bad = {pr[2] for pr in problems if pr[3].startswith("unencodable")}
        self.assertEqual(bad, {708})

    def test_zh_changed_and_stats(self):
        ws.main(["--ws", str(self.wsdir), "init", "--extract", str(self.extract)])
        b = self.load()
        b["strings"][2].update({"en": "Goodbye", "status": "draft"})
        ws.save_json(self.wsdir / "a027" / "0005.json", b)
        self.src["strings"][2]["text"] = "再见了"
        (self.extract / "a027" / "0005.json").write_text(json.dumps(self.src, ensure_ascii=False))
        ws.main(["--ws", str(self.wsdir), "init", "--extract", str(self.extract)])
        e = self.load()["strings"][2]
        self.assertTrue(e["zh_changed"])
        self.assertEqual((e["en"], e["zh"], e["zh_old"]), ("Goodbye", "再见了", "再见"))
        st = ws.stats(self.wsdir)["total"]
        self.assertEqual(st["translatable"], 2)
        self.assertEqual(st["translatable_done"], 1)

    def test_import(self):
        ws.main(["--ws", str(self.wsdir), "init", "--extract", str(self.extract)])
        c = ws.apply_updates(self.wsdir, [
            {"narc": "a027", "bank": 5, "id": 2, "en": "Bye", "zh": "再见"},
            {"narc": "a027", "bank": 5, "id": 0, "en": "X", "zh": "wrong zh"},
        ], default_origin="tm_v3")
        self.assertEqual((c["applied"], c["zh_mismatch"]), (1, 1))
        e = self.load()["strings"][2]
        self.assertEqual((e["en"], e["status"], e["origin"]), ("Bye", "tm", "tm_v3"))
        c = ws.apply_updates(self.wsdir, [{"narc": "a027", "bank": 5, "id": 2, "en": "Other"}])
        self.assertEqual(c["kept_existing"], 1)


class TestLints(unittest.TestCase):
    """prefix_split, mid_sentence_page, glossary_name (qa.py check) and zh_variant (qa.py variants)."""

    def lint(self, zh, en, category="dialogue"):
        return qa.check_bank(bank([(zh, en)], category), fset_name="vanilla_us")

    def test_prefix_split(self):
        for en in ("Go see Prof.{NEWLINE}Oak.", "We’re at Mt.{NEWLINE}Moon.", "Board the S.S.{CLEAR}Aqua!",
                   "Ask Mr.{NEWLINE}{VAR:0103:0}.", "It’s up to{NEWLINE}Lv.{SCROLL}30 now.",
                   "Go to the Pokémon{NEWLINE}Center.", "The Pokémon{NEWLINE}League’s rules."):
            self.assertIn("prefix_split", codes(self.lint("甲乙丙{NEWLINE}丁", en), "error"), en)
        for en in ("I have two TMs.{NEWLINE}Take them.", "He sold HMs.{NEWLINE}Weird.",
                   "Pryce: No.{NEWLINE}Pryce: Go.", "Look at the ID No.{NEWLINE}of your Pokémon.",
                   "I love Pokémon{NEWLINE}more than anything.", "Go see Prof. Oak.{NEWLINE}Now."):
            self.assertNotIn("prefix_split", codes(self.lint("甲乙丙{NEWLINE}丁", en)), en)

    def test_mid_sentence_page(self):
        zh = "你好。{SCROLL}再见。"
        self.assertIn("mid_sentence_page", codes(self.lint(zh, "Hello, how are{SCROLL}you today?"), "warning"))
        self.assertIn("mid_sentence_page", codes(self.lint(zh, "Hello there,{SCROLL}friend."), "warning"))
        for en in ("Hello.{SCROLL}Bye.", "Blue:{SCROLL}Hello!", "“Hi!”{SCROLL}Bye.", "Trainer Tips{SCROLL}Run!",
                   "Want it?{VAR:0200:0}{SCROLL}OK.", "Well...{SCROLL}bye."):
            self.assertNotIn("mid_sentence_page", codes(self.lint(zh, en)), en)
        # the Chinese breaks mid-sentence too: faithful, not reported
        self.assertNotIn("mid_sentence_page", codes(self.lint("你好，{SCROLL}朋友。", "Hello, my{SCROLL}friend.")))
        # more English pages than Chinese: continuation pages ending at a comma are normal; mid-clause is not
        self.assertNotIn("mid_sentence_page", codes(self.lint("你好。", "Hello there, my old,{SCROLL}old friend.")))
        self.assertIn("mid_sentence_page", codes(self.lint("你好。", "Hello there, my old{SCROLL}friend.")))

    def test_single_word_view(self):
        zh = "你好{NEWLINE}朋友{CLEAR}再见"
        sw = lambda en, cat="dialogue": [i for i in self.lint(zh, en, cat) if i["code"] == "single_word_view"]
        # the word after a {CLEAR} (new line scrolled in) or a {SCROLL} (new page) ends the previous line's sentence
        for en in ("Ever since Team Rocket came to Saffron{NEWLINE}City, they’ve robbed everyone they{CLEAR}see.",
                   "It’s so hot in this cave. I suspect{NEWLINE}something in here is giving off heat{SCROLL}nonstop.",
                   "The wild {VAR:0101:0}’s{NEWLINE}{VAR:0105:1} poisoned{CLEAR}{VAR:0101:2}!"):
            hits = sw(en)
            self.assertEqual(len(hits), 1, en)
            self.assertEqual(hits[0]["level"], "warning")
        for en in ("Ever since Team Rocket came to Saffron{NEWLINE}City, they’ve robbed everyone{CLEAR}they see.",
                   "Then you open the lid.{SCROLL}Done!",              # an interjection starts its own sentence
                   "Wait for it...{CLEAR}Done!",
                   "Hello!{SCROLL}World",                               # first view is never reported
                   "All right, we’re ready!{NEWLINE}Aim for the top! Let’s{CLEAR}...",   # no word in the view
                   "Welcome!{NEWLINE}Here we go.{CLEAR}Bye{NEWLINE}now."):            # two words in the view
            self.assertEqual(sw(en), [], en)
        # not reported when only rewording could fix it: neither the word fits on the line before nor the two
        # last words fit on one line
        long = "Wwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwww"                               # one 'word' of 216 px
        self.assertEqual(sw("Hello.{NEWLINE}" + long + "{CLEAR}Wwwwwwwwwww!"), [])
        # allow list (qa_config single_word_view_allow): the Pokéathlon host's 200 % shout page
        cfg = dict(qa.tm.load_config(), single_word_view_allow=["a027/0999#0"])
        b = bank([(zh, "Aim for the top! Let’s{SCROLL}Pokéathlon!")], "dialogue")
        self.assertIn("single_word_view", codes(qa.check_bank(b, None, "vanilla_us")))
        self.assertNotIn("single_word_view", codes(qa.check_bank(b, cfg, "vanilla_us")))

    def test_field_prompt_icons(self):
        # field message window: the last view of a string that waits with {VAR:0200:..} must end by 195 px
        # (the prompt icons at x 211-228, emulator text-fit read-back 2026-10-09); trailing spaces leave no ink
        zh = "要试试吗？{VAR:0200:0}"
        wide = "Give up on teaching it High Jump Kick?{VAR:0200:0}"                  # 199 px
        iss = self.lint(zh, wide)
        self.assertIn("prompt_icon_overlap", codes(iss, "error"))
        self.assertEqual(codes(self.lint(zh, "Give up on teaching it{NEWLINE}High Jump Kick?{VAR:0200:0}"), "error"),
                         [])
        self.assertNotIn("prompt_icon_overlap", codes(self.lint("要试试吗？", wide.replace("{VAR:0200:0}", ""))))
        # an earlier page may use the full 216 px
        self.assertNotIn("prompt_icon_overlap", codes(self.lint(
            "要{SCROLL}吗？{VAR:0200:0}", "I lost to you, but I really enjoyed that{SCROLL}Shall we?{VAR:0200:0}")))
        # a space before the prompt is not ink (196 px with it, 192 px without)
        self.assertNotIn("prompt_icon_overlap", codes(self.lint(zh, "Do you want me to explain it to you? {VAR:0200:0}")))

    def test_glossary_name(self):
        def gn(en, zh="我的精灵"):
            return [(i["level"], i["msg"]) for i in self.lint(zh, en) if i["code"] == "glossary_name"]
        self.assertEqual(gn("Bulbasaur used Feint Attack on Poké Balls and Charmander’s Oran Berries."), [])
        self.assertEqual(gn("Nidoran♀: Ni-do-ran! Ivy-saur! Squir...tle! PIKACHU, go!"), [])
        self.assertEqual(gn("Faint. Listen, Service is over."), [])        # English words, not names
        hits = gn("Use Faint Attack!")                                      # old name -> error (move)
        self.assertEqual(hits[0][0], "error")
        self.assertIn("Feint Attack", hits[0][1])
        self.assertEqual(gn("Buy a Poke Ball.")[0][0], "warning")           # item spelling -> warning
        self.assertEqual(gn("My Pikachuu!")[0][0], "error")                 # species misspelling -> error
        self.assertEqual(gn("It knows ThunderPunch.")[0][0], "error")       # Gen 4 spelling in prose
        self.assertIn("Nidoran♀", gn("My Nidoran is sick.", "我的尼多兰生病了")[0][1])
        self.assertIn("Nidoran♂", gn("My Nidoran is sick.", "我的尼多朗生病了")[0][1])
        self.assertEqual(gn("Nidoran!", "尼多"), [])                        # ambiguous zh: not reported
        self.assertEqual(gn("Dragon Gym"), [])                             # qa_config glossary_names.allow
        self.assertEqual(gn("Ce Pokémon dresse", "Ce Pokémon dresse"), [])  # untouched copy
        b = bank([("我的精灵", "Use Faint Attack!")], "dialogue")
        b["strings"][0]["qa_ignore"] = ["glossary_name:Faint Attack"]
        self.assertEqual([i for i in qa.check_bank(b, fset_name="vanilla_us") if i["code"] == "glossary_name"], [])
        # name banks are atomic and checked by the glossary check instead
        self.assertEqual([i for i in qa.check_bank(bank([("我的精灵", "Faint Attack")], "moves"))
                          if i["code"] == "glossary_name"], [])

    def test_variants(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a027"
            p.mkdir()
            b1 = bank([("忘记了这个技能吗？", "Forget this move?"), ("忘记了这个技能吗？", "Forget this{NEWLINE}move?"),
                       ("忘记了这个技能吗？", "Should it forget this move?"),
                       ("好的好的好的好的", "OK!"), ("好的好的好的好的", "Fine!"),
                       ("{VAR:0101:0}睡着了睡着了！", "{VAR:0101:0} fell asleep!"),
                       ("{VAR:0101:0}睡着了睡着了！", "The wild {VAR:0101:0} fell asleep!"),
                       ("短句", "Hi"), ("短句", "Hello")], no=1)
            b1["strings"][4]["notes"] = "branch: rival route"
            b2 = bank([("忘记了这个技能吗？", "Forget this move?")], no=2)
            b2["strings"][0]["category"] = "menu_touch_1line"
            (p / "0001.json").write_text(json.dumps(b1, ensure_ascii=False), encoding="utf-8")
            (p / "0002.json").write_text(json.dumps(b2, ensure_ascii=False), encoding="utf-8")
            g = qa.variant_groups(d)
            self.assertEqual(len(g), 1)                       # branch note, owner prefix, short zh, category
            self.assertEqual(g[0]["size"], 3)
            self.assertEqual([v["count"] for v in g[0]["variants"]], [2, 1])   # layout-only difference merged
            self.assertEqual(g[0]["variants"][1]["refs"], ["a027/0001#2"])


class TestRegisterValidate(unittest.TestCase):
    def test_validate(self):
        import decisions as dec
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a027").mkdir()
            (Path(d) / "a027" / "0005.json").write_text(json.dumps(bank([("a", "b"), ("c", "d")], no=5)),
                                                         encoding="utf-8")
            recs = [
                {"id": "D-0001", "refs": ["a027/0005#1", "a027/0005", "a027/0005#0-1", "overlay58:0x6F6",
                                          "a012/0958@1074"], "status": "accepted"},
                {"id": "D-0002", "refs": ["a027/0005#7", "a027/0009#1", "a027/0005#0322"], "status": "accepted",
                 "related": ["D-0099"]},
                {"id": "D-0003", "status": "superseded", "superseded_by": "D-0004"},
                {"id": "D-0004", "status": "superseded", "superseded_by": "D-0001"},
                {"id": "D-0005", "status": "superseded"},
                {"id": "D-0006", "status": "accepted", "superseded_by": "D-0042"},
            ]
            iss = dec.validate_register(recs, Path(d))
            got = sorted((i["id"], i["level"], i["field"]) for i in iss)
            self.assertEqual(got, [("D-0002", "error", "refs"), ("D-0002", "error", "refs"),
                                   ("D-0002", "error", "refs"), ("D-0002", "error", "related"),
                                   ("D-0003", "warning", "superseded_by"), ("D-0005", "error", "superseded_by"),
                                   ("D-0006", "error", "status"), ("D-0006", "error", "superseded_by")])


if __name__ == "__main__":
    unittest.main()
