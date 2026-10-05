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

WORK = Path(__file__).resolve().parent.parent
# ROMs, saves and outputs live only in the main checkout (ignored by git). From an agent worktree
# (<main>/.claude/worktrees/<name>/work) fall back to the main checkout's work/.
_parts = WORK.parts
DATA = Path(*_parts[:_parts.index(".claude")], "work") if ".claude" in _parts and not (WORK / "rom").exists() else WORK
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
FIELD_MENU = {"pokemon": (40, 100), "bag": (40, 128)}      # field touch menu (bag works by touch from the field)
BAG_SLOTS = [(64, 56), (192, 56), (64, 98), (192, 98), (64, 140), (192, 140)]   # 6 items per bag page
BAG_GIVE = (47, 173)             # item submenu: give to a Pokemon
PARTY_SLOTS = [(64, 28), (190, 28), (64, 76), (190, 76), (64, 124), (190, 124)]
PARTY_SUMMARY = (190, 40)
BAG_USE = (47, 142)              # item submenu: use
POCKET_TABS = {"items": (15, 15), "medicine": (46, 15), "balls": (80, 15), "tm": (113, 15),
               "berries": (146, 15), "mail": (176, 15), "battle": (206, 15), "key": (239, 15)}        # party submenu: summary (first entry)        # bottom-screen RUN button of the battle command menu
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

    def place_player(self, map_id, x, z, direction="DOWN"):
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
                struct.pack_into("<6h", self.data, a + 0x20, x, 0, oz, x, 0, oz)
            else:
                self.data[a:a + MAP_OBJECT_SIZE] = bytes(MAP_OBJECT_SIZE)

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


def encode_pokemon(raw, species=None, item=None, form=None):
    """Return raw (136+ bytes, encrypted) with boxed fields replaced; checksum recomputed."""
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
    if form is not None:
        b = pos["B"] + 0x18
        plain[b] = (plain[b] & 0x07) | (form << 3)
    words = struct.unpack("<64H", plain)
    checksum = sum(words) & 0xFFFF
    key = _prng_stream(checksum, 64)
    struct.pack_into("<H", raw, 6, checksum)
    struct.pack_into("<64H", raw, 8, *[w ^ k for w, k in zip(words, key)])
    return bytes(raw)


class Harness:
    """One emulator instance. Use as a context manager."""

    def __init__(self, rom=DEF_ROM_CN, sav=None, savestate=None, out=DEF_OUT, verbose=True):
        from desmume.emulator import DeSmuME
        from desmume.controls import Keys, keymask
        self._keymask = keymask
        self._keys = {k: getattr(Keys, "KEY_" + k) for k in KEYS}
        self.rom = Path(rom).resolve()
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._tmp = Path(tempfile.mkdtemp(prefix="emu_harness_"))
        os.symlink(self.rom, self._tmp / "game.nds")
        self._cwd = os.getcwd()
        os.chdir(self._tmp)            # DeSmuME writes its own battery file next to the ROM: keep it in tmp
        self.emu = DeSmuME()
        self.emu.open(str(self._tmp / "game.nds"))
        if sav:
            if not self.emu.backup.import_file(str(Path(sav).resolve()), 524288):
                raise RuntimeError(f"could not import save {sav}")
            self.emu.reset()
        if savestate:
            self.emu.savestate.load_file(str(Path(savestate).resolve()))
        self.mem = self.emu.memory.unsigned
        self.reg = self.emu.memory.register_arm9
        self.frame = 0
        self._per_frame = []
        self._held = set()

    # ------------------------------------------------------------------ lifecycle
    def close(self):
        try:
            self.emu.destroy()
        finally:
            os.chdir(self._cwd)
            shutil.rmtree(self._tmp, ignore_errors=True)

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

    def on_exec(self, addr, fn):
        """Call fn(harness) whenever the ARM9 executes addr (Thumb: even address). fn reads self.reg."""
        self.emu.memory.register_exec(addr, (lambda a, s: fn(self)) if fn else None)

    def on_frame(self, fn):
        """Call fn(harness) after every emulated frame (e.g. to keep a RAM value forced)."""
        self._per_frame.append(fn)

    # ------------------------------------------------------------------ running and input
    def step(self, n=1):
        for _ in range(n):
            self.emu.cycle(with_joystick=False)
            self.frame += 1
            for fn in self._per_frame:
                fn(self)

    def hold(self, *keys):
        for k in keys:
            self.emu.input.keypad_add_key(self._keymask(self._keys[k]))
            self._held.add(k)

    def release(self, *keys):
        for k in keys or list(self._held):
            self.emu.input.keypad_rm_key(self._keymask(self._keys[k]))
            self._held.discard(k)

    def press(self, key, frames=6, after=0):
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
        RTC (about every 10 frames) and right now. DeSmuME itself keeps running on host time."""
        wd = (when.isoweekday()) % 7
        self._clock = (struct.pack("<4I", when.year - 2000, when.month, when.day, wd),
                       struct.pack("<3I", when.hour, when.minute, when.second))
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
        self.save   # raises if the save was not loaded
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
        self.check_code(OV2_SIG)

    # ------------------------------------------------------------------ field helpers
    def in_field(self):
        """True while overlay 2 (field) is resident; battles replace it."""
        for addr, hexs in OV2_SIG.items():
            want = bytes.fromhex(hexs)
            if self.read(addr, len(want)) != want:
                return False
        return True

    def flee(self, max_tries=12, battle_menu_wait=320):
        """From the start of a wild battle: wait for the command menu, touch RUN until the field is back."""
        self.step(battle_menu_wait)
        for _ in range(max_tries):
            self.touch(*RUN_BUTTON, after=60)
            if self.in_field():
                self.step(120)
                return True
            self.press("B", after=60)     # dismiss "can't escape!" text
        return False

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

    def __init__(self, h):
        self.h = h
        self.rows = []
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
        mon = decode_pokemon(h.read(c["mon"], 136))
        c.update(species=mon["species"], form=mon["form"], pid=mon["pid"], checksum_ok=mon["checksum_ok"])
        c["mon"] = hex(c["mon"])
        self.rows.append(c)
        h.log("wild:", c)


# ----------------------------------------------------------------------------- Unown POC

class start_at:
    """Context manager: copy the save, teleport (map, x, y), set flags/vars, pin the clock, boot, Continue.
    Yields a Harness standing on the map. Example:
        with start_at(109, 16, 14, clock=datetime.datetime(2026, 10, 9, 12)) as h: ..."""

    def __init__(self, map_id=None, x=None, y=None, rom=DEF_ROM_CN, sav=None, flags=(), vars=None,
                 clock=None, out=DEF_OUT, verbose=True, hooks=None, edit=None):
        """map_id None: stay where the save is. edit: fn(SaveFile) for further save edits (bag, ...)."""
        self.args = (map_id, x, y, rom, sav or DEF_SAVES / "full_bag_6mons.sav", flags, vars or {}, clock,
                     out, verbose, hooks, edit)

    def __enter__(self):
        map_id, x, y, rom, sav, flags, vars_, clock, out, verbose, hooks, edit = self.args
        sf = SaveFile(sav)
        if map_id is not None:
            sf.place_player(map_id, x, y, "DOWN")
        if edit:
            edit(sf)
        for f in flags:
            sf.set_flag(f)
        for v, val in vars_.items():
            sf.set_var(v, val)
        self._dir = Path(tempfile.mkdtemp(prefix="emu_harness_sav_"))
        sf.write(self._dir / "edited.sav")
        self.h = Harness(rom, self._dir / "edited.sav", out=out, verbose=verbose)
        try:
            if clock:
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


def run_child(args, timeout=900):
    """Run 'emu_harness.py <args>' in a fresh process and return the JSON of its 'RESULT ' line.
    One emulator per process: a second DeSmuME instance in the same process crashes (SIGSEGV)."""
    import subprocess
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve())] + [str(x) for x in args],
                          capture_output=True, text=True, timeout=timeout)
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    raise RuntimeError(f"child {args} failed (rc {proc.returncode}): {proc.stderr[-2000:]}")


PAL_PARK_MAP = 109
ENC_BANK_GETTER_109 = 0x0203A7D6   # 'pop {r4, pc}' of the map-109 branch of the encounter-bank getter 0x0203A7B0
CODE_SIG[ENC_BANK_GETTER_109] = "10bd"


def cmd_palpark(a):
    """D-1484: for each pinned weekday, log the encounter record the bank getter returns on map 109
    (hook on its map-109 return), plus optional encounters."""
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = datetime.date(2026, 10, 4)           # a Sunday
    names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    if a.day is None:                  # parent: one child process per day (DeSmuME can't be reopened)
        report = {"rom": str(a.rom), "days": [run_child(["palpark", "--rom", a.rom, "--sav", a.sav,
                  "--out", a.out, "--x", str(a.x), "--y", str(a.y), "--count", str(a.count),
                  "--max-steps", str(a.max_steps), "--day", str(wd)]) for wd in range(7)]}
        for d in report["days"]:
            print(json.dumps(d))
        js = out / ("palpark_weekdays.json" if a.count == 0 else "palpark_weekdays_encounters.json")
        js.write_text(json.dumps(report, indent=1))
        print("report:", js)
        return 0
    for wd in [a.day]:
        when = datetime.datetime.combine(base + datetime.timedelta(days=wd), datetime.time(12, 0))
        seen = []

        def hooks(h):
            h.on_exec(ENC_BANK_GETTER_109, lambda h: seen.append(h.reg.r0))
        with start_at(PAL_PARK_MAP, a.x, a.y, rom=a.rom, sav=a.sav, clock=when, out=out, verbose=False,
                      hooks=hooks) as h:
            log = WildLog(h)
            steps = 0
            while len(log.rows) < a.count and steps < a.max_steps:
                for d in ("LEFT", "RIGHT"):
                    for _ in range(3):
                        h.walk(d, 1)
                        steps += 1
                if log.rows and not log.rows[-1].get("fled"):
                    if len(log.rows) == 1:
                        h.step(300)
                        h.screenshot(f"palpark_{names[wd]}_encounter")
                    for r in log.rows:
                        r.setdefault("fled", True)
                    if not h.flee():
                        raise RuntimeError("could not flee")
            h.walk("LEFT", 2)
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("palpark", help="D-1484: encounter record of map 109 per pinned weekday")
    pp.add_argument("--rom", default=str(DEF_ROM_CN))
    pp.add_argument("--sav", default=str(DEF_SAVES / "full_bag_6mons.sav"))
    pp.add_argument("--out", default=str(DEF_OUT))
    pp.add_argument("--x", type=int, default=20)
    pp.add_argument("--y", type=int, default=14)
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
    a = ap.parse_args(argv)
    return {"info": cmd_info, "wild": cmd_wild, "unown": cmd_wild, "palpark": cmd_palpark, "arceus": cmd_arceus, "evolve": cmd_evolve, "screens": cmd_screens}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
