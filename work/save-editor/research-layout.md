# Origin v4.0.3 save container investigation

Read-only inspection of six local battery-save fixtures under `work/build/memcheck`, 2026-10-04. No game text or binary data included here. These findings are original observations, not an imported format implementation.

## Verified container layout

All six fixtures are raw 524288-byte saves. Two copies of the following blocks occur at mirror bases 0 and 0x40000:

| Block | Offset relative to mirror | Total length | Footer relative to mirror |
|---|---:|---:|---:|
| General | 0x00000 | 0xF7CC | 0xF7BC |
| Storage | 0x0F800 | 0x18408 | 0x27BF8 |

Each footer is 16 bytes, little endian:

| Offset in footer | Type | Observed meaning |
|---|---|---|
| 0 | u32 | Save counter |
| 4 | u32 | Total block length, including footer |
| 8 | u32 | Magic 0x20060623 |
| 12 | u16 | Block ID: general=0, storage=1 |
| 14 | u16 | CRC |

CRC is non-reflected CRC16-CCITT with polynomial 0x1021 and initial value 0xFFFF, no final XOR. Coverage starts at the block start and ends immediately before the footer. Verified against Python `binascii.crc_hqx(payload, 0xffff)` for all 24 block copies across all six fixtures. This is strong binary evidence for sizes, boundaries and CRC.

The bytes between blocks, after storage and outside these checked regions must be preserved. Their complete purpose has not been established.

## Party

General-relative offset 0x90 contains party capacity (6), +0x94 is u32 party count, +0x98 is first party record. Party records have a 236-byte stride. The existing `work/tools/memcheck.py` independently documents runtime party capacity/count/header and 236-byte stride from Chinese hack code; the first 136 bytes are the boxed record. This investigation does not establish the remaining party-record fields.

## Observations across fixtures

Each observed mirror has equal counters for general and storage. The higher-counter mirror's count agrees with the scenario:

| Local fixture | Mirror 0 counter/count | Mirror 0x40000 counter/count |
|---|---|---|
| full_bag_6mons | 8 / 6 | 7 / 1 |
| route1_townmap | 4 / 2 | 3 / 2 |
| protographer | 6 / 1 | 5 / 1 |
| market | 6 / 1 | 7 / 1 |
| trainer | 4 / 1 | 5 / 1 |
| route1_path_2mons | 2 / 1 | 3 / 2 |

## Remaining uncertainty and safe prototype behavior

**Historical initial investigation:** at that point, the game’s exact recovery behavior with torn writes, mixed counters, equal counters, or u32 counter rollover had not been verified. For the prototype, require valid matching general/storage counters within a mirror, choose the strictly newer coherent mirror in ordinary counter cases, and reject ambiguous cases rather than inventing recovery rules. Do not infer unverified vanilla block offsets; Origin's observed sizes are different.

An unchanged export should preserve the entire input byte-for-byte. A party-only edit should preserve the untouched mirror and storage block, edit only the selected party record and general CRC, and retain the existing selected counter. In-game loading must confirm this editing policy; checksum agreement alone is not that confirmation.

Box-record boundaries and nonempty boxed fixtures have not been established by this container investigation. Money/inventory offsets are also outside this investigation.

**Historical update 2026-10-04 (superseded editor policy):** the editor no longer requires both mirrors and matching storage counters. It selects the newest general block whose footer and CRC are intact, ignores storage blocks and the other mirror (preserved byte for byte), and still rejects equal-counter mirrors with different content and counter rollover. Gen 4 tools such as PKHeX select general and storage blocks independently. The editor never changes counters, so it cannot change which copy the game picks.


**Current policy, 2026-10-09:** the shared TypeScript core requires valid general
and storage blocks at the same mirror with equal counters. It ranks coherent
pairs using the Chinese ROM's native comparison: ordinary unsigned order, except
zero is newer than FFFFFFFF; equality chooses the first mirror. This can select
an older coherent generation when the newest general/storage counters disagree.
No coherent pair means no writable save. Divergent equal-counter mirrors are
accepted because the native tie selection is deterministic. Storage and the
unselected mirror stay byte-exact; no counter changes are invented. The old
claim that ignoring storage cannot affect game selection was incorrect.

See [native disassembly evidence](../research/save_core/native_evidence.md) and
[implementation verification](../research/save_core/IMPLEMENTATION.md). Native
assertion fall-throughs and invalid-storage artificial-zero comparisons are
intentionally rejected instead of being treated as permission to edit.
