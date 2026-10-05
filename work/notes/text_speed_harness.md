# Text speed: integration and harness regression

All work remains on `codex/text-speed-research` in `/private/tmp/poke-text-speed-research`.
The user's primary checkout was on `integration/2026-10-05` (`d0ea7a3`), while
local `main` still pointed to the original base `0121c30`. The primary checkout's
integration branch was merged without conflicts at `ffc9058`, after preserving
the existing feature in `6d925cf`. No primary-checkout files were edited.

## Candidate

Fresh full build: `work/build/text-speed/merged-release/`.
ROM SHA256: `ef9ffc72a3dfd77565cc7f15146eaa544c6e2967f96d2985447f569ab4ebed2e`.
The distributable is `Origin_HeartGold_v4.0.3_EN_wip.xdelta`, against the established
USA base. The xdelta reapplication matches the built ROM. Native payload remains
716 bytes with the previously reviewed digest; no gameplay implementation change
was needed for the merge. Build verification and standalone artifact verification
(including native reproduction) passed.

## New repeatable coverage

The three scripts use the new `work/tools/emu_harness.py` library, explicit ROM
and save paths, private battery storage, and worktree-local ignored outputs.
They hash source ROM/save files before and after execution. Each fails with a
nonzero exit and writes a failed JSON report if an assertion fails.

- `work/research/text_speed/harness_regression.py`: three separate cold boots,
  Options cancel and button Confirm, then six message records across three banks.
  Includes 200%/100% font controls, newline, CLEAR/SCROLL, trailing waits, and a
  message ID above 255. Requires script completion, nonempty pages, the exact
  authored text's glyph count, identical glyph layout and completed text pixels
  across speeds, stable pages without input, and successful heap checks. Scene
  selection is an injected script using the native message renderer; it does not
  claim to reproduce each scene's event context.
- `work/research/text_speed/harness_options.py`: native button/touch input,
  row 0/7 wrap, value wrap in both directions, A on a setting, B cancellation,
  default Quit, Confirm/Quit direction selection, repeated commits and reopening,
  preservation of every unrelated Options bit, and heap checks.
- `work/research/text_speed/harness_fallbacks.py`: ten controlled branch tests,
  using a checkpoint created from the exact candidate and verifying its native
  executable bytes before every restore. Checks initialized Options with the
  cartridge-save flag still zero, invalid mode, transient null runtime pointer,
  legacy music values, and explicit printer delay. Records original-task calls
  and exact relative glyph timing. These deliberate live-RAM/constructor edits
  are controlled path coverage, not natural gameplay or heap certification.

Run from the worktree root with the project's existing Python environment:

```sh
python work/research/text_speed/harness_regression.py --rom /path/to/candidate.nds --save /path/to/trainer.sav --out work/build/text-speed/new-corpus
python work/research/text_speed/harness_options.py --rom /path/to/candidate.nds --save /path/to/trainer.sav --out work/build/text-speed/new-options
python work/research/text_speed/harness_fallbacks.py --rom /path/to/candidate.nds --save /path/to/trainer.sav --out work/build/text-speed/new-fallbacks
```

The corpus fixture uses `trainer.sav`. Its reference messages contain no
scene-dependent text buffers. Regenerate the candidate when those translations
change; glyph-count assertions intentionally detect stale text builds.

## Issues found while adding coverage

The initial button-confirm test selected Quit: the original Chinese menu defaults
its final row to value0 (Quit), and LEFT selects value1 (Confirm). An independent
agent audited the original and patched handlers, touch dispatch, bounds, and
commit state. The feature preserves the original behavior. Tests now explicitly
select and assert Confirm, and separately prove that Quit discards changes.

The shared harness's old `NonNPCMsgVar` command silently truncated message IDs to
8 bits: requested 718#1093 rendered 718#69. This was an actual harness defect,
not a text-speed defect. The new `message_script` helper uses the native
`MsgBoxExtern` command, which preserves the 16-bit ID. Inputs are validated before
emulator mutation. `show_message` now fails if its page budget expires before
script completion and restores the sentinel even on exceptions; unit tests cover
these failure paths. A separate runtime trace confirmed that the native reader
received ID1093, and the first page was visually checked. Earlier screenshots from high-ID requests must not be treated
as coverage of the requested records. The corpus also asserts the expected glyph
count so a wrong record cannot silently pass by rendering consistently in all modes.

## Results and limits

Reports are under `work/build/text-speed/merged-validation/`:

- `corpus-wide/report.json`: all three modes passed six records each (48#20,
  48#26, 48#60, 457#123, 718#160, 718#1093). Each mode rendered 867 dialogue
  glyphs across 21 captured pages. All glyph layouts and completed text crops
  match NORMAL; page waits remain stable without input. Heap checks were
  1,735 / 1,739 / 1,742 (5,216 total), with no reported memory failures.
- `tool-suite-final.json`: 487 tooling tests passed, zero failures/errors/skips.
- `artifact/`: standalone artifact gate passed.
- `native-modes/report.json`: original natural trainer-dialogue regression passed
  on the merged candidate; NORMAL/FAST/INSTANT spans 54/25/2 emulator frame
  intervals, 54 dialogue glyphs each, identical completed text pixels and 257 heap
  checks per mode. Battle startup is included; this is not an extended battle test.
- `options/report.json`: seven groups of menu assertions passed; 490 heap checks,
  no allocation, null-write, heap-corruption, or text-probe failures.
- `fallbacks2/report.json`: all ten controlled cases passed. NORMAL/FAST/INSTANT
  spans 54/33/2; invalid/null/old music have exactly NORMAL's glyph timing. Explicit
  delay3 yields the identical 165-frame glyph span in all three modes, with every
  native task invocation delegating to the original task.

Frame spans describe these runs, not a fixed hardware speed guarantee. Full
second-emulator/hardware testing, extended play and natural callback-driven battle
printers remain outside the demonstrated coverage. Save downgrade support remains
out of scope; valid old battery saves require no preparation before upgrading.

Exploratory `harness-validation*` and the initial `merged-validation/corpus/`
runs are superseded; some were stopped after the ID-truncation discovery. Only
`corpus-wide/report.json` is the completed, corrected corpus release evidence.
