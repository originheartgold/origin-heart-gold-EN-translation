# Native saved variable and flag bounds

Read-only investigation, 2026-10-09. Reference: untouched Chinese
`origin_v4.0.3_cn.nds`, SHA-256
`4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`.
The existing `ndspy` and `capstone` installations decompressed and decoded ARM9
in memory; no ROM data was written or downloaded.

The array-adjacency estimate in the initial research was too generous. Native
`GetFlagAddr` at `0x0204F8E4` establishes these actual bounds:

- Flag zero returns null immediately (`0x0204F8E8..EE`); it is a sentinel, not an
  editable saved bit. Rejecting a request to edit zero prevents misleading success.
- Below `0x4000`, the getter computes `flag >> 3` and compares against
  `0x65 << 2 = 0x194` (`0x0204F8F8..900`). On an invalid byte index it calls
  the assertion function at `0x02025B2C`. Valid saved IDs are therefore
  **1 through `0xC9F` inclusive**, not through `0xCBF`.
- The saved flags start at array offset `0x2E0` (`0x0204F906..90C`). The flags
  occupy `0x194` bytes, so the structure ends at `0x474`. Bytes between this
  structure's end and the next saved-array offset are not flag storage.
- IDs from `0x4000` take a different branch (`0x0204F910..926`) using a global
  temporary array, with byte index below 8. Those flags are not battery-save edits.

`GetVarAddr` at `0x0204F92C` subtracts `0x4000`, compares the result against
`0x17 << 4 = 0x170`, then computes `base + index * 2`. The saved variable API
must accept exactly **`0x4000` through `0x416F` inclusive**, each a u16. It must
also reject IDs below `0x4000`: the native getter's signed comparison is not a
sufficient safe boundary for externally supplied integers.

Existing boot evidence places this saved array at `0xEAC`. Consequently the
variables span `0xEAC..0x118B`, the flags span `0x118C..0x131F`, and
`0x1320..0x1323` must remain untouched. The next LocalFieldData array starts at
`0x1324`. The allocator-size function at `0x0204F840` returns the literal
`0x474`, consistent with the getter-derived structure size.

These are native storage bounds, not proof that every in-range story ID is
meaningful or safe for gameplay. Editing progression remains a fixture operation
whose in-game consequences must be verified for each scenario.

# Native save mirror selection

The same Chinese ARM9 contains the counter comparison at `0x02027B84`, block
ranking at `0x02027BBC`, and complete general/storage recovery logic at
`0x02027C4C`. Counter comparison treats `0xFFFFFFFF` as older than zero, zero as
newer than `0xFFFFFFFF`, and otherwise compares unsigned integers. Equal counters
return zero; block ranking chooses mirror zero first on equality.

A valid block must have the expected size, magic, ID and CRC (`0x02027A94`).
Invalid blocks have their internal comparison counter set to zero
(`0x02027B30`), independent of their untrusted on-disk footer.

For ordinary valid counter states, the selection algorithm is: rank valid general
blocks by the native counter comparator; choose the first general block whose
**same-mirror storage block is valid and has the same counter**. This explicitly
allows falling back to an older coherent pair when the newest general and storage
counters disagree. Independently choosing the latest general/storage blocks is
incorrect for this ROM.

Detailed branches (G/S are counts of valid general/storage copies, H/L the
higher/lower ranked general mirror):

| G | S | Native branch |
|---|---|---|
| 0 | 0 | Return status 0 (no save) |
| 0 | positive | Return status 3 (corrupt) |
| positive | 0 | Return status 3 (corrupt) |
| 2 | 2 | Coherent H: select H/status 1; otherwise coherent L: select L/status 2; otherwise status 3 |
| 1 | 2 | Sole general coherent with same-mirror storage: select it/status 2; otherwise status 3 |
| 2 | 1 | Coherent H: select H/status 1; otherwise coherent L: select L/status 2; otherwise status 3 |
| 1 | 1 | Valid mirrors must agree; assert counters equal, then select same mirror/status 1 |

The 2/2 path is at `0x02027D3E..D92`; 1/2 at `0x02027D94..DC0`; 2/1 at
`0x02027DC2..E16`; 1/1 at `0x02027E18..E56`. Selected mirror and counter are
stored by `0x02027C34`.

Two malformed-input quirks must not become writing permissions: the 2/1 branch
can compare a valid general counter zero to the artificial zero counter of an
invalid storage block, and the 1/1 branch calls the assertion routine for unequal
counters but has a fall-through selection path. The safe external editor should
reject both. Require an actually valid, equal-counter storage block in the
selected mirror. Rank the general mirrors **before** this validation: if native
would select a general counter zero by matching an invalid storage block's
artificial zero, reject the entire save. Do not silently fall back to an older
coherent pair that the native branch would never reach. This matters for
`[0, 0xFFFFFFFF]` and tied `[0, 0]` with the first-ranked storage invalid, plus
the reversed rollover case. This conservative divergence is intentional: editor safety is
not permission to exploit native corrupt-save recovery accidents.

Static branch analysis supports a selection policy; it is not a replacement for
boot/save/reset observations. The root integration run records native loader
matrix observations separately.

# Native location slots and open Pokémon contexts

LocalFieldData is saved array 5 (`0x0203AEBC`) and has size `0x80`
(`0x0203AE14`). Five accessors return offsets `0`, `0x14`, `0x28`, `0x3C` and
`0x50` at `0x0203AE50`, `0x0203AE54`, `0x0203AE58`, `0x0203AE60` and
`0x0203AE5C`. The next accessor at `0x0203AE78` addresses `0x64`, confirming
exactly five contiguous 20-byte location slots. Location index five would damage
other field state and is rejected.

EnterMonDecryptionContext at `0x0206CFC8` sets **both** header bits 0 and 1
(`0x0206CFE2..CFF4`) before decrypting the tail and box; exit at `0x0206D014`
clears both, recalculates the boxed checksum and reencrypts. The box-only context
at `0x0206D060` sets bit 1 and decrypts only the box; its exit is `0x0206D088`.
Thus the stable native context states are zero (closed), two (box open), and
three (whole party record open). GetMonData at `0x0206D848` tests bit 0;
GetBoxMonData at `0x0206D948` tests bit 1. Diagnostic decoding uses bit 1 for box
plaintext and bit 0 for tail plaintext, while production writers reject every
nonzero header flag. Flag one alone is not a stable state emitted by these
context functions and must not be taken as evidence of a writable record.

# Native boot matrix observations

The independently implemented [native loader probe](native_loader_probe.py)
booted private copies derived from a fixed seed with distinct money markers in
each mirror. Its 14 cases ran against both the untouched Chinese ROM above and
the available English ROM SHA-256
`6fa7b4e739391ca9ea9bfcf90d83eec6407c3c04102e52432bb41bc8ae44a7d3`.
Seed SHA-256:
`b3aca10747cd0f1adc3d5852a50dddaaa36ed8680f5ba04012cfe3110faad90f`.
Both reports confirm source ROM and seed hashes stayed unchanged.

Both languages selected the expected first/second ordinary generations, mirror
zero on equal counters (including divergent content), zero after the special
counter rollover, and the older coherent mirror when newest storage was corrupt
or mismatched. Damaged newest general also fell back; damaged backup remained
usable. Crossed storage counters, both mismatched storage counters, and both
corrupt storage copies produced no loaded seed marker. This last observation is
limited to the probe's boot/input window; it does not establish a specific
on-screen error string or recovery UI state.

Local evidence is retained under ignored `work/build/save-core-native-loader-cn/`
and `work/build/save-core-native-loader-en/`, including reports and screenshots.
The synthetic TS mirror tests encode the expected policy independently and do not
depend on these local artifacts. These boots test initial selection; they do not
by themselves establish save-in-game/reset persistence for every malformed case.

# Repeatable verification and generator scope

The [local native gate](NATIVE_VERIFICATION.md) now pins all four binary inputs,
checks worker build identity before emulation, and reproduces the loader matrix,
harness operations and combined save/reset persistence on both ROMs. It also
adds a three-member party scenario with edits to its last active slot.

The generator issue is narrower than the original six-member smoke suggested:
three-member generation produces a valid record, while the original sixth-slot
path still yields malformed closed data. Initializing that sixth slot with a
native-ZeroMonData-shaped empty record does not fix the Chinese-seed reproduction.
The cause is not established; do not label it a confirmed hack bug or repair it
automatically. The whole-record write trace overflowed and is not complete
instruction-level evidence. See the native gate document for the diagnostic
commands and exact limits.
