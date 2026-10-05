"""Cold-boot text-speed corpus regression using emu_harness.

Script injection selects messages only; Options are changed through native UI.
Each mode runs in its own process/private battery directory. No old savestates.
"""
import argparse
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/tools'))
CORPUS = ((48, 20), (48, 26), (48, 60), (457, 123), (718, 160), (718, 1093))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child(args):
    from emu_harness import Harness, SENTINEL_VAR, message_script
    from memcheck import Probe
    from text_speed_patch import load_payload
    payload = load_payload()
    result = {'status': 'failed', 'rom_sha256': digest(args.rom), 'mode': args.mode, 'messages': []}
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False) as h:
            h.set_clock(datetime(2026, 10, 9, 12))
            h.boot_to_menu()
            h.continue_game()
            assert h.read(payload['base'], len(bytes.fromhex(payload['code']))) == bytes.fromhex(payload['code']), 'wrong native payload'
            probe = Probe(h.emu)
            probe.armed = True
            def frame(h):
                probe.frame = h.frame
                if h.frame % 10 == 0 and probe.corrupt is None:
                    bad = probe.heap_walk()
                    if bad:
                        probe.corrupt = (h.frame, bad)
            h.on_frame(frame)
            menus = []
            exits = []
            h.on_exec(payload['symbols']['exit_free'] & ~1, lambda h: exits.append(h.frame))
            glyphs = []
            starts = []
            h.on_exec(payload['symbols']['load_rows'] & ~1, lambda h: menus.append(h.reg.r0))
            h.on_exec(0x02002680, lambda h: glyphs.append((h.frame, h.u16(h.reg.r4+12), h.u16(h.reg.r4+14), h.u8(h.reg.r4+9))) if h.u8(h.reg.r4+9)==1 else None)
            h.on_exec(0x020208D4, lambda h: starts.append({'speed': h.reg.r1, 'callback': h.reg.r2}))
            def open_options():
                before = len(menus)
                h.press('X', after=90)
                h.touch(124, 115, after=300)
                assert len(menus) == before+1, 'Options failed to open'
                d = menus[-1]
                assert h.u16(d+0x27c) == 3, 'text row missing'
                return d
            d = open_options()
            opts = h.u32(d+0x24)
            original = h.u16(opts)
            assert (original >> 2) & 3 == 0, 'fixture is not an old NORMAL save'
            # First exercise cancel after touch, then reopen and commit via buttons.
            h.touch(227, 152, after=60)
            assert h.u16(d+0x27e) == 2 and h.u16(opts) == original
            h.touch(220, 180, after=300)
            assert h.u16(opts) == original, 'Cancel committed text speed'
            d = open_options()
            assert h.u16(d+0x27e) == 0
            # Touch locates the row; d-pad moves the value and A confirms native UI.
            h.touch(130, 152, after=40)
            for _ in range(args.mode):
                h.press('RIGHT', after=30)
            assert h.u16(d+0x27e) == args.mode, 'button selection failed'
            h.press('DOWN', after=30)
            assert (h.u32(d+16)>>2)&7 == 7
            h.press('LEFT', after=30)  # Native CN row defaults to Quit (0); Confirm is 1.
            assert h.u16(d+0x2d2) == 1, 'Confirm button not selected'
            prior_exits = len(exits)
            h.press('A', after=300)
            assert len(exits) == prior_exits+1, 'A did not leave Options'
            h.press('B', after=90)  # Options returns to the field menu; close it before scripts.
            h.screenshot('after-confirm')
            expected = (original & ~12) | (args.mode << 2)
            assert h.u16(opts) == expected, ('Confirm changed unrelated options', h.u16(opts), expected)
            result['options'] = {'before': original, 'after': expected, 'cancel': 'passed', 'buttons': 'passed'}
            for bank, msg in CORPUS:
                mark = len(glyphs)
                sentinel = h.get_var(SENTINEL_VAR)
                h.set_var(SENTINEL_VAR, 0)
                program = message_script(bank, msg)
                try:
                    h.run_script(file=3, index=0, msg_bank=bank, program=program, settle=480)
                    pages = []
                    for page in range(16):
                        if h.get_var(SENTINEL_VAR) == 0x5A5A:
                            break
                        # Exclude the animated continuation arrow, keep all text pixels.
                        crop = h.emu.screenshot().crop((8, 145, 236, 184))
                        pages.append(hashlib.sha256(crop.tobytes()).hexdigest())
                        h.screenshot(f'{bank}_{msg}_{page}')
                        n = len(glyphs)
                        h.step(120)
                        assert len(glyphs) == n, 'page progressed without input'
                        assert crop.tobytes() == h.emu.screenshot().crop((8,145,236,184)).tobytes(), 'text changed while waiting'
                        h.press('A', after=480)
                    assert h.get_var(SENTINEL_VAR) == 0x5A5A, 'message did not complete within page budget'
                    gs = glyphs[mark:]
                    assert gs and pages, 'empty/vacuous message test'
                    bank_source = json.loads((ROOT/f'work/translate/banks/a027/{bank:04d}.json').read_text())
                    source = next(s['en'] for s in bank_source['strings'] if s['id']==msg)
                    expected_glyphs = len(re.sub(r'\{[^}]*\}', '', source))
                    assert len(gs)==expected_glyphs, ('wrong message or incomplete rendering',bank,msg,len(gs),expected_glyphs)
                    result['messages'].append({'bank':bank, 'id':msg, 'pages':pages, 'glyphs':len(gs),
                                               'layout': [g[1:] for g in gs], 'span':gs[-1][0]-gs[0][0]})
                finally:
                    h.set_var(SENTINEL_VAR, sentinel)
                assert h.u16(opts) == expected, 'dialogue changed Options'
            result['printers'] = starts
            result['memory'] = {k:getattr(probe,k) for k in ('heap_checks','corrupt','fails','nullw','text_rejections','heap_table_errors','text_probe_errors')}
            assert probe.heap_checks and not any(result['memory'][k] for k in result['memory'] if k != 'heap_checks'), result['memory']
            result['status'] = 'passed'
    finally:
        (args.out/'report.json').write_text(json.dumps(result, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--save', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--mode', type=int, choices=range(3))
    args = p.parse_args()
    args.rom, args.save, args.out = args.rom.resolve(), args.save.resolve(), args.out.resolve()
    if not args.out.is_relative_to(ROOT/'work/build') or args.out == ROOT/'work/build':
        p.error('Output must be inside this worktree work/build')
    args.out.mkdir(parents=True, exist_ok=True)
    if args.mode is not None:
        child(args)
        return
    identities = {str(path):digest(path) for path in (args.rom,args.save)}
    report = {'status':'failed', 'inputs':identities, 'modes':[]}
    try:
        for mode in range(3):
            out = args.out/str(mode)
            with (args.out/f'{mode}.log').open('w') as log:
                subprocess.run([sys.executable, __file__, '--rom',str(args.rom),'--save',str(args.save),
                                '--out',str(out),'--mode',str(mode)], check=True, timeout=600,
                               stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
            r = json.loads((out/'report.json').read_text())
            assert r['status']=='passed' and r['rom_sha256']==identities[str(args.rom)]
            report['modes'].append(r)
        baseline = report['modes'][0]['messages']
        for r in report['modes'][1:]:
            assert len(r['messages']) == len(baseline)
            for a,b in zip(baseline,r['messages']):
                for key in ('bank','id','pages','glyphs','layout'):
                    assert a[key]==b[key], (r['mode'],a['bank'],a['id'],key)
        assert all(digest(Path(path))==sha for path,sha in identities.items()), 'input modified'
        report['status']='passed'
    finally:
        (args.out/'report.json').write_text(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
