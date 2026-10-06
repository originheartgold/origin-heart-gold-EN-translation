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
    """Per-glyph cadence trace of native printer tasks, plus printer allocation pairing.

    Hooks are registered exclusive (emu_harness raises if anything else registers the
    same address later, which DeSmuME would otherwise do silently): the native print_task (r1 printer), the
    glyph draw (r4 printer), the native init_printer (r0 new printer) and
    FreeToHeap (r0). memcheck.Probe's own FreeToHeap handler is chained.

    A glyph belongs to the printer's most recent native task. The entry is dropped
    when the printer is (re)initialised or freed, so a synchronous print or a
    reused allocation never inherits a stale task. When the game lags, one task can
    straddle an emulator frame boundary; frames are therefore observations only.
    glyphs rows: (printer, task id, phase at task entry, frame, x, y)."""

    def __init__(self, h, payload, font=None, probe=None, on_task=None, on_glyph=None):
        self.h, self.font, self._probe = h, font, probe
        self._on_task, self._on_glyph = on_task, on_glyph
        self.task = 0
        self.current = {}
        self.glyphs = []
        self.events = 0
        self.allocations, self.frees = [], []
        h.on_exec(payload['symbols']['print_task'] & ~1, self._task, exclusive=True)
        h.on_exec(payload['symbols']['init_printer'] & ~1, self._init, exclusive=True)
        h.on_exec(GLYPH, self._glyph, exclusive=True)
        h.on_exec(FREE_TO_HEAP, self._free, exclusive=True)

    def _task(self, h):
        self.task += 1
        ptr = h.reg.r1
        self.current[ptr] = (self.task, h.u8(ptr + 0x34))
        if self._on_task is not None:
            self._on_task(h, ptr)

    def _init(self, h):
        self.events += 1
        self.allocations.append((self.events, h.reg.r0))
        self.current.pop(h.reg.r0, None)

    def _free(self, h):
        self.events += 1
        self.frees.append((self.events, h.reg.r0))
        self.current.pop(h.reg.r0, None)
        if self._probe is not None:
            self._probe._on_summary_free(FREE_TO_HEAP, 2)

    def _glyph(self, h):
        ptr = h.reg.r4
        if self.font is not None and h.u8(ptr + 9) != self.font:
            return
        task, phase = self.current.get(ptr, (None, None))
        self.glyphs.append((ptr, task, phase, h.frame, h.u16(ptr + 12), h.u16(ptr + 14)))
        if self._on_glyph is not None:
            self._on_glyph(h, ptr, (task, phase, h.frame))

    def mark(self):
        return len(self.glyphs)

    def since(self, mark, printer=None):
        return [(task, phase, frame) for ptr, task, phase, frame, _, _ in self.glyphs[mark:]
                if printer is None or ptr == printer]

    def layout(self, mark):
        return [[x, y] for *_, x, y in self.glyphs[mark:]]

    def live(self):
        from text_speed_checks import unfreed
        return unfreed(self.allocations, self.frees)
