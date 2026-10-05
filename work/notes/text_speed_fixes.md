# Text-speed review fixes — 2026-10-05

All three findings in [the independent review](text_speed_review.md) are fixed in the isolated `codex/text-speed-research` worktree. One subagent investigated and fixed each finding; the coordinator reviewed the combined changes, regenerated the native cache and built/validated a fresh candidate. No source ROM, original save, translation bank or main-checkout file was edited. Nothing was committed, merged or published.

Subsequent integration and expanded harness validation: [text_speed_harness.md](text_speed_harness.md). That report supersedes the candidate below; this document records the earlier fix stage.

## Earlier fixed candidate

- ROM (local testing only): `work/build/text-speed/fixed-release/origin_hg_v4.0.3_en_wip.nds`
- SHA-256: `14726d84eadf43856731480a79d4de0aa2155324514da77d6c0001244786f5de`
- Distribution candidate: `work/build/text-speed/fixed-release/Origin_HeartGold_v4.0.3_EN_wip.xdelta`
- Build report: `work/build/text-speed/fixed-release/build_report.json`
- Standalone artifact report: `work/build/text-speed/fixed-validation/artifact.json`

This supersedes the prior `full-build` candidate. Releases remain xdelta patches against the established USA base, never ROMs.

## Finding 1: runtime readiness

`native.c` no longer tests cartridge-save existence. The main runtime SaveData pointer returned by `02001194` is published at `02000CDA` only after construction and block/Options initialization or loading. A read-only blank-battery trace confirmed that ordering. The earlier constructor-internal pointer is a different global and is not used by this code.

The native mode reader now uses that published pointer, retaining null-pointer and invalid-mode fallbacks to NORMAL. Fresh games can therefore use their initialized Options even while the cartridge-save-exists flag is zero.

The readiness agent booted the fixed ROM from an old battery save and created a matching new checkpoint. It checked the checkpoint's ITCM against the fixed payload before each controlled regression, avoiding stale executable RAM from the old ROM. Eight cases passed:

- Save-exists zero: NORMAL, FAST and INSTANT correctly select their respective rendering paths.
- Invalid mode 3 and temporarily absent runtime pointer fall back to NORMAL.
- Old music values 0/1/2 retain their values and default text speed to NORMAL.

The controlled glyph spans were 54 / 21 / 2 frames. These tests deliberately change live test RAM; they are not claimed as natural menu interaction or comprehensive memory certification. Separate blank-battery startup tracing is read-only. See `work/research/text_speed/review/save_readiness_fix/README.md` and its two regression scripts. Reports are under `work/build/text-speed/save-readiness-fix/`.

Valid old in-game saves still upgrade without preparation. New-save → old-ROM downgrade support is outside the user's required scope.

## Finding 2: standalone artifact verification

`build.verify_text_speed` is now shared by normal builds and the standalone artifact checker. It checks ROM feature presence rather than treating absent metadata as automatic permission to skip validation:

- Native candidates reject missing feature metadata or a false opt-out.
- Legacy candidates without the native feature remain supported.
- New opt-outs explicitly record `--no-text-speed` or `--no-hardcoded`.
- Enabled artifact validation calls the feature verifier and requires payload reproduction.
- Patcher, C source, labels header and cached payload are fingerprinted and checked again after verification.

The prior hardcoded verifier still checks individual strings, pointers and instructions, as well as the composed final ARM9 hash. Reproduction errors and missing clang fail enabled release artifact validation. Ordinary cached builds do not require clang.

The actual rebuilt ROM passed the standalone artifact gate. Its report contains both successful native verification and successful reproduction, plus fingerprints for all four feature files. Unit regressions cover verifier rejection, missing metadata, stale source, reproduction/compiler failures, opt-outs and changed verification inputs.

## Finding 3: cached payload validation

`text_speed_patch.py` independently pins a canonical digest over source identity, base, executable bytes and the full symbol map. Both cached and explicitly supplied payloads are validated before ROM access. Checks include exact schema, source identity, base, size, canonical encoding, required symbol inventory, distinct bounded Thumb entry points and the independent pin.

Current payload: 716 bytes; canonical digest:

`a622530bc43d4736c91af9e6ede5f07b801e42d394a84a60c32cd8f12b9d58f5`

The reviewed corruption reproducer now rejects both an infinite-loop instruction and a redirected `print_task` symbol. The test suite also covers malformed payload variants, atomic rejection and reproduction mismatch in code or symbols. `--check-payload` provides a non-skipping release reproduction command.

Future C/header changes require regeneration, review of the compiled output and an updated independent pin. Do not automatically refresh the pin during ordinary builds: that would defeat its purpose. The cache reproduces with the documented local Apple clang 21 toolchain; an unreviewed compiler's different output intentionally fails reproduction.

## Integrated validation

- **474 tooling tests passed, zero failures/errors/skips.** Existing local Chinese ROM and extract fixtures are exposed through ignored worktree symlinks; nothing was downloaded. Report: `fixed-validation/tool-suite.json`.
- Fresh full build passed NARC/text/font/graphics/hardcoded/native verification. Xdelta was reapplied against the USA base and matched the built ROM.
- Corrected standalone artifact gate passed, including native reproduction and feature-source fingerprints.
- `validate_release.py` cold-booted each mode from the same old trainer battery save. It asserts default NORMAL, touch selection, deferred commit, preservation of neighboring option bits, 54 glyphs on the intended page, increasing speed and identical completed dialogue pixels. All modes passed, with 257 heap walks each and no reported memory/probe errors. The three runs reached trainer battle command selection; the INSTANT battle screenshot was visually checked.
- Observed frame spans in these independent cold boots were NORMAL 69, FAST 25, INSTANT 2. They are emulator-frame observations, not fixed hardware guarantees or same-machine-state benchmarks. The isolated readiness comparison above uses a shared checkpoint.
- Fresh candidate persistence: Cancel preserves NORMAL, Confirm writes INSTANT, an actual in-game save and reset/Continue retain INSTANT. Saved Options values were 512 → 512 → 520 → 520; 302 heap walks passed.
- An isolated authored control fixture made from the new ROM preserves page waits and scrolling. First/final page crops remain identical after 240 idle frames; the requested 60-frame pause separates glyph batches by 63 frame intervals; SIZE 200/100 restoration was visually checked. All 307 heap walks passed. This fixture changes one message only in an ignored test ROM.

Runtime reports: `fixed-validation/native-modes2/report.json`, `fixed-validation/persistence/report.json`, `fixed-validation/controls/report.json`, and `fixed-validation/control-persistence-assertions.json`. All paths here are relative to `work/build/text-speed/` unless stated otherwise.

The first mode-matrix attempt used one-frame A pulses; FAST missed the initial synthetic input, so the dialogue-count assertion correctly failed. It was not accepted as passing evidence. The maintained harness uses six-frame presses, and the full rerun passed. No implementation change was made to hide this harness failure. An initial ad-hoc image assertion used system Python without Pillow; it was rerun successfully with the existing project environment.

## Commands

Run from the worktree root using the existing Python environment with ndspy, py-desmume and Pillow:

```sh
python work/tools/text_speed_patch.py --check-payload
TEXT_SPEED_TEST_ROM=/path/to/demand-loaded-English.nds python -m unittest discover -s work/tools -p 'test_*.py'
python work/tools/artifact_check.py --rom work/build/text-speed/fixed-release/origin_hg_v4.0.3_en_wip.nds --base /path/to/HeartGold-USA.nds --build-report work/build/text-speed/fixed-release/build_report.json --extract /path/to/extract/v4 --output work/build/text-speed/fixed-validation/artifact
python work/research/text_speed/validate_release.py --rom work/build/text-speed/fixed-release/origin_hg_v4.0.3_en_wip.nds --trainer-save /path/to/trainer.sav --output work/build/text-speed/new-validation
```

The emulator uses private configuration/output directories. On this Mac its native application initialization requires execution outside the restricted sandbox.

## Remaining release sign-off

The three reported issues are resolved. This does not replace the previously identified second-emulator, DS/flashcart, extended-session and broader battle/callback checks. Full natural interaction selecting speed after story menu unlock but before the first save has not been completed; the readiness and rendering conditions are verified separately as described above. No universal hardware or rare-script certification is claimed.
