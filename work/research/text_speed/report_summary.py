#!/usr/bin/env python3
"""Compact views of validate_release reports, for agents (read this, not the JSON).

  report_summary.py summary REPORT.json     one screen: status, hashes, one line per gate
  report_summary.py diff OLD.json NEW.json  only what changed (observations, statuses, gates)
  report_summary.py faults DIR              one line per fault-run report under DIR

Exit codes: summary 0 only for passed + releasable; diff 0 unless a gate status
regressed; faults 1 if any fault was MISSED. Missing or unknown fields print "?".
"""
import argparse
import json
import sys
from pathlib import Path

ERR_WIDTH = 120
OK = ('passed', 'fault-detected', 'partial-passed')


def load(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise SystemExit(f'{path}: cannot read report ({e})')
    if not isinstance(data, dict):
        raise SystemExit(f'{path}: not a report object')
    return data


def short(v, n=8):
    return v[:n] if isinstance(v, str) and v else '?'


def dget(obj, *path):
    for p in path:
        if isinstance(obj, dict) and p in obj:
            obj = obj[p]
        elif isinstance(obj, list) and isinstance(p, int) and -len(obj) <= p < len(obj):
            obj = obj[p]
        else:
            return None
    return obj


def flatten(obj, prefix='', out=None):
    """Nested dicts/lists -> {dotted.key: scalar}. Empty containers become scalars."""
    out = {} if out is None else out
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            flatten(v, f'{prefix}.{k}' if prefix else str(k), out)
    elif isinstance(obj, list) and obj:
        for i, v in enumerate(obj):
            flatten(v, f'{prefix}[{i}]', out)
    else:
        out[prefix] = obj
    return out


# gate -> list of (label, key path). First usable group wins; groups are tried in order.
# A group is shown only if every key in it exists; unknown gates fall back to a count.
METRICS = {
    'options': [[('checks', ('checks',)), ('heap', ('heap_checks',))]],
    'music': [[('combos', ('combinations',)), ('getters', ('getter_checks',))]],
    'lifecycle': [[('msgs', ('messages',)), ('ctors', ('constructors',)), ('reused', ('reused_allocations',))]],
    'fallbacks': [[('span s/m/f', ('slow', 'span'), ('medium', 'span'), ('fast', 'span'))]],
    'natural-dialogue': [[('span s/m/f', ('slow', 'frame_span'), ('medium', 'frame_span'), ('fast', 'frame_span'))]],
}


def metric(name, obs):
    for group in METRICS.get(name, []):
        parts = []
        for label, *paths in group:
            vals = [dget(obs, *p) for p in (paths if len(paths) > 1 else [paths[0]])]
            if any(v is None for v in vals):
                parts = None
                break
            parts.append(f'{label}={"/".join(str(v) for v in vals)}')
        if parts:
            return ' '.join(parts)
    if name == 'corpus':
        n = dget(obs, 'print_frames')
        if isinstance(n, dict) and n:
            return f'{len(n)} msgs'
    if name == 'battle' and isinstance(dget(obs, 'segments'), list):
        return f'{len(obs["segments"])} segs'
    if name == 'save' and isinstance(obs, list):
        return f'{len(obs)} modes'
    if obs is None or (isinstance(obs, (dict, list)) and not obs):
        return '?'
    return f'{len(flatten(obs))} obs'


def first_error(row):
    err = row.get('errors') if isinstance(row, dict) else None
    if err is None:
        err = row.get('reason') if isinstance(row, dict) else None
    if err is None:
        return ''
    if isinstance(err, list):
        err = err[0] if err else ''
    text = ' '.join(str(err).split())
    return text if len(text) <= ERR_WIDTH else text[:ERR_WIDTH - 3] + '...'


def gates_of(report):
    g = report.get('gates')
    return g if isinstance(g, dict) else {}


def summary_lines(r):
    status = r.get('status', '?')
    inputs = r.get('inputs') if isinstance(r.get('inputs'), dict) else {}
    dirty = r.get('git_dirty')
    dirty_end = r.get('git_dirty_at_end')
    lines = [f"status={status} releasable={r.get('releasable', '?')} "
             f"rom={short(r.get('rom_sha256'))} payload={short(r.get('payload_code_sha256') or r.get('payload_sha256'))} "
             f"save={short(r.get('save_sha256'))} commit={short(r.get('git_head'), 7)} "
             f"dirty={'?' if dirty is None else bool(dirty) or bool(dirty_end)}"]
    pr = r.get('payload_reproduction')
    if isinstance(pr, dict):
        lines.append(f"payload-reproduction exit={pr.get('exit', '?')}")
    if isinstance(r.get('fault_fixture'), dict):
        fv = r.get('fault_verdict')
        lines.append(f"fault={r['fault_fixture'].get('name', '?')} verdict={fv if fv else 'ok'}")
    for name, row in gates_of(r).items():
        row = row if isinstance(row, dict) else {}
        err = first_error(row)
        lines.append(f"{name:<17} {row.get('status', '?'):<7} {metric(name, row.get('observations'))}"
                     + (f'  | {err}' if err else ''))
    for key in ('problems', 'warnings'):
        v = r.get(key)
        items = list(v.items()) if isinstance(v, dict) else list(v or [])
        lines.append(f'{key}: {len(items)}')
        for it in items[:3]:
            text = ' '.join((f'{it[0]}: {it[1]}' if isinstance(v, dict) else str(it)).split())
            lines.append('  ' + (text if len(text) <= ERR_WIDTH else text[:ERR_WIDTH - 3] + '...'))
    return lines


def cmd_summary(a):
    r = load(a.report)
    print('\n'.join(summary_lines(r)))
    return 0 if r.get('status') == 'passed' and r.get('releasable') is True else 1


def fmt(v):
    return json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v


def change(old, new):
    num = (int, float)
    if isinstance(old, num) and isinstance(new, num) and not isinstance(old, bool) and not isinstance(new, bool):
        d = new - old
        return f'{old}->{new} ({d:+g})'
    return f'{fmt(old)}->{fmt(new)}'


def cmd_diff(a):
    old, new = load(a.baseline), load(a.new)
    go, gn = gates_of(old), gates_of(new)
    out, regress = [], False
    for k in ('status', 'releasable', 'rom_sha256', 'payload_code_sha256', 'payload_sha256', 'git_head'):
        if old.get(k) != new.get(k):
            ov, nv = old.get(k), new.get(k)
            out.append(f'{k}: ' + (f'{short(ov, 12)}->{short(nv, 12)}' if 'sha' in k or k == 'git_head'
                                    else change(ov, nv)))
    for name in sorted(set(go) - set(gn)):
        out.append(f'gate removed: {name} (was {dget(go, name, "status") or "?"})')
    for name in sorted(set(gn) - set(go)):
        out.append(f'gate added: {name} ({dget(gn, name, "status") or "?"})')
    for name in gn:
        if name not in go:
            continue
        so, sn = dget(go, name, 'status'), dget(gn, name, 'status')
        if so != sn:
            out.append(f'gate {name}: {so}->{sn}')
            if so == 'passed' and sn != 'passed':
                regress = True
        fo = flatten(dget(go, name, 'observations'))
        fn = flatten(dget(gn, name, 'observations'))
        for key in sorted(set(fo) | set(fn)):
            if key in fo and key in fn:
                if fo[key] != fn[key]:
                    out.append(f'{name}.{key}: {change(fo[key], fn[key])}')
            elif key in fo:
                out.append(f'{name}.{key}: removed (was {fmt(fo[key])})')
            else:
                out.append(f'{name}.{key}: added ({fmt(fn[key])})')
    if not out:
        out = ['no differences']
    shown = out if a.all else out[:a.limit]
    print('\n'.join(shown))
    if len(shown) < len(out):
        print(f'+{len(out) - len(shown)} more (use --all)')
    if new.get('status') != 'passed' and old.get('status') == 'passed':
        regress = True
    return 1 if regress else 0


def find_fault_reports(root):
    root = Path(root)
    found = {}
    for p in sorted(root.rglob('report.json')):
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        # a fault run's report carries fault_fixture; gate sub-reports do not
        # (gate sub-reports may repeat fault_fixture but have no 'gates')
        if isinstance(d.get('gates'), dict) and (
                isinstance(d.get('fault_fixture'), dict) or str(d.get('status', '')).startswith('fault')):
            name = dget(d, 'fault_fixture', 'name') or p.parent.name
            if name not in found or len(p.parts) < len(found[name][0].parts):
                found[name] = (p, d)
    return found


def cmd_faults(a):
    found = find_fault_reports(a.dir)
    if not found:
        print(f'no fault reports under {a.dir}')
        return 1
    missed = 0
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fault_fixture import FAULTS
    except Exception:
        FAULTS = {}
    print(f'{"fault":<18} {"verdict":<9} {"failed-gates":<45} expected-gates')
    for name, (path, d) in sorted(found.items()):
        # derive from the gate rows: older reports have an empty failed_gates
        failed = [n for n, g in gates_of(d).items() if isinstance(g, dict) and g.get('status') == 'failed']
        if not failed and isinstance(d.get('failed_gates'), list):
            failed = d['failed_gates']
        spec = FAULTS.get(name) if isinstance(FAULTS, dict) else None
        expected = sorted(spec['gates']) if isinstance(spec, dict) and 'gates' in spec else None
        # a run that only ran the declared gates still records them as gates
        if expected is None:
            expected = sorted(gates_of(d)) or None
        status = d.get('status')
        if status == 'fault-detected':
            verdict = 'detected'
        elif status == 'fault-dead-code':
            verdict = 'dead-code'
        else:
            verdict = 'MISSED'
            missed += 1
        line = (f'{name:<18} {verdict:<9} {",".join(failed) or "-":<45} '
                f'{",".join(expected) if expected else "?"}')
        if verdict == 'MISSED':
            probs = d.get('fault_verdict')
            if isinstance(probs, list) and probs:
                line += '  | ' + ' '.join(str(probs[0]).split())[:ERR_WIDTH]
        print(line)
    return 1 if missed else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('summary')
    s.add_argument('report')
    s.set_defaults(fn=cmd_summary)
    d = sub.add_parser('diff')
    d.add_argument('baseline')
    d.add_argument('new')
    d.add_argument('--all', action='store_true', help='no line cap')
    d.add_argument('--limit', type=int, default=60)
    d.set_defaults(fn=cmd_diff)
    f = sub.add_parser('faults')
    f.add_argument('dir')
    f.set_defaults(fn=cmd_faults)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
