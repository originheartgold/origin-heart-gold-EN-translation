# Text speed verification: runbook for agents

The one required read. Background (long, read only when a gate fails and you need
the reasoning): `text_speed_release_checks.md` (gates, fault matrix),
`text_speed_vcount.md` (frame rule), `text_speed_harness.md`.

Purpose: prove that a candidate ROM with the native SLOW/MEDIUM/FAST text speed is
releasable. Everything is a command that writes a report under ignored
`work/build/`; you read the compact `report_summary.py` output, not the JSON.

## Setup (once per worktree)

Run from the worktree root with the repo venv (`/Users/simonvergauwen/Developer/poke/.venv/bin/python`, below `PY`).

- ROMs: real directory `work/rom/` holding symlinks to the user's
  `origin_v4.0.3_cn.nds` and `Pokemon - HeartGold Version (USA).nds` (`*.nds` is ignored).
- Dump: real directory `work/extract/` with symlink `work/extract/v4` to the dump.
- Battery fixture: `trainer.sav` (facing an unbeaten Route 1 trainer, SHA-256
  `7ae21586...26fd5`) in the main checkout's `work/build/memcheck/trainer.sav`.
- `git status --short` must be empty (untracked files count). Never commit or
  publish ROMs, saves, reports or extracted text. Never download anything.

## Commands

```sh
# 1. candidate build (cached by tree+inputs+args; prints one line)
PY work/tools/build_cached.py                       # -> cached|built <rom> <sha256>
# 2. unit suite needs a fixture WITHOUT the feature (the patch is applied by the tests)
PY work/tools/build_cached.py --no-text-speed --no-patch   # -> <fixture rom>
TEXT_SPEED_TEST_ROM=<fixture rom> PY -m unittest discover -s work/tools -p 'test_*.py' 2>&1 | tail -15
# 3. payload recompiles from source
PY work/tools/text_speed_patch.py --check-payload
# 4. artifact check against the candidate and its build report (same cache dir)
PY work/tools/artifact_check.py --rom <rom> --base work/rom/"Pokemon - HeartGold Version (USA).nds" \
   --build-report <cache dir>/build_report.json --ws work/translate/banks --extract work/extract/v4 \
   --output work/build/text-speed/<run>/artifact
# 5. runtime gates (iterate on a subset; full run only at the end)
PY work/research/text_speed/validate_release.py --rom <rom> --save <trainer.sav> \
   --out work/build/text-speed/<run> --jobs 6 --only corpus,battle
PY work/research/text_speed/validate_release.py --rom <rom> --save <trainer.sav> \
   --out work/build/text-speed/<run-full> --jobs 6
# 6. fault matrix: for each fault NAME in fault_fixture.FAULTS
PY work/research/text_speed/fault_fixture.py <rom> work/build/text-speed/faults --fault NAME
PY work/research/text_speed/validate_release.py --rom work/build/text-speed/faults/FAULT-NAME.nds \
   --fault-payload work/build/text-speed/faults/FAULT-NAME.payload.json --save <trainer.sav> \
   --out work/build/text-speed/matrix/NAME --only <gates the fault declares> --jobs 6
# 7. read results (compact)
PY work/research/text_speed/report_summary.py summary work/build/text-speed/<run-full>/report.json
PY work/research/text_speed/report_summary.py diff <old>/report.json <new>/report.json
PY work/research/text_speed/report_summary.py faults work/build/text-speed/matrix
```

`<cache dir>` is `work/build/cache/<key>/` (the `built`/`cached` line names the ROM
inside it). Release evidence needs `status: passed` and `releasable: true`
(summary exits 0 only then); `--only` runs end `partial-passed`, never releasable.

## Rules

- Clean tree, untracked files included; it is checked again at the end of a run.
  `--allow-dirty` (validate_release, build_cached) gives non-releasable results only,
  and build_cached then neither reads nor writes the cache.
- Never run with `python -O`: gates refuse it.
- Fault ROMs (`FAULT-*.nds`) and their reports are never release evidence.
- One DeSmuME battery directory per emulator: the gates handle it; never run two
  emulators on the same `.sav`. Parallel emulators are capped by `EMU_HARNESS_MAX_EMULATORS`.
- Reports, fixtures and screenshots stay under ignored `work/build/`.
- Do not change gate or tool code as part of a verification run unless that is the task.

## Token efficiency

- Run builds, the unit suite, validate_release and the fault matrix in the
  background (`run_in_background`) and wait for the completion notice; do not poll
  or tail logs in a loop. A full validate_release takes about 10 minutes.
- Pipe long output through `tail -15`; build_cached already prints one line.
- Read only `report_summary.py` output. Open a gate's own `report.json` or `.log`
  only for one specific failing gate, and read just its `errors` (e.g. with
  `python -c` printing `errors[:3]`), never the whole file.
- While fixing, iterate with `--only <the gates that failed>`; run the full suite
  once at the end, on a clean committed tree.
- After a change, compare with `report_summary.py diff <baseline> <new>` instead of
  re-reading two summaries.
- Fault matrix: run only the faults relevant to what you changed while iterating;
  the full matrix once at the end. `faults DIR` exits 1 if any is MISSED
  (`dead-code` is a documented unreachable fault, not a miss).
