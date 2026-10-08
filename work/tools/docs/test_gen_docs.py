"""Tests for the docs generator parsers (synthetic records) plus a ROM smoke test.

    python3 -m unittest work/tools/docs/test_gen_docs.py
"""
import os
import struct
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import romdata as R  # noqa: E402
import gen_docs as G  # noqa: E402


def personal(stats=(45, 49, 49, 45, 65, 65), types=(12, 3), abil=(65, 34), hidden=47, gender=31, egg=(1, 7)):
    b = bytearray(52)
    b[0:6] = bytes(stats)
    b[6], b[7] = types
    b[8], b[9] = 45, 64
    struct.pack_into('<H', b, 10, 0x0100)  # 1 SpA EV
    b[16], b[17], b[18], b[19] = gender, 20, 50, 3
    b[20], b[21] = egg
    struct.pack_into('<HHH', b, 22, abil[0], abil[1], hidden)
    return bytes(b)


class TestSpecies(unittest.TestCase):
    def test_personal(self):
        p = R.parse_personal(personal())
        self.assertEqual(p['types'], [12, 3])
        self.assertEqual(p['abilities'], [65, 34])
        self.assertEqual(p['hidden_ability'], 47)
        self.assertEqual(p['ev_yield'], [0, 0, 0, 0, 1, 0])
        # stored HP Atk Def Spe SpA SpD, shown HP Atk Def SpA SpD Spe
        self.assertEqual(R.personal_stats(p), [45, 49, 49, 65, 65, 45])

    def test_learnset(self):
        b = struct.pack('<6H', 1, 33, 3, 22, 0xFFFF, 0)
        self.assertEqual(R.parse_learnset(b), [(1, 33), (3, 22)])

    def test_idlist(self):
        self.assertEqual(R.parse_idlist(struct.pack('<4H', 5, 7, 0xFFFF, 9)), [5, 7])
        self.assertEqual(R.parse_idlist(struct.pack('<2H', 0xFFFF, 0)), [])

    def test_evos(self):
        b = struct.pack('<6H', 4, 16, 2, 7, 83, 26) + bytes(48)
        self.assertEqual(R.parse_evos(b), [(4, 16, 2), (7, 83, 26)])

    def test_tm_label(self):
        self.assertEqual(R.tm_label(328), 'TM01')
        self.assertEqual(R.tm_label(419), 'TM92')
        self.assertEqual(R.tm_label(420), 'HM01')
        self.assertEqual(R.tm_label(537), 'TM93')
        self.assertEqual(R.tm_label(574), 'TM130')
        self.assertIsNone(R.tm_label(575))

    def test_split_species(self):
        self.assertEqual(R.split_species(2143), (95, 1))   # Crystal Onix in a WildBattle
        self.assertEqual(R.split_species(25), (25, 0))

    def test_gender(self):
        self.assertEqual(G.gender_text(255), 'genderless')
        self.assertEqual(G.gender_text(0), 'always male')
        self.assertEqual(G.gender_text(254), 'always female')
        self.assertEqual(G.gender_text(31), '12.5% female')
        self.assertEqual(G.gender_text(127), '50.0% female')


class TestEncounters(unittest.TestCase):
    def rec(self):
        b = bytearray(0xC4)
        b[0:6] = bytes([25, 10, 0, 30, 0, 0])
        b[8:20] = bytes(range(2, 14))
        for i in range(12):
            struct.pack_into('<H', b, 0x14 + 2 * i, 16)       # morning Pidgey
            struct.pack_into('<H', b, 0x2C + 2 * i, 19 if i < 2 else 16)
            struct.pack_into('<H', b, 0x44 + 2 * i, 163)
        struct.pack_into('<2H', b, 0x5C, 311, 312)
        struct.pack_into('<BBH', b, 0x64, 5, 10, 129)
        struct.pack_into('<BBH', b, 0x80, 3, 5, 129)
        struct.pack_into('<H', b, 0xBC, 206)
        return bytes(b)

    def test_parse(self):
        e = R.parse_encounter(self.rec())
        self.assertEqual(e['rates']['walk'], 25)
        self.assertEqual(e['levels'][0], 2)
        self.assertEqual(e['day'][:3], [19, 19, 16])
        self.assertEqual(e['hoenn'], [311, 312])
        self.assertEqual(e['surf'][0], (129, 5, 10))
        self.assertEqual(e['old'][0], (129, 3, 5))
        self.assertEqual(e['swarm']['land'], 206)
        self.assertEqual(sum(R.LAND_RATES), 100)
        self.assertEqual(sum(R.SURF_RATES), 100)
        self.assertEqual(sum(R.FISH_RATES), 100)

    def test_merge_and_species(self):
        class Fake:
            def sp(self, s, f=0):
                return 'S%d' % s
        e = R.parse_encounter(self.rec())
        rows = G.merge_slots(Fake(), [(sp, l, l) for sp, l in zip(e['day'], e['levels'])], R.LAND_RATES)
        self.assertEqual(rows[0], ('S19', '2–3', 40))
        self.assertEqual(rows[1], ('S16', '4–13', 60))
        self.assertEqual(G.enc_species(e), {16, 19, 163, 311, 312, 206, 129})

    def test_headbutt(self):
        b = struct.pack('<HH', 3, 1) + struct.pack('<HBB', 165, 5, 7) * 18
        h = R.parse_headbutt(b)
        self.assertEqual(h['trees'], 3)
        self.assertEqual(h['common'][0], (165, 5, 7))
        self.assertIsNone(R.parse_headbutt(bytes(4)))


class TestTrainers(unittest.TestCase):
    def test_trdata(self):
        b = bytes([3, 1, 0, 4]) + struct.pack('<4H', 26, 0, 0, 0) + struct.pack('<II', 5, 2)
        t = R.parse_trdata(b)
        self.assertEqual((t['flags'], t['cls'], t['count']), (3, 1, 4))
        self.assertEqual(t['items'], [26])
        self.assertTrue(t['double'])

    def test_trpoke(self):
        mon = bytes([100, 0, 0, 0xFF]) + struct.pack('<4H', 65, 15, 1, 239) + struct.pack('<4H', 22, 73, 79, 33) \
            + bytes([6, 252, 0, 0, 0, 252]) + bytes(2)
        self.assertEqual(len(mon), R.TRPOKE_SIZE)
        m = R.parse_trpoke(mon + mon, 2)
        self.assertEqual(len(m), 2)
        self.assertEqual((m[0]['species'], m[0]['level'], m[0]['ability'], m[0]['item']), (1, 15, 65, 239))
        self.assertEqual(m[0]['moves'], [22, 73, 79, 33])
        self.assertIsNone(m[0]['nature'])
        self.assertEqual(m[0]['ivs'], 12)
        self.assertEqual(m[0]['evs'], [6, 252, 0, 0, 252, 0])

    def test_trade(self):
        v = [20, 26, 31, 25, 31, 21, 21, 62, 6469, 0, 0, 0, 0, 0, 12345, 0, 0, 0, 1, 12, 0]
        t = R.parse_trade(struct.pack('<21I', *v))
        self.assertEqual((t['give'], t['ask'], t['ability'], t['ot_id']), (20, 12, 62, 6469))


def script(*ins):
    """Build a one-entry script file from (op, [(size, value), ...]) tuples."""
    body = b''
    for op, args in ins:
        body += struct.pack('<H', op)
        for size, v in args:
            body += v.to_bytes(size, 'little', signed=(size == 4))
    return struct.pack('<i', 0) + struct.pack('<H', 0xFD13) + body


class TestScripts(unittest.TestCase):
    def test_disasm_and_resolve(self):
        # entry at offset 4 (header offset 0 -> 4+0) ... the terminator sits at 4, so shift by 2
        data = struct.pack('<i', 2) + struct.pack('<H', 0xFD13) + b''.join([
            struct.pack('<HHH', 41, 0x8004, 385),          # SetVar 0x8004, TM58
            struct.pack('<HH', 17, 0x800C) + struct.pack('<H', 0),  # CompareVarToValue
            struct.pack('<HBi', 28, 1, 0),                  # GoToIf ==, +0 (falls into the next command)
            struct.pack('<HH', 121, 2000),                  # TakeCoins 2000
            struct.pack('<HHHH', 125, 0x8004, 1, 0x800C),   # GiveItem 0x8004, 1
            struct.pack('<H', 2),                           # End
        ])
        entries, ins = R.disasm(data)
        self.assertEqual(entries, [6])
        ops = [ins[pc][0] for pc in sorted(ins)]
        self.assertEqual(ops, [41, 17, 28, 121, 125, 2])
        idx = R.index_scripts([data])[0]
        give = [r for r in idx['recs'] if r['kind'] == 'item_give'][0]
        self.assertEqual(give['args'][0], 385)   # resolved through the branch target
        coins = [r for r in idx['recs'] if r['kind'] == 'coins_take'][0]
        self.assertEqual(coins['args'][0], 2000)

    def test_species_chain(self):
        ins = {}
        pc = 0
        for sp in (1, 2, 3, 152):
            ins[pc] = (17, [0x8005, sp], pc + 6, None)
            ins[pc + 6] = (28, [1, 100], pc + 13, 500)
            pc += 13
        ins[pc] = (27, [], pc + 2, None)
        ch = G.species_chains(ins)
        self.assertEqual(len(ch), 1)
        self.assertEqual(ch[0]['species'], [1, 2, 3, 152])
        self.assertEqual(ch[0]['var'], 0x8005)


class FakeCtx:
    """Just enough of gen_docs.Ctx for mart_calls / script_gifts."""
    def __init__(self, S, n_items=600):
        self.S = S
        self.std_file = 3
        self.ball_file = 141
        self.items = [dict(price=0, pocket=0)] * n_items


class TestAvailability(unittest.TestCase):
    def test_runtime_species_needs_a_complete_list(self):
        give = dict(pc=40, op=137, kind='mon_give', args=[None, 5], raw=[0x4002, 5], alt0=[23, 27], alt0_complete=True)
        S = {903: dict(recs=[give]), 904: dict(recs=[dict(give, alt0=[63], alt0_complete=False)])}
        self.assertEqual(G.static_mons(FakeCtx(S)), [('gift', 23, 0, 5, 903), ('gift', 27, 0, 5, 903)])

    def test_enc_records_include_weekday_tables(self):
        ctx = types.SimpleNamespace(enc_by_file=([], {5: [1, 2]}), enc_weekday={109: [('Sunday', 141), ('Monday', 142)]})
        self.assertEqual(G.enc_records(ctx), {5: [1, 2], 141: [109], 142: [109]})

    def test_item_evolution_needs_an_obtainable_item(self):
        tart = next(i for i, e in G.reviewed('items_not_in_game').items() if e['name'] == 'Tart Apple')
        self.assertFalse(G.evo_works(7, tart))       # use item
        self.assertTrue(G.evo_works(4, tart))        # level up: the parameter is a level, not an item


def callstd(pc, n, v8004=None):
    return dict(pc=pc, op=20, kind='callstd', args=[n], raw=[n], v8004=v8004, v8005=None, v8008=None)


class TestShops(unittest.TestCase):
    def test_greeting_std_is_not_a_mart(self):
        # a standard clerk: CallStd 2011 (greeting only), SetVar 0x8004 3, CallStd 2052 (SpecialMartBuy)
        S = {77: dict(recs=[callstd(10, 2011), callstd(20, 2052, 3)])}
        self.assertEqual(G.mart_calls(FakeCtx(S)), [(77, 'special', 3)])

    def test_badge_mart_only_through_its_std_or_martbuy(self):
        S = {50: dict(recs=[callstd(4, 2049)]),
             51: dict(recs=[dict(pc=8, op=275, kind='mart', args=[None], raw=[0x8004])]),
             52: dict(recs=[dict(pc=8, op=276, kind='special_mart', args=[7], raw=[7])])}
        self.assertEqual(sorted(G.mart_calls(FakeCtx(S))), [(50, 'badge', None), (51, 'badge', None), (52, 'special', 7)])

    def test_std_file_commands_are_not_call_sites(self):
        # file 3 holds the std scripts themselves (MartBuy/SpecialMartBuy on 0x8004)
        S = {3: dict(recs=[dict(pc=8, op=275, kind='mart', args=[None], raw=[0x8004]),
                           dict(pc=12, op=276, kind='special_mart', args=[5], raw=[5])])}
        self.assertEqual(G.mart_calls(FakeCtx(S)), [])

    def test_item_ball_file_is_not_a_gift_source(self):
        # the item-ball std file's shared GiveItem(0x8004) resolves to every ball item
        give = dict(pc=40, op=125, kind='item_give', args=[None, None, None], raw=[0x8004, 0x8005, 0x800C], alt0=[2, 3, 4])
        S = {141: dict(recs=[give]), 200: dict(recs=[dict(give, alt0=[17, 18])])}
        got = G.script_gifts(FakeCtx(S))
        self.assertEqual({g['file'] for g in got}, {200})
        self.assertEqual(sorted(g['item'] for g in got), [17, 18])

    def test_special_mart_override_from_code(self):
        def fake_rom(with_override):
            rom = R.Rom.__new__(R.Rom)
            a9 = bytearray(0x110000)
            fn = R.SPECIAL_MART_FN - R.ARM9_BASE
            fixed = 0x0200F000
            # table: one pointer per list
            for j in range(R.SPECIAL_MART_COUNT):
                struct.pack_into('<I', a9, R.SPECIAL_MARTS - R.ARM9_BASE + 4 * j, 0x02010000 + 0x10 * j)
                struct.pack_into('<3H', a9, 0x10000 + 0x10 * j, 100 + j, 200 + j, 0xFFFF)
            struct.pack_into('<4H', a9, fixed - R.ARM9_BASE, 4, 3, 2, 0xFFFF)
            code = [0xB518, 0x2A03 if with_override else 0x46C0, 0xD10A, 0x4A09, 0xE00B, 0x4A04]
            for k, h in enumerate(code):
                struct.pack_into('<H', a9, fn + 0x18 + 2 * k, h)
            # ldr r2,[pc,#9*4] at fn+0x1E and ldr r2,[pc,#4*4] at fn+0x22 -> pool words
            struct.pack_into('<I', a9, ((fn + 0x1E + 4) & ~3) + 36, fixed)
            struct.pack_into('<I', a9, ((fn + 0x22 + 4) & ~3) + 16, R.SPECIAL_MARTS)
            rom.arm9 = bytes(a9)
            return rom
        rom = fake_rom(True)
        self.assertEqual(rom.special_mart_override(), {3: [4, 3, 2]})
        self.assertEqual(rom.special_marts()[3], [4, 3, 2])
        self.assertEqual(rom.special_marts(table_only=True)[3], [103, 203])
        self.assertEqual(rom.special_marts()[5], [105, 205])
        rom = fake_rom(False)                       # v3: no `cmp r2,#3`, table entry used
        self.assertEqual(rom.special_mart_override(), {})
        self.assertEqual(rom.special_marts()[3], [103, 203])


ROM_OK = os.path.exists(R.ROM_PATH)


@unittest.skipUnless(ROM_OK, 'CN ROM not present')
class TestRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = R.Rom()

    def test_counts(self):
        self.assertEqual(len(self.rom['personal']), 1441)
        self.assertEqual(len(self.rom['trade']), 13)
        self.assertEqual(len(self.rom['moves']), 921)

    def test_known_values(self):
        p = R.parse_personal(self.rom['personal'][1])
        self.assertEqual(R.personal_stats(p), [45, 49, 49, 65, 65, 45])
        tm = R.parse_tm_table(self.rom.arm9)
        self.assertEqual(tm[328], 264)       # TM01 Focus Punch
        self.assertEqual(tm[420], 15)        # HM01 Cut
        self.assertEqual(len(tm), 138)
        self.assertEqual(R.fossils(self.rom)[0], (103, 142))   # Old Amber -> Aerodactyl
        forms = R.parse_form_table(self.rom.arm9)
        self.assertEqual(forms[0], (3, 1, 1026))
        self.assertEqual(len(self.rom.special_marts()), 54)
        self.assertEqual(len(self.rom.hidden_items()), 231)

    def test_vendor_prices(self):
        # Union Cave B1F weekday vendor (script file 57): one price per branch, not the
        # previous branch's price as well (Phase B2 spreadsheet cross-check).
        ctx = G.Ctx(self.rom)
        pays = {(g['item'], tuple(g['pay'])) for g in G.script_gifts(ctx) if g['file'] == 57}
        self.assertIn((109, ('₽3000',)), pays)    # Dawn Stone
        self.assertIn((275, ('₽100',)), pays)     # Focus Sash
        self.assertIn((321, ('₽5000',)), pays)    # Protector
        # Saffron Dojo (file 829) teaches Volt Switch first and charges ₽10000 in a block
        # reached by GoTo.
        vs = [t for t in G.extract_tutors(ctx) if t['file'] == 829 and t['move'] == 521]
        self.assertEqual(vs[0]['cost'], ['₽10000'])


    def test_shop_list_3_override(self):
        # SpecialMartBuy (arm9 0x0204787C) swaps list 3 for the fixed 18-item list at 0x020F8B3E
        self.assertEqual(self.rom.special_mart_override(), {3: [4, 3, 2, 17, 26, 25, 24, 28, 18, 22, 19, 20, 21, 27, 79, 76, 77, 78]})
        self.assertEqual(self.rom.special_marts(table_only=True)[3], [17, 26, 25, 24, 28, 18, 22, 19, 20, 21, 27])

    def test_shop_sources(self):
        ctx = G.Ctx(self.rom)
        marts = G.mart_calls(ctx)
        self.assertFalse([m for m in marts if m[1] == 'badge'])          # badge-tier MartBuy is never called
        self.assertEqual(sum(1 for m in marts if m[2] == 3), 23)          # the 23 standard clerks
        page = G.gen_items(ctx)
        self.assertNotIn('from tier', page)
        self.assertNotIn('Poké Mart (standard clerk)', page)
        self.assertNotIn('script file 141', page)
        for item in (2, 3, 4, 76, 77, 78, 79):    # Ultra/Great/Poké Ball, Super/Max Repel, Escape Rope, Repel
            self.assertTrue(any(s.startswith('shop, ') for s in ctx.item_sources[item]), ctx.it(item))
        self.assertFalse(any('141' in s for v in ctx.item_sources.values() for s in v))
        self.assertIn('gift, Celadon City', ctx.item_sources[ctx_item(ctx, 'Coin Case')])


def ctx_item(ctx, name):
    return next(i for i in range(len(ctx.items)) if ctx.it(i) == name)


class TestSiteLists(unittest.TestCase):
    """The site's never-met lists (work/tools/site/*not_in_game.json) against the exported site data."""
    SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site')
    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'site', 'src', 'data')

    def load(self, *parts):
        return R.read_json(os.path.join(*parts))

    def test_no_trainer_uses_a_removed_pokemon(self):
        gone = {e['id'] for e in self.load(self.SITE, 'not_in_game.json')['entries']}
        teams = {m['id'] for t in self.load(self.DATA, 'trainers.json') if t['places'] for m in t['team']}
        self.assertEqual(sorted(gone & teams), [])

    def test_removed_items_not_held_by_trainers(self):
        kept = {i['name'] for i in self.load(self.DATA, 'items.json')}    # trainer data has names only; some
        gone = {e['name'] for e in self.load(self.SITE, 'items_not_in_game.json')['entries']} - kept   # names repeat
        held = {m.get('item') for t in self.load(self.DATA, 'trainers.json') if t['places'] for m in t['team']}
        self.assertEqual(sorted(gone & held - {None}), [])


if __name__ == '__main__':
    unittest.main()
