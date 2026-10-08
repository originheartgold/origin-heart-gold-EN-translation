#!/usr/bin/env python3
"""Lossless local text catalogue and Mandarin annotation workspace. No network access.

Run from the repository root. See work/translate/text_catalog/README.md.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unicodedata
import zlib

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'work/translate/text_catalog'
DEFAULT_DB = ROOT / 'work/build/text_catalog/catalog.sqlite3'
TAG = re.compile(r'\{[^{}]*\}')
LAYOUT = {'{NEWLINE}', '{CLEAR}', '{SCROLL}'}
REDACTED = re.compile(r'^\[zh redacted: song lyrics; sha256:[0-9a-f]{64}\]$')
CEDICT = re.compile(r'^(\S+) (\S+) \[([^\[\]]+)\] /(.+)/$')
SYLLABLE = re.compile(r'([A-Za-züÜvV:]+)([0-5])')


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def pack_analysis(value):
    # Dictionary alternatives are shared in readings/senses, never copied per occurrence.
    value = dict(value)
    value['tokens'] = [{k: v for k, v in token.items() if k not in ('reading_ids', 'pinyin_candidates')}
                       for token in value['tokens']]
    if value.get('pinyin_display') == value.get('pinyin'):
        value.pop('pinyin_display', None)
    return zlib.compress(packed(value).encode('utf-8'))


def unpack_analysis(value):
    result = json.loads(zlib.decompress(value))
    result.setdefault('pinyin_display', result.get('pinyin'))
    return result


def digest(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def hanzi(char):
    return (0x3400 <= ord(char) <= 0x9FFF or 0xF900 <= ord(char) <= 0xFAFF
            or 0x20000 <= ord(char) <= 0x323AF or char == '〇')


def tone_marks(numbered):
    """Render dictionary citation tones; do not apply spoken tone sandhi."""
    def convert(match):
        base = match[1].replace('u:', 'ü').replace('U:', 'Ü').replace('v', 'ü').replace('V', 'Ü')
        tone = int(match[2])
        if tone in (0, 5):
            return base
        lower = base.lower()
        vowels = [i for i, char in enumerate(lower) if char in 'aeiouü']
        if 'a' in lower:
            index = lower.index('a')
        elif 'e' in lower:
            index = lower.index('e')
        elif 'ou' in lower:
            index = lower.index('o')
        elif vowels:
            index = vowels[-1]
        else:
            index = next((i for i, c in enumerate(lower) if c in 'mn'), None)
        if index is None:
            return match[0]
        return unicodedata.normalize('NFC', base[:index+1] + '\u0304\u0301\u030c\u0300'[tone-1] + base[index+1:])
    return SYLLABLE.sub(convert, numbered)


class Lexicon:
    def __init__(self):
        self.readings = {}
        self.by_form = collections.defaultdict(list)
        self.terms = collections.defaultdict(list)
        self.max_length = 1

    def add_reading(self, traditional, simplified, numbered, senses, source='cc-cedict'):
        # Content-derived IDs survive reordering and imports of the same dictionary.
        rid = digest(packed([source, traditional, simplified, numbered, senses]))
        if rid in self.readings:
            return
        value = dict(id=rid, traditional=traditional, simplified=simplified,
                     pinyin_numbered=numbered, pinyin=tone_marks(numbered), source=source,
                     senses=[dict(id=digest(packed([rid, i, gloss])), gloss=gloss)
                             for i, gloss in enumerate(senses)])
        self.readings[rid] = value
        for form in {traditional, simplified}:
            self.by_form[form].append(rid)
            self.max_length = max(self.max_length, len(form))

    def import_cedict(self, path):
        opener = gzip.open if path.suffix == '.gz' else open
        headers = []
        with opener(path, 'rt', encoding='utf-8-sig') as stream:
            for line_number, line in enumerate(stream, 1):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    headers.append(line)
                    continue
                match = CEDICT.fullmatch(line)
                if not match:
                    raise ValueError(f'{path}:{line_number}: expected CC-CEDICT v1 export')
                traditional, simplified, numbered, definitions = match.groups()
                # Preserve each slash-delimited sense group and its semicolon glosses verbatim.
                self.add_reading(traditional, simplified, numbered, definitions.split('/'))
        return dict(name='CC-CEDICT', path=str(path), sha256=digest(path.read_bytes()),
                    url='https://www.mdbg.net/chinese/dictionary?page=cc-cedict',
                    headers=headers)

    def add_term(self, term):
        self.terms[term['zh']].append(term)
        self.max_length = max(self.max_length, len(term['zh']))

    def candidates(self, form):
        return [self.readings[rid] for rid in self.by_form.get(form, [])]

    def segment(self, text):
        """Deterministic longest dictionary/project match; always an unreviewed suggestion."""
        index = 0
        while index < len(text):
            end = index + 1
            if hanzi(text[index]):
                limit = index
                while limit < len(text) and hanzi(text[limit]) and limit-index < self.max_length:
                    limit += 1
                for candidate_end in range(limit, index, -1):
                    form = text[index:candidate_end]
                    if form in self.by_form or form in self.terms:
                        end = candidate_end
                        break
            else:
                while end < len(text) and not hanzi(text[end]):
                    end += 1
            yield index, end, text[index:end]
            index = end

    def pronunciation(self, form):
        choices = sorted({x['pinyin'] for x in self.candidates(form)})
        if choices:
            return choices
        if len(form) > 1 and all(hanzi(c) for c in form):
            # Only infer a compound reading when EVERY character has one unique reading.
            syllables = [sorted({x['pinyin'] for x in self.candidates(c)}) for c in form]
            if all(len(s) == 1 for s in syllables):
                return [' '.join(s[0] for s in syllables)]
        return []


class Pronunciation:
    """Optional local pypinyin package. Predictions never choose a dictionary sense."""
    def __init__(self, path):
        sys.path.insert(0, str(path.resolve()))
        import pypinyin
        self.module = pypinyin
        self.characters = {}
        self.metadata = dict(name='pypinyin', version=pypinyin.__version__, license='MIT',
                             url='https://github.com/mozillazg/python-pinyin',
                             tone_sandhi=False, status='automatic-unreviewed')

    def predict(self, text, offsets):
        values = self.module.lazy_pinyin(text, style=self.module.Style.TONE,
                                         errors=lambda value: list(value), tone_sandhi=False)
        if len(values) != len(text):
            return []  # Never manufacture an alignment if the provider changes its contract.
        result = []
        for index, (character, value) in enumerate(zip(text, values)):
            if not hanzi(character):
                continue
            if character not in self.characters:
                options = self.module.pinyin(character, style=self.module.Style.TONE,
                                             heteronym=True, errors=lambda value: list(value))
                self.characters[character] = [p for p in options[0] if p != character] if options else []
            result.append(dict(position=offsets[index], pinyin=value if value != character else None))
        return result


def render_pinyin(zh, syllables):
    """Keep original tags and punctuation, inserting spaces between romanized syllables."""
    replacements = {s['position']: s['pinyin'] or '[' + zh[s['position']] + ': ?]' for s in syllables}
    pieces, index = [], 0
    while index < len(zh):
        match = TAG.match(zh, index)
        if match:
            pieces.append(match[0])
            index = match.end()
        elif index in replacements:
            pieces.append(replacements[index])
            index += 1
        else:
            end = index + 1
            while end < len(zh) and end not in replacements and not TAG.match(zh, end):
                end += 1
            pieces.append(zh[index:end])
            index = end
    return ' '.join(pieces)


def project_text(zh):
    """Remove layout tags for segmentation; preserve exact original offset mapping.

    Dynamic variables/control tags are barriers so words cannot span a variable.
    """
    text, offsets, tags = [], [], []
    index = 0
    while index < len(zh):
        match = TAG.match(zh, index)
        if match:
            tags.append(dict(start=index, end=match.end(), text=match[0],
                             kind='layout' if match[0] in LAYOUT else 'control'))
            if match[0] not in LAYOUT:
                text.append('\ufffc')
                offsets.append(index)
            index = match.end()
        else:
            text.append(zh[index])
            offsets.append(index)
            index += 1
    return ''.join(text), offsets, tags


def analyse(zh, language, lexicon, pronunciation=None):
    if REDACTED.fullmatch(zh):
        return dict(state='redacted', pinyin=None, tokens=[], tags=[])
    if language != 'Mandarin':
        return dict(state='not-mandarin', pinyin=None, tokens=[], tags=[])
    visible, offsets, tags = project_text(zh)
    tokens, rendered = [], []
    complete = True
    for start, end, form in lexicon.segment(visible):
        if not any(hanzi(c) for c in form):
            rendered.append(form)
            continue
        readings = lexicon.pronunciation(form)
        positions = offsets[start:end]
        tokens.append(dict(text=form, positions=positions, reading_ids=lexicon.by_form.get(form, []),
                           pinyin_candidates=readings,
                           method='dictionary' if lexicon.by_form.get(form) else 'characters',
                           state='suggested' if len(readings) == 1 else 'ambiguous' if readings else 'missing'))
        complete &= len(readings) == 1
        rendered.append(readings[0] if len(readings) == 1 else
                        '[' + ' | '.join(readings) + ']' if readings else '[' + form + ': ?]')
    result = dict(state='automatic' if tokens else 'no-hanzi',
                pinyin=' '.join(rendered) if complete and tokens else None,
                pinyin_display=' '.join(rendered), tokens=tokens, tags=tags,
                method='longest-match-v1; citation tones; unreviewed')
    if pronunciation and tokens:
        syllables = pronunciation.predict(visible, offsets)
        result['dictionary_pinyin'] = result['pinyin']
        result['syllables'] = syllables
        result['pinyin'] = render_pinyin(zh, syllables) if syllables and all(s['pinyin'] for s in syllables) else None
        result['pinyin_display'] = render_pinyin(zh, syllables) if syllables else None
        result['pinyin_method'] = 'pypinyin-' + pronunciation.module.__version__ + '; tone_sandhi=False; phrase data; unreviewed'
        by_position = {s['position']: s['pinyin'] for s in syllables}
        for token in tokens:
            values = [by_position.get(p) for p in token['positions']]
            token['suggested_pinyin'] = ' '.join(values) if all(values) else None
            token['reading_conflict'] = bool(token['pinyin_candidates'] and token['suggested_pinyin'] and
                                             token['suggested_pinyin'].lower() not in {p.lower() for p in token['pinyin_candidates']})
    return result


def load_terms(root, lexicon):
    for path in sorted((root / 'work/glossary').glob('*.json')):
        for zh, value in read_json(path, {}).items():
            if isinstance(value, dict) and isinstance(value.get('en'), str):
                term = dict(id=f'{path.name}:{zh}', zh=zh, en=value['en'], scope='global',
                            provenance=str(path.relative_to(root)), payload=value)
                lexicon.add_term(term)
    decisions = root / 'work/translate/decisions/decisions.jsonl'
    if decisions.exists():
        for line in decisions.read_text(encoding='utf-8').splitlines():
            decision = json.loads(line)
            if (decision.get('type') != 'term' or decision.get('status') == 'superseded'
                    or not decision.get('zh') or not decision.get('en')):
                continue
            for zh in dict.fromkeys([decision['zh']] + decision.get('aliases', [])):
                lexicon.add_term(dict(id=f"{decision['id']}:{zh}", zh=zh, en=decision['en'],
                                     scope=decision.get('scope', 'global'),
                                     provenance=decision['id'], payload=decision))


def connect(path):
    db = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def load_annotations(path):
    rows = []
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    refs = [row['ref'] for row in rows]
    if len(set(refs)) != len(refs):
        raise ValueError('duplicate annotation refs')
    return rows


def validate_annotation(annotation, zh, lexicon):
    if REDACTED.fullmatch(zh):
        raise ValueError('redacted lyrics cannot be annotated')
    occupied = set()
    for token in annotation.get('tokens', []):
        start, end = token['start'], token['end']
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(zh)):
            raise ValueError('invalid annotation span')
        positions = set(range(start, end))
        if occupied & positions:
            raise ValueError('overlapping annotation spans')
        occupied |= positions
        form = zh[start:end]
        if TAG.search(form):
            raise ValueError('review spans cannot contain control/layout tags')
        rid = token.get('reading_id')
        sid = token.get('sense_id')
        if rid:
            reading = lexicon.readings.get(rid)
            if not reading or form not in (reading['traditional'], reading['simplified']):
                raise ValueError('reading does not belong to this span')
            if sid and sid not in {s['id'] for s in reading['senses']}:
                raise ValueError('sense does not belong to the selected reading')
        elif sid:
            raise ValueError('a sense requires a reading')
        if not rid and not token.get('pinyin') and not token.get('note'):
            raise ValueError('annotation needs a reading, custom pinyin, or a note')


def build(root, destination, cedict=None, annotations=None, pypinyin_path=None):
    root, destination = Path(root), Path(destination)
    lexicon = Lexicon()
    dictionary = lexicon.import_cedict(cedict) if cedict else None
    pronunciation = Pronunciation(pypinyin_path) if pypinyin_path else None
    load_terms(root, lexicon)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.catalog-', suffix='.sqlite3', dir=destination.parent)
    os.close(fd)
    db = sqlite3.connect(temporary)
    try:
        db.executescript((CONFIG / 'schema.sql').read_text())
        if dictionary:
            db.execute('INSERT INTO dictionary_sources VALUES (?,?)', ('cc-cedict', packed(dictionary)))
        for reading in lexicon.readings.values():
            db.execute('INSERT INTO readings VALUES (?,?,?,?,?,?)',
                       (reading['id'], reading['simplified'], reading['traditional'], reading['pinyin_numbered'], reading['pinyin'], reading['source']))
            db.executemany('INSERT INTO senses VALUES (?,?,?,?)',
                           [(s['id'], reading['id'], i, s['gloss']) for i, s in enumerate(reading['senses'])])
        for terms in lexicon.terms.values():
            for term in terms:
                db.execute('INSERT INTO terms VALUES (?,?,?,?,?,?)',
                           (term['id'], term['zh'], term['en'], packed(term['scope']), term['provenance'], packed(term['payload'])))
        maps = read_json(root / 'work/translate/bank_maps.json', {})
        manifest = read_json(root / 'work/translate/manifest_playorder.json', {})
        passthrough = read_json(root / 'work/tools/qa_config.json', {}).get('passthrough_banks', {})
        batches = collections.defaultdict(list)
        for batch in manifest.get('batches', []):
            for part in batch['parts']:
                batches[part['bank']].append(dict(batch=batch['batch'], label=batch['label'], ids=part['ids']))
        paths = sorted((root / 'work/translate/banks').glob('*/*.json'))
        hardcoded = root / 'work/translate/hardcoded/strings.json'
        if hardcoded.exists():
            paths.append(hardcoded)
        source_ids, counter, chars = {}, collections.Counter(), collections.Counter()
        for path in paths:
            relative = str(path.relative_to(root))
            raw = path.read_bytes()
            data = json.loads(raw)
            is_bank = path != hardcoded
            bank = f"{data['narc']}/{data['bank']:04d}" if is_bank else 'hardcoded'
            file_context = dict(maps=maps.get(f"{data['bank']:04d}", []) if is_bank and data['narc'] == 'a027' else [],
                                bank_metadata={k: v for k, v in data.items() if k != 'strings'})
            db.execute('INSERT INTO files VALUES (?,?,?,?)', (relative, digest(raw), raw, packed(file_context)))
            for ordinal, entry in enumerate(data['strings']):
                ref = f"{bank}#{entry['id']}"
                zh = entry['zh']
                language = passthrough.get(bank, 'Mandarin')
                # Kana-containing leftovers are not automatically read as Mandarin.
                if language == 'Mandarin' and re.search(r'[\u3041-\u3096\u30a1-\u30fa\uff66-\uff6f\uff71-\uff9d]', TAG.sub('', zh)):
                    language = 'mixed-or-Japanese'
                key = (digest(zh), language)
                if key not in source_ids:
                    analysis = analyse(zh, language, lexicon, pronunciation)
                    cursor = db.execute('INSERT INTO sources(sha256,language,zh,analysis) VALUES (?,?,?,?)',
                                        (*key, zh, pack_analysis(analysis)))
                    source_ids[key] = (cursor.lastrowid, analysis.get('pinyin'))
                    counter['unique_sources'] += 1
                    counter['source_state:' + analysis['state']] += 1
                    if analysis.get('pinyin'):
                        counter['sources_with_complete_pinyin'] += 1
                    for token in analysis['tokens']:
                        counter['token_state:' + token['state']] += 1
                        counter['pronunciation_conflicts'] += bool(token.get('reading_conflict'))
                        chars.update(token['text'])
                source_id, pinyin = source_ids[key]
                context = dict(batches=[b for b in batches[bank] if b['ids'][0] <= entry['id'] <= b['ids'][1]] if is_bank else [])
                db.execute('INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)',
                           (ref, relative, ordinal, source_id, entry.get('en'), entry.get('status'),
                            entry.get('origin'), packed(entry), packed(context)))
                db.execute('INSERT INTO search VALUES (?,?,?)', (ref, entry.get('en'), pinyin))
                counter['entries'] += 1
            counter['files'] += 1
        if pronunciation:
            db.execute('INSERT INTO dictionary_sources VALUES (?,?)', ('pypinyin', packed(pronunciation.metadata)))
            db.executemany('INSERT INTO character_pronunciations VALUES (?,?,?)',
                           [(c, packed(p), 'pypinyin') for c, p in pronunciation.characters.items()])
            counter['hanzi_with_pronunciation'] = sum(bool(p) for p in pronunciation.characters.values())
        for annotation in load_annotations(annotations or root / 'work/translate/text_catalog/annotations.jsonl'):
            row = db.execute('SELECT s.sha256,s.zh FROM entries e JOIN sources s ON s.id=e.source_id WHERE e.ref=?', (annotation['ref'],)).fetchone()
            if not row:
                raise ValueError(f"annotation ref is missing: {annotation['ref']}")
            state = 'current' if annotation['source_sha256'] == row[0] else 'stale'
            if state == 'current':
                validate_annotation(annotation, row[1], lexicon)
            db.execute('INSERT INTO annotations VALUES (?,?,?,?)',
                       (annotation['ref'], annotation['source_sha256'], state, packed(annotation)))
            counter['annotations:' + state] += 1
        counter['distinct_hanzi'] = len(chars)
        counter['hanzi_with_dictionary'] = sum(bool(lexicon.by_form.get(c)) for c in chars)
        counter['dictionary_readings'] = len(lexicon.readings)
        db.execute('INSERT INTO metadata VALUES (?,?)', ('schema_version', '1'))
        db.execute('INSERT INTO metadata VALUES (?,?)', ('stats', packed(counter)))
        db.execute('INSERT INTO metadata VALUES (?,?)', ('missing_characters', packed([c for c, _ in chars.most_common() if not lexicon.by_form.get(c)])))
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('catalogue integrity check failed')
        db.close()
        os.replace(temporary, destination)
        return dict(counter)
    finally:
        db.close()
        if os.path.exists(temporary):
            os.unlink(temporary)


def dictionary_matches(db, form):
    matches = []
    for row in db.execute('SELECT * FROM readings WHERE simplified=? OR traditional=? ORDER BY id', (form, form)):
        reading = dict(row)
        reading['senses'] = [dict(s) for s in db.execute('SELECT id,gloss FROM senses WHERE reading_id=? ORDER BY ordinal', (row['id'],))]
        matches.append(reading)
    return matches


def inspect(db, ref):
    row = db.execute('SELECT e.*,s.zh,s.sha256,s.language,s.analysis FROM entries e JOIN sources s ON s.id=e.source_id WHERE ref=?', (ref,)).fetchone()
    if row is None:
        raise ValueError(f'unknown text reference: {ref}')
    analysis = unpack_analysis(row['analysis'])
    words, characters = [], []
    syllables = {s['position']: s['pinyin'] for s in analysis.get('syllables', [])}
    for token in analysis['tokens']:
        token = dict(token)
        token['readings'] = dictionary_matches(db, token['text'])
        token['reading_ids'] = [r['id'] for r in token['readings']]
        choices = sorted({r['pinyin'] for r in token['readings']})
        if not choices and len(token['text']) > 1:
            syllable_choices = [sorted({r['pinyin'] for r in dictionary_matches(db, c)}) for c in token['text']]
            if all(len(s) == 1 for s in syllable_choices):
                choices = [' '.join(s[0] for s in syllable_choices)]
        token['pinyin_candidates'] = choices
        token['project_terms'] = []
        for term in db.execute('SELECT * FROM terms WHERE zh=?', (token['text'],)):
            scope = json.loads(term['scope'])
            if scope == 'global' or ref.split('#')[0] in scope:
                token['project_terms'].append(dict(term))
        words.append(token)
        for position in token['positions']:
            character = row['zh'][position]
            pronunciation = db.execute('SELECT candidates FROM character_pronunciations WHERE character=?', (character,)).fetchone()
            characters.append(dict(position=position, text=character, readings=dictionary_matches(db, character),
                                   word=token['text'], word_pinyin_candidates=token['pinyin_candidates'],
                                   suggested_pinyin=syllables.get(position),
                                   pronunciation_candidates=json.loads(pronunciation[0]) if pronunciation else []))
    annotation = db.execute('SELECT state,payload FROM annotations WHERE ref=?', (ref,)).fetchone()
    return dict(ref=ref, original_chinese=row['zh'], source_sha256=row['sha256'],
                english=row['en'], language=row['language'],
                pinyin=analysis.get('pinyin'), pinyin_display=analysis.get('pinyin_display'),
                pinyin_method=analysis.get('pinyin_method', analysis.get('method')),
                analysis_state=analysis['state'], words=words, characters=characters,
                tags=analysis['tags'], translation=json.loads(row['payload']),
                context={**json.loads(db.execute('SELECT context FROM files WHERE path=?', (row['file_path'],)).fetchone()[0]),
                         **json.loads(row['context'])},
                annotation=dict(**{k: v for k, v in json.loads(annotation['payload']).items() if k != 'state'},
                                state=annotation['state']) if annotation else None)


def export_banks(db, destination):
    """Export exact snapshots to a NEW directory; never overwrite the live workspace."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    count = 0
    for row in db.execute('SELECT path,content,sha256 FROM files ORDER BY path'):
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe snapshot path')
        if digest(row['content']) != row['sha256']:
            raise ValueError('snapshot checksum mismatch')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(row['content'])
        count += 1
    return count


def verify(db, root):
    problems = []
    expected = {row[0] for row in db.execute('SELECT path FROM files')}
    current = {str(path.relative_to(root)) for path in (root / 'work/translate/banks').glob('*/*.json')}
    hardcoded = root / 'work/translate/hardcoded/strings.json'
    if hardcoded.exists():
        current.add(str(hardcoded.relative_to(root)))
    problems.extend(sorted(current - expected))
    for row in db.execute('SELECT * FROM files'):
        path = root / row['path']
        if not path.exists() or digest(path.read_bytes()) != row['sha256']:
            problems.append(row['path'])
        entries = db.execute('SELECT payload FROM entries WHERE file_path=? ORDER BY ordinal', (row['path'],)).fetchall()
        if [json.loads(e['payload']) for e in entries] != json.loads(row['content'])['strings']:
            raise ValueError('entry round-trip mismatch: ' + row['path'])
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('database integrity check failed')
    return problems


def save_annotation(db, annotation, path, root):
    """Merge one review atomically; source hash prevents applying it to changed Chinese."""
    import fcntl
    row = db.execute('SELECT s.zh,s.sha256,e.file_path,f.sha256 file_sha FROM entries e JOIN sources s ON s.id=e.source_id JOIN files f ON f.path=e.file_path WHERE e.ref=?', (annotation['ref'],)).fetchone()
    if row is None or annotation['source_sha256'] != row['sha256']:
        raise ValueError('annotation source hash/ref does not match the catalogue')
    if digest((root / row['file_path']).read_bytes()) != row['file_sha']:
        raise ValueError('source bank changed; rebuild the catalogue before saving a review')
    if annotation.get('review_status', 'draft') not in ('draft', 'reviewed'):
        raise ValueError('review_status must be draft or reviewed')
    if annotation.get('review_status') == 'reviewed' and not annotation.get('reviewer'):
        raise ValueError('a reviewed annotation must name its reviewer')
    lexicon = Lexicon()
    for token in annotation.get('tokens', []):
        if not isinstance(token.get('start'), int) or not isinstance(token.get('end'), int):
            raise ValueError('annotation offsets must be integers')
        for reading in dictionary_matches(db, row['zh'][token['start']:token['end']]):
            lexicon.readings[reading['id']] = reading
    validate_annotation(annotation, row['zh'], lexicon)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        annotations = {a['ref']: a for a in load_annotations(path)}
        annotations[annotation['ref']] = annotation
        fd, temporary = tempfile.mkstemp(prefix='.annotations-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                output.write(''.join(packed(annotations[ref]) + '\n' for ref in sorted(annotations)))
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def report_value(value):
    """Render arbitrary JSON evidence as text, never as markup or executable URLs."""
    if value is None or value == '' or value == [] or value == {}:
        return '<span class="muted">Unknown / unavailable</span>'
    if isinstance(value, dict):
        return '<dl>' + ''.join('<dt>' + html.escape(str(k).replace('_', ' ')) + '</dt><dd>'
                               + report_value(v) + '</dd>' for k, v in value.items()) + '</dl>'
    if isinstance(value, list):
        return '<ul>' + ''.join('<li>' + report_value(v) + '</li>' for v in value) + '</ul>'
    return html.escape(str(value))


def render_annotation(db, entry):
    """Keep source-current review claims distinct from automatic and historical data."""
    annotation = entry.get('annotation')
    if not isinstance(annotation, dict):
        return '<p class="muted">No contextual annotation available.</p>'
    current = (annotation.get('state') == 'current' and
               annotation.get('source_sha256') == entry.get('source_sha256'))
    metadata = {k: annotation.get(k) for k in ('review_status', 'reviewer_kind', 'reviewer', 'source_sha256')}
    if not current:
        return ('<details class="stale"><summary>Stale / historical annotation — not applied</summary>'
                '<p>Source hash mismatch or unverified state. This annotation does not describe the current source. '
                'Historical offsets are not applied to current text.</p>'
                + report_value({'current_source_sha256': entry.get('source_sha256'), 'historical_annotation': annotation})
                + '</details>')

    def selection(item):
        rid = item.get('reading_id') or item.get('selected_reading_id')
        sid = item.get('sense_id') or item.get('selected_sense_id')
        selected = {}
        if rid:
            row = db.execute('SELECT pinyin,source_id FROM readings WHERE id=?', (rid,)).fetchone()
            selected['selected reading'] = dict(row) if row else {'id': rid, 'availability': 'Unknown / unavailable'}
        if sid:
            row = db.execute('SELECT gloss,reading_id FROM senses WHERE id=?', (sid,)).fetchone()
            selected['selected sense'] = dict(row) if row and row['reading_id'] == rid else {'id': sid, 'availability': 'Unknown / unavailable'}
        return report_value(selected) if selected else ''

    output = ['<div class="annotation"><h3>Source-current contextual annotation</h3>', report_value(metadata)]
    if str(annotation.get('reviewer_kind', '')).lower() == 'llm':
        output.append('<p><strong>LLM review; not human approval or ground truth.</strong></p>')
    else:
        output.append('<p>Review status records annotation provenance; it does not establish translation approval.</p>')
    for key, label in [('pinyin', 'Contextual Pinyin'), ('literal_english', 'Literal explanation'),
                       ('grammar_notes', 'Grammar and idioms'), ('clauses', 'Clauses'),
                       ('uncertainties', 'Ambiguity and caveats')]:
        output.append('<h4>' + label + '</h4>' + report_value(annotation.get(key)))
    output.append('<details><summary>Contextual character breakdown</summary><table><thead><tr>'
                  '<th>Character / offset</th><th>Contextual Pinyin</th><th>English role and evidence</th></tr></thead><tbody>')
    for char in annotation.get('characters') or []:
        if not isinstance(char, dict):
            continue
        output.append('<tr><td>' + report_value(char.get('text') or char.get('character')) + ' @'
                      + report_value(char.get('position')) + '</td><td>' + report_value(char.get('pinyin'))
                      + '</td><td>' + report_value(char.get('role') or char.get('gloss')) + selection(char)
                      + '<details><summary>Character provenance and alternatives</summary>'
                      + report_value({k: v for k, v in char.items() if k not in ('text', 'character', 'position', 'pinyin', 'role', 'gloss')})
                      + '</details></td></tr>')
    output.append('</tbody></table></details><details><summary>Contextual word spans and selected senses</summary>')
    for token in annotation.get('tokens') or []:
        if not isinstance(token, dict):
            continue
        text = token.get('text')
        start, end = token.get('start'), token.get('end')
        if text is None and isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(entry['original_chinese']):
            text = entry['original_chinese'][start:end]
        output.append('<div class="token"><h4>' + report_value(text) + '</h4>'
                      + report_value(token) + selection(token) + '</div>')
    output.append('</details><details><summary>Annotation provenance and additional fields</summary>'
                  + report_value({k: v for k, v in annotation.items() if k not in
                                  ('characters', 'tokens', 'pinyin', 'literal_english', 'grammar_notes', 'clauses', 'uncertainties')})
                  + '</details></div>')
    return ''.join(output)


def render_report(db, refs, *, summary=None, case_notes=None):
    """Portable escaped HTML; optional JSON summary/case notes add review evidence."""
    esc = lambda value: html.escape(str(value))
    def evidence(value):
        if not isinstance(value, dict):
            return report_value(value)
        return ''.join(('<details><summary>' + esc(k.replace('_', ' ')) + '</summary>'
                        + report_value(v) + '</details>') if isinstance(v, (dict, list)) else
                       '<p><b>' + esc(k.replace('_', ' ')) + ':</b> ' + report_value(v) + '</p>'
                       for k, v in value.items())
    sections, navigation = [], []
    for index, ref in enumerate(refs):
        entry = inspect(db, ref)
        words, characters = [], []
        def definitions(readings):
            return ''.join('<details><summary>' + esc(r['pinyin']) + ' · ' + esc(r['traditional'])
                           + '</summary><p>Source: ' + esc(r.get('source_id', r.get('source', 'Unknown')))
                           + ' · Reading ID: ' + esc(r['id']) + '</p><ul>'
                           + ''.join('<li>' + esc(s['gloss']) + ' <small>(' + esc(s['id']) + ')</small></li>' for s in r['senses'])
                           + '</ul></details>' for r in readings) or '<span class="muted">No dictionary definition</span>'
        for word in entry['words']:
            terms = '<br>'.join(esc(json.loads(t['payload']).get('en', t['en'])) + ' <small>(' + esc(t['provenance']) + ')</small>' for t in word['project_terms'])
            candidates = word.get('pinyin_candidates') or []
            suggested = word.get('suggested_pinyin')
            comparison = ('Unknown / unavailable: no dictionary comparison' if not candidates else
                          'Unknown / unavailable: no automatic reading' if not suggested else
                          'Differs from dictionary candidates; contextual review needed' if suggested.lower() not in {p.lower() for p in candidates} else
                          'Matches a candidate; meaning and correctness remain unverified')
            words.append('<tr><td lang="zh">' + esc(word['text']) + '</td><td>' + esc(suggested or 'Unknown')
                         + '<br><small>Dictionary candidates: ' + esc(' / '.join(candidates) or 'Unknown / unavailable')
                         + '</small><br>' + esc(comparison) + '</td><td>' + terms + definitions(word['readings']) + '</td></tr>')
        for char in entry['characters']:
            characters.append('<tr><td lang="zh">' + esc(char['text']) + '<small> @' + str(char['position']) + '</small></td><td>'
                              + esc(char['suggested_pinyin'] or 'Unknown') + '<br><small>Other pronunciation candidates: '
                              + esc(' / '.join(char['pronunciation_candidates']) or 'Unknown / unavailable') + '</small></td><td>'
                              + definitions(char['readings']) + '</td></tr>')
        navigation.append('<a href="#case-' + str(index) + '">' + esc(ref) + '</a>')
        sections.append('<section class="case" id="case-' + str(index) + '"><h2>' + esc(ref)
                        + '</h2><h3>Original Chinese</h3><p class="zh" lang="zh">' + esc(entry['original_chinese'])
                        + '</p><h3>Current English</h3><p class="english">' + esc(entry['english']) + '</p>'
                        + ('<h3>Case outcome and evidence</h3>' + evidence(case_notes[ref]) if case_notes and ref in case_notes else '')
                        + render_annotation(db, entry)
                        + '<details class="automatic"><summary>Automatic suggestions and dictionary comparison (unreviewed)</summary>'
                        + '<h3>Automatic Pinyin</h3><p>' + esc(entry['pinyin_display'] or entry['analysis_state'])
                        + '</p><p>Recorded method: ' + esc(entry.get('pinyin_method') or 'Unknown / unavailable')
                        + '</p><p>Automatic phrase data may differ from the reviewed tone convention even with tone_sandhi=False. '
                        'Older metadata saying “citation tones” is not a guarantee. Dictionary matches do not establish correctness.</p>'
                        + '<h3>Words and project names</h3><table><thead><tr><th>Word</th><th>Automatic Pinyin / comparison</th><th>English / dictionary meanings</th></tr></thead><tbody>'
                        + ''.join(words) + '</tbody></table><h3>Automatic character breakdown</h3><table><thead><tr><th>Character / offset</th><th>Automatic Pinyin</th><th>Dictionary readings and meanings</th></tr></thead><tbody>'
                        + ''.join(characters) + '</tbody></table></details></section>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Origin HeartGold — text catalogue review</title><style>
body{font:16px/1.6 system-ui,sans-serif;color:#202938;background:#f6f8fa;max-width:1080px;margin:auto;padding:32px}
section{background:white;border:1px solid #d9e1e8;padding:24px;margin:28px 0;border-radius:12px}
h1,h2,h3{line-height:1.25}h2{color:#285c62}table{border-collapse:collapse;width:100%;table-layout:fixed}
td,th{vertical-align:top;text-align:left;border-bottom:1px solid #e2e8ef;padding:12px;overflow-wrap:anywhere}
th:first-child{width:17%}th:nth-child(2){width:26%}summary{cursor:pointer;color:#285c62;font-weight:600}.zh{font-size:24px}
small,.muted{color:#657386}strong,.stale{color:#9c3e00}ul{padding-left:20px}p,dd{overflow-wrap:anywhere;white-space:pre-wrap}
dt{font-weight:600}dd{margin:0 0 12px 20px}details{margin:12px 0}.token{border-top:1px solid #d9e1e8}
nav{display:flex;flex-wrap:wrap;gap:8px 18px}nav a{color:#285c62}input{padding:10px;width:90%;font:inherit}.english{font-weight:600}
@media(max-width:600px){body{padding:10px}section{padding:12px}td,th{padding:6px}}
</style></head><body><h1>Translation text catalogue</h1><p>Original Chinese · contextual review · current English · automatic evidence.</p>
<p>Source-current annotations show their review status and reviewer kind. Drafts are proposals. LLM reviews are not human approvals.
Automatic word boundaries, pronunciations and dictionary alternatives remain separate. A character’s dictionary meanings do not automatically describe its role in a compound.</p>
''' + ('<section><h2>Review summary</h2>' + evidence(summary) + '</section>' if summary is not None else '') + '''
<label for="search">Find a case by reference or text</label><p><input id="search" type="search" placeholder="Search this report"></p><nav aria-label="Cases">''' + ' '.join(navigation) + '</nav>' + ''.join(sections) + '''<footer>Definitions: <a href="https://www.mdbg.net/chinese/dictionary?page=cc-cedict">CC-CEDICT / MDBG</a>,
<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a> (parsed and grouped).
Pronunciation suggestions: <a href="https://github.com/mozillazg/python-pinyin">pypinyin</a> (MIT).
Local review artifact; contains game text. No external assets or network requests.</footer>
<script>document.getElementById('search').addEventListener('input',function(){const q=this.value.toLocaleLowerCase();document.querySelectorAll('.case').forEach(s=>{s.hidden=!s.textContent.toLocaleLowerCase().includes(q)});});document.querySelector('nav').addEventListener('click',function(e){if(e.target.tagName==='A'){document.getElementById('search').value='';document.querySelectorAll('.case').forEach(s=>{s.hidden=false});}});</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('build', help='atomically rebuild from existing banks; never downloads')
    create.add_argument('--cedict', type=Path, help='local CC-CEDICT v1 .txt or .gz export')
    create.add_argument('--annotations', type=Path, default=CONFIG / 'annotations.jsonl')
    create.add_argument('--pypinyin-path', type=Path, help='local directory containing the optional pypinyin package')
    show = sub.add_parser('show', help='Chinese, English, pinyin, words, characters, meanings, context')
    show.add_argument('ref')
    lookup = sub.add_parser('lookup', help='all readings and meanings of a character or word')
    lookup.add_argument('text')
    search = sub.add_parser('search', help='literal Chinese/English substring search')
    search.add_argument('text')
    search.add_argument('--limit', type=int, default=20)
    sub.add_parser('stats')
    sub.add_parser('verify', help='check every field and byte against existing workspace')
    export = sub.add_parser('export', help='lossless bank snapshots into a new directory')
    export.add_argument('destination', type=Path)
    annotate = sub.add_parser('annotate', help='validate and atomically save one JSON review; rebuild afterwards')
    annotate.add_argument('input', type=Path)
    annotate.add_argument('--out', type=Path, default=CONFIG / 'annotations.jsonl')
    report = sub.add_parser('report', help='portable HTML with expandable character/word meanings')
    report.add_argument('refs', nargs='+')
    report.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'build':
        result = build(ROOT, args.db, args.cedict, args.annotations, args.pypinyin_path)
    else:
        with connect(args.db) as db:
            if args.command == 'show':
                result = inspect(db, args.ref)
            elif args.command == 'lookup':
                result = dictionary_matches(db, args.text)
            elif args.command == 'search':
                result = [dict(r) for r in db.execute('SELECT e.ref,s.zh,e.en FROM entries e JOIN sources s ON s.id=e.source_id WHERE instr(s.zh,?)>0 OR instr(lower(e.en),lower(?))>0 LIMIT ?', (args.text, args.text, args.limit))]
            elif args.command == 'stats':
                result = {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM metadata')}
            elif args.command == 'export':
                result = dict(exported=export_banks(db, args.destination))
            elif args.command == 'annotate':
                annotation = read_json(args.input)
                save_annotation(db, annotation, args.out, ROOT)
                result = dict(saved=annotation['ref'], path=str(args.out), next='Rebuild to refresh the catalogue.')
            elif args.command == 'report':
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(render_report(db, args.refs), encoding='utf-8')
                result = dict(report=str(args.out))
            else:
                changed = verify(db, ROOT)
                result = dict(integrity='ok', changed_since_build=changed)
                if changed:
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, sqlite3.Error, OSError) as error:
        raise SystemExit(str(error))
