#!/usr/bin/env python3
"""Build work/translate/bank_maps.json: which in-game maps (zones) load each a027 text bank.

Reads the HACK ROM (work/rom/origin_v4.0.3_cn.nds), not the manifest labels:

* arm9 map-header table (pret MapHeader, 24 bytes x 540 zones; located by a structural scan).
  Per zone: msgBank (the a027 bank its map scripts print from), scriptsBank / scriptHeaderBank
  (a/0/1/2), eventsBank (a/0/3/2), matrixId (a/0/4/1), mapsec (location-name id = string id in
  a027/0272), region bit.
* arm9 sScriptBankMapping (30 x {u16 scriptIdLo, u16 scriptBank, u16 msgBank}): the fixed
  script-file/text-bank pairs used by common ("std") scripts, whatever map they run on.
* a/0/3/2 zone events: warps (12-byte records) -> door/stair connectivity.
* a/0/4/1 matrix 0 (overworld): header id per cell -> outdoor adjacency.
* Location names: work/translate/banks/a027/0272.json (zh + our English); vanilla zone constant
  names: work/translate/ref/hgss_map_constants.json (pret; they describe the VANILLA map).

Output (JSON):
  {"_meta": {...},
   "_zones": [{zone_id, vanilla_const, vanilla_dev, map_name_zh, map_name_en, mapsec, region,
               msg_bank, scripts_bank, script_header_bank, events_bank, matrix_id,
               warps_to: [zone ids], outdoor_neighbours: [zone ids], mapsec_changed}],
   "NNNN": [{zone_id, map_name_zh, map_name_en, kind: "map", header: {...}} |
            {zone_id: null, kind: "common_script", script_id_lo, script_id_hi, scripts_bank}]}

Usage: python3 work/translate/scripts/build_bank_maps.py [--rom PATH] [--us-rom PATH] [--out PATH]
Read-only on the workspace; needs ndspy.
"""
import argparse
import json
import os
import struct

import ndspy.codeCompression
import ndspy.narc
import ndspy.rom

WORK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
N_ZONES = 540


def load_arm9(rom):
    a9 = rom.arm9
    try:
        a9 = ndspy.codeCompression.decompress(a9)
    except Exception:
        pass
    return bytes(a9)


def unpack_header(buf, off):
    (wild, area, mm, mat, scr, hdr, msg, day, night, ev, secw, flags) = struct.unpack_from(
        '<BBHHHHHHHHHI', buf, off)
    return {
        'wild_encounter_bank': wild, 'area_data_bank': area,
        'world_map_xy': [(mm >> 4) & 0x3F, (mm >> 10) & 0x3F],
        'matrix_id': mat, 'scripts_bank': scr, 'script_header_bank': hdr, 'msg_bank': msg,
        'day_music': day, 'night_music': night, 'events_bank': ev,
        'mapsec': secw & 0xFF, 'area_icon': (secw >> 8) & 0xF,
        'region': 'kanto' if flags & 1 else 'johto',
        'map_type': ['invalid', 'town', 'route', 'cave', 'interior', 'pokecenter', 'underground',
                     '?7', '?8', '?9', '?10', '?11', '?12', '?13', '?14', '?15'][(flags >> 8) & 0xF],
        'fly_allowed': bool(flags >> 28 & 1),
    }


def find_map_headers(a9):
    """Structural scan: the only run of 540 plausible 24-byte headers in arm9."""
    def plausible(off):
        _, _, _, mat, scr, hdr, msg, day, night, ev, _ = struct.unpack_from('<BBHHHHHHHHH', a9, off)
        return (msg < 1000 and ev < 1000 and mat < 600 and scr < 3000 and hdr < 3000
                and 1000 <= day < 2000 and 1000 <= night < 2000)
    for off in range(0, len(a9) - 24 * N_ZONES, 4):
        if plausible(off) and all(plausible(off + 24 * k) for k in range(1, N_ZONES)):
            if not plausible(off + 24 * N_ZONES):
                return off
    raise SystemExit('map header table not found')


def find_script_bank_mapping(a9):
    """30 x {u16 lo, u16 scr, u16 msg}; lo strictly decreasing from 10490 to 2000 (pret)."""
    for off in range(0, len(a9) - 180, 2):
        rows = [struct.unpack_from('<HHH', a9, off + 6 * k) for k in range(30)]
        if rows[0][0] == 10490 and rows[-1][0] == 2000 and all(
                rows[k][0] > rows[k + 1][0] for k in range(29)):
            return off, rows
    return None, []


def parse_events(b):
    o = 0
    nb = struct.unpack_from('<I', b, o)[0]; o += 4 + nb * 20
    no = struct.unpack_from('<I', b, o)[0]
    _objs = [struct.unpack_from('<HHHHH', b, o + 4 + 32 * i) for i in range(no)]  # id, sprite, move, type, flag
    o += 4 + no * 32
    nw = struct.unpack_from('<I', b, o)[0]
    warps = [struct.unpack_from('<HHHHI', b, o + 4 + 12 * i) for i in range(nw)]
    o += 4 + nw * 12
    nc = struct.unpack_from('<I', b, o)[0]
    return {'bg': nb, 'objects': no, 'warps': warps, 'coords': nc}


def parse_matrix(b):
    w, h, has_hdr, has_alt, nl = b[:5]
    o = 5 + nl
    if not has_hdr:
        return w, h, None
    hdrs = list(struct.unpack_from('<%dH' % (w * h), b, o))
    return w, h, hdrs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default=os.path.join(WORK, 'rom', 'origin_v4.0.3_cn.nds'))
    ap.add_argument('--us-rom', default=os.path.join(WORK, 'rom', 'Pokemon - HeartGold Version (USA).nds'))
    ap.add_argument('--out', default=os.path.join(WORK, 'translate', 'bank_maps.json'))
    a = ap.parse_args()

    rom = ndspy.rom.NintendoDSRom.fromFile(a.rom)
    a9 = load_arm9(rom)
    mh_off = find_map_headers(a9)
    zones = [unpack_header(a9, mh_off + 24 * i) for i in range(N_ZONES)]
    sbm_off, sbm = find_script_bank_mapping(a9)

    us_zones = None
    if a.us_rom and os.path.exists(a.us_rom):
        us = ndspy.rom.NintendoDSRom.fromFile(a.us_rom)
        ua9 = load_arm9(us)
        uoff = find_map_headers(ua9)
        us_zones = [unpack_header(ua9, uoff + 24 * i) for i in range(N_ZONES)]

    consts = {z['zone_id']: z for z in json.load(open(os.path.join(WORK, 'translate', 'ref', 'hgss_map_constants.json')))['zones']}
    locws = json.load(open(os.path.join(WORK, 'translate', 'banks', 'a027', '0272.json'), encoding='utf-8'))
    loc = {s['id']: (s['zh'], s['en']) for s in locws['strings']}

    us_loc = {}
    usp = os.path.join(WORK, 'extract', 'us', 'a027', '0279.json')  # US location names
    if os.path.exists(usp):
        us_loc = {x['id']: x['text'] for x in json.load(open(usp, encoding='utf-8'))['strings']}

    evn = ndspy.narc.NARC(rom.getFileByName('a/0/3/2'))
    mtx = ndspy.narc.NARC(rom.getFileByName('a/0/4/1'))

    # outdoor adjacency from the overworld matrix (and any other matrix with a header layer)
    neigh = {i: set() for i in range(N_ZONES)}
    for mi, mb in enumerate(mtx.files):
        w, h, hdrs = parse_matrix(mb)
        if not hdrs:
            continue
        for y in range(h):
            for x in range(w):
                z = hdrs[y * w + x]
                for dx, dy in ((1, 0), (0, 1)):
                    if x + dx < w and y + dy < h:
                        z2 = hdrs[(y + dy) * w + x + dx]
                        if z != z2 and 0 < z < N_ZONES and 0 < z2 < N_ZONES:
                            neigh[z].add(z2)
                            neigh[z2].add(z)

    zlist = []
    for i, z in enumerate(zones):
        zh, en = loc.get(z['mapsec'], (None, None))
        try:
            ev = parse_events(evn.files[z['events_bank']])
        except Exception:
            ev = {'warps': [], 'objects': None}
        rec = {
            'zone_id': i,
            'vanilla_const': consts.get(i, {}).get('const'),
            'vanilla_dev': consts.get(i, {}).get('dev'),
            'map_name_zh': zh, 'map_name_en': en,
            **z,
            'warps_to': sorted({w[2] for w in ev['warps'] if w[2] < N_ZONES}),
            'outdoor_neighbours': sorted(neigh[i]),
            'n_objects': ev.get('objects'),
        }
        if us_zones:
            rec['mapsec_changed'] = us_zones[i]['mapsec'] != z['mapsec']
            vs = us_zones[i]['mapsec']
            rec['vanilla_mapsec'] = vs
            rec['vanilla_map_name_en'] = us_loc.get(vs)
        zlist.append(rec)

    out = {'_meta': {
        'source_rom': os.path.relpath(a.rom, WORK),
        'map_header_table_arm9_offset': mh_off,
        'script_bank_mapping_arm9_offset': sbm_off,
        'note': ('Keys "NNNN" are a027 bank numbers (v4 numbering). A bank is listed under a zone '
                 'when that zone\'s map header loads it (msg_bank): the map\'s own scripts print '
                 'from it. map_name_* is the hack\'s location name (mapsec), which is what the '
                 'player sees; vanilla_const is the pret name of the vanilla map the hack reused. '
                 'kind=common_script rows are the fixed std-script text banks (sScriptBankMapping).'),
    }, '_zones': zlist}
    banks = {}
    for r in zlist:
        if r['zone_id'] < 2:  # MAP_EVERYWHERE / MAP_NOTHING dummies
            continue
        banks.setdefault('%04d' % r['msg_bank'], []).append({
            'zone_id': r['zone_id'], 'kind': 'map',
            'map_name_zh': r['map_name_zh'], 'map_name_en': r['map_name_en'],
            'vanilla_const': r['vanilla_const'],
            'header': {k: r[k] for k in ('mapsec', 'region', 'map_type', 'scripts_bank',
                                         'script_header_bank', 'events_bank', 'matrix_id')},
        })
    for k, (lo, scr, msg) in enumerate(sbm):
        hi = sbm[k - 1][0] - 1 if k else 10499
        banks.setdefault('%04d' % msg, []).append({
            'zone_id': None, 'kind': 'common_script', 'script_id_lo': lo, 'script_id_hi': hi,
            'scripts_bank': scr, 'map_name_zh': None, 'map_name_en': '(common script, any map)'})
    out.update(dict(sorted(banks.items())))
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('zones', len(zlist), 'banks', len(banks), 'map-header table @', hex(mh_off),
          'std mapping @', hex(sbm_off) if sbm_off is not None else None, '->', a.out)


if __name__ == '__main__':
    main()
