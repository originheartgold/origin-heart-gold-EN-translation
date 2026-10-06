# Text-speed RC validation recipe

Run from the experimental worktree root. All reports, temporary batteries,
fixture ROMs and screenshots belong under ignored `work/build/`. Use original
battery-save inputs, not savestates from another ROM. Keep source ROM/save hashes
unchanged. Never commit ROMs, battery saves or extracted game text.

## Build-time gates

1. Run the full `work/tools/test_*.py` unittest suite with `TEXT_SPEED_TEST_ROM`
   pointing to the existing demand-loaded English binary fixture. Require no
   failures, errors or skips; missing local ROM/compiler fixtures are not a pass.
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

Each script accepts `--rom`, `--save`, `--out` unless noted. Use the trainer
battery fixture for the existing-save scenarios. Scripts validate the candidate
payload and input identities; output reports must say `status: passed`.

- `work/research/text_speed/harness_options.py`: native text choices, row/value
  wrap, touch/buttons, Confirm/Quit/B, reserved setting repair and repeated entry.
- `music_interaction.py`: nine music/text combinations, getter observations,
  cancellation of pending changes and preservation of all other Options rows.
- `save_persistence.py`: actual in-game save/reset/Continue for all three choices.
- `new_game_default.py`: omit `--save`; read-only blank-battery Options init and
  publication ordering. It must observe MEDIUM before runtime publication.
- `printer_lifecycle.py`: phase initialization after deliberate private-byte
  poisoning, original initializer state and repeated allocation reuse.
- `harness_fallbacks.py`: same-candidate checkpoint, invalid/null runtime paths,
  legacy music bits, explicit delay and bounded glyph budgets. Its deliberate
  test RAM modifications are branch coverage, not natural gameplay evidence.
- `callback_regression.py`: sixteen controlled cases against the original task:
  callback dispatch, four busy retries, held A and held B at all three speeds.
  Busy retries use a byte-verified existing return-zero code sequence and override
  only its return value. No executable test code is injected. Completed pixels,
  glyph layouts and callback/task cadence must match as applicable. Heap checks
  here are end-of-case snapshots, not continuous memory certification.
- `harness_regression.py`: six source messages and 21 pages per speed, preserving
  glyph counts, layout, completed pixels and explicit page waits.
- Generate a separate ROM with `control_fixture.py <candidate> <fixture>` and run
  `harness_regression.py --controls` on that fixture. The authored message checks
  scrolling, clear, enlarged font and a 60-tick pause. This derived ROM must never
  be confused with the deliverable; record its own hash.
- `battle_pacing.py --mode 0`, `--mode 1`, `--mode 2`: three turns each without A/B
  input, actual move messages, visible text-region observations and memory checks.
  RNG can differ across modes; whole-turn durations are not a controlled benchmark.

The shared harness catches exceptions inside ARM9 execution hooks and raises on
the Python side after the emulator cycle. The first failure stays fatal and later
hooks cannot mutate the experiment. A callback assertion must never be accepted
as a passing run merely because ctypes logged and swallowed the exception.

## Release interpretation

Passing these gates establishes bounded automated coverage, not universal memory
safety or subjective readability. Preserve the documented native battle pauses.
Use MEDIUM as the recommended starting point for English playtesting. Device
checks should include short failed-move/status messages, ordinary multi-page
conversations, Options changes and a save/restart during the real playthrough.
Unreleased INSTANT-era saves are not a migration-support requirement.
