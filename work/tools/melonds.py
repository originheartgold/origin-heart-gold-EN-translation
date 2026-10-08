"""melonds - Python (ctypes) wrapper for libmelonds_shim, the headless melonDS 1.1 backend.

The shim (work/tools/melonds_shim/, GPLv3 like melonDS) is built by work/tools/melonds_shim/build.py from a
pinned melonDS 1.1 checkout; see work/notes/melonds_backend.md. This module only loads the built library.

    from melonds import MelonDS
    with MelonDS() as m:
        m.load_rom("game.nds", sav=Path("game.sav").read_bytes(), rtc=datetime.datetime(2026, 10, 9, 12))
        m.run(600)
        m.press("A")
        m.screenshot().save("shot.png")      # PIL image, 256x384, top screen above the bottom screen
        m.u32(0x021D11B4)

Library lookup: MELONDS_SHIM (path to the .dylib/.so), else <work>/build/melonds/libmelonds_shim.dylib.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

KEYS = ("A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L", "X", "Y")
KEY_BITS = {k: 1 << i for i, k in enumerate(KEYS)}
ABI_VERSION = 1
LIB_NAME = "libmelonds_shim.dylib" if sys.platform == "darwin" else "libmelonds_shim.so"
REGS = 31
MODE_ABORT = 0x17

_lib = None


def default_library():
    env = os.environ.get("MELONDS_SHIM")
    if env:
        return Path(env)
    work = Path(__file__).resolve().parent.parent
    return work / "build" / "melonds" / LIB_NAME


def available(path=None):
    return Path(path or default_library()).is_file()


def load_library(path=None):
    """Load (once) and type the shim. Raises FileNotFoundError when it is not built."""
    global _lib
    p = Path(path or default_library())
    if not p.is_file():
        raise FileNotFoundError(f"{p} not found: build it with python3 work/tools/melonds_shim/build.py")
    if _lib is not None:
        return _lib
    lib = ctypes.CDLL(str(p))
    vp, u32, i32, u8p = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.POINTER(ctypes.c_uint8)
    u32p = ctypes.POINTER(ctypes.c_uint32)
    sig = {
        "mds_abi_version": (i32, []),
        "mds_melonds_version": (ctypes.c_char_p, []),
        "mds_create": (vp, []),
        "mds_destroy": (None, [vp]),
        "mds_set_log_echo": (None, [vp, i32]),
        "mds_load_rom": (i32, [vp, ctypes.c_char_p, u8p, u32, i32]),
        "mds_reset": (None, [vp, i32]),
        "mds_set_rtc": (None, [vp, i32, i32, i32, i32, i32, i32]),
        "mds_run_frame": (u32, [vp]),
        "mds_frame": (u32, [vp]),
        "mds_stopped": (i32, [vp]),
        "mds_set_keys": (None, [vp, u32]),
        "mds_touch": (None, [vp, i32, i32]),
        "mds_release_touch": (None, [vp]),
        "mds_screenshot_rgb": (i32, [vp, u8p]),
        "mds_read": (None, [vp, u32, u8p, u32]),
        "mds_write": (None, [vp, u32, u8p, u32]),
        "mds_read_main_ram": (None, [vp, u32, u8p, u32]),
        "mds_write_main_ram": (None, [vp, u32, u8p, u32]),
        "mds_cpu_regs": (None, [vp, i32, u32p]),
        "mds_set_cpu_reg": (None, [vp, i32, i32, u32]),
        "mds_exceptions": (None, [vp, u32p]),
        "mds_clear_exceptions": (None, [vp]),
        "mds_log_drain": (u32, [vp, ctypes.c_char_p, u32]),
        "mds_watch_add": (i32, [vp, u32, u32, u32]),
        "mds_watch_clear": (None, [vp]),
        "mds_watch_capacity": (None, [vp, u32]),
        "mds_watch_hits": (u32, [vp, u32p, u32, u32p]),
        "mds_savestate_save": (u32, [vp]),
        "mds_savestate_copy": (u32, [vp, u8p, u32]),
        "mds_savestate_load": (i32, [vp, u8p, u32]),
        "mds_save_length": (u32, [vp]),
        "mds_save_read": (u32, [vp, u8p, u32]),
        "mds_save_write": (None, [vp, u8p, u32]),
    }
    for name, (res, args) in sig.items():
        fn = getattr(lib, name)
        fn.restype = res
        fn.argtypes = args
    if lib.mds_abi_version() != ABI_VERSION:
        raise RuntimeError(f"{p}: shim ABI {lib.mds_abi_version()}, this wrapper needs {ABI_VERSION}: rebuild it")
    _lib = lib
    return lib


def _buf(data):
    data = bytes(data)
    return (ctypes.c_uint8 * max(1, len(data))).from_buffer_copy(data or b"\0"), len(data)


class MelonDS:
    """One melonDS console. Several may live in one process (unlike py-desmume). Not thread-safe: use each console
    from one thread only (the shim keeps per-call state for the core's log callback in a thread-local)."""

    def __init__(self, library=None, log_echo=False):
        self.lib = load_library(library)
        self.h = self.lib.mds_create()
        if not self.h:
            raise RuntimeError("mds_create failed")
        self.lib.mds_set_log_echo(self.h, 1 if log_echo else 0)
        self._keys = 0
        self.direct_boot = True

    # ---------------------------------------------------------------- lifecycle
    @property
    def _h(self):
        if not self.h:
            raise RuntimeError("this MelonDS console is closed")
        return self.h

    def close(self):
        if self.h:
            self.lib.mds_destroy(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def load_rom(self, rom, sav=None, rtc=None, direct_boot=True):
        """Insert the ROM (a path) with an optional battery save (bytes) and boot. rtc: a datetime for the
        console clock, which then advances with emulated time only (runs are repeatable)."""
        b, n = _buf(sav or b"")
        if not self.lib.mds_load_rom(self._h, str(Path(rom)).encode(), b if sav else None, n if sav else 0,
                                     1 if direct_boot else 0):
            raise RuntimeError(f"melonDS could not load {rom}")
        self.direct_boot = direct_boot
        if rtc is not None:
            self.set_rtc(rtc)

    def reset(self):
        self.lib.mds_reset(self._h, 1 if self.direct_boot else 0)

    def set_rtc(self, when):
        self.lib.mds_set_rtc(self._h, when.year, when.month, when.day, when.hour, when.minute, when.second)

    # ---------------------------------------------------------------- running and input
    @property
    def frame(self):
        return self.lib.mds_frame(self._h)

    def run(self, frames=1):
        for _ in range(frames):
            self.lib.mds_run_frame(self._h)

    def stopped(self):
        """0 while running, else 1 + melonDS's Platform::StopReason."""
        return self.lib.mds_stopped(self._h)

    @property
    def keys(self):
        return {k for k, bit in KEY_BITS.items() if self._keys & bit}

    def set_keys(self, keys):
        self._keys = 0
        for k in keys:
            self._keys |= KEY_BITS[k]
        self.lib.mds_set_keys(self._h, self._keys)

    def hold(self, *keys):
        self.set_keys(self.keys | set(keys))

    def release(self, *keys):
        self.set_keys(self.keys - set(keys) if keys else set())

    def press(self, key, frames=6, after=0):
        self.hold(key)
        self.run(frames)
        self.release(key)
        self.run(after)

    def touch(self, x, y):
        self.lib.mds_touch(self._h, x, y)

    def release_touch(self):
        self.lib.mds_release_touch(self._h)

    # ---------------------------------------------------------------- screen
    def screen_rgb(self):
        """Raw 256x384 RGB bytes (top screen rows first)."""
        out = (ctypes.c_uint8 * (256 * 384 * 3))()
        self.lib.mds_screenshot_rgb(self._h, out)
        return bytes(out)

    def screenshot(self):
        from PIL import Image
        return Image.frombytes("RGB", (256, 384), self.screen_rgb())

    # ---------------------------------------------------------------- memory
    def read(self, addr, n):
        """Bytes as the ARM9 sees them: ITCM, DTCM, then the bus (main RAM, WRAM, VRAM, ...). Reading I/O
        registers goes through the core's register reads, which may have side effects."""
        out = (ctypes.c_uint8 * max(1, n))()
        self.lib.mds_read(self._h, addr, out, n)
        return bytes(out[:n])

    def write(self, addr, data):
        b, n = _buf(data)
        self.lib.mds_write(self._h, addr, b, n)

    def read_main_ram(self, offset, n):
        out = (ctypes.c_uint8 * max(1, n))()
        self.lib.mds_read_main_ram(self._h, offset, out, n)
        return bytes(out[:n])

    def write_main_ram(self, offset, data):
        b, n = _buf(data)
        self.lib.mds_write_main_ram(self._h, offset, b, n)

    def u8(self, a):
        return self.read(a, 1)[0]

    def u16(self, a):
        return int.from_bytes(self.read(a, 2), "little")

    def u32(self, a):
        return int.from_bytes(self.read(a, 4), "little")

    def w8(self, a, v):
        self.write(a, bytes([v & 0xFF]))

    def w16(self, a, v):
        self.write(a, (v & 0xFFFF).to_bytes(2, "little"))

    def w32(self, a, v):
        self.write(a, (v & 0xFFFFFFFF).to_bytes(4, "little"))

    # ---------------------------------------------------------------- CPU state
    def regs(self, cpu=9):
        """dict: r (R0-R15), cpsr, mode, thumb, abt/svc/irq/und banked (sp, lr, spsr), cur_instr, halted.
        Between frames R15 is the next instruction + 8 (ARM) / + 4 (Thumb)."""
        out = (ctypes.c_uint32 * REGS)()
        self.lib.mds_cpu_regs(self._h, 0 if cpu == 9 else 1, out)
        v = list(out)
        return {"r": v[:16], "cpsr": v[16], "mode": v[16] & 0x1F, "thumb": bool(v[16] & 0x20),
                "abt": v[17:20], "svc": v[20:23], "irq": v[23:26], "und": v[26:29],
                "cur_instr": v[29], "halted": v[30]}

    def set_reg(self, reg, value, cpu=9):
        self.lib.mds_set_cpu_reg(self._h, 0 if cpu == 9 else 1, reg, value)

    def exceptions(self):
        """ARM9 exceptions the core logged since boot (or clear_exceptions), and battery save writes."""
        out = (ctypes.c_uint32 * 10)()
        self.lib.mds_exceptions(self._h, out)
        v = list(out)
        return {"data_aborts": v[0], "first_data_abort_r15": v[1], "first_data_abort_frame": v[2],
                "last_data_abort_r15": v[3], "prefetch_aborts": v[4], "first_prefetch_abort_r15": v[5],
                "undefined": v[6], "first_undefined_addr": v[7], "save_writes": v[8],
                "last_save_write_frame": v[9]}

    def clear_exceptions(self):
        self.lib.mds_clear_exceptions(self._h)

    def in_abort_mode(self):
        return self.regs()["mode"] == MODE_ABORT

    def log_lines(self):
        """Core log lines since the last call (at most the last 256 are kept)."""
        lines = []
        buf = ctypes.create_string_buffer(65536)
        while True:
            n = self.lib.mds_log_drain(self._h, buf, len(buf))
            if not n:
                return lines
            lines += buf.raw[:n].decode("utf-8", "replace").splitlines()

    # ---------------------------------------------------------------- watchpoints
    def watch(self, start, length, read=False, write=True):
        """Record ARM9 bus accesses (CPU loads/stores outside the TCMs, ARM9 DMA) touching [start, start+length)."""
        kinds = (1 if read else 0) | (2 if write else 0)
        if not self.lib.mds_watch_add(self._h, start, length, kinds):
            raise ValueError("watch needs a length and read and/or write")

    def clear_watches(self):
        self.lib.mds_watch_clear(self._h)

    def watch_hits(self, max_hits=4096):
        """Hits since the last call: dicts addr, size, value, write, pc (instruction address), thumb, frame.
        The list's .dropped attribute counts hits lost to the shim's buffer (default 4096)."""
        out = (ctypes.c_uint32 * (8 * max_hits))()
        dropped = ctypes.c_uint32(0)
        n = self.lib.mds_watch_hits(self._h, out, max_hits, ctypes.byref(dropped))
        hits = _Hits()
        for i in range(n):
            addr, size, value, wr, r15, cpsr, frame, _ = out[8 * i:8 * i + 8]
            thumb = bool(cpsr & 0x20)
            hits.append({"addr": addr, "size": size, "value": value, "write": bool(wr),
                         "pc": (r15 - (4 if thumb else 8)) & 0xFFFFFFFF, "thumb": thumb, "frame": frame})
        hits.dropped = dropped.value
        return hits

    # ---------------------------------------------------------------- savestates and battery
    def save_state(self):
        n = self.lib.mds_savestate_save(self._h)
        if not n:
            raise RuntimeError("melonDS savestate failed")
        out = (ctypes.c_uint8 * n)()
        self.lib.mds_savestate_copy(self._h, out, n)
        return bytes(out)

    def load_state(self, data):
        b, n = _buf(data)
        if not self.lib.mds_savestate_load(self._h, b, n):
            raise RuntimeError("melonDS could not load the savestate (other version or ROM?)")

    def save_state_file(self, path):
        Path(path).write_bytes(self.save_state())

    def load_state_file(self, path):
        self.load_state(Path(path).read_bytes())

    def battery(self):
        n = self.lib.mds_save_length(self._h)
        out = (ctypes.c_uint8 * max(1, n))()
        got = self.lib.mds_save_read(self._h, out, n)
        return bytes(out[:got])

    def set_battery(self, data):
        b, n = _buf(data)
        self.lib.mds_save_write(self._h, b, n)


class _Hits(list):
    dropped = 0
