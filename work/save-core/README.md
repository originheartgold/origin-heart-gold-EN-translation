# Origin save core

The browser editor and Python emulator harness use these same TypeScript codecs
and writers. The six old editor modules are compatibility exports. Core modules
have no Node, filesystem, DOM, emulator or reference-data bundle dependency.

From the repository root, `npm --prefix work/save-editor run build` compiles the
core first, then the editor. Use the project's installed dependencies; the Python
adapter never installs tools or builds modules automatically.

Each build seals a deterministic SHA-256 manifest covering all core sources,
worker/build scripts, configuration, the pinned compiler lockfile, and emitted
files. The worker checks it before importing compiled code; the Python adapter
then checks a bounded `handshake` response containing `{schema, protocol, buildId}`.
Missing, edited, added, or deleted inputs/outputs require an explicit rebuild.
Builds also reject source changes during compilation. Fingerprints detect stale
or accidentally modified builds, not malicious changes by someone who can rewrite
both files and the manifest. Verification runs at worker startup: an existing
worker retains its verified implementation until closed/restarted.

## Boundaries

- `save.ts` validates both general and storage copies and selects a valid,
  same-mirror, equal-counter generation. The native comparator handles the exact
  FFFFFFFF-to-zero rollover and selects mirror zero on ties. Damaged or mismatched
  generations cannot be made writable merely by fixing their CRC. Storage and
  the other mirror remain unchanged. If native ranking would select an invalid
  storage block through its artificial zero counter, the entire edit is rejected
  even when a later-ranked mirror is coherent. Selecting that later mirror would
  differ from what the game actually loads.
- `pokemon.ts` rejects checksum failures and all nonzero header flags before any
  write, even a no-op. Boxed replacement preserves PID because the existing tail
  is encrypted with it. `decodePokemon` retains the browser's original shape;
  `decodePokemonDetails` exposes harness fields. `decodePokemonDiagnostic` can
  inspect open or corrupt RAM snapshots but cannot be passed to a permissive writer.
- `transaction.ts` owns the common mutation engine. `applyEditorTransaction`
  accepts record replacement, money, and reference-validated pocket changes;
  `applyFixtureTransaction` accepts the explicitly bounded scenario operations.
  Both copy source bytes, apply the whole list privately, update the selected CRC
  once, and return no partial result on failure. There is no public raw-offset
  patch API. Validation covers the selected save structure and touched fields;
  it does not certify every game object in the save.
- `inventory.ts` and `save.ts` retain compatibility helpers that delegate to the
  common engine. Standard pocket edits enforce quantities, native ordering, and
  registered-shortcut cleanup using injected reference metadata.
- `fixture.ts` inspects seed saves and re-exports the fixture transaction API.
  It never constructs a blank playable save. Fixture pockets intentionally allow
  arbitrary positive u16 items/quantities and preserve caller ordering for native
  test scenarios. Pokémon fixture edits require `tailPolicy: 'preserve'` to make
  intentionally stale cached stats explicit. Normal browser stat edits recalculate;
  raw record replacement reports its tail as caller-supplied, not independently
  verified to have been recalculated.

Unknown and unrelated bytes survive. Returned bytes never alias caller-owned
Buffers or typed arrays. No-op transactions preserve original bytes, counters,
checksums and mirrors. Array bounds come from the native getters: variables
4000–416F, saved flags 1–C9F; flag zero is a non-writable sentinel. Review
[the native evidence](../research/save_core/native_evidence.md) for exact addresses.

## Harness protocol

`cli/worker.mjs` is the Node-only boundary. It accepts newline-terminated JSON:

```
{"version":1,"id":1,"op":"decodePokemon","bytes":"BASE64","args":{}}
```

Replies contain `version`, the request `id`, and either `result` or
`error: {code, message, operationIndex?}`. The worker bounds message lengths,
requires canonical base64, validates JSON shapes and numeric ranges, reserves
stdout for protocol replies, and remains usable after rejected requests.

Operations are `handshake` (no bytes/arguments), `decodePokemon` (`diagnostic?: boolean`), `patchPokemon`
(`changes`, `tailPolicy`), `inspectSave`, `transactSave` (`operations`),
`calculateStats`, and the explicit empty-slot fixture initializer `emptyPokemon`.
Mutation results return base64 `bytes` and a report; the worker attaches source
and output SHA-256 values. Save reports include profile, selected mirror/counter,
actual changed byte ranges, and `nativeLoadVerified: false`: a successful edit
alone does not establish that a scenario is playable. Raw arbitrary-offset
patching is deliberately absent from this protocol.

Saved fixture operations are `setFlag`, `setVar`, `setLocation`, `placePlayer`,
`setPocket`, `editPartyMon`, and shrinking-only `setPartyCount`. The exact typed
schema is `FixtureOperation` in `src/transaction.ts`. `patchPokemonFixture` supports
bounded species, held item, ability, form, fateful flag, OT ID, EXP, current HP,
partial move slots and PP. Partial move edits preserve remaining slots and PP
Ups, with legacy default PP 10 when omitted. Empty-slot initialization is not a
playable Pokémon constructor; native Pokémon generation remains in the harness.

Independent synthetic constructors and BigInt codec oracles live in `tests/`.
They are deliberately not implemented with the production writer. Keep runtime
verification readers independent too.

Mixed sequence tests use deterministic seeds and an independent full-byte oracle
to check rollback/retry, shrinking parties, all eight pockets, and exact audit
ranges. `node work/save-core/scripts/mutation-check.mjs` compiles isolated semantic
mutants and requires the intended regression assertion to fail. Compilation or
infrastructure failures never count as caught mutations.

Run the Python and architecture gate with
`python3 work/tools/check_save_harness.py` from the repository root, adding
`--with-images` when the pinned Pillow dependency is present. Native CN/EN
verification is a separate local gate with explicitly pinned private inputs;
see [the native verification guide](../research/save_core/NATIVE_VERIFICATION.md).
