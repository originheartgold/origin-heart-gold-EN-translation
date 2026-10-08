# melonDS backend for the emulator harness (`--emulator melonds`)

**Status (2026-10-08): built and proven.** The harness runs on DeSmuME (py-desmume) by default. A second backend now runs the official **melonDS 1.1** core headless through our own small shim. It is there because DeSmuME does not emulate the ARM9 protection unit: where the hack reads a NULL pointer, DeSmuME returns a value and the game goes on, but melonDS and hardware raise a **data abort** and the game freezes. The Rocket HQ freeze (D-2043) and the Bulbasaur follower reflection freeze can only be seen this way.

## Pieces

| File | What it is |
|---|---|
| `work/tools/melonds_shim/melonds_shim.cpp` | C API over the melonDS core: Platform callbacks for a headless process, a subclass of `melonDS::NDS` for data watchpoints, capture of the core's ARM9 exception log lines. Our code, GPLv3 (it is linked with melonDS). See `LICENSE.md` in that folder. |
| `work/tools/melonds_shim/build.py` | Checks the pinned melonDS checkout, builds the core with CMake, compiles and links `libmelonds_shim.dylib` into `work/build/melonds/` (git-ignored). |
| `work/tools/melonds.py` | Python ctypes wrapper (`MelonDS`). No melonDS code; loads the library at run time. |
| `work/tools/emu_harness.py` | `Harness(..., emulator="melonds")`, `start_at(..., emulator=...)`, the global `--emulator` option, and the crash and hang helpers. |
| `work/tools/emu_hang.py` | The `hang` subcommand: walk from a save and judge hang / pass (Rocket HQ, Viridian follower). |
| `work/tools/test_melonds.py` | Wrapper and adapter tests. The library tests skip when the shim is not built; the boot test also needs the Chinese ROM. |

No melonDS source is in the repository. The build uses a separate checkout of the release tag (like armips). The pin and build steps are in [toolchain.md](toolchain.md#melonds-11-emulator-harness-backend).

## Build

```sh
git clone --depth 1 --branch 1.1 https://github.com/melonDS-emu/melonDS.git ../melonDS   # once; or build.py --fetch
.venv/bin/python work/tools/melonds_shim/build.py          # --src DIR / $MELONDS_SRC, --out DIR
.venv/bin/python -m unittest work/tools/test_melonds.py
```

The core builds with Apple clang and CMake 4 alone: the configuration (no Qt/SDL frontend, no OpenGL, no JIT, no GDB stub, no LTO) needs no Homebrew library. WiFi stays in the core but its network callbacks are stubs. The build takes about a minute. The library is about 3.4 MB; `work/build/melonds/` about 30 MB with the CMake tree. The library is found at `work/build/melonds/libmelonds_shim.dylib` or through `$MELONDS_SHIM`.

**Configuration.** DS mode, direct boot, melonDS's built-in **FreeBIOS** and generated firmware (no BIOS or firmware dump anywhere), interpreter (no JIT), software 3D renderer, unthreaded, audio drained and dropped. The notes' manual repro used the same except a threaded renderer, which only changes speed. Speed: about 500–600 frames/s on an M-series Mac, about twice DeSmuME's. Booting a save to the field takes about 11 s.

**Determinism.** melonDS's RTC runs on emulated time. The harness sets it before boot (`rtc=`; `Harness` defaults to now, `start_at(clock=...)` and `emu_hang` use a fixed date). The core leaves some members of the console object uninitialised (RTC I/O state, Wifi, GPU2D and ARM fields), so a console used to start from whatever the heap held. The shim's `HookedNDS` zeroes the object before construction. What is proven (2026-10-08):

- Two consoles in one process, on a heap first filled with garbage and with a destroyed console's state, give byte-identical savestates at frames 0 and 200 (`test_melonds.Determinism`; the test fails without the zeroing).
- Two processes booting player A's save give identical savestate hashes at frames 0, 200, 1300 and 3000.
- Two processes running `hang --case rocket_hq` abort at the same frame (4283) with the same R1–R15, CPSR and abort LR.
- A savestate reloaded and run for the same frames gives the same RAM.

Not deterministic: **R0 after the Rocket HQ abort** (seen as `0x5`, `0xB`, `0xC`). The faulting `ldr r0,[r0]` is melonDS's `T_LDR_IMM`, which writes an uninitialised local variable into R0 when the read aborts. That is stack garbage inside the core, which the shim cannot reach without changing melonDS. The game never uses that R0 (the handler spins), but do not compare it.

## Shim C API (`melonds_shim.cpp`, ABI 1)

`mds_create/destroy`, `mds_load_rom(path, sav, len, direct_boot)`, `mds_reset`, `mds_set_rtc`, `mds_run_frame`, `mds_set_keys(mask)` (bit 0 A … 9 L, 10 X, 11 Y; 1 = pressed), `mds_touch/release_touch`, `mds_screenshot_rgb` (256×384 RGB, top screen first), `mds_read/write` (as the ARM9 sees memory: ITCM, DTCM, then the bus; no side-effect-free guarantee for I/O registers), `mds_read/write_main_ram` (offset into the 4 MB main RAM), `mds_cpu_regs(cpu)` (R0–R15, CPSR, the abort/SVC/IRQ/undefined banks, current instruction, halted), `mds_set_cpu_reg`, `mds_exceptions` / `mds_clear_exceptions`, `mds_log_drain`, `mds_watch_add/clear/capacity/hits`, `mds_savestate_save/copy/load` (melonDS's own format: the frontend's `.ml1` files of 1.1 load too, checked with the Rocket HQ states), `mds_save_length/read/write` (the cart's battery memory).

### What there is instead of execution hooks

There is **no per-instruction or PC hook.** The interpreter loop (`ARMv5::Execute`) is not virtual. The only stock hook, the GDB stub's breakpoint check, stops the emulation thread and waits for a debugger on a socket. A PC hook would need a change to the core, so it was left out on purpose. `Harness.on_exec` (and py-desmume's `register_read/write`) raise `NotImplementedError` on melonDS. Scenarios that inject scripts through `on_exec` (`run_script`, `warp`, `show_message`, `set_clock`'s cache rewrite, `WildLog`) stay on DeSmuME.

What melonDS offers in their place, with no core change:

- **ARM9 exception record.** The core logs `ARM9: data abort (R15)`, prefetch aborts and undefined instructions through `Platform::Log`. The shim counts them, keeps the first and last R15 and the frame of the first abort. After a data abort the hack's handler spins in abort mode (CPSR mode `0x17`). Its LR minus 8 is the faulting instruction, in Thumb and ARM state alike (`ARMv5::DataAbort`: `R14 = R15 + (Thumb ? 4 : 0)`).
- **Data watchpoints.** The `NDS` subclass overrides the virtual `ARM9Read8/16/32` and `ARM9Write8/16/32`, so every ARM9 access that leaves the TCMs (CPU loads and stores, ARM9 DMA) is checked against the watch ranges. A hit records address, size, value, read/write, R15, CPSR and frame into a buffer (4096 by default, overflow counted). `pc` in the Python hit is the instruction's address (R15 − 4 in Thumb, − 8 in ARM). The hits are buffered, not called back, so the game cannot be changed at the moment of the access. A hit caused by ARM9 DMA carries the CPU's R15 and CPSR at the time of the transfer, not the code that started the DMA. Accesses served by DTCM (the stack, in this game) are never seen.

## Harness API for scenarios

```python
import datetime, emu_harness as E

def lead_bulbasaur(sf):                       # edit a copy of the battery save before boot
    sf.edit_party_mon(0, species=1, form=0)   # new: SaveFile.edit_party_mon / set_party_count / party
    sf.set_party_count(1)

with E.start_at(50, 1017, 260, direction="DOWN", sav=SAVE, rom=ROM, edit=lead_bulbasaur,
                emulator="melonds", clock=datetime.datetime(2026, 10, 9, 12), verbose=False) as h:
    for d in ("DOWN", "RIGHT", "RIGHT", "LEFT"):
        h.step_dir(d)
        if h.arm9_abort():                    # the freeze: the ARM9 is stuck in the abort handler
            break
    rep = h.hang_report(240, probe_key="B")   # dict: hung, screen_changed, black_top/bottom, abort, position, ...
```

| Call | Backend | Returns |
|---|---|---|
| `Harness(rom, sav, emulator="melonds", rtc=dt)` | both | as before; `h.emulator`, `h.melon` (the `melonds.MelonDS`) |
| `start_at(map, x, y, ..., emulator=, direction=)` | both | as before; on melonDS `clock` sets the console RTC before boot |
| `h.arm9_abort()` | melonDS | `None`, or `{in_abort_mode, fault_pc, abort_lr, cpsr, r, data_aborts, first_abort_frame, ...}` |
| `h.cpu_exceptions()` | melonDS | counters of data/prefetch aborts and undefined instructions, battery save writes |
| `h.screen_black(screen="both", threshold=8)` | both | every pixel of the screen(s) at most `threshold` |
| `h.hang_report(frames, probe_key=None)` | both | runs `frames` frames and reports `hung` = abort mode (melonDS) or an unchanging black screen |
| `h.watch(addr, length, read=False, write=True)`, `h.watch_hits()`, `h.clear_watches()` | melonDS | hits: `addr, size, value, write, pc, thumb, frame` |
| `h.melon.save_state()` / `load_state(bytes)` / `h.save_state(path)` | both (own formats) | melonDS states are not DeSmuME states |
| `SaveFile.edit_party_mon(slot, species=, item=, form=, moves=, ability=)`, `set_party_count(n)`, `party()` | — | battery save edits; the game builds the lead's follower from them at Continue |

Everything else in `Harness` that only reads or writes memory, steps, presses keys, touches the screen or takes screenshots works on both backends (`position`, `location`, `party`, `get_flag`/`set_flag`, `walk_to`, `step_dir`, `in_field`, `screenshot`, `pixel`, `on_screen`, `edit_party_mon`, ...).

From the command line, `--emulator melonds` comes before the subcommand and sets `$EMU_HARNESS_EMULATOR`, so child processes inherit it:

```sh
.venv/bin/python work/tools/emu_harness.py --emulator melonds info --sav S
.venv/bin/python work/tools/emu_harness.py hang --case rocket_hq --rom R --sav S --expect hang|pass
.venv/bin/python work/tools/emu_harness.py hang --case follower_viridian --rom R --sav S [--species 4] --expect hang|pass
.venv/bin/python work/tools/emu_harness.py hang --case save --rom R --sav S [--walk LEFT,RIGHT] [--goal X,Y] --expect hang|pass
```

`hang` runs on melonDS unless `--emulator desmume` is given. `fixes` (emu_fixes.py) and `check.py --full --emu` always run on DeSmuME: their scenarios use execution hooks and DeSmuME-approved crop digests. They ignore a stray `$EMU_HARNESS_EMULATOR` with a note and record `"emulator": "desmume"` in `fixes_report.json`.

`MelonDS` objects are not thread-safe: use each console from one thread. Calls after `close()` raise `RuntimeError`. The library exports only the `mds_*` C API. It checks the save by SHA-256 and writes `report.json` and screenshots to `work/build/harness/hang/<case>_<rom>_<emulator>/`. Exit 0 when the judgement matches `--expect`.

**Teleporting outdoors.** `start_at`/`SaveFile.place_player` from the default `memcheck/full_bag_6mons.sav` (saved indoors, map 500) to an outdoor map leaves the player invisible and unable to move, on DeSmuME as well. From a save made outdoors it works (player B's hash-named save, map 29, SHA-256 `0886514d…ebc9eb`, used by `follower_viridian`). Which LocalFieldData field makes the difference is not established. Indoor targets (Rocket HQ from `full_bag_6mons.sav`) work.

## Results (2026-10-08)

Builds from this branch (develop `172dbc0`): `develop.nds` = `build.py --no-patch` (SHA-256 `acd75bfe…`), control = `build.py --no-patch --without overworld-texture-frame-bounds` (`ccfd5dbd…`). The Chinese ROM is `4807ab2c…`. RTC 2026-10-09 12:00.

| Case | ROM | Expect | Result |
|---|---|---|---|
| rocket_hq (player A's save `ee32cbb4…`) | untouched Chinese v4.0.3 | hang | **hang**: data abort at frame 4283 while stepping from (16,4) towards (17,4), CPSR `0x60000097`, abort LR `0x0202469E`, faulting instruction `0x02024696` (`ldr r0,[r0]`); the screen stops changing |
| rocket_hq | develop without overworld-texture-frame-bounds | hang | **hang**, the same signature and frame |
| rocket_hq | develop | pass | **pass**: (23,4) reached, no abort, the camera ambush starts |
| rocket_hq | untouched Chinese, `--emulator desmume` | pass | **pass** (DeSmuME ignores the NULL read, as in the manual test) |
| follower_viridian, Bulbasaur (species 1) | untouched Chinese | hang | **hang**: data abort at `0x02024528` (in the reflection graphics getter `0x0202451C`) on the first RIGHT step along the pond |
| follower_viridian, Bulbasaur | develop (no reflection fix yet) | hang | **hang**, the same signature |
| follower_viridian, Charmander (species 4) | Chinese and develop | pass | **pass**: all four steps, no abort |

Bulbasaur fixture saves, `hang --case save`, run 2026-10-08 after the determinism fix. ROMs were reused read-only from the reflection fix's branch: full build `c72ad376…` and `--without bulbasaur-reflection-boundary` `acd75bfe…`.

| Save | ROM | Expect | Result |
|---|---|---|---|
| Viridian pond, Bulbasaur | without the fix | hang | **hang** while Continue loads the map (frame 3475), fault `0x02024528`, both screens black |
| Viridian pond, Bulbasaur | full build | pass | **pass**: four steps, ends at (1018,261) |
| Route 22 pond, Bulbasaur | without the fix | hang | **hang** while Continue loads the map (frame 3468), fault `0x02024528`, both screens black |
| Route 22 pond, Bulbasaur | full build | pass | **pass**: four steps, ends at (967,270) |
| Viridian / Route 22, Charmander | without the fix | pass | **pass** |

These match the manual melonDS 1.1 reproduction in [rocket_hq_freeze_repro_20261008.md](rocket_hq_freeze_repro_20261008.md) exactly: same CPSR, abort LR and faulting instruction. Loading the manual `.ml1` crash states in the shim also gives the same registers. The Bulbasaur freeze is a static, not a black, screen: the last frame stays up while the ARM9 spins in the abort handler.

### The Bulbasaur reflection fixture saves (`hang --case save`)

`--case save` boots any save as it is, picks Continue and walks `--walk` (one tile per direction). The goal is `--goal x,y` after the last step, or every step moving. `--fault-pc` checks where the abort is. An abort while Continue loads the map counts as a hang, and nothing is walked. It does not check the save's hash; the report records it.

The four in-game saves of the reflection fix (work/notes/bulbasaur_reflection_fix.md, SHA-256s there) were made on the untouched Chinese ROM with one Pokémon in the party. Copy them into a git-ignored folder (here `work/build/reflection-fixtures/`). Then:

```sh
# Viridian City, north shore of the pond (Bulbasaur / Charmander following)
.venv/bin/python work/tools/emu_harness.py hang --case save --rom WITHOUT.nds --sav viridian_bulbasaur.sav \
    --walk LEFT,RIGHT,LEFT,RIGHT --goal 1018,261 --fault-pc 0x02024528 --expect hang
.venv/bin/python work/tools/emu_harness.py hang --case save --rom FIXED.nds --sav viridian_bulbasaur.sav \
    --walk LEFT,RIGHT,LEFT,RIGHT --goal 1018,261 --expect pass
# Route 22, north shore of the pond beside Misty
.venv/bin/python work/tools/emu_harness.py hang --case save --rom WITHOUT.nds --sav route22_bulbasaur.sav \
    --walk LEFT,LEFT,RIGHT,RIGHT --goal 967,270 --fault-pc 0x02024528 --expect hang
.venv/bin/python work/tools/emu_harness.py hang --case save --rom FIXED.nds --sav route22_bulbasaur.sav \
    --walk LEFT,LEFT,RIGHT,RIGHT --goal 967,270 --expect pass
```

`FIXED.nds` is a full build (`build.py --no-patch`); `WITHOUT.nds` is `build.py --no-patch --without bulbasaur-reflection-boundary`. Use the Charmander saves with `--expect pass` on either ROM.

## Limits

- No PC breakpoints or execution hooks (see above). Watchpoints are buffered and miss DTCM accesses.
- One frame is the smallest step: an abort is seen after the frame in which it happened (`first_abort_frame` gives the exact frame).
- Hardware differences beyond the protection unit are melonDS's, not hardware's: a pass on melonDS is evidence, not proof, for hardware.
- melonDS savestates and DeSmuME savestates are not interchangeable; `drive --state` and `wild --state` stay DeSmuME files.
- The emulator slot cap (`EMU_HARNESS_MAX_EMULATORS`) counts melonDS instances like DeSmuME ones.
