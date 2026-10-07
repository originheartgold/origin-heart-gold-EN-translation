"""Unit tests for text_speed_checks (pure rules of the text-speed runtime gates)."""
import unittest

from PIL import Image

import text_speed_checks as C


F, N, O = C.FAST, C.NORMAL, C.ORIGINAL


def batches(sizes, start_frame=100, frames_per_task=1):
    """Glyph events (task, frame) for consecutive tasks of `sizes` glyphs each."""
    out = []
    for i, n in enumerate(sizes):
        out += [(i + 1, start_frame + i * frames_per_task)] * n
    return out


class Budgets(unittest.TestCase):
    def test_design_budgets(self):
        self.assertEqual((C.NORMAL, C.FAST, C.ORIGINAL), (0, 1, 3))
        self.assertEqual([C.task_budget(m) for m in (N, F, O)], [1, 3, 1])
        self.assertEqual(C.MODES, (O, N, F))
        self.assertEqual(C.DELEGATING, {O, N})
        for unknown in (2, 4):
            with self.assertRaises(ValueError):
                C.task_budget(unknown)


class Cadence(unittest.TestCase):
    def test_designed_cadence_passes(self):
        for mode, sizes in ((F, [3] * 10 + [2]), (N, [1] * 30), (O, [1] * 30)):
            summary, errors = C.cadence(mode, batches(sizes))
            self.assertEqual(errors, [], (mode, summary))
            self.assertEqual(summary["glyphs"], sum(sizes))

    def test_empty_is_an_error(self):
        self.assertTrue(C.cadence(F, [])[1])

    def test_over_budget_fails(self):
        # e.g. an INSTANT-like FAST that prints 9 glyphs per task
        _, errors = C.cadence(F, batches([9] * 4))
        self.assertTrue(any("more glyphs than the design budget" in e for e in errors), errors)
        for mode in (N, O):
            _, errors = C.cadence(mode, batches([2] * 10))
            self.assertTrue(errors)

    def test_short_batches_are_left_to_the_stop_reason_check(self):
        # cadence() only bounds tasks from above; task_errors() judges early stops
        self.assertEqual(C.cadence(F, batches([1] * 20))[1], [])

    def test_short_messages_only_judged_on_the_upper_bound(self):
        self.assertEqual(C.cadence(F, batches([1, 2]))[1], [])
        self.assertTrue(C.cadence(F, batches([4]))[1])

    def test_glyph_outside_task_is_reported(self):
        events = batches([2] * 8) + [(None, 999)]
        _, errors = C.cadence(F, events)
        self.assertTrue(any("outside an observed native task" in e for e in errors))

    def test_tasks_per_frame_observed(self):
        events = [(1, 10), (1, 10), (2, 10), (2, 10)]
        summary, errors = C.cadence(F, events)
        self.assertEqual((summary["max_tasks_per_frame"], summary["max_per_frame"]), (2, 4))
        self.assertEqual(errors, [])


class Lag(unittest.TestCase):
    def test_no_extra_dropped_frame(self):
        self.assertEqual(C.lag_errors({3: 1, 0: 1, 1: 0}), [])
        self.assertTrue(C.lag_errors({3: 1, 0: 1, 1: 2}))
        self.assertTrue(C.lag_errors({0: 1}))

    def test_exact(self):
        self.assertEqual(C.exact_errors("to_free", 1, {0: 1, 1: 1}), [])
        self.assertTrue(C.exact_errors("to_free", 1, {0: 1, 1: 0}))
        self.assertTrue(C.exact_errors("to_free", None, {0: 1}))


def state(glyph=(), rest=(), **fields):
    m = C.FrameModel()
    m.glyph[:len(glyph)] = list(glyph)
    m.rest[:len(rest)] = list(rest)
    for k, v in fields.items():
        setattr(m, k, v)
    return m


class Pinned(unittest.TestCase):
    def test_native_values_are_pinned(self):
        from pathlib import Path
        import re
        src = (Path(__file__).resolve().parents[1] / "patches/text_speed/native.c").read_text()
        for name in ("SLOTS", "GLYPH_SEED", "REST_SEED", "STALE", "MARGIN", "SHORT", "SHORT_REST", "FAST_BUDGET"):
            self.assertEqual(int(re.search(rf"#define {name} (\d+)", src).group(1)), getattr(C, name), name)
        self.assertEqual(int(re.search(r"#define VBLANK_LINE (\d+)", src).group(1)), C.VISIBLE_LINES)
        self.assertEqual(int(re.search(r"#define LINES (\d+)", src).group(1)), C.TOTAL_LINES)
        # struct frame_state: glyph[8], rest[8], four u8, u16 mark_line, four u8 = 26 bytes
        body = re.search(r"struct frame_state \{(.*?)\};", src, re.S).group(1)
        fields = []
        for decl in re.sub(r"/\*.*?\*/", "", body, flags=re.S).split(";"):
            decl = decl.strip()
            if decl:
                kind, names = decl.split(None, 1)
                fields += [(kind, *re.fullmatch(r"(\w+)(?:\[(\w+)\])?", n.strip()).groups())
                           for n in names.split(",")]
        size = sum((2 if t == "u16" else 1) * (C.SLOTS if n else 1) for t, _, n in fields)
        self.assertEqual(size, C.STATE_SIZE)
        self.assertEqual([f[1] for f in fields], ["glyph", "rest", "next_glyph", "next_rest", "marked", "idle",
                                                  "mark_line", "mark_vblanks", "ran", "end_vblanks", "ended"])

    def test_fault_knobs_are_off(self):
        self.assertIsNone(C.FIXED_MODEL)
        self.assertFalse(C.IGNORE_REST or C.IGNORE_GLYPH or C.GLYPH_COST_BIAS or C.NO_CATCH_UP)
        self.assertEqual((C.SHORT, C.SHORT_REST), (3, 7))
        self.assertEqual(C.PASS_END_SEEDS, (C.GLYPH_SEED, C.REST_SEED, C.MARGIN))


class FrameModelTests(unittest.TestCase):
    def test_bytes_round_trip(self):
        data = bytes(range(1, 27))
        self.assertEqual(C.FrameModel(data).to_bytes(), data)
        with self.assertRaises(ValueError):
            C.FrameModel(bytes(25))

    def test_lines(self):
        self.assertEqual([C.lines_to_vblank(x) for x in (0, 170, 191, 192, 262)], [192, 22, 1, 263, 193])
        self.assertEqual(C.lines_between(150, 160), 10)
        self.assertEqual(C.lines_between(255, 3), 11)
        with self.assertRaises(ValueError):
            C.lines_to_vblank(263)

    def test_glyph_ring(self):
        m = C.FrameModel()
        for i in range(9):
            m.glyph_cost(100, 110 + i)
        self.assertEqual(m.glyph, [18, 11, 12, 13, 14, 15, 16, 17])
        self.assertEqual(m.next_glyph, 1)
        m.glyph_cost(250, 249)                         # 262 lines: saturates at 255
        self.assertEqual(m.glyph[1], 255)

    def test_rest_measured_only_when_the_counter_agrees(self):
        m = C.FrameModel()
        m.mark(7, 180)
        self.assertEqual(m.frame_end(7, 188), 8)       # no VBlank in between
        m.mark(7, 185)
        self.assertEqual(m.frame_end(8, 195), 10)      # crossed line 192: one VBlank
        m.mark(8, 185)
        self.assertIsNone(m.frame_end(8, 195))         # crossed, but the counter did not step
        m.mark(9, 100)
        self.assertIsNone(m.frame_end(11, 120))        # waited for VBlank elsewhere
        m.mark(9, 230)
        self.assertEqual(m.frame_end(9, 20), 53)       # battle: VBlank-time task, no crossing
        m.mark(255, 185)
        self.assertEqual(m.frame_end(0, 195), 10)      # the counter's low byte wraps
        self.assertEqual(m.rest[:4], [8, 10, 53, 10])
        m.mark(1, 100)
        self.assertEqual(m.frame_end(1, 100), 1)       # never 0 (0 marks an empty slot)
        self.assertEqual(m.marked, 0)

    def test_pass_end_catch_up(self):
        m = C.FrameModel()
        self.assertEqual(m.pass_end(10, 100), (False, False))     # first pass end since power-on
        self.assertEqual((m.end_vblanks, m.ended), (10, 1))
        self.assertEqual(m.pass_end(11, 100), (False, False))     # one VBlank: the wait only (60 fps)
        self.assertEqual(m.pass_end(13, 250), (True, True))       # missed one: 205 lines left >= 13 + 20 + 1
        self.assertEqual(m.pass_end(16, 250), (True, True))       # missed two: still one catch-up
        self.assertEqual(m.pass_end(18, 160), (True, False))      # 32 lines left < 34 (seeds)
        m.glyph[0], m.rest[0] = 9, 8
        self.assertEqual(m.pass_end(20, 174), (True, True))       # 18 left >= 9 + 8 + 1 (measured)
        self.assertEqual(m.pass_end(22, 175), (True, False))      # 17 left
        self.assertEqual(m.pass_end(23, 175), (False, False))
        self.assertEqual(m.pass_end(1, 250), (True, True))        # the counter's low byte wraps (23 -> 257)
        m.marked = 1
        m.catch_up_done()
        self.assertEqual(m.marked, 0)                             # a catch-up batch end is no rest sample

    def test_pass_end_ignores_print_task_fault_knobs(self):
        old = (C.MARGIN, C.REST_SEED, C.IGNORE_REST)
        try:
            C.MARGIN, C.REST_SEED, C.IGNORE_REST = 40, 1, True
            m = C.FrameModel()
            m.pass_end(0, 0)
            self.assertEqual(m.pass_end(2, 158), (True, True))    # 34 left >= 13 + 20 + 1: native constants
        finally:
            C.MARGIN, C.REST_SEED, C.IGNORE_REST = old
        try:
            C.NO_CATCH_UP = True
            m = C.FrameModel()
            m.pass_end(0, 0)
            self.assertEqual(m.pass_end(2, 250), (True, False))
        finally:
            C.NO_CATCH_UP = False

    def test_stale_history_is_cleared_but_waiting_keeps_it(self):
        m = state(rest=(8, 9))
        for _ in range(C.STALE - 1):
            m.frame_end(0, 180)
        self.assertEqual(m.rest[:2], [8, 9])
        m.task_ran()
        m.frame_end(0, 180)                            # a task ran (e.g. waiting for A): fresh
        self.assertEqual((m.idle, m.ran), (0, 0))
        for _ in range(C.STALE):
            m.frame_end(0, 180)
        self.assertEqual(m.rest, [0] * 8)
        self.assertEqual(m.idle, C.STALE)
        m.frame_end(0, 180)
        self.assertEqual(m.idle, C.STALE)              # stops at STALE

    def test_decisions(self):
        m = state(glyph=(9, 10), rest=(7, 8, 8))
        self.assertEqual(m.decide(173)["kind"], "fit")    # 19 left >= 10 + 8 + 1
        self.assertEqual(m.decide(174)["kind"], "stop")   # 18 left
        self.assertEqual(m.decide(184)["kind"], "stop")   # 8 left: the shortest rest (7) still fits
        self.assertEqual(m.decide(186)["kind"], "lost")   # 6 left < 7: the frame is lost anyway
        self.assertEqual(m.decide(230)["kind"], "fit")    # VBlank: a whole frame to the next one
        seeded = state().decide(150)
        self.assertEqual((seeded["glyph"], seeded["rest"], seeded["low"], seeded["seeded"]),
                         (C.GLYPH_SEED, C.REST_SEED, 0, True))
        self.assertEqual(state().decide(191)["kind"], "stop")   # no rest measured: never lost

    def test_short_history_rest_floor(self):
        # fewer than SHORT rests: the rest counts at least SHORT_REST (7) lines
        for rests, rest in (((6,), 7), ((6, 6), 7), ((8,), 8), ((6, 8), 8), ((6, 6, 6), 6), ((6,) * 8, 6)):
            m = state(glyph=(10,), rest=rests)
            d = m.decide(150)
            self.assertEqual((d["rest"], d["low"]), (rest, 6 if 6 in rests else min(rests)), rests)
            self.assertEqual(m.decide(192 - 10 - rest - 1)["kind"], "fit", rests)
            self.assertEqual(m.decide(192 - 10 - rest)["kind"], "stop", rests)
        # Route 1 promoter (2026-10-07): one rest of 6, 17 lines left: no longer draws
        self.assertEqual(state(glyph=(10,), rest=(6,)).decide(175)["kind"], "stop")
        self.assertEqual(state(glyph=(10,), rest=(7,)).decide(174)["kind"], "fit")   # Route 1: 18 left
        from unittest.mock import patch
        with patch.object(C, "SHORT_REST", 0):
            self.assertEqual(state(glyph=(10,), rest=(6,)).decide(175)["kind"], "fit")   # 17 >= 10 + 6 + 1

    def test_fault_knobs(self):
        from unittest.mock import patch
        m = state(glyph=(10,), rest=(8, 8, 8))
        with patch.object(C, "FIXED_MODEL", (20, 7)):
            self.assertEqual([m.decide(x)["kind"] for x in (172, 173, 185, 186)], ["fit", "stop", "stop", "lost"])
        with patch.object(C, "IGNORE_REST", True):
            self.assertEqual(m.decide(181)["kind"], "fit")
        with patch.object(C, "IGNORE_GLYPH", True):
            self.assertEqual(m.decide(183)["kind"], "fit")
        with patch.object(C, "GLYPH_COST_BIAS", 3):
            m.glyph_cost(100, 110)
            self.assertEqual(m.glyph[0], 13)


def task(events, **kw):
    return dict({"id": 1, "paused": False, "delegated": False, "events": events}, **kw)


R = ("render",)


def G(unit=0x12B):
    return ("glyph", unit)


def X(line, kind="fit"):
    return ("check", line, None if kind is None else {"kind": kind, "line": line, "left": 192 - line,
                                                      "glyph": 10, "rest": 8, "low": 7, "seeded": False})


M = ("mark", 180)


class StopReasons(unittest.TestCase):
    def test_reasons(self):
        tasks = [task([R, G(), X(160), R, G(), X(170), R, G(), X(178, "stop"), M]),            # FAST budget
                 task([R, G(), X(174, "stop"), M]),                                         # frame
                 task([R, G(0xFFFE), X(165), M]),                                           # control
                 task([R, X(160, "stop")])]                                                 # result (prompt)
        summary, errors = C.task_errors(F, tasks)
        self.assertEqual(errors, [])
        self.assertEqual(summary["reasons"], {"budget": 1, "control": 1, "frame": 1, "result": 1})
        self.assertEqual(summary["decisions"], {"fit": 2, "stop": 1})
        self.assertEqual(tasks[1]["stop"]["reason"], "frame")

    def test_lost_frame_draws_on(self):
        _, errors = C.task_errors(F, [task([R, G(), X(188, "lost"), R, G(), X(198), R, G(), X(208), M])])
        self.assertEqual(errors, [])

    def test_ignored_frame_stop_fails(self):
        _, errors = C.task_errors(F, [task([R, G(), X(175, "stop"), R, G(), X(185, "stop"), M])])
        self.assertTrue(any("after a frame stop" in e for e in errors), errors)

    def test_early_stop_without_reason_fails(self):
        _, errors = C.task_errors(F, [task([R, G(0x1DE), X(160, None), M])])
        self.assertTrue(any("without a reason" in e for e in errors), errors)
        _, errors = C.task_errors(F, [task([R, G(), X(160), M])])           # decision said draw, task ended
        self.assertTrue(any("allowed another glyph" in e for e in errors), errors)

    def test_structure(self):
        _, errors = C.task_errors(1, [task([])])
        self.assertTrue(any("rendered nothing" in e for e in errors), errors)
        _, errors = C.task_errors(1, [task([X(160), R, G(), X(170), M])])
        self.assertTrue(any("before the first glyph" in e for e in errors), errors)
        _, errors = C.task_errors(1, [task([R, G(), R, G(), X(170), M])])
        self.assertTrue(any("no line reading" in e for e in errors), errors)
        _, errors = C.task_errors(1, [task([R, G(), X(170), M, M])])
        self.assertTrue(any("marked the batch end 2 times" in e for e in errors), errors)
        _, errors = C.task_errors(1, [task([R, X(170), M])])
        self.assertTrue(any("without drawing" in e for e in errors), errors)
        self.assertTrue(C.task_errors(1, [])[1])

    def test_delegation_and_pause(self):
        for mode in (O, N):              # NORMAL is the original printer task (D-1604)
            self.assertEqual(C.task_errors(mode, [task([], delegated=True)])[1], [])
            errors = C.task_errors(mode, [task([R, G(), X(160), M])])[1]
            self.assertTrue(any("did not delegate" in e for e in errors), errors)
        self.assertTrue(C.task_errors(1, [task([], delegated=True)])[1])
        self.assertEqual(C.task_errors(1, [task([], delegated=True, special=True)])[1], [])
        self.assertTrue(C.task_errors(1, [task([R, G(), X(160), M], special=True)])[1])
        self.assertEqual(C.task_errors(1, [task([], paused=True)])[1], [])
        self.assertTrue(C.task_errors(1, [task([R, G()], paused=True)])[1])


def ptask(frame, start, end, b_lines=(), reason=None, glyph=True, seeded=False):
    """A task with its loop pass: start and end are (VBlank count, line)."""
    t = {"frame": frame, "start": start, "pass_end": end, "b_lines": list(b_lines),
         "events": [R, G()] if glyph else [R]}
    if reason:
        t["stop"] = {"reason": reason, "decision": {"seeded": seeded}}
    return t


class Product(unittest.TestCase):
    def test_pass_info(self):
        ok = C.pass_info(ptask(1, (5, 150), (5, 185)), 10)
        self.assertEqual((ok["overran"], ok["unforced"], ok["slack"]), (False, False, 7))
        late = C.pass_info(ptask(1, (5, 175), (6, 210), b_lines=(194, 204)), 10)
        self.assertTrue(late["overran"] and not late["unforced"])      # the first glyph alone ran past 192
        pushed = C.pass_info(ptask(1, (5, 160), (6, 195), b_lines=(173, 183)), 10)
        self.assertTrue(pushed["overran"] and pushed["unforced"])      # 10 extra lines pushed it over
        battle = C.pass_info(ptask(1, (6, 230), (6, 40)), 10)          # VBlank task: next VBlank far away
        self.assertFalse(battle["overran"])
        stop = C.pass_info(ptask(1, (5, 160), (5, 184), reason="frame"), 10)
        self.assertTrue(stop["frame_stop"] and stop["necessary"])     # 184 + 10 >= 191
        stop = C.pass_info(ptask(1, (5, 160), (5, 178), reason="frame"), 10)
        self.assertFalse(stop["necessary"])
        self.assertIsNone(C.pass_info(ptask(1, (5, 160), None), 10))

    def test_speed_record(self):
        tasks = [ptask(10, (1, 150), (1, 180)), ptask(11, (2, 175), (3, 210), b_lines=(194, 204)),
                 ptask(13, (4, 160), (5, 195), b_lines=(173, 183)), ptask(14, (5, 150), (5, 170))]
        r = C.speed_record(tasks, [(10, 14)], 10)
        self.assertEqual((r["frames"], r["drops"], r["printing_tasks"], r["glyph_tasks"]), (4, 1, 4, 4))
        self.assertEqual((r["unforced_drops"], r["forced_drops"], r["unforced_overruns"]), (0, 1, 1))
        self.assertEqual(C.warm_costs(tasks), [10, 10])
        tasks[1] = ptask(11, (2, 175), (3, 200), b_lines=(186, 196))      # its extra glyph pushed it over
        r = C.speed_record(tasks, [(10, 14)], 10)
        self.assertEqual((r["unforced_drops"], r["forced_drops"], r["unforced_overruns"]), (1, 0, 2))
        merged = C.merge_records([r, r])
        self.assertEqual((merged["frames"], merged["pages"]), (8, 2))
        self.assertEqual((r["slacks"], r["warm_cost"]), ([-8, -3, 12, 22], 10))   # every glyph task in the page

    def rec(self, frames, drops=0, tasks=None, unnecessary=0, unforced=0, pages=1, slacks=(), warm=None):
        return {"frames": frames, "drops": drops, "forced_drops": drops,
                "printing_tasks": frames + pages - drops, "glyph_tasks": tasks if tasks is not None else frames + 1,
                "pages": pages, "unnecessary_stops": unnecessary, "futile_stops": 0,
                "unforced_overruns": unforced, "slacks": sorted(slacks), "warm_cost": warm}

    def test_order(self):
        normal = self.rec(54, 1, tasks=54, slacks=(3, 30))
        good = {O: normal, N: dict(normal), F: self.rec(21, 1, tasks=21, warm=10)}
        self.assertEqual(C.order_errors(good), ([], []))
        # NORMAL must be the original printer, exactly
        for key, value in (("frames", 55), ("drops", 2), ("glyph_tasks", 53), ("slacks", [3, 31])):
            errors = C.order_errors({**good, N: dict(normal, **{key: value})})[0]
            self.assertTrue(any("NORMAL must be the original printer" in e for e in errors), key)
        # FAST at most NORMAL's frames; a tie only when no NORMAL frame had room
        self.assertTrue(any("slower than NORMAL" in e for e in C.order_errors({**good, F: self.rec(55, 1)})[0]))
        tie = {**good, F: self.rec(54, 1, warm=10)}
        errors = C.order_errors(tie)[0]
        self.assertTrue(any("not faster than NORMAL" in e and "1 NORMAL frames had room" in e for e in errors),
                        errors)
        capped = {O: self.rec(54, 1, slacks=(3, 11)), N: self.rec(54, 1, slacks=(3, 11)), F: self.rec(54, 1, warm=10)}
        errors, notes = C.order_errors(capped)
        self.assertEqual(errors, [])                                     # 11 < 10 + 2: no room anywhere
        self.assertTrue(notes)
        self.assertEqual(C.room_frames({"slacks": [11, 12, 30]}, {"warm_cost": 10}), 2)
        self.assertEqual(C.room_frames({"slacks": [14, 15]}, {"warm_cost": None}), 1)   # seed 13
        lazy = {**good, F: self.rec(21, 1, unnecessary=3)}
        self.assertTrue(any("would have fitted" in e for e in C.order_errors(lazy)[0]))
        drops = {**good, F: self.rec(21, 2)}
        self.assertTrue(any("dropped frames while printing, NORMAL 1" in e for e in C.order_errors(drops)[0]))
        pushed = {**good, F: self.rec(21, 1, unforced=1)}
        self.assertTrue(any("only because" in e for e in C.order_errors(pushed)[0]))
        self.assertTrue(C.order_errors({O: good[O]})[0])
        self.assertTrue(C.order_errors({**good, O: self.rec(0, slacks=(3, 30))})[0])

    def test_merge_keeps_slacks_and_the_dearest_glyph(self):
        a, b = self.rec(5, slacks=(3, 9), warm=10), self.rec(4, slacks=(1,), warm=11)
        merged = C.merge_records([a, b, self.rec(2, warm=None)])
        self.assertEqual((merged["frames"], merged["slacks"], merged["warm_cost"]), (11, [1, 3, 9], 11))


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
    good = [(108, 146), (188, 212)]                   # NORMAL, FAST

    def test_rendered_labels_pass(self):
        for mode in (N, F):
            self.assertEqual(C.option_label_errors(options_image(self.good, mode), mode), [])

    def test_wrong_selection(self):
        self.assertTrue(C.option_label_errors(options_image(self.good, F), N))

    def test_overflowing_label_fails(self):
        wide = [(108, 186), (190, 212)]                # NORMAL runs into FAST's column
        self.assertTrue(C.option_label_errors(options_image(wide, N), N))
        merged = [(108, 212)]
        self.assertTrue(C.option_label_errors(options_image(merged, N), N))
        three = [(108, 130), (150, 170), (190, 212)]   # a third label (the old three-choice row)
        self.assertTrue(C.option_label_errors(options_image(three, N), N))
        edge = [(108, 146), (188, 250)]                # FAST runs into the panel border
        self.assertTrue(C.option_label_errors(options_image(edge, F), F))

    def test_missing_labels_or_title_or_spill_fail(self):
        self.assertTrue(C.option_label_errors(options_image([], 0), 0))
        self.assertTrue(C.option_label_errors(options_image(self.good, 0, title=False), 0))
        self.assertTrue(C.option_label_errors(options_image(self.good, 0, spill=(170, 355)), 0))


class BattlePacing(unittest.TestCase):
    base = [{"text": "Foe used Tackle!", "glyphs": 16, "after_last": 90, "after_last_passes": 88, "dwell": 88,
             "pixels": "a", "to_free_passes": 1, "to_first_passes": 0},
            {"text": "It missed!", "glyphs": 10, "after_last": 50, "after_last_passes": 50, "dwell": None,
             "pixels": "b", "to_free_passes": 1, "to_first_passes": 0}]

    def other(self, i=0, **kw):
        rows = [dict(r) for r in self.base]
        rows[i].update(kw)
        return rows

    def test_preserved(self):
        self.assertEqual(C.battle_pacing_errors(self.base, self.other()), [])

    def test_exact(self):
        for key, value in (("after_last_passes", 89), ("to_free_passes", 0), ("to_first_passes", 1),
                           ("pixels", "c"), ("dwell", 87)):
            self.assertTrue(C.battle_pacing_errors(self.base, self.other(**{key: value})), key)

    def ab(self, plain=(89, 88), switched=(89, 88), faithful=True):
        return {0: {"faithful": faithful, "plain": list(plain), "switched": list(switched)}}

    def test_ab_replay_equal_accepts_a_different_pause(self):
        # Trainer 40, segment 2, 'Harden!': FAST 145 passes / 154 frames, ORIGINAL 145 / 153;
        # switched to the original printer at the pause start the FAST run still shows 145 / 154.
        other = self.other(after_last_passes=89)
        self.assertEqual(C.battle_pacing_errors(self.base, other, self.ab()), [])
        other = self.other(dwell=89)
        self.assertEqual(C.battle_pacing_errors(self.base, other, self.ab(plain=(88, 89), switched=(88, 89))), [])

    def test_ab_replay_unequal_fails(self):
        other = self.other(after_last_passes=89)
        errors = C.battle_pacing_errors(self.base, other, self.ab(switched=(88, 88)))
        self.assertTrue(any("the speed's code changes the pause" in e for e in errors), errors)
        errors = C.battle_pacing_errors(self.base, other, self.ab(switched=(89, 87)))
        self.assertTrue(any("the speed's code changes the pause" in e for e in errors), errors)

    def test_ab_replay_missing_unfaithful_or_other_run_fails(self):
        other = self.other(after_last_passes=89)
        self.assertTrue(any("no A/B replay" in e for e in C.battle_pacing_errors(self.base, other)))
        self.assertTrue(any("no A/B replay" in e for e in C.battle_pacing_errors(self.base, other, {})))
        errors = C.battle_pacing_errors(self.base, other, self.ab(faithful=False))
        self.assertTrue(any("did not reproduce" in e for e in errors), errors)
        errors = C.battle_pacing_errors(self.base, other, self.ab(plain=(90, 88), switched=(90, 88)))
        self.assertTrue(any("are not the speed run's" in e for e in errors), errors)
        # An A/B replay never excuses the exact steps.
        self.assertTrue(C.battle_pacing_errors(self.base, self.other(to_free_passes=0, after_last_passes=89),
                                               self.ab()))

    def test_no_sampled_jitter_acceptance(self):
        # The old acceptance of values the original showed with a delayed start is gone:
        # a jitter set (pause/dwell value sets) is no A/B replay and accepts nothing.
        import inspect
        self.assertNotIn("jitter", inspect.signature(C.battle_pacing_errors).parameters)
        jitter_like = {0: {"pause": {88, 89}, "dwell": {88, 89}}}
        self.assertTrue(C.battle_pacing_errors(self.base, self.other(after_last_passes=89), jitter_like))
        from pathlib import Path
        gate = Path(__file__).resolve().parents[1] / "research/text_speed/battle_pacing.py"
        self.assertNotIn("JITTER_DELAYS", gate.read_text())

    def test_divergence_and_vacuity_fail(self):
        self.assertTrue(C.battle_pacing_errors(self.base, self.base[:1]))
        self.assertTrue(C.battle_pacing_errors([], []))
        self.assertTrue(C.battle_pacing_errors(self.base, self.other(glyphs=12)))
        self.assertTrue(C.battle_pacing_errors(self.base, self.other(after_last_passes=None)))


class CompletedShown(unittest.TestCase):
    def test_first_frame_of_the_completed_text(self):
        # Original printer: final glyph at frame 10, text complete on screen from 12.
        self.assertEqual(C.completed_shown({10: "x", 11: "y", 12: "f", 13: "f"}, 10, "f"), 12)
        # FAST batch whose last glyph fell after line 0 (labelled one frame later):
        # complete on screen from the frame after it, the same absolute frame.
        self.assertEqual(C.completed_shown({11: "y", 12: "f", 13: "f"}, 11, "f"), 12)
        self.assertEqual(C.completed_shown({10: "f", 11: "f"}, 10, "f"), 10)

    def test_gaps_changes_and_missing_snapshot(self):
        self.assertEqual(C.completed_shown({10: "f", 11: "y", 12: "f"}, 10, "f"), 12)
        self.assertEqual(C.completed_shown({10: "f", 12: "f"}, 10, "f"), 12)   # unrecorded frame: no claim
        self.assertIsNone(C.completed_shown({10: "f", 11: "y"}, 10, "f"))
        self.assertIsNone(C.completed_shown({}, 10, "f"))
        self.assertEqual(C.completed_shown({9: "f", 10: "y", 11: "f"}, 10, "f"), 11)  # before the glyph: ignored


class RngPin(unittest.TestCase):
    def test_pin_must_be_applied_and_hold(self):
        seed = 0x5EED1604
        ok = [{"mode": "ORIGINAL", "delay": 0, "applied": True, "readback": seed},
              {"mode": "FAST", "delay": 0, "applied": True, "readback": seed}]
        self.assertEqual(C.rng_pin_errors(ok, seed), [])
        self.assertTrue(any("vacuous" in e for e in C.rng_pin_errors([], seed)))
        missing = ok + [{"mode": "NORMAL", "delay": 0, "applied": False}]
        self.assertTrue(any("not applied" in e for e in C.rng_pin_errors(missing, seed)))
        lost = [dict(ok[0], readback=seed ^ 1)]
        self.assertTrue(any("did not hold" in e for e in C.rng_pin_errors(lost, seed)))


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
