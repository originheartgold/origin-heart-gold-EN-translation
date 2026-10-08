#!/usr/bin/env python3
"""Local-only translation review. Reads banks; feedback never edits translations.

Run from repository root: python3 work/tools/review_site/server.py
"""
import argparse
import difflib
import re
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlparse, parse_qs

WORK = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parent
BANKS = WORK/'translate/banks'
REVIEW = WORK/'build/qa-current-review/report.json'
STATE = WORK/'build/text-review/feedback.json'
VERDICTS = {'needs-fix', 'accept-proposal', 'keep-current', 'false-positive', 'question', 'unreviewed'}


def word_diff(before, after):
    """Lossless token diff; game controls are indivisible tokens."""
    tokenize = lambda value: re.findall(r'\{[^}]*\}|\w+|\s+|[^\w\s]', value or '')
    a, b = tokenize(before), tokenize(after)
    old, new = [], []
    for op, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if i != j: old.append({'text': ''.join(a[i:j]), 'changed': op != 'equal'})
        if k != l: new.append({'text': ''.join(b[k:l]), 'changed': op != 'equal'})
    return {'before': old, 'after': new}


def read_json(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).is_file() else default


def fingerprint(zh, en):
    return hashlib.sha256(json.dumps([zh, en], ensure_ascii=False).encode()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


class ReviewStore:
    def __init__(self, banks=BANKS, report_path=REVIEW, state_path=STATE):
        self.banks, self.report_path, self.state_path = Path(banks), Path(report_path), Path(state_path)
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.feedback = read_json(self.state_path, {'schema': 1, 'items': {}, 'history': []})
        if not isinstance(self.feedback, dict) or self.feedback.get('schema') != 1 or not isinstance(self.feedback.get('items'), dict) or not isinstance(self.feedback.get('history'), list):
            raise ValueError('Invalid feedback store; refusing to overwrite it')
        self.load()

    def load(self):
        with self.lock:
            report = read_json(self.report_path, {})
            self.items, self.bank_cache = {}, {}
            categories = read_json(WORK/'tools/qa_config.json', {}).get('banks', {})
            for path in sorted(self.banks.glob('*/[0-9][0-9][0-9][0-9].json')):
                bank = read_json(path)
                key = f'{path.parent.name}/{path.stem}'
                self.bank_cache[key] = bank
                for entry in bank['strings']:
                    ref = f'{key}#{entry["id"]}'
                    zh, en = entry.get('zh', ''), entry.get('en')
                    self.items[ref] = {'ref': ref, 'bank': key, 'id': entry['id'], 'zh': zh, 'en': en,
                        'fingerprint': fingerprint(zh, en), 'category': entry.get('category', bank.get('category', categories.get(key, ''))) ,
                        'notes': entry.get('notes', ''), 'findings': [], 'warnings': [], 'proposal': None,
                        'priority': False, 'kind': 'text', 'confidence': None}
            def attach(ref, title, detail, kind='fidelity', priority=True, proposal=None, confidence='high'):
                item = self.items.get(ref)
                if item is None:
                    return
                finding = {'title': title, 'detail': detail, 'kind': kind, 'confidence': confidence}
                if finding not in item['findings']:
                    item['findings'].append(finding)
                item['priority'] |= priority
                if item['kind'] == 'text' or kind == 'overflow':
                    item['kind'] = kind
                if proposal:
                    item['proposal'] = proposal
                item['confidence'] = confidence
            for row in report.get('description_fix_candidates', []):
                current_units = None
                try:
                    import sys
                    sys.path.insert(0, str(WORK/'tools'))
                    import msgtool
                    current_units = len(msgtool.encode_text(self.items[row['ref']]['en'], msgtool.Charmap.load([WORK/'tools/charmap_en.tsv'])))
                except (KeyError, ValueError, TypeError):
                    pass
                self.items[row['ref']]['official_reference'] = row.get('official_reference')
                self.items[row['ref']]['official_note'] = row.get('official_note')
                sid = int(row['ref'].split('#')[1])
                names = self.bank_cache.get('a027/0219', {}).get('strings', [])
                name = next((e.get('en') for e in names if e['id'] == sid), None)
                attach(row['ref'], f'{name or row["ref"]}: description overflow',
                    f'At the audit: limit {row["capacity_units"]} encoded units including the terminator. Current text: {current_units if current_units is not None else "unmeasured"} units. Proposed text: {row["stored_units"]} units.' +
                    (' ' + row['minimal_change'] if row.get('minimal_change') else '') +
                    (' ' + ' '.join(row.get('fidelity_notes', []))) +
                    (' Stable Mulch wording still needs source-ambiguity review.' if row.get('requires_source_review') else ''),
                    kind='overflow', proposal=row.get('proposed'))
                self.items[row['ref']]['capacity'] = {'limit': row['capacity_units'], 'current': current_units, 'proposed': row['stored_units']}
            titles = {
                'a027/0038#73': '“Third” became a quantity', 'a027/0106#57': 'Single Battle changed to Multi Battle',
                'a027/0116#8': 'The Machoke replacement proposal is missing', 'a027/0137#12': 'Three-Pokémon count is missing',
                'a027/0144#11': 'Three-circle count is missing', 'a027/0144#12': 'Three-circle count is missing',
                'a027/0367#1': 'Route 29 comparison is missing', 'a027/0563#60': 'Critical-hit stage increase is missing',
                'a027/0302#224': 'Three-Pokémon instruction is incomplete'}
            for row in report.get('fidelity_findings', []):
                state = row.get('status')
                priority = state in ('confirmed_omission', 'source_contradiction_translation_changed')
                kind = 'fidelity' if priority else 'review' if state != 'false_positive' else 'false-positive'
                title = titles.get(row['ref'], 'One-stage stat change is missing' if row['ref'].startswith('a027/0189#') else 'Contextual UI review' if kind == 'review' else 'Reviewed false positive')
                attach(row['ref'], title, row.get('action', ''), kind, priority, row.get('proposed_en'), row.get('confidence', 'medium'))
            for row in report.get('additional_findings', []):
                attach(row['ref'], row['issue'], row.get('correction_constraint', ''), 'fidelity', row.get('confidence') == 'high', confidence=row.get('confidence'))
            row = report.get('gender_finding')
            if row:
                attach(row['ref'], 'Player is referred to as “him”', row['issue'])
            for row in report.get('choice_and_gender_proposals', []):
                if row['ref'] in self.items:
                    self.items[row['ref']]['proposal'] = row.get('proposed')
            for row in report.get('open_reassessment', {}).get('items', []):
                item = self.items.get(row['ref'])
                if item is None: continue
                fresh = row.get('fingerprint') == item['fingerprint']
                item['findings'].append({'title': 'Reassessment', 'detail': row['reassessment'] if fresh else 'Text has changed since reassessment; the older recommendation needs checking.'})
                if fresh and 'proposed' in row: item['proposal'] = row['proposed']
            self.summary = report.get('summary', {})
            self.scope = report.get('scope', 'Automated findings; not a complete manual translation review.')
            self.gate_findings = report.get('open_nontext_gate_findings', [])
            # Report paths originate in the local audit; constrain them to ignored build output.
            qa_path = (WORK.parent/report.get('qa_report', '')).resolve()
            if not qa_path.is_relative_to((WORK/'build').resolve()):
                raise ValueError('QA report must be under work/build')
            qa = read_json(qa_path, {'issues': []})
            for warning in qa.get('issues', []):
                ref = f'{warning["narc"]}/{warning["bank"]:04d}#{warning["id"]}'
                if ref in self.items:
                    self.items[ref]['warnings'].append(warning)
            # Static control differences were separate from ordinary, suppressible QA warnings.
            static_path = (WORK.parent/report.get('static_report', '')).resolve()
            if static_path.is_relative_to((WORK/'build').resolve()):
                static = read_json(static_path, {})
                ledger_name = static.get('checks', {}).get('safety', {}).get('ledger')
                if ledger_name and Path(ledger_name).resolve().is_relative_to((WORK/'build').resolve()):
                    for row in read_json(ledger_name, {}).get('records', []):
                        details = row.get('workspace', {}).get('control_details') or {}
                        if details.get('status') == 'failed':
                            codes = ', '.join(x.get('code', '') for x in details.get('findings', []))
                            attach(row['ref'], 'Source control sequence differs', codes + '. These include deliberately blanked entries and a documented size reset; a contract failure is not automatically a confirmed game bug.', 'controls', False, confidence='review')
            # Flag evidence/proposals tied to an older translation instead of presenting it as current.
            audited = {}
            for row in report.get('description_fix_candidates', []): audited[row['ref']] = (row.get('source'), row.get('current'))
            for row in report.get('fidelity_findings', []): audited[row['ref']] = (row.get('zh'), row.get('en'))
            for row in report.get('additional_findings', []): audited[row['ref']] = (row.get('zh'), row.get('en'))
            for ref, item in self.items.items():
                item['audit_stale'] = ref in audited and audited[ref] != (item['zh'], item['en'])
                item['search'] = '\n'.join([ref, item['zh'] or '', item['en'] or '', item['proposal'] or '', item['notes'] or '', *[f['title'] for f in item['findings']]]).casefold()
            self.loaded_at = utc()
            self.ordered = sorted(self.items, key=lambda r: (not self.items[r]['priority'], self.items[r]['kind'] != 'overflow', self.items[r]['bank'], self.items[r]['id']))
            self.audit_date = qa_path.parent.name.split('.')[0]
            try:
                self.audit_date = datetime.strptime(self.audit_date.rstrip('Z'), '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass

    def feedback_for(self, ref):
        feedback = self.feedback['items'].get(ref)
        if not feedback: return None
        return dict(feedback, stale=feedback.get('fingerprint') != self.items[ref]['fingerprint'] or feedback.get('proposal') != self.items[ref]['proposal'])

    def meta(self):
        with self.lock:
            return {'token': self.token, 'total': len(self.items), 'priority': sum(x['priority'] for x in self.items.values()),
                    'warning_strings': sum(bool(x['warnings']) for x in self.items.values()),
                    'warning_count': sum(len(x['warnings']) for x in self.items.values()),
                    'reviewed': sum(self.feedback_for(r) is not None and not self.feedback_for(r)['stale'] and self.feedback_for(r)['verdict'] != 'unreviewed' for r in self.items),
                    'summary': self.summary, 'scope': self.scope, 'gate_findings': self.gate_findings,
                    'loaded_at': self.loaded_at, 'audit_date': self.audit_date}

    def query(self, query):
        with self.lock:
            get = lambda k, default='': query.get(k, [default])[0]
            q, view, verdict, kind = get('q').casefold(), get('view', 'priority'), get('verdict'), get('kind')
            offset = max(0, int(get('offset', '0')))
            result = []
            for ref in self.ordered:
                item, f = self.items[ref], self.feedback_for(ref)
                if view == 'priority' and not item['priority']: continue
                if view == 'warnings' and not item['warnings']: continue
                if view == 'findings' and not item['findings']: continue
                if view == 'feedback' and not f: continue
                if q and q not in item['search']: continue
                if kind and kind != item['kind']: continue
                status = 'stale' if f and f['stale'] else f['verdict'] if f else 'unreviewed'
                if verdict == 'open' and status in ('accept-proposal', 'keep-current', 'false-positive'): continue
                if verdict and verdict != 'open' and status != verdict: continue
                result.append(ref)
            rows = []
            for ref in result[offset:offset+40]:
                item = self.items[ref]
                rows.append({k:item[k] for k in ('ref','en','priority','kind','confidence','audit_stale') } |
                            {'title': item['findings'][0]['title'] if item['findings'] else item['warnings'][0]['msg'] if item['warnings'] else 'Text entry',
                             'warning_count': len(item['warnings']), 'feedback': self.feedback_for(ref)})
            return {'items': rows, 'total': len(result), 'offset': offset}

    def detail(self, ref):
        with self.lock:
            item = {k:v for k,v in self.items[ref].items() if k != 'search'}
            entries = self.bank_cache[item['bank']]['strings']
            index = next(i for i,e in enumerate(entries) if e['id'] == item['id'])
            item['context'] = [{'ref': f'{item["bank"]}#{e["id"]}', 'zh':e.get('zh'), 'en':e.get('en')} for e in entries[max(0,index-2):index+3] if e['id'] != item['id']]
            item['feedback'] = self.feedback_for(ref)
            item['diff'] = word_diff(item['en'], item['proposal']) if item['proposal'] is not None else None
            return item

    def save(self, payload):
        with self.lock:
            ref = payload.get('ref')
            if ref not in self.items: raise ValueError('Unknown text reference')
            item = self.items[ref]
            if payload.get('fingerprint') != item['fingerprint']: raise RuntimeError('Text changed. Reload this entry before submitting.')
            current = read_json(self.banks/(item['bank']+'.json'))
            entry = next(e for e in current['strings'] if e['id'] == item['id'])
            if fingerprint(entry.get('zh',''),entry.get('en')) != item['fingerprint']:
                raise RuntimeError('The bank changed on disk. Refresh the review before submitting.')
            verdict = payload.get('verdict')
            if verdict not in VERDICTS: raise ValueError('Choose a valid review decision')
            comment, suggestion = payload.get('comment', ''), payload.get('suggestion', '')
            if not all(isinstance(s,str) and len(s) <= 20000 for s in (comment,suggestion)): raise ValueError('Feedback must be text under 20,000 characters')
            if verdict == 'question' and not comment.strip() and not suggestion.strip(): raise ValueError('Add a comment or suggested wording before submitting a question')
            if verdict == 'accept-proposal' and not item['proposal']: raise ValueError('This entry has no proposal to accept')
            if verdict == 'accept-proposal' and payload.get('proposal') != item['proposal']: raise RuntimeError('Proposal changed. Reload this entry before accepting it.')
            old = self.feedback['items'].get(ref)
            if payload.get('revision', 0) != (old or {}).get('revision',0): raise RuntimeError('Feedback changed in another tab. Reload before submitting.')
            saved = {'ref':ref, 'fingerprint':item['fingerprint'], 'verdict':verdict, 'comment':comment, 'suggestion':suggestion,
                     'proposal':item['proposal'], 'updated_at':utc(), 'revision':(old or {}).get('revision',0)+1}
            state = json.loads(json.dumps(self.feedback))
            state['items'][ref] = saved
            state['history'].append(saved)
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.state_path.with_suffix('.tmp')
            temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            temp.replace(self.state_path)
            self.feedback = state
            return saved


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, status, data, content_type='application/json; charset=utf-8', attachment=False):
        content = json.dumps(data,ensure_ascii=False).encode() if content_type.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if attachment: self.send_header('Content-Disposition','attachment; filename="translation-feedback.json"')
        self.end_headers(); self.wfile.write(content)
    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def do_GET(self):
        if not self.valid_host(): return self.send(403,{'error':'Local access only'})
        p=urlparse(self.path);q=parse_qs(p.query);store=self.server.store
        try:
            if p.path=='/api/meta': return self.send(200,store.meta())
            if p.path=='/api/items': return self.send(200,store.query(q))
            if p.path=='/api/item': return self.send(200,store.detail(q.get('ref',[''])[0]))
            if p.path=='/api/export':
                with store.lock: return self.send(200,dict(store.feedback,exported_at=utc()),attachment=True)
            assets={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}
            if p.path not in assets: return self.send(404,{'error':'Not found'})
            kind={'index.html':'text/html','app.js':'text/javascript','style.css':'text/css','favicon.svg':'image/svg+xml'}[assets[p.path]]
            self.send(200,(ASSETS/assets[p.path]).read_bytes(),kind+'; charset=utf-8')
        except KeyError: self.send(404,{'error':'Text entry not found'})
        except ValueError as e: self.send(400,{'error':str(e)})
    def do_POST(self):
        store=self.server.store
        if not self.valid_host() or self.headers.get('X-Review-Token')!=store.token:
            return self.send(403,{'error':'Reload the local review page before saving'})
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
            return self.send(403,{'error':'Cross-origin feedback is not allowed'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 100000: raise ValueError('Invalid feedback size')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('Expected a feedback object')
            if self.path=='/api/feedback': return self.send(200,store.save(data))
            if self.path=='/api/refresh': store.load();return self.send(200,store.meta())
            self.send(404,{'error':'Not found'})
        except RuntimeError as e: self.send(409,{'error':str(e)})
        except (ValueError,TypeError) as e: self.send(400,{'error':str(e)})
        except OSError: self.send(500,{'error':'Feedback could not be written. Your draft is still in the form; retry saving.'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--state',type=Path,default=STATE)
    args=parser.parse_args()
    if not args.state.resolve().is_relative_to((WORK/'build').resolve()): parser.error('Feedback must remain under ignored work/build')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.store=ReviewStore(state_path=args.state)
    print(f'Text review: http://127.0.0.1:{server.server_port}',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
