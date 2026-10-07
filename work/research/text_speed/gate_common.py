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
    if set(payload) != {'source_sha256', 'base', 'code', 'symbols', 'fault'}:
        raise SystemExit('not a fault_fixture.py payload')
    return payload


def identity(args, payload):
    """Report header binding the run to its inputs and expected payload."""
    inputs = {str(p): digest(p) for p in (args.rom, getattr(args, 'save', None)) if p is not None}
    head = {'inputs': inputs, 'payload_sha256': hashlib.sha256(bytes.fromhex(payload['code'])).hexdigest()}
    if 'fault' in payload:
        head['fault_fixture'] = payload['fault']
    return head


def inputs_unchanged(report):
    return all(digest(Path(path)) == sha for path, sha in report['inputs'].items())


def payload_bytes(payload):
    return bytes.fromhex(payload['code'])


def itcm_errors(h, payload):
    """Original ITCM code, payload and arena reservation intact in emulator RAM."""
    import text_speed_patch
    errors = []
    code = payload_bytes(payload)
    base = payload['base']
    original = h.read(ITCM_START, base - ITCM_START)
    if hashlib.sha256(original).hexdigest() != text_speed_patch.REVIEWED_ITCM_SHA256:
        errors.append('original ITCM code changed in RAM')
    if h.read(base, len(code)) != code:
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


class PrinterTrace:
    """Per-glyph and per-task trace of native printer tasks, plus printer allocation pairing.

    Hooks are registered exclusive (emu_harness raises if anything else registers the
    same address later, which DeSmuME would otherwise do silently): the native
    print_task (r1 printer), the original task when the native task delegates to it,
    the render step when the native loop calls it, the native task's VCOUNT reads
    (found by vcount_reads), the glyph draw (r4 printer), RemoveTextPrinter, the native
    init_printer (r0 new printer) and FreeToHeap (r0). memcheck.Probe's own
    FreeToHeap handler is chained.

    A glyph belongs to the printer's most recent native task. The entry is dropped
    when the printer is (re)initialised or freed, so a synchronous print or a
    reused allocation never inherits a stale task.
    glyphs rows: (printer, task id, phase at task entry, frame, x, y).
    tasks: one record per native task for text_speed_checks.task_errors()."""

    def __init__(self, h, payload, font=None, probe=None, on_task=None, on_glyph=None, on_destroy=None,
                 on_original=None, on_render=None):
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
        self.vcount_reads = vcount_reads(payload)
        h.on_exec(payload['symbols']['print_task'] & ~1, self._task, exclusive=True)
        h.on_exec(payload['symbols']['init_printer'] & ~1, self._init, exclusive=True)
        h.on_exec(PRINTER_TASK, self._original, exclusive=True)
        h.on_exec(RENDER, self._render, exclusive=True)
        h.on_exec(GLYPH, self._glyph, exclusive=True)
        h.on_exec(FREE_TO_HEAP, self._free, exclusive=True)
        h.on_exec(PRINTER_DESTROY, self._destroy, exclusive=True)
        for address, register in self.vcount_reads:
            h.on_exec(address, self._vcount(register), exclusive=True)

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
               'events': [], 'next_phase': None}
        self.records[ptr] = rec
        self.active = rec
        self.tasks.append(rec)
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
            rec['events'].append(('render',))

    def _vcount(self, register):
        def hook(h):
            rec = self.active
            if rec is not None:
                rec['events'].append(('check', getattr(h.reg, register)))
        return hook

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
            rec['events'].append(('glyph', h.u16(h.u32(ptr))))
        if self.font is not None and h.u8(ptr + 9) != self.font:
            return
        task, phase = self.current.get(ptr, (None, None))
        self.glyphs.append((ptr, task, phase, h.frame, h.u16(ptr + 12), h.u16(ptr + 14)))
        if self._on_glyph is not None:
            self._on_glyph(h, ptr, (task, phase, h.frame))

    def reset(self):
        """Forget everything recorded (e.g. after loading a savestate); hooks stay."""
        self.current, self.records, self.active = {}, {}, None
        self.tasks, self.glyphs, self.task_frames = [], [], {}
        self.allocations, self.frees, self.destroys = [], [], []

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
            flat += [(n, e[0]) for e in t['events'] if e[0] != 'check']
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

VCOUNT = 0x04000006            # DS display line register (I/O, read by the native batching loop)


def vcount_reads(payload):
    """[(hook address, register)] of every VCOUNT read in the native print_task.

    Found by disassembling the payload: an 'ldr rX, [pc, #n]' whose literal is
    VCOUNT, followed by 'ldrh rY, [rX]'. The hook address is the instruction after
    the ldrh, where rY holds exactly the line the code compares. Expected: the
    task-start read, then the read before each extra glyph."""
    import capstone
    import struct
    code, base = payload_bytes(payload), payload['base']
    start = payload['symbols']['print_task'] & ~1
    end = min([a & ~1 for a in payload['symbols'].values() if (a & ~1) > start] + [base + len(code)])
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    md.detail = True
    ins = list(md.disasm(code[start - base:end - base], start))
    found, loaded = [], {}
    for i, x in enumerate(ins):
        if x.mnemonic == 'ldr' and '[pc' in x.op_str:
            lit = ((x.address + 4) & ~3) + x.operands[1].mem.disp
            if base <= lit < base + len(code) - 3 and struct.unpack_from('<I', code, lit - base)[0] == VCOUNT:
                loaded[x.operands[0].reg] = True
                continue
        if x.mnemonic == 'ldrh' and x.operands[1].mem.base in loaded and x.operands[1].mem.disp == 0 \
                and i + 1 < len(ins):
            found.append((ins[i + 1].address, x.reg_name(x.operands[0].reg)))
        for op in x.operands[:1]:
            if op.type == capstone.arm.ARM_OP_REG and x.mnemonic not in ('cmp', 'tst', 'str', 'strh', 'strb'):
                loaded.pop(op.reg, None)
    return found
