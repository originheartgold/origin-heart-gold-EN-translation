# Toolchain: armips for the code and data fixes

**Status (2026-10-08): current.** The code and data fixes in `work/patches/` are armips sources. The build assembles them with **armips v0.11.0**; nothing else outside Python is needed for them.

## Why armips

The hack is a binary hack of the Japanese HeartGold, so the pret decompilation cannot build it. The code and data fixes are small edits to the hack's own `arm9` and overlays (an immediate, a branch, keyboard rows, window templates), so they are written the way ROM hackers write such edits ([hg-engine](https://github.com/BluRosie/hg-engine) style): an armips `.asm` file per fix that opens the binary at its RAM load address, goes to the RAM address with `.org` and writes the instruction or data in mnemonic form, with a comment.

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

The build finds armips in this order: `build.py --armips PATH`, the `ARMIPS` environment variable, `armips` on `PATH`. It runs it with no arguments and requires the banner `armips assembler v0.11.0`; any other version stops the build. Without armips, `build.py --code-engine python` still builds the same ROM from the frozen Python patches (below), for as long as that engine is kept.

## Layout

```
work/patches/include/guards.inc     expect16 / expect16_at / expect32_at / expect32_abs: guard macros
work/patches/include/charmap.inc    character codes (CH_A, CH_LC_A, FW_A, ...) from work/tools/charmap_en.tsv
work/patches/<fix>/fix.toml         why/what/decisions, `asm = "<fix>.asm"`, and [[code]] regions
work/patches/<fix>/<fix>.asm        the armips source: the single source of the new bytes
```

A fix's `[[code]]` entries declare the regions the source may change (`file`, `offset` in the file, `expect` = the original bytes). They do not hold the new bytes. They are there so the registry can be checked without armips or a ROM (`fixes.py check`: overlaps between fixes, and every `.open` of the source is a declared file at its load address), and so FIXES.md can list what each fix touches.

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

Conventions:

- **Binaries:** `arm9.bin` (load address `0x02000000`) and `overlayNN.bin` (load address from `work/patches/overlays.toml`, the y9 table of the Chinese ROM), decompressed, overlay numbers of the hack (Japanese base; the USA and pret numbers differ).
- **Addresses** are RAM addresses: `.org 0x021E49CE`, not file offsets. `.headersize`, `.create` and `.createfile` are refused (`fixes.py check`): a source only patches the staged binaries, at the load address of its `.open`.
- **Guards:** every edit starts with a guard on the bytes it replaces (`expect16`, or a macro built on `expect16_at` / `expect32_at` such as the keyboard's `keys_were` or the PC box's `window_was`). A guard reads the file on disk, which still holds the original bytes while armips assembles; on a mismatch armips stops with `guard failed at <address>: expected …, found …` and writes nothing.
- **`.area`** around every edit, so it can never grow into the next code.
- **Syntax:** armips v0.11.0 takes pre-UAL THUMB syntax: `mov r3, #7` (not `movs`), `add r5, r0, #0` (not `adds`). Check each instruction's encoding against the bytes you expect (`asmpatch.py listing <fix>`).
- **Names** are case-insensitive in armips, so lower-case letters in `charmap.inc` are `CH_LC_A`…, full-width ones `FW_A`….

## How the build applies them

`build.py` stage 3c, `asmpatch.apply()` (`--code-engine armips`, the default):

1. Reads the decompressed `arm9` and overlay images it needs through `hardcoded.RomView` (the same path the strings stage uses, so the ROM is written back identically) and checks each region's `expect` bytes.
2. Stages them in a temp folder as `<tmp>/rom/arm9.bin`, `<tmp>/rom/overlayNN.bin`, next to a copy of `work/patches/include` (`<tmp>/include`). armips resolves `.open` and `.include` paths against its **working directory** (not the source's folder), and runs in `<tmp>/rom`; that is why sources say `.open "arm9.bin"` and `.include "../include/guards.inc"`.
3. Runs `armips -erroronwarning -temp <listing> <fix>.asm` once per enabled fix, in build order. The listing gives the address of every assembled line; a byte the source writes twice (the later write would win silently) stops the build.
4. After each run, compares every staged file with its state before: a changed byte outside the fix's regions, a declared region left unchanged, a file that changed size, or a file created or removed stops the build.
5. Writes the changed images back through `RomView`; the verify stage reads the regions back.

To assemble one fix by hand, copy the decompressed binaries into a folder next to a copy of `include/` and run armips from that folder. Keep that folder out of the repo: the binaries are game data (`*.bin` under `work/patches/` is git-ignored as a safety net).

Commands:

```sh
ARMIPS=/path/to/armips python3 work/tools/asmpatch.py check          # assemble every enabled fix (dry run)
ARMIPS=/path/to/armips python3 work/tools/asmpatch.py listing namelen # old -> new bytes of one fix
python3 work/tools/fixes.py check                                     # registry, regions, .open lines; no armips
```

## The legacy Python engine (transition)

Before 2026-10-08 the code and data fixes were halfword patches applied in Python (`expect` → `value` in fix.toml). Their values are frozen in `work/tools/legacy_code_patches.toml` (as of commit c99993d), and `build.py --code-engine python` (also `hardcoded.py check --code-engine python`) still applies them. `test_asmpatch.py` assembles every source and compares the result with the Python engine byte for byte, per fix and all together, and the full and per-fix builds of both engines give the same ROM:

| Build | ROM SHA-1 (both engines) |
|---|---|
| full (xdelta `0241fd9f2ed48f5db4e025b8199b8a6b8f2bdb5b`) | `2a052d2f2d78f04596352797fd501cdad4c6381e` |
| `--only namelen --no-patch` | `3328d49d201e0f88371bf0de1443649f2dfb4f66` |
| `--only naming-keyboard --no-patch` | `4738e3c0fe4a5c54addb061a05343e53028d473e` |
| `--only msgload --no-patch` | `55a0ffc8293cf7ca04d1612efd74c3efaf7f3544` |
| `--only pcbox-name-width --no-patch` | `f2637eca68680cb4d7a2540252338e51a1d279d5` |
| `--only ivev-panel --no-patch` | `ee868d1878d6d55db35090e139e212daf88dd215` |

The legacy file and engine are to be deleted once the armips engine is accepted; a fix added after the freeze exists only as armips source and refuses `--code-engine python`.
