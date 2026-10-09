"""Gift, Egg, starter, prize and NPC-trade sources for individual Pokémon pages.

Records come from the ROM script index and trade archive. Reviewed notes retain
cross-script story requirements that a local branch walk cannot establish.
"""
import collections
import json
import re
from pathlib import Path

NOTES = Path(__file__).with_name('pokemon_acquisition_notes.json')


def load_notes(path=NOTES):
    out = {}
    for row in json.loads(Path(path).read_text(encoding='utf-8'))['entries']:
        for species in row['species']:
            key = (row['file'], species)
            if key in out:
                raise ValueError(f'Duplicate acquisition note: {key}')
            out[key] = row
    return out


def sources(ctx, G, R, zone_area, file_areas, notes=None):
    """Species -> sources; repeated script branches merge without dropping evidence."""
    if notes is None and hasattr(G, 'acquisition_sources'):
        return reviewed_sources(ctx, G, zone_area, file_areas)
    notes = load_notes() if notes is None else notes
    result = collections.defaultdict(list)
    for file, script in ctx.S.items():
        for record in script['recs']:
            kind = record['kind']
            if kind not in ('mon_give', 'egg_give', 'trade', 'loan_give'):
                continue
            values = [record['args'][0]]
            if values == [None]:
                if not record.get('alt0_complete'):
                    continue  # a partial variable resolution is not a confirmed source
                values = record.get('alt0', [])
            for value in values:
                offer = None
                if kind in ('trade', 'loan_give'):
                    trade = R.parse_trade(ctx.rom['trade'][value])
                    species, form = R.split_species(trade['give'])
                    offer = trade['ask'] if kind == 'trade' else None
                    level = None
                    source_kind = 'trade' if kind == 'trade' else 'loan'
                else:
                    species, form = R.split_species(value)
                    level = record['args'][1] if kind == 'mon_give' else None
                    level = level if level is not None and level < 0x4000 else None
                    source_kind = 'gift' if kind == 'mon_give' else 'egg'
                species = G.form_index(ctx, species, form)
                if not species:
                    continue
                note = notes.get((file, species), {})
                if note.get('exclude'):
                    continue
                for area in file_areas(ctx, zone_area, file):
                    places = [ctx.zname(z) for z in sorted(ctx.file_zones[file], key=ctx.zrank)
                              if zone_area.get(z) is area]
                    row = dict(kind=note.get('kind', source_kind), area=area['slug'],
                               place=note.get('place', ' / '.join(dict.fromkeys(places))),
                               level=note.get('level', level), offer=offer,
                               conditions=note.get('conditions', ''), quests=note.get('quests', []))
                    # Unreviewed paths keep meaningful local conditions. Generic
                    # branch summaries cannot stand in for a proven starter check.
                    if 'conditions' not in note:
                        conditions = G.conditions_for(script, record['pc'], ctx, file)
                        row['conditions'] = ' or '.join(conditions)
                    evidence = dict(file=file, pc=record['pc'])
                    existing = next((old for old in result[species]
                                     if {k: v for k, v in old.items() if k != 'evidence'} == row), None)
                    if existing is None:
                        result[species].append(dict(row, evidence=[evidence]))
                    elif evidence not in existing['evidence']:
                        existing['evidence'].append(evidence)
    rank = {a['slug']: a['rank'] for a in zone_area.values()}
    for rows in result.values():
        rows.sort(key=lambda row: (rank[row['area']], row['place'], row['kind']))
    return result


def reviewed_sources(ctx, G, zone_area, file_areas):
    """Use the complete ROM audit with the site's existing acquisition components."""
    result = collections.defaultdict(list)
    notes = load_notes()
    for source in G.acquisition_sources(ctx):
        species = G.form_index(ctx, source['species'], source['form'])
        file = source['file']
        note = notes.get((file, species), {})
        targets = [zone_area[source['zone']]] if 'zone' in source else file_areas(ctx, zone_area, file)[:1]
        for area in targets:
            kind = 'starter' if file == 738 else note.get('kind', source['kind'])
            result[species].append(dict(kind=kind, area=area['slug'],
                place=source.get('place', ctx.place_str(file)), level=source['level'], offer=None,
                conditions=' '.join(source['conditions']), quests=source.get('quests', note.get('quests', [])),
                evidence=[dict(file=file, pc=pc) for pc in source.get('offsets', [])]))
    for trade in G.trade_sources(ctx):
        kind = 'loan-return' if trade.get('acquisitionKind') == 'replacement' else (
            'gift' if trade.get('retains') else 'loan' if trade['loan'] else 'trade')
        for area in file_areas(ctx, zone_area, trade['file'])[:1]:
            result[trade['give']].append(dict(kind=kind, area=area['slug'], place=ctx.place_str(trade['file']),
                level=trade['level'], offer=None if trade['loan'] else trade['ask'],
                conditions=' '.join(trade['conditions']),
                quests=notes.get((trade['file'], trade['give']), {}).get('quests', []),
                evidence=[dict(file=trade['file'], pc=r['pc']) for r in ctx.S[trade['file']]['recs']
                          if r['kind'] in ('trade', 'loan_give') and r['args'][0] == trade['trade']]))
    return result


def other_sources(how, has_wild):
    """Keep evolution, breeding, fossils and battles beside the complete source lists."""
    covered = r'^(?:gift(?: Egg)?(?: \(Lv \d+\))?, |in-game trade, |loan Pokémon, )'
    parts = [part for part in how.split('; ') if not re.match(covered, part)]
    if has_wild:
        parts = [part for part in parts if not part.startswith('wild:')]
    return '; '.join(parts)
