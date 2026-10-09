#!/usr/bin/env python3
"""emu_harness - put the game into a test state by editing memory, then observe it (py-desmume).

Runs the untouched Chinese hack (default) or our English build headless, starting from a battery save,
and lets a test script teleport the player, set event flags, force the clock, walk, log wild encounters
and take screenshots, without playing through. See work/notes/emu_harness.md for the RAM layout it relies
on and how each address was found.

Needs the project venv (py-desmume, capstone, ndspy, pillow; see emu_smoke.py):
    <venv>/bin/python work/tools/emu_harness.py info  [--rom R] [--sav S] [--clock ISO]
        boot the save, Continue, print location, clock and party, screenshot the field
    <venv>/bin/python work/tools/emu_harness.py unown [--rom R] [--sav S] [--map 315 --x 17 --y 24]
        [--flags 2423,2424,2425,2426] [--count 20] [--clock ISO] [--out work/build/harness] [--json OUT]
        POC for D-1487: teleport into the Ruins of Alph Unown room through the battery save, walk until
        --count wild Pokemon were built, log species / letter picked / final form of each, flee every battle
    <venv>/bin/python work/tools/emu_harness.py wild --map M --x X --y Y [--walk LEFT,RIGHT --span 3]
        [--flags ...] [--clock ISO] [--count N]       the same for any map (e.g. Pal Park on a Friday)

Nothing is written next to the ROM or the save: the emulator runs in a temporary directory and the battery
save is imported read-only. Screenshots and reports go to --out (outside git).
"""
import argparse
import datetime
import json
import os
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

# No sound from any emulator this process starts: SDL's dummy audio driver opens no output device
# (the emulated sound chip still runs, so game timing is unchanged).
os.environ["SDL_AUDIODRIVER"] = "dummy"

if __name__ == "__main__":
    # run as a script, the recipe modules' `import emu_harness` must get this module, not a second copy: the
    # child-process registry (stop_children, the signal handlers) has to be one and the same
    sys.modules.setdefault("emu_harness", sys.modules[__name__])

WORK =Path(__file__).resolve().parent.parent
# ROMs, saves and outputs live only in the main checkout (ignored by git). From an agent worktree
# (<main>/.claude/worktrees/<name>/work) fall back to the main checkout's work/.
_parts = WORK.parts
DATA = Path(*_parts[:_parts.index(".claude")], "work") if ".claude" in _parts and not (WORK / "rom").exists() else WORK
if os.environ.get("EMU_HARNESS_DATA"):     # copies outside the repo: point at a checkout's work/ folder
    DATA = Path(os.environ["EMU_HARNESS_DATA"])
DEF_ROM_CN = DATA / "rom" / "origin_v4.0.3_cn.nds"
DEF_ROM_EN = DATA / "build" / "origin_hg_v4.0.3_en_wip.nds"
DEF_SAVES = DATA / "build" / "memcheck"
DEF_OUT = DATA / "build" / "harness"

# ----------------------------------------------------------------------------- addresses (hack arm9 / ov2)
# All addresses are for the hack's code (Japanese HeartGold base, game code IPKJ). Our English build keeps the
# same code, so they hold for both ROMs. CODE_SIG is checked at start-up, so a ROM with different code fails
# loudly instead of producing wrong results.
SAVE_ARRAY_GET = 0x02027740    # SaveArray_Get(SaveData *save, int id): save + 0x10 + table[id].offset
SAVE_TABLE = 0x2E01C           # offset of the array table inside SaveData; 16-byte rows, +0 = array offset
SAVE_PTR_GLOBAL = 0x021D11B4   # a global holding SaveData* (found by scanning RAM for the pointer)
ARR_VARS_FLAGS = 4             # Save_VarsFlags_Get = 0x0204F858 (SaveArray_Get(save, 4))
ARR_LOCAL_FIELD = 5            # Save_LocalFieldData_Get = 0x0203AEBC (SaveArray_Get(save, 5))
ARR_PARTY = 2                  # Save_PlayerParty_Get = 0x0207365C
FLAGS_OFFSET = 0x2E0           # CheckFlagInArray 0x0204F864 -> GetFlagAddr 0x0204F8E4: vars + 0x2E0 + flag/8
FLAGS_MAX = 0x4000             # flags >= 0x4000 are temp flags in a global (0x021D320C)
VARS_BASE = 0x4000             # var ids start at 0x4000; vars live at vars + (id - 0x4000) * 2
WILD_FINALIZE = 0x022489DC     # ov2: wild Pokemon finalizer (r2 = Pokemon *mon); D-1487
WILD_FINALIZE_SETFORM = 0x02248A40   # bl SetMonData(mon, 0x70 FORM, &letter) for Unown (species 0xC9)
WILD_FINALIZE_AFTER_SET = 0x02248A44  # first instruction after the Unown block (reached for every species)
WILD_FINALIZE_RESTORE = 0x02248AD4   # SetMonData(mon, 0x70 FORM, &saved_form): the write-back
WILD_FINALIZE_END = 0x02248AFE
UNOWN_LETTER = 0x022488C4      # ov2: picks the Unown letter for the encounter
ENCOUNTER_GATE = 0x02248420    # ov2: Unown maps (315, 490-492) need one of flags 2423-2426 (0x20659CC)
OV2_SIG_ADDR = 0x02248A2C
RTC_WORK = 0x021CFE8C          # GF_RTC work: +0x10 RTCDate {u32 year-2000, month, day, weekday 0=Sun},
RTC_DATE, RTC_TIME = RTC_WORK + 0x10, RTC_WORK + 0x20   # +0x20 RTCTime {u32 hour, minute, second}
RTC_SYNC_DONE = 0x020142B2     # end of the async-read callback (0x02014280) that copies the new date/time
CODE_SIG = {
    RTC_SYNC_DONE: "00206060",
    0x0201436C: "10b5041c054800680128",
    SAVE_ARRAY_GET: "38b50c1c051c2a2c01dbfef7eff92001291803482a1c08581032101838bd",
    0x0204F8E4: "38b5051c002901d10020",
}
OV2_SIG = {OV2_SIG_ADDR: "c92809d1301cfff747ff", WILD_FINALIZE_RESTORE: "281c702102aa", WILD_FINALIZE: "f0b583b000900e1c"}

# The hack's debug Pokemon generator (SELECT+X in the field): u32 per menu row. Verified: species, level
# (exp recomputed only when the level is edited in the menu), exp, OT ID, PID, moves 1-2, item, form.
GEN_SPECIES, GEN_LEVEL, GEN_EXP, GEN_OTID, GEN_PID, GEN_MOVE1, GEN_ITEM, GEN_FORM = 0, 1, 2, 3, 4, 7, 11, 47
RUN_BUTTON = (128, 178)
# Bottom-screen touch targets (checked on the Chinese ROM; the English build keeps the layout).
# Field touch menu (from the UI hunt agent; BAG also checked here): left column POKeDEX, POKeMON, BAG,
# POKeGEAR; right column trainer card, SAVE, OPTIONS.
FIELD_MENU = {"pokedex": (43, 33), "pokemon": (43, 73), "bag": (43, 113), "pokegear": (43, 153),
              "card": (123, 33), "save": (123, 73), "options": (123, 113)}
MOVE_BUTTONS = [(64, 40), (192, 40), (64, 104), (192, 104)]   # battle move menu (bottom screen)
# Screen recognition: a few pixels (screenshot coordinates, bottom screen y + 192) and their RGB.
SCREENS_KNOWN = {
    # red FIGHT, blue INFO; the INFO sample sits right of the label (the English build's INFO text covers
    # the old sample 225,207 since the label fix of 2026-10-05)
    "battle_menu": [((60, 252), (232, 56, 56)), ((244, 203), (40, 144, 200))],
}
POKEGEAR_TABS = {"settings": (32, 175), "map": (127, 175)}
BATTLE_BUTTONS = {"fight": (128, 88), "bag": (36, 165), "run": (128, 178), "pokemon": (200, 165), "info": (225, 15)}
BAG_SLOTS = [(64, 56), (192, 56), (64, 98), (192, 98), (64, 140), (192, 140)]   # 6 items per bag page
BAG_GIVE = (47, 173)             # item submenu: give to a Pokemon
PARTY_SLOTS = [(64, 28), (190, 28), (64, 76), (190, 76), (64, 124), (190, 124)]
PARTY_SUMMARY = (190, 40)
BAG_USE = (47, 142)              # item submenu: use
POCKET_TABS = {"items": (15, 15), "medicine": (46, 15), "balls": (80, 15), "tm": (113, 15),
               "berries": (146, 15), "mail": (176, 15), "battle": (206, 15), "key": (239, 15)}        # party submenu: summary (first entry)        # bottom-screen RUN button of the battle command menu
# Event scripts (arm9 + field overlay 1). Talking (A) runs StartMapSceneScript(fsys, id, obj) from the field
# input handler ov1 0x021E5CE4: object in front -> bl at 0x021E5D2C (r1 = id), else the bg-event lookup
# 0x0203D320 returns the id in r0 at 0x021E5D5E (0xFFFF = nothing). Overriding that id on one A press runs
# any script. Script id -> file: 0x0203F81C (table 0x020F70E0; 2000-2499 = file 3, index id-2000), the
# loader 0x0203F870(r2 = file, r3 = message bank) can be redirected to any file; after the jump to the
# script's start (0x0203F812, r4 = context) context+0x08 is the script PC (bytes may be replaced there).
TALK_OBJ_START = 0x021E5D2C
TALK_BG_RESULT = 0x021E5D5E
SCRIPT_LOAD_FILE = 0x0203F870
SCRIPT_STARTED = 0x0203F812
START_MAP_SCENE_SCRIPT = 0x0203F57C
STD_SCRIPT_BASE = 2000
SENTINEL_VAR = 0x40FE          # save var used (and restored) to see when an injected script has finished
OV1_SIG = {TALK_OBJ_START: "59f626fc", TALK_BG_RESULT: "011c"}
SCRIPT_CMDS = Path(__file__).resolve().parent / "docs" / "script_cmds.json"
_SCRIPT_CMD_CACHE = {}


def WARP_CMDS(map_id, x, y, direction=0, before=()):
    """Script commands for a scripted warp, as the hack's own scripts do it: fade out, Warp, fade in."""
    return [("LockAll",), *before, ("FadeScreen", 6, 1, 0, 0), ("WaitFade",), ("Warp", map_id, 0, x, y, direction),
            ("FadeScreen", 6, 1, 1, 0), ("WaitFade",), ("ReleaseAll",), ("End",)]


def script_bytes(*cmds):
    """Encode event-script commands: script_bytes(("LockAll",), ("TrainerBattle", 5, 0, 0, 0), ("End",)).
    Argument sizes come from work/tools/docs/script_cmds.json (pret-style names, hack opcodes)."""
    if not _SCRIPT_CMD_CACHE:
        for op, (name, sizes) in json.loads(SCRIPT_CMDS.read_text()).items():
            _SCRIPT_CMD_CACHE.setdefault(name, (int(op), sizes))
    out = bytearray()
    for name, *args in cmds:
        op, sizes = _SCRIPT_CMD_CACHE[name]
        if len(args) != len(sizes):
            raise ValueError(f"{name} takes {len(sizes)} arguments")
        out += struct.pack("<H", op)
        for size, v in zip(sizes, args):
            out += int(v).to_bytes(size, "little", signed=v < 0)
    return bytes(out)


def message_script(bank, msg_id):
    """Build a normal field-message script without truncating the record ID.

    Its completion writes 0x5A5A to SENTINEL_VAR; callers must initialize and
    restore that sentinel. The script also uses temporary variable 0x8000.
    """
    # NonNPCMsgVar truncates its resolved ID to u8 in the Chinese ROM
    # (021EE2E4/021EE2EA). MsgBoxExtern preserves u16 IDs and calls the
    # same field renderer. Pass the ID through a variable so IDs >= 0x4000
    # cannot be interpreted as variable references by the native command.
    if type(msg_id) is not int or not 0 <= msg_id <= 0xFFFF:
        raise ValueError("message ID must be an unsigned 16-bit integer")
    if type(bank) is not int or not 0 <= bank < 0x4000:
        raise ValueError("message bank must be an immediate integer below 0x4000")
    return script_bytes(("LockAll",), ("SetVar", 0x8000, msg_id), ("MsgBoxExtern", bank, 0x8000),
                        ("WaitButton",), ("CloseMsg",), ("SetVar", SENTINEL_VAR, 0x5A5A), ("ReleaseAll",),
                        ("End",))


KEYS = ("A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L", "X", "Y")
DIRS = {"UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}
UNOWN = 201
UNOWN_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!?"

# Gen 4 Pokemon structure (pret PartyPokemon/BoxPokemon): 8-byte header, 4 encrypted 32-byte blocks
BLOCK_ORDERS = ["ABCD", "ABDC", "ACBD", "ACDB", "ADBC", "ADCB", "BACD", "BADC", "BCAD", "BCDA", "BDAC", "BDCA",
                "CABD", "CADB", "CBAD", "CBDA", "CDAB", "CDBA", "DABC", "DACB", "DBAC", "DBCA", "DCAB", "DCBA"]


def _prng_stream(seed, n):
    out = []
    for _ in range(n):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        out.append(seed >> 16)
    return out


def decode_pokemon(raw):
    """Decrypt a 136+ byte (boxed) Pokemon. Returns dict with pid, species, form, level-free fields.
    Block A: species @+0, item @+2, OT id @+4; block B: byte +0x18 = fateful | female<<1 | genderless<<2 | form<<3."""
    pid, flags, checksum = struct.unpack_from("<IHH", raw, 0)
    words = struct.unpack_from("<64H", raw, 8)
    if flags & 0x3:   # pret: partyDecrypted / boxDecrypted flags mean the blocks are already plain
        plain = list(words)
    else:
        key = _prng_stream(checksum, 64)
        plain = [w ^ k for w, k in zip(words, key)]
    data = struct.pack("<64H", *plain)
    order = BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    blocks = {name: data[32 * i:32 * i + 32] for i, name in enumerate(order)}
    ok = (sum(plain) & 0xFFFF) == checksum
    a, b = blocks["A"], blocks["B"]
    species = struct.unpack_from("<H", a, 0)[0]
    fbyte = b[0x18]
    return {"pid": pid, "species": species, "item": struct.unpack_from("<H", a, 2)[0],
            "form": fbyte >> 3, "fateful": fbyte & 1, "checksum_ok": ok, "bad_egg": bool(flags & 4)}


# ----------------------------------------------------------------------------- battery save editing

GENERAL_SIZE = 0xF7CC          # general block incl. 16-byte footer (both mirrors: base 0 and 0x40000)
STORAGE_OFF, STORAGE_SIZE = 0xF800, 0x18408
MIRRORS = (0, 0x40000)
FOOTER_MAGIC = 0x20060623
# Array offsets inside the general block (from the SaveData table at save + 0x2E01C; verified at boot).
ARRAY_OFFSETS = {2: 0x90, 4: 0xEAC, 5: 0x1324, 10: 0x2480}
ARR_BAG = 3                    # bag: pockets of {u16 item, u16 qty} (poke-save-editor research-inventory.md)
ARRAY_OFFSETS[ARR_BAG] = 0x644
POCKETS = {"items": (0x0, 165), "key": (0x294, 50), "tm": (0x35C, 151), "mail": (0x5B8, 12),
           "medicine": (0x5E8, 40), "berries": (0x688, 64), "balls": (0x788, 24), "battle": (0x7E8, 30)}
ARR_MAP_OBJECTS = 10           # saved map objects: 64 x 0x50 bytes (+0x08 u8 id, +0x10 u16 map, +0x12 u16 sprite,
MAP_OBJECT_SIZE, MAP_OBJECT_COUNT = 0x50, 64   # +0x20 s16 initX, initY, initZ, curX, curY, curZ)
PLAYER_OBJ_ID, FOLLOWER_OBJ_ID = 0xFF, 0xFD


class SaveFile:
    """Raw 512 KB battery save. Edits go to the newest general block; its CRC16-CCITT (init 0xFFFF,
    binascii.crc_hqx) is recomputed. Layout: work/notes/emu_harness.md (from poke-save-editor research)."""

    def __init__(self, path):
        self.data = bytearray(Path(path).read_bytes())
        if len(self.data) != 524288:
            raise ValueError("expected a raw 524288-byte save")
        counters = []
        for m in MIRRORS:
            cnt, size, magic, bid, crc = struct.unpack_from("<IIIHH", self.data, m + GENERAL_SIZE - 16)
            ok = magic == FOOTER_MAGIC and size == GENERAL_SIZE and bid == 0 and crc == self._crc(m)
            counters.append((cnt if ok else -1, m))
        cnt, self.base = max(counters)
        if cnt < 0:
            raise ValueError("no valid general block")

    def _crc(self, m):
        import binascii
        return binascii.crc_hqx(bytes(self.data[m:m + GENERAL_SIZE - 16]), 0xFFFF)

    def _a(self, arr, off=0):
        return self.base + ARRAY_OFFSETS[arr] + off

    def set_location(self, map_id, x, y, direction="DOWN", warp=-1, which=0):
        struct.pack_into("<5i", self.data, self._a(ARR_LOCAL_FIELD, 0x14 * which), map_id, warp, x, y,
                         DIRS.get(direction, direction))

    def location(self, which=0):
        return dict(zip(("map", "warp", "x", "y", "dir"),
                        struct.unpack_from("<5i", self.data, self._a(ARR_LOCAL_FIELD, 0x14 * which))))

    def set_flag(self, flag, value=True):
        a = self._a(ARR_VARS_FLAGS, FLAGS_OFFSET + flag // 8)
        self.data[a] = (self.data[a] | (1 << flag % 8)) if value else (self.data[a] & ~(1 << flag % 8))

    def get_flag(self, flag):
        return bool(self.data[self._a(ARR_VARS_FLAGS, FLAGS_OFFSET + flag // 8)] >> (flag % 8) & 1)

    def set_var(self, var, value):
        struct.pack_into("<H", self.data, self._a(ARR_VARS_FLAGS, (var - VARS_BASE) * 2), value)

    def pocket(self, name):
        off, cap = POCKETS[name]
        a = self.base + ARRAY_OFFSETS[ARR_BAG] + off
        return [struct.unpack_from("<HH", self.data, a + 4 * i) for i in range(cap)
                if struct.unpack_from("<H", self.data, a + 4 * i)[0]]

    def set_pocket(self, name, items):
        """Replace a bag pocket with [(item id, quantity), ...] (first entry shows at the top)."""
        off, cap = POCKETS[name]
        if len(items) > cap:
            raise ValueError(f"pocket {name} holds {cap} items")
        a = self.base + ARRAY_OFFSETS[ARR_BAG] + off
        self.data[a:a + 4 * cap] = bytes(4 * cap)
        for i, (item, qty) in enumerate(items):
            struct.pack_into("<HH", self.data, a + 4 * i, item, qty)

    def map_objects(self):
        out = []
        for i in range(MAP_OBJECT_COUNT):
            a = self._a(ARR_MAP_OBJECTS, MAP_OBJECT_SIZE * i)
            flags, = struct.unpack_from("<I", self.data, a)
            if flags:
                obj_id, = struct.unpack_from("<B", self.data, a + 8)
                m, sprite = struct.unpack_from("<HH", self.data, a + 0x10)
                pos = struct.unpack_from("<6h", self.data, a + 0x20)
                out.append({"slot": i, "id": obj_id, "map": m, "sprite": sprite, "x": pos[3], "z": pos[5]})
        return out

    def place_player(self, map_id, x, z, direction="DOWN", height=0):
        """Teleport for Continue: current Location plus the saved player/follower objects; the saved objects
        of the old map (NPCs) are removed, otherwise Continue would restore them on the new map."""
        self.set_location(map_id, x, z, direction)
        for i in range(MAP_OBJECT_COUNT):
            a = self._a(ARR_MAP_OBJECTS, MAP_OBJECT_SIZE * i)
            obj_id = self.data[a + 8]
            if not struct.unpack_from("<I", self.data, a)[0]:
                continue
            if obj_id in (PLAYER_OBJ_ID, FOLLOWER_OBJ_ID):
                oz = z if obj_id == PLAYER_OBJ_ID else z - 1
                struct.pack_into("<6h", self.data, a + 0x20, x, height, oz, x, height, oz)
            else:
                self.data[a:a + MAP_OBJECT_SIZE] = bytes(MAP_OBJECT_SIZE)

    def party(self):
        a = self._a(ARR_PARTY)
        count, = struct.unpack_from("<I", self.data, a + 4)
        return [decode_party_pokemon(bytes(self.data[a + 8 + 236 * i:a + 8 + 236 * (i + 1)]))
                for i in range(min(count, 6))]

    def edit_party_mon(self, slot, **fields):
        """Boxed fields of a party Pokemon (species, item, form, moves, ability; see encode_pokemon), as
        Harness.edit_party_mon does in RAM. With Continue the game builds the lead's follower from it."""
        a = self._a(ARR_PARTY, 8 + 236 * slot)
        self.data[a:a + 136] = encode_pokemon(bytes(self.data[a:a + 136]), **fields)

    def set_party_count(self, n):
        """Keep the first n party Pokemon (1..6); the others stay in the file but the game ignores them."""
        if not 1 <= n <= 6:
            raise ValueError("party count must be 1..6")
        struct.pack_into("<I", self.data, self._a(ARR_PARTY, 4), n)

    def write(self, path):
        struct.pack_into("<H", self.data, self.base + GENERAL_SIZE - 2, self._crc(self.base))
        Path(path).write_bytes(bytes(self.data))
        return path


def decode_party_pokemon(raw):
    """decode_pokemon plus the party extension (100 bytes after the box data, PRNG keyed by the PID)."""
    mon = decode_pokemon(raw)
    if len(raw) >= 236:
        words = struct.unpack_from("<50H", raw, 136)
        ext = struct.pack("<50H", *[w ^ k for w, k in zip(words, _prng_stream(mon["pid"], 50))])
        mon["level"] = ext[4]
    return mon


def encode_pokemon(raw, species=None, item=None, form=None, moves=None, pp=None, ability=None):
    """Return raw (136+ bytes, encrypted) with boxed fields replaced; checksum recomputed. ability: the
    hack's u16 ability at block B +0x1A (abilities go past 255; vanilla's block-A byte +0x0D is not read,
    found 2026-10-06: every party Pokemon holds its summary ability there)."""
    raw = bytearray(raw)
    pid, flags, checksum = struct.unpack_from("<IHH", raw, 0)
    if flags & 0x3:
        raise ValueError("Pokemon is in a decrypted state (mid-edit by the game); try again a frame later")
    key = _prng_stream(checksum, 64)
    plain = bytearray(struct.pack("<64H", *[w ^ k for w, k in zip(struct.unpack_from("<64H", raw, 8), key)]))
    order = BLOCK_ORDERS[((pid & 0x3E000) >> 13) % 24]
    pos = {name: 32 * i for i, name in enumerate(order)}
    if species is not None:
        struct.pack_into("<H", plain, pos["A"], species)
    if item is not None:
        struct.pack_into("<H", plain, pos["A"] + 2, item)
    if ability is not None:
        struct.pack_into("<H", plain, pos["B"] + 0x1A, ability)
    if form is not None:
        b = pos["B"] + 0x18
        plain[b] = (plain[b] & 0x07) | (form << 3)
    if moves is not None:          # block B +0: 4 x u16 move ids, +8: 4 x u8 current PP (verified by the
        for i, mv in enumerate(list(moves)[:4]):   # UI hunt agent in the summary and in battle)
            struct.pack_into("<H", plain, pos["B"] + 2 * i, mv)
            plain[pos["B"] + 8 + i] = pp[i] if pp else 10
    words = struct.unpack("<64H", plain)
    checksum = sum(words) & 0xFFFF
    key = _prng_stream(checksum, 64)
    struct.pack_into("<H", raw, 6, checksum)
    struct.pack_into("<64H", raw, 8, *[w ^ k for w, k in zip(words, key)])
    return bytes(raw)


MAP_HEADERS = 0x020F37C4       # 0x18-byte map headers: +0 wild bank, +4 u16 matrix id, +0x12 events bank
TILE_GRASS = 0x02              # tile behaviour byte of tall grass (land data permissions, low byte)
_ROM_CACHE = {}


class MapGrid:
    """Collision and tile behaviour of a map, read from the ROM (map header -> matrix a/0/4/1 -> land data
    a/0/6/5, 32x32 u16 permissions per chunk after a 0x14-byte header and the header's extra section: low byte
    behaviour, bit 15 blocked).
    Coordinates are the map's tile coordinates, the same as Location / the live player position."""

    def __init__(self, rom_path, map_id):
        import ndspy.narc
        import ndspy.rom
        rom = _ROM_CACHE.get(str(rom_path))
        if rom is None:
            rom = _ROM_CACHE[str(rom_path)] = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
        arm9 = rom.loadArm9().sections[0]
        hdr = arm9.data[MAP_HEADERS - arm9.ramAddress + 0x18 * map_id:][:0x18]
        self.map_id, self.wild_bank = map_id, hdr[0]
        matrix_id = struct.unpack_from("<H", hdr, 4)[0]
        mx = ndspy.narc.NARC(rom.getFileByName("a/0/4/1")).files[matrix_id]
        self.width, self.height, has_headers, has_alt, name_len = mx[0], mx[1], mx[2], mx[3], mx[4]
        p = 5 + name_len + (2 * self.width * self.height if has_headers else 0) + (
            self.width * self.height if has_alt else 0)
        ids = struct.unpack_from("<%dH" % (self.width * self.height), mx, p)
        land = ndspy.narc.NARC(rom.getFileByName("a/0/6/5"))
        self.perms = {}
        for k, lid in enumerate(ids):
            if lid != 0xFFFF:
                # HGSS land data: 0x10-byte size header, u16 0x1234, u16 size of a background-sound section
                # that comes before the permissions (0 for most indoor maps, e.g. 48 bytes on Mt. Silver).
                f = land.files[lid]
                o = 0x14 + struct.unpack_from("<H", f, 0x12)[0]
                self.perms[(k % self.width, k // self.width)] = bytes(f[o:o + 0x800])

    def tile(self, x, y):
        """(behaviour, blocked) or None outside the map."""
        perm = self.perms.get((x // 32, y // 32))
        if perm is None or x < 0 or y < 0:
            return None
        i = 2 * ((y % 32) * 32 + x % 32)
        return perm[i], bool(perm[i + 1] & 0x80)

    def walkable(self, x, y):
        t = self.tile(x, y)
        return t is not None and not t[1]

    def find(self, behaviour, near=None):
        """All walkable tiles with a behaviour, nearest to `near` first."""
        out = [(x, y) for (cx, cy), perm in self.perms.items() for y in range(cy * 32, cy * 32 + 32)
               for x in range(cx * 32, cx * 32 + 32) if self.tile(x, y) == (behaviour, False)]
        if near:
            out.sort(key=lambda t: abs(t[0] - near[0]) + abs(t[1] - near[1]))
        return out

    def path(self, start, goal):
        """Shortest list of directions over walkable tiles (BFS), or None."""
        from collections import deque
        steps = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
        prev = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur == goal:
                out = []
                while prev[cur]:
                    cur, d = prev[cur]
                    out.append(d)
                return out[::-1]
            for d, (dx, dy) in steps.items():
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt not in prev and self.walkable(*nxt):
                    prev[nxt] = (cur, d)
                    q.append(nxt)
        return None


EMULATORS = ("desmume", "melonds")


def default_emulator():
    """The backend a Harness uses when none is given: $EMU_HARNESS_EMULATOR (set by --emulator), else DeSmuME."""
    name = os.environ.get("EMU_HARNESS_EMULATOR", "desmume")
    if name not in EMULATORS:
        raise ValueError(f"EMU_HARNESS_EMULATOR={name!r}; choose one of {', '.join(EMULATORS)}")
    return name


class _MelonMemory:
    """The slice of py-desmume's memory API the Harness uses, over melonds.MelonDS."""

    def __init__(self, m):
        self.m = m

    def __getitem__(self, s):
        if isinstance(s, slice):
            return self.m.read(s.start, s.stop - s.start)
        return self.m.u8(s)

    def read_byte(self, a):
        return self.m.u8(a)

    def read_short(self, a):
        return self.m.u16(a)

    def read_long(self, a):
        return self.m.u32(a)

    def write_byte(self, a, v):
        self.m.w8(a, v)

    def write_short(self, a, v):
        self.m.w16(a, v)

    def write_long(self, a, v):
        self.m.w32(a, v)

    def _no_hooks(self, *a, **k):
        raise NotImplementedError("the melonDS backend has no execution or access callbacks: use "
                                  "Harness.watch()/watch_hits() (buffered data watchpoints) and "
                                  "Harness.cpu_exceptions(); see work/notes/melonds_backend.md")

    register_exec = register_read = register_write = _no_hooks


class _MelonRegs:
    """Live ARM9 registers (py-desmume's register_arm9 shape: .r[i], .pc, .sp, .lr, .cpsr)."""

    def __init__(self, m):
        self.m = m

    @property
    def r(self):
        return self.m.regs()["r"]

    @property
    def pc(self):
        return self.r[15]

    @property
    def sp(self):
        return self.r[13]

    @property
    def lr(self):
        return self.r[14]

    @property
    def cpsr(self):
        return self.m.regs()["cpsr"]


class _MelonInput:
    def __init__(self, m):
        self.m = m

    def keypad_add_key(self, key):
        self.m.hold(key)

    def keypad_rm_key(self, key):
        self.m.release(key)

    def touch_set_pos(self, x, y):
        self.m.touch(x, y)

    def touch_release(self):
        self.m.release_touch()


class _MelonStates:
    def __init__(self, m):
        self.m = m

    def save_file(self, path):
        self.m.save_state_file(path)

    def load_file(self, path):
        self.m.load_state_file(path)


class _MelonEmu:
    """melonds.MelonDS dressed as the part of py-desmume's DeSmuME object the Harness calls (emu.cycle,
    emu.input, emu.memory, emu.savestate, emu.screenshot, emu.reset, emu.destroy). .melon is the full API."""

    def __init__(self, rom, sav=None, rtc=None):
        import melonds
        self.melon = melonds.MelonDS()
        try:
            data = Path(sav).read_bytes() if sav else None
            if data is not None and len(data) != 524288:
                raise RuntimeError(f"expected a raw 524288-byte save: {sav}")
            self.melon.load_rom(rom, sav=data, rtc=rtc or datetime.datetime.now())
        except BaseException:
            self.melon.close()
            raise
        self.memory = _MelonMemory(self.melon)
        self.memory.register_arm9 = _MelonRegs(self.melon)
        self.memory.unsigned = self.memory
        self.input = _MelonInput(self.melon)
        self.savestate = _MelonStates(self.melon)

    def cycle(self, with_joystick=False):
        self.melon.run(1)

    def screenshot(self):
        return self.melon.screenshot()

    def reset(self):
        self.melon.reset()

    def destroy(self):
        self.melon.close()


class Harness:
    """One emulator instance. Use as a context manager."""

    emulator = "desmume"       # instance value set by __init__; the class value serves tests that skip __init__
    melon = None               # melonds.MelonDS on the melonDS backend
    _tmp = None

    def __init__(self, rom=DEF_ROM_CN, sav=None, savestate=None, out=DEF_OUT, verbose=True, rtc=None,
                 emulator=None):
        """rtc: a datetime. DeSmuME's real-time clock otherwise follows the host clock, and the game
        reads it at boot (and later), so two runs of the same inputs diverge with wall time. With rtc
        the emulator records a throw-away movie that starts from the battery file (or a blank
        battery) with its clock fixed at rtc and advanced by emulated frames: runs are repeatable.
        Savestates still work; but emu.reset() during the movie restores the movie's starting
        battery, so in-game saves do not survive a reset: leave rtc unset for save/reset tests.

        emulator: "desmume" (py-desmume, the default) or "melonds" (the melonDS 1.1 shim,
        work/tools/melonds.py); None reads $EMU_HARNESS_EMULATOR. On melonDS the console clock starts
        at rtc (default: now) and advances with emulated time only; with a fixed rtc, runs of the same
        inputs give the same savestates across instances and processes (work/notes/melonds_backend.md,
        Determinism: one exception, R0 after a data abort). There are no execution hooks (on_exec raises), but data watchpoints and the ARM9 exception
        record are available (watch, watch_hits, cpu_exceptions, hang_report)."""
        self.emulator = emulator or default_emulator()
        if self.emulator not in EMULATORS:
            raise ValueError(f"emulator {self.emulator!r}; choose one of {', '.join(EMULATORS)}")
        if self.emulator == "melonds":
            self._init_melonds(rom, sav, savestate, out, verbose, rtc)
            return
        from desmume.emulator import DeSmuME
        from desmume.controls import Keys, keymask
        self._keymask = keymask
        self._keys = {k: getattr(Keys, "KEY_" + k) for k in KEYS}
        self._slot = _EmulatorSlot()       # waits while MAX_EMULATORS emulators run on this machine
        self.rom = Path(rom).resolve()
        self.out = Path(out).resolve()      # the DeSmuME backend chdirs into a temp folder
        self.out.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._tmp = Path(tempfile.mkdtemp(prefix="emu_harness_"))
        os.symlink(self.rom, self._tmp / "game.nds")
        self._cwd = os.getcwd()
        os.chdir(self._tmp)
        # DeSmuME keeps the battery file in $XDG_CONFIG_HOME/desmume/<rom name>.dsv and reads the emulated
        # flash from that file. Without a private config dir every harness process shared
        # ~/.config/desmume/game.dsv, so parallel runs read each other's saves (the 'wrong save, map 500'
        # failures). One private config dir per instance (GLib reads the variable once per process).
        (self._tmp / "config").mkdir()
        os.environ["XDG_CONFIG_HOME"] = str(self._tmp / "config")
        self.emu = DeSmuME()
        self.emu.open(str(self._tmp / "game.nds"))
        if sav:
            if not self.emu.backup.import_file(str(Path(sav).resolve()), 524288):
                raise RuntimeError(f"could not import save {sav}")
            self.emu.reset()
        if rtc is not None:
            from desmume.emulator import DeSmuME_Date, StartFrom
            date = DeSmuME_Date(rtc.year, rtc.month, rtc.day, rtc.hour, rtc.minute, rtc.second, 0)
            self.emu.movie.record(str(self._tmp / "rtc.dsm"), "emu_harness",
                                  StartFrom.START_SRAM if sav else StartFrom.START_BLANK,
                                  str(Path(sav).resolve()) if sav else "", date)
            if not self.emu.movie.is_recording():
                raise RuntimeError("could not start the fixed-clock movie")
        if savestate:
            self.emu.savestate.load_file(str(Path(savestate).resolve()))
        self.mem = self.emu.memory.unsigned
        self.reg = self.emu.memory.register_arm9
        self.frame = 0
        self._per_frame = []
        self._hook_error = None
        self._held = set()

    def _init_melonds(self, rom, sav, savestate, out, verbose, rtc):
        self._keymask = lambda k: k            # _MelonInput takes key names
        self._keys = {k: k for k in KEYS}
        self._slot = _EmulatorSlot()
        self.rom = Path(rom).resolve()
        self.out = Path(out).resolve()      # the DeSmuME backend chdirs into a temp folder
        self.out.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._tmp = None                        # melonDS reads ROM and save from memory: no temp dir, no chdir
        try:
            self.emu = _MelonEmu(self.rom, Path(sav).resolve() if sav else None, rtc)
        except BaseException:
            self._slot.release()
            raise
        self.melon = self.emu.melon
        if savestate:
            self.emu.savestate.load_file(str(Path(savestate).resolve()))
        self.mem = self.emu.memory.unsigned
        self.reg = self.emu.memory.register_arm9
        self.frame = 0
        self._per_frame = []
        self._hook_error = None
        self._held = set()

    # ------------------------------------------------------------------ lifecycle
    def close(self):
        try:
            self.emu.destroy()
        finally:
            if self._tmp is not None:
                os.chdir(self._cwd)
                shutil.rmtree(self._tmp, ignore_errors=True)
            self._slot.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def log(self, *a):
        if self.verbose:
            print(f"[{self.frame:7d}]", *a, flush=True)

    def check_code(self, sigs=CODE_SIG):
        """Compare code bytes in RAM with the hack's code (arm9 after boot; overlay 2 while the field runs)."""
        bad = []
        for addr, hexs in sigs.items():
            want = bytes.fromhex(hexs.replace(" ", ""))
            have = self.read(addr, len(want))
            if have != want:
                bad.append(f"{addr:#x}: {have.hex()} != {want.hex()}")
        if bad:
            raise RuntimeError("code differs from the hack's: " + "; ".join(bad))

    def save_state(self, path):
        self.emu.savestate.save_file(str(Path(path).resolve()))

    def load_state(self, path):
        self.emu.savestate.load_file(str(Path(path).resolve()))

    # ------------------------------------------------------------------ memory
    def read(self, addr, n):
        return bytes(self.mem[addr:addr + n])

    def u8(self, a):
        return self.mem.read_byte(a)

    def u16(self, a):
        return self.mem.read_short(a)

    def u32(self, a):
        return self.mem.read_long(a)

    def s32(self, a):
        v = self.u32(a)
        return v - (1 << 32) if v & 0x80000000 else v

    def write(self, addr, data):
        for i, b in enumerate(bytes(data)):
            self.emu.memory.write_byte(addr + i, b)

    def w8(self, a, v):
        self.emu.memory.write_byte(a, v & 0xFF)

    def w16(self, a, v):
        self.emu.memory.write_short(a, v & 0xFFFF)

    def w32(self, a, v):
        self.emu.memory.write_long(a, v & 0xFFFFFFFF)

    def on_exec(self, addr, fn, exclusive=False, replace=False):
        """Call fn(harness) whenever the ARM9 executes addr (Thumb: even address). fn reads self.reg.

        DeSmuME keeps one callback per address, so a second registration silently replaces
        the first. exclusive=True marks a measurement hook: registering it over an existing
        hook, or any later registration over it, raises unless replace=True. fn=None removes
        the hook."""
        if self.emulator == "melonds":
            self.emu.memory.register_exec(addr, fn)       # raises NotImplementedError with the alternatives
        hooks = self.__dict__.setdefault("_hooks", {})
        if fn is None:
            hooks.pop(addr, None)
        else:
            if addr in hooks and (exclusive or hooks[addr]) and not replace:
                raise ValueError(f"ARM9 execution hook at {addr:#010x} is already registered "
                                 "(DeSmuME would replace it silently)")
            hooks[addr] = exclusive or (hooks.get(addr, False) and replace)
        # ctypes callbacks cannot propagate Python exceptions through the emulator.
        # Keep the first failure and raise it on the Python side of cycle(), so an
        # assertion in instrumentation can never silently produce a passing run.
        def checked(a, size):
            if self._hook_error is not None:
                return
            try:
                fn(self)
            except BaseException as exc:
                self._hook_error = (addr, exc)
        self.emu.memory.register_exec(addr, checked if fn else None)

    def _raise_hook_error(self):
        if self._hook_error is not None:
            addr, exc = self._hook_error
            raise RuntimeError(f"ARM9 execution hook failed at {addr:#010x}") from exc

    def on_frame(self, fn):
        """Call fn(harness) after every emulated frame (e.g. to keep a RAM value forced)."""
        self._per_frame.append(fn)

    # ------------------------------------------------------------------ running and input
    def step(self, n=1):
        self._raise_hook_error()
        for _ in range(n):
            self.emu.cycle(with_joystick=False)
            self._raise_hook_error()
            self.frame += 1
            for fn in self._per_frame:
                fn(self)

    def hold(self, *keys):
        for k in keys:
            self.emu.input.keypad_add_key(self._keymask(self._keys[k]))
            self._held.add(k)

    def release(self, *keys):
        released = self.__dict__.setdefault("_released", {})
        for k in keys or list(self._held):
            self.emu.input.keypad_rm_key(self._keymask(self._keys[k]))
            self._held.discard(k)
            released[k] = self.frame

    def press(self, key, frames=6, after=0):
        """A new press of `key`: the game must see it up, then down. Pressing a key that is
        held cannot create a press edge, so it is an error; a key released in this same frame
        is first left up for one frame."""
        if key in self._held:
            raise ValueError(f"{key} is held; release it before pressing it again")
        if self.__dict__.get("_released", {}).get(key) == self.frame:
            self.step(1)
        self.hold(key)
        self.step(frames)
        self.release(key)
        self.step(after)

    def touch(self, x, y, frames=8, after=0):
        self.emu.input.touch_set_pos(x, y)
        self.step(frames)
        self.emu.input.touch_release()
        self.step(after)

    def run_until(self, cond, max_frames, every=1):
        """Step until cond(self) is true; returns True, or False after max_frames."""
        for i in range(0, max_frames, every):
            if cond(self):
                return True
            self.step(every)
        return bool(cond(self))

    def screenshot(self, name):
        path = self.out / f"{name}.png"
        self.emu.screenshot().save(path)
        self.log("screenshot", path)
        return path

    # ------------------------------------------------------------------ crash and hang detection
    def _need_melonds(self, what):
        if self.emulator != "melonds":
            raise NotImplementedError(f"{what} needs the melonDS backend (--emulator melonds)")

    def cpu_exceptions(self):
        """melonDS: ARM9 data/prefetch aborts and undefined instructions logged by the core since boot."""
        self._need_melonds("cpu_exceptions")
        return self.melon.exceptions()

    def arm9_abort(self):
        """melonDS: None while the ARM9 runs normally; after a data abort (the console's protection unit
        refused an access, e.g. a NULL read) a dict with the faulting instruction's address. The hack's
        abort handler never returns: the ARM9 spins in abort mode, so this stays set (= the freeze)."""
        self._need_melonds("arm9_abort")
        r = self.melon.regs()
        ex = self.melon.exceptions()
        if r["mode"] != 0x17 and not ex["data_aborts"]:
            return None
        lr = r["r"][14] if r["mode"] == 0x17 else r["abt"][1]
        return {"in_abort_mode": r["mode"] == 0x17, "cpsr": r["cpsr"], "abort_lr": lr,
                "fault_pc": (lr - 8) & 0xFFFFFFFF, "r": r["r"], "data_aborts": ex["data_aborts"],
                "first_abort_frame": ex["first_data_abort_frame"], "prefetch_aborts": ex["prefetch_aborts"],
                "undefined": ex["undefined"]}

    def screen_black(self, screen="both", threshold=8):
        """True when every pixel of the top / bottom / both screens is at most `threshold` in each channel."""
        img = self.emu.screenshot().convert("RGB")
        box = {"top": (0, 0, 256, 192), "bottom": (0, 192, 256, 384), "both": (0, 0, 256, 384)}[screen]
        return max(hi for lo, hi in img.crop(box).getextrema()) <= threshold

    def hang_report(self, frames=120, probe_key=None):
        """Run `frames` frames (pressing probe_key in the middle, if given) and describe whether the game
        still lives: screen changes, black screens, the ARM9 abort state (melonDS), the field position.
        hung = ARM9 in abort mode, or a black screen that did not change over the whole window."""
        first = self.emu.screenshot().convert("RGB").tobytes()
        changed = False
        for i in range(frames):
            if probe_key and i == frames // 2:
                self.hold(probe_key)
            if probe_key and i == frames // 2 + 6:
                self.release(probe_key)
            self.step(1)
            if not changed and self.emu.screenshot().convert("RGB").tobytes() != first:
                changed = True
        if probe_key and probe_key in self._held:
            self.release(probe_key)
        rep = {"frame": self.frame, "frames": frames, "screen_changed": changed,
               "black_top": self.screen_black("top"), "black_bottom": self.screen_black("bottom")}
        try:
            rep["position"] = self.position()
        except RuntimeError:
            rep["position"] = None
        if self.emulator == "melonds":
            rep["abort"] = self.arm9_abort()
            rep["exceptions"] = self.cpu_exceptions()
        abort = bool(rep.get("abort") and rep["abort"]["in_abort_mode"])
        rep["hung"] = abort or (not changed and rep["black_top"] and rep["black_bottom"])
        return rep

    def watch(self, start, length, read=False, write=True):
        """melonDS: record ARM9 bus accesses to [start, start+length) (CPU loads/stores that do not hit ITCM/
        DTCM, and ARM9 DMA). Read the hits with watch_hits() after stepping; each has the instruction's pc."""
        self._need_melonds("watch")
        self.melon.watch(start, length, read=read, write=write)

    def watch_hits(self):
        self._need_melonds("watch_hits")
        return self.melon.watch_hits()

    def clear_watches(self):
        self._need_melonds("clear_watches")
        self.melon.clear_watches()

    # ------------------------------------------------------------------ save data in RAM
    @property
    def save(self):
        p = self.u32(SAVE_PTR_GLOBAL)
        if not (0x02000000 <= p < 0x02400000):
            raise RuntimeError("SaveData is not allocated yet (boot further)")
        return p

    def array(self, idx):
        s = self.save
        return s + 0x10 + self.u32(s + SAVE_TABLE + 16 * idx)

    def get_flag(self, flag):
        if not 0 < flag < FLAGS_MAX:
            raise ValueError("only saved flags 1..0x3FFF are supported")
        return bool(self.u8(self.array(ARR_VARS_FLAGS) + FLAGS_OFFSET + flag // 8) >> (flag % 8) & 1)

    def set_flag(self, flag, value=True):
        if not 0 < flag < FLAGS_MAX:
            raise ValueError("only saved flags 1..0x3FFF are supported")
        a = self.array(ARR_VARS_FLAGS) + FLAGS_OFFSET + flag // 8
        b = self.u8(a)
        self.w8(a, (b | (1 << flag % 8)) if value else (b & ~(1 << flag % 8)))

    def get_var(self, var):
        return self.u16(self.array(ARR_VARS_FLAGS) + (var - VARS_BASE) * 2)

    def set_var(self, var, value):
        self.w16(self.array(ARR_VARS_FLAGS) + (var - VARS_BASE) * 2, value)

    def location(self, which=0):
        """LocalFieldData Location (pret): 0 current position, 1 previous (+0x14), 2 dynamic warp (+0x28),
        3 special spawn/escape (+0x3C), 4 +0x50. {s32 map, warp, x, y, direction}."""
        a = self.array(ARR_LOCAL_FIELD) + 0x14 * which
        return dict(zip(("map", "warp", "x", "y", "dir"), struct.unpack("<5i", self.read(a, 20))))

    def set_location(self, map_id, x, y, direction="DOWN", warp=-1, which=0):
        a = self.array(ARR_LOCAL_FIELD) + 0x14 * which
        d = DIRS.get(direction, direction)
        self.write(a, struct.pack("<5i", map_id, warp, x, y, d))

    # ------------------------------------------------------------------ clock
    def set_clock(self, when):
        """Pin the game's clock (GF_RTC cache) to a datetime: rewritten every time the game re-reads the
        RTC (about every 10 frames) and right now. DeSmuME itself keeps running on host time.
        melonDS: its RTC runs on emulated time, so the console clock itself is set to `when` (and the cache
        right now); the game then reads it as usual and the clock advances from `when` (not pinned)."""
        wd = (when.isoweekday()) % 7
        self._clock = (struct.pack("<4I", when.year - 2000, when.month, when.day, wd),
                       struct.pack("<3I", when.hour, when.minute, when.second))
        if self.emulator == "melonds":
            self.melon.set_rtc(when)
            self._apply_clock()
            return
        if not getattr(self, "_clock_hooked", False):
            self.on_exec(RTC_SYNC_DONE, lambda h: h._apply_clock())
            self._clock_hooked = True
        self._apply_clock()

    def _apply_clock(self):
        if getattr(self, "_clock", None):
            self.write(RTC_DATE, self._clock[0])
            self.write(RTC_TIME, self._clock[1])

    def clock(self):
        y, mo, d, wd = struct.unpack("<4I", self.read(RTC_DATE, 16))
        hh, mm, ss = struct.unpack("<3I", self.read(RTC_TIME, 12))
        return {"date": f"{2000 + y:04d}-{mo:02d}-{d:02d}", "weekday": wd, "time": f"{hh:02d}:{mm:02d}:{ss:02d}"}

    # ------------------------------------------------------------------ boot
    def boot_to_menu(self):
        """Power on -> title -> START -> Continue menu (save data is loaded into RAM at this point)."""
        self.step(2400)
        self.press("START", after=400)
        self.step(300)
        _ = self.save   # raises if the save was not loaded
        self.check_code(CODE_SIG)
        for arr, off in ARRAY_OFFSETS.items():
            have = self.u32(self.save + SAVE_TABLE + 16 * arr)
            if have != off:
                raise RuntimeError(f"save array {arr} is at {have:#x}, expected {off:#x}: update ARRAY_OFFSETS")
        self.log("at the Continue menu; current location", self.location())

    def continue_game(self, settle=900):
        """Pick Continue and wait for the field. Continue reloads the save from flash, so RAM edits made at
        the menu are lost: edit the battery save (SaveFile) before booting, or edit RAM once in the field."""
        self.press("A", after=200)
        self.press("A", after=settle)
        if not self.run_until(lambda h: h.in_field(), 1200, every=20):   # slow under parallel load
            self.check_code(OV2_SIG)        # raises with the differing bytes

    # ------------------------------------------------------------------ field helpers
    def in_field(self):
        """True while overlay 2 (field) is resident; battles replace it."""
        for addr, hexs in OV2_SIG.items():
            want = bytes.fromhex(hexs)
            if self.read(addr, len(want)) != want:
                return False
        return True

    def flee(self, max_tries=20, battle_menu_wait=320):
        """From the start of a wild battle: wait for the command menu, touch RUN until the field is back.
        After each touch it polls for the field for up to 240 frames, so it never touches the field menu."""
        self.step(battle_menu_wait)
        for _ in range(max_tries):
            if self.in_field():
                self.step(120)
                return True
            self.touch(*RUN_BUTTON, after=10)
            if self.run_until(lambda h: h.in_field(), 240, every=10):
                self.step(120)
                return True
            self.press("B", after=40)     # dismiss "can't escape!" text
        self.screenshot("flee_failed")
        return False

    def pixel(self, x, y):
        """RGB at (x, y) of the 256x384 screenshot (bottom screen starts at y 192)."""
        return self.emu.screenshot().convert("RGB").getpixel((x, y))

    def on_screen(self, name, tolerance=24):
        """True when every sample pixel of a known screen (SCREENS_KNOWN) matches."""
        img = self.emu.screenshot().convert("RGB")
        return all(max(abs(a - b) for a, b in zip(img.getpixel(xy), rgb)) <= tolerance
                   for xy, rgb in SCREENS_KNOWN[name])

    def wait_screen(self, name, max_frames=1200, every=10):
        return self.run_until(lambda h: h.on_screen(name), max_frames, every)

    def battle_turn(self, move_slot, max_frames=3000, shots=None):
        """At the battle command menu: FIGHT -> move_slot, then step through the turn's messages with B
        (B never selects anything) until the menu is back ('menu') or the battle is over ('field')."""
        if not self.wait_screen("battle_menu", 1500):
            raise RuntimeError("battle command menu not found")
        self.touch(*BATTLE_BUTTONS["fight"], frames=10, after=40)
        self.touch(*MOVE_BUTTONS[move_slot], frames=10, after=60)
        last = None
        for i in range(0, max_frames, 15):
            self.step(15)
            if self.in_field():
                self.step(60)
                return "field"
            if self.on_screen("battle_menu"):
                return "menu"
            if shots is not None:          # keep a screenshot whenever the top-screen text box changes
                box = self.emu.screenshot().crop((8, 146, 248, 186)).tobytes()
                if box != last:
                    last = box
                    shots.append(self.screenshot(f"turn_{self.frame}"))
            if i % 60 == 45:
                self.press("B", after=0)
        self.screenshot("turn_stuck")
        raise RuntimeError("turn did not finish")

    def fight(self, plan, max_turns=40):
        """Fight until the battle ends: plan = move slots for the first turns, the last one repeats."""
        for t in range(max_turns):
            if self.battle_turn(plan[min(t, len(plan) - 1)]) == "field":
                return t + 1
        raise RuntimeError("battle did not end")

    def position(self):
        """Live player position: (map, x, y). LocalFieldData's current Location is updated on every step
        (found by diffing RAM while walking: x 17 -> 15 -> 12 at save array 5 + 8)."""
        loc = self.location()
        return loc["map"], loc["x"], loc["y"]

    def grid(self):
        m = self.position()[0]
        if getattr(self, "_grid", None) is None or self._grid.map_id != m:
            self._grid = MapGrid(self.rom, m)
        return self._grid

    def step_dir(self, direction, max_frames=40):
        """Move one tile; returns True when the position changed (a first press may only turn)."""
        start = self.position()
        self.hold(direction)
        for _ in range(max_frames):
            self.step(1)
            if self.position() != start:
                break
        self.release(direction)
        self.step(8)
        return self.position() != start

    def walk_to(self, x, y, on_step=None):
        """Walk to (x, y) along a BFS path over the map's collision data. on_step(h) after each tile may
        return True to stop (e.g. a battle started). Returns True on arrival."""
        for _ in range(3):
            m, cx, cy = self.position()
            route = self.grid().path((cx, cy), (x, y))
            if route is None:
                raise RuntimeError(f"no path from {(cx, cy)} to {(x, y)} on map {m}")
            for d in route:
                if not self.step_dir(d) and not self.step_dir(d):
                    break
                if on_step and on_step(self):
                    return False
            if self.position()[1:] == (x, y):
                return True
        return self.position()[1:] == (x, y)

    def walk(self, direction, tiles=1, frames_per_tile=16):
        self.hold(direction)
        self.step(frames_per_tile * tiles)
        self.release(direction)
        self.step(2)

    # ------------------------------------------------------------------ party
    def party(self):
        a = self.array(ARR_PARTY)
        count = self.u32(a + 4)
        return [decode_party_pokemon(self.read(a + 8 + 236 * i, 236)) for i in range(min(count, 6))]

    def generate_pokemon(self, species, level=5, item=0, form=0, free_slot=True):
        """Create a Pokemon with the hack's own debug generator (field: hold SELECT, press X; see the FAQ).
        The menu keeps one u32 per row in a heap array (GEN_* indexes); we write species/item/form there, set
        the level through the menu (A, UP, A on the level row) so it recomputes the experience, then START.
        With free_slot the party count is lowered to 5 first so the new Pokemon lands in slot 6 instead of
        the PC (test-only edit; the old slot-6 Pokemon is overwritten). Returns the decoded new Pokemon."""
        party = self.array(ARR_PARTY)
        if free_slot and self.u32(party + 4) == 6:
            self.w32(party + 4, 5)
        self.hold("SELECT")
        self.step(10)
        self.press("X", after=10)
        self.release("SELECT")
        self.step(120)
        base = self._find_generator()
        self.w32(base + 4 * GEN_SPECIES, species)
        self.w32(base + 4 * GEN_ITEM, item)
        self.w32(base + 4 * GEN_FORM, form)
        self.w32(base + 4 * GEN_LEVEL, max(1, level - 1))
        self.press("DOWN", after=20)              # cursor to the level row
        self.press("A", after=20)                 # edit
        self.press("UP", after=20)                # level + 1: the menu recomputes experience
        self.press("A", after=20)
        if self.u32(base + 4 * GEN_LEVEL) != level:
            raise RuntimeError("generator did not take the level")
        count = self.u32(party + 4)
        self.press("START", after=120)
        self.press("A", after=60)                 # dismiss "added to party/box"
        self.press("B", after=60)                 # close the menu
        if self.u32(party + 4) != count + 1:
            raise RuntimeError("generator did not add the Pokemon to the party (party full?)")
        self.generated_slot = count
        mon = decode_party_pokemon(self.read(party + 8 + 236 * count, 236))
        mon["slot"] = count
        return mon

    # ------------------------------------------------------------------ menus (timing-based; see notes)
    def bag_put_first(self, item, qty=1, pocket="items"):
        """Live RAM edit: make item the first entry of a bag pocket (the rest of the pocket is cleared)."""
        off, cap = POCKETS[pocket]
        a = self.array(ARR_BAG) + off
        self.write(a, struct.pack("<HH", item, qty) + bytes(4 * (cap - 1)))

    def open_bag(self):
        """From the field (touch menu visible): open the bag on its last pocket (the Items pocket after boot)."""
        self.touch(*FIELD_MENU["bag"], frames=12, after=120)

    def give_from_bag(self, bag_slot, party_slot):
        """In the bag: item at bag_slot -> Give -> party_slot, then dismiss the message. The party slot must
        hold no item (a swap asks two more questions). Uses the game's own give path (form routines run)."""
        self.touch(*BAG_SLOTS[bag_slot], frames=12, after=60)
        self.touch(*BAG_GIVE, frames=12, after=60)
        self.touch(*PARTY_SLOTS[party_slot], frames=12, after=120)
        self.press("A", after=100)

    def field_menu(self, entry):
        """Open the X menu and pick an entry. Cursor starts on POKeDEX; left column POKeDEX, POKeMON, BAG,
        POKeGEAR; right column trainer card, SAVE, OPTIONS (memcheck_scenarios.json)."""
        col, row = {"pokedex": (0, 0), "pokemon": (0, 1), "bag": (0, 2), "pokegear": (0, 3),
                    "card": (1, 0), "save": (1, 1), "options": (1, 2)}[entry]
        self.press("X", after=90)
        for _ in range(col):
            self.press("RIGHT", after=30)
        for _ in range(row):
            self.press("DOWN", after=30)
        self.press("A", after=300)

    def swap_party(self, i, j):
        """Swap two party slots in RAM (field only), e.g. to make a generated Pokemon the lead."""
        a = self.array(ARR_PARTY) + 8
        x, y = self.read(a + 236 * i, 236), self.read(a + 236 * j, 236)
        self.write(a + 236 * i, y)
        self.write(a + 236 * j, x)

    def walk_until_battle(self, max_steps=600):
        """Pace LEFT/RIGHT until a wild Pokemon is built; returns the WildLog (battle intro still running)."""
        log = WildLog(self)
        steps = 0
        while not log.rows and steps < max_steps:
            for d in ("LEFT", "RIGHT"):
                for _ in range(3):
                    self.walk(d, 1)
                    steps += 1
        if not log.rows:
            raise RuntimeError("no wild battle")
        return log

    def mark(self, name):
        """Screen-check point: screenshot as <name>_<tag>.png and remember it (see cmd_screens)."""
        self.marks = getattr(self, "marks", [])
        self.marks.append(name)
        return self.screenshot(f"{name}_{getattr(self, 'tag', 'x')}")

    def run_script(self, script_id=None, file=None, index=None, msg_bank=None, program=None, settle=30):
        """Start an event script from the field without walking anywhere: the next A press is redirected.
        - script_id: any global id (map scripts 1.., std 2000.., ...), run in the current map's context;
        - file/index/msg_bank: script <index> (scriptdump number - 1) of script file <file> (a/0/1/2), bank <msg_bank>;
        - program: raw bytes (script_bytes(...)) run instead of the loaded script.
        The player must stand still in the field (no menu, no message)."""
        if file is not None:
            script_id = STD_SCRIPT_BASE + index
        if program is not None and script_id is None:
            script_id = STD_SCRIPT_BASE
        state = {"id": True, "file": file is not None, "program": program is not None}

        def talk_obj(h):
            if state["id"] and h.read(TALK_OBJ_START, 4) == bytes.fromhex(OV1_SIG[TALK_OBJ_START]):
                h.reg.r1, state["id"] = script_id, False

        def talk_bg(h):
            if state["id"] and h.read(TALK_BG_RESULT, 2) == bytes.fromhex(OV1_SIG[TALK_BG_RESULT]):
                h.reg.r0, state["id"] = script_id, False

        def load(h):
            if state["file"] and not state["id"]:
                h.reg.r2, h.reg.r3, state["file"] = file, msg_bank, False

        def started(h):
            if state["program"] and not state["id"] and not state["file"]:
                h.write(h.u32(h.reg.r4 + 8), program)
                state["program"] = False
        self.on_exec(TALK_OBJ_START, talk_obj)
        self.on_exec(TALK_BG_RESULT, talk_bg)
        self.on_exec(SCRIPT_LOAD_FILE, load)
        self.on_exec(SCRIPT_STARTED, started)
        self.press("A", after=settle)
        ok = not state["id"]
        for addr in (TALK_OBJ_START, TALK_BG_RESULT, SCRIPT_LOAD_FILE, SCRIPT_STARTED):
            self.on_exec(addr, None)
        if not ok:
            raise RuntimeError("A press did not reach the field talk handler (menu or message open?)")
        return script_id

    def show_message(self, bank, msg_id, name=None, max_pages=8, settle=150):
        """Print message <msg_id> of a027 bank <bank> in the field's normal message window with a one-off
        script (MsgBoxExtern via var 0x8000; unsigned 16-bit id), screenshot every page (A between pages), close it.
        The text and its control codes (sizes, colours, buffers) render as in a scene; the scene's own
        context (camera, speaker objects, a special window) is not reproduced."""
        prog = message_script(bank, msg_id)
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("max_pages must be a positive integer")
        saved = self.get_var(SENTINEL_VAR)
        try:
            self.set_var(SENTINEL_VAR, 0)
            self.run_script(file=3, index=0, msg_bank=bank, program=prog, settle=settle)
            shots = []
            for page in range(max_pages):
                if self.get_var(SENTINEL_VAR) == 0x5A5A:  # the script has closed the window
                    return shots
                shots.append(self.screenshot(f"{name or f'msg_{bank:04d}_{msg_id}'}_p{page + 1}"))
                self.press("A", after=settle)
            # The last allowed press may have completed the script.
            if self.get_var(SENTINEL_VAR) != 0x5A5A:
                raise RuntimeError(f"message {bank}#{msg_id} did not complete within {max_pages} pages")
            return shots
        finally:
            self.set_var(SENTINEL_VAR, saved)

    def trainer_battle(self, trainer_id):
        """Start a battle against trainer_id (a/0/5/5) with the game's TrainerBattle command."""
        return self.run_script(program=script_bytes(("LockAll",), ("TrainerBattle", trainer_id, 0, 0, 0),
                                                    ("ReleaseAll",), ("End",)))

    def warp(self, map_id, x, y, direction=0):
        """Warp with the game's own Warp command (a normal map entry: map scripts and objects load)."""
        return self.run_script(program=script_bytes(*WARP_CMDS(map_id, x, y, direction)), settle=300)

    def bag_pocket(self, pocket):
        """In the bag: switch to a pocket by its tab."""
        self.touch(*POCKET_TABS[pocket], frames=12, after=60)

    def use_from_bag(self, bag_slot, party_slot, evolves=None, level_up=False):
        """In the bag: item at bag_slot -> Use -> party_slot, then step through the messages and, if the
        Pokemon evolves, the evolution scene. Fixed timings (checked for Rare Candy and evolution stones);
        ends back in the bag list. Returns the party Pokemon afterwards."""
        self.touch(*BAG_SLOTS[bag_slot], frames=12, after=60)
        self.touch(*BAG_USE, frames=12, after=60)
        self.touch(*PARTY_SLOTS[party_slot], frames=12, after=120)
        if level_up:                 # "grew to Lv N" -> stat gains -> new stats
            for _ in range(3):
                self.press("A", after=90)
        self.step(800)               # evolution scene (or nothing)
        self.press("A", after=300)   # "evolved into ..." -> back to the bag
        return self.party()[party_slot]

    def level_up_with_candy(self, party_slot, candy_slot=0):
        """From the field: open the bag, Medicine pocket, use the Rare Candy at candy_slot on party_slot.
        The Medicine pocket must hold the candy (SaveFile.set_pocket / bag_put_first)."""
        self.open_bag()
        self.bag_pocket("medicine")
        return self.use_from_bag(candy_slot, party_slot, level_up=True)

    def open_summary_from_bag(self, party_slot):
        """Leave the bag, open the party from the field menu (cursor is on Bag, UP = Pokemon), open the
        summary of party_slot. Ends on the summary's first page."""
        self.press("B", after=180)
        self.press("UP", after=40)
        self.press("A", after=120)
        self.touch(*PARTY_SLOTS[party_slot], frames=12, after=60)
        self.touch(*PARTY_SUMMARY, frames=12, after=150)

    def _find_generator(self):
        """The generator's row array starts as Bulbasaur: species 1, level 1, exp 0, ..., Tackle, Growl."""
        ram = self.read(0x02200000, 0x200000)
        pat = struct.pack("<3I", 1, 1, 0)
        i = ram.find(pat)
        while i >= 0:
            if struct.unpack_from("<2I", ram, i + 4 * GEN_MOVE1) == (33, 45):
                return 0x02200000 + i
            i = ram.find(pat, i + 4)
        raise RuntimeError("generator menu not found (is the player in the field?)")

    def edit_party_mon(self, slot, **fields):
        """Change boxed fields of a party Pokemon in RAM (species, item, form); re-encrypts and fixes the
        checksum. Stats in the party extension are left alone (the game recalculates them on level-up)."""
        a = self.array(ARR_PARTY) + 8 + 236 * slot
        self.write(a, encode_pokemon(self.read(a, 136), **fields))


# ----------------------------------------------------------------------------- wild encounter logger

class WildLog:
    """Hooks the overlay-2 wild finalizer and records each wild Pokemon it builds:
    species, the letter the game picked (UnownLetter result, for Unown), the form it saved before, and the
    form stored in the finished Pokemon (decrypted from RAM at the end of the finalizer)."""

    def __init__(self, h, on_mon=None):
        """on_mon(h, mon_address) runs when a wild Pokemon is finished (e.g. to give it a held item)."""
        self.h = h
        self.rows = []
        self.on_mon = on_mon
        self._cur = None
        h.on_exec(WILD_FINALIZE, self._enter)
        h.on_exec(WILD_FINALIZE_SETFORM, self._setform)
        h.on_exec(WILD_FINALIZE_AFTER_SET, self._after_set)
        h.on_exec(WILD_FINALIZE_RESTORE, self._restore)
        h.on_exec(WILD_FINALIZE_END, self._end)

    def _enter(self, h):
        self._cur = {"frame": h.frame, "mon": h.reg.r2, "letter_set": None, "form_after_letter": None,
                     "saved_form": None}

    def _setform(self, h):
        if self._cur is not None:   # r2 = &letter on the stack
            self._cur["letter_set"] = h.u8(h.reg.r2)

    def _after_set(self, h):
        if self._cur is not None:   # form stored in the Pokemon right after the letter was written
            self._cur["form_after_letter"] = decode_pokemon(h.read(self._cur["mon"], 136))["form"]

    def _restore(self, h):
        if self._cur is not None:   # sp+8 = form read before the letter was set
            self._cur["saved_form"] = h.u32(h.reg.sp + 8)

    def _end(self, h):
        c, self._cur = self._cur, None
        if c is None:
            return
        if self.on_mon:
            self.on_mon(h, c["mon"])
        mon = decode_pokemon(h.read(c["mon"], 136))
        c.update(species=mon["species"], form=mon["form"], item=mon["item"], pid=mon["pid"], checksum_ok=mon["checksum_ok"])
        c["mon"] = hex(c["mon"])
        self.rows.append(c)
        h.log("wild:", c)


# ----------------------------------------------------------------------------- Unown POC

class start_at:
    """Context manager: copy the save, teleport (map, x, y), set flags/vars, pin the clock, boot, Continue.
    Yields a Harness standing on the map. Example:
        with start_at(109, 16, 14, clock=datetime.datetime(2026, 10, 9, 12)) as h: ..."""

    def __init__(self, map_id=None, x=None, y=None, rom=DEF_ROM_CN, sav=None, flags=(), vars=None,
                 clock=None, out=DEF_OUT, verbose=True, hooks=None, edit=None, height=0, emulator=None,
                 direction="DOWN"):
        """map_id None: stay where the save is. edit: fn(SaveFile) for further save edits (bag, party, ...).
        emulator: "desmume" / "melonds" / None ($EMU_HARNESS_EMULATOR). On melonDS the clock is the console's
        RTC set before boot (repeatable), and hooks may not use on_exec."""
        self.args = (map_id, x, y, rom, sav or DEF_SAVES / "full_bag_6mons.sav", flags, vars or {}, clock,
                     out, verbose, hooks, edit)
        self.height = height
        self.emulator = emulator
        self.direction = direction

    def __enter__(self):
        map_id, x, y, rom, sav, flags, vars_, clock, out, verbose, hooks, edit = self.args
        sf = SaveFile(sav)
        if map_id is not None:
            sf.place_player(map_id, x, y, self.direction, height=self.height)
        if edit:
            edit(sf)
        for f in flags:
            sf.set_flag(f)
        for v, val in vars_.items():
            sf.set_var(v, val)
        self._dir = Path(tempfile.mkdtemp(prefix="emu_harness_sav_"))
        sf.write(self._dir / "edited.sav")
        self.h = Harness(rom, self._dir / "edited.sav", out=out, verbose=verbose, emulator=self.emulator,
                         rtc=clock if (self.emulator or default_emulator()) == "melonds" else None)
        try:
            if clock and self.h.emulator != "melonds":     # melonDS: the console RTC was set to clock before boot
                self.h.set_clock(clock)
            if hooks:
                hooks(self.h)          # installed before boot: sees calls made while the map loads
            self.h.boot_to_menu()
            self.h.continue_game()
            self.h.press("B", after=30)
            if map_id is not None and self.h.location()["map"] != map_id:
                raise RuntimeError(f"teleport failed: {self.h.location()}")
        except BaseException:
            self.__exit__()
            raise
        return self.h

    def __exit__(self, *exc):
        try:
            self.h.close()
        finally:
            shutil.rmtree(self._dir, ignore_errors=True)


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
        if i % 4 == 0 and decode_pokemon(ram[i:i + 136])["checksum_ok"]:
            out.append(lo + i)
        i = ram.find(key, i + 1)
    return out


def wild_battle(h, species, level, item=None, moves=None, pp=None, form=None):
    """Start a scripted WildBattle and, right after the wild finalizer, give the wild Pokemon an item / moves /
    form in every RAM copy (the battle copies the BattleSetup party ~130 frames later, so the edit holds).
    Returns {pid, copies edited, finalizer row}. (Moved from emu_open.py on 2026-10-09; emu_fixes uses it.)"""
    log = WildLog(h)
    h.run_script(program=script_bytes(("LockAll",), ("WildBattle", species, level, 0), ("ReleaseAll",),
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
            h.write(a, encode_pokemon(h.read(a, 136), **fields))
    for addr in (WILD_FINALIZE, WILD_FINALIZE_SETFORM, WILD_FINALIZE_AFTER_SET, WILD_FINALIZE_RESTORE,
                 WILD_FINALIZE_END):
        h.on_exec(addr, None)
    return {"pid": row["pid"], "copies": [hex(a) for a in cps], "finalizer": {k: row[k] for k in
            ("species", "form", "item")}}


def cmd_wild(a):
    """Teleport through the battery save, walk back and forth until --count wild Pokemon were built, log
    each one (species, form; for Unown the letter the game picked), flee every battle. 'unown' is this
    command with the Ruins of Alph defaults (D-1487)."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    flags = [int(f) for f in a.flags.split(",") if f]
    sf = SaveFile(a.sav)
    before = sf.location()
    sf.place_player(a.map, a.x, a.y, "DOWN")
    for f in flags:
        sf.set_flag(f)
    tmp_sav = Path(tempfile.mkdtemp(prefix="emu_harness_sav_")) / "edited.sav"
    sf.write(tmp_sav)
    t0 = time.time()
    back, forth = a.walk.split(",")
    report = {"rom": str(a.rom), "save": str(a.sav), "map": a.map, "start": [a.x, a.y], "flags": flags,
              "location_before": before, "encounters": []}
    try:
        with Harness(a.rom, tmp_sav, out=out) as h:
            if a.clock:
                h.set_clock(datetime.datetime.fromisoformat(a.clock))
            h.boot_to_menu()
            h.continue_game()
            h.press("B", after=30)
            report["clock"] = h.clock()
            report["location_after_continue"] = h.location()
            if h.location()["map"] != a.map:
                raise RuntimeError(f"teleport failed: {h.location()}")
            h.screenshot(f"{a.tag}_field")
            if a.state:
                h.save_state(a.state)     # reuse: Harness(rom, savestate=...) skips boot and teleport
            log = WildLog(h)
            steps = shots = battles = 0
            while len(log.rows) < a.count and steps < a.max_steps:
                n = len(log.rows)
                for d in (back, forth):
                    for _ in range(a.span):
                        h.walk(d, 1)
                        steps += 1
                        if len(log.rows) > n:
                            break
                    if len(log.rows) > n:
                        break
                if len(log.rows) > n:
                    battles += 1
                    h.step(300)     # both Pokemon of a double battle are built within a few frames
                    for r in log.rows[n:]:
                        r["battle"] = battles
                    row = log.rows[-1]
                    if shots < a.shots or row.get("letter_set") not in (None, 0):
                        row["screenshot"] = str(h.screenshot(f"{a.tag}_encounter_{len(log.rows):02d}"))
                        shots += 1
                    row["fled"] = h.flee(battle_menu_wait=20)
                    if not row["fled"]:
                        h.screenshot(f"{a.tag}_stuck")
                        raise RuntimeError("could not flee")
            report["encounters"] = log.rows
            report["steps"] = steps
            report["clock_end"] = h.clock()
    finally:
        shutil.rmtree(tmp_sav.parent, ignore_errors=True)
    rows = report["encounters"]
    report["seconds"] = round(time.time() - t0, 1)
    species = {}
    for r in rows:
        key = f"{r['species']}/{r['form']}"
        species[key] = species.get(key, 0) + 1
    report["summary"] = {"encounters": len(rows), "battles": len({r["battle"] for r in rows}),
                         "species_form_counts": species}
    unown = [r for r in rows if r["species"] == UNOWN]
    if unown:
        report["summary"]["unown"] = {
            "count": len(unown),
            "letter_picked": "".join(UNOWN_LETTERS[r["letter_set"]] if r["letter_set"] is not None and r["letter_set"] < 28 else "-" for r in unown),
            "final_form": "".join(UNOWN_LETTERS[r["form"]] if r["form"] < 28 else "?" for r in unown),
            "all_final_A": all(r["form"] == 0 for r in unown),
            "decoder_check": all(r["form_after_letter"] == r["letter_set"] for r in unown),
        }
    js = Path(a.json) if a.json else out / f"{a.tag}_report.json"
    js.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(report["summary"], indent=1))
    print("report:", js)
    return 0


# ----------------------------------------------------------------------------- child processes
# Every harness command that fans out runs `emu_harness.py <cmd>` children (one emulator per process). They are
# tracked so that none outlives its parent: a per-child wall-clock timeout (SIGTERM, then SIGKILL, the case
# fails with 'timeout'), all live children are stopped when the parent exits or gets SIGINT/SIGTERM/SIGHUP, and
# a child whose parent has died stops itself (watchdog thread; covers a parent killed with SIGKILL). Live
# emulators are capped machine-wide by slot lock files (EMU_HARNESS_MAX_EMULATORS, default 6), so a big
# fan-out queues instead of opening 20 emulators. `emu_harness.py cleanup [--kill]` lists leftovers.
CHILD_ENV = "EMU_HARNESS_PARENT_PID"
MAX_EMULATORS = int(os.environ.get("EMU_HARNESS_MAX_EMULATORS", "6"))
SLOT_DIR = Path(tempfile.gettempdir()) / "emu_harness_slots"
_CHILDREN = set()
_CHILD_HOOKS = []


class ChildTimeout(RuntimeError):
    """A child ran past its wall-clock timeout and was stopped (the case is reported as 'timeout')."""


def _signal_proc(proc, sig):
    """Send sig to the child, and to its whole process group when it leads one (a top-level child: its own
    children, emulator or not, share the group, so nothing of the tree survives)."""
    try:
        if getattr(proc, "own_group", False):
            os.killpg(proc.pid, sig)
        else:
            proc.send_signal(sig)
    except (ProcessLookupError, PermissionError):
        pass


def _stop_proc(proc, grace=10):
    """SIGTERM a child (its own handlers stop its children), SIGKILL (the group) after <grace> s."""
    import signal
    if proc.poll() is not None:
        if getattr(proc, "own_group", False):       # the child is gone; make sure its group is too
            _signal_proc(proc, signal.SIGKILL)
        return
    try:
        _signal_proc(proc, signal.SIGTERM)
        proc.wait(grace)
    except Exception:
        pass
    if getattr(proc, "own_group", False) or proc.poll() is None:
        _signal_proc(proc, signal.SIGKILL)
    try:
        proc.wait(5)
    except Exception:
        pass


def stop_children():
    for proc in list(_CHILDREN):
        _stop_proc(proc, grace=5)
        _CHILDREN.discard(proc)


def _install_child_handlers():
    """Once per process: stop every tracked child at exit and on SIGINT/SIGTERM/SIGHUP."""
    if _CHILD_HOOKS:
        return
    import atexit
    import signal
    import threading
    _CHILD_HOOKS.append(True)
    atexit.register(stop_children)
    if threading.current_thread() is not threading.main_thread():
        return

    def handler(signum, frame):
        stop_children()
        raise SystemExit(128 + signum)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


def spawn(args, timeout=900):
    """Run 'emu_harness.py <args>' as a tracked child; returns (returncode, stdout, stderr). On timeout the
    child (and its process group) is stopped and ChildTimeout('timeout ...') is raised."""
    import subprocess
    _install_child_handlers()
    env = dict(os.environ, **{CHILD_ENV: str(os.getpid())})
    # a top-level parent puts each child in a new process group (session); nested children stay in their
    # parent's group, so stopping a top-level child's group stops its whole tree
    own_group = CHILD_ENV not in os.environ
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve())] + [str(x) for x in args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                            start_new_session=own_group)
    proc.own_group = own_group
    _CHILDREN.add(proc)
    # the clock starts when the child gets an emulator slot (SLOT_DIR/active_<pid>), so queueing behind the
    # MAX_EMULATORS cap does not count; a child that never opens an emulator (a fan-out parent) gets 4 x timeout
    t0, started, hard = time.time(), None, time.time() + 4 * timeout
    try:
        while True:
            try:
                out, err = proc.communicate(timeout=5)
                break
            except subprocess.TimeoutExpired:
                now = time.time()
                if started is None and (SLOT_DIR / f"active_{proc.pid}").exists():
                    started = now
                if (started is not None and now - started > timeout) or now > hard:
                    _stop_proc(proc)
                    out, err = proc.communicate()
                    raise ChildTimeout(f"timeout after {round(now - (started or t0))} s: child {args[:4]} stopped; "
                                       f"{err[-500:]}") from None
    finally:
        if proc.poll() is None:         # interrupted while waiting (KeyboardInterrupt, SystemExit)
            _stop_proc(proc, grace=5)
        _CHILDREN.discard(proc)
        if own_group:                   # nothing of the child's tree outlives it (a stray grandchild)
            import signal
            _signal_proc(proc, signal.SIGKILL)
        (SLOT_DIR / f"active_{proc.pid}").unlink(missing_ok=True)     # left behind by a killed child
    return proc.returncode, out, err


def child_error(e):
    """The result row of a fan-out case whose child failed: verdict 'timeout' for ChildTimeout, else 'error'."""
    return {"verdict": "timeout" if isinstance(e, ChildTimeout) else "error", "error": str(e)[-1500:]}


def timed_out(r):
    """True when a case result (or one of its variants) is a child that hit its timeout."""
    return r.get("verdict") == "timeout" or any(isinstance(x, dict) and x.get("verdict") == "timeout"
                                                for x in r.values())


def _parent_watchdog():
    """In a child: exit when the parent that started it is gone (re-parented), so an orphan never keeps an
    emulator running."""
    ppid = os.environ.get(CHILD_ENV)
    if not ppid:
        return
    import threading

    def watch():
        while True:
            time.sleep(5)
            if os.getppid() != int(ppid):
                stop_children()
                os._exit(3)
    threading.Thread(target=watch, daemon=True).start()


def _log_slot_wait(event):
    """Append 'wait <time>' / 'got <time>' to $EMU_HARNESS_WAIT_LOG (if set), so a supervising
    runner can exclude time spent waiting for an emulator slot from its timeout."""
    path = os.environ.get("EMU_HARNESS_WAIT_LOG")
    if path:
        with open(path, "a") as fh:
            fh.write(f"{event} {os.getpid()} {time.time():.3f}\n")


def slot_wait_seconds(path, now=None):
    """Seconds processes logging to `path` spent waiting for a slot (open waits count up to now)."""
    now = time.time() if now is None else now
    total, open_waits = 0.0, {}
    try:
        lines = Path(path).read_text().splitlines()
    except FileNotFoundError:
        return 0.0
    for line in lines:
        parts = line.split()
        if len(parts) != 3:
            continue
        event, pid, stamp = parts[0], parts[1], float(parts[2])
        if event == "wait":
            open_waits[pid] = stamp
        elif event == "got" and pid in open_waits:
            total += stamp - open_waits.pop(pid)
    return total + sum(now - t for t in open_waits.values())


class _EmulatorSlot:
    """A machine-wide cap on live emulators: one of MAX_EMULATORS lock files, held while the Harness lives."""

    def __init__(self):
        import fcntl
        SLOT_DIR.mkdir(exist_ok=True)
        self.fh = None
        _log_slot_wait("wait")
        try:
            self._acquire(fcntl)
        finally:
            _log_slot_wait("got")

    def _acquire(self, fcntl):
        while self.fh is None:
            for k in range(MAX_EMULATORS):
                fh = open(SLOT_DIR / f"slot{k}.lock", "w")
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    fh.close()
                    continue
                fh.write(str(os.getpid()))
                fh.flush()
                self.fh = fh
                self.active = SLOT_DIR / f"active_{os.getpid()}"
                self.active.touch()
                break
            else:
                time.sleep(1)

    def release(self):
        if self.fh:
            self.fh.close()            # closing drops the lock (also when the process dies)
            self.fh = None
            self.active.unlink(missing_ok=True)


def parse_ps(out, self_pid):
    """Rows of `ps -Ao pid=,ppid=,etime=,command=` output that run the emu_harness.py script (not a test file
    or an editor that only names it), other than self_pid and cleanup itself."""
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) != 4:
            continue
        argv = parts[3].split()
        if Path(argv[0]).name.lower().startswith("python") and \
                any(Path(t).name == "emu_harness.py" for t in argv[1:3]) and int(parts[0]) != self_pid and \
                "cleanup" not in argv:
            rows.append({"pid": int(parts[0]), "ppid": int(parts[1]), "elapsed": parts[2], "command": parts[3][:200],
                         "orphan": int(parts[1]) == 1})
    return rows


def harness_processes():
    """Running emu_harness.py processes (pid, ppid, elapsed, command, orphan) other than this one."""
    import subprocess
    out = subprocess.run(["ps", "-Ao", "pid=,ppid=,etime=,command="], capture_output=True, text=True).stdout
    return parse_ps(out, os.getpid())


def cmd_cleanup(a):
    """List leftover harness processes; --kill stops the orphans (--all: every one)."""
    import signal
    rows = harness_processes()
    for r in rows:
        print(json.dumps(r))
    victims = [r for r in rows if a.all or r["orphan"]] if a.kill else []
    for r in victims:
        try:
            os.kill(r["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    if victims:
        time.sleep(5)
        for r in victims:
            try:
                os.kill(r["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
    stale = 0                       # slot markers of children that died without releasing them
    for p in SLOT_DIR.glob("active_*"):
        try:
            os.kill(int(p.name.split("_")[1]), 0)      # still running (any process using the harness)
        except ProcessLookupError:
            p.unlink(missing_ok=True)
            stale += 1
        except (PermissionError, ValueError):
            pass
    print(json.dumps({"processes": len(rows), "orphans": sum(r["orphan"] for r in rows), "stopped": len(victims),
                      "stale_slot_markers_removed": stale}))
    return 0


def run_child(args, timeout=900):
    """Run 'emu_harness.py <args>' in a fresh process and return the JSON of its 'RESULT ' line.
    One emulator per process: a second DeSmuME instance in the same process crashes (SIGSEGV)."""
    rc, out, err = spawn(args, timeout)
    for line in out.splitlines():
        if "RESULT " in line:          # DeSmuME may print to stdout without a newline just before it
            return json.loads(line[line.index("RESULT ") + 7:])
    raise RuntimeError(f"child {args} failed (rc {rc}): {err[-2000:]}")


PAL_PARK_MAP = 109
ENC_BANK_GETTER_109 = 0x0203A7D6   # 'pop {r4, pc}' of the map-109 branch of the encounter-bank getter 0x0203A7B0
CODE_SIG[ENC_BANK_GETTER_109] = "10bd"


FAST_LEAD = 291                    # Ninjask: generated at Lv100 and made the lead so fleeing never fails
PAL_PARK_ENTRY = (24, 46)          # where the gate script (file 809) warps the player
PAL_PARK_STATE_VAR = 16565         # set to 3 by the gate script before the warp
PAL_PARK_GRASS = ((16, 40), (17, 40))   # two tall-grass tiles of the big field (MapGrid)
# Hide flags of the eight standing-Pokemon groups (2124-2131); the gate clears the day's two groups. With
# all eight set the map's load script leaves the player locked.
PAL_PARK_FLAGS = [("ClearFlag", 2126), ("ClearFlag", 2130)] + [("SetFlag", f) for f in (2124, 2125, 2127,
                                                                                            2128, 2129, 2131)]


def enter_pal_park(h):
    """From the field: what the gate's Fixed Catch script does before its Warp (var, group flags), then the
    same Warp. Leaves the player standing at the park entrance with control."""
    h.run_script(program=script_bytes(*WARP_CMDS(PAL_PARK_MAP, *PAL_PARK_ENTRY, 0, before=[
        ("SetVar", PAL_PARK_STATE_VAR, 3)] + PAL_PARK_FLAGS)), settle=300)
    h.step(200)
    if h.position() != (PAL_PARK_MAP, *PAL_PARK_ENTRY):
        raise RuntimeError(f"Pal Park entry failed: {h.position()}")


def cmd_palpark(a):
    """D-1484: for each pinned weekday, log the encounter record the bank getter returns on map 109
    (hook on its map-109 return) and, with --count, sample wild encounters in the park's tall grass."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = datetime.date(2026, 10, 4)           # a Sunday
    names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    days = [names.index(d) for d in a.days.split(",")] if a.days else range(7)
    if a.day is None:                  # parent: one child process per day (DeSmuME can't be reopened)
        report = {"rom": str(a.rom), "days": [run_child(["palpark", "--rom", a.rom, "--sav", a.sav,
                  "--out", a.out, "--count", str(a.count), "--max-steps", str(a.max_steps),
                  "--day", str(wd)]) for wd in days]}
        for d in report["days"]:
            print(json.dumps(d))
        js = out / ("palpark_weekdays.json" if a.count == 0 else "palpark_weekdays_encounters.json")
        js.write_text(json.dumps(report, indent=1))
        print("report:", js)
        return 0
    wd = a.day
    when = datetime.datetime.combine(base + datetime.timedelta(days=wd), datetime.time(12, 0))
    seen = []

    def hooks(h):
        h.on_exec(ENC_BANK_GETTER_109, lambda h: seen.append(h.reg.r0))
    with start_at(None, rom=a.rom, sav=a.sav, clock=when, out=out, verbose=False, hooks=hooks) as h:
        if a.count:                    # a fast lead so RUN always works (Lv100 Ninjask)
            h.generate_pokemon(FAST_LEAD, level=100)
            h.swap_party(0, h.generated_slot)
        enter_pal_park(h)
        log = WildLog(h)
        steps = 0
        if a.count:
            h.walk_to(*PAL_PARK_GRASS[0])
        while len(log.rows) < a.count and steps < a.max_steps:
            n = len(log.rows)
            for tile in (PAL_PARK_GRASS[1], PAL_PARK_GRASS[0]):
                h.walk_to(*tile)
                steps += 1
                if len(log.rows) > n:
                    break
            if len(log.rows) > n:
                h.step(300)
                if n == 0:
                    h.screenshot(f"palpark_{names[wd]}_encounter")
                if not h.flee(battle_menu_wait=20):
                    raise RuntimeError("could not flee")
        day = {"weekday": wd, "name": names[wd], "clock": h.clock(), "records": sorted(set(seen)),
               "getter_calls": len(seen), "steps": steps,
               "species": [r["species"] for r in log.rows]}
    print("RESULT " + json.dumps(day), flush=True)
    return 0


PLATES = {298: "Flame", 299: "Splash", 300: "Zap", 301: "Meadow", 302: "Icicle", 303: "Fist", 304: "Toxic",
          305: "Earth", 306: "Sky", 307: "Mind", 308: "Insect", 309: "Stone", 310: "Spooky", 311: "Draco",
          312: "Dread", 313: "Iron"}
ARCEUS = 493
RARE_CANDY, SUN_STONE, BLACK_BELT = 50, 80, 241
LYCANROC_SETFORM = 0x02074B0E    # evolution completion: bl SetMonData(mon, 0x70 FORM, sp+0xC) for species 745
CODE_SIG[LYCANROC_SETFORM] = "f9f72ffa"


def cmd_arceus(a):
    """D-1501: give Arceus each Plate through Bag -> Give and record the stored form; screenshot the summary.
    Parent: one child builds a savestate with a generated Arceus in party slot 6, one child per Plate."""
    out = Path(a.out) / "arceus"
    out.mkdir(parents=True, exist_ok=True)
    state = out / "arceus_base.dst"
    if a.plate is None:
        run_child(["arceus", "--rom", a.rom, "--sav", a.sav, "--out", a.out, "--plate", "0"])
        rows = [run_child(["arceus", "--rom", a.rom, "--sav", a.sav, "--out", a.out, "--plate", str(p)])
                for p in PLATES]
        for r in rows:
            print(json.dumps(r))
        (out / "arceus_report.json").write_text(json.dumps({"rom": str(a.rom), "plates": rows}, indent=1))
        print("report:", out / "arceus_report.json")
        return 0
    if a.plate == 0:
        with start_at(None, rom=a.rom, sav=a.sav, out=out, verbose=False) as h:
            mon = h.generate_pokemon(ARCEUS, level=50)
            h.save_state(state)
        print("RESULT " + json.dumps({"base": str(state), "arceus": mon}))
        return 0
    with Harness(a.rom, None, savestate=state, out=out, verbose=False) as h:
        h.bag_put_first(a.plate)
        h.open_bag()
        h.give_from_bag(0, 5)
        mon = h.party()[5]
        h.open_summary_from_bag(5)
        shot = h.screenshot(f"arceus_{a.plate}_summary")
    print("RESULT " + json.dumps({"plate": PLATES[a.plate], "item": mon["item"], "form": mon["form"],
                                  "species": mon["species"], "screenshot": str(shot)}))
    return 0


def cmd_evolve(a):
    """D-1485 / D-1486: generate a Pokemon holding an item, pin the clock, level it up with a Rare Candy
    through the bag (the game's own level-up path), optionally use a stone, log species/form after each."""
    out = Path(a.out) / "evolve"
    out.mkdir(parents=True, exist_ok=True)
    clock = datetime.datetime.fromisoformat(a.clock)

    def edit(sf):
        sf.set_pocket("medicine", [(RARE_CANDY, 99)])
        sf.set_pocket("items", [(a.stone, 5)] if a.stone else [])

    rows = {"rom": str(a.rom), "species": a.species, "level": a.level, "item": a.item, "clock": a.clock}
    form_writes = rows["lycanroc_form_written"] = []

    def hooks(h):
        h.on_exec(LYCANROC_SETFORM, lambda h: form_writes.append(h.u8(h.reg.r2)))
    with start_at(None, rom=a.rom, sav=a.sav, edit=edit, clock=clock, out=out, verbose=False,
                  hooks=hooks) as h:
        rows["created"] = h.generate_pokemon(a.species, level=a.level, item=a.item)
        rows["clock_seen"] = h.clock()
        slot = h.generated_slot
        rows["after_candy"] = h.level_up_with_candy(slot)
        h.screenshot(f"{a.tag}_after_candy")
        if a.stone:
            h.bag_pocket("items")
            rows["after_stone"] = h.use_from_bag(0, slot)
            h.screenshot(f"{a.tag}_after_stone")
        h.open_summary_from_bag(slot)
        rows["summary"] = str(h.screenshot(f"{a.tag}_summary"))
    print("RESULT " + json.dumps(rows))
    return 0


def screen_diff(img_a, img_b, box=None):
    """Fraction of pixels that differ between two screenshots (optionally inside box), plus a diff mask.
    For regression use, diff against an approved baseline of the same ROM: any change gets a human look."""
    from PIL import ImageChops
    a, b = img_a.convert("RGB"), img_b.convert("RGB")
    if box:
        a, b = a.crop(box), b.crop(box)
    d = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 24 else 0)
    return d.histogram()[255] / (d.size[0] * d.size[1]), d


def _screen_options(h):
    h.field_menu("options")
    h.mark("options")


def _screen_ev(h):
    h.open_bag()
    h.bag_pocket("key")
    h.touch(*BAG_SLOTS[0], frames=12, after=30)
    h.touch(*BAG_USE, frames=12, after=180)
    h.mark("ev_allocator")


def _screen_dex(h):
    h.field_menu("pokedex")
    h.press("Y", after=260)
    h.mark("dex_search")
    h.touch(75, 40, frames=12, after=120)       # NAME field -> search by letter
    h.mark("dex_letters")


def _screen_battle(h):
    h.generate_pokemon(383, level=70)           # Groudon: Drought -> sun shows in the battle info panel
    h.swap_party(0, h.generated_slot)
    h.walk_until_battle()
    h.step(900)
    h.mark("battle_menu")
    h.touch(225, 15, frames=12, after=150)      # INFO
    h.mark("battle_info")


EV_ALLOCATOR = 745
SCREENS = {  # name: (map or None to stay, x, y, flags, recipe)
    "options": (None, 0, 0, (), _screen_options),
    "ev": (None, 0, 0, (), _screen_ev),
    "dex": (None, 0, 0, (), _screen_dex),
    "battle": (315, 17, 24, (2423,), _screen_battle),
}


def cmd_screens(a):
    """Run screen recipes on the Chinese and the English ROM (one child per recipe and ROM) and save
    CN|EN pairs plus a pixel-difference figure. A human (or a baseline diff) decides whether text fits."""
    from PIL import Image
    out = Path(a.out) / "screens"
    out.mkdir(parents=True, exist_ok=True)
    names = list(SCREENS) if a.only == "all" else a.only.split(",")
    if a.lang is None:
        rows = []
        for name in names:
            res = {lang: run_child(["screens", "--only", name, "--lang", lang, "--out", a.out, "--sav", a.sav,
                                    "--rom-cn", a.rom_cn, "--rom-en", a.rom_en]) for lang in ("cn", "en")}
            for shot in res["en"]["marks"]:
                cn, en = Image.open(out / f"{shot}_cn.png"), Image.open(out / f"{shot}_en.png")
                pair = Image.new("RGB", (2 * 256 + 8, 384), "white")
                pair.paste(cn, (0, 0))
                pair.paste(en, (264, 0))
                pair.save(out / f"{shot}_pair.png")
                rows.append({"screen": shot, "pair": str(out / f"{shot}_pair.png"),
                             "cn_en_diff": round(screen_diff(cn, en)[0], 3)})
                print(json.dumps(rows[-1]), flush=True)
        (out / "screens_report.json").write_text(json.dumps(rows, indent=1))
        return 0
    rom = a.rom_en if a.lang == "en" else a.rom_cn
    map_id, x, y, flags, recipe = SCREENS[names[0]]

    def edit(sf):
        sf.set_pocket("key", [(EV_ALLOCATOR, 1)] + sf.pocket("key")[:40])
    with start_at(map_id, x, y, rom=rom, sav=a.sav, flags=flags, edit=edit, out=out, verbose=False,
                  clock=datetime.datetime(2026, 10, 9, 12)) as h:
        h.tag = a.lang
        recipe(h)
        marks = h.marks
    print("RESULT " + json.dumps({"lang": a.lang, "marks": marks}))
    return 0


def run_ops(h, ops, tag="x", states=None):
    """Tiny op language for recipes and exploration (from the UI hunt agent's drive.py):
      A B X Y L R START SELECT UP DOWN LEFT RIGHT   press, 40 frames after; KEY*n repeats; KEY/after
      wN            wait N frames            tX,Y[/after]   touch (60 frames after)
      hKEY / uKEY   hold / release           s:name         screenshot <out>/name_<tag>.png
      ss:name       savestate <states>/name_<tag>.dst
      gen:species,level[,item[,form]]        the hack's generator (party slot 6, or the next free slot)
      moves:slot,m1[,m2,m3,m4]               write moves (PP 10) into a party Pokemon
      script:id | prog:Cmd,arg,...;Cmd,...   run a script id / an encoded script program
      warp:map,x,y                           scripted warp (normal map entry)
      walk:x,y                               walk_to on the current map
    Returns the list of screenshots taken."""
    shots = []
    for op in ops:
        if not op:
            continue
        head, _, arg = op.partition(":")
        if op.startswith("s:"):
            shots.append(str(h.screenshot(f"{arg}_{tag}")))
        elif op.startswith("ss:"):
            Path(states or h.out).mkdir(parents=True, exist_ok=True)
            h.save_state(Path(states or h.out) / f"{arg}_{tag}.dst")
        elif head == "gen" and arg:
            v = [int(x) for x in arg.split(",")] + [0, 0]
            print("GEN", h.generate_pokemon(v[0], level=v[1], item=v[2], form=v[3]), flush=True)
        elif head == "moves" and arg:
            v = [int(x) for x in arg.split(",")]
            h.edit_party_mon(v[0], moves=v[1:5])
        elif head == "script" and arg:
            h.run_script(int(arg))
        elif head == "prog" and arg:
            cmds = [tuple([c.split(",")[0]] + [int(x) for x in c.split(",")[1:]]) for c in arg.split(";")]
            h.run_script(program=script_bytes(*cmds))
        elif head == "warp" and arg:
            h.warp(*[int(x) for x in arg.split(",")])
        elif head == "walk" and arg:
            h.walk_to(*[int(x) for x in arg.split(",")])
        elif op[0] == "w" and op[1:].isdigit():
            h.step(int(op[1:]))
        elif op[0] == "t" and op[1:2].isdigit():
            xy, _, after = op[1:].partition("/")
            x, y = map(int, xy.split(","))
            h.touch(x, y, frames=10, after=int(after or 60))
        elif op[0] in "hu" and op[1:] in KEYS:
            (h.hold if op[0] == "h" else h.release)(op[1:])
        else:
            k, _, after = op.partition("/")
            k, _, n = k.partition("*")
            if k not in KEYS:
                raise ValueError(f"unknown op {op!r}")
            for _ in range(int(n or 1)):
                h.press(k, after=int(after or 40))
    return shots


def cmd_drive(a):
    """Run ops on one ROM from a savestate, or from a (teleported) battery save."""
    rom = {"en": a.rom_en, "cn": a.rom_cn}[a.lang]
    out = Path(a.out) / "drive"
    clock = datetime.datetime.fromisoformat(a.clock)
    if a.state:
        with Harness(rom, savestate=a.state, out=out, verbose=False) as h:
            h.set_clock(clock)
            shots = run_ops(h, a.ops, a.lang, a.states)
    else:
        with start_at(a.map, a.x, a.y, rom=rom, sav=a.sav, out=out, verbose=False, clock=clock) as h:
            shots = run_ops(h, a.ops, a.lang, a.states)
    print("RESULT " + json.dumps({"lang": a.lang, "shots": shots}))
    return 0


THIEF, SEISMIC_TOSS, CHANSEY = 168, 69, 113
SKARMORY = 227
THIEF_CASES = {   # case: (item, trainer id or None for the wild control, attacker species); the holder leads
    "air_balloon": (576, 252, CHANSEY), "eviolite": (584, 452, SKARMORY), "weakness_policy": (600, 207, CHANSEY),
    "salac": (203, 605, CHANSEY), "petaya": (204, 595, SKARMORY), "wild_eviolite": (584, None, CHANSEY),
}
THIEF_TURNS = 2                   # Thief on the first two turns (the first can be lost to a flinch)


def bag_items(h):
    """{item: quantity} over the whole bag (RAM)."""
    raw = h.read(h.array(ARR_BAG), 0x860)
    out = {}
    for i in range(0, 0x860, 4):
        item, qty = struct.unpack_from("<HH", raw, i)
        if item:
            out[item] = out.get(item, 0) + qty
    return out


def cmd_thief(a):
    """Tier 4: does a Pokemon keep an item it stole with Thief? A Lv100 Chansey (generator; Thief, Seismic
    Toss; no held item) leads; the battle starts with the game's TrainerBattle command against a trainer
    whose lead holds the item (or a scripted wild battle whose Pokemon is given the item: the control).
    Turn 1 Thief (every message screenshotted), then Seismic Toss until the battle ends; then the lead's
    held item and the bag are compared with before the battle."""
    out = Path(a.out) / "thief"
    out.mkdir(parents=True, exist_ok=True)
    cases = list(THIEF_CASES) if a.case == "all" else a.case.split(",")
    if a.child is None:
        rows = []
        for c in cases:
            try:
                rows.append(run_child(["thief", "--rom", a.rom, "--sav", a.sav, "--out", a.out, "--case", c,
                                       "--child", c]))
            except RuntimeError as e:
                rows.append({"case": c, "error": str(e)[-300:]})
        for r in rows:
            print(json.dumps(r))
        (out / "thief_report.json").write_text(json.dumps(rows, indent=1))
        return 0
    item, tid, attacker = THIEF_CASES[a.child]
    with start_at(None, rom=a.rom, sav=a.sav, out=out, verbose=False,
                  clock=datetime.datetime(2026, 10, 9, 12)) as h:
        h.generate_pokemon(attacker, level=100)
        h.edit_party_mon(h.generated_slot, moves=[THIEF, SEISMIC_TOSS], pp=[25, 20], item=0)
        h.swap_party(0, h.generated_slot)
        before = bag_items(h)
        wild = None
        if tid is None:
            wild = WildLog(h, on_mon=lambda h, m: h.write(m, encode_pokemon(h.read(m, 136), item=item)))
            h.run_script(program=script_bytes(("LockAll",), ("WildBattle", 19, 20, 0), ("ReleaseAll",),
                                              ("End",)))
        else:
            h.trainer_battle(tid)
        shots = []
        turns, state = 0, "menu"
        while turns < THIEF_TURNS and state == "menu":
            state = h.battle_turn(0, shots=shots)
            turns += 1
        if state == "menu":
            turns += h.fight([1])
        h.step(120)
        after = bag_items(h)
        lead = h.party()[0]
        from PIL import Image
        cols = 6
        sheet = Image.new("RGB", (256 * cols, 192 * max(1, (len(shots) + cols - 1) // cols)), "white")
        for i, p in enumerate(shots):
            sheet.paste(Image.open(p).crop((0, 0, 256, 192)), (256 * (i % cols), 192 * (i // cols)))
        sheet_path = out / f"thief_{a.child}_turn1.png"
        sheet.save(sheet_path)
        for p in shots:
            Path(p).unlink()
        row = {"case": a.child, "item": item, "trainer": tid, "attacker": attacker, "turns": turns,
               "lead_item_after": lead["item"], "lead_species": lead["species"],
               "bag_change": {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)
                              if after.get(k, 0) != before.get(k, 0)},
               "turn1_messages": str(sheet_path), "wild": wild.rows if wild else None}
    print("RESULT " + json.dumps(row))
    return 0


CUTSCENE_LINES = (   # SIZE-200% lines and placeholders from D-0541 D-0553 D-0571 D-0719 D-0744 D-0853 D-0903
    "313#28 314#14 314#28 457#123 319#26 48#5 48#6 48#20 321#27 476#14 476#19 476#69 476#74 476#85 476#102 "
    "356#4 356#10 356#70 356#71 356#72 356#73 356#74 356#75 356#76 356#77 356#78 356#79 356#80 356#81 356#84 "
    "511#153 124#124 124#125 547#7 53#1 53#39 546#12 546#48 90#141 599#45 599#56 81#25 377#136 "   # D-0983
    "457#140 457#172 126#100")                                                                    # D-0550/0746


def cmd_messages(a):
    """Print a027 lines in the normal field message window on both ROMs and save CN|EN page pairs."""
    from PIL import Image
    out = Path(a.out) / "messages"
    out.mkdir(parents=True, exist_ok=True)
    refs = [(int(b), int(i)) for b, i in (r.split("#") for r in (a.refs or CUTSCENE_LINES).split())]
    if a.lang is None:
        res = {lang: run_child(["messages", "--lang", lang, "--out", a.out, "--sav", a.sav, "--rom-cn", a.rom_cn,
                                "--rom-en", a.rom_en, "--refs", " ".join(f"{b}#{i}" for b, i in refs)],
                               timeout=3600) for lang in ("cn", "en")}
        rows = []
        for b, i in refs:
            key = f"{b}#{i}"
            cn, en = res["cn"]["pages"].get(key, []), res["en"]["pages"].get(key, [])
            n = max(len(cn), len(en), 1)
            pair = Image.new("RGB", (2 * 256 + 8, 192 * n), "white")
            for k, pth in enumerate(cn):
                pair.paste(Image.open(pth).crop((0, 0, 256, 192)), (0, 192 * k))
            for k, pth in enumerate(en):
                pair.paste(Image.open(pth).crop((0, 0, 256, 192)), (264, 192 * k))
            path = out / f"msg_{b:04d}_{i}_pair.png"
            pair.save(path)
            rows.append({"ref": f"a027/{b:04d}#{i}", "pages_cn": len(cn), "pages_en": len(en), "pair": str(path)})
            print(json.dumps(rows[-1]), flush=True)
        (out / "messages_report.json").write_text(json.dumps(rows, indent=1))
        return 0
    rom = a.rom_en if a.lang == "en" else a.rom_cn
    pages = {}
    with start_at(None, rom=rom, sav=a.sav, out=out, verbose=False, clock=datetime.datetime(2026, 10, 9, 12)) as h:
        for b, i in refs:
            pages[f"{b}#{i}"] = [str(p) for p in h.show_message(b, i, name=f"msg_{b:04d}_{i}_{a.lang}")]
    print("RESULT " + json.dumps({"lang": a.lang, "pages": pages}))
    return 0


# ----------------------------------------------------------------------------- regression suite

def _child_json(args, path, timeout=3600):
    """Run a harness command in a child process and load the JSON report it writes."""
    rc, out, err = spawn(args, timeout)
    if not Path(path).exists():
        raise RuntimeError(f"{args[0]} failed (rc {rc}): {err[-1500:]}")
    return json.loads(Path(path).read_text())


def _check_unown(rom, out):
    rep = _child_json(["unown", "--rom", rom, "--count", "6", "--shots", "1", "--out", out,
                       "--clock", "2026-10-09T12:00:00", "--json", out / "unown.json"], out / "unown.json")
    u = rep["summary"].get("unown", {})
    return (u.get("count", 0) >= 6 and u.get("all_final_A") and u.get("decoder_check")), u


def _check_palpark(rom, out):
    rep = _child_json(["palpark", "--rom", rom, "--out", out], out / "palpark_weekdays.json")
    got = [d["records"] for d in rep["days"]]
    return got == [[141 + k] for k in range(7)], {"records": got}


ARCEUS_EXPECTED = {"Flame": 10, "Splash": 11, "Zap": 13, "Meadow": 12, "Icicle": 15, "Fist": 1, "Toxic": 3,
                   "Earth": 4, "Sky": 2, "Mind": 14, "Insect": 6, "Stone": 5, "Spooky": 7, "Draco": 16,
                   "Dread": 17, "Iron": 8}


def _check_arceus(rom, out):
    rep = _child_json(["arceus", "--rom", rom, "--out", out], out / "arceus" / "arceus_report.json")
    got = {r["plate"]: r["form"] for r in rep["plates"]}
    return got == ARCEUS_EXPECTED, {"forms": got}


EVOLVE_CASES = [  # (tag, args, check(result))
    ("petilil_day", ["--species", 548, "--level", 10, "--item", 241, "--stone", 80, "--clock", "2026-10-09T12:00:00"],
     lambda r: (r["after_candy"]["species"], r["after_candy"]["form"], r["after_stone"]["species"],
                r["after_stone"]["form"]) == (548, 1, 549, 1)),
    ("petilil_night", ["--species", 548, "--level", 10, "--item", 241, "--clock", "2026-10-09T22:00:00"],
     lambda r: (r["after_candy"]["form"], r["after_candy"]["item"]) == (0, 241)),
    ("rockruff_12", ["--species", 744, "--level", 24, "--clock", "2026-10-09T12:00:00"],
     lambda r: (r["after_candy"]["species"], r["after_candy"]["form"]) == (745, 0)),
    ("rockruff_18", ["--species", 744, "--level", 24, "--clock", "2026-10-09T18:00:00"],
     lambda r: (r["after_candy"]["species"], r["after_candy"]["form"]) == (745, 2)),
    ("rockruff_22", ["--species", 744, "--level", 24, "--clock", "2026-10-09T22:00:00"],
     lambda r: (r["after_candy"]["species"], r["after_candy"]["form"]) == (745, 1)),
]


def _check_evolve(rom, out):
    details, ok = {}, True
    for tag, args, test in EVOLVE_CASES:
        r = run_child(["evolve", "--rom", rom, "--out", out, "--tag", tag] + args)
        passed = bool(test(r))
        ok &= passed
        details[tag] = {"pass": passed, "after_candy": {k: r["after_candy"][k] for k in ("species", "form", "item")},
                        **({"after_stone": {k: r["after_stone"][k] for k in ("species", "form")}}
                           if "after_stone" in r else {})}
    return ok, details


def _check_dex(rom, out, last=30):
    """Capture Pokedex entry panels 1..last (number verified by OCR) and diff them against the approved
    baseline for this ROM (work/build/harness/baselines/dex_<rom name>/). A missing baseline is created."""
    r = run_child(["dexcapture", "--rom", rom, "--out", out, "--last", last])
    base = DEF_OUT / "baselines" / f"dex_{Path(rom).stem}"
    shots = Path(r["dir"])
    from PIL import Image
    if not base.exists():
        shutil.copytree(shots, base)
        return not r["errors"], {"captured": len(r["captured"]), "baseline": f"created {base}", "errors": r["errors"]}
    changed = []
    for img in sorted(shots.glob("*.png")):
        ref = base / img.name
        if not ref.exists() or screen_diff(Image.open(img), Image.open(ref))[0] > 0:
            changed.append(img.name)
    return not r["errors"] and not changed, {"captured": len(r["captured"]), "changed_vs_baseline": changed,
                                              "errors": r["errors"], "baseline": str(base)}


SUITE_CHECKS = {"unown": _check_unown, "palpark": _check_palpark, "arceus": _check_arceus,
                "evolve": _check_evolve, "dex": _check_dex}


def cmd_suite(a):
    """Behaviour + screen checks on both ROMs, run in parallel child processes; one JSON report, pass/fail."""
    from concurrent.futures import ThreadPoolExecutor
    out = Path(a.out) / "suite"
    checks = list(SUITE_CHECKS) if a.only == "all" else a.only.split(",")
    roms = {"cn": a.rom_cn, "en": a.rom_en}
    jobs = [(c, lang) for c in checks for lang in roms]
    t0 = time.time()

    def run(job):
        c, lang = job
        d = out / lang / c
        d.mkdir(parents=True, exist_ok=True)
        t = time.time()
        try:
            ok, details = SUITE_CHECKS[c](roms[lang], d)
            row = {"check": c, "rom": lang, "pass": bool(ok), "details": details}
        except Exception as e:     # a crash is a failure with its message
            row = {"check": c, "rom": lang, "pass": False, "error": f"{type(e).__name__}: {str(e)[-800:]}"}
        row["seconds"] = round(time.time() - t, 1)
        print(json.dumps({k: row[k] for k in ("check", "rom", "pass", "seconds")}), flush=True)
        return row

    with ThreadPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(run, jobs))
    report = {"roms": roms, "seconds": round(time.time() - t0, 1), "pass": all(r["pass"] for r in rows),
              "results": rows}
    (out / "suite_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({"pass": report["pass"], "seconds": report["seconds"],
                      "report": str(out / "suite_report.json")}))
    return 0 if report["pass"] else 1


def cmd_dexcapture(a):
    """Child for the dex check: capture entry panels 1..--last on one ROM."""
    import emu_dex
    shots = Path(a.out) / "dex"
    with start_at(None, rom=a.rom, out=a.out, verbose=False, clock=datetime.datetime(2026, 10, 9, 12)) as h:
        emu_dex.open_dex_list(h)
        done, errors = emu_dex.capture_entries(h, 1, a.last, shots)
    print("RESULT " + json.dumps({"dir": str(shots), "captured": done, "errors": errors}))
    return 0


def cmd_info(a):
    with Harness(a.rom, a.sav, out=a.out) as h:
        if a.clock:
            h.set_clock(datetime.datetime.fromisoformat(a.clock))
        h.boot_to_menu()
        h.continue_game()
        print(json.dumps({"save": hex(h.save), "location": h.location(), "previous": h.location(1),
                          "clock": h.clock(), "in_field": h.in_field(), "party": h.party(),
                          "screenshot": str(h.screenshot("info_field"))}, indent=1))
    return 0


def main(argv=None):
    _parent_watchdog()
    _install_child_handlers()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emulator", choices=EMULATORS, help="backend for every Harness of this run and its child "
                    "processes: desmume (py-desmume, the default) or melonds (work/tools/melonds.py); sets "
                    "$EMU_HARNESS_EMULATOR")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cl = sub.add_parser("cleanup", help="list leftover emu_harness processes; --kill stops orphans (--all: every one)")
    cl.add_argument("--kill", action="store_true")
    cl.add_argument("--all", action="store_true")
    pp = sub.add_parser("palpark", help="D-1484: encounter record of map 109 per pinned weekday")
    pp.add_argument("--rom", default=str(DEF_ROM_CN))
    pp.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    pp.add_argument("--out", default=str(DEF_OUT))
    pp.add_argument("--days", help="comma list of Sun,Mon,...; default all seven")
    pp.add_argument("--count", type=int, default=0, help="wild Pokemon to log per day (0: only the getter)")
    pp.add_argument("--max-steps", type=int, default=600)
    pp.add_argument("--day", type=int, help=argparse.SUPPRESS)
    ar = sub.add_parser("arceus", help="D-1501: Arceus form for each Plate given through the bag")
    ar.add_argument("--rom", default=str(DEF_ROM_CN))
    ar.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    ar.add_argument("--out", default=str(DEF_OUT))
    ar.add_argument("--plate", type=int, help=argparse.SUPPRESS)
    ev = sub.add_parser("evolve", help="level up a generated Pokemon with a Rare Candy at a pinned time")
    ev.add_argument("--rom", default=str(DEF_ROM_CN))
    ev.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    ev.add_argument("--out", default=str(DEF_OUT))
    ev.add_argument("--species", type=int, required=True)
    ev.add_argument("--level", type=int, required=True)
    ev.add_argument("--item", type=int, default=0, help="held item")
    ev.add_argument("--stone", type=int, default=0, help="also use this item from the Items pocket")
    ev.add_argument("--clock", required=True)
    ev.add_argument("--tag", default="evolve")
    sc = sub.add_parser("screens", help="screen recipes on CN and EN, saved as side-by-side pairs")
    sc.add_argument("--only", default="all", help="comma list of: " + ", ".join(SCREENS))
    sc.add_argument("--rom-cn", default=str(DEF_ROM_CN))
    sc.add_argument("--rom-en", default=str(DEF_ROM_EN))
    sc.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    sc.add_argument("--out", default=str(DEF_OUT))
    sc.add_argument("--lang", choices=("cn", "en"), help=argparse.SUPPRESS)
    dr = sub.add_parser("drive", help="run the op language (see run_ops) on one ROM")
    dr.add_argument("--lang", choices=("cn", "en"), default="en")
    dr.add_argument("--rom-cn", default=str(DEF_ROM_CN))
    dr.add_argument("--rom-en", default=str(DEF_ROM_EN))
    dr.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    dr.add_argument("--state", help="start from this DeSmuME savestate instead of booting")
    dr.add_argument("--states", help="folder for ss: savestates (default --out/drive)")
    dr.add_argument("--map", type=int)
    dr.add_argument("--x", type=int)
    dr.add_argument("--y", type=int)
    dr.add_argument("--clock", default="2026-10-09T12:00:00")
    dr.add_argument("--out", default=str(DEF_OUT))
    dr.add_argument("ops", nargs="*")
    th = sub.add_parser("thief", help="Tier 4: keep an item stolen with Thief?")
    th.add_argument("--rom", default=str(DEF_ROM_CN))
    th.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    th.add_argument("--out", default=str(DEF_OUT))
    th.add_argument("--case", default="all", help="comma list of: " + ", ".join(THIEF_CASES))
    th.add_argument("--child", help=argparse.SUPPRESS)
    ms = sub.add_parser("messages", help="render a027 lines (bank#id) in the message window, CN|EN pairs")
    ms.add_argument("--refs", help="space-separated bank#id list; default: the SIZE-200%% cut-scene lines")
    ms.add_argument("--rom-cn", default=str(DEF_ROM_CN))
    ms.add_argument("--rom-en", default=str(DEF_ROM_EN))
    ms.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    ms.add_argument("--out", default=str(DEF_OUT))
    ms.add_argument("--lang", choices=("cn", "en"), help=argparse.SUPPRESS)
    su = sub.add_parser("suite", help="regression suite: behaviour and screen checks on both ROMs, pass/fail")
    su.add_argument("--only", default="all", help="comma list of: " + ", ".join(SUITE_CHECKS))
    su.add_argument("--rom-cn", default=str(DEF_ROM_CN))
    su.add_argument("--rom-en", default=str(DEF_ROM_EN))
    su.add_argument("--out", default=str(DEF_OUT))
    su.add_argument("--jobs", type=int, default=4, help="checks run in parallel (each starts its own emulators; "
                    "live emulators are capped by EMU_HARNESS_MAX_EMULATORS, default 6)")
    dc = sub.add_parser("dexcapture", help=argparse.SUPPRESS)
    dc.add_argument("--rom", default=str(DEF_ROM_CN))
    dc.add_argument("--out", default=str(DEF_OUT))
    dc.add_argument("--last", type=int, default=30)
    for name in ("info", "wild", "unown"):
        p = sub.add_parser(name)
        p.add_argument("--rom", default=str(DEF_ROM_CN))
        p.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
        p.add_argument("--out", default=str(DEF_OUT))
        p.add_argument("--clock", help="pin the game clock, ISO format, e.g. 2026-10-09T12:00:00 (a Friday)")
        if name != "info":
            unown = name == "unown"
            p.add_argument("--map", type=int, default=315 if unown else None, required=not unown)
            p.add_argument("--x", type=int, default=17 if unown else None, required=not unown)
            p.add_argument("--y", type=int, default=24 if unown else None, required=not unown)
            p.add_argument("--walk", default="LEFT,RIGHT", help="the two directions to pace in")
            p.add_argument("--span", type=int, default=3, help="tiles per direction")
            p.add_argument("--flags", default="2423,2424,2425,2426" if unown else "",
                           help="flags to set in the save (Unown: the four panel puzzles solved)")
            p.add_argument("--count", type=int, default=20, help="wild Pokemon to log")
            p.add_argument("--max-steps", type=int, default=3000)
            p.add_argument("--shots", type=int, default=3, help="screenshots of the first N battles")
            p.add_argument("--tag", default="unown_cn" if unown else "wild")
            p.add_argument("--state", help="also write a DeSmuME savestate taken right after the teleport")
            p.add_argument("--json")
    hg = sub.add_parser("hang", help="walk from a battery save and check for a freeze (ARM9 abort / dead screen); "
                        "melonDS unless --emulator desmume (emu_hang.py)")
    import emu_hang
    emu_hang.add_arguments(hg)
    tx = sub.add_parser("texture-bounds", help="four overworld texture-bound reproducers; original/fixed assertions")
    import emu_texture_bounds
    emu_texture_bounds.add_arguments(tx)
    rf = sub.add_parser("reflection", help="following-Pokemon water reflection (Bulbasaur NULL pointer); "
                        "original/fixed assertions")
    import emu_reflection
    emu_reflection.add_arguments(rf)
    import emu_fixes
    fx = sub.add_parser("fixes", help="one scenario per fix in work/patches: the fixed ROM and each control build "
                                      "(build.py --without <fix>) (emu_fixes.py)")
    emu_fixes.add_arguments(fx, DATA)
    emu_fixes.add_child_arguments(sub.add_parser("fixes-child", help=argparse.SUPPRESS))
    a = ap.parse_args(argv)
    if a.emulator:
        os.environ["EMU_HARNESS_EMULATOR"] = a.emulator
    return {"info": cmd_info, "wild": cmd_wild, "unown": cmd_wild, "palpark": cmd_palpark, "arceus": cmd_arceus, "evolve": cmd_evolve, "screens": cmd_screens, "drive": cmd_drive, "thief": cmd_thief, "messages": cmd_messages, "suite": cmd_suite,
            "dexcapture": cmd_dexcapture,
            "texture-bounds": emu_texture_bounds.run, "reflection": emu_reflection.run, "hang": emu_hang.run,
            "fixes": emu_fixes.run, "fixes-child": emu_fixes.cmd_child, "cleanup": cmd_cleanup}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
