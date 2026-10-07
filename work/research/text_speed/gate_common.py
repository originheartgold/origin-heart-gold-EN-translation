"""Shared setup for the text-speed runtime gates.

- Every gate takes --rom/--out (and --save where needed). Output stays under
  this worktree's work/build. Inputs are hashed before and after.
- The expected native payload is the reviewed one (text_speed_patch.load_payload).
  --fault-payload accepts a payload written by fault_fixture.py for a deliberately
  broken ROM. Such reports are marked "fault_fixture" and never count as release
  evidence (validate_release.py refuses them).
- itcm_errors() checks the original ITCM code, the payload and the SDK ITCM arena
  in emulator RAM; gates call it at the start and again at the end of a session.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

if sys.flags.optimize:
    # Gate checks must never be stripped: refuse to run under python -O.
    raise SystemExit('text-speed gates refuse to run with python -O (sys.flags.optimize is set)')


class GateError(Exception):
    """A gate check failed (raised by require(); never stripped like assert)."""


def require(condition, message):
    """Explicit gate check: raise GateError(message) unless condition holds."""
    if not condition:
        raise GateError(message if isinstance(message, str) else repr(message))

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / 'work/build'
sys.path.insert(0, str(ROOT / 'work/tools'))

ITCM_START = 0x01FF8000
ITCM_END = 0x02000000
ARENA_LO_ITCM = 0x027FFDAC     # OSArenaInfo lo[OS_ARENA_ITCM] (main-memory system area)
ARENA_HI_ITCM = 0x027FFDD0     # OSArenaInfo hi[OS_ARENA_ITCM]
PRINTER_TASK = 0x02020A1C      # original printer task (the native task delegates here)
GLYPH = 0x02002680             # RenderText glyph draw: r4 = printer
PRINTER_START = 0x020208D4     # AddTextPrinter: r0 template, r1 speed, r2 callback
PRINTER_DESTROY = 0x0202075C   # RemoveTextPrinter(id)
RENDER = 0x02020A88            # render one step (glyph or control) of a printer: r0 printer
PRINT_PAUSED = 0x021D0EF4      # global flag: printer tasks return without printing
FREE_TO_HEAP = 0x0201B33C
MEMORY_KEYS = ('heap_checks', 'corrupt', 'fails', 'nullw', 'text_rejections',
               'heap_table_errors', 'text_probe_errors')


# The emulated RTC otherwise follows host time; clock-driven field work changes how
# often the game drops frames, which changes measured frame spans between runs.
CLOCK = datetime(2026, 10, 9, 12)


def start_game(h):
    """Pinned clock, cold boot, Continue into the field."""
    h.set_clock(CLOCK)
    h.boot_to_menu()
    h.continue_game()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def add_arguments(parser, save=True):
    parser.add_argument('--rom', type=Path, required=True)
    if save:
        parser.add_argument('--save', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fault-payload', type=Path,
                        help='payload.json of a fault_fixture.py ROM (proves a check fails; never release evidence)')


def resolve(parser, args):
    for name in ('rom', 'save', 'out', 'fault_payload'):
        if getattr(args, name, None) is not None:
            setattr(args, name, getattr(args, name).resolve())
    if not args.out.is_relative_to(BUILD) or args.out == BUILD:
        parser.error('Output must be a separate directory under this worktree work/build')
    args.out.mkdir(parents=True, exist_ok=True)
    return args


def load_expected_payload(args):
    import text_speed_patch
    if getattr(args, 'fault_payload', None) is None:
        return text_speed_patch.load_payload()
    if not args.fault_payload.is_relative_to(BUILD):
        raise SystemExit('fault payloads must live under work/build')
    payload = json.loads(args.fault_payload.read_text())
    if not {'source_sha256', 'base', 'code', 'symbols', 'fault'} <= set(payload) <= {
            'source_sha256', 'base', 'code', 'symbols', 'fault', 'checker'}:
        raise SystemExit('not a fault_fixture.py payload')
    # A fault may declare the frame model its broken payload implements, so that the
    # gates' model matches it and only the product checks can catch the fault. Only
    # fault payloads (never release evidence) can do this.
    import text_speed_checks
    for name, value in payload.get('checker', {}).items():
        if name not in text_speed_checks.FAULT_KNOBS:
            raise SystemExit(f'fault payload sets unknown checker constant {name}')
        setattr(text_speed_checks, name, tuple(value) if isinstance(value, list) else value)
    return payload


def identity(args, payload):
    """Report header binding the run to its inputs and expected payload."""
    inputs = {str(p): digest(p) for p in (args.rom, getattr(args, 'save', None)) if p is not None}
    head = {'inputs': inputs, 'payload_code_sha256': hashlib.sha256(bytes.fromhex(payload['code'])).hexdigest()}
    if 'fault' in payload:
        head['fault_fixture'] = payload['fault']
    return head


def inputs_unchanged(report):
    return all(digest(Path(path)) == sha for path, sha in report['inputs'].items())


def payload_bytes(payload):
    return bytes.fromhex(payload['code'])


def code_bytes(payload):
    """The payload's fixed bytes: everything before the runtime frame state (its last bytes)."""
    return payload_bytes(payload)[:payload['symbols']['text_speed_state'] - payload['base']]


PAGE_GAP = 20   # frames without a glyph that separate two pages (page waits are far longer)


def page_ranges(frames, gap=PAGE_GAP):
    """[(first, last)] glyph frames of each page, split where no glyph was drawn for > gap frames."""
    out = []
    for f in sorted(frames):
        if out and f - out[-1][1] <= gap:
            out[-1][1] = f
        else:
            out.append([f, f])
    return [tuple(x) for x in out]


def judge_message(trace, mode, mark, task_mark, pages=None):
    """Model and product verdict for one message printed since (mark, task_mark).

    Returns (record, stop summary, errors): text_speed_checks.task_errors over the
    printer's tasks (must run before the product record), then speed_record with the
    median observed cost of an extra glyph."""
    import statistics
    import text_speed_checks as checks
    glyphs = trace.since(mark)
    tasks = trace.tasks_since(task_mark, set(trace.printers_since(mark)))
    summary, errors = checks.task_errors(mode, tasks)
    pages = pages or page_ranges([f for _, _, f in glyphs])
    warm = checks.warm_costs(tasks)
    cost = statistics.median(warm) if warm else None
    record = checks.speed_record(tasks, pages, cost if cost is not None else checks.GLYPH_SEED)
    record.update(warm_cost=cost, glyphs=len(glyphs), page_spans=[b - a for a, b in pages])
    return record, summary, errors


def itcm_errors(h, payload):
    """Original ITCM code, payload and arena reservation intact in emulator RAM."""
    import text_speed_patch
    errors = []
    code = payload_bytes(payload)
    base = payload['base']
    original = h.read(ITCM_START, base - ITCM_START)
    if hashlib.sha256(original).hexdigest() != text_speed_patch.REVIEWED_ITCM_SHA256:
        errors.append('original ITCM code changed in RAM')
    fixed = code_bytes(payload)
    if h.read(base, len(fixed)) != fixed:
        errors.append('native payload in ITCM differs from the expected payload')
    end = (base + len(code) + 31) & ~31
    lo, hi = h.u32(ARENA_LO_ITCM), h.u32(ARENA_HI_ITCM)
    if lo < end or hi != ITCM_END or lo > hi:
        errors.append(f'ITCM arena {lo:#x}..{hi:#x} overlaps the payload (ends {end:#x})')
    return errors


def attach_probe(h, every=10):
    """memcheck.Probe with a heap walk every `every` frames, armed now."""
    from memcheck import Probe
    probe = Probe(h.emu)
    probe.armed = True

    def frame(h):
        probe.frame = h.frame
        if h.frame % every == 0 and probe.corrupt is None:
            bad = probe.heap_walk()
            if bad:
                probe.corrupt = (h.frame, bad)
    h.on_frame(frame)
    return probe


def memory_summary(probe):
    return {key: getattr(probe, key) for key in MEMORY_KEYS}


def memory_errors(summary):
    if not summary['heap_checks']:
        return ['no heap checks ran (vacuous memory check)']
    return [f'{key}: {summary[key]}' for key in MEMORY_KEYS if key != 'heap_checks' and summary[key]]


def heap_usage(h):
    """{heap id: (used blocks, used bytes)} of every live expanded heap (memcheck's heap table)."""
    from memcheck import HEAP_INFO
    handles, idxs, count = h.u32(HEAP_INFO), h.u32(HEAP_INFO + 0x10), h.u16(HEAP_INFO + 0x14)
    usage = {}
    for hid in range(count):
        heap = h.u32(handles + 4 * h.u8(idxs + hid))
        if not heap or h.u32(heap) != 0x45585048:
            continue
        p, blocks, size, n = h.u32(heap + 0x2C), 0, 0, 0
        while p and n < 8192:
            blocks, size, n = blocks + 1, size + h.u32(p + 4), n + 1
            p = h.u32(p + 12)
        usage[hid] = (blocks, size)
    return usage


VCOUNT = 0x04000006            # DS display line register (I/O)
VBLANKS = 0x027FFC3C           # SDK VBlank counter (HW_VBLANK_COUNT_BUF), stepped at line 192
FRAME_END_CALL = 0x02000DE0    # the game loop's 'bl' that the payload redirects to frame_end
FRAME_END_RETURN = 0x02000DE4  # the instruction after it


class PrinterTrace:
    """Per-glyph and per-task trace of native printer tasks, the payload's frame model,
    and printer allocation pairing.

    Hooks are registered exclusive (emu_harness raises if anything else registers the
    same address later, which DeSmuME would otherwise do silently): the native
    print_task (r1 printer), the original task when the native task delegates to it,
    the render step when the native loop calls it, the glyph draw (r4 printer),
    RemoveTextPrinter, the native init_printer (r0 new printer), FreeToHeap (r0), and
    every VCOUNT / VBlank-counter load in print_task and frame_end (found by io_reads;
    hooked on the instruction after the load, so the hook sees exactly the value the
    payload read). memcheck.Probe's own FreeToHeap handler is chained.

    The frame model (text_speed_checks.FrameModel) starts from the payload's state in
    RAM and is then updated only from these observed readings; before every reading
    the payload's RAM state must equal the model (state_errors otherwise). Each
    reading after a render is recorded as ('check', line, decision) with the model's
    decision at that line; the end of a batch as ('mark', line). Each task also gets
    'start' (VBlank count, line) at entry, 'b_lines' (readings after renders that drew
    a glyph) and 'pass_end' (VBlank count, line) from the next frame_end.

    A glyph belongs to the printer's most recent native task. The entry is dropped
    when the printer is (re)initialised or freed, so a synchronous print or a
    reused allocation never inherits a stale task.
    glyphs rows: (printer, task id, phase at task entry, frame, x, y).
    tasks: one record per native task for text_speed_checks.task_errors()."""

    def __init__(self, h, payload, font=None, probe=None, on_task=None, on_glyph=None, on_destroy=None,
                 on_original=None, on_render=None):
        import text_speed_checks as checks
        self._checks = checks
        self.h, self.font, self._probe = h, font, probe
        self._on_render = on_render
        self._on_task, self._on_glyph, self._on_destroy, self._on_original = on_task, on_glyph, on_destroy, on_original
        self.task = 0
        self.current = {}
        self.records = {}
        self.active = None
        self.tasks = []
        self.glyphs = []
        self.events = 0
        self.allocations, self.frees, self.destroys = [], [], []
        self.task_frames = {}
        code = payload_bytes(payload)
        self._payload_range = (payload['base'], payload['base'] + len(code))
        self._state = payload['symbols']['text_speed_state']
        self.reads = io_reads(payload)
        h.on_exec(payload['symbols']['print_task'] & ~1, self._task, exclusive=True)
        h.on_exec(payload['symbols']['init_printer'] & ~1, self._init, exclusive=True)
        h.on_exec(PRINTER_TASK, self._original, exclusive=True)
        h.on_exec(RENDER, self._render, exclusive=True)
        h.on_exec(GLYPH, self._glyph, exclusive=True)
        h.on_exec(FREE_TO_HEAP, self._free, exclusive=True)
        h.on_exec(PRINTER_DESTROY, self._destroy, exclusive=True)
        for where, loads in self.reads.items():
            for address, mnemonic, base_reg, index_reg, offset in loads:
                h.on_exec(address, self._load(where, mnemonic, base_reg, index_reg, offset), exclusive=True)
        self._reset_model()

    # ------------------------------------------------------------------ frame model
    def _reset_model(self):
        self.model = self._checks.FrameModel(self.h.read(self._state, self._checks.STATE_SIZE))
        self.state_errors = []
        self.frame_ends = []
        self._open = []            # tasks whose loop pass has not ended yet
        self._vblanks = None       # VBlank counter value just read, waiting for its VCOUNT reading

    def resync(self):
        """After loading a savestate without reset(): restart the frame model from RAM (the
        payload's state came back with the savestate); recorded tasks and errors stay."""
        errors = self.state_errors
        self._reset_model()
        self.state_errors = errors

    def _compare(self, where):
        ram = self.h.read(self._state, self._checks.STATE_SIZE)
        want = self.model.to_bytes()
        if ram != want and len(self.state_errors) < 20:
            self.state_errors.append(f'frame {self.h.frame} {where}: payload state {ram.hex()} != model '
                                     f'{want.hex()} (the stored costs differ from the observed ones)')
            self.model = self._checks.FrameModel(ram)   # resynchronise; the error stays

    def _load(self, where, mnemonic, base_reg, index_reg, offset):
        """Hook on a load instruction about to run: if it reads VCOUNT or the VBlank counter,
        record the value it is going to load (no emulated time passes before it runs)."""
        size = {'ldrb': 1, 'ldrsb': 1, 'ldrh': 2, 'ldrsh': 2}.get(mnemonic, 4)
        io = self._io(where)

        def hook(h):
            address = (getattr(h.reg, base_reg) + (getattr(h.reg, index_reg) if index_reg else offset)) & 0xFFFFFFFF
            if address == VCOUNT:
                if size != 2:
                    self.state_errors.append(f'frame {h.frame}: {mnemonic} of VCOUNT in {where}')
                io(h, 'vcount', h.u16(VCOUNT))
            elif address == VBLANKS:
                io(h, 'vblanks', h.u8(VBLANKS) if size == 1 else h.u32(VBLANKS))
        return hook

    def _io(self, where):
        def hook(h, what, value):
            if what == 'vblanks':
                # mark() stores the counter before it reads VCOUNT: compare here, before that store.
                self._compare(f'{where} reading')
                self._vblanks = value & 255
                return
            line = value
            vblanks, self._vblanks = self._vblanks, None
            if vblanks is None:
                self._compare(f'{where} reading')
            if where == 'frame_end':
                if vblanks is None:
                    self.state_errors.append(f'frame {h.frame}: frame_end read VCOUNT without the VBlank counter')
                    return
                self.model.frame_end(vblanks, line)
                full = h.u32(VBLANKS)
                end = (full - ((full - vblanks) & 255), line)
                self.frame_ends.append((h.frame, line, end[0]))
                for rec in self._open:
                    rec['pass_end'] = end
                    rec['pass_end_frame'] = h.frame
                self._open = []
                return
            rec = self.active
            if vblanks is not None:                      # mark(): VBlank counter, then VCOUNT
                self.model.mark(vblanks, line)
                if rec is not None:
                    rec['events'].append(('mark', line))
                return
            if rec is None:
                self.state_errors.append(f'frame {h.frame}: print_task read VCOUNT outside an observed task')
                return
            drew = rec['_since_render'] == 'glyph'
            if drew:
                if rec['b_lines']:
                    self.model.glyph_cost(rec['b_lines'][-1], line)
                rec['b_lines'].append(line)
            rec['events'].append(('check', line, self.model.decide(line)))
        return hook

    def _from_payload(self, h):
        lo, hi = self._payload_range
        return lo <= (h.reg.lr & ~1) < hi

    def _task(self, h):
        self.task += 1
        ptr = h.reg.r1
        phase = h.u8(ptr + 0x34)
        previous = self.records.get(ptr)
        if previous is not None:
            previous['next_phase'] = phase
        rec = {'id': self.task, 'printer': ptr, 'frame': h.frame, 'phase': phase, 'font': h.u8(ptr + 9),
               'printer_id': h.u8(ptr + 0x2C), 'paused': h.u8(PRINT_PAUSED) != 0, 'delegated': False,
               'special': h.u32(ptr + 0x1C) != 0 or (h.u8(ptr + 0x29) & 127) != 0,
               'events': [], 'next_phase': None, 'start': (h.u32(VBLANKS), h.u16(VCOUNT)), 'b_lines': [],
               'pass_end': None, '_since_render': None}
        self.records[ptr] = rec
        self.active = rec
        self.tasks.append(rec)
        self._open.append(rec)
        self.current[ptr] = (self.task, phase)
        self.task_frames.setdefault(ptr, set()).add(h.frame)
        if self._on_task is not None:
            self._on_task(h, ptr)

    def _original(self, h):
        delegated = self._from_payload(h)
        rec = self.active
        if delegated and rec is not None and rec['printer'] == h.reg.r1:
            rec['delegated'] = True
        if self._on_original is not None:
            self._on_original(h, h.reg.r1, delegated)

    def _render(self, h):
        if self._on_render is not None:
            self._on_render(h)
        rec = self.active
        lr = h.reg.lr & ~1
        if rec is not None and rec['printer'] == h.reg.r0 and (
                self._from_payload(h) or PRINTER_TASK <= lr < RENDER):
            if self._from_payload(h) and not any(e[0] == 'render' for e in rec['events']):
                self.model.task_ran()        # print_task sets 'ran' before its first render
            rec['events'].append(('render',))
            rec['_since_render'] = 'render'

    def _forget(self, ptr):
        self.current.pop(ptr, None)
        self.records.pop(ptr, None)
        if self.active is not None and self.active['printer'] == ptr:
            self.active = None

    def _init(self, h):
        self.events += 1
        self.allocations.append((self.events, h.reg.r0))
        self._forget(h.reg.r0)

    def _free(self, h):
        self.events += 1
        self.frees.append((self.events, h.reg.r0))
        self._forget(h.reg.r0)
        if self._probe is not None:
            self._probe._on_summary_free(FREE_TO_HEAP, 2)

    def _destroy(self, h):
        self.destroys.append((h.frame, h.reg.r0))
        if self._on_destroy is not None:
            self._on_destroy(h)

    def _glyph(self, h):
        ptr = h.reg.r4
        rec = self.records.get(ptr)
        if rec is not None and rec is self.active:
            # The next unit the batch looks at: newlines (0xE000) render together with the unit after them.
            at = h.u32(ptr)
            unit = h.u16(at)
            while unit == 0xE000:
                at += 2
                unit = h.u16(at)
            rec['events'].append(('glyph', unit))
            rec['_since_render'] = 'glyph'
        if self.font is not None and h.u8(ptr + 9) != self.font:
            return
        task, phase = self.current.get(ptr, (None, None))
        self.glyphs.append((ptr, task, phase, h.frame, h.u16(ptr + 12), h.u16(ptr + 14)))
        if self._on_glyph is not None:
            self._on_glyph(h, ptr, (task, phase, h.frame))

    def reset(self):
        """Forget everything recorded (e.g. after loading a savestate); hooks stay. The
        frame model restarts from the payload's state in RAM."""
        self.current, self.records, self.active = {}, {}, None
        self.tasks, self.glyphs, self.task_frames = [], [], {}
        self.allocations, self.frees, self.destroys = [], [], []
        self._reset_model()

    def mark(self):
        return len(self.glyphs)

    def task_mark(self):
        return len(self.tasks)

    def since(self, mark, printer=None):
        return [(task, phase, frame) for ptr, task, phase, frame, _, _ in self.glyphs[mark:]
                if printer is None or ptr == printer]

    def printers_since(self, mark):
        return sorted({ptr for ptr, *_ in self.glyphs[mark:]})

    def tasks_since(self, task_mark, printers=None):
        return [t for t in self.tasks[task_mark:] if printers is None or t['printer'] in printers]

    def lag(self, mark, end=None):
        """Frames between a printer's first and last glyph (glyphs[mark:end]) in which that
        printer's native task did not run: frames the game dropped while printing."""
        rows = self.glyphs[mark:end]
        total = 0
        for ptr in {r[0] for r in rows}:
            frames = [r[3] for r in rows if r[0] == ptr]
            ran = self.task_frames.get(ptr, set())
            total += sum(1 for f in range(min(frames), max(frames) + 1) if f not in ran)
        return total

    def control_latencies(self, task_mark, printers):
        """For each glyph that is followed by a control step (a render that draws no glyph:
        page prompt, scroll, pause, end of text), the number of the printer's tasks from
        the glyph's task to the task that handles the control. The original printer handles
        it in the next task (1); batching that ran on into the control would give 0.
        Counted in tasks, not frames, so dropped frames do not change it."""
        flat = []
        for n, t in enumerate(t for t in self.tasks[task_mark:] if t['printer'] in printers):
            flat += [(n, e[0]) for e in t['events'] if e[0] in ('render', 'glyph')]
        out = []
        for i, (n, kind) in enumerate(flat):
            if kind != 'render' or (i + 1 < len(flat) and flat[i + 1][1] == 'glyph'):
                continue                       # not a render, or a render that drew a glyph
            if i and flat[i - 1][1] == 'glyph':
                out.append(n - flat[i - 1][0])
        return out

    def tasks_between(self, first_id, last_id, printer):
        """Tasks of `printer` with first_id < id <= last_id."""
        return sum(1 for t in self.tasks if t['printer'] == printer and first_id < t['id'] <= last_id)

    def layout(self, mark):
        return [[x, y] for *_, x, y in self.glyphs[mark:]]

    def live(self):
        from text_speed_checks import unfreed
        return unfreed(self.allocations, self.frees)

def io_reads(payload):
    """{routine: [(address, mnemonic, base register, offset register or None, offset)]}: every
    byte, halfword or word load in print_task and frame_end (from each entry to the next
    global symbol, so inlined and local helpers are included). PrinterTrace hooks all of
    them and keeps those whose effective address, computed from the registers when the
    instruction is about to run, is VCOUNT or the VBlank counter. This does not depend
    on how the compiler keeps the I/O address in registers."""
    import capstone
    code, base = payload_bytes(payload), payload['base']
    state = payload['symbols']['text_speed_state']
    starts = sorted(a & ~1 for n, a in payload['symbols'].items() if n != 'text_speed_state')
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    md.detail = True
    out = {}
    for routine in ('print_task', 'frame_end'):
        start = payload['symbols'][routine] & ~1
        end = min([a for a in starts if a > start] + [state])
        loads = []
        for x in md.disasm(code[start - base:end - base], start):
            if x.mnemonic in ('ldrb', 'ldrh', 'ldr', 'ldrsb', 'ldrsh') and len(x.operands) == 2:
                mem = x.operands[1].mem
                if mem.base == capstone.arm.ARM_REG_PC:
                    continue
                index = x.reg_name(mem.index) if mem.index else None
                loads.append((x.address, x.mnemonic, x.reg_name(mem.base), index, mem.disp))
        out[routine] = loads
    return out
