# Repeatable local native verification

Run from the repository/worktree root. This is an optional local gate requiring
existing ROMs, a six-party seed, the melonDS shim, Node, and the project's Python
venv. It never downloads inputs, builds a ROM, or repairs a native record. Compile
the shared core/editor explicitly first:

```sh
npm --prefix work/save-editor run build
python3 work/research/save_core/verify_native.py --inputs work/build/native-verification-inputs.json --run-id review-001 --plan
python3 work/research/save_core/verify_native.py --inputs work/build/native-verification-inputs.json --run-id review-001
```

Create the local manifest under ignored `work/build/`. Each binary input must
supply its expected SHA-256 explicitly; a mismatch stops preflight before any
emulator or fixture work. `repo` supplies the existing `.venv/bin/python` and the
independent verification readers. Example for the locally audited inputs:

```json
{
  "repo": "/Users/simonvergauwen/Developer/poke",
  "inputs": {
    "cn": {
      "path": "/Users/simonvergauwen/Developer/poke/work/rom/origin_v4.0.3_cn.nds",
      "sha256": "4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8"
    },
    "en": {
      "path": "/Users/simonvergauwen/Developer/poke/work/build/origin_hg_v4.0.3_en_wip.nds",
      "sha256": "6fa7b4e739391ca9ea9bfcf90d83eec6407c3c04102e52432bb41bc8ae44a7d3"
    },
    "seed": {
      "path": "/Users/simonvergauwen/Developer/poke/work/build/memcheck/full_bag_6mons.sav",
      "sha256": "b3aca10747cd0f1adc3d5852a50dddaaa36ed8680f5ba04012cfe3110faad90f"
    },
    "shim": {
      "path": "/Users/simonvergauwen/Developer/poke/work/build/melonds/libmelonds_shim.dylib",
      "sha256": "866802df3e266a5ecb28c6fa0667176aaee0837ae36cdda2b737aa25dfe147db"
    }
  }
}
```

The command runs twelve stages, sequentially:

1. Verify the Python/Node build-identity handshake before emulation.
2. For each language, boot all fourteen independent save-loader recovery cases
   and compare their observed mirror selection with the shared core.
3. For each language, test the original six-member harness scenario: battery
   edits, variables, inventory, live partial move/HP edits, inactive-slot refusal,
   and strict rejection of the scenario's malformed generated record.
4. For each language, test a party shrunk from six to three through a shared
   transaction: native count and last-active-slot edits, refusal of the fourth
   inactive slot, byte preservation, and successful native generation checked by
   independent move and party-stat readers. Shrinking does not clear old slots.
5. Build the combined six-member editor fixture and verify native load, trait
   getters, moves, stats, all pockets, in-game save and reset/reload on both ROMs.

The combined fixture covers level/nature/EXP, moves/PP/PP Ups, IVs/EVs, shiny
state, Pokérus, money and inventory. This gate does not add arbitrary form edits
or claim that every party/form/inventory combination is playable. The independent
readers are not replaced by the production writer.

Every run requires a fresh ID. Logs, screenshots, saves and detailed native
reports remain ignored under `work/build/save-core-native-<id>/` and
`work/save-editor/local/shared-core-native-<id>/`. Existing output directories,
including dangling symlinks, are refused. Input identities are checked before
and after each executed stage. Reports are updated atomically after each stage.

Each stage has a bounded wall-clock timeout (`--timeout`, default 600 seconds).
A timeout kills its whole subprocess group, including native worker children.
A failed dependency causes an explicit skipped stage; unrelated checks continue.
`--only loader`, `--only harness` or `--only persistence` allows targeted diagnosis,
but omitted checks stay **skipped** and the overall result is **incomplete**.
Exit codes are 0 for a complete native pass (or `--plan`), 1 for failure, and 2
for incomplete selected coverage. This is a POSIX local runner.

A successful report is scoped to the named native scenarios. The separate
bundled-reference provenance gate is always reported as skipped here, with both
ROM hashes and their match status. The available English WIP hash differs from
the reference bundle's `caf987949ea7e208f8cae1c49c76b1cf3fd596338cafeb7270693116bb448b3b`.
Nothing silently regenerates the bundle or treats a native scenario pass as
whole-ROM provenance verification.

Portable runner tests require no game data or emulator:

```sh
python3 -m unittest discover -s work/research/save_core -p test_verify_native.py
```

The tests cover input pinning, malformed manifests, output isolation, full/partial
plans, stale-core preflight failure, dependent skips, incomplete report rejection,
input changes during a run, log capture and process-tree timeout cleanup.

## Generator investigation scope

The six-member scenario's checksum-invalid generator output predates this
migration and reproduces with the original harness and untouched Chinese seed.
The new three-member scenario produces a valid record on both ROMs. This is a
scenario-dependent generator-path issue; it is not proof of a universal native
creation failure or an identified hack bug. The six-member harness explicitly
lowers the count to five before invoking the debug menu, whereas the three-member
case already has room. Their other record/RNG/game-state differences also matter.

A controlled Chinese-seed probe lowered the count to five and initialized the
sixth slot with the shared native-`ZeroMonData`-shaped empty record before invoking
the generator. The resulting record was still invalid. Simple stale target bytes
therefore do not explain this reproduction. No production fix or automatic
repair is justified by this evidence.

`generator_probe.py --trace-party-writes` records native bus writes to the target
record. `--clear-target-slot` is an explicit disposable diagnostic modification,
not a game or harness behavior change. The initial whole-record write trace
captured 4,096 events and dropped 54,331; it is incomplete and does not establish
the instruction that caused the inconsistency. Traces remain private ignored
artifacts. Narrower traces or a controlled party-count/record matrix would be
needed to identify the cause.

## Audited run, 2026-10-09

`strengthened-final-20261009` completed all twelve native stages with no failures
or skipped native groups. All four pinned binary inputs remained unchanged.
The twenty-eight native loader cases, both six-member rejection scenarios, both
three-member successful-generation scenarios, and CN/EN in-game save/reset
persistence passed. The bundled-reference provenance gate remains explicitly
skipped for the hash mismatch described above. Twenty-two portable runner tests
pass without native dependencies.

The earlier `strengthened-20261009` exploratory run retained an incorrect
expectation that the new three-member scenario would also produce invalid
native output. Both languages instead produced valid output, so those two stages
failed correctly. Its artifacts are preserved; the final run tests the observed
six- and three-member scenarios separately rather than suppressing that failure.
