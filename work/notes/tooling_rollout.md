# Tooling rollout

**Status (2026-10-09): historical.** The rc5 quality tools this note describes (quality_runner, static_text_check and its text_*_check helpers, review_site) were removed in the 2026-10-09 cleanup; the release gate is `check.py --full --strict-release` plus `--emu`. The findings below stay as the record; `git log --diff-filter=D -- work/tools` finds the scripts.

## Stage 1: local quality gate

Run all commands from the repository root:

```sh
python3 work/tools/quality_runner.py
python3 work/tools/quality_runner.py --checks tools docs --timeout 120
python3 work/tools/quality_runner.py --checks qa --output work/build/quality/manual-review
```

The runner executes three checks sequentially in separate subprocesses, using the
same Python interpreter as the caller:

- `tools`: explicit `test_*.py` discovery in `work/tools`.
- `docs`: separate discovery in `work/tools/docs`, which ordinary top-level
  discovery misses because this directory is not a Python package.
- `qa`: `qa.py check work/translate/banks` with its structured JSON output.

No packages are downloaded, ROMs built, or translation banks changed. Some existing
tests optionally inspect local ROMs; this is not a guarantee of ROM-independent
coverage. Missing optional fixtures appear as skips. Missing mandatory imported
modules are reported as unavailable, with the traceback in the suite result.

Each run creates a new directory beneath ignored `work/build/quality/` containing
`report.json`, per-check logs, and per-check JSON results. A custom output directory
must be new and inside `work/build`; this avoids publishing logs containing game
text or overwriting earlier evidence. Keep these artifacts local.

The version-1 report includes exact command argument arrays, working directory,
interpreter, return codes, durations, statuses, logs, and result summaries. Suite
results include test/failure/error/skip counts and failure/error/skip details. QA
results retain all issues in `qa.json` and summary counts in the report. Warnings
remain warnings and do not independently fail the gate. The console displays
counts, including skips and QA warnings.

Exit 0 means every selected check passed. A successful suite with skipped tests is
`incomplete` and returns a nonzero gate exit; other non-passing states are `failed`,
`timeout`, and `unavailable`. Zero discovered tests, zero checked banks, or zero
checked translated strings fail rather than silently producing green results.
A skipped check is never a claim of complete coverage. `--checks` limits the scope:
a passing subset does not imply that the omitted checks passed.

`--timeout` is a finite positive per-check limit, default 300 seconds. Timeout logs
retain output written before termination; no return code is invented. The current
checks spawn direct Python subprocesses rather than emulator process trees.

Synthetic orchestration tests cover failures, skipped tests, missing dependencies,
missing executables, timeouts with partial output, empty discovery/QA, QA warnings,
and a process failure contradicting a passing payload. They run inside the tools
suite and require only the standard library.

## Subsequent stages

Runtime integration is pending; this gate does not yet launch emulator scenarios.
The agreed runtime policy is to block new English regressions, report findings that
also reproduce in the untouched Chinese hack as baseline findings, and treat skips
as incomplete. Establish reproducible scenarios, explicit baseline comparisons,
and failure evidence before adding runtime checks to the gate. Original hack bugs
remain findings rather than fixes. Follow with targeted static binary checks and
debugger integration where investigation demonstrates a need.

## Initial validation (2026-10-02)

The full runner passed with 100 tools tests (including eight new orchestration
tests), 25 docs tests, and no skipped tests. Translation QA checked 76,862 strings
in 821 banks: zero errors and 16,023 existing warnings. This is a recorded warning
baseline, not a waiver or automatic warning suppression. The local report is
`work/build/quality/20261002T152259.134041Z/report.json`.

## Stage 2: runtime instrumentation gate

```sh
.venv/bin/python work/tools/memcheck.py run --scenario summary --timeout 120 --out work/build/memcheck-stage2
```

The local `.venv` uses pinned `work/tools/requirements-runtime.txt` dependencies. Runtime integration into the quality
runner remains pending until emulator evidence is reviewed. No ROM is built here.
The existing scenarios and local raw 512 KB battery saves are inputs.

`memcheck run` now validates scenario names, ROM files, hook code signatures and
save files. Missing/invalid saves, failed child processes, missing dependencies,
timeouts, unarmed instrumentation, no heap observations and truncated scripts are
incomplete, with exit 2. English-only observed failure signatures return exit 1.
A complete comparison without English-only failures returns exit 0. Chinese-only
failures are baseline findings but make the comparison incomplete because they may
truncate the Chinese run. Identical failures in both runs are baseline findings;
if a low-address write truncated either script, coverage remains incomplete.

Allocation signatures compare heap and request size; low-address writes compare
PC; heap corruption compares its diagnostic with RAM addresses normalized and
frames excluded. Different signatures never cancel each other. These signatures
are conservative triage evidence, not a proof that two failures have the same
root cause. Negative estimated spare room is a warning, not an observed failed
allocation. Static whole-bank analysis remains reporting-only.

Each child has a finite positive timeout (120 seconds by default). Periodic
600-frame raw snapshots retain partial diagnostics if a child times out. Report
schema 2 records overall status/counts, scenario status/findings, commands,
return codes, durations, stdout/stderr and raw Chinese/English observations:
frames, armed state, script completion, heap minimum spare values, allocation
failures, low-address write PCs, corruption diagnostic and screenshot paths.
Artifacts and custom report paths must remain under ignored `work/build`.
`report.json` is written to the output directory unless `--json` selects a path.
Use a separate output directory for each run to preserve earlier evidence.

Arming currently records completion of the scripted boot sequence; it does not
assert that Continue reached the intended field or that the target menu opened.
Scenario state assertions and clock/RNG control still require investigation.
Ten standard-library synthetic tests cover signature comparison, missing saves,
invalid selection, incomplete evidence and timeouts retaining partial diagnostics.

Stage 2 review adds interpreter/dependency versions and streamed SHA-256 identities
for both ROMs and scenario saves, capability preflight, explicit evidence gaps and
atomic report writes. Without `--out`, each run creates a fresh timestamped directory
under `work/build/memcheck-runs`; fixture saves remain under `work/build/memcheck`.
Verbose heap rows and reporting-only static growth predictions are retained.
`emu_smoke.py` resolves its output directory before changing to its temporary
emulator directory, so relative screenshot paths work correctly.

## Stage 3: bounded heap inspection and scenario evidence

The first runtime investigation found that py-desmume implements a RAM slice as
individual byte reads. Copying all 4 MB every 30 frames severely slowed inspection.
The approved replacement reads only heap-table entries and live block headers,
with width-aware RAM bounds, cycle detection and a block-count cap. The 30-frame
inspection interval is preserved. Uninitialized heap tables may be skipped before
arming; invalid tables after arming become explicit incomplete evidence.

Reports add integrity-check counts, heap-table errors, observed message-load
arguments and call sites, plus hashes of the scenario manifest and checker.
The summary scenario requires observed message loads for archive 27, banks 295
and 739 on heap 19 in both ROMs. Missing loads are incomplete coverage rather than
a claimed game regression. This verifies resource loading, not visible menu state.
Thirteen synthetic tests include equivalence against the original snapshot walker
for healthy/dead heaps, bad signatures, broken backlinks and bad bounds. Sparse
memory fixtures reject bulk RAM slicing and unsafe reads; cycle and invalid-table
cases exercise the added guards.

## Stage 4: optional runtime memory gate

Runtime memory instrumentation is now explicitly selectable; the default remains
`tools docs qa`. Use the environment with installed emulator dependencies:

```sh
.venv/bin/python work/tools/quality_runner.py --checks runtime
.venv/bin/python work/tools/quality_runner.py --checks tools docs qa runtime --runtime-scenarios summary
.venv/bin/python work/tools/quality_runner.py --checks runtime --runtime-scenarios all --timeout 1800
```

`--runtime-scenarios` (alias `--scenario`) accepts comma-separated scenario names
or `all`; its default is `summary`. `--runtime-timeout` defaults to 120 seconds
per emulator child. The outer `--timeout` still defaults to 300 seconds **per
check**, so budget the runtime check for two children per selected scenario plus
static-analysis overhead. For 17 scenarios allowing every child its full
120-second limit requires more than 4,080 seconds; `--timeout 4500` is a reasonable
full worst-case budget. A budget of 1,800 seconds covers the observed normal run
rate, while intentionally failing sooner than the full worst case.

The runtime check delegates to `memcheck.py run`, writes its full structured
report to `runtime.json`, and stores emulator logs, screenshots, and other
artifacts beneath the new quality run's `runtime/` directory. The unified report
includes selected/executed/passed/failed/incomplete scenario counts and finding
counts; it references the detailed report rather than duplicating its ROM data.
Missing runtime prerequisites are unavailable, child or outer timeouts are
timeout, and insufficient evidence is incomplete. Contradictory counts or a
passing payload from a failing process fail. A zero-scenario report fails.
Aggregate status preserves failures, timeouts, unavailable checks, and incomplete
coverage instead of labeling every non-passing result failed. Every non-passing
aggregate still exits nonzero. Reports also record the Python version.

On POSIX, checks run in a new process group; an outer timeout kills the group and
waits for the direct child, so nested emulator children do not remain running.
On other platforms only the direct child is terminated. Synthetic tests exercise
runtime result states, inconsistent payloads, findings, and POSIX descendant
termination without starting an emulator.

Passing runtime instrumentation means the selected memory comparisons passed.
It does not prove that every input reached the intended menu or establish visual
correctness. The summary scenario asserts expected message loads; other scenarios
still need screenshot review and explicit state evidence. Matched Chinese baseline
findings remain reported rather than fixed. The earlier pending-stage paragraph
records the state before this optional integration.

Stage-4 standard-gate validation passed on 2026-10-02: 127 tools tests,
25 docs tests, no failures/errors/skips, and translation QA unchanged at zero
errors and 16,023 warnings. Report:
`work/build/quality/20261002T160543.477875Z/report.json`.
The runtime parser also rejects passing scenarios without both completed Chinese
and English child runs and structured raw evidence. This integration validation
uses synthetic runtime payloads; actual emulator validation is a separate run.

## Stage 5: existing ROM artifact verification

Run `.venv/bin/python work/tools/artifact_check.py` to verify the existing English ROM without building or saving a ROM. It uses a fresh workspace export and the existing `build.verify_rom` function: message archive/container round trips, encoded translation equality, name buffers, restored glyphs, graphics member/code hashes, hardcoded patches, and audited graphics runtime allocations. It does not call the build entry point.

Options select `--rom`, `--base`, `--build-report`, `--ws`, and `--extract`. `--output` selects the parent for a new unique run directory; the default is ignored `work/build/artifact-checks/`. Reports and fresh exported text remain local there. JSON records SHA-256 input provenance, export counts/problems, verifier output or failure, and verifier/config file hashes. The ROM and base must match build-report SHA-1 identities before its graphics/hardcoded metadata is trusted. This metadata is a historical build manifest; the verifier does not prove every current graphics source has been included.

Missing assets/verification metadata are incomplete (exit 2). Empty inputs, stale identities, any export fallback/problem, zero exported banks/strings, and verification failures fail (exit 1). Success exits 0. Python optimization is rejected because the reused verifier depends on assertions. Inputs are checked again after successful verification to detect concurrent changes. Fourteen synthetic tests cover these orchestration conditions without building a ROM or starting an emulator.

The first real run on 2026-10-02 correctly rejects the existing RC4 ROM (SHA-1 `7234f7b34933e0dc8902d1d079e4747490241a2d`): `data/linkcapture.narc` screen 25 references tile 74 while the runtime loads only tiles 0–47. This is the already documented Chain Logger defect in `graphics_layout_audit.md`; current production graphics have been repaired, but the existing ROM has not been rebuilt. Fresh text export contains 76,862 strings, all English, 1,019 compressed names, and zero problems. No game data was corrected by this rollout. The failed artifact result remains visible pending the user’s decision about a later build.

### Optional artifact quality gate

Run `.venv/bin/python work/tools/quality_runner.py --checks artifacts`, or include `artifacts` alongside the other selected checks. Default checks remain tools, docs, and QA. The artifact payload is saved as `artifacts.json` in the quality run directory; detailed export artifacts go into a fresh nested `artifact-checks/` run. Both artifact `--output` and `--json` paths are restricted to ignored `work/build/`. Passing payloads require nonzero exported strings, no export problems, completed identity/export/artifact checks, and a populated verifier result. Failed reasons remain in the console and unified JSON.

Integration validation on 2026-10-02: 143 tools tests and 25 docs tests pass with no failures/errors/skips; translation QA has zero errors and the unchanged 16,023 warnings. Standard report: `work/build/quality/20261002T161724.908478Z/report.json`. The optional artifact gate exits nonzero for the documented stale RC4 Chain Logger allocation defect, preserving that finding: `work/build/quality/20261002T161736.946440Z/report.json`. See [graphics allocation audit](graphics_layout_audit.md) for the known cause and repaired production assets. No ROM rebuild or gameplay change was made.

The coordinator separately verified all 17 runtime scenarios: 233,396 frames, 7,118 heap checks, 132 screenshots, and zero instrumentation findings. This confirms memory instrumentation coverage, not visual correctness or complete state reachability: screenshot review identified a description discrepancy in the English full-bag scenario despite its passing memory checks. Investigation and further regression evidence take priority; game changes remain pending discussion with the user.

## Stage 6: item-description capacity regression gate

```sh
.venv/bin/python work/tools/quality_runner.py --checks buffers
.venv/bin/python work/tools/quality_runner.py --checks buffers artifacts --rom work/build/candidate.nds --build-report work/build/candidate_report.json
```

The optional `buffers` check delegates to `text_buffer_check.py` and compares
stored item-description lengths with the allocation capacity read from the
selected English ROM's guarded allocation instructions. It also checks current
workspace bank `a027/0218.json` against that capacity. Defaults remain tools, docs,
and QA. A future capacity is read dynamically, so a validated allocation of 128
units can pass without hardcoding that proposed change into the gate.

`buffers.json` contains ROM provenance, code evidence, lengths, offending IDs,
and workspace findings. A passing payload requires positive capacity and checked
counts, maximum lengths within capacity, no findings, and passing ROM and workspace
statuses. Missing or inconsistent result evidence cannot silently pass. This
check diagnoses a capacity mismatch; it does not change code or translations.

`--rom` selects the English ROM for any selected buffers, artifacts, and runtime
checks. `--build-report` selects the matching build manifest for artifacts. Without
these options, each checker retains its existing default inputs. This lets a later
isolated candidate build be tested explicitly rather than repeatedly testing the
old default ROM. Runtime retains its untouched Chinese reference.

The checker now independently guards four direct description consumers: shop,
bag, overlay 9 (screen context unconfirmed), and PC. The first three allocate
114 units; PC allocates 1024. The smallest capacity governs the bank gate and
individual overflow IDs are reported per consumer.

Validation on 2026-10-02: 19 quality-runner synthetic tests passed; the standard
gate passed 150 tools tests and 25 docs tests with no skips/errors/failures. QA
remains at zero errors and 16,023 warnings. Report:
`work/build/quality/20261002T163231.782526Z/report.json`.
The real optional buffer gate correctly **failed**: capacity 114, 791 descriptions,
17 ROM overflows and 17 workspace overflows. Report:
`work/build/quality/20261002T163238.521171Z/report.json`.
See the [item-description investigation and proposed fix](item_description_fix_proposal.md)
for the evidence. The wording alternatives are awaiting
[manual review](item_description_manual_review.md); no game-data change is approved.

## Isolated candidate builds

`build.py --work-dir work/build/<candidate> --no-patch` keeps exports, ROM output,
build report and verification scratch files together, without replacing the
existing RC4 export or manifest. Explicit `--out` and `--patch` still override
their derived defaults. Base-ROM provenance is recorded even with `--no-patch`.
Three ROM-free tests verify output paths and isolation of existing report/export
files. No candidate ROM was built during this tooling change; game-data fixes
remain pending discussion.

Final combined validation: 156 tools tests and 25 docs tests passed without
failures, errors or skips; QA reported zero errors and 16,023 warnings.
Report: `work/build/quality/20261002T164014.726181Z/report.json`.
The extended buffer gate intentionally failed the same 17 English descriptions:
`work/build/quality/20261002T163926.813293Z/report.json`.
No ROM was built or changed by this gate.

## Stage 7: temporal runtime checkpoint evidence

The description wording proposals are saved for manual review. Tooling work
continues without applying translations or changing ROMs.

`memcheck.py` now records `boot` and every named screenshot checkpoint, including
the frame, observed message loads, screenshot path and capture status. A scenario
may declare `expected_checkpoints`, where each checkpoint names an earlier
checkpoint through `since` and a nonempty list of `{narc, bank, heap}` loads.
The witness must occur strictly after that earlier checkpoint and no later than
the target checkpoint. Earlier preload events cannot satisfy later transitions.

For example, summary `skills` requires bank 712 on heap 19 between `info` and
`skills`; `skills_switched` requires a fresh bank 712 load between `skills` and
`skills_switched`. Summary entry requires bank 295, and the move-details stage
requires bank 738. Both ordinary and full-party summary scenarios have these
four expectations, based on paired runtime timing and screenshots.

This proves configured resource transitions. It does not assert every button
press, actual move order, Pokémon identity or final game state. The explicit
`coverage_scope` is included in results. Screenshot capture records evidence for
review; it does not automatically interpret the screenshot.

`memory_status` is reported separately from paired `coverage` status. Missing
expectations, checkpoints, captures or temporal witnesses produce incomplete
coverage. A scenario can therefore have clean memory results and remain
incomplete overall. New English memory regressions still fail; matching Chinese
baseline findings remain reported and nonblocking.

Malformed expectations are rejected before emulator execution. Tests cover stale
preloads, interval boundaries, wrong banks, missing checkpoints, uncaptured
screenshots, truncated scripts, empty objectives and malformed manifests. The
unified runner requires paired coverage evidence and cannot turn a memory-only
result into a green runtime gate.

The user chose to leave battle incomplete. Its known coverage warnings remain in
the manifest; the battle script and fixture are unchanged. Other scenarios have
no checkpoint objectives yet and also remain incomplete for coverage. The prior
17-pair run is evidence of memory checks, not comprehensive interaction coverage.

Standard validation: 163 tools tests and 25 docs tests passed, with zero failures,
errors or skips. Translation QA: zero errors and 16,023 warnings. Report:
`work/build/quality/20261002T180847.674084Z/report.json`.

Real paired validation of `summary` and `summary_full` passed all four configured
temporal checkpoints on both unchanged ROMs. The four runs completed 31,484 frames
and 972 heap inspections with no memory findings. Both coverage results passed
within their declared resource-checkpoint scope. The unified runner also parsed
the resulting report as passed. Evidence:
`work/build/runtime-checkpoints-summary/report.json`.

## Stage 8: runtime rejected-text-copy detection

`memcheck.py` now observes the guarded native String-copy operation. It records
requested units, destination capacity, caller and frame whenever the game rejects
an oversized copy. It does not modify the copy or bypass its bounds check.
Invalid pointers produce instrumentation gaps rather than unchecked reads.
The result is reported as `text_status`, separately from `memory_status` and
checkpoint coverage. A clean heap cannot hide a new English text rejection.

Known item-description calls have scoped item IDs and caller context. Comparing
the same rejected item across ROMs ignores text length and RAM placement, while
retaining the item, call sites and capacity. This permits differing Chinese and
English lengths to be reported as a shared baseline when both reject. Generic
copies without item context are compared more conservatively using caller,
capacity and requested length. Chinese-only rejections make comparison incomplete;
new English rejections fail; shared rejections are reported and nonblocking.

The unified runner requires positive copy observations and no text-probe errors
from both ROMs before a runtime result can pass. Reports lacking this newer
evidence remain incomplete rather than silently passing.

Real paired `bag_full` validation against unchanged ROMs observed 1,041 bounded
copies in each ROM, with no instrumentation errors. Chinese rejected none;
English rejected Scope Lens twice and Sticky Barb once. Both are among the
already documented oversized descriptions. Heap checks passed, text checks
failed, and the unified runner correctly classified the result as failed.
Evidence: `work/build/runtime-text-copy-bag-full/report.json`.

Standard validation: 175 tools tests and 25 docs tests passed. Translation QA:
zero errors and 16,023 warnings. Report:
`work/build/quality/20261002T183024.599464Z/report.json`.
No wording, game code, graphics, fixture or ROM was changed.

## Stage 9: bag and shop entry checkpoints

Checkpoints now snapshot all item-description requests, including accepted copies,
with item ID, heap, caller, frame and destination. Expectations can require exact
`{item, heap}` requests in the same strict temporal interval as resource loads.
These requests prove which description was requested; text-copy rejection status
independently reports whether the copy was rejected. They do not prove rendering.

The additional `start` checkpoint records frame zero. It permits explicit
expectations for shop resources loaded during boot, before the first screenshot.
Reserved `start` and `boot` names cannot be reused for screenshot checkpoints.
Malformed or empty evidence lists, stale requests, requests after a checkpoint,
wrong item IDs and wrong heaps are covered by synthetic tests.

Five additional scenarios now have scoped entry expectations:

- `bag`, `bag_townmap`: bag bank 10 on heap 6 after boot and before `open`.
- `bag_full`: the same bank plus a Scope Lens description request on heap 6
  before `open`.
- `mart`: buying banks 428/218 on heaps 8/11 and item 4 on heap 11 between
  `start` and `buy`; selling bank 10 on heap 6 between `mart_menu` and `sell`.
- `mart_full`: selling bank 10 on heap 6 after boot and before `sell`.

All 17 definitions validate. Seven scenarios now have configured temporal
expectations, including the two summary scenarios. The coverage scopes remain
explicitly limited: bag pockets, quantity widgets, item menus, actual rendering
and final state are not automatically established by these witnesses. Battle
remains incomplete under the user's decision, and its script/fixture are unchanged.

Real paired validation of all five new bag/shop scenarios passed their configured
coverage checks, with no probe errors. `bag`, `bag_townmap` and `mart` passed
overall. `bag_full` and `mart_full` failed on the known English description-copy
rejections, while their memory checks and checkpoint coverage passed. The ten
ROM runs completed 63,488 frames and 1,922 heap inspections. ROMs, save fixtures,
checker and manifest identities remained unchanged throughout the validation.
Evidence: `work/build/runtime-bag-shop-checkpoints/report.json`.

Final standard gate: 180 tools tests and 25 docs tests passed with no failures,
errors or skips. Translation QA: zero errors and 16,023 warnings. Report:
`work/build/quality/20261002T183519.842412Z/report.json`.

The unified `--checks runtime --runtime-scenarios summary` control also passed
with the new instrumentation: paired memory, temporal coverage and text evidence
all passed, with zero findings. Runtime duration: 40.023 seconds. Report:
`work/build/quality/20261002T183943.491797Z/report.json`.


## Stage 10: QA-owned non-battle entry coverage (2026-10-04)

The user assigned this work to QA/testing; developers own fixes. Known description
failures remain failing checks. Wording proposals, game code, graphics, ROMs and
save fixtures are not changed by this stage. Battle remains explicitly deferred.

Nine additional scenarios now declare temporal resource witnesses, using the
historical paired trace audit as the hypothesis and fresh paired emulator runs
for validation: party and full-party menu (bank 293, heap 12), Pokedex list
(790, 37), trainer card (717, 25), Pokegear phone (264, 91), options (43, 38),
save prompt (416, 4), photographer prompt (439/11 and 29/32 during boot), and
touch summary (295/19 on entry, then a fresh 712/19 after info_tapped).

Each new scenario states its limited coverage scope. These witnesses do not
prove party order, card reversal, app switching, saved settings, cancellation,
photo capture, selected Pokemon or ribbon navigation. The Pokegear description
now labels app navigation as attempted rather than claiming all apps are tested.
Sixteen of seventeen scenarios have scoped expectations; that is not complete
interaction coverage. Battle still has no expectations and retains its warnings.

Coverage reports now list configured_checkpoints and unasserted_checkpoints,
so downstream reviewers can see screenshot stages without assertions even when
the configured scope passes. A regression test verifies that partial scoped
coverage remains distinguishable from an entirely unconfigured scenario.

QA backlog, independent of developer fixes:
- Guarded memory assertions for selected Pokemon, party order and move order.
- State witnesses for reused-resource pages and exit/cancellation outcomes.
- Rendering checks for text regions, including blank descriptions.
- Fixture integrity and emulator configuration checks across each paired run.
- Battle script/fixture work only when its explicit deferral is lifted.

Developer acceptance remains separate: reproduce the current text rejection,
apply the developer's fix in an isolated candidate, then run buffers, artifacts
and paired runtime checks with that candidate's matching build report. Do not
suppress existing rejections to obtain a green result.


Visual review found two test-label/input problems, not game regressions:
- The legacy Pokedex `list` shot shows the landing screen; `entry` shows an
  actual Pokemon entry. Scope and description now say startup/landing.
- Trainer-card `front` and `back` both showed the front in both ROMs when the
  script pressed A. The displayed instruction asks for a touch. A separate
  paired run tests a touch at bottom-screen coordinates (128, 96).

The nine-scenario discovery run started before the additive report fields and
these follow-up changes. Its recorded checker/manifest hashes describe that
starting revision; the changed card input is validated in a separate run.
No instrumentation hooks, native reads or comparison rules changed during it.


The corrected trainer-card touch run passed in both ROMs. Manual screenshot
review confirms the reverse displays Hall of Fame/link statistics in English
and the corresponding fields in Chinese. This is fresh visual evidence, not
an automated reverse-page assertion. Evidence:
`work/build/runtime-qa-card-touch-20261004/report.json` and paired `*_back.png`.
The unchanged A-input run showed the front at both checkpoints; retained images
make the QA script correction reviewable.

Standard validation passed 181 tools tests and 25 documentation tests, without
failures, errors or skips:
`work/build/quality/20261004T065543.205106Z/report.json`.


Final validation:
- All nine new scopes passed paired Chinese/English runs: 113,788 frames,
  3,442 heap inspections and no findings. Evidence:
  `work/build/runtime-qa-entry-checkpoints-20261004-native/report.json`.
- Post-run SHA-256 verification confirmed both ROMs and every used source save
  unchanged. `coverage-review.json` alongside that report re-evaluates the raw
  entry evidence with the final reporting fields and records current code/config
  identities; it does not claim to rerun the corrected trainer-card input.
- The separate corrected trainer-card run passed, with visual confirmation of
  the reverse in both languages.
- Negative control `bag_full` still fails on English item IDs 232 (Scope Lens)
  and 288 (Sticky Barb), while Chinese has no rejected copies. These are the
  existing developer-owned defects, not new failures introduced by this stage.
  Evidence: `work/build/runtime-qa-known-defect-20261004/report.json`.
- Final tools/docs gate: 181 + 25 tests pass, no skips/errors/failures:
  `work/build/quality/20261004T070053.364434Z/report.json`.

The initial sandboxed attempt aborted in native emulator startup (SIGABRT),
without usable runtime observations, and correctly reported incomplete. The
successful paired runs used the native emulator outside that sandbox. Retained
failed-startup evidence: `work/build/runtime-qa-entry-checkpoints-20261004/report.json`.
Translation QA was not rerun: no translation or game-data edits were made.


## Stage 11: party-order state assertions (2026-10-04)

QA strengthening continues with a subagent implementing the runtime probe and
scenario assertions, while the coordinator independently validates report
integration. No game or translation fix is part of this stage.

The new probe discovers the save-party pointer through the Chinese hack's
SaveArrayGet(2) return. Guarded code establishes the party header and 236-byte
slot stride; snapshots read only the count and unencrypted personality IDs.
Pointers must be aligned with the full party allocation inside RAM, capacity
must be six, and the observed count must match the fixture's declared count.
Duplicate IDs are ambiguous evidence, not proof of a successful swap. No
Pokemon data is decrypted, modified or written back.

Party and full-party scenarios declare the expected permutation relative to
an earlier checkpoint. The intended checks prove that the first two identities
swap and that the original order is restored, retaining the other four slots
in the full-party fixture. Resource entry and party-state evidence are separate.

Paired reports expose state_status, state_expectations, party_size and paired
state_evidence. New English mismatches fail; shared mismatches are reported as
baseline findings but keep the scripted objective incomplete. Missing or invalid
snapshots are incomplete. Scenarios without such assertions explicitly report
not_configured; this is not counted as verified gameplay-state coverage.

The quality runner independently checks each permutation against the raw paired
snapshots, including identity uniqueness, counts, bounded addresses and increasing
checkpoint frames. A passing label with missing or contradictory raw evidence
cannot pass. Legacy reports without explicit state configuration are incomplete
under the current parser and remain valid historical evidence for older scopes.


The first real paired run exposed a QA-script defect in both scenarios: the
first-two swap succeeded, but the final checkpoint retained the swapped order.
Chinese and English agreed exactly, with no probe gaps. This is a test-input
problem, not evidence of a game bug. The new assertion correctly returned
incomplete and a baseline_shared party_order finding for `end`, instead of the
previous resource-only pass. Original negative evidence is retained at
`work/build/qa-party-state/initial/report.json`.


The QA input correction moves the target cursor LEFT before confirming the second
swap; the cursor remained on the right-hand slot after the first swap. This
changes only the test sequence. The first corrected two-Pokemon paired run
passed. The full-party run additionally checks that the other four identities
remain in their original positions.

Guard details: SaveArrayGet return at 0x0202775C supplies the pointer when its
index register is 2. Signature checks cover the generic getter, the party getter
at 0x0207365C, and count/slot-access code at 0x02073398. The entire six-slot
allocation must fit within 0x02000000–0x02400000; reads use the header at +0/+4
and one identity word per occupied slot at +8 + 236*i. Multiple discovered party
pointers make the evidence ambiguous and incomplete. Local Chinese disassembly
is retained in `work/build/qa-party-state/chinese-layout-disassembly.txt`.

The standard gate passed 192 tool tests and 25 documentation tests, no failures,
errors or skips: `work/build/quality/20261004T084200.642217Z/report.json`.
New negative cases cover unperformed swaps, failed restoration, duplicate IDs,
invalid pointers/counts/frames, missing paired evidence, malformed expectations,
Chinese-only/shared/English-only mismatches and failure precedence. The current
quality runner independently classifies the retained initial report incomplete.


Final paired validation passed both party scenarios in both languages: 24,252
frames, 732 heap inspections, zero findings and state_status passed. The first
two identity words swapped exactly at `switched`, then every identity returned
to its original position at `end`; the remaining four slots stayed unchanged
in the full-party scenario. The coordinator independently rechecked the raw
permutations through quality_runner and verified the checker, manifest, both
ROMs and source saves still match recorded hashes. Evidence:
`work/build/qa-party-state/final/report.json` and `coordinator-review.json`.

The integrated full-bag negative control still fails on the known English
rejected-copy defects (two findings), with memory and resource evidence passing:
`work/build/quality/20261004T084235.246651Z/report.json`. Nothing suppresses or
fixes those developer-owned failures. No game data or source save changed.

Scope remaining: party assertions establish order at the selected checkpoints,
not rendered labels, move order, active summary selection, field exit UI or
persistence after save/reload. Two scenarios now have gameplay-state assertions;
the other fifteen explicitly do not. Battle remains deferred. Translation QA
was not rerun because no translation data changed.


## Stage 12: summary selected-Pokemon assertions (2026-10-04)

The next bounded QA phase uses a subagent for Chinese-hack investigation,
read-only instrumentation and paired validation, with independent coordinator
review of the quality-runner integration. Stored move-order verification remains
a separate phase; this change focuses on selected Pokemon identity.

The summary resolver is byte-signature guarded. Evidence connects its screen
owner, live context, party pointer, slot index and unencrypted identity to the
bounded party snapshot. Expectations name the preceding checkpoint and required
slot, so an old resolver observation cannot satisfy a later transition. Screen
and context frees invalidate captured pointers; readable old memory alone is
not proof of an active selection. No native data is decrypted or modified.

Reports expose summary_status, summary_expectations and paired summary_evidence,
independently of resource coverage, party-order state, text copies and memory
health. The quality runner rechecks raw identity ownership, address bounds,
expected slot and observation timing instead of accepting a passing label.
Missing configuration metadata or malformed evidence is incomplete. Explicit
not_configured indicates the absence of this scope, not a verified selection.
English-only selection mismatches fail; shared mismatches keep the test objective
incomplete and remain distinguishable from translation regressions.


The configured selection sequence is slot 0 at `info`, slot 0 at `skills`,
slot 1 at `skills_switched`, and slot 0 again at `move_swap`, for both ordinary
and full-party summaries. Existing party-order assertions also require the
identities at all four checkpoints and `end` to match their order at `boot`.
This ties a slot to its original Pokemon instead of allowing unexpected party
reordering to change the meaning of the selection assertion.

Native guard evidence: resolver entry/return 0x020899BC/0x020899EA; screen+0x23C
owns the context; party-mode context fields provide the party pointer, mode at
+0x11, count at +0x13 and selected slot at +0x14. Additional guarded code at
0x02089910 establishes the count field. FreeToHeap at 0x0201B33C invalidates
captured screen/context ownership, and a new resolver entry clears the previous
observation. Chinese disassembly is retained locally at
`work/build/qa-summary-state/chinese-layout-disassembly.txt`.

The initial exploratory run included implementation changes between children
and is not acceptance evidence. Final validation uses a frozen checker and
manifest in `work/build/qa-summary-state/final/`.


Final frozen summary validation passed: 31,484 frames, 972 heap inspections,
zero findings across ordinary/full-party Chinese and English runs. Selected
identities follow 0 -> 0 -> 1 -> 0 at the four asserted checkpoints, and party
identities remain in boot order. On exit all four summary context/screen pointers
are invalidated. Independent quality-runner re-evaluation passed and input hashes
matched. Evidence: `work/build/qa-summary-state/final/report.json` and
`coordinator-review.json`. Standard gate: 200 tool tests and 25 documentation
tests pass without errors/failures/skips, recorded at
`work/build/quality/20261004T090004.534371Z/report.json`.

A concurrently run control revealed a fixture-loading anomaly: the English
`party` child showed a shop and a single Pokemon despite the recorded two-Pokemon
route fixture input. Both new count checks and resource entry checks correctly
made it incomplete. The Chinese party child passed, and the full-bag negative
control still failed on the two known English text-copy findings. Retained
control evidence: `work/build/quality/20261004T090009.614626Z/report.json`.
This anomaly is under QA harness investigation; it is not classified as a game
regression or accepted as a passing control.


### Concurrent emulator fixture isolation

The serial retry of the same party control passed with no findings:
`work/build/quality/20261004T090222.387509Z/report.json`. Investigation found a
shared native save at `~/.config/desmume/game.dsv`: each temporary test ROM was
named `game.nds`, while the emulator uses GLib's user configuration directory
for battery saves rather than the process working directory. Distinct temporary
working directories therefore did not isolate simultaneous emulator children.
Native path-loading disassembly establishes use of `g_get_user_config_dir`.
This explains why a concurrently imported shop fixture could replace the route
fixture when a child reset; it is a QA harness defect.

The harness isolation fix gives each fresh emulator child its own temporary
XDG_CONFIG_HOME before native initialization. The prior environment is restored
on exit, and temporary configuration/save artifacts are removed. HOME and
preexisting user configuration/saves are not changed by this isolation mechanism.
The summary state probe and game inputs are unchanged by this harness fix.


Post-isolation validation reran summary and summary_full concurrently with a
separate party_full/bag_full gate. Both summaries and party_full passed; bag_full
still failed exactly on the known English description-copy regressions. Recorded
ROM, source-save, checker and manifest identities still match. Evidence:
- `work/build/quality/20261004T090525.578403Z/report.json` (summary controls).
- `work/build/quality/20261004T090531.175675Z/report.json` (party control and known defect).
- `work/build/qa-summary-state/isolated-acceptance-review.json` (independent parser/hash review).

The final standard gate passed 202 tools tests and 25 documentation tests with
no failures/errors/skips: `work/build/quality/20261004T090519.034395Z/report.json`.
Two additional tests verify temporary configuration separation and restoration/
cleanup after exceptions, including a preexisting XDG_CONFIG_HOME value.
Native diagnostics confirmed constructor, open, fixture import, reset and destroy
use a temporary battery save and do not touch the shared save in the controlled
diagnostic: `work/build/qa-summary-state/native-isolation-diagnostic.json`.
An earlier shared-save mtime change during the wider investigation remained
unattributed; contents were unchanged. It is not used as acceptance evidence.

The isolation wrapper belongs to fresh `_one` workers. Ad hoc Python callers
must likewise isolate configuration before initializing GLib/DeSmuME; a cached
native configuration path cannot safely be switched inside an existing emulator
process. Hard process termination can leave temporary directories, but it cannot
turn their isolated paths into a shared user configuration path.


Final bracketed concurrency check passed simultaneous two- and six-Pokemon
party scenarios on both ROMs, proving exact swap/restoration with their expected
fixture counts. Shared user battery-save SHA-256, size and mtime were identical
immediately before and after these runs; all recorded source fixture/ROM/checker/
manifest hashes also matched. Evidence: quality runs
`20261004T090943.675064Z` and `20261004T090944.298227Z`, with the combined audit
at `work/build/qa-summary-state/concurrency-review.json`.

No ROM, translation bank or source save fixture was edited. Battle remains
deferred. Move-order, rendered-text and touch-summary selection assertions remain
future scopes; `move_swap` currently proves selected identity, not stored move
order. Translation QA was not rerun because translation data did not change.


## Stage 13: stored move-order assertions (2026-10-04)

A subagent implements stored-data acquisition and native-layout guards while the
coordinator independently checks copied data in the quality runner. The phase
proves the first two move IDs swap, the other two stay in place, and other party
members' move lists remain unchanged. It does not infer storage from UI labels
or resource loads, and it does not claim save/reload persistence.

The probe copies each occupied Pokemon's 136-byte boxed record to Python, then
decodes only that copy. Nonzero native flags, invalid ownership, invalid checksum,
unsupported layout or ambiguous/no-op move slots make evidence incomplete.
The Chinese hack's crypto routines, getter and PID-selected block table are
signature guarded. The quality runner independently decodes the recorded copies,
recomputes their checksums, ties identity/address to the bounded party snapshot,
checks capture frames and verifies exact move permutations. Reported decoded
lists must agree with those copies. No emulator memory is written by the probe.

Reports add move_status, move_expectations and paired move_evidence. Explicit
not_configured identifies scenarios without this scope; older reports lacking
these fields do not silently pass the current parser. Valid English-only
mismatches fail; shared mismatches remain incomplete scripted objectives.
Corrupt or otherwise undecodable samples remain incomplete evidence rather than
being misclassified as a demonstrated game regression.

Early paired evidence confirmed the swap but caught an invalid full-party sample
on exit: another party member failed checksum validation in both ROMs. The
strict check retained this gap for investigation rather than suppressing it.


The exit diagnostic sampled ten further frames in both ROMs and found recurring
native crypto activity rather than a one-time settling delay. Some copied buffers
were plaintext (their direct word sum matched the header checksum despite flags
being zero); others were partway through the XOR operation. A fixed extra wait
would merely choose a different phase of that cycle. These samples are not
accepted as stored move evidence and are not called hack corruption bugs.

The bounded assertion is therefore taken at a new `summary_closed` screenshot
checkpoint on the party screen, after closing the summary and before returning
to field processing. It proves that the stored permutation survives summary
closure. The original field-exit `end` checkpoint is retained for existing
party-order and memory checks, with no stored-move claim there. This explicitly
replaces the exploratory field-end move objective; no retries or checksum
exceptions turn an invalid sample into a pass.

Final integrated validation passed 215 tooling tests and 25 documentation tests
(zero failures, errors or skips), recorded in quality run
`20261004T093134.801175Z`. Paired runtime run `20261004T093140.271228Z`
passed both summary scenarios with no findings or incomplete evidence. Ordinary
summary closure was captured at frame 7190 and full-party closure at frame 7728
in both ROMs. Independent decoding confirmed the first two stored moves swapped,
the remaining slots and every other party member's moves stayed unchanged, and
the permutation persisted at closure. Native summary screen/context pointers
were cleared, with resolver frame -1; prior ownership was verified against the
active summary. Existing party and summary identity checks also passed.

Concurrent control run `20261004T093140.533394Z` passed party_full and failed
bag_full with exactly the two known English text-copy rejections (items 232 and
288). These failures remain developer-owned. All recorded checker, manifest,
ROM and source-save hashes matched their final files. The compact independent
review is `work/build/qa-move-order/final-review.json`; native-layout and transient
field-sampling evidence is in `work/build/qa-move-order/native-layout.md`.

This phase changes QA scripts, scenario inputs, tests and these notes only.
No ROM, translation bank or source save was edited. Stored-move proof is bounded
to the summary interaction and its closure: save/reload persistence, arbitrary
field processing and rendered-text assertions remain unproven. Battle remains
deferred. Translation QA was not rerun because translation data did not change.

## Stages 14–15: rendering and reproducibility hardening (2026-10-04)

The coordinator recovered the original five-point strengthening plan from task
`01a0fd1a-c921-72c3-96b7-a5235a21b37b`. Three subagents implemented the remaining
rendering checks, reproducibility proofs and independent gate review. The scope
is QA infrastructure: developers still own game-data and executable fixes.

`runtime_rendering.py` checks a fixed interior bag-description region, excluding
the window border and item icon. It accepts the verified native background and
glyph palette, detects an entirely blank background, and treats unknown layouts
as incomplete. Both languages must show glyph evidence to pass; an English blank
against visible Chinese text fails. A shared blank is incomplete baseline
evidence. No exact Chinese/English image equality or OCR is used.

Four checkpoint assertions are configured: full-bag opening (item 232), key items
(437), scrolling key items (744), and Town Map key items (744). Each requires the
last item-description request to match the item and heap after its baseline
checkpoint. PNG decoding is bounded, requires the expected dimensions and opaque
single-frame content, and rejects missing/corrupt/oversized images or paths
outside ignored work/build. The gate recomputes hashes and pixel metrics, so
deleted or modified screenshots cannot silently preserve a pass. Ordinary bag
opening is deliberately unconfigured: its empty pocket is legitimately blank.
These are presence checks, not proof of wording, clipping or legibility.

`runtime_reproducibility.py` brackets every run with identities for both ROMs,
all selected source saves, the checker, manifest, gate and helper modules. Each
scenario also brackets its source fixture. The gate independently verifies
matching records and binds the scenario fixture to the full-run record. Missing,
unreadable or changed inputs make evidence incomplete rather than a game bug.
File-descriptor metadata detects changes while hashing; nonregular inputs cannot
block on FIFO reads. Hashes cannot detect an edit fully reverted between captures.

Fresh emulator workers record their initially empty isolated configuration path,
PID, loaded native library identity, Python/platform, dependency versions and
known harness settings. Chinese and English workers must have distinct isolated
directories and PIDs but matching native code, versions and settings. macOS
`/var` and `/private/var` aliases are canonicalized while retaining the original
environment value. Other native settings are explicitly recorded as unqueried
library defaults. The host RTC remains uncontrolled; the report makes no claim
of deterministic time, encounters or RNG. No unsupported native APIs are called.

Gate review also rejects malformed report containers and non-object child JSON.
It reconstructs text-rejection signatures from paired raw observations: a stale
passing summary cannot hide an English rejection. Confirmed failures keep
precedence over incomplete provenance; missing proof never produces green.

The exploratory pilot at `work/build/qa-hardening-pilot-20261004/report.json`
confirmed the known English blank and passing key-item crops. It is not final
acceptance evidence: checker/helper edits happened during that run and were
correctly reported by the new hash verification. Its earlier workers also
exposed the macOS path-alias issue described above, corrected before final runs.

### Final acceptance and plan closure

Frozen-code validation passed 256 tooling tests and 25 documentation tests with
zero failures, errors or skips (`20261004T102649.387536Z`). The full static gate
(`20261004T102554.876135Z`) checked 76,862 translated strings: zero errors and the
unchanged 16,023 warnings. Artifact verification still fails the documented
Chain Logger tile-allocation defect; buffer verification still fails all 17
oversized ROM/workspace descriptions. These expected failures are not waived.

All sixteen non-battle scenarios completed on both ROMs: 32 isolated workers,
208,868 frames and 6,340 heap inspections. Fourteen scenarios passed; bag_full
and mart_full failed only on the known item-description defects. No scenario
was incomplete. All sixteen memory checks, scoped temporal objectives, fixture
integrity proofs and paired environment checks passed. Both summary scenarios
retained passing party, selected-Pokemon and stored-move assertions.

The new renderer independently failed the full-bag opening description (232):
the Chinese crop contained 1,057 black and 945 white glyph pixels, while all
10,528 English crop pixels were background. Both subsequent full-bag description
checks and the Town Map key-item check passed. Parent visual review agreed with
the opening-region result. Full-bag runtime retained its two rejected-copy
signatures (232/288); full-bag shop retained its one signature (232). The added
blank-region finding is corroboration of F001, not a new defect.

Final paired reports:
- `work/build/quality/20261004T102645.789446Z/runtime.json`: summary, summary_full,
  party, party_full, bag, bag_full, bag_townmap and mart_full.
- `work/build/quality/20261004T102648.216001Z/runtime.json`: pokedex, trainer_card,
  pokegear, options, save_prompt, photo, mart and summary_touch.
- `work/build/qa-hardening-final/review.json`: independent gate re-evaluation,
  per-scenario scope/results, totals, and post-run current-input hash verification.

Every recorded source input still matched after validation. No ROM, translation
bank, graphics asset, executable patch or source save was changed by this phase.

| Original hardening objective | Completion evidence |
| --- | --- |
| Expand non-battle runtime coverage | Sixteen explicit scoped temporal objectives; fresh paired runs above |
| Verify actual Pokemon, party and move state | Guarded identity, swap/restoration, move permutation and summary-closure assertions |
| Detect rejected text copies | Runtime detector plus independent raw-signature gate; known defects remain failing |
| Inspect selected text regions for blank output | Four context-bound description checkpoints with recomputed PNG proof |
| Verify fixtures and record emulator configuration | Full-run/per-scenario hash brackets and comparable isolated-worker records |

This closes the original five-point hardening plan. It does not certify every
interaction: complete rendering fidelity, touch-selection/page state across all
screens, save/reload persistence and deterministic clock/RNG remain additional
scopes. Battle remains deferred by the user; its existing incomplete coverage
has not been promoted to passing or repaired. Developer fixes and validation of
a rebuilt candidate remain separate from QA infrastructure completion. The
developer acceptance command is recorded in `work/notes/tooling_findings.md`.


## Static text boundary gate (2026-10-04)

The next QA priority adds three checks for existing artifacts: an independent
binary message parser, exact source/workspace/export/candidate inventories, and
a logical ROM change-boundary comparison against the untouched Chinese hack.
Run all three with:

```sh
.venv/bin/python work/tools/quality_runner.py --checks text_static
```

The boundary derives permitted changes from the existing graphics, font and
hardcoded patch declarations, never from the candidate build report. All other
logical files, executables and header attributes must match. Message archive
metadata is protected separately from translated member payloads. The boundary
uses existing patch helpers to reconstruct expected components in memory; it is
not an independent proof that those approved patches preserve game semantics,
nor a byte-level certification of physical ROM packing gaps.

Inventory checks reject missing/extra banks, reordered or duplicate string IDs,
changed Chinese workspace sources, and candidate bytes that differ from a fresh
export. Opaque entries must remain byte-identical and retain an explicit
incomplete classification. The binary parser does not import the production
message codec; it checks bounded records, command argument storage, terminators
and compressed streams. A structural pass does not prove command-specific
semantics, consumer buffer capacity, layout or translation fidelity. Existing
buffer, artifact, translation QA and runtime checks remain necessary.

The gate records input hashes before and after checking, including failed runs.
It never saves or rebuilds a ROM and does not correct translations or gameplay.

Final validation: `work/build/quality/20261004T110944.476591Z/report.json`.
All 327 tooling tests and 25 documentation tests pass with no skips. Independent
binary validation passes for 821 banks / 76,862 records in each ROM. Inventory
counts and fresh-export equality match; two preserved opaque strings
(`a027/0763#66` and `#80`) keep that check incomplete. Boundary verification
compares 549 nonmessage files, both message archive envelopes and 41 ROM
attributes; it fails only the existing `data/linkcapture.narc` mismatch (known
Chain Logger graphics). All eight input groups have unchanged before/after
fingerprints, including ROMs and translation banks. Overall status correctly
remains failed; no defect was repaired or waived.

An earlier run detected a concurrent change to `work/tools/docs/gen_docs.py`
and rejected input stability. The final run above used stable inputs and
supersedes that run; no unrelated generator changes were reverted.


## Complete text accounting and consumer contracts (2026-10-04)

The `text_static` gate now also emits `static-text/text-safety-ledger.json`, with
one record for every source/candidate/fresh-export message ID. Each candidate
and workspace record reports source-relative controls, stored/decompressed
length, a proven expansion bound or explicit gap, and every applicable known
consumer contract. Every record retains `consumer_discovery_incomplete`: a
passing known consumer does not establish safety in all consumers. Four known
hardcoded labels are checked separately, including actual ROM pointer targets
and current workspace lengths. Baked-in graphic text remains in the existing
graphics artifact/layout checks, explicitly outside message-buffer proof.

`text_consumer_check.py` adds guarded trainer-name and Frontier-name eight-unit
copy checks to the four existing item-description consumers. Character policies,
default player/rival names, unformatted trainer-name exceptions and hardcoded
labels are also checked, but remain policy-only where native code is not guarded.
Policy limits are never presented as verified native destination capacities.
Source-only capacity findings are retained separately from introduced violations.

`text_control_check.py` preserves substitution command IDs, arguments and
multiplicity. English may reorder substitutions while preserving effective
formatting state and other stateful barriers. COLOR/SIZE restoration is handled
without mistaking a restored state for a changed argument. Unknown native
command arities remain incomplete; example argc values from source messages are
not treated as proof of handler requirements. Explicit contracts can check
handler arities and referenced inventories once independently evidenced.

`text_expansion_check.py` measures literals/compressed messages exactly and
requires explicit evidence for variable expansion. Native formatter guards
establish the identity of the engine, not per-message bounds: its substitution
commands index runtime slots; the apparent placeholder kind does not choose a
name bank. The default constructor uses eight slots of 32 units, but custom
constructors exist, and packed trainer names expand during concatenation.
No global 32-unit or name-kind bound is therefore applied. Consumer/slot-producer
mapping remains necessary before any dynamic message receives a safe maximum.

`text_reference_check.py` compares the full script archive, map/std-script bank
mappings and ordered message counts. This establishes reference preservation;
it does not prove all original or dynamic references valid. Unresolved dynamic
targets and menu behavior remain explicit gaps. A failed message decode blocks
reference conclusions instead of shifting bank indices.

The control review flags 50 deliberately blanked strings in banks 0034, 0035,
0041 and 0267, plus the documented SIZE reset in 0616#37. Existing notes cite
unused US leftovers for the blanks; Chinese-hack unreachability has not been
proven here. These are source-contract review findings, not 51 newly confirmed
game bugs. No QA-ignore or blanket exception waives them. Triage is recorded in
`work/build/qa-static-text/controls/triage.json`. No translation, game code,
graphics asset or ROM was changed by this work.

Validation: `work/build/quality/20261004T114243.952915Z/report.json` records
380 tooling tests and 25 documentation tests passing, with no skips. The final
static run has stable before/after fingerprints for all nine input groups.
Both ROMs retain passing binary grammar across 821 banks / 76,862 records each.
Every candidate and fresh-export string is represented in the safety ledger.
There are 21 scoped consumer contracts and 9,433 individual consumer/string
checks per ROM; 5,712 message IDs have at least one capacity or character-policy
contract, including 2,130 with a ROM-guarded consumer. This does not establish
complete consumer coverage even for those IDs. Exact literal expansion bounds
are available for 61,965 strings; all unresolved command expansion remains
incomplete. Four hardcoded labels are included separately.

The gate retains the 17 known description overflows and 51 control-contract
review findings on both candidate and workspace. Script/reference preservation
passes for all 966 script members, 540 map mappings and 30 standard mappings,
while dynamic resolution remains incomplete. The existing Chain Logger graphic
mismatch still fails boundary validation. Fresh workspace export now differs
from the current ROM in 28 banks; both versions were checked, with no ROM build
or attempt to reconcile another task's translation changes. The final report
therefore correctly remains failed, and does not certify all text safe.
