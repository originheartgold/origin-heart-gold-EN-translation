"""Synthetic fixtures only: no ROM, downloaded data, or game text required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('text_catalog', Path(__file__).with_name('text_catalog.py'))
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bank = self.root / 'work/translate/banks/a027/0001.json'
        self.bank.parent.mkdir(parents=True)
        self.entries = [
            dict(id=0, zh='银行{NEWLINE}很好。', en='The bank is good.', status='draft',
                 origin='agent', notes='Context A', qa_ignore=['test'], custom={'future': True}),
            dict(id=1, zh='银行{NEWLINE}很好。', en='A good bank.', status='reviewed',
                 origin='us', notes='Context B'),
            dict(id=2, zh='placeholder'),
        ]
        self.entries[2] = dict(id=2, zh='[zh redacted: song lyrics; sha256:' + '0'*64 + ']', en='(hums)')
        self.data = dict(narc='a027', bank=1, custom='retained', strings=self.entries)
        self.bank.write_text(json.dumps(self.data, ensure_ascii=False, indent=1) + '\n')
        self.db_path = self.root / 'out/catalog.sqlite3'
        self.lexicon = catalog.Lexicon()
        self.lexicon.add_reading('行', '行', 'xing2', ['to walk', 'capable; acceptable'])
        self.lexicon.add_reading('行', '行', 'hang2', ['row; line', 'profession'])
        self.lexicon.add_reading('銀行', '银行', 'yin2 hang2', ['bank (finance)'])

    def build(self, **kwargs):
        return catalog.build(self.root, self.db_path, **kwargs)

    def test_default_annotations_belong_to_supplied_root(self):
        path = self.root / 'work/translate/text_catalog/annotations.jsonl'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(ref='a027/0001#0', source_sha256=catalog.digest(self.entries[0]['zh']),
                                        literal_english='Root-local review')) + '\n')
        self.build()
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.inspect(db, 'a027/0001#0')['annotation']['literal_english'], 'Root-local review')

    def test_lossless_and_occurrence_specific_translations(self):
        self.build()
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.verify(db, self.root), [])
            a = catalog.inspect(db, 'a027/0001#0')
            b = catalog.inspect(db, 'a027/0001#1')
            self.assertEqual(a['translation'], self.entries[0])
            self.assertEqual(a['source_sha256'], b['source_sha256'])
            self.assertNotEqual(a['english'], b['english'])
            self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0], 2)
            out = self.root / 'export'
            catalog.export_banks(db, out)
            self.assertEqual((out / self.bank.relative_to(self.root)).read_bytes(), self.bank.read_bytes())
            with self.assertRaises(FileExistsError):
                catalog.export_banks(db, out)

    def test_layout_split_word_offsets_and_control_barrier(self):
        analysis = catalog.analyse('银{NEWLINE}行{VAR:0103:0}行', 'Mandarin', self.lexicon)
        self.assertEqual(analysis['tokens'][0]['text'], '银行')
        self.assertEqual(analysis['tokens'][0]['positions'], [0, 10])
        self.assertEqual(analysis['tokens'][0]['pinyin_candidates'], ['yín háng'])
        self.assertEqual(analysis['tokens'][1]['pinyin_candidates'], ['háng', 'xíng'])
        self.assertIsNone(analysis['pinyin'])
        self.assertEqual(len(analysis['tags']), 2)
        barriers = catalog.analyse('银{VAR:0103:0}行', 'Mandarin', self.lexicon)
        self.assertEqual([t['text'] for t in barriers['tokens']], ['银', '行'])

    def test_dictionary_preserves_polyphony_senses_and_merged_forms(self):
        path = self.root / 'dictionary.txt'
        path.write_text('#! license=synthetic-test-data\n行 行 [xing2] /walk; move/acceptable/\n'
                        '行 行 [hang2] /row/profession/\n發 发 [fa1] /emit/\n髮 发 [fa4] /hair/\n')
        lex = catalog.Lexicon()
        lex.import_cedict(path)
        self.assertEqual(len(lex.candidates('行')), 2)
        self.assertEqual(lex.candidates('行')[0]['senses'][0]['gloss'], 'walk; move')
        self.assertEqual({r['traditional'] for r in lex.candidates('发')}, {'發', '髮'})
        self.build(cedict=path)
        with catalog.connect(self.db_path) as db:
            self.assertEqual(len(catalog.dictionary_matches(db, '行')), 2)

    def test_redactions_never_analysed(self):
        self.build()
        with catalog.connect(self.db_path) as db:
            entry = catalog.inspect(db, 'a027/0001#2')
            self.assertEqual(entry['analysis_state'], 'redacted')
            self.assertEqual(entry['characters'], [])
            self.assertIsNone(entry['pinyin'])

    def test_non_mandarin_is_not_romanised(self):
        self.assertEqual(catalog.analyse('行', 'Japanese', self.lexicon)['tokens'], [])

    def test_tones(self):
        self.assertEqual(catalog.tone_marks('nu:3 liu2 gui3 ou1 ma5 r5'), 'nǚ liú guǐ ōu ma r')
        self.assertEqual(catalog.tone_marks('Ni3 hao3'), 'Nǐ hǎo')

    def test_hardcoded_and_passthrough(self):
        hardcoded = self.root / 'work/translate/hardcoded/strings.json'
        hardcoded.parent.mkdir(parents=True)
        hardcoded.write_text(json.dumps(dict(strings=[dict(id='overlay:0x12', zh='行', en='Go', pointers=['0x4'])])))
        config = self.root / 'work/tools/qa_config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps(dict(passthrough_banks={'a027/0001': 'English'})))
        self.build()
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.inspect(db, 'a027/0001#0')['analysis_state'], 'not-mandarin')
            self.assertEqual(catalog.inspect(db, 'hardcoded#overlay:0x12')['translation']['pointers'], ['0x4'])

    def test_annotations_are_current_or_stale(self):
        path = self.root / 'annotations.jsonl'
        annotation = dict(ref='a027/0001#0', source_sha256=catalog.digest(self.entries[0]['zh']),
                          tokens=[dict(start=0, end=2, pinyin='yín háng', note='financial institution')])
        path.write_text(json.dumps(annotation) + '\n')
        self.build(annotations=path)
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.inspect(db, annotation['ref'])['annotation']['state'], 'current')
        annotation['source_sha256'] = 'old'
        path.write_text(json.dumps(annotation) + '\n')
        self.build(annotations=path)
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.inspect(db, annotation['ref'])['annotation']['state'], 'stale')

    def test_invalid_sense_or_overlap_rejected(self):
        rid = self.lexicon.by_form['行'][0]
        with self.assertRaisesRegex(ValueError, 'sense'):
            catalog.validate_annotation(dict(tokens=[dict(start=0, end=1, reading_id=rid, sense_id='wrong')]), '行', self.lexicon)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            catalog.validate_annotation(dict(tokens=[dict(start=0, end=1, note='a'), dict(start=0, end=1, note='b')]), '行', self.lexicon)

    def test_failed_rebuild_preserves_previous_database(self):
        self.build()
        previous = self.db_path.read_bytes()
        annotations = self.root / 'invalid.jsonl'
        annotations.write_text(json.dumps(dict(ref='missing', source_sha256='x')))
        with self.assertRaises(ValueError):
            self.build(annotations=annotations)
        self.assertEqual(self.db_path.read_bytes(), previous)

    def test_verify_detects_workspace_change(self):
        self.build()
        self.bank.write_text(self.bank.read_text() + '\n')
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.verify(db, self.root), [str(self.bank.relative_to(self.root))])

    def test_annotation_save_and_source_guard(self):
        self.build()
        annotation = dict(ref='a027/0001#0', source_sha256=catalog.digest(self.entries[0]['zh']),
                          review_status='reviewed', reviewer='test-reviewer',
                          tokens=[dict(start=0, end=2, pinyin='yín háng')])
        path = self.root / 'reviews.jsonl'
        with catalog.connect(self.db_path) as db:
            catalog.save_annotation(db, annotation, path, self.root)
            self.assertEqual(catalog.load_annotations(path), [annotation])
            self.bank.write_text(self.bank.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                catalog.save_annotation(db, annotation, path, self.root)

    def test_pinyin_keeps_tags_and_unknowns(self):
        self.assertEqual(catalog.render_pinyin('银{NEWLINE}行！', [dict(position=0, pinyin='yín'), dict(position=10, pinyin='háng')]),
                         'yín {NEWLINE} háng ！')
        self.assertEqual(catalog.render_pinyin('行', [dict(position=0, pinyin=None)]), '[行: ?]')

    def test_html_escapes_text(self):
        self.entries[0]['en'] = '<script>alert(1)</script>'
        self.bank.write_text(json.dumps(self.data))
        self.build()
        with catalog.connect(self.db_path) as db:
            report = catalog.render_report(db, ['a027/0001#0'])
            self.assertNotIn('<script>alert(1)</script>', report)
            self.assertIn('&lt;script&gt;', report)

    def annotation_report(self, **overrides):
        annotation = dict(ref='a027/0001#0', source_sha256=catalog.digest(self.entries[0]['zh']),
                          review_status='reviewed', reviewer='synthetic-reviewer', reviewer_kind='llm',
                          pinyin='yín háng', literal_english='A financial institution is good.',
                          grammar_notes='很 modifies 好.', clauses=[dict(explanation='A positive assessment.')],
                          characters=[dict(position=1, text='行', pinyin='háng', role='bank compound component')],
                          tokens=[dict(start=0, end=2, pinyin='yín háng', note='Financial institution in context.')])
        annotation.update(overrides)
        path = self.root / 'report-annotations.jsonl'
        path.write_text(json.dumps(annotation) + '\n')
        self.build(annotations=path)
        with catalog.connect(self.db_path) as db:
            return catalog.render_report(db, [annotation['ref']])

    def test_report_current_review_is_distinct_from_automatic(self):
        report = self.annotation_report()
        current, automatic = report.split('<details class="automatic">')
        self.assertIn('Source-current contextual annotation', current)
        for text in ('reviewed', 'llm', 'synthetic-reviewer', 'yín háng', 'bank compound component',
                     'A financial institution is good.', '很 modifies 好.', 'A positive assessment.',
                     'Financial institution in context.', 'LLM review; not human approval'):
            self.assertIn(text, current)
        self.assertNotIn('bank compound component', automatic)
        self.assertIn('Automatic character breakdown', automatic)
        self.assertIn('Unknown', automatic)  # No automatic pronunciation provider in this fixture.

    def test_report_contextual_character_does_not_rewrite_automatic(self):
        from unittest.mock import patch
        self.annotation_report()
        with catalog.connect(self.db_path) as db:
            entry = catalog.inspect(db, 'a027/0001#0')
            entry['characters'][1]['suggested_pinyin'] = 'xíng'
            with patch.object(catalog, 'inspect', return_value=entry):
                report = catalog.render_report(db, [entry['ref']])
        contextual, automatic = report.split('<details class="automatic">')
        self.assertIn('háng', contextual)
        self.assertNotIn('xíng', contextual)
        self.assertIn('xíng', automatic)
        self.assertEqual(entry['characters'][1]['suggested_pinyin'], 'xíng')

    def test_report_draft_and_absent_fields(self):
        report = self.annotation_report(review_status='draft', reviewer_kind=None, pinyin=None,
                                        characters=None, clauses=None, tokens=[], future_field='<future>')
        self.assertIn('draft', report)
        self.assertIn('Unknown / unavailable', report)
        self.assertIn('&lt;future&gt;', report)
        self.assertNotIn('LLM review; not human approval', report)

    def test_report_stale_annotation_is_historical_only(self):
        report = self.annotation_report(source_sha256='old-hash', state='current',
                                        pinyin='historical-reading', tokens=[dict(start=999, end=1000)])
        self.assertNotIn('Source-current contextual annotation', report)
        self.assertNotIn('Contextual character breakdown', report)
        self.assertIn('Stale / historical annotation — not applied', report)
        self.assertIn('old-hash', report)
        self.assertIn(catalog.digest(self.entries[0]['zh']), report)
        historical, automatic = report.split('<details class="automatic">')
        self.assertIn('historical-reading', historical)
        self.assertNotIn('historical-reading', automatic)
        self.assertIn('银行{NEWLINE}很好。', report)

    def test_report_annotation_and_metadata_are_escaped(self):
        unsafe = '<img src=x onerror="alert(1)"> & </script>'
        report = self.annotation_report(reviewer=unsafe, literal_english=unsafe,
                                        characters=[dict(text=unsafe, position=1, pinyin=unsafe, role=unsafe)],
                                        clauses=[dict(explanation=unsafe)], tokens=[dict(start=0, end=2, note=unsafe)])
        self.assertNotIn('<img', report)
        self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &lt;/script&gt;', report)
        with catalog.connect(self.db_path) as db:
            report = catalog.render_report(db, ['a027/0001#0'], summary={'x': unsafe},
                                           case_notes={'a027/0001#0': {'outcome': unsafe}})
        self.assertNotIn('<img', report)

    def test_report_unknown_dictionary_comparison_with_automatic_phrase(self):
        from unittest.mock import patch
        self.build()
        with catalog.connect(self.db_path) as db:
            entry = catalog.inspect(db, 'a027/0001#0')
            entry['words'] = [dict(text='银行', suggested_pinyin='yín háng', pinyin_candidates=[],
                                   reading_conflict=False, project_terms=[], readings=[])]
            with patch.object(catalog, 'inspect', return_value=entry):
                report = catalog.render_report(db, ['a027/0001#0'])
        self.assertIn('Unknown / unavailable: no dictionary comparison', report)
        self.assertNotIn('Matches a candidate', report)
        self.assertIn('No contextual annotation available', report)

    def test_report_resolves_selected_sense_with_provenance(self):
        path = self.root / 'dictionary.txt'
        path.write_text('銀行 银行 [yin2 hang2] /bank (finance)/\n')
        self.build(cedict=path)
        with catalog.connect(self.db_path) as db:
            entry = catalog.inspect(db, 'a027/0001#0')
            reading = catalog.dictionary_matches(db, '银行')[0]
            entry['annotation'] = dict(state='current', source_sha256=entry['source_sha256'],
                                       tokens=[dict(start=0, end=2, reading_id=reading['id'],
                                                    sense_id=reading['senses'][0]['id'])])
            result = catalog.render_annotation(db, entry)
        self.assertIn('bank (finance)', result)
        self.assertIn('cc-cedict', result)
        self.assertIn('selected sense', result)

    def test_prediction_does_not_select_a_sense(self):
        from types import SimpleNamespace
        provider = SimpleNamespace(module=SimpleNamespace(__version__='test'),
                                   predict=lambda text, offsets: [dict(position=offsets[0], pinyin='xíng')])
        result = catalog.analyse('行', 'Mandarin', self.lexicon, provider)
        self.assertEqual(result['pinyin'], 'xíng')
        self.assertEqual(result['tokens'][0]['state'], 'ambiguous')
        self.assertEqual(len(result['tokens'][0]['reading_ids']), 2)
        self.assertNotIn('sense_id', result['tokens'][0])

    def test_verify_detects_added_bank(self):
        self.build()
        new_bank = self.bank.with_name('0002.json')
        new_bank.write_text(json.dumps(dict(narc='a027', bank=2, strings=[])))
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.verify(db, self.root), [str(new_bank.relative_to(self.root))])

    def test_cjk_punctuation_does_not_make_chinese_japanese(self):
        self.entries[0]['zh'] = '确认中・・・'
        self.bank.write_text(json.dumps(self.data))
        self.build()
        with catalog.connect(self.db_path) as db:
            self.assertEqual(catalog.inspect(db, 'a027/0001#0')['language'], 'Mandarin')


if __name__ == '__main__':
    unittest.main()
