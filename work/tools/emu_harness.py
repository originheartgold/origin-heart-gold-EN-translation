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
RUN_BUTTON = (128, 178)        # bottom-screen RUN button of the battle command menu
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
        return decode_party_pokemon(self.read(party + 8 + 236 * count, 236))

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
    return {"info": cmd_info, "wild": cmd_wild, "unown": cmd_wild}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
