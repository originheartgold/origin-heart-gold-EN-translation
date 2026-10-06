# Native text speed release candidate — 2026-10-05

Current revision: [SLOW / MEDIUM / FAST](text_speed_readable_rc6.md). This document records the earlier candidate.

**Current status:** the three review findings are resolved in the [rebuilt candidate and fix report](text_speed_fixes.md). The evidence below describes the superseded initial candidate. The user requires old-save → new-ROM upgrades; downgrades are out of scope.

Worktree: `/private/tmp/poke-text-speed-research`, branch `codex/text-speed-research`, base `0121c30`. This implements the earlier [feasibility research](text_speed_research.md). All ROMs, saves, screenshots, traces and patches remain ignored under `work/build/text-speed/`. Nothing was merged or published.

## Player behavior

Options has a seventh row: **TEXT SPEED — NORMAL / FAST / INSTANT**. NORMAL is the default for existing valid saves and new games and calls the original Chinese printer task. FAST batches up to three glyphs per task; INSTANT batches up to 128. Page prompts, scrolling and explicit timing controls still use the original renderer. INSTANT reveals a page promptly; it does not advance pages automatically. Callback-driven printers and printers with a nonzero explicit glyph delay keep original pacing in every mode.

The native menu supports buttons and touch, Confirm and Cancel. Existing font, palette, arrow and button assets are reused. Music speed remains a separate option. No translated bank or graphic asset was changed for this feature.

The RC4 demand-loading instruction at `0200BA9A` stays `0125`. Loading one requested message and rendering glyphs are separate operations; the feature does not restore whole-bank loading.

## Implementation and compatibility

- `work/patches/text_speed/native.c` and `labels.h` are original project code. The checked-in `payload.json` contains compiled project code, not extracted ROM content. Apple clang 21.0.0 reproduces it exactly. Normal builds use the cached payload and do not require clang.
- `work/tools/text_speed_patch.py` guards the entire reviewed ARM9, ITCM and Options overlay before changing anything. The ARM9 pin is the untouched Chinese hack's main section: every enabled arm9 patch in `work/translate/hardcoded/code_patches.json` must hold exactly its `expect` or `value` bytes and is put back to `expect` before hashing, so new reviewed code patches elsewhere in ARM9 (e.g. D-1574) do not need a new pin. A code patch that overlaps any ARM9 byte text speed edits, lies outside the main section, or targets overlay 50 fails closed; the demand-loading fix (`msgload-all`) is the one required patch, read but never edited. Text speed is an optional English-community feature, a deliberate exception to D-1002 (D-1575). Unknown binaries, stale source/payload pairs and double application fail closed. The payload occupies 732 bytes and extends the original ITCM section from `01FF8620` to the aligned `01FF8900`; the SDK ITCM arena lower bound is raised accordingly. Main RAM, main BSS, and DTCM placement stay unchanged.
- Overlay 50 grows to hold relocated menu tables. Its allocation, row metadata, navigation bounds, drawing positions, touch hitboxes and both touch mapping pointer aliases are updated together. The original six settings retain their indexes.
- The two-byte Options record uses bits 0–1 for MUSIC SPEED and bits 2–3 for TEXT SPEED (0 NORMAL, 1 FAST, 2 INSTANT; 3 falls back to NORMAL). The original music getter/setter previously used a four-bit nibble for three values. Both now mask only two bits. Audited callers are the audio updater and Options overlay; no pointer references to either function were found in the reviewed ARM9/overlays. The unchanged initializer clears the whole nibble, establishing NORMAL for new games.
- Confirm updates text bits before menu data is freed; Cancel preserves the saved value. Other option bits are preserved. No save structure or checksum format changes.
- **Downgrades:** existing saves load with NORMAL. Before taking a save made with FAST/INSTANT back to an older ROM without this feature, select NORMAL and save in-game. Older Options code interprets all four music bits as its music selection. This candidate does not claim backward compatibility for saves carrying a nonzero text-speed value.

`build.py` enables the feature after hardcoded patches; `--no-text-speed` omits it. `--no-hardcoded` also omits it because demand loading is a prerequisite. The build verifies hardcoded edits before composing the patch, retains that stage's hashes, then checks all hardcoded strings/pointers/instructions and final hashes after writing. Native payload, final ARM9, Options data/layout and the demand-loading instruction are checked separately. Xdelta is reapplied and compared byte-for-byte through the build's hash check.

## Validation completed

Artifact: `work/build/text-speed/full-build/origin_hg_v4.0.3_en_wip.nds`

SHA-256: `78a19fbc9431bbddc0802cde1d587db2149cd69518199223263e53a77fa65ad2`

Distribution candidate: `work/build/text-speed/full-build/Origin_HeartGold_v4.0.3_EN_wip.xdelta`, against the established USA base. The patch reapplies successfully; the ROM is not a distribution artifact.

- Full clean build: 73,981 main-bank strings, 2,881 battle strings, font glyphs, 165 graphics members plus one code range, four hardcoded strings and 25 code patches verified. Trainer-name compression verification also passes.
- 23 unit tests run across text-speed, hardcoded and build-path suites: 21 pass, two existing hardcoded tests skip because their fixed worktree ROM path is absent. The full build independently verifies hardcoded output. Native tests exercise real local ROM guards, round-trip persistence, unchanged unrelated files, heap-fix preservation, payload reproducibility, and detection of changed ARM9/overlay bytes or overlay layout metadata.
- Native same-checkpoint dialogue runs: the same 54-glyph page spans 54/25/2 emulated frame intervals for NORMAL/FAST/INSTANT. Each run has 136 heap walks with no corruption, rejected allocation/text request, or null write. These are glyph timing intervals, not wall-clock or hardware benchmarks. Some screenshot names in these research runs were optimistic: their `battle.png` is still dialogue, not evidence of battle entry.
- `persistence2`: old save defaults to NORMAL; selecting INSTANT then Cancel preserves NORMAL; FAST Confirm survives menu reopen, an actual in-game save and emulator reset/Continue. 364 heap walks, no observed memory faults. An earlier run stopped on the emulator's `.dsv` export API; the successful test uses the emulator's ordinary battery-save file and reset instead.
- `instant-persistence`: INSTANT Confirm survives an actual save, reset and Continue on the clean build (Options remains 520). All 246 heap walks pass, with no heap-table/probe errors, allocation failures, null writes, or text rejections. Options heap 38 has at least 140,884 bytes of recorded allocation headroom in this run.
- `full-runtime`: the clean build selects INSTANT, prints both trainer-dialogue pages, transitions into battle and reaches move selection during play. 357 heap walks, no observed memory faults. This is one single-trainer encounter, not coverage of every battle script.
- `control-runtime2`: an authored isolated message tests explicit page prompts, newline, scrolling, a 60-frame pause, and SIZE 200 / SIZE 100 restoration. First and final pages remain waiting after 240 additional idle frames. The pause separates glyph batches by 63 frame intervals. 306 heap walks, no observed memory faults. The fixture ends with an explicit page prompt; end-of-string alone does not invent one.
- `held-buttons`: 120-frame A and B holds followed by idle periods retain explicit page boundaries, and a subsequent press advances the scrolling fixture. 209 heap walks pass with no heap-table/probe errors or observed memory faults. This is a bounded input smoke test, not every held-button/battle combination.
- `music-regression`: MUSIC SPEED 1/4 remains value 2 while switching FAST → INSTANT → NORMAL. Saved Options values 522 then 514 preserve the music bits. 235 heap walks, no observed memory faults.
- `options-regression`: button-driven frame selection and battle-background selection persist alongside text speed; 252 heap walks, no observed memory faults. Its snapshot named `music` actually changed the battle-background row; the separate music regression above is the music evidence.
- `full-menus`: all seven existing bag, party, Pokédex, trainer card, Pokégear, Options and save-prompt scenarios pass against the untouched Chinese ROM with original saves (zero findings).
- `full-summary`: existing summary regression passes, including skills page, switching Pokémon and move swapping, using the naturally saved FAST value. The Chinese audio updater treats that unused music value as normal; this run does not exercise Chinese Options with the new bits.

Runtime instrumentation is read-only: it records constructors, glyphs, menu state and heap checks. The native tests do not use register-changing acceleration hooks. Earlier native-v1/v3 experiments found menu pointer/metadata mistakes; they were corrected before native-v5 and are not release evidence. The exploratory `probe.py` remains historical only.

## Reproduce

Run commands from the worktree root, with the existing Python environment that provides ndspy and py-desmume. No downloads are needed.

```sh
TEXT_SPEED_TEST_ROM=/path/to/existing-demand-loaded-English.nds python -m unittest work/tools/test_text_speed_patch.py work/tools/test_hardcoded.py work/tools/test_build_paths.py -v
python work/tools/build.py --rom /path/to/origin_v4.0.3_cn.nds --base /path/to/HeartGold-USA.nds --extract /path/to/extract/v4 --work-dir work/build/text-speed/full-build --keep-export
python work/research/text_speed/control_fixture.py work/build/text-speed/full-build/origin_hg_v4.0.3_en_wip.nds work/build/text-speed/control-fixture/game.nds
```

`native_probe.py OUT ROM SAVE 'commands'` runs an isolated emulator with screenshots and `report.json`; all output must be under this worktree's `work/build`. Useful commands are `fieldboot`, `boot`, `press A 1`, `wait 239`, `touch X Y`, `shot NAME`, `reset`. Use pauses between repeated key presses. The fixture replaces only bank 718 entry 160 in an ignored candidate, never a translation source. The saved trainer checkpoint faces that trainer. On this machine DeSmuME requires macOS app initialization outside the restricted sandbox.

## Release sign-off still required

This is a tested native release candidate, not a claim of universal hardware validation. Before publishing, play-test on the target DS/flashcart and a second emulator, including held A/B, long sessions, wild/double battles, battle endings and unusual sound/callback-driven dialogue. Callback and explicit-delay text deliberately retains original timing. Save downgrade compatibility has the limitation above. No hardware or second-emulator result is implied by the DeSmuME checks. melonDS is installed locally, but its independent UI check could not proceed: computer-use reported pending macOS Accessibility/Screen Recording permissions, and the retry timed out. No second-emulator pass is claimed.
