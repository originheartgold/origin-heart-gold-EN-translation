"""Chapter layer of the quest guide: load and validate guide/chapters/*.toml, render chapter pages.

The quest bodies stay in guide/NN-*.md (storage, one H2 per quest, stable ids). guide/chapters/NN-slug.toml
says which chapter each quest belongs to, the walkthrough of the chapter and what each step unlocks or
permanently closes (see work/notes/guide_chapters_plan.md for the format). sync_guide.py builds the site's
chapter pages from both.

    python3 work/tools/site/chapters.py          # validate guide/chapters against the quest ledger
"""
import html
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
CHAPTERS = os.path.join(REPO, 'guide', 'chapters')
LEDGER = os.path.join(HERE, 'quest_ledger.json')

QUEST_ID = re.compile(r'^q-\d{4}$')
# Player-facing fields must not carry technical references; those belong in `evidence`.
TECH_RE = re.compile(r'\b(flags?|scripts?|vars?|file \d+|map \d+|zone \d+)\b|0x[0-9a-f]+|\b\d{3,4},\d{3,4}\b|@\d{3,}|\bL\d{3,}\b', re.I)
PLAYER_FIELDS = ('title', 'summary', 'intro')
STEP_PLAYER_FIELDS = ('text',)
QUEST_PLAYER_FIELDS = ('available_note', 'level_note')


def load(directory=CHAPTERS):
    """Chapter dicts sorted by `order`; each gets `_file`."""
    out = []
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith('.toml'):
            continue
        with open(os.path.join(directory, fn), 'rb') as fh:
            ch = tomllib.load(fh)
        ch['_file'] = fn
        out.append(ch)
    out.sort(key=lambda c: c['order'])
    return out


def validate(chapters, ledger_ids, missable_ids=()):
    """List of error strings; empty when the chapter files are consistent."""
    errs = []
    placed = {}
    where = {}
    if [c['order'] for c in chapters] != list(range(1, len(chapters) + 1)):
        errs.append('chapter orders are not 1..%d without gaps or duplicates' % len(chapters))
    seen_postgame = False
    ids = set()
    for ch in chapters:
        name = ch['_file']
        for key in ('id', 'order', 'title', 'summary', 'kind', 'intro', 'steps', 'quests'):
            if key not in ch:
                errs.append('%s: missing %s' % (name, key))
        if ch.get('id') in ids:
            errs.append('%s: duplicate chapter id' % name)
        ids.add(ch.get('id'))
        if ch.get('kind') not in ('story', 'postgame'):
            errs.append('%s: kind must be story or postgame' % name)
        if ch.get('kind') == 'postgame':
            seen_postgame = True
        elif seen_postgame:
            errs.append('%s: story chapter after a postgame chapter' % name)
        for f in PLAYER_FIELDS:
            if TECH_RE.search(ch.get(f, '')):
                errs.append('%s: technical reference in %s: %r' % (name, f, TECH_RE.search(ch[f]).group(0)))
        for q in ch.get('quests', []):
            qid = q.get('id')
            if not QUEST_ID.match(qid or '') or qid not in ledger_ids:
                errs.append('%s: unknown quest id %r' % (name, qid))
            elif qid in placed:
                errs.append('%s: %s already placed in %s' % (name, qid, placed[qid]))
            else:
                placed[qid] = ch['id']
                where[qid] = ch['order']
            for f in QUEST_PLAYER_FIELDS:
                if TECH_RE.search(q.get(f, '')):
                    errs.append('%s: technical reference in %s of %s' % (name, f, qid))
        step_ids = set()
        for s in ch.get('steps', []):
            sid = s.get('id')
            if sid in step_ids:
                errs.append('%s: duplicate step id %s' % (name, sid))
            step_ids.add(sid)
            for f in STEP_PLAYER_FIELDS:
                if TECH_RE.search(s.get(f, '')):
                    errs.append('%s %s: technical reference in %s: %r' % (name, sid, f, TECH_RE.search(s[f]).group(0)))
            if 'evidence' not in s:
                errs.append('%s %s: missing evidence' % (name, sid))
    for ch in chapters:
        for s in ch.get('steps', []):
            for field in ('unlocks', 'closes'):
                for qid in s.get(field, []):
                    if qid not in where:
                        errs.append('%s %s: %s of unplaced %s' % (ch['_file'], s['id'], field, qid))
                    elif where[qid] > ch['order']:
                        errs.append('%s %s: %s points forward to %s (chapter %d)' % (ch['_file'], s['id'], field, qid, where[qid]))
        for q in ch.get('quests', []):
            for qid in q.get('needs', []):
                if qid not in where or where[qid] > ch['order']:
                    errs.append('%s: %s needs %s which is unplaced or in a later chapter' % (ch['_file'], q['id'], qid))
    for qid in sorted(ledger_ids - set(placed)):
        errs.append('%s is not placed in any chapter' % qid)
    closed = {qid for ch in chapters for s in ch.get('steps', []) for qid in s.get('closes', [])}
    noclose = {m for ch in chapters for s in ch.get('steps', []) for m in re.findall(r'NOCLOSE (q-\d{4})', s.get('evidence', ''))}
    for ch in chapters:
        for q in ch.get('quests', []):
            if q.get('missable') and q['id'] not in closed | noclose:
                errs.append('%s: %s is missable but no step closes it (add closes, or "NOCLOSE %s: reason" to the evidence)' % (ch['_file'], q['id'], q['id']))
            if q.get('missable') and missable_ids and q['id'] not in missable_ids:
                errs.append('%s: %s is missable here but its guide quest line has no missable=yes' % (ch['_file'], q['id']))
            if not q.get('missable') and missable_ids and q['id'] in missable_ids:
                errs.append('%s: %s has missable=yes in the guide but not in the chapter' % (ch['_file'], q['id']))
    return errs


def short_label(ch):
    return re.sub(r'^Chapter (\d+): ', r'\1. ', ch['title']) if ch['kind'] == 'story' else ch['title']


def _attrs(tags):
    out = []
    for key in ('starter', 'gender'):
        if key in tags:
            out.append('data-%s="%s"' % (key, ','.join(tags[key])))
    if 'kind' in tags:
        out.append('data-kind="%s"' % tags['kind'])
    if tags.get('postgame'):
        out.append('data-postgame="yes"')
    return ' '.join(out)


def _chips(tags):
    out = []
    if 'starter' in tags:
        out.append('<span class="tag tag-starter">%s only</span>' % ' / '.join(tags['starter']))
    if 'gender' in tags:
        out.append('<span class="tag tag-gender">%s players only</span>' % ('Male' if tags['gender'] == ['male'] else 'Female'))
    if tags.get('missable'):
        out.append('<span class="tag tag-missable">Missable</span>')
    if tags.get('postgame'):
        out.append('<span class="tag tag-postgame">Post-game</span>')
    return ' '.join(out)


def quest_link(qid, info, chapter_of, here, up='../'):
    """Markdown/HTML link to a quest, relative to chapter page `here`."""
    q = info[qid]
    target = chapter_of[qid]
    href = '#' + q['anchor'] if target == here else '%s%s/#%s' % (up, target, q['anchor'])
    return '<a href="%s">%s</a>' % (href, html.escape(q['title'], quote=False))


def _item(qid, info, chapter_of, here):
    q = info[qid]
    chips = _chips(q['tags'])
    return '<li class="chapter-quest" data-quest-id="%s" %s>%s%s</li>' % (
        qid, _attrs(q['tags']), quest_link(qid, info, chapter_of, here), (' ' + chips) if chips else '')


STEP_TITLE = re.compile(r'^\*\*(.+?)\*\*')


def step_title(step):
    """The bold lead-in of a step's text, without its full stop (\"**Route 3.** …\" -> \"Route 3\")."""
    m = STEP_TITLE.match(step['text'].strip())
    return m.group(1).strip().rstrip('.:') if m else ''


def render_step(step, info, chapter_of, here):
    title = step_title(step)
    attrs = ' id="step-%s"' % step['id'] if step.get('id') else ''
    if title:
        attrs += ' data-title="%s"' % html.escape(title)
    out = ['<div class="chapter-step%s"%s>' % ('' if step.get('main') else ' chapter-optional', attrs), '', step['text'].strip(), '']
    if step.get('unlocks'):
        out += ['<div class="chapter-unlocks">', '<strong>Opens up:</strong>', '<ul>']
        out += [_item(q, info, chapter_of, here) for q in step['unlocks']]
        out += ['</ul>', '</div>', '']
    if step.get('closes'):
        out += ['<aside class="chapter-warning" role="note">', '<strong>Warning:</strong> doing this closes these for good. Finish them first.', '<ul>']
        out += [_item(q, info, chapter_of, here) for q in step['closes']]
        out += ['</ul>', '</aside>', '']
    ev = step.get('evidence', '').strip()
    if ev:
        out += ['<details class="tech" data-pagefind-ignore="all"><summary>Technical source (script files and flags)</summary>', '', ev, '', '</details>', '']
    out += ['</div>', '']
    return out


def render_chapter(ch, info, chapter_of, sections, previous, following, hidden_items=()):
    """Markdown body (no frontmatter) of a chapter page. `sections` maps quest id -> section lines (already link-rewritten)."""
    here = ch['id']
    out = [ch['intro'].strip(), '']
    out += hidden_items
    if ch['steps']:
        out += ['## Walkthrough', '']
        for step in ch['steps']:
            out += render_step(step, info, chapter_of, here)
    qs = ch['quests']
    out += ['## Quests in this chapter', '',
            'Open the ones you want; tick **Done** to hide them. Filters at the top apply to this whole page.', '']
    for q in qs:
        out += sections[q['id']]
    return out


def main():
    ledger = json.load(open(LEDGER, encoding='utf-8'))
    ids = {q['id'] for q in ledger['quests']}
    chapters = load()
    errs = validate(chapters, ids)
    for e in errs:
        print('ERROR: ' + e)
    print('%d chapters, %d errors' % (len(chapters), len(errs)))
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
