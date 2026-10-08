"""Pure pass/fail rules for the text-speed runtime gates (no emulator, ROM or save).

The runtime scripts in work/research/text_speed record raw observations from the
emulator; the functions here turn those observations into findings, so the rules
themselves are unit-tested (test_text_speed_checks.py) and cannot silently pass
on empty input. Every check returns a list of human-readable errors; an empty
list is a pass only when the observation it was given was itself non-empty.

Design under test (work/patches/text-speed/native.c, D-1604):
- NORMAL (stored 0, also every unknown value 2/3 and an unpublished save): the
  original printer task, one renderer step per task, plus the printer catch-up in
  30 fps maps (D-1603, pass_end) that every printer gets;
- FAST (stored 1): at most 3 renderer steps per native task;
- callbacks and explicit delays: the original task at both speeds.
- every FAST task draws at least one glyph (or handles one control). Before
  each further glyph it predicts the end of the game loop pass from costs it
  measured itself (FrameModel, a line-for-line mirror of the payload's frame
  state): it draws when the glyph and the rest of the pass fit before VBlank, or
  when the frame is lost anyway; otherwise it stops (frame stop).

Two kinds of checks use this:
- the model (task_errors): every decision of the binary equals FrameModel's,
  and the payload's stored state equals the state predicted from the costs the
  gate observed itself (gate_common.PrinterTrace);
- the product (pass_info, speed_record, order_errors): frames, dropped frames and
  whether each frame stop was physically necessary, judged from the observed frame
  ends only, without the model's constants.
"""
from collections import Counter

# Stored text-speed values the gates use (bits 2..3 of the Options record, D-1604).
# ORIGINAL is the reference: the unknown value 3, which the payload must treat as
# NORMAL (the original printer task); NORMAL must be identical to it.
NORMAL, FAST, ORIGINAL = 0, 1, 3
NAMES = {NORMAL: "NORMAL", FAST: "FAST", ORIGINAL: "ORIGINAL"}
MODES = (ORIGINAL, NORMAL, FAST)       # baseline first
DELEGATING = frozenset((ORIGINAL, NORMAL))
FAST_BUDGET = 3
# Units the native loop stops before (end, extended control, page/scroll prompts, 0xF0FD).
CONTROLS = frozenset((0xFFFF, 0xFFFE, 0x25BC, 0x25BD, 0xF0FD))
# Same values as the constants in work/patches/text-speed/native.c, pinned here
# independently (a unit test keeps them equal): the gates judge every frame
# decision of the binary against this model. Costs and the time left are in ticks
# of the SDK's tick timer (timer 0, bus clock / 64, D-2269); a display line is
# 2130 bus cycles, RHO = 33.28125 ticks (x 256). Seeds and the short-history floor
# are in display lines.
SLOTS = 8
GLYPH_SEED = 13           # lines
REST_SEED = 20            # lines
STALE = 60
MARGIN = 64               # ticks: a glyph and a rest spike in one decision plus the loop tail (D-2271)
SHORT = 3                 # fewer measured rests than this: the rest counts at least SHORT_REST lines
SHORT_REST = 7            # lines
RHO = 8520                # ticks per display line x 256
MAX_AGE = 52800           # ticks an anchor stays usable (about six frames)
STATE_SIZE = 52
ENDED_OFFSET = 49          # frame_state.ended (field_rate clears it to switch the catch-up off)
VISIBLE_LINES, TOTAL_LINES = 192, 263
# The 'would have fitted' allowance (D-2271): a FAST frame stop is judged unnecessary only
# when one more glyph of the message's median cost would still have ended the pass more than
# FIT_ALLOWANCE ticks before VBlank (see work/notes/text_speed_vcount.md for the derivation).
FIT_ALLOWANCE = 79
# Unforced overruns (a FAST frame dropped only because of the batch's extra glyphs) are a
# budget, not zero (D-2276, amends D-2271): at most OVERRUNS_PER_MESSAGE in one message (here),
# at most one per OVERRUN_FRAMES FAST printing frames over the whole run (validate_release,
# from every gate's 'overrun_budget', see tally_overruns()).
OVERRUNS_PER_MESSAGE = 1
OVERRUN_FRAMES = 1000
# Fault fixtures only (fault_fixture.py 'checker', applied by gate_common for a
# --fault-payload run, never for release evidence): make the gates' model match a
# deliberately broken payload, so that only the product checks can catch it.
IGNORE_REST = False
IGNORE_GLYPH = False
GLYPH_COST_BIAS = 0       # ticks added to every stored glyph cost
NO_CATCH_UP = False       # fault model: pass_end never catches up
NO_ANCHOR = False         # fault model: the position in the line is never known (the worst case)
FIXED_NEED = None         # fault model: an extra glyph needs this many ticks, whatever the costs
# pass_end's own copy of the decision constant (native.c value; the fault knobs above
# model edits of print_task's decision, which pass_end does not share).
PASS_END_MARGIN = MARGIN
FAULT_KNOBS = frozenset(("MARGIN", "GLYPH_SEED", "REST_SEED", "IGNORE_REST", "IGNORE_GLYPH",
                         "GLYPH_COST_BIAS", "NO_CATCH_UP", "SHORT_REST", "NO_ANCHOR", "FIXED_NEED"))
STOP_REASONS = ("budget", "frame", "control", "result", "original", "paused")


def task_budget(mode):
    """Renderer steps one native task may take at this speed."""
    if mode not in NAMES:
        raise ValueError(f"unknown text-speed mode {mode!r}")
    return FAST_BUDGET if mode == FAST else 1


def cadence(mode, glyphs):
    """Summarise one message's glyph cadence and check the per-task upper bound.

    Whether a task that drew fewer glyphs than its budget had a reason to stop is
    judged per task by task_errors(), which sees the frame checks and controls.

    glyphs: [(task, frame), ...] in render order: task is a unique id of the native
    task invocation that drew the glyph, frame the emulator frame. Returns (summary, errors).
    """
    errors = []
    if not glyphs:
        return {"glyphs": 0}, ["no glyphs observed (vacuous cadence check)"]
    if any(task is None for task, _ in glyphs):
        errors.append("glyph drawn outside an observed native task")
        glyphs = [g for g in glyphs if g[0] is not None]
        if not glyphs:
            return {"glyphs": 0}, errors
    counts = Counter(task for task, _ in glyphs)
    budget = task_budget(mode)
    over = sorted({counts[t] for t in counts if counts[t] > budget})
    if over:
        errors.append(f"{NAMES[mode]}: tasks rendered more glyphs than the design budget {budget}: {over}")
    frames = Counter(frame for _, frame in glyphs)
    first, last = min(frames), max(frames)
    summary = {
        "glyphs": len(glyphs), "tasks": len(counts),
        "per_task": dict(sorted(Counter(counts.values()).items())),
        "full_budget": f"{sum(1 for n in counts.values() if n == budget)}/{len(counts)}",
        "frames_with_glyphs": len(frames), "max_per_frame": max(frames.values()),
        "first_to_last_frame": last - first,
    }
    # The game itself sometimes runs a printer task twice in one frame (seen in battle
    # with the original task too), so glyphs per frame are an observation; the
    # scheduler is compared against the original printer by the gates.
    task_frames = set(glyphs)
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


def ticks_between(start, end):
    """TM0 ticks from reading start to reading end (16-bit counter), as native.c counts them."""
    return (end - start) & 0xFFFF


def agree(dt, lines):
    """Do dt ticks agree with the display lines between two readings (native agree())?"""
    if dt > 0xFFFF:
        return False
    dt = (dt + 1) << 8
    return dt + RHO > lines * RHO and dt < (lines + 1) * RHO + 512


def lower_median(values, floor=1):
    """native median(): the lower median of the slots at or above floor, 0 when fewer than SHORT."""
    filled = sorted(v for v in values if v and v >= floor)
    return filled[(len(filled) - 1) // 2] if len(filled) >= SHORT else 0


class FrameModel:
    """Line-for-line mirror of the payload's frame state (struct frame_state, 52 bytes).

    The gates build it from the payload's RAM once, then update it only from what
    they observe themselves (the VCOUNT, tick and VBlank-counter values the payload
    read), and compare it with the payload's RAM at every read: the payload must
    store exactly the costs the gate measured, and decide exactly as decide() says."""

    FIELDS = ("mark_tick", "anchor", "mark_line", "next_glyph", "next_rest", "marked", "idle", "mark_vblanks", "ran",
              "end_vblanks", "ended", "anchored")

    def __init__(self, data=bytes(STATE_SIZE)):
        if len(data) != STATE_SIZE:
            raise ValueError(f"frame state is {STATE_SIZE} bytes")
        u16 = lambda o: data[o] | data[o + 1] << 8
        self.glyph = [u16(2 * i) for i in range(SLOTS)]
        self.rest = [u16(16 + 2 * i) for i in range(SLOTS)]
        self.mark_tick = int.from_bytes(data[32:36], "little")
        self.anchor = int.from_bytes(data[36:40], "little")
        self.mark_line = u16(40)
        (self.next_glyph, self.next_rest, self.marked, self.idle, self.mark_vblanks, self.ran, self.end_vblanks,
         self.ended, self.anchored, self.pad) = data[42:52]

    def to_bytes(self):
        out = b"".join(x.to_bytes(2, "little") for x in self.glyph + self.rest)
        out += self.mark_tick.to_bytes(4, "little") + self.anchor.to_bytes(4, "little")
        out += self.mark_line.to_bytes(2, "little")
        return out + bytes([self.next_glyph, self.next_rest, self.marked, self.idle, self.mark_vblanks, self.ran,
                            self.end_vblanks, self.ended, self.anchored, self.pad])

    def task_ran(self):
        """A batching task started (after the pause test, before its first render)."""
        self.ran = 1

    def glyph_cost(self, before_line, before_tick, line, tick):
        """An extra glyph: from the reading after the previous glyph to the reading after it.
        Returns the stored cost, or None when the ticks do not agree with the lines."""
        cost = (tick - before_tick) & 0xFFFFFFFF
        if not agree(cost, lines_between(before_line, line)):
            return None
        cost = min((cost or 1) + GLYPH_COST_BIAS, 0xFFFF)
        self.glyph[self.next_glyph] = cost
        self.next_glyph = (self.next_glyph + 1) & (SLOTS - 1)
        return cost

    def mark(self, vblanks, line, tick):
        """End of a batch that drew."""
        self.mark_vblanks, self.mark_line, self.mark_tick, self.marked = vblanks & 255, line, tick, 1

    def frame_end(self, vblanks, line, tick):
        """The game loop's last step before its VBlank wait. Returns the rest sample stored, or None."""
        sample = None
        if self.marked:
            start = self.mark_line
            lines = lines_between(start, line)
            crossed = int(start + lines >= (VISIBLE_LINES if start < VISIBLE_LINES else VISIBLE_LINES + TOTAL_LINES))
            rest = (tick - self.mark_tick) & 0xFFFFFFFF
            self.marked = 0
            if (vblanks - self.mark_vblanks) & 255 == crossed and agree(rest, lines):
                sample = rest or 1
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

    def left(self, line, tick):
        """(ticks left until the next VBlank starts, known): native left_ticks()."""
        n = lines_to_vblank(line) * RHO
        age = (tick - self.anchor) & 0xFFFFFFFF
        if self.anchored and age < MAX_AGE and not NO_ANCHOR:
            into = (age << 8) % RHO
            return ((n - into) >> 8 if n > into else 0), True
        return (n - RHO) >> 8, False

    def set_anchor(self, tick):
        """pass_end saw VCOUNT change: tick is a line start."""
        self.anchor, self.anchored = tick, 1

    def costs(self):
        """(glyph, rest, low, samples) in ticks (native costs()): the typical glyph cost among the
        glyphs that read their font data (at least half the seed; with fewer than SHORT, the
        largest recent cost, at least the seed), the typical rest (with fewer than SHORT rests the
        largest, with none the seed), the shortest recent rest (0: none) and the number of rests."""
        seed = (GLYPH_SEED * RHO) >> 8
        glyph = lower_median(self.glyph, seed // 2) or max(max(self.glyph), seed)
        samples = sum(1 for r in self.rest if r)
        rest = lower_median(self.rest) or max(self.rest)
        low = min((r for r in self.rest if r), default=0)
        if not rest:
            rest, low = (REST_SEED * RHO) >> 8, 0
        return glyph, rest, low, samples

    def pass_end(self, vblanks, line, tick):
        """pass_end's reading after frame_end (D-1603): the pass is late when a VBlank passed
        since the previous pass ended (the counter moved by two or more: the wait plus a
        missed VBlank). A late pass catches up (each printer task runs once more) only when
        one glyph and the rest fit before the next VBlank. Returns (late, catch_up). The
        catch-up's batch end is no rest sample: catch_up_done() clears the mark."""
        late = bool(self.ended) and (vblanks - self.end_vblanks) & 255 >= 2
        self.end_vblanks, self.ended = vblanks & 255, 1
        if not late or NO_CATCH_UP:
            return late, False
        glyph, rest, _, _ = self.costs()
        left, _ = self.left(line, tick)
        return late, left >= glyph + rest + PASS_END_MARGIN

    def catch_up_done(self):
        """After the catch-up: a catch-up batch's end is not measured."""
        self.marked = 0

    def estimates(self):
        """(glyph, rest, low, seeded): the predicted cost in ticks of one more glyph, of the rest
        of the pass, the shortest recent rest (0: none), and whether a seed stood in for a
        measurement. While fewer than SHORT rests are measured the rest counts at least
        SHORT_REST lines."""
        glyph, rest, low, samples = self.costs()
        seed = (GLYPH_SEED * RHO) >> 8
        seeded = sum(1 for g in self.glyph if g >= seed // 2) < SHORT or not samples
        if low and samples < SHORT:
            rest = max(rest, (SHORT_REST * RHO) >> 8)
        return glyph, rest, low, seeded

    def decide(self, line, tick):
        """The payload's room() at a reading (VCOUNT line, tick): 'fit' (draw: the glyph and the
        rest end before VBlank), 'lost' (draw: even the shortest recent rest ends after VBlank,
        so the frame is dropped anyway) or 'stop'."""
        glyph, rest, low, seeded = self.estimates()
        left, known = self.left(line, tick)
        need = (0 if IGNORE_GLYPH else glyph) + (0 if IGNORE_REST else rest) + MARGIN
        if FIXED_NEED is not None:
            need = FIXED_NEED
        kind = "fit" if left >= need else "lost" if left < low else "stop"
        return {"kind": kind, "line": line, "tick": tick, "left": left, "known": known,
                "glyph": glyph, "rest": rest, "low": low, "need": need, "seeded": seeded}


DRAWS = ("fit", "lost")


def task_errors(mode, tasks):
    """Judge every native task of one message against the loop's design.

    tasks: [{'id', 'paused' (global print pause flag at entry), 'delegated' (the native task
    called the original task), 'special' (callback or explicit delay), 'events': [('render',),
    ('glyph', next unit), ('check', VCOUNT line, decision), ('mark', line), ...] in order}].
    A 'check' is the reading after every render; its decision is FrameModel.decide() at
    that line (gate_common.PrinterTrace), None if the gate had no model.

    Rules: NORMAL (and the unknown value ORIGINAL), callbacks and explicit delays delegate
    every task to the original printer; FAST never delegates an ordinary task. A FAST task
    renders at least once and reads the line after every render; after a glyph with budget
    left and no control next (a decision point) the task draws another glyph exactly when
    the decision says so; a task that drew marks its end once, after its last reading, and a
    task that drew nothing does not. A task that ends with budget left after a glyph must
    stop for a reason: the next unit is a control, or the decision was a frame stop.
    Returns (summary {'reasons': {reason: n}, 'frame': n, 'decisions': {kind: n}}, errors)."""
    errors, reasons, kinds = [], Counter(), Counter()
    if not tasks:
        return {"tasks": 0}, ["no native tasks observed (vacuous stop-reason check)"]
    for t in tasks:
        tag = f"task {t['id']}"
        if t.get("delegated"):
            reasons["original"] += 1
            if mode not in DELEGATING and not t.get("special"):
                errors.append(f"{tag}: {NAMES[mode]} task delegated to the original printer")
            continue
        if mode in DELEGATING or t.get("special"):
            errors.append(f"{tag}: {NAMES[mode] + ' mode' if mode in DELEGATING else 'callback/delay'} task "
                          "did not delegate to the original printer")
            continue
        events = t["events"]
        if t.get("paused"):
            reasons["paused"] += 1
            if events:
                errors.append(f"{tag}: rendered although printing was paused")
            continue
        budget = task_budget(mode)
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
                                  f"({decision['left']} ticks left, needed {decision['glyph']}+{decision['rest']}"
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
    each render that drew a glyph) and 'stop' (set by task_errors(), which must run first).
    The pass must end before the first VBlank after the task started (deadline).
    overran: it did not (a dropped frame). unforced: it would have made it without the
    task's extra glyphs (their lines removed).
    In ticks of the tick timer (D-2269), observed by the gate itself: 'end_tick' (the pass
    end), 'deadline_tick' (the VBlank interrupt that started the next frame), 'line_ticks'
    (ticks per display line, from the gate's own VBlank-to-VBlank intervals), all as ticks
    since 'start_tick'; warm_cost is the message's median extra glyph in ticks. tick_slack:
    ticks from the pass end to the deadline. For a frame stop: necessary when the pass,
    with one more glyph of warm_cost, would have ended less than one display line before
    the deadline (the line rule 'two or more lines before VBlank' on VCOUNT readings means
    more than one whole line), so the stop gave up no glyph that would have fitted."""
    if not task.get("pass_end") or task.get("start") is None:
        return None
    start = time_of(*task["start"])
    deadline = start - start % TOTAL_LINES + TOTAL_LINES     # the first VBlank start after the task started
    end = time_of(*task["pass_end"])
    b = task.get("b_lines") or []
    extra = sum(lines_between(x, y) for x, y in zip(b, b[1:]))
    info = {"overran": end >= deadline, "unforced": end >= deadline and end - extra < deadline,
            "slack": deadline - end, "extra_lines": extra}
    ticks = all(task.get(k) is not None for k in ("end_tick", "deadline_tick", "line_ticks"))
    if ticks:
        info["tick_slack"] = task["deadline_tick"] - task["end_tick"]
        bt = task.get("b_ticks") or []
        extra_ticks = sum((y - x) & 0xFFFF for x, y in zip(bt, bt[1:]))
        info["extra_ticks"] = extra_ticks
        # in ticks (D-2271): without the extra glyphs' time the pass would have ended before VBlank
        info["unforced"] = info["overran"] and info["tick_slack"] + extra_ticks > 0
    stop = task.get("stop") or {}
    if stop.get("reason") == "frame":
        info["frame_stop"] = True
        info["seeded"] = bool(stop["decision"].get("seeded"))
        if ticks:
            info["necessary"] = info["tick_slack"] - warm_cost <= FIT_ALLOWANCE
        else:
            info["necessary"] = False
            info["untimed"] = True
    return info


def warm_costs(tasks):
    """Ticks of every extra glyph observed (reading after a glyph to the reading after the next)."""
    out = []
    for t in tasks:
        b = t.get("b_ticks") or []
        out += [ticks_between(x, y) for x, y in zip(b, b[1:])]
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
    stops: frame stops and whether each was necessary; slacks: lines from the end of each
    glyph task's pass to its deadline (order_errors: did a frame have room for one more
    glyph); warm_cost: the extra-glyph cost the record was judged with."""
    ran = sorted({t["frame"] for t in tasks})
    by_frame = {}
    for t in tasks:
        by_frame[t["frame"]] = t
    infos = {id(t): pass_info(t, warm_cost) for t in tasks}
    line_ticks = [t["line_ticks"] for t in tasks if t.get("line_ticks")]
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
    glyph_infos = [infos[id(t)] for t in tasks
                   if infos.get(id(t)) and any(e[0] == "glyph" for e in t.get("events", ()))
                   and any(a <= t["frame"] <= b for a, b in pages)]
    slacks = sorted(i["slack"] for i in glyph_infos)
    tick_slacks = sorted(i["tick_slack"] for i in glyph_infos if "tick_slack" in i)
    return {"frames": frames, "drops": drops, "printing_tasks": printing, "glyph_tasks": glyph_tasks,
            "slacks": slacks, "tick_slacks": tick_slacks, "warm_cost": warm_cost,
            "line_ticks": max(line_ticks) if line_ticks else None,
            "untimed_stops": sum(1 for i in stops if i.get("untimed")),
            "stop_wastes": sorted(round(i["tick_slack"] - warm_cost) for i in stops if "tick_slack" in i and not i["seeded"]),
            "pages": len(pages),
            "unforced_drops": unforced, "forced_drops": drops - unforced,
            "frame_stops": len(stops), "seeded_stops": sum(1 for i in stops if i["seeded"]),
            "unnecessary_stops": sum(1 for i in stops if not i["seeded"] and not i["necessary"]),
            "futile_stops": sum(1 for i in stops if i["overran"]),
            "unforced_overruns": sum(1 for i in infos.values() if i and i["unforced"])}


def merge_records(records):
    """One record for several messages (e.g. a battle segment): counts add up, slacks are
    concatenated, warm_cost is the largest (a frame has room only for the dearest glyph)."""
    out = {}
    for r in records:
        for k, v in r.items():
            if k == "warm_cost":
                if v is not None:
                    out[k] = max(out.get(k, v), v)
            elif k in ("slacks", "tick_slacks", "stop_wastes"):
                out[k] = sorted(out.get(k, []) + list(v))
            elif k == "line_ticks":
                if v is not None:
                    out[k] = max(out.get(k) or v, v)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = out.get(k, 0) + v
    return out


IDENTICAL_KEYS = ("frames", "drops", "printing_tasks", "glyph_tasks", "pages", "slacks")


def room_frames(normal, fast):
    """Glyph tasks of the NORMAL run whose pass had room for one more glyph: with one more
    glyph of FAST's measured extra-glyph cost (ticks) it would still have ended more than one
    display line before VBlank (the same physical test as an unnecessary frame stop)."""
    warm = fast.get("warm_cost")
    if warm is None:
        return 0
    return sum(1 for slack in normal.get("tick_slacks", ()) if slack - warm > FIT_ALLOWANCE)


def order_errors(records):
    """Judge one message's speeds by the product (records: {mode: speed_record}).

    - NORMAL is the original printer: frames, dropped frames, printing and glyph tasks,
      pages and every pass's slack equal the ORIGINAL (unknown value 3) run's exactly;
    - no FAST frame stop gave up a glyph that would have fitted: with one more glyph of
      the median observed cost the pass would still have ended at least two lines before
      VBlank (pass_info; stops before any cost was measured in the scene are exempt);
    - FAST takes at most NORMAL's frames, and strictly fewer when any NORMAL frame had
      room for one more glyph (room_frames); a tie without such a frame is reported as a
      note (the physical cap);
    - FAST drops no more frames than NORMAL, and at most OVERRUNS_PER_MESSAGE only because
      of its extra glyphs (an unforced overrun; one is reported as a note, D-2276).
    Returns (errors, notes)."""
    if any(m not in records for m in MODES):
        return [f"speeds missing: {sorted(set(MODES) - set(records))} (vacuous order check)"], []
    errors, notes = [], []
    o, n, f = records[ORIGINAL], records[NORMAL], records[FAST]
    if not o["frames"]:
        errors.append("the original printer took no frames (vacuous order check)")
    errors += [f"NORMAL: {k} {n.get(k)} != original {o.get(k)} (NORMAL must be the original printer)"
               for k in IDENTICAL_KEYS if n.get(k) != o.get(k)]
    if f.get("untimed_stops"):
        errors.append(f"FAST: {f['untimed_stops']} frame stops without the gate's own tick timing (vacuous stop check)")
    if f["unnecessary_stops"]:
        errors.append(f"FAST: {f['unnecessary_stops']} frame stops gave up a glyph that would have fitted "
                      f"(one more glyph would still have ended the pass more than {FIT_ALLOWANCE} ticks before VBlank)")
    room = room_frames(n, f)
    if f["frames"] > n["frames"]:
        errors.append(f"FAST ({f['frames']} frames) is slower than NORMAL ({n['frames']} frames)")
    elif f["frames"] == n["frames"]:
        if room:
            errors.append(f"FAST ({f['frames']} frames) is not faster than NORMAL ({n['frames']} frames) although "
                          f"{room} NORMAL frames had room for one more glyph")
        else:
            notes.append(f"FAST {f['frames']} / NORMAL {n['frames']} frames at the physical cap: no NORMAL frame "
                         "had room for one more glyph")
    if f["drops"] > n["drops"]:
        errors.append(f"FAST: {f['drops']} dropped frames while printing, NORMAL {n['drops']}")
    if f["unforced_overruns"] > OVERRUNS_PER_MESSAGE:
        errors.append(f"FAST: {f['unforced_overruns']} frames dropped only because of the batch's extra glyphs "
                      f"(without them the pass would have ended before VBlank; at most {OVERRUNS_PER_MESSAGE} "
                      "per message, D-2276)")
    elif f["unforced_overruns"]:
        notes.append(f"FAST: {f['unforced_overruns']} frame dropped only because of the batch's extra glyphs "
                     "(within the per-message budget, D-2276)")
    return errors, notes


def tally_overruns(summary, records):
    """Add one message's FAST printing frames and unforced overruns to the gate report's
    'overrun_budget' (validate_release judges the run's total against OVERRUN_FRAMES, D-2276)."""
    f = records.get(FAST)
    if not f:
        return
    budget = summary.setdefault("overrun_budget", {"fast_frames": 0, "unforced_overruns": 0})
    budget["fast_frames"] += f.get("frames", 0)
    budget["unforced_overruns"] += f.get("unforced_overruns", 0)


def overrun_budget_error(total):
    """The run-wide budget (D-2276): total {'fast_frames', 'unforced_overruns'} over all gates."""
    over, frames = total.get("unforced_overruns", 0), total.get("fast_frames", 0)
    if over * OVERRUN_FRAMES > frames:
        return (f"FAST: {over} frames dropped only because of the batch's extra glyphs in {frames} FAST "
                f"printing frames (budget: at most 1 per {OVERRUN_FRAMES}, D-2276)")
    return None


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
VALUE_COLUMNS = ((100, 184), (184, 248))   # NORMAL (label at x 108), FAST (label at x 188)
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
    """The TEXT SPEED row shows two separate value labels (NORMAL, FAST), each inside its own
    column, the one for `mode` (0 NORMAL, 1 FAST) in the selected colour and the other not,
    and nothing spills above/below the row. A label running into the panel border
    (x >= 248) leaves its column. img: 256x384 RGB."""
    y0, y1 = row
    errors = []
    bg = img.getpixel((100, y0 - 3))
    for y in (y0 - 3, y0 - 2, y1 + 2, y1 + 3):
        spill = [x for x in range(*ROW_X) if _is_text(img.getpixel((x, y)), bg)]
        if spill:
            errors.append(f"text pixels outside the row at y={y} x={spill[0]}..{spill[-1]}")
    labels = row_clusters(img, y0, y1)
    if len(labels) != len(columns):
        return errors + [f"expected {len(columns)} value labels in the TEXT SPEED row, found {len(labels)}: {labels}"]
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
def completed_shown(shots, last, final):
    """First frame from which the text box shows the completed message, or None.

    shots: {emulator frame: text-box hash} for the frames from the final glyph's frame
    `last` up to the snapshot of the completed text (hash `final`). The completed
    text is on screen from the earliest frame f >= last such that every recorded
    frame from f up to the snapshot shows `final`. The battle's dwell is measured
    from this frame, not from the final glyph's frame: DeSmuME's emulator frame
    starts at display line 0, while a battle loop pass starts at VBlank (line 192),
    so one task run can span two emulator frames, and a FAST batch whose last glyph
    is drawn after line 0 gets the next frame's number although the pass, its window
    copy and the frame the text appears in are the same (work/notes/text_speed_vcount.md)."""
    frames = sorted(f for f in shots if f >= last)
    if not frames or shots[frames[-1]] != final:
        return None
    shown = frames[-1]
    for f in reversed(frames[:-1]):
        if shots[f] != final or f != shown - 1:
            break
        shown = f
    return shown


def pause_values(row):
    """(pause in passes, dwell in frames) of one battle message row."""
    return (row.get("after_last_passes"), row.get("dwell"))


def battle_pacing_errors(baseline, other, ab=None):
    """Compare one segment (battle start or one turn) between the original printer and a
    speed, both started from the same checkpoint. Rows: {'text', 'glyphs', 'pixels',
    'to_first_passes' / 'to_free_passes': game-loop passes from the printer's start to its
    first glyph / from the final glyph to the printer's removal, 'after_last_passes':
    passes from the final glyph to the next printer or the segment end, 'dwell': frames
    the completed text stayed unchanged on screen}.

    The text sequence must be identical (same battle), every message complete and its
    completed text pixels identical; the first-glyph and end-of-text steps exactly equal.
    The pause (passes) and the dwell (frames) must equal the original's. Where they do
    not, ab[i] must hold the A/B replay of that message (battle_pacing.py): the speed run
    replayed from the same checkpoint, switched to the original printer at the pause
    start (the pass in which the printer is freed). {'faithful': the replay reproduced
    the speed run up to the switch, 'plain': (pause, dwell) of the speed run, 'switched':
    (pause, dwell) of the replay}. The difference is accepted only when the replay is
    faithful and both values are exactly equal to the speed run's: the pause then does
    not depend on the speed's code during the pause. The pause depends on the sound engine's
    state, which every sound triggered earlier in the segment shapes at its own absolute
    time (work/notes/text_speed_vcount.md). Nothing is sampled and nothing tolerated."""
    if not baseline:
        return ["baseline segment printed no messages (vacuous comparison)"]
    errors = []
    texts_a = [r["text"] for r in baseline]
    texts_b = [r["text"] for r in other]
    if texts_a != texts_b:
        return [f"message sequence differs from the original printer: {texts_b} != {texts_a}"]
    for i, (a, b) in enumerate(zip(baseline, other)):
        name = a["text"][:40]
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
        if a.get("after_last_passes") is None or b.get("after_last_passes") is None:
            errors.append(f"{name!r}: pause not measured in passes")
            continue
        va, vb = pause_values(a), pause_values(b)
        if va == vb:
            continue
        what = f"pause/dwell {vb[0]} passes/{vb[1]} frames != original {va[0]}/{va[1]}"
        replay = (ab or {}).get(i)
        if replay is None:
            errors.append(f"{name!r}: {what} and no A/B replay at the pause start")
        elif not replay.get("faithful"):
            errors.append(f"{name!r}: {what}; the A/B replay did not reproduce the speed run up to the pause "
                          f"start")
        elif tuple(replay["plain"]) != vb:
            errors.append(f"{name!r}: {what}; the A/B replay's speed values {tuple(replay['plain'])} are not the "
                          f"speed run's {vb}")
        elif tuple(replay["switched"]) != vb:
            errors.append(f"{name!r}: {what}; switched to the original printer at the pause start the pause/"
                          f"dwell is {tuple(replay['switched'])}: the speed's code changes the pause")
    return errors


def rng_pin_errors(pins, seed):
    """Battle RNG pin (battle_pacing.py): every segment-0 run must have written `seed` into the
    battle RNG state at its first use and read the same value back. pins: [{'applied',
    'readback', 'mode', 'delay', ...}] in run order."""
    if not pins:
        return ["no battle RNG pin recorded (vacuous pin check)"]
    errors = []
    for p in pins:
        tag = f"{p.get('mode')} delay {p.get('delay', 0)}"
        if not p.get("applied"):
            errors.append(f"battle RNG pin not applied ({tag}): the battle RNG was never used in segment 0")
        elif p.get("readback") != seed:
            errors.append(f"battle RNG pin did not hold ({tag}): read back {p.get('readback')!r}, pinned {seed:#x}")
    return errors


def segment_start_errors(reached, pins, seed):
    """One battle segment run (battle_pacing.py): whether it reached its end without A/B input
    and, for a segment-0 run (pins: its pin records; None for later segments), the pin check.
    Cause first: a run that stopped before the battle RNG's first use (the pin was never
    applied) failed by being stuck, and the missing pin is a consequence. A pin that was
    applied but did not hold comes first (the wrong battle may be why the run got stuck);
    a run that reached its end gets the strict pin check alone."""
    pin = rng_pin_errors(pins, seed) if pins is not None else []
    if reached:
        return pin
    stuck = "stuck without A/B input"
    if pins and not all(p.get("applied") for p in pins):
        return [stuck] + [f"{e} (a consequence: the run stopped before the battle RNG's first use)" for e in pin]
    return pin + [stuck]


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
