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
`work/build/memcheck/`). `report.json` must say `status: passed`; each gate's own
report sits beside it. Each gate is its own process with its own DeSmuME battery
directory and a timeout; a timeout, crash, missing report or a report without
`passed` fails the gate. `--only a,b` runs a subset (status `partial-passed`).

Determinism: every gate except `save` runs with `Harness(..., rtc=CLOCK)`, which
records a throw-away DeSmuME movie so the emulated real-time clock starts at a
fixed date and advances with emulated frames. Without it the game reads host time
at boot and frame counts differ from run to run (seen: SLOW/MEDIUM/FAST spans
49/36/29 in one run, 36/37/33 in another). `save` cannot use it (a reset during
movie recording restores the starting battery) and asserts values only.

| Gate | Script | What fails it |
| --- | --- | --- |
| options | `harness_options.py` | row/value wrap, touch, Confirm/Quit/B, reserved value 3, neighbouring bits; six screenshots of the TEXT SPEED row: three labels, each inside its touch column with a 4 px margin, only the stored choice in the selected colour, nothing spilling out of the row |
| music | `music_interaction.py` | nine music/text combinations, native getter returns, Cancel on all seven rows |
| save | `save_persistence.py` | in-game save → reset → Continue for all three values; reloaded menu labels |
| new-game | `new_game_default.py` | blank battery: MEDIUM (516) before runtime publication |
| lifecycle | `printer_lifecycle.py` | phase/focus reset after poisoning; 24 messages: every printer freed, heap growth ≤ 2 blocks / 1 KiB, an open message must be visible to the heap measurement |
| fallbacks | `harness_fallbacks.py` | invalid/null/legacy-music/explicit-delay paths; exact budgets {1,2}/{2}/{3}; printing-frame order (lag-explained inversions are warnings) |
| callbacks | `callback_regression.py` | callback/busy cadence and pixels vs the original task; held A, held B and tapping: no page skipped, one new press after release starts page 2 with the original latency (±2 frames), budgets per task |
| corpus | `harness_regression.py` | six real messages per speed vs the original printer (reserved value 3): identical page pixels, glyph count and layout; budgets per task; printing-frame order; printer allocation/free pairing; heap growth; ITCM at start and end |
| controls | `control_fixture.py` + `harness_regression.py --controls` | the authored scroll/clear/size/60-tick-pause message against the original; pause within 1 frame of the original |
| battle | `battle_pacing.py` | from shared checkpoints, battle start + three turns per speed and the original: same messages, budgets, the pause after every completed message and the on-screen dwell within 2 frames of the original, segment shortened exactly by the printing saved |
| natural-dialogue | `natural_dialogue.py` | touch selection after a cold boot, trainer page: budgets, identical pixels/layout, printing-frame order |

Every Harness gate checks at start and end that the original ITCM code still has
its reviewed hash, the payload bytes equal the expected payload and the SDK ITCM
arena (`0x027FFDAC`/`0x027FFDD0`) starts at or above the payload end. Heap
integrity is walked every 10 frames. Measurement hooks are registered
`exclusive`: emu_harness raises if anything later registers the same address
(DeSmuME would otherwise replace a hook silently).

Warnings in the summary are not failures but must be read: in 60 fps field
scenes DeSmuME drops frames while a task draws two or three glyphs, so a faster
setting can take as many or more frames than the slower one (release-gates run:
fallbacks FAST 29 vs MEDIUM 28 frames with 12 lag frames; natural dialogue
MEDIUM 37 vs SLOW 36 with 11 lag frames). Printing frames without lag are still
strictly ordered. Whether hardware drops the same frames needs a device check.

### Proving a check is not vacuous

`fault_fixture.py CANDIDATE work/build/<dir> --fault NAME` writes a deliberately
broken `FAULT-NAME.nds` and matching `FAULT-NAME.payload.json` (exact original
bytes are verified first; the candidate is never changed). Run
`validate_release.py --rom <dir>/FAULT-NAME.nds --fault-payload <dir>/FAULT-NAME.payload.json --only …`;
its status must be `fault-detected`. Fault reports are marked and are never
release evidence; validate_release refuses a `FAULT-` ROM without the flag.
Pure rules live in `work/tools/text_speed_checks.py` and are unit-tested in
`test_text_speed_checks.py` (including altered expectations: a changed page hash,
a shortened battle pause, an unfreed printer, a growing heap, an overflowing label).

Results on candidate `e9aedbb1…2d13` (2026-10-06):

| Fault | Gates that failed |
| --- | --- |
| `fast-budget` (MEDIUM/FAST 8/9 glyphs per task) | corpus, battle, callbacks, fallbacks, natural-dialogue |
| `slow-flat` (SLOW always 1 glyph) | corpus, battle, callbacks, fallbacks, natural-dialogue |
| `no-phase-reset` | lifecycle |
| `commit-noop` (inlined store in `exit_free`) | options, save, music, corpus |
| `label-overflow` (ten-letter MEDIUM) | options, save |
| `default-slow` (new games SLOW) | new-game |
| `arena-overlap` (ITCM arena over the payload) | lifecycle, options (every Harness gate checks it) |
| `no-control-stop` (batching runs into control codes) | none: no observable difference in any gate, including the authored control message; the stop list is unproven defence, not tested behaviour |
| any fault ROM against the reviewed payload | refused at start: "native payload in ITCM differs" |

The standalone `commit_speed` routine in the payload is never called: the compiler
inlined it into `exit_free`. A first `commit-noop` fixture that patched the
standalone copy went undetected for that reason, not because of a gate gap.

## Release interpretation

Passing these gates establishes bounded automated coverage, not universal memory
safety or subjective readability. Not covered automatically: signs, PC, Pokédex,
mail, naming screen, intro and credits, Pokégear radio/TV, and other scene-specific
printers; physical hardware and a second emulator. Preserve the documented native battle pauses.
Use MEDIUM as the recommended starting point for English playtesting. Device
checks should include short failed-move/status messages, ordinary multi-page
conversations, Options changes and a save/restart during the real playthrough.
Unreleased INSTANT-era saves are not a migration-support requirement.
