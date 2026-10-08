# Native text speed: release notes

Status: final review of d115c71 passed. Gates and fault matrix are in [text_speed_release_checks.md](text_speed_release_checks.md); the frame rule is in [text_speed_vcount.md](text_speed_vcount.md). Everything below the "History (superseded)" heading describes earlier candidates and is kept as a record only.

## What ships

- **TEXT SPEED row.** Options gets a seventh row with NORMAL and FAST (D-1604). Stored value 1 is FAST; 0, 2 and 3 all read as NORMAL. Confirm writes 0 or 1. Existing saves read as NORMAL; new games start on FAST.

  | Stored | Shown | Where it comes from |
  | --- | --- | --- |
  | 0 | NORMAL | every existing save, choosing NORMAL |
  | 1 | FAST | new games, choosing FAST |
  | 2, 3 | NORMAL | unreleased test saves, corrupt data |

  Before the save is published (title screen, new-game intro) the payload has no Options record and uses NORMAL. Cancel keeps the stored value. Labels are project-authored in the existing English font (NORMAL at x 108, FAST at x 188).
- **NORMAL** is the hack's original printer. **FAST** prints up to three letters per frame when the frame has room, never slower than NORMAL and never dropping more frames (measured frame rule, D-1601). Callback printers and printers with an explicit glyph delay keep their original pacing per task.
- **30 fps printer catch-up (D-1603), at every setting.** In maps where the hack's game loop runs at 30 fps (most towns and routes), text printers get one extra turn per missed screen refresh. Text prints at vanilla FAST's one letter per frame instead of one per two frames (measured about 2.0 to about 1.0 frames per letter in Viridian, Route 30, Cherrygrove and Violet; vanilla US FAST 0.98). Side effect: pauses counted in printer turns (callback and explicit-delay printers, auto-advance waits) last vanilla length in those scenes, about half the hack's.
- **Pokégear calls wait for A/B on every page**, also right after a battle (D-1600). The hack's battle code leaves auto-advance on (D-1599). Other text shown right after a battle may still auto-advance; D-1599 stays open for those.
- **Anti-piracy bypass for real hardware (D-1616, D-1617).** Six overlay114 checks return the genuine-cartridge result. No change on emulators or genuine cartridges. Not tested on any real console or flashcart.
- **Payload.** Native payload 1466 bytes, ITCM end `01FF8BE0`. The checked-in `payload.json` is compiled project code; Apple clang reproduces it, normal builds use the cached payload. Text speed is an optional English-community feature, a deliberate exception to D-1002 (D-1575).

## Changes from the Chinese hack

1. TEXT SPEED option (NORMAL / FAST) with FAST as the default for new games.
2. 30 fps printer catch-up, and the shortened printer-turn pauses that come with it.
3. Pokégear calls wait for A/B on every page, including right after a battle.
4. Anti-piracy bypass (six overlay114 checks) for real hardware.

## Downgrade warning

Text speed shares the old 4-bit options field (bit 2; MUSIC SPEED keeps bits 0-1). A save made with this version and taken back to the Chinese hack or an older English patch may carry an unusual MUSIC SPEED value. Before downgrading, set TEXT SPEED to NORMAL and save. Old-save to new-ROM upgrades are the supported direction.

## Known gaps and risks

- Automated emulator gates ran in DeSmuME only for this build. No melonDS or other second-emulator pass was made for it (an earlier melonDS attempt on the old candidate stopped on macOS permissions).
- No hardware test, of the text speed or of the anti-piracy bypass.
- Not covered by gates: cutscenes, intro and credits, radio and TV, mail, the naming screen.
- The frame rule was calibrated in DeSmuME only.
- The short-history floor of the frame rule is verified by code path only, not by a run.
- Other text right after a battle may still auto-advance (D-1599).

## Evidence

Final run at d115c71: `work/build/text-speed/rc4`. Full suite releasable; 664 unit tests; 25 faults detected by their declared gates; 1 fault (`no-state-stop`) targets code proven unreachable (the batching loop's state-field stop; RenderText disassembly in text_speed_release_checks.md). Details per gate are in [text_speed_release_checks.md](text_speed_release_checks.md).

## Reproduce

Run commands from the worktree root, with the existing Python environment that provides ndspy and py-desmume. No downloads are needed.

```sh
TEXT_SPEED_TEST_ROM=/path/to/existing-demand-loaded-English.nds python -m unittest work/tools/test_text_speed_patch.py work/tools/test_hardcoded.py work/tools/test_build_paths.py -v
python work/tools/build.py --rom /path/to/origin_v4.0.3_cn.nds --base /path/to/HeartGold-USA.nds --extract /path/to/extract/v4 --work-dir work/build/text-speed/full-build --keep-export
python work/research/text_speed/control_fixture.py work/build/text-speed/full-build/origin_hg_v4.0.3_en_wip.nds work/build/text-speed/control-fixture/game.nds
```

`native_probe.py OUT ROM SAVE 'commands'` runs an isolated emulator with screenshots and `report.json`; all output must be under this worktree's `work/build`. Useful commands are `fieldboot`, `boot`, `press A 1`, `wait 239`, `touch X Y`, `shot NAME`, `reset`. Use pauses between repeated key presses. The fixture replaces only bank 718 entry 160 in an ignored candidate, never a translation source. The saved trainer checkpoint faces that trainer. On this machine DeSmuME requires macOS app initialization outside the restricted sandbox.


## History (superseded)

Everything below is the record of earlier candidates (NORMAL / FAST / INSTANT, SLOW / MEDIUM / FAST, RC6) and is out of date where it disagrees with the sections above. The payload sizes and ITCM addresses in it are stale (current: 1466 bytes, ITCM end `01FF8BE0`). The guard rules under "Implementation and compatibility" still apply. The worktree it names, `/private/tmp/poke-text-speed-research`, no longer exists.

## Native text speed release candidate — 2026-10-05

Current revision: **NORMAL / FAST** (D-1604, 2026-10-07): see "Current design" below; gates and fault matrix in [text_speed_release_checks.md](text_speed_release_checks.md), frame rule in [text_speed_vcount.md](text_speed_vcount.md). The SLOW / MEDIUM / FAST revision ([text_speed_readable_rc6.md](text_speed_readable_rc6.md)) and the NORMAL / FAST / INSTANT candidate recorded further down are historical.

### Current design (D-1604)

- **TEXT SPEED** has two choices, **NORMAL** and **FAST**. NORMAL is the hack's original printer task (one glyph per printer turn, no batching) plus the 30 fps printer catch-up (D-1603), so text prints at the vanilla FAST rate (about one glyph per frame) in 60 fps and 30 fps maps. FAST batches up to three glyphs per printer task under the measured frame rule (D-1601), plus the catch-up. Callback-driven printers and printers with an explicit glyph delay use the original task at both speeds.
- **Stored value** (bits 2-3 of the two-byte Options record; music speed keeps bits 0-1):

  | Stored | Shown | Prints as | Where it comes from |
  | --- | --- | --- | --- |
  | 0 | NORMAL | NORMAL | every existing save (the bits were always 0), choosing NORMAL |
  | 1 | FAST | FAST | new games (the Options initialiser), choosing FAST |
  | 2 | NORMAL | NORMAL | unreleased SLOW/MEDIUM/FAST-era test saves (old FAST), corrupt data |
  | 3 | NORMAL | NORMAL | unreleased test saves (old reserved value), corrupt data |

  Before the save is published (title screen, new-game intro) the payload has no Options record and uses NORMAL. Opening Options on an unknown value shows NORMAL; Cancel keeps the stored value, Confirm stores 0 (NORMAL) or 1 (FAST).
- **Options row:** two labels, NORMAL at x 108 and FAST at x 188 (the label pitch and touch columns of the two-choice rows 2 and 3: boxes x 112-167 and 192-247 on the row's y 146-166). The labels are project-authored in the existing English font.
- **ARM9 edits** since D-1604: the private printer extension (allocation 0x34 to 0x38 and the `init_printer` wrapper that cleared the SLOW phase byte) is gone; the printer constructor is unchanged. Remaining edits: print task pointer, game-loop `pass_end` call, SDK ITCM arena bound, new-game default (FAST), music getter/setter masks. Native payload 1418 bytes (26 of them the frame state), ITCM `01FF8620`-`01FF8BC0`.

**Current status:** the three review findings are resolved in the [rebuilt candidate and fix report](text_speed_fixes.md). The evidence below describes the superseded initial candidate. The user requires old-save → new-ROM upgrades; downgrades are out of scope.

Worktree: `/private/tmp/poke-text-speed-research`, branch `codex/text-speed-research`, base `0121c30`. This implements the earlier [feasibility research](text_speed_research.md). All ROMs, saves, screenshots, traces and patches remain ignored under `work/build/text-speed/`. Nothing was merged or published.

### Player behavior

Options has a seventh row: **TEXT SPEED — NORMAL / FAST / INSTANT**. NORMAL is the default for existing valid saves and new games and calls the original Chinese printer task. FAST batches up to three glyphs per task; INSTANT batches up to 128. Page prompts, scrolling and explicit timing controls still use the original renderer. INSTANT reveals a page promptly; it does not advance pages automatically. Callback-driven printers and printers with a nonzero explicit glyph delay keep original pacing in every mode.

The native menu supports buttons and touch, Confirm and Cancel. Existing font, palette, arrow and button assets are reused. Music speed remains a separate option. No translated bank or graphic asset was changed for this feature.

The RC4 demand-loading instruction at `0200BA9A` stays `0125`. Loading one requested message and rendering glyphs are separate operations; the feature does not restore whole-bank loading.

### Implementation and compatibility

Historical: the first three bullets were updated on 2026-10-06 to match the SLOW / MEDIUM / FAST code of that day (superseded by D-1604, see "Current design" above; the guard rules they describe still apply). The rest of this document, including the validation evidence, describes the superseded NORMAL / FAST / INSTANT candidate.

- `work/patches/text-speed/native.c` and `labels.h` are original project code. The checked-in `payload.json` contains compiled project code, not extracted ROM content. Apple clang 21.0.0 reproduces it exactly. Normal builds use the cached payload and do not require clang.
- `work/tools/text_speed_patch.py` checks these before changing anything:
  - **ARM9 main section:** its SHA-256 must equal the untouched Chinese hack's main section after every arm9 `[[code]]` region of the other selected fixes (`work/patches/*/fix.toml`; until 2026-10-08 `code_patches.json`) is put back to its `expect` bytes. Each such region must hold exactly its `expect` bytes or the bytes the armips stage wrote (the build passes them from its report). So new reviewed code patches elsewhere in ARM9 (e.g. D-1574) need no new pin, but the digest does not say which of our patches are present; the build's hardcoded verification checks those.
  - **Code patches near text speed fail closed:** a code patch fails the build if it overlaps a byte text speed edits, lies outside the main section, targets overlay 50 or 92, or overlaps a reviewed dependency (`DEPENDENCIES` in the script). The dependencies are the full bodies of the original ARM9 routines that `native.c` calls, including the routines two trampolines tail-call; the glyph-render path the batching loop relies on (RenderText entry `02002E40` and its control-code state machine `020022D0`–`020027EE`, whose two jump tables are decoded by hand in `REVIEWED_SWITCHES`); the routines containing the edits (printer constructor, Options init, music getter and setter, and the game loop NitroMain, whose last call before its VBlank wait goes through `frame_end`); the SDK arena table; and the code-settings words that `code.save()` rewrites. Extents come from a recursive capstone disassembly of the base ARM9, which refuses any computed jump other than those reviewed tables, and `test_text_speed_patch.py` re-derives them, checks each start is a real routine entry and checks that every `FN()` call target in `native.c` is covered. A call to an unreviewed routine fails closed. `verify()` applies the same overlap rule.
  - **Demand loading:** the fix (`msgload-all`, `0x2501` at `0200BA9A`) is the one required code patch. It is read and never edited, and is missing if the patch is still at `expect`.
  - **ITCM, Options overlay and Pokégear overlay:** their exact SHA-256 values are pinned (overlay 92 is byte-identical in the Chinese hack and the English build).
  - **Not covered:** other ARM9 bytes are covered only by the base digest. A code patch elsewhere that changes behaviour text speed relies on indirectly is not detected.

  Text speed is an optional English-community feature, a deliberate exception to D-1002 (D-1575). Unknown binaries, stale source/payload pairs and double application fail closed. The native payload is 1240 bytes (24 of them the zero-initialised frame state) and extends the original ITCM section from `01FF8620` to the aligned `01FF8B00` (updated 2026-10-07, [frame-aware batching](text_speed_vcount.md)); the SDK ITCM arena lower bound is raised accordingly. The game loop's last call before its VBlank wait (`0x02000DE0`) is redirected through the payload's `frame_end`, which makes that call and then measures the end of the frame. Main RAM, main BSS, and DTCM placement stay unchanged. With the phone-call wrapper (D-1600, 2026-10-07) the payload is 1466 bytes (26 of them the frame state) and the ITCM section ends at the aligned `01FF8BE0`.
- **Phone calls wait for A/B (D-1600, bug D-1599):** the hack's battle overlay sets the renderer to auto-scroll (`SetAutoScrollParam(3)`; flag byte `021106CE`, bit 2 auto, bit 5 auto with A/B) and, unlike the US game, never clears it at battle exit. Field message boxes clear it, but the Pokégear sets no auto flag, so after a battle every call page advanced by itself after 101 frames. The Pokégear call-page printer (overlay 92 `021F11E8`, used by outgoing calls and by incoming calls alike) has one `AddTextPrinterParameterized` call at `021F1228`; text speed redirects that BL to the native `call_print`, which calls `SetAutoScrollParam(0)` (clears bits 2 and 5, as the field box does) and then forwards all eight arguments and the return value unchanged. It leaves the A/B speed-up bit and the touch-advance bit alone (the Pokégear sets touch itself at call start and clears it at call end). The wrapper does not read the text-speed value, so it applies at NORMAL, FAST and the reserved values alike. Other overlay 92 text (contact list, menus) is untouched, and other post-battle text that sets no flags of its own still inherits the battle's auto-scroll (D-1599); only calls are fixed.
- Overlay 50 grows to hold relocated menu tables. Its allocation, row metadata, navigation bounds, drawing positions, touch hitboxes and both touch mapping pointer aliases are updated together. The original six settings retain their indexes.
- The two-byte Options record uses bits 0–1 for MUSIC SPEED and bits 2–3 for TEXT SPEED (0 SLOW, 1 MEDIUM, 2 FAST; reserved 3 uses the original printer and shows MEDIUM). Existing saves read as SLOW; new games start at MEDIUM. The original music getter/setter previously used a four-bit nibble for three values. Both now mask only two bits. Audited callers are the audio updater and Options overlay; no pointer references to either function were found in the reviewed ARM9/overlays. The initializer already zeroes the record; its old nibble clear now sets TEXT SPEED to MEDIUM for new games.
- Confirm updates text bits before menu data is freed; Cancel preserves the saved value. Other option bits are preserved. No save structure or checksum format changes.
- **Downgrades:** existing saves load with NORMAL. Before taking a save made with FAST/INSTANT back to an older ROM without this feature, select NORMAL and save in-game. Older Options code interprets all four music bits as its music selection. This candidate does not claim backward compatibility for saves carrying a nonzero text-speed value.

`build.py` applies the feature (fix `text-speed`, `work/patches/text-speed/fix.toml`) after the armips fixes; `--without text-speed` omits it (until 2026-10-08: `--no-text-speed`). It `requires` the `msgload` fix, so `--no-hardcoded` or `--without msgload` alone is refused; demand loading is a prerequisite. The build verifies hardcoded edits before composing the patch, retains that stage's hashes, then checks all hardcoded strings/pointers/instructions and final hashes after writing. Native payload, final ARM9, Options data/layout and the demand-loading instruction are checked separately. Xdelta is reapplied and compared byte-for-byte through the build's hash check.

### Validation completed

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


### Release sign-off still required

This is a tested native release candidate, not a claim of universal hardware validation. Before publishing, play-test on the target DS/flashcart and a second emulator, including held A/B, long sessions, wild/double battles, battle endings and unusual sound/callback-driven dialogue. Callback and explicit-delay text deliberately retains original timing. Save downgrade compatibility has the limitation above. No hardware or second-emulator result is implied by the DeSmuME checks. melonDS is installed locally, but its independent UI check could not proceed: computer-use reported pending macOS Accessibility/Screen Recording permissions, and the retry timed out. No second-emulator pass is claimed.

