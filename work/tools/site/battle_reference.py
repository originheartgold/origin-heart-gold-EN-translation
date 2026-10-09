"""Battle reference fields with explicit evidence levels; no gameplay inference.

Names/text use approved translation banks. Structured attributes come from the
live CN table whose loader/layout is documented in move_data_audit.md.
Author workbook notes are imported separately by reconcile_references.py.
"""
import json
import os
import re
import move_comparisons as MC

# Only meanings explicitly established by the local audits are named.
TARGETS = {0: 'Selected target', 5: 'All opponents', 7: 'User'}
FLAGS = {0: 'contact', 1: 'charge', 2: 'recharge', 34: 'slicing'}
# These are findings, not corrections to either source.
STALE_DESCRIPTIONS = {49, 55, 110, 175, 177, 199, 209, 268, 295, 354, 294, 417,
                      192, 59, 158, 81, 230, 729, 340}
AMBIGUOUS_EFFECTS = {66, 161, 307, 308, 318, 338, 344, 401, 439, 461}
with open(os.path.join(os.path.dirname(__file__), 'move_tested_notes.json'), encoding='utf-8') as source:
    TESTED_NOTES = {row['moveId']: row for row in json.load(source)}


def evidence(kind, source, **extra):
    return dict(kind=kind, source=source, **extra)


def description(bank, ident, rows):
    row = rows.get(ident, {})
    # Never leak unreviewed Chinese into the English site.
    text = row.get('en')
    if not text:
        return None
    text = re.sub(r'\{(?:NEWLINE|SCROLL|CLEAR)\}', ' ', text)
    return dict(text=re.sub(r'\s+', ' ', text).strip(),
                evidence=evidence('game-text', 'a027/%04d#%d' % (bank, ident)),
                translationStatus=row.get('status'))


def effect_summary(ident, data):
    """Player-readable descriptions of fields, explicitly configured, never tested."""
    texts = []
    lo, hi = data['hits']
    if lo and hi:
        texts.append('Configured hits: %s.' % (str(lo) if lo == hi else '%d–%d' % (lo, hi)))
    conditions = {1: 'paralysis', 2: 'sleep', 3: 'freezing', 4: 'burn', 5: 'poison', 6: 'confusion'}
    if data['condition'] in conditions and data['condition_chance']:
        texts.append('Configured %d%% chance of %s.' % (data['condition_chance'], conditions[data['condition']]))
    if data['flinch_chance']:
        texts.append('Configured %d%% flinch chance.' % data['flinch_chance'])
    if data['crit_stage']:
        texts.append('Configured critical-hit stage: +%d.' % data['crit_stage'])
    if data['drain']:
        texts.append('Configured %s: %d%%.' % ('drain' if data['drain'] > 0 else 'recoil', abs(data['drain'])))
    if data['heal'] > 0:
        texts.append('Configured healing: %d%%.' % data['heal'])
    elif data['heal'] < 0:
        texts.append('Configured HP loss/cost field: %d; basis and timing not decoded.' % data['heal'])
    stats = {1: 'Attack', 2: 'Defense', 3: 'Sp. Atk', 4: 'Sp. Def', 5: 'Speed', 6: 'accuracy', 7: 'evasion', 9: 'all stats'}
    for change in data['stat_changes']:
        if change['stat'] in stats:
            # Zero is not a literal probability for primary stat effects. Keep
            # unknown semantics in the raw record, without inventing 0% or 100%.
            chance = ', %d%% chance' % change['chance'] if change['chance'] else ''
            texts.append('Configured %s change: %+d stage(s)%s.' % (
                stats[change['stat']], change['stages'], chance))
    return [dict(text=text, evidence=evidence('rom-data', 'extra/new_move_data.narc#%d' % ident,
                audit='work/notes/move_data_audit.md')) for text in texts]


def move_reference(ident, data, rows):
    result = dict(effectSummary=effect_summary(ident, data), description=description(738, ident, rows), priority=data['priority'],
                  targetId=data['target'], target=TARGETS.get(data['target']),
                  flags=[name for bit, name in FLAGS.items() if data['flags'] & (1 << bit)],
                  flagBits=[bit for bit in range(64) if data['flags'] & (1 << bit)],
                  effects={key: data[key] for key in ('quality', 'hits', 'condition', 'condition_chance',
                      'condition_kind', 'condition_turns', 'crit_stage', 'flinch_chance', 'effect',
                      'drain', 'heal', 'stat_changes')},
                  evidence=[evidence('rom-data', 'extra/new_move_data.narc#%d' % ident,
                            audit='work/notes/move_data_audit.md')], conflicts=[])
    if ident in STALE_DESCRIPTIONS:
        result['conflicts'].append(dict(kind='stale-description',
            text='The game description disagrees with the live move record; see the move data audit.',
            source='work/notes/move_data_audit.md'))
    result['testedNotes'] = [TESTED_NOTES[ident]] if ident in TESTED_NOTES else []
    if ident in AMBIGUOUS_EFFECTS:
        result['conflicts'].append(dict(kind='unresolved-behavior',
            text=('Effect ID, secondary fields or description disagree. A scoped gameplay result is recorded below; other conditions and unresolved fields remain unverified.'
                  if ident in TESTED_NOTES else
                  'Effect ID, secondary fields or description disagree; battle behavior needs an in-game test.'),
            source='work/notes/move_data_audit.md'))
    return result


def enrich(ctx, data, R, slugs):
    move_desc, ability_desc, item_desc = (R.load_bank_full(n) for n in (738, 712, 218))
    facts_path = os.path.join(os.path.dirname(__file__), 'reference_facts.json')
    facts = json.load(open(facts_path, encoding='utf-8')) if os.path.exists(facts_path) else {}
    originals, change_notes = MC.load_comparisons()
    for move in data['moves']:
        move.update(move_reference(move['id'], ctx.moves[move['id']], move_desc))
        move['authorNotes'] = [x for x in (facts.get('moveChanges', []) + facts.get('newTms', [])) if x.get('moveId') == move['id']]
        move['originalComparison'] = MC.compare_move(move, originals.get(move['id']), change_notes.get(move['id'], []))
        # Later moves have no HG baseline. Preserve explicitly advertised changes,
        # without guessing previous-generation values or treating new TMs as changes.
        if move['id'] not in originals:
            names = {'Type': 'type', 'Category': 'cat', 'Power': 'power', 'Accuracy': 'acc', 'PP': 'pp', 'Target': 'target'}
            fields = set()
            for note in facts.get('moveChanges', []):
                if note.get('moveId') == move['id']:
                    fields.update(note.get('highlightedFields', []))
            for label, key in names.items():
                if label in fields and move[key] is not None:
                    move['originalComparison']['fields'].append(dict(field=label, before=None, after=str(move[key])))
    ids = {i for i in ctx.AB if i} | {i for i in ability_desc if i}
    for sp in data['species']:
        p = ctx.personal[sp['id']]
        sp['abilityIds'] = list(dict.fromkeys(a for a in p['abilities'] if a))
        sp['abilitySlots'] = list(p['abilities'])
        sp['hiddenAbilityId'] = p['hidden_ability'] or None
        sp['baseSpeciesId'], sp['formId'] = ctx.forms.get(sp['id'], (sp['id'], 0))
        ids.update(sp['abilityIds'])
        if sp['hiddenAbilityId']:
            ids.add(sp['hiddenAbilityId'])
    ids.update(mon['abilityId'] for trainer in data['trainers'] for mon in trainer['team'] if mon['abilityId'])
    abilities = []
    for ident in sorted(ids):
        unnamed = not ctx.AB.get(ident) or ctx.AB.get(ident) in ('—', '-')
        name = 'Unnamed ability #%d' % ident if unnamed else ctx.ab(ident)
        abilities.append(dict(id=ident, name=name, slug=slugs.make('ability', name, ident),
            unnamed=unnamed, description=description(712, ident, ability_desc),
            authorNotes=[x for x in facts.get('abilityChanges', []) if x.get('abilityId') == ident],
            applicability=[x for x in facts.get('applicability', []) if x.get('abilityId') == ident],
            evidence=[evidence('rom-data', 'a/0/0/2 ability fields; a027/0711 names')]))
    # Missing #327 name is intentionally a placeholder. Workbook label is an author alias.
    for ability in abilities:
        ability['conflicts'] = [dict(kind='description-source-difference',text='The author claims an added Aqua Ring effect, but the game description mentions only burn immunity. The battle effect has not been verified.',source='work/notes/sheet_mismatch_verification.md section 4.4')] if ability['id']==41 else []
    data['abilities'] = abilities
    for sp in data['species']:
        sp['referenceNotes']=[x for x in facts.get('pokemonNotes',[]) if x.get('speciesId')==sp['id']]
    for area in data['areas']:
        area['referenceNotes']=[x for x in facts.get('encounterNotes',[]) if x.get('areaSlug')==area['slug']]
    for trainer in data['trainers']:
        trainer['evidence']=evidence('rom-data','a/0/5/5#%d; a/0/5/6#%d; script battle references'%(trainer['id'],trainer['id']))
    for item in data['items']:
        item['description'] = description(218, item['id'], item_desc)
        item['effectText'] = item['description']
        item['effects'] = dict(holdEffectId=ctx.items[item['id']]['hold_effect'],
            evidence=evidence('rom-data', 'a/0/1/7#%d' % item['id']),
            note='Raw held-effect ID; no battle-effect meaning inferred.')
        item['authorNotes'] = [x for x in facts.get('itemEffects', []) if x.get('itemId') == item['id']]
        item['referenceNotes'] = [x for x in facts.get('itemReference',[]) if x.get('itemId')==item['id']]
        item['legacySourceNotes'] = [x for x in facts.get('legacyItemSources',[]) if x.get('itemId')==item['id']]
        item['legacyUseNotes'] = [x for x in facts.get('legacyItemUses',[]) if x.get('itemId')==item['id']]
        item['evolutionUses'] = [dict(speciesId=sp['id'],resultId=e['id'],how=e['how'],blocked=e.get('blocked'),never=e.get('never',False))
            for sp in data['species'] for e in sp['evoTo'] if any(c.get('item')==item['id'] for c in e['conds'])]
        item['tutorUses'] = [dict(moveId=t['move'],places=t['places'],cost=t['cost']) for t in data['tutors']
            if any(re.sub(r'\s*[×x]\s*\d+$','',c)==item['name'] for c in (t.get('cost') or []))]
        item['trainerUses'] = [t['id'] for t in data['trainers'] if any(m['itemId']==item['id'] for m in t['team'])]

    data['tms'] = [dict(itemId=i, moveId=ctx.tm[i], label=R.tm_label(i),
        newInV4=R.ITEM_TM93 <= i <= R.ITEM_TM130,
        evidence=evidence('rom-data', 'arm9 TM tables 0x020FFFF8 / 0x020FFFAC'),
        authorNotes=[x for x in facts.get('newTms', []) if x.get('itemId') == i]) for i in ctx.tm_sorted]
    referenced = {m for s in data['species'] for _, m in s['levelup']}
    referenced |= {m for s in data['species'] for key in ('egg', 'tutors') for m in s[key]}
    referenced |= set(ctx.tm.values()) | {t['move'] for t in data['tutors']}
    for raw, party in zip(ctx.rom['trdata'], ctx.rom['trpoke']):
        info = R.parse_trdata(raw)
        referenced.update(m for mon in R.parse_trpoke(party, info['count']) for m in mon['moves'] if m)
    data['move_slots'] = dict(total=len(ctx.moves)-1, unnamed=[dict(id=m['id'],
        referenced=m['id'] in referenced, disposition='placeholder' if m['id'] in referenced else 'unreferenced-live-slot')
        for m in data['moves'] if m.get('unnamed')], evidence=evidence('rom-data', 'extra/new_move_data.narc'))
    for tutor in data['tutors']:
        tutor['authorNotes'] = [x for x in facts.get('tutorNotes', []) if x.get('configuredMoveId',x.get('moveId')) == tutor['move']]
    data['battle_notes'] = {key: facts.get(key, []) for key in ('moveChanges', 'abilityChanges', 'applicability', 'newTms', 'itemEffects', 'tutorNotes', 'pokemonNotes', 'encounterNotes', 'mapNotes', 'unmappedEncounterTables')}
    data['reference_coverage'] = facts.get('coverageSummary', {})
    data['meta']['itemRarityLegend']=facts.get('itemLegend',{})
    data['meta']['tradeGoodsNote']=facts.get('tradeGoodsNote')
    data['meta']['counts'].update(abilities=len(abilities), tms=len(data['tms']))
    return data
