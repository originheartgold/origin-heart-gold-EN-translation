"""Regenerate trainer research evidence from the local, untouched Chinese ROM.

Run from the repository root: python3 work/research/trainer_verification/export_index.py
Outputs contain game data and are restricted to ignored work/build/ directories.
This replaces the old pipeline's dependence on its own stale parsed roster.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/tools/docs'))
import gen_docs as G
import romdata as R


def sha(data):
    return hashlib.sha256(data).hexdigest()


def input_hashes():
    """Conservative manifest: dialogue banks affect menu/condition descriptions too."""
    paths = set()
    for pattern in ('work/tools/docs/*.py', 'work/tools/docs/*.json', 'work/tools/site/*.json',
                    'work/docs/*names.json', 'work/translate/banks/a027/*.json',
                    'work/glossary/*.json'):
        paths.update(ROOT.glob(pattern))
    paths.update(ROOT / p for p in ('work/translate/bank_maps.json', 'work/translate/play_order.json',
                                   'work/glossary/manual_overrides.py', 'work/tools/fill_names.py'))
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(paths)}


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def successors(row):
    op, _args, next_pc, target = row
    if op in R.TERM:
        return []
    return ([target] if target is not None else []) + ([] if R.JUMPS.get(op, False) else [next_pc])


def walk(d, start, stop=None):
    """Syntactic traversal only: both branches, no state feasibility or call stack."""
    seen, todo = set(), [start]
    while todo:
        pc = todo.pop()
        if pc in seen or pc not in d['ins']:
            continue
        seen.add(pc)
        if not stop or not stop(pc):
            todo.extend(successors(d['ins'][pc]))
    return seen


def instruction(d, pc):
    op, args, next_pc, target = d['ins'][pc]
    return dict(pc=pc, command=R.cmds()[op][0], args=args, next=next_pc, target=target)


def party_maxima(kind, args, parties):
    def maximum(ids):
        return max((m['level'] for tid in ids if tid is not None and 0 < tid < len(parties)
                    for m in parties[tid]), default=None)
    opponents = args[1:3] if kind == 'multi_battle' else args[:2]
    partners = args[:1] if kind == 'multi_battle' else []
    return dict(opponent_party_max=maximum(opponents), partner_party_max=maximum(partners),
                all_participants_party_max=maximum(opponents + partners))


def check_party_bytes(raw, td, party):
    """Independent offsets and runtime expectations; do not compare to an older parser dump."""
    assert len(raw) == td['count'] * 28 == len(party) * 28
    for slot, mon in enumerate(party):
        p = raw[slot * 28:(slot + 1) * 28]
        ability, level, species, item = struct.unpack_from('<4H', p, 4)
        assert (mon['ability'], mon['level'], mon['species'], mon['item']) == (ability, level, species, item)
        assert mon['form'] == p[2]
        assert mon['ivs'] == p[0] * 31 // 255
        assert mon['hp_ivs'] == (10 if level < 41 else 31 if level >= 80 else 20)
        assert mon['evs'] == [p[20], p[21], p[22], p[24], p[25], p[23]]
        assert mon['nature'] == (None if p[3] == 255 else p[3])
        assert mon['moves'] == [x for x in struct.unpack_from('<4H', p, 12) if x]


def export(ctx):
    rom, commands = ctx.rom, R.cmds()
    tds, parties = G.load_trainers(ctx)
    locations = G.trainer_locations(ctx)
    references, unresolved = collections.defaultdict(list), []
    encounters, frontiers, badges = [], [], []
    for file_id, d in ctx.S.items():
        raw = rom['scripts'][file_id]
        targets = set(d['entries'])
        for row in d['ins'].values():
            targets.update(successors(row))
        for pc in sorted(targets - set(d['ins'])):
            in_bounds = 0 <= pc < len(raw) - 1
            frontiers.append(dict(script=file_id, pc=pc, reason='unknown-or-truncated-opcode' if in_bounds else 'outside-file',
                                  file_size=len(raw), opcode=struct.unpack_from('<H', raw, pc)[0] if in_bounds else None))
        battles = [r for r in d['recs'] if r['kind'] in ('trainer', 'multi_battle')]
        entry_paths = [walk(d, e) for e in d['entries']] if battles else []
        for r in battles:
            args = r['args'][:3 if r['kind'] == 'multi_battle' else 2]
            entry_ids = [i + 1 for i, path in enumerate(entry_paths) if r['pc'] in path]
            triggers = []
            for zid in ctx.file_zones.get(file_id, []):
                zone = ctx.zones[zid]
                for kind in ('obj', 'bg', 'coord'):
                    for event in ctx.events.get(zone['events_bank'], {}).get(kind, []):
                        if event.get('script') in entry_ids:
                            triggers.append(dict(zone=zid, event_bank=zone['events_bank'], kind=kind, event=event))
            participants = []
            for slot, tid in enumerate(args):
                if tid == 0:
                    continue
                role = 'partner' if r['kind'] == 'multi_battle' and slot == 0 else 'opponent'
                participants.append(dict(role=role, slot=slot, trainer_id=tid))
                ref = dict(file=file_id, pc=r['pc'], kind=r['kind'], slot=slot, role=role,
                           raw=r['raw'], resolved_args=r['args'], zones=ctx.file_zones.get(file_id, []),
                           dead_scene=G._dead_pc(d, file_id, r['pc']), conditions=G.conditions_for(d, r['pc'], ctx, file_id))
                if tid is None:
                    unresolved.append(ref)
                else:
                    references[tid].append(ref)
            encounters.append(dict(key=f'script:{file_id}:{r["pc"]}', script=file_id, pc=r['pc'], kind=r['kind'],
                raw_args=r['raw'], resolved_args=r['args'], participants=participants, zones=ctx.file_zones.get(file_id, []),
                entry_candidates=entry_ids, physical_trigger_candidates=triggers,
                conditions_summary=G.conditions_for(d, r['pc'], ctx, file_id), conditions_complete=False,
                local_instruction_window=[instruction(d, p) for p in sorted(d['ins']) if r['pc'] - 180 <= p <= r['pc'] + 100],
                curated_dead_scene=G._dead_pc(d, file_id, r['pc']), **party_maxima(r['kind'], args, parties),
                reachability='static-reference-only'))
        battle_pcs = {r['pc'] for r in battles}
        for pc, (op, _a, _n, _t) in d['ins'].items():
            if commands[op][0] != 'GiveBadge':
                continue
            candidates = [r for r in battles if pc in walk(d, r['pc'], lambda p: p != r['pc'] and p in battle_pcs)]
            badges.append(dict(script=file_id, award=instruction(d, pc), zones=ctx.file_zones.get(file_id, []),
                battle_candidates=[r['pc'] for r in candidates], candidate_teams=[r['args'] for r in candidates],
                nearby_evidence=[instruction(d, p) for p in sorted(d['ins']) if pc - 100 <= p <= pc + 60],
                confidence='syntactic-control-flow-only',
                unresolved=['branch feasibility', 'victory gating', 'map access', 'first challenge versus rematch', 'global ordering']))
    for zone in ctx.zones:
        for event in ctx.events.get(zone['events_bank'], {}).get('obj', []):
            script = event['script']
            if 3000 <= script < 7000:
                tid = script - (2999 if script < 5000 else 4999)
                references[tid].append(dict(kind='map_object', zone=zone['zone_id'], event_bank=zone['events_bank'],
                                           object=event, unreachable_zone=zone['zone_id'] in G.UNREACHABLE_ZONES))
    menu = []
    d = ctx.S[78]
    expected_menu_ids = set(G.memory_trainer_ids(ctx))
    for pc, (op, a, _n, _t) in d['ins'].items():
        if commands[op][0] != 'SetVar' or a[0] != 0x800C or a[1] not in expected_menu_ids:
            continue
        reached = walk(d, pc, lambda p: commands[d['ins'][p][0]][0] == 'TrainerBattle')
        calls = [p for p in sorted(reached) if commands[d['ins'][p][0]][0] == 'TrainerBattle']
        assert calls == [1040, 1083]
        menu.append(dict(trainer_id=a[1], assignment_pc=pc, battle_pcs=calls, branch_flag=311,
                         evidence=[instruction(d, p) for p in sorted(reached)],
                         scope='assignment-to-call; see reachability supplement for menu/cancel analysis'))
    roster = []
    for tid, (td, party) in enumerate(zip(tds, parties)):
        check_party_bytes(rom['trpoke'][tid], td, party)
        roster.append(dict(id=tid, label=G.trainer_label(ctx, tid, td), metadata=td, party=party,
            raw_party_sha256=sha(rom['trpoke'][tid]), raw_metadata_sha256=sha(rom['trdata'][tid]),
            references=references[tid], guide_locations=locations.get(tid, []),
            reachability='referenced-not-proven-reachable' if references[tid] else 'unresolved-no-static-reference',
            max_level=max((m['level'] for m in party), default=None)))
    unreferenced = []
    for row in roster[1:]:
        tid = row['id']
        if not row['party'] or row['references']:
            continue
        hits = [dict(script=f, pc=pc, command=commands[op][0], args=a)
                for f, d in ctx.S.items() for pc, (op, a, _n, _t) in d['ins'].items() if tid in a]
        unreferenced.append(dict(trainer_id=tid, label=row['label'], max_level=row['max_level'], party=row['party'],
            identical_raw_party_ids=[i for i in range(1, len(tds)) if i != tid and rom['trpoke'][i] == rom['trpoke'][tid]],
            nonsemantic_numeric_instruction_hits=hits, conclusion='no decoded battle/map-object reference; not proven unused',
            possible_special_runtime_table=707 <= tid <= 711))
    counts = dict(trainer_records=len(roster), teams=sum(bool(r['party']) for r in roster[1:]),
        party_slots=sum(len(r['party']) for r in roster[1:]), battle_callsites=len(encounters),
        multi_battle_callsites=sum(e['kind'] == 'multi_battle' for e in encounters), badge_award_sites=len(badges),
        dynamic_menu_teams=len(menu), decode_frontiers=len(frontiers), unreferenced_teams=len(unreferenced),
        unresolved_argument_occurrences=len(unresolved),
        corrected_form_slots=sum(bool(m['form']) for p in parties for m in p),
        separate_hp_iv_slots=sum(m['hp_ivs'] != m['ivs'] for p in parties for m in p))
    provenance = dict(rom_sha256=sha(Path(rom.path).read_bytes()), source=str(ROOT),
        modules={n: sha((ROOT / 'work/tools/docs' / n).read_bytes()) for n in ('romdata.py', 'gen_docs.py', 'trainer_guide.py')},
        inputs=input_hashes(), exporter_sha256=sha(Path(__file__).read_bytes()))
    return dict(roster=roster, encounters=encounters, badge_candidates=badges, menu78_assignments=menu,
                unreferenced=unreferenced, decode_frontiers=frontiers, unresolved_arguments=unresolved,
                summary=dict(schema_version=3, summary=counts, provenance=provenance,
                    party_semantics=dict(form='separate byte 2', evs=['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe'],
                                         ivs='five non-HP stats', hp_ivs='original Chinese loader override'),
                    reachability='references and syntactic candidates only; see separate reachability evidence'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'work/build/difficulty-trainers-v3')
    args = ap.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'work/build'):
        ap.error('raw game-data output must stay under ignored work/build/')
    out.mkdir(parents=True, exist_ok=True)
    ctx = G.Ctx(R.Rom(cache=str(out / 'docs_cache.pkl'), refresh=True))
    data = export(ctx)
    for name, value in data.items():
        write_json(out / (name + '.json'), value)
    print(json.dumps(data['summary']['summary'], indent=2))


if __name__ == '__main__':
    main()
