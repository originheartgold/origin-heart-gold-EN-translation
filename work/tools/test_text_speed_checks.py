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

    def test_short_batches_are_left_to_the_stop_reason_check(self):
        # cadence() only bounds tasks from above; task_errors() judges early stops
        self.assertEqual(C.cadence(2, batches([1] * 20))[1], [])

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


class FrameOrder(unittest.TestCase):
    def test_strict_order_passes(self):
        self.assertEqual(C.frame_order({3: 54, 0: 36, 1: 28, 2: 19}, {}), ([], []))

    def test_inversion_fails_even_with_frame_stops(self):
        errors, _ = C.frame_order({0: 36, 1: 28, 2: 33}, {2: 10})
        self.assertTrue(any("slower than MEDIUM" in e for e in errors), errors)

    def test_tie_needs_frame_limit_on_the_faster_speed(self):
        errors, notes = C.frame_order({3: 54, 0: 37, 1: 37, 2: 36}, {1: 9, 2: 18})
        self.assertEqual(errors, [])
        self.assertEqual(len(notes), 1)
        errors, _ = C.frame_order({3: 54, 0: 37, 1: 37, 2: 36}, {1: 0, 2: 18})
        self.assertTrue(errors)

    def test_original_must_be_strictly_slower(self):
        errors, _ = C.frame_order({3: 37, 0: 37}, {0: 5})
        self.assertTrue(errors)
        self.assertTrue(C.frame_order({1: 3}, {})[0])


class Lag(unittest.TestCase):
    def test_one_extra_dropped_frame_allowed(self):
        self.assertEqual(C.lag_errors({3: 1, 0: 1, 1: 2, 2: 1}), [])
        self.assertTrue(C.lag_errors({3: 1, 0: 1, 1: 11, 2: 16}))
        self.assertTrue(C.lag_errors({0: 1}))

    def test_exact(self):
        self.assertEqual(C.exact_errors("to_free", 1, {0: 1, 1: 1}), [])
        self.assertTrue(C.exact_errors("to_free", 1, {0: 1, 2: 0}))
        self.assertTrue(C.exact_errors("to_free", None, {0: 1}))


def task(events, phase=0, next_phase=None, start=155, **kw):
    return dict({"id": 1, "phase": phase, "paused": False, "delegated": False, "start_line": start,
                 "events": events, "next_phase": next_phase}, **kw)


R, G, X = ("render",), (lambda u=0x12B: ("glyph", u)), (lambda line: ("check", line))


class StopReasons(unittest.TestCase):
    def test_native_value_is_pinned(self):
        from pathlib import Path
        import re
        src = (Path(__file__).resolve().parents[1] / "patches/text_speed/native.c").read_text()
        self.assertEqual(int(re.search(r"#define MIN_LINES_FOR_GLYPH (\d+)", src).group(1)), C.MIN_LINES_FOR_GLYPH)
        self.assertEqual(int(re.search(r"#define FRAME_LOST_LINES (\d+)", src).group(1)), C.FRAME_LOST_LINES)

    def test_lines_to_vblank(self):
        self.assertEqual([C.lines_to_vblank(x) for x in (0, 170, 191, 192, 262)], [192, 22, 1, 263, 193])
        self.assertTrue(C.frame_stop(173))                # 19 lines left
        self.assertFalse(C.frame_stop(172))               # 20 lines left: the glyph fits
        self.assertFalse(C.frame_stop(250))               # battle / after a VBlank: a frame ahead
        self.assertFalse(C.frame_stop(5))                 # wrapped: next VBlank 187 lines away
        self.assertTrue(C.frame_stop(185))                # 7 lines: stopping still saves the frame
        self.assertFalse(C.frame_stop(186))               # 6 lines: the frame is lost anyway

    def test_reasons(self):
        tasks = [task([R, G(), X(160), R, G(), X(170), R, G()], phase=0),           # FAST budget
                 task([R, G(), X(174)]),                                            # frame
                 task([R, G(0xFFFE)]),                                             # control
                 task([R])]                                                        # result (prompt)
        summary, errors = C.task_errors(2, tasks)
        self.assertEqual(errors, [])
        self.assertEqual(summary["reasons"], {"budget": 1, "control": 1, "frame": 1, "result": 1})

    def test_ignored_frame_stop_fails(self):
        _, errors = C.task_errors(2, [task([R, G(), X(175), R, G()])])
        self.assertTrue(any("after a frame stop" in e for e in errors), errors)

    def test_early_stop_without_reason_fails(self):
        _, errors = C.task_errors(2, [task([R, G(0x1DE)])])               # e.g. stopping at a space
        self.assertTrue(any("without a reason" in e for e in errors), errors)
        _, errors = C.task_errors(2, [task([R, G(), X(160)])])             # check said go, task ended
        self.assertTrue(any("allowed another glyph" in e for e in errors), errors)

    def test_structure(self):
        _, errors = C.task_errors(1, [task([])])
        self.assertTrue(any("rendered nothing" in e for e in errors), errors)
        _, errors = C.task_errors(1, [task([X(160), R, G()])])
        self.assertTrue(any("before the first glyph" in e for e in errors), errors)
        _, errors = C.task_errors(1, [task([R, G(), R, G()])])
        self.assertTrue(any("without a frame check" in e for e in errors), errors)
        self.assertTrue(C.task_errors(1, [])[1])

    def test_slow_phase(self):
        ok = [task([R, G()], phase=0, next_phase=1), task([R, G(), X(160), R, G()], phase=1, next_phase=0),
              task([R, G(), X(175)], phase=1, next_phase=1)]                  # frame stop keeps phase 1
        self.assertEqual(C.task_errors(0, ok)[1], [])
        _, errors = C.task_errors(0, [task([R, G(), X(175)], phase=1, next_phase=0)])
        self.assertTrue(any("phase" in e for e in errors), errors)
        _, errors = C.task_errors(0, [task([R, G()], phase=1, next_phase=1)])  # phase 2 drew one, no reason
        self.assertTrue(errors)
        _, errors = C.task_errors(1, [task([R, G(), X(160), R, G()], next_phase=1)])
        self.assertTrue(any("phase" in e for e in errors), errors)

    def test_delegation_and_pause(self):
        self.assertEqual(C.task_errors(C.ORIGINAL, [task([], delegated=True)])[1], [])
        self.assertTrue(C.task_errors(C.ORIGINAL, [task([R, G()])])[1])
        self.assertTrue(C.task_errors(1, [task([], delegated=True)])[1])
        self.assertEqual(C.task_errors(1, [task([], delegated=True, special=True)])[1], [])
        self.assertTrue(C.task_errors(1, [task([R, G()], special=True)])[1])
        self.assertEqual(C.task_errors(1, [task([], paused=True)])[1], [])
        self.assertTrue(C.task_errors(1, [task([R, G()], paused=True)])[1])


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
    base = [{"text": "Foe used Tackle!", "glyphs": 16, "after_last": 90, "dwell": 88, "pixels": "a", "to_free": 1},
            {"text": "It missed!", "glyphs": 10, "after_last": 50, "dwell": None, "pixels": "b", "to_free": 1}]

    def test_preserved(self):
        other = [dict(self.base[0]), dict(self.base[1])]
        self.assertEqual(C.battle_pacing_errors(self.base, other), [])

    def test_exact(self):
        for key, value in (("after_last", 91), ("to_free", 0), ("pixels", "c")):
            other = [dict(self.base[0], **{key: value}), dict(self.base[1])]
            self.assertTrue(C.battle_pacing_errors(self.base, other), key)

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
