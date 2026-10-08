#!/usr/bin/env python3
"""emu_guide0813 - emulator checks for the hedged claims in guide chapters 08-13 and known-issues.md
(`emu_harness.py guide0813`).

Same approach as emu_guide0107 (whose helpers it reuses): each case puts the game into the state the guide's
*Source:* line names (flags, vars, badges, clock, party, bag, money), runs the hack's own event script
(talking to the object, or a GoTo into the script's own bytes with `run_from`) and reads back what the game
did. New here: `OpTrace`, a hook on the script interpreter itself (RunScriptContext, arm9 0x0203F474), which
logs every script command the game executes (name, script file offset) and every invalid opcode that stops
a script. So a case can say which branch of a script ran, and whether a script ended or died.

    .venv/bin/python work/tools/emu_harness.py guide0813 [--case ribbon,fortune,...] [--lang cn|en|both]

Every case returns a dict with `verdict` ('confirmed', 'contradicted', 'observed' or 'blocked') and its
evidence; screenshots go to <out>/guide08_13/<lang>/. Cases are listed in CASES at the end of the file.
`suite` runs SUITE_EXPECT (the cheap deterministic ones) and fails when a verdict changes.
"""
import datetime
import json
import struct
from pathlib import Path

import emu_harness as E
import emu_skitty as K
import emu_guide0107 as G

CLOCK = G.CLOCK                                  # Friday 2026-10-09 12:00
FAST_LEAD = G.FAST_LEAD

# ----------------------------------------------------------------------------- the script interpreter
RUN_CTX = 0x0203F474          # RunScriptContext(ctx): mode at +1, native fn +4, PC +8, table +0x5C, count +0x60
RUN_CTX_DISPATCH = 0x0203F4CE  # r1 = opcode (< count), r4 = ctx: just before the handler is called
RUN_CTX_BAD_OP = 0x0203F4C4    # r1 = opcode >= count: GF_ASSERT, then mode = 0 (the script stops)
CTX_SCRIPT_BASE = 0x7C         # ctx +0x7C: the loaded script file (set by the loader 0x0203F870)
OPTRACE_SIG = {0x0203F4BE: "206e814204d3", 0x0203F4CE: "e26d89005158"}   # ldr r0,[r4,#0x60]; cmp; blo / ldr r2,[r4,#0x5c]; ...
_CMDS = {}


def cmd_names():
    if not _CMDS:
        raw = json.loads(E.SCRIPT_CMDS.read_text())
        _CMDS.update({int(k): v[0] for k, v in raw.items()})
    return _CMDS


CMP_VAR_VALUE = 0x0204021C     # CompareVarToValue handler: r0 = GetVarPointer(fsys, var) (0x0203FAB0) result
CMP_SIG = {0x0204021C: "0588"}  # ldrh r5, [r0]


class OpTrace:
    """Logs every script command the interpreter dispatches, as rows (name, offset in its script file, file
    base, frame, first 4 argument bytes), and invalid opcodes (`bad`). CompareVarToValue also logs the
    value it read (`cmp`: row index -> value), so special vars (0x8000+) can be seen at a given offset."""

    def __init__(self, h, limit=20000):
        self.h, self.rows, self.bad, self.limit, self.cmp = h, [], [], limit, {}
        h.check_code(OPTRACE_SIG)
        h.check_code(CMP_SIG)
        names = cmd_names()
        self.names = names

        def disp(h):
            if len(self.rows) < self.limit:
                ctx = h.reg.r4
                base, pc = h.u32(ctx + CTX_SCRIPT_BASE), h.u32(ctx + 8)
                self.rows.append((names.get(h.reg.r1, h.reg.r1), pc - 2 - base, base, h.frame, h.read(pc, 4)))

        def bad(h):
            ctx = h.reg.r4
            base = h.u32(ctx + CTX_SCRIPT_BASE)
            self.bad.append({"op": h.reg.r1, "offset": h.u32(ctx + 8) - 2 - base, "frame": h.frame})

        def cmp(h):
            if self.rows:
                self.cmp[len(self.rows) - 1] = h.u16(h.reg.r0)
        h.on_exec(RUN_CTX_DISPATCH, disp)
        h.on_exec(RUN_CTX_BAD_OP, bad)
        h.on_exec(CMP_VAR_VALUE, cmp)

    def mark(self):
        return len(self.rows)

    def ops(self, since=0):
        return [(r[0], r[1]) for r in self.rows[since:]]

    def names_since(self, since=0):
        return [r[0] for r in self.rows[since:]]

    def offsets(self, name=None, since=0):
        return [r[1] for r in self.rows[since:] if name is None or r[0] == name]

    def reached(self, offset, since=0):
        return any(r[1] == offset for r in self.rows[since:])

    def msgs(self, since=0, ops=("NPCMsg", "NonNPCMsg")):
        """Message ids of NPCMsg-style commands (u8 argument)."""
        return [r[4][0] for r in self.rows[since:] if r[0] in ops]

    def u16_args(self, name, since=0):
        return [struct.unpack_from("<H", r[4])[0] for r in self.rows[since:] if r[0] == name]

    def cmp_at(self, offset, since=0):
        """Values CompareVarToValue read at <offset>."""
        return [self.cmp[i] for i in range(since, len(self.rows)) if self.rows[i][1] == offset and i in self.cmp]

    def idle_frames(self):
        return self.h.frame - (self.rows[-1][3] if self.rows else 0)

    def close(self):
        for a in (RUN_CTX_DISPATCH, RUN_CTX_BAD_OP, CMP_VAR_VALUE):
            self.h.on_exec(a, None)


MENU_OPS = {"YesNo", "GetMenuChoice", "MenuExec"}


def wait_stable(h, max_frames=900, still=3):
    """Step until both screens stay unchanged for <still> looks 10 frames apart (text printed, menu drawn)."""
    prev, same = None, 0
    for _ in range(0, max_frames, 10):
        img = h.emu.screenshot().tobytes()
        same = same + 1 if img == prev else 0
        if same >= still:
            return True
        prev = img
        h.step(10)
    return False


def talk_through(h, tr, answers=(), max_iter=250, idle=150, shots=None, tag="t", every=40, battle=None):
    """Press A through a running script until it ends (End executed and no command for <idle> frames while
    in the field) or dies (an invalid opcode). `answers`: per menu/yes-no, in order, the number of DOWN
    presses before A (0 = first choice / Yes; 1 = No); 'B' presses B. `battle`: what to do when a battle's
    command menu shows: 'flee', 'lose', 'win' (or None: stop and return 'battle'). Outside the field only B
    is pressed (A would pick FIGHT). Screenshots every few pages into <shots>. Returns 'end', 'bad_op',
    'battle' or 'timeout'."""
    answers = list(answers)
    nbad = len(tr.bad)
    last_menu = len(tr.rows)
    battles = 0
    for i in range(max_iter):
        h.step(every)
        if len(tr.bad) > nbad:
            h.step(120)
            return "bad_op"
        rows = tr.rows
        if not h.in_field():
            if h.on_screen("battle_menu"):
                battles += 1
                if battle is None:
                    return "battle"
                if battle == "flee":
                    h.flee(battle_menu_wait=60)
                elif battle == "lose":
                    G.lose_battle(h)
                else:
                    G.win_battle(h)
                continue
            if i % 2:
                h.press("B", after=4)
            continue
        if rows and rows[-1][0] == "End" and h.in_field():
            if tr.idle_frames() >= idle:
                return "end"
            if tr.idle_frames() >= 30:           # ended a moment ago: wait, don't talk again
                continue
        waiting_menu = any(r[0] in MENU_OPS for r in rows[last_menu:])
        if waiting_menu and answers:
            last_menu = len(rows)
            wait_stable(h)                         # the text has printed and the menu is drawn
            a = answers.pop(0)
            if shots is not None:
                shots.append(str(h.screenshot(f"{tag}_menu{len(shots):02d}")))
            if a == "B":
                h.press("B", after=40)
            elif isinstance(a, tuple):             # ("touch", x, y): a bottom-screen menu button
                h.touch(a[1], a[2], frames=8, after=40)
            else:
                for _ in range(a):
                    h.press("DOWN", after=12)
                h.press("A", after=40)
            continue
        if waiting_menu:
            last_menu = len(rows)
        if shots is not None and i % 6 == 3:
            shots.append(str(h.screenshot(f"{tag}_{len(shots):02d}")))
        h.press("A", after=4)
    return "timeout"


def can_walk(h, direction="DOWN", tiles=2):
    """Does the player move? Live position before/after a short walk (the field must take input)."""
    p0 = h.position()
    h.walk(direction, tiles)
    h.step(30)
    p1 = h.position()
    return p0 != p1, p0, p1


def menu_opens(h, entry="pokemon"):
    """Does the bottom-screen field menu still react? Touch an entry and compare the screens (then B back)."""
    a = h.emu.screenshot().convert("RGB")
    h.touch(*E.FIELD_MENU[entry], frames=8, after=150)
    b = h.emu.screenshot().convert("RGB")
    changed = E.screen_diff(a, b)[0] > 0.05
    if changed:
        h.press("B", after=150)
    return changed


def stand_by(h, map_id, oid, side="DOWN"):
    """Warp to the tile next to live object <oid> and face it. side: where the player stands."""
    o = G.obj_at(h, map_id, oid)
    if o is None:
        return None
    dx, dz, face = {"DOWN": (0, 1, "UP"), "UP": (0, -1, "DOWN"), "LEFT": (-1, 0, "RIGHT"),
                    "RIGHT": (1, 0, "LEFT")}[side]
    h.warp(map_id, o["x"] + dx, o["z"] + dz, E.DIRS[face])
    h.step(60)
    return o


def decrypted_blocks(raw):
    """The 128 decrypted data bytes of a 236-byte party Pokemon, in A-B-C-D order (for diffs)."""
    pid, fl, checksum = struct.unpack_from("<IHH", raw, 0)
    words = struct.unpack_from("<64H", raw, 8)
    plain = list(words) if fl & 3 else [w ^ k for w, k in zip(words, E._prng_stream(checksum, 64))]
    data = struct.pack("<64H", *plain)
    order = E.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    blk = {n: data[32 * i:32 * i + 32] for i, n in enumerate(order)}
    return blk["A"] + blk["B"] + blk["C"] + blk["D"]


def party_raw(h, slot):
    return h.read(h.array(E.ARR_PARTY) + 8 + 236 * slot, 236)


def set_money(h, value):
    h.w32(h.array(1) + 0x18, value)


def bag_change(before, after):
    return {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after) if after.get(k, 0) != before.get(k, 0)}


def set_bag(h, pocket, items):
    """Write a bag pocket in RAM: [(item, qty), ...] (the rest of the pocket is cleared)."""
    off, n = E.POCKETS[pocket]
    base = h.array(E.ARR_BAG) + off
    for i in range(n):
        it, q = items[i] if i < len(items) else (0, 0)
        h.w16(base + 4 * i, it)
        h.w16(base + 4 * i + 2, q)


def remove_item(h, item):
    """Remove every stack of <item> from the bag (RAM)."""
    for pocket, (off, n) in E.POCKETS.items():
        base = h.array(E.ARR_BAG) + off
        for i in range(n):
            if h.u16(base + 4 * i) == item:
                h.w16(base + 4 * i, 0)
                h.w16(base + 4 * i + 2, 0)


def add_item(h, item, qty, pocket="items"):
    """Put <item> x qty into the first empty slot of <pocket> (RAM)."""
    off, n = E.POCKETS[pocket]
    base = h.array(E.ARR_BAG) + off
    for i in range(n):
        if h.u16(base + 4 * i) in (0, item):
            h.w16(base + 4 * i, item)
            h.w16(base + 4 * i + 2, qty)
            return
    raise RuntimeError("pocket full")


def out_dir(out, rom):
    d = Path(out).resolve() / "guide08_13" / K.lang_of(rom)
    d.mkdir(parents=True, exist_ok=True)
    return d


def weekday_clock(weekday, hour=12):
    """A pinned date with that weekday (0 = Sunday): 2026-10-04 is a Sunday."""
    return datetime.datetime(2026, 10, 4 + weekday, hour, 0)


# ----------------------------------------------------------------------------- cases
# The seven weekday siblings: name -> (zone, script file, script no., object id, weekday, ribbon id).
SIBLINGS = {"tuscany": (33, 225, 4, 6, 2, 60), "frieda": (36, 232, 6, 14, 5, 63), "arthur": (40, 243, 2, 6, 4, 62),
            "sunny": (41, 246, 2, 3, 0, 65), "wesley": (88, 934, 6, 2, 3, 61), "santos": (89, 937, 7, 8, 6, 64),
            "monica": (94, 958, 2, 0, 1, 59)}


def window_open(h):
    """Is the field message window drawn? Its white text area has a light frame at MSG_BOX's corners."""
    img = h.emu.screenshot().convert("RGB")
    px = [img.getpixel(xy) for xy in ((12, 150), (228, 150), (12, 182), (228, 182))]
    return all(min(p) > 200 for p in px)


def save_prompt(h):
    """The bottom-screen save question ('Save your progress?') is showing: its white text box corners."""
    img = h.emu.screenshot().convert("RGB")
    return all(min(img.getpixel(xy)) > 230 for xy in ((14, 344), (14, 376), (220, 344)))


def case_ribbon(rom, out, variant):
    """Known issues: Arthur's / Santos's and Wesley's ribbon freeze (D-1331), and the four other siblings.
    variant '<name>': on the sibling's own day with var 0x4094 = 7 (met all seven) and flag 2748 clear, talk to
    him/her with a generator lead (no ribbons); the visibility conditions of the map scripts are met (badge 0
    for Tuscany, var 0x40B2 = 5 for Wesley). variant '<name>_control': var 0x4094 = 6: the normal daily gift.
    variant 'arthur_a' / 'arthur_b': as 'arthur', but A (talk again) or B is pressed once before the probes.
    After the talk: is the window still open; does the player move; does X open the field menu; does SAVE
    open the save prompt. Observed: every script command executed (OpTrace), invalid opcodes, the lead's data
    before/after (the ribbon byte), the bag, screenshots."""
    name, _, mode = variant.partition("_")
    control = mode == "control"
    zone, f, sno, oid, wday, ribbon = SIBLINGS[name]
    var = 6 if control else 7
    extra = {0x40B2: 5} if name == "wesley" else {}

    def edit(sf):
        sf.set_flag(2748, False)
        if name == "wesley":            # Rocket HQ cleared: the calm-day code (0x0203A580) writes 0x4037
            sf.set_flag(202)
    with E.start_at(None, rom=rom, out=out, verbose=False, clock=weekday_clock(wday),
                    vars={0x4094: var, **extra}, edit=edit) as h:
        G.set_badge(h, 0)
        G.lead(h, 25, level=30)
        x, z = obj_rom(zone, oid)
        tr = OpTrace(h)
        h.warp(zone, x, z + 1, E.DIRS["UP"])
        h.step(90)
        o = G.obj_at(h, zone, oid)
        res = {"sibling": name, "zone": zone, "weekday": wday, "var_4094": var, "object": o and (o["x"], o["z"]),
               "map_script_ops": tr.ops()[:60]}
        if o is None:
            res["shot_missing"] = str(h.screenshot(f"ribbon_{variant}_missing"))
            return {**res, "verdict": "blocked", "reason": "sibling not shown"}
        o = stand_by(h, zone, oid)
        before = decrypted_blocks(party_raw(h, 0))
        bag0 = E.bag_items(h)
        m = tr.mark()
        shots = []
        h.press("A", after=10)
        res["end"] = talk_through(h, tr, shots=shots, tag=f"ribbon_{variant}", max_iter=60)
        res["ops"] = tr.names_since(m)[:80]
        res["bad_ops"] = tr.bad[:]
        res["gave_ribbon"] = "GiveRibbon" in res["ops"]
        h.step(300)
        res["shot_after"] = str(h.screenshot(f"ribbon_{variant}_after"))
        res["window_after"] = window_open(h)
        after = decrypted_blocks(party_raw(h, 0))
        res["lead_bytes_changed"] = [i for i in range(128) if before[i] != after[i]]
        res["bag_change"] = bag_change(bag0, E.bag_items(h))
        if mode in ("a", "b"):
            m2 = tr.mark()
            h.press(mode.upper(), after=200)
            res["press_ops"] = tr.names_since(m2)[:40]
            res["window_after_press"] = window_open(h)
            res["shot_press"] = str(h.screenshot(f"ribbon_{variant}_press"))
        res["walks"], p0, p1 = can_walk(h, "DOWN", 1)
        res["window_after_walk"] = window_open(h)
        res["shot_walk"] = str(h.screenshot(f"ribbon_{variant}_walk"))
        h.press("X", after=150)
        res["shot_x"] = str(h.screenshot(f"ribbon_{variant}_x"))
        res["x_menu_opens"] = not window_open(h) and E.screen_diff(Image_open(res["shot_walk"]), h.emu.screenshot())[0] > 0.02
        if res["x_menu_opens"]:                    # SAVE in the menu: does the save question appear?
            tr.mark()
            h.touch(*E.FIELD_MENU["save"], frames=8, after=200)
            res["shot_save"] = str(h.screenshot(f"ribbon_{variant}_save"))
            res["save_prompt"] = save_prompt(h)
            if res["save_prompt"] and name == "arthur":      # answer Yes: does the save finish?
                h.press("A", after=900)
                res["shot_saved"] = str(h.screenshot(f"ribbon_{variant}_saved"))
                h.press("A", after=60)
            for _ in range(3):
                h.press("B", after=60)
        res["var_4094_after"] = h.get_var(0x4094)
        res["shots"] = shots[-6:]
    return res


def Image_open(p):
    from PIL import Image
    return Image.open(p)


def obj_rom(zone, oid):
    """(x, z) of object <oid> in the zone's event data (CN ROM)."""
    import romdata as R
    z = R.read_json(str(E.WORK / "translate" / "bank_maps.json"))["_zones"][zone]
    o = next(o for o in R.parse_events(G.static()["events"][z["events_bank"]])["obj"] if o["id"] == oid)
    return o["x"], o["z"]


def judge_ribbon(res):
    """'contradicted' (the guide said it can freeze): the ribbon is given, the script dies on opcode 2009
    with its text left on screen, but the player walks, X opens the menu and SAVE asks to save; the control
    (daily gift) ends normally. 'confirmed' would be a real freeze (no walking, no menu)."""
    out = {}
    for name in SIBLINGS:
        r = res.get(name)
        if not r:
            continue
        if "gave_ribbon" not in r:
            out[name] = "blocked"
            continue
        died = r["gave_ribbon"] and r["bad_ops"] and r["bad_ops"][0]["op"] == 2009 and r["window_after"]
        usable = r["walks"] and r["x_menu_opens"] and r.get("save_prompt")
        out[name] = ("contradicted" if died and usable else "confirmed" if died and not r["walks"]
                     and not r["x_menu_opens"] else "observed")
    c = res.get("arthur_control")
    if c and (c["bad_ops"] or not c.get("save_prompt") or c["window_after"]):
        out["control"] = "control failed"
    v = set(out.values())
    return v.pop() if len(v) == 1 else json.dumps(out)


# ----------------------------------------------------------------------------- generic talk recipe
def session(rom, out, clock=CLOCK, flags=(), clear=(), vars=None, edit=None):
    """start_at with flags set (`flags`) and cleared (`clear`) in the save, vars, the clock pinned."""
    def ed(sf):
        for f in clear:
            sf.set_flag(f, False)
        if edit:
            edit(sf)
    return E.start_at(None, rom=rom, out=out, verbose=False, clock=clock, flags=flags, vars=vars or {}, edit=ed)


SIDES = {"DOWN": (0, 1, "UP"), "UP": (0, -1, "DOWN"), "LEFT": (-1, 0, "RIGHT"), "RIGHT": (1, 0, "LEFT")}


def goto_obj(h, zone, oid, side="DOWN"):
    """Warp next to object <oid> of <zone> (event data first, so the map loads; then its live position)."""
    x, z = obj_rom(zone, oid)
    dx, dz, face = SIDES[side]
    h.warp(zone, x + dx, z + dz, E.DIRS[face])
    h.step(60)
    o = G.obj_at(h, zone, oid)
    if o and (o["x"], o["z"]) != (x, z):
        h.warp(zone, o["x"] + dx, o["z"] + dz, E.DIRS[face])
        h.step(60)
    return o


def talk(h, tr, answers=(), battle=None, tag="t", shots=None, max_iter=150, start=None):
    """Press A (or run `start(h)`) and play the script through; returns what changed."""
    m, money0, bag0 = tr.mark(), G.money(h), E.bag_items(h)
    if start:
        start(h)
    else:
        h.press("A", after=10)
    end = talk_through(h, tr, answers=answers, battle=battle, shots=shots, tag=tag, max_iter=max_iter)
    return {"end": end, "ops": tr.ops(m)[:400], "msgs": tr.msgs(m), "money_before": money0, "money_after": G.money(h),
            "bag_change": bag_change(bag0, E.bag_items(h)), "mark": m}


def slim(r):
    """A result without the long op list (for reports); keeps the offsets as a compact list."""
    out = {k: v for k, v in r.items() if k not in ("ops",)}
    if "ops" in r:
        out["offsets"] = [o for _, o in r["ops"]][:200]
    return out


# ----------------------------------------------------------------------------- money and item cases
def case_fortune(rom, out, variant):
    """09 / known issues: Goldenrod fortune-teller (zone 206, object 0 = file 895 script 1). 'My ideal
    Pokemon' (first menu item) with $<variant>: L228 checks $300, L313 takes $10000."""
    money = int(variant)
    with session(rom, out, clear=(2289, 1617, 1618, 1287, 1288)) as h:
        tr = OpTrace(h)
        goto_obj(h, 206, 0)
        set_money(h, money)
        shots = []
        r = talk(h, tr, answers=[0], tag=f"fortune_{money}", shots=shots)
        r.update(flag_1617=h.get_flag(1617), shots=shots[-4:], shot_end=str(h.screenshot(f"fortune_{money}_end")))
    return slim(r)


def judge_fortune(res):
    lo, hi = res["5000"], res["20000"]
    ok = (lo["money_after"] == 0 and lo["bag_change"].get("247") == 1 and lo["flag_1617"]
          and hi["money_after"] == 10000 and hi["bag_change"].get("247") == 1)
    return "confirmed" if ok else "contradicted"


def case_ssanne_tm(rom, out, variant):
    """Known issues: S.S. Anne ship shop (zone 307, object 12 = file 156 script 20, hide flag 1440):
    menu item 2 'Frustration TM63, $4000' -> L4328 checks $400, L4349 takes $4000; item 348 given."""
    money = int(variant)
    with session(rom, out, clear=(1440,)) as h:
        tr = OpTrace(h)
        o = goto_obj(h, 307, 12)
        if o is None:
            return {"verdict": "blocked", "reason": "shop clerk not shown"}
        set_money(h, money)
        shots = []
        r = talk(h, tr, answers=[("touch", 192, 44)], tag=f"ssanne_tm_{money}", shots=shots,
                 start=lambda h: h.run_script(script_id=20))      # the clerk stands behind a counter
        r.update(shots=shots[-4:], reached_4349=tr.reached(4349, r["mark"]))
    return slim(r)


def judge_ssanne_tm(res):
    """Money only: the test save already holds 99 of every TM, so the bag count can't rise (the 'obtained'
    lines 25/88 are printed)."""
    lo, hi = res["1000"], res["5000"]
    ok = (lo["money_after"] == 0 and lo["reached_4349"] and 88 in lo["msgs"] and hi["money_after"] == 1000)
    return "confirmed" if ok else "contradicted"


def case_sprout(rom, out, variant):
    """Known issues: Sprout Tower 1F monk (zone 110, object 7 = file 16 script 8, flag 2107 clear): Yes to
    the offering -> L973 ... L1022 SubMoneyImmediate 3000 with no money check."""
    money = int(variant)
    with session(rom, out, clear=(2107,)) as h:
        tr = OpTrace(h)
        goto_obj(h, 110, 7)
        set_money(h, money)
        shots = []
        r = talk(h, tr, answers=[0], tag=f"sprout_{money}", shots=shots)
        r.update(flag_2107=h.get_flag(2107), shots=shots[-4:])
    return slim(r)


def judge_sprout(res):
    lo, hi = res["1000"], res["5000"]
    ok = lo["money_after"] == 0 and lo["flag_2107"] and hi["money_after"] == 2000 and hi["flag_2107"]
    return "confirmed" if ok else "contradicted"


def case_kiln(rom, out, variant):
    """Known issues: Charcoal Kiln apprentice (zone 164, object 5 = file 871 script 14, flag 1984 clear):
    Yes to 'Give him the TM for Cut?' -> Leek (259) given, HM01 (420) taken, no HasItem check."""
    with session(rom, out, clear=(1984,)) as h:
        tr = OpTrace(h)
        if variant == "nohm01":
            remove_item(h, 420)
        elif 420 not in E.bag_items(h):
            add_item(h, 420, 1, "tm")
        goto_obj(h, 164, 5)
        had = E.bag_items(h).get(420, 0)
        shots = []
        r = talk(h, tr, answers=[0], tag=f"kiln_{variant}", shots=shots)
        r.update(hm01_before=had, flag_1984=h.get_flag(1984), shots=shots[-4:])
    return slim(r)


def judge_kiln(res):
    a, b = res["hm01"], res["nohm01"]
    ok = (a["bag_change"].get("259") == 1 and a["bag_change"].get("420") == -1 and b["hm01_before"] == 0
          and b["bag_change"].get("259") == 1 and "420" not in b["bag_change"])
    return "confirmed" if ok else "contradicted"


def case_whirl(rom, out):
    """Known issues: Whirl Islands Challenge (zone 75, object 0 = file 872 script 3). Flags 2094 (challenge
    taken) and 2097 (northwest island) set, 2098-2100 clear: talk 1 (report), talk 2 (offer -> Yes), talk 3
    (report again). L2417-L2450 test 2097 four times."""
    with session(rom, out, flags=(2094, 2097), clear=(2098, 2099, 2100)) as h:
        tr = OpTrace(h)
        goto_obj(h, 75, 0)
        talks = []
        for k, ans in enumerate(([], [0], [])):
            r = talk(h, tr, answers=ans, tag=f"whirl_{k}")
            talks.append({"bag_change": r["bag_change"], "msgs": r["msgs"], "end": r["end"],
                          "flag_2094": h.get_flag(2094)})
        res = {"talks": talks, "shot": str(h.screenshot("whirl_end"))}
        prizes = [t for t in talks if t["bag_change"]]
        res["verdict"] = "confirmed" if len(prizes) == 2 and talks[1]["flag_2094"] else "contradicted"
    return res


def case_jirachi(rom, out, variant):
    """11 / known issues: the Frontier Access stone (zone 411, object 11 = file 81 script 10, hide flag 2350)
    after the final Hall of Fame (2261), var 0x408C = 17 (the legendary story finished). Repair with Yes
    until the Jirachi scene starts (L1985); variant nostar: no Star Pieces, star: 10 Star Pieces."""
    with session(rom, out, flags=(2261,), clear=(2350,), vars={0x408C: 17, 0x40E5: 1}) as h:   # 0x40E5: first visit seen
        tr = OpTrace(h)
        remove_item(h, 91)
        if variant == "star":
            add_item(h, 91, 10)
        goto_obj(h, 411, 11)
        reps, values = 0, []
        for k in range(12):
            m = tr.mark()
            r = talk(h, tr, answers=[0], tag=f"jirachi_{variant}_{k}", max_iter=60)
            if any(o == 1985 for _, o in r["ops"]):
                values.append(("scene", h.get_var(0x408C)))
                break
            reps += "AddVar" in tr.names_since(m)
            values.append((reps, h.get_var(0x408C), r["bag_change"]))
        res = {"repairs_before_scene": reps, "values": values, "star_pieces_left": E.bag_items(h).get(91, 0),
               "shot": str(h.screenshot(f"jirachi_{variant}_end"))}
    return res


def judge_jirachi(res):
    a, b = res["nostar"], res["star"]
    ok = (a["values"][-1][0] == "scene" and b["values"][-1][0] == "scene"
          and a["repairs_before_scene"] + 1 == 7 and b["repairs_before_scene"] + 1 == 7 and b["star_pieces_left"] == 3)
    return "confirmed" if ok else "contradicted"


def case_cutman(rom, out, variant):
    """Known issues: Frontier Access Cut man (zone 411, object 2 = file 81 script 6): without HM01 (420)
    L1057 jumps to L1491 inside the photographer's routine. Var 0x40E5 = 1: the first-visit scene is over."""
    with session(rom, out, vars={0x40E5: 1}) as h:
        tr = OpTrace(h)
        if variant == "nohm01":
            remove_item(h, 420)
        elif 420 not in E.bag_items(h):
            add_item(h, 420, 1, "tm")
        goto_obj(h, 411, 2)
        shots = []
        r = talk(h, tr, answers=[0, 0], tag=f"cutman_{variant}", shots=shots, max_iter=80)
        r.update(reached_1491=tr.reached(1491, r["mark"]), photo="CameronPhoto" in tr.names_since(r["mark"]),
                 shots=shots[-6:], walks=can_walk(h, "DOWN", 1)[0])
    return slim(r)


def judge_cutman(res):
    a, b = res["hm01"], res["nohm01"]
    ok = not a["reached_1491"] and 38 in a["msgs"] and b["reached_1491"] and b["end"] == "end"
    return "confirmed" if ok else "contradicted"


# ----------------------------------------------------------------------------- Radio Tower
def case_radio_quiz(rom, out, variant):
    """09 / known issues: radio quiz (zone 112, object 2 = file 29 script 3; flag 280 radio, 287 clear).
    Variant b: Yes, then B on all five menus; wrong: Yes, then answer '1' (wrong) to Q1 and the first
    choice after. Takeover NPCs hidden (flag 441) to keep the map under its sprite limit."""
    answers = [0] + (["B"] * 5 if variant == "b" else [0] * 5)     # touch menus: A takes the first button
    with session(rom, out, flags=(280, 441), clear=(287, 439)) as h:
        tr = OpTrace(h)
        goto_obj(h, 112, 2)
        shots = []
        r = talk(h, tr, answers=answers, tag=f"radio_quiz_{variant}", shots=shots)
        r.update(flag_287=h.get_flag(287), shots=shots[-8:],
                 menu_values={o: tr.cmp_at(o, r["mark"]) for o in (375, 467, 559, 651, 743)})
    return slim(r)


def judge_radio_quiz(res):
    """'contradicted' when B does not pass the quiz: on these touch menus B returns the last choice (3)."""
    b, w = res["b"], res["wrong"]
    if b["flag_287"] and 126 in b["msgs"]:
        return "confirmed"
    return "contradicted" if b["menu_values"]["375"] == [3] and 125 in b["msgs"] and not w["flag_287"] else "blocked"


def case_buena(rom, out):
    """09 / known issues: Buena's right-answer path (file 29 L4353) with var 0x413A = 1 (the new total 2 is
    no prize total): which lines does the scene print? Run from L4353 next to Buena (object 10)."""
    with session(rom, out, flags=(441,), clear=(439,), vars={0x413A: 1}) as h:
        tr = OpTrace(h)
        goto_obj(h, 112, 10)
        shots = []
        r = talk(h, tr, tag="buena", shots=shots, start=lambda h: G.run_from(h, 29, 18, 4353))
        r.update(var_413a=h.get_var(0x413A), shots=shots)
        r["verdict"] = "confirmed" if 32 in r["msgs"] and 87 not in r["msgs"] and r["var_413a"] == 2 else "contradicted"
    return slim(r)


# ----------------------------------------------------------------------------- battles: team data
def _battle_parties(rom, out, tag, prog, trainer):
    import romdata as R
    td = R.parse_trdata(G.static()["trdata"][trainer])
    team = [(m["species"], m.get("level")) for m in R.parse_trpoke(G.static()["trpoke"][trainer], td["count"])]
    with session(rom, out) as h:
        log = K.SceneLog(h)
        mine = [m["species"] for m in h.party()]
        h.run_script(program=E.script_bytes(*prog))
        shots = []
        for k in range(14):
            h.step(45)
            shots.append(str(h.screenshot(f"{tag}_intro_{k:02d}")))
        parties = [p["mons"] for p in K.find_parties(h)]
        foe = [p for p in parties if [m["species"] for m in p] == [t[0] for t in team]]
        cries = [e["species"] for e in log.events if e["t"] == "cry" and e["species"] not in mine]
    return {"rom_team": team, "foe_party_in_ram": foe[:1], "copies": len(foe), "foe_sendout_cries": cries,
            "shots": shots}


def case_morty(rom, out):
    """Known issues: Morty's Gym team (trainer 31, `TrainerBattle 31 31` as in file 918): the levels of the
    party the battle builds."""
    res = _battle_parties(rom, out, "morty", [("LockAll",), ("TrainerBattle", 31, 31, 0, 0), ("ReleaseAll",),
                                              ("End",)], 31)
    lv = [m.get("level") for m in (res["foe_party_in_ram"] or [[]])[0]]
    res["levels_in_battle"] = lv
    res["verdict"] = "confirmed" if sorted(lv) == [1, 1, 1, 80, 80, 80] else "contradicted" if lv else "blocked"
    return res


def case_chuck(rom, out):
    """11: Chuck's badge battle `TrainerBattle 34 34` (file 874): a Double Battle with one copy of his
    team; the first two foe send-outs are his first two Pokemon."""
    res = _battle_parties(rom, out, "chuck", [("LockAll",), ("TrainerBattle", 34, 34, 0, 0), ("ReleaseAll",),
                                              ("End",)], 34)
    team = [t[0] for t in res["rom_team"]]
    res["verdict"] = ("confirmed" if len(team) == 4 and res["copies"] >= 1 and res["foe_sendout_cries"][:2] == team[:2]
                      else "contradicted")
    return res


def case_e4names(rom, out, variant):
    """Known issues: Elite Four practice rematches: Agatha's room starts trainer 703, Lance's 705
    (`TrainerBattle <id> 0 0 0`). The battle intro names the opponent: screenshots; the trainer's name is
    read from the ROM's trainer-name bank for comparison."""
    tid = int(variant)
    res = _battle_parties(rom, out, f"e4_{tid}", [("LockAll",), ("TrainerBattle", tid, 0, 0, 0), ("ReleaseAll",),
                                                  ("End",)], tid)
    res["verdict"] = "observed"
    return res


# ----------------------------------------------------------------------------- visibility and state cases
def case_misty_cape(rom, out, variant):
    """Known issues: Misty's Cerulean Cape photo (Route 25, zone 29, object 35, hide flag 598) after the final
    Hall of Fame (2261) with no romance (1645 clear), hour <variant>: is she there?"""
    hour = int(variant)
    with session(rom, out, clock=datetime.datetime(2026, 10, 9, hour, 30), flags=(2261,), clear=(1645, 598)) as h:
        tr = OpTrace(h)
        h.warp(29, 1418, 40, E.DIRS["RIGHT"])
        h.step(90)
        o = G.obj_at(h, 29, 35)
        res = {"hour": hour, "misty_visible": o is not None, "flag_598": h.get_flag(598),
               "hour_compares": [v for i, v in tr.cmp.items()], "shot": str(h.screenshot(f"misty_cape_{hour:02d}"))}
    return res


def judge_misty_cape(res):
    vis = [res[k]["misty_visible"] for k in res if k != "verdict" and isinstance(res[k], dict)]
    return "confirmed" if vis and not any(vis) else "contradicted"


def case_petrel(rom, out, variant):
    """Known issues: Petrel's Chatot (Team Rocket HQ B2F, zone 248, object 31 = file 90 script 6, hide flag
    500). Variant set: 500 set -> hidden?; clear: shown, talk -> does the catch offer (L2874) run?"""
    on = variant == "set"
    with session(rom, out, flags=(500,) if on else (), clear=() if on else (500,)) as h:
        tr = OpTrace(h)
        x, z = obj_rom(248, 31)
        h.warp(248, x, z + 1, E.DIRS["UP"])
        h.step(90)
        o = G.obj_at(h, 248, 31)
        res = {"flag_500": on, "chatot_visible": o is not None, "shot": str(h.screenshot(f"petrel_{variant}"))}
        if o is not None:
            goto_obj(h, 248, 31)
            r = talk(h, tr, answers=[0], battle="flee", tag=f"petrel_{variant}", max_iter=60)
            res.update(talk_end=r["end"], msgs=r["msgs"], offer=any(o_ == 2874 for _, o_ in r["ops"]),
                       wild_battle="WildBattle" in [n for n, _ in r["ops"]])
    return res


def judge_petrel(res):
    s, c = res["set"], res["clear"]
    ok = not s["chatot_visible"] and c["chatot_visible"] and not c.get("wild_battle")
    return "confirmed" if ok else "contradicted"


def case_satsuki(rom, out):
    """11 / known issues: Satsuki (file 924) with var 0x40A9 = 11 and flag 265 clear: the short menu (L4915),
    'I want to see Lugia' -> L4968: message 87 (Clear Bell) and var 0x40A9 = 7. Run from L4299."""
    with session(rom, out, clear=(265,), vars={0x40A9: 11}) as h:
        tr = OpTrace(h)
        h.warp(86, 8, 10, E.DIRS["UP"])
        h.step(60)
        shots = []
        r = talk(h, tr, answers=[0], tag="satsuki", shots=shots, start=lambda h: G.run_from(h, 924, 1, 4299))
        r.update(var_40a9=h.get_var(0x40A9), short_menu=tr.reached(4915, r["mark"]), shots=shots[-4:])
        r["verdict"] = "confirmed" if r["short_menu"] and 87 in r["msgs"] and r["var_40a9"] == 7 else "contradicted"
    return slim(r)


def case_entei(rom, out):
    """08: Entei in the dream world (zone 326, object 22 = file 51 script 8, hide flag 2318): Yes -> wild
    Entei; its level; flee (CheckBattleWon counts a flee as a win) -> flag 2318 set, Entei gone."""
    with session(rom, out, flags=(1904,), clear=(2318,)) as h:      # 1904 hides the story actors on that spot
        G.lead(h, FAST_LEAD)
        tr = OpTrace(h)
        wl = E.WildLog(h)
        o = goto_obj(h, 326, 22, side="RIGHT")
        if o is None:
            return {"verdict": "blocked", "reason": "Entei (object 22) not shown"}
        r = talk(h, tr, answers=[0], battle=None, tag="entei", max_iter=100)
        parties = [p["mons"] for p in K.find_parties(h)] if r["end"] == "battle" else []
        shot_b = str(h.screenshot("entei_battle"))
        fled = h.flee(battle_menu_wait=60) if r["end"] == "battle" else None
        end2 = talk_through(h, tr, max_iter=60)
        h.step(120)
        foe = [m for p in parties for m in p if m["species"] == 244]
        wild = [{"species": w["species"], "level": (foe[0]["level"] if foe else None)} for w in wl.rows]
        res = {"entei_before": (o["x"], o["z"]), "wild": wild, "talk_end": r["end"], "fled": fled, "end2": end2,
               "flag_2318": h.get_flag(2318), "entei_after": G.obj_at(h, 326, 22) is not None,
               "shot_battle": shot_b, "shot": str(h.screenshot("entei_after"))}
        res["verdict"] = ("confirmed" if wild and wild[0]["species"] == 244 and wild[0]["level"] == 90
                          and res["flag_2318"] and not res["entei_after"] else "contradicted" if wild else "blocked")
    return res


def case_bugsy(rom, out, variant):
    """Known issues: Bugsy's rematch rule (zone 180, object 5 = file 866 script 2; badge 9 clear): Yes ->
    L367 compares var 0x8005 with 5/6 (refusal L4470). The value read is logged. Variant fresh: talk right
    after loading; after5: a one-off script `SetVar 0x8005 5` runs first (a leftover from another script)."""
    with session(rom, out, flags=(2031,)) as h:          # 2031: Bugsy is in his Gym (map script L76)
        G.set_badge(h, 9, False)
        tr = OpTrace(h)
        goto_obj(h, 180, 5)
        if variant == "after5":
            h.run_script(program=E.script_bytes(("SetVar", 0x8005, 5), ("End",)))
            h.step(60)
            goto_obj(h, 180, 5)
        shots = []
        r = talk(h, tr, answers=[0], tag=f"bugsy_{variant}", shots=shots, max_iter=40, battle=None)
        r.update(value_at_367=tr.cmp_at(367, r["mark"]), refused=tr.reached(4470, r["mark"]),
                 party_count=len(h.party()), shots=shots[-4:])
    return slim(r)


def judge_bugsy(res):
    f, a = res["fresh"], res["after5"]
    ok = f["value_at_367"] == [0] and not f["refused"] and f["party_count"] > 4
    return ("confirmed" if ok and a["value_at_367"] != [5] else "contradicted" if not ok
            else "confirmed (leftover reaches it: refused=%s)" % a["refused"])


def case_magcargo(rom, out):
    """Known issues: Pokemon Tower Magcargo (file 17 L2519: TouchscreenMenuShow, PlayCry, WildBattle 219; a
    loss jumps back to L2519). Splash-only party (weak_party), run from L2519, lose. Then 3000 frames with
    A/B/START now and then: does a second WildBattle start, does the field come back, where is the CPU?"""
    with session(rom, out) as h:
        G.weak_party(h)
        tr = OpTrace(h)
        h.warp(155, 17, 12, E.DIRS["UP"])
        h.step(60)
        m = tr.mark()
        G.run_from(h, 17, 1, 2519)
        h.run_until(lambda h: h.on_screen("battle_menu"), 3000, every=10)
        shot_battle = str(h.screenshot("magcargo_battle"))
        G.lose_battle(h, max_steps=300)
        samples = []
        for k in range(20):
            h.step(150)
            h.press(("A", "B", "START", "A")[k % 4], after=0)
            samples.append({"field": h.in_field(), "pc": hex(h.reg.pc), "battle_menu": h.on_screen("battle_menu")})
        names = tr.names_since(m)
        res = {"wildbattles": names.count("WildBattle"), "after_loss_ops": [o for o in tr.ops(m)][-8:],
               "whiteout": "WhiteOut" in names, "samples": samples[::4], "field_back": any(x["field"] for x in samples),
               "shot_battle": shot_battle, "shot_after": str(h.screenshot("magcargo_after"))}
        res["verdict"] = ("confirmed" if res["wildbattles"] >= 2 else
                          "contradicted" if not res["field_back"] and not res["whiteout"] else "observed")
    return res


def case_dance(rom, out, variant):
    """13: Mt. Moon entrance (map 448, file 8 script 1): the Square doorway moves to the dance map (513,
    MoveWarp at L159/L96) on Monday 20-23 h / Tuesday 0-3 h unless daily flag 2741 is set.
    Variants: tue01 (2741 clear), tue05, mon22set (2741 set), daychange (start Monday 22:00 with 2741 set,
    then the clock goes to Tuesday 00:30 in game; re-enter)."""
    clocks = {"tue01": datetime.datetime(2026, 10, 6, 1, 0), "tue05": datetime.datetime(2026, 10, 6, 5, 0),
              "mon22set": datetime.datetime(2026, 10, 5, 22, 0), "daychange": datetime.datetime(2026, 10, 5, 22, 0)}
    with session(rom, out, clock=clocks[variant]) as h:
        if variant in ("mon22set", "daychange"):       # seen today (the boot's day change clears daily flags)
            h.set_flag(2741)
        else:
            h.set_flag(2741, False)
        tr = OpTrace(h)
        h.warp(448, 5, 15, E.DIRS["UP"])
        h.step(90)
        res = {"variant": variant, "flag_2741_before": h.get_flag(2741), "movewarp": "MoveWarp" in tr.names_since()}
        if variant == "daychange":
            h.set_clock(datetime.datetime(2026, 10, 6, 0, 30))
            h.step(600)
            m = tr.mark()
            h.warp(448, 5, 15, E.DIRS["UP"])
            h.step(90)
            res.update(flag_2741_after=h.get_flag(2741), movewarp_after="MoveWarp" in tr.names_since(m))
        res["shot"] = str(h.screenshot(f"dance_{variant}"))
    return res


def judge_dance(res):
    ok = (res["tue01"]["movewarp"] and not res["tue05"]["movewarp"] and not res["mon22set"]["movewarp"]
          and res["daychange"].get("movewarp_after") and not res["daychange"].get("flag_2741_after"))
    return "confirmed" if ok else "contradicted"


def case_blackthorn(rom, out, variant):
    """Known issues: Blackthorn Gym trainers (zone 141): the entrance trainer (object 1 at 11,62 = file 939
    script 7, also its coord trigger) battles (trainer 932) only when var 0x40A3 = 1; otherwise L14262,
    msg 13. Variant var5 (after the MooMoo farmer's Yes) / var1: talk to him from the south."""
    val = int(variant[3:])
    with session(rom, out, vars={0x40A3: val}) as h:
        tr = OpTrace(h)
        goto_obj(h, 141, 1)
        log = K.SceneLog(h)
        r = talk(h, tr, tag=f"blackthorn_{variant}", max_iter=40)
        res = {"var": val, "msgs": r["msgs"], "end": r["end"], "reached_14262": tr.reached(14262, r["mark"]),
               "trainer_battles": [e["trainers"] for e in log.events if e["t"] == "trainer_battle"],
               "shot": str(h.screenshot(f"blackthorn_{variant}"))}
    return res


def judge_blackthorn(res):
    a, b = res["var5"], res["var1"]
    ok = a["reached_14262"] and 13 in a["msgs"] and not a["trainer_battles"] and b["trainer_battles"]
    return "confirmed" if ok else "contradicted"


def case_partner_room(rom, out, variant):
    """11: Battle Tower partner room (zone 271): which partners stand there. Variant after39: flags 603
    (Yellow) and 336 (Misty) set, as the Route 39 scene leaves them; base: as in the test save."""
    with session(rom, out, flags=(603, 336) if variant == "after39" else ()) as h:
        h.warp(271, 7, 12, E.DIRS["UP"])
        h.step(90)
        objs = K.live_objects(h, 271)
        return {"visible": sorted((o["id"], o["script"]) for o in objs.values()),
                "flags": {f: h.get_flag(f) for f in (603, 336, 685)}, "shot": str(h.screenshot(f"partner_{variant}"))}


def case_island_forest(rom, out, variant):
    """Known issues: Island Forest (map 492) is inside the Ruins of Alph encounter gate (ov2 0x02248420:
    maps 490-492 need one of flags 2423-2426). Pace on two tall-grass tiles for 400 steps with a Lv100
    Ninjask lead (flees every battle); count the wild Pokemon built. Variant none: flags 2423-2426 clear;
    panel: 2423 set."""
    with session(rom, out, flags=(2423,) if variant == "panel" else (), clear=(2424, 2425, 2426) +
                 (() if variant == "panel" else (2423,))) as h:
        G.lead(h, FAST_LEAD)
        g = E.MapGrid(h.rom, 492)
        grass = g.find(E.TILE_GRASS)
        pair = next(((x, y) for x, y in grass if (x + 1, y) in set(grass)), None)
        if pair is None:
            return {"verdict": "blocked", "reason": "no two grass tiles side by side"}
        h.warp(492, pair[0], pair[1], E.DIRS["RIGHT"])
        h.step(60)
        wl = E.WildLog(h)
        steps, battles = 0, 0
        while steps < 400:
            for d in ("RIGHT", "LEFT"):
                h.walk(d, 1)
                steps += 1
                if not h.in_field():
                    battles += 1
                    h.flee(battle_menu_wait=200)
                    h.step(60)
        res = {"variant": variant, "start": pair, "pos": h.position(), "steps": steps, "battles": battles,
               "wild": [w["species"] for w in wl.rows], "flags": {f: h.get_flag(f) for f in (2423, 2424, 2425, 2426)},
               "shot": str(h.screenshot(f"island_forest_{variant}"))}
    return res


def judge_island_forest(res):
    a, b = res["none"], res["panel"]
    return "confirmed" if not a["wild"] and b["wild"] else "contradicted" if a["wild"] else "blocked"


def case_weezing_dex(rom, out, variant):
    """Known issues (D-1333/D-1550): the expedition's `SetFlag 4461` sets the caught bit of No. 110 Weezing
    without its seen bit. Dex filled (RAM) for 1-130 except 110; variant flag: 110's bits cleared, then the
    real command `SetFlag 4461` runs; unseen: 110 left clear (control); seen: 110 seen + caught (control).
    Then the Pokedex list at No. 110 and its entry page are screenshotted."""
    import emu_dex as D
    with session(rom, out) as h:
        D.fill_dex_ram(h, n=130)
        base = h.save + 0x10
        i, k = (110 - 1) // 8, (110 - 1) % 8
        for off in (D.CAUGHT, D.SEEN):
            if variant != "seen":
                h.w8(base + off + i, h.u8(base + off + i) & ~(1 << k))
        if variant == "flag":
            h.run_script(program=E.script_bytes(("SetFlag", 4461), ("End",)))
            h.step(60)
        bits = {"caught": bool(h.u8(base + D.CAUGHT + i) >> k & 1), "seen": bool(h.u8(base + D.SEEN + i) >> k & 1)}
        D.open_dex_list(h, fill=False)
        shown = D.goto(h, 110)
        D.settle_top(h)
        res = {"variant": variant, "bits_110": bits, "list_number": shown,
               "shot_list": str(h.screenshot(f"weezing_{variant}_list"))}
        if shown == 110:
            img = D.detail_page(h, "info")
            p = out / f"weezing_{variant}_entry.png"
            img.save(p)
            res["shot_entry"] = str(p)
    return res


def empty_mon():
    """A party slot as the game's ZeroMonData leaves it: all-zero data encrypted with PID 0 / checksum 0."""
    return (struct.pack("<IHH", 0, 0, 0) + struct.pack("<64H", *E._prng_stream(0, 64)) +
            struct.pack("<50H", *E._prng_stream(0, 50)))


def one_mon_party(h):
    """Party of one, as after depositing the others: count 1 and slots 1-5 emptied (empty_mon)."""
    a = h.array(E.ARR_PARTY)
    for slot in range(1, 6):
        h.write(a + 8 + 236 * slot, empty_mon())
    h.w32(a + 4, 1)


def case_white_flute(rom, out, variant):
    """09: Dept. Store 6F (zone 196, file 901): the shoppers' battle `TrainerBattle 777 778 0 0` (L3087).
    Variant one: a one-Pokemon party (one_mon_party); full: the test save's six (control). Does the battle
    start, against both trainers; what stands on the player's side; does one turn (FIGHT, first move) play?"""
    import romdata as R
    teams = {}
    for t in (777, 778):
        td = R.parse_trdata(G.static()["trdata"][t])
        teams[t] = [m["species"] for m in R.parse_trpoke(G.static()["trpoke"][t], td["count"])]
    with session(rom, out) as h:
        if variant == "one":
            one_mon_party(h)
        h.warp(196, 4, 8, E.DIRS["UP"])
        h.step(60)
        log = K.SceneLog(h)
        G.run_from(h, 901, 11, 3087)
        h.run_until(lambda h: h.on_screen("battle_menu"), 3000, every=10)
        parties = [[m["species"] for m in p["mons"]] for p in K.find_parties(h)]
        res = {"variant": variant, "party_count": h.u32(h.array(E.ARR_PARTY) + 4), "battle_menu": h.on_screen("battle_menu"),
               "trainer_battles": [e["trainers"] for e in log.events if e["t"] == "trainer_battle"],
               "teams": teams, "both_teams_in_ram": sorted({tuple(p) for p in parties if p in teams.values()}),
               "shot": str(h.screenshot(f"white_flute_{variant}_battle"))}
        try:
            res["turn"] = G.turn(h, max_frames=2400)
        except RuntimeError as e:
            res["turn"] = "stuck: " + str(e)
        res["pc_after_turn"] = hex(h.reg.pc)
        res["shot_turn"] = str(h.screenshot(f"white_flute_{variant}_turn"))
    return res


def judge_white_flute(res):
    """The guide said: no party-size check, so one Pokemon faces both. 'contradicted' when the one-Pokemon
    battle starts (both teams) but the first turn hangs while the six-Pokemon control plays it."""
    o, f = res["one"], res["full"]
    started = o["battle_menu"] and len(o["both_teams_in_ram"]) == 2
    if started and o["turn"] in ("menu", "field"):
        return "confirmed"
    return "contradicted" if started and str(o["turn"]).startswith("stuck") and f["turn"] in ("menu", "field") else "blocked"


def case_moomoo(rom, out, variant):
    """10 / known issues: the MooMoo farmer (zone 215, object 0 = file 251 script 1) with the Miltank sick
    again (flag 744 clear): variant cured (Dream World done, 2289 set) -> L903, no investigation offer;
    fresh (2289 clear) -> L925, the investigation chain."""
    with session(rom, out, flags=(2289,) if variant == "cured" else (), clear=(744,) + (() if variant == "cured" else (2289,))) as h:
        tr = OpTrace(h)
        goto_obj(h, 215, 0)
        r = talk(h, tr, answers=[1, 1, 1], tag=f"moomoo_{variant}", max_iter=60)
        res = {"variant": variant, "msgs": r["msgs"], "reached_903": tr.reached(903, r["mark"]),
               "reached_925": tr.reached(925, r["mark"]), "end": r["end"]}
    return res


def judge_moomoo(res):
    c, f = res["cured"], res["fresh"]
    return "confirmed" if c["reached_903"] and not c["reached_925"] and f["reached_925"] else "contradicted"


def case_petrel_scene(rom, out, variant):
    """12: the Petrel scene in the lake guardian's house (zone 294, file 935 script 2, a frame script): does
    it start on entry when var 0x40B2 = 4 (set by the League HQ, file 31 L4541)? Variant var4 / var3."""
    val = int(variant[3:])
    import romdata as R
    z = R.read_json(str(E.WORK / "translate" / "bank_maps.json"))["_zones"][294]
    w = R.parse_events(G.static()["events"][z["events_bank"]])["warp"][0]
    with session(rom, out, vars={0x40B2: val}) as h:
        tr = OpTrace(h)
        h.warp(294, w["x"], w["z"] - 1, E.DIRS["UP"])
        h.step(240)
        res = {"var": val, "scene_started": tr.reached(111) and tr.reached(135), "msgs": tr.msgs()[:5],
               "shot": str(h.screenshot(f"petrel_scene_{variant}"))}
    return res


def judge_petrel_scene(res):
    return "confirmed" if res["var4"]["scene_started"] and not res["var3"]["scene_started"] else "contradicted"


# ----------------------------------------------------------------------------- registry, runner, suite
# name -> (function, variants or None, judge(results by variant) or None)
CASES = {
    "ribbon": (case_ribbon, tuple(SIBLINGS) + ("arthur_control", "arthur_a", "arthur_b"), judge_ribbon),
    "fortune": (case_fortune, ("5000", "20000"), judge_fortune),
    "ssanne_tm": (case_ssanne_tm, ("1000", "5000"), judge_ssanne_tm),
    "sprout": (case_sprout, ("1000", "5000"), judge_sprout),
    "kiln": (case_kiln, ("hm01", "nohm01"), judge_kiln),
    "whirl": (case_whirl, None, None),
    "jirachi": (case_jirachi, ("nostar", "star"), judge_jirachi),
    "cutman": (case_cutman, ("hm01", "nohm01"), judge_cutman),
    "radio_quiz": (case_radio_quiz, ("b", "wrong"), judge_radio_quiz),
    "buena": (case_buena, None, None),
    "morty": (case_morty, None, None),
    "chuck": (case_chuck, None, None),
    "e4names": (case_e4names, ("703", "705"), None),
    "misty_cape": (case_misty_cape, ("12", "14", "15"), judge_misty_cape),
    "petrel": (case_petrel, ("set", "clear"), judge_petrel),
    "satsuki": (case_satsuki, None, None),
    "entei": (case_entei, None, None),
    "bugsy": (case_bugsy, ("fresh", "after5"), judge_bugsy),
    "magcargo": (case_magcargo, None, None),
    "dance": (case_dance, ("tue01", "tue05", "mon22set", "daychange"), judge_dance),
    "blackthorn": (case_blackthorn, ("var5", "var1"), judge_blackthorn),
    "partner_room": (case_partner_room, ("base", "after39"), None),
    "island_forest": (case_island_forest, ("none", "panel"), judge_island_forest),
    "weezing_dex": (case_weezing_dex, ("flag", "unseen", "seen"), None),
    "white_flute": (case_white_flute, ("one", "full"), judge_white_flute),
    "moomoo": (case_moomoo, ("cured", "fresh"), judge_moomoo),
    "petrel_scene": (case_petrel_scene, ("var4", "var3"), judge_petrel_scene),
}


def run_cases(roms, cases, out, jobs=6, variants=None):
    """Like emu_guide0107.run_cases, for this module's CASES (children run `guide0813 --child`).
    variants: {case: (variant, ...)} to run fewer variants than CASES lists (the suite)."""
    from concurrent.futures import ThreadPoolExecutor
    variants = variants or {}
    todo = [(c, v, l) for c in cases for v in (variants.get(c) or CASES[c][1] or [None]) for l in roms]

    def run(job):
        c, v, l = job
        try:
            return c, v, l, E.run_child(["guide0813", "--child", c + (":" + v if v else ""), "--rom", roms[l],
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


# Cheap deterministic cases for `emu_harness.py suite` and the verdict each must keep (the hack's behaviour as
# observed on 2026-10-06; 'contradicted' means the guide's old wording was wrong, not a failure).
SUITE_EXPECT = {"ribbon": "contradicted", "magcargo": "contradicted", "white_flute": "contradicted",
                "radio_quiz": "contradicted", "fortune": "confirmed", "sprout": "confirmed", "kiln": "confirmed",
                "whirl": "confirmed", "bugsy": "confirmed", "dance": "confirmed", "morty": "confirmed",
                "blackthorn": "confirmed"}
SUITE_VARIANTS = {"ribbon": ("arthur", "arthur_control")}


def suite_check(rom, out):
    """emu_harness.py suite: the SUITE_EXPECT cases on one ROM; pass when every verdict is the expected one."""
    report = run_cases({"x": rom}, list(SUITE_EXPECT), out, jobs=6, variants=SUITE_VARIANTS)
    got = {c: report[c]["x"].get("verdict") for c in SUITE_EXPECT}
    return got == SUITE_EXPECT, {"verdicts": got}


def cmd(a):
    """emu_harness.py guide0813: each case/variant and ROM in its own child process; one JSON report."""
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
    path = Path(a.out) / "guide08_13" / ("report_" + name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"report": str(path)}))
    return 0
