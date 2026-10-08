# Text speed verification: runbook for agents

The one required read. Background (long, read only when a gate fails and you need
the reasoning): `text_speed_release_checks.md` (gates, fault matrix),
`text_speed_vcount.md` (frame rule), `text_speed_harness.md`.

Purpose: prove that a candidate ROM with the native text-speed feature (Options
TEXT SPEED NORMAL / FAST, D-1604: NORMAL is the original printer plus the 30 fps
catch-up, FAST the batched printer plus the catch-up) is releasable. Everything is
a command that writes a report under ignored `work/build/`; you read the compact
`report_summary.py` output, not the JSON.

## Setup (once per worktree)

Run from the worktree root with the repo venv (`/Users/simonvergauwen/Developer/poke/.venv/bin/python`, below `PY`).

- ROMs: real directory `work/rom/` holding symlinks to the user's
  `origin_v4.0.3_cn.nds` and `Pokemon - HeartGold Version (USA).nds` (`*.nds` is ignored).
- Dump: real directory `work/extract/` with symlink `work/extract/v4` to the dump.
- Battery fixture: `trainer.sav` (facing an unbeaten Route 1 trainer, SHA-256
  `7ae21586...26fd5`) in the main checkout's `work/build/memcheck/trainer.sav`.
- `git status --short` must be empty (untracked files count). Never commit or
  publish ROMs, saves, reports or extracted text. Never download anything.

## Process (user rules, 2026-10-07)

Work in three stages and stop at the first one that fails:

1. **Inner loop, per change** (minutes): cached build, then only the unit tests
   and `--only` gates your change can affect. Repeat until green. Never run the
   full gate suite or any fault run here.
2. **Full suite, once** (~8 min): only when the inner loop is green and the change
   is committed on a clean tree. If any gate fails: stop, do NOT start the fault
   matrix, and report the failure (or fix it and go back to stage 1).
3. **Fault matrix, release candidates only** (~20-25 min in parallel): only after
   stage 2 passed, and only when the task says this is a release candidate or the
   gate/check code changed. Between releases rerun only the faults whose declared
   gates or checked code you changed. Start every fault run at once as its own
   background job; the machine-wide emulator cap (6) queues them. Never one by one.

Stop and report instead of starting another long run when a decision is needed
(a check that would have to be loosened, a behaviour trade-off, a design change).
Never loosen a check to make a run pass.

Checkpoints: commit after every green inner loop, and keep every report under the
worktree's ignored `work/build/` (never `/private/tmp`, which is wiped on restart).
After a crash, read `git log` and the newest summaries and continue from the last
completed stage; do not rerun stages whose commit, ROM and fixture hashes match.

## Commands

```sh
# 1. candidate build (cached by tree+inputs+args; prints one line)
PY work/tools/build_cached.py                       # -> cached|built <rom> <sha256>
# 2. unit suite needs a fixture WITHOUT the feature (the patch is applied by the tests)
PY work/tools/build_cached.py --without text-speed --no-patch   # -> <fixture rom> (its build_report.json is read too)
ARMIPS=<armips v0.11.0> TEXT_SPEED_TEST_ROM=<fixture rom> PY -m unittest discover -s work/tools -p 'test_*.py' 2>&1 | tail -15
# 3. payload recompiles from source
PY work/tools/text_speed_patch.py --check-payload
# 4. artifact check against the candidate and its build report (same cache dir)
PY work/tools/artifact_check.py --rom <rom> --base work/rom/"Pokemon - HeartGold Version (USA).nds" \
   --build-report <cache dir>/build_report.json --ws work/translate/banks --extract work/extract/v4 \
   --output work/build/text-speed/<run>/artifact
# 5. runtime gates (stage 1: subset; stage 2: full run once)
PY work/research/text_speed/validate_release.py --rom <rom> --save <trainer.sav> \
   --out work/build/text-speed/<run> --jobs 6 --only corpus,battle
PY work/research/text_speed/validate_release.py --rom <rom> --save <trainer.sav> \
   --out work/build/text-speed/<run-full> --jobs 6
# 6. fault matrix (stage 3 only): for each fault NAME in fault_fixture.FAULTS, all in parallel
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
  or tail logs in a loop. A full validate_release takes about 8 minutes.
- Pipe long output through `tail -15`; build_cached already prints one line.
- Read only `report_summary.py` output. Open a gate's own `report.json` or `.log`
  only for one specific failing gate, and read just its `errors` (e.g. with
  `python -c` printing `errors[:3]`), never the whole file.
- While fixing, iterate with `--only <the gates that failed>`; run the full suite
  once at the end, on a clean committed tree.
- After a change, compare with `report_summary.py diff <baseline> <new>` instead of
  re-reading two summaries.
- Fault matrix: see Process stage 3. `faults DIR` exits 1 if any is MISSED
  (`dead-code` is a documented unreachable fault, not a miss).
