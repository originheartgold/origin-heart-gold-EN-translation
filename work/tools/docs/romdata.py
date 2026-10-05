"""Read the game data of 起源心金 v4.0.3 (the untouched CN ROM) for the player docs.

Every parser here is a pure function over bytes, so the unit tests can feed it
synthetic records. `Rom` loads the ROM once (ndspy) and caches the members we
need in work/build/docs_cache.pkl (gitignored).

Where each table lives, and how that was established, is documented in
work/docs/README.md ("Data sources"). The addresses below are for the CN
v4.0.3 arm9 (uncompressed, loaded at 0x02000000).
"""
import json
import os
import pickle
import struct

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
ROM_PATH = os.path.join(REPO, 'work', 'rom', 'origin_v4.0.3_cn.nds')
CACHE = os.path.join(REPO, 'work', 'build', 'docs_cache.pkl')
US_ROM_PATH = os.path.join(REPO, 'work', 'rom', 'Pokemon - HeartGold Version (USA).nds')
US_ITEMS = os.path.join(REPO, 'work', 'extract', 'us', 'a027', '0222.json')
BANKS = os.path.join(REPO, 'work', 'translate', 'banks', 'a027')
HERE = os.path.dirname(os.path.abspath(__file__))
ARM9_BASE = 0x02000000

def read_json(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


# --- arm9 tables (found by the loaders that read them; see README) ---
TM_TABLE_1 = 0x020FFFF8      # TM01..TM92 + HM01..HM08, u16 move ids (items 328..427)
TM_TABLE_2 = 0x020FFFAC      # TM93..TM130, u16 move ids (items 537..574)
FORM_TABLE = 0x020FEDC0      # 415 x {u16 species, u16 personal index, u16 form}
FORM_COUNT = 415
HIDDEN_ITEMS = 0x020F7194    # 231 x {u16 item, u8 qty, u8, u16, u16 index}
HIDDEN_COUNT = 231
SPECIAL_MARTS = 0x0210EAEC   # u16* table read by SpecialMartBuy
SPECIAL_MART_COUNT = 54
SPECIAL_MART_FN = 0x0204787C  # the hack's SpecialMartBuy: `list = id == 3 ? <fixed list> : table[id]`
SPECIAL_MART_FN_LEN = 0x58    # Thumb code up to and including its literal pool
BADGE_MART = 0x020F8D3A      # {u16 item, u16 tier} x 19, read by MartBuy (std 2048-2050; no v4 script calls them)
BADGE_MART_COUNT = 19
STD_MAPPING = 0x020F70E0     # 30 x {u16 lo, u16 script file, u16 msg bank}
FOSSIL_OVERLAY, FOSSIL_TABLE, FOSSIL_COUNT = 22, 0x0225C0F0, 7   # {u16 item, u16 species}, read by GetFossilPokemon

ITEM_TM01, ITEM_HM01, ITEM_HM08 = 328, 420, 427
ITEM_TM93, ITEM_TM130 = 537, 574

NARCS = {
    'personal': 'a/0/0/2', 'learnset': 'a/0/3/3', 'evo': 'a/0/3/4',
    'encounter': 'a/0/3/7', 'headbutt': 'a/2/5/2', 'trdata': 'a/0/5/5',
    'trpoke': 'a/0/5/6', 'trade': 'a/1/1/2', 'item': 'a/0/1/7',
    'scripts': 'a/0/1/2', 'events': 'a/0/3/2', 'compat': 'data/tutor_moves.narc',
    'eggmoves': 'data/egg_moves.narc', 'moves': 'extra/new_move_data.narc',
}
RAW_FILES = {'bugcontest': 'data/mushi/mushi_encount.bin'}

TYPES = ['Normal', 'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug', 'Ghost',
         'Steel', 'Fairy', 'Fire', 'Water', 'Grass', 'Electric', 'Psychic', 'Ice',
         'Dragon', 'Dark']
EGG_GROUPS = {1: 'Monster', 2: 'Water 1', 3: 'Bug', 4: 'Flying', 5: 'Field', 6: 'Fairy',
              7: 'Grass', 8: 'Human-Like', 9: 'Water 3', 10: 'Mineral', 11: 'Amorphous',
              12: 'Water 2', 13: 'Ditto', 14: 'Dragon', 15: 'Undiscovered'}
GROWTH = ['Medium Fast', 'Erratic', 'Fluctuating', 'Medium Slow', 'Fast', 'Slow']
POCKETS = ['Items', 'Medicine', 'Poké Balls', 'TMs & HMs', 'Berries', 'Mail',
           'Battle Items', 'Key Items']
NATURES = ['Hardy', 'Lonely', 'Brave', 'Adamant', 'Naughty', 'Bold', 'Docile', 'Relaxed',
           'Impish', 'Lax', 'Timid', 'Hasty', 'Serious', 'Jolly', 'Naive', 'Modest', 'Mild',
           'Quiet', 'Bashful', 'Rash', 'Calm', 'Gentle', 'Sassy', 'Careful', 'Quirky']


def u16s(b, off=0, n=None):
    n = (len(b) - off) // 2 if n is None else n
    return list(struct.unpack_from('<%dH' % n, b, off))


# ---------------------------------------------------------------- species
def parse_personal(b):
    """52-byte hack record (vanilla 44-byte layout, abilities widened to u16,
    hidden ability added at 0x1A; TM bits dropped)."""
    if len(b) < 28:
        raise ValueError('personal record too short')
    ev = struct.unpack_from('<H', b, 10)[0]
    return dict(
        stats=list(b[0:6]),               # HP Atk Def SpA SpD Spe? see below
        types=[b[6], b[7]], catch_rate=b[8], base_exp=b[9],
        ev_yield=[(ev >> (2 * i)) & 3 for i in range(6)],  # hp atk def spe spa spd
        items=[struct.unpack_from('<H', b, 12)[0], struct.unpack_from('<H', b, 14)[0]],
        gender=b[16], hatch_cycles=b[17], friendship=b[18], growth=b[19],
        egg_groups=[b[20], b[21]],
        abilities=[struct.unpack_from('<H', b, 22)[0], struct.unpack_from('<H', b, 24)[0]],
        hidden_ability=struct.unpack_from('<H', b, 26)[0],
    )


def personal_stats(p):
    """Personal order is HP, Atk, Def, Spe, SpA, SpD (Gen 4). Return HP/Atk/Def/SpA/SpD/Spe."""
    hp, at, df, sp, sa, sd = p['stats']
    return [hp, at, df, sa, sd, sp]


def parse_learnset(b):
    """(level, move) u16 pairs, 0xFFFF terminated."""
    out = []
    for i in range(0, len(b) - 1, 4):
        lv = struct.unpack_from('<H', b, i)[0]
        if lv == 0xFFFF or i + 4 > len(b):
            break
        mv = struct.unpack_from('<H', b, i + 2)[0]
        out.append((lv, mv))
    return out


def parse_idlist(b):
    """u16 list terminated by 0xFFFF (TM/tutor compat, egg moves)."""
    out = []
    for v in u16s(b, 0, len(b) // 2):
        if v == 0xFFFF:
            break
        out.append(v)
    return out


def parse_evos(b):
    out = []
    for k in range(len(b) // 6):
        m, p, t = struct.unpack_from('<3H', b, 6 * k)
        if m:
            out.append((m, p, t))
    return out


def vanilla_evos(path=US_ROM_PATH):
    """Evolutions of the untouched HeartGold (USA): {species: [(method, param, target)]} for #1-#493,
    and the US item names (id -> name). Used only to mark what the hack changed."""
    import ndspy.rom
    import ndspy.narc
    rom = ndspy.rom.NintendoDSRom.fromFile(path)
    files = ndspy.narc.NARC(rom.getFileByName('a/0/3/4')).files
    evos = {s: [e for e in (struct.unpack_from('<3H', files[s], 6 * k) for k in range(7)) if e[0]]
            for s in range(1, 494)}
    items = {x['id']: x['text'] for x in read_json(US_ITEMS)['strings']}
    return evos, items


def parse_form_table(arm9):
    o = FORM_TABLE - ARM9_BASE
    out = []
    for i in range(FORM_COUNT):
        sp, tgt, form = struct.unpack_from('<HHH', arm9, o + 6 * i)
        out.append((sp, form, tgt))
    return out


def parse_tm_table(arm9):
    """Return {item_id: move_id} for TM01..TM92, HM01..HM08, TM93..TM130."""
    a = u16s(arm9, TM_TABLE_1 - ARM9_BASE, 100)
    b = u16s(arm9, TM_TABLE_2 - ARM9_BASE, ITEM_TM130 - ITEM_TM93 + 1)
    out = {ITEM_TM01 + i: m for i, m in enumerate(a)}
    out.update({ITEM_TM93 + i: m for i, m in enumerate(b)})
    return out


def tm_label(item):
    if ITEM_TM01 <= item < ITEM_HM01:
        return 'TM%02d' % (item - ITEM_TM01 + 1)
    if ITEM_HM01 <= item <= ITEM_HM08:
        return 'HM%02d' % (item - ITEM_HM01 + 1)
    if ITEM_TM93 <= item <= ITEM_TM130:
        return 'TM%d' % (item - ITEM_TM93 + 93)
    return None


def parse_move(b):
    """40-byte record of extra/new_move_data.narc (see work/notes/move_data_audit.md)."""
    return dict(type=b[0], category=b[2], power=b[3], accuracy=b[4], pp=b[5],
                priority=struct.unpack_from('<b', b, 6)[0])


def parse_item(b):
    """34-byte item record (a/0/1/7). Price at 0, packed pocket word at 8."""
    price = struct.unpack_from('<H', b, 0)[0]
    w = struct.unpack_from('<H', b, 8)[0]
    return dict(price=price, pocket=(w >> 7) & 0xF, hold_effect=b[2])


# ---------------------------------------------------------------- encounters
LAND_RATES = [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1]
SURF_RATES = [60, 30, 5, 4, 1]
FISH_RATES = [40, 30, 15, 10, 5]
ROCK_RATES = [80, 20]
HEADBUTT_RATES = [50, 15, 15, 10, 5, 5]


def _slots(b, off, n):
    out = []
    for i in range(n):
        lo, hi, sp = struct.unpack_from('<BBH', b, off + 4 * i)
        out.append((sp, lo, hi))
    return out


def parse_encounter(b):
    """pret EncounterData (0xC4 bytes, HeartGold layout)."""
    if len(b) < 0xC4:
        raise ValueError('encounter record too short')
    r = b[0:6]
    lv = list(b[8:20])
    return dict(
        rates=dict(walk=r[0], surf=r[1], rock=r[2], old=r[3], good=r[4], super=r[5]),
        levels=lv,
        morning=u16s(b, 0x14, 12), day=u16s(b, 0x2C, 12), night=u16s(b, 0x44, 12),
        hoenn=u16s(b, 0x5C, 2), sinnoh=u16s(b, 0x60, 2),
        surf=_slots(b, 0x64, 5), rock=_slots(b, 0x78, 2),
        old=_slots(b, 0x80, 5), good=_slots(b, 0x94, 5), super=_slots(b, 0xA8, 5),
        swarm=dict(land=struct.unpack_from('<H', b, 0xBC)[0], surf=struct.unpack_from('<H', b, 0xBE)[0],
                   night_fish=struct.unpack_from('<H', b, 0xC0)[0], fish=struct.unpack_from('<H', b, 0xC2)[0]),
    )


def parse_headbutt(b):
    if len(b) < 4 + 18 * 4:
        return None
    n1, n2 = struct.unpack_from('<HH', b, 0)
    def sl(off):
        out = []
        for i in range(6):
            sp, lo, hi = struct.unpack_from('<HBB', b, off + 4 * i)
            out.append((sp, lo, hi))
        return out
    return dict(trees=n1, secret_trees=n2, common=sl(4), rare=sl(28), secret=sl(52))


def parse_bug_contest(b):
    """data/mushi/mushi_encount.bin: 4 sets of 10 x {u16 species, u8 min, u8 max, u8 rate, u8 score, u16}."""
    sets = []
    for s in range(len(b) // 80):
        rows = []
        for i in range(10):
            sp, lo, hi, rate, score, _ = struct.unpack_from('<HBBBBH', b, 80 * s + 8 * i)
            rows.append(dict(species=sp, min=lo, max=hi, rate=rate, score=score))
        sets.append(rows)
    return sets


# ---------------------------------------------------------------- trainers
def parse_trdata(b):
    flags, cls, count = b[0], struct.unpack_from('<H', b, 1)[0], b[3]
    items = u16s(b, 4, 4)
    ai, btype = struct.unpack_from('<II', b, 12)
    return dict(flags=flags, cls=cls, count=count, items=[i for i in items if i],
                ai=ai, double=btype != 0)


TRPOKE_SIZE = 28


def split_species(v):
    """Species fields in trainer/script data keep the form in the top 5 bits."""
    return v & 0x7FF, v >> 11


def parse_trpoke(b, count):
    """CN v4.0.3 party-loader semantics, not the vanilla packed-form layout.

    arm9 0x02072822 applies byte 2 as the form; 0x02072880 assigns EVs in
    HP/Atk/Def/Spe/SpA/SpD order. Return EVs in the guide's display order.
    At 0x020728E0 the loader overwrites HP IV with a level-based value. Its
    six-iteration loop never increments the field id, so the other five IVs
    retain the initial scaled value. Preserve this original-hack behaviour.
    """
    mons = []
    for i in range(count):
        o = TRPOKE_SIZE * i
        if o + TRPOKE_SIZE > len(b):
            break
        iv, abil_slot, form, nature = b[o], b[o + 1], b[o + 2], b[o + 3]
        ability, level, species, item = struct.unpack_from('<4H', b, o + 4)
        moves = [m for m in u16s(b, o + 12, 4) if m]
        raw_evs = list(b[o + 20:o + 26])
        evs = [raw_evs[j] for j in (0, 1, 2, 4, 5, 3)]
        hp_ivs = 10 if level <= 40 else 20 if level < 80 else 31
        mons.append(dict(iv=iv, ivs=iv * 31 // 255, hp_ivs=hp_ivs, abil_slot=abil_slot,
                         nature=None if nature == 0xFF else nature,
                         ability=ability, level=level, species=species, form=form, item=item,
                         moves=moves, evs=evs))
    return mons


# ---------------------------------------------------------------- trades
def parse_trade(b):
    v = struct.unpack('<21I', b[:84])
    return dict(give=v[0], ivs=list(v[1:7]), ability=v[7], ot_id=v[8] & 0xFFFF, pid=v[14],
                item=v[15], gender=v[16], ask=v[19])


# ---------------------------------------------------------------- map events
def parse_events(b):
    p = 0
    n = struct.unpack_from('<I', b, p)[0]; p += 4
    bgs = []
    for _ in range(n):
        sid, typ, x, z, y, d = struct.unpack_from('<HHiiiH', b, p); p += 20
        bgs.append(dict(script=sid, type=typ, x=x, z=z))
    n = struct.unpack_from('<I', b, p)[0]; p += 4
    objs = []
    for _ in range(n):
        v = struct.unpack_from('<HHHHHHhHHHhhHHi', b, p); p += 32
        objs.append(dict(id=v[0], sprite=v[1], type=v[3], flag=v[4], script=v[5], x=v[12], z=v[13]))
    n = struct.unpack_from('<I', b, p)[0]; p += 4
    warps = []
    for _ in range(n):
        x, z, h, a, y = struct.unpack_from('<HHHHI', b, p); p += 12
        warps.append(dict(x=x, z=z, dest=h))
    n = struct.unpack_from('<I', b, p)[0]; p += 4
    coords = []
    for _ in range(n):
        v = struct.unpack_from('<HhhHHHHH', b, p); p += 16
        coords.append(dict(script=v[0], x=v[1], z=v[2]))
    return dict(bg=bgs, obj=objs, warp=warps, coord=coords)


# ---------------------------------------------------------------- scripts
_CMDS = None


def cmds():
    global _CMDS
    if _CMDS is None:
        raw = read_json(os.path.join(HERE, 'script_cmds.json'))
        _CMDS = {int(k): (v[0], v[1]) for k, v in raw.items()}
    return _CMDS


JUMPS = {22: True, 26: False, 23: False, 24: False, 25: False, 28: False, 29: False, 225: False}
TERM = {2, 27}


def _argsizes(op, data, p):
    if op in (400, 401, 402):
        return [1, 2] if data[p] == 2 else [1]
    if op == 465:
        a = struct.unpack_from('<H', data, p)[0]
        return [2, 2, 2] if a <= 3 else ([2] if a == 6 else [2, 2])
    if op == 489:
        a = struct.unpack_from('<H', data, p)[0]
        return [2, 2] if 1 <= a <= 3 else ([2, 2, 2] if a in (5, 6) else [2])
    return cmds()[op][1]


def script_entries(data):
    out, p = [], 0
    while p + 4 <= len(data):
        if struct.unpack_from('<H', data, p)[0] == 0xFD13:
            break
        off = struct.unpack_from('<i', data, p)[0]
        out.append(p + 4 + off)
        p += 4
    return out


def disasm(data):
    """Return {pc: (op, args, next_pc, jump_target)} reachable from the header entries."""
    C = cmds()
    entries = script_entries(data)
    todo, ins = list(entries), {}
    while todo:
        pc = todo.pop()
        while pc not in ins and 0 <= pc and pc + 2 <= len(data):
            op = struct.unpack_from('<H', data, pc)[0]
            if op not in C:
                break
            q, args, bad = pc + 2, [], False
            for s in _argsizes(op, data, q):
                if q + s > len(data):
                    bad = True
                    break
                args.append(int.from_bytes(data[q:q + s], 'little', signed=(s == 4)))
                q += s
            if bad:
                break
            tgt = None
            if op in JUMPS:
                tgt = q + args[-1]
                todo.append(tgt)
            ins[pc] = (op, args, q, tgt)
            if (op in JUMPS and JUMPS[op]) or op in TERM:
                break
            pc = q
    return entries, ins


def const_prop(entries, ins):
    """Known constant values of vars at each pc (linear runs only, like the Phase A index)."""
    targets = set(t for (_, _, _, t) in ins.values() if t is not None) | set(entries)
    known, cur, prev_next = {}, {}, None
    for pc in sorted(ins):
        if pc in targets or pc != prev_next:
            cur = {}
        known[pc] = dict(cur)
        op, a, n, t = ins[pc]
        if op in (41, 43):
            if op == 41 or a[1] < 0x4000:
                cur[a[0]] = a[1]
            else:
                cur.pop(a[0], None)
        elif op in (39, 40, 42):
            cur.pop(a[0], None)
        elif op in (22, 2, 27):
            cur = {}
        prev_next = n
    return known


def val(v, known):
    if v < 0x4000:
        return v
    return known.get(v)


# ---------------------------------------------------------------- names
def load_bank(num):
    d = read_json(os.path.join(BANKS, '%04d.json' % num))
    return {x['id']: (x.get('en') or x.get('zh') or '') for x in d['strings']}


def load_bank_full(num):
    d = read_json(os.path.join(BANKS, '%04d.json' % num))
    return {x['id']: x for x in d['strings']}


# ---------------------------------------------------------------- ROM
class Rom:
    """Everything the generator reads from the ROM, cached as plain bytes."""

    def __init__(self, path=ROM_PATH, cache=CACHE, refresh=False):
        self.path = path
        if not refresh and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
            with open(cache, 'rb') as fh:
                d = pickle.load(fh)
        else:
            import ndspy.rom
            import ndspy.narc
            rom = ndspy.rom.NintendoDSRom.fromFile(path)
            d = {'arm9': bytes(rom.arm9)}
            ovs = rom.loadArm9Overlays([FOSSIL_OVERLAY])
            d['ov%d' % FOSSIL_OVERLAY] = (ovs[FOSSIL_OVERLAY].ramAddress, bytes(ovs[FOSSIL_OVERLAY].data))
            for k, n in NARCS.items():
                d[k] = [bytes(x) for x in ndspy.narc.NARC(rom.getFileByName(n)).files]
            for k, n in RAW_FILES.items():
                d[k] = bytes(rom.getFileByName(n))
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, 'wb') as fh:
                pickle.dump(d, fh)
        self.d = d
        self.arm9 = d['arm9']

    def __getitem__(self, k):
        return self.d[k]

    def a9(self, addr, n):
        o = addr - ARM9_BASE
        return self.arm9[o:o + n]

    def u16(self, addr):
        return struct.unpack_from('<H', self.arm9, addr - ARM9_BASE)[0]

    def u32(self, addr):
        return struct.unpack_from('<I', self.arm9, addr - ARM9_BASE)[0]

    def hidden_items(self):
        o = HIDDEN_ITEMS - ARM9_BASE
        out = []
        for i in range(HIDDEN_COUNT):
            it, q, _u3, _u4, idx = struct.unpack_from('<HBBHH', self.arm9, o + 8 * i)
            out.append(dict(item=it, qty=q, index=idx))
        return out

    def _item_list(self, p):
        items = []
        while True:
            v = self.u16(p + 2 * len(items))
            if v == 0xFFFF or len(items) > 100:
                break
            items.append(v)
        return items

    def special_mart_override(self):
        """{list id: [items]} for the ids SpecialMartBuy does not read from the table. The hack's
        command (arm9 0x0204787C) does `cmp r2,#3; bne; ldr r2,=0x020F8B3E` and only takes the
        table entry otherwise. Read from the code: every `cmp r2,#imm` followed by a `ldr r2,=X`
        whose X is not the table. Empty when the command has no such special case (v3)."""
        out, cmp_imm = {}, None
        for x in range(SPECIAL_MART_FN, SPECIAL_MART_FN + SPECIAL_MART_FN_LEN, 2):
            h = self.u16(x)
            if h >> 8 == 0x2A:                      # cmp r2, #imm
                cmp_imm = h & 0xFF
            elif h >> 8 == 0x4A and cmp_imm is not None:   # ldr r2, [pc, #imm*4]
                v = self.u32(((x + 4) & ~3) + (h & 0xFF) * 4)
                if v != SPECIAL_MARTS and ARM9_BASE <= v < ARM9_BASE + len(self.arm9):
                    out[cmp_imm] = self._item_list(v)
                cmp_imm = None
        return out

    def special_marts(self, table_only=False):
        """The SpecialMartBuy lists by id, as the game uses them (the code's override applied),
        or the raw table entries with table_only=True."""
        out = [self._item_list(self.u32(SPECIAL_MARTS + 4 * j)) for j in range(SPECIAL_MART_COUNT)]
        if not table_only:
            for j, lst in self.special_mart_override().items():
                if j < len(out):
                    out[j] = lst
        return out

    def badge_mart(self):
        o = BADGE_MART - ARM9_BASE
        return [struct.unpack_from('<HH', self.arm9, o + 4 * i) for i in range(BADGE_MART_COUNT)]

    def std_mapping(self):
        o = STD_MAPPING - ARM9_BASE
        return [struct.unpack_from('<HHH', self.arm9, o + 6 * i) for i in range(30)]


# ---------------------------------------------------------------- script index
INTERESTING = {
    20: 'callstd', 125: 'item_give', 126: 'item_take', 128: 'item_has', 137: 'mon_give',
    138: 'egg_give', 139: 'set_move', 140: 'has_move', 213: 'trainer', 467: 'relearner',
    468: 'tutor_init', 470: 'trade', 589: 'wild', 120: 'coins_give', 121: 'coins_take',
    532: 'coins_check', 111: 'money_take', 112: 'money_check', 275: 'mart', 276: 'special_mart',
    41: 'setvar', 557: 'bp_check', 122: 'athlete_points', 362: 'loan_give', 295: 'badge_give',
    30: 'flag_set', 32: 'flag_check', 562: 'multi_battle',
}


def resolve_back(ins, prev, jumpers, pc, var, limit=120):
    """Walk backwards from pc (linear predecessors, then single jump sources) to the SetVar that
    gives var a constant. Returns the value or None. Stops at the first write that is not a constant."""
    seen = set()
    cur = pc
    for _ in range(limit):
        p = prev.get(cur)
        if p is not None and p in ins and not (ins[p][0] in TERM or (ins[p][0] in JUMPS and JUMPS[ins[p][0]])):
            cur = p
        else:
            js = jumpers.get(cur, [])
            if len(js) != 1:
                return None
            cur = js[0]
        if cur in seen:
            return None
        seen.add(cur)
        op, a, n, t = ins[cur]
        if op in (41, 43) and a[0] == var:
            return a[1] if (op == 41 or a[1] < 0x4000) else None
        if op in (39, 40, 42) and a[0] == var:
            return None
        if op == 26:  # a Call may change it
            continue
    return None


def resolve_set(ins, prev, jumpers, pc, var, limit=400, depth=0):
    """All constants var can hold at pc, following every predecessor (linear and jumps).
    Returns (values, complete) where complete is False if some path has an unknown value."""
    vals, complete = set(), True
    stack, seen = [pc], {pc}
    steps = 0
    while stack:
        cur = stack.pop()
        preds = []
        p = prev.get(cur)
        if p is not None and p in ins and not (ins[p][0] in TERM or (ins[p][0] in JUMPS and JUMPS[ins[p][0]])):
            preds.append(p)
        preds += jumpers.get(cur, [])
        if not preds:
            complete = False
        for q in preds:
            if q in seen:
                continue
            seen.add(q)
            steps += 1
            if steps > limit:
                return vals, False
            op, a, n, t = ins[q]
            if op in (41, 43) and a[0] == var:
                if op == 41 or a[1] < 0x4000:
                    vals.add(a[1])
                elif depth < 3:
                    v2, c2 = resolve_set(ins, prev, jumpers, q, a[1], limit, depth + 1)
                    vals |= v2
                    complete &= c2
                else:
                    complete = False
                continue
            if op == 42 and a[0] == var and depth < 3:   # CopyVar dest, src
                v2, c2 = resolve_set(ins, prev, jumpers, q, a[1], limit, depth + 1)
                vals |= v2
                complete &= c2
                continue
            if op in (39, 40, 42) and a[0] == var:
                complete = False
                continue
            stack.append(q)
    return vals, complete


def index_scripts(files):
    """Scan every script file. Returns {file: dict(entries, ins, recs)} with resolved args."""
    out = {}
    for f, data in enumerate(files):
        try:
            entries, ins = disasm(data)
        except Exception:
            entries, ins = [], {}
        known = const_prop(entries, ins) if ins else {}
        prev = {n: pc for pc, (op, a, n, t) in ins.items()}
        jumpers = {}
        for pc, (op, a, n, t) in ins.items():
            if t is not None:
                jumpers.setdefault(t, []).append(pc)
        recs = []
        for pc in sorted(ins):
            op, a, n, t = ins[pc]
            if op not in INTERESTING:
                continue
            k = known.get(pc, {})

            def rv(x):
                v = val(x, k)
                if v is None and 0x4000 <= x < 0x8010:
                    v = resolve_back(ins, prev, jumpers, pc, x)
                return v
            r = dict(pc=pc, op=op, kind=INTERESTING[op], raw=a,
                     args=[rv(x) if isinstance(x, int) and op not in (41,) else x for x in a])
            if op == 20:
                r['v8004'] = rv(0x8004)
                r['v8005'] = rv(0x8005)
                r['v8008'] = rv(0x8008)
                if r['v8004'] is None:
                    r['alt8004'] = sorted(resolve_set(ins, prev, jumpers, pc, 0x8004)[0])
            elif op in (125, 137, 138, 589) and r['args'][0] is None and 0x4000 <= a[0] < 0x8010:
                vals, complete = resolve_set(ins, prev, jumpers, pc, a[0])
                r['alt0'] = sorted(vals)
                r['alt0_complete'] = complete     # False: some path sets the variable at run time
            recs.append(r)
        out[f] = dict(entries=entries, ins=ins, recs=recs)
    return out

def fossils(rom):
    """[(fossil item, species)] from the GetFossilPokemon table in overlay 22."""
    ra, data = rom.d['ov%d' % FOSSIL_OVERLAY]
    o = FOSSIL_TABLE - ra
    return [struct.unpack_from('<HH', data, o + 4 * i) for i in range(FOSSIL_COUNT)]
