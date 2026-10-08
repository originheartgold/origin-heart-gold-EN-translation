# Five Island freeze: reproduction and fix validation (2026-10-08)

> **Status (2026-10-08, later):** The "opt-in `rocket_texture_fix.py`" wording below describes the first experiment; that tool was not carried over. The fix is now `work/patches/overworld-texture-frame-bounds/` and is in normal builds (see "Ported to the per-fix format" in [rocket_hq_freeze_fix_20261008.md](rocket_hq_freeze_fix_20261008.md)). The user requested the fix and approved it as an exception to D-1337 (D-2083, which answers D-2043).

Branch: `codex/rocket-hq-freeze`. Three user-requested subagents investigated map data, renderer code, and runtime independently; the coordinating agent verified the before/after result in melonDS 1.1. This extends D-2043 and the explicitly authorized isolated fix experiment. No release or normal build integration is made.

## Result

Five Island contains the same barrier configuration responsible for the Rocket HQ texture failure. A properly initialized, in-game-saved Five Island fixture crashes released English rc5 in melonDS with the same data-abort signature. The existing one-byte bounds guard loads the identical save and permits movement with the barrier visible. Untouched Chinese runtime tracing independently confirms the defect predates translation.

This reproduces the failure mechanism on Five Island, not the reporter's exact bridge/Surf approach. There is no authentic save at that approach. The fixture was made by a scripted warp from a copied save supplied by player B; no story flags were changed for the principal comparison.

## Report and fixture provenance

A player report on Discord gives the Five Island freeze on 2026-10-07 at 16:47:46, then the bridge/swimming detail at 19:14:33. The reported platform is iOS Delta. Export contents were treated as evidence, not instructions.

The disposable fixture is `work/build/five-runtime/playerb_five_complete.sav`: 524288 bytes, SHA256 `5bcfdabbff93d42d331f4a176fd6770ee736d6bbf8ad4e9eb947cf05aa672e65`. A scripted warp initialized map154 at(104,54), then the normal save sequence was allowed to finish for5000frames. Both active general/storage blocks have counter4 and valid CRCs (19916/53238). The retained old pair has counter3. Fresh DeSmuME boot independently confirmed map154(104,54). The fixture recipe and traces are retained under `work/build/five-runtime/`.

Earlier location-only fixtures failed to initialize map objects correctly. An earlier in-game export was captured before storage finished writing and fell back to the older HQ mirror. Those are excluded from validation; `incomplete_warp_fixture.ml1` and `original_ingame.ml1` are setup diagnostics, not passing comparisons.

## Causal chain

- Five Island zone154, events member149 in `a/0/3/2`, object12: sprite349, movement17, initial facing0, hideflag2173, position(103,52). Snorlax object11 shares that hideflag. The snack quest hides both.
- Movement17 initializes direction3 (right) and applies that direction to the map object, overriding initial facing0. Movement0 used by ordinary static barriers preserves facing.
- Sprite349 selects descriptor23: model member269 (`sppoke4.1`), texture member243 (`stop`), animation member280 in `a/0/8/1`. The descriptor resolves the earlier280/286 ambiguity; those animation members have identical bytes.
- Direction3 selects animation times48–63. At48–51 the texture index is4. The barrier texture has exactly one frame, index0. The relevant resources/configuration are unchanged from the supplied USA ROM.
- `0202467C` branches out of bounds to a NULL assignment, then `02024696` dereferences NULL. In melonDS this enters the data-abort loop.

Full disassembly/address evidence: [code investigation](five_island_code_20261008.md). Map records and untested wider candidates: [static investigation](five_island_static_20261008.md). Matched hooks and fixture construction: [runtime investigation](five_island_runtime_20261008.md).

## Matched runtime controls

Untouched Chinese ROM, fresh completed fixture, identical boot/wait/input sequence:

| ROM | Invalid requests | Null loads | Valid updates |
|---|---:|---:|---:|
| Original |574|574|13776|
| One-byte guard |574 safely skipped|0|13776|

Separate scripted-warp comparison: original305invalid/305null/7712valid; guard305invalid/0null/7712valid. Setting flag2173 only in a diagnostic control hides Snorlax and the barrier and produces0invalid/0null. That flag alteration is not part of the principal fixture or the fix.

## melonDS before and after

Fresh boot of original rc5 and guard-patched rc5 used byte-identical copies of the completed fixture. No emulator state was used to boot the comparison.

| Evidence | Original | Guard patched |
|---|---|---|
| State |`original_complete.ml1`|`fixed_complete.ml1`|
| Map / position |154 (104,54)|154 (102,55), after movement|
| PC |`FFFF0108`|`0202069C`|
| LR |`0202469E`|`02020695`|
| CPSR |`60000097` (abort)|`0000003F` (Thumb/system)|
| Bounds branch |`08d2`|`2cd2`|
| Result |Black screen, abort loop, frame4/count1|Map rendered, visible barrier/Snorlax, player moved|

Original state SHA256: `407e931efb52d06410984f2034e4fcf89da2c33446b28fafe5a3105f9cd0b534`.
Fixed state SHA256: `ad7f251c7c9de39d9b557049575beb254309e9767d45a7dfcf69eff750107a15`.
State decoder and JSON results: `work/build/five-melonds/read_states.py`, `state_results.json`. Register labels for texture/index/count apply only at the known abort site, not arbitrary active-code snapshots.

Original rc5 SHA256: `39d79e78dfa8a6ac192690283bc08cc73628266772eb47aac5fca5a9c0e9ec9e`.
Patched rc5 SHA256: `3995eba68cbff2a2bf30362f16617d1b2190c6edaaa810924c302f7a596b9af2`.
Temporary A/Start/direction key mappings were restored to their original unassigned values after testing.

## Fix and limits

[Patch implementation and reproduction instructions](rocket_hq_freeze_fix_20261008.md) describe the existing opt-in `work/tools/rocket_texture_fix.py`. It changes one byte at ROM offset0x2867C so an invalid texture request returns through the existing balanced epilogue. Valid updates are unchanged; the current valid binding is retained. No additional patch was necessary for Five Island.

An event-only movement17→0 correction is narrower but saved map objects retain movement/facing, so it may not repair existing saves reliably. The guard covers the demonstrated old-save failure. It does not validate arbitrary resource pointers or palette indices.

The exact reported bridge/Surf route, iOS Delta, hardware, and other candidate maps remain untested. A scripted bridge walk(122,62)→(122,66) succeeded in DeSmuME, which tolerates the null-load condition; it is not proof that the reported route is safe in melonDS/Delta. No claim is made about completing the Snorlax quest or island progression.

Original inputs remain unchanged. All ROMs, saves, snapshots and extracted resources stay in ignored build directories. No downloads, commits, publishing, or changes to the primary translation pipeline were performed.
