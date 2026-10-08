#!/usr/bin/env python3
"""Estimate play order of a027 text banks and re-plan the remaining translation batches.

Inputs (read-only):
  work/translate/bank_maps.json      (build_bank_maps.py: zone -> msg bank, mapsec, warps)
  work/translate/manifest.json       (bank sizes / categories / original batch plan)
  work/translate/banks/<narc>/*.json (current string statuses)

Method
  1. STORY below is the hack's route as a sequence of location ids (mapsec, the location
     name the player sees). Kanto first (Pallet -> ... -> Indigo Plateau -> Silver
     Conference on Mt. Silver), then Johto from New Bark (post-League), in vanilla Johto order.
     The Kanto part follows the scenes the translators found in B032-B057; the Johto part is
     vanilla order (not yet confirmed from the hack's scripts).
  2. Each zone gets the rank of its mapsec. Zones whose mapsec is not in STORY (Sevii Islands,
     Alto Mare, Frontier, Resort Zone ...) are side content; they are attached to the nearest
     ranked zone through warps / overworld adjacency (BFS) so they still sort sensibly.
  3. A bank's rank = the earliest rank among the zones whose map header loads it.
     Banks loaded by no map (and std-script banks): EXPLICIT placements, else by category.
     Final phase order: PHASE_ORDER (early Kanto map banks first, then first-hour std/menu text,
     the rest of Kanto, a review pass over v3-TM text, Pokedex, Johto, side features, unused).
Outputs
  work/translate/play_order.json          bank ranking with phase, zones, status counts
  work/translate/manifest_playorder.json  re-ordered batch plan for the remaining work
Usage: python3 work/translate/scripts/build_playorder.py
"""
import json
import os
from collections import Counter, deque

WORK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
T = os.path.join(WORK, 'translate')

# (phase, [mapsec ids in visiting order]); names from a027/0272
STORY = [
    ('kanto_early', [138, 149, 139, 170, 150, 224, 140, 151, 198, 152, 141, 172, 173]),
    # Pallet, Route 1, Viridian, Route 22, Route 2, Viridian Forest, Pewter, Route 3, Mt. Moon,
    # Route 4, Cerulean, Route 24, Route 25
    ('kanto_mid', [153, 154, 143, 226, 197, 159, 157, 158, 200, 201, 142, 156, 155, 144, 164,
                   165, 166, 145, 55, 227, 160, 161, 162, 163, 148, 121, 167, 168, 203, 169, 146]),
    # Route 5, Route 6, Vermilion, S.S. Anne, Diglett's Cave, Route 11, Route 9, Route 10,
    # Rock Tunnel, Power Plant, Lavender, Route 8, Route 7, Celadon, Routes 16-18, Fuchsia,
    # Safari Zone Gate, Resort Zone, Routes 12-15, Saffron, Rotom's Room, Routes 19/20,
    # Seafoam, Route 21, Cinnabar
    ('kanto_league', [221, 147, 15, 174, 175, 223, 176, 137, 219, 199]),
    # Victory Road, Indigo Plateau, Pokemon League, Routes 26/27, Tohjo Falls, Route 28,
    # Mt. Silver (Silver Conference), Mt. Silver Cave, Cerulean Cave
    ('johto', [126, 177, 127, 178, 179, 220, 128, 204, 180, 209, 210, 181, 129, 211, 214, 182,
               131, 215, 118, 49, 208, 183, 207, 225, 184, 185, 133, 206, 205, 230, 186, 187, 132,
               212, 188, 229, 112, 80, 81, 111, 113, 114, 115, 116, 189, 130, 234, 218, 190, 216,
               46, 134, 213, 135, 191, 192, 217, 136, 222, 193, 194, 228, 195, 196, 202, 231, 232]),
]
PHASE_ORDER = ['kanto_early', 'kanto_early_side', 'early_std', 'early_desc', 'kanto_mid',
               'kanto_mid_side', 'kanto_league', 'kanto_league_side', 'tm_review', 'pokedex',
               'johto', 'johto_side', 'nonmap', 'unused']
PRIORITY = {'kanto_early': 'P1', 'kanto_early_side': 'P1', 'early_std': 'P1', 'early_desc': 'P1',
            'kanto_mid': 'P2', 'kanto_mid_side': 'P2', 'kanto_league': 'P2', 'kanto_league_side': 'P2',
            'tm_review': 'P2', 'pokedex': 'P2', 'johto': 'P2', 'johto_side': 'P3', 'nonmap': 'P3',
            'unused': 'P4'}
DUMMY_BANKS = {3}  # battle-message bank used as the "no text" placeholder in map headers

# Banks no map header loads (or std-script banks), by where they first show up in play.
EXPLICIT = {
    # std scripts met in the first hour: TV in the player's house (std_tv), TV interviewer,
    # Pokemon Center link-club reception, Oak's Pokedex evaluation
    722: ('early_std', 'std_tv'), 721: ('early_std', 'std_tv_interview'),
    44: ('early_std', 'std_comm_reception'), 657: ('early_std', 'std_dex_evaluation'),
    # menu text seen from the first menu open (Chinese still shows for their todo strings)
    738: ('early_desc', 'move_descriptions'), 218: ('early_desc', 'item_descriptions'),
    712: ('early_desc', 'ability_descriptions'), 243: ('early_desc', 'berry_descriptions'),
    # English already present (v3 TM, status tm) -> review pass after the Kanto map leftovers
    718: ('tm_review', 'trainer_battle_text'), 258: ('tm_review', 'walking_pokemon_reactions'),
    791: ('pokedex', 'pokedex_entries_hg'),
    792: ('unused', 'pokedex_entries_ss'), 798: ('unused', 'pokedex_entries_platinum'),
    41: ('unused', 'contest_reception_jp'),
}
CATEGORY_TIER = {
    'pokegear_phone': 'phone_radio_tv', 'pokegear_radio_map': 'phone_radio_tv', 'tv_news': 'phone_radio_tv',
    'battle_frontier': 'side_features', 'battle_frontier_trainer_text': 'side_features',
    'pokeathlon': 'side_features', 'easy_chat_words': 'side_features', 'mail': 'side_features',
    'side_features_minigames': 'side_features', 'misc_ui_system': 'side_features',
    'link_wifi': 'link_wifi', 'debug_or_unlisted': 'debug', 'debug_unused': 'debug',
}
TIER_ORDER = ['map', 'std_tv', 'std_tv_interview', 'std_comm_reception', 'std_dex_evaluation',
              'move_descriptions', 'item_descriptions', 'ability_descriptions', 'berry_descriptions',
              'trainer_battle_text', 'walking_pokemon_reactions', 'pokedex_entries_hg',
              'std_script', 'phone_radio_tv', 'side_features', 'other_nonmap',
              'pokedex_entries_ss', 'pokedex_entries_platinum', 'contest_reception_jp',
              'map_bank_unreferenced', 'link_wifi', 'debug', 'done_early']


def load_status():
    st = {}
    for narc in ('a027', 'battle_string'):
        d = os.path.join(T, 'banks', narc)
        for f in sorted(os.listdir(d)):
            if f.endswith('.json'):
                j = json.load(open(os.path.join(d, f), encoding='utf-8'))
                st['%s/%s' % (narc, f[:4])] = {s['id']: s['status'] for s in j['strings']}
    return st


def main():
    bm = json.load(open(os.path.join(T, 'bank_maps.json'), encoding='utf-8'))
    man = json.load(open(os.path.join(T, 'manifest.json'), encoding='utf-8'))
    zones = bm['_zones']
    status = load_status()

    sec_rank, sec_phase = {}, {}
    k = 0
    for phase, secs in STORY:
        for s in secs:
            sec_rank.setdefault(s, k)
            sec_phase.setdefault(s, phase)
            k += 1

    # graph: warps (both ways) + overworld adjacency
    adj = {z['zone_id']: set() for z in zones}
    for z in zones:
        for w in z['warps_to'] + z['outdoor_neighbours']:
            if w in adj:
                adj[z['zone_id']].add(w)
                adj[w].add(z['zone_id'])

    zrank, zphase = {}, {}
    for z in zones:
        if z['mapsec'] in sec_rank and z['zone_id'] >= 2:
            zrank[z['zone_id']] = sec_rank[z['mapsec']]
            zphase[z['zone_id']] = sec_phase[z['mapsec']]
    # side zones: BFS to the nearest story zone (ties -> earliest rank)
    story_rank, story_phase = dict(zrank), dict(zphase)
    for z in zones:
        zid = z['zone_id']
        if zid in zrank or zid < 2 or z['mapsec'] == 0:  # mapsec 0: union/underground/wifi rooms
            continue
        seen, q, found = {zid}, deque([(zid, 0)]), []
        while q:
            u, d = q.popleft()
            if found and d > found[0][0]:
                break
            if u in story_rank and u != zid:
                found.append((d, story_rank[u], story_phase[u]))
                continue
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    q.append((v, d + 1))
        if found:
            _, r, p = min(found, key=lambda t: (t[0], t[1]))
            zrank[zid] = r + 0.5
            zphase[zid] = p + '_side'

    # bank -> zones
    bank_rank, bank_phase, bank_zones = {}, {}, {}
    for key, rows in bm.items():
        if key.startswith('_'):
            continue
        b = int(key)
        for r in rows:
            if r['kind'] == 'common_script':
                bank_rank[b], bank_phase[b] = -1, 'global'
                bank_zones.setdefault(b, []).append('std %d-%d' % (r['script_id_lo'], r['script_id_hi']))
                continue
            if b in DUMMY_BANKS:
                continue
            zid = r['zone_id']
            bank_zones.setdefault(b, []).append('%d %s (%s)' % (zid, r['map_name_en'], r['vanilla_const']))
            if zid in zrank and (b not in bank_rank or zrank[zid] < bank_rank[b]):
                bank_rank[b], bank_phase[b] = zrank[zid], zphase[zid]

    mb = {x['key']: x for x in man['banks']}
    std_banks = {int(k) for k, v in bm.items() if not k.startswith('_') and any(r['kind'] == 'common_script' for r in v)}

    rows = []
    for key, x in mb.items():
        narc, b = x['narc'], x['bank']
        st = Counter(status.get(key, {}).values())
        rank = 1000
        if narc == 'battle_string':
            phase, tier = 'early_desc', 'done_early'
        elif b in EXPLICIT:
            phase, tier = EXPLICIT[b]
        elif b in bank_rank and bank_phase[b] != 'global':
            phase, tier, rank = bank_phase[b], 'map', bank_rank[b]
        elif b in std_banks:
            phase, tier = 'nonmap', 'std_script'
            if x['priority'] in ('P0', 'P1'):
                phase, tier = 'early_desc', 'done_early'
        elif x['priority'] in ('P0', 'P1'):
            phase, tier = 'early_desc', 'done_early'  # names/UI/battle: B001-B031, done
        else:
            tier = CATEGORY_TIER.get(x['category'], 'other_nonmap')
            phase = 'unused' if tier in ('link_wifi', 'debug') else 'nonmap'
            if x['category'] == 'map_script':
                phase, tier = 'nonmap', 'map_bank_unreferenced'  # no map header loads it
        rows.append({
            'bank': key, 'phase': phase, 'tier': tier, 'rank': rank,
            'category': x['category'], 'old_batches': x.get('batches', []),
            'zones': bank_zones.get(b, []) if narc == 'a027' else [],
            'strings': x['strings'], 'cjk_strings': x['cjk_strings'],
            'todo': st['todo'], 'tm': st['tm'], 'draft': st['draft'], 'reviewed': st['reviewed'],
        })
    rows.sort(key=lambda r: (PHASE_ORDER.index(r['phase']), TIER_ORDER.index(r['tier']), r['rank'], r['bank']))
    for i, r in enumerate(rows):
        r['order'] = i
    json.dump({'description': 'a027/battle_string banks in estimated play order (see build_playorder.py)',
               'story_mapsecs': STORY, 'banks': rows},
              open(os.path.join(T, 'play_order.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # ---- re-plan remaining batches -------------------------------------------------------
    done_batches = {'B%03d' % i for i in range(1, 60)}  # B001-B059 (PROGRESS.md Done; B058/B059 in flight)
    part_ranges = {}  # bank -> list of (lo, hi) still to do, from the original manifest parts
    for bt in man['batches']:
        if bt['batch'] in done_batches:
            continue
        for p in bt['parts']:
            part_ranges.setdefault(p['bank'], []).append(tuple(p['ids']))
    cjk_per_string = {}
    for narc in ('a027', 'battle_string'):
        d = os.path.join(WORK, 'extract', 'v4', narc)
        for f in os.listdir(d):
            if f[:4].isdigit() and f.endswith('.json'):
                j = json.load(open(os.path.join(d, f), encoding='utf-8'))
                key = '%s/%s' % (narc, f[:4])
                cjk_per_string[key] = {s['id']: sum(1 for ch in s['text'] if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿')
                                       for s in j['strings']}

    units = []  # (row, bank, lo, hi, n_strings, n_chars)
    for r in rows:
        if r['bank'] not in part_ranges:
            continue
        cj = cjk_per_string.get(r['bank'], {})
        rng = sorted(part_ranges[r['bank']])
        # the old plan split some banks over two batches; re-join them (split again only if too big)
        for lo, hi in [(rng[0][0], max(h for _, h in rng))]:
            ids = [i for i in range(lo, hi + 1) if cj.get(i, 0) > 0]
            units.append((r, r['bank'], lo, hi, len(ids), sum(cj[i] for i in ids), ids, cj))

    MAX_S, MAX_C = 600, 15000
    # pre-split only ranges that cannot fit in one batch
    pieces = []
    for r, bank, lo, hi, n, c, ids, cj in units:
        if n <= MAX_S and c <= MAX_C:
            pieces.append((r, bank, lo, hi, n, c))
            continue
        chunk_lo, s_acc, c_acc = lo, 0, 0
        for i in range(lo, hi + 1):
            ci = cj.get(i, 0)
            if s_acc and (s_acc + (ci > 0) > MAX_S or c_acc + ci > MAX_C):
                pieces.append((r, bank, chunk_lo, i - 1, s_acc, c_acc))
                chunk_lo, s_acc, c_acc = i, 0, 0
            s_acc += ci > 0
            c_acc += ci
        pieces.append((r, bank, chunk_lo, hi, s_acc, c_acc))

    PACK = {'kanto_early': 'first_hour', 'kanto_early_side': 'first_hour', 'early_std': 'first_hour'}

    def group_of(r):
        return PACK.get(r['phase'], r['phase'])

    batches, cur = [], None
    for r, bank, lo, hi, n, c in pieces:
        g = group_of(r)
        if cur is None or cur['group'] != g or cur['cjk_strings'] + n > MAX_S or cur['cjk_chars'] + c > MAX_C:
            if cur:
                batches.append(cur)
            cur = {'group': g, 'parts': [], 'cjk_strings': 0, 'cjk_chars': 0, 'labels': []}
        cur['parts'].append({'bank': bank, 'ids': [lo, hi], 'cjk_strings': n, 'cjk_chars': c})
        cur['cjk_strings'] += n
        cur['cjk_chars'] += c
        if r['tier'] == 'map' and r['zones'] and not r['zones'][0].startswith('std'):
            lab = r['zones'][0].split(' (')[0].split(' ', 1)[1]
        else:
            lab = r['tier'] if r['tier'] not in ('other_nonmap', 'side_features', 'phone_radio_tv', 'link_wifi', 'debug') else r['category']
        if lab not in cur['labels']:
            cur['labels'].append(lab)
    if cur:
        batches.append(cur)

    out_batches = []
    for i, b in enumerate(batches):
        prio = PRIORITY.get(b['group'], 'P1' if b['group'] == 'first_hour' else 'P3')
        cats = []
        for p in b['parts']:
            c = mb[p['bank']]['category']
            if c not in cats:
                cats.append(c)
        olds = sorted({ob for p in b['parts'] for ob in mb[p['bank']].get('batches', []) if ob not in done_batches})
        out_batches.append({
            'batch': 'R%03d' % (i + 1), 'label': ' + '.join(b['labels'][:6]) + (' …' if len(b['labels']) > 6 else ''),
            'priority': prio, 'phase': b['group'], 'categories': cats,
            'parts': [{'bank': p['bank'], 'ids': p['ids'], 'cjk_strings': p['cjk_strings'], 'cjk_chars': p['cjk_chars']} for p in b['parts']],
            'cjk_strings': b['cjk_strings'], 'cjk_chars': b['cjk_chars'], 'replaces_old_batches': olds,
        })
    out = {
        'description': ('Play-order re-plan of the batches not yet done (manifest.json B060-B142). '
                        'Same batch schema as manifest.json plus phase / replaces_old_batches. Built by '
                        'work/translate/scripts/build_playorder.py from bank_maps.json. Batch ids are R###, '
                        'to avoid clashing with the B### ids already referenced in PROGRESS.md.'),
        'done_batches_excluded': 'B001-B059',
        'totals': {'batches': len(out_batches), 'cjk_strings': sum(b['cjk_strings'] for b in out_batches),
                   'cjk_chars': sum(b['cjk_chars'] for b in out_batches)},
        'batches': out_batches,
    }
    json.dump(out, open(os.path.join(T, 'manifest_playorder.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('play_order.json banks', len(rows), '| manifest_playorder.json batches', len(out_batches), out['totals'])


if __name__ == '__main__':
    main()
