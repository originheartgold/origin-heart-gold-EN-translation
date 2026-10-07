# Text-speed RC validation recipe

Current design: TEXT SPEED **NORMAL / FAST** (D-1604; see
[text_speed_release.md](text_speed_release.md#current-design-d-1604) for the stored
values). The rules and gates below describe it; results tables marked historical
are from the earlier SLOW / MEDIUM / FAST revision.

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

The native verifier checks the printer task pointer, the game-loop `pass_end` call,
the new-game FAST default, music masks and ITCM arena/section layout independently
of output hashes in the build receipt. (Since D-1604 the printer constructor is no
longer edited: no 0x38 allocation, no private initializer.) A subsequent build
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
- Every gate process (and every child a gate starts) runs as `python -I` (no
  `PYTHONPATH`, no user site, no script directory injected) with a clean
  environment: only `PATH`, `HOME`, `USER`, `LOGNAME`, `TMPDIR`, the locale variables
  and `EMU_HARNESS_MAX_EMULATORS` are passed on (`validate_release.gate_env`).
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

Modes the gates run: ORIGINAL (stored value 3, written to RAM: an unknown value the
payload must treat as NORMAL, i.e. the original printer task; the baseline), NORMAL
(0) and FAST (1). Where a gate chooses the speed through the Options UI, the
ORIGINAL run makes the same choice as the NORMAL run before writing 3, so both get
the same input.

Shared per-task rule, the model (corpus, controls, battle, callbacks, fallbacks,
natural-dialogue, printers, scenes): `text_speed_checks.task_errors` judges every
native task. `gate_common.PrinterTrace` hooks the task, the render step, each glyph
and every load in `print_task` and `frame_end` whose address is VCOUNT or the VBlank
counter, mirrors the payload's frame state from those readings
(`text_speed_checks.FrameModel`) and compares it with the payload's RAM before every
reading. Rules: NORMAL and ORIGINAL delegate every task to the original printer task;
FAST: at most its budget (3); at least one render; a line reading after every
render; after a glyph with budget left and no control next (a newline counts as part
of the unit after it), another glyph exactly when the model's decision draws
([frame rule](text_speed_vcount.md), including the short-history rest floor); a task that
drew marks its end once, after its last reading; every task that drew less than its
budget stopped for a logged reason (control next, render result, frame stop);
callback and explicit-delay printers delegate to the original task at both speeds.

Product rules (corpus, controls, battle per segment, fallbacks, natural-dialogue,
scenes; `text_speed_checks.order_errors`), per message against the original printer
(D-1604):

- NORMAL is the original printer: printing frames, dropped frames, printing and
  glyph tasks, pages and every glyph task's pass slack equal the ORIGINAL run's
  exactly (pixels and layout are compared by each gate);
- no FAST frame stop gave up a glyph that would have fitted (one more glyph of the
  message's median measured cost would still have ended the loop pass two or more
  lines before VBlank; stops before any cost of the scene was measured are exempt);
- FAST printing frames at most NORMAL's, and strictly fewer when any NORMAL glyph
  task's pass had room for one more glyph (slack of at least FAST's measured
  extra-glyph cost + 2 lines, the same physical test); a tie without such a frame
  is reported as `capped_ties`;
- FAST drops no more frames than NORMAL (dropped frame: a frame inside a page's
  printing in which the printer's task did not run), and none only because of a
  batch's extra glyphs.

The SLOW-only rules of the earlier revision (SLOW floor, SLOW phase flips, the
SLOW > MEDIUM > FAST order) were removed with SLOW and MEDIUM.

| Gate | Script | What fails it |
| --- | --- | --- |
| options | `harness_options.py` | the row has two choices; row/value wrap, touch, Confirm/Quit/B; unknown values 2 and 3 shown as NORMAL, kept by Cancel, stored as NORMAL by Confirm; neighbouring bits; six screenshots of the TEXT SPEED row: two labels (NORMAL, FAST), each inside its column with a 4 px margin, only the stored choice in the selected colour, nothing spilling out of the row |
| music | `music_interaction.py` | six music/text combinations (NORMAL, FAST), native getter returns, Cancel on all seven rows |
| save | `save_persistence.py` | in-game save → reset → Continue for both values (FAST, then NORMAL); reloaded menu labels |
| new-game | `new_game_default.py` | blank battery: FAST (Options 516, text-speed bits 1) before runtime publication |
| lifecycle | `printer_lifecycle.py` | every constructed printer returns with its focus pointer reset (reused slots included); 24 messages alternating NORMAL/FAST: every printer freed, heap growth ≤ 2 blocks / 1 KiB, an open message must be visible to the heap measurement |
| fallbacks | `harness_fallbacks.py` | NORMAL, unknown values 3 and 2, null runtime pointer (FAST stored), explicit delay: every task delegated; value 2 prints exactly like value 3; legacy music bits next to FAST print exactly like FAST; per-task rule; product rules against the value-3 original printer |
| callbacks | `callback_regression.py` | callback/busy cadence and pixels vs the original task; held A, held B and tapping: no page skipped, one new press after release starts page 2 with exactly the original's latency (counted from the later of the press and the frame the page prompt reads input, last glyph + 2); per-task rule |
| corpus | `harness_regression.py` | six real messages per speed (NORMAL, FAST) vs the original printer (unknown value 3, chosen after the same NORMAL input): Confirm stores the chosen speed; identical page pixels, glyph count and layout; per-task rule; product rules; printer tasks from each page's last glyph to its control step (prompt, scroll, end) exactly equal to the original's; printer allocation/free pairing; heap growth; ITCM at start and end |
| controls | `control_fixture.py` + `harness_regression.py --controls` | the authored scroll/clear/size/60-tick-pause message against the original, with the corpus checks; the explicit pause in printer tasks exactly equal (frames are reported: a dropped frame inside the pause lengthens it by one frame at any speed) |
| battle | `battle_pacing.py` | eight battles (trainers 1, 2, 5, 15, 8, 40, 50, 20; each its own process; the battle RNG pinned to `0x5EED1604` at its first use in every segment-0 run, written, read back and recorded in the report, a missing or lost pin fails the gate; 15 replaced Leader Whitney (30), who blacks out with the original printer under the pin), from shared checkpoints battle start + three turns per speed and the original: same messages and glyph counts, completed text pixels; the first glyph and the end-of-text step the same number of loop passes after the printer's start and last glyph as with the original; the pause after every message (passes) and its on-screen dwell (frames, from the first frame the completed text is on screen) equal to the original's, or a value the original printer itself shows when replayed from the same checkpoint with its start delayed by 1-12 frames (the battle waits for its sound; [mechanism](text_speed_vcount.md#battle)); identical lead-in; each segment shorter by exactly the printing frames saved plus those pause differences; per-task rule; product rules per segment. Excluded with reason: trainers 100, 3, 6, 10, 30 (black-out needs a button), 9, 13 (the original printer itself does not reach the command menu without input under the pin) |
| natural-dialogue | `natural_dialogue.py` | touch selection after a cold boot (old-save default NORMAL, row of two), trainer page, original printer as baseline (same input as NORMAL): per-task rule, identical pixels/layout, product rules |
| printers | `printer_smoke.py` | save prompt, Route 1 sign, Pokémon Center PC (two messages), Pokégear phone call to Mom (three pages, each captured), each from one checkpoint per mode: every AddTextPrinter call logged (speed, callback, caller); the declared path holds (save, PC and phone go through the batched path with FAST and only through the original task with NORMAL and value 3; the sign starts no asynchronous printer); per-task rule; captured text identical to the original printer |
| phone-call | `phone_call_wait.py` | D-1600 / D-1599. Seven scenarios, each its own process: win the trainer.sav battle, then call Mom from the Pokégear at NORMAL, FAST and the reserved value 3 (speed set after the battle so every run reaches the call identically); win the battle, then Mom calls the player (incoming call through the game's scripted-call commands `SetPhoneCall 0, 2, 0` / `RunPhoneCall`; several messages) at NORMAL and FAST; and both calls with no battle (controls). The battle must leave auto-scroll set (else the bug was not reproduced: fail), the controls must not; every call message enters `call_print`; no call glyph is drawn with auto-scroll set; the auto-scroll wait `02002AB0` is never entered for the call printer; every complete page holds 600 frames without input (no glyph, no advance, window pixels unchanged, page wait polled every frame) and a fresh A press continues within 30 frames; the Pokégear call teardown runs; the next battle sets auto-scroll again on entry and reaches its command menu with no input; per call (outgoing, incoming) the pages' window pixel buffer and glyph layout are identical in every scenario; the incoming call has at least two messages |
| field-rate | `field_rate.py` | printer catch-up (D-1603): ten field scenes (Route 1 two spots, Viridian, Viridian Forest, Routes 29/30, New Bark, Cherrygrove and its Pokémon Center, Violet), catch-up on and off from one checkpoint: NORMAL (D-1604) at most 1.05 frames per glyph; idle passes not fewer; same glyphs, layout, pages and window pixels; print queue run once per pass; printer slots hold only printer tasks; catch-up tasks only after the model's decision; no catch-up moves the VBlank counter; every 30 fps scene ran catch-ups ([design](text_speed_vcount.md#printer-catch-up-in-30-fps-maps-d-1603-provisional)) |
| scenes | `scene_pacing.py` | 17 scenes, each a cold boot (busy 60 fps: trainer page after Options, idle Route 1, Celadon Gym, Goldenrod Dept. Store 6F; light 60 fps; 30 fps): the trainer page, message 718#160 or a real NPC talk per speed and the original printer from one checkpoint: per-task rule, identical glyphs/layout/pages, product rules ([table](text_speed_vcount.md#scenes-before-and-after)) |

Every Harness gate checks at start and end that the original ITCM code still has
its reviewed hash, the payload's fixed bytes (all but the 26-byte runtime frame
state at its end) equal the expected payload and the SDK ITCM
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

Historical (SLOW / MEDIUM / FAST): candidate of 2026-10-07 (second revision): `work/build/text-speed/candidate-adaptive/`, ROM SHA-256
`5fc707148c4ef8503f4ed8141dfdf876fbcd6c26bc47f02aebdb3c95962a2460`, xdelta `6d460e7a…d60d` (decodes
against the USA base, CRC32 `C180A0E9`, to that ROM). Build verification, `artifact_check.py`,
`--check-payload` (digest `e17e38e0…be9`) and the full unit suite (612 tests against a fresh
`--no-text-speed` fixture `6fa7b4e7…a7d3`, no skips) passed. The runtime report is
`work/build/text-speed/release-adaptive/report.json`, bound to the commit that added this paragraph;
frame numbers are in [text_speed_vcount.md](text_speed_vcount.md).

### Proving a check is not vacuous

`fault_fixture.py CANDIDATE work/build/<dir> --fault NAME` writes a deliberately
broken `FAULT-NAME.nds` and matching `FAULT-NAME.payload.json` (exact original
bytes are verified first; the candidate is never changed). Each fault declares the
gates that must catch it and a text their errors must contain. Run
`validate_release.py --rom <dir>/FAULT-NAME.nds --fault-payload <dir>/FAULT-NAME.payload.json --only <declared gates>`;
its status must be `fault-detected`, which requires every declared gate to fail with
its declared text, found in the gate's own check messages (a timeout, a crash or an
unexpected Python exception such as a `KeyError` does not count; every declared gate
names a text). A fault may also set the gates' frame model to the broken payload's
(`checker` in `fault_fixture.FAULTS`, applied only for `--fault-payload` runs): then
only the product rules can catch it. Fault reports are marked and
are never release evidence; validate_release refuses a `FAULT-` ROM without the
flag. Pure rules live in `work/tools/text_speed_checks.py` and are unit-tested in
`test_text_speed_checks.py`; the runner's verdict rules in `test_text_speed_release.py`.

Fault set for D-1604 (NORMAL / FAST; payload 1406 bytes; `fault_fixture.FAULTS` holds the
addresses, declared gates and texts). Not yet run as a matrix for this revision.

- Kept, re-addressed: `fast-budget` (FAST budget 9 instead of 3), `commit-noop`, `label-overflow`
  (now the FAST label, ten letters: it runs into the panel border), `arena-overlap`,
  `no-control-stop`, `eos-only-no-stop`, `no-newline-peek`, `space-stop`, `no-color-setup`,
  `no-state-stop` (dead code, same proof), `zero-glyph`, `frame-rule-ignored`, `rest-not-stored`,
  `fixed-model`, `tail-ignored`, `glyph-ignored`, `no-catch-up`.
- Renamed: `default-slow` → `new-game-normal` (the initialiser stores NORMAL instead of FAST;
  new-game 'does not start at FAST'); `reserved-fast` → `unknown-value-fast` (values 2 and 3
  print and show as FAST; options 'is not shown as NORMAL', fallbacks 'fallback skipped the
  original task', corpus 'did not delegate').
- New: `normal-batches` (NORMAL batches like FAST; corpus, scenes, natural-dialogue and
  field-rate 'did not delegate', fallbacks 'fallback skipped the original task') and
  `short-history-unguarded` (the short-history rest floor removed, gates' model set to match;
  scenes 'dropped only because', the Route 1 promoter drop).
- Changed: the too-conservative payloads now bias every stored glyph cost (+4: `too-conservative-24`,
  +7: `too-conservative-27`, the largest bias one Thumb instruction encodes; the SLOW-era
  `too-conservative-30` biased the rest by 7 and the glyph by 3) with the gates' model set to
  match; without the SLOW floor both must be caught by 'would have fitted' (scenes,
  natural-dialogue).
- Removed: `slow-flat` (SLOW's phase: there is no SLOW) and `no-phase-reset` (the private
  phase byte +0x34 and `init_printer` no longer exist; the printer constructor is unchanged).

Historical: results on candidate `5fc70714…2460` (2026-10-07, second revision; payload digest `e17e38e0…be9`,
1240 bytes; reports in ignored `work/build/text-speed/matrix-adaptive/`). Every fault was run with
`--only` its declared gates; `no-state-stop` with corpus, controls, natural-dialogue, callbacks,
fallbacks, battle and scenes, none of which failed. After the runs, the declared texts of five faults
(`slow-flat`, `space-stop`, `no-control-stop`, `eos-only-no-stop`, `zero-glyph`) were changed to the
wording the new model check reports (for example 'stopped although the frame decision ... allowed
another glyph' instead of 'without a reason': every glyph now has a decision); every declared gate of
those faults had failed, and their verdicts were recomputed from the stored reports with
`validate_release.fault_verdict` (`verdicts.json`). The last five faults set the gates' frame model to
the broken payload's, so only the product rules could catch them: `fixed-model` (the `cf50a23` rule) by
frame stops that gave up a glyph that would have fitted (trainer page after Options, Celadon Gym),
the two too-conservative payloads (the review's thresholds 24 and 30) by the same rule and the SLOW
floor, `tail-ignored` and `glyph-ignored` by frames dropped only because of extra glyphs.

| Fault | What it breaks | Declared gates (required text) | Gates that failed | Verdict |
| --- | --- | --- | --- | --- |
| `fast-budget` | MEDIUM/FAST budget m+7 instead of m+1 (8 and 9 glyphs per task) | corpus ('design budget'), battle ('design budget'), callbacks ('design budget'), fallbacks ('budget'), natural-dialogue ('design budget'), scenes ('budget') | battle, callbacks, corpus, fallbacks, natural-dialogue, scenes | fault-detected |
| `slow-flat` | SLOW ignores its phase: always one glyph per task | corpus ('allowed another glyph'), callbacks ('allowed another glyph'), fallbacks ('allowed another glyph'), natural-dialogue ('allowed another glyph'), battle ('allowed another glyph'), scenes ('allowed another glyph') | battle, callbacks, corpus, fallbacks, natural-dialogue, scenes | fault-detected |
| `no-phase-reset` | init_printer no longer clears the private phase byte (+0x34) | lifecycle ('phase') | lifecycle | fault-detected |
| `commit-noop` | Options Confirm no longer stores the text-speed bits | options ('did not store the chosen text speed'), save ('did not store the chosen text speed'), music ('did not store the chosen text speed'), corpus ('did not store the chosen text speed') | corpus, music, options, save | fault-detected |
| `label-overflow` | MEDIUM label replaced by a ten-letter label | options ('label'), save ('label') | options, save | fault-detected |
| `default-slow` | new-game Options initialiser sets SLOW instead of MEDIUM (main ARM9) | new-game ('does not start at MEDIUM') | new-game | fault-detected |
| `arena-overlap` | SDK ITCM arena lower bound put back over the payload (main ARM9 data) | lifecycle ('ITCM arena'), options ('ITCM arena') | lifecycle, options | fault-detected |
| `no-call-redirect` | Pokégear call printer calls AddTextPrinterParameterized directly again (overlay 92) | phone-call ('advanced without input') | phone-call | not run yet (stage 3) |
| `call-clear-noop` | call_print no longer clears auto-scroll (blx SetAutoScrollParam -> nop) | phone-call ('advanced without input') | phone-call | not run yet (stage 3) |
| `no-control-stop` | batching no longer stops before control codes | corpus ('without a frame decision'), controls ('without a frame decision'), battle ('to_free') | battle, controls, corpus | fault-detected |
| `eos-only-no-stop` | batching no longer stops before 0xFFFF/0xFFFE (end of text, extended controls) | corpus ('without a frame decision'), battle ('without a frame decision') | battle, corpus | fault-detected |
| `no-newline-peek` | batching no longer looks past a newline: a newline before the end of the text is rendered with the batch | battle ('end-of-text step moved') | battle | fault-detected |
| `space-stop` | batching stops before every space (0x01DE) instead of 0xF0FD | corpus ('allowed another glyph'), natural-dialogue ('allowed another glyph'), fallbacks ('allowed another glyph'), callbacks ('allowed another glyph') | callbacks, corpus, fallbacks, natural-dialogue | fault-detected |
| `no-color-setup` | native task no longer sets the glyph colour table before rendering | corpus ('pages differs'), controls ('pages differs'), callbacks ('pixels differ') | callbacks, controls, corpus | fault-detected |
| `no-state-stop` | batch ignores RenderText state +0x28 / delay counter +0x2a after a glyph | none: dead code | none | fault-dead-code |
| `reserved-fast` | Options shows reserved/legacy value 3 as FAST instead of MEDIUM | options ('reserved value 3 is not shown as MEDIUM') | options | fault-detected |
| `zero-glyph` | the batching task returns before its first render (draws nothing) | corpus ('did not complete'), natural-dialogue ('expected the 54-glyph trainer page'), fallbacks ('expected 54 glyphs'), callbacks ('(0 glyphs)'), scenes ('no native tasks observed'), battle ('stuck without A/B input') | battle, callbacks, corpus, fallbacks, natural-dialogue, scenes | fault-detected |
| `frame-rule-ignored` | the frame decision always draws (the batch always uses its whole budget) | natural-dialogue ('after a frame stop'), fallbacks ('after a frame stop'), callbacks ('after a frame stop'), scenes ('after a frame stop') | callbacks, fallbacks, natural-dialogue, scenes | fault-detected |
| `rest-not-stored` | frame_end no longer stores the measured rest (the decision runs on the seed) | natural-dialogue ('payload state'), scenes ('payload state'), corpus ('payload state'), fallbacks ('payload state'), callbacks ('payload state') | callbacks, corpus, fallbacks, natural-dialogue, scenes | fault-detected |
| `fixed-model` | the cf50a23 rule: draw when 20 or more lines are left, lost below 7, no measured costs (gates' model set to match) | scenes ('would have fitted') | scenes | fault-detected |
| `tail-ignored` | the decision leaves out the rest of the pass (predicts only the glyph) (gates' model set to match) | scenes ('dropped only because'), natural-dialogue ('dropped only because') | natural-dialogue, scenes | fault-detected |
| `glyph-ignored` | the decision leaves out the glyph cost (predicts only the rest of the pass) (gates' model set to match) | scenes ('dropped only because'), natural-dialogue ('dropped only because') | natural-dialogue, scenes | fault-detected |
| `too-conservative-24` | needs 4 more lines for an extra glyph (the review's threshold 24 against 20) (gates' model set to match) | scenes ('SLOW floor'), natural-dialogue ('SLOW floor') | natural-dialogue, scenes | fault-detected |
| `too-conservative-30` | needs 10 more lines for an extra glyph (the review's threshold 30 against 20) (gates' model set to match) | scenes ('SLOW floor'), natural-dialogue ('SLOW floor') | natural-dialogue, scenes | fault-detected |

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
guard; no gate can catch its removal. (The proof does not depend on the payload's
frame rule; the test is the same in this revision.)

The standalone `commit_speed` routine in the payload is never called: the compiler
inlined it into `exit_free`. The `commit-noop` fault therefore patches the inlined
store.

## Release interpretation

Passing these gates establishes bounded automated coverage, not universal memory
safety or subjective readability. Not covered automatically: Pokédex, naming
screen, intro and credits, Pokégear radio/TV (calls are covered: phone-call), mail and other scene-specific
printers; physical hardware and a second emulator. Preserve the documented native
battle pauses. New games start on FAST and existing saves on NORMAL (D-1604);
playtest both. Device checks should include short failed-move/status messages,
ordinary multi-page conversations, Options changes and a save/restart during the
real playthrough. The frame rule measures its costs at run time, but its seeds and
margin were chosen from DeSmuME measurements; whether hardware drops the same frames
needs a device check. Unreleased INSTANT-era saves are not a
migration-support requirement.
