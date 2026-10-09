# Native message loading verification

**Status (2026-10-09): historical.** The rc5 quality tools this note describes (native_load_check, native_load_validation, opaque_control_proof, quality_runner) were removed in the 2026-10-09 cleanup; the release gate is `check.py --full --strict-release` plus `--emu`. The findings below stay as the record; `git log --diff-filter=D -- work/tools` finds the scripts.

`work/tools/native_load_check.py` exercises the candidate ROM's actual ARM9
message routines in DeSmuME. It never changes the ROM, bank text or game code.
Run from the repository root with the existing local Python environment:

```sh
.venv/bin/python work/tools/native_load_check.py \
  --rom work/build/approved-review-20261004/candidate/origin_hg_v4.0.3_en_wip.nds \
  --out work/build/native-load-verification/final-verified
.venv/bin/python work/tools/native_load_validation.py \
  work/build/native-load-verification/final-verified/report.json
.venv/bin/python -m unittest discover -s work/tools -p 'test_native_load*.py'
```

The emulator may need permission to initialize outside the filesystem sandbox.
The trainer save provides initialized filesystem and heap services. A guarded
native constructor boundary supplies a valid Thumb caller stack and heap ID.
The harness changes CPU arguments and the return address to schedule normal
native calls; it does not replace implementations. Each native return must
restore the caller's stack. The suspended scene is never resumed: this is an
isolated API test, not a gameplay or rendering test.

Both message archives use the native archive path table: a/0/2/7 is ID 27 and
battle/string/battle_string.narc is ID 277. Native resolver return hooks verify
the actual paths. Bank inventories and independent decrypted unit expectations
come from the candidate itself, including empty strings and opaque text.
A deliberately limited `--limit` run is always incomplete, never a full pass.

For each bank the test requests a type 0 handle and verifies that the installed
lazy-loading fix returns type 1. Every entry passes through allocating loader
`0200BB40`; the returned units are compared by length and SHA256. The test then
calls the native String destructor. After destroying the bank handle, the heap's
used-block addresses/sizes and largest free block must exactly match the before
snapshot. Live heap list integrity, allocation failures and null writes are
also checked.

The loader returns compressed trainer-name strings still packed. These are
separately passed through native decompressor `0202703C` into a String allocated
by `02026864`, sized from the independent decoded oracle plus one terminator. The
expanded result must match the oracle, and both Strings are freed. This proves
the decompressor's output with an adequate destination; it does **not** prove
that every existing caller allocates an adequate destination. The decompressor's
compressed branch itself has no capacity guard, making consumer-capacity proofs
especially important.

Twenty stress rounds hold four handles concurrently, including the largest
text, a compressed-name bank and the battle archive. They alternate repeated
reads, then release handles in reverse order. Requested constructor modes
alternate between 0 and 1. Every round must restore the heap allocation snapshot.
This tests one initialized field heap; it is not exhaustive evidence for all
possible gameplay allocation orders, memory pressure, UI buffers or lifetimes.

Reports record exact entry coverage, stored and expanded hashes, per-bank and
stress cleanup snapshots, native completion evidence, and source/script/save
identities. Native code ranges covering the constructor, loader dispatch,
String operations, decompressor and archive resolver are SHA256 guarded.
A changed binary fails closed and requires review; never regenerate guards
merely to make a different binary pass. Unit tests ensure a same-length wrong
output and missing/duplicate/failed inventory entries cannot be accepted.

Two preserved Chinese records (`a027/0763#66` and `#80`) have an FFFF value
inside the second argument of command 0129. The native String length is 4, but
that does **not** mean the remaining payload was lost: `02026EE4` copies all six
stored units before the length scan. The real terminator at index 5 survives.
The guarded formatter substitutes slot 0, ignores argument 1, and advances by
the declared two arguments to that real terminator. The exact six-unit payload
must also match the untouched Chinese ROM.

`opaque_control_proof.py` guards that complete dataflow. Every full native sweep
now loads both entries and formats each with controlled slot lengths 0, 7 and
31. All six cases must preserve the full copied payload, produce exactly the
slot contents and a terminator, and restore the heap allocation snapshot.
The independent validator reopens both ROMs, checks the proof fingerprints and
requires the exact six-case evidence. Missing cases, altered payloads, changed
argument skipping/copy/formatter code, wrong output or unbalanced cleanup fail.
This closes the particular embedded-FFFF interpretation gap; it does not prove
original callers populate that slot correctly, have adequate destinations, or
render every scene. Raw length/grammar differences remain recorded in each row.

On the reviewed 2026-10-04 candidate, the exhaustive run covers 76,862 entries in
821 banks, including 1,019 compressed entries. Twenty concurrent-handle stress
rounds exercise four banks and 240 additional loads. Native API checks pass;
the report status is `passed_with_semantic_gaps` for the two source-preserved
records above. This status must not be promoted to universal rendering safety.
The local evidence is `work/build/native-load-verification/final-verified/report.json`.

## Verified candidate result (2026-10-04)

The final native run covers 76,862 entries in 821 banks, including all 1,019
compressed entries and both opaque records. It completed 159,063 native calls,
1,682 heap walks and 20 concurrent-bank stress rounds in 63.22 seconds after
boot. Every cleanup snapshot matched, with no allocation failures, null writes
or detected heap corruption. ROM, Chinese reference, save and tool hashes stayed
unchanged. The independent validator reopens the ROM using the separate msgtool
parser/decrypter and checks every returned output hash, exact inventory, cleanup
snapshots and provenance. Both report `passed_with_semantic_gaps`, retaining the
two source-identical opaque controls described above.

The existing quality runner also exposes the sweep as an explicit check:

```sh
.venv/bin/python work/tools/quality_runner.py --checks native_loading \
  --rom work/build/approved-review-20261004/candidate/origin_hg_v4.0.3_en_wip.nds \
  --output work/build/native-load-quality-new
```

This runs the native sweep and independent validator together. The earlier two
semantic gaps made that historical quality gate `incomplete` (exit 1). Current
runs include the narrow formatter proof described above and can pass that gate.
Any other unresolved semantic gap remains incomplete. A missing report, failed
native process, wrong output, missing entry or changed input fails the gate. The check is opt-in
because it requires the local emulator and save; default unit/QA checks stay fast.

## Follow-up after approved warning corrections

The new candidate's guarded formatter evidence is recorded under
`work/build/approved-warning-followup/investigations/native-final/`.
Earlier reports above retain their original `passed_with_semantic_gaps` status;
they were produced before this additional proof and are not silently rewritten.
Current full sweeps can report `pass` for the bounded native loading/formatter
scope when both preserved controls satisfy the narrow proof and all other
loading checks pass. This still does not constitute exhaustive gameplay render
coverage. Mutation tests are in `test_opaque_control_proof.py`.

The final follow-up sweep and independent validator both passed: 76,862 entries,
821 banks, 159,079 native calls, 1,690 heap walks, 20 stress rounds and six
formatter cases. The sweep took 67.17 seconds after boot. No semantic gaps remain
within this bounded loading and controlled-formatting scope.
