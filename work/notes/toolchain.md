# Toolchain: armips for the code, data and strings fixes

**Status (2026-10-08): current.** The code, data and strings fixes in `work/patches/` are armips sources, and armips is the only engine that applies them. The build assembles them with **armips v0.11.0**; nothing else outside Python is needed for them.

## Why armips

The hack is a binary hack of the Japanese HeartGold, so the pret decompilation cannot build it. The code, data and strings fixes are small edits to the hack's own `arm9` and overlays (an immediate, a branch, keyboard rows, window templates, the outfit chooser's labels), so they are written the way ROM hackers write such edits ([hg-engine](https://github.com/BluRosie/hg-engine) style): an armips `.asm` file per fix that opens the binary at its RAM load address, goes to the RAM address with `.org` and writes the instruction or data in mnemonic form, with a comment.

## Version and build steps

The build is pinned to **armips v0.11.0**: tag object `8d2c76cb5107a1a04324fbb2dd9aecec61b779a3`, commit `156f78f6bccfc07498578ac491ce7fe2a1e807a6` of <https://github.com/Kingcom/armips>. It is not bundled with the repo. Build it yourself:

```sh
git clone https://github.com/Kingcom/armips.git
cd armips
git checkout v0.11.0          # no submodules at this tag
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5   # the policy flag is for CMake 4
make
```

The binary itself is not reproducible (its banner embeds the build date and time), so there is no binary hash to check: the tag and commit above are the pin, and the build checks the version banner.

The build finds armips in this order: `build.py --armips PATH`, the `ARMIPS` environment variable, `armips` on `PATH`. It runs it with no arguments and requires the banner `armips assembler v0.11.0`; any other version stops the build. Without armips the build stops as soon as a strings, code or data fix is selected; `--no-hardcoded --without gfx-naming-tabs` leaves them all out (`gfx-naming-tabs` `requires` the naming keyboard, so `--no-hardcoded` alone is refused). The build looks for armips in stage 0, before the export, so a missing or wrong armips stops it at once. A relative `--armips`/`ARMIPS` path is made absolute (armips runs in a staging folder); a bare name is looked up on `PATH`.

## Layout

```
work/patches/include/guards.inc     expect16 / expect16_at / expect32 / expect32_at / expect32_abs / expect_end: guard macros
work/patches/include/charmap.inc    character-code constants (CH_A, CH_LC_A, FW_A, ...) from work/tools/charmap_en.tsv
work/patches/include/charmap.tbl    armips table file for `.string` (generated: `asmpatch.py tbl`)
work/patches/<fix>/fix.toml         why/what/decisions, `asm = "<fix>.asm"`, [[code]] regions / [[string]] entries, [[grow]]
work/patches/<fix>/<fix>.asm        the armips source: the single source of the new bytes
work/patches/<fix>/<fix>.listing    its disassembly snapshot: every edit, old -> new (generated; see below)
work/patches/expected.toml          hashes of the default full build (check.py --full; see Checks)
```

A fix's `[[code]]` entries declare the regions the source may change (`file`, `offset` in the file, `expect` = the original bytes). They do not hold the new bytes. They are there so the registry can be checked without armips or a ROM (`fixes.py check`: overlaps between fixes, and every `.open` of the source is a declared file at its load address), and so FIXES.md can list what each fix touches.

A strings fix (kind `strings`, today only `outfit-chooser-strings`) declares `[[string]]` entries instead: the slot (`file`, `offset`, `max_units`), the Chinese it holds (`zh`), the English (`en`), the pointer words that reference it (`pointers`) and the longest English the consumer takes when relocated (`reloc_max_units`). The slot must change and the pointers may. **Where the English lives:** in both places, on purpose. Translators edit `en` in fix.toml and the text checks (`text_consumer_check.py`, `text_safety_check.py`, through `hardcoded.load()`) read it there, with the Chinese next to it; the `.asm` writes the same text literally (`.string "Outfit 1"`), like a hand-written hack. Two checks keep them equal: `fixes.py check` (and every registry load) requires the source's `.string` literals to be exactly the entries' `en` values, and the build reads every entry back after assembling (the string its pointers, or its slot, lead to must be `en` with its `0xFFFF` end, in place within `max_units`, relocated within `reloc_max_units`). Generating the asm from fix.toml was rejected: the source would no longer be human-written, and the bytes would have two authors.

A fix may grow an overlay only by appending, and only an overlay it declares in `[[grow]]` (`file = "overlay58"`, `max` in bytes). The build refuses growth past `max`, a size that is not a multiple of 4, an overlay with `.bss`, and another overlay that starts in the grown range (one that also overlaps the overlay's current image can never be loaded with it, so it does not count). When the grown image is written back, `RomView` sets the overlay's `ramSize` in the y9 table. A source appends under `.org <old end>` with the `expect_end` guard, so it grows from the hack's original end. Whether an English string is written in place or relocated is decided in the `.asm`, not by the build: if a new `en` no longer fits its slot (or a relocated one would now fit), change the source too (move the `.string` to the appended block and repoint, or back); otherwise the build refuses (the string read back is not `en`, or it overflows `max_units`).

A source looks like this (from `namelen.asm`):

```asm
.nds
.thumb
.include "../include/guards.inc"

TRAINER_NAME_LEN equ 7

.open "overlay49.bin", 0x021E4980       ; load address from work/patches/overlays.toml

.org 0x021E49CE                         ; RAM address
.area 2                                 ; the edit must not grow
    expect16 0x2305                     ; guard: the original instruction, mov r3, #5
    mov     r3, #TRAINER_NAME_LEN
.endarea

.close
```

A strings source looks like this (from `outfit-chooser-strings.asm`, shortened):

```asm
.nds
.include "../include/guards.inc"
.loadtable "../include/charmap.tbl", "UTF-8"     ; .string: game character codes, 0xFFFF end

.definelabel OutfitChooser_Outfit1Label,    0x021E8AB6   ; +0x6F6: u16[4] 形象1
.definelabel OutfitChooser_OutfitLabels,    0x021E8B80   ; +0x7C0: u16 *[3], list items 1, 2, 3
.definelabel Overlay58_End,                 0x021E8BA0   ; +0x7E0: end of the hack's overlay

.open "overlay58.bin", 0x021E83C0
.org OutfitChooser_OutfitLabels
.area 3 * 4
    expect32_at 0, OutfitChooser_Outfit1Label   ; guard: the old pointer
    ...
    .word Outfit1Label_EN, Outfit2Label_EN, Outfit3Label_EN
.endarea

.org Overlay58_End                                ; appended: fix.toml [[grow]]
.area 64
    expect_end                                    ; guard: the overlay still ends here
Outfit1Label_EN:
    .string "Outfit 1"
    ...
    .align 4, 0xFF
.endarea
.close
```

`charmap.tbl` is generated from `work/tools/charmap_en.tsv`, the Gen-4 font charmap from pret/pokeheartgold (`python3 work/tools/asmpatch.py tbl`; `test_asmpatch.py` checks it is current byte for byte, and `.gitattributes` keeps it, the `.asm` and the `.inc` files at LF line endings). It holds table lines only: armips table files have no comment syntax, so its provenance is here and in the `asmpatch.py tbl` docstring. armips writes a table entry's hex digits as bytes in the order given, so each u16 code is written little-endian (`2B01=A` for 0x012B); where several codes share a character the lowest is used, as `msgtool` encodes it; `/FFFF` is the terminator `.string` appends (`.stringn` writes none). A character missing from the table stops armips (`Failed to encode`). Tested with armips v0.11.0: 16-bit entries, the terminator and UTF-8 characters work. Write `.string "text"` with one literal per line: `fixes.py check` refuses the multi-argument forms (`.string "a", 0`, `.string "a", "b"`), because it compares each literal with a `[[string]]` `en`.

Conventions:

- **Binaries:** `arm9.bin` (load address `0x02000000`), `itcm.bin` (the ARM9 autoload section copied to ITCM, load address `0x01FF8000`) and `overlayNN.bin` (load address from `work/patches/overlays.toml`, the y9 table of the Chinese ROM), decompressed, overlay numbers of the hack (Japanese base; the USA and pret numbers differ).
- **Addresses** are RAM addresses: `.org 0x021E49CE`, not file offsets. `.headersize`, `.create` and `.createfile` are refused (`fixes.py check`): a source only patches the staged binaries, at the load address of its `.open`.
- **Header:** line 1 is `; <fix-id> - <title>. <decisions>`; the leading comment lines name every decision of fix.toml (or, when it lists none, the pending decision).
- **Guards:** every edit starts with a guard on the bytes it replaces (`expect16`, `expect32`, or a macro built on `expect16_at` / `expect32_at` such as the keyboard's `keys_were_1to7` / `keys_were_8to13` or the PC box's `window_was`); appended data starts with `expect_end`. A guard reads the file on disk, which still holds the original bytes while armips assembles; on a mismatch armips stops with `guard failed at <address>: expected …, found …` and writes nothing.
- **`.area`** around every edit, so it can never grow into the next code; one `.area` per `.org`.
- **Lines** of at most 120 characters (a long row of data is split over several `.halfword` lines).

`fixes.py check` (and every registry load, so the build too) enforces these statically; see "Checks" below.
- **Syntax:** armips v0.11.0 takes pre-UAL THUMB syntax: `mov r3, #7` (not `movs`), `add r5, r0, #0` (not `adds`). Check each instruction's encoding against the bytes you expect (`asmpatch.py listing <fix>`).
- **Names** are case-insensitive in armips, so lower-case letters in `charmap.inc` are `CH_LC_A`…, full-width ones `FW_A`….

## Native code (text speed)

One fix adds C code: `text-speed` (work/patches/text-speed). Its parts:

- `native.c` + `labels.h`: the new Thumb routines (print task, frame measurement, printer catch-up, the Options row, the call printer). Original project code.
- `payload.json`: the reviewed compiler output, `{source_sha256, base, code, symbols}`: the bytes to place at `0x01FF8620` and each routine's address. `work/tools/text_speed_patch.py` links it from the clang object itself (no linker: `.text`, then `.rodata`, each 4-aligned, then `.bss`, so the zeroed 26-byte frame state is the block's tail; only `R_ARM_ABS32` and payload-internal `R_ARM_THM_CALL` relocations), and pins its canonical sha256 (`REVIEWED_PAYLOAD_SHA256`) separately from the file. Normal builds use payload.json and need no compiler; `text_speed_patch.py --check-payload` (a release gate, also `test_cached_payload_reproduces_from_source`) recompiles and requires the same bytes and symbols.
- **Compiler pin:** Apple clang 21.0.0 (`clang-2100.0.123.102`, Xcode toolchain, macOS), flags `-target arm-none-eabi -march=armv5te -mthumb -Os -Wall -Werror -ffreestanding -fno-builtin -fno-unwind-tables -fno-asynchronous-unwind-tables -c`. Another clang may produce other bytes; then the reproduction gate fails, and a new payload needs review (below).
- `text-speed.asm`: every ROM edit, like any other fix. It `.incbin`s the payload (`"../native/text-speed.bin"`: the build writes payload.json's bytes there after `text_speed_patch.load_payload()` validated them: schema, source digest, pin) at the end of `itcm.bin`, names each payload symbol with `.definelabel` (the address with the Thumb bit clear; `fixes.py check` compares them with payload.json; a Thumb pointer is written `label + 1`, a `bl label` needs the even address), and writes the hooks: the game loop's frame-end call, the printer task pointer, the new-game default, the music-speed masks, the SDK ITCM arena start, the Options overlay 50 (seventh row: 40 field offsets, row counts, positions, calls, its tables appended) and the overlay 92 call printer. Each edit is guarded by its original bytes.
- fix.toml declares its regions (overlay 50 as one SHA-1-pinned region: `length` + `expect_sha1`, since it is rewritten in ~100 places) and `[[grow]]` overlay 50 and `itcm`, and `[native]` (source, headers, payload, the checking module).
- Before assembling, build.py runs `text_speed_patch.precheck()`: the hack's base ARM9 (with the other fixes' arm9 regions put back to `expect`), the ITCM section and overlays 50/92 equal the reviewed images (sha256), and no other selected fix touches a byte text speed edits, overlays 50/92, or the original routines and data the payload calls or relies on (`DEPENDENCIES`, derived by a capstone traversal, re-derived by the tests). After writing, `text_speed_patch.receipt()` records the hashes (and checks that msgload's demand-loading fix is in place) and `verify()` checks the runtime contract in the written ROM.

**ITCM growth.** `itcm.bin` is staged from ndspy `loadArm9()` (the section at `0x01FF8000`) and written back through `RomView.set("itcm")`, which rebuilds the ARM9 file with ndspy `save(compress=False)`: the main section, the autoload sections and their table, and the two code-settings words that point at that table (autoload list start and end, ARM9 `+0xBA0`/`+0xBA4`). asmpatch writes arm9 before itcm and then refuses any other main-section difference from the assembled `arm9.bin`. A grown ITCM block must stay a multiple of 4, have no .bss and end at or below `0x01FFA000` (`fixes.ITCM_LIMIT`, the RC's reserve below the rest of ITCM's arena); the asm aligns its end to 32 bytes and points the SDK arena there.

**Why `.incbin` and not `.importobj`.** armips v0.11.0 can link the clang object directly (`.importobj "native.o"` assembles, and its symbols become labels), but it lays the sections out in section-header order with their natural alignment (`.text`, `.bss`, `.rodata` for this object: the frame state lands at `0x01FF8B7C` instead of the block's tail at `0x01FF8BC0`), so it cannot produce the reviewed payload without changing native.c (and its review). The payload stays the reviewed artifact, placed with `.incbin`.

**Changing native.c:** `python3 work/tools/text_speed_patch.py --compile work/build/text-speed/payload.json` compiles a candidate and prints its `.definelabel` lines; after review, replace payload.json, `REVIEWED_PAYLOAD_SHA256` and the labels in text-speed.asm together, and rerun the text-speed release gates (work/notes/text_speed_RUNBOOK.md).

## How the build applies them

`build.py` stage 3c, `asmpatch.apply()`, for every selected fix of kind strings, data or code (strings first, then data and code, as in FIXES.md):

1. Reads the decompressed `arm9` and overlay images it needs through `hardcoded.RomView` and checks each region's original bytes (`expect`; for a string its encoded `zh` and its pointers' old target).
2. Stages them in a temp folder as `<tmp>/rom/arm9.bin`, `<tmp>/rom/itcm.bin`, `<tmp>/rom/overlayNN.bin` (and a `[native]` fix's payload bytes as `<tmp>/native/<fix>.bin`), next to a copy of `work/patches/include` (`<tmp>/include`). armips resolves `.open` and `.include` paths against its **working directory** (not the source's folder), and runs in `<tmp>/rom`; that is why sources say `.open "arm9.bin"` and `.include "../include/guards.inc"`.
3. Runs `armips -erroronwarning -temp <listing> <fix>.asm` once per enabled fix, in build order. The listing gives the address of every assembled line; a byte the source writes twice (the later write would win silently) stops the build.
4. After each run, compares every staged file with its state before: a changed byte outside the fix's regions, a required region left unchanged, a size change other than `[[grow]]` growth (above), or a file created or removed stops the build. A strings fix is then read back against its `en`.
5. Writes the changed images back through `RomView` (which updates a grown overlay's y9 `ramSize`, and rebuilds the ARM9 file around a grown ITCM section, see "Native code"); the verify stage (`asmpatch.verify`) re-reads the written ROM: file hashes, overlay sizes, strings and pointers, code regions.

To assemble one fix by hand, copy the decompressed binaries into a folder next to a copy of `include/` and run armips from that folder. Keep that folder out of the repo: the binaries are game data (`*.bin` under `work/patches/` is git-ignored as a safety net).

Commands:

```sh
python3 work/tools/check.py [--full]                                  # all checks (see "Checks" below)
ARMIPS=/path/to/armips python3 work/tools/asmpatch.py check          # assemble every enabled fix (dry run)
ARMIPS=/path/to/armips python3 work/tools/asmpatch.py listing namelen # the disassembly snapshot of one fix
ARMIPS=/path/to/armips python3 work/tools/asmpatch.py listing --write # (re)write every snapshot
ARMIPS=/path/to/armips python3 work/tools/usref.py                    # check every [[us_ref]] against the USA ROM
python3 work/tools/asmpatch.py tbl                                    # regenerate include/charmap.tbl
python3 work/tools/fixes.py check                                     # registry, regions, .open lines, .string = en,
                                                                      # asm lint; no armips
```

## Proof of equivalence and golden hashes

Until 2026-10-08 the code and data fixes were halfword patches (`expect` → `value`) and the outfit-chooser strings were written by `hardcoded.py`, both in Python. The armips sources replaced them in two steps, and each step was proven byte-identical before the Python path was removed: the ROM built with either engine had the same SHA-1, in full and with each fix alone (`build.py --only <fix> --no-patch`), and the assembled binaries were compared byte for byte in memory. The Python engine and its frozen values (`work/tools/legacy_code_patches.toml`) are gone; the hashes of the proven run are what is checked now.

| Build | ROM SHA-1 |
|---|---|
| full (xdelta `0241fd9f2ed48f5db4e025b8199b8a6b8f2bdb5b`) | `2a052d2f2d78f04596352797fd501cdad4c6381e` |
| `--only outfit-chooser-strings --no-patch` | `9ca23ec71658abddff0ff8ce20787e0405c982c0` |
| `--only namelen --no-patch` | `3328d49d201e0f88371bf0de1443649f2dfb4f66` |
| `--only naming-keyboard --no-patch` | `4738e3c0fe4a5c54addb061a05343e53028d473e` |
| `--only msgload --no-patch` | `55a0ffc8293cf7ca04d1612efd74c3efaf7f3544` |
| `--only pcbox-name-width --no-patch` | `f2637eca68680cb4d7a2540252338e51a1d279d5` |
| `--only ivev-panel --no-patch` | `ee868d1878d6d55db35090e139e212daf88dd215` |

Then the text-speed release candidate (`codex/text-speed-research` fb5fa7e, with the anti-piracy bypass) was ported in two steps on branch `refactor/patches-rc`: first merged as it was (antipiracy as an armips fix; text speed still applied by `text_speed_patch.apply()` as a build stage of its own), then text speed as the armips source above. Each step built the same bytes as the release candidate's own build of fb5fa7e (its runbook, `build_cached.py`, built twice), and the full text-speed runtime gate suite passed on the step-1 ROM (releasable, the same results as the RC's run rc4; the step-2 ROM is the same file):

| Build (2026-10-08) | ROM SHA-1 |
|---|---|
| full (xdelta `588b931f97774fa5f35f19aa1cc821f79de86385`) | `35e67a5f53b9a05e62ea8b38d2c73a4268001102` (sha256 `91cc299e…`, the RC's) |
| `--only text-speed,msgload --no-patch` | `50676fea5dba10601f9b458399d72bcf5de712b9` |
| `--without text-speed --no-patch` (= the RC's `--no-text-speed`) | `139e252258bd41bb31fae4ebbc2515fd365130e1` |
| `--only antipiracy --no-patch` | `64dfa83282456548d11d3a3c16f703bf88900558` |

Fixes added after these runs were written as armips sources from the start; each was proven against a build of its original form:

| Build (2026-10-08) | ROM SHA-1 |
|---|---|
| `overworld-texture-frame-bounds` (Rocket HQ freeze): full, = develop `dfe8ba2` + its `code_patches.json` entry (worktree `codex/rocket-hq-freeze`); xdelta `427c0ec160187cdb28a9c30353d47ba9f9b51691` | `df28a14ff92de9169bf5d4b8613136ab1207cf72` |
| `--without overworld-texture-frame-bounds` (= the develop full build above, xdelta `0241fd9f…`) | `2a052d2f2d78f04596352797fd501cdad4c6381e` |
| `refactor/patches-rc` full, with `overworld-texture-frame-bounds` (xdelta `71d44f915f8a4a11863ceb43e703fd32914bb45a`): the RC's ROM with only the one arm9 byte changed | `fa34e72444401d7a966cc751cdbab0e54dad8d7c` |
| `refactor/patches-rc` `--without overworld-texture-frame-bounds` (= the RC's, xdelta `588b931f…`) | `35e67a5f53b9a05e62ea8b38d2c73a4268001102` |

These depend on the workspace text at the time (2026-10-08, branches `refactor/fix-format` and `refactor/patches-rc`); a translation change moves them. The per-binary golden SHA-1s in `test_asmpatch.py` (`GOLDEN`: every binary each fix changes, alone and all together, plus the y9 overlay table) do not depend on the text, so the test suite checks them on every run that has armips and the Chinese ROM. A change to a fix source that changes its bytes must update `GOLDEN` and say why.

## Checks

`python3 work/tools/check.py` is the one entry point (`work/tools/check.py` docstring; the repo's pre-commit hook `.githooks/pre-commit` runs it on the staged files when the shared `.git/hooks/pre-commit` dispatches to it, see CONTRIBUTING.md → Checks: never set `core.hooksPath`, it would switch off the identity guard). Every step prints PASS / FAIL / SKIP and its time; the exit status is non-zero when a step failed.

| Step | Fast (default) | `--full` |
|---|---|---|
| `registry`: `fixes.py check`, including the asm lint below | yes | yes |
| `fixes-md`: `work/patches/FIXES.md` equals `fixes.py docs` | yes | yes |
| `ruff`: `ruff check` with `ruff.toml`, the version pinned in `work/tools/requirements-dev.txt` | yes (SKIP with a note when ruff is not installed) | yes (required) |
| `tests`: every `work/tools/test_*.py` | armips hidden; ROM tests run only if the ROM is there | with armips: GOLDEN |
| `prereq`: armips v0.11.0, both ROMs, `xdelta3` | – | required |
| `asmpatch`: `asmpatch.py check` against the Chinese ROM | – | yes |
| `listings`: every fix's disassembly snapshot is current (`asmlisting.py`, capstone pinned) | – | yes |
| `us-refs`: every `[[us_ref]]` holds in the USA ROM (`usref.py`) | – | yes (SKIP without the USA ROM; `prereq` already requires it) |
| `build`: `build.py --work-dir work/build/check`, hashes against `work/patches/expected.toml` | – | yes |

Timings on the reference machine (2026-10-08): fast about 6 s (the staged run too; `--registry-only` under a second), full about 30-40 s (the build 23 s; `listings` and `us-refs` together under a second, they share one assembly of every fix).

**The asm lint** (`fixes.lint_asm`, no armips, no ROM) reads a fix source as armips does as far as the rules need: it follows `.include` for macros and `equ` constants, expands macro invocations with their arguments, and classifies each statement as a write (an instruction or a data directive such as `.halfword`, `.word`, `.string`, `.fill`, `.align`, `.incbin`), a guard, or neither; an unknown directive is reported rather than guessed. A guard is an `.if` that reads the patched file: `readu8/16/32(outputname(), …org()…)` checks the bytes at the current address (`expect16`, `expect32`, `expect16_at`, `expect32_at` and macros built on them), `filesize(outputname())` is the end guard (`expect_end`), and a read at an absolute address (`expect32_abs`, e.g. the keyboard's `keyboard_row`) is a read-only check that guards nothing. The rules, each reported as `<fix>/<file>.asm:<line>` (the line of the macro invocation, plus `macro line <file>:<line>` for a statement inside a macro):

- **header**: line 1 is `; <fix-id> - …`, and the leading comment lines (up to the first `;` line) name every decision of fix.toml, or a D-id when fix.toml lists none (the pending decision). Catches a source copied from another fix, or a decision added to fix.toml but not to the source.
- **area**: every write is inside an `.area`, no `.area` comes before an `.org`, each `.area` is the first after its `.org`, no `.org` inside an `.area`, every `.area` is closed. Catches an edit that could silently grow into the next code (armips stops only at an `.area` overflow).
- **guard**: the first write of every `.area` has a guard since its `.org` (before the `.area` or inside it). Catches an edit that would patch whatever bytes are there. It checks that a guard exists, not that it covers every byte (the build's `expect` check and the region check cover that).
- **region**: an `.area` lies inside the regions fix.toml declares in the opened file (`[[code]]` regions, `[[string]]` slots and pointer words; adjacent regions count together), computed from the `.org` and `.area` expressions (numbers, `equ`, `.definelabel`; anything else is reported as unresolvable); an appended area (`expect_end`) needs a `[[grow]]` of that file. An `.org` block that only reads (the overworld fix's read-only guard of the whole routine) may be anywhere. Catches an `.area` larger than its region or an `.org` off its region before armips runs (the build still compares every byte after assembling).
- **length**: no line of a fix source or of `work/patches/include/*.inc` is longer than 120 characters.
- **includes**: an include file (the shared `work/patches/include/*.inc` and any file a fix includes from its own folder) may only define macros, `equ` constants and `.definelabel` labels; the lint reads includes for these definitions only, so a statement there (a write, an `.org`, a guard) would escape the other rules and is refused. A missing include is reported.
- **syntax**: `/* */` block comments are refused (the lint reads `;` and `//` comments), and so is an `.area` whose size is zero or negative.

Tests: `test_fixes.py` → `AsmLint`, each rule positive and negative, plus every checked-in source clean.

**Disassembly snapshots** (`work/patches/<id>/<id>.listing`, `asmlisting.py`). Every armips fix has a committed text file that shows each `.area` of its source: the file, offset and RAM address, the region it lies in, the old bytes (the Chinese ROM) and the new ones (the source assembled alone over the Chinese ROM), disassembled by capstone in the mode the source assembles that area in (`.thumb` / `.arm`; Thumb bytes as halfwords, ARM bytes as words, branch targets named by the source's labels). Data areas are shown as what each statement writes: u16 rows with their characters for strings and keyboard rows (`'|'` is the 0xFFFF end), u32 words with the label a pointer names, bytes for window templates; a rewritten row whose values stay the same is shown once as context; appended data has only `+` rows; a native payload (`.incbin`) is its size, SHA-256 and the labels inside it, not a disassembly. Code areas get up to 4 bytes of unchanged context on each side (cut where the fix changes other bytes, widened so a Thumb `bl` pair is never split; an ARM context word that points into RAM is shown as `.word`, a literal pool entry, not as the conditional instruction capstone would make of it); an `.org` block that only guards (the overworld fix's check of the whole routine) is shown as unchanged context, and the words read by absolute guards (`expect32_abs`: the keyboard's pointer table, the outfit chooser's literal) are listed. That is all of the ROM a snapshot holds: the bytes fix.toml (`expect`) and the guards already name, plus the context. A snapshot is regenerated, never edited: `python3 work/tools/asmpatch.py listing --write [<id>...]` (needs armips, the Chinese ROM and capstone at the version pinned in `work/tools/requirements-dev.txt`; another version may print an instruction differently, so it is refused). `check.py --full` (the `listings` step) regenerates every snapshot in memory and fails on any difference, naming the first differing line and the command; a change to a source, an include, armips or capstone that moves a byte or a mnemonic therefore shows up in review as a diff of the snapshot. `asmpatch.py listing --check` runs the same check alone. FIXES.md links each snapshot. Tests: `test_asmlisting.py` (disassembly, context and data rows on synthetic images; with armips and the ROM: the committed snapshots are current, and a changed source makes its snapshot stale).

**USA cross-checks** (`[[us_ref]]` in fix.toml, `usref.py`). Sources and fix.toml often cite the USA ROM: the same call site with the US value, the table the fix copies, the function a hack routine corresponds to. Such a citation is written `US <file> 0x<RAM address>` or `US <file>+0x<file offset>` with the USA overlay number (`US arm9 0x020431D6`, `US overlay43 0x0222CD5C`, `US overlay14+0x12BB4`), and fix.toml states the claim in a `[[us_ref]]`: `id`, `claim` (one line, the citation and what it says), `file`, `address` or `offset`, and what is there, one of
- `expect`: the USA bytes themselves, a few halfwords (`"230A F7F1 FF87"`: `mov r3, #10` and the `bl` to CreateArgs);
- `new`: a `[[code]]` region of this fix: the USA ROM holds exactly the bytes the fix writes there ("the same instruction with #7", "the same table");
- `hack` + `length`: a Chinese-ROM location (`"arm9 0x02083814"`, `"overlay14+0x4BBC8"`) with the same original bytes ("the same function prologue", "the same layout around the copied tiles");
- for a NARC (`file = "a/1/5/2"`): `members` (and `lz10 = true` to compare them decompressed): the same members as the Chinese ROM.

The fast registry check (`fixes.py check`) refuses a citation without its `[[us_ref]]` and any hex number of 4+ digits after `US`/`USA` in the same clause (up to `;`, `)`, `. ` or the line end) that is not written as a citation, so a free-form USA address cannot slip in; the USA source of a `code_from_us` graphics op counts as backed (the build checks those bytes by SHA-1). `check.py --full` (the `us-refs` step, `python3 work/tools/usref.py` alone) checks every claim against the USA ROM and prints the bytes it found when one is wrong; it skips with a note when the USA ROM is missing. Only `expect` puts USA bytes into git, and only the cited halfwords; `new`, `hack` and NARC claims compare the USA ROM with bytes already in the sources or in the Chinese ROM. pret names (`NamingScreen_HandleCharacterInput`, `NAME_SCREEN_UNK7`) stay in the comments and claims as names; there is no pret checkout to check them against. Tests: `test_usref.py` (the citation lint and the schema, the check on synthetic images, and with the ROMs every real claim plus the two citations that were wrong before (kind 7 at 0x0222CD5A, the PC box templates at overlay14+0x12C42)).

**Expected hashes** (`work/patches/expected.toml`, per branch): the per-binary GOLDEN SHA-1s in `test_asmpatch.py` cover only the armips binaries, so `--full` also builds the whole ROM and compares four SHA-1s. `nontext_sha1` covers every ROM part except the two message NARCs (arm9, arm7, overlay tables, banner, every other file): what the fixes, graphics and code produce. It does not depend on the message banks, but it does contain the English of the hardcoded strings (outfit-chooser-strings writes its `[[string]]` en into overlay 58), so changing that English moves it. `text_sha1` covers the two message NARCs, and `rom_sha1` / `xdelta_sha1` are what is released. `--full` fails only when `nontext_sha1` differs; the other three move with every translation change, so it reports them as notes (and says whether the text or the bytes outside it moved), and fails on them only with `--strict-release` (for a release build). After an intended change, record the new hashes in the same commit after reviewing the build: `python3 work/tools/check.py --full --update-expected`. The file belongs to its branch (`refactor/patches-rc` builds other bytes than `refactor/fix-format`): when merging one branch into another, keep the target's file and rerun `--update-expected` there if the merge changed the build.

**ruff** (`ruff.toml`, pinned in `work/tools/requirements-dev.txt`) checks every Python file under `work/` with pycodestyle errors and warnings, pyflakes, bugbear and import order. The toolchain files (`fixes.py`, `asmpatch.py`, `build.py`, `check.py` and their tests) get every rule, line length 120; the older tools, audits and research scripts keep their compact style (per-file ignores of the style-only rules: line length, one-line statements, ambiguous names, import order, unused loop variables, closures over loop variables, `zip()` without `strict=`), while the bug-finding rules (undefined names, unused imports and variables, mutable defaults, …) apply to every file. `ruff format` is not enforced.

