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

- **Binaries:** `arm9.bin` (load address `0x02000000`) and `overlayNN.bin` (load address from `work/patches/overlays.toml`, the y9 table of the Chinese ROM), decompressed, overlay numbers of the hack (Japanese base; the USA and pret numbers differ).
- **Addresses** are RAM addresses: `.org 0x021E49CE`, not file offsets. `.headersize`, `.create` and `.createfile` are refused (`fixes.py check`): a source only patches the staged binaries, at the load address of its `.open`.
- **Header:** line 1 is `; <fix-id> - <title>. <decisions>`; the leading comment lines name every decision of fix.toml (or, when it lists none, the pending decision).
- **Guards:** every edit starts with a guard on the bytes it replaces (`expect16`, `expect32`, or a macro built on `expect16_at` / `expect32_at` such as the keyboard's `keys_were_1to7` / `keys_were_8to13` or the PC box's `window_was`); appended data starts with `expect_end`. A guard reads the file on disk, which still holds the original bytes while armips assembles; on a mismatch armips stops with `guard failed at <address>: expected …, found …` and writes nothing.
- **`.area`** around every edit, so it can never grow into the next code; one `.area` per `.org`.
- **Lines** of at most 120 characters (a long row of data is split over several `.halfword` lines).

`fixes.py check` (and every registry load, so the build too) enforces these statically; see "Checks" below.
- **Syntax:** armips v0.11.0 takes pre-UAL THUMB syntax: `mov r3, #7` (not `movs`), `add r5, r0, #0` (not `adds`). Check each instruction's encoding against the bytes you expect (`asmpatch.py listing <fix>`).
- **Names** are case-insensitive in armips, so lower-case letters in `charmap.inc` are `CH_LC_A`…, full-width ones `FW_A`….

## How the build applies them

`build.py` stage 3c, `asmpatch.apply()`, for every selected fix of kind strings, data or code (strings first, then data and code, as in FIXES.md):

1. Reads the decompressed `arm9` and overlay images it needs through `hardcoded.RomView` and checks each region's original bytes (`expect`; for a string its encoded `zh` and its pointers' old target).
2. Stages them in a temp folder as `<tmp>/rom/arm9.bin`, `<tmp>/rom/overlayNN.bin`, next to a copy of `work/patches/include` (`<tmp>/include`). armips resolves `.open` and `.include` paths against its **working directory** (not the source's folder), and runs in `<tmp>/rom`; that is why sources say `.open "arm9.bin"` and `.include "../include/guards.inc"`.
3. Runs `armips -erroronwarning -temp <listing> <fix>.asm` once per enabled fix, in build order. The listing gives the address of every assembled line; a byte the source writes twice (the later write would win silently) stops the build.
4. After each run, compares every staged file with its state before: a changed byte outside the fix's regions, a required region left unchanged, a size change other than `[[grow]]` growth (above), or a file created or removed stops the build. A strings fix is then read back against its `en`.
5. Writes the changed images back through `RomView` (which updates a grown overlay's y9 `ramSize`); the verify stage (`asmpatch.verify`) re-reads the written ROM: file hashes, overlay sizes, strings and pointers, code regions.

To assemble one fix by hand, copy the decompressed binaries into a folder next to a copy of `include/` and run armips from that folder. Keep that folder out of the repo: the binaries are game data (`*.bin` under `work/patches/` is git-ignored as a safety net).

Commands:

```sh
python3 work/tools/check.py [--full]                                  # all checks (see "Checks" below)
ARMIPS=/path/to/armips python3 work/tools/asmpatch.py check          # assemble every enabled fix (dry run)
ARMIPS=/path/to/armips python3 work/tools/asmpatch.py listing namelen # old -> new bytes of one fix
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

Fixes added after that run were written as armips sources from the start; each was proven against a build of its original form:

| Build (2026-10-08) | ROM SHA-1 |
|---|---|
| `overworld-texture-frame-bounds` (Rocket HQ freeze): full, = develop `dfe8ba2` + its `code_patches.json` entry (worktree `codex/rocket-hq-freeze`); xdelta `427c0ec160187cdb28a9c30353d47ba9f9b51691` | `df28a14ff92de9169bf5d4b8613136ab1207cf72` |
| `--without overworld-texture-frame-bounds` (= the full build above, xdelta `0241fd9f…`) | `2a052d2f2d78f04596352797fd501cdad4c6381e` |

These depend on the workspace text at the time (2026-10-08, branch `refactor/fix-format`); a translation change moves them. The per-binary golden SHA-1s in `test_asmpatch.py` (`GOLDEN`: every binary each fix changes, alone and all together, plus the y9 overlay table) do not depend on the text, so the test suite checks them on every run that has armips and the Chinese ROM. A change to a fix source that changes its bytes must update `GOLDEN` and say why.

## Checks

`python3 work/tools/check.py` is the one entry point (`work/tools/check.py` docstring; the pre-commit hook `.githooks/pre-commit` runs it on the staged files, see CONTRIBUTING.md → Checks). Every step prints PASS / FAIL / SKIP and its time; the exit status is non-zero when a step failed.

| Step | Fast (default) | `--full` |
|---|---|---|
| `registry`: `fixes.py check`, including the asm lint below | yes | yes |
| `fixes-md`: `work/patches/FIXES.md` equals `fixes.py docs` | yes | yes |
| `ruff`: `ruff check` with `ruff.toml`, the version pinned in `work/tools/requirements-dev.txt` | yes (SKIP with a note when ruff is not installed) | yes (required) |
| `tests`: every `work/tools/test_*.py` | armips hidden; ROM tests run only if the ROM is there | with armips: GOLDEN |
| `prereq`: armips v0.11.0, both ROMs, `xdelta3` | – | required |
| `asmpatch`: `asmpatch.py check` against the Chinese ROM | – | yes |
| `build`: `build.py --work-dir work/build/check`, hashes against `work/patches/expected.toml` | – | yes |

Timings on the reference machine (2026-10-08): fast about 6 s (the staged run too), full about 30 s (the build 23 s).

**The asm lint** (`fixes.lint_asm`, no armips, no ROM) reads a fix source as armips does as far as the rules need: it follows `.include` for macros and `equ` constants, expands macro invocations with their arguments, and classifies each statement as a write (an instruction or a data directive such as `.halfword`, `.word`, `.string`, `.fill`, `.align`, `.incbin`), a guard, or neither; an unknown directive is reported rather than guessed. A guard is an `.if` that reads the patched file: `readu8/16/32(outputname(), …org()…)` checks the bytes at the current address (`expect16`, `expect32`, `expect16_at`, `expect32_at` and macros built on them), `filesize(outputname())` is the end guard (`expect_end`), and a read at an absolute address (`expect32_abs`, e.g. the keyboard's `keyboard_row`) is a read-only check that guards nothing. The rules, each reported as `<fix>/<file>.asm:<line>` (the line of the macro invocation, plus `macro line <file>:<line>` for a statement inside a macro):

- **header**: line 1 is `; <fix-id> - …`, and the leading comment lines (up to the first `;` line) name every decision of fix.toml, or a D-id when fix.toml lists none (the pending decision). Catches a source copied from another fix, or a decision added to fix.toml but not to the source.
- **area**: every write is inside an `.area`, no `.area` comes before an `.org`, each `.area` is the first after its `.org`, no `.org` inside an `.area`, every `.area` is closed. Catches an edit that could silently grow into the next code (armips stops only at an `.area` overflow).
- **guard**: the first write of every `.area` has a guard since its `.org` (before the `.area` or inside it). Catches an edit that would patch whatever bytes are there. It checks that a guard exists, not that it covers every byte (the build's `expect` check and the region check cover that).
- **region**: an `.area` lies inside the regions fix.toml declares in the opened file (`[[code]]` regions, `[[string]]` slots and pointer words; adjacent regions count together), computed from the `.org` and `.area` expressions (numbers, `equ`, `.definelabel`; anything else is reported as unresolvable); an appended area (`expect_end`) needs a `[[grow]]` of that file. An `.org` block that only reads (the overworld fix's read-only guard of the whole routine) may be anywhere. Catches an `.area` larger than its region or an `.org` off its region before armips runs (the build still compares every byte after assembling).
- **length**: no line of a fix source or of `work/patches/include/*.inc` is longer than 120 characters.

Tests: `test_fixes.py` → `AsmLint`, each rule positive and negative, plus every checked-in source clean.

**Expected hashes** (`work/patches/expected.toml`, per branch): the per-binary GOLDEN SHA-1s in `test_asmpatch.py` cover only the armips binaries, so `--full` also builds the whole ROM and compares four SHA-1s: `nontext_sha1` (every ROM part except the two message NARCs: arm9, arm7, overlay tables, banner, every other file; what the fixes, graphics and code produce, independent of the text), `text_sha1` (the two message NARCs), and `rom_sha1` / `xdelta_sha1` (what is released). A change to the translation text moves `text_sha1`, `rom_sha1` and `xdelta_sha1` but not `nontext_sha1`; the failure message says which of the two happened. Whoever changes the text or a fix records the new hashes in the same commit after reviewing the build: `python3 work/tools/check.py --full --update-expected`. The file belongs to its branch (`refactor/patches-rc` builds other bytes than `refactor/fix-format`): when merging one branch into another, keep the target's file and rerun `--update-expected` there if the merge changed the build. Translators do not run `--full` (the pre-commit hook runs the fast check, and only for commits that touch the tools or the fixes), so a text-only commit leaves `expected.toml` stale until the next `--full`, which then says so.

**ruff** (`ruff.toml`, pinned in `work/tools/requirements-dev.txt`) checks every Python file under `work/` with pycodestyle errors and warnings, pyflakes, bugbear and import order. The toolchain files (`fixes.py`, `asmpatch.py`, `build.py`, `check.py` and their tests) get every rule, line length 120; the older tools, audits and research scripts keep their compact style (per-file ignores of the style-only rules: line length, one-line statements, ambiguous names, import order, unused loop variables, closures over loop variables, `zip()` without `strict=`), while the bug-finding rules (undefined names, unused imports and variables, mutable defaults, …) apply to every file. `ruff format` is not enforced.

