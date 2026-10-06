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
"""
from collections import Counter, defaultdict
import math

ORIGINAL = 3
NAMES = {0: "SLOW", 1: "MEDIUM", 2: "FAST", ORIGINAL: "ORIGINAL"}
# A message must have at least this many glyphs before its cadence is judged on
# "the budget is actually used" (short words and control codes truncate batches).
MIN_GLYPHS_FOR_USE = 12
# Fraction of tasks that must render their whole budget: proves the budget is
# exercised, so a ROM that silently prints one glyph per task cannot pass.
MIN_FULL_FRACTION = 0.5


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
    """Judge one message's glyph cadence.

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
    if len(glyphs) >= MIN_GLYPHS_FOR_USE:
        for budget, (n, full) in sorted(per_budget.items()):
            if budget > 1 and full < MIN_FULL_FRACTION * n:
                errors.append(f"{NAMES[mode]}: only {full}/{n} tasks with budget {budget} used it "
                              "(the speed is slower than designed)")
        if mode == 0 and set(per_budget) != {1, 2}:
            errors.append(f"SLOW: phase did not alternate (budgets seen {sorted(per_budget)})")
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


def speed_order_with_lag(spans, lag):
    """Frame order where the game may drop frames (lag) while printing.

    spans: {mode: first-to-last glyph frames}; lag: {mode: frames inside that span in
    which no glyph was drawn although printing was not waiting (game skipped the task)}.
    Returns (errors, warnings). Printing frames (span - lag) must be strictly ordered;
    a span violation that the lag fully explains is only a warning: the setting does
    less work per frame as designed, but the game ran slower meanwhile."""
    work = {m: spans[m] - lag.get(m, 0) for m in spans}
    errors = speed_order(work, strict=True)
    warnings = [] if errors else [f"{e} because of lag frames {lag}" for e in speed_order(spans, strict=True)]
    return errors, warnings


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
def battle_pacing_errors(baseline, other, tolerance=2):
    """Compare one segment (battle start or one turn) between the original printer and a
    speed, both started from the same checkpoint. Rows: {'text', 'glyphs',
    'after_last': frames from the final glyph to the next printer or the segment end,
    'dwell': frames the completed text stayed unchanged (None if not measured)}.

    The text sequence must be identical (same battle), every message complete, and
    every pause after a completed message preserved within `tolerance` frames."""
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
        for key in ("after_last", "dwell"):
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
