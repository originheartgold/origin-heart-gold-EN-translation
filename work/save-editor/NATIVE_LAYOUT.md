# Origin rc5 advanced editor layout research

Checked 2026-10-07 against the user’s local English Origin v4.0.3 rc5 ROM and save. No ROM or save is included. Exact ROM and guide-data SHA-256 hashes are recorded in `src/core/editor-reference.ts`. That reference is regenerated from local files by `scripts/generate-editor-reference.mjs` (ROM path, optional guide species JSON path).

## Save chunks and checksums

The ARM9 save table at `0x020f30cc` has 42 entries of 16 bytes: index, block, size getter, initializer. Native size getters confirm player `+0x60/0x2c`, party `+0x90/0x5b0`, bag `+0x644/0x864`, Pokédex `+0x13a8/0x370` and Mystery Gift `+0x9ee0/0x1680`. Each chunk rounds its data size to four-byte alignment and adds a CRC16 plus two padding bytes. Summing the general chunks and the 16-byte main footer yields `0xf7cc`; storage starts at `0xf800`. These independently agree with the existing save parser.

Edits repair affected inner CRCs and the main block CRC. PC edits also repair its inner CRC at storage `+0x183f4`. Counter selection, backup mirrors and unaffected chunks are preserved. The checksum algorithm is the existing CRC16-CCITT implementation.

## Pokédex

Native caught reader `0x0202a508` addresses species `(id−1)` at chunk `+4`; seen reader `0x0202a554` addresses the same bit at `+0xcc`. The native species upper-bound constant is 1025. The local save marker at general `+0x13a8` is `0xbeefcafe`. Only verified seen/caught bits are edited. Remaining bit-array padding and form/gender/language records stay untouched.

## Mystery Gift

Table entry 27 points to size getter `0x0202ddd0`, returning `0x1680`. Native readers `0x0202ddf4` and `0x0202de1c` confirm eight gifts at `+0x100` with stride `0x104`, and three cards at `+0x920` with stride `0x358`. The special card is at `+0x1328`. Native insertion at `0x0202de54` links gifts by the low two flag bits; card insertion at `0x0202ded4` checks byte `+0x152` bit 3 for a pending gift. Receipt readers/setters at `0x0202e1a4` onward address 2048 bits at chunk start. Native card removal clears its tag/receipt and associated gift. The editor preserves unrelated events and the special card.

Import validation accepts only native Pokémon, Egg and Item payloads; it checks Origin species/forms or known item IDs before changing a save. Full compatibility of other event handlers and vanilla event-file imports is not established.

## Pokémon fields

Metadata follows the four decrypted 32-byte blocks: friendship/markings/language in A; nickname flag and modern egg/met locations in B; nickname/origin and Gen IV contest ribbon banks in C; OT, dates, legacy locations, ball, met level/OT gender and terrain in D. Origin uses vanilla’s B+20 ribbon storage for nature/shiny overrides and B+26 for its expanded ability ID. Those bytes are excluded from ribbon editing. Gen III ribbons in that overwritten bank are therefore not exposed.

Unedited contest stats and party tails are preserved. Named ribbon controls follow Gen IV ordering; advanced banks retain unknown flag bits. Native form mappings come from the existing verified ARM9 reference and are limited to five-bit form values 1–31. Forms not encodable in that field are not offered.

## Supporting primary references

These describe vanilla structure names; Origin offsets above were separately checked in the local ROM, rather than assumed from upstream.

- [Save layout and CRC functions](https://github.com/pret/pokeheartgold/blob/master/src/save.c)
- [Save table](https://github.com/pret/pokeheartgold/blob/master/src/save_arrays.c)
- [Pokémon block fields](https://github.com/pret/pokeheartgold/blob/master/include/pokemon_types_def.h)
- [Mystery Gift structures](https://github.com/pret/pokeheartgold/blob/master/include/mystery_gift.h) and [operations](https://github.com/pret/pokeheartgold/blob/master/src/mystery_gift.c)
- [Item metadata fields](https://github.com/pret/pokeheartgold/blob/master/include/item.h)

No upstream implementation code was copied; the editor implements these independently from format observations and the existing codec.
