# Trainer encounter context review — 2026-10-05

Reviewed the current Chinese-ROM script/event decode and the recent research index at `/private/tmp/poke-difficulty-research/work/build/difficulty-trainers-v2/`. No ROM, translation bank, or raw trainer dump was modified or copied into tracked files.

## Full-index cross-check

All 941 research battle callsites match the current Chinese decode at the recorded script file and byte offset, including opcode and raw arguments. Checked the partner/opponent designation for all 1,367 participant entries against command argument position. All 18 exported badge instructions match the current `GiveBadge` opcode and argument. These checks verify the index, not global reachability or a required progression order.

A second automated pass freshly extracted the Chinese ROM to an isolated ignored cache (`work/build/trainer-context-review/fresh.pkl`) and verified its SHA-256 against the research provenance. The executable audit is `work/build/trainer-context-review/audit.py`. It additionally rederived every resolved battle argument, participant role, syntactic entry candidate and zone association; all 18 syntactic preceding-battle candidate lists; all 17 menu assignment paths; and all 1,379 decoder-frontier records in 473 files (1,349 outside-file, 30 in-bounds unknown/truncated). All matched. Recomputed unreferenced-team membership is the same 15 IDs. This is structural automation across the full dump, not manual proof of every path.

Read the research validator and collection/progression reports before using their conclusions. In particular, the badge-candidate graph is syntactic: its 18 rows cannot be presented as 18 proven badge battles. The research index's stale `curated_dead_scene` value differs from the new review in precisely one place: file 741 offset 151.

## Corrections implemented

- **Blue's old Viridian badge encounter is dormant.** File 741 entry 1 alone reaches battle 261 at offset 151. No object, background event, or coordinate event in zone 496 invokes entry 1; map-header file 516 invokes entry 3 only. Added entry 1 to `DEAD_SCRIPTS`. Record 261 remains playable at the Mt. Silver lodge; this marks the encounter, not the whole team, dormant.
- **Memory rematches had missing locations.** File 78 selects 17 trainer IDs through variable `0x800C`. Independently checked each explicit assignment's path through flag 311 to the single call at 1083 or same-team double at 1040. Added both forms at the Frontier Access Pokémon Center, with the final Hall of Fame and menu-selection context. The generator checks the reviewed local instruction patterns against the ROM before accepting these associations. Menu cancellation/fallback behavior is not included in the claim.

`python3 -m unittest work/tools/docs/test_trainer_context.py`: four tests passed. They verify the absent Blue trigger plus surviving lodge encounter, Giovanni's actual Earth Badge call and Blue's later rematch, all 17 memory selections in both formats, and Misty's Gym partner/opponent distinction.

## Leader classification and display facts

- Misty: initial Gym team 254; rematch 721. Teams 83, 84, 123 and 989 are partners; 989's Cerulean Gym appearance is specifically a partner scene. Record 272 combines partner scenes with a probably-never Victory Road opponent branch. Do not treat every Misty team, or every team appearing inside a Gym, as a Gym challenge.
- Lt. Surge: Gym team 255; record 142 is the separate Vermilion story multi battle.
- Koga: Gym team 257; record 325 is Janine disguised as Koga, confirmed by file 806's battle at 553 and subsequent reveal. Keep the stored battle label and explain the disguise rather than silently renaming game data. Record 286 is the forest-preserve trial, not the badge team.
- Giovanni: actual Viridian Gym story opponent 662, file 741 battle 2311; Earth Badge 7 at 2863. Blue 727 is the later Gym rematch. Blue 261's old Gym call awards Rising Badge 15 and is dormant as above.
- Whitney: both 30 (multi battle with Gold as partner and Norman as second opponent) and 714 (single battle) appear before the Plain Badge. Record 714 is also reused for rematches. High trainer IDs do not identify rematches reliably.
- Clair: initial team 35 does not immediately award the Rising Badge; the Dragon's Den trial does. Avoid claiming every first Gym team immediately earns its badge.

The research file-112 edge from battle 937 at 167 to badge 15 at 4728 is real syntactic evidence, but is not a direct Clair badge battle. It is Elder Tianyuan's trial followed by the shrine quiz and subsequent dialogue; the guide describes those intermediate steps. Keep it separate from Clair's team 35. The file-741 edge from Blue 261 to badge 15 similarly matches bytes but belongs to the dormant entry, whereas Giovanni 662 leads to Earth Badge 7 in the live scene. These are the clearest examples of why reproducing a candidate edge does not validate its player-facing interpretation.

For presentation, follow the walkthrough's Kanto progression: Brock, Misty, Lt. Surge, Erika, Koga, Blaine, Sabrina, Giovanni. Sabrina's Pokémon Tower step requires the Volcano Badge, so listing her before Blaine by vanilla badge order is misleading. Follow the walkthrough's Johto chapters: Falkner, Bugsy, Whitney, Morty, Jasmine, Chuck, Pryce, Clair. Label this as guide order rather than a fully proven mandatory sequence; local badge checks do not establish global prerequisites. Blue is a later Viridian Leader, not a replacement for Giovanni's initial challenge.

## Remaining limits

The research dump retains 15 records without a decoded battle/map-object reference. They are unresolved, not proven unused. Generic script 949 still has runtime-selected trainer variables requiring caller context. The index preserves incomplete condition summaries and static-reference-only reachability; object visibility lifecycles, map access, unusual decoder frontiers, facility runtime pools, and every alternate route have not been proven by this review. No emulator playthrough was performed. Exact team contents and runtime ability precedence are reviewed separately by other agents.
