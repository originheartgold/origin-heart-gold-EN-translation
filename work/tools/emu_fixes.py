"""emu_fixes - one emulator scenario per fix in work/patches: the fix's effect, seen in game.

Each scenario plays one screen or path on a ROM and records what the game did there (hooked arguments of the
patched instructions, return values, RAM tables the screen uses, pixel measurements). Per fix a classifier turns
those observations into 'fixed' (the fix's behaviour), 'original' (the Chinese hack's behaviour) or 'unclear'.
The proof for a fix is a pair of runs:

    the fixed ROM (a normal build)                       -> every fix it covers is 'fixed'
    the control ROM (build.py --without <fix>, plus the fixes that require it)   -> that fix is 'original'

A scenario that shows the fix on the fixed ROM but cannot tell it apart on the control proves nothing, so the
control run is part of every check. Graphics scenarios compare a screen crop with the same crop on the
untouched Chinese ROM (the 'reference' run): 'original' when it is identical, 'fixed' when it differs.

    <venv>/bin/python work/tools/emu_harness.py fixes --rom FIXED.nds --controls DIR [--build-controls]
        [--case all|<scenario or fix id>,...] [--out DIR] [--sav-dir DIR] [--jobs 3]

--controls DIR holds the control ROMs as no-<fix>.nds; --build-controls builds the missing ones there,
--rebuild-controls all selected ones (build.py --no-patch --without <fix>[,<fixes that require it>]; about 7 s
each). A control must come from the same tree as the fixed ROM: check.py --full --emu rebuilds them. The report
(<out>/fixes_report.json) has one row per fix: scenario, the state on the fixed ROM and on its control, the
evidence and the time. Exit 0 only when every selected fix is 'fixed' on the fixed ROM and 'original' on its
control. COVERAGE lists every fix in work/patches: its scenario, or why it has none (test_emu_fixes.py keeps
the list complete and each fix.toml's evidence pointing at its scenario).

Nothing is written next to the ROMs or saves: every run imports its save into a private emulator folder.
Screenshots, crops and reports go to --out (work/build, git-ignored). Addresses are the hack's (IPKJ base) and
are the same in our build; each is cited from the fix's .listing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
CHARMAP = TOOLS / "charmap_en.tsv"

# --------------------------------------------------------------------------------------------- coverage
# fix id -> scenario names that cover it (every scenario run on the fixed ROM and on no-<fix>.nds)
COVERAGE = {
    "namelen": ("naming", "newgame"),
    "naming-keyboard": ("naming",),
    "gfx-naming-tabs": ("naming",),
    "outfit-chooser-strings": ("newgame",),
    "gfx-title-subtitle": ("newgame",),
    "pcbox-name-width": ("pcbox",),
    "ivev-panel": ("ivev",),
    "gfx-type-icons": ("ivev", "battle"),
    "antipiracy": ("antipiracy",),
    "font-glyphs": ("font",),
    "text-speed": ("textspeed",),
    "msgload": ("msgload",),
    "overworld-texture-frame-bounds": ("texture-bounds",),
    "bulbasaur-reflection-boundary": ("reflection",),
    "evolution-moves": ("evolution",),
}
# fix id -> why no scenario of this command covers it (honest gaps; see work/notes/emu_harness.md)
UNCOVERED = {
    "gfx-bag-labels": "graphics; the bag's HM pocket and 1 SET/2 SET labels: no crop check yet",
    "gfx-battle-panel-labels": "graphics; the in-battle info panel (needs a battle): no crop check yet",
    "gfx-battle-result-labels": "graphics; link/facility battle result screen: not reachable by the harness",
    "gfx-battle-status-icons": "graphics; needs a battle with a status condition: no crop check yet",
    "gfx-dex-header": "graphics; the Pokédex header/buttons: the `dex` suite check diffs Pokédex panels against "
                      "an approved baseline, not against a control build",
    "gfx-dex-type-badges": "graphics; Pokédex type badges: as gfx-dex-header",
    "gfx-jp-buttons": "graphics; the CANCEL/START buttons of rarely used screens: no crop check yet",
    "gfx-linkcapture-bar": "graphics; the Chain Logger menu bar: no recipe reaches it",
    "gfx-pokeathlon": "graphics; Pokéathlon screens: no recipe reaches them",
    "gfx-pokegear-calendar": "graphics; Pokégear clock/calendar labels: no crop check yet",
    "gfx-summary-labels": "graphics; summary condition labels/status icons: no crop check yet",
    "gfx-trainer-card": "graphics; trainer card units and labels: no crop check yet",
    "gfx-weather-banners": "graphics; needs a battle in weather: no crop check yet",
    "gfx-yes-no-buttons": "graphics; the touch-screen YES/NO buttons: no crop check yet",
}

# --------------------------------------------------------------------------------------------- addresses
# namelen (namelen.listing): the maxLen argument r3 of NamingScreen_CreateArgs (0x02081DA4) and of
# CallTask_NamingScreen (0x0203EDEC); a call is attributed to its site by the return address (bl + 4).
CREATE_ARGS = 0x02081DA4
CALL_TASK_NAMING = 0x0203EDEC
NAMING_SITES = {   # address of the bl -> (fix.toml region id, fixed maxLen, original maxLen)
    0x02042864: ("namelen-player-script", 7, 5),
    0x02042894: ("namelen-rival-script", 7, 5),
    0x02042920: ("namelen-nickname-script", 10, 5),
    0x020490DC: ("namelen-group-script", 7, 5),
    0x02090946: ("namelen-nickname-egg", 10, 5),
    0x02228DAE: ("namelen-kind7", 7, 5),
    0x021E49D2: ("namelen-player-intro", 7, 5),
    0x021E49EA: ("namelen-rival-intro", 7, 5),
}
# naming-keyboard (naming-keyboard.listing): the key handler's page-0 branch at 0x02083C24 ('bne insert' in
# the hack, 'b insert' fixed); the instruction after it is the first of the pinyin IME path.
NAMING_IME_PATH = 0x02083C26
CH_A = 0x012B                       # 'A' (charmap_en.tsv; the first key of the ABC page and the cursor's start)
# outfit-chooser-strings (overlay58 at 0x021E83C0, outfit-chooser-strings.listing)
OV58 = 0x021E83C0
OV58_ITEM_PTRS = OV58 + 0x7C0       # u32[3]: list items 1, 2, 3
OV58_OK_LITERAL = OV58 + 0x4E4      # u32: the 'OK' item
OV58_ORIGINAL_SLOTS = (OV58 + 0x6F0, OV58 + 0x710)   # where the hack's four strings live
OV58_STRINGS = (OV58 + 0x6F0, OV58 + 0x818)   # the hack's strings and the relocated English ones (watched reads)
# pcbox-name-width (pcbox-name-width.listing): the PC box top-screen WindowTemplate table in overlay 16
PCBOX_TEMPLATES = 0x021F781C        # [0] = species name window {bg 4, x 8, y 5, width, height 2, pal 15, 0x69}
PC_STD_SCRIPT = 2010                # the Pokemon Center PC (found by running std scripts 2000-2039)
PC_MAP = (69, 4, 9)                 # Cherrygrove Pokemon Center 1F, in front of the PC
NAME_BOX = (120, 40, 128, 56)       # screenshot box: the 8th tile of the name window (x 120-127, top screen)
NAME_ROW = (64, 40, 128, 56)        # the whole name window (8 tiles from x 64; the gender icon starts at x 128)
PCBOX_BASES = {"fixed": [0x69, 0x79, 0x89, 0x0F, 0x95, 0x99, 0xA5, 0xB5, 0xCB],     # templates [0]-[8], base tile
               "original": [0x69, 0x77, 0x87, 0x0F, 0x93, 0x97, 0xA3, 0xB3, 0xC9]}  # (pcbox-name-width.asm)
# ivev-panel (ivev-panel.listing): 'movs r2, #x' before bl 0x0208C154 (IV numbers), 'movs r3, #x' before the
# 'IVs' header print; the EV column is drawn with x 0x40 by the same routine and is not changed.
IVEV_IV_CALL = 0x0208C264
IVEV_HEADER_CALL = 0x0208C1E4
IVEV_EV_X = 0x40
IVEV_ROWS = [(56, 72), (72, 88), (88, 104), (104, 120), (120, 136), (136, 152)]   # HP .. Speed (screenshot y)
IVEV_X = (150, 256)
# evolution-moves (evolution-moves.listing): the evolution scene's learn call (0x02074BD4, bl TryLearnOnEvolution
# fixed, bl 0x02070870 in the hack) returns at 0x02074BD8: r0 = the move learned, 0xFFFE (already known), 0xFFFF
# (four moves: the forget-a-move flow follows) or 0 (nothing left); the move it looked at is the u16 at sp + 0xE.
# Level-up without evolution: the Rare Candy's learn call at 0x020806F2 returns at 0x020806F6.
EVO_LEARN_RETURN = 0x02074BD8
LEVELUP_LEARN_RETURN = 0x020806F6
RARE_CANDY_ITEM, THUNDER_STONE_ITEM = 50, 83
TACKLE, GROWL, EMBER, SCRATCH = 33, 45, 52, 10
# case: (species, level, moves, item (None: Rare Candy), friendship or None, species after, evolution moves
# (level 0 in the learnset: offered only with the fix), moves of the new level (learned with and without it))
EVOLUTION_CASES = {
    "charizard": (5, 35, (TACKLE, 0, 0, 0), None, None, 6, (403,), ()),               # Air Slash
    "charizard_full": (5, 35, (TACKLE, GROWL, EMBER, SCRATCH), None, None, 6, (403,), ()),   # forget Tackle
    "charizard_lv39": (5, 38, (TACKLE, 0, 0, 0), None, None, 6, (403,), (184,)),      # + Scary Face (Lv39)
    "gyarados": (129, 19, (TACKLE, 0, 0, 0), None, None, 130, (44,), ()),             # Bite
    "crobat": (42, 29, (TACKLE, 0, 0, 0), None, 255, 169, (440,), ()),                # Cross Poison
    "raichu_stone": (25, 20, (TACKLE, 0, 0, 0), THUNDER_STONE_ITEM, None, 26, (9,), ()),   # Thunder Punch
    "charizard_levelup": (6, 40, (TACKLE, 0, 0, 0), None, None, 6, (), ()),           # no evolution: no Air Slash
}
EVOLUTION_LEVELUP_ONLY_FORBIDDEN = 403      # charizard_levelup must not be offered Air Slash on a plain level-up
# antipiracy (antipiracy.listing): the six DS Protect entry points in overlay 114 and their genuine values
ANTIPIRACY_ENTRIES = {0x02263A64: 0, 0x02263B4C: 1, 0x02263C34: 0, 0x02263D1C: 1, 0x02263E04: 0, 0x02263ECC: 1}
def _fix_expect_bytes(fix_id, region_id):
    """A [[code]] region's expect (halfwords) as the bytes in memory (little-endian per halfword)."""
    import tomllib
    with open(WORK / "patches" / fix_id / "fix.toml", "rb") as f:
        entry = next(e for e in tomllib.load(f)["code"] if e["id"] == region_id)
    return b"".join(int(hw, 16).to_bytes(2, "little") for hw in entry["expect"].split())


# push {r4-r10, lr}; sub sp, sp, #0x80: the entries' original first 8 bytes (all six regions expect the same)
ANTIPIRACY_PROLOGUE = _fix_expect_bytes("antipiracy", "antipiracy-ov114-0x864")
# font-glyphs: the codes the fix restores and the fonts whose width tables the field keeps in RAM
FONT_CODES = (0x01AF, 0x01B4, 0x01B5)      # … “ ”
FONT_RAM = (0, 1, 4)                       # font 2 is not loaded in the field
FONT_WIDTHS = {"fixed": {0: 6, 1: 6, 4: 7}, "original": {0: 12, 1: 12, 4: 13}}
# text-speed: Options bits 2-3 (1 = FAST; native.c fast())
TEXT_SPEED_MSG = (457, 123)         # a field message of the text-speed corpus (work/notes/text_speed_harness.md)
TEXT_WINDOW = (8, 150, 232, 186)    # the field message window's text area (top screen), without the page arrow
TEXT_SPEED_FRAMES = 400

# Graphics crops (screenshot coordinates, 256x384: bottom screen from y 192). A graphics fix is 'fixed' when its
# crop is the approved one (and not the Chinese ROM's), 'original' when it equals the Chinese ROM's crop.
CROPS = {
    "naming-tabs": (20, 246, 240, 276),          # naming screen: the four tabs and the BACK / OK buttons
    "type-icon-summary": (7, 201, 41, 215),      # summary skills page: the first move's type icon
    "type-icon-battle": (16, 247, 49, 261),      # battle FIGHT menu: the first move's type icon
    "title-subtitle": (96, 98, 250, 128),        # title screen under the 起源心金 logo: 'Origin HeartGold'
}
# sha256 of each crop's RGB pixels (crop_digest) on the fixed build. Only the digests are in git: the crop
# images are game graphics. The images the digests were taken from are kept locally for review.
APPROVAL_IMAGES = "work/build/hard4/approve/ (in the poke-patches worktree): <crop>_build.png, <crop>_chinese.png"
APPROVED = {   # taken from run work/build/hard4/run3 (2026-10-08), the build of develop aab6efb
    "naming-tabs": {"digest": "037dab60bd0a6a0ac04d497fdd82463dd679ac22c72ba558c188d501f0e991b1",
                    "approved_by": "user, 2026-10-08", "images": APPROVAL_IMAGES},
    "type-icon-summary": {"digest": "dea47b53d48bb954194db1cc0b0c219395697b40a966ee4e43035809464aa85b",
                          "approved_by": "user, 2026-10-08", "images": APPROVAL_IMAGES},
    "type-icon-battle": {"digest": "cdd429d35e5f48a50c0a98fa4b68a55cd2a289675c582ffb1278364b8cdff89b",
                         "approved_by": "user, 2026-10-08", "images": APPROVAL_IMAGES},
    "title-subtitle": {"digest": "ef249d7e92d33f907702649a2304ccbfb587e2ffdc317053aa1b2c8cfd10f1ad",
                       "approved_by": "user, 2026-10-08", "images": APPROVAL_IMAGES},
}
TITLE_FRAME = 2400                  # frames after power-on (intro movie); START then shows the title screen


# --------------------------------------------------------------------------------------------- helpers
_CHARS = {}


def decode(raw: bytes) -> str:
    """Game-font u16 codes -> text (charmap_en.tsv); unknown codes as [xxxx]; stops at 0xFFFF."""
    if not _CHARS:
        for line in CHARMAP.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or "\t" not in line:
                continue
            code, text = line.split("\t", 1)
            _CHARS[int(code, 16)] = text
    out = []
    for (w,) in struct.iter_unpack("<H", raw[:len(raw) // 2 * 2]):
        if w == 0xFFFF:
            break
        out.append(_CHARS.get(w, f"[{w:04x}]"))
    return "".join(out)


def codes(raw: bytes) -> list:
    out = []
    for (w,) in struct.iter_unpack("<H", raw[:len(raw) // 2 * 2]):
        if w == 0xFFFF:
            break
        out.append(w)
    return out


def file_sha1(path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def crop_digest(img, box) -> str:
    return hashlib.sha256(img.convert("RGB").crop(box).tobytes()).hexdigest()


def ink_columns(img, box, threshold=250) -> list:
    """Columns of box (x0, y0, x1, y1) that hold a dark pixel (R+G+B below threshold): text ink."""
    x0, y0, x1, y1 = box
    rgb = img.convert("RGB")
    return [x for x in range(x0, x1) if any(sum(rgb.getpixel((x, y))) < threshold for y in range(y0, y1))]


def column_distance(cols, min_gap=10):
    """Right edges of the last two ink blocks separated by a gap of at least min_gap columns: (iv, ev)."""
    if not cols:
        return None
    ev_right = cols[-1]
    i = len(cols) - 1
    while i > 0 and cols[i] - cols[i - 1] < min_gap:
        i -= 1
    if i == 0:
        return None
    return cols[i - 1], ev_right


def site_of(lr):
    """The NAMING_SITES key of a call that returns to lr (Thumb bl: return = bl + 4, bit 0 set)."""
    return (lr & ~1) - 4


def nickname(raw236: bytes) -> list:
    """Nickname codes (block C +0, 11 u16) of an encrypted party Pokemon (Gen 4 layout, emu_harness)."""
    import emu_harness as E
    pid, flags, checksum = struct.unpack_from("<IHH", raw236, 0)
    words = struct.unpack_from("<64H", raw236, 8)
    plain = list(words) if flags & 3 else [w ^ k for w, k in zip(words, E._prng_stream(checksum, 64))]
    data = struct.pack("<64H", *plain)
    order = E.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    c = order.index("C")
    return codes(data[32 * c:32 * c + 22])


def scripted(h, *cmds, settle=300):
    """Run commands from the field; a sentinel var tells when they have finished. Returns the sentinel check."""
    import emu_harness as E
    h.set_var(E.SENTINEL_VAR, 0)
    prog = E.script_bytes(("LockAll",), *cmds, ("SetVar", E.SENTINEL_VAR, 0x5A5A), ("ReleaseAll",), ("End",))
    h.run_script(program=prog, settle=settle)
    return lambda: h.get_var(E.SENTINEL_VAR) == 0x5A5A


def type_name(h, done, max_presses):
    """In the naming screen: A until the screen closes (the cursor starts on the first key, and moves to OK
    when the name is full), then, if it is still open, START (cursor to OK) and A."""
    presses = 0
    while not done() and presses < max_presses:
        h.press("A", after=40)
        presses += 1
    if not done():
        h.press("START", after=40)
        for _ in range(6):
            if done():
                break
            h.press("A", after=150)
    h.step(120)
    return {"a_presses": presses, "closed": bool(done())}


class NamingCalls:
    """maxLen (r3) of every naming-screen call, attributed to its call site."""

    def __init__(self, h):
        self.rows = []
        h.on_exec(CREATE_ARGS, lambda m: self._add(m, "CreateArgs"))
        h.on_exec(CALL_TASK_NAMING, lambda m: self._add(m, "CallTask"))

    def _add(self, m, fn):
        site = site_of(m.reg.lr)
        self.rows.append({"fn": fn, "site": NAMING_SITES.get(site, (f"{site:#010x}",))[0], "max_len": m.reg.r3,
                          "frame": m.frame})

    def by_site(self):
        out = {}
        for r in self.rows:
            if r["site"].startswith("namelen-"):
                out.setdefault(r["site"], set()).add(r["max_len"])
        return {k: sorted(v) for k, v in out.items()}


def screenshot(h, name, crops=()):
    """Screenshot plus the digests (and saved images) of the given CROPS keys."""
    path = h.screenshot(name)
    img = h.emu.screenshot()
    out = {"screenshot": str(path)}
    for key in crops:
        out.setdefault("crops", {})[key] = crop_digest(img, CROPS[key])
        img.convert("RGB").crop(CROPS[key]).save(h.out / f"{name}_{key}_crop.png")
    return out, img


# --------------------------------------------------------------------------------------------- scenarios
def observe_naming(h):
    """Field (full_bag_6mons.sav): the script commands NamePlayer, NameRival and NicknameInput (party slot 0)
    open the naming screen; A is pressed until it closes, so the stored name shows how many characters the
    screen took and which codes the first key types."""
    calls = NamingCalls(h)
    ime = []
    h.on_exec(NAMING_IME_PATH, lambda m: ime.append(m.frame))
    obs = {}
    done = scripted(h, ("NamePlayer", 0x8000))
    shot, _ = screenshot(h, "naming_player_open", crops=("naming-tabs",))
    obs["player"] = dict(shot, **type_name(h, done, 14))
    name = h.read(h.array(1) + 4, 16)          # PlayerProfile name, u16[8] (save array 1 after the 4-byte Options)
    obs["player"].update(codes=codes(name), text=decode(name))
    done = scripted(h, ("NameRival", 0x8000))
    obs["rival"] = type_name(h, done, 14)
    done = scripted(h, ("NicknameInput", 0, 0x8001))
    obs["nickname"] = type_name(h, done, 14)
    nick = nickname(h.read(h.array(2) + 8, 236))
    obs["nickname"].update(codes=nick, text=decode(struct.pack(f"<{len(nick)}H", *nick)))
    obs["max_len"] = calls.by_site()
    obs["ime_path_runs"] = len(ime)
    return obs


def observe_newgame(h):
    """Blank battery: power on, the title screen (crop), New Game with NO INFO NEEDED, A through Oak's speech
    until the outfit chooser (overlay 58) is shown; its list strings are read where the game reads them."""
    import ndspy.rom
    ov = ndspy.rom.NintendoDSRom.fromFile(str(h.rom)).loadArm9Overlays([58])[58]
    sig = bytes(ov.data[:16])               # the overlay's first code bytes: resident or not
    calls = NamingCalls(h)
    reads = set()

    def on_read(addr, size):
        # the RAM is shared with other overlays: count reads only while overlay 58 is resident
        try:
            if h.read(OV58, 16) == sig:
                reads.add(addr & ~1)
        except Exception:
            pass
    h.emu.memory.register_read(OV58_STRINGS[0], on_read, size=OV58_STRINGS[1] - OV58_STRINGS[0])
    obs = {}
    h.step(TITLE_FRAME)
    h.press("START", after=400)        # skips the intro movie to the title screen
    shot, _ = screenshot(h, "newgame_title", crops=("title-subtitle",))
    obs["title"] = shot
    for i in range(160):
        if h.read(OV58, 16) == sig:
            obs["chooser_after_presses"] = i
            break
        h.touch(130, 152, after=4)          # NO INFO NEEDED on the controls-info menu (harmless elsewhere)
        h.press("A", after=56)
    else:
        obs["error"] = "the outfit chooser (overlay 58) never loaded"
        obs["max_len"] = calls.by_site()
        return obs
    h.step(90)
    shot, _ = screenshot(h, "newgame_outfit_chooser")
    obs["chooser"] = shot
    ptrs = list(struct.unpack("<3I", h.read(OV58_ITEM_PTRS, 12))) + [h.u32(OV58_OK_LITERAL)]
    obs["items"] = [{"ptr": p, "text": decode(h.read(p, 32)), "in_original_slots":
                     OV58_ORIGINAL_SLOTS[0] <= p < OV58_ORIGINAL_SLOTS[1]} for p in ptrs]
    h.emu.memory.register_read(OV58_STRINGS[0], None, size=OV58_STRINGS[1] - OV58_STRINGS[0])
    # an item string the game read while building the list: its first code unit was read
    obs["read_by_the_game"] = [i["text"] for i, p in zip(obs["items"], ptrs) if p in reads]
    obs["reads"] = len(reads)
    obs["max_len"] = calls.by_site()
    return obs


def observe_pcbox(h):
    """Cherrygrove Pokemon Center: the PC (std script 2010), A until the box screen (overlay 16) is up; the
    top screen shows party Pokemon 1 (full_bag_6mons.sav: Charmeleon, 10 letters, before the gender icon)."""
    h.run_script(script_id=PC_STD_SCRIPT, settle=60)
    for i in range(16):
        h.press("A", after=80)
        if h.read(PCBOX_TEMPLATES, 3) == bytes([4, 8, 5]):
            break
    h.step(120)
    shot, img = screenshot(h, "pcbox_top")
    tmpl = h.read(PCBOX_TEMPLATES, 0x18 * 8)
    rgb = img.convert("RGB")
    x0, y0, x1, y1 = NAME_ROW
    ink = [(x, y) for x in range(x0, x1) for y in range(y0, y1) if sum(rgb.getpixel((x, y))) < 300]
    return dict(shot, a_presses=i + 1, template=tmpl[:8].hex(), name_window_width=tmpl[3],
                base_tiles=[int.from_bytes(tmpl[8 * k + 6:8 * k + 8], "little") for k in range(9)],
                ink_columns_x120_127=len(ink_columns(img, NAME_BOX, threshold=300)),
                name_ink_pixels=len(ink), name_ink_right=max((x for x, _ in ink), default=None))


def observe_ivev(h):
    """Party -> summary of slot 0 -> skills page (RIGHT) -> L: the IV/EV panel. Hooks the x of the IV numbers
    and of the 'IVs' header; measures, per stat row, the distance between the IV and EV columns' right edges."""
    import emu_harness as E
    iv_x, header_x = [], []
    h.on_exec(IVEV_IV_CALL, lambda m: iv_x.append(m.reg.r2))
    h.on_exec(IVEV_HEADER_CALL, lambda m: header_x.append(m.reg.r3))
    h.touch(*E.FIELD_MENU["pokemon"], frames=12, after=150)
    h.touch(*E.PARTY_SLOTS[0], frames=12, after=60)
    h.touch(*E.PARTY_SUMMARY, frames=12, after=150)
    h.press("RIGHT", after=60)
    shot, _ = screenshot(h, "ivev_skills", crops=("type-icon-summary",))
    h.press("L", after=90)
    panel, img = screenshot(h, "ivev_panel")
    rows = []
    for y0, y1 in IVEV_ROWS:
        edges = column_distance(ink_columns(img, (IVEV_X[0], y0, IVEV_X[1], y1)))
        rows.append(None if edges is None else edges[1] - edges[0])
    return {"skills": shot, "panel": panel, "iv_x": sorted(set(iv_x)), "iv_calls": len(iv_x),
            "header_x": sorted(set(header_x)), "iv_ev_distance": rows}


def observe_antipiracy(h):
    """Continue (overlay 115) and field start (overlay 1), then the bag and the party (field exit and start
    again): every call of the six DS Protect entries, the bytes there, whether the check body ran, and the
    value each call returned (read at its return address)."""
    import emu_harness as E
    log = h.__dict__["_antipiracy_log"]
    h.open_bag()
    h.step(60)
    h.press("B", after=300)
    h.touch(*E.FIELD_MENU["pokemon"], frames=12, after=200)
    h.press("B", after=300)
    h.step(120)
    entries = {}
    for row in log:
        e = entries.setdefault(f"{row['entry']:#010x}", {"calls": 0, "returns": [], "body_runs": 0, "code": set()})
        if row["kind"] == "entry":
            e["calls"] += 1
            e["code"].add(row["code"])
        elif row["kind"] == "body":
            e["body_runs"] += 1
        else:
            e["returns"].append(row["r0"])
    for e in entries.values():
        e["code"] = sorted(e["code"])
        e["returns"] = sorted(set(e["returns"]))
    return {"entries": entries}


def antipiracy_hooks(h):
    """Installed before boot (Continue runs three of the entries)."""
    log = h.__dict__.setdefault("_antipiracy_log", [])
    returns = {}
    for entry in ANTIPIRACY_ENTRIES:
        def on_entry(m, entry=entry):
            code = m.read(entry, 8)
            if code != ANTIPIRACY_PROLOGUE and code[4:] != bytes.fromhex("1eff2fe1"):
                return              # another overlay occupies this RAM: not a DS Protect call
            log.append({"kind": "entry", "entry": entry, "code": code.hex(), "frame": m.frame})
            ret = m.reg.lr & ~1
            if ret not in returns:
                returns[ret] = entry
                m.on_exec(ret, lambda mm, ret=ret: log.append({"kind": "return", "entry": returns[ret],
                                                               "r0": mm.reg.r0, "frame": mm.frame}))

        def on_body(m, entry=entry):
            if m.read(entry, 8) == ANTIPIRACY_PROLOGUE:
                log.append({"kind": "body", "entry": entry, "frame": m.frame})
        h.on_exec(entry, on_entry)
        h.on_exec(entry + 8, on_body)


def _set_friendship(h, slot, value):
    """Block A +0x0C of a party Pokemon (friendship), re-encrypted with a new checksum (test-only edit)."""
    import emu_harness as E
    a = h.array(E.ARR_PARTY) + 8 + 236 * slot
    raw = bytearray(h.read(a, 136))
    pid, _, cs = struct.unpack_from("<IHH", raw)
    words = struct.unpack_from("<64H", raw, 8)
    plain = bytearray(struct.pack("<64H", *[w ^ k for w, k in zip(words, E._prng_stream(cs, 64), strict=True)]))
    plain[E.BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24].index("A") * 32 + 0x0C] = value
    words = struct.unpack("<64H", plain)
    cs = sum(words) & 0xFFFF
    struct.pack_into("<H", raw, 6, cs)
    struct.pack_into("<64H", raw, 8, *[w ^ k for w, k in zip(words, E._prng_stream(cs, 64), strict=True)])
    h.write(a, bytes(raw))


def _party_mon(h, slot):
    import emu_guide0107 as G
    import emu_harness as E
    m = G.mon_details(h.read(h.array(E.ARR_PARTY) + 8 + 236 * slot, 236))
    return {k: m[k] for k in ("species", "level", "moves", "checksum_ok")}


def observe_evolution(h):
    """EVOLUTION_CASES one after another: create the Pokemon with the hack's generator, set its moves, use a Rare
    Candy (or a Thunder Stone) from the bag and press A through the level-up, the evolution scene and its
    'wants to learn' / forget-a-move flow (A answers 'Forget a move!', picks the first move, Tackle, and
    confirms) until the scene's learn call returns 0, or for the plain level-up until the level-up's learn call
    does. Records every return of the evolution scene's learn call and the Pokemon afterwards."""
    import emu_harness as E
    log = []
    h.on_exec(EVO_LEARN_RETURN, lambda m: log.append(("evo", m.reg.r0, m.u16(m.reg.sp + 0xE))))
    h.on_exec(LEVELUP_LEARN_RETURN, lambda m: log.append(("levelup", m.reg.r0, None)))
    cases = {}
    for name, (species, level, moves, item, friendship, _, _, _) in EVOLUTION_CASES.items():
        h.generate_pokemon(species, level=level)
        slot = h.generated_slot
        h.edit_party_mon(slot, moves=list(moves))
        if friendship is not None:
            _set_friendship(h, slot, friendship)
        before = _party_mon(h, slot)
        del log[:]
        pocket = "items" if item else "medicine"
        h.bag_put_first(item or RARE_CANDY_ITEM, 5, pocket)
        h.open_bag()
        h.bag_pocket(pocket)
        h.touch(*E.BAG_SLOTS[0], frames=12, after=60)
        h.touch(*E.BAG_USE, frames=12, after=60)
        h.touch(*E.PARTY_SLOTS[slot], frames=12, after=120)
        presses = 0
        evolves = EVOLUTION_CASES[name][5] != species
        while presses < 60:
            h.press("A", after=90)
            presses += 1
            if evolves and any(site == "evo" and r0 == 0 for site, r0, _ in log):
                break                      # the scene asked for the last time: nothing left to learn
            if not evolves and any(site == "levelup" and r0 == 0 for site, r0, _ in log):
                h.step(600)                # no input is needed after the level-up's last move; an extra A
                break                      # in the bag would open the candy's menu
        h.step(300)
        shot = h.screenshot(f"evolution_{name}")
        after = _party_mon(h, slot)
        for _ in range(3):                 # back to the field: bag (and an item menu an extra A opened) closed
            h.press("B", after=120)
        cases[name] = {"before": before, "after": after, "a_presses": presses, "screenshot": str(shot),
                       "evo_calls": [{"r0": r0, "move": mv} for site, r0, mv in log if site == "evo"],
                       "levelup_calls": [r0 for site, r0, _ in log if site == "levelup"]}
    return {"cases": cases}


def observe_font(h):
    """In the field: the width tables of the fonts the game keeps in RAM (0, 1, 4), found by their first 0x1A0
    bytes (which the fix does not touch), and the widths the text printer reads for … “ ”."""
    import ndspy.narc
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(str(h.rom))
    narc = ndspy.narc.NARC(rom.getFileByName("a/0/1/6"))
    ram = h.read(0x02000000, 0x400000)
    out = {}
    for fi in FONT_RAM:
        d = narc.files[fi]
        _, wo, cnt = struct.unpack_from("<III", d, 0)
        prefix = bytes(d[wo:wo + 0x1A0])
        hits = []
        i = ram.find(prefix)
        while i >= 0:
            hits.append(i)
            i = ram.find(prefix, i + 1)
        out[str(fi)] = {"tables_in_ram": [f"{0x02000000 + i:#010x}" for i in hits],
                        "widths": sorted({tuple(ram[i + c - 1] for c in FONT_CODES) for i in hits})}
    return {"fonts": out}


def observe_textspeed(h):
    """One field message printed with the Options text speed NORMAL (bits 2-3 = 0) and FAST (1): the frame,
    counted from the script start, of the last change inside the message window's text area (page 1 complete;
    the blinking page arrow is outside the crop)."""
    import emu_harness as E
    out = {}
    for mode, value in (("normal", 0), ("fast", 1)):
        opt = h.array(1)
        h.w16(opt, (h.u16(opt) & ~0x000C) | (value << 2))
        saved = h.get_var(E.SENTINEL_VAR)
        h.set_var(E.SENTINEL_VAR, 0)
        bank, msg = TEXT_SPEED_MSG
        h.run_script(file=3, index=0, msg_bank=bank, program=E.message_script(bank, msg), settle=0)
        start, last, prev, changes = h.frame, None, None, 0
        for _ in range(TEXT_SPEED_FRAMES):
            h.step(1)
            digest = crop_digest(h.emu.screenshot(), TEXT_WINDOW)
            if prev is not None and digest != prev:
                last, changes = h.frame - start, changes + 1
            prev = digest
        shot = str(h.screenshot(f"textspeed_{mode}"))
        for _ in range(10):
            if h.get_var(E.SENTINEL_VAR) == 0x5A5A:
                break
            h.press("A", after=200)
        h.set_var(E.SENTINEL_VAR, saved)
        out[mode] = {"last_text_change_frame": last, "text_changes": changes, "screenshot": shot}
    return out


def observe_battle(h):
    """A scripted wild battle (Shuckle Lv5), FIGHT: the move buttons with their type icons."""
    import emu_harness as E
    import emu_open
    emu_open.wild_battle(h, 213, 5)
    if not h.wait_screen("battle_menu", 2400):
        return {"error": "the battle command menu never appeared"}
    h.touch(*E.BATTLE_BUTTONS["fight"], frames=10, after=90)
    shot, _ = screenshot(h, "battle_fight", crops=("type-icon-battle",))
    return {"fight": shot}


SCENARIOS = {
    # name: (save file or None for a blank battery, start map or None, observe, needs the Chinese reference run)
    "naming": ("full_bag_6mons.sav", None, observe_naming, True),
    "newgame": (None, None, observe_newgame, True),
    "pcbox": ("full_bag_6mons.sav", PC_MAP, observe_pcbox, False),
    "ivev": ("full_bag_6mons.sav", None, observe_ivev, True),
    "antipiracy": ("full_bag_6mons.sav", None, observe_antipiracy, False),
    "font": ("full_bag_6mons.sav", None, observe_font, False),
    "textspeed": ("full_bag_6mons.sav", None, observe_textspeed, False),
    "battle": ("full_bag_6mons.sav", None, observe_battle, True),
    "evolution": ("full_bag_6mons.sav", None, observe_evolution, False),
}
EXTERNAL = {"msgload", "texture-bounds", "reflection"}  # scenarios run by other tools (memcheck.py,
#                                                         emu_texture_bounds.py, emu_reflection.py)
ALL_SCENARIOS = tuple(SCENARIOS) + tuple(sorted(EXTERNAL))


def observe(scenario, rom, sav_dir, out):
    """Run one in-process scenario (in a child process: one emulator per process)."""
    import emu_harness as E
    sav, start, fn, _ = SCENARIOS[scenario]
    # the emulator runs in a private working directory: every path absolute
    rom, sav_dir, out = Path(rom).resolve(), Path(sav_dir).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if sav is None:
        with E.Harness(rom, out=out, verbose=False) as h:
            obs = fn(h)
    else:
        hooks = antipiracy_hooks if scenario == "antipiracy" else None
        place = start or (None, None, None)
        with E.start_at(*place, rom=rom, sav=Path(sav_dir) / sav, out=out, verbose=False, hooks=hooks) as h:
            obs = fn(h)
    obs["seconds"] = round(time.time() - t0, 1)
    return obs


# --------------------------------------------------------------------------------------------- classifiers
def _state(fixed_ok, original_ok, why):
    return ("fixed" if fixed_ok and not original_ok else "original" if original_ok and not fixed_ok
            else "unclear"), why


def judge_namelen(scenario, obs, ref=None):
    sites = obs.get("max_len", {})
    want = {"naming": ("namelen-player-script", "namelen-rival-script", "namelen-nickname-script"),
            "newgame": ("namelen-player-intro", "namelen-rival-intro")}[scenario]
    got = {s: sites.get(s) for s in want}
    fixed = all(got[s] == [NAMING_SITES_BY_ID[s][1]] for s in want)
    original = all(got[s] == [NAMING_SITES_BY_ID[s][2]] for s in want)
    why = {"max_len": got}
    if scenario == "naming":
        player, nick = obs["player"], obs["nickname"]
        typed = (len(player["codes"]), len(nick["codes"]))
        why["typed_lengths"] = {"player": typed[0], "nickname": typed[1], "player_text": player["text"],
                                "nickname_text": nick["text"]}
        # the typed names: 7 / 10 with the fix, 5 / 5 without (A on the first key types 'A' either way)
        fixed = fixed and typed == (7, 10)
        original = original and typed == (5, 5)
    return _state(fixed, original, why)


def judge_naming_keyboard(scenario, obs, ref=None):
    player = obs["player"]
    first = player["codes"][:1]
    why = {"ime_path_runs": obs["ime_path_runs"], "first_code": [f"{c:#06x}" for c in first],
           "player_text": player["text"]}
    fixed = obs["ime_path_runs"] == 0 and first == [CH_A] and set(player["codes"]) == {CH_A}
    # without the fix the first key is a blank pinyin candidate: nothing is typed (the name may be a default)
    original = obs["ime_path_runs"] > 0 and set(player["codes"]) != {CH_A}
    return _state(fixed, original, why)


def _judge_crop(key, shot, ref_shot):
    """'fixed': the crop is the approved one (APPROVED) and not the Chinese ROM's; 'original': it is the
    Chinese ROM's. Any other picture (a mirrored label, a wrong palette, a missing tile) is 'unclear'."""
    mine = (shot or {}).get("crops", {}).get(key)
    theirs = (ref_shot or {}).get("crops", {}).get(key)
    approved = APPROVED[key]
    why = {"crop": CROPS[key], "digest": mine, "chinese_rom_digest": theirs, "approved_digest": approved["digest"],
           "approved_by": approved["approved_by"]}
    if not mine or not theirs:
        return "unclear", dict(why, error="crop missing")
    if not approved["digest"]:
        return "unclear", dict(why, error=f"no approved digest for {key}")
    return _state(mine == approved["digest"] and mine != theirs, mine == theirs, why)


def judge_outfit(scenario, obs, ref=None):
    items = obs.get("items")
    if not items:
        return "unclear", {"error": obs.get("error", "no list items")}
    texts = [i["text"] for i in items]
    read = obs.get("read_by_the_game", [])
    why = {"items": texts, "read_by_the_game": read}
    english = ["Outfit 1", "Outfit 2", "Outfit 3", "OK"]
    fixed = texts == english and read == english
    original = all(i["in_original_slots"] for i in items) and not any(t in english for t in texts)
    return _state(fixed, original, why)


def judge_pcbox(scenario, obs, ref=None):
    """The window templates in RAM (width and every moved base tile) and the name's pixels: with the fix the
    name's last letter reaches into the 8th tile (x 120-127); without it the text stops at x 119."""
    why = {k: obs.get(k) for k in ("name_window_width", "base_tiles", "ink_columns_x120_127", "name_ink_pixels",
                                   "name_ink_right", "template")}
    right = obs.get("name_ink_right")
    fixed = (obs["name_window_width"] == 8 and obs.get("base_tiles") == PCBOX_BASES["fixed"]
             and obs["ink_columns_x120_127"] > 0 and right is not None and right >= 120)
    original = (obs["name_window_width"] == 7 and obs.get("base_tiles") == PCBOX_BASES["original"]
                and obs["ink_columns_x120_127"] == 0 and right is not None and right <= 119)
    return _state(fixed, original, why)


def pair_pcbox(fixed, control):
    """The fixed name shows more of the text than the cut one."""
    return fixed["name_ink_pixels"] > control["name_ink_pixels"], {
        "name_ink_pixels": [fixed["name_ink_pixels"], control["name_ink_pixels"]]}


def judge_ivev(scenario, obs, ref=None):
    dist = obs["iv_ev_distance"]
    why = {k: obs[k] for k in ("iv_x", "header_x", "iv_calls", "iv_ev_distance")}

    def is_state(iv, header):
        # the right edges of the IV and EV numbers are (EV x - IV x) apart; the last digits' ink moves the
        # measured edge by 1 px (observed 31-33 with the fix, 37-39 without)
        return (obs["iv_x"] == [iv] and obs["header_x"] == [header] and obs["iv_calls"] >= 6
                and all(d is not None and abs(d - (IVEV_EV_X - iv)) <= 1 for d in dist))
    return _state(is_state(0x20, 0x28), is_state(0x1A, 0x22), why)


def pair_ivev(fixed, control):
    """Row by row the IV column sits exactly 6 px further right (the same digits on both builds)."""
    shift = [c - f if c is not None and f is not None else None
             for f, c in zip(fixed["iv_ev_distance"], control["iv_ev_distance"])]
    return shift == [0x20 - 0x1A] * len(IVEV_ROWS), {"iv_shift_px": shift}


def judge_antipiracy(scenario, obs, ref=None):
    entries = obs["entries"]
    why = {"entries": entries}
    reached = set(entries) == {f"{e:#010x}" for e in ANTIPIRACY_ENTRIES}
    genuine = all(entries[f"{e:#010x}"]["returns"] == [v] for e, v in ANTIPIRACY_ENTRIES.items()
                  if f"{e:#010x}" in entries)
    stubs = all(e["body_runs"] == 0 and all(c != ANTIPIRACY_PROLOGUE.hex() for c in e["code"])
                for e in entries.values())
    bodies = all(e["body_runs"] == e["calls"] > 0 for e in entries.values())
    # DeSmuME passes the checks either way, so both return the genuine values; the fix skips the check bodies
    return _state(reached and genuine and stubs, reached and genuine and bodies, why)


def judge_font(scenario, obs, ref=None):
    fonts = obs["fonts"]
    why = {"fonts": fonts}

    def is_state(state):
        return all(fonts[str(fi)]["widths"] == [[FONT_WIDTHS[state][fi]] * len(FONT_CODES)] for fi in FONT_RAM)
    return _state(is_state("fixed"), is_state("original"), why)


def judge_textspeed(scenario, obs, ref=None):
    n, f = obs["normal"]["last_text_change_frame"], obs["fast"]["last_text_change_frame"]
    why = {"normal_page_frames": n, "fast_page_frames": f, "message": "%d#%d" % TEXT_SPEED_MSG}
    if not n or not f:
        return "unclear", dict(why, error="no text printed")
    why["normal_over_fast"] = round(n / f, 2)
    # FAST prints up to three glyphs per frame (D-1601): its page completes in well under half NORMAL's frames;
    # the hack has no FAST and ignores the bits (observed: 28 / 8 frames with the fix, 29 / 30 without)
    return _state(n / f >= 2.0, n / f <= 1.25, why)


NAMING_SITES_BY_ID = {v[0]: v for v in NAMING_SITES.values()}
JUDGES = {
    ("naming", "namelen"): judge_namelen,
    ("newgame", "namelen"): judge_namelen,
    ("naming", "naming-keyboard"): judge_naming_keyboard,
    ("naming", "gfx-naming-tabs"): lambda s, o, r: _judge_crop("naming-tabs", o.get("player"),
                                                               (r or {}).get("player")),
    ("newgame", "outfit-chooser-strings"): judge_outfit,
    ("newgame", "gfx-title-subtitle"): lambda s, o, r: _judge_crop("title-subtitle", o.get("title"),
                                                                   (r or {}).get("title")),
    ("pcbox", "pcbox-name-width"): judge_pcbox,
    ("ivev", "ivev-panel"): judge_ivev,
    ("ivev", "gfx-type-icons"): lambda s, o, r: _judge_crop("type-icon-summary", o.get("skills"),
                                                            (r or {}).get("skills")),
    ("battle", "gfx-type-icons"): lambda s, o, r: _judge_crop("type-icon-battle", o.get("fight"),
                                                              (r or {}).get("fight")),
    ("antipiracy", "antipiracy"): judge_antipiracy,
    ("font", "font-glyphs"): judge_font,
    ("textspeed", "text-speed"): judge_textspeed,
}


# --------------------------------------------------------------------------------------------- external scenarios
def run_msgload(rom, cn, sav_dir, out):
    """memcheck.py's 'summary' scenario (party -> summary, switch Pokemon on every page; the rc3 crash)."""
    out = Path(out)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(TOOLS / "memcheck.py"), "run", "--saves", str(sav_dir), "--rom", str(rom),
                        "--ref", str(cn), "--scenario", "summary", "--out", str(out), "--json",
                        str(out / "memcheck.json")], capture_output=True, text=True)
    try:
        rep = json.loads((out / "memcheck.json").read_text())
    except (OSError, ValueError):
        return {"error": f"memcheck.py failed (rc {r.returncode}): {r.stderr[-800:]}", "seconds": 0}
    sc = rep.get("scenarios", {}).get("summary", {})
    return {"rc": r.returncode, "status": sc.get("status"), "findings": sc.get("findings", []),
            "report": str(out / "memcheck.json"), "seconds": round(time.time() - t0, 1)}


def judge_msgload(scenario, obs, ref=None):
    sig = [f.get("signature") for f in obs.get("findings", []) if f.get("category") == "english_regression"]
    why = {"status": obs.get("status"), "english_regressions": sig, "report": obs.get("report")}
    crash = any(s and s[0] == "allocation" and s[1] == 19 for s in sig)
    return _state(obs.get("status") == "passed" and not sig, crash, why)


def run_texture_bounds(rom, expect, sav_dir, out):
    import emu_harness as E
    out = Path(out)
    if (out / "report.json").exists():       # --overwrite: texture-bounds refuses an existing report
        os.replace(out / "report.json", out / "report.previous.json")
    t0 = time.time()
    rc, _, err = E.spawn(["texture-bounds", "--rom", Path(rom).resolve(), "--sav",
                          (Path(sav_dir) / "full_bag_6mons.sav").resolve(), "--out", out.resolve(), "--case", "all",
                          "--expect", expect], timeout=900)
    try:
        rep = json.loads((out / "report.json").read_text())
    except (OSError, ValueError):
        return {"error": f"texture-bounds failed (rc {rc}): {err[-800:]}", "seconds": 0}
    return {"expect": expect, "rc": rc, "passed": rep.get("passed"), "error": rep.get("error"),
            "cases": [{"name": c["name"], "passed": c["passed"], "null_loads": c.get("trace", {}).get("null_loads"),
                       "failures": c.get("failures")} for c in rep.get("cases", [])],
            "report": str(out / "report.json"), "seconds": round(time.time() - t0, 1)}


def judge_texture_bounds(scenario, obs, ref=None):
    why = {k: obs.get(k) for k in ("expect", "passed", "cases", "error", "report")}
    ok = bool(obs.get("passed")) and obs.get("rc") == 0
    return _state(ok and obs.get("expect") == "fixed", ok and obs.get("expect") == "original", why)


def run_reflection(rom, expect, sav_dir, out):
    """emu_reflection.py (Bulbasaur following next to water) on one ROM: --expect original on a control, fixed
    on the ROM under test."""
    import emu_harness as E
    out = Path(out)
    if (out / "report.json").exists():       # --overwrite: reflection refuses an existing report
        os.replace(out / "report.json", out / "report.previous.json")
    t0 = time.time()
    rc, _, err = E.spawn(["reflection", "--rom", Path(rom).resolve(), "--sav",
                          (Path(sav_dir) / "market.sav").resolve(), "--out", out.resolve(), "--case", "all",
                          "--scene", "all", "--expect", expect], timeout=900)
    try:
        rep = json.loads((out / "report.json").read_text())
    except (OSError, ValueError):
        return {"error": f"reflection failed (rc {rc}): {err[-800:]}", "seconds": 0}
    return {"expect": expect, "rc": rc, "passed": rep.get("passed"), "error": rep.get("error"),
            "cases": [{"scene": c.get("scene"), "name": c["name"], "passed": c["passed"],
                       "null_returns": c.get("trace", {}).get("counts", {}).get("null_return", 0),
                       "failures": c.get("failures")} for c in rep.get("cases", [])],
            "report": str(out / "report.json"), "seconds": round(time.time() - t0, 1)}


def judge_reflection(scenario, obs, ref=None):
    why = {k: obs.get(k) for k in ("expect", "passed", "cases", "error", "report")}
    ok = bool(obs.get("passed")) and obs.get("rc") == 0
    return _state(ok and obs.get("expect") == "fixed", ok and obs.get("expect") == "original", why)


def judge_evolution(scenario, obs, ref=None):
    """Every case evolves (or, for the plain level-up, does not) with a valid checksum and learns its new-level
    moves; 'fixed': every evolution move learned (charizard_full: offered with 0xFFFF and learned in Tackle's
    place) and the plain level-up offers no evolution move; 'original': no evolution move offered at all."""
    cases, why, fixed, original = obs["cases"], {}, True, True
    for name, (_, _, moves, _, _, target, evo_moves, level_moves) in EVOLUTION_CASES.items():
        c = cases[name]
        after, offered = c["after"], [e["move"] for e in c["evo_calls"] if e["r0"] != 0]
        base = (after["species"] == target and after["checksum_ok"]
                and all(mv in after["moves"] for mv in level_moves))
        learned = [mv for mv in evo_moves if mv in after["moves"]]
        why[name] = {"species": after["species"], "moves": after["moves"], "evo_calls": c["evo_calls"],
                     "evolution_moves_learned": learned}
        if not evo_moves:            # plain level-up: no evolution scene, never Air Slash
            ok = base and not c["evo_calls"] and EVOLUTION_LEVELUP_ONLY_FORBIDDEN not in after["moves"]
            fixed &= ok
            original &= ok
            continue
        got = base and learned == list(evo_moves) and all(mv in offered for mv in evo_moves)
        if name == "charizard_full":
            got = got and {"r0": 0xFFFF, "move": 403} in c["evo_calls"] and TACKLE not in after["moves"]
        fixed &= got
        original &= base and not learned and not any(mv in offered for mv in evo_moves) \
            and (name != "charizard_full" or after["moves"] == list(moves))
    return _state(fixed, original, why)


JUDGES[("msgload", "msgload")] = judge_msgload
# checks across the two runs of a fix (fixed ROM, control), after both judged right
PAIR_CHECKS = {("ivev", "ivev-panel"): pair_ivev, ("pcbox", "pcbox-name-width"): pair_pcbox}
JUDGES[("texture-bounds", "overworld-texture-frame-bounds")] = judge_texture_bounds
JUDGES[("reflection", "bulbasaur-reflection-boundary")] = judge_reflection
JUDGES[("evolution", "evolution-moves")] = judge_evolution


# --------------------------------------------------------------------------------------------- runner
def scenario_fixes(scenario):
    return [fx for fx, scs in COVERAGE.items() if scenario in scs]


def select(case):
    """--case: 'all', scenario names and/or fix ids -> the scenarios to run, with the fixes judged in each."""
    if case == "all":
        return {sc: scenario_fixes(sc) for sc in ALL_SCENARIOS}
    out = {}
    for name in case.split(","):
        if name in ALL_SCENARIOS:
            out.setdefault(name, [])
            out[name] = sorted(set(out[name]) | set(scenario_fixes(name)))
        elif name in COVERAGE:
            for sc in COVERAGE[name]:
                out.setdefault(sc, [])
                out[sc] = sorted(set(out[sc]) | {name})
        elif name in UNCOVERED:
            raise ValueError(f"{name} has no scenario: {UNCOVERED[name]}")
        else:
            raise ValueError(f"unknown scenario or fix {name!r}; scenarios: {', '.join(ALL_SCENARIOS)}")
    return out


def dependents(fix_id, fixes=None):
    """The fix plus every enabled fix that requires it (directly or not): what --without must drop."""
    import fixes as fixreg
    fixes = fixes if fixes is not None else fixreg.load_all()
    drop, changed = {fix_id}, True
    while changed:
        changed = False
        for fx in fixes:
            if fx["id"] not in drop and set(fx.get("requires", [])) & drop:
                drop.add(fx["id"])
                changed = True
    return sorted(drop)


def control_path(controls, fix_id):
    return Path(controls) / f"no-{fix_id}.nds"


def build_control(fix_id, controls, armips=None, log=print):
    """build.py --no-patch --without <fix and its dependents> --out <controls>/no-<fix>.nds."""
    controls = Path(controls).resolve()   # build.py runs from the repo root
    controls.mkdir(parents=True, exist_ok=True)
    drop = dependents(fix_id)
    work = controls / f"work-no-{fix_id}"
    cmd = [sys.executable, str(TOOLS / "build.py"), "--no-patch", "--work-dir", str(work), "--out",
           str(control_path(controls, fix_id)), "--without", ",".join(drop)]
    if armips:
        cmd += ["--armips", armips]
    t0 = time.time()
    with open(controls / f"no-{fix_id}.log", "w", encoding="utf-8") as f:
        r = subprocess.run(cmd, cwd=WORK.parent, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        raise RuntimeError(f"control build for {fix_id} failed (exit {r.returncode}); log {controls}/no-{fix_id}.log")
    log(f"built control no-{fix_id} (--without {','.join(drop)}) in {time.time() - t0:.0f} s")
    return control_path(controls, fix_id)


def text_sha1(rom_path):
    """SHA-1 over the two message NARCs (check.TEXT_NARCS): a control must carry the same text as the build."""
    import check
    import msgtool
    rom = msgtool.load_rom(str(rom_path))
    h = hashlib.sha1()
    for path in check.TEXT_NARCS:
        h.update(hashlib.sha1(bytes(rom.files[rom.filenames.idOf(path)])).digest())
    return h.hexdigest()


def fixed_applied(rom, rom_report=None):
    """The fixes the fixed ROM was built with: its build report (--rom-report, or build_report.json next to the
    ROM when its rom.sha1 matches), else every enabled fix of the registry (a normal build)."""
    candidates = [Path(rom_report)] if rom_report else [Path(rom).parent / "build_report.json"]
    for rep_path in candidates:
        if rep_path.is_file():
            rep = json.loads(rep_path.read_text(encoding="utf-8"))
            if rep.get("rom", {}).get("sha1") == file_sha1(rom):
                return sorted(rep["fixes"]["applied"]), str(rep_path)
            if rom_report:
                raise ValueError(f"{rep_path} is not the report of {rom} (rom.sha1 differs)")
    import fixes as fixreg
    return sorted(f["id"] for f in fixreg.active_fixes()), "registry (every enabled fix)"


def control_problems(controls, fix_id, applied, text):
    """Why the control ROM no-<fix>.nds cannot be trusted as 'the build without <fix>' ([] when it can): its
    build report must be the file's, list exactly the fixed ROM's fixes minus dependents(fix), and the ROM must
    carry the same message text as the fixed ROM."""
    rom = control_path(controls, fix_id)
    rep_path = Path(controls) / f"work-no-{fix_id}" / "build_report.json"
    if not rom.is_file():
        return [f"{rom} is missing"]
    if not rep_path.is_file():
        return [f"{rep_path} is missing (built elsewhere?)"]
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    problems = []
    if rep.get("rom", {}).get("sha1") != file_sha1(rom):
        problems.append(f"{rep_path} is not the report of {rom.name} (rom.sha1 differs)")
    want = sorted(set(applied) - set(dependents(fix_id)))
    got = sorted(rep.get("fixes", {}).get("applied", []))
    if got != want:
        problems.append(f"applied fixes differ from the build minus {dependents(fix_id)}: extra "
                        f"{sorted(set(got) - set(want))}, missing {sorted(set(want) - set(got))}")
    if not problems and text_sha1(rom) != text:
        problems.append("its message text differs from the fixed ROM's (another tree)")
    return problems


def plan(selection, rom, cn, controls):
    """The runs: (scenario, label, rom). 'fixed' (the ROM under test), 'cn' (reference crops) and one control
    ('no-<fix>') per judged fix."""
    jobs = []
    for sc, fixes in selection.items():
        jobs.append((sc, "fixed", Path(rom)))
        if sc in SCENARIOS and SCENARIOS[sc][3]:
            jobs.append((sc, "cn", Path(cn)))
        for fx in fixes:
            jobs.append((sc, f"no-{fx}", control_path(controls, fx)))
    return jobs


def run_job(job, cn, sav_dir, out):
    import emu_harness as E
    sc, label, rom = job
    d = Path(out) / sc / label
    t0 = time.time()
    try:
        if sc == "msgload":
            obs = run_msgload(rom, cn, sav_dir, d)
        elif sc == "texture-bounds":
            obs = run_texture_bounds(rom, "fixed" if label == "fixed" else "original", sav_dir, d)
        elif sc == "reflection":
            obs = run_reflection(rom, "fixed" if label == "fixed" else "original", sav_dir, d)
        else:
            obs = E.run_child(["fixes-child", "--scenario", sc, "--rom", Path(rom).resolve(), "--sav-dir",
                               Path(sav_dir).resolve(), "--out", d.resolve()], timeout=900)
    except Exception as exc:          # a crash is an observation too: the judge sees no data
        obs = {"error": f"{type(exc).__name__}: {str(exc)[-800:]}"}
    obs.setdefault("seconds", round(time.time() - t0, 1))
    obs["wall_seconds"] = round(time.time() - t0, 1)
    return obs


def judge(selection, results):
    """Per fix: the state on the fixed ROM (every scenario covering it must say 'fixed') and on its control
    (every scenario must say 'original')."""
    rows = []
    for sc, fixes in selection.items():
        ref = results.get((sc, "cn"))
        for fx in fixes:
            row = {"fix": fx, "scenario": sc}
            for label, want in (("fixed", "fixed"), (f"no-{fx}", "original")):
                obs = results.get((sc, label))
                key = "fixed_rom" if label == "fixed" else "control"
                if obs is None:
                    row[key] = {"state": "error", "error": "not run"}
                    continue
                try:
                    state, why = JUDGES[(sc, fx)](sc, obs, ref)
                except Exception as exc:     # missing observations (a crashed run) cannot be judged
                    state, why = "error", {"error": obs.get("error") or f"{type(exc).__name__}: {exc}"}
                row[key] = {"state": state, "expected": want, "evidence": why, "seconds": obs.get("wall_seconds")}
            row["pass"] = (row["fixed_rom"].get("state") == "fixed" and row["control"].get("state") == "original")
            pair = PAIR_CHECKS.get((sc, fx))
            if pair and row["pass"]:
                ok, why = pair(results[(sc, "fixed")], results[(sc, f"no-{fx}")])
                row["pair"] = dict(why, ok=ok)
                row["pass"] = ok
            rows.append(row)
    return rows


BACKEND = "desmume"       # the scenarios use execution hooks and DeSmuME-approved crop digests (APPROVED)


def pin_backend():
    """Run every Harness of this process and its children on DeSmuME, whatever $EMU_HARNESS_EMULATOR says."""
    was = os.environ.get("EMU_HARNESS_EMULATOR")
    if was and was != BACKEND:
        print(f"note: fix scenarios run on {BACKEND}; ignoring EMU_HARNESS_EMULATOR={was}", file=sys.stderr)
    os.environ["EMU_HARNESS_EMULATOR"] = BACKEND


def run(a):
    from concurrent.futures import ThreadPoolExecutor
    pin_backend()
    out = Path(a.out).resolve()
    if (out / "fixes_report.json").exists() and not a.overwrite:
        raise ValueError(f"{out}/fixes_report.json exists; choose a new --out or pass --overwrite")
    selection = select(a.case) if isinstance(a.case, str) else a.case
    rom, cn, sav_dir = Path(a.rom).resolve(), Path(a.rom_cn).resolve(), Path(a.sav_dir).resolve()
    controls = Path(a.controls).resolve()
    t0 = time.time()
    built, provenance = [], {}
    applied, applied_from = fixed_applied(rom, a.rom_report)
    text = text_sha1(rom)
    for fx in sorted({f for fixes in selection.values() for f in fixes}):
        problems = ["--rebuild-controls"] if a.rebuild_controls else control_problems(controls, fx, applied, text)
        if problems:
            if not (a.build_controls or a.rebuild_controls):
                raise ValueError(f"control ROM no-{fx}.nds cannot be used: {'; '.join(problems)} "
                                 "(pass --build-controls to rebuild it)")
            build_control(fx, controls, a.armips)
            built.append(fx)
            problems = control_problems(controls, fx, applied, text)
            if problems:
                raise ValueError(f"rebuilt control no-{fx}.nds still does not match the fixed ROM: "
                                 + "; ".join(problems))
        provenance[fx] = "checked: build report, applied fixes, message text"
    inputs = {"rom": {"path": str(rom), "sha256": file_sha256(rom)}, "cn": {"path": str(cn), "sha256": file_sha256(cn)},
              "controls": {fx: {"path": str(control_path(controls, fx)),
                                "sha256": file_sha256(control_path(controls, fx)),
                                "without": dependents(fx)}
                           for fx in sorted({f for fixes in selection.values() for f in fixes})}}
    jobs = plan(selection, rom, cn, controls)
    print(f"{len(jobs)} runs, {a.jobs} at a time", flush=True)

    def go(job):
        obs = run_job(job, cn, sav_dir, out)
        print(json.dumps({"scenario": job[0], "rom": job[1], "seconds": obs.get("wall_seconds"),
                          **({"error": str(obs["error"])[:200]} if obs.get("error") else {})}), flush=True)
        return job, obs
    with ThreadPoolExecutor(max(1, min(a.jobs, 3))) as ex:
        results = {(job[0], job[1]): obs for job, obs in ex.map(go, jobs)}
    rows = judge(selection, results)
    inputs["fixed_applied_from"] = applied_from
    report = {"schema": 1, "emulator": BACKEND, "inputs": inputs, "controls_built": built, "controls_provenance": provenance, "seconds": round(time.time() - t0, 1),
              "pass": all(r["pass"] for r in rows), "fixes": rows,
              "uncovered": {fx: why for fx, why in UNCOVERED.items()},
              "observations": {f"{sc}/{label}": obs for (sc, label), obs in results.items()}}
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixes_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'} {r['fix']:32s} {r['scenario']:15s} fixed ROM: "
              f"{r['fixed_rom'].get('state'):8s} control: {r['control'].get('state')}")
    print(json.dumps({"pass": report["pass"], "seconds": report["seconds"], "report": str(out / "fixes_report.json")}))
    return 0 if report["pass"] else 1


def cmd_child(a):
    pin_backend()
    obs = observe(a.scenario, a.rom, a.sav_dir, a.out)
    print("RESULT " + json.dumps(obs, default=str), flush=True)
    return 0


def _case_arg(value):
    try:
        return select(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def add_arguments(p, data):
    """The `fixes` subcommand of emu_harness.py; data = emu_harness.DATA (the checkout's work/ with ROMs)."""
    p.add_argument("--rom", required=True, help="the fixed ROM (a normal build)")
    p.add_argument("--rom-cn", default=str(data / "rom" / "origin_v4.0.3_cn.nds"),
                   help="the untouched Chinese ROM (reference crops, memcheck baseline)")
    p.add_argument("--controls", required=True, help="folder of control ROMs no-<fix>.nds")
    p.add_argument("--build-controls", action="store_true", help="build the missing control ROMs with build.py")
    p.add_argument("--rebuild-controls", action="store_true",
                   help="build every selected control ROM again (a control from an older tree proves nothing)")
    p.add_argument("--armips", help="armips for --build-controls (default: $ARMIPS, PATH)")
    p.add_argument("--case", default="all", type=_case_arg,
                   help="all, or scenario names / fix ids: " + ",".join(ALL_SCENARIOS))
    p.add_argument("--rom-report", help="build_report.json of --rom (default: next to the ROM, else the registry's "
                                        "enabled fixes): what each control must equal minus its fix")
    p.add_argument("--overwrite", action="store_true", help="reuse --out (a fixed run folder; files are replaced)")
    p.add_argument("--sav-dir", default=str(data / "build" / "memcheck"),
                   help="folder with full_bag_6mons.sav and route1_path_2mons.sav (read only; default "
                        "<checkout>/work/build/memcheck, the same folder as check.py --emu-saves)")
    p.add_argument("--out", default=str(data / "build" / "harness" / "fixes" / time.strftime("%Y%m%dT%H%M%S")))
    p.add_argument("--jobs", type=int, default=3, help="parallel emulator runs (at most 3)")


def add_child_arguments(p):
    p.add_argument("--scenario", required=True, choices=tuple(SCENARIOS))
    p.add_argument("--rom", required=True)
    p.add_argument("--sav-dir", required=True)
    p.add_argument("--out", required=True)


if __name__ == "__main__":
    sys.path.insert(0, str(TOOLS))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    import emu_harness
    add_arguments(ap, emu_harness.DATA)
    sys.exit(run(ap.parse_args()))
