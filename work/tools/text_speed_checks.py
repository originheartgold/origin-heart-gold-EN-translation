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
- every native task draws at least one glyph (or handles one control); before each
  further glyph it stops if fewer than MIN_LINES_FOR_GLYPH display lines are left
  until the next VBlank starts, unless fewer than FRAME_LOST_LINES are left (the
  frame is lost anyway) (frame stop). A frame stop keeps SLOW's two-glyph phase
  for the next task.
"""
from collections import Counter, defaultdict
import math

ORIGINAL = 3
NAMES = {0: "SLOW", 1: "MEDIUM", 2: "FAST", ORIGINAL: "ORIGINAL"}
# Units the native loop stops before (end, extended control, page/scroll prompts, 0xF0FD).
CONTROLS = frozenset((0xFFFF, 0xFFFE, 0x25BC, 0x25BD, 0xF0FD))
# Same values as MIN_LINES_FOR_GLYPH / FRAME_LOST_LINES in work/patches/text_speed/native.c, pinned here
# independently: the gates judge the binary's frame stops against this model.
MIN_LINES_FOR_GLYPH = 20
FRAME_LOST_LINES = 7
VISIBLE_LINES, TOTAL_LINES = 192, 263
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


def speed_order(spans, strict=True):
    """spans: {mode: frames from first to last glyph of the same message}.

    ORIGINAL >= SLOW >= MEDIUM >= FAST must hold; with strict=True the three
    choices must also be strictly ordered (a label promising FAST must be faster
    than MEDIUM on this message). Returns errors."""
    errors = []
    order = [m for m in (ORIGINAL, 0, 1, 2) if m in spans]
    if len(order) < 2:
        return ["fewer than two speeds observed (vacuous order check)"]
    for slower, faster in zip(order, order[1:]):
        a, b = spans[slower], spans[faster]
        if b > a or (strict and slower != ORIGINAL and b == a):
            errors.append(f"{NAMES[faster]} ({b} frames) is not faster than {NAMES[slower]} ({a} frames)")
    return errors


def frame_order(spans, frame_limited):
    """Total printing frames of the same message per mode, judged strictly.

    spans: {mode: frames from first to last glyph}; frame_limited: {mode: number of
    tasks that stopped on the frame limit (task_errors summary 'frame')}.
    The original printer must be strictly slower than SLOW, and SLOW >= MEDIUM >=
    FAST. Two neighbouring speeds may take the same number of frames only when the
    faster one hit the frame limit in this message: then every frame already holds
    as many glyphs as fit before VBlank, and a larger budget cannot print faster
    without dropping frames. Any other tie, and every inversion, is an error.
    Returns (errors, notes); notes list the frame-limited ties."""
    order = [m for m in (ORIGINAL, 0, 1, 2) if m in spans]
    if len(order) < 2:
        return ["fewer than two speeds observed (vacuous order check)"], []
    errors, notes = [], []
    for slower, faster in zip(order, order[1:]):
        a, b = spans[slower], spans[faster]
        if b > a:
            errors.append(f"{NAMES[faster]} ({b} frames) is slower than {NAMES[slower]} ({a} frames)")
        elif b == a:
            if slower != ORIGINAL and frame_limited.get(faster, 0) > 0:
                notes.append(f"{NAMES[faster]} = {NAMES[slower]} ({a} frames): {NAMES[faster]} "
                             f"stopped {frame_limited[faster]} tasks on the frame limit")
            else:
                errors.append(f"{NAMES[faster]} ({b} frames) is not faster than {NAMES[slower]} ({a} frames)")
    return errors, notes


def lag_errors(lag, slack=1):
    """lag: {mode: frames inside the printing span in which the game did not run the
    printer's task (dropped frames)}. No speed may drop more than `slack` frames more
    than the original printer did on the same message."""
    if ORIGINAL not in lag or len(lag) < 2:
        return ["lag of the original printer and at least one speed required (vacuous lag check)"]
    return [f"{NAMES[m]}: {lag[m]} dropped frames while printing, original {lag[ORIGINAL]}"
            for m in sorted(lag) if m != ORIGINAL and lag[m] > lag[ORIGINAL] + slack]


def exact_errors(name, baseline, values):
    """values: {mode: number} that must equal the original printer's value exactly."""
    if baseline is None:
        return [f"{name}: not measured for the original printer (vacuous comparison)"]
    return [f"{NAMES[m]}: {name} {v} != original {baseline}" for m, v in sorted(values.items()) if v != baseline]


# ----------------------------------------------------------------- per-task stop reasons
def lines_to_vblank(line):
    """Display lines left until the next VBlank starts (1..263), as native.c computes it."""
    if not 0 <= line < TOTAL_LINES:
        raise ValueError(f"VCOUNT {line} out of range")
    return VISIBLE_LINES - line if line < VISIBLE_LINES else VISIBLE_LINES + TOTAL_LINES - line


def frame_stop(line, min_lines=MIN_LINES_FOR_GLYPH, lost=FRAME_LOST_LINES):
    """The native loop's frame rule: stop before another glyph? Stop when the glyph would
    not fit before the next VBlank, unless the frame is lost anyway (too few lines left
    even to stop)."""
    left = lines_to_vblank(line)
    return lost <= left < min_lines


def task_errors(mode, tasks, min_lines=MIN_LINES_FOR_GLYPH):
    """Judge every native task of one message against the loop's design.

    tasks: [{'id', 'phase' (+0x34 at entry), 'paused' (global print pause flag at
    entry), 'delegated' (the native task called the original task), 'events': [('render',),
    ('glyph', next unit), ('check', VCOUNT line), ...] in order, 'next_phase' (phase at
    the same printer's next task, None if none)}].

    Rules: an ordinary task renders at least once; a glyph is followed either by
    the end of the task or by a frame check; a check comes only after a glyph, and
    the next render happens exactly when the check allows it (frame_stop). A task
    that ends with budget left after a glyph must stop for a reason: the next unit is
    a control, or the last check was a frame stop. SLOW's phase flips after a task
    that drew, except after a frame stop; MEDIUM/FAST never change it.
    Returns (summary {'reasons': {reason: n}, 'frame': n, ...}, errors)."""
    errors, reasons = [], Counter()
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
        renders = sum(1 for e in events if e[0] == "render")
        glyphs = sum(1 for e in events if e[0] == "glyph")
        if not renders:
            errors.append(f"{tag}: rendered nothing (a task must draw at least one glyph)")
            continue
        if glyphs > budget:
            errors.append(f"{tag}: {glyphs} glyphs, budget {budget}")
        last_check, prev = None, None
        for i, e in enumerate(events):
            if e[0] == "check":
                if prev is None or prev[0] != "glyph":
                    errors.append(f"{tag}: frame check {'before the first glyph' if prev is None else 'not after a glyph'}")
                stop = frame_stop(e[1], min_lines)
                following = events[i + 1][0] if i + 1 < len(events) else None
                if stop and following is not None:
                    errors.append(f"{tag}: drew on after a frame stop at line {e[1]} "
                                  f"({lines_to_vblank(e[1])} lines left)")
                if not stop and following != "render":
                    errors.append(f"{tag}: stopped although the frame check at line {e[1]} allowed another glyph")
                last_check = (e[1], stop)
            elif e[0] == "render" and prev is not None:
                if prev[0] != "check":
                    errors.append(f"{tag}: started another glyph without a frame check")
            prev = e
        last_render = max(i for i, e in enumerate(events) if e[0] == "render")
        drew_last = any(e[0] == "glyph" for e in events[last_render + 1:])
        last_glyph = [e for e in events if e[0] == "glyph"][-1:] or None
        if not drew_last:
            reason = "result"
        elif glyphs >= budget:
            reason = "budget"
        elif last_glyph and last_glyph[0][1] in CONTROLS:
            reason = "control"
        elif events[-1][0] == "check" and last_check and last_check[1]:
            reason = "frame"
        else:
            reason = None
            unit = last_glyph[0][1] if last_glyph else None
            errors.append(f"{tag}: stopped after {glyphs} of {budget} glyphs without a reason"
                          f" (next unit {unit:#06x})" if unit is not None else f"{tag}: stopped without a reason")
        if reason:
            reasons[reason] += 1
        if t.get("next_phase") is not None:
            flip = mode == 0 and glyphs > 0 and reason != "frame"
            want = (t["phase"] ^ 1) & 0xFF if flip else t["phase"]
            if t["next_phase"] != want:
                errors.append(f"{tag}: phase {t['phase']} -> {t['next_phase']}, expected {want} "
                              f"({NAMES[mode]}, {reason} stop)")
    summary = {"tasks": len(tasks), "reasons": dict(sorted(reasons.items())), "frame": reasons["frame"]}
    return summary, errors


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
def battle_pacing_errors(baseline, other, tolerance=0):
    """Compare one segment (battle start or one turn) between the original printer and a
    speed, both started from the same checkpoint. Rows: {'text', 'glyphs',
    'after_last': frames from the final glyph to the next printer or the segment end,
    'dwell': frames the completed text stayed unchanged (None if not measured)}.

    The text sequence must be identical (same battle), every message complete, the
    completed text pixels identical (key 'pixels') and every pause after a completed
    message, the on-screen dwell and the frames from the final glyph to the printer's
    removal ('to_free') exactly equal to the original's (tolerance 0)."""
    if not baseline:
        return ["baseline segment printed no messages (vacuous comparison)"]
    errors = []
    texts_a = [r["text"] for r in baseline]
    texts_b = [r["text"] for r in other]
    if texts_a != texts_b:
        return [f"message sequence differs from the original printer: {texts_b} != {texts_a}"]
    for a, b in zip(baseline, other):
        name = a["text"][:40]
        if a["glyphs"] != b["glyphs"]:
            errors.append(f"{name!r}: {b['glyphs']} glyphs != original {a['glyphs']}")
        if a.get("pixels") != b.get("pixels"):
            errors.append(f"{name!r}: completed text pixels differ from the original printer")
        for key in ("after_last", "dwell", "to_free"):
            if a.get(key) is None and b.get(key) is None:
                continue
            if a.get(key) is None or b.get(key) is None:
                errors.append(f"{name!r}: {key} measured in only one run")
            elif abs(a[key] - b[key]) > tolerance:
                errors.append(f"{name!r}: {key} {b[key]} frames != original {a[key]} (pause not preserved)")
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
