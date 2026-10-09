# Pokédex wild encounter and trade restriction audit (2026-10-09)

Read-only research against the untouched Chinese v4.0.3 ROM, using the local ROM readers and native-code dumps from the prior source verification. No ROM built or changed. Reviewed conditions are exported in `work/tools/site/acquisition_trades.json`; Safari object requirements are now retained by `safari_held.py`.

## Starter choice and normal wild encounters

Charmander's normal source is **Rock Tunnel, map 342, encounter record 83, morning slot 11, Lv. 5, 1%**. The morning period is 04:00–09:59. It is absent from the day/night tables and from **Rock Tunnel B1F**, map 452, encounter record 109. These were reread through `romdata.Rom` against the untouched CN data.

**No starter restriction exists in the inspected ordinary wild selection path.** This is separate from the explicitly starter-gated rescue/gift quests. Evidence:

- ARM9 `0203A7B0–0203A7E4` obtains the encounter bank from the map header. The only custom branch is map 109 (Pal Park): header bank + weekday − 1. It never reads the starter.
- ARM9 `0203AD24–0203ADAA` loads that record and applies the eight map/date overrides at `020F6A64`. Rock Tunnel is not a calendar override target.
- Overlay 2 `02246E44–02246E92` chooses morning/day/night by clock and copies species/levels directly from the encounter buffer.
- Normal land selection `02247154–022471FA` applies swarm and radio modifications, then uses `02247770 → 02247F24`. Land slots are chosen through the ordinary RNG or lead-ability branches. No starter choice or starter flag is read.
- `0224819E` has a species-specific exclusion for **Unown (201)**, not starter species. Other rejection checks handle lead/level/Repel behavior. No Charmander-specific replacement was found.

This supports showing the ordinary Charmander encounter to every starter. No new emulator replay of all starters was performed. Native paths for visible overworld spawns were already audited separately in `chinese_source_rom_verify_mechanics.md`; this pass does not claim that every retained visible-spawn state was replayed.

## Wild sources that must keep their conditions

- Keep exact map/floor, time/weekday, method, level and table slot probability on the Pokémon page. A region/area and “grass” alone loses information even when the underlying map tables are right.
- Keep **Old Rod, Good Rod and Super Rod** distinct for ordinary fishing. The stored night-fishing replacement fields are inactive in this hack and must be excluded; see the final native verification below.
- Keep **Headbutt common/rare/special tree class**. The existing docs identify common versus rare by Trainer ID; the record does not mean every tree can yield every listed species. Special rows require at least one special tree in the map's record. Headbutt has no Badge requirement; field interaction details are verified in `guide/13-dungeons-and-common.md`.
- Exclude **Hoenn/Sinnoh radio** and **swarm** encounter rows. Their slot-replacement routines exist, but the hack disables the required state getters. The final native audit below supersedes the earlier provisional uncertainty about schedules. Stored replacement species are not obtainable through these methods.
- **Pal Park** uses seven weekday records, including the hack's Sunday off-by-one table (Cerulean Cave's record 141). Record 148 is not selected. Fixed Catch entry costs $10,000, needs six free PC slots and no stocked transferred GBA Pokémon, and uses the player's own Balls. Keep the weekday and Fixed Catch method. Sunday Surf/fishing are possible; Rock Smash is excluded because the map has no breakable rocks. Existing audit: `availability_audit.md` and the Resort Zone section of `guide/04-celadon-fuchsia-saffron.md`.
- **Calendar** entries must keep exact date, time, floor and slot weight. They replace the ordinary final 1% land slot only. Native loader and emulator outcomes, including map-load refresh behavior, are documented in `chinese_source_rom_verify_calendar.md`. Volcanion's zero-rate Lake of Rage land entry is not obtainable. Diancie resolves to ordinary Diancie despite stored form 4. These are already handled by the reviewed exporter.
- **Safari Zone ordinary-map placeholder** (Rattata) and **contest-map ordinary table** must stay excluded. Safari has its own area tables. The Bug-Catching Contest uses only its **first species set**, on Tuesdays, Thursdays and Saturdays; the extra National Dex sets are inactive in the hack.
- **Island Forest** is not globally gated behind the Ruins of Alph puzzles. The old claim was rejected in `guide/known-issues.md` and the native gate audit; do not reintroduce it as a restriction on all species there.

## Final native encounter gate verification

These findings supersede this audit's initial provisional advice to retain radio/swarm/night-fishing tables with uncertainty labels. The remaining-source agent independently traced the activation paths; the fishing path was independently checked by both agents, including fresh CN overlay2 extraction in this audit.

- **Swarms are disabled.** ARM9 `0202DC08` returns literal zero. Land handler `02246EEC` calls it at `02246EFE`, and Surf handler `02246F30` calls it at `02246F40`; both skip their replacement branches. Stored grass/Surf swarm species must not seed availability or appear as acquisition sources.
- **National Dex radio species are disabled.** ARM9 `0202AA74` returns literal zero. Overlay92 music constructor `021F4EF2` stores this as bit0 of state+4; branches `021F4F66/021F4F84` cannot choose the National Dex music modes. Table `021F7A28` stores tracks1100/1099/1169/1170; overlay2 `02254590` recognizes1169/1170 as Hoenn/Sinnoh encounter modes3/4. Those tracks' activation condition never succeeds. The replacement handlers themselves remain in overlay2, but their existence is not evidence of a reachable source. Companion finding D-2294 / `pokedex_wild_gates.md`.
- **Night-fishing and fishing-swarm fields are unused.** Normal fishing begins at overlay2 `022472D4`. `0224737E–022473BE` copies exactly five slots from the selected rod table at record offset `80`, `94` or `A8`; `022473D6 → 02247860 → 02247F24` selects from that array. The fishing branch at `022480F8–02248144` applies lead-ability/RNG slot selection (`02247AD0`) and level selection (`02247BF8`). There is no clock-based replacement and no read of record fields `C0` or `C2`. Remove both stored replacement categories, preserving the ordinary five-slot rod tables. Fresh CN overlay2 disassembly confirmed this call sequence.
- **Contest always uses the first set.** Overlay25 constructor `0225BFEC` calls the disabled National Dex getter at `0225BFF2`, writing its result to bit1 of state+17. Set selection `0225C526` checks that bit and selects set0 at `0225C534`; the alternate weekday-based selection is unreachable. Only the first stored set is active, regardless of the ordinary three contest weekdays. Exclude the other three stored sets and their species-source claims (D-2294).

The companion agent registered D-2293 for disabled swarms and D-2295 for inactive night-fishing/fishing-swarm fields.

## Unown map reachability

**Exclude map490, the unused Arceus-event underground-hall copy, from encounter sources.** All script warps to it are file40 @506, file44 @510, file46 @506 and file47 @506. They require research progress variable `0x403E == 6`. The complete script writer scan finds only file38 @2304 (`AddVar 0x403E,1`), behind the research progression that requires `0x40EC >= 1`; no reachable script raises that gate (existing guide13 audit / D-1427). The event-warp scan finds no inbound map warp to490. Its own map53 load conditions and Arceus-event scenes execute only after entry and do not establish an external route into the map. No alternative condition-loaded entrance was found.

**Exclude map491 too.** A subsequent independent collision check established that the relocated entrance tiles (418/419,284) are solid blocked terrain. The accessible doorway instead leads to map323. See `work/notes/pokedex_unown_access.md` for the raw collision evidence and reproduction steps.

## Safari object requirements

All 12 area records in CN `a/2/3/0` were parsed fresh: **2,484 candidate rows**, of which **684** require objects (includes three time periods). Previously the helper discarded every object's requirement record.

The native Safari loader at ARM9 `02096A0C` confirms the layout already used for species: 120 bytes of ordinary time tables per method, then `12 * additional_count` bytes of additional time tables, then `4 * additional_count` requirement bytes. Each four-byte record is:

`[category1, minimum_points1, category2, minimum_points2]`

At `02096B12–02096B38` both requirements are checked; category2 zero means no second requirement. Categories are 1 Plains, 2 Forest, 3 Peak (rocks), 4 Waterside (water). Bank 0422 #10–13 describes the same four object categories in that order. Eligible additional entries replace ordinary slots in sequence; they are not unconditional rows.

These thresholds are **effective block points, not a guaranteed count of placed objects**. At `02096BDC` the area's development counter is divided by ten; `02096B98` uses category-dependent thresholds at `02107B26` to determine each object's point contribution. Mature areas can meet requirements above the object limit. This pass does not derive a full days-to-points schedule or replay Safari ownership/object unlock events.

Examples from the fresh ROM: Forest grass Bronzong requires **56 Peak + 35 Forest points**, and Beldum requires **63 Peak points**. Showing either as simply “Safari Zone” is incomplete.

Implementation: conditional helper rows now add `requirements: [{category: "Peak", points: 56}, ...]`. Ordinary rows keep their prior shape. Requirements use the same additional-slot index in morning, day and night. Parser rejects unknown categories, zero-point categories and points with category zero. Four focused parser tests pass, and all fresh CN records pass validation.

## Complete trade inventory

All 13 records are reachable script sources; no trade source was excluded. Each has one `trade + file` metadata entry. Regular trades require the named offered species and are one-time unless stated below. No ordinary trade checks starter choice or player gender.

| Trade | Receive | File / command offset | Additional restriction |
|---|---|---|---|
| 0 | Raticate | 156 @4969 | Defeat Gentleman (battle156); offer Butterfree during S.S. Anne visit. |
| 1 | Butterfree | 161 @969 | Reverse trade only after trade0 (flag1515); offer Raticate. Clears1515. |
| 2 | Ditto | 884 @168 | Budew; requires flag441 (normal Goldenrod, not the Rocket occupation); completed flag1616. |
| 3 | Feebas | 916 @592 | Goldeen; completed flag138. |
| 4 | Pineco | 88 @1552 | Hoothoot; annex east door, answer “Insomnia Pokémon”, then “Hoothoot”; flag509 clears on completion. Wrong answers retry. |
| 5 | Torkoal | 116 @1021 | Bagon; completed flag2132. |
| 6 | Pidgeot | 115 @5818 | Pikachu-only replacement after lending own Pidgeot; start after Volcano but before Earth/Champion; receive Lv20 after Hall of Fame with free slot. |
| 7 | Mudkip | 761 @348 | Shellder; completed flag1040. |
| 8 | Gyarados | 172 @2481 / @11020 | Male + Bulbasaur only; Celadon rescue/Misty wounded-Starmie scene; free party slot, retry if full; Lv20. |
| 9 | Onix | 751 @148 | Beedrill; completed flag307. |
| 10 | Skarmory | 860 @160 | Exeggutor; completed flag1814. |
| 11 | Porygon2 | 940 @215 | Dragonair; completed flag226. |
| 12 | Rhyhorn | 5 @159 | Bonsly; completed flag357; Thunder Fang is added @197. |

Trade6 is not a free Pidgeot gift: the original Pokémon is removed and a fixed replacement is created. The existing emulator evidence confirms loss of the original's level, moves, EVs and item (D-1392/D-1552). Trade8 is encoded as a loan; the guide confirms Misty lets the player keep it at the end of the arc. Neither should be described as an unconditional ordinary trade.

Both received Pokémon are permanent. Metadata marks both `retains: true`, with acquisition kinds `replacement` (Pidgeot) and `gift` (Gyarados), and level 20. A fresh scan of every `ReturnLoanMon` command finds only file115 (Pidgeot hand-in), file240 (Jigglypuff), file842 (Mr. Mime), and file913 (Tentacool). None takes Gyarados. Celadon file853 / bank0547#106 explicitly tells the player to keep Misty's Gyarados. Do not label these received Pokémon “temporary loan” merely because their creation command is named `GiveLoanMon`.

Goldenrod flag441 has multiple story writers and is not simply “after a particular single battle”: the safe player wording is **not during Team Rocket occupation**, matching the dialog on its false branch. Map access remains subject to ordinary story progression; absence of an extra gate in the NPC script is not a promise that the map can be reached at game start.

## Additional native verification for the other acquisition audit

**GetGameVersion always returns 7.** Command495 in the CN table at `020F793C` points to Thumb handler `02044C6C`; `02044C7E movs r1,#7`, `02044C80 strh r1,[r0]`. Therefore the Goldenrod Game Corner's alternative Sandshrew branch (`GetGameVersion != 7`) is unreachable in this hack. Evidence sent to the special-source agent; Sandshrew still has other real wild sources.

## Validation and limits

`python -m unittest discover -s work/tools/site -p test_safari_held.py`: 4 tests pass. Fresh CN Safari records: 2,484 rows / 684 conditional. Trade metadata: 13 distinct `(trade,file)` entries; all match `gen_docs.trade_places` and the ROM's give species.

No download, ROM patch, translated bank edit, or game-data commit was performed. Radio, swarms, night-fishing replacements and extra contest sets are now verified inactive, not merely awaiting schedule research. Remaining qualifications in this report are Safari development/unlock details (see the companion native-gate audit for subsequent findings) and physical accessibility of map491's relocated entrance warps.

## Final Safari access correction

The block-point parser remains useful for auditing the stored data, but those bonus encounters are excluded from player acquisition listings: Object Arrangement never unlocks because Baoba’s calls require the disabled National Dex getter. Basic Safari area tables remain. See `pokedex_wild_gates.md` and D-2296.
