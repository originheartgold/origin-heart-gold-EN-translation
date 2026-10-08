#!/usr/bin/env python3
"""Step 4: per-bank manifest + batch plan -> work/translate/manifest.json

Inputs: v4 extracts, bank_map_v3_v4.json, bank_map_us_v4.json, tm_v4_coverage.json,
us_reuse_summary.json, ref/vanilla_hgss.json (JP dev bank names), us_ref.json (pret map names).
"""
import json, os, re, sys
from collections import Counter, OrderedDict, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *

A027 = load_narc('v4', 'a027')
BS = load_narc('v4', 'battle_string')
XZ = {int(k): v for k, v in json.load(open(os.path.join(OUT, 'ref', 'vanilla_hgss.json')))['banks'].items()}
JP = {int(k): v for k, v in json.load(open(os.path.join(OUT, 'ref', 'jp_a027.json')))['banks'].items()}
USREF = {b['bank']: b for b in json.load(open(os.path.join(OUT, 'us_ref.json')))['banks']}
UMAP = {e['v4']: e for e in json.load(open(os.path.join(OUT, 'bank_map_us_v4.json')))['map'] if e['v4'] is not None}
V3MAP = {e['v4']: e for e in json.load(open(os.path.join(OUT, 'bank_map_v3_v4.json')))['map'] if e['v4'] is not None}
TMCOV = json.load(open(os.path.join(OUT, 'tm_v4_coverage.json')))['per_bank']
USRE = json.load(open(os.path.join(OUT, 'us_reuse_summary.json')))['per_bank']

# ---------------------------------------------------------------- categories
# (regex on the JP dev name of the bank, category, priority)
# P0 = name lists (glossary / official-name driven), P1 = core UI, battle, hack notices,
# P2 = story & frequently seen text, P3 = side features, P4 = link/Wi-Fi/debug, skip = nothing to translate
RULES = [
    (r'^monsname$', 'species_names', 'P0'), (r'^wazaname$', 'move_names', 'P0'),
    (r'^itemname$', 'item_names', 'P0'), (r'^tokusei$', 'ability_names', 'P0'),
    (r'^typename$', 'type_names', 'P0'), (r'^chr$', 'nature_names', 'P0'),
    (r'^trtype$', 'trainer_classes', 'P0'), (r'^trname$', 'trainer_names', 'P0'),
    (r'^place_name', 'location_names', 'P0'), (r'^nuts_name$', 'berry_names', 'P0'),
    (r'^zkn_type$', 'pokedex_categories', 'P0'), (r'^gym_name$', 'location_names', 'P0'),
    (r'^wazainfo$', 'move_descriptions', 'P2'), (r'^iteminfo$', 'item_descriptions', 'P2'),
    (r'^tokuseiinfo$', 'ability_descriptions', 'P2'), (r'^nuts_info$', 'berry_descriptions', 'P3'),
    (r'^zkn_comment', 'pokedex_entries', 'P3'), (r'^zkn$', 'pokedex_ui', 'P1'),
    (r'^zkn_(gram|height)$', 'pokedex_measurements', 'P3'),
    (r'^(atkmsg|fightmsg_dp)$', 'battle_messages', 'P1'), (r'^(b_bag|b_plist|bconfind)$', 'battle_ui', 'P1'),
    (r'^trmsg$', 'trainer_battle_text', 'P2'), (r'^tower_trainer', 'battle_frontier_trainer_text', 'P3'),
    (r'^(bag|boxmenu|boxmes|pokelist|pokestatus|startmenu|config|fieldmenu|namein|status|shop|itempocket.*|'
     r'fld_item|hiden|gameover|report|backup_.*|load_warning|waza_oboe|waza_oshie|townmap|trainerscard|'
     r'poke_select|time|title|condition|itemeqp|ribbon|support|supportname|pgamestart|egg_demo|'
     r'encount_effect|dungeon_cutin|fld_demo|fld_trade|demo_trade|evolution|sodateya)$', 'menus_ui_system', 'P1'),
    (r'^(common_scr|ev_win|ev_pokeselect|fum|pair_scr|haitatu|dendou_.*|intro|opening.*|pc_ug)$', 'common_script_text', 'P1'),
    (r'^pair_reaction$', 'walking_pokemon_reactions', 'P2'),
    (r'^(tel_.*|pg_tel)$', 'pokegear_phone', 'P3'),
    (r'^(radio_.*|pg_radio|pg_skin|pgmap_guide)$', 'pokegear_radio_map', 'P3'),
    (r'^(msg_tv_.*|tv_.*|tvcm|msgboy|cameraman|telop)$', 'tv_news', 'P3'),
    (r'^(bf_.*|factory_.*|castle_.*|stage_room|roulette.*|btower_app|btdtrname|battle_room|br_ranking|'
     r'bug_select|directbattlecorner)$', 'battle_frontier', 'P3'),
    (r'^(pokethlon.*|pkth.*)$', 'pokeathlon', 'P3'),
    (r'^(pms_.*|pmss_.*)$', 'easy_chat_words', 'P3'),
    (r'^(mailbox.*|mailview)$', 'mail', 'P3'),
    (r'^(an_note|an_puzzle|album|award|balloon|ball_custom|bong_.*|bonguri_get|kinomi.*|n_planter|imageclip.*|'
     r'mushitori|safari.*|pokemonpark|p_park|scratch_.*|slot|saisen|guru2.*|lobby_minigame.*|minigame_.*|'
     r'oekaki|poketch_.*|poruto.*|seal_comment|bc_seal_name|perap|phc_.*|taste|mystery|fushigi_pwd|'
     r'earth|worldtimer|weekbros|con_.*|cmsg_.*|icontest|poke_anime|stafflist|tr_house|codein|'
     r'bc_.*|dstrade|battle_rec|taisen_rokuga|mictest|hyouka|email|group|record|ranking)$', 'side_features_minigames', 'P3'),
    (r'^(wifi_.*|gtc|communication|connect|union|ug|undergroundgoods|uwstatus|wflby_.*|hiroba)$', 'link_wifi', 'P4'),
    (r'^(debug_.*|dummy_scr|poke_test)$', 'debug_unused', 'P4'),
]

MAP_ORDER = ('T01 R01 T02 R22 R02 D46 T03 R03 D02 R04 T04 R24 R25 R05 R06 T06 P01 D01 R11 R09 R10 T05 R08 R07 T07 '
             'R16 R17 R18 T08 D47 D10 R12 R13 R14 R15 T11 W19 W20 W21 D11 T09 T10 R26 R27 D43 R28 T31 D41 '
             'T20 R29 T21 R30 R31 D42 T22 D15 R32 D25 R33 T23 D26 D36 R34 T25 D23 D37 R35 D22 R36 R37 T27 '
             'D17 D18 R38 R39 T26 D27 W40 W41 T24 D40 R42 D38 T28 D35 R43 T29 R44 D39 T30 D44 R45 R46 D45 '
             'R47 R48 D50 D48 D49 D24 D31 D32 D51 D52').split()
MAP_RANK = {c: i for i, c in enumerate(MAP_ORDER)}
KANTO = set(MAP_ORDER[:MAP_ORDER.index('T20')])


def map_group_name(code):
    names = []
    for u in USREF.values():
        mc = (u.get('map_code') or '')
        if mc == code or (mc.startswith(code) and not names):
            names = u.get('maps') or names
            if mc == code:
                break
    return names[0] if names else code


def classify(b, strings):
    name = XZ.get(b, {}).get('name')
    if b >= 814:
        return {814: ('hack_ui_new', 'P1'), 815: ('hack_ui_new', 'P1'), 816: ('hack_intro_credits', 'P1')}[b] + (None,)
    if name and re.match(r'^[a-z]\d\d', name):
        code = re.match(r'^([a-z]\d\d)', name).group(1).upper()
        return ('map_script', 'P2', code)
    if name:
        for rx, cat, pr in RULES:
            if re.match(rx, name):
                return (cat, pr, None)
        return ('misc_ui_system', 'P3', None)
    return ('debug_or_unlisted', 'P4', None)


def bank_stats(ss):
    cj = [s for s in ss if has_cjk(s)]
    return len(ss), len(cj), sum(cjk_count(s) for s in cj), sum(1 for s in ss if s and not has_cjk(s) and
                                                               re.search('[A-Za-z]{3}', TAG_RE.sub('', s)))


banks = []
for narc, src in (('a027', A027), ('battle_string', BS)):
    for b in sorted(src):
        ss = src[b]
        n, ncj, nch, nlat = bank_stats(ss)
        e = {'narc': narc, 'bank': b, 'key': f'{narc}/{b:04d}', 'strings': n, 'cjk_strings': ncj, 'cjk_chars': nch,
             'latin_only_strings': nlat}
        if narc == 'battle_string':
            e.update({'category': 'battle_messages_hack', 'priority': 'P1', 'map_code': None, 'jp_name': None,
                      'origin': 'hack-new (non-retail NARC battle/string/battle_string.narc)',
                      'us_bank_guess': None, 'us_confidence': None, 'vanilla_count': None,
                      'sample': next((s for s in ss if has_cjk(s)), '')[:60]})
        else:
            cat, pr, code = classify(b, ss)
            um = UMAP.get(b, {})
            jn = XZ.get(b, {}).get('name')
            vc = len(JP[b]) if b in JP else None
            e.update({'category': cat, 'priority': pr, 'map_code': code, 'jp_name': jn,
                      'map_group': (code and map_group_name(code)) or None,
                      'us_bank_guess': um.get('us'), 'us_file': um.get('us_file'),
                      'us_confidence': um.get('confidence'), 'vanilla_count': vc,
                      'v3_bank': V3MAP.get(b, {}).get('v3'), 'v3_confidence': V3MAP.get(b, {}).get('confidence'),
                      'sample': next((s for s in ss if has_cjk(s)), '')[:60]})
            if code:
                e['region'] = 'Kanto' if code in KANTO else ('Johto' if code in MAP_RANK else 'other')
        tc = TMCOV.get(f'{narc}/{b}', {})
        e['tm'] = {k: tc.get(k, 0) for k in ('exact', 'exact_loose', 'fuzzy90', 'fuzzy80')}
        e['tm']['exact_chars'] = tc.get('exact_chars', 0)
        ur = USRE.get(str(b), {}) if narc == 'a027' else {}
        e['us_reuse'] = {k: ur.get(k, 0) for k in ('likely', 'possible', 'unlikely', 'no_us')}
        e['us_reuse']['likely_chars'] = ur.get('likely_chars', 0)
        if narc == 'a027':
            if b >= 814:
                e['origin'] = 'hack-new bank (no v3/vanilla counterpart)'
            elif ncj == 0:
                e['origin'] = 'no CJK (foreign-language, debug or placeholder text)'
            else:
                lr = (ur.get('likely', 0) + ur.get('possible', 0)) / max(ncj, 1)
                ext = vc is not None and n > vc * 1.2 + 2
                if lr >= 0.7:
                    e['origin'] = 'vanilla-derived (mostly untouched)'
                elif lr >= 0.3:
                    e['origin'] = 'vanilla-derived, partly rewritten/extended' if not ext else 'vanilla-derived + hack-extended'
                else:
                    e['origin'] = 'hack-rewritten' + (' + extended' if ext else '')
            e['origin_basis'] = {'vanilla_strings': e.get('vanilla_count'), 'v4_strings': n,
                                 'us_likely_or_possible': ur.get('likely', 0) + ur.get('possible', 0)}
        # remaining work estimate: CJK strings with neither TM exact nor US-likely
        e['cjk_strings_without_exact_tm'] = ncj - e['tm']['exact'] - e['tm']['exact_loose']
        if ncj == 0:
            e['priority'] = 'skip'
        banks.append(e)

# ---------------------------------------------------------------- batches
MAX_STR, MIN_STR, MAX_CH = 600, 300, 15000
units = []   # (sort_key, group_label, [parts]) ; part = (key, id_from, id_to, n_cjk, chars)


def split_bank(e, strings):
    """split one bank into parts that respect the limits (by id range)."""
    parts, cn, cc, start = [], 0, 0, 0
    ids = [i for i, s in enumerate(strings) if has_cjk(s)]
    if not ids:
        return []
    start = ids[0]
    last = ids[0]
    for i in ids:
        ch = cjk_count(strings[i])
        if cn and (cn + 1 > MAX_STR or cc + ch > MAX_CH):
            parts.append((e['key'], start, last, cn, cc))
            start, cn, cc = i, 0, 0
        cn += 1
        cc += ch
        last = i
    parts.append((e['key'], start, last, cn, cc))
    return parts


CAT_ORDER = ['hack_intro_credits', 'hack_ui_new', 'menus_ui_system', 'common_script_text', 'battle_messages',
             'battle_messages_hack', 'battle_ui', 'pokedex_ui', 'species_names', 'move_names', 'item_names',
             'ability_names', 'type_names', 'nature_names', 'trainer_classes', 'trainer_names', 'location_names',
             'berry_names', 'pokedex_categories', 'map_script', 'trainer_battle_text', 'walking_pokemon_reactions',
             'move_descriptions', 'item_descriptions', 'ability_descriptions', 'berry_descriptions',
             'pokedex_entries', 'pokedex_measurements', 'pokegear_phone', 'pokegear_radio_map', 'tv_news',
             'battle_frontier', 'battle_frontier_trainer_text', 'pokeathlon', 'easy_chat_words', 'mail',
             'side_features_minigames', 'misc_ui_system', 'link_wifi', 'debug_or_unlisted', 'debug_unused']
PR_ORDER = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4}
src_of = {'a027': A027, 'battle_string': BS}

groups = OrderedDict()
for e in banks:
    if e['priority'] == 'skip':
        continue
    if e['category'] == 'map_script':
        gk = ('map', e['map_code'][:3])
    else:
        gk = ('cat', e['category'])
    groups.setdefault(gk, []).append(e)


def group_sort(gk):
    es = groups[gk]
    pr = min(PR_ORDER[x['priority']] for x in es)
    if gk[0] == 'map':
        return (PR_ORDER['P2'], CAT_ORDER.index('map_script'), MAP_RANK.get(gk[1], 999), gk[1])
    return (pr, CAT_ORDER.index(gk[1]) if gk[1] in CAT_ORDER else 99, 0, gk[1])


batches = []
pending = []   # small map groups get merged with the next ones in story order


def flush(parts, label, prio, cats):
    if not parts:
        return
    batches.append({'batch': None, 'label': label, 'priority': prio, 'categories': sorted(set(cats)),
                    'parts': [{'bank': p[0], 'ids': [p[1], p[2]], 'cjk_strings': p[3], 'cjk_chars': p[4]} for p in parts],
                    'cjk_strings': sum(p[3] for p in parts), 'cjk_chars': sum(p[4] for p in parts)})


ordered = sorted(groups, key=group_sort)


def chunk_group(es):
    """balanced split of a group's CJK strings (bank order) into chunks within the limits;
    returns list of chunks, each a list of parts (key, id_from, id_to, n, chars)."""
    items = []
    for e in es:
        ss = src_of[e['narc']][e['bank']]
        items += [(e['key'], i, cjk_count(t)) for i, t in enumerate(ss) if has_cjk(t)]
    S, C = len(items), sum(x[2] for x in items)
    if not S:
        return []
    k = max(1, -(-S // MAX_STR), -(-C // MAX_CH))
    ts, tc = S / k, C / k
    chunks, cur, cs, cc = [], [], 0, 0
    for idx, it in enumerate(items):
        at_boundary = cur and cur[-1][0] != it[0]
        hard = cs + 1 > MAX_STR or cc + it[2] > MAX_CH
        soft = len(chunks) < k - 1 and (cs >= ts or cc >= tc or
                                        (at_boundary and (cs >= 0.85 * ts or cc >= 0.85 * tc)))
        if cur and (hard or soft):
            chunks.append(cur)
            cur, cs, cc = [], 0, 0
        cur.append(it)
        cs += 1
        cc += it[2]
    chunks.append(cur)
    out = []
    for ch in chunks:
        parts = []
        for key, i, n in ch:
            if parts and parts[-1][0] == key:
                k_, a, _, pn, pc = parts[-1]
                parts[-1] = (k_, a, i, pn + 1, pc + n)
            else:
                parts.append((key, i, i, 1, n))
        out.append(parts)
    return out


cur_parts, cur_labels, cur_prio, cur_cats, cur_is_map = [], [], None, [], None
for gk in ordered:
    es = sorted(groups[gk], key=lambda x: x['bank'])
    prio = min((x['priority'] for x in es), key=lambda p: PR_ORDER[p])
    label = (map_group_name(gk[1]) if gk[0] == 'map' else gk[1])
    is_map = gk[0] == 'map'
    for parts in chunk_group(es):
        ps, pc = sum(p[3] for p in parts), sum(p[4] for p in parts)
        acc_s, acc_c = sum(p[3] for p in cur_parts), sum(p[4] for p in cur_parts)
        merge = cur_parts and cur_prio == prio and cur_is_map == is_map and (acc_s < MIN_STR or ps < MIN_STR * 0.5) \
            and acc_s + ps <= MAX_STR and acc_c + pc <= MAX_CH
        if not merge:
            flush(cur_parts, ' + '.join(cur_labels), cur_prio, cur_cats)
            cur_parts, cur_labels, cur_cats = [], [], []
        cur_prio, cur_is_map = prio, is_map
        cur_parts += parts
        if not cur_labels or cur_labels[-1] != label:
            cur_labels.append(label)
        keys = {p[0] for p in parts}
        cur_cats += [x['category'] for x in es if x['key'] in keys]
flush(cur_parts, ' + '.join(cur_labels), cur_prio, cur_cats)
for i, bt in enumerate(batches, 1):
    bt['batch'] = f'B{i:03d}'
bank_batches = defaultdict(list)
for bt in batches:
    for p in bt['parts']:
        bank_batches[p['bank']].append(bt['batch'])
for e in banks:
    e['batches'] = sorted(set(bank_batches.get(e['key'], [])))

# ---------------------------------------------------------------- totals
cat_tot = defaultdict(Counter)
for e in banks:
    c = cat_tot[e['category']]
    c['banks'] += 1
    c['strings'] += e['strings']
    c['cjk_strings'] += e['cjk_strings']
    c['cjk_chars'] += e['cjk_chars']
    c['tm_exact'] += e['tm']['exact'] + e['tm']['exact_loose']
    c['tm_fuzzy'] += e['tm']['fuzzy90'] + e['tm']['fuzzy80']
    c['us_likely'] += e['us_reuse']['likely']
    c['us_possible'] += e['us_reuse']['possible']
pr_tot = defaultdict(Counter)
for e in banks:
    pr_tot[e['priority']]['banks'] += 1
    pr_tot[e['priority']]['cjk_strings'] += e['cjk_strings']
    pr_tot[e['priority']]['cjk_chars'] += e['cjk_chars']
out = {
    'description': 'Per-bank manifest for the v4.0.3 English translation. a027 = main message NARC a/0/2/7; '
                   'battle_string = battle/string/battle_string.narc (hack-only). See work/notes/tm_and_manifest.md.',
    'fields': {
        'jp_name': 'Japanese dev name of the bank (Xzonn messages_list; v4 banks 0-813 share the JP/CN layout)',
        'us_bank_guess': 'US a/0/2/7 index (work/extract/us/a027, pret msg_NNNN.gmm) for official English',
        'us_confidence': 'from bank_map_us_v4.json',
        'vanilla_count': 'string count of the vanilla JP bank',
        'tm': 'v3 Eng translation-memory hits (exact/exact_loose usable; fuzzy = review only)',
        'us_reuse': 'per-string vanilla check (us_reuse.jsonl): likely = official US English at us_id reusable',
        'origin': 'vanilla-derived / partly rewritten / hack-rewritten / hack-new (from per-string vanilla check)',
        'priority': 'P0 name lists, P1 core UI/battle/hack notices, P2 story+frequent, P3 side features, '
                    'P4 link/Wi-Fi/debug, skip = no CJK',
    },
    'totals': {'by_category': {k: dict(v) for k, v in sorted(cat_tot.items(), key=lambda x: -x[1]['cjk_chars'])},
               'by_priority': {k: dict(v) for k, v in sorted(pr_tot.items())},
               'batches': len(batches)},
    'banks': banks,
    'batches': batches,
}
json.dump(out, open(os.path.join(OUT, 'manifest.json'), 'w'), ensure_ascii=False, indent=1)
print(len(banks), 'banks,', len(batches), 'batches')
for k, v in out['totals']['by_category'].items():
    print(f"{k:32s} banks={v['banks']:4d} cjk_str={v['cjk_strings']:6d} chars={v['cjk_chars']:7d} tm={v['tm_exact']:5d} us_likely={v['us_likely']:5d}")
print(out['totals']['by_priority'])
