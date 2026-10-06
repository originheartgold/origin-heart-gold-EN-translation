#!/usr/bin/env python3
"""emu_verify - recipes for the open verify-in-game records of the decision register
(`emu_harness.py verify`).

Translators left questions of the form "check in game how this renders / whether it is shown / what it
prints" (subtype verify-in-game). Each case here reaches the real screen or scene line on the untouched
Chinese ROM and the English build and keeps CN|EN screenshot pairs, so the question can be settled by
looking, plus what the game did (messages printed by the script, OpTrace; flags, bag, party):

- `line` cases run the hack's own script bytes from the message command (or a few commands before it, for
  the buffers it needs) inside the right map: warp into the zone, GoTo the label (emu_hackbugs.run_from_with),
  press A through the pages and screenshot each page of the message. The window, the 200 % size and the
  colours are the scene's own; camera moves and people placed by earlier parts of the scene are not.
- `never` cases run a scene from the message before a placeholder line and log every message the script
  prints until the one after it (is the placeholder ever printed?), with a static scan of the script file.
- the other cases drive a menu, a statue, a trade or a phone-free NPC and read back what happened.

    .venv/bin/python work/tools/emu_harness.py verify [--case bigtext,never,statue:badge,...] [--lang cn|en|both]

Screenshots: <out>/verify/<lang>/; pairs: <out>/verify/pairs/<case>_<variant>.png; report
<out>/verify/report_<cases>.json. CASES lists each case with the record(s) it settles.
"""
import json
from pathlib import Path

import emu_harness as E
import emu_skitty as K
import emu_guide0107 as G
import emu_guide0813 as M
import emu_hackbugs as B

CLOCK = G.CLOCK                                   # Friday 2026-10-09 12:00
MSG_OPS = {"NPCMsg": 1, "NonNPCMsg": 1, "GenderMsgBox": 2}   # message commands: u8 id(s) after the opcode
TOP = (0, 0, 256, 192)
TOP_ONLY = {"bigtext", "never", "lines"}            # cases whose pairs show only the top screen


# ----------------------------------------------------------------------------- helpers
def out_dir(out, rom):
    d = Path(out).resolve() / "verify" / K.lang_of(rom)
    d.mkdir(parents=True, exist_ok=True)
    return d


def msg_ids(row):
    """Message id(s) a traced message command prints (u8 arguments)."""
    n = MSG_OPS.get(row[0])
    return list(row[4][:n]) if n else []


def printed(tr, since=0):
    """Message ids printed by message commands since trace row <since>, in order."""
    out = []
    for r in tr.rows[since:]:
        out += msg_ids(r)[:1] if r[0] != "GenderMsgBox" else [msg_ids(r)]
    return out


def top_bytes(h):
    return h.emu.screenshot().crop(TOP).tobytes()


def capture_message(h, tr, targets, tag, max_iter=60, settle=30):
    """Press A through the running script until a message command printing one of <targets> has run and
    finished; screenshot every distinct page of it (stable top screen). Returns (shots, printed ids, how it
    ended: 'done', 'end' (script ended first), 'bad_op' or 'timeout')."""
    shots, prev, nbad, hit = [], None, len(tr.bad), None
    for i in range(max_iter):
        M.wait_stable(h, max_frames=600)
        if len(tr.bad) > nbad:
            return shots, printed(tr), "bad_op"
        rows = tr.rows
        if hit is None:
            for k, r in enumerate(rows):
                ids = msg_ids(r)
                if ids and any(t in ids for t in targets):
                    hit = k
                    break
        if hit is not None:
            img = top_bytes(h)
            if img != prev:
                shots.append(str(h.screenshot(f"{tag}_p{len(shots) + 1}")))
                prev = img
            if len(rows) > hit + 1:               # the next command runs: the message has finished
                return shots, printed(tr), "done"
        elif rows and rows[-1][0] == "End" and tr.idle_frames() > 120:
            return shots, printed(tr), "end"
        h.press("A", after=settle)
    return shots, printed(tr), "timeout"


def hide_flags(zone):
    """The hide flags of every flag-gated person of <zone>. The test saves have many of them clear, and some
    maps (Route 2, Route 3, Route 34, Mt. Moon Square) then load more people than the sprite table holds and
    crash on entry, as Goldenrod does (D-1547); the scene lines don't need the people."""
    return tuple(sorted({o["flag"] for o in B.objects(zone) if o.get("flag")}))


def scene_line(rom, out, zone, file, label, targets, pre=(), tag="line", flags=(), clear=(), vars=None,
               at=None, setup=None, hide=False):
    """Warp into <zone>, run its script file <file> from byte <label> (after the commands <pre>) and capture
    the pages of message(s) <targets>. at=(x, z): where to stand (default: below the zone's first object).
    hide: set the zone's hide flags first (see hide_flags)."""
    o = out_dir(out, rom)
    if hide:
        flags = tuple(flags) + hide_flags(zone)
    with M.session(rom, o, clock=CLOCK, flags=flags, clear=clear, vars=vars) as h:
        if setup:
            setup(h)
        if at:
            B.enter(h, zone, at[0], at[1])
        else:
            B.enter(h, zone)
        tr = M.OpTrace(h)
        B.run_from_with(h, file, label, pre=pre)
        shots, ids, end = capture_message(h, tr, targets, f"{tag}")
        return {"zone": zone, "file": file, "label": label, "targets": list(targets), "printed": ids, "end": end,
                "shots": shots, "bad": tr.bad[:3]}


def never_case(rom, out, zone, file, label, until, placeholder, tag, max_iter=80):
    """Run <file> from <label> in <zone>, press through until message <until> has printed; return every
    message id printed and whether <placeholder> was among them."""
    o = out_dir(out, rom)
    with M.session(rom, o, clock=CLOCK) as h:
        B.enter(h, zone)
        tr = M.OpTrace(h)
        B.run_from_with(h, file, label)
        shots, ids, end = capture_message(h, tr, [until], tag, max_iter=max_iter)
        flat = [i for x in ids for i in (x if isinstance(x, list) else [x])]
        return {"printed": ids, "end": end, "placeholder_printed": placeholder in flat, "shots": shots[-2:],
                "static_refs": static_refs(file, placeholder)}


def static_refs(file, msg):
    """Offsets of commands in script file <file> that name message <msg>: message and menu commands with <msg>
    as first argument, and SetVar of a special var to <msg> where the file prints that var (a *MsgVar command
    or MsgBoxExtern)."""
    import romdata as R
    names = M.cmd_names()
    _, ins = R.disasm(G.static()["scripts"][file])
    msg_vars = {a[0] for op, a, n, t in ins.values()
                if a and ("MsgVar" in names.get(op, "") or names.get(op, "") == "MsgBoxExtern")}
    out = []
    for pc, (op, a, n, t) in sorted(ins.items()):
        name = names.get(op, "")
        if ("Msg" in name or "Menu" in name or "YesNo" in name) and a and a[0] == msg:
            out.append((pc, name))
        if name == "SetVar" and a[0] in msg_vars and a[1] == msg:
            out.append((pc, "SetVar"))
    return out


# ----------------------------------------------------------------------------- strings the game reads
MSG_READERS = {0x0200BB0C: "18b581b0041c",    # ReadMsgDataIntoString(MsgData *, id, String *)
               0x0200BB40: "08b5031c1888",    # NewString_ReadMsgData(MsgData *, id)
               0x0200BB94: "18b581b0041c"}    # the same for a temporary MsgData (0x0200BBC8)
# NewMsgDataFromNarc (arm9 0x0200BA98; type, narc, file, heap) stores the NARC id at MsgData +4 and the file
# (message bank) at +6 in every mode, so the readers' r0 tells which bank a string comes from. a027 is NARC 27.
MSG_NARC_A027 = 27


class MsgLog:
    """Every message string the game reads through the MsgData readers: rows (narc, bank, id, frame). Script
    messages, menus, app screens (bag, Pokégear, move relearner, ...) all read their text this way; a string
    that is never read is never shown."""

    def __init__(self, h, limit=50000, check=True):
        self.h, self.rows, self.limit = h, [], limit
        if check:                                    # (before boot the code is not in RAM yet)
            h.check_code(MSG_READERS)

        def hook(h):
            if len(self.rows) < self.limit:
                md = h.reg.r0
                self.rows.append((h.u16(md + 4), h.u16(md + 6), h.reg.r1 & 0xFFFF, h.frame))
        for a in MSG_READERS:
            h.on_exec(a, hook)

    def mark(self):
        return len(self.rows)

    def read(self, bank=None, since=0):
        """(bank, id) pairs read from a027 since row <since> (only <bank> when given), in order, deduplicated."""
        out = []
        for narc, b, i, _ in self.rows[since:]:
            if narc == MSG_NARC_A027 and (bank is None or b == bank) and (b, i) not in out:
                out.append((b, i))
        return out

    def ids(self, bank, since=0):
        return sorted({i for b, i in self.read(bank, since)})

    def close(self):
        for a in MSG_READERS:
            self.h.on_exec(a, None)


def play(h, tr, answers=(), max_iter=80, tag="play", idle=150, shots=None, stop_at_menu=False, crop="both"):
    """Press through a running script, answering menus with <answers> (DOWN presses, 'B', or ('touch', x, y)),
    screenshotting every distinct stable screen. Ends when the script has ended (End, idle), at the first menu
    without an answer left (stop_at_menu), or on an invalid opcode. Returns (shots, how it ended)."""
    shots = [] if shots is None else shots
    answers = list(answers)
    last_menu, prev, nbad = len(tr.rows), None, len(tr.bad)
    for i in range(max_iter):
        M.wait_stable(h, max_frames=600)
        img = h.emu.screenshot()
        b = (img if crop == "both" else img.crop(TOP)).tobytes()
        if b != prev:
            shots.append(str(h.screenshot(f"{tag}_{len(shots):02d}")))
            prev = b
        if len(tr.bad) > nbad:
            return shots, "bad_op"
        rows = tr.rows
        if rows and rows[-1][0] == "End" and tr.idle_frames() >= idle and h.in_field():
            return shots, "end"
        if any(r[0] in M.MENU_OPS for r in rows[last_menu:]):
            last_menu = len(rows)
            if not answers:
                if stop_at_menu:
                    return shots, "menu"
                h.press("A", after=40)
                continue
            a = answers.pop(0)
            if a == "B":
                h.press("B", after=40)
            elif isinstance(a, tuple):
                h.touch(a[1], a[2], frames=8, after=40)
            else:
                for _ in range(a):
                    h.press("DOWN", after=12)
                h.press("A", after=40)
            continue
        h.press("A", after=20)
    return shots, "timeout"


def run_scene(rom, out, zone, tag, start, answers=(), flags=(), clear=(), vars=None, setup=None, at=None,
              hide=False, max_iter=80, stop_at_menu=False, read=None, after=None, face="DOWN"):
    """Warp into <zone>, start a script (start(h): e.g. run_script / run_from_with / a talk) with OpTrace and
    MsgLog on, play it through (see play) and return messages printed, a027 strings read, shots."""
    o = out_dir(out, rom)
    if hide:
        flags = tuple(flags) + hide_flags(zone)
    with M.session(rom, o, clock=CLOCK, flags=flags, clear=clear, vars=vars) as h:
        if setup:
            setup(h)
        if at is not False:
            B.enter(h, zone, *(at or (None, None)), face=face)
        tr, ml = M.OpTrace(h), MsgLog(h)
        start(h)
        shots, end = play(h, tr, answers, max_iter=max_iter, tag=tag, stop_at_menu=stop_at_menu)
        r = {"zone": zone, "printed": printed(tr), "strings": ml.read(), "end": end, "shots": shots,
             "ops": [n for n, _ in tr.ops()][:200], "bad": tr.bad[:3]}
        if after:
            r.update(after(h, tr, ml, shots) or {})
        if read:
            r.update(read(h) or {})
        return r


# ----------------------------------------------------------------------------- big-text scene lines
# (record, bank, msg ids, zone, script file, label, pre-commands)
PLAYER = (("BufferPlayersName", 0),)
LINES = {
    "0313_28": ("D-0541", 313, [28], 10, 169, 606, ()),
    "0314_14": ("D-0541", 314, [14], 414, 170, None, ()),
    "0314_28": ("D-0541", 314, [28], 414, 170, 546, ()),
    "0457_123": ("D-0553", 457, [123], 471, 753, 1329, ()),
    "0319_26": ("D-0553", 319, [26], 11, 175, 3170, ()),
    "0048_5": ("D-0553", 48, [5], 449, 9, 1174, ()),
    "0048_6": ("D-0553", 48, [6], 449, 9, "show", ()),       # female branch of GenderMsgBox 5/6 (save is male)
    "0048_20": ("D-0553", 48, [20], 449, 9, 2402, ()),
    "0321_27": ("D-0553", 321, [27], 12, 178, 757, ()),
    "0476_14": ("D-0571", 476, [14], 54, 774, 942, ()),
    "0476_19": ("D-0571", 476, [19], 54, 774, 1067, ()),
    "0476_69": ("D-0571", 476, [69], 54, 774, 3052, ()),
    "0476_74": ("D-0571", 476, [74], 54, 774, 3185, ()),
    "0476_85": ("D-0571", 476, [85], 54, 774, None, ()),
    "0476_102": ("D-0571", 476, [102], 54, 774, 7172, ()),
    "0356_4": ("D-0571", 356, [4], 29, 216, 355, ()),
    "0356_10": ("D-0571", 356, [10], 29, 216, 3590, ()),
    "0356_70": ("D-0571", 356, [70], 29, 216, 4686, PLAYER),
    "0356_72": ("D-0571", 356, [72], 29, 216, 4734, ()),
    "0356_74": ("D-0571", 356, [74], 29, 216, 4764, ()),
    "0356_78": ("D-0571", 356, [78], 29, 216, 8760, ()),
    "0356_79": ("D-0571", 356, [79], 29, 216, 8790, PLAYER),
    "0356_80": ("D-0571", 356, [80], 29, 216, 11682, ()),
    "0356_81": ("D-0571", 356, [81], 29, 216, 11712, PLAYER),
    "0356_84": ("D-0571", 356, [84], 29, 216, 9206, ()),
    "0511_153": ("D-0719", 511, [153], 57, 812, 2077, ()),
    "0124_124": ("D-0744", 124, [124], 465, 107, 3141, ()),
    "0124_125": ("D-0744", 124, [125], 465, 107, 3148, ()),
    "0547_7": ("D-0853", 547, [7], 72, 853, 737, ()),
    "0053_1": ("D-0853", 53, [1], 155, 17, 160, ()),
    "0053_39": ("D-0853", 53, [39], 155, 17, 5929, ()),
    "0546_12": ("D-0853", 546, [12], 71, 852, 801, ()),
    "0546_48": ("D-0853", 546, [48], 71, 852, 1800, ()),
    "0090_141": ("D-0853", 90, [141], 181, 61, 1144, ()),
    "0599_45": ("D-0903", 599, [45], 228, 912, 5407, PLAYER),
    "0599_56": ("D-0903", 599, [56], 228, 912, 2276, PLAYER),
    "0081_25": ("D-0983", 81, [25], 327, 52, 5159, ()),
    "0377_136": ("D-0983", 377, [136], 38, 237, 1905, ()),
}


# other single scene lines the records ask about (same recipe)
OTHER_LINES = {
    "0550_53": ("D-0936", 550, [53], 135, 856, 895, PLAYER),          # Falkner: {player}先生, no honorific
    "0106_95": ("D-1103", 106, [95], 276, 85, 3483, PLAYER),          # Battle Hall: Green (partner label)
    "0106_96": ("D-1103", 106, [96], 276, 85, 3472, ()),              # Red
    "0106_97": ("D-1103", 106, [97], 276, 85, 3494, PLAYER),          # Mom: Celadon Dept. Store
    "0626_40": ("D-1138", 626, [40], 291, 944, 3590,                  # Play Rough tutor: forget prompt
                (("SetVar", 0x8006, 0), ("SetVar", 0x8001, 0))),
    "0083_0": ("D-0955", 83, [0], 491, 54, 98, ()),                   # Ruins hall statue
}


def line_label(key):
    """The label of a LINES entry; None means: the first message command printing the id in the file."""
    rec, bank, ids, zone, file, label, pre = LINES[key] if key in LINES else OTHER_LINES[key]
    if label is None:
        label = static_refs(file, ids[0])[0][0]
    return label


CROWDED = {10, 11, 38, 449}     # zones that crash on entry with the test saves' people (see hide_flags)


def case_lines(rom, out, variant):
    rec, bank, ids, zone, file, label, pre = OTHER_LINES[variant]
    return scene_line(rom, out, zone, file, line_label(variant), ids, pre=pre, tag=f"lines_{variant}",
                      hide=zone in CROWDED, at=STAND.get(zone))


def case_bigtext(rom, out, variant):
    rec, bank, ids, zone, file, label, pre = LINES[variant]
    if label == "show" or (label is None and not static_refs(file, ids[0])):
        # no script command prints it (or only another branch of the save's state): render it with a one-off
        # script in the same window instead, with the player's name buffered
        o = out_dir(out, rom)
        with M.session(rom, o, clock=CLOCK, flags=hide_flags(zone) if zone in CROWDED else ()) as h:
            B.enter(h, zone, *STAND.get(zone, (None, None)))
            h.run_script(program=E.script_bytes(("BufferPlayersName", 0), ("End",)))
            h.step(30)
            shots = [str(p) for p in h.show_message(bank, ids[0], name=f"bigtext_{variant}")]
        note = ("other branch of the script's GenderMsgBox; shown with show_message" if label == "show" else
                "no script command prints this id (static); shown with show_message")
        return {"zone": zone, "file": file, "label": None, "targets": ids, "printed": [], "end": "done",
                "shots": shots, "static_refs": static_refs(file, ids[0]), "note": note}
    return scene_line(rom, out, zone, file, line_label(variant), ids, pre=pre, tag=f"bigtext_{variant}",
                      hide=zone in CROWDED, at=STAND.get(zone))


STAND = {10: (1034, 193), 11: (1172, 103)}   # below a door: the first object of these routes is a trainer who
#                                              sees the player and starts a battle


def judge_shown(res):
    """'shown' when every variant printed its target and captured pages; otherwise what went wrong."""
    rows = res.values() if all(isinstance(v, dict) for v in res.values()) and "end" not in res else [res]
    bad = [r for r in rows if r.get("end") != "done" or not r.get("shots")]
    return "shown" if not bad else "incomplete"


# ----------------------------------------------------------------------------- placeholders (never printed?)
NEVER = {
    "heist_140": ("D-0550", 471, 753, 2026, 141, 140),     # 0457 #139 -> #141 (the cut-scene's case shatters)
    "ambush_100": ("D-0746", 179, 110, 2624, 102, 100),    # 0126 #101 -> #99 -> #102 (Crystal's ambush)
}


def case_never(rom, out, variant):
    rec, zone, file, label, until, ph = NEVER[variant]
    return never_case(rom, out, zone, file, label, until, ph, f"never_{variant}")


def judge_never(res):
    rows = list(res.values())
    if any(r.get("placeholder_printed") for r in rows):
        return "printed"
    if all(r.get("end") == "done" and not r.get("static_refs") for r in rows):
        return "never_printed"
    return "unclear"



# ----------------------------------------------------------------------------- scenes, menus, screens
def rf(file, label, pre=()):
    """start(h) for run_scene: GoTo <label> of the current map's script file <file> after <pre>."""
    return lambda h: B.run_from_with(h, file, label, pre=pre)


def rs(script_id):
    """start(h) for run_scene: run map script <script_id> of the current map (as if talked to)."""
    return lambda h: h.run_script(script_id=script_id)


def case_statue(rom, out, variant):
    """D-0560: Cerulean Gym statue (zone 427, script 3): no Cascade Badge -> #6, badge -> #7 (player in the
    recognized-trainers line), flag 1042 -> #53."""
    def setup(h):
        G.set_badge(h, 1, variant == "badge")
        h.set_flag(1042, variant == "misty")
    return run_scene(rom, out, 427, f"statue_{variant}", rs(3), setup=setup)


def judge_statue(res):
    want = {"nobadge": [6], "badge": [7], "misty": [53]}
    return "confirmed" if all(res.get(v, {}).get("printed") == w for v, w in want.items()) else "changed"


def case_trade(rom, out):
    """D-0575: Diglett's Cave Bonsly/Rhyhorn trader (object 1, script 2, NPC trade 12): which person speaks."""
    def start(h):
        B.face_obj(h, 106, 1)
        h.press("A", after=10)

    def read(h):
        live = K.live_objects(h, 106)
        return {"trader_sprite": (live.get(1) or {}).get("sprite"), "brock_object_7": B.objects(106)[7]}
    return run_scene(rom, out, 106, "trade", start, answers=[1], at=False, read=read)


def case_tip(rom, out):
    """D-0622: Alex (Celadon Condominiums 3F, file 796): 'show some appreciation' -> Yes (L796, menu 0)."""
    return run_scene(rom, out, 378, "tip", rf(796, 796), answers=[0], max_iter=40)


def case_prize(rom, out, variant):
    """D-0623: Celadon Prize Corner Pokémon menu (script 5, #33-35)."""
    start = rs(5)
    return run_scene(rom, out, 382, f"prize_{variant}", start, stop_at_menu=True, max_iter=20)


def case_palpark(rom, out):
    """D-0661: Pal Park greeting (file 809 L4401, GenderMsgBox 0/1) and the Yes/No that follows."""
    return run_scene(rom, out, 479, "palpark", rf(809, 4401), stop_at_menu=True, max_iter=20)


def case_mom(rom, out):
    """D-0762 / D-0936: Mom's gift after the first Pokémon (file 842 L6104): what she gives, which lines print
    (the only GiveRunningShoes in the hack's scripts)."""
    return run_scene(rom, out, 63, "mom", rf(842, 6104), max_iter=40)


def case_seal(rom, out):
    """D-0855: what the 'Sealed by the Pokémon League' (0547 #105) sign is: bg event at (21, 18) of zone 72,
    script 8 (flag 1803 clear)."""
    def setup(h):
        h.set_flag(1803, False)

    def start(h):
        h.warp(72, 21, 19, E.DIRS["UP"])
        h.step(90)
        h.screenshot("seal_field")
        h.press("A", after=10)
    return run_scene(rom, out, 72, "seal", start, setup=setup, at=False, max_iter=20)


def case_ball(rom, out):
    """D-0884: Ariana's 'Special Ball' (Sky Pillar Peak, file 914 L899): object 11 (sprite 87) thrown at
    Rayquaza; screenshots of the throw."""
    def after(h, tr, ml, shots):
        return {"ball_object": B.objects(230)[11]}
    return run_scene(rom, out, 230, "ball", rf(914, 899), max_iter=14, after=after)


def case_psychic(rom, out):
    """D-1076: Frontier Access memory-battle NPC (object 7, script 6, flag 2261 set -> #4 prompt)."""
    def setup(h):
        h.set_flag(2261, True)

    def start(h):
        B.face_obj(h, 528, 7)
        h.screenshot("psychic_field")
        h.press("A", after=10)
    return run_scene(rom, out, 528, "psychic", start, setup=setup, at=False, answers=[1], max_iter=30,
                     read=lambda h: {"sprite": B.objects(528)[7]["sprite"]})


def case_elm(rom, out):
    """D-1103: 0123 #29/#30 are in script 4 of file 104 (Lugia's cave), which no object or trigger of map 244
    uses; run script 4 directly (flag 265 set -> #30) to see the line without a speaker."""
    def setup(h):
        h.set_flag(265, True)
    return run_scene(rom, out, 244, "elm", rs(4), setup=setup, max_iter=20,
                     read=lambda h: {"events_using_script_4": [e for e in B.objects(244) if e["script"] == 4]})


def case_ruins(rom, out, variant):
    """D-0955: Ruins of Alph hint lines. 'aerodactyl' / 'omanyte': the panel puzzle (AlphPuzzle, zone 314 / 316
    script 1): does the app read 0073/0075 #0? 'statue': the hall's statues (zone 491 script 5, 0083 #0)."""
    zone = {"aerodactyl": 314, "omanyte": 316, "statue": 491}[variant]
    bank = {314: 73, 316: 75, 491: 83}[zone]

    def after(h, tr, ml, shots):
        return {"bank": bank, "bank_read": ml.ids(bank)}
    if variant == "statue":
        return run_scene(rom, out, zone, f"ruins_{variant}", rs(5), max_iter=10, after=after)

    def start(h):
        h.run_script(script_id=1)
        h.step(400)
        h.screenshot(f"ruins_{variant}_app")
        h.press("B", after=200)
    return run_scene(rom, out, zone, f"ruins_{variant}", start, max_iter=12, after=after)


def case_nurse(rom, out, variant):
    """D-0781: Pokémon Center nurse (std script 9001, file 4) while the player wears the Rocket costume
    (SetAvatarBits 1024, UpdateAvatarState, RocketCostumeFlagAction 1 as file 94 does): GetPlayerState 3 ->
    0044 #144. Control: normal clothes."""
    def start(h):
        if variant == "costume":
            h.run_script(program=E.script_bytes(("LockAll",), ("SetAvatarBits", 1024), ("UpdateAvatarState",),
                                                ("RocketCostumeFlagAction", 1), ("ReleaseAll",), ("End",)))
            h.step(120)
        B.face_obj(h, 528, 3, side="DOWN")
        h.press("A", after=10)
    return run_scene(rom, out, 528, f"nurse_{variant}", start, at=False, answers=["B", "B"], max_iter=30)


def judge_nurse(res):
    a, b = res.get("costume", {}).get("printed") or [None], res.get("normal", {}).get("printed") or [None]
    return "confirmed" if a[0] == 144 and b[0] != 144 else "changed"


def case_relearner(rom, out):
    """D-1138: Blackthorn Move Reminder (file 944 L214, party slot 0): the relearner app's prompts (which
    bank/ids it reads), first move picked with A."""
    def start(h):
        B.run_from_with(h, 944, 214, pre=(("SetVar", 0x8005, 0),))
        h.step(300)
        h.screenshot("relearner_app")
        h.press("A", after=120)
        h.screenshot("relearner_pick")
        h.press("A", after=120)
        h.screenshot("relearner_confirm")
        h.press("B", after=60)
        h.press("B", after=60)
        h.press("B", after=200)

    def after(h, tr, ml, shots):
        return {"bank626_read": ml.ids(626), "banks_read": sorted({b for b, _ in ml.read()})}
    return run_scene(rom, out, 291, "relearner", start, answers=["B", "B"], max_iter=20, after=after)


def case_notice(rom, out):
    """D-0504: the notice screen shown on New Game (bank 0816 #0-#4, timer #5, #6/#7 prompts, #8 under the QR
    code): every page, both screens."""
    o = out_dir(out, rom)
    shots, pages = [], []
    with E.Harness(rom, E.DEF_SAVES / "full_bag_6mons.sav", out=o, verbose=False) as h:
        h.step(5)
        ml = MsgLog(h, check=False)
        h.step(3000)
        h.press("START", after=400)
        h.step(300)
        h.screenshot("notice_menu")
        h.press("DOWN", after=30)
        h.press("A", after=300)
        seen = set()
        for k in range(40):
            h.step(60)
            got = [i for i in ml.ids(816) if i <= 4 and i not in seen]
            if got:
                seen.update(got)
                h.step(90)
                pages.append(got)
                shots.append(str(h.screenshot(f"notice_p{len(shots) + 1}")))
                h.step(330)                       # the 'next page in N seconds' timer, then 'Press A'
                shots.append(str(h.screenshot(f"notice_p{len(shots) + 1}")))
            if seen >= {0, 1, 2, 3, 4} and 7 in ml.ids(816):
                break
            h.press("A", after=10)
        return {"pages": pages, "read": ml.ids(816), "shots": shots}




def case_berrybag(rom, out):
    """D-0829: does anything show the berry 'tag' texts of bank 0243? Bag -> Berries pocket, first berry
    selected; the a027 banks read are logged (bank 0243 read or not)."""
    o = out_dir(out, rom)
    with M.session(rom, o, clock=CLOCK) as h:
        ml = MsgLog(h)
        h.open_bag()
        h.bag_pocket("berries")
        h.step(60)
        shots = [str(h.screenshot("berrybag_pocket"))]
        h.touch(*E.BAG_SLOTS[0], frames=12, after=60)
        shots.append(str(h.screenshot("berrybag_item")))
        return {"bank243_read": ml.ids(243), "banks_read": sorted({b for b, _ in ml.read()}), "shots": shots}


BATTLE_BAG_POCKETS = {"restore": (64, 40), "balls": (192, 40), "status": (64, 112), "battle": (192, 112)}
BATTLE_BAG_USE = (128, 172)
GUARD_SPEC = 55


def case_battlebag(rom, out):
    """D-0522: battle bag (bank 0005: #21 NEXT, #35 'Shrouded in mist!') and FIGHT (bank 0006 #57 APPEAL): a
    wild battle in the Unown hall; BAG -> HP/PP RESTORE (two pages), BAG -> BATTLE ITEMS -> Guard Spec. -> USE,
    then FIGHT; every a027 string read is logged."""
    o = out_dir(out, rom)
    with E.start_at(315, 17, 24, rom=rom, out=o, verbose=False, clock=CLOCK, flags=(2423,)) as h:
        G.lead(h, 291, level=100)
        h.bag_put_first(GUARD_SPEC, 5, pocket="battle")
        ml = MsgLog(h)
        h.walk_until_battle()
        h.wait_screen("battle_menu", max_frames=2400)
        shots, seen = [], {}
        m = ml.mark()
        h.touch(*E.BATTLE_BUTTONS["bag"], frames=10, after=120)
        h.touch(*BATTLE_BAG_POCKETS["restore"], frames=10, after=90)
        shots.append(str(h.screenshot("battlebag_restore")))
        h.touch(*BATTLE_BAG_POCKETS["balls"], frames=10, after=0)   # nothing there on this page
        seen["restore"] = ml.read(5, m)
        h.touch(25, 172, frames=10, after=90)                        # back (return arrow)
        h.touch(25, 172, frames=10, after=120)
        h.wait_screen("battle_menu", max_frames=600)
        m = ml.mark()
        h.touch(*E.BATTLE_BUTTONS["bag"], frames=10, after=120)
        h.touch(*BATTLE_BAG_POCKETS["battle"], frames=10, after=90)
        shots.append(str(h.screenshot("battlebag_battleitems")))
        h.touch(64, 28, frames=10, after=90)
        shots.append(str(h.screenshot("battlebag_guardspec")))
        h.touch(*BATTLE_BAG_USE, frames=10, after=10)
        for k in range(6):
            h.step(60)
            shots.append(str(h.screenshot(f"battlebag_use{k}")))
        seen["battle_items"] = ml.read(5, m)
        M.wait_stable(h)
        for _ in range(10):
            if h.on_screen("battle_menu"):
                break
            h.press("B", after=60)
        m = ml.mark()
        h.touch(*E.BATTLE_BUTTONS["fight"], frames=10, after=120)
        shots.append(str(h.screenshot("battlebag_fight")))
        seen["fight"] = ml.read(6, m)
        return {"bank5_read": ml.ids(5), "bank6_read": ml.ids(6), "per_screen": seen, "shots": shots,
                "battle_strings": [x for x in ml.read(since=m)][:40]}




def case_gearmap(rom, out):
    """D-1153: Pokégear map descriptions (bank 0266 #68, #117): open the map, sweep the cursor with the D-pad
    (rows of LEFT/RIGHT, one DOWN between), screenshot when #68 or #117 is first read."""
    o = out_dir(out, rom)
    targets = {68, 117}
    with M.session(rom, o, clock=CLOCK) as h:
        ml = MsgLog(h)
        h.field_menu("pokegear")
        h.step(120)
        h.touch(*E.POKEGEAR_TABS["map"], frames=10, after=200)
        shots, hits = [str(h.screenshot("gearmap_open"))], {}
        for _ in range(20):
            h.press("UP", frames=4, after=6)
        for _ in range(30):
            h.press("LEFT", frames=4, after=6)
        for row in range(24):
            for _ in range(32):
                h.press("RIGHT" if row % 2 == 0 else "LEFT", frames=4, after=14)
                got = targets & set(ml.ids(266)) - set(hits)
                for t in got:
                    h.step(30)
                    hits[t] = str(h.screenshot(f"gearmap_{t}"))
            if len(hits) == len(targets):
                break
            h.press("DOWN", frames=4, after=14)
        shots += [hits[t] for t in sorted(hits)]
        return {"bank266_read": ml.ids(266), "hits": hits, "shots": shots}


# ----------------------------------------------------------------------------- runner
CASES = {
    "bigtext": (case_bigtext, tuple(LINES), judge_shown,
                "D-0541 D-0553 D-0571 D-0719 D-0744 D-0853 D-0903 D-0983"),
    "never": (case_never, tuple(NEVER), judge_never, "D-0550 D-0746"),
    "lines": (case_lines, tuple(OTHER_LINES), judge_shown, "D-0936 D-1103 D-1138 D-0955"),
    "statue": (case_statue, ("nobadge", "badge", "misty"), judge_statue, "D-0560"),
    "trade": (case_trade, None, None, "D-0575"),
    "tip": (case_tip, None, None, "D-0622"),
    "prize": (case_prize, ("pokemon",), None, "D-0623"),
    "palpark": (case_palpark, None, None, "D-0661"),
    "mom": (case_mom, None, None, "D-0762 D-0936"),
    "seal": (case_seal, None, None, "D-0855"),
    "ball": (case_ball, None, None, "D-0884"),
    "psychic": (case_psychic, None, None, "D-1076"),
    "elm": (case_elm, None, None, "D-1103"),
    "ruins": (case_ruins, ("aerodactyl", "omanyte", "statue"), None, "D-0955"),
    "nurse": (case_nurse, ("costume", "normal"), judge_nurse, "D-0781"),
    "relearner": (case_relearner, None, None, "D-1138"),
    "notice": (case_notice, None, None, "D-0504"),
    "berrybag": (case_berrybag, None, None, "D-0829"),
    "battlebag": (case_battlebag, None, None, "D-0522"),
    "gearmap": (case_gearmap, None, None, "D-1153"),
}


def make_pairs(report, out):
    """CN|EN pairs (top screens stacked per page) for every case/variant that has shots on both ROMs."""
    from PIL import Image
    pdir = Path(out).resolve() / "verify" / "pairs"
    pdir.mkdir(parents=True, exist_ok=True)
    made = []
    for c, by_lang in report.items():
        if "cn" not in by_lang or "en" not in by_lang:
            continue
        cn, en = by_lang["cn"], by_lang["en"]
        variants = [k for k in cn if isinstance(cn.get(k), dict) and "shots" in cn[k]] or [None]
        for v in variants:
            a = (cn[v] if v else cn).get("shots") or []
            b = (en[v] if v else en).get("shots") or []
            n = max(len(a), len(b))
            if not n:
                continue
            hgt = 192 if c in TOP_ONLY else 384           # message lines: top screen; menus/apps: both
            box = (0, 0, 256, hgt)
            img = Image.new("RGB", (2 * 256 + 8, (hgt + 4) * n), "white")
            for k, p in enumerate(a):
                img.paste(Image.open(p).crop(box), (0, (hgt + 4) * k))
            for k, p in enumerate(b):
                img.paste(Image.open(p).crop(box), (264, (hgt + 4) * k))
            path = pdir / f"{c}_{v}.png" if v else pdir / f"{c}.png"
            img.save(path)
            made.append(str(path))
    return made


def run_cases(roms, cases, out, jobs=6, variants=None):
    """Each case/variant and ROM in its own child process (`verify --child`); judges combine variants."""
    from concurrent.futures import ThreadPoolExecutor
    variants = variants or {}
    todo = [(c, v, l) for c in cases for v in (variants.get(c) or CASES[c][1] or [None]) for l in roms]

    def run(job):
        c, v, l = job
        try:
            return c, v, l, E.run_child(["verify", "--child", c + (":" + v if v else ""), "--rom", roms[l],
                                         "--out", out], timeout=1800)
        except Exception as e:
            return c, v, l, {"verdict": "error", "error": str(e)[-1500:]}
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
            if CASES[c][2]:
                try:
                    r["verdict"] = CASES[c][2](r)
                except Exception as e:
                    r["verdict"] = "error"
                    r["judge_error"] = repr(e)
            r["records"] = CASES[c][3]
    return report


SUITE_EXPECT = {"never": "never_printed", "statue": "confirmed", "nurse": "confirmed"}
SUITE_VARIANTS = {}


def suite_check(rom, out):
    """emu_harness.py suite: the SUITE_EXPECT cases on one ROM; pass when every verdict is the expected one."""
    report = run_cases({"x": rom}, list(SUITE_EXPECT), out, jobs=8, variants=SUITE_VARIANTS)
    got = {c: report[c]["x"].get("verdict") for c in SUITE_EXPECT}
    return got == SUITE_EXPECT, {"verdicts": got}


def cmd(a):
    """emu_harness.py verify: each case/variant and ROM in its own child process; one JSON report + pairs."""
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
    pairs = make_pairs(report, a.out) if len(langs) == 2 else []
    name = ("all" if set(cases) == set(CASES) else "_".join(cases)[:80]) + ("" if a.lang == "cn" else "_" + a.lang)
    path = Path(a.out) / "verify" / ("report_" + name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"report": str(path), "pairs": len(pairs)}))
    return 0
