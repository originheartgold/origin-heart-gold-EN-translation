"""Pokégear phone-call pages wait for A/B after a battle, at every text speed (D-1600, bug D-1599).

    python phone_call_wait.py --rom CANDIDATE.nds --save trainer.sav --out work/build/<dir>

Bug: the battle sets the renderer's auto-scroll mode (SetAutoScrollParam(3)) and
the hack never clears it at battle exit, so a phone call made after a battle
advanced every page by itself after 101 frames. The fix redirects the Pokégear's
only call-page printer call (overlay 92, 0x021F1228) to the native call_print,
which clears auto-scroll and then prints exactly as before.

Scenarios, each in its own process (own DeSmuME battery directory, pinned clock):

- battle-normal / battle-fast / battle-reserved: from the trainer.sav checkpoint,
  start and win the facing trainer battle (at the save's own speed, so every run
  reaches the call identically), set the text speed (NORMAL 0, FAST 1, or the
  reserved value 3, which the payload treats as NORMAL), open the Pokégear and
  call Mom (outgoing call);
- ring-battle-normal / ring-battle-fast: the same battle, then an incoming call:
  Mom calls the player through the game's own scripted-call commands
  (SetPhoneCall 0, 2, 0 and RunPhoneCall, the commands the hack's scripts use for a
  forced call, between a fade-out and RestoreOverworld plus fade-in as for any
  scripted application); the Pokégear opens in call mode and prints through the same call
  printer. This call has several messages (call_print entries), which the gate
  requires;
- control / ring-control: the outgoing and the incoming call with no battle before
  it (NORMAL).

Fails unless, per scenario:
- the scenario reproduces the bug's precondition: after the battle the text-flag
  byte has auto-scroll set (a run that cannot reproduce the bug is not a pass);
  in the controls it is clear;
- the call reaches call_print for every message, and auto-scroll is clear while
  the call prints;
- the auto-scroll wait (0x02002AB0) is never entered for the call printer;
- every page waits: after it is complete, HOLD frames without input draw no glyph
  and do not advance, and one fresh A press then continues within PRESS_LATENCY
  frames; after a message's last page (the printer is removed) the call neither
  starts the next message nor hangs up within HOLD frames without input; the call
  ends normally (the Pokégear's call teardown runs);
- after the call, the next battle sets auto-scroll again on entry and its intro
  messages advance with no input (auto-wait completes) up to the command menu;
- original ITCM, payload and ITCM arena intact at start and end; heap walks clean.

Across scenarios: the completed call pages (window pixel buffer and glyph layout)
are identical at every speed, the reserved value and in the control, per call
(outgoing, incoming); the incoming call has at least two messages.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess
import sys

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import (CLOCK, GLYPH, PRINTER_DESTROY, ROOT, add_arguments, attach_probe, digest, identity,  # noqa: E402
                         inputs_unchanged, itcm_errors, load_expected_payload, memory_errors, memory_summary,
                         require, resolve, start_game)

TEXT_FLAGS = 0x021106CE          # renderer flags byte: bit 2 auto-scroll, bit 5 auto + A/B, bit 4 touch
AUTO_BITS = 0x24
SET_AUTO_SCROLL = 0x02002B50     # SetAutoScrollParam(r0)
SET_TOUCH = 0x02002B8C           # SetTouch(r0); the Pokégear sets it at call start and clears it at call end
AUTO_WAIT = 0x02002AB0           # TextPrinterWaitAutoMode(printer): counts to 100, then advances
PAGE_WAIT = (0x02002AEC, 0x02002B10)   # RenderText page waits (r0 printer): auto wait or A/B wait
CALL_PRINTER = 0x021F11E8        # overlay 92 call-page printer (ctx in r0)
CALL_PRINTER_SIG = bytes.fromhex('10b584b0041c081c')
CALL_END_LR = 0x021EF0B9         # SetTouch(0) return address in the overlay 92 call teardown
TALK_OBJ_START, TALK_OBJ_SIG = 0x021E5D2C, bytes.fromhex('59f626fc')   # field talk handler (emu_harness OV1_SIG)
INCOMING = (0, 2, 0)             # SetPhoneCall arguments: Mom's scripted call (several messages)
HOLD = 600                       # frames a completed page must stay without input
PRESS_LATENCY = 30               # frames from a fresh A press to the next page's first glyph
# name: (battle first, stored text-speed value, call: 'out' (player calls Mom) or 'in' (Mom calls))
SCENARIOS = {'battle-normal': (True, 0, 'out'), 'battle-fast': (True, 1, 'out'), 'battle-reserved': (True, 3, 'out'),
             'control': (False, 0, 'out'),
             'ring-battle-normal': (True, 0, 'in'), 'ring-battle-fast': (True, 1, 'in'),
             'ring-control': (False, 0, 'in')}


class CallTrace:
    """Event hooks (exclusive) for the call printer, page waits and text flags."""

    def __init__(self, h, payload):
        self.h = h
        self.window = None
        self.ctx = None
        self.messages = []        # (frame, flags at call_print entry)
        self.ov92_entries = 0
        self.glyphs = []          # call printer: (frame, x, y)
        self.other_glyphs = 0
        self.auto_glyphs = 0      # call glyphs drawn while auto-scroll was set
        self.waits = []           # frames of a call-printer page-wait poll
        self.auto_waits = []      # call printer: (frame, counter)
        self.other_auto_done = []  # any other printer's auto wait completing (counter 100): frames
        self.auto_params = []     # (frame, value, lr)
        self.touch = []           # (frame, value, lr)
        self.removed = []         # frames the call printer was removed
        h.on_exec(payload['symbols']['call_print'] & ~1, self._call_print, exclusive=True)
        h.on_exec(CALL_PRINTER, self._ov92, exclusive=True)
        h.on_exec(GLYPH, self._glyph, exclusive=True)
        h.on_exec(AUTO_WAIT, self._auto, exclusive=True)
        for addr in PAGE_WAIT:
            h.on_exec(addr, self._wait, exclusive=True)
        h.on_exec(SET_AUTO_SCROLL, lambda h: self.auto_params.append((h.frame, h.reg.r0, h.reg.lr)), exclusive=True)
        h.on_exec(SET_TOUCH, lambda h: self.touch.append((h.frame, h.reg.r0, h.reg.lr)), exclusive=True)
        h.on_exec(PRINTER_DESTROY, self._destroy, exclusive=True)

    def _ours(self, printer):
        return self.window is not None and self.h.u32(printer + 4) == self.window

    def _call_print(self, h):
        self.window = h.reg.r0
        self.messages.append((h.frame, h.u8(TEXT_FLAGS)))

    def _ov92(self, h):
        if h.read(CALL_PRINTER, len(CALL_PRINTER_SIG)) == CALL_PRINTER_SIG:
            self.ov92_entries += 1
            self.ctx = h.reg.r0
            self.window = h.u32(h.reg.r0 + 0xC)

    def _glyph(self, h):
        if self._ours(h.reg.r4):
            self.glyphs.append((h.frame, h.u16(h.reg.r4 + 12), h.u16(h.reg.r4 + 14)))
            self.auto_glyphs += bool(h.u8(TEXT_FLAGS) & AUTO_BITS)
        else:
            self.other_glyphs += 1

    def _wait(self, h):
        if self._ours(h.reg.r0):
            self.waits.append(h.frame)

    def _auto(self, h):
        counter = h.u8(h.reg.r0 + 0x22)
        if self._ours(h.reg.r0):
            self.auto_waits.append((h.frame, counter))
        elif counter == 100:
            self.other_auto_done.append(h.frame)

    def _destroy(self, h):
        if self.ctx is not None and h.reg.r0 == h.u8(self.ctx + 0x35):
            self.removed.append(h.frame)

    def hung_up(self):
        return any(lr == CALL_END_LR and v == 0 for _, v, lr in self.touch)

    def window_pixels(self):
        """SHA-256 of the call window's 4bpp pixel buffer (exact text pixels, no screen animation)."""
        w = self.window
        width, height = self.h.u8(w + 7), self.h.u8(w + 8)
        return hashlib.sha256(self.h.read(self.h.u32(w + 0xC), width * height * 32)).hexdigest()


def run_call(h, t, result, errors):
    """From the first call message: hold and advance every page until the call ends."""
    call_start = h.frame
    ended = None
    next_page = 0           # call glyphs before the call printer started
    for page_no in range(24):
        # The press that ends a page is followed by the next page's first glyphs;
        # they belong to that page however many one task draws.
        glyph_mark = next_page
        wait_mark, removed_mark = len(t.waits), len(t.removed)
        messages_mark = len(t.messages)

        def page_state(h):
            if len(t.removed) > removed_mark:
                return 'finished'
            if len(t.waits) > wait_mark and len(t.glyphs) > glyph_mark:
                return 'waiting'
            return None
        require(h.run_until(page_state, 2000), f'page {page_no + 1}: neither waiting nor finished')
        state = page_state(h)
        page = {'page': page_no + 1, 'message': len(t.messages), 'end': state, 'glyphs': len(t.glyphs) - glyph_mark,
                'layout': [[x, y] for _, x, y in t.glyphs[glyph_mark:]],
                'pixels': t.window_pixels(), 'complete_frame': h.frame - call_start}
        h.screenshot(f'page{page_no + 1}')
        result['pages'].append(page)
        if state == 'waiting':
            g, a, w = len(t.glyphs), len(t.auto_waits), len(t.waits)
            h.step(HOLD)
            page['hold'] = {'frames': HOLD, 'glyphs': len(t.glyphs) - g, 'auto_waits': len(t.auto_waits) - a,
                            'wait_polls': len(t.waits) - w, 'removed': len(t.removed) > removed_mark}
            if page['hold']['glyphs'] or page['hold']['removed']:
                errors.append(f'page {page_no + 1} advanced without input during the {HOLD}-frame hold')
            if page['hold']['wait_polls'] < HOLD - 10:
                errors.append(f'page {page_no + 1}: printer not waiting through the hold '
                              f"({page['hold']['wait_polls']} polls)")
            if t.window_pixels() != page['pixels']:
                errors.append(f'page {page_no + 1}: window changed during the hold')
            pressed, next_page = h.frame, g
            h.press('A', frames=2)
            moved = h.run_until(lambda h: len(t.glyphs) > g or len(t.removed) > removed_mark, 120)
            page['press_latency'] = h.frame - pressed
            if not moved or page['press_latency'] > PRESS_LATENCY:
                errors.append(f"page {page_no + 1}: a fresh A press did not continue within "
                              f"{PRESS_LATENCY} frames ({page['press_latency']})")
            continue
        # Message finished (the printer is removed): the Pokégear itself waits for A/B
        # before the next message or the hang-up. That wait must hold too.
        next_page = len(t.glyphs)
        held = h.frame
        moved = h.run_until(lambda h: len(t.messages) > messages_mark or t.hung_up(), HOLD)
        page['hold'] = {'frames': HOLD, 'continued_without_input': bool(moved), 'after_frames': h.frame - held}
        if moved:
            errors.append(f'page {page_no + 1} (end of message {len(t.messages)}): the call went on without '
                          f'input after {h.frame - held} frames')
        for _ in range(8):
            if h.run_until(lambda h: len(t.messages) > messages_mark or t.hung_up(), 240):
                break
            h.press('A', after=0)
        if t.hung_up():
            ended = h.frame - call_start
            break
        require(len(t.messages) > messages_mark, 'call neither continued nor ended after a finished message')
    return ended


def child(args):
    from emu_harness import Harness, script_bytes
    payload = load_expected_payload(args)
    battle, mode, call = SCENARIOS[args.scenario]
    result = {'status': 'failed', 'scenario': args.scenario, 'mode': mode, 'call_kind': call,
              'rom_sha256': digest(args.rom), 'errors': [], 'pages': []}
    errors = result['errors']
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            start_game(h)
            start = itcm_errors(h, payload)
            require(not start, repr(start))
            probe = attach_probe(h)
            t = CallTrace(h, payload)
            if battle:
                for _ in range(12):
                    h.press('A', after=90)
                    if not h.in_field():
                        break
                h.step(300)
                require(not h.in_field(), 'the trainer battle did not start')
                result['first_battle_turns'] = h.fight([0])
                require(h.in_field(), 'not back in the field after the battle')
            h.step(400)
            flags = h.u8(TEXT_FLAGS)
            result['flags_before_call'] = flags
            result['battle_auto_params'] = [(f, v, hex(lr)) for f, v, lr in t.auto_params]
            require(not battle or flags & 4,
                    f'precondition not reproduced: auto-scroll clear after the battle ({flags:#x})')
            require(battle or not flags & 4, f'control: auto-scroll already set before the call ({flags:#x})')
            opts = h.array(1)
            h.w16(opts, (h.u16(opts) & ~12) | (mode << 2))
            result['options'] = h.u16(opts)
            if call == 'out':
                h.field_menu('pokegear')
                h.screenshot('pokegear')
                for i in range(3):          # Mom -> Call
                    h.press('A', after=54)
            else:
                # Mom calls: the game's scripted incoming call; the script waits for the call to end.
                # As the game's scripts launch an application: fade out, run, restore the field, fade in.
                h.run_script(program=script_bytes(("LockAll",), ("FadeScreen", 6, 1, 0, 0), ("WaitFade",),
                                                  ("SetPhoneCall", *INCOMING), ("RunPhoneCall",),
                                                  ("RestoreOverworld",), ("FadeScreen", 6, 1, 1, 0), ("WaitFade",),
                                                  ("ReleaseAll",), ("End",)), settle=0)
            require(h.run_until(lambda h: t.ov92_entries, 900), 'the call printer was not reached')
            h.screenshot('call-start')
            ended = run_call(h, t, result, errors)
            result['call'] = {'messages': len(t.messages), 'ov92_entries': t.ov92_entries,
                              'flags_at_call_print': [f for _, f in t.messages],
                              'flags_after_call': h.u8(TEXT_FLAGS), 'ended_frame': ended,
                              'auto_waits': len(t.auto_waits), 'page_wait_polls': len(t.waits),
                              'glyphs': len(t.glyphs), 'glyphs_with_auto_scroll': t.auto_glyphs}
            if ended is None:
                errors.append('the call did not end normally')
            if t.ov92_entries != len(t.messages) or not t.messages:
                errors.append(f'call printer entries {t.ov92_entries} vs call_print {len(t.messages)}: '
                              'a call message bypassed call_print')
            if t.auto_glyphs:
                errors.append(f'{t.auto_glyphs} call glyphs printed while auto-scroll was set')
            if t.auto_waits:
                errors.append(f'auto-scroll wait entered {len(t.auto_waits)} times for the call printer')
            if h.u8(TEXT_FLAGS) & AUTO_BITS:
                errors.append(f'auto-scroll still set after the call ({h.u8(TEXT_FLAGS):#x})')
            # The next battle must set auto-scroll again and advance its intro by itself.
            # B: phone list -> field with the X menu open -> menu closed (one spare press).
            # The field overlay check alone is not enough: it stays resident under the Pokégear.
            for i in range(4):
                h.press('B', after=150)
            h.screenshot('after-call-field')
            require(h.in_field() and h.read(TALK_OBJ_START, 4) == TALK_OBJ_SIG, 'not back in the field after the call')
            h.step(60)
            params, done = len(t.auto_params), len(t.other_auto_done)
            h.trainer_battle(1)
            entered = h.run_until(lambda h: not h.in_field(), 600)
            menu = entered and h.run_until(lambda h: h.on_screen('battle_menu'), 1800)
            h.screenshot('next-battle')
            set3 = [(f, v, hex(lr)) for f, v, lr in t.auto_params[params:] if v == 3]
            result['next_battle'] = {'entered': entered, 'menu_without_input': menu, 'auto_param_3': set3,
                                     'flags': h.u8(TEXT_FLAGS), 'auto_wait_completions': len(t.other_auto_done) - done}
            if not entered or not menu:
                errors.append('next battle: did not reach the command menu without input')
            if not set3 or not h.u8(TEXT_FLAGS) & 4:
                errors.append('next battle: auto-scroll was not set again on entry')
            if not result['next_battle']['auto_wait_completions']:
                errors.append('next battle: no message advanced by the auto-scroll wait')
            result['memory'] = memory_summary(probe)
            errors.extend(memory_errors(result['memory']))
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
        if not errors:
            result['status'] = 'passed'
    except BaseException as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(result, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(parser)
    parser.add_argument('--scenario', choices=sorted(SCENARIOS))
    parser.add_argument('--only', help='comma-separated scenarios (exploration; status is partial-passed)')
    parser.add_argument('--jobs', type=int, default=4)
    args = resolve(parser, parser.parse_args())
    if args.scenario is not None:
        child(args)
        return
    payload = load_expected_payload(args)
    names = args.only.split(',') if args.only else list(SCENARIOS)
    summary = {'status': 'failed', **identity(args, payload), 'hold_frames': HOLD, 'scenarios': {}, 'errors': []}

    def run(name):
        out = args.out / name
        command = [sys.executable, '-I', __file__, '--rom', str(args.rom), '--save', str(args.save),
                   '--out', str(out), '--scenario', name]
        command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
        with (args.out / f'{name}.log').open('w') as log:
            return name, subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=1800).returncode
    try:
        with ThreadPoolExecutor(max(1, args.jobs)) as pool:
            results = list(pool.map(run, names))
        reports = {}
        for name, code in results:
            path = args.out / name / 'report.json'
            if not path.exists():
                summary['errors'].append(f'{name}: child wrote no report (exit {code})')
                continue
            r = reports[name] = json.loads(path.read_text())
            summary['scenarios'][name] = {k: r.get(k) for k in ('status', 'mode', 'call_kind', 'flags_before_call',
                                                                'call', 'next_battle', 'errors')}
            summary['scenarios'][name]['pages'] = [{k: p.get(k) for k in ('page', 'message', 'end', 'glyphs',
                                                                           'pixels', 'hold', 'press_latency')}
                                                   for p in r.get('pages', [])]
            if r.get('rom_sha256') != digest(args.rom):
                summary['errors'].append(f'{name}: wrong candidate executed')
            if code or r['status'] != 'passed':
                summary['errors'].append(f'{name}: {r.get("errors")}')
        if not summary['errors']:
            for kind in ('out', 'in'):
                same = [n for n in names if SCENARIOS[n][2] == kind]
                pages = {n: [(p['pixels'], p['layout']) for p in reports[n]['pages']] for n in same}
                if len(pages) > 1:
                    reference = next(iter(pages.values()))
                    for n, got in pages.items():
                        if got != reference:
                            summary['errors'].append(f'{n}: call pages differ from {same[0]} '
                                                     '(window pixels or glyph layout)')
                incoming = [reports[n]['call']['messages'] for n in same if kind == 'in']
                if any(m < 2 for m in incoming):
                    summary['errors'].append(f'incoming call has fewer than two messages: {incoming} '
                                             '(the multi-message case is not exercised)')
        require(inputs_unchanged(summary), 'source input changed')
        if not summary['errors']:
            summary['status'] = 'passed' if not args.only else 'partial-passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(summary, indent=2, default=str))
    if summary['status'] not in ('passed', 'partial-passed'):
        raise SystemExit('\n'.join(map(str, summary['errors'])))


if __name__ == '__main__':
    main()
