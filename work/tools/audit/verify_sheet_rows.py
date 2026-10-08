#!/usr/bin/env python3
"""Independent re-check of the spreadsheet cross-check rows (work/notes/spreadsheet_crossref.md).

AUDIT TOOL. It deliberately shares no parsing code with work/tools/docs/romdata.py or gen_docs.py:
every record layout below is written out here from the public format descriptions, and every
hack-specific layout is first validated against the untouched US HeartGold ROM.

Usage:
  python3 work/tools/audit/verify_sheet_rows.py --v4 <fresh v4.nds> --v3 <fresh v3.nds> \
      --us <US.nds> --out <result.json>

Format references (cited per parser):
  [pret-personal]  pret/pokeheartgold include/pokemon.h `BaseStats` (44 bytes): 0 hp, 1 atk, 2 def,
                   3 speed, 4 spatk, 5 spdef, 6/7 types, 8 catch rate, 9 base exp, 0xA ev word,
                   0xC/0xE items, 0x10 gender, 0x11 egg cycles, 0x12 friendship, 0x13 growth,
                   0x14/0x15 egg groups, 0x16/0x17 abilities (u8), 0x18 run chance, 0x19 colour/flip,
                   0x1C.. TM bits. v4 record is 52 bytes: same 0x00-0x15, abilities widened to u16 at
                   0x16/0x18 and a third (hidden) u16 at 0x1A. Validated below against US Bulbasaur..Arceus.
  [pret-evo]       pret include/pokemon.h `struct Evolution {u16 method; u16 param; u16 target;}`, 7 per
                   species in HGSS (v4 file: 10 per species, 60 bytes). Method ids pret
                   include/constants/pokemon.h EVO_*; ids > 26 are the hack's own (named by use below).
  [bw-move]        Gen 5 move record (Project Pokemon "BW move data structure", as used by pk3DS / PKHeX
                   PersonalInfo-era tools): 0 type, 1 quality, 2 category, 3 power, 4 accuracy, 5 pp,
                   6 priority (s8), 7 hits, 8-9 inflicted condition, 10 condition chance, 11-13 kind/turns,
                   14 crit stage, 15 flinch, 16-17 effect sequence, 18 recoil/drain, 19 heal, 20 target,
                   21-29 stat changes, 32-35 flags. v4 extra/new_move_data.narc uses it (40 bytes).
                   Validated below against US a/0/1/1.
  [pret-move]      pret include/move_data.h `MoveTbl` (16 bytes): u16 effect, u8 class, u8 power, u8 type,
                   u8 accuracy, u8 pp, u8 effect chance, u16 target, s8 priority, u8 flags, u8 contest...
  [pret-enc]       pret include/wild_encounter.h / src/wild_encounter.c HGSS `ENC_DATA` (0xC4 bytes):
                   0 land rate, 1 surf, 2 rock smash, 3 old, 4 good, 5 super rod rate, 8 land levels[12],
                   0x14 morning[12] u16, 0x2C day[12], 0x44 night[12], 0x5C hoenn[2], 0x60 sinnoh[2],
                   0x64 surf 5x{u8 min,u8 max,u16 species}, 0x78 rock[2], 0x80 old[5], 0x94 good[5],
                   0xA8 super[5], 0xBC swarm species[4]. Species u16: low 11 bits species, high 5 form (hack).
  [pret-maphdr]    pret include/map_header.h `MapHeader` (24 bytes): 0 wild encounter bank (u8, 0xFF none),
                   1 area data, 2-3 move model/..., 4 matrix, 6 scripts, 8 script header, 0xA msg bank,
                   0xC/0xE music, 0x10 events bank, 0x12 mapsec, ...
  [pret-script]    pret asm/macros/script.inc command numbers: 20 CallStd, 40 SubVar, 41 SetVar,
                   43 SetOrCopyVar, 125 GiveItem(item,qty,result), 126 TakeItem, 128 HasItem,
                   139 SetMonMove, 276 SpecialMartBuy, 468 MoveTutorInit, 653-655 tutor commands.
  [pret-msg]       Gen 4 message file (pret tools/msgenc): u16 count, u16 seed; entry i (off,len) xor
                   k|k<<16 with k=(seed*0x2FD*(i+1))&0xFFFF; chars xor key0=(0x91BD3*(i+1))&0xFFFF,
                   key += 0x493D per char; 0xFFFF end, 0xFFFE control (u16 cmd, u16 n, n args).
"""
import argparse
import json
import os
import pickle
import struct

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
CHARMAP = os.path.join(REPO, 'work', 'tools', 'charmaps', 'charmap_zh_xzonn_gen4.tsv')
NEED = ['a/0/0/2', 'a/0/3/4', 'a/0/1/1', 'a/0/3/7', 'a/0/1/2', 'a/0/3/2', 'a/0/1/7', 'a/0/2/7',
        'extra/new_move_data.narc']
A9 = 0x02000000


# ------------------------------------------------------------------ loading
def load_rom(path, cache_dir):
    """Return {'arm9', 'ovl': {id: bytes}, narc path: [members]} for one ROM (cached by size+mtime)."""
    st = os.stat(path)
    key = os.path.join(cache_dir, 'vsr_%s_%d_%d.pkl' % (os.path.basename(path), st.st_size, int(st.st_mtime)))
    if os.path.exists(key):
        return pickle.load(open(key, 'rb'))
    import ndspy.rom
    import ndspy.narc
    rom = ndspy.rom.NintendoDSRom.fromFile(path)
    out = {'arm9': bytes(rom.arm9), 'ovl': {k: bytes(v.data) for k, v in rom.loadArm9Overlays().items()}}
    for n in NEED:
        try:
            data = rom.getFileByName(n)
        except Exception:
            continue
        out[n] = [bytes(x) for x in ndspy.narc.NARC(data).files]
    pickle.dump(out, open(key, 'wb'))
    return out


# ------------------------------------------------------------------ text [pret-msg]
CHARMAP_V3 = os.path.join(REPO, 'work', 'tools', 'charmaps', 'charmap_zh_acg_hgss.tsv')
_CM = {}


def charmap(path=CHARMAP):
    if path not in _CM:
        cm = _CM[path] = {}
        for line in open(path, encoding='utf-8'):
            if line.startswith('#') or '\t' not in line:
                continue
            code, txt = line.rstrip('\n').split('\t', 1)
            cm[int(code, 16)] = txt
    return _CM[path]


def decode_bank(b, cmap=CHARMAP):
    """Decode one message file to a list of strings (controls as {XXXX:args})."""
    n, seed = struct.unpack_from('<HH', b, 0)
    cm = charmap(cmap)
    out = []
    for i in range(n):
        k = (seed * 0x2FD * (i + 1)) & 0xFFFF
        k32 = k | (k << 16)
        off, ln = struct.unpack_from('<II', b, 4 + 8 * i)
        off ^= k32
        ln ^= k32
        key = (0x91BD3 * (i + 1)) & 0xFFFF
        units = []
        for j in range(ln):
            c = struct.unpack_from('<H', b, off + 2 * j)[0] ^ key
            key = (key + 0x493D) & 0xFFFF
            units.append(c)
        s = []
        j = 0
        while j < len(units):
            c = units[j]
            if c == 0xFFFF:
                break
            if c == 0xFFFE:
                cmd, na = units[j + 1], units[j + 2]
                s.append('{%04X:%s}' % (cmd, ','.join(str(x) for x in units[j + 3:j + 3 + na])))
                j += 3 + na
                continue
            if c == 0xF100:
                s.append('{COMPRESSED}')
                break
            s.append(cm.get(c, '{U+%04X}' % c))
            j += 1
        out.append(''.join(s))
    return out


# ------------------------------------------------------------------ records
def personal_v4(b):
    """[pret-personal] with the v4 widening. Returns stats in sheet order HP/Atk/Def/SpA/SpD/Spe."""
    hp, at, df, sp, sa, sd = b[0:6]
    ab = struct.unpack_from('<3H', b, 0x16)
    return dict(stats=[hp, at, df, sa, sd, sp], types=[b[6], b[7]], abilities=list(ab))


def personal_v3(b):
    """[pret-personal] vanilla 44-byte record (v3 and US)."""
    hp, at, df, sp, sa, sd = b[0:6]
    return dict(stats=[hp, at, df, sa, sd, sp], types=[b[6], b[7]], abilities=[b[0x16], b[0x17], None])


def evos(b):
    """[pret-evo] list of (method, param, target)."""
    out = []
    for k in range(len(b) // 6):
        m, p, t = struct.unpack_from('<3H', b, 6 * k)
        if m or p or t:
            out.append((m, p, t))
    return out


def move_bw(b):
    """[bw-move]"""
    return dict(type=b[0], quality=b[1], category=b[2], power=b[3], accuracy=b[4], pp=b[5],
                priority=struct.unpack_from('<b', b, 6)[0], crit=b[14], flinch=b[15],
                effect=struct.unpack_from('<H', b, 16)[0], target=b[20],
                flags=struct.unpack_from('<I', b, 32)[0])


def move_pret(b):
    """[pret-move]"""
    eff, cls, pw, ty, acc, pp, ch, tgt, pri, fl = struct.unpack_from('<HBBBBBBHbB', b, 0)
    return dict(effect=eff, category=cls, power=pw, type=ty, accuracy=acc, pp=pp, chance=ch,
                target=tgt, priority=pri, flags=fl)


def enc_record(b):
    """[pret-enc]"""
    def slots(off, n):
        return [dict(min=b[off + 4 * i], max=b[off + 4 * i + 1],
                     species=struct.unpack_from('<H', b, off + 4 * i + 2)[0]) for i in range(n)]
    lv = list(b[8:20])
    land = lambda off: [dict(level=lv[i], species=struct.unpack_from('<H', b, off + 2 * i)[0]) for i in range(12)]
    return dict(rates=list(b[0:6]), morning=land(0x14), day=land(0x2C), night=land(0x44),
                surf=slots(0x64, 5), rock=slots(0x78, 2), old=slots(0x80, 5), good=slots(0x94, 5),
                super=slots(0xA8, 5))


def sp_form(v):
    return v & 0x7FF, v >> 11


TYPES_ZH = ['普', '斗', '飞', '毒', '地', '岩', '虫', '鬼', '钢', '妖', '火', '水', '草', '电', '超', '冰', '龙', '恶']
TYPES_EN = ['Normal', 'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug', 'Ghost', 'Steel', 'Fairy',
            'Fire', 'Water', 'Grass', 'Electric', 'Psychic', 'Ice', 'Dragon', 'Dark']


def find_form_table(a9):
    """Locate {u16 species, u16 personal index, u16 form} runs by structure alone (no fixed address)."""
    best = (0, 0)
    for start in range(0, len(a9) - 6, 2):
        if best[0] and start < best[1] + 6 * best[0]:
            continue
        n, o = 0, start
        while o + 6 <= len(a9):
            sp, idx, f = struct.unpack_from('<3H', a9, o)
            if 0 < sp < 1100 and 494 <= idx < 2000 and 1 <= f < 64:
                n += 1
                o += 6
            else:
                break
        if n > best[0]:
            best = (n, start)
    n, start = best
    return start, [struct.unpack_from('<3H', a9, start + 6 * i) for i in range(n)]


class Game:
    """One ROM, with name lookups decoded by this file's own text decoder."""

    def __init__(self, data, v4=True, cmap=CHARMAP):
        self.d = data
        self.v4 = v4
        self.cmap = cmap
        self.text = {}
        if v4:
            self.form_addr, self.forms = find_form_table(data['arm9'])
        else:
            self.form_addr, self.forms = None, []

    def bank(self, n):
        if n not in self.text:
            self.text[n] = [s.replace('{U+E000}', '\\n') for s in decode_bank(self.d['a/0/2/7'][n], self.cmap)]
        return self.text[n]

    def species_ids(self, zh):
        return [i for i, s in enumerate(self.bank(232)) if s == zh]

    def move_ids(self, zh):
        return [i for i, s in enumerate(self.bank(739)) if s == zh]

    def item_ids(self, zh):
        return [i for i, s in enumerate(self.bank(219)) if s == zh]

    def personal(self, idx):
        recs = self.d['a/0/0/2']
        if idx >= len(recs):
            return None
        return (personal_v4 if self.v4 else personal_v3)(recs[idx])

    def form_records(self, sp):
        """[(form, personal index)] including form 0."""
        out = [(0, sp)]
        if self.v4:
            out += [(f, idx) for s, idx, f in self.forms if s == sp]
        return out

    def ability_name(self, a):
        if a is None:
            return None
        names = self.bank(711)
        return names[a] if a < len(names) else '#%d (no name string)' % a

    def type_name(self, t):
        return TYPES_EN[t] if t < len(TYPES_EN) else '#%d' % t


# ------------------------------------------------------------------ sheets (read directly)
SHEET_POKE = os.path.join(REPO, 'Pokémon Origin HeartGold v4.0.3 Cn List of Pokemons.xlsx')
SHEET_ENC = os.path.join(REPO, 'Pokémon Origin HeartGold v4.0.3 Cn Encounters.xlsx')
SHEET_ITEMS = os.path.join(REPO, 'Pokémon Origin HeartGold v4.0.3 Cn Items.xlsx')
_WB = {}


def sheet_rows(path, name):
    if (path, name) not in _WB:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        _WB[(path, name)] = [None] + [tuple(r) for r in wb[name].iter_rows(values_only=True)]
    return _WB[(path, name)]


# rows of spreadsheet_crossref.md §1.1 (class a and b)
SPECIES_ROWS = [10, 30, 32, 61, 79, 84, 85, 93, 155, 246, 289, 304, 325, 379, 404, 417, 418, 430, 461, 462,
                473, 494, 511, 513, 517, 518, 519, 528, 529, 554, 597, 630, 654, 676, 680, 731, 747]
STAT_NAMES = ['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe']


def base_name(n):
    for ch in '（(':
        if ch in n:
            n = n[:n.index(ch)]
    return n.strip()


def species_view(g, sp):
    out = []
    for form, idx in g.form_records(sp):
        p = g.personal(idx)
        if p is None:
            continue
        out.append(dict(form=form, index=idx, stats=p['stats'],
                        types=sorted(set(g.type_name(t) for t in p['types'])),
                        abilities=[g.ability_name(a) for a in p['abilities']],
                        ability_ids=p['abilities']))
    return out


def sheet_species(row):
    r = sheet_rows(SHEET_POKE, '4.0精灵数据')[row]
    types = sorted(set(TYPES_EN[TYPES_ZH.index(t)] for t in r[5:7] if t))
    return dict(row=row, name=r[1], abilities=list(r[2:5]), types=types, stats=list(r[7:13]), evo=r[14])


def check_species(g4, g3, v3_forms):
    res = []
    for row in SPECIES_ROWS:
        sh = sheet_species(row)
        ids = g4.species_ids(base_name(sh['name']))
        sp = ids[0] if ids else None
        v4 = species_view(g4, sp) if sp else []
        # v3: vanilla national ids (<=493) plus pret's fixed form records 496-507 (+508)
        v3 = []
        if sp and sp < len(g3.d['a/0/0/2']) and sp <= 493:
            v3 = species_view(g3, sp)
            for f, idx in v3_forms.get(sp, []):
                p = g3.personal(idx)
                v3.append(dict(form=f, index=idx, stats=p['stats'],
                               types=sorted(set(g3.type_name(t) for t in p['types'])),
                               abilities=[g3.ability_name(a) for a in p['abilities']]))

        def diff(rec):
            d = {}
            for k, n in enumerate(STAT_NAMES):
                if sh['stats'][k] != rec['stats'][k]:
                    d[n] = (sh['stats'][k], rec['stats'][k])
            if sh['types'] != rec['types']:
                d['types'] = (sh['types'], rec['types'])
            for k, n in enumerate(['ability1', 'ability2', 'hidden']):
                ra = rec['abilities'][k] if k < len(rec['abilities']) else None
                if ra is not None and sh['abilities'][k] != ra:
                    d[n] = (sh['abilities'][k], ra)
            return d
        for rec in v4 + v3:
            rec['diff'] = diff(rec)
        res.append(dict(sheet=sh, species=sp, en=None, v4=v4, v3=v3))
    return res


def find_map_headers(a9, n_enc, n_scr, n_msg, n_evt):
    """[pret-maphdr] locate the 24-byte header table by structure alone; return (offset, headers)."""
    def ok(o):
        w = a9[o]
        sc, sh, msg = struct.unpack_from('<HHH', a9, o + 6)
        ev = struct.unpack_from('<H', a9, o + 0x10)[0]
        return (w < n_enc or w == 0xFF) and sc < n_scr and sh < n_scr and msg < n_msg and ev < n_evt
    best = (0, 0)
    s = 0
    while s < len(a9) - 24:
        n, o = 0, s
        while o + 24 <= len(a9) and ok(o):
            n += 1
            o += 24
        if n > best[0]:
            best = (n, s)
        s += 4
    n, s = best
    return s, [dict(wild=a9[s + 24 * i], scripts=struct.unpack_from('<H', a9, s + 24 * i + 6)[0],
                    msg=struct.unpack_from('<H', a9, s + 24 * i + 10)[0],
                    events=struct.unpack_from('<H', a9, s + 24 * i + 0x10)[0],
                    mapsec=struct.unpack_from('<H', a9, s + 24 * i + 0x12)[0]) for i in range(n)]


# ------------------------------------------------------------------ item sources
OP_GIVEITEM, OP_TAKEITEM, OP_HASITEM = 125, 126, 128
OP_SETVAR, OP_SETORCOPY = 41, 43
OP_MARTBUY, OP_SPECIALMART = 275, 276


def scan_scripts(files, n_items):
    """Raw byte-pattern scan of every script file at every byte offset [pret-script].

    Over-inclusive on purpose (a pattern inside unrelated data also counts), so an empty result is a
    strong 'no source' statement. Returns {item: [(kind, file, offset, extra)]} and mart ids per file."""
    give, marts = {}, {}
    for fi, b in enumerate(files):
        for o in range(0, len(b) - 5):
            op = b[o] | (b[o + 1] << 8)
            if op == OP_GIVEITEM and o + 8 <= len(b):
                it, q = struct.unpack_from('<HH', b, o + 2)
                if 0 < it < n_items:
                    give.setdefault(it, []).append(('GiveItem', fi, o, q))
            elif op in (OP_SETVAR, OP_SETORCOPY) and o + 6 <= len(b):
                var, val = struct.unpack_from('<HH', b, o + 2)
                if 0x4000 <= var < 0x8100 and 0 < val < n_items:
                    give.setdefault(val, []).append(('SetVar%04X' % var, fi, o, None))
            elif op in (OP_TAKEITEM, OP_HASITEM) and o + 8 <= len(b):
                it, q = struct.unpack_from('<HH', b, o + 2)
                if 0 < it < n_items:
                    give.setdefault(it, []).append(('TakeItem' if op == OP_TAKEITEM else 'HasItem', fi, o, q))
            elif op in (OP_SPECIALMART, OP_MARTBUY) and o + 4 <= len(b):
                mid = struct.unpack_from('<H', b, o + 2)[0]
                marts.setdefault(fi, []).append((op, mid, o))
    return give, marts


def find_hidden_items(a9, n_items):
    """{u16 item, u8 qty, u8 unk, u16 unk, u16 flag index} records (pret HGSS `HiddenItem` table read by
    the hidden-item bg events). Located by structure alone: the longest run of records with a valid item,
    qty 1-99, zero padding and a flag index < 1000, all flag indices distinct."""
    best = (0, 0)
    s = 0
    while s < len(a9) - 8:
        n, o, seen = 0, s, set()
        while o + 8 <= len(a9):
            it, q, a, b, idx = struct.unpack_from('<HBBHH', a9, o)
            if not (0 < it < n_items and 0 < q < 100 and a == 0 and b == 0 and idx < 1000 and idx not in seen):
                break
            seen.add(idx)
            n += 1
            o += 8
        if n > best[0]:
            best = (n, s)
        s += 2
    n, s = best
    return s, [struct.unpack_from('<HBBHH', a9, s + 8 * i) for i in range(n)]


def find_special_marts(a9, n_items):
    """Pointer table (u32 into arm9) of 0xFFFF-terminated u16 item lists, read by SpecialMartBuy
    (pret scrcmd_shop.c sMartSpecialItems). Located by structure alone."""
    def lst(p):
        o = p - A9
        if not (0 <= o < len(a9) - 2) or o & 1:
            return None
        out = []
        while o + 2 <= len(a9) and len(out) < 64:
            v = struct.unpack_from('<H', a9, o)[0]
            if v == 0xFFFF:
                return out if out else None
            if not (0 < v < n_items):
                return None
            out.append(v)
            o += 2
        return None
    best = (0, 0)
    for s in range(0, len(a9) - 4, 4):
        n, o = 0, s
        while o + 4 <= len(a9):
            p = struct.unpack_from('<I', a9, o)[0]
            if not (A9 <= p < A9 + len(a9)) or lst(p) is None:
                break
            n += 1
            o += 4
        if n > best[0]:
            best = (n, s)
        if n > 20:
            pass
    n, s = best
    return s, [lst(struct.unpack_from('<I', a9, s + 4 * i)[0]) for i in range(n)]


def find_badge_mart(a9, n_items):
    """{u16 item, u16 badges needed} list read by MartBuy (pret scrcmd_shop.c sNormalMartItems):
    vanilla starts with Poké Ball (4) needing 1 badge. Located by the longest run of such pairs whose
    badge count never decreases and starts at Poke Ball."""
    best = (0, 0)
    for s in range(0, len(a9) - 4, 2):
        if struct.unpack_from('<HH', a9, s) != (4, 1):
            continue
        n, o = 0, s
        while o + 4 <= len(a9):
            it, bd = struct.unpack_from('<HH', a9, o)
            if not (0 < it < n_items and bd <= 16):
                break
            n += 1
            o += 4
        if n > best[0]:
            best = (n, s)
    n, s = best
    return s, [struct.unpack_from('<HH', a9, s + 4 * i) for i in range(n)]


def find_std_mapping(a9, n_scr, n_msg):
    """{u16 first script id, u16 script file, u16 msg bank} table (pret fieldmap.c sScriptBankMapping),
    located as the longest run with strictly descending/ascending first ids that contains 7000."""
    best = (0, 0)
    for s in range(0, len(a9) - 6, 2):
        n, o, prev, vals = 0, s, None, []
        while o + 6 <= len(a9):
            lo, f, m = struct.unpack_from('<3H', a9, o)
            if not (f < n_scr and m < n_msg and lo < 20000 and (prev is None or lo != prev)):
                break
            vals.append(lo)
            prev = lo
            n += 1
            o += 6
        if n > best[0] and 7000 in vals and 8000 in vals:
            best = (n, s)
    n, s = best
    return s, [struct.unpack_from('<3H', a9, s + 6 * i) for i in range(n)]


def parse_events(b):
    """pret HGSS map events file: u32 nBG + 20-byte BgEvent {u16 script, u16 type, s32 x, s32 z, s32 y,
    u16 dir, u16 pad}; u32 nObj + 32-byte ObjectEvent {u16 id, sprite, movement, type, flag, script, ...,
    u16 x @0x18, u16 y @0x1A, s32 z}; then warps and coord events (not needed)."""
    o = 0
    nbg = struct.unpack_from('<I', b, o)[0]
    o += 4
    bgs = [dict(script=struct.unpack_from('<H', b, o + 20 * i)[0]) for i in range(nbg)]
    o += 20 * nbg
    nobj = struct.unpack_from('<I', b, o)[0]
    o += 4
    objs = []
    for i in range(nobj):
        r = struct.unpack_from('<6H', b, o + 32 * i)
        objs.append(dict(id=r[0], sprite=r[1], flag=r[4], script=r[5]))
    return dict(bg=bgs, obj=objs)


def script_offsets(b):
    """Script entry table: u32 relative offsets until the 0xFD13 marker (pret script header)."""
    out, o = [], 0
    while o + 2 <= len(b) and struct.unpack_from('<H', b, o)[0] != 0xFD13 and o + 4 <= len(b):
        out.append(o + 4 + struct.unpack_from('<i', b, o)[0])
        o += 4
    return out


# pret asm/macros/script.inc argument sizes, as tabulated (data only) in work/tools/docs/script_cmds.json.
CMDS = {int(k): v for k, v in json.load(open(os.path.join(REPO, 'work', 'tools', 'docs', 'script_cmds.json'))).items()}
JUMPS = {'GoTo': 0, 'Call': 0, 'GoToIf': 1, 'CallIf': 1, 'ObjectGoTo': 1, 'BGGoTo': 1, 'DirectionGoTo': 1}


def walk(b, entries):
    """Reachable instructions from the entry points, with straight-line constant propagation of SetVar.
    Returns {offset: (name, args, next, vars-at-this-point)}."""
    ins = {}
    todo = [(o, {}) for o in entries]
    visits = {}
    while todo:
        o, env = todo.pop()
        env = dict(env)
        while 0 <= o and o + 2 <= len(b):
            key = (o, tuple(sorted(env.items())))
            if visits.get(o, 0) > 8 or key in visits:
                break
            visits[key] = 1
            visits[o] = visits.get(o, 0) + 1
            op = struct.unpack_from('<H', b, o)[0]
            if op not in CMDS:
                break
            name, sz = CMDS[op]
            a, p = [], o + 2
            for n in sz:
                a.append(int.from_bytes(b[p:p + n], 'little', signed=(n == 4)))
                p += n
            if o not in ins:
                ins[o] = (name, a, p, dict(env))
            if name == 'SetVar' and 0x4000 <= a[0]:
                env[a[0]] = a[1] if a[1] < 0x4000 else None
            if name in JUMPS:
                todo.append((p + a[JUMPS[name]], env))
            if name in ('End', 'Return', 'GoTo'):
                break
            o = p
    return ins


def find_mart_override(a9, table_off, n_items):
    """The hack's SpecialMartBuy (v4 arm9 0x0204787C) does `if (id == 3) list = <hardcoded>; else list =
    table[id]`. Find that: the literal-pool word pointing at the special-mart table, then, in the 0x54 bytes
    of Thumb code before it, a `cmp r2,#imm` (0x2Axx) and a `ldr r2,=X` (0x4Axx) whose X is not the table.
    Returns {id: [items]} (empty when the command has no such special case, as in v3)."""
    T = A9 + table_off
    out = {}
    for L in range(0, len(a9) - 4, 4):
        if struct.unpack_from('<I', a9, L)[0] != T:
            continue
        cmp_imm, other = None, None
        for x in range(L - 0x54, L, 2):
            h = struct.unpack_from('<H', a9, x)[0]
            if h >> 8 == 0x2A:
                cmp_imm = h & 0xFF
            if h >> 8 == 0x4A:
                pa = ((x + A9 + 4) & ~3) + (h & 0xFF) * 4
                v = struct.unpack_from('<I', a9, pa - A9)[0]
                if v != T and A9 <= v < A9 + len(a9):
                    other = v
        if cmp_imm is not None and other is not None:
            o, lst = other - A9, []
            while struct.unpack_from('<H', a9, o)[0] != 0xFFFF and len(lst) < 64:
                lst.append(struct.unpack_from('<H', a9, o)[0])
                o += 2
            out[cmp_imm] = lst
    return out


class ItemIndex:
    """Every fixed item source in one ROM, placed on maps where possible (reachable script code only)."""

    def __init__(self, g):
        d = g.d
        self.g = g
        a9 = d['arm9']
        self.n_items = len(d['a/0/1/7'])
        scr, msg, evt = d['a/0/1/2'], d['a/0/2/7'], d['a/0/3/2']
        self.hdr_off, self.hdr = find_map_headers(a9, len(d['a/0/3/7']), len(scr), len(msg), len(evt))
        self.hidden_off, self.hidden = find_hidden_items(a9, self.n_items)
        self.marts_off, self.marts = find_special_marts(a9, self.n_items)
        self.badge_off, self.badge = find_badge_mart(a9, self.n_items)
        self.mart_override = find_mart_override(a9, self.marts_off, self.n_items)
        self.table_marts = list(self.marts)
        for k, lst in self.mart_override.items():
            self.marts[k] = lst
        self.std_off, self.std = find_std_mapping(a9, len(scr), len(msg))
        self.ball_file = [f for lo, f, m in self.std if lo == 7000][0]
        self.raw_give, _ = scan_scripts(scr, self.n_items)
        self.locnames = g.bank(272)
        self.file_maps, self.evt_maps = {}, {}
        for m, h in enumerate(self.hdr):
            self.file_maps.setdefault(h['scripts'], []).append(m)
            self.evt_maps.setdefault(h['events'], []).append(m)
        # std scripts (CallStd n -> file of the highest std-table 'first id' <= n, entry n - first id):
        # which item command each one reaches with a variable argument
        self.std_effect = {}
        rng = sorted((lo, f) for lo, f, m in self.std if 2000 <= lo < 3000)
        for i, (lo, f) in enumerate(rng):
            hi = rng[i + 1][0] if i + 1 < len(rng) else 3000
            offs = script_offsets(scr[f])
            for k, o in enumerate(offs):
                if lo + k >= hi:
                    break
                eff = set()
                for name, a, p, env in walk(scr[f], [o]).values():
                    if name in ('GiveItem', 'TakeItem', 'HasItem') and a[0] >= 0x4000:
                        eff.add((name, a[0], a[1]))
                    elif name in ('SpecialMartBuy', 'MartBuy') and a[0] >= 0x4000:
                        eff.add((name, a[0], None))
                if eff:
                    self.std_effect[lo + k] = sorted(eff)
        # reachable item commands per script file
        self.give, self.mart_use, self.std_called = {}, {}, set()
        for fi, b in enumerate(scr):
            if fi == 3:
                continue
            try:
                ins = walk(b, script_offsets(b))
            except Exception:
                continue
            for o, (name, a, p, env) in ins.items():
                if name in ('GiveItem', 'TakeItem', 'HasItem'):
                    it = a[0] if a[0] < 0x4000 else env.get(a[0])
                    if it and 0 < it < self.n_items:
                        self.give.setdefault(it, []).append((name, fi, o, a[1]))
                elif name == 'SpecialMartBuy':
                    mid = a[0] if a[0] < 0x4000 else env.get(a[0])
                    self.mart_use.setdefault(mid, []).append((fi, o))
                elif name == 'CallStd':
                    self.std_called.add(a[0])
                if name == 'CallStd' and a[0] in self.std_effect:
                    for kind, var, qv in self.std_effect[a[0]]:
                        v = env.get(var)
                        if kind == 'SpecialMartBuy':
                            self.mart_use.setdefault(v, []).append((fi, o))
                        elif kind != 'MartBuy' and v and 0 < v < self.n_items:
                            self.give.setdefault(v, []).append(('std%d:%s' % (a[0], kind), fi, o, env.get(qv, qv)))
        # item balls: object script 7000+k -> entry k of the item-ball script file; first SetVar value = item
        bf = scr[self.ball_file]
        self.ball_item = {}
        for k, o in enumerate(script_offsets(bf)):
            for p in range(o, min(o + 24, len(bf) - 5)):
                if bf[p] | (bf[p + 1] << 8) == OP_SETVAR:
                    var, val = struct.unpack_from('<HH', bf, p + 2)
                    if 0 < val < self.n_items:
                        self.ball_item[k] = val
                        break
        self.balls, self.hidden_on = {}, {}
        for e, b in enumerate(evt):
            try:
                ev = parse_events(b)
            except struct.error:
                continue
            for ob in ev['obj']:
                if 7000 <= ob['script'] < 8000 and ob['script'] - 7000 in self.ball_item:
                    self.balls.setdefault(self.ball_item[ob['script'] - 7000], []).append(e)
            # the game looks the bg script (8000+n) up by the record's flag-index field, not by position:
            # arm9 0x0203FCB4 / 0x0203FCF0 loop over the 231 records comparing ldrh [rec,#6] with script-8000
            by_index = {h[4]: h for h in self.hidden}
            for bg in ev['bg']:
                if 8000 <= bg['script'] < 8800 and bg['script'] - 8000 in by_index:
                    self.hidden_on.setdefault(by_index[bg['script'] - 8000][0], []).append(e)

    def map_name(self, m):
        ms = self.hdr[m]['mapsec'] & 0xFF
        return '%d:%s' % (m, self.locnames[ms] if ms < len(self.locnames) else '?')

    def maps_of_file(self, fi):
        return [self.map_name(m) for m in self.file_maps.get(fi, [])] or ['script file %d (no map header)' % fi]

    def maps_of_events(self, e):
        return [self.map_name(m) for m in self.evt_maps.get(e, [])] or ['events %d' % e]

    def sources(self, item, raw=False):
        out = []
        for e in self.balls.get(item, []):
            out.append(('item ball', self.maps_of_events(e)))
        for e in self.hidden_on.get(item, []):
            out.append(('hidden', self.maps_of_events(e)))
        if any(h[0] == item for h in self.hidden) and not self.hidden_on.get(item):
            out.append(('hidden-table entry without bg event', []))
        for kind, fi, o, q in (self.raw_give if raw else self.give).get(item, []):
            if fi == self.ball_file:
                continue
            out.append(('%s a/0/1/2[%d]+0x%X' % (kind, fi, o), self.maps_of_file(fi)))
        for j, lst in enumerate(self.marts):
            if lst and item in lst:
                where = sorted(set(m for fi, o in self.mart_use.get(j, []) for m in self.maps_of_file(fi)))
                out.append(('SpecialMartBuy list %d' % j, where or ['(no reachable SpecialMartBuy uses this list)']))
        # the badge-tier MartBuy list is only reachable through std 2048-2050, which no v3/v4 script calls
        called = any(n in (2048, 2049, 2050) for n in self.std_called)
        for it, bd in self.badge:
            if it == item:
                out.append(('Poke Mart (badges >= %d)%s' % (bd, '' if called else ' [UNREACHABLE: no script calls std 2048-2050]'), []))
        return out


# ------------------------------------------------------------------ our docs (work/docs), for the "docs value" column
def docs_species():
    """{personal index: dict(types, stats)} from work/docs/pokemon_*.md (the generated player docs)."""
    import glob
    import re
    out = {}
    for path in sorted(glob.glob(os.path.join(REPO, 'work', 'docs', 'pokemon_*.md'))):
        lines = open(path, encoding='utf-8').read().split('\n')
        for i, line in enumerate(lines):
            m = re.match(r'### #(\d+) ', line)
            if not m:
                continue
            for row in lines[i + 1:i + 6]:
                cells = [c.strip() for c in row.strip().strip('|').split('|')]
                if len(cells) >= 10 and cells[3].isdigit():
                    out[int(m.group(1))] = dict(types=sorted(t.strip() for t in cells[0].split('/')),
                                                stats=[int(c) for c in cells[3:9]], abilities=cells[1],
                                                hidden=cells[2])
                    break
    return out


def compare_docs_species(g4, docs):
    """Every personal record: our docs' stats and types against this file's own parse of the fresh ROM."""
    bad = []
    for idx in range(1, len(g4.d['a/0/0/2'])):
        p = g4.personal(idx)
        d = docs.get(idx)
        if d is None:
            continue
        types = sorted(set(g4.type_name(t) for t in p['types']))
        if d['stats'] != p['stats'] or d['types'] != types:
            bad.append(dict(index=idx, docs=d, rom=dict(stats=p['stats'], types=types)))
    return bad


CATS = ['Status', 'Physical', 'Special']


def compare_docs_moves(g4):
    """work/docs/moves.md type / category / power / accuracy / PP against [bw-move] of the fresh ROM."""
    import re
    bad, n = [], 0
    M = g4.d['extra/new_move_data.narc']
    for line in open(os.path.join(REPO, 'work', 'docs', 'moves.md'), encoding='utf-8'):
        m = re.match(r'\| (\d+) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|', line)
        if not m:
            continue
        i = int(m.group(1))
        r = move_bw(M[i])
        n += 1
        d = dict(type=m.group(3).strip(), cat=m.group(4).strip(), power=m.group(5).strip(),
                 acc=m.group(6).strip(), pp=m.group(7).strip())
        probs = []
        if d['type'] != g4.type_name(r['type']):
            probs.append('type')
        if d['cat'] != CATS[r['category']]:
            probs.append('category')
        if d['power'].isdigit() and int(d['power']) != r['power']:
            probs.append('power')
        if d['acc'].isdigit() and int(d['acc']) != r['accuracy']:
            probs.append('accuracy')
        if d['pp'].isdigit() and int(d['pp']) != r['pp']:
            probs.append('pp')
        if probs:
            bad.append((i, probs, d, r))
    return n, bad


# ------------------------------------------------------------------ the rows of spreadsheet_crossref.md
# species rows: (sheet row, form used for the comparison in v4, form in v3 (pret fixed index) or None, class)
SPECIES_FORMS = {30: 1, 32: 1, 155: 1, 517: 1}
V3_FORM_INDEX = {386: {1: 496, 2: 497, 3: 498}, 413: {1: 499, 2: 500}, 487: {1: 501}, 492: {1: 502},
                 479: {i: 502 + i for i in range(1, 6)}}   # pret src/pokemon.c form -> personal index (vanilla)
CLASS_B_SPECIES = {79, 84, 517, 518, 676, 747}
NAME_ALIASES = {'懒人翁': 287, '铁面龙': 410, '胡说盆栽': 438, '冰精灵': 471, '仙子精灵': 700}


def species_rows(g4, g3):
    out = []
    for row in SPECIES_ROWS:
        sh = sheet_species(row)
        nm = base_name(sh['name'])
        sp = (g4.species_ids(nm) or [NAME_ALIASES.get(nm)])[0]
        f = SPECIES_FORMS.get(row, 0)
        idx4 = dict(g4.form_records(sp))[f]
        p4 = g4.personal(idx4)
        p3 = None
        if sp <= 493:
            idx3 = sp if f == 0 else V3_FORM_INDEX.get(sp, {}).get(f)
            if idx3 is not None:
                p3 = g3.personal(idx3)
        fields = []
        for k, n in enumerate(STAT_NAMES):
            fields.append((n, sh['stats'][k], p4['stats'][k], p3['stats'][k] if p3 else None))
        fields.append(('types', '/'.join(sh['types']), '/'.join(sorted(set(g4.type_name(t) for t in p4['types']))),
                       '/'.join(sorted(set(g3.type_name(t) for t in p3['types']))) if p3 else None))
        for k, n in enumerate(['ability1', 'ability2', 'hidden']):
            a3 = p3['abilities'][k] if p3 and k < 2 else None
            fields.append((n, sh['abilities'][k], g4.ability_name(p4['abilities'][k]),
                           g3.ability_name(a3) if a3 is not None else None))
        diffs = [f_ for f_ in fields if str(f_[1]) != str(f_[2])]
        out.append(dict(row=row, name=sh['name'], species=sp, form=f, personal_index=idx4,
                        cls='b' if row in CLASS_B_SPECIES else 'a',
                        diffs=[dict(field=a, sheet=b, v4=c, v3=d) for a, b, c, d in diffs]))
    return out


EVO_ROWS = [(3, 2), (105, 98), (109, 102), (213, 200), (413, 393), (414, 394), (481, 458), (547, 525),
            (553, 533), (587, 570), (718, 747), (737, 769), (779, 868), (787, 123), (680, 133), (248, 137),
            (386, 369)]


def evo_rows(g4, g3):
    out = []
    names4 = g4.bank(232)
    for row, sp in EVO_ROWS:
        sh = sheet_rows(SHEET_POKE, '4.0精灵数据')[row]
        e4 = evos(g4.d['a/0/3/4'][sp])
        e3 = evos(g3.d['a/0/3/4'][sp]) if sp < len(g3.d['a/0/3/4']) and sp <= 493 else None
        # Porygon2's own row (248) is about Porygon2 -> Porygon-Z
        if row == 248:
            e4 = evos(g4.d['a/0/3/4'][233])
            e3 = evos(g3.d['a/0/3/4'][233])
        out.append(dict(row=row, sheet_name=sh[1], sheet=sh[14], species=sp, v4=[(m, p, t, names4[t]) for m, p, t in e4],
                        v3=e3))
    return out


MOVE_ROWS = [('招式变动 10', 130, 'power', 100), ('招式变动 25', 238, 'accuracy', 90),
             ('招式变动 40', 337, 'crit', 'easily crits'), ('招式变动 50', 439, 'target', '双 (both foes)'),
             ('招式变动 42', 340, 'charge flag', 'one-turn'), ('技能机 34', 800, 'accuracy', 95)]


def move_rows(g4, g3):
    out = []
    M4, M3 = g4.d['extra/new_move_data.narc'], g3.d['a/0/1/1']
    for row, mid, field, sheet in MOVE_ROWS:
        r4 = move_bw(M4[mid])
        r3 = move_pret(M3[mid]) if mid < len(M3) else None
        v4 = dict(power=r4['power'], accuracy=r4['accuracy'], crit=r4['crit'], target=r4['target'],
                  **{'charge flag': 'set (two-turn)' if r4['flags'] >> 1 & 1 else 'clear',
                     'effect': r4['effect']})
        v3 = None
        if r3:
            v3 = dict(power=r3['power'], accuracy=r3['accuracy'], crit='effect %d' % r3['effect'],
                      target=r3['target'], **{'charge flag': 'vanilla effect %d' % r3['effect']})
        out.append(dict(row=row, move=mid, name4=g4.bank(739)[mid], name3=g3.bank(739)[mid] if r3 else None,
                        field=field, sheet=sheet, v4=v4[field], v3=v3[field] if v3 else None,
                        v4_effect=r4['effect'], desc4=g4.bank(738)[mid]))
    return out


def charge_census(g4):
    M4 = g4.d['extra/new_move_data.narc']
    return [(i, g4.bank(739)[i]) for i in range(len(M4)) if move_bw(M4[i])['flags'] >> 1 & 1]


ENC_ROWS = [(5420, 28, 'surf', [4]), (1238, 40, 'night', [6]), ('4784-4785', 15, 'night', [4, 5])]


def enc_rows(g4, g3, I4, I3):
    out = []
    for row, m, fld, slots in ENC_ROWS:
        res = dict(row=row, map=m, method=fld, slots={})
        for tag, g, I in (('v4', g4, I4), ('v3', g3, I3)):
            w = I.hdr[m]['wild']
            b = g.d['a/0/3/7'][w]
            b = b + bytes(max(0, 0xC4 - len(b)))
            e = enc_record(b)
            names = g.bank(232)
            res[tag + '_record'] = w
            res['map_name'] = I4.map_name(m)
            for s in slots:
                x = e[fld][s]
                sp, fm = sp_form(x['species'])
                res['slots'].setdefault(s, {})[tag] = '%s form %d Lv %s' % (names[sp], fm, x.get('min', x.get('level')))
        out.append(res)
    return out


ITEM_ROWS = [  # (sheet row, item ids, sheet claim, class)
    (173, [171], 'Saffron City shop', 'a'), (176, [174], 'Saffron City shop', 'a'),
    (171, [169, 170, 172, 173], 'Saffron shop; Fuchsia shard exchange', 'a'),
    (203, [201, 202], 'Celadon Dept. Store 5F', 'a'), (205, [203, 204, 205, 206], 'Celadon Dept. Store 5F', 'a'),
    (211, [209, 210], 'Route 9 girl; Celadon Dept. Store 5F', 'a'), (288, [286], 'item ball, Goldenrod Dept. B1F', 'a'),
    (34, [32], 'Azalea Town shop', 'a'), (88, [86], 'Azalea Town shop', 'a'),
    (244, [242], 'Union Cave, Saturday vendor', 'a'), (17, [15], 'regular shops', 'a'),
    (375, [373], 'Six Island Meowth quest reward', 'a'), (483, [481], 'Goldenrod cafeteria', 'b'),
    (372, [370], 'Route 27 house', 'b'),
    ('S', [23, 57, 58, 59, 60, 61, 62, 55, 56], 'rarity S: no source', 'a'),
]


def item_rows(g4, g3, I4, I3):
    out = []
    for row, ids, claim, cls in ITEM_ROWS:
        for it in ids:
            out.append(dict(row=row, item=it, name4=g4.bank(219)[it], name3=g3.bank(219)[it], claim=claim, cls=cls,
                            v4=I4.sources(it), v3=I3.sources(it), v4_raw_hits=len(I4.raw_give.get(it, [])),
                            v3_raw_hits=len(I3.raw_give.get(it, []))))
    return out


def script_facts(g4, g3, I4, I3):
    """Tutor and recipe scripts: teaching commands and their item/money costs, both ROMs."""
    facts = {}
    for tag, g, I in (('v4', g4, I4), ('v3', g3, I3)):
        scr = g.d['a/0/1/2']
        it, mv = g.bank(219), g.bank(739)
        for key, fi in (('Blackthorn tutor file 944', 944), ('Saffron Dojo file 829', 829),
                        ("Dragon's Den file 112", 112), ('Six Island file 943', 943), ('Cliff Cave file 880', 880),
                        ('Ecruteak house file 925', 925), ('Ice Path spray file 101', 101),
                        ('New Bark Oran vendor file 841', 841), ('Goldenrod Oran vendor file 890', 890)):
            ins = walk(scr[fi], script_offsets(scr[fi]))
            rows = []
            for o, (n, a, p, env) in sorted(ins.items()):
                r = [x if x < 0x4000 else env.get(x, 'var%04X' % x) for x in a]
                if n == 'SetMonMove':
                    rows.append('0x%X SetMonMove slot=%s move=%s %s' % (o, a[1] == 0x8002 and 'free' or 'chosen', r[2],
                                                                       mv[r[2]] if isinstance(r[2], int) else ''))
                elif n in ('TakeItem', 'HasItem') and isinstance(r[0], int):
                    rows.append('0x%X %s %s x%s' % (o, n, it[r[0]], r[1]))
                elif n in ('SubMoneyImmediate',):
                    rows.append('0x%X %s %d' % (o, n, r[0]))
                elif n == 'CallStd' and a[0] == 2033 and isinstance(env.get(0x8004), int):
                    rows.append('0x%X give %s x%s' % (o, it[env[0x8004]], env.get(0x8005)))
            facts.setdefault(key, {})[tag] = rows
    return facts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--v4', required=True)
    ap.add_argument('--v3', required=True)
    ap.add_argument('--cache', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    d4, d3 = load_rom(a.v4, a.cache), load_rom(a.v3, a.cache)
    g4, g3 = Game(d4), Game(d3, v4=False, cmap=CHARMAP_V3)
    I4, I3 = ItemIndex(g4), ItemIndex(g3)
    res = dict(
        tables=dict(v4=dict(form_table=hex(A9 + g4.form_addr), forms=len(g4.forms), map_headers=hex(A9 + I4.hdr_off),
                            hidden=hex(A9 + I4.hidden_off), special_marts=hex(A9 + I4.marts_off), n_marts=len(I4.marts),
                            mart_override={k: v for k, v in I4.mart_override.items()},
                            badge_mart=hex(A9 + I4.badge_off), std_mapping=hex(A9 + I4.std_off)),
                    v3=dict(map_headers=hex(A9 + I3.hdr_off), hidden=hex(A9 + I3.hidden_off),
                            special_marts=hex(A9 + I3.marts_off), n_marts=len(I3.marts),
                            mart_override=I3.mart_override)),
        badge_mart_std_called=dict(v4=sorted(n for n in I4.std_called if 2048 <= n <= 2054),
                                   v3=sorted(n for n in I3.std_called if 2048 <= n <= 2054)),
        names=dict(v4_0711=len(g4.bank(711)), v4_0712_327=g4.bank(712)[327] if len(g4.bank(712)) > 327 else None,
                   water_veil=dict(v4=g4.bank(712)[41], v3=g3.bank(712)[41]),
                   item114=dict(v4=g4.bank(219)[114], v3=g3.bank(219)[114]),
                   item429=dict(v4=g4.bank(219)[429], v3=g3.bank(219)[429]),
                   item479=dict(v4=g4.bank(219)[479], v3=g3.bank(219)[479])),
        species=species_rows(g4, g3), evolutions=evo_rows(g4, g3), moves=move_rows(g4, g3),
        charge_flag_moves=charge_census(g4), encounters=enc_rows(g4, g3, I4, I3), items=item_rows(g4, g3, I4, I3),
        scripts=script_facts(g4, g3, I4, I3),
        docs_species_mismatches=compare_docs_species(g4, docs_species()),
        docs_moves=compare_docs_moves(g4),
    )
    json.dump(res, open(a.out, 'w'), ensure_ascii=False, indent=1, default=str)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
