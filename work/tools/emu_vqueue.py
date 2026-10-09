#!/usr/bin/env python3
"""emu_vqueue - recipes for the open verify queue of the 2026-10-06 triage (bucket D)
(`emu_harness.py vqueue`).

Each case answers one open record of the decision register in the emulator, on the untouched Chinese ROM
(behaviour reference, D-1002) and the English build, with the hack's own scripts and screens:

  ssanne_story  D-1549  first S.S. Anne voyage from a realistic arrival state: who writes flag 1440, can the
                        Captain give HM01, which order starts the party (variants oldboy_first / honey_first)
  new_captain   D-1549  the new S.S. Anne captain gives HM01 when the Bag has none
  cut_yes       D-1549  a Cut tree is really cut with the Cascade Badge and nobody knowing Cut (no HM01)
  notice        D-0905  Goodshow prints the author's end-of-content notice only without the starter flag
  sign          D-1475  the Goldenrod sign 0573#46 and the street around it
  banner        D-0501  location name 46 on the save window in zone 385
  rematch_b     D-1499  B on the memory-rematch Doubles menu
  exp           D-1377  Exp. of a traded Pokemon (own / traded OT)
  probe         D-1350, D-1568, D-1461  Bounce / Fly, Future Sight both ways, Soak, Protean: battle_string ids
  follow        D-1191  following Venonat / Tangela / Pikachu in the Celadon Gym
  buttons       D-1458  Options rows vs the options word; R and L on the stats page for button-mode values 0-2
  battlebag     D-0522  Guard Spec. in battle, battle-bag paging, the battle move-detail page
  dex           D-0521  Pokedex DATA / SIZE / FORMS pages of No. 421
  infopanel     D-0518  battle INFO panel description popup

Screenshots: <out>/verifyqueue/<lang>/; report <out>/verifyqueue/report_<cases>.json.

    .venv/bin/python work/tools/emu_harness.py vqueue [--case ssanne_story,...] [--lang cn|en|both]
"""
import json
from pathlib import Path

import emu_harness as E
import emu_skitty as K
import emu_guide0107 as G
import emu_guide0813 as M

CLOCK = G.CLOCK                                   # Friday 2026-10-09 12:00


def out_dir(out, rom):
    d = Path(out).resolve() / "verifyqueue" / K.lang_of(rom)
    d.mkdir(parents=True, exist_ok=True)
    return d


class FlagWatch:
    """Logs every write to the byte that holds <flag> (pc, frame, whether the bit is set afterwards)."""

    def __init__(self, h, flag):
        self.h, self.flag, self.rows = h, flag, []
        self.addr = h.array(E.ARR_VARS_FLAGS) + E.FLAGS_OFFSET + flag // 8
        self.last = h.get_flag(flag)

        def wr(a, s):
            now = h.get_flag(flag)
            if now != self.last:
                self.rows.append({"frame": h.frame, "pc": hex(h.reg.pc), "bit": int(now)})
            self.last = now
        h.emu.memory.register_write(self.addr, wr, 1)

    def close(self):
        self.h.emu.memory.register_write(self.addr, None, 1)


# ----------------------------------------------------------------------------- D-1549: the first voyage
# Vermilion arrival scene (file 774 @1227-@1267) sets these flags and var 0x40A5 = 1; nothing in the
# S.S. Anne files has run yet (new-game values: all their flags clear, vars 0).
ARRIVAL_FLAGS = (1079, 1080, 1083, 1085, 1087, 1089, 1090, 1091, 1873, 610)
SHIP_CLEAR = (1440, 1439, 1092, 533, 534, 554, 1082, 1084, 1086, 1093, 1421, 1422, 1423, 1424, 1425, 1492,
              1516, 1517, 1518, 1519, 235, 1366)
STATE_FLAGS = (1440, 1439, 533, 534, 554, 1082, 1085, 1421, 1422, 1423, 1424, 1516)
STATE_VARS = (0x40A4, 0x40A5, 0x40A8, 0x40CB, 0x40DC, 0x40E1)   # 16548 party stage, 16549, 16552, 16587, ...


def ship_state(h):
    return {"flags": {f: int(h.get_flag(f)) for f in STATE_FLAGS},
            "vars": {hex(v): h.get_var(v) for v in STATE_VARS}}


def board(h, tr, shots, tag):
    """Board at Vermilion Harbor the real way: the sailor (zone 387 object 0, file 155 script 1) ->
    ScrCmd_723 -> zone 307, the arrival scene (156 script 6), then the Captain's speech trigger (coord
    script 5 at 22,14, var 0x40CB == 0)."""
    h.warp(387, 24, 19, E.DIRS["LEFT"])
    h.step(60)
    r = M.talk(h, tr, tag=f"{tag}_board", shots=shots, max_iter=120)
    for _ in range(10):                        # the map change and the arrival scene (position() lags)
        h.step(100)
        if not h.in_field() or (tr.rows and tr.rows[-1][0] != "End"):
            M.talk_through(h, tr, shots=shots, tag=f"{tag}_arrive", max_iter=60)
    loc = h.location()
    for d, n in (("LEFT", 2), ("UP", 1)):      # (24,15) -> the speech trigger at (22,14)
        h.walk(d, n)
        h.step(30)
    m = tr.mark()
    M.talk_through(h, tr, shots=shots, tag=f"{tag}_speech", max_iter=200)
    return {"board_end": r["end"], "map_after_board": loc["map"], "speech_msgs": tr.msgs(m)}


def talk_obj(h, tr, zone, oid, side, answers=(), battle=None, tag="t", shots=None):
    o = M.goto_obj(h, zone, oid, side)
    r = M.talk(h, tr, answers=answers, battle=battle, tag=tag, shots=shots, max_iter=250)
    r = M.slim(r)
    r["obj_found"] = o is not None
    r.pop("offsets", None)
    r["state"] = ship_state(h)
    return r


def case_ssanne_story(rom, out, variant):
    """D-1549. Realistic state before boarding: the Vermilion arrival flags set, every S.S. Anne flag and var
    at its new-game value, no HM01 / Shoal Salt / Honey in the Bag, $3,000. A watch on flag 1440's byte runs
    from boarding to the end. Real boarding, arrival scene, Captain's speech; then
    'oldboy_first': battle the old boy in the hall (156 script 23: with 1440 clear his party branch L4604
    sets 1424 'met the Captain' before the battle), get Honey (put in the Bag: 'any Honey works'), give it
    to the girl (161 script 4) -> with 1424 set the announcement runs (L1535) and the party starts;
    then the Captain (157 script 5) and the hall trigger at 8,13 (party intro, 156 script 18);
    'blue_first': battle Blue in the hall first (his party branch L4502 sets 1423 'Honey given' before the
    battle), then the old boy, then offer the girl Honey;
    'honey_first': give the girl Honey first (1424 clear -> L1745, nothing), then the Captain, then the old
    boy battle, then the girl, the grandfather and the Captain again, then the hall trigger: does anything
    start the party?"""
    od = out_dir(out, rom)
    shots = []

    def edit(sf):
        for f in SHIP_CLEAR:
            sf.set_flag(f, False)
        for f in ARRIVAL_FLAGS:
            sf.set_flag(f)
        for v, val in {0x40A5: 1, 0x40A4: 0, 0x40A6: 0, 0x40A8: 0, 0x40CB: 0, 0x40DC: 0, 0x40E1: 0}.items():
            sf.set_var(v, val)
    with E.start_at(None, rom=rom, out=od, verbose=False, clock=CLOCK, edit=edit) as h:
        for it in (420, 70, 94):
            M.remove_item(h, it)
        M.set_money(h, 3000)
        G.lead(h, 150, level=100, moves=[57, 85, 58, 94])   # Mewtwo Lv100 with Surf first: every battle is won
        res = {"variant": variant, "badges": [i for i in range(16) if E_badge(h, i)]}
        watch = FlagWatch(h, 1440)
        tr = M.OpTrace(h)
        res["before"] = ship_state(h)
        res["boarding"] = board(h, tr, shots, variant)
        res["after_speech"] = ship_state(h)
        res["guests_visible"] = sorted(o["id"] for o in K.live_objects(h, 307).values() if o["flag"] == 1440)
        res["shot_hall"] = str(h.screenshot(f"{variant}_hall"))
        steps = []

        def do(name, zone, oid, side, answers=(), battle=None, honey=False):
            if honey:
                M.add_item(h, 94, 1)
            bag0 = E.bag_items(h)
            r = talk_obj(h, tr, zone, oid, side, answers=answers, battle=battle, tag=f"{variant}_{name}",
                         shots=shots)
            r["step"] = name
            r["bag_change"] = M.bag_change(bag0, E.bag_items(h))
            steps.append(r)
            return r
        if variant == "oldboy_first":
            do("oldboy", 307, 20, "RIGHT", battle="win")
            do("girl_honey", 328, 1, "DOWN", answers=(0,), honey=True)
            do("captain", 308, 0, "DOWN")
        elif variant == "blue_first":
            do("blue", 307, 18, "RIGHT", battle="win")
            do("oldboy", 307, 20, "RIGHT", battle="win")
            do("girl_honey", 328, 1, "DOWN", answers=(0,), honey=True)
            do("grandfather", 328, 0, "LEFT")
            do("captain", 308, 0, "DOWN")
        else:
            do("girl_honey", 328, 1, "DOWN", answers=(0,), honey=True)
            do("captain", 308, 0, "DOWN")
            do("oldboy", 307, 20, "RIGHT", battle="win")
            do("girl_again", 328, 1, "DOWN")
            do("grandfather", 328, 0, "LEFT")
            do("captain_again", 308, 0, "DOWN")
            do("blue", 307, 18, "RIGHT")
        # the hall trigger at 8,13 (coord script 18, var 0x40A5 == 0): party intro or nothing
        h.warp(307, 8, 15, E.DIRS["UP"])
        h.step(60)
        m = tr.mark()
        h.walk("UP", 2)
        h.step(60)
        M.talk_through(h, tr, shots=shots, tag=f"{variant}_trigger", max_iter=80)
        res["trigger_msgs"] = tr.msgs(m)
        res["trigger_ran"] = any(name == "ApplyMovement" or name == "NPCMsg" for name, _ in tr.ops(m))
        if variant == "honey_first":
            # can the player leave? The gangway (exit warp 24,19) is behind a one-tile gap at 24,16; the
            # sailor (object 1, hide flag 1084) stands at 24,17.
            h.warp(307, 24, 14, E.DIRS["DOWN"])
            h.step(60)
            sailor = G.obj_at(h, 307, 1)
            res["gangway_sailor"] = sailor and {"x": sailor["x"], "z": sailor["z"]}
            h.walk("DOWN", 5)
            h.step(90)
            res["exit_try"] = {"map": h.location()["map"], "pos": h.position()}
            res["shot_exit"] = str(h.screenshot(f"{variant}_exit"))
            m = tr.mark()
            h.press("A", after=10)
            M.talk_through(h, tr, shots=shots, tag=f"{variant}_sailor", max_iter=40)
            res["sailor_msgs"] = tr.msgs(m)
        res["steps"] = steps
        res["end_state"] = ship_state(h)
        res["flag1440_writes"] = watch.rows
        res["shot_end"] = str(h.screenshot(f"{variant}_end"))
        res["shots"] = shots[-40:]
        watch.close()
    return res


def E_badge(h, i):
    prof = h.array(1)
    off = 0x20 if i < 8 else 0x23
    return bool(h.u8(prof + off) >> (i % 8) & 1)


def judge_ssanne_story(res):
    a, b = res["oldboy_first"], res["honey_first"]
    no_1440 = not a["flag1440_writes"] and not b["flag1440_writes"]
    cap = [s for r in (a, b) for s in r["steps"] if s["step"].startswith("captain")]
    no_hm = all(62 in s["msgs"] and 420 not in s["bag_change"] for s in cap)
    a_party = a["end_state"]["vars"][hex(0x40A4)] == 3 and 18 in next(s for s in a["steps"]
                                                                       if s["step"] == "girl_honey")["msgs"]
    b_stuck = b["end_state"]["vars"][hex(0x40A4)] != 3 and not b["trigger_ran"]
    c = res.get("blue_first")
    if c:                                 # Blue's party battle sets 1423 ('Honey given'): the girl never asks
        girl = next(s for s in c["steps"] if s["step"] == "girl_honey")
        b_stuck = b_stuck and c["end_state"]["vars"][hex(0x40A4)] != 3 and not c["trigger_ran"] and \
            girl["bag_change"].get("94") is None and not c["flag1440_writes"]
    if no_1440 and no_hm and a_party and b_stuck:
        return "order_dependent"
    return json.dumps({"no_1440": no_1440, "no_hm": no_hm, "a_party": a_party, "b_stuck": b_stuck})


def case_new_captain(rom, out, variant):
    """D-1549: the second HM01 source. The new S.S. Anne captain (zone 308 object 14, file 157 script 6, hide
    flag 1091, cleared when Sabrina gives HM02 at 826 @936) gives HM01 as the '1000th visitor' gift when the
    Bag has no HM01 (L606), else greets (msg 68). Variants: no_hm01 / has_hm01."""
    od = out_dir(out, rom)
    shots = []
    with M.session(rom, od, flags=(1092, 1087, 1086), clear=(1091,), vars={0x40A9: 1}) as h:
        M.remove_item(h, 420)
        if variant == "has_hm01":
            M.add_item(h, 420, 1, pocket="tm")
        tr = M.OpTrace(h)
        r = talk_obj(h, tr, 308, 14, "RIGHT", tag=f"newcap_{variant}", shots=shots)
        r["hm01_after"] = E.bag_items(h).get(420, 0)
        r["shots"] = shots
    return r


def judge_new_captain(res):
    a, b = res["no_hm01"], res["has_hm01"]
    ok = 69 in a["msgs"] and a["bag_change"].get("420") == 1 and 68 in b["msgs"] and not b["bag_change"]
    return "confirmed" if ok else "contradicted"


def case_cut_yes(rom, out):
    """D-1549 / D-1428: the only Cut trees of the hack (Route 10, objects 3 and 8, std script 10000, hide
    flags 16 and 17). With the Cascade Badge, no HM01 and a party in which nobody knows Cut, talk to the tree
    and answer Yes: is it cut (hide flag set, object gone)?"""
    od = out_dir(out, rom)
    shots = []
    with M.session(rom, od, clear=(16, 17)) as h:
        G.set_badge(h, 1)
        G.weak_party(h)
        M.remove_item(h, 420)
        tr = M.OpTrace(h)
        r = talk_obj(h, tr, 18, 3, "LEFT", answers=(0,), tag="cut_yes", shots=shots)
        r["flag16"] = int(h.get_flag(16))
        r["tree_live"] = G.obj_at(h, 18, 3) is not None
        r["party_moves"] = [m["moves"] if "moves" in m else None for m in [G.mon_details(M.party_raw(h, i))
                                                                           for i in range(len(h.party()))]]
        r["shot_after"] = str(h.screenshot("cut_yes_after"))
        r["shots"] = shots
    return r


def judge_cut_yes(res):
    return "cut" if res["flag16"] and not res["tree_live"] else "not_cut"


# ----------------------------------------------------------------------------- batch 2: scenes, signs, battles
import emu_hackbugs as B                               # noqa: E402
import emu_verify as V                                 # noqa: E402
import emu_open as O                                   # noqa: E402

NARC_BATTLE = 277


def case_notice(rom, out, variant):
    """D-0905: Goodshow (zone 187 object 0, file 31 script 2) with var 0x40A2 = 13: L1604 checks flag 106
    (FLAG_GOT_STARTER, set by every starter choice) and only without it prints the author's notice 0065#62.
    Variants: starter (106 set, as in every real game) / no_starter (106 cleared: the only way to see #62)."""
    od = out_dir(out, rom)
    shots = []
    clear = (2261, 514) + ((106,) if variant == "no_starter" else ())
    with M.session(rom, od, flags=((106,) if variant == "starter" else ()), clear=clear,
                   vars={0x40A2: 13, 0x40B7: 0}) as h:
        tr = M.OpTrace(h)
        r = talk_obj(h, tr, 187, 0, "DOWN", tag=f"notice_{variant}", shots=shots)
        r["flag106"] = int(h.get_flag(106))
        r["shots"] = shots
    return r


def judge_notice(res):
    a, b = res["starter"], res["no_starter"]
    return "unreachable" if 62 not in a["msgs"] and 62 in b["msgs"] else "reachable" if 62 in a["msgs"] else "unclear"


def case_sign(rom, out):
    """D-1475: the Goldenrod sign that prints 0573#46 (file 882 script 30, bg event at 373,333). Read it,
    then photograph the street around it (the Flower Shop door is at 371,332, the door of zone 192 at
    376,335). Hide flag 441 set (the post-takeover state; both NPC groups crash the test saves, D-1547)."""
    od = out_dir(out, rom)
    shots = []
    with M.session(rom, od, flags=(441,)) as h:
        ml = V.MsgLog(h)
        tr = M.OpTrace(h)
        h.warp(76, 373, 334, E.DIRS["UP"])
        h.step(60)
        m = ml.mark()
        r = M.slim(M.talk(h, tr, tag="sign", shots=shots, max_iter=60))
        r.pop("offsets", None)
        r["a027_reads"] = ml.read(573, m)
        h.walk("DOWN", 3)
        h.step(60)
        r["street"] = str(h.screenshot("sign_street"))
        r["shots"] = shots + [r["street"]]
    return r


def case_banner(rom, out):
    """D-0501: enter zone 385 (location name 46, 'Boot Camp Ruins', the only map whose header uses it; an
    interior, so no banner), then open SAVE, whose window names the location; MsgLog says which bank 0272
    ids the game reads. No map header uses 54."""
    od = out_dir(out, rom)
    with M.session(rom, od) as h:
        ml = V.MsgLog(h)
        m = ml.mark()
        o = B.objects(385)[0]
        h.warp(385, o["x"], o["z"] + 1, E.DIRS["DOWN"])
        shots = []
        for k in range(3):
            h.step(40)
            shots.append(str(h.screenshot(f"banner_{k}")))
        entry_reads = ml.ids(272, m)
        m2 = ml.mark()
        h.field_menu("save")                    # the save window names the current location
        h.step(60)
        shots.append(str(h.screenshot("banner_save")))
        save_reads = ml.ids(272, m2)
        for _ in range(3):
            h.press("B", after=60)
        return {"reads_0272_entry": entry_reads, "reads_0272_save": save_reads, "map": h.location()["map"],
                "shots": shots}


def case_rematch_b(rom, out):
    """D-1499: memory-rematch Doubles menu (zone 528, file 78 L832, 0100#11). Press B at the opponent menu:
    which value lands in 0x8008/0x800C (CompareVarToValue reads at @921-@1012), does the script fall through
    to TrainerBattle 0x800C 0x800C (@1040), what starts, does the game freeze?"""
    od = out_dir(out, rom)
    shots = []
    with M.session(rom, od) as h:
        tr = M.OpTrace(h)
        B.enter(h, 528)
        m = tr.mark()
        B.run_from_with(h, 78, 832)
        end = M.talk_through(h, tr, answers=("B",), shots=shots, tag="rematch_b", max_iter=80)
        res = {"end": end, "msgs": tr.msgs(m), "cmp_921": tr.cmp_at(921, m), "cmp_1012": tr.cmp_at(1012, m),
               "reached_1040": tr.reached(1040, m), "reached_813": tr.reached(813, m),
               "trainer_battle_args": [r[4].hex() for r in tr.rows[m:] if r[0] == "TrainerBattle"],
               "bad": tr.bad[:3], "in_field": h.in_field()}
        if end == "battle" or not h.in_field():
            h.step(300)
            res["battle_shot"] = str(h.screenshot("rematch_b_battle"))
            try:
                res["foe_parties"] = [[m_["species"] for m_ in p] for p in B.battle_parties_raw(h)][:4]
            except Exception as e:
                res["foe_parties"] = repr(e)
            h.step(1200)
            res["pc_after"] = hex(h.reg.pc)
            res["later_shot"] = str(h.screenshot("rematch_b_later"))
        res["shots"] = shots[-12:]
        return res


def judge_rematch_b(res):
    if res["reached_1040"]:
        return "battle_on_b"
    return "exits" if res["reached_813"] or res["end"] == "end" else "unclear"


def set_ot(raw, ot_id):
    return E.encode_pokemon(raw, otId=ot_id)


def party_addr(h, slot=0):
    return h.array(E.ARR_PARTY) + 8 + 236 * slot


def battle_reads(ml, since):
    return [(b, i) for narc, b, i, _ in ml.rows[since:] if narc == NARC_BATTLE]


def case_exp(rom, out, variant):
    """D-1377: Exp. for a traded Pokemon. Mewtwo Lv50 (Psychic) beats a wild Chansey Lv10 with its OT ID equal
    to the player's (own) or different (traded); read the battle_string id (2#29 normal / 2#30 boosted) and
    the experience gained (block A +8 before/after)."""
    od = out_dir(out, rom)
    with M.session(rom, od) as h:
        G.lead(h, 150, level=50, moves=[94])
        h.edit_party_mon(0, item=0)
        me = G.player_ot(h)["ot_id"]
        a = party_addr(h)
        h.write(a, set_ot(h.read(a, 136), me if variant == "own" else (me ^ 0x00010001)))
        d = G.mon_details(h.read(a, 236))             # read back: the edit took (OT id, valid checksum)
        ot_check = {"ot_id": d["ot_id"], "differs_from_player": d["ot_id"] != me,
                    "checksum_ok": d.get("checksum_ok"), "species": d.get("species")}
        exp0 = O.exp_of(h.read(a, 136))
        ml = V.MsgLog(h)
        m = ml.mark()
        O.wild_battle(h, 113, 10, moves=[150])
        pages = []
        turns = []
        for _ in range(6):
            r = O.turn(h, ml, 0, pages)
            turns.append(r)
            if r == "field":
                break
        h.step(120)
        exp1 = O.exp_of(h.read(a, 136))
        reads = battle_reads(ml, m)
        sheet = O.page_sheet(pages, od / f"exp_{variant}_pages.png")
        return {"variant": variant, "player_ot": me, "ot_check": ot_check, "exp_before": exp0, "exp_after": exp1, "gained": exp1 - exp0,
                "turns": turns, "exp_msgs": [x for x in reads if x[0] == 2 and x[1] in (29, 30)], "sheet": sheet,
                "shots": [sheet] if sheet else []}


def judge_exp(res):
    a, b = res["own"], res["traded"]
    if not a["gained"]:
        return "unclear"
    if "ot_check" in b and not (b["ot_check"]["differs_from_player"] and b["ot_check"]["checksum_ok"] is not False):
        return "ot_not_set"
    ratio = b["gained"] / a["gained"]
    msg = "boosted_msg" if [2, 30] in [list(x) for x in b["exp_msgs"]] else "plain_msg"
    return f"ratio_{ratio:.2f}_{msg}"


BATTLE_PROBES = {
    # variant: (lead species, lead level, lead moves, lead ability, foe species, foe level, foe moves, turns)
    "bounce": (150, 100, [340], None, 213, 100, [150], 3),
    "fly": (150, 100, [19], None, 213, 100, [150], 3),
    "fs_foe": (113, 100, [150], None, 150, 30, [248], 5),
    "fs_own": (150, 100, [248, 150], None, 213, 100, [150], 5),
    "soak": (150, 100, [487], None, 74, 50, [150], 1),
    "protean": (658, 100, [98], 168, 213, 100, [150], 1),
}


def case_probe(rom, out, variant):
    """D-1350 (bounce, control fly), D-1568 (fs_foe: a wild Future Sight lands on the player's Pokemon; fs_own:
    the player's lands on the wild one), D-1461 (soak on a wild Geodude; protean: Greninja with Protean uses
    Quick Attack). Scripted wild battle, fixed movesets (foe: one move), every battle_string read logged per
    turn, the message window pages kept."""
    sp, lv, moves, abil, foe, flv, fmoves, nturns = BATTLE_PROBES[variant]
    od = out_dir(out, rom)
    with M.session(rom, od) as h:
        G.lead(h, sp, level=lv, moves=moves)
        h.edit_party_mon(0, item=0)
        if abil:
            h.edit_party_mon(0, ability=abil)
        ml = V.MsgLog(h)
        ml.mark()
        O.wild_battle(h, foe, flv, moves=fmoves)
        if not h.wait_screen("battle_menu", 2000):
            raise RuntimeError("battle menu not reached")
        pages, turns = [], []
        for k in range(nturns):
            m1 = ml.mark()
            n0 = len(pages)
            act = 1 if (variant == "fs_own" and k > 0) else 0
            r = O.turn(h, ml, act, pages)
            turns.append({"result": r, "reads": battle_reads(ml, m1), "pages": len(pages) - n0})
            if r != "menu":
                break
        sheet = O.page_sheet(pages, od / f"probe_{variant}_pages.png")
        if h.on_screen("battle_menu"):
            O.end_battle(h, ml, ("run",))
        return {"variant": variant, "turns": turns, "sheet": sheet, "shots": [sheet] if sheet else []}


def _reads(res):
    return [tuple(x) for t in res["turns"] for x in t["reads"]]


def judge_probe(res):
    out = {}
    if "bounce" in res:
        t1 = [tuple(x) for x in res["bounce"]["turns"][0]["reads"]]
        out["bounce"] = "two_turn" if (1, 734) in t1 else "one_turn"
    if "fs_foe" in res:
        hit = [i for b, i in _reads(res["fs_foe"]) if b == 1 and 1464 <= i <= 1467]
        out["fs_foe"] = hit
    if "fs_own" in res:
        out["fs_own"] = [i for b, i in _reads(res["fs_own"]) if b == 1 and 1464 <= i <= 1467]
    for v in ("soak", "protean"):
        if v in res:
            out[v] = [i for b, i in _reads(res[v]) if b == 1 and i in (1212, 1213, 1214, 1215)]
    return json.dumps(out)


FOLLOW = {"venonat": 48, "tangela": 114, "pikachu": 25}


def case_follow(rom, out, variant):
    """D-1191: lead <variant> (follows the player) in the Celadon Gym (zone 395); step down, turn back, talk
    to it (FollowMonInteract) three times; which bank 0258 lines are read? Tangela's special line is 725."""
    od = out_dir(out, rom)
    with M.session(rom, od) as h:
        G.lead(h, FOLLOW[variant], level=30)
        ml = V.MsgLog(h)
        tr = M.OpTrace(h)
        rows, shots = [], []
        for k in range(3):
            h.warp(395, 7, 8, E.DIRS["DOWN"])
            h.step(40)
            h.walk("DOWN", 1)
            h.step(20)
            h.hold("UP")
            h.step(3)
            h.release("UP")
            h.step(20)
            m, t = ml.mark(), tr.mark()
            h.press("A", after=10)
            M.talk_through(h, tr, answers=(0,), shots=shots, tag=f"follow_{variant}{k}", max_iter=40)
            rows.append({"lines_0258": ml.ids(258, m), "ops": [o[0] for o in tr.ops(t)][:12]})
        return {"variant": variant, "talks": rows, "shots": shots[:4]}


def judge_follow(res):
    got = {v: sorted({i for t in r["talks"] for i in t["lines_0258"]}) for v, r in res.items() if isinstance(r, dict)}
    return json.dumps(got)


def _summary_stats(h):
    """Party (X menu) -> slot 0 summary -> RIGHT (the stats/moves page where L opens the IV/EV panel)."""
    h.touch(*E.FIELD_MENU["pokemon"], frames=12, after=150)
    h.touch(*E.PARTY_SLOTS[0], frames=12, after=60)
    h.touch(*E.PARTY_SUMMARY, frames=12, after=150)
    h.press("RIGHT", after=60)                 # pages: info, stats/moves, ribbons (observed)


def _diff(a, b):
    return round(E.screen_diff(a, b)[0], 4)


def case_buttons(rom, out):
    """D-1458. (1) The hack's Options screen (bank 0043: MUSIC SPEED, BATTLE SCENE, BATTLE STYLE, TITLE SCREEN,
    BATTLE BG, FRAME) has no BUTTON MODE row: change every row once and compare the options word (save array
    1 +0, u16; vanilla button mode = bits 8-9) before/after. (2) With the button-mode bits forced to 0, 1, 2
    in RAM: on the stats page press R, then L; does the IV/EV panel open (screen change)?"""
    od = out_dir(out, rom)
    res = {"modes": {}}
    with M.session(rom, od) as h:
        opt = h.array(1)
        w0 = h.u16(opt)
        res["word_before"] = hex(w0)
        res["rows"] = {}
        for row in range(6):                   # one row changed per visit, then CONFIRM (touch)
            h.field_menu("options")
            if row == 0:
                res["options_shot"] = str(h.screenshot("buttons_options"))
            for _ in range(row):
                h.press("DOWN", after=20)
            a = h.u16(opt)
            h.press("RIGHT", after=30)
            h.touch(150, 180, frames=10, after=120)
            for _ in range(3):
                h.press("B", after=60)
            b = h.u16(opt)
            res["rows"][row] = {"before": hex(a), "after": hex(b), "bits": [k for k in range(16) if (a ^ b) >> k & 1]}
        h.w16(opt, w0)
        for mode in (0, 1, 2):
            h.w16(opt, (w0 & ~0x0300) | (mode << 8))
            _summary_stats(h)
            base = h.emu.screenshot().convert("RGB")
            h.press("R", after=60)
            after_r = h.emu.screenshot().convert("RGB")
            r_shot = str(h.screenshot(f"buttons_m{mode}_R"))
            h.press("B", after=60) if _diff(base, after_r) > 0.02 else None
            h.press("L", after=60)
            after_l = h.emu.screenshot().convert("RGB")
            l_shot = str(h.screenshot(f"buttons_m{mode}_L"))
            res["modes"][mode] = {"R_change": _diff(base, after_r), "L_change": _diff(base, after_l),
                                  "shots": [r_shot, l_shot]}
            for _ in range(4):
                h.press("B", after=90)
        h.w16(opt, w0)
        res["shots"] = [res["options_shot"]] + [x for m in res["modes"].values() for x in m["shots"]]
    return res


def case_battlebag(rom, out):
    """D-0522 (and the battle party screen): a scripted single wild battle (Shuckle Lv100, Splash); BAG ->
    BATTLE ITEMS -> Guard Spec. -> USE (0005 #35 'Shrouded in mist!'); BAG -> HP/PP RESTORE with 8 items
    (two pages: 0005 #21 NEXT?); POKeMON -> first slot -> each submenu button -> first move (0006 #57
    APPEAL?). Every a027 string read is logged per screen; both screens are photographed."""
    od = out_dir(out, rom)
    with M.session(rom, od) as h:
        G.lead(h, 291, level=100, moves=[150])
        h.bag_put_first(V.GUARD_SPEC, 5, pocket="battle")
        M.set_bag(h, "medicine", [(k, 3) for k in (17, 23, 24, 25, 26, 30, 31, 32, 33, 38)])
        ml = V.MsgLog(h)
        O.wild_battle(h, 213, 100, moves=[150])
        h.wait_screen("battle_menu", 2400)
        shots, seen = [], {}

        def back_to_menu():
            for _ in range(10):
                if h.on_screen("battle_menu"):
                    return True
                h.touch(240, 172, frames=10, after=60)     # the return button (bottom right)
                if h.on_screen("battle_menu"):
                    return True
                h.press("B", after=60)
            return h.on_screen("battle_menu")
        m = ml.mark()
        h.touch(*E.BATTLE_BUTTONS["bag"], frames=10, after=120)
        h.touch(*V.BATTLE_BAG_POCKETS["restore"], frames=10, after=90)
        shots.append(str(h.screenshot("bb_restore_p1")))
        h.touch(56, 172, frames=10, after=90)           # the right page arrow (bottom left, observed)
        shots.append(str(h.screenshot("bb_restore_p2")))
        seen["restore"] = ml.read(5, m)
        back_to_menu()
        m = ml.mark()
        h.touch(*E.BATTLE_BUTTONS["bag"], frames=10, after=120)
        h.touch(*V.BATTLE_BAG_POCKETS["battle"], frames=10, after=90)
        h.touch(64, 28, frames=10, after=90)
        shots.append(str(h.screenshot("bb_guardspec")))
        h.touch(*V.BATTLE_BAG_USE, frames=10, after=10)
        for k in range(5):
            h.step(50)
            shots.append(str(h.screenshot(f"bb_use{k}")))
        seen["guard_spec"] = ml.read(5, m)
        seen["guard_spec_battle"] = [(b, i) for nn, b, i, _ in ml.rows[m:] if nn == NARC_BATTLE]
        M.wait_stable(h)
        back_to_menu()
        m = ml.mark()
        h.touch(*E.BATTLE_BUTTONS["pokemon"], frames=10, after=120)
        shots.append(str(h.screenshot("bb_party")))
        h.touch(64, 28, frames=10, after=90)
        shots.append(str(h.screenshot("bb_party_slot")))
        h.touch(192, 168, frames=10, after=120)               # CHECK MOVES (observed)
        shots.append(str(h.screenshot("bb_moves")))
        m6 = ml.mark()
        h.touch(64, 62, frames=10, after=120)                 # the first move's button: its detail page
        shots.append(str(h.screenshot("bb_move_detail")))
        seen["move_detail"] = ml.read(6, m6)
        h.touch(192, 62, frames=10, after=120)
        shots.append(str(h.screenshot("bb_move_detail2")))
        seen["party"] = ml.read(6, m)
        back_to_menu()
        return {"bank5_read": ml.ids(5), "bank6_read": ml.ids(6), "per_screen": seen, "shots": shots}


def case_dex(rom, out):
    """D-0521: Pokedex entries (dex filled in RAM): No. 421 (Cherrim, whose US form labels the hack's 0790
    #164/165 'Front'/'Back' replaced), No. 25 and No. 201; detail tabs info, size, forms; on the forms tab
    also tap the bottom screen's buttons. Logs every bank 0790 id read per tab (languages #2-7, Front/Back
    #164/165, #179) and photographs both screens. Tab buttons of the hack's detail view (observed): AREA,
    DATA, SIZE, FORMS (样子), BACK along the bottom."""
    import emu_dex as D
    od = out_dir(out, rom)
    with M.session(rom, od) as h:
        ml = V.MsgLog(h)
        D.open_dex_list(h)
        res, shots = {}, []
        tabs = {"area": (36, 176), "data": (88, 176), "size": (136, 176), "forms": (186, 176)}   # observed
        for n in (421, 25, 201):
            got = D.goto(h, n)
            row = {"shown": got}
            D.settle_both(h)
            h.step(60)
            h.press("A", frames=6, after=200)
            D.settle_both(h)
            shots.append(str(h.screenshot(f"dex_{n}_opened")))
            for tab in ("data", "size", "forms", "area"):
                m = ml.mark()
                h.touch(*tabs[tab], frames=8)
                D.settle_both(h)
                shots.append(str(h.screenshot(f"dex_{n}_{tab}")))
                row[tab] = ml.ids(790, m)
            h.touch(*tabs["forms"], frames=8)
            D.settle_both(h)
            m = ml.mark()
            for k, xy in enumerate(((40, 60), (40, 100), (40, 140), (216, 60), (216, 100), (216, 140))):
                h.touch(*xy, frames=8, after=60)              # buttons of the forms page
                D.settle_both(h)
                shots.append(str(h.screenshot(f"dex_{n}_forms_t{k}")))
            row["forms_tapped"] = ml.ids(790, m)
            h.touch(236, 180, frames=8)
            h.step(60)
            for _ in range(0, 300, 4):
                if D.number(h) is not None:
                    break
                h.step(4)
            D.settle_top(h)
            res[n] = row
        res["all_0790"] = ml.ids(790)
        res["shots"] = shots
        return res


def case_infopanel(rom, out):
    """D-0518: the battle INFO panel's description view (battle_string bank 0). Tyranitar Lv100 (Sand Stream)
    leads against a wild Shuckle (Splash): sandstorm is up; turn 1 Stealth Rock on the foe's side. RIGHT
    switches to the foe's panel. Open INFO, then drive the panel with the keys
    (A opens the selected row's description, observed) and taps on the right column's rows (ability, weather);
    log every bank 0 id read and photograph both screens."""
    od = out_dir(out, rom)
    with M.session(rom, od) as h:
        G.lead(h, 248, level=100, moves=[446])     # Stealth Rock: a foe-side entry without a turn count
        h.edit_party_mon(0, ability=45)
        ml = V.MsgLog(h)
        O.wild_battle(h, 213, 100, moves=[150])
        h.wait_screen("battle_menu", 2400)
        O.turn(h, ml, 0)
        h.wait_screen("battle_menu", 2400)
        steps, shots = [], []
        m = ml.mark()
        h.touch(*E.BATTLE_BUTTONS["info"], frames=10, after=150)
        shots.append(str(h.screenshot("info_open")))
        steps.append(("open", [(b, i) for nn, b, i, _ in ml.rows[m:] if nn == NARC_BATTLE]))
        for k, keys in enumerate((("A",), ("RIGHT", "A"), ("DOWN", "A"), ("DOWN", "A"), ("UP", "A"))):
            m = ml.mark()
            for key in keys:
                h.press(key, after=40)
            h.step(40)
            shots.append(str(h.screenshot(f"info_sel{k}")))
            steps.append(("+".join(keys), [(nn, b_, i) for nn, b_, i, _ in ml.rows[m:]]))
            h.press("B", after=60)
        return {"steps": steps, "bank0": sorted({i for nn, b, i, _ in ml.rows if nn == NARC_BATTLE and b == 0}),
                "shots": shots}


CASES = {
    "ssanne_story": (case_ssanne_story, ("oldboy_first", "honey_first", "blue_first"), judge_ssanne_story,
                     "D-1549"),
    "new_captain": (case_new_captain, ("no_hm01", "has_hm01"), judge_new_captain, "D-1549"),
    "cut_yes": (case_cut_yes, None, judge_cut_yes, "D-1549, D-1428"),
    "notice": (case_notice, ("starter", "no_starter"), judge_notice, "D-0905"),
    "sign": (case_sign, None, None, "D-1475"),
    "banner": (case_banner, None, None, "D-0501"),
    "rematch_b": (case_rematch_b, None, judge_rematch_b, "D-1499"),
    "exp": (case_exp, ("own", "traded"), judge_exp, "D-1377"),
    "probe": (case_probe, tuple(BATTLE_PROBES), judge_probe, "D-1350, D-1568, D-1461"),
    "follow": (case_follow, ("venonat", "tangela", "pikachu"), judge_follow, "D-1191"),
    "buttons": (case_buttons, None, None, "D-1458"),
    "battlebag": (case_battlebag, None, None, "D-0522"),
    "dex": (case_dex, None, None, "D-0521"),
    "infopanel": (case_infopanel, None, None, "D-0518"),
}


# ----------------------------------------------------------------------------- runner
def run_cases(roms, cases, out, jobs=4, variants=None):
    """Each case/variant and ROM in its own child process (`vqueue --child`); judges combine variants."""
    from concurrent.futures import ThreadPoolExecutor
    variants = variants or {}
    todo = [(c, v, l) for c in cases for v in (variants.get(c) or CASES[c][1] or [None]) for l in roms]

    def run(job):
        c, v, l = job
        try:
            return c, v, l, E.run_child(["vqueue", "--child", c + (":" + v if v else ""), "--rom", roms[l],
                                         "--out", out], timeout=2400)
        except Exception as e:
            return c, v, l, E.child_error(e)
    with ThreadPoolExecutor(jobs) as ex:
        rows = list(ex.map(run, todo))
    report = {}
    for c, v, l, r in rows:
        if v:
            report.setdefault(c, {}).setdefault(l, {})[v] = r
        else:
            report.setdefault(c, {})[l] = r
    for c in cases:
        for l in roms:
            r = report[c][l]
            if E.timed_out(r):
                r["verdict"] = "timeout"
            elif CASES[c][2]:
                try:
                    r["verdict"] = CASES[c][2](r)
                except Exception as e:
                    r["verdict"] = "error"
                    r["judge_error"] = repr(e)
            r["records"] = CASES[c][3]
    return report


SUITE_EXPECT = {"cut_yes": "cut", "new_captain": "confirmed", "notice": "unreachable", "rematch_b": "exits",
                "follow": json.dumps({"venonat": [205], "tangela": [725]})}
SUITE_VARIANTS = {"follow": ("venonat", "tangela")}


def suite_check(rom, out):
    """emu_harness.py suite: the SUITE_EXPECT cases on one ROM; pass when every verdict is the expected one."""
    report = run_cases({"x": rom}, list(SUITE_EXPECT), out, jobs=4, variants=SUITE_VARIANTS)
    got = {c: report[c]["x"].get("verdict") for c in SUITE_EXPECT}
    return got == SUITE_EXPECT, {"verdicts": got}


def cmd(a):
    """emu_harness.py vqueue: each case/variant and ROM in its own child process; one JSON report."""
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
            print(json.dumps({"case": c, "rom": l, "records": CASES[c][3], "verdict": report[c][l].get("verdict")}),
                  flush=True)
    name = ("all" if set(cases) == set(CASES) else "_".join(cases)[:80]) + ("" if a.lang == "cn" else "_" + a.lang)
    path = Path(a.out) / "verifyqueue" / ("report_" + name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"report": str(path)}))
    return 0
