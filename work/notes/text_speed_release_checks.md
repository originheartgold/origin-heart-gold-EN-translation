# Text-speed RC validation recipe

Run from the experimental worktree root. All reports, temporary batteries,
fixture ROMs and screenshots belong under ignored `work/build/`. Use original
battery-save inputs, not savestates from another ROM. Keep source ROM/save hashes
unchanged. Never commit ROMs, battery saves or extracted game text.

## Build-time gates

1. Run the full `work/tools/test_*.py` unittest suite with `TEXT_SPEED_TEST_ROM`
   pointing to a demand-loaded English ROM built from the same tree WITHOUT the
   feature (`build.py --no-text-speed --no-patch --work-dir work/build/...`). The
   tests apply the patch to that fixture, so the candidate itself is refused there
   (double application fails closed). Require no failures, errors or skips; missing
   local ROM/compiler fixtures are not a pass. In a worktree, provide the ROMs as
   symlinks inside a real `work/rom/` directory (`*.nds` is ignored) and the dump
   as a symlink `work/extract/v4` inside a real `work/extract/` directory (ignored);
   `git status --short` must stay empty.
2. Run `work/tools/text_speed_patch.py --check-payload`. This independently
   recompiles the cached native code and checks the complete code/symbol identity.
3. Build with the native feature enabled, retaining the normal ROM verifier and
   xdelta round-trip check. Verify the intended USA base CRC32 `C180A0E9`.
4. Run `work/tools/artifact_check.py` against that ROM and its build report, using
   `--ws work/translate/banks` and the correct original extraction directory.
   The artifact check includes native payload reproduction and critical runtime
   contract checks. Bind the passing artifact report to the delivered ROM hash.
5. Decode the packaged xdelta separately and require its SHA256 to equal the
   tested ROM. A renamed or copied patch still needs this packaging check.

The native verifier checks the printer task pointer, 0x38 allocation, private
initializer call, new-game MEDIUM default, music masks and ITCM arena/section
layout independently of output hashes in the build receipt. A subsequent build
stage cannot silently undo those operations and pass by refreshing the receipt.

## Runtime gates

One command runs every runtime gate and writes one report bound to the ROM,
battery and payload SHA-256 and the git commit:

```sh
python work/research/text_speed/validate_release.py --rom CANDIDATE.nds \
    --save /path/to/memcheck/trainer.sav --out work/build/text-speed/<run> --jobs 6
```

The battery is the user-made `trainer.sav` fixture (facing an unbeaten Route 1
trainer; SHA-256 `7ae21586…26fd5`, kept in the main checkout's ignored
`work/build/memcheck/`). `report.json` must say `status: passed` and
`releasable: true`; each gate's own report sits beside it. Each gate is its own
process with its own DeSmuME battery directory and a timeout of one hour of
running time (time spent waiting for a free emulator slot, see
`EMU_HARNESS_MAX_EMULATORS`, is logged by emu_harness and not counted); a
timeout, crash, missing report or a report without `passed` fails the gate.
`--only a,b` runs a subset (status `partial-passed`).

Fail closed:

- `validate_release.py` and every gate refuse to run under `python -O`; gate checks
  use `gate_common.require()` (raises `GateError` with a message), never `assert`.
- The work tree must be clean, untracked files included
  (`git status --porcelain --untracked-files=all`); it is checked again at the end,
  with HEAD. `--allow-dirty` runs anyway but can only end in
  `passed-not-releasable`.
- `--fault-payload` runs (below) never produce `passed`.

Determinism: every gate except `save` runs with `Harness(..., rtc=CLOCK)`, which
records a throw-away DeSmuME movie so the emulated real-time clock starts at a
fixed date and advances with emulated frames. Without it the game reads host time
at boot and frame counts differ from run to run (seen: SLOW/MEDIUM/FAST spans
49/36/29 in one run, 36/37/33 in another). `save` cannot use it (a reset during
movie recording restores the starting battery) and asserts values only. Because
runs repeat frame for frame, the gates compare with the original printer exactly,
without tolerances.

Shared per-task rule (corpus, controls, battle, callbacks, fallbacks,
natural-dialogue, printers): `text_speed_checks.task_errors` judges every native
task from hooks on the task, the render step, each glyph and the VCOUNT read: at
most its budget (SLOW 1/2 by phase, MEDIUM 2, FAST 3); at least one render; a frame
check after each glyph that has budget left and no control next, and another glyph
exactly when the frame rule allows it ([frame rule](text_speed_vcount.md)); every
task that drew less than its budget stopped for a logged reason (control next,
render result, frame stop); SLOW's phase flips after a task that drew, except after
a frame stop; callback and explicit-delay printers delegate to the original task.

Frame order (corpus, controls, battle, fallbacks, natural-dialogue): total printing
frames original > SLOW >= MEDIUM >= FAST for every message; two speeds may tie only
when the faster one stopped on the frame limit in that message (reported as
`frame_limited_ties`), any inversion fails. Dropped frames (frames between a
printer's first and last glyph in which its task did not run, i.e. the game loop
missed a VBlank) may exceed the original printer's by at most one per message.

| Gate | Script | What fails it |
| --- | --- | --- |
| options | `harness_options.py` | row/value wrap, touch, Confirm/Quit/B, reserved value 3, neighbouring bits; six screenshots of the TEXT SPEED row: three labels, each inside its touch column with a 4 px margin, only the stored choice in the selected colour, nothing spilling out of the row |
| music | `music_interaction.py` | nine music/text combinations, native getter returns, Cancel on all seven rows |
| save | `save_persistence.py` | in-game save → reset → Continue for all three values; reloaded menu labels |
| new-game | `new_game_default.py` | blank battery: MEDIUM (516) before runtime publication |
| lifecycle | `printer_lifecycle.py` | phase/focus reset after poisoning; 24 messages: every printer freed, heap growth ≤ 2 blocks / 1 KiB, an open message must be visible to the heap measurement |
| fallbacks | `harness_fallbacks.py` | invalid/null/legacy-music/explicit-delay paths (every task delegated where required); per-task rule; frame order and dropped frames against the invalid-mode original printer |
| callbacks | `callback_regression.py` | callback/busy cadence and pixels vs the original task; held A, held B and tapping: no page skipped, one new press after release starts page 2 with exactly the original's latency (counted from the later of the press and the frame the page prompt reads input, last glyph + 2); per-task rule |
| corpus | `harness_regression.py` | six real messages per speed vs the original printer (reserved value 3): identical page pixels, glyph count and layout; per-task rule; frame order; dropped frames; printer tasks from each page's last glyph to its control step (prompt, scroll, end) exactly equal to the original's; printer allocation/free pairing; heap growth; ITCM at start and end |
| controls | `control_fixture.py` + `harness_regression.py --controls` | the authored scroll/clear/size/60-tick-pause message against the original, with the corpus checks; the explicit pause in printer tasks exactly equal (frames are reported: a dropped frame inside the pause lengthens it by one frame at any speed) |
| battle | `battle_pacing.py` | from shared checkpoints, battle start + three turns per speed and the original: same messages and glyph counts, completed text pixels, the pause after every completed message, its on-screen dwell and the frames from the last glyph to the printer's removal all exactly equal to the original; each segment shorter by exactly the printing frames saved; per-task rule; frame order; dropped frames |
| natural-dialogue | `natural_dialogue.py` | touch selection after a cold boot, trainer page, original printer as baseline: per-task rule, identical pixels/layout, frame order, dropped frames |
| printers | `printer_smoke.py` | save prompt, Route 1 sign, Pokémon Center PC (two messages), Pokégear phone call, each from one checkpoint per mode: every AddTextPrinter call logged (speed, callback, caller); the declared path holds (save, PC and phone go through the batched path at every speed and only through the original task with value 3; the sign starts no asynchronous printer); per-task rule; captured text identical to the original printer |

Every Harness gate checks at start and end that the original ITCM code still has
its reviewed hash, the payload bytes equal the expected payload and the SDK ITCM
arena (`0x027FFDAC`/`0x027FFDD0`) starts at or above the payload end. Heap
integrity is walked every 10 frames. Measurement hooks are registered
`exclusive`: emu_harness raises if anything later registers the same address
(DeSmuME would otherwise replace a hook silently).

Not covered by the printers gate: the Pokégear radio (the fixture has no radio
card), mail (no mail item), the credits (end of the game) and the new-game
introduction. The introduction is reachable from a blank battery (about 32 A
presses), but its pages are drawn synchronously: the one asynchronous printer it
starts renders a single control step before the scene removes it, and New Game
re-initialises Options, so no mode can be chosen there.

Candidate of 2026-10-07: `work/build/text-speed/candidate-vcount/`, ROM SHA-256
`8c6e97f97cbd844df34c3554615275230a7b3cc50dd63d2e78d94f72399fb86c`, xdelta
`27200ee8…6c29` (decodes against the USA base, CRC32 `C180A0E9`, to that ROM).
Build verification, `artifact_check.py`, `--check-payload` and the full unit suite
(601 tests against a fresh `--no-text-speed` fixture, no skips) passed. The runtime
report is `work/build/text-speed/release-vcount/report.json`, bound to the commit
that added this paragraph; frame numbers are in [text_speed_vcount.md](text_speed_vcount.md).

### Proving a check is not vacuous

`fault_fixture.py CANDIDATE work/build/<dir> --fault NAME` writes a deliberately
broken `FAULT-NAME.nds` and matching `FAULT-NAME.payload.json` (exact original
bytes are verified first; the candidate is never changed). Each fault declares the
gates that must catch it and a text their errors must contain. Run
`validate_release.py --rom <dir>/FAULT-NAME.nds --fault-payload <dir>/FAULT-NAME.payload.json --only <declared gates>`;
its status must be `fault-detected`, which requires every declared gate to fail with
its declared text (a timeout or crash does not count). Fault reports are marked and
are never release evidence; validate_release refuses a `FAULT-` ROM without the
flag. Pure rules live in `work/tools/text_speed_checks.py` and are unit-tested in
`test_text_speed_checks.py`; the runner's verdict rules in `test_text_speed_release.py`.

Results on candidate `8c6e97f9…fb86c` (2026-10-07, payload `fccee874…f211`,
812 bytes; reports in ignored `work/build/text-speed/matrix-rc/`). Every fault was
run with `--only` its declared gates; `no-state-stop` with corpus, controls,
natural-dialogue, callbacks, fallbacks and battle, none of which failed.

| Fault | What it breaks | Declared gates (required text) | Gates that failed | Verdict |
| --- | --- | --- | --- | --- |
| `fast-budget` | MEDIUM/FAST budget m+7 instead of m+1 (8 and 9 glyphs per task) | corpus ('design budget'), battle ('design budget'), callbacks ('design budget'), fallbacks ('budget'), natural-dialogue ('design budget') | battle, callbacks, corpus, fallbacks, natural-dialogue | fault-detected |
| `slow-flat` | SLOW ignores its phase: always one glyph per task | corpus ('without a reason'), callbacks ('without a reason'), fallbacks ('without a reason'), natural-dialogue ('without a reason'), battle ('without a reason') | battle, callbacks, corpus, fallbacks, natural-dialogue | fault-detected |
| `no-phase-reset` | init_printer no longer clears the private phase byte (+0x34) | lifecycle ('phase') | lifecycle | fault-detected |
| `commit-noop` | Options Confirm no longer stores the text-speed bits | options, save, music, corpus | corpus, music, options, save | fault-detected |
| `label-overflow` | MEDIUM label replaced by a ten-letter label | options ('label'), save ('label') | options, save | fault-detected |
| `default-slow` | new-game Options initialiser sets SLOW instead of MEDIUM (main ARM9) | new-game | new-game | fault-detected |
| `arena-overlap` | SDK ITCM arena lower bound put back over the payload (main ARM9 data) | lifecycle ('ITCM arena'), options ('ITCM arena') | lifecycle, options | fault-detected |
| `no-control-stop` | batching no longer stops before control codes | corpus ('control step'), controls ('control step'), battle ('to_free') | battle, controls, corpus | fault-detected |
| `eos-only-no-stop` | batching no longer stops before 0xFFFF/0xFFFE (end of text, extended controls) | corpus ('control step'), battle ('to_free') | battle, corpus | fault-detected |
| `space-stop` | batching stops before every space (0x01DE) instead of 0xF0FD | corpus ('without a reason'), natural-dialogue ('without a reason'), fallbacks ('without a reason'), callbacks ('without a reason') | callbacks, corpus, fallbacks, natural-dialogue | fault-detected |
| `no-color-setup` | native task no longer sets the glyph colour table before rendering | corpus ('pages differs'), controls ('pages differs'), callbacks ('pixels differ') | callbacks, controls, corpus | fault-detected |
| `no-state-stop` | batch ignores RenderText state +0x28 / delay counter +0x2a after a glyph | none: dead code | none | fault-dead-code |
| `reserved-fast` | Options shows reserved/legacy value 3 as FAST instead of MEDIUM | options | options | fault-detected |
| `vcount-ignored` | batch ignores the VCOUNT frame check (always draws its whole budget) | natural-dialogue ('after a frame stop'), fallbacks ('after a frame stop'), callbacks ('after a frame stop') | callbacks, fallbacks, natural-dialogue | fault-detected |
| `vcount-zero-glyph` | frame check runs before the first glyph (a late task draws nothing) | corpus ('did not complete'), natural-dialogue ('before the first glyph'), fallbacks ('before the first glyph'), callbacks ('before the first glyph'), battle ('before the first glyph') | battle, callbacks, corpus, fallbacks, natural-dialogue | fault-detected |

`no-state-stop` removes the loop's test of RenderText's state (+0x28) and delay
counter (+0x2a) after a glyph. It is dead code under the pinned base ARM9, proven
from the disassembly of RenderText (`0x020022D0`, state machine with the two
reviewed jump tables): the only `return 0` (glyph drawn) is at `0x02002694`, at the
end of the glyph block `0x02002658`-`0x02002696`, which is reached only from the
state-0 character dispatcher. That handler runs with +0x28 = 0, stores
+0x2a = +0x29 & 0x7F before reading the character (`0x02002376`-`0x02002384`), and
the glyph block writes neither field (it stores only the x position +0x0C; its
callees get the window and glyph data, not the printer). The native task batches
only printers with +0x29 & 0x7F = 0 and nothing in the loop changes +0x29. So after
every glyph +0x28 = 0 and +0x2a = 0, and the test can never fire. It is kept as a
guard; no gate can catch its removal.

The standalone `commit_speed` routine in the payload is never called: the compiler
inlined it into `exit_free`. The `commit-noop` fault therefore patches the inlined
store.

## Release interpretation

Passing these gates establishes bounded automated coverage, not universal memory
safety or subjective readability. Not covered automatically: Pokédex, naming
screen, intro and credits, Pokégear radio/TV, mail and other scene-specific
printers; physical hardware and a second emulator. Preserve the documented native
battle pauses. Use MEDIUM as the recommended starting point for English
playtesting. Device checks should include short failed-move/status messages,
ordinary multi-page conversations, Options changes and a save/restart during the
real playthrough. Frame costs were measured in DeSmuME; whether hardware drops the
same frames needs a device check. Unreleased INSTANT-era saves are not a
migration-support requirement.
