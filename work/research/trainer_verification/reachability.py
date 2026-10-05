"""Conservative entry-linkage audit; never claims world-state feasibility.

Run from repository root. Raw ROM-derived evidence stays in ignored work/build.
"""
import collections
import json
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
sys.path.insert(0, str(Path('work/tools/docs').resolve()))
import gen_docs as G


def headers(data):
    """Map header: u8 type/u32 payload; type 1 is a relative conditional table."""
    out = []
    p = 0
    while p < len(data) and data[p]:
        typ = data[p]
        value = struct.unpack_from('<I', data, p + 1)[0]
        if typ == 1:
            q = p + 5 + value
            while True:
                var = struct.unpack_from('<H', data, q)[0]
                if var == 0:
                    break
                var, expected, script = struct.unpack_from('<HHH', data, q)
                out.append(dict(type=typ, script=script, variable=var, expected=expected, offset=q))
                q += 6
        else:
            out.append(dict(type=typ, script=value, offset=p))
        p += 5
    return out


def successors(row):
    op, args, nxt, target = row
    if op in G.R.TERM:
        return []
    return ([target] if target is not None else []) + ([] if G.R.JUMPS.get(op, False) else [nxt])


def build(c):
    names = G.R.cmds()
    mapped_header_ids = {z['script_header_bank'] for z in c.zones}
    # Contiguous header block also contains 16 unassigned header members.
    header_ids = set(range(min(mapped_header_ids), max(mapped_header_ids) + 1))
    for f in header_ids:
        headers(c.rom['scripts'][f])
    ordinary = {f: d for f, d in c.S.items() if f not in header_ids}
    std = c.rom.std_mapping()
    def resolve(sid, local):
        if sid < 2000:
            return local, sid
        for lower, bank, _ in std:
            if sid >= lower:
                return bank, sid - lower + 1
        return None
    roots = []
    objects = []
    for z in c.zones:
        common = dict(zone=z['zone_id'], local_file=z['scripts_bank'])
        for kind in ('obj', 'bg', 'coord'):
            for i, ev in enumerate(c.events[z['events_bank']][kind]):
                roots.append(dict(**common, source=kind, index=i, script_id=ev['script']))
                if kind == 'obj' and 3000 <= ev['script'] < 7000:
                    objects.append(dict(**common, object_id=ev['id'], script_id=ev['script'], trainer_id=ev['script']-(2999 if ev['script']<5000 else 4999), flag=ev['flag']))
        for h in headers(c.rom['scripts'][z['script_header_bank']]):
            roots.append(dict(**common, source='header', header_file=z['script_header_bank'], script_id=h['script'], header=h))
    reached = collections.defaultdict(set)
    invalid = []
    # A per-zone union avoids tens of thousands of redundant entry traversals.
    zone_roots = collections.defaultdict(list)
    for root in roots:
        resolved = resolve(root['script_id'], root['local_file'])
        if root['script_id'] in (0, 65535) or not resolved:
            continue
        f, entry = resolved
        if f not in ordinary or not 1 <= entry <= len(ordinary[f]['entries']):
            invalid.append(dict(root, resolved=resolved))
            continue
        root['resolved'] = [f, entry]
        zone_roots[root['zone']].append((f, ordinary[f]['entries'][entry-1]))
    for zone, todo in zone_roots.items():
        seen = set()
        while todo:
            f, pc = todo.pop()
            if (f, pc) in seen or f not in ordinary or pc not in ordinary[f]['ins']:
                continue
            seen.add((f, pc)); reached[f, pc].add(zone)
            row = ordinary[f]['ins'][pc]
            todo.extend((f, p) for p in successors(row))
            if names[row[0]][0] in ('CallStd', 'RunScript'):
                resolved = resolve(row[1][0], f)
                if resolved:
                    ff, entry = resolved
                    if ff in ordinary and 1 <= entry <= len(ordinary[ff]['entries']):
                        todo.append((ff, ordinary[ff]['entries'][entry-1]))
    # CN engine's trainer-sight dispatch uses standard script 3739 (949 entry740).
    # Both literal loads and BL encodings are checked against the reviewed slice.
    assert c.rom.a9(0x020633A0, 4) == struct.pack('<I', 3739)
    assert c.rom.a9(0x020632AA, 10) == bytes.fromhex('3d49159a281cdcf764f9')
    assert c.rom.a9(0x02063350, 10) == bytes.fromhex('1349159a281cdcf711f9')
    assert resolve(3739, 0) == (949, 740)
    engine_sight = set()
    todo = [ordinary[949]['entries'][739]]
    while todo:
        pc = todo.pop()
        if pc in engine_sight or pc not in ordinary[949]['ins']:continue
        engine_sight.add(pc)
        todo.extend(successors(ordinary[949]['ins'][pc]))
    encounters = []
    frontiers = []
    for f, d in ordinary.items():
        for rec in d['recs']:
            if rec['kind'] in ('trainer', 'multi_battle'):
                engine_linked = f == 949 and rec['pc'] in engine_sight
                status = 'entry-linked' if reached[f,rec['pc']] else ('engine-entry-linked' if engine_linked else 'no-static-root-found')
                classification = ('curated-dormant' if G._dead_pc(d,f,rec['pc']) else
                                  'known-inaccessible-zone' if f == 964 else
                                  'engine-trainer-sight' if engine_linked else
                                  'local-entry-without-static-trigger' if status == 'no-static-root-found' else 'map-or-standard-root')
                encounters.append(dict(script=f, pc=rec['pc'], entry_linked_zones=sorted(reached[f,rec['pc']]), status=status, classification=classification, engine_entry_linked=engine_linked, curated_dead_scene=G._dead_pc(d,f,rec['pc']), world_state_feasibility='unproven'))
        targets = set(d['entries'])
        for row in d['ins'].values():targets.update(successors(row))
        for pc in sorted(targets-set(d['ins'])):
            raw = c.rom['scripts'][f]
            frontiers.append(dict(script=f,pc=pc,file_size=len(raw),reason='outside-file' if not 0<=pc<len(raw)-1 else 'unknown-or-truncated-opcode',opcode=struct.unpack_from('<H',raw,pc)[0] if 0<=pc<len(raw)-1 else None))
    _, parties = G.load_trainers(c)
    locations = G.trainer_locations(c)
    unreferenced = [i for i,p in enumerate(parties) if p and i not in locations]
    from work.research.trainer_verification.reachability_phone import build as build_phone
    return dict(phone_rematches=build_phone(c), summary=dict(encounters=len(encounters), entry_linked=sum(bool(x['entry_linked_zones']) for x in encounters), engine_entry_linked=sum(x['engine_entry_linked'] for x in encounters), no_static_root_found=sum(x['status']=='no-static-root-found' for x in encounters), map_header_files=len(header_ids), mapped_header_files=len(mapped_header_ids), header_triggers=sum(x['source']=='header' for x in roots), remaining_frontiers=len(frontiers), generic_trainer_objects=len(objects), unreferenced=unreferenced), roots=roots, invalid_roots=invalid, encounters=encounters, decode_frontiers=frontiers, generic_trainer_objects=objects)

if __name__ == '__main__':
    result = build(G.Ctx())
    out = Path('work/build/trainer_verification/reachability')
    out.mkdir(parents=True,exist_ok=True)
    (out/'supplement.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))


def menu_outcome(ins, start, value, singles=False):
    """Trace a menu result until another menu, battle or End; fail on unmodelled flow."""
    variables = {0x800C: value}
    pc, comparison = start, None
    for _ in range(250):
        op, args, nxt, target = ins[pc]
        name = G.R.cmds()[op][0]
        if name in ('End', 'TrainerBattle', 'MenuInit'):
            return dict(kind=name, pc=pc, value=variables.get(0x800C))
        if name == 'CopyVar':variables[args[0]] = variables.get(args[1])
        elif name == 'SetVar':variables[args[0]] = args[1]
        elif name == 'CheckFlag':
            if args != [311]:raise ValueError('unmodelled flag')
            comparison = (int(singles), 1)
        elif name == 'CompareVarToValue':comparison = (variables[args[0]], args[1])
        elif name == 'GoToIf':
            a, b = comparison
            take = (a < b, a == b, a > b, a <= b, a >= b, a != b)[args[0]]
            pc = target if take else nxt
            continue
        elif name == 'GoTo':
            pc = target
            continue
        elif target is not None:
            raise ValueError('unmodelled branch at %s' % pc)
        pc = nxt
    raise ValueError('menu trace exceeded bound')
