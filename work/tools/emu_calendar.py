#!/usr/bin/env python3
"""emu_calendar - the calendar encounter hook in the emulator (`emu_harness.py calendar`).

The hack's encounter loader (arm9 0x0203AD24, called when a map's data loads, e.g. from 0x0203AB04) clears
the 0xC4-byte encounter buffer, reads the map's encounter record, then walks eight 8-byte records at
0x020F6A64 {u8 month, u8 day, u16 map, u16 species, u8 form, u8 period}. A record whose month, day and map
match the pinned RTC date writes `species | form << 11` over land slot 11 (the last, 1% slot) of the morning
(+0x2A), day (+0x42) and night (+0x5A) tables: period 0 all three, 1 morning only, else night only.
Static analysis: work/notes/chinese_source_rom_verify_calendar.md.

What the cases observe, on the Chinese ROM and on the English build:

- `table` (deterministic, in `suite`): one emulator per ROM; for every entry the clock is pinned to the day
  before, the player warps onto an encounter tile of the map (MapGrid), then the clock is pinned to the date
  and the player warps again (a normal map entry each time). A hook at the loader's return (0x0203ADA8,
  r4 = map, r5 = buffer) copies the buffer the game built. Expected: the control day equals the ROM's
  encounter record; the date has the configured word in exactly the configured period slots, everything
  else unchanged.
- `battle` (forced-slot test, clearly not the real 1% odds): the land slot picker (ov2 0x02247A0C, and the
  visible-spawn picker arm9 0x02019E3A) gets r0 = 99 (the roll that selects slot 11) before its first
  compare, so every land encounter uses slot 11. The rest is the game's own: walking in the grass with a
  Lv100 Ninjask lead (party count 1), the wild Pokemon built by the finalizer (species, form, level, stats,
  IVs, nature), a screenshot of the battle, then a Master Ball through the battle bag, the party afterwards
  (species, form, level, stats; which personal entry the stats fit) and its summary page.
- `volcanion`: April 16 at Lake of Rage (walk rate 0) with the slot forced: walk 400 steps per period and
  count battles; plus a static scan of every other source (scripts, encounter/headbutt/contest tables,
  trades) for species 721.
- `stale`: load Mt. Silver on July 17 at night, pin July 18 night without reloading, forced battle (does the
  buffer refresh by itself?), then re-enter and battle again.

    .venv/bin/python work/tools/emu_harness.py calendar [--case table,battle,volcanion,stale] [--lang cn|en|both]
"""
import datetime
import json
import struct
from pathlib import Path

import emu_harness as E
import emu_guide0107 as G

LOADER = 0x0203AD24
LOADER_END = 0x0203ADA8          # add sp, #0x1c; pop {r4, r5, pc}: r4 = map, r5 = encounter buffer
CAL_TABLE = 0x020F6A64
LAND_PICK_CMP = 0x02247A0C       # ov2: cmp r0, #0x14 with r0 = Random % 100 (land slot picker 0x022479F8)
VISIBLE_PICK_CMP = 0x02019E3A    # arm9: the same chain in the visible-spawn code
CODE = {LOADER: "30b587b00c1c0021c422051c", LOADER_END: "07b030bd", 0x0203AD84: "6885", VISIBLE_PICK_CMP: "142801d2"}
OV2_CODE = {LAND_PICK_CMP: "142801d2"}
SLOT11 = {"morning": 0x2A, "day": 0x42, "night": 0x5A}
PERIOD_HOURS = {"morning": 6, "day": 12, "night": 22}
MASTER_BALL = 1
FAST_LEAD = 291
ENCOUNTER_TILES = (0x02, 0x03, 0x08)   # tall grass, very tall grass, cave/forest floor (Ilex Forest)
BATTLE_BAG = {"balls": (192, 56), "first": (64, 28), "use": (100, 173)}

# name: (month, day, map, species, form, period selector, level of slot 11) from the table at 0x020F6A64
ENTRIES = {
    "keldeo": (6, 23, 181, 647, 0, 0, 5),
    "meloetta": (7, 14, 117, 648, 0, 0, 6),
    "genesect": (8, 11, 113, 649, 0, 0, 5),
    "floette": (10, 16, 96, 670, 5, 0, 14),
    "diancie": (7, 19, 492, 719, 4, 0, 17),
    "hoopa": (7, 18, 90, 720, 0, 1, 50),
    "hoopa_unbound": (7, 18, 90, 720, 1, 2, 50),
    "volcanion": (4, 16, 88, 721, 0, 0, 0),
}


def periods_of(sel):
    return ("morning", "day", "night") if sel == 0 else ("morning",) if sel == 1 else ("night",)


# ----------------------------------------------------------------------------- static data
_ROM = {}


def rom_data(rom):
    """Encounter records (a/0/3/7), personal data (a/0/0/2), the calendar table, the form table."""
    key = str(Path(rom).resolve())
    if key not in _ROM:
        import ndspy.narc
        import ndspy.rom
        r = ndspy.rom.NintendoDSRom.fromFile(key)
        arm9 = r.loadArm9().sections[0]
        a9 = lambda addr, n: bytes(arm9.data[addr - arm9.ramAddress:addr - arm9.ramAddress + n])
        forms = {}
        for i in range(415):                       # romdata.FORM_TABLE: {u16 species, u16 personal, u16 form}
            sp, tgt, form = struct.unpack_from("<HHH", a9(0x020FEDC0 + 6 * i, 6))
            forms[(sp, form)] = tgt
        _ROM[key] = {"enc": [bytes(f) for f in ndspy.narc.NARC(r.getFileByName("a/0/3/7")).files],
                     "personal": [bytes(f) for f in ndspy.narc.NARC(r.getFileByName("a/0/0/2")).files],
                     "table": [struct.unpack_from("<BBHHBB", a9(CAL_TABLE + 8 * i, 8)) for i in range(8)],
                     "forms": forms, "rom": r}
    return _ROM[key]


def encounter_tiles(rom, map_id, behaviours=ENCOUNTER_TILES):
    """Pairs of side-by-side encounter tiles inside the map's own chunks (outdoor maps share matrix 0)."""
    import ndspy.narc
    g = E.MapGrid(rom, map_id)
    r = rom_data(rom)["rom"]
    arm9 = r.loadArm9().sections[0]
    hdr = arm9.data[E.MAP_HEADERS - arm9.ramAddress + 0x18 * map_id:][:0x18]
    mx = ndspy.narc.NARC(r.getFileByName("a/0/4/1")).files[struct.unpack_from("<H", hdr, 4)[0]]
    w, h, has_headers, _, name_len = mx[:5]
    own = None
    if has_headers:
        zones = struct.unpack_from("<%dH" % (w * h), mx, 5 + name_len)
        own = {(k % w, k // w) for k, z in enumerate(zones) if z == map_id}
    tiles = {t for b in behaviours for t in g.find(b) if own is None or (t[0] // 32, t[1] // 32) in own}
    pairs = sorted((x, y) for x, y in tiles if (x + 1, y) in tiles)
    return pairs


def decode_buffer(buf):
    w = lambda o: struct.unpack_from("<H", buf, o)[0]
    return {"walk_rate": buf[0], "slot11_level": buf[8 + 11],
            "slot11": {p: {"species": w(o) & 0x7FF, "form": w(o) >> 11, "word": w(o)} for p, o in SLOT11.items()}}


def expected_buffer(rom, name, on_date):
    """The buffer the hook should build for an entry's map: the ROM record, plus the configured overwrite(s)
    on the date (every record for that map and date, e.g. both Hoopa rows)."""
    d = rom_data(rom)
    month, day, map_id = ENTRIES[name][:3]
    bank = E.MapGrid(rom, map_id).wild_bank
    buf = bytearray(d["enc"][bank][:0xC4])
    if on_date:
        for m, dd, mp, sp, form, sel in d["table"]:
            if (m, dd, mp) == (month, day, map_id):
                for p in periods_of(sel):
                    struct.pack_into("<H", buf, SLOT11[p], sp | form << 11)
    return bytes(buf)


# ----------------------------------------------------------------------------- hooks
class LoaderLog:
    """Every run of the encounter loader: (frame, map, buffer address, buffer bytes)."""

    def __init__(self, h):
        self.rows = []
        h.on_exec(LOADER_END, lambda h: self.rows.append(
            {"frame": h.frame, "map": h.reg.r4, "buf": h.reg.r5, "data": h.read(h.reg.r5, 0xC4)}))

    def last(self, map_id):
        return next((r for r in reversed(self.rows) if r["map"] == map_id), None)


def force_slot11(h):
    """Forced-slot test only: the land slot pickers see the roll 99 (slot 11) instead of Random % 100."""
    def f(h):
        h.reg.r0 = 99
    h.on_exec(LAND_PICK_CMP, f)
    h.on_exec(VISIBLE_PICK_CMP, f)


def full_mon(raw):
    """decode_party_pokemon plus IVs, EVs, nature and the party stats (Gen 4 layout)."""
    mon = E.decode_party_pokemon(raw)
    pid, _, checksum = struct.unpack_from("<IHH", raw, 0)
    words = struct.unpack_from("<64H", raw, 8)
    flags = struct.unpack_from("<H", raw, 4)[0]
    plain = list(words) if flags & 3 else [a ^ k for a, k in zip(words, E._prng_stream(checksum, 64))]
    data = struct.pack("<64H", *plain)
    order = E.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    blk = {n: data[32 * i:32 * i + 32] for i, n in enumerate(order)}
    ivw = struct.unpack_from("<I", blk["B"], 0x10)[0]
    mon["ivs"] = [(ivw >> (5 * i)) & 31 for i in range(6)]              # HP Atk Def Spe SpA SpD
    mon["evs"] = list(blk["A"][0x10:0x16])
    mon["nature"] = pid % 25
    ext = struct.pack("<50H", *[a ^ k for a, k in zip(struct.unpack_from("<50H", raw, 136), E._prng_stream(pid, 50))])
    mon["stats"] = list(struct.unpack_from("<6H", ext, 8))                # max HP, Atk, Def, Spe, SpA, SpD
    return mon


def calc_stats(base, level, ivs, evs, nature):
    up, down = nature // 5, nature % 5
    out = [(2 * base[0] + ivs[0] + evs[0] // 4) * level // 100 + level + 10]
    for i in range(1, 6):
        v = (2 * base[i] + ivs[i] + evs[i] // 4) * level // 100 + 5
        if up != down:
            v = v * 110 // 100 if i - 1 == up else v * 90 // 100 if i - 1 == down else v
        out.append(v)
    return out


def personal_fit(rom, mon):
    """Which personal entries (the species' own, and its form entry if the form table has one) give exactly
    the stats the game stored."""
    d = rom_data(rom)
    cands = {mon["species"]: "base"}
    if (mon["species"], mon["form"]) in d["forms"]:
        cands[d["forms"][(mon["species"], mon["form"])]] = f"form {mon['form']}"
    fit = {}
    for idx, label in cands.items():
        p = d["personal"][idx]
        base = [p[0], p[1], p[2], p[3], p[4], p[5]]
        fit[idx] = {"label": label, "types": [p[6], p[7]],
                    "match": calc_stats(base, mon["level"], mon["ivs"], mon["evs"], mon["nature"]) == mon["stats"]}
    return fit


# ----------------------------------------------------------------------------- recipes
def session(rom, out, clock):
    def ed(sf):
        sf.set_pocket("balls", [(MASTER_BALL, 50)])
    return E.start_at(None, rom=rom, out=out, verbose=False, clock=clock, edit=ed)


def go_to_tiles(h, rom, map_id, which=0):
    """Warp onto the first (which=0) or middle (-1) pair of encounter tiles; a map without any (Lake of Rage)
    gets a pair of plain walkable tiles (behaviour 0) instead."""
    pairs = encounter_tiles(rom, map_id) or encounter_tiles(rom, map_id, (0x00,))
    x, y = pairs[min(which, len(pairs) - 1) if which >= 0 else len(pairs) // 2]
    h.warp(map_id, x, y, E.DIRS["RIGHT"])
    h.step(60)
    return (x, y)


def case_table(rom, out):
    """All entries in one emulator: day before, then the date, a fresh warp onto the map each time."""
    res = {}
    with session(rom, out, datetime.datetime(2026, 1, 5, 12)) as h:
        h.check_code(CODE)
        ram_table = [struct.unpack_from("<BBHHBB", h.read(CAL_TABLE + 8 * i, 8)) for i in range(8)]
        log = LoaderLog(h)
        for name, (month, day, map_id, *_rest) in ENTRIES.items():
            date = datetime.datetime(2026, month, day, 12)
            row = {}
            for tag, when, which in (("control", date - datetime.timedelta(days=1), 0), ("date", date, -1)):
                h.set_clock(when)
                n = len(log.rows)
                tile = go_to_tiles(h, rom, map_id, which)
                got = next((r for r in reversed(log.rows[n:]) if r["map"] == map_id), None)
                want = expected_buffer(rom, name, tag == "date")
                row[tag] = {"clock": when.isoformat(), "tile": tile, "pos": h.position(),
                            "loads": [r["map"] for r in log.rows[n:]],
                            "buffer": decode_buffer(got["data"]) if got else None,
                            "equals_expected": bool(got) and got["data"] == want,
                            "equals_rom_record": bool(got) and got["data"] == expected_buffer(rom, name, False)}
            res[name] = row
    ok = all(r["control"]["equals_rom_record"] and r["date"]["equals_expected"]
             and not r["date"]["equals_rom_record"] for r in res.values())
    return {"verdict": "confirmed" if ok else "contradicted", "ram_table": ram_table,
            "rom_table": rom_data(rom)["table"], "entries": res}


def catch_with_master_ball(h, tag):
    """Battle command menu -> BAG -> Poke Balls -> first ball (Master Ball) -> Use; then A through the catch
    messages and the Pokedex page until the field is back. Returns screenshots."""
    shots = []
    h.touch(*E.BATTLE_BUTTONS["bag"], frames=10, after=120)
    h.touch(*BATTLE_BAG["balls"], frames=10, after=120)
    h.touch(*BATTLE_BAG["first"], frames=10, after=120)
    h.touch(*BATTLE_BAG["use"], frames=10, after=600)
    for i in range(20):
        if h.in_field():
            break
        if i in (0, 2, 3):
            shots.append(str(h.screenshot(f"{tag}_catch_{i}")))
        h.press("A", after=200)
    h.step(120)
    return shots, h.in_field()


def open_summary(h, slot, tag):
    h.press("B", after=30)
    h.field_menu("pokemon")
    h.touch(*E.PARTY_SLOTS[slot], frames=12, after=60)
    h.touch(*E.PARTY_SUMMARY, frames=12, after=200)
    shots = [str(h.screenshot(f"{tag}_summary_1"))]
    h.press("RIGHT", after=90)
    shots.append(str(h.screenshot(f"{tag}_summary_2")))
    return shots


def pace(h, rom, map_id, done, max_steps):
    """Walk RIGHT/LEFT one tile at a time (position checked) until done() or max_steps. When neither direction
    moves (a visible Pokemon or the follower in the way), warp to another pair of encounter tiles."""
    pairs = encounter_tiles(rom, map_id) or encounter_tiles(rom, map_id, (0x00,))
    steps, warps = 0, 0
    h.other_battles = []
    while not done() and steps < max_steps:
        if not h.in_field():                 # a battle the wild finalizer did not build (seen once: a Lv48
            h.step(300)                      # Typhlosion on the English build), not a slot-11 encounter
            if done():
                break
            if not h.in_field():
                h.other_battles.append(str(h.screenshot(f"other_battle_{len(h.other_battles)}")))
                if not h.flee():             # e.g. a trainer who saw the player: give up this run
                    break
                continue
        moved = False
        for d in ("RIGHT", "LEFT"):
            moved |= h.step_dir(d) or (not done() and h.in_field() and h.step_dir(d))
            steps += 1
            if done() or not h.in_field():
                break
        if not moved and not done() and h.in_field():
            h.step(90)                       # a battle may be starting (the field is still up during its intro)
            if done() or not h.in_field():
                continue
            warps += 1
            x, y = pairs[(7 * warps) % len(pairs)]
            try:
                h.warp(map_id, x, y, E.DIRS["RIGHT"])
            except RuntimeError:             # A did not reach the field (a battle or a message): look again
                h.press("B", after=30)
            h.step(60)
    return steps, warps


def forced_battle(h, rom, map_id, tag, max_steps=1500, catch=True):
    """Pace on encounter tiles with slot 11 forced until a wild Pokemon is built; screenshot; Master Ball."""
    wl = E.WildLog(h, on_mon=lambda h, a: setattr(h, "_wild_raw", h.read(a, 236)))
    steps, warps = pace(h, rom, map_id, lambda: bool(wl.rows), max_steps)
    if not wl.rows:
        return {"steps": steps, "warps": warps, "battle": False, "pos": h.position(), "other_battles": h.other_battles,
                "shot": str(h.screenshot(f"{tag}_no_battle"))}
    wild = full_mon(h._wild_raw)
    res = {"steps": steps, "warps": warps, "battle": True, "other_battles": h.other_battles, "wild": {k: wild[k] for k in
                                                    ("species", "form", "level", "stats", "ivs", "nature", "pid")},
           "wild_count": len(wl.rows), "wild_fit": personal_fit(rom, wild)}
    h.wait_screen("battle_menu", 1500)
    res["battle_shot"] = str(h.screenshot(f"{tag}_battle"))
    if not catch:
        h.flee()
        return res
    count = h.u32(h.array(E.ARR_PARTY) + 4)
    res["catch_shots"], res["back_in_field"] = catch_with_master_ball(h, tag)
    party = h.array(E.ARR_PARTY)
    res["party_count"] = (count, h.u32(party + 4))
    if h.u32(party + 4) == count + 1:
        mon = full_mon(h.read(party + 8 + 236 * count, 236))
        res["caught"] = {k: mon[k] for k in ("species", "form", "level", "stats", "pid", "checksum_ok")}
        res["caught_fit"] = personal_fit(rom, mon)
        res["summary_shots"] = open_summary(h, count, tag)
    return res


def battle_time(period):
    """'morning' / 'day' / 'night' (06:00, 12:00, 22:00) or an exact 'hh:mm'."""
    if period in PERIOD_HOURS:
        return PERIOD_HOURS[period], 0
    hh, _, mm = period.partition(":")
    return int(hh), int(mm or 0)


def wild_period(hour):
    """The land table a wild encounter uses at this hour: morning 04-09, day 10-19, night 20-03 (the site's
    windows; the boundary variants of the battle case test them)."""
    return "morning" if 4 <= hour <= 9 else "day" if 10 <= hour <= 19 else "night"


def case_battle(rom, out, variant):
    """variant '<entry>:<period>' (e.g. hoopa:morning) or '<entry>:<hh:mm>' (e.g. hoopa:03:59)."""
    name, _, period = variant.partition(":")
    month, day, map_id, species, form, sel, level = ENTRIES[name]
    hour, minute = battle_time(period)
    clock = datetime.datetime(2026, month, day, hour, minute)
    tag = f"{name}_{period.replace(':', '')}"
    with session(rom, out, clock) as h:
        G.lead(h, FAST_LEAD)
        h.w32(h.array(E.ARR_PARTY) + 4, 1)          # only the lead: the catch goes into the party
        h.check_code(CODE)
        log = LoaderLog(h)
        tile = go_to_tiles(h, rom, map_id, 0)
        h.check_code(OV2_CODE)
        loaded = log.last(map_id)
        force_slot11(h)
        res = forced_battle(h, rom, map_id, tag)
        res.update(entry=name, clock=clock.isoformat(), tile=tile,
                   buffer=decode_buffer(loaded["data"]) if loaded else None, forced_slot=True)
    return res


def judge_battle(name, period, res):
    """Expected: slot 11 of the table for the clock's period, as the hook builds it on that date (both Hoopa
    rows included; a period an entry doesn't patch keeps the ROM record's slot 11)."""
    w = res.get("wild")
    if not w:
        return "blocked"
    buf = expected_buffer(E.DEF_ROM_CN, name, True)
    word = struct.unpack_from("<H", buf, SLOT11[wild_period(battle_time(period)[0])])[0]
    want = (word & 0x7FF, word >> 11, buf[8 + 11])
    got = (w["species"], w["form"], w["level"])
    caught = res.get("caught")
    return "confirmed" if got == want and caught and (caught["species"], caught["form"]) == want[:2] else \
        "contradicted" if got != want else "observed"


def case_volcanion(rom, out, variant):
    """April 16, Lake of Rage, slot 11 forced: no land encounter in 400 steps? variant = period."""
    clock = datetime.datetime(2026, 4, 16, PERIOD_HOURS[variant])
    with session(rom, out, clock) as h:
        G.lead(h, FAST_LEAD)
        log = LoaderLog(h)
        tile = go_to_tiles(h, rom, 88, -1)
        loaded = log.last(88)
        force_slot11(h)
        wl = E.WildLog(h)
        steps, battles, moves = 0, 0, 0
        while steps < 400:
            for d in ("RIGHT", "LEFT"):
                moves += h.step_dir(d)
                steps += 1
                if not h.in_field():
                    battles += 1
                    h.flee(battle_menu_wait=200)
        return {"clock": clock.isoformat(), "tile": tile, "pos": h.position(), "steps": steps, "moves": moves,
                "battles": battles, "grass_tiles": len(encounter_tiles(rom, 88)),
                "wild": [(r["species"], r["form"]) for r in wl.rows],
                "buffer": decode_buffer(loaded["data"]) if loaded else None,
                "shot": str(h.screenshot(f"volcanion_{variant}_field"))}


def volcanion_static(rom):
    """Every other place species 721 could come from: script commands (GiveMon, GiveEgg, WildBattle, any
    SetVar to 721), encounter records (all slots), headbutt trees, the Bug-Catching Contest, NPC trades."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / "docs"))
    import ndspy.narc
    import romdata as R
    r = rom_data(rom)["rom"]
    hits = {"scripts": [], "encounters": [], "headbutt": [], "contest": [], "trades": []}
    for fi, data in enumerate(ndspy.narc.NARC(r.getFileByName("a/0/1/2")).files):
        try:
            _, ins = R.disasm(bytes(data))
        except Exception:
            continue
        for pc, (op, args, _, _) in ins.items():
            if any(isinstance(a, int) and a & 0x7FF == 721 and a < 0x4000 for a in args) and op in (137, 138, 589, 41, 43):
                hits["scripts"].append((fi, pc, op, args))
    for bi, b in enumerate(rom_data(rom)["enc"]):
        e = R.parse_encounter(b)
        sp = e["morning"] + e["day"] + e["night"] + e["hoenn"] + e["sinnoh"] + \
            [s[0] for k in ("surf", "rock", "old", "good", "super") for s in e[k]] + list(e["swarm"].values())
        if any(s & 0x7FF == 721 for s in sp):
            hits["encounters"].append(bi)
    for bi, b in enumerate(ndspy.narc.NARC(r.getFileByName("a/2/5/2")).files):
        hb = R.parse_headbutt(bytes(b))
        if hb and any(s[0] & 0x7FF == 721 for k in ("common", "rare", "secret") for s in hb[k]):
            hits["headbutt"].append(bi)
    for si, rows in enumerate(R.parse_bug_contest(bytes(r.getFileByName("data/mushi/mushi_encount.bin")))):
        hits["contest"] += [si for x in rows if x["species"] == 721]
    for ti, b in enumerate(ndspy.narc.NARC(r.getFileByName("a/1/1/2")).files):
        if len(b) >= 84 and R.parse_trade(bytes(b))["give"] == 721:
            hits["trades"].append(ti)
    others = [row for row in rom_data(rom)["table"] if row[3] == 721]
    return {"hits": hits, "calendar_rows": others}


def case_stale(rom, out):
    """Mt. Silver loaded on July 17 22:00; clock pinned to July 18 22:00 without reloading, forced battle;
    then re-enter (warp) and battle again."""
    res = {}
    with session(rom, out, datetime.datetime(2026, 7, 17, 22)) as h:
        G.lead(h, FAST_LEAD)
        h.w32(h.array(E.ARR_PARTY) + 4, 1)
        log = LoaderLog(h)
        res["tile"] = go_to_tiles(h, rom, 90, -1)
        n = len(log.rows)
        h.set_clock(datetime.datetime(2026, 7, 18, 22))
        force_slot11(h)
        h.step(300)
        a = forced_battle(h, rom, 90, "stale_same_map", catch=False)
        res["same_map"] = {k: a.get(k) for k in ("wild", "battle", "steps", "battle_shot")}
        res["loads_without_warp"] = [r["map"] for r in log.rows[n:]]
        res["buffer_after_battle"] = decode_buffer(log.last(90)["data"])
        go_to_tiles(h, rom, 90, 0)
        b = forced_battle(h, rom, 90, "stale_reentered", catch=False)
        res["reentered"] = {k: b.get(k) for k in ("wild", "battle", "steps", "battle_shot")}
    res["verdict"] = "observed"
    return res


# ----------------------------------------------------------------------------- registry, runner, suite
BATTLES = ["keldeo:day", "meloetta:day", "genesect:day", "floette:day", "diancie:day", "hoopa:morning",
           "hoopa:day", "hoopa_unbound:night", "keldeo:morning", "keldeo:night",
           "hoopa:03:59", "hoopa:04:00", "hoopa:09:59", "hoopa:10:00", "hoopa:19:59", "hoopa:20:00"]
CASES = {
    "table": (case_table, None),
    "battle": (case_battle, tuple(BATTLES)),
    "volcanion": (case_volcanion, ("morning", "day", "night")),
    "stale": (case_stale, None),
}


def out_dir(out, rom):
    import emu_skitty as K
    d = Path(out) / "calendar" / K.lang_of(rom)
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_cases(roms, cases, out, jobs=6, variants=None):
    from concurrent.futures import ThreadPoolExecutor
    variants = variants or {}
    todo = [(c, v, l) for c in cases for v in (variants.get(c) or CASES[c][1] or [None]) for l in roms]

    def run(job):
        c, v, l = job
        try:
            return c, v, l, E.run_child(["calendar", "--child", c + ("@" + v if v else ""), "--rom", roms[l],
                                         "--out", out], timeout=1800)
        except Exception as e:
            return c, v, l, {"verdict": "error", "error": str(e)[-1500:]}
    with ThreadPoolExecutor(jobs) as ex:
        rows = list(ex.map(run, todo))
    report = {}
    for c, v, l, r in rows:
        if c == "battle" and "error" not in r:
            n, _, p = v.partition(":")
            r["verdict"] = judge_battle(n, p, r)
        if c == "volcanion" and "error" not in r:
            r["verdict"] = "confirmed" if r["battles"] == 0 and r["moves"] > 0 else "contradicted"
        if v:
            report.setdefault(c, {}).setdefault(l, {})[v] = r
        else:
            report.setdefault(c, {})[l] = r
    return report


def suite_check(rom, out):
    """emu_harness.py suite: the deterministic table check on one ROM (all eight entries + controls)."""
    report = run_cases({"x": rom}, ["table"], out, jobs=1)
    r = report["table"]["x"]
    return r.get("verdict") == "confirmed", {"verdict": r.get("verdict"), "error": r.get("error"),
                                             "entries": {n: {t: e[t]["equals_expected"] for t in e}
                                                         for n, e in r.get("entries", {}).items()}}


def cmd(a):
    if a.child:
        o = out_dir(a.out, a.rom)
        name, _, variant = a.child.partition("@")
        fn = CASES[name][0]
        res = fn(a.rom, o, variant) if variant else fn(a.rom, o)
        if name == "volcanion" and variant == "day":
            res["static"] = volcanion_static(a.rom)
        print("RESULT " + json.dumps(res, ensure_ascii=False, default=str))
        return 0
    cases = list(CASES) if a.case == "all" else a.case.split(",")
    langs = ["cn", "en"] if a.lang == "both" else [a.lang]
    roms = {l: {"cn": a.rom_cn, "en": a.rom_en}[l] for l in langs}
    variants = {"battle": tuple(a.battles.split(","))} if getattr(a, "battles", None) else None
    report = run_cases(roms, cases, a.out, a.jobs, variants)
    for c in cases:
        for l in langs:
            r = report[c][l]
            if "verdict" in r or "error" in r:
                print(json.dumps({"case": c, "rom": l, "verdict": r.get("verdict"), "error": r.get("error")}))
            else:
                print(json.dumps({"case": c, "rom": l, "verdicts": {v: x.get("verdict") for v, x in r.items()}}))
    name = "_".join(cases if len(cases) < 4 else ["all"]) + ("" if a.lang == "cn" else "_" + a.lang)
    path = Path(a.out) / "calendar" / ("report_" + name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"report": str(path)}))
    return 0
