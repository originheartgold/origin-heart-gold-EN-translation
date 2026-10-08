# Rocket HQ freeze reproduced — 2026-10-08 (D-2043)

> **Status (2026-10-08, later):** "Preserve it under D-1002/D-1337" below was written before the fix was requested. The fix is now `work/patches/overworld-texture-frame-bounds/` and is in normal builds (see "Ported to the per-fix format" in [rocket_hq_freeze_fix_20261008.md](rocket_hq_freeze_fix_20261008.md)). The user requested the fix; the exception to D-1337 is not yet recorded in the register (D-2043 still says "preserve under D-1337") and must be recorded by the user before release.

The reported Rocket HQ freeze reproduces in melonDS 1.1 on macOS ARM64 with Abdil's correct battery save. Released English rc5, current English WIP, and untouched Chinese v4.0.3 all enter the same ARM9 data-abort loop at map 247, position (17,4), before the camera ambush at (23,4). This is an original-hack failure exposed by this emulator configuration, not an English translation regression. Preserve it under D-1002/D-1337.

## Correct input and reproduction

Use `Downloads/Origin_HeartGold_v4.0.3_EN_v1.0.0-rc5.sav` (524288 bytes), SHA-256 `ee32cbb4ecba965b4de02b5bd7ed3dba33d85a6f18fc8c2b154fcc357b97978b`. The trainer is Abdi (with a smile glyph), 14 badges, 113:37 played. Continue starts in Rocket HQ, map 247 at (13,4).

The previously supplied `Origin_HeartGold_v4.0.3_EN_v1.0.0-rc55.dsv` is a different save: Yuri in a Pokémon Center, map 246 at (8,14). It is excluded from this comparison.

1. Copy the correct battery save alongside the test ROM with the same basename and `.sav` extension.
2. Open the ROM in melonDS 1.1; use Continue from a fresh boot.
3. Walk right from (13,4). The game freezes at (17,4), before reaching the camera trigger.
4. Save an emulator state for CPU inspection. Additional input and elapsed emulation do not move the English WIP out of the abort loop (two separate snapshots agree).

Test configuration: DS mode, direct boot, built-in BIOS, JIT disabled, software 3D renderer with threading enabled, cheats disabled. Normal game inputs only; no teleporting, flag editing, or ROM/battery modifications. Tests used copies; all four supplied original battery save hashes were checked unchanged afterward.

## Comparison

| ROM | melonDS 1.1 | DeSmuME 0.9.12 |
| --- | --- | --- |
| Untouched Chinese v4.0.3 | Freeze at (17,4), same abort signature | Passes the position and reaches camera double battle |
| English WIP | Freeze at (17,4), same abort signature | Passes the position and reaches an interactive battle menu |
| Released English rc5 | Freeze at (17,4), same abort signature | Not tested in this run |

Luke's named `.dsv` also starts at (13,4) and passed into the camera battle in English WIP on DeSmuME. The other hash-named save was inspected but not runtime-tested. Earlier DeSmuME-only attempts therefore did not exercise the emulator that exposes the crash. Neither completing the battle nor saving after it was verified; the user-reported transfer-save workaround is not independently confirmed here. Five Island and other reported locations remain untested.

ROM identity:

| ROM | SHA-256 |
| --- | --- |
| `work/rom/origin_v4.0.3_cn.nds` | `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8` |
| `work/build/origin_hg_v4.0.3_en_wip.nds` | `6fa7b4e739391ca9ea9bfcf90d83eec6407c3c04102e52432bb41bc8ae44a7d3` |
| Local released rc5 | `39d79e78dfa8a6ac192690283bc08cc73628266772eb47aac5fca5a9c0e9ec9e` |

The local release ROM is named `Downloads/Origin_HeartGold_v4.0.3_EN_v1.0.0-rc55.nds`, but its SHA-1 `6eecb13762af6893ba1ffeebb9142976f51807a5` matches `work/release/v1.0.0-rc5/latest.json`'s patched ROM hash. Its identity is established by the hash, not the filename. No ROM was built or downloaded for this test.

## CPU evidence and remaining uncertainty

All four melonDS snapshots (CN, WIP twice, rc5) have:

- Location `(247, -1, 17, 4, 3)`.
- CPSR `0x60000097` (abort mode), saved R15 `0xFFFF0108`, current instruction `0xEAFFFFFE` (branch to self).
- Abort LR `0x0202469E`, locating the faulting Thumb instruction at `0x02024696`: `ldr r0,[r0]`.

State layout and abort-PC interpretation were checked against [melonDS 1.1 ARM implementation](https://github.com/melonDS-emu/melonDS/blob/1.1/src/ARM.cpp), specifically `DoSavestate` and `DataAbort`. Saved R15 includes pipeline adjustment and is not presented as the address of the looping instruction itself.

Read-only execution hooks in DeSmuME observed R0 = 0 immediately before the same load in both Chinese and English, while that emulator continued. In the melonDS *post-abort* snapshots R0 is `0xC`; these observations are at different execution points and should not be conflated.

The preceding code appears to look up a texture dictionary entry: R1 points to a `TEX0` block, R2 is 4, R3 is 1, and the out-of-range branch supplies a zero pointer before the load. Nearby resource data contains `sppoke4.1`. This suggests a model/texture binding problem, but the exact offending asset and why the lookup requests that index are **not yet established**. The runtime comparison proves the failure exists in the untouched hack; it does not establish that every emulator or hardware configuration will fail.

## Local evidence

Ignored directory: `work/build/rocket-repro-20261008/`.

- `inputs.json`, `roms.json`: original-save and ROM identities.
- `abdi_correct_en.ml1`, `abdi_correct_en.ml2`, `abdi_correct_cn.ml1`, `abdi_rc5.ml1`: melonDS crash states.
- `inspect_states.py`, `state_report.json`: state parser and decoded CPU/location evidence.
- `abdi_correct_en_desmume/` and `abdi_correct_cn_desmume/`: screenshots, camera/battle states, and read-only register observations (`null_reads.json` / `low_reads.json`).
- `luke_named_en_desmume/`: comparison screenshots and states.

Game data and emulator states remain local and ignored. No game logic or translation changes were made.

## Release-note wording

Known original-hack issue (D-2043): walking east through Rocket HQ B1F can freeze on melonDS before the camera ambush. Reproduced with the same save in untouched Chinese v4.0.3 and English rc5/WIP. DeSmuME passed this point in testing; a complete post-battle workaround has not been verified.
