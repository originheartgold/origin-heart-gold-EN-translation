import unittest
from size_render_validation import SENTINEL, validate_case, validate_report


class EvidenceValidationTests(unittest.TestCase):
    def case(self):
        glyph = {'frame': 1, 'printer': 123, 'x': 0, 'y': 0, 'size_word': 65532, 'font': 1}
        normal = dict(glyph, frame=250, size_word=0)
        return dict(ref='a027/0616#37', text='{VAR:FF01:200}Shout!{VAR:FF01:100}',
                    heap_checks=50, minspare={'0': 100}, corrupt=None, allocation_failures=[],
                    null_writes=[], heap_table_errors=[], glyphs=[glyph, normal],
                    size_events=[{'size_word': 65532}, {'size_word': 0}],
                    printer_starts=[{'size_word': 0}], screenshots=[
                        dict(expected='{VAR:FF01:200}Shout!{VAR:FF01:100}', glyphs=[glyph], text_crop_sha256='a'*64),
                        dict(expected=SENTINEL, glyphs=[normal], text_crop_sha256='b'*64)])

    def test_complete_case(self):
        self.assertEqual(validate_case(self.case())['status'], 'pass')

    def test_missing_or_corrupt_evidence_rejected(self):
        for key, value in [('heap_checks', 0), ('glyphs', []), ('printer_starts', []),
                           ('size_events', [{'size_word': 65532}]), ('screenshots', []),
                           ('corrupt', [30, 'heap corruption'])]:
            with self.subTest(key=key):
                case = self.case(); case[key] = value
                self.assertEqual(validate_case(case)['status'], 'fail')

    def test_summary_pass_cannot_hide_size_leak(self):
        case = self.case(); case['status'] = 'pass'; case['assertions'] = {'all_good': True}
        case['screenshots'][-1]['glyphs'][0]['size_word'] = 65532
        self.assertEqual(validate_case(case)['status'], 'fail')

    def test_page_missing_glyphs_rejected(self):
        case = self.case(); case['screenshots'][0]['glyphs'] = []
        self.assertEqual(validate_case(case)['status'], 'fail')

    def test_negative_requires_actual_corruption(self):
        case = self.case(); case['ref'] = 'negative-misty-newline'
        case['allocation_failures'] = [1]
        self.assertEqual(validate_case(case)['status'], 'fail')
        case['corrupt'] = [30, 'heap corruption']
        self.assertEqual(validate_case(case)['status'], 'expected-failure')

    def test_incomplete_report_rejected(self):
        self.assertEqual(validate_report({'cases': [self.case()]})['status'], 'fail')

    def test_ui_requires_following_printer_and_native_bounds(self):
        case = self.case(); case.update(ui_case=True, text='{VAR:FF01:200}Shout!', native_width=144,
                                       harness_font=1, rendered_advance_extent=70, static_font_width=70)
        case['size_events'] = [{'size_word': 65532}]
        case['printer_starts'].append({'frame': 245, 'size_word': 0})
        case['screenshots'] = [dict(expected=case['text'], glyphs=[case['glyphs'][0]], frame_end=240, text_crop_sha256='a'*64)]
        self.assertEqual(validate_case(case)['status'], 'pass')
        case['rendered_advance_extent'] = 145
        self.assertEqual(validate_case(case)['status'], 'fail')


if __name__ == '__main__': unittest.main()
