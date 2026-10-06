#!/usr/bin/env python3
"""emu_hackbugs - emulator checks for the open hack-finding records of the decision register
(`emu_harness.py hackbugs`).

The register holds suspected bugs of the original Chinese hack found by reading its scripts, code and data
(subtype hack-finding). Under D-1337 they are reported, never fixed. This module observes the behaving ones
in game, the same way as emu_guide0107/emu_guide0813 (whose helpers it reuses): a case sets the state the
record names (flags, vars, badges, clock, party, bag, money), runs the hack's own event script (talking to the
object, or a GoTo into the script's own bytes, optionally after a few setup commands with `run_from_with`),
a trainer battle, a scripted wild battle or a bag action, and reads back what the game did: flags, party
moves and data, bag, money, coins, messages, the branch taken (OpTrace), battle parties in RAM, the map.

    .venv/bin/python work/tools/emu_harness.py hackbugs [--case tutor,nugget,...] [--lang cn|en|both]

Every case returns a dict with `verdict` ('confirmed', 'contradicted', 'observed' or 'blocked') and its
evidence; screenshots go to <out>/hackbugs/<lang>/. CASES at the end lists them with the record each one
checks; `suite` runs SUITE_EXPECT (the cheap deterministic ones) and fails when a verdict changes.
"""
import datetime
import json
import struct
from pathlib import Path

import emu_harness as E
import emu_skitty as K
import emu_guide0107 as G
import emu_guide0813 as M

CLOCK = G.CLOCK                                  # Friday 2026-10-09 12:00
FAST_LEAD = G.FAST_LEAD


# ----------------------------------------------------------------------------- helpers
def out_dir(out, rom):
    d = Path(out).resolve() / "hackbugs" / K.lang_of(rom)
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_from_with(h, file, label, pre=(), script_no=1, settle=30, anywhere=False):
    """Like emu_guide0107.run_from, but first run a few commands of our own (`pre`, e.g. the special vars a
    skipped menu would have set: 0x800C = the chosen party slot), then GoTo <label> of the map's script file
    <file>. The bytes are written over the start of map script <script_no> in RAM (the loaded copy).
    anywhere: load <file> (and its message bank) through the script loader instead, so the current map
    doesn't matter (for maps that start a scene on entry, e.g. the Hall of Fame)."""
    start = G.script_entries(file)[0][script_no - 1]
    head = E.script_bytes(("LockAll",), *pre)
    prog = head + E.script_bytes(("GoTo", label - (start + len(head) + 6)))
    if anywhere:
        bank = next(z["msg_bank"] for z in zones() if z["scripts_bank"] == file)
        return h.run_script(file=file, index=script_no - 1, msg_bank=bank, program=prog, settle=settle)
    return h.run_script(script_id=script_no, program=prog, settle=settle)


def zones():
    import romdata as R
    return R.read_json(str(E.WORK / "translate" / "bank_maps.json"))["_zones"]


def zone_info(zone):
    import romdata as R
    return R.read_json(str(E.WORK / "translate" / "bank_maps.json"))["_zones"][zone]


def objects(zone):
    import romdata as R
    return R.parse_events(G.static()["events"][zone_info(zone)["events_bank"]])["obj"]


def obj_for_script(zone, script):
    """Object id of the first object in <zone> whose talk script is <script>."""
    return next(o["id"] for o in objects(zone) if o["script"] == script)


def enter(h, zone, x=None, z=None, face="DOWN"):
    """Warp into <zone> (a normal map entry): at (x, z), or below the zone's first object, facing away from it
    (so a stray A press talks to nobody)."""
    if x is None:
        o = objects(zone)[0]
        x, z = o["x"], o["z"] + 1
    h.warp(zone, x, z, E.DIRS[face])
    h.step(60)


def mon(h, slot=0):
    """Decrypted details of a party Pokemon (moves, IVs, OT, species, form, level) plus its ability byte
    (block A +0x0D) and its party-extension stats (+4 level, +6 HP, +8 max HP, +0x0A..+0x12 Atk/Def/Spe/
    SpA/SpD, decrypted with the PID stream)."""
    raw = M.party_raw(h, slot)
    d = G.mon_details(raw)
    d["ability"] = M.decrypted_blocks(raw)[0x0D]
    pid = struct.unpack_from("<I", raw, 0)[0]
    ext = [w ^ k for w, k in zip(struct.unpack_from("<50H", raw, 136), E._prng_stream(pid, 50))]
    d["hp"], d["stats"] = ext[3], ext[4:10]
    return d


COINS_OFF = 0x24      # PlayerSaveData (save array 1): +4 PlayerProfile (0x20 bytes), then u16 coins


def coins(h):
    """Coin count: save array 1 +0x24 (u16, right after the PlayerProfile; checked by the coins case, which
    diffs array 1 around the game's GiveCoins). Script command 119 (GetCoinAmount) crashes this hack."""
    return h.u16(h.array(1) + COINS_OFF)


def set_coins(h, n):
    h.w16(h.array(1) + COINS_OFF, n)
    return coins(h)


def item_count(h, item):
    return E.bag_items(h).get(item, 0)


def move_names(rom, ids):
    """In-game move names (a027 bank 739 = move names in both ROMs) for the ids, read from the ROM."""
    lines = K.bank_lines(rom, MOVE_NAME_BANK)
    return {m: lines[m] if m < len(lines) else None for m in ids}


MOVE_NAME_BANK = 739


def battle_parties_raw(h, lo=0x02200000, hi=0x02400000):
    """Like emu_skitty.find_parties, but with mon() details of every member (moves, IVs, form, ability)."""
    out = []
    for p in K.find_parties(h, lo, hi):
        a = int(p["addr"], 16)
        cnt = h.u32(a + 4)
        mons = []
        for k in range(cnt):
            raw = h.read(a + 8 + 236 * k, 236)
            d = G.mon_details(raw)
            d["ability"] = M.decrypted_blocks(raw)[0x0D]
            mons.append({k_: d[k_] for k_ in ("species", "form", "level", "moves", "ivs", "ability", "item")})
        out.append({"addr": p["addr"], "mons": mons})
    return out


def rom_team(trainer):
    import romdata as R
    td = R.parse_trdata(G.static()["trdata"][trainer])
    return td, R.parse_trpoke(G.static()["trpoke"][trainer], td["count"])


# ----------------------------------------------------------------------------- move tutors
# name -> (record, zone, script file, label right after GetPartySelection (0x800C = slot), label of the
#          compatibility list (first CompareVarToValue species is used as the pupil), move the text promises,
#          move the 3-move path writes, move the 4-move path writes, fee: ('money', n) / ('item', id, qty))
TUTORS = {
    "blackthorn": ("D-1305", 291, 944, 1900, 2280, "Play Rough", 175, 175, None),
    "dojo": ("D-1347", 398, 829, 3446, 3755, "Volt Switch", 268, 521, ("money", 10000)),
    "rocktunnel": ("D-1338", 342, 129, 4252, 4741, "Signal Beam", 676, 676, ("item", 13, 1)),
    "hans": ("D-1408", 75, 872, 4077, 4180, "Close Combat", 370, 370, ("item", 50, 3)),
}
FOUR_MOVES = [85, 98, 86, 87]          # Thunderbolt, Quick Attack, Thunder Wave, Thunder (any 4 moves)


def compat_species(file, label):
    ins = dict(G.script_entries(file)[1])
    op, args, _, _ = ins[label]
    return args[1]


def case_tutor(rom, out, variant):
    """Move tutors whose text names one move but whose SetMonMove writes another (D-1305, D-1347, D-1338) or
    whose fee is skipped (D-1408). Variant '<tutor><3|4>': the pupil (generator, the first species of the
    tutor's own compatibility list, Lv50) knows 3 or 4 moves. The script runs from the label right after the
    party selection with 0x800C = 0 (the lead), so the game's own CountMonMoves branch, SetMonMove, fee and
    messages run; on the 4-move path Yes is answered, the first move is picked in the summary (A, A) and
    'forget it' is answered Yes. Read: the lead's moves, money, the fee item, the summary screenshot (it
    names the new move at the bottom)."""
    name, n = variant[:-1], int(variant[-1])
    rec, zone, file, after_sel, compat, promised, m3, m4, fee = TUTORS[name]
    species = compat_species(file, compat)
    with M.session(rom, out) as h:
        moves = FOUR_MOVES[:n] + [0] * (4 - n)
        G.lead(h, species, level=50, moves=moves, pp=[10 if m else 0 for m in moves])
        if fee and fee[0] == "money":
            M.set_money(h, fee[1] * 2)
        elif fee:
            M.remove_item(h, fee[1])
            M.add_item(h, fee[1], fee[2] + 2, "balls" if fee[1] < 17 else "medicine" if fee[1] == 50 else "items")
        tr = M.OpTrace(h)
        enter(h, zone)
        before = mon(h, 0)["moves"]
        money0, item0 = G.money(h), (item_count(h, fee[1]) if fee and fee[0] == "item" else None)
        m = tr.mark()
        shots = []
        run_from_with(h, file, after_sel, pre=[("SetVar", 0x800C, 0)])
        summary = None
        for i in range(80):                 # play to the summary (4 moves) or the end (3 moves)
            h.step(30)
            names = tr.names_since(m)
            if "PokemonSummaryScreen" in names or (names and names[-1] == "End"):
                break
            if names and names[-1] == "GetMenuChoice":
                M.wait_stable(h)
                h.press("A", after=40)      # Yes: forget a move
            else:
                h.press("A", after=4)
        if "PokemonSummaryScreen" in tr.names_since(m):
            h.step(240)
            summary = str(h.screenshot(f"tutor_{variant}_summary"))
            h.press("A", after=120)         # the first move
            h.press("A", after=120)
            h.step(200)
        end = M.talk_through(h, tr, answers=[0, 0], shots=shots, tag=f"tutor_{variant}", max_iter=80)
        after = mon(h, 0)["moves"]
        res = {"tutor": name, "record": rec, "pupil_species": species, "moves_before": before, "moves_after": after,
               "end": end, "msgs": tr.msgs(m), "set_mon_move": tr.u16_args("SetMonMove", m),
               "money_before": money0, "money_after": G.money(h), "shot_summary": summary, "shots": shots[-4:],
               "fee_item_before": item0,
               "fee_item_after": item_count(h, fee[1]) if fee and fee[0] == "item" else None}
        new = [x for x in after if x not in before]
        res["learned"] = new
        res["learned_names"] = move_names(rom, new)
        res["expected_move"] = m3 if n == 3 else m4
        res["promised"] = promised
        res["fee_taken"] = (res["money_before"] - res["money_after"] if fee and fee[0] == "money" else
                            (item0 - res["fee_item_after"]) if fee else None)
    return res


def judge_tutor(res):
    """Per tutor: 'confirmed' when the learned move ids are those the record names (and the fee claim holds);
    'contradicted' otherwise."""
    out = {}
    for name in TUTORS:
        r3, r4 = res.get(name + "3"), res.get(name + "4")
        if not r3 or not r4:
            continue
        ok = r3["learned"] == [r3["expected_move"]] and r4["learned"] == [r4["expected_move"]]
        if name == "hans":          # D-1408: 3 Rare Candies taken on the free-slot path only
            ok = ok and r3["fee_taken"] == 3 and r4["fee_taken"] == 0
        out[name] = "confirmed" if ok else "contradicted"
    v = set(out.values())
    return v.pop() if len(v) == 1 else json.dumps(out)


# ----------------------------------------------------------------------------- items, money, coins
def face_obj(h, zone, oid, side="DOWN", tries=6):
    """emu_guide0813.goto_obj, repeated until the object (which may wander) is still on the tile the player
    faces a moment later."""
    dx, dz, _ = M.SIDES[side]
    o = None
    for _ in range(tries):
        o = M.goto_obj(h, zone, oid, side=side)
        if o is None:
            return None
        h.step(20)
        o2 = G.obj_at(h, zone, oid)
        if o2 and h.position() == (zone, o2["x"] + dx, o2["z"] + dz):
            return o2
    return o


def talk_obj(rom, out, zone, script, answers=(), flags=(), clear=(), vars=None, setup=None, side="DOWN",
             tag="t", battle=None, clock=CLOCK, max_iter=150, read=None):
    """Talk to the object of <zone> whose talk script is <script>, play the script through with <answers>,
    return what changed (talk(): msgs, money, bag) plus read(h) and the end screenshot."""
    with M.session(rom, out, clock=clock, flags=flags, clear=clear, vars=vars) as h:
        if setup:
            setup(h)
        tr = M.OpTrace(h)
        oid = obj_for_script(zone, script)
        o = face_obj(h, zone, oid, side)
        if o is None:
            return {"verdict": "blocked", "reason": f"object {oid} not shown", "shot": str(h.screenshot(tag + "_missing"))}
        shots = []
        r = M.talk(h, tr, answers=answers, battle=battle, tag=tag, shots=shots, max_iter=max_iter)
        r.update(object=oid, shots=shots[-4:], shot_end=str(h.screenshot(tag + "_end")))
        r["offsets_hit"] = sorted({o_ for _, o_ in r["ops"]})
        if read:
            r.update(read(h))
    return M.slim(r)


def case_nugget(rom, out, variant):
    """D-1404: Route 26 Phanpy trainer (zone 30, script 7). With one Nugget (92): 'Have it' (menu 1) gives
    TM41 (368) and keeps the Nugget; control 'sell' (menu 0) takes it and pays $30000."""
    def setup(h):
        M.remove_item(h, 92)
        M.remove_item(h, 368)
        M.add_item(h, 92, 1)
    r = talk_obj(rom, out, 30, 7, answers=[1 if variant == "have" else 0], clear=(1111,), setup=setup,
                 tag=f"nugget_{variant}", read=lambda h: {"flag_1111": h.get_flag(1111)})
    return r


def judge_nugget(res):
    a, b = res["have"], res["sell"]
    ok = (a["bag_change"].get("368") == 1 and "92" not in a["bag_change"] and a["flag_1111"]
          and b["bag_change"].get("92") == -1 and b["money_after"] - b["money_before"] == 30000)
    return "confirmed" if ok else "contradicted"


def case_friendball(rom, out):
    """D-1399: Route 2 East Apricorn Ball maker (zone 414, script 4): with one Friend Ball (497), Yes to 'Give
    him a Friend Ball?' (L992 -> L3021). Is the ball taken?"""
    def setup(h):
        M.remove_item(h, 497)
        M.add_item(h, 497, 1, "balls")
    r = talk_obj(rom, out, 414, 4, answers=[0, 0, 0, 0], clear=(1347,), setup=setup, tag="friendball",
                 battle=None, max_iter=250, read=lambda h: {"friend_balls_after": item_count(h, 497),
                                                            "flag_1347": h.get_flag(1347)})
    # the scene ends in a trainer battle (talk stops there); the bag is read at that point, long after the
    # hand-over (L3021/L3031: 'you're giving it to me?!') and with no TakeItem anywhere in file 170
    r["reached_3031"] = 3031 in r.get("offsets", [])
    r["verdict"] = ("confirmed" if r.get("friend_balls_after") == 1 and r["reached_3031"]
                    else "contradicted" if r["reached_3031"] else "blocked")
    return r


def case_gyroball(rom, out):
    """D-1425: Violet City Forretress kid (zone 73, script 15, flag 1850 clear): with TM74 (401), Yes to
    'Give the Youngster the TM for Gyro Ball?' (L1873 ... L3872). Is the TM taken?"""
    def setup(h):
        M.remove_item(h, 401)
        M.add_item(h, 401, 1, "tm")
    r = talk_obj(rom, out, 73, 15, answers=[0], clear=(1850, 740), setup=setup, tag="gyroball",
                 read=lambda h: {"tm74_after": item_count(h, 401), "flag_1850": h.get_flag(1850)})
    r["reached_3872"] = 3872 in r.get("offsets", [])
    r["verdict"] = ("confirmed" if r.get("tm74_after") == 1 and r["reached_3872"] and r["flag_1850"]
                    else "contradicted" if r["reached_3872"] else "blocked")
    return r


def case_coins(rom, out, variant):
    """D-1415: Goldenrod Game Corner clerk (zone 183, file 903), the inflated-price menu (L6396). Variant
    option500: run from L7575 ('500 coins for $50000'); option50: L7501 ('50 coins for $5000', control).
    $60000, 0 coins. The
    coin commands need the script overlay the clerk's script loads first (ScriptOverlayCmd 3 0, as at L1524);
    without it CheckGiveCoins never returns."""
    label = {"option500": 7575, "option50": 7501}[variant]
    with M.session(rom, out) as h:
        tr = M.OpTrace(h)
        enter(h, 183)
        set_coins(h, 0)
        M.set_money(h, 60000)
        c0, m0 = coins(h), G.money(h)
        arr1 = h.read(h.array(1), 0x40)
        m = tr.mark()
        run_from_with(h, 903, label, pre=[("ScriptOverlayCmd", 3, 0)])   # the coin commands' overlay, as at L1524
        end = M.talk_through(h, tr, answers=[2], max_iter=60)            # back at the menu: 'No, thanks'
        arr1b = h.read(h.array(1), 0x40)
        res = {"variant": variant, "label": label, "end": end, "coins_before": c0, "coins_after": coins(h),
               "money_before": m0, "money_after": G.money(h), "msgs": tr.msgs(m),
               "give_coins": tr.u16_args("GiveCoins", m), "shot": str(h.screenshot(f"coins_{variant}")),
               "array1_changed": [hex(i) for i in range(0x40) if arr1[i] != arr1b[i]]}
    return res


def judge_coins(res):
    a, b = res["option500"], res["option50"]
    ok = (a["money_before"] - a["money_after"] == 50000 and a["coins_after"] - a["coins_before"] == 50
          and b["money_before"] - b["money_after"] == 5000 and b["coins_after"] - b["coins_before"] == 50)
    return "confirmed" if ok else "contradicted"


def case_lara(rom, out):
    """D-1502: Lara's thanks after the race (Route 14, zone 22, file 202 L3524): msg 62 says 'these Heart
    Scales'; the script gives item 93 with quantity 1. Run from 3524 with no Heart Scales; count them."""
    with M.session(rom, out) as h:
        M.remove_item(h, 93)
        tr = M.OpTrace(h)
        enter(h, 22)
        m = tr.mark()
        run_from_with(h, 202, 3524)
        shots = []
        end = M.talk_through(h, tr, shots=shots, tag="lara", max_iter=60)
        res = {"end": end, "msgs": tr.msgs(m), "heart_scales": item_count(h, 93), "shots": shots[-4:]}
        res["verdict"] = "confirmed" if res["heart_scales"] == 1 and 62 in res["msgs"] else "contradicted"
    return res


def case_merchant(rom, out):
    """D-1421: Saffron Choice-item merchant (zone 59, file 824 L2891): 'Nothing, thanks' (4th item) falls
    through to NPCMsg 40, a menu label ('The Pokemon League's reforms') instead of a goodbye."""
    with M.session(rom, out) as h:
        tr = M.OpTrace(h)
        enter(h, 59)
        m = tr.mark()
        run_from_with(h, 824, 2891)
        shots = []
        end = M.talk_through(h, tr, answers=[3], shots=shots, tag="merchant", max_iter=40)
        res = {"end": end, "msgs": tr.msgs(m), "reached_2989": tr.reached(2989, m), "shots": shots[-4:],
               "money_change": 0}
        res["verdict"] = "confirmed" if res["reached_2989"] and res["msgs"][-1:] == [40] else "contradicted"
    return res


RESPAWN_HIDE = (578, 450, 773, 774, 775)       # cleared by L744/L756/L764/L770/L801 when the caught flag is clear


def case_ssticket(rom, out, variant):
    """D-1492 / D-1335: Hall of Fame script (zone 306, file 822) from L154 (HasItem 456 -> L603, else L175).
    Variant held456: S.S. Ticket item 456 in the bag; held478: only item 478 (the Sea Cottage ticket). The
    hide flags of the respawnable legendaries are set and their caught flags cleared first, so the CallIf
    blocks show whether they are cleared again (D-1335). Only the branch and the flags are read."""
    caught = (278, 279, 361, 362, 363, 364, 330, 365, 371, 373)
    with M.session(rom, out, flags=RESPAWN_HIDE, clear=caught) as h:
        M.remove_item(h, 456)
        M.remove_item(h, 478)
        M.add_item(h, 456 if variant == "held456" else 478, 1, "key")
        tr = M.OpTrace(h)
        m = tr.mark()
        run_from_with(h, 822, 154, anywhere=True)      # the Hall of Fame map starts its scene on entry
        h.step(400)
        res = {"variant": variant, "reached_603": tr.reached(603, m), "reached_175": tr.reached(175, m),
               "hide_flags_after": {f: h.get_flag(f) for f in RESPAWN_HIDE},
               "ops": tr.ops(m)[:40], "shot": str(h.screenshot(f"ssticket_{variant}"))}
    return res


def judge_ssticket(res):
    a, b = res["held456"], res["held478"]
    ok = a["reached_603"] and not a["reached_175"] and b["reached_175"] and not b["reached_603"]
    return "confirmed" if ok else "contradicted"


def case_hm04(rom, out, variant):
    """D-1403: Fuchsia, Baoba family room man (zone 481, script 3): HasItem 423 (HM04 Strength) -> L334;
    without it msg 5 (the pond / Surf line). Variant hm04 / none."""
    def setup(h):
        M.remove_item(h, 423)
        if variant == "hm04":
            M.add_item(h, 423, 1, "tm")
    r = talk_obj(rom, out, 481, 3, setup=setup, tag=f"hm04_{variant}", max_iter=60)
    r["reached_334"] = 334 in r.get("offsets", [])
    return r


def judge_hm04(res):
    a, b = res["hm04"], res["none"]
    return "confirmed" if a["reached_334"] and not b["reached_334"] and 5 in b["msgs"] else "contradicted"


def case_dawn(rom, out, variant):
    """D-1444: Route 9 Veteran Dawn (zone 17, script 20): CheckBadge 4 only. Variant only4: badge 4 alone;
    all_but4: badges 0-15 except 4. Which branch (L3929 = challenge, msg 137 = refusal)?"""
    def setup(h):
        for b in range(16):
            G.set_badge(h, b, (b == 4) if variant == "only4" else (b != 4))
    r = talk_obj(rom, out, 17, 20, setup=setup, tag=f"dawn_{variant}", answers=[1, 1, 1], max_iter=40)
    r["reached_3929"] = 3929 in r.get("offsets", [])
    return r


def judge_dawn(res):
    a, b = res["only4"], res["all_but4"]
    return "confirmed" if a["reached_3929"] and not b["reached_3929"] and 137 in b["msgs"] else "contradicted"


def case_uxie(rom, out, variant):
    """D-1439: Lake guardian's quiz, question 4 (zone 294, file 935 L1205, MenuInit cancellable): which
    answers go on to question 5 (msg 18, L1299) and which to the failure (L1825)? Variant a0..a3 = the n-th
    choice; b = the B button (0xFFFE is not tested, so it falls through like the right answer?)."""
    with M.session(rom, out, vars={0x40B2: 0}) as h:
        tr = M.OpTrace(h)
        enter(h, 294)
        m = tr.mark()
        run_from_with(h, 935, 1205)
        ans = ["B"] if variant == "b" else [int(variant[1])]
        shots = []
        end = M.talk_through(h, tr, answers=ans, shots=shots, tag=f"uxie_{variant}", max_iter=25)
        res = {"variant": variant, "choice_value": tr.cmp_at(1260, m), "q5": tr.reached(1299, m),
               "fail": tr.reached(1825, m), "msgs": tr.msgs(m)[:6], "shots": shots[-3:]}
    return res


def judge_uxie(res):
    """'confirmed' when only the 2nd choice (14) goes on; B (which returns the last choice here) fails too."""
    others = [k for k in ("a0", "a2", "a3", "b") if k in res]
    ok = res["a1"]["q5"] and not res["a1"]["fail"] and all(res[k]["fail"] and not res[k]["q5"] for k in others)
    return "confirmed" if ok else "contradicted"


def case_cameron(rom, out, variant):
    """D-1334: Route 34 level script (file 237 L2599 -> L4691: CheckBadge 18, always false -> SetFlag 638):
    Cameron (object 15, hide flag 638) on Wednesday with all 16 badges and flag 393 clear. Variant wed: as
    is; control thu_ctl: badge 18 can't be given, so the control is the same entry on Thursday (the weekday
    branch is never reached either way)."""
    wd = 3 if variant == "wed" else 4
    with M.session(rom, out, clock=M.weekday_clock(wd), clear=(393, 638)) as h:
        for b in range(16):
            G.set_badge(h, b)
        tr = M.OpTrace(h)
        enter(h, 38, 363, 418)
        res = {"weekday": wd, "flag_638": h.get_flag(638), "cameron_visible": G.obj_at(h, 38, 15) is not None,
               "badge18_value": tr.cmp_at(4697), "weekday_branch": tr.reached(4710),
               "shot": str(h.screenshot(f"cameron_{variant}"))}
    return res


def judge_cameron(res):
    ok = all(r["flag_638"] and not r["cameron_visible"] and not r["weekday_branch"] for r in res.values()
             if isinstance(r, dict) and "flag_638" in r)
    return "confirmed" if ok else "contradicted"


def case_brock_cave(rom, out, variant):
    """D-1394: Diglett's Cave (zone 106, file 5 L608): after the final Hall of Fame (2261) Brock (object 7,
    hide flag 610) appears only if the hour is 17 and 18 and 19 at once. Variant = the pinned hour."""
    hour = int(variant)
    with M.session(rom, out, clock=datetime.datetime(2026, 10, 9, hour, 30), flags=(2261, 610)) as h:
        tr = M.OpTrace(h)
        enter(h, 106, 36, 6)
        res = {"hour": hour, "brock_visible": G.obj_at(h, 106, 7) is not None, "flag_610": h.get_flag(610),
               "hour_compares": list(tr.cmp.values())[:8], "shot": str(h.screenshot(f"brock_cave_{hour}"))}
    return res


def judge_brock_cave(res):
    vis = [r["brock_visible"] for r in res.values() if isinstance(r, dict) and "brock_visible" in r]
    return "confirmed" if vis and not any(vis) else "contradicted"


def case_gatehouse(rom, out, variant):
    """D-1336: Route 36 gatehouse (zone 149, file 862 script 2): CheckFlag 450 (Sudowoodo hide flag) -> L170;
    clear: msg 2 ('blocked by an odd tree'). Variant clear (as the hack leaves it) / set (control)."""
    r = talk_obj(rom, out, 149, 2, flags=(450,) if variant == "set" else (), clear=() if variant == "set" else (450,),
                 tag=f"gatehouse_{variant}", max_iter=30)
    return r


def judge_gatehouse(res):
    a, b = res["clear"], res["set"]
    return "confirmed" if 2 in a["msgs"] and 2 not in b["msgs"] else "contradicted"


def case_museum(rom, out):
    """D-1424: Pewter Museum Brock (zone 471, script 16, object 6 / hide flag 1315): talking with 0x52C and
    0x52D clear sets flag 1323, the Route 30 Chikorita's hide flag. 1323 clear before."""
    r = talk_obj(rom, out, 471, 16, clear=(1323, 0x52C, 0x52D, 1315), tag="museum", max_iter=60,
                 read=lambda h: {"flag_1323": h.get_flag(1323)})
    r["verdict"] = "confirmed" if r.get("flag_1323") else "contradicted"
    return r


# ----------------------------------------------------------------------------- battles
def _battle_intro(h, tag, n=14):
    log = K.SceneLog(h)
    mine = [x["species"] for x in h.party()]
    return log, mine


def case_battle_type(rom, out, variant):
    """D-1410 / D-1447: is the battle a Double? Variant lex: Route 41 Swimmer Lex's 'Doubles' option (zone 95,
    file 960 L2385: TrainerBattle 823 0 0 0); yellow: Yellow's 'Singles' option in the League (zone 305, file
    821 L3734: TrainerBattle 951 951 0 0). Read: send-out cries before the first command menu (1 = single,
    2 = double), the copies of the team in RAM, the intro screenshot."""
    zone, file, label, trainer = {"lex": (95, 960, 2385, 823), "yellow": (305, 821, 3734, 951)}[variant]
    _, team = rom_team(trainer)
    with M.session(rom, out) as h:
        enter(h, zone)
        log = K.SceneLog(h)
        mine = [x["species"] for x in h.party()]
        run_from_with(h, file, label)
        shots = []
        for k in range(60):
            h.step(30)
            if h.on_screen("battle_menu"):
                break
            if h.in_field() and k % 2:
                h.press("A", after=4)
            if k % 6 == 0:
                shots.append(str(h.screenshot(f"battle_{variant}_{k:02d}")))
        shot_menu = str(h.screenshot(f"battle_{variant}_menu"))
        cries = [e["species"] for e in log.events if e["t"] == "cry" and e["species"] not in mine]
        parties = [p for p in K.find_parties(h) if [x["species"] for x in p["mons"]] == [t["species"] for t in team]]
        res = {"trainer": trainer, "battles": [e["trainers"] for e in log.events if e["t"] == "trainer_battle"],
               "foe_sendout_cries": cries, "team_copies_in_ram": len(parties), "battle_menu": h.on_screen("battle_menu"),
               "shot_menu": shot_menu, "shots": shots[-3:]}
        res["double"] = len(cries) >= 2
    return res


def judge_battle_type(res):
    a, b = res["lex"], res["yellow"]
    return "confirmed" if a["battle_menu"] and not a["double"] and b["battle_menu"] and b["double"] else "contradicted"


def case_trainer(rom, out, variant):
    """D-1497 (IVs), D-1342 (duplicate moves), D-1498 (Deoxys form 4), D-1341 (stored ability): start
    `TrainerBattle <variant> 0 0 0` and read the foe party the battle built (RAM Party struct whose species
    match the ROM team): IVs, moves, form, the block-A ability byte (0/1 here: not the ability id); INFO
    screenshots (own lead, then RIGHT = the foe's lead; INFO shows no foe ability). For D-1341 the leads of
    trainers 146 (Glalie, stored Snow Warning) and 376 (Houndoom, stored Drought) announce their weather on
    entry only if the battle uses the stored ability: the command-menu and INFO screenshots show it."""
    tid = int(variant)
    td, team = rom_team(tid)
    with M.session(rom, out) as h:
        G.lead(h, FAST_LEAD)
        h.trainer_battle(tid)
        h.run_until(lambda h: h.on_screen("battle_menu"), 3000, every=10)
        parties = [p for p in battle_parties_raw(h) if [x["species"] for x in p["mons"]] == [t["species"] for t in team]]
        shot = str(h.screenshot(f"trainer_{tid}_battle"))
        h.touch(*E.BATTLE_BUTTONS["info"], frames=10, after=120)
        shot_info = str(h.screenshot(f"trainer_{tid}_info"))
        h.press("RIGHT", after=120)                    # INFO: LEFT/RIGHT cycle the Pokemon on the field
        shot_info2 = str(h.screenshot(f"trainer_{tid}_info_foe"))
        res = {"trainer": tid, "rom_team": [{k: t[k] for k in ("species", "form", "level", "iv", "ivs", "hp_ivs", "ability", "moves")}
                                            for t in team],
               "battle_party": parties[0]["mons"] if parties else None, "copies": len(parties),
               "shot": shot, "shot_info": shot_info, "shot_info_foe": shot_info2}
        if parties:
            res["iv_rule_holds"] = all(b["ivs"][0] == t["hp_ivs"] and all(v == t["ivs"] for v in b["ivs"][1:])
                                       for b, t in zip(parties[0]["mons"], team))
            res["moves_as_rom"] = all([m for m in b["moves"] if m] == t["moves"] for b, t in zip(parties[0]["mons"], team))
            res["forms"] = [b["form"] for b in parties[0]["mons"]]
            res["ability_bytes"] = [b["ability"] for b in parties[0]["mons"]]
    return res


def judge_trainer(res):
    rows = [r for r in res.values() if isinstance(r, dict) and "trainer" in r]
    if not rows or any(r.get("battle_party") is None for r in rows):
        return "blocked"
    return "confirmed" if all(r["iv_rule_holds"] and r["moves_as_rom"] for r in rows) else "contradicted"


# ----------------------------------------------------------------------------- Pokemon data: forms, TMs, evolutions
def summary_shot(h, slot, name, pages=(0, 2)):
    """Open the party (X menu) -> summary of <slot>; screenshot the given pages (0 info, 2 = stats/moves page
    after two RIGHT presses); back to the field."""
    h.touch(*E.FIELD_MENU["pokemon"], frames=12, after=150)
    h.touch(*E.PARTY_SLOTS[slot], frames=12, after=60)
    h.touch(*E.PARTY_SUMMARY, frames=12, after=150)
    shots, page = [], 0
    for p in pages:
        while page < p:
            h.press("RIGHT", after=40)
            page += 1
        shots.append(str(h.screenshot(f"{name}_p{p}")))
    for _ in range(3):
        h.press("B", after=90)
    return shots


def two_forms(h, species, level, forms=(1, 0)):
    """Generator Pokemon <species> in form forms[0] as the lead and forms[1] in slot 5 (same generator PID)."""
    h.generate_pokemon(species, level=level, form=forms[1])
    h.swap_party(0, h.generated_slot)
    h.generate_pokemon(species, level=level, form=forms[0])
    h.swap_party(0, h.generated_slot)


TM_ITEMS = {"tm13": (340, 58), "tm11": (338, 241), "tm39": (366, 317)}   # item -> move (Ice Beam, Sunny Day, Rock Tomb)


def case_crystal_onix(rom, out, variant):
    """D-1448: Crystal Onix (Onix form 1 = personal 1439, Rock/Ice) and TMs. Party: Crystal Onix lead, Onix
    form 0 in slot 5 (two moves each, so a TM fits). Variant '<tm>_<crystal|onix>': use the TM from the bag
    (the game's own TM path: Use -> 'teach?' Yes -> party list with able/not-able labels), pick the lead
    (crystal) or slot 5 (onix). TM13 Ice Beam is in 1439's list only, TM11 Sunny Day in Onix's only, TM39 Rock
    Tomb in both. Read: the target's moves afterwards, the party-list screenshot, the lead's types (summary)."""
    tm, who = variant.split("_")
    item, move = TM_ITEMS[tm]
    slot = 0 if who == "crystal" else 5
    with M.session(rom, out) as h:
        two_forms(h, 95, 50)
        for s_ in (0, 5):
            h.edit_party_mon(s_, moves=[33, 103, 0, 0], pp=[35, 40, 0, 0])
        lead = mon(h, 0)
        h.bag_put_first(item, 1, "tm")
        h.open_bag()
        h.bag_pocket("tm")
        h.touch(*E.BAG_SLOTS[0], frames=12, after=60)
        h.touch(*E.BAG_USE, frames=12, after=90)
        for _ in range(3):                              # 'booted up', 'it contained X', 'teach X?' -> Yes
            h.press("A", after=90)
        shot_list = str(h.screenshot(f"onix_{variant}_list"))
        h.touch(*E.PARTY_SLOTS[slot], frames=12, after=150)
        shot_pick = str(h.screenshot(f"onix_{variant}_pick"))
        for _ in range(6):
            h.press("A", after=90)
        after = mon(h, slot)["moves"]
        for _ in range(4):
            h.press("B", after=90)
        res = {"tm": tm, "move": move, "target_slot": slot, "lead_species_form": (lead["species"], lead["form"]),
               "lead_stats": lead["stats"], "slot5_stats": mon(h, 5)["stats"], "target_moves_after": after,
               "learned": move in after, "shot_list": shot_list, "shot_pick": shot_pick}
        if who == "crystal" and tm == "tm39":
            res["shots_summary"] = summary_shot(h, 0, f"onix_{variant}_summary", pages=(0,))
    return res


def judge_crystal_onix(res):
    """'contradicted' (the record says Crystal Onix can learn no TM) when the form-1 lead learns TMs; the
    detail says which list the check uses."""
    c = {k: res[k]["learned"] for k in res if isinstance(res[k], dict) and "learned" in res[k]}
    if not any(c.get(k) for k in ("tm13_crystal", "tm11_crystal", "tm39_crystal")):
        return "confirmed"
    return "contradicted"


def case_darumaka(rom, out):
    """D-1443 / D-1491: Darumaka form 1 (Ice Path's wild form; no form-table entry) and its evolution. A
    generator Darumaka form 1 Lv34 leads, form 0 in slot 5 (control). Summary of the lead (types), then a Rare
    Candy (Lv35 -> Darmanitan): species/form and stats (party extension) of the result, compared with personal
    555 (Darmanitan) and 1174 (Zen Mode, Fire/Psychic); summary screenshot."""
    import romdata as R
    with M.session(rom, out, edit=lambda sf: sf.set_pocket("medicine", [(50, 20)])) as h:
        two_forms(h, 554, 34)
        before = {"lead": (mon(h, 0)["species"], mon(h, 0)["form"], mon(h, 0)["stats"]),
                  "slot5": (mon(h, 5)["species"], mon(h, 5)["form"], mon(h, 5)["stats"])}
        shots0 = summary_shot(h, 0, "darumaka_f1", pages=(0,))
        evolved = h.level_up_with_candy(0)
        h.press("B", after=120)
        h.press("B", after=120)
        d = mon(h, 0)
        shots1 = summary_shot(h, 0, "darmanitan_after", pages=(0,))
        base = {sp: R.parse_personal(G.static()["personal"][sp])["stats"] for sp in (555, 1174)}
        res = {"before": before, "after": {"species": d["species"], "form": d["form"], "level": d["level"],
                                           "stats": d["stats"]},
               "personal_555": base[555], "personal_1174": base[1174], "evolved": evolved.get("species"),
               "shots": shots0 + shots1}
        # which base stats fit: Zen Mode has Atk 30 / SpA 140, Standard Mode Atk 140 / SpA 30
        st = d["stats"]
        res["zen_mode_stats"] = st[1] < st[4] if len(st) >= 5 else None   # [max HP, Atk, Def, Spe, SpA, SpD]
        res["verdict"] = ("confirmed" if d["species"] == 555 and d["form"] == 1 and res["zen_mode_stats"]
                          else "contradicted" if d["species"] == 555 else "blocked")
    return res


def case_pancham(rom, out):
    """D-1481: Pancham (674) evolves into Pangoro at Lv32 with a Dark-type in the party (method 31, which the
    evolution code never checks). Pancham Lv31 lead, Umbreon (Dark) in slot 5, Rare Candy -> Lv32: does it
    evolve?"""
    with M.session(rom, out, edit=lambda sf: sf.set_pocket("medicine", [(50, 20)])) as h:
        h.generate_pokemon(197, level=50)
        h.swap_party(0, h.generated_slot)
        h.generate_pokemon(674, level=31)
        h.swap_party(0, h.generated_slot)
        party0 = [(p["species"], p["level"]) for p in h.party()]
        after = h.level_up_with_candy(0)
        h.press("B", after=120)
        res = {"party_before": party0, "after": {"species": after.get("species"), "level": after.get("level")},
               "shot": str(h.screenshot("pancham_after"))}
        res["verdict"] = ("confirmed" if after.get("species") == 674 and after.get("level") == 32
                          else "contradicted" if after.get("species") == 675 else "blocked")
    return res


# ----------------------------------------------------------------------------- move effects in battle
# name -> (record, user species, user moves, wild species, wild level, turns)
MOVE_TESTS = {
    "volttackle": ("D-1319", 25, [344], 129, 2, 1),
    "doubleedge": ("D-1319 control", 25, [38], 129, 2, 1),
    "thunderbolt": ("D-1319 control", 25, [85], 129, 2, 1),
    "blastburn": ("D-1318", 6, [307, 53], 242, 100, 2),
    "hyperbeam": ("D-1318 control", 6, [63, 53], 242, 100, 2),
    "flamethrower": ("D-1318 control", 6, [53, 307], 242, 100, 2),
    "lunardance": ("D-1311", 488, [461], 242, 100, 1),
}


def battle_turn_named(h, move_slot, tag, max_frames=3000):
    """Harness.battle_turn with the text-box screenshots named <tag>_NN (battle_turn names them by frame,
    which collides between parallel runs). Returns (result, [paths])."""
    if not h.wait_screen("battle_menu", 1500):
        raise RuntimeError("battle command menu not found")
    h.touch(*E.BATTLE_BUTTONS["fight"], frames=10, after=40)
    h.touch(*E.MOVE_BUTTONS[move_slot], frames=10, after=60)
    last, shots = None, []
    for i in range(0, max_frames, 15):
        h.step(15)
        if h.in_field():
            h.step(60)
            return "field", shots
        if h.on_screen("battle_menu"):
            return "menu", shots
        box = h.emu.screenshot().crop(K.MSG_BOX).tobytes()
        if box != last:
            last = box
            shots.append(str(h.screenshot(f"{tag}_{len(shots):02d}")))
        if i % 60 == 45:
            h.press("B", after=0)
    return "stuck", shots


def text_sheet(paths, dest):
    """The top-screen text boxes of <paths> stacked into one image (for reading a turn's messages)."""
    from PIL import Image
    crops = [Image.open(p).convert("RGB").crop((0, 140, 256, 192)) for p in paths]
    if not crops:
        return None
    sheet = Image.new("RGB", (256, 52 * len(crops)), (0, 0, 0))
    for i, c in enumerate(crops):
        sheet.paste(c, (0, 52 * i))
    sheet.save(dest)
    return str(dest)


def party_hp(h, slot=0):
    return mon(h, slot)["hp"]


def case_move(rom, out, variant):
    """D-1319 Volt Tackle recoil, D-1318 recharge of Blast Burn & co., D-1311 Lunar Dance. A Lv100 user
    (generator, only the listed moves) fights a scripted WildBattle (Magikarp Lv2, KO'd in one hit, or Blissey
    Lv100, which survives and attacks back; editing the wild Pokemon's moves at the finalizer does not hold).
    Turn 1 uses move 0; for the recharge tests turn 2 uses move 1 at the next command menu. Every text box of
    a turn is screenshotted and stacked into move_<variant>_t<n>_sheet.png (the recoil, recharge and stat
    lines are readable there); the turn's length in frames is kept; the user's HP is read from the party after
    the battle (won, or fled)."""
    rec, sp, moves, foe, flv, turns = MOVE_TESTS[variant]
    with M.session(rom, out) as h:
        G.lead(h, sp, level=100, moves=moves + [0] * (4 - len(moves)), pp=[5] * len(moves) + [0] * (4 - len(moves)))
        hp0 = party_hp(h)
        wl = E.WildLog(h)
        h.run_script(program=E.script_bytes(("LockAll",), ("WildBattle", foe, flv, 0), ("ReleaseAll",), ("End",)))
        if not h.wait_screen("battle_menu", 3000):
            return {"verdict": "blocked", "reason": "no battle menu", "shot": str(h.screenshot(f"move_{variant}_nomenu"))}
        turn_rows = []
        for t in range(turns):
            f0 = h.frame
            try:
                r, shots = battle_turn_named(h, t if t < len(moves) else 0, f"move_{variant}_t{t + 1}")
            except RuntimeError as e:
                r, shots = "stuck: " + str(e), []
            turn_rows.append({"result": r, "frames": h.frame - f0, "text_boxes": len(shots), "shots": shots,
                              "sheet": text_sheet(shots, Path(out) / f"move_{variant}_t{t + 1}_sheet.png")})
            if r != "menu":
                break
        if h.on_screen("battle_menu"):
            h.flee(battle_menu_wait=30)
        G.wait_idle(h, None, 600)
        d = mon(h, 0)
        res = {"record": rec, "user": sp, "moves": moves, "hp_before": hp0, "hp_after": d["hp"],
               "pp_after": None, "turns": turn_rows, "wild": [w["species"] for w in wl.rows],
               "shot_end": str(h.screenshot(f"move_{variant}_end"))}
    return res


def judge_move(res):
    """Per record, from the observed numbers (the text sheets carry the messages):
    D-1319: Volt Tackle costs no HP while Double-Edge does (recoil 1/3) and Thunderbolt doesn't.
    D-1318: a recharge turn makes turn 1 last until the foe has attacked twice: Hyper Beam's turn 1 is much
    longer than Flamethrower's; Blast Burn's is compared with both.
    D-1311: Lunar Dance faints the user (vanilla) or not."""
    out = {}
    v, de, tb = res.get("volttackle"), res.get("doubleedge"), res.get("thunderbolt")
    if v and de and tb and "hp_after" in v and "hp_after" in de and "hp_after" in tb:
        recoil_ok = de["hp_after"] < de["hp_before"] and tb["hp_after"] == tb["hp_before"]
        out["D-1319"] = ("unclear" if not recoil_ok else "no recoil" if v["hp_after"] == v["hp_before"] else "recoil")
    bb, hb, ft = res.get("blastburn"), res.get("hyperbeam"), res.get("flamethrower")
    if bb and hb and ft and all("turns" in x for x in (bb, hb, ft)):
        b, h_, f = (x["turns"][0]["frames"] for x in (bb, hb, ft))
        if any(x["turns"][0]["result"] != "menu" for x in (bb, hb, ft)):
            out["D-1318"] = "unclear"           # e.g. a critical hit KO'd the Blissey: no next turn to see
        elif h_ < 1.25 * f:
            out["D-1318"] = "unclear"
        else:
            out["D-1318"] = "no recharge" if b < 1.15 * f else "recharge" if b > 1.25 * f else "unclear"
    ld = res.get("lunardance")
    if ld and "hp_after" in ld:
        out["D-1311"] = "user faints" if ld["hp_after"] == 0 else "user survives"
    return json.dumps(out, sort_keys=True)


# ----------------------------------------------------------------------------- field moves and warps
def case_cut(rom, out, variant):
    """D-1428: the Cut prompt (std script 10000 = file 146 script 1) with the Cascade Badge (id 1): the
    hack's GetPartySlotWithMove ignores the move. Variant nocut: every party Pokemon knows only Splash; the
    slot value read at @92 (6 = nobody knows Cut) and the message shown (0 = 'cut it?' prompt, 2 = 'looks
    like it can be cut'); answered No, so nothing is cut. Variant fainted_lead: the lead has 0 HP too."""
    with M.session(rom, out) as h:
        G.set_badge(h, 1)
        G.weak_party(h)
        if variant == "fainted_lead":
            G.set_party_hp(h, 0, 0)
        tr = M.OpTrace(h)
        m = tr.mark()
        shots = []
        h.run_script(script_id=10000)
        end = M.talk_through(h, tr, answers=[1], shots=shots, tag=f"cut_{variant}", max_iter=30)
        res = {"variant": variant, "slot_value": tr.cmp_at(92, m), "msgs": tr.msgs(m), "end": end,
               "party_moves": [mon(h, i)["moves"][:1] for i in range(len(h.party()))], "shots": shots[-3:]}
        res["prompt_shown"] = 0 in res["msgs"]
    return res


def judge_cut(res):
    a, b = res["nocut"], res["fainted_lead"]
    ok = a["prompt_shown"] and a["slot_value"] == [0] and b["prompt_shown"] and b["slot_value"] not in ([6], [0])
    return "confirmed" if ok else "contradicted" if not a["prompt_shown"] else json.dumps(
        {"nocut": a["slot_value"], "fainted_lead": b["slot_value"]})


def case_gatehouse_warp(rom, out, variant):
    """D-1332: the unused National Park north gatehouse (zone 150, 'Pokeathlon Dome'). Variant exit: warp
    into the gatehouse next to its exit (5, 12) and walk onto it: its target is National Park warp #5, which
    the hack's zone 96 lacks. Variant entrance: in the National Park (zone 96), is the entrance warp #4 at
    (33, 15) reachable on foot (MapGrid path from the south gate), and does walking onto it enter zone 150?"""
    with M.session(rom, out) as h:
        if variant == "exit":
            h.warp(150, 5, 11, E.DIRS["DOWN"])
            h.step(60)
            p0 = h.position()
            h.walk("DOWN", 2)
            samples = []
            for k in range(10):
                h.step(60)
                samples.append({"pos": h.position(), "field": h.in_field(), "pc": hex(h.reg.pc)})
            res = {"start": p0, "samples": samples[::3], "shot": str(h.screenshot("gatehouse_exit"))}
            res["walks_after"] = M.can_walk(h, "UP", 1)[0] if h.in_field() else False
            res["shot_after"] = str(h.screenshot("gatehouse_exit_after"))
        else:
            g = E.MapGrid(h.rom, 96)
            path = g.path((40, 85), (33, 16))
            res = {"path_from_south_gate_to_33_16": None if path is None else len(path),
                   "tile_33_15": g.tile(33, 15), "tile_33_16": g.tile(33, 16)}
            h.warp(96, 33, 17, E.DIRS["UP"])
            h.step(60)
            h.walk("UP", 3)
            h.step(240)
            res.update(pos=h.position(), shot=str(h.screenshot("gatehouse_entrance")))
    return res


def judge_gatehouse_warp(res):
    """'confirmed' (latent): the exit drops the player at nonsense coordinates in zone 96 where they can't
    walk, and the entrance tiles (33, 15)/(33, 16) are blocked with no path to them, so normal play can't
    get there."""
    a, b = res["exit"], res["entrance"]
    pos = a["samples"][-1]["pos"]
    lost = pos[0] == 96 and not (0 <= pos[1] < 128 and 0 <= pos[2] < 128) and not a["walks_after"]
    sealed = b["path_from_south_gate_to_33_16"] is None and b["tile_33_16"][1] and b["pos"][0] == 96
    return "confirmed" if lost and sealed else "contradicted" if not lost else "observed"


def case_palkia_cabin(rom, out):
    """D-1417: Palkia's space (zone 521): the cabin door warp (20, 25) -> zone 523. Warp to (20, 24), walk
    DOWN twice: does the map change? MapGrid: is (20, 25) blocked?"""
    with M.session(rom, out) as h:
        g = E.MapGrid(h.rom, 521)
        h.warp(521, 20, 24, E.DIRS["DOWN"])
        h.step(60)
        p0 = h.position()
        h.walk("DOWN", 2)
        h.step(240)
        res = {"start": p0, "pos": h.position(), "tile_20_25": g.tile(20, 25), "tile_20_26": g.tile(20, 26),
               "shot": str(h.screenshot("palkia_cabin"))}
        res["verdict"] = "confirmed" if res["pos"][0] == 521 else "contradicted"
    return res


# ----------------------------------------------------------------------------- shared flags, gifts
def case_shinystone(rom, out, variant):
    """D-1400: Route 17 item ball (zone 25, object 21, script 4: Shiny Stone 107, then SetFlag 1890) is hidden
    by flag 1890, which the Mt. Moon roadblock scene also sets (file 9 @5522, static). Variant clear: 1890
    clear -> the ball is there and gives the Shiny Stone; set: 1890 set (after Mt. Moon) -> no ball."""
    on = variant == "set"
    with M.session(rom, out, flags=(1890,) if on else (), clear=() if on else (1890,)) as h:
        M.remove_item(h, 107)
        tr = M.OpTrace(h)
        h.warp(25, 1143, 403, E.DIRS["UP"])
        h.step(90)
        o = G.obj_at(h, 25, 21)
        res = {"flag_1890": on, "ball_visible": o is not None, "shot": str(h.screenshot(f"shinystone_{variant}"))}
        if o is not None:
            r = M.talk(h, tr, tag=f"shinystone_{variant}", max_iter=40)
            res.update(bag_change=r["bag_change"], flag_1890_after=h.get_flag(1890))
    return res


def judge_shinystone(res):
    a, b = res["clear"], res["set"]
    ok = a["ball_visible"] and a.get("bag_change", {}).get("107") == 1 and not b["ball_visible"]
    return "confirmed" if ok else "contradicted"


def case_rockyhelmet(rom, out):
    """D-1412: Ilex Forest Rocky Helmet man (zone 117, script 20, object 30): his gift (item 324) sets flag 2104,
    the bug hunt's Ariados 'done' flag (file 92 L1927 etc., static)."""
    r = talk_obj(rom, out, 117, 20, clear=(2104,), tag="rockyhelmet", max_iter=60,
                 setup=lambda h: M.remove_item(h, 324), read=lambda h: {"flag_2104": h.get_flag(2104)})
    r["verdict"] = "confirmed" if r.get("flag_2104") and r.get("bag_change", {}).get(324) == 1 else "contradicted"
    return r


def case_graffiti(rom, out):
    """D-1420: Cinnabar graffiti couple (zone 57, file 812): SetFlag 1742 @3390 comes before TrainerBattle
    982 983 (a loss whites out at L4661). doomed_party (in a Double Battle the forced switch of a weak party
    stalls on fainted slots), run from 3390, lose; after the white-out read
    1742, then talk to the couple (object 6, script 12: CheckFlag 1742 -> L3216 'our names are carved')."""
    with M.session(rom, out, clear=(1742, 1747)) as h:
        G.doomed_party(h)                 # Splash only, lead at 1 HP, the rest fainted: the first hit ends it
        tr = M.OpTrace(h)
        enter(h, 57, 1034, 504)
        m = tr.mark()
        run_from_with(h, 812, 3390)
        h.run_until(lambda h: h.on_screen("battle_menu"), 3000, every=10)
        shot_b = str(h.screenshot("graffiti_battle"))
        log = K.SceneLog(h)
        trace = G.lose_battle(h)
        G.finish_scene(h, log)
        h.step(200)
        res = {"whiteout": "WhiteOut" in tr.names_since(m), "flag_1742_after_loss": h.get_flag(1742),
               "where": h.position(), "lose_trace_end": trace[-1][:2] if trace else None, "shot_battle": shot_b,
               "shot_whiteout": str(h.screenshot("graffiti_whiteout"))}
        try:
            G.safe_warp(h, 57, 1034, 504, E.DIRS["UP"])
        except RuntimeError as e:
            res.update(verdict="observed" if res["flag_1742_after_loss"] else "contradicted", talk="not reached: " + str(e))
            return res
        h.step(60)
        r = talk_obj_here(h, tr, 57, 12, "graffiti_after")
        res.update(talk_msgs=r["msgs"], reached_3216=3216 in r["offsets"], shot=str(h.screenshot("graffiti_after_end")))
        res["verdict"] = ("confirmed" if res["whiteout"] and res["flag_1742_after_loss"] and res["reached_3216"]
                          else "contradicted")
    return res


def talk_obj_here(h, tr, zone, script, tag):
    oid = obj_for_script(zone, script)
    face_obj(h, zone, oid)
    r = M.talk(h, tr, tag=tag, max_iter=40)
    r["offsets"] = sorted({o for _, o in r["ops"]})
    return r


def fateful(raw):
    """Fateful-encounter bit: block B +0x18 bit 0 (Gen 4 layout)."""
    return M.decrypted_blocks(raw)[32 + 0x18] & 1


def set_fateful(h, slot, on=True):
    """Set/clear the fateful-encounter bit (block B +0x18 bit 0) of a party Pokemon; checksum fixed."""
    a = h.array(E.ARR_PARTY) + 8 + 236 * slot
    raw = bytearray(h.read(a, 136))
    pid, _, checksum = struct.unpack_from("<IHH", raw, 0)
    plain = bytearray(struct.pack("<64H", *[w ^ k for w, k in zip(struct.unpack_from("<64H", raw, 8),
                                                                   E._prng_stream(checksum, 64))]))
    b = 32 * E.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24].index("B") + 0x18
    plain[b] = (plain[b] | 1) if on else (plain[b] & ~1)
    words = struct.unpack("<64H", plain)
    checksum = sum(words) & 0xFFFF
    struct.pack_into("<H", raw, 6, checksum)
    struct.pack_into("<64H", raw, 8, *[w ^ k for w, k in zip(words, E._prng_stream(checksum, 64))])
    h.write(a, bytes(raw))


def case_gracidea(rom, out, variant):
    """D-1490: the game's Shaymin (Forest of Time, zone 327, file 52 @3428 GiveMon 492 Lv90) and the Gracidea
    (item 466, Key Items). Run the GiveMon (party of five, so it joins the party), read its fateful-encounter
    bit, then use the Gracidea on it from the bag at noon; read the form (Sky Forme = 1). Variant asgiven: as the
    script made it; fateful: the bit set by a data edit first (control: shows the Gracidea path itself works)."""
    with M.session(rom, out, clock=datetime.datetime(2026, 10, 9, 12)) as h:
        h.w32(h.array(E.ARR_PARTY) + 4, 5)
        tr = M.OpTrace(h)
        enter(h, 327)
        m = tr.mark()
        run_from_with(h, 52, 3428)
        M.talk_through(h, tr, max_iter=30)
        party = h.party()
        slot = next((i for i, p in enumerate(party) if p["species"] == 492), None)
        if slot is None:
            return {"verdict": "blocked", "reason": "no Shaymin", "party": [p["species"] for p in party]}
        res = {"variant": variant, "slot": slot, "fateful_as_given": fateful(M.party_raw(h, slot)),
               "form_before": party[slot]["form"]}
        if variant == "fateful":
            set_fateful(h, slot)
        res["fateful_used"] = fateful(M.party_raw(h, slot))
        h.bag_put_first(466, 1, "key")
        h.open_bag()
        h.bag_pocket("key")
        shots = []
        h.touch(*E.BAG_SLOTS[0], frames=12, after=60)
        shots.append(str(h.screenshot(f"gracidea_{variant}_1")))
        h.touch(*E.BAG_USE, frames=12, after=90)
        shots.append(str(h.screenshot(f"gracidea_{variant}_2")))
        h.touch(*E.PARTY_SLOTS[slot], frames=12, after=200)
        shots.append(str(h.screenshot(f"gracidea_{variant}_3")))
        for k in range(4):
            h.step(150)
            shots.append(str(h.screenshot(f"gracidea_{variant}_{4 + k}")))
            h.press("A", after=30)
        for _ in range(3):
            h.press("B", after=90)
        res["form_after"] = h.party()[slot]["form"]
        res["shots"] = shots
    return res


def judge_gracidea(res):
    a, b = res["asgiven"], res["fateful"]
    if b.get("form_after") != 1:
        return "blocked"              # the control did not reach the Gracidea's effect
    return "confirmed" if not a["fateful_as_given"] and a["form_after"] == 0 else "contradicted"


# ----------------------------------------------------------------------------- registry, runner, suite
# name -> (function, variants or None, judge or None, records)
CASES = {
    "tutor": (case_tutor, tuple(f"{t}{n}" for t in TUTORS for n in (3, 4)), judge_tutor,
              "D-1305 D-1347 D-1338 D-1408"),
    "nugget": (case_nugget, ("have", "sell"), judge_nugget, "D-1404"),
    "friendball": (case_friendball, None, None, "D-1399"),
    "gyroball": (case_gyroball, None, None, "D-1425"),
    "coins": (case_coins, ("option500", "option50"), judge_coins, "D-1415"),
    "lara": (case_lara, None, None, "D-1502"),
    "merchant": (case_merchant, None, None, "D-1421"),
    "ssticket": (case_ssticket, ("held456", "held478"), judge_ssticket, "D-1492 D-1335"),
    "hm04": (case_hm04, ("hm04", "none"), judge_hm04, "D-1403"),
    "dawn": (case_dawn, ("only4", "all_but4"), judge_dawn, "D-1444"),
    "uxie": (case_uxie, ("a0", "a1", "a2", "a3", "b"), judge_uxie, "D-1439"),
    "cameron": (case_cameron, ("wed", "thu_ctl"), judge_cameron, "D-1334"),
    "brock_cave": (case_brock_cave, ("17", "18", "19"), judge_brock_cave, "D-1394"),
    "gatehouse": (case_gatehouse, ("clear", "set"), judge_gatehouse, "D-1336"),
    "museum": (case_museum, None, None, "D-1424"),
    "battle_type": (case_battle_type, ("lex", "yellow"), judge_battle_type, "D-1410 D-1447"),
    "crystal_onix": (case_crystal_onix, tuple(f"{t}_{w}" for t in TM_ITEMS for w in ("crystal", "onix")),
                     judge_crystal_onix, "D-1448"),
    "darumaka": (case_darumaka, None, None, "D-1443 D-1491"),
    "pancham": (case_pancham, None, None, "D-1481"),
    "move": (case_move, tuple(MOVE_TESTS), judge_move, "D-1319 D-1318 D-1311"),
    "cut": (case_cut, ("nocut", "fainted_lead"), judge_cut, "D-1428"),
    "gatehouse_warp": (case_gatehouse_warp, ("exit", "entrance"), judge_gatehouse_warp, "D-1332"),
    "palkia_cabin": (case_palkia_cabin, None, None, "D-1417"),
    "shinystone": (case_shinystone, ("clear", "set"), judge_shinystone, "D-1400"),
    "rockyhelmet": (case_rockyhelmet, None, None, "D-1412"),
    "graffiti": (case_graffiti, None, None, "D-1420"),
    "gracidea": (case_gracidea, ("asgiven", "fateful"), judge_gracidea, "D-1490"),
    "trainer": (case_trainer, ("11", "31", "80", "253", "865", "146", "376"), judge_trainer,
                "D-1497 D-1342 D-1498 D-1341"),
}


def run_cases(roms, cases, out, jobs=6, variants=None):
    """Each case/variant and ROM in its own child process (`hackbugs --child`); judges combine variants."""
    from concurrent.futures import ThreadPoolExecutor
    variants = variants or {}
    todo = [(c, v, l) for c in cases for v in (variants.get(c) or CASES[c][1] or [None]) for l in roms]

    def run(job):
        c, v, l = job
        try:
            return c, v, l, E.run_child(["hackbugs", "--child", c + (":" + v if v else ""), "--rom", roms[l],
                                         "--out", out], timeout=1800)
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


# Cheap deterministic cases for `emu_harness.py suite` and the verdict each must keep (the hack's behaviour
# as observed on 2026-10-06).
SUITE_EXPECT = {
    "tutor": "confirmed", "nugget": "confirmed", "gyroball": "confirmed", "coins": "confirmed", "lara": "confirmed",
    "merchant": "confirmed", "ssticket": "confirmed", "hm04": "confirmed", "dawn": "confirmed", "uxie": "confirmed",
    "cameron": "confirmed", "brock_cave": "confirmed", "gatehouse": "confirmed", "museum": "confirmed",
    "battle_type": "confirmed", "trainer": "confirmed", "crystal_onix": "contradicted", "darumaka": "confirmed",
    "pancham": "confirmed", "cut": "confirmed", "gatehouse_warp": "confirmed", "palkia_cabin": "confirmed",
}
# Not in the suite: `move` (the battle RNG isn't reproducible run to run; a critical hit can KO the Blissey,
# then D-1318 reads 'unclear') and the long scenes (friendball, graffiti, gracidea, rockyhelmet, shinystone).
SUITE_VARIANTS = {"uxie": ("a1", "b"), "trainer": ("11", "31", "146"), "crystal_onix": ("tm13_crystal", "tm11_crystal")}


def suite_check(rom, out):
    """emu_harness.py suite: the SUITE_EXPECT cases on one ROM; pass when every verdict is the expected one."""
    report = run_cases({"x": rom}, list(SUITE_EXPECT), out, jobs=10, variants=SUITE_VARIANTS)
    got = {c: report[c]["x"].get("verdict") for c in SUITE_EXPECT}
    return got == SUITE_EXPECT, {"verdicts": got}


def cmd(a):
    """emu_harness.py hackbugs: each case/variant and ROM in its own child process; one JSON report."""
    if a.child:
        o = out_dir(a.out, a.rom)
        name, _, variant = a.child.partition(":")
        fn = CASES[name][0]
        res = fn(a.rom, o, variant) if variant else fn(a.rom, o)
        print("RESULT " + json.dumps(res, ensure_ascii=False, default=str))
        return 0
    cases = list(CASES) if a.case == "all" else a.case.split(",")
    langs = ["cn", "en"] if a.lang == "both" else [a.lang]
    roms = {l: {"cn": a.rom_cn, "en": a.rom_en}[l] for l in langs}
    report = run_cases(roms, cases, a.out, a.jobs)
    for c in cases:
        for l in langs:
            print(json.dumps({"case": c, "rom": l, "records": CASES[c][3], "verdict": report[c][l].get("verdict")}),
                  flush=True)
    name = ("all" if set(cases) == set(CASES) else "_".join(cases)[:80]) + ("" if a.lang == "cn" else "_" + a.lang)
    path = Path(a.out) / "hackbugs" / ("report_" + name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"report": str(path)}))
    return 0
