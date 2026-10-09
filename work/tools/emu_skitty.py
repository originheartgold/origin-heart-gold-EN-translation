#!/usr/bin/env python3
"""emu_skitty - D-0582: the Route 8 Skitty scene in the emulator (used by `emu_harness.py skitty` and `suite`).

The scene (zone 16, Route 8; event script file 188, message bank a027/0331, map events a/0/3/2 #13):
- script 4 (object 3, Persian's trainer by the Underground Path): line #3 mentions the Skitty, sets flag 1636;
- script 3 (object 1, Skitty's trainer) with flag 1636 set runs part 1 (L980): Persian's cry, Skitty's cry
  (PlayCry 300) with #4, #5, again PlayCry 300 with #4, #6; sets flag 1163 (hides objects 1-4), clears flag
  1568 (shows objects 12-15 in the meadow), var 16576 = 0;
- script 5 (coord trigger at (1384, 242) / (1375, 246), var 16576 == 0) runs part 2 (L1208): the quarrel
  (#7-#21, PlayCry 53 / 300 with #11 / #19), the player steps in (#22-#31), TrainerBattle 276 + 277 (Persian's
  trainer and Skitty's trainer, a double battle); after a win (part 3) #32-#38 with PlayCry 53 / 300, var
  16576 = 1;
- scripts 7 (the Skitty objects 2 and 14: PlayCry 300, #4) and 12 (object 15, Skitty's trainer later: #48).

What the check observes, on the Chinese ROM and on the English build:
- every cry the scene's script plays: the PlayCry handler (script command 76, arm9 0x020487BC from the command
  table 0x020F793C) calls the cry routine 0x0200629C at 0x020487F0 with r1 = species, r0 = the second
  argument; every call of the cry routine is logged too (battle cries included);
- the live map objects (LocalMapObject, 0x12C bytes: +8 id, +0xC map, +0x10 sprite, +0x1C flag, +0x20
  script; found by scanning the heap) and their sprite ids, mapped to a species with the game's own data:
  every object in every map whose talk script plays exactly one literal cry gives a (sprite, species) pair
  (`sprite_species_table`); sprite 761 is used by four Skitty objects (cry 300) and nothing else;
- the opponent parties of the real TrainerBattle 276 + 277 (Party structs {u32 max 6, u32 count, 6 x 236}
  found in RAM once the battle has started; species and form decrypted);
- every message the scene prints (NPCMsg 0x021EE288 and GenderMsgBox 0x021EE388 in overlay 1, CloseMsg
  0x020408A4), one screenshot per page, so each bank-0331 line can be compared as a CN|EN pair.

The battle is not fought: part 3 runs in a fresh emulator from the state after part 2 (flags 1163 set, 1568
clear) by starting script 5 with a GoTo to the first command after the battle check (the script's own
bytes from there on). Nothing in the save on disk is changed.
"""
import collections
import datetime
import json
import struct
import sys
from pathlib import Path

import emu_harness as E

sys.path.insert(0, str(Path(__file__).resolve().parent / "docs"))

SCENE_MAP = 16                    # Route 8 (zone 16)
SCRIPT_FILE, MSG_BANK, EVENTS_FILE = 188, 331, 13
SKITTY, GLAMEOW, PERSIAN = 300, 431, 53
TRAINER_PERSIAN, TRAINER_SKITTY = 276, 277
FLAG_PART1_DONE = 1163            # set at the end of part 1 (hides objects 1-4)
FLAG_MEADOW_HIDDEN = 1568         # objects 12-15 hidden while set; part 1 clears it
FLAG_HEARD_ABOUT = 1636           # set by script 4; script 3 runs part 1 only with it
VAR_SCENE = 16576                 # coord trigger fires while 0; part 3 sets 1
SKITTY_OBJECTS = (2, 14)          # objects whose talk script is 7 (PlayCry 300)

PLAYCRY_HANDLER = 0x020487BC      # script command 76 (table 0x020F793C)
PLAYCRY_CALL = 0x020487F0         # bl 0x0200629C: r0 = second argument, r1 = species
CRY_ROUTINE = 0x0200629C          # every cry (scripts and battle)
CLOSEMSG_HANDLER = 0x020408A4     # script command 53
TRAINERBATTLE_HANDLER = 0x02048B64   # script command 213
NPCMSG_HANDLER = 0x021EE288       # overlay 1, script command 45: u8 message id at the script PC
GENDERMSG_HANDLER = 0x021EE388    # overlay 1, script command 132: u8 male id, u8 female id
CODE_SIG = {PLAYCRY_HANDLER: "38b582b0051c", PLAYCRY_CALL: "bdf754fd", CRY_ROUTINE: "f8b58ab00190",
            CLOSEMSG_HANDLER: "70b580300568", TRAINERBATTLE_HANDLER: "f8b588b0051c"}
OV1_SIG = {NPCMSG_HANDLER: "18b581b0041ca268", GENDERMSG_HANDLER: "78b581b0051c8030"}
MAP_OBJECT_SIZE = 0x12C

# Lines of a027/0331 that name the Pokemon (向尾喵 / 卷尾猫 in the Chinese) or write its cry.
SKITTY_LINES = (3, 4, 5, 6, 8, 17, 18, 19, 21, 24, 26, 31, 33, 34, 35, 37, 38, 48)
CRY_LINES = (4, 19, 38)           # written cries: English must be Skitty-style ("Skit..."), not "Gla..."
EXPECTED_SCRIPT_CRIES = {          # per part, in order (literal PlayCry arguments of the script)
    "part1": [PERSIAN, SKITTY, SKITTY],
    "part2": [PERSIAN, PERSIAN, SKITTY],
    "talk": [SKITTY],
    "part3": [PERSIAN, SKITTY, PERSIAN, SKITTY],
}
CLOCK = datetime.datetime(2026, 10, 9, 12)


# ----------------------------------------------------------------------------- static data (ROM)
def _rom(path):
    import romdata as R
    cache = E.DEF_OUT / "skitty" / f"romdata_{Path(path).stem}.pickle"
    return R.Rom(path=str(path), cache=str(cache))


def sprite_species_table(rom):
    """{sprite: Counter(species)} from every map: objects whose talk script plays exactly one literal cry
    before its first message (FacePlayer; PlayCry N; NPCMsg 'Name: cry!'). This is the game's own pairing
    of overworld sprites with species."""
    import romdata as R
    zones = R.read_json(str(E.WORK / "translate" / "bank_maps.json"))["_zones"]
    pairs = collections.defaultdict(collections.Counter)
    seen = set()
    for z in zones:
        key = (z["scripts_bank"], z.get("events_bank"))
        if key[1] is None or key in seen:
            continue
        seen.add(key)
        try:
            ev = R.parse_events(rom["events"][key[1]])
            entries, ins = R.disasm(rom["scripts"][key[0]])
        except Exception:
            continue
        for o in ev["obj"]:
            cries = script_cries(entries, ins, o["script"])
            if len(cries) == 1:
                pairs[o["sprite"]][cries[0]] += 1
    return pairs


def script_cries(entries, ins, script, limit=12):
    """Literal PlayCry species at the start of map script <script> (1-based) up to its first message."""
    import romdata as R
    names = R.cmds()
    if not 1 <= script <= len(entries):
        return []
    pc, cries = entries[script - 1], []
    for _ in range(limit):
        if pc not in ins:
            break
        op, args, nxt, _ = ins[pc]
        name = names[op][0] if isinstance(names[op], (list, tuple)) else names[op]
        if name == "PlayCry" and args[0] < E.VARS_BASE:
            cries.append(args[0])
        if name in ("End", "GoTo", "GoToIf", "NPCMsg", "NonNPCMsg", "GenderMsgBox"):
            break
        pc = nxt
    return cries


def species_for_sprite(table, sprite):
    """Most common species for a sprite in sprite_species_table, or None."""
    c = table.get(sprite)
    return c.most_common(1)[0][0] if c else None


def after_battle_offset(data, trainers=(TRAINER_PERSIAN, TRAINER_SKITTY)):
    """Offset of the first command after `TrainerBattle a b; CheckBattleWon; CompareVarToValue; GoToIf` in
    script file data (the scene's part 3), and the offset of map script 5's start."""
    import romdata as R
    names = R.cmds()
    entries, ins = R.disasm(data)

    def name(op):
        return names[op][0] if isinstance(names[op], (list, tuple)) else names[op]
    for pc in sorted(ins):
        op, args, nxt, _ = ins[pc]
        if name(op) == "TrainerBattle" and tuple(args[:2]) == tuple(trainers):
            for _ in range(3):
                nxt = ins[nxt][2]
            return nxt, entries[4]
    raise ValueError("TrainerBattle %s not found" % (trainers,))


def goto_bytes(at, target):
    """A GoTo command placed at offset <at> that jumps to <target> (offset relative to the next command)."""
    return E.script_bytes(("GoTo", target - (at + 6)))


def bank_lines(rom_path, bank=MSG_BANK):
    """Decoded text of a027 bank <bank> from a ROM (msgtool + the build's charmaps)."""
    import msgtool
    cm = msgtool.Charmap.load([str(E.WORK / "tools" / "charmap_en.tsv"),
                               str(E.WORK / "tools" / "charmaps" / "charmap_zh_xzonn_gen4.tsv")])
    narc = msgtool._msg_narc(msgtool.load_rom(rom_path))
    return [s["text"] for s in msgtool.bank_to_json(bank, narc.files[bank], cm)["strings"]]


def check_text(lines, lang):
    """Each SKITTY_LINES line names the Skitty (EN: 'Skitty', never 'Glameow'); written cries Skitty-style."""
    bad = []
    for i in SKITTY_LINES:
        t = lines[i]
        if lang == "en":
            if "Skitty" not in t or "Gla" in t:
                bad.append((i, t))
            elif i in CRY_LINES and not t.split("Skitty:")[-1].strip().startswith("Ski"):
                bad.append((i, t))
        elif "向尾喵" not in t and "卷尾猫" not in t:
            bad.append((i, t))
    return bad


# ----------------------------------------------------------------------------- live observation
class SceneLog:
    """Hooks the cry, message and battle script commands; keeps one ordered event list."""

    def __init__(self, h):
        self.h, self.events, self.msg, self.battle = h, [], None, False
        self.part = "setup"
        h.check_code(CODE_SIG)
        h.on_exec(PLAYCRY_CALL, self._cry)
        h.on_exec(CRY_ROUTINE, self._cry_any)
        h.on_exec(CLOSEMSG_HANDLER, self._close)
        h.on_exec(TRAINERBATTLE_HANDLER, self._battle)
        h.on_exec(NPCMSG_HANDLER, self._npcmsg)
        h.on_exec(GENDERMSG_HANDLER, self._gendermsg)

    def _ov1(self, addr):
        return self.h.read(addr, len(OV1_SIG[addr]) // 2) == bytes.fromhex(OV1_SIG[addr])

    def _add(self, **ev):
        ev["part"], ev["frame"] = self.part, self.h.frame
        self.events.append(ev)

    def _cry(self, h):
        self._add(t="script_cry", species=h.reg.r1, arg2=h.reg.r0)

    def _cry_any(self, h):
        self._add(t="cry", species=h.reg.r1)

    def _close(self, h):
        self.msg = None
        self._add(t="close")

    def _battle(self, h):
        pc = h.u32(h.reg.r0 + 8)
        self.battle = True
        self._add(t="trainer_battle", trainers=list(struct.unpack("<HH", h.read(pc, 4))))

    def _npcmsg(self, h):
        if self._ov1(NPCMSG_HANDLER):
            self.msg = h.u8(h.u32(h.reg.r0 + 8))
            self._add(t="msg", id=self.msg)

    def _gendermsg(self, h):
        if self._ov1(GENDERMSG_HANDLER):
            pc = h.u32(h.reg.r0 + 8)
            male, female = h.u8(pc), h.u8(pc + 1)
            self.msg = male        # the save's player is male (screenshots show the male label line)
            self._add(t="msg", id=male, female=female)

    def cries(self, part=None, script=True):
        return [e["species"] for e in self.events if e["t"] == ("script_cry" if script else "cry")
                and (part is None or e["part"] == part)]

    def msgs(self, part=None):
        return [e["id"] for e in self.events if e["t"] == "msg" and (part is None or e["part"] == part)]


def live_objects(h, map_id, lo=0x02200000, hi=0x02400000):
    """The field's LocalMapObjects for map_id: {id: {sprite, flag, script, x, z, addr}}. Records are 0x12C
    bytes (+0 flags, bit 0 active; +8 id; +0xC map; +0x10 sprite; +0x1C flag; +0x20 script; +0x64 x,
    +0x6C z); a record counts when the slot 0x12C before or after it also holds this map (the manager's
    array; free slots keep their old map)."""
    ram = h.read(lo, hi - lo)

    def rec(i):
        if i < 0 or i + MAP_OBJECT_SIZE > len(ram):
            return None
        fl, _, oid, mp, spr = struct.unpack_from("<5I", ram, i)
        if not fl & 1 or oid > 0xFF or mp != map_id or spr > 0xFFF:
            return None
        flag, script = struct.unpack_from("<2I", ram, i + 0x1C)
        x, _, z = struct.unpack_from("<3i", ram, i + 0x64)
        return {"id": oid, "sprite": spr, "flag": flag, "script": script, "x": x, "z": z, "addr": hex(lo + i)}
    out = {}
    pat = struct.pack("<I", map_id)
    i = ram.find(pat)
    while i >= 0:
        r = rec(i - 0xC) if i % 4 == 0 else None
        if r and any(0 <= j + 4 <= len(ram) and ram[j:j + 4] == pat for j in (i - MAP_OBJECT_SIZE, i + MAP_OBJECT_SIZE)):
            out.setdefault(r["id"], r)
        i = ram.find(pat, i + 1)
    return out


def ram_pokemon_checksum_ok(raw):
    """Cheap read-only scan filter; full field decoding stays in the shared core.

    RAM may hold opened payloads (bit 1). Closed payloads reuse the independent
    memcheck checksum oracle. Clear header flags only in its temporary copy:
    this tests the checksum, not whether a record is safe to edit or persist.
    """
    if len(raw) not in (136, 236):
        return False
    flags, checksum = struct.unpack_from("<HH", raw, 4)
    if flags & 2:
        return sum(struct.unpack_from("<64H", raw, 8)) & 0xFFFF == checksum
    from memcheck import decode_stored_moves
    try:
        decode_stored_moves(raw[:4] + b"\0\0" + raw[6:136])
    except ValueError:
        return False
    return True


def find_parties(h, lo=0x02200000, hi=0x02400000):
    """Party structs in RAM: {u32 max 6, u32 count 1-6, count x 236-byte Pokemon with valid checksums}."""
    ram = h.read(lo, hi - lo)
    out, i = [], ram.find(b"\x06\x00\x00\x00")
    while 0 <= i <= len(ram) - 8:
        if i % 4 == 0:
            cnt = struct.unpack_from("<I", ram, i + 4)[0]
            mons = []
            bounded = 1 <= cnt <= 6 and i + 8 + 236 * cnt <= len(ram)
            for k in range(cnt if bounded else 0):
                raw = ram[i + 8 + 236 * k:i + 8 + 236 * (k + 1)]
                if not ram_pokemon_checksum_ok(raw):
                    break
                m = E.decode_party_pokemon(raw)
                if not m["checksum_ok"] or not 0 < m["species"] < 1200 or m["bad_egg"]:
                    break
                mons.append({"species": m["species"], "form": m["form"], "level": m.get("level"),
                             "item": m["item"]})
            if mons and len(mons) == cnt:
                out.append({"addr": hex(lo + i), "mons": mons})
        i = ram.find(b"\x06\x00\x00\x00", i + 1)
    return out


SPRITE_ZOOM = (100, 56, 172, 104)  # field screenshot around the player at (1397, 233): objects 1 and 2
MSG_BOX = (8, 146, 232, 186)       # top-screen text area of the field message window (without the arrow)


def drive(h, log, done, shots, tag, max_iter=400, settle=60):
    """Press A through a running scene: after every wait, while a message is open, wait until its text
    area stops changing (the page is fully printed), screenshot the page (one file per new page text) and
    press A; stop when done(h) is true."""
    last = None
    for _ in range(max_iter):
        h.step(settle)
        if done(h):
            return True
        if log.msg is None:
            last = None
            continue
        prev = None
        for _ in range(60):                      # printed when two looks 12 frames apart agree
            box = h.emu.screenshot().crop(MSG_BOX).tobytes()
            if box == prev:
                break
            prev = box
            h.step(12)
        if box != last and log.msg is not None:
            last = box
            path = h.out / f"{tag}_{len(shots):03d}_m{log.msg}.png"
            h.emu.screenshot().crop((0, 0, 256, 192)).save(path)
            shots.append({"msg": log.msg, "part": log.part, "path": str(path)})
        h.press("A", after=4)
    return False


def run_part(rom, part, out):
    """One emulator run. part 'a': scripts 4 and 3 (part 1), then the coord trigger (part 2) up to the
    battle and the opponents' parties. part 'b': talk to the meadow Skitty (7) and its trainer (12), then
    part 3 (after the battle)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rom_data = _rom(E.DEF_ROM_CN)
    res = {"part": part, "rom": str(rom)}
    if part == "a":
        flags_on, flags_off, var = (FLAG_HEARD_ABOUT, FLAG_MEADOW_HIDDEN), (FLAG_PART1_DONE,), 1
    else:
        flags_on, flags_off, var = (FLAG_HEARD_ABOUT, FLAG_PART1_DONE), (FLAG_MEADOW_HIDDEN,), 0   # as after part 1

    def edit(sf):
        for f in flags_off:
            sf.set_flag(f, False)
    shots = []
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=CLOCK, flags=flags_on, vars={VAR_SCENE: var},
                    edit=edit) as h:
        log = SceneLog(h)
        tag = lang_of(rom) + "_" + part
        if part == "a":
            log.part = "npc"                                  # object 3 (script 4): line #3
            h.warp(SCENE_MAP, 1365, 234, E.DIRS["UP"])
            h.press("A", after=10)
            drive(h, log, lambda h: log.msg is None and "close" in [e["t"] for e in log.events], shots, tag)
            h.warp(SCENE_MAP, 1397, 233, E.DIRS["UP"])        # below object 1 (Skitty's trainer)
            h.step(30)
            res["objects"] = live_objects(h, SCENE_MAP)
            res["objects_shot"] = str(h.screenshot(f"{tag}_objects"))
            log.part = "part1"
            h.press("A", after=10)
            res["part1_done"] = drive(h, log, lambda h: h.get_flag(FLAG_PART1_DONE) and log.msg is None
                                      and h.get_var(VAR_SCENE) == 0, shots, tag)
            h.step(60)
            res["objects_after_part1"] = live_objects(h, SCENE_MAP)
            log.part = "part2"
            h.warp(SCENE_MAP, 1385, 242, E.DIRS["LEFT"])      # next to the coord trigger (1384, 242)
            h.step(30)
            h.hold("LEFT")
            h.step(20)
            h.release("LEFT")
            res["part2_reached_battle"] = drive(h, log, lambda h: log.battle, shots, tag, max_iter=600)
            frames = []
            for k in range(8):                                # the battle intro: send-out messages
                h.step(90)
                frames.append(str(h.screenshot(f"{tag}_battle_{k}")))
            res["battle_shots"] = frames
            res["parties"] = find_parties(h)
            res["player_party"] = [m["species"] for m in h.party()]
        else:
            log.part = "talk"
            h.warp(SCENE_MAP, 1380, 247, E.DIRS["UP"])        # below object 14 (meadow Skitty, script 7)
            h.step(30)
            res["objects"] = live_objects(h, SCENE_MAP)
            res["objects_shot"] = str(h.screenshot(f"{tag}_objects"))
            h.press("A", after=10)
            n_close = lambda: sum(e["t"] == "close" for e in log.events)
            drive(h, log, lambda h: n_close() >= 1 and log.msg is None, shots, tag)
            log.part = "talk48"
            h.warp(SCENE_MAP, 1381, 247, E.DIRS["UP"])        # below object 15 (script 12, line #48)
            h.step(30)
            h.press("A", after=10)
            drive(h, log, lambda h: n_close() >= 2 and log.msg is None, shots, tag)
            log.part = "part3"
            h.warp(SCENE_MAP, 1379, 249, E.DIRS["UP"])
            h.step(30)
            target, start = after_battle_offset(rom_data["scripts"][SCRIPT_FILE])
            res["part3_jump"] = {"script5_start": start, "after_battle": target}
            h.run_script(script_id=5, program=goto_bytes(start, target))
            res["part3_done"] = drive(h, log, lambda h: h.get_var(VAR_SCENE) == 1 and log.msg is None, shots, tag)
    res["events"] = log.events
    res["shots"] = shots
    return res


# ----------------------------------------------------------------------------- evaluation
def trainer_parties(rom, ids=(TRAINER_PERSIAN, TRAINER_SKITTY)):
    """{trainer: [(species, form), ...]} from the ROM's trainer data (romdata.parse_trpoke, hack layout)."""
    import romdata as R
    out = {}
    for t in ids:
        td = R.parse_trdata(rom["trdata"][t])
        out[t] = [(m["species"], m["form"]) for m in R.parse_trpoke(rom["trpoke"][t], td["count"])]
    return out


def battle_cries(events):
    """Species of the cries played after the TrainerBattle command (the send-outs)."""
    k = next((n for n, e in enumerate(events) if e["t"] == "trainer_battle"), len(events))
    return [e["species"] for e in events[k:] if e["t"] == "cry"]


def evaluate(a, b, table, parties, lines=None, lang=None):
    """Pass/fail of one ROM from its two runs (a: npc, part 1, part 2 + battle; b: talks, part 3).
    table: sprite_species_table; parties: trainer_parties (expected opponents)."""
    log = {"a": a["events"], "b": b["events"]}

    def cries(run, part):
        return [e["species"] for e in log[run] if e["t"] == "script_cry" and e["part"] == part]
    got = {"part1": cries("a", "part1"), "part2": cries("a", "part2"), "talk": cries("b", "talk"),
           "part3": cries("b", "part3")}
    sprites = {}
    for run, objs in (("a", a.get("objects", {})), ("b", b.get("objects", {}))):
        for oid, o in objs.items():
            if int(oid) in SKITTY_OBJECTS + (4, 13):
                sprites[f"{run}:{oid}"] = {"sprite": o["sprite"], "script": o["script"],
                                           "species": species_for_sprite(table, o["sprite"])}
    skitty_objs = [v for v in sprites.values() if v["script"] == 7]
    battle = [e for e in log["a"] if e["t"] == "trainer_battle"]
    in_ram = [[(m["species"], m["form"]) for m in p["mons"]] for p in a.get("parties", [])]
    found = {t: [list(x) for x in mons] if [tuple(x) for x in mons] in [[tuple(y) for y in r] for r in in_ram]
             else None for t, mons in parties.items()}
    msgs = set(e["id"] for r in log.values() for e in r if e["t"] == "msg")
    skitty_party = found.get(TRAINER_SKITTY)
    checks = {
        "cries": got == EXPECTED_SCRIPT_CRIES,
        "no_glameow_cry": GLAMEOW not in [e["species"] for r in log.values() for e in r if "species" in e],
        "sprite": len(skitty_objs) == 2 and all(v["species"] == SKITTY for v in skitty_objs),
        "battle": bool(battle) and battle[0]["trainers"] == [TRAINER_PERSIAN, TRAINER_SKITTY],
        "opponents_in_battle": all(v is not None for v in found.values()),
        "trainer_277_lead_skitty": bool(skitty_party) and tuple(skitty_party[0]) == (SKITTY, 0),
        "lines_shown": set(SKITTY_LINES) <= msgs,
        "part1_done": bool(a.get("part1_done")), "part3_done": bool(b.get("part3_done")),
    }
    details = {"script_cries": got, "sprites": sprites, "battle": battle[:1],
               "opponent_parties_in_ram": {str(t): v for t, v in found.items()},
               "lines_missing": sorted(set(SKITTY_LINES) - msgs),
               "all_cries": [e["species"] for r in log.values() for e in r if e["t"] == "cry"],
               "battle_cries": battle_cries(log["a"])}
    if lines is not None:
        bad = check_text(lines, lang)
        checks["text"] = not bad
        details["text_bad"] = bad
        details["text"] = {i: lines[i] for i in SKITTY_LINES}
    return all(checks.values()), {"checks": checks, **details}


# ----------------------------------------------------------------------------- runs, pairs, report
def lang_of(rom):
    return "cn" if Path(rom).resolve() == E.DEF_ROM_CN.resolve() else "en"


def run_rom(rom, out):
    """Both runs of one ROM in parallel child processes, evaluated. Returns (ok, details, runs)."""
    from concurrent.futures import ThreadPoolExecutor
    out = Path(out)
    with ThreadPoolExecutor(2) as ex:
        a, b = ex.map(lambda p: E.run_child(["skitty", "--rom", rom, "--out", out, "--part", p], timeout=1800),
                      ("a", "b"))
    static = _rom(E.DEF_ROM_CN)
    lang = lang_of(rom)
    ok, details = evaluate(a, b, sprite_species_table(static), trainer_parties(static),
                           lines=bank_lines(rom), lang=lang)
    if lang != "cn":                 # the static data comes from the CN ROM: the build must not differ there
        mine = _rom(rom)
        same = (mine["scripts"][SCRIPT_FILE] == static["scripts"][SCRIPT_FILE]
                and mine["events"][EVENTS_FILE] == static["events"][EVENTS_FILE]
                and trainer_parties(mine) == trainer_parties(static))
        details["checks"]["scene_data_same_as_cn"] = same
        ok = ok and same
    (out / f"skitty_{lang}_runs.json").write_text(json.dumps({"a": a, "b": b}, ensure_ascii=False, indent=1))
    return ok, details, {"a": a, "b": b}


def first_pages(runs, msg_id):
    """Page screenshots of the first time msg_id was shown (consecutive shots of that message)."""
    shots = runs["a"]["shots"] + runs["b"]["shots"]
    pages, started = [], False
    for s in shots:
        if s["msg"] == msg_id:
            pages.append(s["path"])
            started = True
        elif started:
            break
    return pages


def make_pairs(runs_cn, runs_en, out):
    """CN|EN pairs (top screen) of every SKITTY_LINES line, the scene objects and the battle intro."""
    from PIL import Image
    out = Path(out)
    rows = {}

    def pair(name, cn, en):
        n = max(len(cn), len(en), 1)
        img = Image.new("RGB", (2 * 256 + 8, 192 * n), "white")
        for k, p in enumerate(cn):
            img.paste(Image.open(p).crop((0, 0, 256, 192)), (0, 192 * k))
        for k, p in enumerate(en):
            img.paste(Image.open(p).crop((0, 0, 256, 192)), (264, 192 * k))
        path = out / f"{name}_pair.png"
        img.save(path)
        return str(path)
    for i in SKITTY_LINES:
        cn, en = first_pages(runs_cn, i), first_pages(runs_en, i)
        rows[f"a027/0331#{i}"] = {"pair": pair(f"msg_0331_{i}", cn, en), "pages_cn": len(cn), "pages_en": len(en)}
    cn, en = [runs_cn["a"].get("objects_shot")], [runs_en["a"].get("objects_shot")]
    if all(cn + en):
        rows["scene_objects"] = {"pair": pair("scene_objects", cn, en)}
        zoom = Image.new("RGB", (2 * 216 + 8, 144), "white")      # objects 1 and 2 (trainer, Skitty), x3
        for k, p in enumerate(cn + en):
            zoom.paste(Image.open(p).crop(SPRITE_ZOOM).resize((216, 144), Image.NEAREST), (224 * k, 0))
        zoom.save(out / "skitty_sprite_zoom_pair.png")
        rows["skitty_sprite_zoom"] = {"pair": str(out / "skitty_sprite_zoom_pair.png")}
    cn, en = runs_cn["a"].get("battle_shots", [])[-1:], runs_en["a"].get("battle_shots", [])[-1:]
    rows["battle_intro"] = {"pair": pair("battle_intro", cn, en)}
    return rows


def cmd_skitty(a):
    """emu_harness.py skitty: run the scene on both ROMs (or one with --lang), write the report and pairs."""
    if a.part:                     # child: one run, into --out/<lang>
        res = run_part(a.rom, a.part, Path(a.out) / lang_of(a.rom))
        print("RESULT " + json.dumps(res, ensure_ascii=False))
        return 0
    out = Path(a.out) / "skitty"
    out.mkdir(parents=True, exist_ok=True)
    roms = {"cn": a.rom_cn, "en": a.rom_en}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as ex:
        results = dict(zip(roms, ex.map(lambda r: run_rom(r, out), roms.values())))
    report = {"roms": roms, "pass": all(r[0] for r in results.values()),
              "results": {k: {"pass": r[0], **r[1]} for k, r in results.items()}}
    report["pairs"] = make_pairs(results["cn"][2], results["en"][2], out)
    (out / "skitty_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    for k, r in results.items():
        print(json.dumps({"rom": k, "pass": r[0], "checks": r[1]["checks"]}))
    print(json.dumps({"pass": report["pass"], "report": str(out / "skitty_report.json")}))
    return 0 if report["pass"] else 1


def suite_check(rom, out):
    """emu_harness.py suite: the scene on one ROM, pass/fail."""
    ok, details, _ = run_rom(rom, out)
    return ok, details
