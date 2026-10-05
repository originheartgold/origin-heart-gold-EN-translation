# Trainer data and runtime interpretation review — 2026-10-05

Follow-up: the old research dump's parsed fields have now been regenerated in the ignored v3 bundle. See [the follow-up review](trainer_research_followup_2026-10-05.md) for entry-linkage and partial facility-runtime verification that supersede the broader unresolved statements below.

Read-only source: untouched `work/rom/origin_v4.0.3_cn.nds`. No ROM was built or changed. The fixes affect guide parsing only.

## Coverage and discoveries

An independent unpack of the fresh ROM's trainer archives, compared with the pre-review website export, found exact agreement for all 1,023 trainers / 3,891 party slots: class/name mappings, party count, battle flag, trainer items, levels, species values, explicit abilities, held items, stored natures, scaled IV parameter, EV bytes and moves. Every party length matches its declared count. This proves extraction parity, not that the former parser correctly interpreted every field.

Disassembling the Chinese runtime exposed three errors in that interpretation:

1. **Forms:** byte 2 of each 28-byte trainer Pokémon record is the form. The old parser ignored it and read the species word's top bits instead. All those top bits are zero; 21 slots have nonzero form bytes. The loader reads byte 2 at `0x020727A4`, passes it to field 112 at `0x02072822–0x0207282A`, and the setter at `0x0206E590` stores its five low bits. The species word is passed directly to creation.
2. **EV labels:** bytes 20–25 are HP, Attack, Defense, Speed, Special Attack, Special Defense. The loader at `0x02072880–0x020728C4` writes fields 13–18 in order. The stat calculator reads fields 16–18 at `0x0206D608–0x0206D63E`; their values are combined with personal-data bytes 3–5 at `0x0206D736`, `0x0206D776`, `0x0206D7B6`. These are Speed, Special Attack, Special Defense. The guide's display order requires permutation 0,1,2,4,5,3. This changes 1,129 displays; 32 other nonzero spreads are unchanged by that permutation.
3. **HP IV override:** creation first uses floor(raw IV parameter × 31 / 255) at `0x020727F8–0x0207281E`. The loader then chooses 10 for levels ≤40, 20 for levels 41–79, or 31 for levels ≥80 at `0x020728E0–0x020728FE`. The loop at `0x02072900–0x02072912` writes field 70 six times without incrementing its field register. Field 70's setter at `0x0206E478` changes only the low five bits of the packed IV word: HP IV. The other five retain their initial scaled IVs. Every one of the 3,891 stored slots differs from the former uniform-IV display. Preserve this original behavior; do not fix the game.

`parse_trpoke` now returns the actual form, EVs in guide display order, and a separate `hp_ivs` alongside `ivs` for the other five stats. Regression tests cover boundaries, form byte, EV permutation, and hashes of the reviewed source code regions so these claims are not silently applied to a different runtime.

## Additional runtime facts and limitations

- Nonzero explicit ability IDs are applied after creation at `0x0207282E–0x0207283A`. The field-10 setter at `0x0206E3A6` stores a full u16. Therefore the known nonstandard trainer abilities are intentional stored overrides, not grounds for replacing them with species defaults. Two Castform slots and the known species-zero placeholder have zero ability IDs, meaning no explicit override.
- A nonzero first move at byte 12 causes all four stored move slots to be applied (`0x0207283E–0x0207285A`); otherwise creation's level-up moves remain. There are 150 slots with no explicit move list. Blank lists must be described as default level-up moves, not as a Pokémon knowing no moves.
- Held item is applied directly from bytes 10–11 (`0x0207285C–0x02072864`). Misty's record 254 therefore retains its stored Wise Glasses; there is no inferred substitution based on evasion.
- Nature 255 leaves creation's nature in place; other values write a nature override (value + 1) to field 190 at `0x020728C8–0x020728DC`. There are 2,731 unspecified natures. A blank nature is not a claim that a Pokémon has no nature.
- Byte 26 sets field 189 for records 635 and 636, slot 6. This review preserves it in the original bytes and makes no new player-facing claim about that flag.
- Record 865's first Deoxys has form byte 4, for which the form table has no entry. The personal-data loader at `0x02071834` calls lookup `0x020721C0`, whose no-match return at `0x020721EE` preserves the base species ID; therefore its personal stats fall back to base Deoxys. Sprite/battle-specific behavior remains unverified. Keep it identified as stored form 4, never silently relabel it as a canonical form.
- No emulator battle replay was performed in this review. The conclusions above follow the actual Chinese party loader, setter and stat calculator; later battle-specific modifications are outside this audit.

## Affected form slots

Slot numbers below are one-based.

| Trainer record | Slot | Correct stored form |
|---|---:|---|
| 10 | 6 | Fan Rotom |
| 129 | 3 | Wormadam (Trash Cloak) |
| 147 | 2 | Frost Rotom |
| 174 | 3 | Wormadam (Trash Cloak) |
| 197 | 2 | Mow Rotom |
| 336 | 2 | Frost Rotom |
| 362 | 1 | Heat Rotom |
| 476 | 3 | Wash Rotom |
| 553 | 5 | Wash Rotom |
| 557 | 1 | Giratina (Origin Forme) |
| 557 | 2 | Wash Rotom |
| 562 | 5 | Wormadam (Trash Cloak) |
| 623 | 3 | Mow Rotom |
| 647 | 3 | Heat Rotom |
| 795 | 3 | Frost Rotom |
| 835 | 4 | Wormadam (Trash Cloak) |
| 865 | 1 | Deoxys, stored form 4; unresolved |
| 865 | 2 | Deoxys (Speed Forme) |
| 865 | 3 | Deoxys (Defense Forme) |
| 1015 | 1 | Giratina (Origin Forme) |
| 1015 | 3 | Frost Rotom |

## Review of the recent independent job's data

The recent job is in `/private/tmp/poke-difficulty-research`, with output in its ignored `work/build/difficulty-trainers-v2/` directory. Its original and v2 rosters contain all 1,024 archive records including sentinel zero. Their IDs, metadata, parsed parties and raw-party SHA-256 hashes agree with each other; all 1,024 raw hashes independently match fresh Chinese ROM members. Both rosters inherited the old parser's form/EV/HP-IV interpretations and should be regenerated before their parsed fields are reused. Their raw provenance remains useful.

`facilities.json` was independently checked against fresh CN and US ROM archives:

| Archive | Members checked |
|---|---:|
| a/1/2/9 | 951 Pokémon sets |
| a/2/0/3 | 951 Pokémon sets |
| a/2/0/4 | 478 Pokémon sets |
| a/1/2/8 | 307 trainer pools |
| a/2/0/2 | 315 trainer pools |

All 3,002 member payloads, indices, lengths, decoded fields, trainer membership lists, bounds, archive hashes, US comparison hashes/counts and changed-member lists agree. This validates the inventory. Its form field is explicitly a candidate; facility routing, levels, IVs, selection rules, facility-name mappings and links to ordinary trainer IDs remain unverified. Do not promote those candidates into ordinary story teams.

All 1,379 `decode_frontiers.json` records match their actual script archive sizes and boundary/opcode observations: 1,349 outside-file targets and 30 in-bounds unknown/truncated opcode observations. Those counts describe decoder limitations, not broken scripts or proven missing encounters.

All 15 `unreferenced.json` entries retain the corresponding complete roster party and have no reference in that static index. They are unresolved, not proven inaccessible. This audit does not claim a complete independent reachability analysis.

Audit scripts and machine-readable summaries remain ignored under `work/build/trainer_review/data/`. No game-data dump was added to version control.

## Final exported-data check and Illuminate follow-up

After regeneration, an independent fresh-ROM check of the current `site/src/data/trainers.json` passed all 1,023 trainers and 3,891 slots. Each slot's exported species/form name and ID, EV permutation, HP IV and other-five IV value matches independently calculated expectations. This covers all 21 nonzero form bytes, all 1,129 changed EV displays, and all 3,891 HP-IV corrections.

A bounded additional static search did not isolate Illuminate's battle accuracy handler confidently enough to state its exact modifier. The Chinese ability description explicitly says the Pokémon is harder to hit, and trainer 254's Starmie directly stores item 267 (Wise Glasses). The guide should retain that verified held item and attribute the evasion explanation to the hack's description. No percentage or blanket guarantee about all causes of misses is established by this follow-up.
