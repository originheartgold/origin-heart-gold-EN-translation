"""Tests for the chapter layer (guide/chapters/*.toml). Run: python3 work/tools/site/test_chapters.py"""
import json
import os
import unittest

import chapters
import relink_guide

HERE = os.path.dirname(os.path.abspath(__file__))
IDS = {q['id'] for q in json.load(open(os.path.join(HERE, 'quest_ledger.json'), encoding='utf-8'))['quests']}


def tiny():
    return [
        {'_file': 'a.toml', 'id': 'c1', 'order': 1, 'title': 'Chapter 1: A', 'summary': 's', 'kind': 'story', 'intro': 'Go north.',
         'steps': [{'id': 's1', 'text': 'Walk.', 'evidence': 'x', 'unlocks': ['q-0001'], 'closes': ['q-0001']}],
         'quests': [{'id': 'q-0001', 'missable': True}]},
        {'_file': 'b.toml', 'id': 'c2', 'order': 2, 'title': 'Postgame: B', 'summary': 's', 'kind': 'postgame', 'intro': 'More.',
         'steps': [], 'quests': [{'id': 'q-0002', 'needs': ['q-0001']}]},
    ]


class ChapterFiles(unittest.TestCase):
    def test_repository_chapters_are_valid(self):
        self.assertEqual(chapters.validate(chapters.load(), IDS), [])

    def test_valid_example(self):
        self.assertEqual(chapters.validate(tiny(), {'q-0001', 'q-0002'}), [])

    def test_every_quest_placed_exactly_once(self):
        c = tiny()
        c[1]['quests'].append({'id': 'q-0001'})
        self.assertTrue(any('already placed' in e for e in chapters.validate(c, {'q-0001', 'q-0002'})))
        self.assertTrue(any('not placed' in e for e in chapters.validate(tiny(), {'q-0001', 'q-0002', 'q-0003'})))

    def test_references_never_point_forward(self):
        c = tiny()
        c[0]['steps'][0]['unlocks'] = ['q-0002']
        self.assertTrue(any('points forward' in e for e in chapters.validate(c, {'q-0001', 'q-0002'})))

    def test_postgame_comes_last(self):
        c = tiny()
        c[0]['kind'], c[1]['kind'] = 'postgame', 'story'
        self.assertTrue(any('after a postgame' in e for e in chapters.validate(c, {'q-0001', 'q-0002'})))

    def test_missable_needs_a_closing_step(self):
        c = tiny()
        c[0]['steps'][0]['closes'] = []
        self.assertTrue(any('missable but no step closes' in e for e in chapters.validate(c, {'q-0001', 'q-0002'})))
        c[0]['steps'][0]['evidence'] = 'NOCLOSE q-0001: one-time choice'
        self.assertEqual(chapters.validate(c, {'q-0001', 'q-0002'}), [])

    def test_player_text_has_no_technical_references(self):
        c = tiny()
        c[0]['steps'][0]['text'] = 'Flag 1234 is set by script 5.'
        self.assertTrue(any('technical reference' in e for e in chapters.validate(c, {'q-0001', 'q-0002'})))

    def test_guide_missable_tag_must_match(self):
        errs = chapters.validate(tiny(), {'q-0001', 'q-0002'}, missable_ids={'q-0002'})
        self.assertEqual(len([e for e in errs if 'missable' in e]), 2)


class Relink(unittest.TestCase):
    legacy = {'old-page': {'default': 'ch01-a', 'anchors': {'quest-one': 'ch02-b'}}}

    def test_step_carries_id_and_title(self):
        info = {'q-0001': {'title': 'Q', 'anchor': 'q', 'tags': {}}}
        step = {'id': 's3', 'main': True, 'text': '**Mt. Moon, first cave.** Talk to "Cynthia".'}
        first = chapters.render_step(step, info, {'q-0001': 'c1'}, 'c1')[0]
        self.assertEqual(first, '<div class="chapter-step" id="step-s3" data-title="Mt. Moon, first cave">')
        self.assertEqual(chapters.step_title({'text': 'No title here.'}), '')

    def test_known_anchor_goes_to_its_chapter(self):
        self.assertEqual(relink_guide.rewrite('[x](/guide/old-page/#quest-one)', self.legacy), '[x](/guide/ch02-b/#quest-one)')

    def test_page_link_goes_to_first_chapter(self):
        self.assertEqual(relink_guide.rewrite('<a href="../guide/old-page/">', self.legacy), '<a href="../guide/ch01-a/">')

    def test_rewrite_is_idempotent_and_leaves_other_links(self):
        once = relink_guide.rewrite('[x](/guide/old-page/#quest-one) [y](/guide/ch02-b/#z) [i](/items/old-page/)', self.legacy)
        self.assertEqual(relink_guide.rewrite(once, self.legacy), once)
        self.assertIn('/items/old-page/', once)


if __name__ == '__main__':
    unittest.main()
