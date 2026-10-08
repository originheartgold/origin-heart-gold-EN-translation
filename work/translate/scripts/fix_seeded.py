#!/usr/bin/env python3
"""fix_seeded - mechanical fixes + QA gate for seeded (status "tm", origin us/tm_v3) strings.

Per string, in order:
  1. drop {COMPRESSED} when the zh has none (US trainer names are 9-bit packed; plain text works);
  2. remap {VAR:cmd:args} to the zh's form of the same command (the hack writes 1 arg, US/v3 2:
     {VAR:0101:0,0} -> {VAR:0101:0}); matched by command + first arg (buffer index), then by command;
  3. ASCII quotes/dashes -> ’ ‘ “ ” - (qa.normalize_punct) when the text has them;
  4. qa check; on line_too_wide / too_many_lines: reflow with qa.wrap (= `qa.py wrap --reflow`
     restricted to that id), re-check;
  5. strings that still have QA errors are reset to status "todo" (en null, origin null); the
     error codes and a pointer to the candidate are kept in notes ("seed rejected <origin> [...]
     (candidate US BBBB#N; text not kept)"); the candidate text itself only goes to --json.

Only touches entries with status "tm" and origin "us"/"tm_v3"; drafts/reviewed are never changed.
Usage: python3 work/translate/scripts/fix_seeded.py [--dry-run] [--ws ...] [--json report.json]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(WORK, 'tools'))
import qa  # noqa: E402
import textmetrics as tm  # noqa: E402
import ws as wsmod  # noqa: E402

VAR_RE = re.compile(r'\{VAR:([0-9A-F]{4})(?::([0-9,]*))?\}')
LAYOUT_ERRS = {'line_too_wide', 'too_many_lines'}
ORIGINS = {'us', 'tm_v3'}


def remap_vars(zh, en):
    zvars = [(m.group(1), m.group(2) or '', m.group(0)) for m in VAR_RE.finditer(zh)]
    zc = Counter(v[2] for v in zvars)
    ec = Counter(m.group(0) for m in VAR_RE.finditer(en))
    if zc == ec:
        return en
    pool = list(zvars)
    # exact tags consume their zh counterpart first
    exact_left = Counter(zc)
    out = []
    pending = []
    parts = VAR_RE.split(en)  # [text, cmd, args, text, cmd, args, ...]
    tags = [(parts[i], parts[i + 1] or '') for i in range(1, len(parts), 3)]
    resolved = [None] * len(tags)
    for k, (cmd, args) in enumerate(tags):
        full = '{VAR:%s%s}' % (cmd, (':' + args) if args else '')
        if exact_left[full] > 0:
            exact_left[full] -= 1
            resolved[k] = full
            pool.remove(next(v for v in pool if v[2] == full))
        else:
            pending.append(k)
    for k in pending:
        cmd, args = tags[k]
        first = args.split(',')[0] if args else ''
        cand = [v for v in pool if v[0] == cmd and (v[1].split(',')[0] if v[1] else '') == first]
        if not cand:
            cand = [v for v in pool if v[0] == cmd]
            if len({v[2] for v in cand}) > 1:
                cand = []
        if cand:
            resolved[k] = cand[0][2]
            pool.remove(cand[0])
        else:
            resolved[k] = '{VAR:%s%s}' % (cmd, (':' + args) if args else '')
    for i in range(0, len(parts), 3):
        out.append(parts[i])
        k = i // 3
        if k < len(resolved):
            out.append(resolved[k])
    return ''.join(out)


def mech_fix(zh, en):
    if '{COMPRESSED}' in en and '{COMPRESSED}' not in zh:
        en = en.replace('{COMPRESSED}', '')
    en = remap_vars(zh, en)
    # hack-specific end command {VAR:0207} (US ends these with {SCROLL} or nothing): copy the zh tail
    if zh.endswith('{VAR:0207}') and '{VAR:0207}' not in en:
        tail = re.search(r'(?:\{(?:NEWLINE|SCROLL|CLEAR|VAR:0207)\})+$', zh).group(0)
        en = re.sub(r'(?:\{(?:NEWLINE|SCROLL|CLEAR)\})+$', '', en) + tail
    # spaces next to line/page breaks (v3 lines often have 'word {NEWLINE}')
    en = re.sub(r' +(\{(?:NEWLINE|SCROLL|CLEAR)\})', r'\1', en)
    en = re.sub(r'(\{(?:NEWLINE|SCROLL|CLEAR)\}) +', r'\1', en)
    en = re.sub(r'(?<=[^\s}])  +(?=[^\s{])', ' ', en)
    en = re.sub(r'\bPokemon\b', 'Pokémon', en)
    en = re.sub(r'\bPokedex\b', 'Pokédex', en)
    if re.search(r"['\"—–]", tm.visible_text(en) if hasattr(tm, 'visible_text') else en):
        en = qa.normalize_punct(en)
    return en


def errors_for(bank, e, cfg, catname):
    one = dict(bank)
    one['strings'] = [e]
    one['category'] = catname      # the category is otherwise inferred from the whole bank's zh
    return [i for i in qa.check_bank(one, cfg, None, None, glossary=False) if i['level'] == 'error']


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ws', default=os.path.join(WORK, 'translate', 'banks'))
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--json', help='write the list of rejected strings here')
    a = ap.parse_args(argv)
    cfg = tm.load_config()
    fset = tm.font_set()
    c = Counter()
    rejected_by = Counter()
    rejected = []
    for p in sorted(Path(a.ws).rglob('[0-9]*.json')):
        b = wsmod.load_json(p)
        catname = qa.bank_category(b, cfg)
        changed = False
        # bank context (ui banks compare with the widest zh line) needs the whole bank: fine, per string
        for e in b['strings']:
            if e.get('status') != 'tm' or e.get('origin') not in ORIGINS or e.get('en') is None:
                continue
            c['checked'] += 1
            en0 = e['en']
            en = mech_fix(e['zh'], en0)
            if en != en0:
                c['mech_fixed'] += 1
                e['en'] = en
                changed = True
            errs = errors_for(b, e, cfg, catname)
            codes = {i['code'] for i in errs}
            if codes and codes <= LAYOUT_ERRS:
                cname = e.get('category') or catname
                new = qa.wrap(en, e['zh'], cname, 'auto', True, b['narc'], cfg, fset)
                if new != en:
                    old = e['en']
                    e['en'] = new
                    errs2 = errors_for(b, e, cfg, catname)
                    if errs2 and len(errs2) >= len(errs):
                        e['en'] = old
                    else:
                        c['rewrapped'] += 1
                        changed = True
                        errs = errs2
                codes = {i['code'] for i in errs}
            if errs:
                for code in sorted(codes):
                    rejected_by[code] += 1
                rejected.append({'narc': b['narc'], 'bank': b['bank'], 'id': e['id'], 'origin': e['origin'],
                                 'codes': sorted(codes), 'msgs': [i['msg'] for i in errs][:3],
                                 'zh': e['zh'], 'en': e['en']})
                # pointer only: never copy US / v3 text into notes (the --json report keeps it locally)
                m = re.search(r'\bUS (\d{4})/(\d+)', e.get('notes') or '')
                src = ('US %s#%s' % m.groups() if m else 'US text') if e['origin'] == 'us' else 'v3 TM text'
                note = 'seed rejected %s [%s] (candidate %s; text not kept)' % (
                    e['origin'], ','.join(sorted(codes)), src)
                e['notes'] = (e.get('notes') + ' | ' if e.get('notes') else '') + note
                e['en'] = None
                e['status'] = 'todo'
                e['origin'] = None
                c['reset_todo'] += 1
                c['reset_todo_' + rejected[-1]['origin']] += 1
                changed = True
        if changed and not a.dry_run:
            wsmod.save_json(p, b)
    print(json.dumps({'counts': c, 'rejected_by_code': rejected_by}, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(rejected, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
