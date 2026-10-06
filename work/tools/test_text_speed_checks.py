"""Unit tests for text_speed_checks (pure rules of the text-speed runtime gates)."""
import unittest

from PIL import Image

import text_speed_checks as C


def batches(sizes, phases=None, start_frame=100, frames_per_task=1):
    """Glyph events for consecutive tasks of `sizes` glyphs each."""
    out = []
    for i, n in enumerate(sizes):
        phase = phases[i] if phases else 0
        out += [(i + 1, phase, start_frame + i * frames_per_task)] * n
    return out


class Budgets(unittest.TestCase):
    def test_design_budgets(self):
        self.assertEqual([C.task_budget(0, p) for p in (0, 1, 2, 3)], [1, 2, 1, 2])
        self.assertEqual(C.task_budget(1, 0), 2)
        self.assertEqual(C.task_budget(2, 1), 3)
        self.assertEqual(C.task_budget(C.ORIGINAL, 1), 1)
        with self.assertRaises(ValueError):
            C.task_budget(4, 0)


class Cadence(unittest.TestCase):
    def test_designed_cadence_passes(self):
        for mode, sizes, phases in ((0, [1, 2] * 10, [0, 1] * 10), (1, [2] * 15, None), (2, [3] * 10 + [2], None),
                                    (C.ORIGINAL, [1] * 30, None)):
            summary, errors = C.cadence(mode, batches(sizes, phases))
            self.assertEqual(errors, [], (mode, summary))
            self.assertEqual(summary["glyphs"], sum(sizes))

    def test_empty_is_an_error(self):
        self.assertTrue(C.cadence(1, [])[1])

    def test_over_budget_fails(self):
        # e.g. an INSTANT-like FAST that prints 9 glyphs per task
        _, errors = C.cadence(2, batches([9] * 4))
        self.assertTrue(any("more glyphs than the design budget" in e for e in errors), errors)
        _, errors = C.cadence(C.ORIGINAL, batches([2] * 10))
        self.assertTrue(errors)

    def test_unused_budget_fails(self):
        # FAST that only ever prints one glyph per task is slower than designed
        _, errors = C.cadence(2, batches([1] * 20))
        self.assertTrue(any("used it" in e for e in errors), errors)
        # SLOW whose phase-1 tasks still print one glyph (no alternation in effect)
        _, errors = C.cadence(0, batches([1] * 20, [0, 1] * 10))
        self.assertTrue(any("budget 2 used it" in e for e in errors), errors)

    def test_slow_phase_must_alternate(self):
        _, errors = C.cadence(0, batches([1] * 20, [0] * 20))
        self.assertTrue(any("alternate" in e for e in errors), errors)

    def test_short_messages_only_judged_on_the_upper_bound(self):
        self.assertEqual(C.cadence(2, batches([1, 2]))[1], [])
        self.assertTrue(C.cadence(2, batches([4]))[1])

    def test_glyph_outside_task_is_reported(self):
        events = batches([2] * 8) + [(None, None, 999)]
        _, errors = C.cadence(1, events)
        self.assertTrue(any("outside an observed native task" in e for e in errors))

    def test_tasks_per_frame_observed(self):
        events = [(1, 0, 10), (1, 0, 10), (2, 0, 10), (2, 0, 10)]
        summary, errors = C.cadence(1, events)
        self.assertEqual((summary["max_tasks_per_frame"], summary["max_per_frame"]), (2, 4))
        self.assertEqual(errors, [])


class Ordering(unittest.TestCase):
    def test_order(self):
        self.assertEqual(C.speed_order({3: 82, 0: 55, 1: 41, 2: 27}), [])
        errors = C.speed_order({0: 36, 1: 27, 2: 29})
        self.assertEqual(len(errors), 1)
        self.assertIn("FAST (29 frames) is not faster than MEDIUM (27 frames)", errors[0])
        self.assertTrue(C.speed_order({0: 30, 1: 30}))
        self.assertEqual(C.speed_order({0: 30, 1: 30}, strict=False), [])
        self.assertTrue(C.speed_order({3: 40, 0: 41}))       # SLOW slower than the original
        self.assertEqual(C.speed_order({3: 40, 0: 40}), [])  # equal to the original is allowed
        self.assertTrue(C.speed_order({1: 3}))


class OrderingWithLag(unittest.TestCase):
    def test_lag_explained_inversion_is_a_warning(self):
        errors, warnings = C.speed_order_with_lag({0: 36, 1: 28, 2: 33}, {0: 1, 1: 2, 2: 16})
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)

    def test_inversion_without_lag_is_an_error(self):
        errors, _ = C.speed_order_with_lag({0: 36, 1: 28, 2: 33}, {0: 1, 1: 2, 2: 2})
        self.assertTrue(errors)
        errors, warnings = C.speed_order_with_lag({0: 36, 1: 28, 2: 19}, {0: 0, 1: 0, 2: 0})
        self.assertEqual((errors, warnings), ([], []))


class Messages(unittest.TestCase):
    base = [{"bank": 48, "id": 20, "glyphs": 3, "layout": [[0, 0], [6, 0], [12, 0]], "pages": ["a"]}]

    def test_identical(self):
        self.assertEqual(C.compare_messages(self.base, [dict(self.base[0])]), [])

    def test_each_difference_is_reported(self):
        for key, value in (("pages", ["b"]), ("layout", [[0, 0]]), ("glyphs", 2)):
            other = [dict(self.base[0], **{key: value})]
            self.assertTrue(any(key in e for e in C.compare_messages(self.base, other)), key)
        self.assertTrue(C.compare_messages(self.base, []))
        self.assertTrue(C.compare_messages([], []))

    def test_nonblank(self):
        self.assertFalse(C.nonblank(bytes([1, 2, 3]) * 10))
        self.assertTrue(C.nonblank(bytes([1, 2, 3, 4, 5, 6])))


def options_image(labels, selected, title=True, spill=None):
    """Synthetic bottom-screen Options row: (x0, x1) label boxes in rows 344..352."""
    img = Image.new("RGB", (256, 384), (168, 184, 184))
    for i, (x0, x1) in enumerate(labels):
        colour = C.SELECTED if i == selected else (88, 88, 80)
        for x in range(x0, x1 + 1, 2):
            for y in range(344, 353):
                img.putpixel((x, y), colour)
    if title:
        for x in range(10, 60, 2):
            img.putpixel((x, 348), (88, 88, 80))
    if spill:
        img.putpixel(spill, (88, 88, 80))
    for x in range(248, 256):
        for y in range(330, 360):
            img.putpixel((x, y), (56, 144, 208))   # panel border is not text
    return img


class OptionLabels(unittest.TestCase):
    good = [(116, 138), (161, 195), (206, 228)]

    def test_rendered_labels_pass(self):
        for mode in range(3):
            self.assertEqual(C.option_label_errors(options_image(self.good, mode), mode), [])

    def test_wrong_selection(self):
        self.assertTrue(C.option_label_errors(options_image(self.good, 2), 1))

    def test_overflowing_label_fails(self):
        wide = [(116, 138), (161, 215), (218, 240)]       # MEDIUM runs into FAST's column
        self.assertTrue(C.option_label_errors(options_image(wide, 1), 1))
        merged = [(116, 138), (161, 228)]
        self.assertTrue(C.option_label_errors(options_image(merged, 1), 1))
        edge = [(116, 138), (161, 195), (206, 250)]        # FAST runs into the panel border
        self.assertTrue(C.option_label_errors(options_image(edge, 2), 2))

    def test_missing_labels_or_title_or_spill_fail(self):
        self.assertTrue(C.option_label_errors(options_image([], 0), 0))
        self.assertTrue(C.option_label_errors(options_image(self.good, 0, title=False), 0))
        self.assertTrue(C.option_label_errors(options_image(self.good, 0, spill=(170, 355)), 0))


class BattlePacing(unittest.TestCase):
    base = [{"text": "Foe used Tackle!", "glyphs": 16, "after_last": 90, "dwell": 88},
            {"text": "It missed!", "glyphs": 10, "after_last": 50, "dwell": None}]

    def test_preserved(self):
        other = [dict(self.base[0], after_last=91), dict(self.base[1])]
        self.assertEqual(C.battle_pacing_errors(self.base, other), [])

    def test_shortened_pause_fails(self):
        other = [dict(self.base[0], after_last=80), dict(self.base[1])]
        self.assertTrue(any("pause not preserved" in e for e in C.battle_pacing_errors(self.base, other)))
        other = [dict(self.base[0], dwell=70), dict(self.base[1])]
        self.assertTrue(C.battle_pacing_errors(self.base, other))

    def test_divergence_and_vacuity_fail(self):
        self.assertTrue(C.battle_pacing_errors(self.base, self.base[:1]))
        self.assertTrue(C.battle_pacing_errors([], []))
        other = [dict(self.base[0], glyphs=12), dict(self.base[1])]
        self.assertTrue(C.battle_pacing_errors(self.base, other))
        other = [dict(self.base[0]), dict(self.base[1], dwell=50)]
        self.assertTrue(any("only one run" in e for e in C.battle_pacing_errors(self.base, other)))


class Memory(unittest.TestCase):
    def test_unfreed(self):
        self.assertEqual(C.unfreed([(1, 0x10), (3, 0x10)], [(2, 0x10), (4, 0x10)]), [])
        self.assertEqual(C.unfreed([(1, 0x10), (3, 0x20)], [(2, 0x10)]), [0x20])
        self.assertEqual(C.unfreed([(2, 0x10)], [(1, 0x10)]), [0x10])   # a free before the allocation

    def test_heap_growth(self):
        idle = {4: (302, 569124), 11: (12, 26788)}
        self.assertEqual(C.heap_growth_errors([idle, {4: (304, 569924), 11: (12, 26788)}]), [])
        leak = [{**idle, 11: (12 + n, 26788 + 0x48 * n)} for n in range(24)]
        self.assertTrue(C.heap_growth_errors(leak))
        self.assertTrue(C.heap_growth_errors([idle]))
        self.assertTrue(C.heap_growth_errors([idle, {4: (302, 569124)}]))


if __name__ == "__main__":
    unittest.main()
