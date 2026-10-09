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

## Harness audit and fail-closed gates — 2026-10-06

The runtime gates were audited claim by claim against a fresh build of this
branch (`e9aedbb1…2d13`, 760-byte payload). Gaps found and closed:

- **No original-printer baseline for real messages.** The corpus only compared
  the three speeds with each other. It now also runs mode 3 (reserved value →
  original task) and requires identical page pixels, glyph count and layout.
- **Cadence was asserted on one page only.** Every corpus, battle, callback/input
  and natural-dialogue message is now judged per native task against the design
  budget (`text_speed_checks.cadence`): never more than the budget. (Superseded:
  the first version also required half of the tasks to use their whole budget;
  that rule is now replaced by a stop reason per task, see the section below.)
- **Battle pauses were recorded, not asserted.** `battle_pacing.py` now replays
  battle start and three turns from shared checkpoints for the original and all
  three speeds, so the same messages print, and requires the pause after each
  completed message and its on-screen dwell to equal the original within 2 frames.
  (Correction: that run was not all identical. One message, "Blazor used
  Scratch!" in turn 3, paused one frame longer at every speed, and that segment was
  shortened by one frame less than the printing saved; the gate's 2n+2 slack hid
  it. The gate is now exact, see below.)
- **Held input never released.** Held A/B cases now release and press once; page 2
  must start with the original's latency. A new tap case taps A throughout. This
  check first caught a harness defect: `release()` followed by `press()` in the
  same frame never gives the game a press edge. `press()` now leaves the key up
  for a frame in that case and refuses to "press" a held key.
- **No English label check.** The Options gates now inspect the TEXT SPEED row in
  screenshots (three labels inside their columns, selected colour, no spill).
- **Memory.** Heap walks only proved integrity. Printer allocations are now paired
  with frees, and per-heap usage may not grow across 24 messages; the ITCM code,
  payload and SDK arena are checked at the end of every session, not only at boot.
- **Non-repeatable timing.** DeSmuME's real-time clock follows the host clock and
  the game reads it at boot, so frame spans changed between runs even with the
  game's clock cache pinned. `Harness(rtc=...)` fixes the emulated RTC through a
  movie recording; repeated runs then match frame for frame.
- **Silent hook replacement.** DeSmuME keeps one exec callback per address.
  Measurement hooks are now registered `exclusive` and a later collision raises.
- **Frame order assumed monotonic.** In 60 fps field scenes the game dropped frames
  while a task rendered two or three glyphs, so FAST could take as many frames as
  MEDIUM, and MEDIUM as many as SLOW. (Superseded: the gates then subtracted "frames
  without a glyph" as lag, which also counted page waits and pauses and excused the
  inversions. The cause was the batch overrunning VBlank: about 10 lines per glyph,
  most of it one lazy cartridge read of the glyph's font data; it is fixed in the
  payload, see [text_speed_vcount.md](text_speed_vcount.md).)

See [the recipe](text_speed_release_checks.md) for the gate table, the single
entry point and the fault fixtures used to prove each check fails when it should.

## Exact gates and the frame rule — 2026-10-07

Second independent review of `35c1a31` and user decision D-1601. Changes:

- **Payload:** the batching loop stops before another glyph when the frame is
  nearly used up (VCOUNT), see [text_speed_vcount.md](text_speed_vcount.md). Payload
  812 bytes, ITCM extension `01FF8620`-`01FF8960`.
- **Per-task stop reasons** replace the "half the tasks at full budget" rule: every
  native task is judged from hooks on the task, render step, glyph and the VCOUNT
  read (`text_speed_checks.task_errors`).
- **Dropped frames** are frames in which the printer's task did not run (the game
  loop missed a VBlank), not frames without a glyph. Frame order is strict in every
  scene; a tie is allowed only when the faster speed hit the frame limit.
- **Exact comparisons:** battle pauses, dwell, last glyph → printer removal and the
  segment shortening are exact; page-2 latency is exact in printer tasks, judged from
  the page prompt's observed input polls (D-2175: last glyph to the first poll, the
  accepting poll to page 2's first glyph; no skipped poll, no latched or lost press),
  not in frames from the press; printer tasks from each page's last glyph to
  its control step are exact (this catches a batch that runs into a control, which no
  gate caught before); the controls pause is exact in printer tasks.
- **Battle pixels** are compared with the original printer.
- **Printers smoke gate** (`printer_smoke.py`): save prompt, sign, PC, phone call.
- **Fail closed:** no `python -O`, `require()` instead of `assert`, clean tree incl.
  untracked files or `passed-not-releasable`, faults must be caught by their
  declared gates with their declared text, slot waits excluded from timeouts.

The old "+1" battle pause was not investigated in this round. (It was later: the
battle waits for its sound, whose clock is not the video frame; see the next section.)

## Measured frame costs and the product gates — 2026-10-07 (second revision)

Third independent review of `cc36910..cf50a23`; user decision extends D-1601.

- **Payload:** the frame rule predicts the end of the game loop from costs it
  measures itself (extra-glyph cost, rest of the loop pass after the batch, measured
  through a hook on the game loop's last call before its VBlank wait), instead of two
  fixed constants; a newline before a control is that control's step. Payload 1240
  bytes, ITCM extension `01FF8620`-`01FF8B00`. See [text_speed_vcount.md](text_speed_vcount.md).
- **Gates measure the product:** frames strictly ordered except at a demonstrated
  physical cap, no more dropped frames than the original printer, no frame dropped
  only by extra glyphs, no frame stop that gave up a glyph that would have fitted, a
  SLOW floor derived from its design; a `scenes` gate over 17 busy, light and 30 fps
  scenes. The model check mirrors the payload's frame state from the readings the
  gate observes and compares it with RAM.
- **Battle:** seven battles; waits compared in loop passes; a pause may differ from
  the original only by values the original printer itself shows when replayed with a
  delayed start (the battle waits for its sound).
- **Fail closed:** gates run with `python -I` and a clean environment; every fault
  declares the failure text its gates must report from their own checks; faults whose
  gate model is set to match the broken payload prove the product checks.
