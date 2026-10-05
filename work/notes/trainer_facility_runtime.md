# Facility runtime audit — 2026-10-05

Source: the untouched Chinese v4.0.3 ROM, inspected directly with ndspy and Capstone. No download, ROM build, game change, or emulator battle replay. This extends the archive inventory review in `trainer_runtime_review.md`; it establishes several previously unknown field meanings and runtime paths, but is **not a complete verification of every facility mode's selection policy**.

## Reproduction and guarded evidence

From the repository root:

```
.venv/bin/python work/research/trainer_verification/facilities_disasm.py
.venv/bin/python work/research/trainer_verification/facilities_verify.py
.venv/bin/python work/research/trainer_verification/facilities_test.py
```

The first command produces local disassembly and candidate cross-references. Linear disassembly includes data; only the manually traced routines below are treated as code evidence. The second checks SHA-256 guards on 26 reviewed code regions, checks both Factory script members, and validates the ROM's archive path table before deriving form/EV interpretations for all 2,380 facility set records. Output, including ROM-derived data, stays ignored under `work/build/trainer_verification/facilities/`. No archive payload is added to git. Ten reference-model regression tests cover EV budget/order, form truncation, packed IVs, IV thresholds, level sentinels, and the differing duplicate/fallback policies. These test the transcribed models; they are not CPU execution tests.

## Archive consumers are located

The ROM's path table at `0x0210E21C` maps archive constants as follows:

| Runtime constant | Archive | Inventory |
|---|---|---:|
| 128 (`0x80`) | a/1/2/8 | 307 trainer pools |
| 129 (`0x81`) | a/1/2/9 | 951 sets |
| 204 (`0xCC`) | a/2/0/2 | 315 trainer pools |
| 205 (`0xCD`) | a/2/0/3 | 951 sets |
| 206 (`0xCE`) | a/2/0/4 | 478 sets |

The resolver at `0x02007838` and its optional remapper at `0x020077F8` were checked: none of these five archive IDs is in the twelve-entry remapping table. ARM9 wrappers `0x0204B18C` and `0x0204B19C` directly select 204 and 205. Overlay 77 wrappers `0x02225F40` and `0x02225F54` accept the archive ID from the caller and reach the same NARC readers.

The route at `ov77:0x02232A54` chooses set archive 129 or 205, and `0x02232A68` chooses the corresponding trainer archive 128 or 204. Both use `0x02232A98`: mode values other than 3 or 6 choose the newer 204/205 pair; modes 3 and 6 retrieve two participant records through `0x020346D8` and call `0x0202950C`. **The Chinese ROM patches that getter to `movs r0, #7; bx lr`.** Both results are therefore nonzero: assuming participant retrieval/assertions complete, this selector always returns 1 and chooses 204/205, including modes 3 and 6. The purported live participant-flag distinction is absent in this ROM. The caller at `0x022323CE` loads the trainer pool, the sampler at `0x02232414` reads its set IDs, and the constructor at `0x022326A4` consumes the selected archive. The legacy 128/129 alternatives are present in the selector but are not selected by this patched path. This alone does not prove they are unreachable from every other caller.

Another path explicitly supplies archive 206 at `0x02233656`, through `0x022337FC` → `0x02226540` → `0x02225FCC`. This proves that its form words are consumed by the common constructor too. No ordinary story-trainer ID is used as a substitute for the facility set/pool namespace.

## Verified set construction

The shared constructor is `ov77:0x02225FCC`; its result is materialized into a Pokémon at `0x02226194`. The earlier ARM9 constructor at `0x0204AD50` and archive-selecting constructor at `ov77:0x022326A4` show matching field handling. These are facility paths; do not apply the ordinary trainer loader's HP-IV bug to them.

| Field | Verified handling |
|---|---|
| Species | u16 at offset 0, masked to eleven bits in the intermediate representation. |
| Form | u16 at offset 14, **low five bits**, packed above species at `0x02226006–0x0222600E`; unpacked into Pokémon field 112 at `0x022261EA–0x022261FC`. This is no longer merely a candidate field. |
| Moves | Four u16 values at offsets 2–9, copied into the intermediate record and then fields 54–57. |
| Item | u16 at offset 12 normally used, but an explicit caller flag replaces it with the item table at `0x02237578` (four entries indexed by slot modulo four). Thus stored item is not an unconditional statement about the generated battle. |
| Nature | Byte 11 constrains generated PID: `PID % 25` must match. The loop also rejects the XOR-based shiny predicate at `0x0206F42C`. A supplied nonzero PID bypasses both tests. |
| Ability | Reads base-species personal fields 24/25 through `0x0206EFA8`; selects second ability when it exists and PID is odd, otherwise first. Applies the stored ability to field 10 later. No hidden-ability selector occurs in this constructor; do not infer a fixed ability from the set alone. |
| IVs | Caller-supplied value's low five bits are repeated across all six IV slots (`0x02226088–0x022260C6`) and applied as packed field 175 (`0x022261B2–0x022261E0`). |
| EVs | Byte 10 is a six-bit mask. For nonzero masks, each selected stat gets `min(255, floor(510 / popcount(mask)))`; other stats remain zero. Bit order is HP, Attack, Defense, Speed, Special Attack, Special Defense. |
| Level | Supplied by the caller. Materializer special values 120/121 mean level 50/100 (`0x022261A4–0x022261B0`); other supplied levels pass through. |

The EV mask loop uses the bit helper at `0x020718B8`. EV writes into Pokémon fields 13–18 at `0x0222627A–0x022262E2` confirm the ordering. The player-facing display order needs permutation 0,1,2,4,5,3, as with ordinary trainers.

Archive a/1/2/9 has zero masks at records 0, 67, and 160; a/2/0/3 and a/2/0/4 have zero masks only at record 0. With no selected bits, no EV bytes are written after initialization, so the result has zero EVs. This observation does not claim to emulate the intermediate division helper's divide-by-zero handling.

Across all 2,380 records there are only two nonzero form words, both in a/2/0/4 (values 1 and 2). The checker emits verified form and EV values for each record in the ignored supplement. It deliberately does not invent per-record battle levels or IVs.

## Selection policies differ

At least three distinct rejection samplers are present (the third is the Factory rental sampler described below). A single label such as “random team without duplicates” loses material behavior:

- ARM9 `0x0204AFCC` and overlay `0x02232414` choose a pool index using RNG remainder by pool size (the result is narrowed to a byte on these paths). They reject species already selected, and can reject species in an external exclusion list. Nonzero item duplicates within the team or external list increment a counter. Once that counter reaches 50, item checks are skipped; the constructor receives the fallback flag and substitutes slot-dependent items. Species checks remain. The counter is accumulated across team construction, not a separate 50-attempt cap per slot. There is no proof of perfectly uniform probability because the source is a bounded RNG followed by remainder.
- Overlay `0x02226634` samples archive 205 and always rejects species **or item** duplicates among already accepted sets (including an item value of zero). It also checks supplied external species/item lists; after 50 external-list conflicts, only those external checks are bypassed. Internal duplicate checks remain. It returns a fallback indication. Caller `0x0222670C` handles the single/split-team cases separately. This differs from the preceding sampler.

The IV helper `0x022265F8` (also ARM9 `0x0204A9F0`) maps facility trainer IDs to values: below 100 → 3; 100–119 → 6; 120–139 → 9; 140–159 → 12; 160–179 → 15; 180–199 → 18; 200–219 → 21; 220+ → 31. Its use is traced in `0x0222670C`, but it is not the only IV policy: `0x022337FC` gives trainer IDs 307/308 value 31 and otherwise reads a separate indexed table via `0x022338D4`. Do not apply the first helper to every facility.

A separate level helper `0x0223308C` chooses 50/100 from a state byte, and its caller at `0x022330E6` passes that to the materializer for six records. Another path uses `0x02233860`, whose special-case helper `0x02233930` takes levels from participating Pokémon. These prove that a global “all facility sets are level 50” rule would be false; semantic mode labels and every calling context still require tracing.

## Names and remaining limits

The facility trainer constructor at `0x02225F64` loads name bank 26 and indexes it with the **facility trainer ID** (`0x02225FA2–0x02225FA8`), independently of story names. In the current translated bank, 305/306 are Palmer, 307/308 Argenta, 309/310 Thorton, 311/312 Dahlia, 313/314 Darach. This is a name mapping, not a claim that the story trainer records 707–711 define these teams.

The previous statement “facility routing and field interpretation unverified” is now too broad. Archive consumers, form interpretation, EV generation, shared construction, and the particular selection paths above have been traced in the Chinese runtime. However, the following remain unresolved:

1. End-to-end mapping from every map/script/menu mode to these functions and facility names, including all multiplayer and saved-session routes.
2. Every stage/rank-dependent trainer range, set eligibility table, weighting, rental exchange path, and special Brain override. The presence of multiple policies makes a vanilla-based shortcut unsafe.
3. All caller values for levels, IVs, forced PID, and item fallback, plus later facility events or temporary battle modifications.
4. Emulator replay of these paths. Static code guards establish that the reviewed instructions have not changed; they do not establish that all branches have been exercised.

Keep the main dump labelled an inventory with a **partial runtime supplement**. The confirmed field meanings can be used now; a complete player-facing facility team list still needs the unresolved dispatch/selection work above.


## Concrete Battle Factory menu-to-runtime example

This final pass establishes a named route, without relying on vanilla facility equivalence:

1. The CN map mapping assigns zone 275 to the Battle Factory, field script 84 and message bank 105. That bank explicitly labels its receptionist and Level 50/Open Level menu. In script 84, selecting menu item 21 (Level 50) writes variable `0x4144 = 0` at `0x01B2`; selecting item 22 (Open Level) writes `0x4144 = 1` at `0x01C0`. The battle-format selection writes `0x4143`, and the fresh-entry path initializes `0x4003 = 0`.
2. Script 84 at `0x0411` runs field command 627 with byte argument 3. The actual CN command table resolves 627 to ARM9 `0x02045AB4`, which stores that byte into the application argument at offset `0x20`. Application initialization `0x02095BBC` passes it to overlay routines `0x022268A0` and `0x022269AC`.
3. Application ID 3's 40-byte descriptor at `0x0223767C + 3*40` supplies runtime-script member 1. Loader `0x02226A94` resolves archive constant 182 to **a/1/8/2**, loads member 1, and starts its entry zero. Its entry offset is `0x02D6`. This is the Frontier's separate bytecode, not field-script opcodes.
4. Runtime opcode 62 at offsets `0x02D6`, `0x02DC`, and `0x02E2` copies field variables `0x4143`, `0x4144`, and `0x4003` to runtime variables `0x8001`, `0x8002`, and `0x8003` respectively. Its actual handler is `0x022293BC`. At `0x034C`, runtime opcode 92 consumes `[0x8003,0x8001,0x8002]`. Its dispatch entry is `0x0222B570`, which invokes state initializer `0x0222BC6C`. On the fresh-entry branch, that stores format at state offset 4 and the level-menu value at offset 5 (`0x0222BCCC–0x0222BCD0`).
5. The same Factory object's level helper `0x0223308C` reads offset 5: zero → level 50, nonzero → level 100. `0x0223309C` uses it when materializing six rental records, passing the level directly into `0x02226194`. Thus this named menu's 50/100 meaning is verified by runtime dataflow, not inferred solely from dialogue.
6. Factory rental generation through `0x0222BE68` → `0x02232D8C` → `0x02232C04` selects archive **a/2/0/3**. The last routine samples inclusive set-ID ranges from the selected eight-byte stage table row, rejects species or held-item duplicates among accepted rentals and any supplied exclusion lists, and stores each accepted row's IV byte. **It has no 50-conflict relaxation.** This is a third policy, separate from both earlier samplers.
7. For the explicitly bounded case **stage-table index 0 with no rental upgrades**, the Level 50 table at `0x0223849C` selects IDs **1–150**, with all six IVs **0**; the Open Level table at `0x0223844C` selects IDs **351–486**, also with all six IVs **0**. These are rental candidates, not a fixed opponent team. Higher stages, upgrade counts and resumed sessions select other rows/branches and are outside this example. The IV byte is supplied through `0x02226580` to the already-reviewed constructor, so the ordinary trainer HP override does not apply.

This is a static map/menu/state and constructor linkage. The graphical screens and a complete seven-battle run were not replayed. The runtime script's other branches (wireless setup, resume, exchange and battle events) have not all been decoded, so this example must not be broadened into an exhaustive Factory guide.
