#!/usr/bin/env python3
"""memcheck - find screens where the English text runs a heap out of memory (crash class seen in rc3).

The hack's code comes from the Japanese HeartGold and its screens get fixed-size heaps. Many screens load
whole message banks into their heap (NewMsgDataFromNarc type 0). The English banks are 1.5-3x the size of the
Chinese ones, so a screen that had a few KB to spare in Chinese can run out: an allocation returns NULL, the
next file read goes to address 0 (the ITCM mirror), the IRQ handler is overwritten and the game crashes
(melonDS) or hangs (DeSmuME). rc3 example: summary screen, skills page, switch Pokemon (heap 19 loads banks
0295 + 0739; the 6448-byte a/1/1/4 #259 no longer fits).

Needs a venv with py-desmume and capstone (see emu_smoke.py):
    python3 -m venv <venv> && <venv>/bin/pip install py-desmume capstone ndspy pillow

    <venv>/bin/python work/tools/memcheck.py static [--rom EN.nds] [--ref CN.nds] [--json OUT]
        every call site in our build that still loads a whole a/0/2/7 bank into a heap (code in arm9 and all
        overlays), with the bank's Chinese and English size. Biggest growth first. Empty with the global fix.

    <venv>/bin/python work/tools/memcheck.py run [--saves DIR] [--rom EN.nds] [--ref CN.nds]
        [--scenario NAME[,NAME..]|all] [--out DIR] [--json OUT] [--warn BYTES]
        plays each scenario (memcheck_scenarios.json) on both ROMs from its battery save ("sav", a file name in
        --saves, default work/build/memcheck/; missing saves make the run incomplete) and hooks the
        game's allocator (AllocFromHeapInternal). For every heap it records the smallest spare room seen at
        any allocation: largest free block minus the request. Reports per scenario and heap:
          FAIL   an allocation failed (NULL), something wrote to address 0-0x3F (crash), or a heap's block
                 list is corrupted (checked every 30 frames from frame 600; e.g. text drawn past the bottom
                 of its window)
          WARN   English spare room < --warn bytes (default 4096) and more than 256 bytes below Chinese
        plus a prediction from the static list: whole-bank loads on a measured heap whose English growth
        exceeds the Chinese spare room. Screenshots of each scenario's end go to --out.
        Exit 1 for English-only failure signatures; 2 for incomplete execution. Chinese findings
        are reported separately. Negative estimated spare room is a warning, not proof of failure.
        Each emulator child has a finite --timeout (default 120 seconds).

The save must be a raw 512 KB battery save (.sav, as melonDS writes). Keep saves out of git (*.sav is
ignored). Scenario scripts use emu_smoke.py's commands (wait, press, mash, touch, shot) plus 'boot'
(title screen -> Continue -> field). DeSmuME's clock is the real time, so overworld encounters are not
repeatable; scenarios stay in menus.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib
import importlib.metadata
from datetime import datetime, timezone
import math
import re
import time
import json
import os
import shutil
import struct
import sys
import subprocess
import tempfile
from pathlib import Path
import runtime_reproducibility as reproducibility
import runtime_rendering as rendering

# No sound from any emulator this process starts: SDL's dummy audio driver opens no output device
# (the emulated sound chip still runs, so game timing is unchanged).
os.environ["SDL_AUDIODRIVER"] = "dummy"

WORK = Path(__file__).resolve().parent.parent
DEF_ROM = WORK / "build" / "origin_hg_v4.0.3_en_wip.nds"
DEF_REF = WORK / "rom" / "origin_v4.0.3_cn.nds"
SCENARIOS = Path(__file__).resolve().parent / "memcheck_scenarios.json"

MSG_NARC = 27                 # a/0/2/7
NEW_MSGDATA = 0x0200BA98      # NewMsgDataFromNarc(type, narc, bank, heap); type 0 = whole bank into the heap
LOAD_WHOLE = 0x0200B5B0       # LoadSingleElementFromNarc(narc, member, heap) used by type 0
ALLOC = 0x0201B258            # AllocFromHeapInternal(expHeap, size, align, heapId); adds a 16-byte header
ALLOC_RET = 0x0201B284        # 'cmp r4, #0' right after NNS_FndAllocFromExpHeapEx: r4 = block or NULL
# Code bytes the hooks rely on (hack arm9, identical in our build); checked before every run.
CODE_SIG = {ALLOC: "F8B5 051C 0C1C 171C 1E1C 002D", ALLOC_RET: "002C 07D0", 0x0201B338: "0C05 1D02", NEW_MSGDATA: ["F8B5 051C 0E1C 181C", "F8B5 0125 0E1C 181C"]}  # 2nd: global on-demand fix
STRING_COPY = 0x02026EB8
COPY_GUARD = 0x02026ED4
ITEM_DESCRIPTION = 0x020763EC
ITEM_DESCRIPTION_RETURN = 0x02076408
CODE_SIG[STRING_COPY] = "F8B5 051C 0F1C 141C"
CODE_SIG[COPY_GUARD] = "2888 8442 19D8"
CODE_SIG[ITEM_DESCRIPTION] = "70B5 051C 0C1C 131C"
CODE_SIG[ITEM_DESCRIPTION_RETURN] = "301C"
# Party layout verified from the Chinese hack: SaveArrayGet(2), count +4,
# slots +8 with 236-byte stride; PID is the unencrypted first word.
PARTY_GET_RETURN = 0x0202775C
CODE_SIG[0x2027740] = "38b50c1c051c2a2c01dbfef7eff92001291803482a1c08581032101838bdc0461ce00200"
CODE_SIG[0x207365c] = "014b02211847c04641770202"
CODE_SIG[0x2073398] = "4068704738b5051c0c1c01d5b2f7c2fb6868844201dbb2f7bdfb2868844201dbb2f7b8fbec2008356043281838bd"
SUMMARY_ENTER = 0x020899BC
FREE_TO_HEAP = 0x0201B33C
CODE_SIG[FREE_TO_HEAP] = "f8b5061c301f00680006040e1848818a8c4229d2"
SUMMARY_RETURN = 0x020899EA
CODE_SIG[0x02089910] = "8f2080002958c87c844202db0020c043f8bd0868211ce9f739fd"
CODE_SIG[0x020899BC] = "10b58f2189004458607c002804d0012809d002280cd012e0e6f71cfb217d22684843101810bd217d2068e9f7d9fc10bde6f712fb217d22684843101810bd002010bd"

# Stored move decoder: native crypto, checksum, logical block table and move getter.
CODE_SIG[0x2020680] = "0fb4f8b5051c00244e080ad008af381c00f010f82988641c48402880ad1cb442f5d3f8bc08bc04b018470000004b18478106020202680549131c4b43044959180160080c0004000c7047c0466d4ec64173600000"
CODE_SIG[0x206d948] = "70b5051ca8880c1c161c8007c00f15d1ea88281c0830802103f080ff281c0830802103f07fffe988884207d0884201d0b8f7d8f8a98804200843a880281c211c321c"
CODE_SIG[0x207186c] = "18b400231a1c4c0807d00188521c801c591809040b0ca242f7d3181c18bc704770b5051c3e200c1c00032040161c440b032e01d9b4f744f90348a1004018305c0835281870bdc04663e90f02"
CODE_SIG[0x206d9a8] = "f0b583b00191011c0024029209680090221c03f067ff061c00980122011c096803f060ff051c0098"
CODE_SIG[0x206da6a] = "9402940294029402"
CODE_SIG[0x206dc94] = "01983638019040002c5a61e1"
CODE_SIG[0x20fe963] = "0020406000206040004020600060204000406020006040202000406020006040400020606000204040006020600040202040006020600040402000606020004040600020604000202040600020604000402060006020400040602000604020000020406000206040004020600060204000406020006040202000406020006040"
MOVE_BLOCK_OFFSETS = (32, 32, 64, 96, 64, 96, 0, 0, 0, 0, 0, 0, 64, 96, 32, 32, 96, 64, 64, 96, 32, 32, 96, 64, 32, 32, 64, 96, 64, 96, 0, 0)
FREE_SIG = 0x4652             # NNS expanded-heap free block 'FR'
HEAP_INFO = 0x021D050C        # sHeapInfo: +0 heap handles, +0x10 u8 index per heap id, +0x14 u16 heap count
RAM = (0x02000000, 0x02400000)


# ----------------------------------------------------------------------------- static

def _blobs(rom):
    arm9 = rom.loadArm9()
    out = [("arm9", arm9.sections[0].ramAddress, arm9.sections[0].data)]
    for i, o in rom.loadArm9Overlays().items():
        out.append((f"ov{i}", o.ramAddress, o.data))
    return out


def _bl_target(d, off, base):
    h1, h2 = struct.unpack_from("<HH", d, off)
    if (h1 & 0xF800) == 0xF000 and (h2 & 0xF800) in (0xF800, 0xE800):
        o = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
        if o & 0x400000:
            o -= 0x800000
        t = base + off + 4 + o
        return t & ~3 if (h2 & 0xF800) == 0xE800 else t
    return None


def _resolve_args(md, d, base, off):
    """Constant r0-r3 at a Thumb BL, by straight-line tracking from up to 24 instructions back."""
    from capstone import arm
    ins = None
    for back in range(48, 0, -2):
        if off - back < 0:
            continue
        cand = list(md.disasm(d[off - back:off + 4], base + off - back))
        if cand and cand[-1].address == base + off and cand[-1].mnemonic in ("bl", "blx"):
            ins = cand
            break
    if not ins:
        return [None] * 4
    regs = {}

    def reg(op, i):
        n = i.reg_name(op.reg)
        return int(n[1:]) if n and n[0] == "r" and n[1:].isdigit() else None

    for i in ins[:-1]:
        ops = i.operands
        if i.mnemonic in ("bl", "blx"):
            for k in range(4):
                regs.pop(k, None)
            continue
        if not ops or ops[0].type != arm.ARM_OP_REG or i.mnemonic.startswith(("str", "cmp", "tst", "push")):
            continue
        rd = reg(ops[0], i)
        if rd is None:
            continue
        v = None
        m = i.mnemonic
        if m in ("movs", "mov") and len(ops) == 2:
            if ops[1].type == arm.ARM_OP_IMM:
                v = ops[1].imm
            elif ops[1].type == arm.ARM_OP_REG:
                v = regs.get(reg(ops[1], i))
        elif m in ("adds", "add") and len(ops) == 3 and ops[1].type == arm.ARM_OP_REG and ops[2].type == arm.ARM_OP_IMM:
            b = regs.get(reg(ops[1], i))
            v = None if b is None else b + ops[2].imm
        elif m in ("adds", "add") and len(ops) == 2 and ops[1].type == arm.ARM_OP_IMM:
            b = regs.get(rd)
            v = None if b is None else b + ops[1].imm
        elif m == "lsls" and len(ops) == 3 and ops[2].type == arm.ARM_OP_IMM:
            b = regs.get(reg(ops[1], i))
            v = None if b is None else (b << ops[2].imm) & 0xFFFFFFFF
        elif m == "ldr" and len(ops) == 2 and ops[1].type == arm.ARM_OP_MEM and i.reg_name(ops[1].mem.base) == "pc":
            o = ((i.address + 4) & ~3) + ops[1].mem.disp - base
            if 0 <= o <= len(d) - 4:
                v = struct.unpack_from("<I", d, o)[0]
        if v is None:
            regs.pop(rd, None)
        else:
            regs[rd] = v
    return [regs.get(k) for k in range(4)]


def bank_sizes(path):
    import ndspy.narc
    import ndspy.rom
    n = ndspy.narc.NARC(ndspy.rom.NintendoDSRom.fromFile(path).getFileByName("a/0/2/7"))
    return [len(f) for f in n.files]


def static_loads(rom_path, ref_path):
    """Whole-bank loads left in our build's code (call sites patched to type 1 drop out), with both bank sizes.
    With the global fix (NewMsgDataFromNarc forces type 1) there are none."""
    import capstone
    import ndspy.rom
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    md.detail = True
    rom = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
    rows, unresolved = [], []
    if rom.loadArm9().sections[0].data[NEW_MSGDATA - 0x02000000 + 2:NEW_MSGDATA - 0x02000000 + 4] == bytes.fromhex("0125"):
        return rows, unresolved
    for name, base, d in _blobs(rom):
        for off in range(0, len(d) - 4, 2):
            t = _bl_target(d, off, base)
            if t not in (NEW_MSGDATA, LOAD_WHOLE) or NEW_MSGDATA <= base + off < NEW_MSGDATA + 0x4C:
                continue          # (the loader's own call to LOAD_WHOLE is not a call site)
            a = _resolve_args(md, d, base, off)
            if t == NEW_MSGDATA:
                typ, narc, bank, heap = a
            else:
                typ, (narc, bank, heap) = 0, a[:3]
            site = {"code": name, "addr": f"{base + off:08X}", "type": typ, "narc": narc, "bank": bank, "heap": heap}
            if narc == MSG_NARC and typ == 0 and bank is not None:
                rows.append(site)
            elif typ != 1 and narc in (MSG_NARC, None):
                unresolved.append(site)
    cn, en = bank_sizes(ref_path), bank_sizes(rom_path)
    for r in rows:
        r["cn"], r["en"] = cn[r["bank"]], en[r["bank"]]
        r["growth"] = r["en"] - r["cn"]
    rows.sort(key=lambda r: (-r["growth"], r["bank"], r["code"]))
    return rows, unresolved


def cmd_static(a):
    rows, unresolved = static_loads(a.rom, a.ref)
    banks = {}
    for r in rows:
        banks.setdefault(r["bank"], []).append(r)
    print(f"{len(rows)} whole-bank loads of {len(banks)} banks; English growth of those banks: "
          f"{sum(v[0]['growth'] for v in banks.values())} bytes")
    print(f"{'bank':>4}  {'zh':>6} -> {'en':>6}  {'growth':>7}  call sites (code@addr/heap)")
    for b, v in sorted(banks.items(), key=lambda kv: -kv[1][0]["growth"]):
        sites = " ".join(f"{r['code']}@{r['addr']}/h{r['heap']}" for r in v)
        print(f"{b:04d}  {v[0]['cn']:6d} -> {v[0]['en']:6d}  {v[0]['growth']:+7d}  {sites}")
    if unresolved:
        print(f"\n{len(unresolved)} possible whole-bank loads with a non-constant type, archive or bank "
              "(check by hand or with 'run'):")
        for r in unresolved:
            print(f"  {r['code']}@{r['addr']} type={r['type']} narc={r['narc']} bank={r['bank']} heap={r['heap']}")
    if a.json:
        Path(a.json).write_text(json.dumps({"loads": rows, "unresolved": unresolved}, indent=1))


# ----------------------------------------------------------------------------- run

class Probe:
    def __init__(self, emu):
        self.emu = emu
        self.mem = emu.memory.unsigned
        self.R = emu.memory.register_arm9
        self.minspare = {}       # heapId -> (spare, request, frame)
        self.fails = []          # (heapId, request, frame)
        self.nullw = []          # (pc, frame)
        self.corrupt = None      # (frame, message): first heap corruption seen by heap_walk
        self.frame = 0
        self.screenshots = []
        self.script_completed = False
        self.heap_checks = 0
        self.heap_table_errors = []
        self.message_loads = []
        self.checkpoints = {}
        self.text_copy_checks = 0
        self.text_rejections = []
        self.text_probe_errors = []
        self._item_contexts = []
        self.item_description_reads = []
        self.checkpoints["start"] = {"frame": 0, "message_loads": [], "item_description_reads": [], "screenshot": None}
        self.party_addresses = set()
        self.summary_screen = None
        self.summary_context = None
        self.summary_observed_frame = -1
        emu.memory.register_exec(SUMMARY_ENTER, self._on_summary_enter)
        emu.memory.register_exec(FREE_TO_HEAP, self._on_summary_free)
        emu.memory.register_exec(SUMMARY_RETURN, self._on_summary_return)
        emu.memory.register_exec(PARTY_GET_RETURN, self._on_save_array_return)
        self._pending = None
        self.armed = False       # the boot code itself writes to 0-0x3F; arm after 'boot'
        emu.memory.register_exec(ITEM_DESCRIPTION, self._on_item_description)
        emu.memory.register_exec(ITEM_DESCRIPTION_RETURN, self._on_item_description_return)
        emu.memory.register_exec(STRING_COPY, self._on_text_copy)
        emu.memory.register_exec(NEW_MSGDATA, self._on_message)
        emu.memory.register_exec(ALLOC, self._on_alloc)
        emu.memory.register_exec(ALLOC_RET, self._on_ret)
        for adr in range(0, 0x40, 4):
            emu.memory.register_write(adr, self._on_null, 4)

    def _on_save_array_return(self, addr, size):
        if self.R.r4 == 2:
            self.party_addresses.add(self.R.r0)

    def party_snapshot(self):
        if len(self.party_addresses) != 1:
            return {"status": "incomplete", "error": "Missing or ambiguous save-party pointer"}
        address = next(iter(self.party_addresses))
        return read_party_snapshot(self.mem, address)

    def move_snapshot(self):
        return dict(read_move_snapshot(self.mem, self.party_snapshot()), observed_frame=self.frame)

    def _on_summary_enter(self, addr, size):
        self.summary_screen = self.R.r0
        self.summary_context = None
        self.summary_observed_frame = -1

    def _on_summary_free(self, addr, size):
        if self.R.r0 in (self.summary_screen, self.summary_context):
            self.summary_screen = self.summary_context = None
            self.summary_observed_frame = -1

    def _on_summary_return(self, addr, size):
        self.summary_context = self.R.r4
        self.summary_observed_frame = self.frame

    def summary_snapshot(self):
        return read_summary_snapshot(self.mem, self.summary_context,
                                     self.summary_observed_frame, self.party_snapshot(), self.summary_screen)

    def _on_item_description(self, addr, size):
        self.item_description_reads.append({"item": self.R.r1, "heap": self.R.r2,
                                            "caller": self.R.lr, "frame": self.frame, "destination": self.R.r0})
        self._item_contexts.append({"destination": self.R.r0, "item": self.R.r1,
                                    "item_caller": self.R.lr})

    def _on_item_description_return(self, addr, size):
        if self._item_contexts:
            self._item_contexts.pop()
        else:
            self.text_probe_errors.append("Item-description return without entry")

    def _on_text_copy(self, addr, size):
        destination, units, caller = self.R.r0, self.R.r2, self.R.lr
        self.text_copy_checks += 1
        # This hook observes the native capacity guard; it does not modify the copy.
        if destination % 4 or not RAM[0] <= destination <= RAM[1] - 10:
            issue = "String-copy destination outside readable RAM"
            if issue not in self.text_probe_errors:
                self.text_probe_errors.append(issue)
            return
        capacity = self.mem.read_short(destination)
        if units > capacity:
            event = {"caller": caller, "units": units, "capacity": capacity,
                     "frame": self.frame, "destination": destination}
            if self._item_contexts and self._item_contexts[-1]["destination"] == destination:
                event.update({key: value for key, value in self._item_contexts[-1].items() if key != "destination"})
            self.text_rejections.append(event)

    def _on_message(self, addr, size):
        event = {"narc": self.R.r1, "bank": self.R.r2, "heap": self.R.r3,
                 "caller": self.R.lr, "frame": self.frame}
        if event not in self.message_loads:
            self.message_loads.append(event)

    def _largest_free(self, heap):
        rd = self.mem.read_long
        p, big, n = rd(heap + 0x24), 0, 0
        while p and n < 4096:
            if not RAM[0] <= p < RAM[1] or self.mem.read_short(p) != FREE_SIG:
                return None
            big = max(big, rd(p + 4))
            p = rd(p + 12)
            n += 1
        return big

    def _on_alloc(self, addr, size):
        R = self.R
        heap, req, align, hid = R.r0, R.r1 + 0x10, R.r2, R.r3 & 0xFF
        self._pending = (hid, req)
        if not heap:
            return
        big = self._largest_free(heap)
        if big is None:
            return
        # NNS takes a 16-byte block header and pads to the alignment
        spare = big - req - 0x10 - (abs(align) - 4 if abs(align) > 4 else 0)
        cur = self.minspare.get(hid)
        if cur is None or spare < cur[0]:
            self.minspare[hid] = (spare, req - 0x10, self.frame)

    def _on_ret(self, addr, size):
        if self._pending and self.R.r4 == 0:
            self.fails.append((self._pending[0], self._pending[1] - 0x10, self.frame))
        self._pending = None

    def heap_walk(self):
        """Walk every live NNS expanded heap (from the game's heap table): each used/free block must have its
        signature, lie inside its heap and link back to the previous block. Text drawn past the bottom of a
        window overwrites the block headers after its pixel buffer (rc3 Misty scene); this finds it before
        anything crashes. Only live heaps: a destroyed heap's header stays in RAM and would look corrupted."""
        lo, hi = RAM
        self.heap_checks += 1
        def readable(address, width):
            return lo <= address <= hi - width
        u32, u16, u8 = self.mem.read_long, self.mem.read_short, self.mem.read_byte
        def table_error(message):
            # The game has not initialized its heap table during early boot.
            if self.armed and message not in self.heap_table_errors:
                self.heap_table_errors.append(message)
            return None
        handles, idxs, count = u32(HEAP_INFO), u32(HEAP_INFO + 0x10), u16(HEAP_INFO + 0x14)
        if not readable(handles, 4) or not readable(idxs, max(count, 1)) or not 0 < count <= 1024:
            return table_error("invalid live heap table bounds/count")
        live = set()
        for hid in range(count):
            slot = handles + 4 * u8(idxs + hid)
            if not readable(slot, 4):
                return table_error(f"heap {hid}: handle slot outside RAM")
            h = u32(slot)
            if h == 0:
                continue
            if not readable(h, 0x30):
                return table_error(f"heap {hid}: heap handle outside RAM")
            if u32(h) == 0x45585048:
                live.add((hid, h))
        if not live:
            return table_error("no live expanded heaps found")
        for hid, h in sorted(live):
            st, en = u32(h + 0x18), u32(h + 0x1C)
            if not lo <= st < en <= hi:
                return f"heap {hid} ({h:08X}): bad bounds"
            for head, want, kind in ((0x24, FREE_SIG, "free"), (0x2C, 0x5544, "used")):
                p, prev, n, visited = u32(h + head), 0, 0, set()
                while p:
                    if p in visited:
                        return f"heap {hid} ({h:08X}): {kind} list has a cycle"
                    if n >= 8192:
                        return f"heap {hid} ({h:08X}): {kind} list exceeds block limit"
                    visited.add(p)
                    if not st <= p < en - 16 or not readable(p, 16) or u16(p) != want:
                        return f"heap {hid} ({h:08X}): {kind} block {n} at {p:08X} has a bad header"
                    if u32(p + 8) != prev:
                        return f"heap {hid} ({h:08X}): {kind} block at {p:08X} has a broken back link"
                    prev, p, n = p, u32(p + 12), n + 1
        return None

    def _on_null(self, addr, size):
        if self.armed and len(self.nullw) < 8:
            self.nullw.append((self.R.pc, self.frame))


def _check_code(path):
    import ndspy.rom
    d = ndspy.rom.NintendoDSRom.fromFile(str(path)).loadArm9().sections[0].data
    for adr, sigs in CODE_SIG.items():
        sigs = [sigs] if isinstance(sigs, str) else sigs
        wants = [bytes.fromhex(x.replace(" ", "")) for x in sigs]
        want = wants[0]
        got = d[adr - 0x02000000:adr - 0x02000000 + len(want)]
        if got not in wants:
            sys.exit(f"{path}: code at {adr:08X} is {got.hex()} (expected {want.hex()}); the allocator moved, "
                     "update memcheck.py")


def run_scenario(rom, sav, script, shots, tag):
    from desmume.controls import Keys, keymask
    from desmume.emulator import DeSmuME
    sav = os.path.abspath(sav)
    shots = os.path.abspath(shots) if shots else shots
    tmp = Path(tempfile.mkdtemp(prefix="memcheck_"))
    os.symlink(os.path.abspath(rom), tmp / "game.nds")
    cwd = os.getcwd()
    os.chdir(tmp)
    emu = None
    try:
        isolation = reproducibility.begin_worker(os.environ.get("XDG_CONFIG_HOME"))
        emu = DeSmuME()
        environment = reproducibility.worker_environment(emu, isolation)
        emu.open(str(tmp / "game.nds"))
        if not emu.backup.import_file(sav, 524288):
            sys.exit(f"could not import save {sav}")
        emu.reset()
        pr = Probe(emu)
        pr.environment = environment
        keys = {k[4:]: getattr(Keys, k) for k in dir(Keys) if k.startswith("KEY_")}

        def step(n):
            for _ in range(n):
                emu.cycle(with_joystick=False)
                pr.frame += 1
                if pr.frame % 600 == 0:
                    print("MEMCHECK " + json.dumps(probe_data(pr)), flush=True)
                if pr.frame >= 600 and pr.corrupt is None and pr.frame % 30 == 0:   # not gated on 'boot'
                    bad = pr.heap_walk()
                    if bad:
                        pr.corrupt = (pr.frame, bad)

        def press(k, n=6):
            emu.input.keypad_add_key(keymask(keys[k]))
            step(n)
            emu.input.keypad_rm_key(keymask(keys[k]))

        for cmd in [c.strip() for c in script.split(";") if c.strip()]:
            p = cmd.split()
            if p[0] == "boot":      # title -> Continue -> field (the hack's notice pages only show without a save)
                step(2400); press("START"); step(400)
                for _ in range(4):
                    press("A"); step(300)
                step(600)
                pr.armed = True
                pr.checkpoints["boot"] = {"frame": pr.frame, "message_loads": list(pr.message_loads), "item_description_reads": list(pr.item_description_reads), "screenshot": None, "party": pr.party_snapshot(), "summary": pr.summary_snapshot(), "moves": pr.move_snapshot()}
            elif p[0] == "wait":
                step(int(p[1]))
            elif p[0] == "press":
                press(p[1].upper(), int(p[2]) if len(p) > 2 else 6)
            elif p[0] == "mash":
                for _ in range(int(p[2])):
                    press(p[1].upper()); step(int(p[3]))
            elif p[0] == "touch":
                emu.input.touch_set_pos(int(p[1]), int(p[2]))
                step(int(p[3]) if len(p) > 3 else 8)
                emu.input.touch_release()
            elif p[0] == "shot":
                if shots:
                    checkpoint = Path(shots) / f"{tag}_{p[1]}.png"
                    emu.screenshot().save(checkpoint)
                    pr.screenshots.append(str(checkpoint))
                    pr.checkpoints[p[1]] = {"frame": pr.frame, "message_loads": list(pr.message_loads),
                                           "item_description_reads": list(pr.item_description_reads),
                                           "screenshot": str(checkpoint), "screenshot_captured": checkpoint.is_file(),
                                           "party": pr.party_snapshot(), "summary": pr.summary_snapshot(), "moves": pr.move_snapshot()}
            else:
                sys.exit(f"unknown command {cmd!r}")
            if pr.nullw:
                break
        else:
            pr.script_completed = True
        return pr
    finally:
        try:
            if emu is not None:
                emu.destroy()
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp, ignore_errors=True)


def probe_data(pr):
    return {"minspare": pr.minspare, "fails": pr.fails, "nullw": pr.nullw,
            "corrupt": pr.corrupt, "frames": pr.frame, "armed": pr.armed,
            "screenshots": pr.screenshots, "script_completed": pr.script_completed, "heap_checks": pr.heap_checks,
            "heap_table_errors": pr.heap_table_errors, "message_loads": pr.message_loads, "checkpoints": pr.checkpoints, "text_copy_checks": pr.text_copy_checks,
            "text_rejections": pr.text_rejections, "text_probe_errors": pr.text_probe_errors,
            "item_description_reads": pr.item_description_reads,
            "environment": getattr(pr, "environment", None)}


def read_party_snapshot(mem, address):
    """Read only bounded slot identities, never decrypt or modify Pokemon data."""
    result = {"status": "incomplete", "address": address}
    if type(address) is not int or address % 4 or not RAM[0] <= address <= RAM[1] - (8 + 6 * 236):
        return dict(result, error="Party pointer outside bounded aligned RAM")
    try:
        capacity, count = mem.read_long(address), mem.read_long(address + 4)
        if capacity != 6 or not 1 <= count <= capacity:
            return dict(result, error="Invalid party capacity/count")
        identities = [mem.read_long(address + 8 + 236 * i) for i in range(count)]
        if len(set(identities)) != count:
            return dict(result, error="Duplicate party identities are ambiguous")
        return dict(result, status="passed", count=count, identities=identities)
    except Exception as exc:
        return dict(result, error=f"Party read unavailable: {exc}")


def decode_stored_moves(blob):
    """Decrypt a Python copy only; reject native open/decrypted or bad-egg flags."""
    if not isinstance(blob, bytes) or len(blob) != 136:
        raise ValueError("Expected 136-byte boxed Pokemon copy")
    identity, flags, checksum = struct.unpack_from("<IHH", blob)
    if flags != 0:
        raise ValueError("Pokemon data is open, corrupt or has unknown flags")
    seed = checksum
    words = []
    for word in struct.unpack_from("<64H", blob, 8):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        words.append(word ^ (seed >> 16))
    if sum(words) & 0xFFFF != checksum:
        raise ValueError("Pokemon checksum mismatch")
    offset = MOVE_BLOCK_OFFSETS[(identity >> 13) & 31] // 2
    return {"identity": identity, "checksum": checksum, "moves": words[offset:offset+4]}


def read_move_snapshot(mem, party):
    party = party if isinstance(party, dict) else {}
    address, count, ids = party.get("address"), party.get("count"), party.get("identities")
    result = {"status": "incomplete", "party_address": address, "slots": []}
    if (party.get("status") != "passed" or party.get("error") or
            type(address) is not int or address % 4 or not RAM[0] <= address <= RAM[1] - (8 + 6 * 236) or
            type(count) is not int or not 1 <= count <= 6 or not isinstance(ids, list) or len(ids) != count or
            any(type(i) is not int or not 0 <= i <= 0xFFFFFFFF for i in ids) or len(set(ids)) != count):
        return dict(result, error="Missing bounded party owner")
    try:
        for slot, identity in enumerate(party["identities"]):
            address = party["address"] + 8 + 236 * slot
            blob = bytes(mem.read_byte(address + i) for i in range(136))
            result["pending_slot"] = {"slot": slot, "address": address, "boxed_hex": blob.hex()}
            decoded = decode_stored_moves(blob)
            if decoded["identity"] != identity:
                raise ValueError("Pokemon identity changed during copy")
            result["slots"].append(dict(decoded, slot=slot, address=address, boxed_hex=blob.hex()))
        result.pop("pending_slot", None)
        return dict(result, status="passed")
    except Exception as exc:
        return dict(result, error=f"Stored move read unavailable: {exc}")


def move_state_evidence(scenario, raw):
    gaps, mismatches = [], []
    observations = raw.get("checkpoints", {})
    observations = observations if isinstance(observations, dict) else {}
    for name, expected in scenario.get("expected_move_order", {}).items():
        pair = [observations.get(key, {}) for key in (expected["relative_to"], name)]
        decoded_pair = []
        try:
            for checkpoint in pair:
                party, state = checkpoint["party"], checkpoint["moves"]
                address, ids = party["address"], party["identities"]
                if (party["status"] != "passed" or state["status"] != "passed" or
                        party.get("error") or state.get("error") or type(address) is not int or address % 4 or
                        not RAM[0] <= address <= RAM[1] - (8 + 6 * 236) or
                        type(party["count"]) is not int or party["count"] != scenario["party_size"] or
                        not isinstance(ids, list) or len(ids) != party["count"] or len(set(ids)) != len(ids) or
                        any(type(i) is not int or not 0 <= i <= 0xFFFFFFFF for i in ids) or
                        type(state["party_address"]) is not int or state["party_address"] != address or
                        not isinstance(state["slots"], list) or len(state["slots"]) != len(ids) or
                        type(state["observed_frame"]) is not int or state["observed_frame"] != checkpoint["frame"] or
                        type(checkpoint["frame"]) is not int or checkpoint["frame"] < 0):
                    raise ValueError("Invalid move owner or checkpoint")
                for slot, saved in enumerate(state["slots"]):
                    if (not isinstance(saved["boxed_hex"], str) or len(saved["boxed_hex"]) != 272 or
                            any(type(saved[k]) is not int for k in ("slot", "address", "identity", "checksum")) or
                            not isinstance(saved["moves"], list) or len(saved["moves"]) != 4 or
                            any(type(i) is not int for i in saved["moves"])):
                        raise ValueError("Invalid stored move payload fields")
                    decoded = decode_stored_moves(bytes.fromhex(saved["boxed_hex"]))
                    if (saved["slot"] != slot or saved["address"] != address + 8 + 236 * slot or
                            decoded["identity"] != ids[slot] or any(saved[k] != v for k, v in decoded.items())):
                        raise ValueError("Move payload disagrees with owner or decoded evidence")
                decoded_pair.append(state["slots"][expected["slot"]])
            if pair[0]["frame"] >= pair[1]["frame"]:
                raise ValueError("Stale move checkpoint interval")
            a, b = decoded_pair
            if expected.get("summary_closed"):
                previous, current = pair[0]["summary"], pair[1]["summary"]
                if (previous.get("status") != "passed" or previous.get("identity") != a["identity"] or
                        previous.get("address") != a["address"] or current.get("status") != "incomplete" or
                        "context_address" not in current or current["context_address"] is not None or
                        "screen_address" not in current or current["screen_address"] is not None or
                        type(current.get("observed_frame")) is not int or current["observed_frame"] != -1):
                    raise ValueError("Summary teardown is not proven")
            if pair[0]["party"]["identities"] != pair[1]["party"]["identities"] or a["identity"] != b["identity"] or a["address"] != b["address"]:
                raise ValueError("Move checkpoints refer to different Pokemon")
            if not a["moves"][0] or not a["moves"][1] or a["moves"][0] == a["moves"][1]:
                raise ValueError("First two move slots cannot prove a real swap")
            wanted = [a["moves"][i] for i in expected["order"]]
            if wanted == a["moves"]:
                raise ValueError("Expected move order does not prove a real change")
            if (b["moves"] != wanted or
                    any(left["moves"] != right["moves"] for slot, (left, right) in
                        enumerate(zip(pair[0]["moves"]["slots"], pair[1]["moves"]["slots"]))
                        if slot != expected["slot"])):
                mismatches.append(name)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            gaps.append(f"{name}: missing, stale or invalid stored move evidence: {exc}")
    return {"gaps": gaps, "mismatches": mismatches}


def compare_move_runs(scenario, zh, en):
    if not scenario.get("expected_move_order"):
        return "not_configured", [], {}
    evidence = {tag: move_state_evidence(scenario, raw) for tag, raw in (("zh", zh), ("en", en))}
    z, e = (set(evidence[tag]["mismatches"]) for tag in ("zh", "en"))
    findings = []
    for category, names in (("baseline_shared", z & e), ("baseline_chinese", z - e),
                             ("english_regression" if not evidence["zh"]["gaps"] else "unverified", e - z)):
        findings.extend({"category": category, "kind": "move_order", "checkpoint": name} for name in sorted(names))
    status = ("failed" if any(f["category"] == "english_regression" for f in findings) else
              "incomplete" if z or e or any(v["gaps"] for v in evidence.values()) else "passed")
    return status, findings, evidence


def read_summary_snapshot(mem, context, observed_frame, party, screen):
    """Read the party-mode summary resolver's live context, without writing RAM."""
    result = {"status": "incomplete", "context_address": context, "observed_frame": observed_frame, "screen_address": screen}
    if type(context) is not int or context % 4 or not RAM[0] <= context <= RAM[1] - 0x15:
        return dict(result, error="Missing or invalid summary context")
    if type(screen) is not int or screen % 4 or not RAM[0] <= screen <= RAM[1] - 0x240:
        return dict(result, error="Missing or invalid summary screen")
    try:
        if mem.read_long(screen + 0x23C) != context:
            return dict(result, error="Summary screen no longer owns context")
        address, mode, count, slot = (mem.read_long(context), mem.read_byte(context + 0x11),
                                    mem.read_byte(context + 0x13), mem.read_byte(context + 0x14))
        if (party.get("status") != "passed" or address != party["address"] or mode != 1 or
                count != party["count"] or not 0 <= slot < count):
            return dict(result, error="Summary context does not own a valid party slot")
        pokemon = address + 8 + 236 * slot
        identity = mem.read_long(pokemon)
        if identity != party["identities"][slot]:
            return dict(result, error="Summary slot identity changed during snapshot")
        return dict(result, status="passed", party_address=address, address=pokemon,
                    slot=slot, identity=identity)
    except Exception as exc:
        return dict(result, error=f"Summary read unavailable: {exc}")


def summary_state_evidence(scenario, raw):
    gaps, mismatches = [], []
    observations = raw.get("checkpoints", {})
    observations = observations if isinstance(observations, dict) else {}
    for name, expected in scenario.get("expected_summary_selection", {}).items():
        before, checkpoint = (observations.get(key, {}) for key in (expected["since"], name))
        before = before if isinstance(before, dict) else {}
        checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
        state, party = checkpoint.get("summary", {}), checkpoint.get("party", {})
        state = state if isinstance(state, dict) else {}
        party = party if isinstance(party, dict) else {}
        screen = state.get("screen_address")
        context, address, slot = state.get("context_address"), party.get("address"), state.get("slot")
        ids = party.get("identities", [])
        frames = [before.get("frame"), state.get("observed_frame"), checkpoint.get("frame")]
        valid = (state.get("status") == party.get("status") == "passed" and not state.get("error") and not party.get("error") and
                 type(screen) is int and screen % 4 == 0 and RAM[0] <= screen <= RAM[1] - 0x240 and
                 type(context) is int and context % 4 == 0 and RAM[0] <= context <= RAM[1] - 0x15 and
                 type(address) is int and address % 4 == 0 and RAM[0] <= address <= RAM[1] - (8 + 6 * 236) and
                 type(party.get("count")) is int and party["count"] == scenario["party_size"] and
                 isinstance(ids, list) and len(ids) == party["count"] and
                 all(type(i) is int and 0 <= i <= 0xFFFFFFFF for i in ids) and len(set(ids)) == len(ids) and
                 type(slot) is int and 0 <= slot < len(ids) and
                 type(state.get("identity")) is int and state["identity"] == ids[slot] and
                 state.get("party_address") == address and state.get("address") == address + 8 + 236 * slot and
                 all(type(f) is int and f >= 0 for f in frames) and frames[0] < frames[1] <= frames[2])
        if not valid:
            gaps.append(f"{name}: missing, stale or invalid summary selection snapshot")
        elif slot != expected["slot"]:
            mismatches.append(name)
    return {"gaps": gaps, "mismatches": mismatches}


def compare_summary_runs(scenario, zh, en):
    if not scenario.get("expected_summary_selection"):
        return "not_configured", [], {}
    evidence = {tag: summary_state_evidence(scenario, raw) for tag, raw in (("zh", zh), ("en", en))}
    z, e = (set(evidence[tag]["mismatches"]) for tag in ("zh", "en"))
    findings = []
    for category, names in (("baseline_shared", z & e), ("baseline_chinese", z - e),
                             ("english_regression" if not evidence["zh"]["gaps"] else "unverified", e - z)):
        findings.extend({"category": category, "kind": "summary_selection", "checkpoint": name} for name in sorted(names))
    status = ("failed" if any(f["category"] == "english_regression" for f in findings) else
              "incomplete" if z or e or any(v["gaps"] for v in evidence.values()) else "passed")
    return status, findings, evidence


def party_state_evidence(scenario, raw):
    gaps, mismatches = [], []
    observations = raw.get("checkpoints", {})
    for name, expected in scenario.get("expected_party_order", {}).items():
        reference = expected["relative_to"]
        pair = [observations.get(key, {}) for key in (reference, name)]
        pair = [value if isinstance(value, dict) else {} for value in pair]
        valid = True
        for key, checkpoint in zip((reference, name), pair):
            state = checkpoint.get("party", {})
            state = state if isinstance(state, dict) else {}
            ids = state.get("identities", [])
            ids = ids if isinstance(ids, list) else []
            address = state.get("address")
            if (state.get("status") != "passed" or state.get("error") or
                    type(state.get("count")) is not int or state.get("count") != scenario["party_size"] or len(ids) != scenario["party_size"] or
                    any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in ids) or
                    len(set(ids)) != len(ids) or type(address) is not int or address % 4 or
                    not RAM[0] <= address <= RAM[1] - (8 + 6 * 236)):
                gaps.append(f"{key}: missing, invalid or ambiguous bounded party snapshot")
                valid = False
        if not valid:
            continue
        if (any(type(c.get("frame")) is not int or c["frame"] < 0 for c in pair) or
                pair[0]["frame"] >= pair[1]["frame"]):
            gaps.append(f"{name}: invalid party checkpoint interval")
            continue
        wanted = [pair[0]["party"]["identities"][i] for i in expected["order"]]
        if pair[1]["party"]["identities"] != wanted:
            mismatches.append(name)
    return {"gaps": gaps, "mismatches": mismatches}


def compare_party_runs(scenario, zh, en):
    if not scenario.get("expected_party_order"):
        return "not_configured", [], {}
    evidence = {tag: party_state_evidence(scenario, raw) for tag, raw in (("zh", zh), ("en", en))}
    z, e = (set(evidence[tag]["mismatches"]) for tag in ("zh", "en"))
    findings = []
    # An English-only mismatch is a regression only when the Chinese evidence is valid.
    for category, names in (("baseline_shared", z & e), ("baseline_chinese", z - e),
                             ("english_regression" if not evidence["zh"]["gaps"] else "unverified", e - z)):
        findings.extend({"category": category, "kind": "party_order", "checkpoint": name} for name in sorted(names))
    failed = any(f["category"] == "english_regression" for f in findings)
    status = "failed" if failed else "incomplete" if z or e or any(v["gaps"] for v in evidence.values()) else "passed"
    return status, findings, evidence


def failure_signatures(raw):
    """Frame-independent signatures; differing failures must never cancel each other."""
    signatures = set()
    for hid, req, _ in raw.get("fails", []):
        signatures.add(("allocation", hid, req))
    for pc, _ in raw.get("nullw", []):
        signatures.add(("nullwrite", pc))
    if raw.get("corrupt"):
        # Heap placement can shift between ROMs. Retain heap/block/kind/error identity.
        message = re.sub(r"\b[0-9A-Fa-f]{8}\b", "<address>", raw["corrupt"][1])
        signatures.add(("corruption", message))
    return signatures


def compare_runs(zh, en):
    z, e = failure_signatures(zh), failure_signatures(en)
    findings = []
    for category, signatures in (("baseline_shared", z & e),
                                 ("baseline_chinese", z - e),
                                 ("english_regression", e - z)):
        for signature in sorted(signatures, key=repr):
            findings.append({"category": category, "signature": list(signature)})
    complete = all(raw.get("armed") and raw.get("script_completed") and raw.get("frames", 0) > 0 and raw.get("minspare") and raw.get("heap_checks", 0) > 0 and not raw.get("heap_table_errors")
                   for raw in (zh, en))
    # A baseline crash can truncate execution before a later English failure becomes observable.
    status = "failed" if e - z else "incomplete" if not complete or z - e else "passed"
    return status, findings


def compare_text_runs(zh, en):
    def signatures(raw):
        signatures = set()
        for event in raw.get("text_rejections", []):
            if "item" in event:
                signature = ("item", event["caller"], event["capacity"], event["item"], event["item_caller"])
            else:
                signature = ("generic", event["caller"], event["capacity"], event["units"])
            signatures.add(signature)
        return signatures
    z, e = signatures(zh), signatures(en)
    findings = []
    for category, observed in (("baseline_shared", z & e), ("baseline_chinese", z - e),
                               ("english_regression", e - z)):
        for signature in sorted(observed):
            findings.append({"category": category, "kind": "text_copy_rejected",
                             "signature": list(signature)})
    gaps = {tag: list(raw.get("text_probe_errors", [])) +
            ([] if raw.get("text_copy_checks", 0) else ["No bounded String-copy observations"])
            for tag, raw in (("zh", zh), ("en", en))}
    status = "failed" if e - z else "incomplete" if z - e or any(gaps.values()) else "passed"
    return status, findings, gaps


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return number


def run_child(command, timeout):
    started = time.monotonic()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        result = {"returncode": proc.returncode, "stdout": proc.stdout,
                  "stderr": proc.stderr, "status": "completed"}
    except subprocess.TimeoutExpired as exc:
        decode = lambda v: v.decode(errors="replace") if isinstance(v, bytes) else (v or "")
        result = {"returncode": None, "stdout": decode(exc.stdout),
                  "stderr": decode(exc.stderr), "status": "timeout"}
    except OSError as exc:
        result = {"returncode": None, "stdout": "", "stderr": str(exc), "status": "unavailable"}
    result.update(command=command, duration_seconds=time.monotonic() - started)
    lines = [line[9:] for line in result["stdout"].splitlines() if line.startswith("MEMCHECK ")]
    result["raw"] = None
    if lines:
        try:
            result["raw"] = json.loads(lines[-1])
            if not isinstance(result["raw"], dict):
                result["raw"] = None
                raise ValueError("Runtime child evidence must be a JSON object")
        except (ValueError, TypeError) as exc:
            result["parse_error"] = str(exc)
    if result["status"] == "completed" and (result["returncode"] or result["raw"] is None):
        result["status"] = "error"
    return result


@contextmanager
def isolated_emulator_config():
    """Fresh _one workers must isolate GLib's cached user-config path before loading DeSmuME."""
    previous = os.environ.get("XDG_CONFIG_HOME")
    with tempfile.TemporaryDirectory(prefix="memcheck_config_") as temporary:
        config = Path(temporary) / "config"
        config.mkdir()
        os.environ["XDG_CONFIG_HOME"] = str(config)
        try:
            yield config
        finally:
            if previous is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = previous


def cmd_one(a):
    sc = json.loads(SCENARIOS.read_text())["scenarios"][a.name]
    with isolated_emulator_config():
        pr = run_scenario(a.rom, a.sav, sc["script"], a.out, f"{a.name}_{a.tag}")
    print("MEMCHECK " + json.dumps(probe_data(pr)), flush=True)


def validate_expectations(scenario):
    rendering.validate_expectations(scenario.get("expected_rendering", {}))
    checkpoints = scenario.get("expected_checkpoints", {})
    warnings = scenario.get("coverage_warnings", [])
    if "coverage_scope" in scenario and (not isinstance(scenario["coverage_scope"], str) or not scenario["coverage_scope"].strip()):
        raise ValueError("coverage_scope must be a nonempty string")
    if not isinstance(warnings, list) or any(not isinstance(w, str) or not w for w in warnings):
        raise ValueError("coverage_warnings must contain nonempty strings")
    shots = [command.split()[1] for command in scenario["script"].split(";")
             if command.strip().startswith("shot ")]
    if len(shots) != len(set(shots)):
        raise ValueError("checkpoint names must be unique")
    if any(name in ("start", "boot") for name in shots):
        raise ValueError("shot names start and boot are reserved for bootstrap checkpoints")
    if not isinstance(checkpoints, dict):
        raise ValueError("expected_checkpoints must be an object")
    sequence = ["start", "boot"] + shots
    for name, expected in scenario.get("expected_rendering", {}).items():
        if (name not in shots or expected["since"] not in sequence
                or sequence.index(expected["since"]) >= sequence.index(name)):
            raise ValueError("Rendering requires an existing later screenshot checkpoint")
    party = scenario.get("expected_party_order", {})
    if not isinstance(party, dict):
        raise ValueError("expected_party_order must be an object")
    if party:
        count = scenario.get("party_size")
        if type(count) is not int or not 1 <= count <= 6:
            raise ValueError("party_size must be between 1 and 6")
        for name, expected in party.items():
            if (name not in shots or not isinstance(expected, dict) or
                    set(expected) != {"relative_to", "order"} or expected["relative_to"] not in sequence or
                    sequence.index(expected["relative_to"]) >= sequence.index(name) or
                    not isinstance(expected["order"], list) or any(type(i) is not int for i in expected["order"]) or
                    sorted(expected["order"]) != list(range(count))):
                raise ValueError(f"Invalid party expectation: {name}")
    summary = scenario.get("expected_summary_selection", {})
    if not isinstance(summary, dict):
        raise ValueError("expected_summary_selection must be an object")
    for name, expected in summary.items():
        count = scenario.get("party_size")
        if (type(count) is not int or not 1 <= count <= 6 or name not in shots or
                not isinstance(expected, dict) or set(expected) != {"since", "slot"} or
                expected["since"] not in sequence or sequence.index(expected["since"]) >= sequence.index(name) or
                type(expected["slot"]) is not int or not 0 <= expected["slot"] < count):
            raise ValueError(f"Invalid summary expectation: {name}")
    moves = scenario.get("expected_move_order", {})
    if not isinstance(moves, dict):
        raise ValueError("expected_move_order must be an object")
    for name, expected in moves.items():
        count = scenario.get("party_size")
        if (type(count) is not int or not 1 <= count <= 6 or name not in shots or
                not isinstance(expected, dict) or not {"relative_to", "slot", "order"} <= set(expected) <= {"relative_to", "slot", "order", "summary_closed"} or
                ("summary_closed" in expected and expected["summary_closed"] is not True) or
                expected["relative_to"] not in sequence or sequence.index(expected["relative_to"]) >= sequence.index(name) or
                type(expected["slot"]) is not int or not 0 <= expected["slot"] < count or
                expected["order"] != [1, 0, 2, 3] or any(type(i) is not int for i in expected["order"])):
            raise ValueError(f"Invalid move expectation: {name}")
    for name, expectation in checkpoints.items():
        if name not in shots or not isinstance(expectation, dict) or "since" not in expectation or not set(expectation) <= {"since", "loads", "descriptions"}:
            raise ValueError(f"Invalid checkpoint expectation: {name}")
        since, loads = expectation["since"], expectation.get("loads", [])
        if since not in sequence or sequence.index(since) >= sequence.index(name):
            raise ValueError(f"Checkpoint {name}: since must name an earlier checkpoint")
        descriptions = expectation.get("descriptions", [])
        if not isinstance(loads, list) or not isinstance(descriptions, list) or not (loads or descriptions):
            raise ValueError(f"Checkpoint {name}: at least one expected evidence list must be nonempty")
        for description in descriptions:
            if not isinstance(description, dict) or set(description) != {"item", "heap"} or any(
                    type(value) is not int or value < 0 for value in description.values()):
                raise ValueError(f"Checkpoint {name}: invalid item-description expectation")
        for load in loads:
            if not isinstance(load, dict) or set(load) != {"narc", "bank", "heap"} or any(
                    type(value) is not int or value < 0 for value in load.values()):
                raise ValueError(f"Checkpoint {name}: invalid message-load expectation")


def checkpoint_coverage(scenario, raw):
    gaps = list(scenario.get("coverage_warnings", []))
    expectations = scenario.get("expected_checkpoints", {})
    if not expectations:
        gaps.append("No checkpoint objective expectations configured")
    observations = raw.get("checkpoints", {})
    for name, expected in expectations.items():
        stop, start = observations.get(name), observations.get(expected["since"])
        if not stop or not start:
            gaps.append(f"{name}: missing checkpoint or interval start")
            continue
        if not stop.get("screenshot_captured"):
            gaps.append(f"{name}: screenshot checkpoint was not captured")
        if start["frame"] >= stop["frame"]:
            gaps.append(f"{name}: invalid checkpoint interval")
            continue
        for wanted in expected.get("descriptions", []):
            if not any(start["frame"] < event.get("frame", -1) <= stop["frame"]
                       and all(event.get(key) == value for key, value in wanted.items())
                       for event in stop.get("item_description_reads", [])):
                gaps.append(f"{name}: expected description missing in ({expected['since']}, {name}] interval: {wanted}")
        for wanted in expected.get("loads", []):
            if not any(start["frame"] < event.get("frame", -1) <= stop["frame"]
                       and all(event.get(key) == value for key, value in wanted.items())
                       for event in stop.get("message_loads", [])):
                gaps.append(f"{name}: expected load missing in ({expected['since']}, {name}] interval: {wanted}")
    if not raw.get("script_completed"):
        gaps.append("Scenario script did not complete")
    shots = [command.split()[1] for command in scenario["script"].split(";")
             if command.strip().startswith("shot ")]
    return {"status": "incomplete" if gaps else "passed", "gaps": gaps,
            "configured_checkpoints": list(dict.fromkeys([*expectations, *scenario.get("expected_party_order", {}), *scenario.get("expected_summary_selection", {}), *scenario.get("expected_move_order", {})])),
            "unasserted_checkpoints": [name for name in shots if name not in expectations and name not in scenario.get("expected_party_order", {}) and name not in scenario.get("expected_summary_selection", {}) and name not in scenario.get("expected_move_order", {})],
            "scope": scenario.get("coverage_scope", "Configured temporal resource checkpoints only; not complete screen/action verification")}


def file_identity(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(Path(path).resolve()), "size": Path(path).stat().st_size,
            "sha256": digest.hexdigest()}


def capabilities():
    versions = {}
    for module, package in (("desmume.emulator", "py-desmume"), ("PIL.Image", "Pillow"),
                            ("capstone", "capstone"), ("ndspy.rom", "ndspy")):
        importlib.import_module(module)
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    return versions


def evidence_gaps(raw):
    gaps = []
    if not raw.get("armed"):
        gaps.append("boot instrumentation was not armed")
    if not raw.get("script_completed"):
        gaps.append("scenario script did not complete")
    if not raw.get("frames", 0):
        gaps.append("no frames observed")
    if not raw.get("minspare"):
        gaps.append("no heap observations")
    if not raw.get("heap_checks", 0):
        gaps.append("no heap integrity checks")
    gaps.extend(raw.get("heap_table_errors", []))
    return gaps


def atomic_report(destination, report):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".memcheck-", suffix=".json", dir=destination.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def cmd_run(a):
    report = {"schema_version": 2, "status": "incomplete", "scenarios": {}, "errors": [],
              "metadata": {"interpreter": sys.executable, "python": sys.version,
                           "emulator_isolation": "fresh worker with temporary XDG_CONFIG_HOME before native initialization"},
              "policy": "block English-only failure signatures; report Chinese baseline findings"}
    scenarios = json.loads(SCENARIOS.read_text())["scenarios"]
    names = list(scenarios) if a.scenario == "all" else a.scenario.split(",")
    input_paths = {"checker": __file__, "manifest": SCENARIOS, "rom_zh": a.ref, "rom_en": a.rom,
                   "helper_rendering": rendering.__file__, "helper_reproducibility": reproducibility.__file__}
    input_paths.update({"save:" + name: Path(a.saves) / scenarios[name]["sav"]
                        for name in names if name in scenarios})
    inputs_before = reproducibility.capture_inputs(input_paths)
    if not names or any(not name or name not in scenarios for name in names) or len(set(names)) != len(names):
        report["errors"].append("Select known, nonempty, unique scenario names")
    for label, path in (("English ROM", a.rom), ("Chinese ROM", a.ref)):
        if not Path(path).is_file():
            report["errors"].append(f"{label} missing: {path}")
    out = (Path(a.out) if a.out else WORK / "build" / "memcheck-runs" /
           datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")).resolve()
    if not out.is_relative_to((WORK / "build").resolve()):
        report["errors"].append("Runtime artifacts must stay inside ignored work/build")
    if not report["errors"]:
        out.mkdir(parents=True, exist_ok=True)
        try:
            for name in names:
                validate_expectations(scenarios[name])
            report["metadata"]["dependencies"] = capabilities()
            report["metadata"]["manifest"] = file_identity(SCENARIOS)
            report["metadata"]["checker"] = file_identity(__file__)
            report["metadata"]["roms"] = {"zh": file_identity(a.ref), "en": file_identity(a.rom)}
            _check_code(a.rom)
            _check_code(a.ref)
            loads, unresolved = static_loads(a.rom, a.ref)
            report["static"] = {"loads": loads, "unresolved": unresolved, "reporting_only": True}
        except (Exception, SystemExit) as exc:
            report["errors"].append(f"Prerequisite check failed: {exc}")
    if not report["errors"]:
        for name in names:
            scenario = scenarios[name]
            entry = {"description": scenario["desc"], "status": "incomplete", "findings": [], "runs": {},
                     "state_status": "incomplete" if scenario.get("expected_party_order") else "not_configured",
                     "state_expectations": scenario.get("expected_party_order", {}),
                     "party_size": scenario.get("party_size"),
                     "summary_status": "incomplete" if scenario.get("expected_summary_selection") else "not_configured",
                     "summary_expectations": scenario.get("expected_summary_selection", {}), "summary_evidence": {},
                     "move_status": "incomplete" if scenario.get("expected_move_order") else "not_configured",
                     "move_expectations": scenario.get("expected_move_order", {}), "move_evidence": {},
                     "rendering_expectations": scenario.get("expected_rendering", {}),
                     "rendering_status": "incomplete" if scenario.get("expected_rendering") else "not_configured",
                     "rendering_evidence": {}, "environment_status": "incomplete"}
            report["scenarios"][name] = entry
            sav = Path(a.saves) / scenario["sav"]
            if not sav.is_file() or sav.stat().st_size != 524288:
                entry["reason"] = f"Missing or invalid raw 512 KB save: {sav}"
            else:
                entry["save"] = file_identity(sav)
                fixture_before = reproducibility.capture_inputs({"fixture": sav})
                for tag, rom in (("zh", a.ref), ("en", a.rom)):
                    entry["runs"][tag] = run_child(
                        [sys.executable, __file__, "_one", str(Path(rom).resolve()),
                         str(sav.resolve()), name, str(out), tag], a.timeout)
                entry["fixture_integrity"] = reproducibility.verify_inputs(
                    fixture_before, reproducibility.capture_inputs({"fixture": sav}))
                if all(run["status"] == "completed" for run in entry["runs"].values()):
                    zh, en = (entry["runs"][tag]["raw"] for tag in ("zh", "en"))
                    entry["status"], entry["findings"] = compare_runs(zh, en)
                    entry["memory_status"] = entry["status"]
                    entry["state_status"], state_findings, entry["state_evidence"] = compare_party_runs(scenario, zh, en)
                    entry["findings"].extend(state_findings)
                    if entry["state_status"] == "failed":
                        entry["status"] = "failed"
                    elif entry["state_status"] == "incomplete" and entry["status"] != "failed":
                        entry["status"] = "incomplete"
                    entry["summary_status"], summary_findings, entry["summary_evidence"] = compare_summary_runs(scenario, zh, en)
                    entry["findings"].extend(summary_findings)
                    if entry["summary_status"] == "failed":
                        entry["status"] = "failed"
                    elif entry["summary_status"] == "incomplete" and entry["status"] != "failed":
                        entry["status"] = "incomplete"
                    entry["move_status"], move_findings, entry["move_evidence"] = compare_move_runs(scenario, zh, en)
                    entry["findings"].extend(move_findings)
                    if entry["move_status"] == "failed":
                        entry["status"] = "failed"
                    elif entry["move_status"] == "incomplete" and entry["status"] != "failed":
                        entry["status"] = "incomplete"
                    entry["text_status"], text_findings, entry["text_evidence_gaps"] = compare_text_runs(zh, en)
                    entry["findings"].extend(text_findings)
                    if entry["text_status"] == "failed":
                        entry["status"] = "failed"
                    elif entry["text_status"] == "incomplete" and entry["status"] != "failed":
                        entry["status"] = "incomplete"
                    entry["coverage"] = {tag: checkpoint_coverage(scenario, raw) for tag, raw in (("zh", zh), ("en", en))}
                    entry["environment_status"] = reproducibility.pair_environment_status(
                        zh.get("environment"), en.get("environment"))
                    entry["rendering_evidence"] = rendering.evaluate(entry["rendering_expectations"], entry["runs"])
                    entry["rendering_status"] = entry["rendering_evidence"]["status"]
                    for checkpoint, proof in entry["rendering_evidence"].get("checkpoints", {}).items():
                        if proof["status"] == "failed":
                            entry["findings"].append({"category": "english_regression", "kind": "blank_description_region",
                                                      "checkpoint": checkpoint,
                                                      "item": entry["rendering_expectations"][checkpoint]["item"]})
                        elif all(sample.get("status") == "blank" for sample in proof["evidence"].values()):
                            entry["findings"].append({"category": "baseline_shared", "kind": "blank_description_region",
                                                      "checkpoint": checkpoint})
                    if entry["rendering_status"] == "failed":
                        entry["status"] = "failed"
                    elif (entry["rendering_status"] == "incomplete" or entry["environment_status"] != "passed"
                          or reproducibility.evidence_status(entry["fixture_integrity"], required_roles=("fixture",)) != "passed") and entry["status"] != "failed":
                        entry["status"] = "incomplete"
                    if any(value["status"] != "passed" for value in entry["coverage"].values()) and entry["status"] != "failed":
                        entry["status"] = "incomplete"
                    gaps = {tag: evidence_gaps(raw) for tag, raw in (("zh", zh), ("en", en))}
                    for tag, raw in (("zh", zh), ("en", en)):
                        for expected in scenario.get("expected_message_loads", []):
                            if not any(all(event.get(key) == value for key, value in expected.items())
                                       for event in raw.get("message_loads", [])):
                                gaps[tag].append("expected message load not observed: " + json.dumps(expected))
                    if any(gaps.values()):
                        if entry["status"] != "failed":
                            entry["status"] = "incomplete"
                        entry["evidence_gaps"] = gaps
                        entry["reason"] = "Insufficient runtime evidence: " + json.dumps(gaps)
                    elif entry["memory_status"] == "incomplete":
                        entry["reason"] = "Chinese-only failure makes the comparison inconclusive"
                    elif entry["text_status"] == "incomplete":
                        entry["reason"] = "Text-copy evidence is incomplete or differs from the Chinese baseline"
                    elif entry["state_status"] == "incomplete":
                        entry["reason"] = "Party-state evidence is missing, invalid, or does not meet the scripted objective"
                    elif entry["environment_status"] != "passed":
                        entry["reason"] = "Paired emulator environment evidence is incomplete or inconsistent"
                    elif reproducibility.evidence_status(entry["fixture_integrity"], required_roles=("fixture",)) != "passed":
                        entry["reason"] = "Source fixture identity changed or could not be verified"
                    elif entry["rendering_status"] == "incomplete":
                        entry["reason"] = "Selected rendering evidence is incomplete or the Chinese baseline is blank"
                    elif entry["status"] == "incomplete":
                        entry["reason"] = "Configured scenario checkpoint coverage is incomplete"
                    by_heap = {}
                    for load in report["static"]["loads"]:
                        by_heap.setdefault(str(load["heap"]), {})[load["bank"]] = load
                    for hid, e in en["minspare"].items():
                        z = zh["minspare"].get(hid)
                        if a.verbose:
                            print(f"  heap {hid}: spare zh {z[0] if z else '-'} en {e[0]}")
                        for bank, load in by_heap.get(hid, {}).items():
                            if z and load["growth"] > z[0]:
                                entry["findings"].append({"category": "prediction", "heap": hid,
                                                          "bank": bank, "growth": load["growth"],
                                                          "chinese_spare": z[0], "reporting_only": True})
                        if e[0] < a.warn and (z is None or e[0] < z[0] - 256):
                            entry["findings"].append({"category": "warning", "heap": hid,
                                                      "english_spare": e[0], "chinese_spare": z[0] if z else None})
                else:
                    entry["reason"] = "Emulator child failed, timed out, or produced no usable result"
            print(f"{name}: {entry['status']} ({len(entry['findings'])} findings)", flush=True)
            if entry.get("reason"):
                print("  " + entry["reason"])
            for finding in entry["findings"]:
                print("  " + json.dumps(finding))
    report["reproducibility"] = reproducibility.verify_inputs(inputs_before, reproducibility.capture_inputs(input_paths))
    if reproducibility.evidence_status(report["reproducibility"]) != "passed":
        report["errors"].append("Input identity verification failed; see reproducibility evidence")
        for entry in report["scenarios"].values():
            if entry["status"] == "passed":
                entry["status"] = "incomplete"
    counts = {status: sum(s["status"] == status for s in report["scenarios"].values())
              for status in ("passed", "failed", "incomplete")}
    report["counts"] = dict(counts, selected=len(names), executed=sum(bool(s["runs"]) for s in report["scenarios"].values()))
    report["status"] = "failed" if counts["failed"] else "incomplete" if report["errors"] or counts["incomplete"] or not counts["passed"] else "passed"
    for error in report["errors"]:
        print(error, file=sys.stderr)
    destination = Path(a.json).resolve() if a.json else out / "report.json"
    if not destination.is_relative_to((WORK / "build").resolve()):
        print("Report must stay inside ignored work/build", file=sys.stderr)
        return 2
    atomic_report(destination, report)
    print(f"{report['status']}: {destination}")
    return 0 if report["status"] == "passed" else 1 if report["status"] == "failed" else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("static")
    s.add_argument("--rom", default=str(DEF_ROM))
    s.add_argument("--ref", default=str(DEF_REF))
    s.add_argument("--json")
    r = sub.add_parser("run")
    r.add_argument("--saves", default=str(WORK / "build" / "memcheck"))
    r.add_argument("--rom", default=str(DEF_ROM))
    r.add_argument("--ref", default=str(DEF_REF))
    r.add_argument("--scenario", default="all")
    r.add_argument("--out", help="artifact directory under work/build; default a new timestamped run directory")
    r.add_argument("--json")
    r.add_argument("--timeout", type=positive_seconds, default=120, help="finite positive seconds per emulator child")
    r.add_argument("--warn", type=int, default=4096)
    r.add_argument("-v", "--verbose", action="store_true", help="print every heap, not only flagged ones")
    o = sub.add_parser("_one")
    for k in ("rom", "sav", "name", "out", "tag"):
        o.add_argument(k)
    a = ap.parse_args(argv)
    return {"static": cmd_static, "run": cmd_run, "_one": cmd_one}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
