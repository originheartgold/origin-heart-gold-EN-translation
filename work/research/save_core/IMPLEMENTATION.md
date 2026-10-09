# Shared save core implementation

Implemented on `research/save-core-unification`, based on `e084341`, in
`/private/tmp/poke-save-core-research`. All implementation changes are confined
to this worktree; unrelated work in the main checkout is left alone.

## Result

The browser editor and harness previously had separate binary implementations.
They now use one TypeScript implementation in `work/save-core`: save selection,
CRC, Pokémon encryption and fields, stats, containers, inventory, and bounded
fixture transactions. Browser compatibility exports keep existing imports stable.
The Python harness calls the same compiled modules through a persistent Node
worker; Python retains emulator control and native debug-menu generation.

Three subagents owned the core, Python migration, and independent review/tests.
Integration review resolved native-loader corner cases, buffer ownership,
nested inspection aliases, process lifecycle, and malformed native generation.
See [the core contract](../../save-core/README.md) and
[native evidence](native_evidence.md) for details.

## Follow-up hardening

Five further subagents implemented one requested step each:

1. **Common transaction engine:** browser and harness policies now share
   `transaction.ts`. Browser edits use `applyEditorTransaction`; compatibility
   helpers delegate to it. The public raw-offset writer was removed. Transactions
   preserve indexed/contextual errors and validate staged state across operations.
2. **Build identity:** explicit builds seal source/configuration/worker/compiler
   lockfile and compiled-output hashes. The worker verifies them before and after
   importing modules, preventing a concurrent rebuild from substituting a
   different implementation during startup. Python requires a matching bounded
   handshake before sending save data. Existing workers remain on their verified
   version until restarted; freshness is a startup guarantee.
3. **Sequence and mutation tests:** deterministic mixed transactions compare
   complete output against independent byte/cipher/CRC oracles, including failure,
   rollback, retry and party shrinking. Eight isolated semantic mutants must
   compile and fail the intended assertion; syntax errors and infrastructure
   failures cannot count as caught faults.
4. **Repeatable native verification:** a local runner validates explicit hashes,
   checks the compiled core, executes CN/EN probes with bounded process trees,
   preserves partial reports, and distinguishes failures and omitted checks.
   Harness smoke coverage now includes three-member parties and the last active
   versus first inactive slot; persistence still covers a six-member party.
5. **Continuous checks:** portable Python suites and native-runner orchestration
   tests are integrated with explicit optional-test classification. Architecture
   checks guard the Python delegation and editor compatibility boundaries.
   Patch CI builds the core before test discovery; staged checks reuse a build
   only when its fingerprint matches the exported Git index.

These checks detect accidental regressions; they do not prove every possible
game state is valid or defend against deliberate rewriting of code and evidence.

## Safety and compatibility

- Mutation requires structurally valid saves and closed, checksum-valid Pokémon.
  Diagnostic RAM inspection is separate from writing.
- Transactions validate and edit a private copy, repair checksums once, and return
  hashes and changed ranges. Failure exposes no partial result. Exact no-ops
  preserve bytes; unrelated regions and the other mirror remain unchanged.
- General/storage validity and counters follow the observed native loader,
  including ties and rollover. Unsafe native zero-counter recovery states are
  rejected rather than silently selecting a different generation.
- Saved flags, variables, party slots/counts, locations and pockets have explicit
  bounds. Growing a party count cannot activate invalid unused slots.
- Harness partial moves preserve unused slots and PP Ups. Deliberately stale
  cached stats require an explicit fixture tail policy. Normal editor stat edits
  continue to recalculate dependent fields.
- Source and returned buffers never alias. Python inspection results are deep
  copies. Save publication is atomic and refuses existing files and seed aliases.
- The Node protocol bounds bytes/messages, validates IDs/version/base64, applies
  deadlines, serializes concurrent calls and handles forks. Failed requests are
  never replayed. Workers are reaped and restarted on the next request.
- Build the core explicitly with `npm --prefix work/save-editor run build`.
  The harness now requires Node.js and compiled modules; it never installs or
  builds dependencies automatically. Site and editor build paths include the core.

Independent verification readers remain independent of the production writer.
No blank playable-save constructor was added: fixtures derive from existing seeds.

## Initial validation, 2026-10-09

All commands run from the worktree root, using existing local dependencies.

| Gate | Result |
|---|---|
| `npm --prefix work/save-editor run check` | Typecheck/lint pass; 354 tests: 353 pass, one optional ROM provenance test skipped |
| Python bridge/harness/fixes/reflection/texture suites in the project venv | 151 tests: 147 pass, four local ROM/tool-dependent tests skipped |
| CI bridge suite with system Python, no third-party Python packages | 42 pass |
| `npm --prefix site run build` | 4,636 pages built |
| `GUIDE_TEST_DIST=1 npm --prefix site test` | 66 pass |
| `node work/save-editor/scripts/verify-site.mjs site/dist /` | Pass; editor assets local, no private game inputs |
| Standalone server module graph and private-path isolation | Pass, included in editor tests |
| Native save-loader parity | 14 cases on each of CN and EN, all 28 match |
| Combined editor/fixture native EN validation | Load, native getters, in-game save and reset/reload pass with no gaps |
| Migrated harness native CN and EN smoke tests | Both pass: battery edits, live partial moves/HP, independent decoding, inactive-slot rejection, and safe rejection of malformed native generation |

Core coverage includes all 32 shuffle selectors, boxed/party records, 512 seeded
randomized edits checked by independent plaintext/BigInt oracles, all pocket
boundaries, rollback, malformed protocol traffic, and 128 independently modeled
native validity/counter combinations. Browser tests exercise the actual app and
preserve existing sessions/drafts on failures. Python tests cover timeout,
crash/restart, concurrency, fork ownership, process reaping, atomic publication,
generator rejection and nested inspection mutation.

The combined native fixture changes level/nature/EXP, moves/PP/PP Ups, IVs/EVs,
shiny state, Pokérus, money and inventory. Its output SHA-256 is
`70d03d3a866e54dea2d3d6789abadf004e119ca760d3abfaca2a1d6b962c3383`;
144 allowed bytes change, matching the earlier independently audited fixture.

Reproduction scripts are `native_loader_probe.py`, `native_parity.py`,
`runtime_fixture.mjs`, `harness_runtime.py` and `generator_probe.py` in this
directory. Binary fixtures, screenshots and detailed reports stay ignored under
`work/build/save-core-*` and `work/save-editor/local/shared-core-*`.
The follow-up [native verification guide](NATIVE_VERIFICATION.md) documents the
single `verify_native.py` entry point, required hash manifest and result scope.

Native inputs:

| Input | SHA-256 |
|---|---|
| Untouched Chinese v4.0.3 | `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8` |
| Existing English WIP | `6fa7b4e739391ca9ea9bfcf90d83eec6407c3c04102e52432bb41bc8ae44a7d3` |
| Existing six-party seed | `b3aca10747cd0f1adc3d5852a50dddaaa36ed8680f5ba04012cfe3110faad90f` |

Input hashes remain unchanged. No ROM was built, downloaded or committed.

## Follow-up validation, 2026-10-09

| Gate | Result |
|---|---|
| Editor/core typecheck, lint and tests | 399 tests: 398 pass, one optional ROM-provenance test skipped |
| Semantic mutation gate | All eight mutants compile and are caught by their intended assertions |
| Portable Python runner, with images | 193 pass, zero unexpected skips; includes 22 native-runner orchestration tests; four named ROM/armips checks explicitly excluded |
| Repository `check.py --fast` | Registry, generated fix docs, lint and unit checks pass; 1,082 tests with 100 optional skips; synthetic assembly skipped because armips is unavailable |
| Site build and compiled-site tests | 4,636 pages built; all 66 tests pass |
| Standalone/static site integration | Shared transaction module reachable; private paths blocked; static verifier passes |
| Repeatable CN/EN native suite | All 12 stages pass, zero failed or omitted native stages: 28 recovery cases, four harness scenarios, combined fixture, both save/reset/reload runs and core preflight |

The repository-wide lint pass required removal of one pre-existing unused
`unicodedata` import in `work/tools/site/reconcile_references.py`, as well as
obsolete imports left behind by the codec migration. No behavior was changed.

The pre-review native replay's startup handshake matched its sealed core
build `38cde560ae6c63adcfce9e4eb33e98f247ee8de2b9d3d56add3a621d51f14823`.
Its ignored report is
`work/build/save-core-native-strengthened-final-20261009/report.json`; all four
pinned binary inputs remain unchanged. The independent bundled-reference gate
is explicitly reported as skipped and is outside those twelve native stages.

An earlier exploratory replay expected invalid generation in the new
three-member scenario and failed precisely because generation succeeded. That
report is preserved under `work/build/save-core-native-strengthened-20261009/`.
The final runner separates successful free-slot generation from strict rejection
in the six-member scenario; it does not suppress or reinterpret the earlier
failure. Clearing the sixth slot was separately investigated without a production
behavior change.

## Review fixes, 2026-10-09

All nine review items are addressed:

- Live diagnostic flag reads again accept `0..0x3FFF`, including 7286 and 4461;
  save-file operations and live writes retain their strict saved-array bounds.
- Every editor transaction and compatibility writer refuses equal-counter mirrors,
  including empty/no-op edits. Inspection and explicit fixture transactions retain
  the native first-mirror tie selection established by the earlier loader probes.
- Battle diagnostics expose the effective 16-bit `ability` and a distinct
  `vanilla_ability_byte`; the existing `ability_bytes` report keeps its old meaning.
- Invalid personal/stat candidates return `match: false` with a reason. Unexpected
  core errors and worker failures still propagate; strict stat APIs remain strict.
- Save transactions include their resulting inspection in one worker reply.
  `start_at` and `cmd_wild` batch scenario operations while preserving callback order.
- RAM scans reject bad checksums locally before shared-core decoding. Complete
  active records at the scan boundary are supported, including opened RAM records.
- Partial pipe writes share one memoryview rather than copying the unsent suffix.
- Typechecking uses `tsc --noEmit` and an isolated source tree, preserving the live
  core build even when it is absent or stale; current source signatures are checked.
- Core save offsets and record strides are defined once in `layout.ts`; independent
  test oracles retain literal layouts to detect mistakes in production constants.

New deterministic regression tests verify one worker round trip per edit, one
transaction for 1,003 setup operations, zero worker decodes for checksum-invalid
candidates, partial-write buffer ownership, diagnostic failures, and tied-mirror
refusals. A scan containing 1,500 invalid parties and one valid party makes one
worker decode; a PID scan with 1,000 invalid and four valid records makes four.

| Gate | Result |
|---|---|
| Editor/core typecheck, lint and tests | 404 tests: 403 pass, one optional ROM-provenance skip |
| Semantic mutation gate | All eight compiled mutants caught |
| Portable Python runner with images | 217 pass; four named ROM/armips checks explicitly excluded |
| Repository `check.py --fast` | Pass; 1,106 tests, 100 optional skips; armips assembly unavailable |
| Site build, compiled-site tests and static verifier | 4,636 pages; 66 tests pass; packaging/private-input checks pass |
| Targeted native CN and EN smoke tests | Both pass, including flags 7286/4461, party/PID scans, battery/live edits, and valid fourth-member generation |

The targeted native checks use sealed core build
`798c33148769ed0629c2baaf259eaed303452fd6eb59e5f94cb75624e4b67bbd`.
Reports remain ignored at `work/build/save-core-review-cn-20261009/report.json`
and `work/build/save-core-review-en-20261009/report.json`. Both verify unchanged
ROM/seed hashes. The full twelve-stage loader/save/reload matrix above is historical
validation of the preceding build; this review reran the targeted smoke scenarios,
not that entire matrix. Existing provenance and native-generator limitations below
remain unchanged.

## Remaining limits

The native debug-generator path can produce a checksum-invalid record with
plaintext boxed data but closed flags when adding into the sixth party slot.
This reproduces in the original harness on the untouched Chinese ROM and
untouched seed, without fixture edits, and persists through 120 frames. Clearing
the destination with the shared empty-slot initializer does not fix it. By
contrast, the new three-member-party scenario successfully generates a valid
fourth member. The exact cause remains open: evidence does not establish a
universal generator failure or justify a ROM change. The harness rejects invalid
output and never attempts to repair native records.

The available English ROM does not match the bundled reference metadata's whole-ROM
hash (`caf987949ea7e208f8cae1c49c76b1cf3fd596338cafeb7270693116bb448b3b`).
The optional provenance gate therefore remains skipped in the normal suite.
Diagnostic comparison finds matching moves/species, all 262,400 personal/form
pairs and item pockets, but one item label and readiness count differ. The bundle
was not regenerated against an arbitrary WIP build. See `reference-results.json`.

Native testing covers named scenarios, not every game state. Transaction reports
correctly retain `nativeLoadVerified: false`; codec validation alone does not
prove playability. The historical `probe.py`/`probe.mjs` characterize the old
baseline and are not regression tests for the new implementation.
