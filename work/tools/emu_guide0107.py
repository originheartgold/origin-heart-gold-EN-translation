#!/usr/bin/env python3
"""emu_guide0107 - emulator checks for the hedged claims in guide chapters 01-07 (`emu_harness.py guide0107`).

Each case puts the game into the state the guide's *Source:* line names (flags, vars, party, clock, map),
runs the hack's own event script (talking to the object, or a GoTo into the script's own bytes at a label
when only a later part matters), and reads back what the game did: flags, vars, party, bag, money, live map
objects, messages shown, battles started, memory writes. Every case returns a dict with `verdict`
('confirmed', 'contradicted', 'observed' or 'blocked') and the evidence; screenshots go to
<out>/guide01_07/<lang>/.

    .venv/bin/python work/tools/emu_harness.py guide0107 [--case electrode,promo_flag,...] [--lang cn|en|both]

Cases (guide claim -> what is run; variants run in separate child processes, a judge combines them):
  promo_flag    D-1333: Route 1 promoter (file 168 script 4) sets flag 7286, past the flag array: the byte
                written, its save array (the Pokedex), its meaning, reads of it            -> D-1550
  mortar_flag   D-1333: `SetFlag 4461` (Mt. Mortar end, file 962 @1819) the same way         -> D-1550
  electrode     01 Victory Road 1F Lv70 Electrode ball: flee (removed) / lose (white-out, stays)
  pikachu       01 Viridian Pikachu thief: back at its first spot after leaving the city
  pidgeot       01 Viridian Forest Pidgeot loan: lend through the party menu, get back trade record 6
  mom_visit     01 "Meet my mom" plays Cynthia's version (flag 106) / control with 106 clear
  living        01 the 2F PC at the move-in stage does nothing (flag 106) / control
  misty_date    02/04 Misty missing from the Gym and the Cape after a won Resort Zone date
  clash         03 Vermilion clash: side flags reset at the clash, re-choosing locks both partners
  ssanne        03 S.S. Anne: real boarding, flag 1440, Captain's HM01 and Blue's salt / control  -> D-1549
  corner_kid    03 Rock Tunnel corner kid: a loss freezes the game / two controls          -> D-1548
  sabrina       03 Pokemon Tower Sabrina with var 0x40AF = 0 / 5
  tony          04 Department Store roof before the Route 7 scene, then Suzie's offer
  monday        04 Pal Park Monday groups at seven pinned hours (ScrCmd_522 = hour)        -> D-1551
  blue_saffron  04 Saffron takeover step 5: Blue's scene in the Pokemon Center with its three battles
  kecleon       06 Seven Island blocked spot with an Alomomola / a Noctowl lead
  azure_flute   06 Ritual Shrine keeper with var 0x40b7 = 4 / 3
  giovanni      07 Cerulean Cave rematch `TrainerBattle 402 402`: double battle, leads
  koga          07 Route 26 gate: Koga present by hour after the final Hall of Fame
`suite` runs SUITE_EXPECT (the cheap deterministic ones) and fails when a verdict changes.
"""
import datetime
import json
import struct
import sys
from pathlib import Path

import emu_harness as E
import emu_skitty as K

sys.path.insert(0, str(Path(__file__).resolve().parent / "docs"))

CLOCK = datetime.datetime(2026, 10, 9, 12)      # a Friday, noon
FAST_LEAD = 291                                 # Ninjask Lv100: always flees, always moves first


# ----------------------------------------------------------------------------- shared helpers
_STATIC = {}


def static():
    """romdata of the untouched CN ROM (scripts, events, trainers); cached per process."""
    if "rom" not in _STATIC:
        _STATIC["rom"] = K._rom(E.DEF_ROM_CN)
    return _STATIC["rom"]


def script_entries(file):
    import romdata as R
    return R.disasm(static()["scripts"][file])


def run_from(h, file, script_no, label, settle=30):
    """Start map script <script_no> of the current map (whose script file is <file>) and jump straight to
    byte offset <label> of that file: the script's own bytes run from there (emu_skitty's part-3 trick)."""
    start = script_entries(file)[0][script_no - 1]
    return h.run_script(script_id=script_no, program=K.goto_bytes(start, label), settle=settle)


def flags(h, ids):
    return {f: h.get_flag(f) for f in ids}


def lead(h, species, level=100, moves=None, pp=None):
    """Generator Pokemon made the party lead (old lead moves to its slot)."""
    mon = h.generate_pokemon(species, level=level)
    if moves:
        h.edit_party_mon(h.generated_slot, moves=moves, pp=pp)
    h.swap_party(0, h.generated_slot)
    return mon


PARTY_LIST = [((5, 197), (224, 208, 184)), ((250, 197), (224, 208, 184)), ((20, 362), (248, 248, 248))]
PARTY_SUBMENU = [((5, 197), (224, 208, 184)), ((20, 362), (56, 144, 224))]
SUBMENU_SHIFT = (128, 108)           # forced switch: the party Pokemon's submenu, 'shift' button


def _match(h, samples, tol=24):
    img = h.emu.screenshot().convert("RGB")
    return all(max(abs(a - b) for a, b in zip(img.getpixel(xy), rgb)) <= tol for xy, rgb in samples)


def weak_party(h):
    """Make every party Pokemon know only Splash (a data edit of the moves; HP, count and levels stay
    real), so the next battle is lost by fainting for real. (Lowering the party count or writing 0 HP made
    the battle offer fainted Pokemon and is not used.)"""
    for i in range(len(h.party())):
        h.edit_party_mon(i, moves=[150], pp=[40])


def set_party_hp(h, slot, hp):
    """Current HP of a party Pokemon: party extension +6 (u16), encrypted with the PID stream."""
    a = h.array(E.ARR_PARTY) + 8 + 236 * slot
    key = E._prng_stream(h.u32(a), 50)
    h.w16(a + 136 + 6, hp ^ key[3])


def doomed_party(h):
    """weak_party plus 1 HP on the lead and 0 HP on the others, so the first hit ends the battle (used for
    the wild Electrode, which can otherwise explode and lose the battle for itself)."""
    weak_party(h)
    for i in range(len(h.party())):
        set_party_hp(h, i, 1 if i == 0 else 0)


MEMENTO = 262


def memento_party(h):
    """A loss that no foe move can turn into a win: a Lv100 Ninjask lead (outspeeds everything the recipes
    meet) that knows only Memento, every other party Pokemon at 0 HP. Memento faints the user on turn 1
    before the foe acts, so the battle is lost whatever the battle RNG picks. (doomed_party leaves the foe
    one move first: a wild Electrode then picked Explosion often enough to turn the 'loss' into a win, the
    guide0107 'electrode' flake.)"""
    lead(h, FAST_LEAD, moves=[MEMENTO], pp=[10])
    for i in range(1, len(h.party())):
        set_party_hp(h, i, 0)


def lose_battle(h, max_steps=600):
    """Play the running battle to a loss: Splash at every command menu; on the forced-switch party list
    send out the next Pokemon (slots 1-5 in turn). Returns a trace of (in_field, map, pc) every 15 frames
    after the battle UI is gone, ending when the field is back or after 120 steps without it."""
    nxt, idle, trace = 1, 0, []
    for _ in range(max_steps):
        h.step(15)
        if h.in_field():
            trace.append((True, h.position()[0], h.reg.pc))
            return trace
        if h.on_screen("battle_menu"):
            h.touch(*E.BATTLE_BUTTONS["fight"], frames=10, after=40)
            h.touch(*E.MOVE_BUTTONS[0], frames=10, after=60)
            for xy in TARGETS:                       # double battles: confirm a target
                if h.on_screen("battle_menu") or h.in_field():
                    break
                h.touch(*xy, frames=10, after=40)
            idle = 0
        elif _match(h, PARTY_LIST):
            h.touch(*E.PARTY_SLOTS[nxt], frames=10, after=60)
            if _match(h, PARTY_SUBMENU):
                h.touch(*SUBMENU_SHIFT, frames=10, after=90)
                if _match(h, PARTY_SUBMENU):      # 'has no will to fight': back to the list, try the next
                    h.press("B", after=40)
                    h.press("B", after=40)
            nxt = nxt % 5 + 1
            idle = 0
        else:
            idle += 1
            if idle % 4 == 0:
                h.press("B", after=0)
            if idle > 40:
                trace.append((False, h.position()[0], h.reg.pc))
                if len(trace) > 120:
                    return trace
    return trace


TARGETS = ((64, 40), (192, 40), (64, 104), (192, 104))   # double battles: foe panels, then own side


def turn(h, max_frames=3000):
    """One command: FIGHT -> move 0 -> (double battles) touch a target panel: the first foe, then the
    user's own panel (moves such as Splash only allow that one); touches on a screen that has already moved
    on hit nothing. Then like battle_turn: B through messages until the command menu or the field."""
    if not h.wait_screen("battle_menu", 1500):
        raise RuntimeError("battle command menu not found")
    h.touch(*E.BATTLE_BUTTONS["fight"], frames=10, after=40)
    h.touch(*E.MOVE_BUTTONS[0], frames=10, after=60)
    for xy in TARGETS:
        if h.on_screen("battle_menu") or h.in_field():
            break
        h.touch(*xy, frames=10, after=40)
    nxt = 1
    for i in range(0, max_frames, 15):
        h.step(15)
        if h.in_field():
            h.step(60)
            return "field"
        if h.on_screen("battle_menu"):
            return "menu"
        if _match(h, PARTY_LIST):                 # a fainted Pokemon must be replaced
            h.touch(*E.PARTY_SLOTS[nxt], frames=10, after=60)
            if _match(h, PARTY_SUBMENU):
                h.touch(*SUBMENU_SHIFT, frames=10, after=60)
            nxt = nxt % 5 + 1
            continue
        if i % 60 == 45:
            h.press("B", after=0)
        if i % 600 == 585:                        # a message that B doesn't advance: A, then a tap
            h.press("A", after=20)
            h.touch(128, 96, frames=8, after=0)
    h.screenshot("turn_stuck")
    raise RuntimeError("turn did not finish")


def win_battle(h, max_turns=60):
    """Choose move 0 at every command menu until the battle is over (field back)."""
    for t in range(max_turns):
        if turn(h) == "field":
            return t + 1
        if t % 10 == 9:
            h.screenshot(f"win_battle_turn{t + 1}")
    raise RuntimeError("battle did not end")


def wait_idle(h, log, max_frames=3000):
    """Step until no message is open and the field has been quiet for a moment (script over)."""
    quiet = 0
    for _ in range(0, max_frames, 30):
        h.step(30)
        quiet = quiet + 1 if (log is None or log.msg is None) and h.in_field() else 0
        if quiet >= 4:
            return True
    return False


def safe_warp(h, map_id, x, y, direction=0, tries=12):
    """h.warp once the player has control again: after a white-out or a long scene the first A press may
    still go to a message (the nurse's lines use another command than NPCMsg); press B and retry."""
    for _ in range(tries):
        try:
            return h.warp(map_id, x, y, direction)
        except RuntimeError:
            for _ in range(3):
                h.press("B", after=60)
            h.step(120)
    return h.warp(map_id, x, y, direction)


def finish_scene(h, log, shots=None, tag="x", rounds=30, quiet=180):
    """Press through a running scene until no message has opened and nothing was logged for <quiet>
    frames while in the field (the script is over or waits for nothing)."""
    for _ in range(rounds):
        press_through(h, log, lambda h: log.msg is None and h.in_field(), shots, tag, max_iter=200)
        n = len(log.events)
        h.step(quiet)
        if log.msg is None and h.in_field() and len(log.events) == n:
            return True
    return False


def press_through(h, log, until, shots=None, tag="x", max_iter=300):
    """K.drive with a screenshot per page."""
    return K.drive(h, log, until, shots if shots is not None else [], tag, max_iter=max_iter)


def money(h):
    """Player money: PlayerProfile (save array 1) +0x18 u32 (after the id; checked against the trainer card)."""
    return h.u32(h.array(1) + 0x18)


def set_badge(h, n, on=True):
    """Badge n as CheckBadge sees it: PlayerProfile (array 1) +0x20 bits for 0-7 (the hack's Kanto gyms),
    +0x23 bits for 8-15 (found by probing with CheckBadge in the field)."""
    a = h.array(1) + (0x20 if n < 8 else 0x23)
    b = h.u8(a)
    h.w8(a, (b | 1 << n % 8) if on else (b & ~(1 << n % 8)))


def obj_at(h, map_id, oid):
    return K.live_objects(h, map_id).get(oid)


def out_dir(out, rom):
    d = Path(out) / "guide01_07" / K.lang_of(rom)
    d.mkdir(parents=True, exist_ok=True)
    return d


def mon_details(raw):
    """Decrypted fields of a 236-byte party Pokemon beyond decode_party_pokemon: OT id, IVs, moves, held
    item, OT name (raw u16 codes), level (Gen 4 layout: A +4 OT id; B +0 moves, +0x10 IV word; D +0
    OT name)."""
    m = E.decode_party_pokemon(raw)
    pid, flags_, checksum = struct.unpack_from("<IHH", raw, 0)
    words = struct.unpack_from("<64H", raw, 8)
    plain = list(words) if flags_ & 3 else [w ^ k for w, k in zip(words, E._prng_stream(checksum, 64))]
    data = struct.pack("<64H", *plain)
    order = E.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    blk = {n: data[32 * i:32 * i + 32] for i, n in enumerate(order)}
    iv = struct.unpack_from("<I", blk["B"], 0x10)[0]
    m.update(ot_id=struct.unpack_from("<I", blk["A"], 4)[0], moves=list(struct.unpack_from("<4H", blk["B"], 0)),
             ivs=[(iv >> (5 * k)) & 31 for k in range(6)], ot_name=list(struct.unpack_from("<8H", blk["D"], 0)))
    return m


def party_details(h):
    a = h.array(E.ARR_PARTY)
    return [mon_details(h.read(a + 8 + 236 * i, 236)) for i in range(h.u32(a + 4))]


def player_ot(h):
    """PlayerProfile (save array 1; observed: +4 name, 8 u16 with 0xFFFF end, +0x14 u32 trainer id)."""
    p = h.array(1)
    return {"ot_name": list(struct.unpack("<8H", h.read(p + 4, 16))), "ot_id": h.u32(p + 0x14)}


# ----------------------------------------------------------------------------- cases
def case_promo_flag(rom, out):
    """D-1333: Route 1 promoter (zone 9, object 0, file 168 script 4: CheckFlag 7286 @235, SetFlag 7286
    @1954). The flag byte is computed the way GetFlagAddr forms it (vars array + 0x2E0 + flag/8, no bound)
    and watched for writes; the save array table (save + 0x2E01C, rows {offset, crc, next id, next size})
    says which block holds it. The test save has done the scene, so the bit is cleared in RAM first (a fresh
    save's state). Then: talk (scene, Berry Juice), talk again (line 1 only), and log every read of that
    byte while the Pokedex and the trainer card are open."""
    FLAG = 7286
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK) as h:
        rows = [struct.unpack("<4I", h.read(h.save + E.SAVE_TABLE + 16 * i, 16)) for i in range(42)]
        size = {i + 1: rows[i][3] for i in range(41)}            # row i holds the size of array i + 1
        addr = h.array(E.ARR_VARS_FLAGS) + E.FLAGS_OFFSET + FLAG // 8
        rel = addr - (h.save + 0x10)
        owner = next(i for i in range(41) if rows[i][0] <= rel < rows[i][0] + size.get(i, 0x30))
        base = h.save + 0x10 + rows[owner][0]
        res = {"flag": FLAG, "bit": FLAG % 8, "save_offset": hex(rel), "owner_array": owner,
               "owner_offset": hex(rows[owner][0]), "owner_size": hex(size[owner]),
               "offset_in_owner": hex(rel - rows[owner][0]), "owner_magic": h.read(base, 4)[::-1].hex(),
               "flags_array_size": hex(size[E.ARR_VARS_FLAGS]), "byte_in_save": h.u8(addr)}
        h.w8(addr, h.u8(addr) & ~(1 << FLAG % 8))            # as on a save that hasn't met the promoter
        res["byte_before"] = h.u8(addr)
        writes = []
        h.emu.memory.register_write(addr, lambda a, s: writes.append(
            {"frame": h.frame, "pc": hex(h.reg.pc), "value_after": h.u8(addr)}), 1)
        h.warp(9, 1041, 335, E.DIRS["UP"])            # below the promoter (object 0, script 4, at 1041,334)
        h.step(30)
        bag0 = E.bag_items(h)
        log = K.SceneLog(h)
        shots = []
        h.press("A", after=10)
        press_through(h, log, lambda h: log.msg is None and h.get_flag(FLAG) and h.in_field(), shots,
                      tag=str(out / "promo"))
        wait_idle(h, log)
        res["byte_after"] = h.u8(addr)
        res["flag_after"] = h.get_flag(FLAG)
        res["writes"] = writes[:]
        res["msgs_first"] = log.msgs()
        res["bag_change"] = {k: v - bag0.get(k, 0) for k, v in E.bag_items(h).items() if v != bag0.get(k, 0)}
        n = len(log.events)
        h.warp(9, 1041, 335, E.DIRS["UP"])
        h.step(30)
        h.press("A", after=10)
        press_through(h, log, lambda h: log.msg is None and any(e["t"] == "close" for e in log.events[n:]), shots,
                      tag=str(out / "promo2"))
        wait_idle(h, log)
        res["msgs_second"] = [e["id"] for e in log.events[n:] if e["t"] == "msg"]
        # Who reads that byte? Hooks on the byte and its aligned word, plus a control: the word holding the
        # caught bit of species 1 (Pokedex + 4), which the Pokedex must read.
        reads = {"target": set(), "control": set()}
        h.emu.memory.register_write(addr, None, 1)
        mem = h.emu.memory
        for key, a_ in (("target", addr), ("target", addr & ~3), ("control", base + 4)):
            mem.register_read(a_, (lambda k: lambda a, s: reads[k].add(hex(h.reg.pc)))(key), 4 if a_ % 4 == 0 else 1)
        h.field_menu("pokedex")
        h.step(200)
        h.press("A", after=200)
        res["shot_dex"] = str(h.screenshot("promo_dex"))
        h.press("B", after=200)
        h.press("B", after=200)
        h.field_menu("card")
        h.step(100)
        res["shot_card"] = str(h.screenshot("promo_card"))
        h.press("B", after=200)
        for a_ in (addr, addr & ~3, base + 4):
            mem.register_read(a_, None, 4 if a_ % 4 == 0 else 1)
        res["reads_dex_card"] = {k: sorted(v) for k, v in reads.items()}
        # the Pokedex layout of the hack (emu_dex): seen bits at +0xCC, 200 bytes, bit = species - 1
        off = rel - rows[owner][0]
        if owner == 6 and 0xCC <= off < 0xCC + 200:
            res["meaning"] = {"array": "Pokedex seen bits", "species": (off - 0xCC) * 8 + FLAG % 8 + 1}
        res["shots"] = [s["path"] for s in shots]
        res["verdict"] = "observed"
    return res


def case_electrode(rom, out, variant):
    """01 Victory Road 1F (zone 124): file 109 script 9 = PlayCry; WildBattle Electrode; CheckBattleWon;
    win/flee -> SetFlag 1241, HidePerson 8; loss -> WhiteOut. Variant flee: a Lv100 Ninjask lead runs;
    variant lose: memento_party (the Ninjask uses Memento on turn 1, the rest are at 0 HP). The Electrode
    (Lv70: Explosion, Zap Cannon, Gyro Ball, Mirror Coat) never gets a move, so the loss does not depend on
    the battle RNG: with doomed_party it moved first, and an Explosion counted as a win (flag set, ball
    gone), which made the suite fail once under load."""
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK) as h:
        if variant == "flee":
            lead(h, FAST_LEAD)
        else:
            memento_party(h)
        h.warp(124, 21, 41, E.DIRS["UP"])
        h.step(60)
        objs = K.live_objects(h, 124)
        ball = next((o for o in objs.values() if o["script"] == 9), None)
        res = {"variant": variant, "ball_before": ball and (ball["x"], ball["z"]), "flag_1241_before": h.get_flag(1241)}
        log = K.SceneLog(h)
        wl = E.WildLog(h)
        h.press("A", after=10)
        h.run_until(lambda h: wl.rows, 1500, every=10)
        res["wild"] = [{k: r[k] for k in ("species", "form")} for r in wl.rows]
        h.step(200)
        res["shot_battle"] = str(h.screenshot(f"electrode_{variant}_battle"))
        if variant == "flee":
            res["fled"] = h.flee(battle_menu_wait=200)
        else:
            res["lost_trace_end"] = lose_battle(h)[-1][:2]
            finish_scene(h, log)
        h.step(200)
        res["map_after"] = h.position()[0]
        res["flag_1241_after"] = h.get_flag(1241)
        if variant == "lose":                        # back to the ball: is it still there?
            safe_warp(h, 124, 21, 41, E.DIRS["UP"])
            h.step(60)
        objs = K.live_objects(h, 124)
        ball = next((o for o in objs.values() if o["script"] == 9), None)
        res["ball_after"] = ball and (ball["x"], ball["z"])
        res["shot_after"] = str(h.screenshot(f"electrode_{variant}_after"))
    return res


def judge_electrode(res):
    f, l = res["flee"], res["lose"]
    ok = (f["wild"] and f["wild"][0]["species"] == 101 and f.get("fled") and f["flag_1241_after"]
          and f["ball_after"] is None and l["map_after"] != 124 and not l["flag_1241_after"] and l["ball_after"])
    return "confirmed" if ok else "contradicted"


def case_mortar_flag(rom, out):
    """D-1333, the other write (known issues; chapter 11 map): `SetFlag 4461` as the end of the Mt. Mortar
    expedition runs it (file 962 @1819), injected as a one-command script. Watch the byte GetFlagAddr forms,
    name the save array and offset, and log reads of it while the Pokedex and the trainer card are open."""
    FLAG = 4461
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK) as h:
        rows = [struct.unpack("<4I", h.read(h.save + E.SAVE_TABLE + 16 * i, 16)) for i in range(42)]
        size = {i + 1: rows[i][3] for i in range(41)}
        addr = h.array(E.ARR_VARS_FLAGS) + E.FLAGS_OFFSET + FLAG // 8
        rel = addr - (h.save + 0x10)
        owner = next(i for i in range(41) if rows[i][0] <= rel < rows[i][0] + size.get(i, 0x30))
        base = h.save + 0x10 + rows[owner][0]
        off = rel - rows[owner][0]
        res = {"flag": FLAG, "save_offset": hex(rel), "owner_array": owner, "offset_in_owner": hex(off),
               "owner_magic": h.read(base, 4)[::-1].hex(), "bit": FLAG % 8, "byte_before": h.u8(addr)}
        if owner == 6 and 4 <= off < 4 + 200:
            res["meaning"] = {"array": "Pokedex caught bits", "species": (off - 4) * 8 + FLAG % 8 + 1}
        writes = []
        h.emu.memory.register_write(addr, lambda a, s: writes.append({"pc": hex(h.reg.pc), "value": h.u8(addr)}), 1)
        h.run_script(program=E.script_bytes(("SetFlag", FLAG), ("End",)))
        h.step(30)
        h.emu.memory.register_write(addr, None, 1)
        res["writes"] = writes
        res["byte_after"] = h.u8(addr)
        reads = {"target": set(), "control": set()}
        mem = h.emu.memory
        for key, a_ in (("target", addr & ~3), ("control", base + 4)):
            mem.register_read(a_, (lambda k: lambda a, s: reads[k].add(hex(h.reg.pc)))(key), 4)
        h.field_menu("pokedex")
        h.step(200)
        h.press("A", after=200)
        res["shot_dex"] = str(h.screenshot("mortar_dex"))
        h.press("B", after=200)
        h.press("B", after=200)
        for a_ in (addr & ~3, base + 4):
            mem.register_read(a_, None, 4)
        res["reads_dex"] = {k: sorted(v) for k, v in reads.items()}
        res["verdict"] = "observed"
    return res


def case_pikachu(rom, out):
    """01 Viridian Pikachu thief (zone 50, object 5 = script 3, hide flag 1334, start 1033,247): talk from
    the south, answer Yes; the script ends with MovePersonFacing 5 -> (1008, 235) @4603. Then leave Viridian
    (warp to Route 1) and come back: where is object 5?"""
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK,
                    edit=lambda sf: sf.set_flag(1334, False)) as h:
        h.warp(50, 1033, 248, E.DIRS["UP"])
        h.step(60)
        o = obj_at(h, 50, 5)
        res = {"pikachu_start": o and (o["x"], o["z"])}
        if o is None:
            return {**res, "verdict": "blocked", "reason": "Pikachu (object 5) not shown"}
        log = K.SceneLog(h)
        shots = []
        h.press("A", after=10)
        press_through(h, log, lambda h: log.msg is None and h.in_field() and (obj_at(h, 50, 5) or {}).get("x") == 1008,
                      shots, tag=str(out / "pikachu"))
        wait_idle(h, log)
        o = obj_at(h, 50, 5)
        res["after_first_chase"] = o and (o["x"], o["z"])
        res["msgs"] = log.msgs()
        res["shot_moved"] = str(h.screenshot("pikachu_after_chase"))
        h.warp(9, 1041, 340, E.DIRS["UP"])           # leave Viridian (Route 1)
        h.step(60)
        h.warp(50, 1033, 250, E.DIRS["UP"])          # and come back
        h.step(90)
        o = obj_at(h, 50, 5)
        res["after_leaving"] = o and (o["x"], o["z"])
        res["flag_1334"] = h.get_flag(1334)
        res["shot_back"] = str(h.screenshot("pikachu_after_leaving"))
        res["verdict"] = ("confirmed" if res["after_first_chase"] == (1008, 235) and res["after_leaving"] == (1033, 247)
                          else "contradicted" if res["after_first_chase"] == (1008, 235) else "blocked")
    return res


def case_pidgeot(rom, out):
    """01 Viridian Forest (zone 147; woman = object 16, script 11; lent Pidgeot = object 38, hide flag 410).
    Pikachu starter (flag 1288). A generator Pidgeot Lv60 holding Leftovers with four set moves is lent
    through the game's party menu (L2225 -> L4827, ReturnLoanMon); then the final Hall of Fame flag 2404 is
    set and the woman returns 'your' Pidgeot (L4805 -> L5794 GiveLoanMon 6, 20, 75). The two are compared."""
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, flags=[1288, 410],
                    edit=lambda sf: sf.set_flag(2404, False)) as h:
        mon = h.generate_pokemon(18, level=60, item=234)
        h.edit_party_mon(h.generated_slot, moves=[19, 98, 17, 129], pp=[15, 30, 35, 20])
        slot = h.generated_slot
        lent = party_details(h)[slot]
        res = {"lent": {k: lent[k] for k in ("species", "level", "item", "moves", "ivs", "ot_id", "ot_name", "pid")},
               "player": player_ot(h), "party_count_before": len(party_details(h))}
        h.warp(147, 90, 73, E.DIRS["UP"])
        h.step(60)
        log = K.SceneLog(h)
        shots = []
        run_from(h, 115, 11, 2225)
        # msg 149 + Yes -> fade -> party menu
        press_through(h, log, lambda h: log.msg is None and not h.in_field(), shots, tag=str(out / "pidgeot_ask"),
                      max_iter=40)
        h.step(200)
        res["shot_party_menu"] = str(h.screenshot("pidgeot_party_menu"))
        h.touch(*E.PARTY_SLOTS[slot], frames=12, after=90)
        res["shot_party_pick"] = str(h.screenshot("pidgeot_party_pick"))
        h.touch(*E.PARTY_SUMMARY, frames=12, after=200)     # first entry of the submenu (select)
        press_through(h, log, lambda h: log.msg is None and h.in_field() and not h.get_flag(410), shots,
                      tag=str(out / "pidgeot_lend"), max_iter=80)
        wait_idle(h, log)
        res["party_after_lend"] = [m["species"] for m in party_details(h)]
        res["flag_410_after_lend"] = h.get_flag(410)
        res["msgs_lend"] = log.msgs()
        h.set_flag(2404)
        n = len(log.events)
        run_from(h, 115, 11, 2225)
        press_through(h, log, lambda h: log.msg is None and h.in_field() and h.get_flag(410), shots,
                      tag=str(out / "pidgeot_return"), max_iter=80)
        wait_idle(h, log)
        party = party_details(h)
        res["msgs_return"] = [e["id"] for e in log.events[n:] if e["t"] == "msg"]
        got = party[-1]
        res["returned"] = {k: got[k] for k in ("species", "level", "item", "moves", "ivs", "ot_id", "ot_name", "pid")}
        res["party_after_return"] = [m["species"] for m in party]
        h.field_menu("pokemon")                      # summary of the returned Pidgeot (OT / ID No.)
        h.touch(*E.PARTY_SLOTS[len(party) - 1], frames=12, after=60)
        h.touch(*E.PARTY_SUMMARY, frames=12, after=200)
        res["shot_summary"] = str(h.screenshot("pidgeot_returned_summary"))
        h.press("RIGHT", after=120)
        res["shot_summary2"] = str(h.screenshot("pidgeot_returned_summary2"))
        res["shots"] = [x["path"] for x in shots]
        lent_gone = 18 not in res["party_after_lend"][:] or len(res["party_after_lend"]) < res["party_count_before"]
        r = res["returned"]
        fixed = (r["species"] == 18 and r["level"] == 20 and r["ivs"] == [31] * 6
                 and r["pid"] != lent["pid"] and r["item"] != 234)
        res["ot_is_player"] = r["ot_id"] == res["player"]["ot_id"]
        res["verdict"] = ("confirmed" if lent_gone and fixed and res["ot_is_player"] else
                          "contradicted" if lent_gone else "blocked")
    return res


def case_mom_visit(rom, out, variant):
    """01 Yellow's third date ("I want you to meet my mom"): file 739 L10063 warps to zone 504 (Pallet Town
    house) and sets var 0x40b5 = 5; the zone's scene table (level script 511: 0x40b5 == 5 -> script 4) runs
    file 736 script 4, which checks flag 106 first (-> L559, Cynthia's version) before Yellow's flag 2143.
    State: Yellow is the partner (2261 final Hall of Fame, 1645 confessed, 2143 clear = Yellow not locked
    out; the other partners locked out: 2141, 2142, 2144, 2154 set), var 0x40b5 = 4. Run 1: flag 106 as
    in the save (set with the starter). Run 2 (control): 106 cleared."""
    tag = variant
    f106 = None if variant == "as_saved" else False
    if True:
        def edit(sf):
            for f in (2261, 1645, 2141, 2142, 2144, 2154):
                sf.set_flag(f)
            sf.set_flag(2143, False)
            sf.set_var(0x40B5, 4)
            if f106 is not None:
                sf.set_flag(106, f106)
        with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, edit=edit) as h:
            r = {"flag_106": h.get_flag(106)}
            h.warp(50, 1041, 262, E.DIRS["UP"])          # Viridian, next to Yellow's spot
            h.step(30)
            log = K.SceneLog(h)
            shots = []
            run_from(h, 739, 40, 10063)
            press_through(h, log, lambda h: h.get_var(0x40B5) == 6 and log.msg is None and h.in_field(), shots,
                          tag=str(out / f"mom_{tag}"), max_iter=250)
            wait_idle(h, log)
            r["msgs"] = log.msgs()
            r["var_40b5"] = h.get_var(0x40B5)
            r["position"] = h.position()
            objs = K.live_objects(h, 504)
            r["partner_objects_shown"] = {o["id"]: o["sprite"] for o in objs.values() if 4 <= o["id"] <= 7}
            r["shots"] = [x["path"] for x in shots]
            r["shot_end"] = str(h.screenshot(f"mom_{tag}_end"))
    return r


def judge_mom_visit(res):
    a, b = res["as_saved"], res["flag106_clear"]
    return ("confirmed" if a["flag_106"] and 58 in a["msgs"] and 58 not in b["msgs"] else
            "contradicted" if a["msgs"] else "blocked")


def case_living(rom, out, variant):
    """01 "Living together": the 2F PC (zone 64, bg event at 6,3 = file 843 script 1): with the Cascade
    Badge and var 0x40b5 = 6 it goes to L363, where flag 106 (always set) jumps to L4292 End before any
    partner branch. Observed: messages, var, and whether the player can still walk afterwards (the script
    ends after LockAll without ReleaseAll). Control: flag 106 cleared (Yellow as partner)."""
    tag = variant
    f106 = None if variant == "as_saved" else False
    if True:
        def edit(sf):
            for f in (2261, 1645, 2141, 2142, 2144, 2154):
                sf.set_flag(f)
            sf.set_flag(2143, False)
            sf.set_var(0x40B5, 6)
            if f106 is not None:
                sf.set_flag(106, f106)
        with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, edit=edit) as h:
            r = {"flag_106": h.get_flag(106)}
            set_badge(h, 1)                               # the PC's CheckBadge 1 (else 'Internet spotty')
            h.warp(64, 6, 4, E.DIRS["UP"])
            h.step(60)
            log = K.SceneLog(h)
            shots = []
            h.press("A", after=10)
            press_through(h, log, lambda h: log.msg is None and h.frame > 0 and len(log.events) > 0
                          and log.events[-1]["t"] == "close", shots, tag=str(out / f"living_{tag}"), max_iter=60)
            h.step(200)
            r["msgs"] = log.msgs()
            r["var_40b5"] = h.get_var(0x40B5)
            before = h.position()
            moved = h.step_dir("DOWN") or h.step_dir("DOWN")
            r["can_walk_after"] = moved
            r["position_before_after"] = [before, h.position()]
            r["shots"] = [x["path"] for x in shots]
            r["shot_end"] = str(h.screenshot(f"living_{tag}_end"))
    return r


def judge_living(res):
    a, b = res["as_saved"], res["flag106_clear"]
    return ("confirmed" if a["flag_106"] and not a["msgs"] and a["var_40b5"] == 6 and b["msgs"] else
            "contradicted" if a["msgs"] else "blocked")


def case_misty_date(rom, out):
    """02/04 Misty's Resort Zone date, won: the date's end (file 809 script 15 from L4312: fade, Warp 427
    = Cerulean Gym, var 0x40b5 = 4) run with the state the date leaves (hide flag 595 set at its start by
    758 @7636; Misty is the partner: 2261, 1645 set, 2142 clear). Then: is Misty (Gym object 6, flag 595)
    in the Gym, after re-entering it, and is the Cape Misty (Route 25 object 35, flag 598) there?"""
    def edit(sf):
        for f in (2261, 1645, 595):
            sf.set_flag(f)
        sf.set_flag(2142, False)
        sf.set_var(0x40B5, 3)
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, edit=edit) as h:
        h.warp(479, 8, 21, E.DIRS["UP"])
        h.step(30)
        run_from(h, 809, 15, 4312)
        h.run_until(lambda h: h.get_var(0x40B5) == 4, 1500, every=10)
        h.step(200)
        res = {"position_after_date": h.position(), "var_40b5": h.get_var(0x40B5), "flag_595": h.get_flag(595),
               "misty_in_gym": obj_at(h, 427, 6) is not None,
               "shot_gym": str(h.screenshot("misty_gym_after_date"))}
        h.warp(427, 10, 20, E.DIRS["UP"])            # walk in again (fresh map entry, map scripts run)
        h.step(200)
        res["misty_in_gym_reentered"] = obj_at(h, 427, 6) is not None
        res["misty_sprites_in_gym"] = [{k: o[k] for k in ("id", "script", "x", "z")}      # sprite 370 = Misty
                                       for o in K.live_objects(h, 427).values() if o["sprite"] == 370]
        res["flag_595_reentered"] = h.get_flag(595)
        res["shot_gym2"] = str(h.screenshot("misty_gym_reentered"))
        h.warp(29, 1422, 42, E.DIRS["UP"])
        h.step(200)
        res["misty_at_cape"] = obj_at(h, 29, 35) is not None
        res["flag_598"] = h.get_flag(598)
        res["shot_cape"] = str(h.screenshot("misty_cape"))
        missing = not (res["misty_in_gym"] or res["misty_in_gym_reentered"] or res["misty_at_cape"])
        res["verdict"] = "confirmed" if res["var_40b5"] == 4 and missing else (
            "contradicted" if res["var_40b5"] == 4 else "blocked")
    return res


MONDAY_HOURS = ("0", "6", "7", "12", "18", "19", "23")


def case_monday(rom, out, variant):
    """04 Pal Park on a Monday: the receptionist's Monday branch (file 809 L6143: ScrCmd_522 compared with
    7..18 -> L6679 clears hide flags 2124 + 2127 (groups A, D), else 2128 + 2131 (E, H)) run with the clock
    pinned to Monday 2026-10-05 <variant>:00 and all eight group flags set; read which two were cleared at
    the fee question (msg 46), then answer No. Also logs what ScrCmd_522 returns (var 0x4000)."""
    hour = int(variant)
    clock = datetime.datetime(2026, 10, 5, hour, 30)
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=clock, flags=range(2124, 2132)) as h:
        h.warp(479, 8, 21, E.DIRS["UP"])
        h.step(30)
        log = K.SceneLog(h)
        run_from(h, 809, 1, 6143)
        h.run_until(lambda h: log.msg == 46, 1200, every=10)
        h.step(120)
        cleared = [f for f in range(2124, 2132) if not h.get_flag(f)]
        res = {"clock": h.clock(), "scrcmd_522": h.get_var(0x4000), "cleared": cleared,
               "groups": "".join("ABCDEFGH"[f - 2124] for f in cleared), "msg": log.msg,
               "shot": str(h.screenshot(f"monday_{hour:02d}"))}
        h.press("DOWN", after=20)
        h.press("A", after=60)
        press_through(h, log, lambda h: log.msg is None and h.in_field(), [], tag=str(out / "monday"), max_iter=20)
    return res


def judge_monday(res):
    want = {h: ("AD" if 7 <= int(h) <= 18 else "EH") for h in MONDAY_HOURS}
    ok = all(res[h]["groups"] == want[h] and res[h]["scrcmd_522"] == int(h) for h in MONDAY_HOURS)
    return "confirmed" if ok else "contradicted"


def case_azure_flute(rom, out, variant):
    """06 Ritual Shrine keeper (zone 289, object 3 = file 942 script 4): var 0x40b7 >= 4 -> L252 'keep the
    flute safe' before the final-Hall-of-Fame check (2261 -> L263 offer, Yes -> L516 gives item 536).
    Variant var4: 0x40b7 = 4 (set by the League HQ report, file 31 @3316) and 2261 set; var3: the value
    the Arceus scene leaves (file 49 @5260) with 2261 set (control). Pilgrimage done (2137; without it the
    map script moves the keeper to the entrance, 942 script 1 -> L226)."""
    val = int(variant[-1])
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, flags=[2261, 2137], vars={0x40B7: val}) as h:
        h.warp(289, 16, 8, E.DIRS["UP"])
        h.step(60)
        keeper = obj_at(h, 289, 3)                   # the map script may move it (MovePersonFacing 3 @226)
        h.warp(289, keeper["x"], keeper["z"] + 1, E.DIRS["UP"])
        h.step(60)
        bag0 = E.bag_items(h)
        log = K.SceneLog(h)
        shots = []
        h.press("A", after=10)
        press_through(h, log, lambda h: log.msg is None and h.in_field() and any(e["t"] == "close" for e in log.events),
                      shots, tag=str(out / f"flute_{variant}"), max_iter=60)
        wait_idle(h, log)
        return {"keeper": (keeper["x"], keeper["z"]), "msgs": log.msgs(), "var_40b7": h.get_var(0x40B7),
                "bag_change": {k: v - bag0.get(k, 0) for k, v in E.bag_items(h).items() if v != bag0.get(k, 0)},
                "shots": [x["path"] for x in shots]}


def judge_azure_flute(res):
    a, b = res["var4"], res["var3"]
    no_flute = a["msgs"][:1] == [47] and "536" not in map(str, a["bag_change"])
    control = 45 in b["msgs"] and "536" in map(str, b["bag_change"])
    return "confirmed" if no_flute and control else "contradicted" if control else "blocked"


KOGA_HOURS = ("17", "18", "20", "21")


def case_koga(rom, out, variant):
    """07 League reception gate (zone 299): after the final Hall of Fame (2261) the map-load script (file
    213 L523) leaves Koga (object 12, hide flag 624, at 17,10) visible only when ScrCmd_522 (the hour) is
    18, 19 or 20. Clock pinned per variant; at 18:00 Koga is also talked to (script 16, photo offer)."""
    hour = int(variant)
    clock = datetime.datetime(2026, 10, 9, hour, 0)
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=clock, flags=[2261]) as h:
        h.warp(299, 11, 20, E.DIRS["UP"])
        h.step(120)
        o = obj_at(h, 299, 12)
        res = {"hour": hour, "koga_visible": o is not None, "koga_pos": o and (o["x"], o["z"]),
               "flag_624": h.get_flag(624), "warps": "east door 21,8 -> zone 27; west door 1,8 -> zone 32",
               "shot": str(h.screenshot(f"koga_{hour:02d}"))}
        if o is not None and hour == 18:
            h.warp(299, o["x"], o["z"] + 1, E.DIRS["UP"])
            h.step(60)
            log = K.SceneLog(h)
            h.press("A", after=10)
            h.run_until(lambda h: log.msg is not None, 600, every=10)
            h.step(150)
            res["talk_msg"] = log.msg
            res["shot_talk"] = str(h.screenshot("koga_talk"))
            h.press("DOWN", after=20)
            h.press("A", after=120)
            press_through(h, log, lambda h: log.msg is None and h.in_field(), [], tag=str(out / "koga"), max_iter=20)
    return res


def judge_koga(res):
    vis = {h: res[h]["koga_visible"] for h in KOGA_HOURS}
    ok = vis == {"17": False, "18": True, "20": True, "21": False} and list(res["18"]["koga_pos"]) == [17, 10] \
        and res["18"].get("talk_msg") == 12
    return "confirmed" if ok else "contradicted"


def case_giovanni(rom, out):
    """07 Cerulean Cave rematch: file 912 L2559 `TrainerBattle 402 402 0 0`, run with the same command.
    Observed: the cries of the opponent's send-outs (cry routine hook), the opposing Party structs in RAM
    (one copy of the team or two), and the battle intro screenshots."""
    import romdata as R
    td = R.parse_trdata(static()["trdata"][402])
    team = [m["species"] for m in R.parse_trpoke(static()["trpoke"][402], td["count"])]
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK) as h:
        log = K.SceneLog(h)
        mine = [m["species"] for m in h.party()]
        h.run_script(program=E.script_bytes(("LockAll",), ("TrainerBattle", 402, 402, 0, 0), ("ReleaseAll",),
                                            ("End",)))
        shots = []
        for k in range(10):
            h.step(90)
            shots.append(str(h.screenshot(f"giovanni_intro_{k}")))
        cries = [e["species"] for e in log.events if e["t"] == "cry"]
        parties = [[m["species"] for m in p["mons"]] for p in K.find_parties(h)]
        res = {"rom_team": team, "player_party": mine, "cries": cries, "parties_in_ram": parties,
               "copies_of_team": sum(p == team for p in parties), "shots": shots}
        foe = [c for c in cries if c not in mine]
        res["foe_sendout_cries"] = foe
        res["verdict"] = ("confirmed" if foe[:2] == team[:2] and res["copies_of_team"] >= 1 else
                          "contradicted" if foe else "blocked")
    return res


def case_kecleon(rom, out, variant):
    """06 Seven Island blocked spot (zone 163, object 16 = file 870 script 12, hide flag 2198; flag 2197 set
    by the tourist): L1038 GetPartyLeadAlive + species == 594 (Alomomola) -> L1500 (PlayCry 164 Noctowl,
    'Nooo-tow!', then the Kecleon). Variant = lead species: 594 Alomomola, 164 Noctowl. Generator Lv50."""
    species = int(variant)
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, flags=[2197],
                    edit=lambda sf: sf.set_flag(2198, False)) as h:
        lead(h, species, level=50)
        h.warp(163, 245, 104, E.DIRS["UP"])
        h.step(60)
        o = obj_at(h, 163, 16)
        log = K.SceneLog(h)
        wl = E.WildLog(h)
        shots = []
        h.press("A", after=10)
        press_through(h, log, lambda h: bool(wl.rows) or (log.msg is None and h.in_field() and
                      any(e["t"] == "close" for e in log.events)), shots, tag=str(out / f"kecleon_{species}"),
                      max_iter=80)
        h.step(300)
        res = {"lead": species, "object": o and (o["x"], o["z"]), "msgs": log.msgs(),
               "script_cries": log.cries(), "wild": [{k: r[k] for k in ("species", "form")} for r in wl.rows],
               "shots": [x["path"] for x in shots], "shot_end": str(h.screenshot(f"kecleon_{species}_end"))}
        if wl.rows:
            res["fled"] = h.flee(battle_menu_wait=200)
    return res


def judge_kecleon(res):
    a, n = res["594"], res["164"]
    ok = (a["wild"] and a["wild"][0]["species"] == 352 and 164 in a["script_cries"] and 34 in a["msgs"]
          and not n["wild"] and 34 not in n["msgs"])
    return "confirmed" if ok else "contradicted"


def case_corner_kid(rom, out, variant):
    """03 Rock Tunnel hide-and-seek (zone 342): the corner kid (object 17 = file 129 script 18, flag 1966
    clear) battles with `TrainerBattle 606 0 0 0` (third argument 0: a loss is not allowed); on a loss the
    script goes on at L3782 (NPCMsg 46, the 'Pikachu' kid's line) instead of WhiteOut. Lost with a party
    that only knows Splash (weak_party). Variants: real (talk to the kid); controls
    with the same trainer from an injected script: canlose (`TrainerBattle 606 0 1 0`, as Giovanni's
    L4818) and whiteout (`TrainerBattle 606 0 0 0; WhiteOut`, as the hack's other trainer scripts)."""
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK,
                    edit=lambda sf: (sf.set_flag(1966, False), sf.set_flag(1554, False))) as h:
        weak_party(h)
        h.warp(342, 43, 99, E.DIRS["UP"])
        h.step(60)
        log = K.SceneLog(h)
        h.set_var(E.SENTINEL_VAR, 0)
        if variant == "real":
            h.press("A", after=10)
            press_through(h, log, lambda h: log.battle, [], tag=str(out / "corner_before"), max_iter=40)
        else:
            tail = [("WhiteOut",)] if variant == "whiteout" else []
            h.run_script(program=E.script_bytes(("LockAll",), ("TrainerBattle", 606, 0, 1 if variant == "canlose" else 0, 0),
                                                ("SetVar", E.SENTINEL_VAR, 0x5A5A), *tail, ("ReleaseAll",), ("End",)))
        h.step(300)
        res = {"variant": variant, "battle_started": h.wait_screen("battle_menu", 1500)}
        trace = lose_battle(h)
        res["field_back"] = trace[-1][0]
        res["map_after"] = trace[-1][1]
        res["pc_after"] = hex(trace[-1][2])
        res["pc_in_heap"] = 0x02200000 <= trace[-1][2] < 0x02400000 and not res["field_back"]
        res["script_went_on"] = h.get_var(E.SENTINEL_VAR) == 0x5A5A
        res["msgs_after_battle"] = [e["id"] for e in log.events if e["t"] == "msg" and e["frame"] > 0][1:] \
            if variant == "real" else log.msgs()
        res["flag_1966"] = h.get_flag(1966)
        res["shot"] = str(h.screenshot(f"corner_{variant}_after_loss"))
    return res


def judge_corner_kid(res):
    r, c, w = res["real"], res["canlose"], res["whiteout"]
    controls_ok = c["field_back"] and c["map_after"] == 342 and w["field_back"] and w["map_after"] != 342
    if not controls_ok:
        return "blocked"
    return "contradicted" if not r["field_back"] else "confirmed"


def case_sabrina(rom, out, variant):
    """03 Pokemon Tower top (zone 155): Sabrina (object 38, file 17 script 23, hide flag 1100) with badge 6
    and the task not yet active (1504 clear) goes to L3237: var 0x40AF == 0 -> L5532 (line 53#210, 'deep
    in her training'), else line 149 (the task offer). Variants: var 0 (as after the S.S. Anne hijack
    ending, file 156 @6600 = the only script that writes 0) and var 5."""
    val = int(variant[-1])
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, vars={0x40AF: val},
                    edit=lambda sf: (sf.set_flag(1100, False), sf.set_flag(1504, False))) as h:
        set_badge(h, 6)
        h.warp(155, 45, 35, E.DIRS["UP"])
        h.step(60)
        log = K.SceneLog(h)
        h.run_script(script_id=23, settle=10)        # Sabrina's own script (an object with script 0 is in front)
        h.run_until(lambda h: log.msg is not None, 600, every=10)
        h.step(120)
        res = {"var_40af": val, "first_msg": log.msg, "shot": str(h.screenshot(f"sabrina_var{val}"))}
        h.press("B", after=60)
        press_through(h, log, lambda h: log.msg is None and h.in_field(), [], tag=str(out / "sabrina"), max_iter=20)
    return res


def judge_sabrina(res):
    return "confirmed" if res["var0"]["first_msg"] == 210 and res["var5"]["first_msg"] == 149 else "contradicted"


def case_ssanne(rom, out, variant):
    """03 S.S. Anne before the party. Board for real at Vermilion Harbor (zone 387: the sailor, object 0 at
    23,19, file 155 script 1, without badge 4 and flag 235, boards with ScrCmd_723 -> zone 307), wait for the
    arrival scene (scene var 0x40DC), walk onto the Captain's speech trigger (coord script 5 at 22,14).
    Then read flag 1440, which Blue's free Shoal Salt (file 156 script 22) and the Captain's HM01 (file 157
    script 5) both need, talk to the Captain (zone 308, object 0; hide flag 1092 cleared) and to Blue (cook's
    request 1422 set, under $6000, no Shoal Salt). Variant 'as_boarded': 1440 as the game leaves it (a real
    new game also has it clear); 'flag1440': 1440 set after the speech (control: what both scripts need)."""
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK,
                    edit=lambda sf: (sf.set_flag(1092, False), sf.set_flag(1424, False), sf.set_flag(1439, False),
                                     sf.set_flag(235, False))) as h:
        res = {"variant": variant, "flag_1440_before": h.get_flag(1440), "money": money(h)}
        log = K.SceneLog(h)
        shots = []
        h.warp(387, 24, 19, E.DIRS["LEFT"])
        h.step(60)
        h.press("A", after=10)
        for _ in range(12):                    # boarding, ScrCmd_723, the arrival scene (position() lags here)
            h.step(100)
            if log.msg is not None:
                h.press("A", after=10)
        res["arrival_scene_var_40dc"] = h.get_var(0x40DC)
        for d, n in (("LEFT", 2), ("UP", 1)):   # (24,15) -> the speech trigger at (22,14)
            h.walk(d, n)
            h.step(30)
        press_through(h, log, lambda h: log.msg is None and h.in_field() and h.get_var(0x40AF) == 1, shots,
                      tag=str(out / f"ssanne_{variant}_board"), max_iter=120)
        wait_idle(h, log)
        res["boarding_msgs"] = log.msgs()
        res["flag_1440_after_boarding"] = h.get_flag(1440)
        res["party_guests_visible"] = sorted(o["id"] for o in K.live_objects(h, 307).values() if o["flag"] == 1440)
        res["shot_hall"] = str(h.screenshot(f"ssanne_{variant}_hall"))
        if variant == "flag1440":
            h.set_flag(1440)
        bag0 = E.bag_items(h)
        n = len(log.events)
        h.warp(308, 9, 5, E.DIRS["UP"])
        h.step(60)
        h.run_script(script_id=5, settle=10)
        press_through(h, log, lambda h: log.msg is None and h.in_field() and any(e["t"] == "close" for e in log.events[n:]),
                      shots, tag=str(out / f"ssanne_{variant}_captain"), max_iter=60)
        wait_idle(h, log)
        res["captain_msgs"] = [e["id"] for e in log.events[n:] if e["t"] == "msg"]
        res["captain_gave"] = {k: v - bag0.get(k, 0) for k, v in E.bag_items(h).items() if v != bag0.get(k, 0)}
        h.set_flag(1422)
        bag1 = E.bag_items(h)
        n = len(log.events)
        h.warp(307, 6, 10, E.DIRS["UP"])
        h.step(60)
        h.run_script(script_id=22, settle=10)
        press_through(h, log, lambda h: log.msg is None and h.in_field() and any(e["t"] == "close" for e in log.events[n:]),
                      shots, tag=str(out / f"ssanne_{variant}_blue"), max_iter=60)
        wait_idle(h, log)
        res["blue_msgs"] = [e["id"] for e in log.events[n:] if e["t"] == "msg"]
        res["blue_gave"] = {k: v - bag1.get(k, 0) for k, v in E.bag_items(h).items() if v != bag1.get(k, 0)}
        res["shots"] = [x["path"] for x in shots]
    return res


def judge_ssanne(res):
    a, c = res["as_boarded"], res["flag1440"]
    # the full-bag test save already holds HM01 and Shoal Salt, so the gifts are read from the lines:
    # Captain 58 'please take this' (+ std 'obtained'), Blue 48 'take it if you need it'
    same_gate = (58 not in a["captain_msgs"] and 48 not in a["blue_msgs"]
                 and 58 in c["captain_msgs"] and 48 in c["blue_msgs"])
    return "confirmed" if same_gate else "contradicted"


CLASH_FLAGS = (1064, 1065, 2141, 2153, 692, 1058)
ASKED_AROUND = (1997, 1404, 1996, 1995, 1059, 1060)   # the six 'asked around town' flags the partners check


def case_clash(rom, out, variant):
    """03 Vermilion clash. 'start': the state right after siding with the law through Blue (file 777 L614:
    1064 + 2141 set, 1065 clear; L677: 692 clear, 1058 set, var 0x40A4 = 1), step onto the coord trigger
    (1297,295; var 0x40A4 == 1) -> file 774 script 14 -> L2623; read the side and romance flags when the
    first battle has started. 'rechoose': the flags as observed at that point (what the loss's WhiteOut,
    L6321, leaves), then talk to Green/Red in the Pokemon Center (zone 358, object 15 = file 777 script 11)
    and answer Yes (townsfolk side): which flags are set afterwards."""
    if variant == "start":
        on, off, var = (1064, 2141, 1058) + ASKED_AROUND, (1065, 2153, 692), 1
    else:
        on, off, var = (2141, 692) + ASKED_AROUND, (1064, 1065, 2153, 1058), 0
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, flags=on, vars={0x40A4: var},
                    edit=lambda sf: [sf.set_flag(f, False) for f in off]) as h:
        log = K.SceneLog(h)
        shots = []
        res = {"variant": variant, "flags_before": flags(h, CLASH_FLAGS)}
        if variant == "start":
            h.warp(54, 1297, 296, E.DIRS["UP"])
            h.step(60)
            h.walk("UP", 1)
            press_through(h, log, lambda h: not h.in_field(), shots, tag=str(out / "clash_start"), max_iter=300)
            h.step(300)
            res["flags_at_first_battle"] = flags(h, CLASH_FLAGS)
            res["var_40a4"] = h.get_var(0x40A4)
            res["shot_battle"] = str(h.screenshot("clash_first_battle"))
        else:
            h.warp(358, 3, 16, E.DIRS["UP"])
            h.step(60)
            h.run_script(script_id=11, settle=10)
            press_through(h, log, lambda h: log.msg is None and h.in_field() and h.get_flag(1065), shots,
                          tag=str(out / "clash_rechoose"), max_iter=120)
            wait_idle(h, log)
            res["flags_after_green"] = flags(h, CLASH_FLAGS)
            res["var_40a4"] = h.get_var(0x40A4)
        res["msgs"] = log.msgs()
        res["shots"] = [x["path"] for x in shots]
    return res


def judge_clash(res):
    st, rc = res["start"], res["rechoose"]
    fb = {int(k): v for k, v in st.get("flags_at_first_battle", {}).items()}
    fa = {int(k): v for k, v in rc.get("flags_after_green", {}).items()}
    reset = fb and not fb[1064] and not fb[1065] and fb[2141]
    both_locked = fa and fa[1065] and fa[2153] and fa[2141]
    return "confirmed" if reset and both_locked else "contradicted"


def case_tony(rom, out, variant):
    """04 Celadon Department Store roof before the Route 7 scene: var 0x40d0 at its start value 0, flag
    1535 clear (no Route 7 scene, no free massage), Tony/Mary shown (1544/1545 clear).
    'scene': ask Suzie (zone 376, object 0 = file 794 script 1) which offer she makes, walk onto the roof
    trigger (zone 375, coord 4,5 = file 792 script 21), win the Beedrill (trainer 462) with a Lv100 Mewtwo
    and stop when Jessie & James's battle (460 + 461) starts: is the quest var already 2 (@1530)?
    'suzie': the state the scene leaves at that point (0x40d0 = 2, 1544/1545 set, 1535 clear): her offer."""
    if variant == "scene":
        vars_, on, off = {0x40D0: 0}, (), (1535, 1544, 1545)
    else:
        vars_, on, off = {0x40D0: 2}, (1544, 1545), (1535,)
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, vars=vars_, flags=on,
                    edit=lambda sf: [sf.set_flag(f, False) for f in off]) as h:
        lead(h, 150, moves=[94, 0, 0, 0], pp=[40, 0, 0, 0])   # Mewtwo Lv100, Psychic
        log = K.SceneLog(h)
        shots = []
        res = {"variant": variant}

        def ask_suzie(tag):
            safe_warp(h, 376, 10, 6, E.DIRS["UP"])
            h.step(60)
            h.run_script(script_id=1, settle=10)
            h.run_until(lambda h: log.msg is not None, 600, every=10)
            h.step(120)
            first = log.msg
            shots.append({"path": str(h.screenshot(f"tony_suzie_{tag}"))})
            for _ in range(12):                          # B pages on, and answers 'No' to the offer
                h.press("B", after=60)
                if log.msg is None and h.in_field():
                    break
            wait_idle(h, log)
            return first
        if variant == "scene":
            res["suzie_before"] = ask_suzie("before")
            safe_warp(h, 375, 4, 6, E.DIRS["UP"])
            h.step(60)
            h.walk("UP", 1)
            nb = lambda: len([e for e in log.events if e["t"] == "trainer_battle"])
            press_through(h, log, lambda h: nb() >= 1, shots, tag=str(out / "tony_scene"), max_iter=200)
            h.step(200)
            res["beedrill_turns"] = win_battle(h)        # trainer 462
            press_through(h, log, lambda h: nb() >= 2, shots, tag=str(out / "tony_scene"), max_iter=200)
            res["var_40d0_at_jj_battle"] = h.get_var(0x40D0)
            res["flags_at_jj_battle"] = flags(h, (1535, 1544, 1545))
            res["trainer_battles"] = [e["trainers"] for e in log.events if e["t"] == "trainer_battle"]
            res["scene_msgs"] = log.msgs()
            h.step(300)
            res["shot_jj"] = str(h.screenshot("tony_jj_battle"))
        else:
            res["suzie"] = ask_suzie("after_scene_state")
        res["shots"] = [x["path"] for x in shots]
    return res


def judge_tony(res):
    a, b = res["scene"], res["suzie"]
    played = [462, 0] in a.get("trainer_battles", []) and [460, 461] in a.get("trainer_battles", [])
    ok = played and a.get("suzie_before") == 0 and a.get("var_40d0_at_jj_battle") == 2 and b.get("suzie") == 36
    return "confirmed" if ok else ("contradicted" if played else "blocked")


def case_blue_saffron(rom, out):
    """04 Saffron takeover, step 5: Blue's scene in the Saffron Pokemon Center (zone 407, coord script 5 at
    8,18, file 827, bank a027/0524 lines 20-44). Run from the trigger tile with a Lv100 Mewtwo (Surf) lead;
    the scene's battles (TrainerBattle 414, MultiBattle 385+416+613, MultiBattle 385+614+615, Blue = 385)
    are won by pressing move 0. Logged: every message id, the battles, the end state."""
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK) as h:
        lead(h, 150, moves=[94, 0, 0, 0], pp=[40, 0, 0, 0])   # Mewtwo Lv100, Psychic only (the foes are Poison)
        log = K.SceneLog(h)
        shots = []
        h.warp(407, 8, 18, E.DIRS["UP"])
        h.step(60)
        h.run_script(script_id=5, settle=10)
        battles = 0
        for _ in range(4):
            press_through(h, log, lambda h: not h.in_field() or 44 in log.msgs(), shots,
                          tag=str(out / "blue_saffron"), max_iter=300)
            if h.in_field():
                break
            h.step(200)
            win_battle(h)
            battles += 1
        finish_scene(h, log, shots, tag=str(out / "blue_saffron"))
        msgs = log.msgs()
        res = {"msgs": msgs, "battles_won": battles, "lines_20_44_shown": sorted(set(msgs) & set(range(20, 45))),
               "missing_20_44": sorted(set(range(20, 45)) - set(msgs)), "shots": [x["path"] for x in shots],
               "shot_end": str(h.screenshot("blue_saffron_end"))}
        res["verdict"] = "confirmed" if 44 in msgs and battles >= 3 else ("blocked" if not msgs else "contradicted")
    return res


TWO_RUNS = ("as_saved", "flag106_clear")
# name -> (function, variants or None, judge(results by variant) or None); one child process per variant
CASES = {
    "promo_flag": (case_promo_flag, None, None),
    "electrode": (case_electrode, ("flee", "lose"), judge_electrode),
    "mortar_flag": (case_mortar_flag, None, None),
    "pikachu": (case_pikachu, None, None),
    "pidgeot": (case_pidgeot, None, None),
    "mom_visit": (case_mom_visit, TWO_RUNS, judge_mom_visit),
    "living": (case_living, TWO_RUNS, judge_living),
    "misty_date": (case_misty_date, None, None),
    "monday": (case_monday, MONDAY_HOURS, judge_monday),
    "azure_flute": (case_azure_flute, ("var4", "var3"), judge_azure_flute),
    "koga": (case_koga, KOGA_HOURS, judge_koga),
    "giovanni": (case_giovanni, None, None),
    "kecleon": (case_kecleon, ("594", "164"), judge_kecleon),
    "tony": (case_tony, ("scene", "suzie"), judge_tony),
    "blue_saffron": (case_blue_saffron, None, None),
    "clash": (case_clash, ("start", "rechoose"), judge_clash),
    "ssanne": (case_ssanne, ("as_boarded", "flag1440"), judge_ssanne),
    "sabrina": (case_sabrina, ("var0", "var5"), judge_sabrina),
    "corner_kid": (case_corner_kid, ("real", "canlose", "whiteout"), judge_corner_kid),
}


# ----------------------------------------------------------------------------- runner, suite, command line
def run_cases(roms, cases, out, jobs=6):
    """Run cases (all variants) on roms {lang: path}, one child process per case/variant/ROM, judge them.
    Returns {case: {lang: result}} with a 'verdict' in every result."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [(c, v, l) for c in cases for v in (CASES[c][1] or [None]) for l in roms]

    def run(job):
        c, v, l = job
        try:
            return c, v, l, E.run_child(["guide0107", "--child", c + (":" + v if v else ""), "--rom", roms[l],
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
    return report


# Cheap deterministic cases for `emu_harness.py suite` and the verdict each must keep (the hack's behaviour
# as observed on 2026-10-06; 'contradicted' means the guide's old wording was wrong, not a failure).
SUITE_EXPECT = {"pikachu": "confirmed", "electrode": "confirmed", "misty_date": "confirmed",
                "azure_flute": "confirmed", "koga": "confirmed", "giovanni": "confirmed", "sabrina": "confirmed",
                "kecleon": "confirmed", "promo_flag": "observed"}


def suite_check(rom, out):
    """emu_harness.py suite: the SUITE_EXPECT cases on one ROM; pass when every verdict is the expected one
    (promo_flag: the write lands in the Pokedex seen bits of No. 1335 and the scene does not repeat)."""
    report = run_cases({"x": rom}, list(SUITE_EXPECT), out, jobs=4)
    got = {c: report[c]["x"].get("verdict") for c in SUITE_EXPECT}
    promo = report["promo_flag"]["x"]
    promo_ok = promo.get("meaning", {}).get("species") == 1335 and promo.get("msgs_second") == [1]
    ok = got == SUITE_EXPECT and promo_ok
    return ok, {"verdicts": got, "promo_flag_meaning": promo.get("meaning"), "promo_second_talk": promo.get("msgs_second")}


def cmd(a):
    """emu_harness.py guide0107: each case and ROM in its own child process; one JSON report."""
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
            print(json.dumps({"case": c, "rom": l, "verdict": report[c][l].get("verdict")}), flush=True)
    name = "_".join(cases if len(cases) < 4 else ["all"]) + ("" if a.lang == "cn" else "_" + a.lang)
    path = Path(a.out) / "guide01_07" / ("report_" + name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"report": str(path)}))
    return 0
