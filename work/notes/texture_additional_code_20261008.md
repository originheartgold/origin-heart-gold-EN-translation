# Additional texture and palette binary audit — 2026-10-08

This is a read-only search of the supplied original Chinese v4.0.3 ROM. It extends the proven Rocket HQ / Five Island issue without treating every suspicious instruction sequence as a reproduced gameplay bug. No patch or input ROM was changed.

## Binary search

The scanner in ignored `work/build/five-code/additional.py` searches the entire ARM9 and every decompressed ARM9 overlay, at halfword alignment, for an unsigned bounds branch (`BHS`) whose target sets a register to zero and then reaches a load through that register, either directly or after one unconditional branch. This exact signature finds five sites. Disassembly inspection distinguishes their roles:

| Bounds branch | NULL assignment | Dereference | Assessment |
|---|---|---|---|
| ARM9 `0202467C` | `02024690` | `02024696`: word load | Known overworld texture-frame failure; existing experimental guard addresses this site. |
| ARM9 `020246AC` | `020246BE` | `020246C0`: byte load at +3 | Material dictionary iteration inside the texture updater. The loop already bounds its index against the same dictionary count, so no normal invalid-index route was established. |
| ARM9 `02024780` | `02024792` | `02024798`: halfword load at +2 | A genuine analogous unchecked **palette** lookup. Out-of-range palette indices reach NULL. Not fixed by the texture-only guard; no natural gameplay reproduction yet. |
| ARM9 `020247B4` | `020247C6` | `020247C8`: byte load at +3 | Material dictionary iteration inside the palette updater; same loop-invariant caveat as the texture material loop. |
| Overlay 87 `021EDB0A` | `021EDB20` | `021EDB26`: word load | Another texture dictionary lookup in helper `021EDAD0`, with texture index supplied as function argument r2 and preserved in r4. This is outside the shared overworld updater. Natural caller/scene and invalid input not identified. |

The palette updater starts at `02024758`. It obtains the palette dictionary from TEX0 offset `0x34`, reads its count, compares requested r2 against count r1, and still dereferences the NULL result. For the proven barrier case, the palette index is always 0 and palette count is 1; this additional site is therefore not needed to explain that failure. A runtime test should record r2 and r1 at `02024780`, and NULL loads at `02024798`, before considering a palette guard.

There are additional malformed-resource assumptions nearby: the texture/palette routines dereference a NULL model-derived pointer at `02024666` / `0202476A` if their model input is absent, and nested material helpers assume valid model/material references. These are structural preconditions, not evidence of further map bugs. The exact-pattern scan is not an exhaustive proof that no other unsafe paths exist, and scanning aligned data can theoretically produce false hits; the five listed sites were manually disassembled as code.

## Sprite/resource cross-check

The full overlay-1 sprite table has **1,801 rows**, ending at its `0xFFFF` sentinel at `02208DCE`. Its descriptor-selected animation was compared with the texture and palette dictionary counts in `a/0/8/1`.

**Twenty-four sprite IDs** have only one texture but select animation member 280, whose possible texture indices are 0–15:

`84, 85, 86, 87, 210, 270, 271, 272, 273, 274, 275, 276, 290, 349, 395, 396, 397, 398, 399, 400, 401, 402, 403, 404`.

All of these have valid palette selection zero. They share generic directional ranges `(0..15), (16..31), (32..47), (48..63)`. This is a **compatibility risk under unsuitable movement/facing**, not a list of 24 broken sprites: a correctly configured static object stays at time 0 and requests texture 0. The map-audit agent is independently checking actual event movement/facing assignments. The strongest direct candidates are objects forced to directions 1–3 by movement types 15–17, or initialized with those directions. Movement type 14 forces direction 0 and should not be classified as broken merely because it is nonzero.

**Seven additional sprite IDs**, 263–269, have three textures and three palettes but select animation member 293. Its time keys are `0,4,8,12,16,20,22,24`, with texture and palette selections both `0,1,0,2,3,4,5,6`. Descriptor 21 uses a special range table `(0,0,0), (1,15,0), (16,25,1), (0,0,2)`, rather than the ordinary four directional ranges. Therefore the mere presence of keys 3–6 does not establish normal reachability: a specialized handler may deliberately select the valid subset. These require object-handler tracing before being called defects. If a natural path does select time 16 or later, **both texture and palette** can become invalid and the current texture-only guard would not be sufficient.

The scan skips resources which are not ordinary BTX0 textures and entries whose descriptor/animation does not parse under the verified fixed-table format. It does not validate dynamic sprite remapping, alternate clothing archives, every specialized animation controller, or saved-object changes. Exact candidate dictionaries and instruction matches are retained in ignored `work/build/five-code/additional_candidates.json` and `bounds_null_patterns.json`.

## Next useful tests

1. Join the 24 single-texture candidates with real event movement/facing data; reproduce suspicious naturally reachable map objects using their normal flags.
2. Instrument both texture and palette bounds checks on those maps, reporting invalid requests separately from actual emulator aborts.
3. Trace sprite263–269's specialized handler before testing its animation tail; avoid forcing impossible states and presenting them as gameplay bugs.
4. Identify overlay87 helper callers and resource IDs before proposing a fix there.

No additional defect is declared runtime-proven by this code-only audit. The root agent's and map/runtime agents' reports establish any actual reproductions separately.

A supplementary palette probe was prepared but cancelled while waiting for an emulator slot, before emulator initialization. It produced no measurements; no zero-invalid-palette runtime claim is made. The scratch probe now names the complete Five Island fixture for any future run.
