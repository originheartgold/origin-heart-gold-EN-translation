"""Pure pass/fail rules for the text-speed runtime gates (no emulator, ROM or save).

The runtime scripts in work/research/text_speed record raw observations from the
emulator; the functions here turn those observations into findings, so the rules
themselves are unit-tested (test_text_speed_checks.py) and cannot silently pass
on empty input. Every check returns a list of human-readable errors; an empty
list is a pass only when the observation it was given was itself non-empty.

Design under test (work/patches/text_speed/native.c):
- SLOW (0): one native task renders at most 1 + phase renderer steps, where the
  printer's private phase byte (+0x34) flips after every task that drew output;
- MEDIUM (1): at most 2 per task; FAST (2): at most 3 per task;
- reserved value 3, callbacks and explicit delays: the original task (1 per task).
- every native task draws at least one glyph (or handles one control). Before
  each further glyph it predicts the end of the game loop pass from costs it
  measured itself (FrameModel, a line-for-line mirror of the payload's frame
  state): it draws when the glyph and the rest of the pass fit before VBlank, or
  when the frame is lost anyway; otherwise it stops (frame stop), and a frame
  stop keeps SLOW's two-glyph phase for the next task.

Two kinds of checks use this:
- the model (task_errors): every decision of the binary equals FrameModel's,
  and the payload's stored state equals the state predicted from the costs the
  gate observed itself (gate_common.PrinterTrace);
- the product (pass_info, product_errors, order_errors, slow_floor_errors):
  frames, dropped frames and whether each frame stop was physically necessary,
  judged from the observed frame ends only, without the model's constants.
"""
from collections import Counter, defaultdict
import math

ORIGINAL = 3
NAMES = {0: "SLOW", 1: "MEDIUM", 2: "FAST", ORIGINAL: "ORIGINAL"}
# Units the native loop stops before (end, extended control, page/scroll prompts, 0xF0FD).
CONTROLS = frozenset((0xFFFF, 0xFFFE, 0x25BC, 0x25BD, 0xF0FD))
# Same values as the constants in work/patches/text_speed/native.c, pinned here
# independently (a unit test keeps them equal): the gates judge every frame
# decision of the binary against this model.
SLOTS = 8
GLYPH_SEED = 13
REST_SEED = 20
STALE = 60
MARGIN = 1
STATE_SIZE = 24
VISIBLE_LINES, TOTAL_LINES = 192, 263
# Fault fixtures only (fault_fixture.py 'checker', applied by gate_common for a
# --fault-payload run, never for release evidence): make the gates' model match a
# deliberately broken payload, so that only the product checks can catch it.
FIXED_MODEL = None        # (fits at or above, lost below): the cf50a23 constant rule
IGNORE_REST = False
IGNORE_GLYPH = False
GLYPH_COST_BIAS = 0
FAULT_KNOBS = frozenset(("MARGIN", "GLYPH_SEED", "REST_SEED", "FIXED_MODEL", "IGNORE_REST", "IGNORE_GLYPH",
                         "GLYPH_COST_BIAS"))
STOP_REASONS = ("budget", "frame", "control", "result", "original", "paused")


def task_budget(mode, phase):
    """Renderer steps one native task may take for this printer."""
    if mode not in NAMES:
        raise ValueError(f"unknown text-speed mode {mode!r}")
    if mode == ORIGINAL:
        return 1
    if mode == 0:
        return 1 + (phase & 1)
    return mode + 1


def cadence(mode, glyphs):
    """Summarise one message's glyph cadence and check the per-task upper bound.

    Whether a task that drew fewer glyphs than its budget had a reason to stop is
    judged per task by task_errors(), which sees the frame checks and controls.

    glyphs: [(task, phase, frame), ...] in render order: task is a unique id of the
    native task invocation that drew the glyph, phase the printer's private phase
    byte at that task's entry, frame the emulator frame. Returns (summary, errors).
    """
    errors = []
    if not glyphs:
        return {"glyphs": 0}, ["no glyphs observed (vacuous cadence check)"]
    if any(task is None for task, _, _ in glyphs):
        errors.append("glyph drawn outside an observed native task")
        glyphs = [g for g in glyphs if g[0] is not None]
        if not glyphs:
            return {"glyphs": 0}, errors
    counts = Counter(task for task, _, _ in glyphs)
    phases = {task: phase for task, phase, _ in glyphs}
    budgets = {task: task_budget(mode, phases[task]) for task in counts}
    over = sorted({(counts[t], budgets[t]) for t in counts if counts[t] > budgets[t]})
    if over:
        errors.append(f"{NAMES[mode]}: tasks rendered more glyphs than the design budget "
                      f"(count, budget) {over}")
    per_budget = defaultdict(lambda: [0, 0])          # budget -> [tasks, tasks at full budget]
    for task, count in counts.items():
        row = per_budget[budgets[task]]
        row[0] += 1
        row[1] += count == budgets[task]
    frames = Counter(frame for _, _, frame in glyphs)
    first, last = min(frames), max(frames)
    summary = {
        "glyphs": len(glyphs), "tasks": len(counts),
        "per_task": dict(sorted(Counter(counts.values()).items())),
        "full_budget": {b: f"{full}/{n}" for b, (n, full) in sorted(per_budget.items())},
        "frames_with_glyphs": len(frames), "max_per_frame": max(frames.values()),
        "first_to_last_frame": last - first,
    }
    # The game itself sometimes runs a printer task twice in one frame (seen in battle
    # with the original task too), so glyphs per frame are an observation; the
    # scheduler is compared against the original printer by the gates.
    task_frames = {(task, frame) for task, _, frame in glyphs}
    summary["max_tasks_per_frame"] = max(Counter(frame for _, frame in task_frames).values())
    return summary, errors


def lag_errors(lag, slack=0):
    """lag: {mode: frames inside the printing span in which the game did not run the
    printer's task (dropped frames)}. No speed may drop more frames than the original
    printer did on the same message (slack 0)."""
    if ORIGINAL not in lag or len(lag) < 2:
        return ["lag of the original printer and at least one speed required (vacuous lag check)"]
    return [f"{NAMES[m]}: {lag[m]} dropped frames while printing, original {lag[ORIGINAL]}"
            for m in sorted(lag) if m != ORIGINAL and lag[m] > lag[ORIGINAL] + slack]


def exact_errors(name, baseline, values):
    """values: {mode: number} that must equal the original printer's value exactly."""
    if baseline is None:
        return [f"{name}: not measured for the original printer (vacuous comparison)"]
    return [f"{NAMES[m]}: {name} {v} != original {baseline}" for m, v in sorted(values.items()) if v != baseline]


# ----------------------------------------------------------------- frame model (mirror of native.c)
def lines_between(start, end):
    """Display lines from reading start to reading end (VCOUNT, 0..262), as native.c counts them."""
    return end - start if end >= start else end + TOTAL_LINES - start


def lines_to_vblank(line):
    """Display lines left until the next VBlank starts (1..263), as native.c computes it."""
    if not 0 <= line < TOTAL_LINES:
        raise ValueError(f"VCOUNT {line} out of range")
    return VISIBLE_LINES - line if line < VISIBLE_LINES else VISIBLE_LINES + TOTAL_LINES - line


class FrameModel:
    """Line-for-line mirror of the payload's frame state (struct frame_state, 24 bytes).

    The gates build it from the payload's RAM once, then update it only from what
    they observe themselves (the VCOUNT / VBlank-counter values the payload read),
    and compare it with the payload's RAM at every read: the payload must store
    exactly the costs the gate measured, and decide exactly as decide() says."""

    FIELDS = ("next_glyph", "next_rest", "marked", "idle", "mark_line", "mark_vblanks", "ran")

    def __init__(self, data=bytes(STATE_SIZE)):
        if len(data) != STATE_SIZE:
            raise ValueError("frame state is 24 bytes")
        self.glyph = list(data[0:8])
        self.rest = list(data[8:16])
        self.next_glyph, self.next_rest, self.marked, self.idle = data[16], data[17], data[18], data[19]
        self.mark_line = data[20] | data[21] << 8
        self.mark_vblanks, self.ran = data[22], data[23]

    def to_bytes(self):
        return bytes(self.glyph + self.rest + [self.next_glyph, self.next_rest, self.marked, self.idle,
                                               self.mark_line & 255, self.mark_line >> 8, self.mark_vblanks, self.ran])

    def task_ran(self):
        """A batching task started (after the pause test, before its first render)."""
        self.ran = 1

    def glyph_cost(self, before, now):
        """An extra glyph: lines from the reading after the previous glyph to the reading after it."""
        self.glyph[self.next_glyph] = min(lines_between(before, now) + GLYPH_COST_BIAS, 255)
        self.next_glyph = (self.next_glyph + 1) & (SLOTS - 1)

    def mark(self, vblanks, line):
        """End of a batch that drew."""
        self.mark_vblanks, self.mark_line, self.marked = vblanks & 255, line, 1

    def frame_end(self, vblanks, line):
        """The game loop's last step before its VBlank wait. Returns the rest sample stored, or None."""
        sample = None
        if self.marked:
            start = self.mark_line
            rest = lines_between(start, line)
            crossed = int(start + rest >= (VISIBLE_LINES if start < VISIBLE_LINES else VISIBLE_LINES + TOTAL_LINES))
            self.marked = 0
            if (vblanks - self.mark_vblanks) & 255 == crossed:
                sample = min(rest, 255) or 1
                self.rest[self.next_rest] = sample
                self.next_rest = (self.next_rest + 1) & (SLOTS - 1)
        if self.ran:
            self.idle = 0
        elif self.idle < STALE:
            self.idle += 1
            if self.idle == STALE:
                self.rest = [0] * SLOTS
        self.ran = 0
        return sample

    def estimates(self):
        """(glyph, rest, low, seeded): the predicted cost of one more glyph, of the rest of the
        pass, the shortest recent rest (0: none), and whether a seed stood in for a measurement."""
        glyph = max(self.glyph)
        measured = [r for r in self.rest if r]
        seeded = not glyph or not measured
        return (glyph or GLYPH_SEED, max(measured) if measured else REST_SEED,
                min(measured) if measured else 0, seeded)

    def decide(self, now):
        """The payload's room() at display line now: 'fit' (draw: the glyph and the rest end
        before VBlank), 'lost' (draw: even the shortest recent rest ends after VBlank, so the
        frame is dropped anyway) or 'stop'."""
        left = lines_to_vblank(now)
        glyph, rest, low, seeded = self.estimates()
        if FIXED_MODEL:
            kind = "fit" if left >= FIXED_MODEL[0] else "lost" if left < FIXED_MODEL[1] else "stop"
        else:
            need = (0 if IGNORE_GLYPH else glyph) + (0 if IGNORE_REST else rest) + MARGIN
            kind = "fit" if left >= need else "lost" if left < low else "stop"
        return {"kind": kind, "line": now, "left": left, "glyph": glyph, "rest": rest, "low": low,
                "seeded": seeded}


DRAWS = ("fit", "lost")


def task_errors(mode, tasks):
    """Judge every native task of one message against the loop's design.

    tasks: [{'id', 'phase' (+0x34 at entry), 'paused' (global print pause flag at
    entry), 'delegated' (the native task called the original task), 'events': [('render',),
    ('glyph', next unit), ('check', VCOUNT line, decision), ('mark', line), ...] in order,
    'next_phase' (phase at the same printer's next task, None if none)}].
    A 'check' is the reading after every render; its decision is FrameModel.decide() at
    that line (gate_common.PrinterTrace), None if the gate had no model.

    Rules: an ordinary task renders at least once and reads the line after every render;
    after a glyph with budget left and no control next (a decision point) the task draws
    another glyph exactly when the decision says so; a task that drew marks its end once,
    after its last reading, and a task that drew nothing does not. A task that ends with
    budget left after a glyph must stop for a reason: the next unit is a control, or the
    decision was a frame stop. SLOW's phase flips after a task that drew, except after a
    frame stop; MEDIUM/FAST never change it.
    Returns (summary {'reasons': {reason: n}, 'frame': n, 'decisions': {kind: n}}, errors)."""
    errors, reasons, kinds = [], Counter(), Counter()
    if not tasks:
        return {"tasks": 0}, ["no native tasks observed (vacuous stop-reason check)"]
    for t in tasks:
        tag = f"task {t['id']}"
        if t.get("delegated"):
            reasons["original"] += 1
            if mode != ORIGINAL and not t.get("special"):
                errors.append(f"{tag}: {NAMES[mode]} task delegated to the original printer")
            continue
        if mode == ORIGINAL or t.get("special"):
            errors.append(f"{tag}: {'ORIGINAL mode' if mode == ORIGINAL else 'callback/delay'} task "
                          "did not delegate to the original printer")
            continue
        events = t["events"]
        if t.get("paused"):
            reasons["paused"] += 1
            if events:
                errors.append(f"{tag}: rendered although printing was paused")
            continue
        budget = task_budget(mode, t["phase"])
        renders = [i for i, e in enumerate(events) if e[0] == "render"]
        glyphs = sum(1 for e in events if e[0] == "glyph")
        marks = [i for i, e in enumerate(events) if e[0] == "mark"]
        if not renders:
            errors.append(f"{tag}: rendered nothing (a task must draw at least one glyph)")
            continue
        if events[0][0] != "render":
            errors.append(f"{tag}: {events[0][0]} before the first glyph")
        if glyphs > budget:
            errors.append(f"{tag}: {glyphs} glyphs, budget {budget}")
        drawn, decision, last_unit = 0, None, None
        for n, i in enumerate(renders):
            following = [e for e in events[i + 1:(renders[n + 1] if n + 1 < len(renders) else len(events))]]
            kinds_after = [e[0] for e in following]
            glyph = next((e for e in following if e[0] == "glyph"), None)
            check = next((e for e in following if e[0] == "check"), None)
            if check is None:
                errors.append(f"{tag}: no line reading after a render")
                break
            if n:
                if decision is None:
                    errors.append(f"{tag}: started another glyph without a frame decision")
                elif decision.get("kind") not in DRAWS:
                    errors.append(f"{tag}: drew on after a frame stop at line {decision['line']} "
                                  f"({decision['left']} lines left, needed {decision['glyph']}+{decision['rest']}"
                                  f"+{MARGIN})")
            decision = None
            if glyph is None:
                continue
            drawn += 1
            last_unit = glyph[1]
            if drawn < budget and last_unit not in CONTROLS and len(check) > 2:
                decision = check[2]
                if decision is not None:
                    kinds[decision["kind"]] += 1
        last_render = renders[-1]
        drew_last = any(e[0] == "glyph" for e in events[last_render + 1:])
        if not drew_last:
            reason = "result"
        elif drawn >= budget:
            reason = "budget"
        elif last_unit in CONTROLS:
            reason = "control"
        elif decision is not None and decision.get("kind") not in DRAWS:
            reason = "frame"
        elif decision is not None:
            reason = None
            errors.append(f"{tag}: stopped although the frame decision at line {decision['line']} allowed "
                          f"another glyph ({decision['kind']})")
        else:
            reason = None
            errors.append(f"{tag}: stopped after {glyphs} of {budget} glyphs without a reason"
                          f" (next unit {last_unit:#06x})" if last_unit is not None
                          else f"{tag}: stopped without a reason")
        if reason:
            reasons[reason] += 1
        t["stop"] = {"reason": reason, "decision": decision}     # read by pass_info()
        if glyphs and len(marks) != 1:
            errors.append(f"{tag}: drew {glyphs} glyphs but marked the batch end {len(marks)} times")
        elif not glyphs and marks:
            errors.append(f"{tag}: marked a batch end without drawing")
        elif marks and any(e[0] in ("render", "check") for e in events[marks[0] + 1:]):
            errors.append(f"{tag}: marked the batch end before its last reading")
        if t.get("next_phase") is not None:
            flip = mode == 0 and glyphs > 0 and reason != "frame"
            want = (t["phase"] ^ 1) & 0xFF if flip else t["phase"]
            if t["next_phase"] != want:
                errors.append(f"{tag}: phase {t['phase']} -> {t['next_phase']}, expected {want} "
                              f"({NAMES[mode]}, {reason} stop)")
    summary = {"tasks": len(tasks), "reasons": dict(sorted(reasons.items())), "frame": reasons["frame"],
               "decisions": dict(sorted(kinds.items()))}
    return summary, errors


# ----------------------------------------------------------------- the product: frames, drops, stops
def time_of(vblanks, line):
    """Lines since the VBlank count was 0: the SDK counter steps at line 192 (start of VBlank)."""
    return TOTAL_LINES * vblanks + (line - VISIBLE_LINES) % TOTAL_LINES


def pass_info(task, warm_cost):
    """How one native task's game loop pass ended, judged from observations only.

    task: 'start' (VBlank count, line) at task entry, 'pass_end' (VBlank count, line) at
    the end of its loop pass (None if not observed), 'b_lines' (the line readings after
    each render that drew a glyph) and 'stop' (set by task_errors(), which must run first). The pass must end before the first VBlank after the task
    started (deadline). overran: it did not (a dropped frame). unforced: it would have
    made it without the task's extra glyphs (their lines removed). For a frame stop:
    necessary when the pass, with one more glyph of warm_cost lines, would have ended at
    most one line before the deadline (VCOUNT counts whole lines)."""
    if not task.get("pass_end") or task.get("start") is None:
        return None
    start = time_of(*task["start"])
    deadline = start - start % TOTAL_LINES + TOTAL_LINES     # the first VBlank start after the task started
    end = time_of(*task["pass_end"])
    b = task.get("b_lines") or []
    extra = sum(lines_between(x, y) for x, y in zip(b, b[1:]))
    info = {"overran": end >= deadline, "unforced": end >= deadline and end - extra < deadline,
            "slack": deadline - end, "extra_lines": extra}
    stop = task.get("stop") or {}
    if stop.get("reason") == "frame":
        info["frame_stop"] = True
        info["seeded"] = bool(stop["decision"].get("seeded"))
        info["necessary"] = end + warm_cost >= deadline - 1
    return info


def warm_costs(tasks):
    """Lines of every extra glyph observed (reading after a glyph to the reading after the next)."""
    out = []
    for t in tasks:
        b = t.get("b_lines") or []
        out += [lines_between(x, y) for x, y in zip(b, b[1:])]
    return out


def speed_record(tasks, pages, warm_cost):
    """Product summary of one message at one speed.

    tasks: the printer's native task records (gate_common.PrinterTrace), each with 'frame';
    pages: [(first glyph frame, last glyph frame)] per page; warm_cost: lines of one extra
    glyph (median observed). frames: sum of page spans; drops: frames inside a span in which
    the task did not run; printing_tasks: frames inside the spans in which it ran;
    glyph_tasks: tasks that drew at least one glyph (an explicit pause inside a page runs
    tasks that draw nothing, at every speed alike);
    unforced_drops: drops after a pass that only the task's extra glyphs pushed past VBlank;
    stops: frame stops and whether each was necessary."""
    ran = sorted({t["frame"] for t in tasks})
    by_frame = {}
    for t in tasks:
        by_frame[t["frame"]] = t
    infos = {id(t): pass_info(t, warm_cost) for t in tasks}
    frames = drops = printing = unforced = 0
    glyph_tasks = sum(1 for t in tasks if any(e[0] == "glyph" for e in t.get("events", ()))
                      and any(a <= t["frame"] <= b for a, b in pages))
    for first, last in pages:
        frames += last - first
        for f in range(first, last + 1):
            if f in by_frame:
                printing += 1
                continue
            drops += 1
            before = [x for x in ran if x < f]
            info = infos.get(id(by_frame[before[-1]])) if before else None
            unforced += bool(info and info["unforced"])
    stops = [i for i in infos.values() if i and i.get("frame_stop")]
    return {"frames": frames, "drops": drops, "printing_tasks": printing, "glyph_tasks": glyph_tasks,
            "pages": len(pages),
            "unforced_drops": unforced, "forced_drops": drops - unforced,
            "frame_stops": len(stops), "seeded_stops": sum(1 for i in stops if i["seeded"]),
            "unnecessary_stops": sum(1 for i in stops if not i["seeded"] and not i["necessary"]),
            "futile_stops": sum(1 for i in stops if i["overran"]),
            "unforced_overruns": sum(1 for i in infos.values() if i and i["unforced"])}


def merge_records(records):
    """One record for several messages (e.g. a battle segment): counts add up."""
    out = {}
    for r in records:
        for k, v in r.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k != "warm_cost":
                out[k] = out.get(k, 0) + v
    return out


def slow_floor(original, slow):
    """SLOW renders three glyphs per two tasks, the original one per task: SLOW's tasks that
    drew a glyph are at most ceil(2/3 of the original's), plus one per page (the phase at a page's
    start), plus one per futile frame stop of SLOW: a stop that tried to save a frame the
    pass then missed anyway (whether a frame can still be saved is not known when the
    batch decides; the frame model declares a frame lost only when even the shortest
    recent rest misses VBlank). Such a stop keeps SLOW's two-glyph turn for the next task,
    so it costs one task, never a glyph."""
    return math.ceil(original["glyph_tasks"] * 2 / 3) + original["pages"] + slow["futile_stops"]


def order_errors(records):
    """Judge one message's speeds by the product (records: {mode: speed_record}).

    - no frame stop gave up a glyph that would have fitted: with one more glyph of the
      median observed cost the pass would still have ended at least two lines before
      VBlank (pass_info; stops before any cost was measured in the scene are exempt);
    - the original printer takes strictly more frames than SLOW;
    - SLOW > MEDIUM > FAST in frames, strictly. A tie or inversion between two
      neighbours is allowed only at the physical cap: both drew every glyph that fitted
      (no unnecessary frame stop, above), and the faster one's frames, without the drops
      its mandatory first glyphs forced, are at most the slower one's (the difference is
      only drops no batching can avoid);
    - no speed drops more frames than the original printer, and none drops a frame only
      because of its extra glyphs (an unforced overrun);
    - SLOW floor: SLOW's tasks that drew glyphs at most slow_floor().
    Returns (errors, notes)."""
    if any(m not in records for m in (ORIGINAL, 0, 1, 2)):
        return [f"speeds missing: {sorted(set((ORIGINAL, 0, 1, 2)) - set(records))} (vacuous order check)"], []
    errors, notes = [], []
    o, slow = records[ORIGINAL], records[0]
    errors += [f"{NAMES[m]}: {records[m]['unnecessary_stops']} frame stops gave up a glyph that would have fitted "
               "(one more glyph would still have ended the pass two or more lines before VBlank)"
               for m in (0, 1, 2) if records[m]["unnecessary_stops"]]
    if not o["frames"]:
        errors.append("the original printer took no frames (vacuous order check)")
    if slow["frames"] >= o["frames"]:
        errors.append(f"SLOW ({slow['frames']} frames) is not faster than ORIGINAL ({o['frames']} frames)")
    for x, y in ((0, 1), (1, 2)):
        a, b = records[x], records[y]
        if b["frames"] < a["frames"]:
            continue
        what = "not faster than" if b["frames"] == a["frames"] else "slower than"
        problems = [f"{NAMES[m]} had {records[m]['unnecessary_stops']} unnecessary frame stops"
                    for m in (x, y) if records[m]["unnecessary_stops"]]
        net = (b["frames"] - b["forced_drops"], a["frames"] - a["forced_drops"])
        if net[0] > net[1]:
            problems.append(f"without forced drops {NAMES[y]} takes {net[0]} frames, {NAMES[x]} {net[1]}")
        if problems:
            errors.append(f"{NAMES[y]} ({b['frames']} frames) is {what} {NAMES[x]} ({a['frames']} frames): "
                          + "; ".join(problems))
        else:
            notes.append(f"{NAMES[y]} {b['frames']} / {NAMES[x]} {a['frames']} frames at the physical cap: no "
                         f"unnecessary frame stop; forced drops {b['forced_drops']} / {a['forced_drops']}")
    errors += [f"{NAMES[m]}: {records[m]['drops']} dropped frames while printing, original {o['drops']}"
               for m in (0, 1, 2) if records[m]["drops"] > o["drops"]]
    errors += [f"{NAMES[m]}: {records[m]['unforced_overruns']} frames dropped only because of the batch's "
               "extra glyphs (without them the pass would have ended before VBlank)"
               for m in (0, 1, 2) if records[m]["unforced_overruns"]]
    floor = slow_floor(o, slow)
    if slow["glyph_tasks"] > floor:
        errors.append(f"SLOW floor: {slow['glyph_tasks']} tasks drew glyphs, at most {floor} "
                      f"(2/3 of the original's {o['glyph_tasks']} plus {o['pages']} per page plus "
                      f"{slow['futile_stops']} futile frame stops)")
    return errors, notes


def compare_messages(baseline, other, keys=("bank", "id", "glyphs", "layout", "pages")):
    """Completed text must be identical to the baseline (original printer) message by message."""
    if not baseline:
        return ["baseline has no messages (vacuous comparison)"]
    errors = []
    if len(baseline) != len(other):
        errors.append(f"message count {len(other)} != baseline {len(baseline)}")
    for i, (a, b) in enumerate(zip(baseline, other)):
        for key in keys:
            if a.get(key) != b.get(key):
                errors.append(f"message {i} ({a.get('bank')}#{a.get('id')}): {key} differs from baseline")
    return errors


def nonblank(pixels, background=None):
    """True when a crop (bytes or a list of RGB tuples) holds at least two colours."""
    if isinstance(pixels, (bytes, bytearray)):
        values = {bytes(pixels[i:i + 3]) for i in range(0, len(pixels) - 2, 3)}
    else:
        values = set(pixels)
    return len(values) > 1


# ----------------------------------------------------------------- Options screen
TEXT_SPEED_ROW = (344, 353)   # glyph rows of the seventh Options row (bottom screen, 256x384 shot)
ROW_X = (8, 248)              # the row's background; the blue panel border starts at x=248
VALUE_COLUMNS = ((100, 150), (150, 200), (200, 248))   # SLOW, MEDIUM, FAST touch columns
SELECTED = (232, 32, 16)


def _is_text(p, bg):
    return max(abs(a - b) for a, b in zip(p, bg)) > 40


def row_clusters(img, y0, y1, x0=100, x1=248, gap=4):
    """Horizontal text clusters [(xmin, xmax, selected_pixels, pixels)] in rows y0..y1 of an RGB image."""
    bg = img.getpixel((x0, y0 - 3))
    cols = []
    for x in range(x0, x1):
        px = [img.getpixel((x, y)) for y in range(y0, y1 + 1)]
        text = [p for p in px if _is_text(p, bg)]
        cols.append((x, len(text), sum(p == SELECTED for p in text)))
    clusters, current, blank = [], None, 0
    for x, n, red in cols:
        if n:
            if current is None:
                current = [x, x, 0, 0]
            current[1], current[2], current[3], blank = x, current[2] + red, current[3] + n, 0
        elif current is not None:
            blank += 1
            if blank >= gap:
                clusters.append(tuple(current))
                current, blank = None, 0
    if current is not None:
        clusters.append(tuple(current))
    return clusters


def option_label_errors(img, mode, row=TEXT_SPEED_ROW, columns=VALUE_COLUMNS):
    """The TEXT SPEED row shows three separate value labels, each inside its own touch
    column, the one for `mode` (0..2) in the selected colour and the others not, and
    nothing spills above/below the row. A label running into the panel border
    (x >= 248) leaves its column. img: 256x384 RGB."""
    y0, y1 = row
    errors = []
    bg = img.getpixel((100, y0 - 3))
    for y in (y0 - 3, y0 - 2, y1 + 2, y1 + 3):
        spill = [x for x in range(*ROW_X) if _is_text(img.getpixel((x, y)), bg)]
        if spill:
            errors.append(f"text pixels outside the row at y={y} x={spill[0]}..{spill[-1]}")
    labels = row_clusters(img, y0, y1)
    if len(labels) != 3:
        return errors + [f"expected 3 value labels in the TEXT SPEED row, found {len(labels)}: {labels}"]
    for i, ((lo, hi), (x0, x1, red, n)) in enumerate(zip(columns, labels)):
        if not (lo <= x0 and x1 < hi - 3):     # keep a 4 px gap to the next column / panel border
            errors.append(f"label {i} spans x={x0}..{x1}, outside its column {lo}..{hi - 4}")
        selected = red * 2 > n
        if selected != (i == mode):
            errors.append(f"label {i} {'is' if selected else 'is not'} drawn in the selected colour (mode {mode})")
    title = row_clusters(img, y0, y1, x0=ROW_X[0], x1=100)
    if not title:
        errors.append("TEXT SPEED row title is missing")
    return errors


# ----------------------------------------------------------------- battle pacing
def battle_pacing_errors(baseline, other, jitter=None):
    """Compare one segment (battle start or one turn) between the original printer and a
    speed, both started from the same checkpoint. Rows: {'text', 'glyphs', 'pixels',
    'to_first_passes' / 'to_free_passes': game-loop passes from the printer's start to its
    first glyph / from the final glyph to the printer's removal, 'after_last_passes':
    passes from the final glyph to the next printer or the segment end, 'dwell': frames
    the completed text stayed unchanged on screen}.

    The text sequence must be identical (same battle), every message complete and its
    completed text pixels identical; the first-glyph and end-of-text steps exactly equal.
    The pause (passes) and the dwell (frames) must equal the original's, or be values in
    jitter[i]: the original printer's own pause and dwell for message i when its run
    started 1..n frames later (the battle waits for its sound, which runs on the ARM7
    sound clock, so the game itself varies there). No other tolerance."""
    if not baseline:
        return ["baseline segment printed no messages (vacuous comparison)"]
    errors = []
    texts_a = [r["text"] for r in baseline]
    texts_b = [r["text"] for r in other]
    if texts_a != texts_b:
        return [f"message sequence differs from the original printer: {texts_b} != {texts_a}"]
    for i, (a, b) in enumerate(zip(baseline, other)):
        name = a["text"][:40]
        seen = jitter[i] if jitter and i < len(jitter) else {}
        if a["glyphs"] != b["glyphs"]:
            errors.append(f"{name!r}: {b['glyphs']} glyphs != original {a['glyphs']}")
        if a.get("pixels") != b.get("pixels"):
            errors.append(f"{name!r}: completed text pixels differ from the original printer")
        if a.get("to_first_passes") != b.get("to_first_passes"):
            errors.append(f"{name!r}: first glyph {b.get('to_first_passes')} passes after the printer started, "
                          f"original {a.get('to_first_passes')}")
        if a.get("to_free_passes") != b.get("to_free_passes"):
            errors.append(f"{name!r}: to_free {b.get('to_free_passes')} passes != original "
                          f"{a.get('to_free_passes')} (the end-of-text step moved)")
        for key, unit, field in (("after_last_passes", "passes", "pause"), ("dwell", "frames", "dwell")):
            va, vb = a.get(key), b.get(key)
            if key == "after_last_passes" and (va is None or vb is None):
                errors.append(f"{name!r}: pause not measured in passes")
            elif va != vb and vb not in seen.get(field, ()):
                label = "after_last" if field == "pause" else "dwell"
                errors.append(f"{name!r}: {label} {vb} {unit} != original {va} (pause not preserved; the "
                              f"original's own values with a delayed start: {sorted(seen.get(field, ()), key=str)})")
    return errors


def heap_growth_errors(points, max_blocks=2, max_bytes=1024):
    """points: [{heap id: (used blocks, used bytes)}, ...] at idle moments, oldest first.

    The field allocates and frees unrelated blocks (NPC/animation work) while time
    passes, so idle usage fluctuates by a block or two. A leak per message grows
    without bound; this flags growth from the first to the last point beyond the
    tolerance in any heap, and heaps that appear or vanish."""
    if len(points) < 2:
        return ["fewer than two idle heap measurements (vacuous leak check)"]
    first, last = points[0], points[-1]
    errors = []
    if set(first) != set(last):
        errors.append(f"live heaps changed: {sorted(first)} -> {sorted(last)}")
    for hid in sorted(set(first) & set(last), key=int):
        blocks, size = last[hid][0] - first[hid][0], last[hid][1] - first[hid][1]
        if blocks > max_blocks or size > max_bytes:
            errors.append(f"heap {hid} grew by {blocks} blocks / {size} bytes over {len(points) - 1} messages")
    return errors


def unfreed(allocations, frees):
    """Printer allocations (address list, in order) not followed by a matching free."""
    live = Counter()
    for event, address in sorted([(i, ("alloc", a)) for i, a in allocations] +
                                 [(i, ("free", a)) for i, a in frees]):
        kind, ptr = address
        if kind == "alloc":
            live[ptr] += 1
        elif live[ptr]:
            live[ptr] -= 1
    return sorted(p for p, n in live.items() if n)
