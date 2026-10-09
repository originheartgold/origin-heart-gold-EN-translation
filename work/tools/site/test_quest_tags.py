"""Quest classification coverage and generated badge/filter contracts (no ROM required)."""
from pathlib import Path
import unittest

import sync_guide as guide


class QuestTagsTest(unittest.TestCase):
    def test_every_entry_has_an_explicit_kind_and_generated_badge(self):
        for path in sorted(Path(guide.GUIDE).glob('[0-9]*.md')):
            source = path.read_text()
            entries = guide.quest_headings(source)
            _, page = guide.convert(path.name, source, guide.AreaIndex([]))
            self.assertEqual(page.count('<section class="quest"'), len(entries))
            for heading, meta in entries:
                with self.subTest(page=path.name, heading=heading):
                    self.assertIn(meta.get('kind'), ('main', 'side'))
            for kind in ('main', 'side'):
                count = sum(meta['kind'] == kind for _, meta in entries)
                self.assertEqual(page.count(f'data-kind="{kind}"'), count)
                self.assertEqual(page.count(f'>{kind.capitalize()} quest</span>'), count)

    def test_missing_or_invalid_classification_fails_generation(self):
        for metadata in ('', '<!-- quest: kind=optional -->'):
            with self.subTest(metadata=metadata), self.assertRaises(SystemExit):
                guide.convert('01-example.md', f'# Chapter\n\n## Quest\n{metadata}\n', guide.AreaIndex([]))

    def test_postgame_is_independent_of_quest_kind_and_keeps_existing_boundaries(self):
        for heading, postgame in (
            ('Visit (after the final Hall of Fame)', True),
            ("Visit (after Lance's visit)", True),
            ('Visit (post-game)', True),
            ('Visit (after your first Hall of Fame)', False),
            ('Visit (final chapter)', False),
        ):
            tags = guide.apply_meta(guide.heading_tags(heading), {'kind': 'side'}, heading)
            self.assertEqual(bool(tags.get('postgame')), postgame)
            self.assertIn('Side quest', guide.tag_badges(tags))
            self.assertEqual('Post-game' in guide.tag_badges(tags), postgame)
        tags = guide.apply_meta({'postgame': True}, {'kind': 'main', 'postgame': 'no'}, 'mixed entry')
        self.assertNotIn('postgame', tags)

    def test_metadata_does_not_change_headings_or_leak_into_mdx(self):
        source = '# Chapter\n\n## Same heading\n<!-- quest: kind=main; id=stable; starter=Pikachu -->\n\nSteps.\n'
        for mdx in (False, True):
            _, page = guide.convert('01-example.md', source, guide.AreaIndex([]), force_mdx=mdx)
            self.assertIn('## Same heading\n', page)
            self.assertIn('data-quest-id="stable"', page)
            self.assertIn('data-starter="Pikachu"', page)
            self.assertNotIn('<!-- quest:', page)


if __name__ == '__main__':
    unittest.main()
