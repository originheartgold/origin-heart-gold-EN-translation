#!/usr/bin/env python3
"""emu_open - recipes for open behaviour questions left after the earlier rounds (`emu_harness.py open`).

Each case runs on the untouched Chinese ROM (behaviour reference, D-1002) and on the English build, in its own
child process per variant, and returns what the game did plus a verdict:

  arceus    D-1501: does Arceus's stored Plate form (Gen 4 type number, read against the newer form table)
            change its in-battle type? Arceus Lv100 from the generator gets the Plate through Bag -> Give (the
            game's own form code runs), leads with Splash + Judgment; a scripted wild Pokemon that knows one
            probe move attacks it. The probe's effectiveness tells the defending type, Judgment's
            effectiveness tells the move type (battle_string reads through MsgLog). Each Plate is chosen so
            that the Plate type and the type of the personal entry the stored form points at disagree.
  thief     Thief in a wild battle (control for the trainer-battle Thief result): the wild Pokemon holds an
            item the game rolled itself (Miltank: Moomoo Milk, 100 %) or one set in its RAM copies before the
            battle copies its party (Rattata + Eviolite). Lead: Chansey Lv100 with Thief / Seismic Toss.
  rockruff  D-1486: Rockruff Lv24 one experience point short of Lv25 wins a wild battle; the level-up after the
            battle evolves it (a different caller than the Rare Candy path); the form byte written by the
            evolution code (0x02074B0E) and the stored form are logged, by day and at the evening/night controls.
  primal    Groudon/Kyogre holding the Red/Blue Orb, in battle: own (generator + Bag -> Give) and wild (orb set
            in the wild Pokemon's copies). Does anything read the Primal Reversion strings (1#1666-1671) or
            change the form (party copies in battle, party after)?
  palpark   Nanab Berry (Pal Park prize): enter the Fixed Catch show through the receptionist (file 809), catch
            Pokemon with Master Balls and watch the show's caught flags (0x021D3214 +0x30) and whether file 12
            script 3 (the "caught the stocked Pokemon" scene that leads to the score and prize) ever runs.

    .venv/bin/python work/tools/emu_harness.py open [--case arceus,thief:miltank,...] [--lang cn|en|both]

Wild Pokemon held items / moves (found here): the wild finalizer's Pokemon is a temporary copy. The battle copies
its parties from the BattleSetup party about 130 frames after the finalizer (two copies, battle overlay), so the
finalizer edit used by the earlier Thief control never reached the battle. `wild_battle` edits every RAM copy
with the wild Pokemon's PID right after the finalizer instead (observed: the battle copies then hold the item).

Screenshots: <out>/open/<lang>/; report <out>/open/report_<cases>.json.
"""
import datetime
import json
import struct
from pathlib import Path

import emu_harness as E
import emu_skitty as K
import emu_guide0107 as G
import emu_guide0813 as M
import emu_verify as V

CLOCK = G.CLOCK                     # Friday 2026-10-09 12:00
NARC_BATTLE = 277                   # battle_string.narc (MsgLog rows: narc, bank, id, frame)
MOVE_NAMES = 739                    # a027 bank of move names
USED = {2179: "player", 2180: "wild", 2181: "foe"}          # 1#2179-2181 "<mon> used <move>!"
EFFECT = {(2, 74): "super", (2, 75): "not_very"}
EFFECT.update({(1, i): "super" for i in range(8, 24)})
EFFECT.update({(1, i): "not_very" for i in range(24, 40)})
EFFECT.update({(1, i): "no_effect" for i in range(288, 292)})
EFFECT.update({(1, i): "missed" for i in range(292, 296)})       # 1#292-295 "... avoided the attack!"
STOLE = set(range(622, 626)) | set(range(1432, 1442))        # 1#622-625 "It stole ...", 1#1432-1441
PRIMAL = set(range(1666, 1672))                              # 1#1666-1671 "... Primal Reversion!"
MEGA = set(range(1576, 1580)) | set(range(1676, 1680))

SPLASH, JUDGMENT, TACKLE, SEISMIC = 150, 449, 33, 69
THIEF = 168
CHANSEY, ARCEUS, ROCKRUFF, GROUDON, KYOGRE = 113, 493, 744, 383, 382
RED_ORB, BLUE_ORB = 534, 535
MASTER_BALL = 1


def out_dir(out, rom):
    d = Path(out).resolve() / "open" / K.lang_of(rom)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ----------------------------------------------------------------------------- Pokemon data helpers
def with_exp(raw, exp):
    """Explicit fixture edit; cached party level/stats stay stale for native level-up tests."""
    return E.encode_pokemon(raw, exp=exp)


def exp_of(raw):
    return E.decode_pokemon(raw)["exp"]


def moveset(moves, pp):
    """Four move slots (the rest emptied) and their PP: encode_pokemon only replaces the slots it is given."""
    moves, pp = list(moves) + [0] * (4 - len(moves)), list(pp) + [0] * (4 - len(pp))
    return {"moves": moves, "pp": pp}


def pid_copies(h, pid, lo=0x02200000, hi=0x02400000):
    """Addresses of every RAM copy of a Pokemon with this PID (valid checksum)."""
    ram = h.read(lo, hi - lo)
    key = struct.pack("<I", pid)
    out, i = [], ram.find(key)
    while i >= 0:
        if i % 4 == 0 and E.decode_pokemon(ram[i:i + 136])["checksum_ok"]:
            out.append(lo + i)
        i = ram.find(key, i + 1)
    return out


def copies_state(h, pid):
    """[(address, species, form, item)] of every copy of a Pokemon (e.g. the battle's party copies)."""
    return [(hex(a), *(lambda m: (m["species"], m["form"], m["item"]))(E.decode_pokemon(h.read(a, 136))))
            for a in pid_copies(h, pid)]


def wild_battle(h, species, level, item=None, moves=None, pp=None, form=None):
    """Start a scripted WildBattle and, right after the wild finalizer, give the wild Pokemon an item / moves /
    form in every RAM copy (the battle copies the BattleSetup party ~130 frames later, so the edit holds).
    Returns {pid, copies edited, finalizer row}."""
    log = E.WildLog(h)
    h.run_script(program=E.script_bytes(("LockAll",), ("WildBattle", species, level, 0), ("ReleaseAll",),
                                        ("End",)))
    if not h.run_until(lambda h: log.rows, 900):
        raise RuntimeError("no wild Pokemon built")
    row = log.rows[0]
    fields = {k: v for k, v in (("item", item), ("form", form)) if v is not None}
    if moves is not None:
        fields.update(moveset(moves, pp or [30] * len(moves)))
    cps = pid_copies(h, row["pid"])
    if fields:
        for a in cps:
            h.write(a, E.encode_pokemon(h.read(a, 136), **fields))
    for addr in (E.WILD_FINALIZE, E.WILD_FINALIZE_SETFORM, E.WILD_FINALIZE_AFTER_SET, E.WILD_FINALIZE_RESTORE,
                 E.WILD_FINALIZE_END):
        h.on_exec(addr, None)
    return {"pid": row["pid"], "copies": [hex(a) for a in cps], "finalizer": {k: row[k] for k in
            ("species", "form", "item")}}


def give_via_bag(h, item, slot):
    """Bag -> Give <item> to party <slot> (the party-menu form code runs), back to the field."""
    h.bag_put_first(item)
    h.open_bag()
    h.give_from_bag(0, slot)
    h.screenshot(f"give_{item}")
    for _ in range(3):                   # bag -> field menu -> field (a third B is harmless in the field)
        h.press("B", after=120)
    return h.party()[slot]


def battle_events(ml, since=0):
    """The battle's message reads, grouped per 'used' message: [{side, move, effect, reads}]; plus a list of
    every (bank, id) battle_string read."""
    events, cur, reads = [], None, []
    for narc, b, i, fr in ml.rows[since:]:
        if narc == NARC_BATTLE:
            reads.append((b, i))
            if b == 1 and i in USED:
                cur = {"side": USED[i], "move": None, "effect": "normal", "reads": []}
                events.append(cur)
            elif cur is not None:
                cur["reads"].append((b, i))
                if (b, i) in EFFECT and cur["effect"] == "normal":
                    cur["effect"] = EFFECT[(b, i)]
        elif narc == V.MSG_NARC_A027 and b == MOVE_NAMES and cur is not None and cur["move"] is None:
            cur["move"] = i
    return events, reads


def info_panel(h, tag):
    """Battle command menu -> INFO (the active Pokemon's panel), screenshot, back."""
    h.touch(*E.BATTLE_BUTTONS["info"], frames=10, after=150)
    shot = str(h.screenshot(tag))
    h.press("B", after=90)
    if not h.wait_screen("battle_menu", 600):
        h.press("B", after=90)
    return shot


def turn(h, ml, action, pages=None):
    """One command (move slot or 'run') with the sweeps' turn driver (B through messages). pages: a list that
    gets every distinct battle message window of the turn (PIL images)."""
    import emu_sweeps as S
    log = S.BattleLog(h, ml, None)
    r = S.b_turn(h, log, action)
    if pages is not None:
        pages.extend(img for _, _, img in log.shots)
    return r


def page_sheet(pages, dest):
    """The battle message windows of <pages> stacked into one image."""
    from PIL import Image
    crops = [p.convert("RGB").crop((0, 140, 256, 192)) for p in pages]
    if not crops:
        return None
    sheet = Image.new("RGB", (256, 52 * len(crops)), (0, 0, 0))
    for i, c in enumerate(crops):
        sheet.paste(c, (0, 52 * i))
    sheet.save(dest)
    return str(dest)


def end_battle(h, ml, plan=("run",), max_turns=12):
    """Play the plan's last action until the battle is over (field back)."""
    for k in range(max_turns):
        if h.in_field():
            return True
        r = turn(h, ml, plan[min(k, len(plan) - 1)])
        if r == "field":
            return True
    return h.in_field()


# ----------------------------------------------------------------------------- arceus (D-1501)
# variant: (plate item, plate type, type of personal entry 1153 + stored form, foe species, foe probe move;
#           expected probe effectiveness if Arceus has the Plate type / the personal-entry type,
#           expected Judgment effectiveness on the foe for the same two readings)
ARCEUS_CASES = {
    "flame": (298, "Fire", "Water", 114, 55, ("super", "not_very"), ("super", "not_very")),        # Tangela, Water Gun
    "splash": (299, "Water", "Grass", 126, 84, ("super", "not_very"), ("super", "not_very")),      # Magmar, ThunderShock
    "zap": (300, "Electric", "Psychic", 54, 89, ("super", "normal"), ("super", "normal")),        # Psyduck, Earthquake
    "dread": (312, "Dark", "Fairy", 96, 2, ("super", "not_very"), ("super", "normal")),           # Drowzee, Karate Chop
    "fist": (303, "Fighting", "Fighting", 19, 16, ("super", "super"), ("super", "super")),        # Rattata, Gust (control)
}


def case_arceus(rom, out, variant):
    plate, ptype, etype, foe, probe, exp_probe, exp_judg = ARCEUS_CASES[variant]
    o = out_dir(out, rom)
    with M.session(rom, o, clock=CLOCK) as h:
        h.generate_pokemon(ARCEUS, level=100)
        slot = h.generated_slot
        given = give_via_bag(h, plate, slot)
        h.edit_party_mon(slot, **moveset([SPLASH, JUDGMENT], [40, 10]))
        h.swap_party(0, slot)
        lead = h.party()[0]
        ml = V.MsgLog(h)
        m0 = ml.mark()
        wb = wild_battle(h, foe, 50, moves=[probe], pp=[30])
        if not h.wait_screen("battle_menu", 2000):
            raise RuntimeError("battle menu not reached")
        start = str(h.screenshot(f"arceus_{variant}_battle"))
        info = info_panel(h, f"arceus_{variant}_info")
        own = copies_state(h, lead["pid"])
        pages = []
        results = [turn(h, ml, 0, pages)]               # Splash: the foe's probe hits Arceus
        for _ in range(3):                              # Judgment (again after a miss)
            if results[-1] != "menu":
                break
            results.append(turn(h, ml, 1, pages))
            if [e["effect"] for e in battle_events(ml, m0)[0] if e["move"] == JUDGMENT][-1:] != ["missed"]:
                break
        end_shot = str(h.screenshot(f"arceus_{variant}_after"))
        sheet = page_sheet(pages, Path(o) / f"arceus_{variant}_pages.png")
        if not h.in_field():
            end_battle(h, ml, ("run",))
        events, reads = battle_events(ml, m0)
        return {"plate": plate, "plate_type": ptype, "entry_type": etype, "stored_form": given["form"],
                "lead": {k: lead[k] for k in ("species", "form", "item")}, "battle_copies": own,
                "wild": wb, "turns": results, "events": events, "reads": reads,
                "expected_probe": exp_probe, "expected_judgment": exp_judg,
                "shots": [start, info, end_shot], "sheet": sheet}


def judge_arceus(res):
    """'plate_type' when the probe and Judgment behave as for the Plate's type, 'entry_type' when as for the
    personal entry the stored form points at, 'unclear' otherwise."""
    probe = [e["effect"] for e in res["events"] if e["side"] == "wild" and e["effect"] != "missed"]
    judg = [e["effect"] for e in res["events"] if e["side"] == "player" and e["move"] == JUDGMENT
            and e["effect"] != "missed"]
    if not probe or not judg:
        return "unclear"
    p, j = probe[0], judg[0]
    ep, ej = res["expected_probe"], res["expected_judgment"]
    if p == ep[0] and j == ej[0]:
        return "plate_type"
    if p == ep[1] and j == ej[1]:
        return "entry_type"
    return "unclear"


# ----------------------------------------------------------------------------- thief in a wild battle
THIEF_WILD = {   # variant: (foe species, level, item to set or None = the game's own roll, expected item)
    "miltank": (241, 20, None, 33),      # Moomoo Milk: personal item 1 = item 2, so the game always gives it
    "eviolite": (19, 20, 584, 584),      # Rattata given an Eviolite in its RAM copies (the trainer-case item)
    "control": (241, 20, None, 33),      # Miltank again, no Thief (Seismic Toss only): does the bag change anyway?
}


def case_thief(rom, out, variant):
    foe, level, item, expect = THIEF_WILD[variant]
    o = out_dir(out, rom)
    with M.session(rom, o, clock=CLOCK) as h:
        G.lead(h, CHANSEY, level=100, **moveset([THIEF, SEISMIC], [25, 20]))
        h.edit_party_mon(0, item=0)
        before = E.bag_items(h)
        ml = V.MsgLog(h)
        m0 = ml.mark()
        wb = wild_battle(h, foe, level, item=item)
        if not h.wait_screen("battle_menu", 2000):
            raise RuntimeError("battle menu not reached")
        foe_items = [c[3] for c in copies_state(h, wb["pid"])]
        pages = []
        thief_turns = 0 if variant == "control" else 2
        results = ["menu"]
        for _ in range(thief_turns):                    # Thief (twice: the first can miss)
            if results[-1] == "menu":
                results.append(turn(h, ml, 0, pages))
        k = 0
        while results[-1] == "menu" and k < 10:
            results.append(turn(h, ml, 1, pages))       # Seismic Toss until the battle is won
            k += 1
        m1 = ml.mark()
        h.step(120)
        events, reads = battle_events(ml, m0)
        after = E.bag_items(h)
        lead = h.party()[0]
        stole = [r for r in reads if r[0] == 1 and r[1] in STOLE]
        sheet = page_sheet(pages, Path(o) / f"thief_wild_{variant}_pages.png")
        field = str(h.screenshot(f"thief_wild_{variant}_field"))
        return {"foe": foe, "foe_items_in_battle": foe_items, "set_item": item, "expected_item": expect,
                "turns": results[1:], "stole_reads": stole, "events": events,
                "lead_item_after": lead["item"], "lead_species": lead["species"],
                "bag_change": M.bag_change(before, after), "reads_at_end": ml.rows[m1 - 12:],
                "sheet": sheet, "shots": [field]}


def judge_thief(res):
    if res["turns"] and res.get("stole_reads") == [] and not any(e["move"] == THIEF for e in res["events"]):
        return "control"           # no Thief used
    if res["expected_item"] not in res["foe_items_in_battle"]:
        return "unclear"           # the wild Pokemon did not hold the item in battle
    if not res["stole_reads"]:
        return "not_stolen"
    return "kept" if res["lead_item_after"] == res["expected_item"] else "lost"


# ----------------------------------------------------------------------------- rockruff (D-1486)
ROCKRUFF_RUNS = {   # variant: (hour, minute, foe species, foe level)
    "12a": (12, 0, 19, 2), "12b": (12, 0, 16, 3), "12c": (12, 0, 161, 2),
    "15a": (15, 0, 19, 2), "15b": (15, 0, 16, 3), "15c": (15, 0, 161, 2),
    "18": (18, 0, 19, 2), "22": (22, 0, 19, 2),
}
EXP_LV25_MEDIUM_FAST = 25 ** 3       # Rockruff's growth rate 0 (Medium Fast): 15625 exp at Lv25


def win_without_b(h, max_frames=9000, every=40):
    """A battle where B would cancel an evolution: press only A (advances messages; at the command menu A
    picks FIGHT and the first move) until the field is back. Returns 'field' or 'timeout'."""
    for i in range(0, max_frames, every):
        h.step(every)
        if h.in_field():
            h.step(60)
            return "field"
        h.press("A", after=0)
    return "timeout"


def case_rockruff(rom, out, variant):
    hour, minute, foe, flv = ROCKRUFF_RUNS[variant]
    clock = datetime.datetime(2026, 10, 9, hour, minute)
    o = out_dir(out, rom)
    form_writes = []

    def hooks(h):
        h.on_exec(E.LYCANROC_SETFORM, lambda h: form_writes.append(h.u8(h.reg.r2)))
    with E.start_at(None, rom=rom, out=o, verbose=False, clock=clock, hooks=hooks) as h:
        G.lead(h, ROCKRUFF, level=24, **moveset([TACKLE], [35]))
        a = h.array(E.ARR_PARTY) + 8
        h.write(a, with_exp(h.read(a, 136), EXP_LV25_MEDIUM_FAST - 1))
        before = h.party()[0]
        exp_before = exp_of(h.read(a, 136))
        wild_battle(h, foe, flv)
        if not h.wait_screen("battle_menu", 2000):
            raise RuntimeError("battle menu not reached")
        end = win_without_b(h)
        after = h.party()[0]
        shot = str(h.screenshot(f"rockruff_{variant}_field"))
        h.field_menu("pokemon")
        h.touch(*E.PARTY_SLOTS[0], frames=12, after=60)
        h.touch(*E.PARTY_SUMMARY, frames=12, after=150)
        summ = str(h.screenshot(f"rockruff_{variant}_summary"))
        return {"clock": h.clock(), "foe": foe, "exp_before": exp_before, "level_before": before["level"],
                "end": end, "form_written": form_writes, "after": {k: after[k] for k in
                ("species", "form", "level")}, "shots": [shot, summ]}


def judge_rockruff(res):
    a = res["after"]
    if a["species"] != 745:
        return "no_evolution"
    return {0: "midday", 1: "midnight", 2: "dusk"}.get(a["form"], f"form_{a['form']}")


# ----------------------------------------------------------------------------- primal (Red/Blue Orb)
PRIMAL_CASES = {   # variant: (side, species, orb)
    "groudon_own": ("own", GROUDON, RED_ORB), "kyogre_own": ("own", KYOGRE, BLUE_ORB),
    "groudon_wild": ("wild", GROUDON, RED_ORB), "kyogre_wild": ("wild", KYOGRE, BLUE_ORB),
}


def case_primal(rom, out, variant):
    side, species, orb = PRIMAL_CASES[variant]
    o = out_dir(out, rom)
    with M.session(rom, o, clock=CLOCK) as h:
        if side == "own":
            h.generate_pokemon(species, level=100)
            slot = h.generated_slot
            given = give_via_bag(h, orb, slot)          # the orb's bag menu has no Give: item stays 0
            h.edit_party_mon(slot, item=orb, **moveset([SPLASH], [40]))   # so the item is set directly
            h.swap_party(0, slot)
            mon = h.party()[0]
            ml = V.MsgLog(h)
            m0 = ml.mark()
            wb = wild_battle(h, 19, 5, moves=[SPLASH], pp=[40])
            pid = mon["pid"]
        else:
            G.lead(h, E.FAST_LEAD, level=100, **moveset([SPLASH], [40]))
            ml = V.MsgLog(h)
            m0 = ml.mark()
            wb = wild_battle(h, species, 70, item=orb, moves=[SPLASH], pp=[40])
            pid, given = wb["pid"], None
        if not h.wait_screen("battle_menu", 2500):
            raise RuntimeError("battle menu not reached")
        start = str(h.screenshot(f"primal_{variant}_battle"))
        info = info_panel(h, f"primal_{variant}_info") if side == "own" else None
        in_battle = copies_state(h, pid)
        pages = []
        r = turn(h, ml, 0, pages)
        mid = str(h.screenshot(f"primal_{variant}_turn1"))
        sheet = page_sheet(pages, Path(o) / f"primal_{variant}_pages.png")
        in_battle_2 = copies_state(h, pid) if not h.in_field() else None
        if not h.in_field():
            end_battle(h, ml, ("run",))
        events, reads = battle_events(ml, m0)
        after = h.party()[0] if side == "own" else None
        return {"side": side, "species": species, "orb": orb,
                "after_bag_give": {k: given[k] for k in ("species", "form", "item")} if given else None,
                "give_menu_shot": str(Path(o) / f"give_{orb}.png") if given else None,
                "wild": wb, "copies_battle_start": in_battle, "copies_after_turn1": in_battle_2, "turn": r,
                "primal_reads": [x for x in reads if x[0] == 1 and x[1] in PRIMAL],
                "mega_reads": [x for x in reads if x[0] == 1 and x[1] in MEGA], "reads": reads,
                "after": {k: after[k] for k in ("species", "form", "item")} if after else None,
                "shots": [s for s in (start, info, mid) if s], "sheet": sheet}


def judge_primal(res):
    forms = {c[2] for c in (res["copies_battle_start"] + (res["copies_after_turn1"] or []))
             if c[1] == res["species"]}
    if res["primal_reads"] or forms - {0} or (res["after"] and res["after"]["form"]):
        return "reverts"
    return "no_reversion"


# ----------------------------------------------------------------------------- Pal Park show (Nanab Berry)
PAL_STRUCT = 0x021D3214      # the show's work area (arm9 literal of 0x0205493C init / 0x02054A70 load):
PAL_CAUGHT = PAL_STRUCT + 0x30   # 6 caught flags (0x02054AF8 counts them; 0x02054A00 = 6 - count)
RECEPTION = 479              # Pal Park reception (file 809)
PAL_MAP = 109


def pal_state(h):
    raw = h.read(PAL_STRUCT, 0x4C)
    entries = [struct.unpack_from("<HBBHBB", raw, 8 * i) for i in range(6)]
    return {"caught": list(raw[0x30:0x36]), "remaining": 6 - sum(1 for b in raw[0x30:0x36] if b),
            "steps": struct.unpack_from("<I", raw, 0x38)[0], "picked": struct.unpack_from("<I", raw, 0x3C)[0],
            "stocked_species": [e[0] for e in entries]}


def catch_with_master_ball(h, max_frames=3000):
    """At the battle command menu: Bag -> Poke Balls -> first ball -> Use, then A through the catch messages
    and the Pokedex page; B at a nickname prompt. Returns True when the field is back."""
    import emu_sweeps as S
    h.touch(*E.BATTLE_BUTTONS["bag"], frames=10, after=120)
    h.touch(*S.BATTLE_BAG["balls"], frames=10, after=120)
    h.touch(*S.BATTLE_BAG["first"], frames=10, after=120)
    h.touch(*S.BATTLE_BAG["use"], frames=10, after=0)
    for i in range(0, max_frames, 30):
        h.step(30)
        if h.in_field():
            h.step(60)
            return True
        h.press("A" if i % 120 else "B", after=0)
    return h.in_field()


STOCK = (19, 16, 21, 161, 20, 17)    # Rattata, Pidgey, Spearow, Sentret, Raticate, Pidgeotto (field-area species: Caterpie and Weedle never appeared on the field grass)
PAL_MIGRATED = 28            # SaveArray_Get(save, 28) (0x0202756C): the 6 Pokemon migrated from a GBA game (236 bytes
                             # each, read by 0x02054A70 into the show's entries when the show starts)


def case_palpark(rom, out, variant="fixed"):
    """Fixed Catch show: receptionist -> take part -> Fixed Catch, pay -> park; catch up to 6 wild Pokemon with
    Master Balls; after each, the show's caught flags, and whether file 12 script 3 has run.
    variant 'stocked': six party Pokemon are first copied into the migrated-Pokemon save array (what a GBA
    migration leaves there), so the receptionist runs the normal Catching Show instead (emulates the GBA path;
    the score and the prize routine of file 809 then run if the show completes)."""
    o = out_dir(out, rom)
    rec_obj = 6

    def edit(sf):
        sf.set_pocket("balls", [(MASTER_BALL, 99)])
    with M.session(rom, o, clock=CLOCK, edit=edit, flags=(1366,), vars={16676: 0}) as h:
        M.set_money(h, 50000)
        G.lead(h, E.FAST_LEAD, level=100, **moveset([SPLASH], [40]))
        if variant == "stocked":
            pa, mg = h.array(E.ARR_PARTY) + 8, h.array(PAL_MIGRATED)
            for i, sp in enumerate(STOCK):          # copies of party slot 5 as common grass species
                h.write(mg + 236 * i, E.encode_pokemon(h.read(pa + 236 * 5, 236), species=sp))
        bag0 = E.bag_items(h)
        tr = M.OpTrace(h)
        ml = V.MsgLog(h)
        M.goto_obj(h, RECEPTION, rec_obj)
        m0 = tr.mark()
        h.press("A", after=10)
        shots = []
        end = M.talk_through(h, tr, answers=[0, 0, 0, 0, 0], shots=shots, tag="palpark_talk", max_iter=200)
        h.step(300)
        entry = {"end": end, "pos": h.position(), "msgs_809": tr.msgs(m0), "money": G.money(h),
                 "ops": [n for n, _ in tr.ops(m0)][:120], "pal_state": pal_state(h)}
        shots.append(str(h.screenshot("palpark_entered")))
        catches = []
        if h.position()[0] == PAL_MAP:
            h.walk_to(*E.PAL_PARK_GRASS[0])
            steps = 0
            while len([c for c in catches if c["caught"]]) < 6 and steps < 6000:
                log = E.WildLog(h)
                n0 = tr.mark()
                got = False
                for tile in (E.PAL_PARK_GRASS[1], E.PAL_PARK_GRASS[0]) * 20:
                    h.walk_to(*tile)
                    steps += 1
                    if log.rows or not h.in_field():
                        got = True
                        break
                if not got:
                    continue
                h.step(200)
                if not h.wait_screen("battle_menu", 2500):
                    raise RuntimeError("battle menu not reached")
                h.step(10)
                double = len(log.rows) > 1
                row = {"species": [r["species"] for r in log.rows], "double": double, "frame": h.frame}
                if double:
                    row["caught"] = False
                    h.flee(battle_menu_wait=0)
                else:
                    row["caught"] = catch_with_master_ball(h)
                h.step(240)
                for addr in (E.WILD_FINALIZE, E.WILD_FINALIZE_SETFORM, E.WILD_FINALIZE_AFTER_SET,
                             E.WILD_FINALIZE_RESTORE, E.WILD_FINALIZE_END):
                    h.on_exec(addr, None)
                row["pal_state"] = pal_state(h)
                row["map"] = h.position()[0]
                row["ops_after"] = [(n, off) for n, off in tr.ops(n0)][:40]
                row["msgs_after"] = tr.msgs(n0)
                catches.append(row)
                row["balls_left"] = E.bag_items(h).get(MASTER_BALL, 0)
                shots.append(str(h.screenshot(f"palpark_catch{len(catches)}")))
                if row["map"] != PAL_MAP or any(r[1] == 411 for r in tr.rows[n0:]):
                    break
        script3 = any(r[0] == "NPCMsg" and r[4][0] == 4 and r[1] == 411 for r in tr.rows)
        finale = None
        if script3:                 # the show ended: back at the reception, score and prize (file 809 script 2)
            m1 = tr.mark()
            ends = [M.talk_through(h, tr, answers=[0, 1, 1, 1], shots=shots, tag="palpark_score", max_iter=300)
                    for _ in range(2)]
            finale = {"ends": ends, "msgs": tr.msgs(m1), "offsets": tr.offsets(since=m1)[:200],
                      "map": h.position()[0], "score_cmp": tr.cmp_at(4441, m1) + tr.cmp_at(265, m1)}
        bag_change = M.bag_change(bag0, E.bag_items(h))
        return {"variant": variant, "entry": entry, "catches": catches, "script3_ran": script3, "finale": finale,
                "final_map": h.position()[0], "bag_change": bag_change,
                "prize": {k: v for k, v in bag_change.items() if 149 <= int(k) <= 174},
                "party_count": len(h.party()), "strings_809": ml.ids(508), "shots": shots}


def judge_palpark(res):
    if res.get("prize"):
        return "prize_given"
    if res["entry"]["pos"][0] != PAL_MAP:
        return "not_entered"
    n = sum(1 for c in res["catches"] if c["caught"])
    if res["script3_ran"]:
        return "show_completed"
    return "never_completes" if n >= 6 else f"caught_{n}"


# ----------------------------------------------------------------------------- runner
CASES = {
    "arceus": (case_arceus, tuple(ARCEUS_CASES), judge_arceus, "D-1501"),
    "thief": (case_thief, tuple(THIEF_WILD), judge_thief, "items_extra_sources (Thief)"),
    "rockruff": (case_rockruff, tuple(ROCKRUFF_RUNS), judge_rockruff, "D-1486"),
    "primal": (case_primal, tuple(PRIMAL_CASES), judge_primal, "availability_audit (no Primal Reversion)"),
    "palpark": (case_palpark, ("fixed", "stocked"), judge_palpark, "items_extra_sources 166 (Nanab Berry)"),
}


def run_cases(roms, cases, out, jobs=4, variants=None):
    """Each case/variant and ROM in its own child process (`open --child`), judged per variant."""
    from concurrent.futures import ThreadPoolExecutor
    variants = variants or {}
    todo = [(c, v, l) for c in cases for v in (variants.get(c) or CASES[c][1] or [None]) for l in roms]

    def run(job):
        c, v, l = job
        try:
            return c, v, l, E.run_child(["open", "--child", c + (":" + v if v else ""), "--rom", roms[l],
                                         "--out", out], timeout=1800)
        except Exception as e:
            return c, v, l, E.child_error(e)
    with ThreadPoolExecutor(jobs) as ex:
        rows = list(ex.map(run, todo))
    report = {}
    for c, v, l, r in rows:
        if E.timed_out(r):
            r["verdict"] = "timeout"
        elif "error" in r and len(r) <= 2:
            r["verdict"] = "error"
        else:
            try:
                r["verdict"] = CASES[c][2](r)
            except Exception as e:
                r["verdict"] = "error"
                r["judge_error"] = repr(e)
        r["records"] = CASES[c][3]
        if v:
            report.setdefault(c, {}).setdefault(l, {})[v] = r
        else:
            report.setdefault(c, {})[l] = r
    return report


# Deterministic cases for `emu_harness.py suite` and the verdict each keeps (observed 2026-10-06).
SUITE_EXPECT = {"arceus": {"flame": "plate_type", "zap": "plate_type"},
                "thief": {"miltank": "kept"},
                "rockruff": {"12a": "midday", "18": "dusk"},
                "primal": {"groudon_own": "no_reversion"}}


def suite_check(rom, out):
    variants = {c: tuple(v) for c, v in SUITE_EXPECT.items()}
    report = run_cases({"x": rom}, list(SUITE_EXPECT), out, jobs=3, variants=variants)
    got = {c: {v: report[c]["x"][v].get("verdict") for v in SUITE_EXPECT[c]} for c in SUITE_EXPECT}
    return got == SUITE_EXPECT, {"verdicts": got}


def cmd(a):
    """emu_harness.py open: each case/variant and ROM in its own child process; one JSON report."""
    if a.child:
        name, _, variant = a.child.partition(":")
        fn = CASES[name][0]
        res = fn(a.rom, a.out, variant) if variant else fn(a.rom, a.out)
        print("RESULT " + json.dumps(res, ensure_ascii=False, default=str))
        return 0
    cases = list(CASES) if a.case == "all" else a.case.split(",")
    variants = {}
    for c in list(cases):                      # case:variant1+variant2 runs only those variants
        if ":" in c:
            name, _, vs = c.partition(":")
            cases[cases.index(c)] = name
            variants[name] = tuple(vs.split("+"))
    langs = ["cn", "en"] if a.lang == "both" else [a.lang]
    roms = {l: {"cn": a.rom_cn, "en": a.rom_en}[l] for l in langs}
    report = run_cases(roms, cases, a.out, a.jobs, variants)
    for c in cases:
        for l in langs:
            r = report[c][l]
            verdicts = {v: x.get("verdict") for v, x in r.items()} if CASES[c][1] else r.get("verdict")
            print(json.dumps({"case": c, "rom": l, "records": CASES[c][3], "verdict": verdicts}), flush=True)
    name = ("all" if set(cases) == set(CASES) else "_".join(cases)[:80]) + ("" if a.lang == "cn" else "_" + a.lang)
    path = Path(a.out) / "open" / ("report_" + name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"report": str(path)}))
    return 0
