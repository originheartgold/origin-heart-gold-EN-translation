# Softlock audit of the hack's event scripts (Phase A, step 1)

**Status (reviewed 2026-09-29): current (Phase A record).**

Status: 2026-09-29, agent phaseA2. This audit covers the **original hack's** game logic in `work/rom/origin_v4.0.3_cn.nds`. Our build has byte-identical scripts, map events and headers (`integrity_audit_text.md` §1), so every finding here applies to both. No bank, tool or build file was changed. The findings are registered as D-1331 … D-1336. The Blackthorn tutor bug is D-1305, which this audit confirms.

**Bottom line:** the audit found **no hard dead end on the main story path**. One real bug affects all seven weekday siblings once they give ribbons (D-1331): the script dies after the ribbon, which leaves its message on screen but doesn't freeze the game (observed, D-1558). One latent crash is a warp whose target no longer exists (D-1332). The rest are missables, cosmetic slips and one out-of-range save write.

## Method

All tools are Python scripts in the session scratchpad (`phaseA2/`). The scratchpad is temporary, so they are not kept in the repo.

1. **Disassembler for `a/0/1/2`.** It uses pret's `asm/macros/script.inc` argument table (853 commands, with the conditional-argument commands 400–402, 465 and 489 handled). The hack's command table (arm9 `0x020F793C`, count word at `0x020F78CC`) has **843** entries, the JP base. It follows every script-header entry through `GoTo`/`GoToIf`/`Call`/`CallIf`/`ObjectGoTo`/`BGGoTo`/`DirectionGoTo`/`GoToIfTrainerDefeated`.
   - Level-script files (map-header `scriptHeaderBank`) are parsed separately: `type, u32` records; type 1 holds the `var == value → script` scene tables.
   - hg-engine: its `Script_RunNewCmd` extension isn't wired into this table, and no script uses a command ≥ 843 except the broken bytes in D-1331. The hack does keep hg-engine's `ScrCmd_WildBattle` hook, which has the same argument layout.
2. **Map data.**
   - Events (`a/0/3/2`): bg 20 bytes, object 32 bytes, warp 12 bytes, coord 16 bytes.
   - Map headers and the std-script bank mapping come from `bank_maps.json` / arm9 `0xF70E0`.
   - For comparison, the same pipeline was run on the US ROM (header table at arm9 `0xF6BE0`, std mapping at `0xFA4A4` after decompression).
3. **Index.** Every flag and var set, clear and test; item give, take and check (`GiveItem`, `std_give_item_verbose` with a constant-propagated `0x8004`, item balls in file 141); Pokémon gifts and species checks; `CheckBadge`/`GiveBadge`; script and event warps; trainer battles; show/hide of objects.
4. **Detectors:**
   - **Lock state.** Abstract interpretation of `LockAll`/`ReleaseAll` over every entry, into `Call` and `CallStd`, looking for `End` reached while locked and for aborts (a bad opcode or running off the file).
   - **Menu B-button.** Every cancellable menu (4th init byte = 1) is simulated with the B result `0xFFFE` (from ov01 `0x021EE520`).
   - **Flags.** Tested but never set; object hide flags set and never cleared; flags past the flag array.
   - **Vars.** Coord triggers and scene tables whose value is never assigned, or that are permanent.
   - **Branches.** Gender branches (`GetPlayerGender`) and starter branches (`GetStarterChoice`): the effect sets of the two sides (flags, vars, items, gifts, warps, trainers, show/hide) are compared outside their common tail.
   - **Key items.** Required but never given, or needed on maps that come earlier in `play_order.json` than any giver.
   - **Warp graph.** Event warps, overworld adjacency and script warps, from the start house (zone 64): trap zones, unreachable zones and one-way warps.
   - **References.** Event script ids past the file's script count, std ids past their file, warp anchors past the target's warp count, message ids past the bank, trainer ids and species ids.
   - **HM gates.** The field-move badge checks were read from arm9 (`0x0206721E` …).
5. Every candidate was then read by hand in the disassembly with the Chinese and English text beside it, and diffed against vanilla where that helped.

## Coverage

| Item | Count |
|---|---|
| `a/0/1/2` files | 966: 516 script files (69 of them stubs or unused), 450 level-script headers |
| Script entries / decoded commands | 7,167 / 292,869; 1.28 MB of 1.47 MB decoded as code (the rest is movement data and unreachable bytes) |
| Unknown opcodes | only `2009` (0x07D9), in 7 files. It's an invalid id, not a hack command; see D-1331. |
| Parse errors | 16 stub files of 4–24 bytes (e.g. 288, 297, 332–335, 648) that no zone uses |
| Events | 489 event files for 540 zones: 6,731 objects, 1,131 bg events, 1,548 warps, 409 coord triggers |
| Level scripts | 486 records, including all scene tables |
| Cancellable menus simulated with B | 971 (all 997 menus parsed) |

## Findings by severity

| # | Severity | What | Evidence | Register |
|---|---|---|---|---|
| 1 | Script abort (not a freeze) | Weekday siblings' ribbon gift aborts mid-script, leaving `LockAll` active and the text box open. **Observed in the emulator** (all seven, both ROMs): the ribbon is given; the player can still walk, X opens the menu (the message clears) and SAVE works (`emu_harness.py guide0813 --case ribbon`, D-1558) | Files 225 @3985 (Route 29), 232 @12121 (Route 32), 243 @2334 (Route 36), 246 @764 (Route 37), 934 @5653 (Lake of Rage), 937 @2784 (Blackthorn), 958 @1078 (Route 40). Bytes after `GiveRibbon 0x8002, 59–65`: `4E 00 14 00 \| D9 07 …` = `PlayFanfare 20`, then opcode 2009 ≥ 843, so `RunScriptCommand` stops the context. US has `PlayFanfare 1185 / WaitFanfare / SetFlag <daily> / WaitButton / CloseMsg / ReleaseAll / End`. | D-1331 |
| 2 | Softlock if reachable (latent) | Unused National Park north gatehouse (zone 150, "Pokéathlon Dome") exits to National Park warp #5, but the hack's zone 96 has only 5 warps (0–4). `Field_GetWarpEventI` returns NULL, so the player lands at garbage coordinates. **Observed in the emulator** (both ROMs): the exit drops the player in zone 96 at x 16384, y 59693 on a black screen, unable to walk; the entrance tiles (33,15)/(33,16) are blocked, so normal play can't get there (`emu_harness.py hackbugs --case gatehouse_warp`). | Zone 150 warp 0 → (96, anchor 5). Entrance: zone 96 warp #4 (33,15); zone 487 warps (33–35,15). Vanilla zone 96 has 7 warps. | D-1332 |
| 3 | Save-data side effect | Flags 0x1C76 (Route 1 Viridian Mart promo, file 168 @235/@1954) and 0x116D (Mt. Mortar expedition end, file 962 @1819) are past the hack's 3,232-flag array (bound 0x194 bytes, block size 0x474). The writes land in the next save block (by the vanilla layout, the Pokédex). The events still behave once. | Hack `GetFlagAddr` at `0x0204F8E4`, sizeof at `0x0204F840` | D-1333 |
| 4 | Missable | Cameron the photographer never appears on Route 34: the level script does `CheckBadge 18`, which is always false, so it sets `FLAG_HIDE_CAMERON`. **Observed in the emulator** (Wednesday and Thursday, all 16 badges; `hackbugs --case cameron`). | File 237 @4691 → L6244 | D-1334 |
| 5 | Gameplay bug (not a softlock) | The Blackthorn Move Tutor promises Play Rough but teaches move 175 (Flail). **Confirmed**, also **observed in the emulator** (3- and 4-move paths; `hackbugs --case tutor`). | File 944: `MonHasMove … 175` @1925; `SetMonMove … 175` @3461 and @3619; text 0626 #62–68 says 嬉闹 | D-1305 |
| 6 | Cosmetic / exploit | After every Hall of Fame the legendaries respawn even when already caught, because no hack script sets `FLAG_CAUGHT_*` (0x116, 0x117, 0x169–0x16D, 0x173, 0x175, 0x17B). The clearing was **observed in the emulator** (file 822 from L154; `hackbugs --case ssticket`). | File 822 @189–@288 (`CallIf <` → `ClearFlag FLAG_HIDE_…`) | D-1335 |
| 7 | Cosmetic | Route 30 NPC: `CheckBadge 16` is always false, so one line never shows | File 227 @789 | D-1334 |
| 8 | Cosmetic | Dead flag checks: Route 36 gatehouse NPCs always say the odd tree still blocks the road (0x1C2); the Elite Four door operators never say "the door is already open" (0x211–0x214; the door still opens through `HidePerson`); a Route 4 line is gated on flag 2007, which is never set | Files 862 @33/@61, 817–820 @1623…, 178 @121 | D-1336 |
| 9 | Latent, unreachable | The Route 39 barn (zone 214, script file 250 with 2 scripts) has objects 1 and 3–6 on scripts 3 and 4, which don't exist. No map warps into zone 214. | `bad_local_ref` | – |
| 10 | Latent, unreachable | Dark Cave Route 31 side (zone 176, file 964): 34 `NPCMsg` ids past bank 0338 (49 strings). No map warps into zone 176. | – | – |
| 11 | Gameplay bug (not a softlock) | Goldenrod fortune teller: the "ideal Pokémon" reading checks for $300 but takes $10000, so with $300–$9999 it is given and the money drops to $0. **Observed in the emulator.** | File 895 `HasEnoughMoneyImmediate 0x800C, 300` @228, `SubMoneyImmediate 10000` @313/@537/@589 | D-1545 |
| 12 | Cosmetic | Goldenrod fortune teller: the "love fortune" choice without $10000 ends without `TouchscreenMenuShow`, so the bottom-screen menu stays hidden; walking and X still work. **Observed in the emulator.** | File 895 `TouchscreenMenuHide` @139, L323 → L484 | D-1546 |
| 13 | **Crash** | Entering Goldenrod City with both hide flags 439 (townsfolk) and 441 (Team Rocket takeover NPCs) clear needs 33 overworld sprite graphics; the field's table holds 32, the 33rd write goes through NULL to the IRQ vectors and the game crashes. Either group alone fits. Scripts that change only one of the pair: file 822 @2482 (first Hall of Fame clears 439), file 34 @1195 and file 29 @3194/@3407 (clear 441). **Observed in the emulator** (both ROMs, all 8 flag combinations). | Events 73 (49 objects, 34 sprites); arm9 0x02025E38 / 0x02026104; ov1 0x021F9660 | D-1547 |
| 14 | **Freeze** | Rock Tunnel hide-and-seek: losing to the corner kid (`TrainerBattle 606 0 0 0`, a loss not allowed) doesn't white out; the script goes on to the "Pikachu" kid's NPCMsg 46 (L3782) without the field being restored, the screen stays black and the CPU runs into heap memory. **Observed in the emulator** (both ROMs; controls: `606 0 1 0` returns to the field, `WhiteOut` after it to the Pokémon Center). The audit's lock detector couldn't see it: it is the battle's no-loss setting, not a lock. | File 129 @2879, @2897 → L3782; `emu_harness.py guide0107 --case corner_kid` | D-1548 (D-1395) |
| 15 | **Freeze** | Pokémon Tower Magcargo: a loss jumps back to L2519 (`TouchscreenMenuShow`, `PlayCry`, `WildBattle 219`) with the field not restored; `TouchscreenMenuShow` never returns, the screen stays black. **Observed in the emulator** (both ROMs). Same mechanism as 14. | File 17 @2529, @2546 → L2519; `emu_harness.py guide0813 --case magcargo` | D-1560 |
| 16 | **Freeze** | Department Store 6F blind man: `TrainerBattle 777 778 0 0` with no party-size check; with one Pokémon a broken second ally appears and the game hangs at FIGHT. **Observed in the emulator** (both ROMs; a six-Pokémon control plays the turn). | File 901 @3087; `emu_harness.py guide0813 --case white_flute` | D-1559 |

### Checked and found OK

- **Menus.** All 971 cancellable menus handle the B result (`0xFFFE`) and release the player. The seven B-paths that end locked are vanilla std code (mart menu in file 3, Pokédex evaluation in file 148).
- **`End` while locked.** Except for finding 1, every such case is a vanilla-style unreachable default after a compare chain (e.g. an elevator floor that can't happen), a whiteout, or a scene change (`ScrCmd_819` at the Sinjoh Mystri Stage).
- **Gender and partner branches** (29 branch points).
  - Branches with unequal effects are gender-exclusive side content: female-only romance and partner events (flag 1645 in files 109/110/758/923; flag 1081 in file 172), the male-only choice of the rude answer to Erika (file 791: it only switches which Celadon objects appear, and the plot continues), and the live-in partner in the player's house (file 842).
  - Trainer ids differ by gender or partner as expected (28/29, 131/169, 340/341).
  - No story var or flag is set on only one side of a main-story branch.
- **Starter branches** (files 110, 816, 847): only the rival's trainer id changes (264/268/272, 489/490/491, 495/496/497). In file 816, all three starter paths share the same post-battle tail (L749); the tool reported a difference only because of how it splits the paths.
- **Key items.** Every key item that a script checks or takes is given somewhere.
  - The only items never given by a script are shop, berry-tree or field items: Repeat/Premier Ball, Lemonade, Escape Rope, Repel, Bubble/Snow Mail, the Yache/Haban/Colbur berries (tutor payments) and TM74.
  - The S.S. Ticket is only a branch in the Hall of Fame script.
  - The Suite Key is given once and taken twice, but `TakeItem` of a missing item is harmless.
  - HM08 needs the Town Map from Mt. Mortar (file 962 @4442), which is available there.
- **HMs and badges.** The hack keeps the vanilla field-move badge slots: Flash 0, Cut 1, Strength 2, Surf 3, Fly 4, Whirlpool 6, Waterfall 7, Rock Climb 15. The Kanto gyms give 0–7 (Pewter 0 … Viridian 7) and the Johto gyms give 8–15 (Dragon's Den 15).
  - HMs come from: HM01 on the S.S. Anne, HM02 in Saffron, HM03 and HM04 in Fuchsia, HM05 in Olivine, HM06 in Pewter, HM07 in Celadon or New Bark (plus an item ball), HM08 in Mt. Mortar.
  - The Viridian Gym has an unused script 1 that would give badge 15. No event calls it; the real Giovanni scene (coord trigger → script 8) gives badge 7.
- **Warps.** From the start house, 461 of 540 zones are reachable.
  - The only zone with no way back to the start is the Safari Zone exterior, whose exit is script-driven as in vanilla.
  - One-way warps are elevators or script-returned areas.
  - The unreachable zones are unused vanilla leftovers or hack-sealed areas: Dark Cave Route 31 side, the Route 39 barn, the Fuchsia warden's house, and others.
- **Other checks.**
  - Every trainer id used by a script exists (1,024 trainers).
  - Every std id and local script id on a reachable map resolves.
  - Every script var is in range (0x4000–0x416F, 0x8000–0x800F).
  - Flags 0xB60–0xB63 (the Crystal Onix and others) are inside the hack's expanded 3,232-flag array.
  - Species 2143 in `WildBattle` (file 24, Island Cave) is the Crystal Onix form, with a level given as `0xFF28`. That is intentional.
- **Coord triggers and scenes.** No coord trigger blocks forever.
  - The hack-only "always" triggers use var 0 and check conditions inside. The Violet City trigger on 0x4074 runs an empty script.
  - Unreachable scene values (e.g. `VAR_SCENE_ELMS_LAB` 8, `VAR_UNK_4116` 1) are unused vanilla scenes.
  - The Route 24 Rocket trigger (0x4087 == 1) can't fire; it is a leftover, and the hack's Route 24 flow uses other scripts.

## Later gameplay finding: evolution moves (2026-10-07, D-1602)

Rare Candy evolutions skip Crobat's Cross Poison, Charizard's Air Slash and Gyarados's Bite in both the untouched Chinese v4.0.3 and the English WIP, even with three empty move slots. The evolution learning routine accepts only entries matching the current level, so it ignores their level-0 entries. A delayed Charizard evolution at Lv39 correctly learns Scary Face in both ROMs, confirming the distinction. This is a move-learning defect, not a softlock. See [reproduction and binary evidence](evolution_moves_investigation.md). Preserve the original behavior under D-1002/D-1337.

## Limits

- Story order is estimated: `play_order.json` ranks maps, not script states, so an "item needed earlier" hit only flags revisit quests (for example, Cerulean asks for the Slowpoketail given later in Vermilion).
- Map tiles weren't parsed, so the audit can't tell whether a Cut tree, boulder or water tile blocks a path before its HM. It only checked that each HM and its badge are obtainable.
- Flags set by engine code (trainer flags after battles, system flags, the Alph puzzle flags) are treated as settable.
- Vars written by commands other than `SetVar`/`AddVar`/`CopyVar` (e.g. native field code) may make some "never set" scene values reachable. Those were only reported after a manual check.
- Nothing was confirmed in an emulator: every candidate needs hours of play to reach. See the "Softlock checks" section in `ingame_checklist.md`.

## Rocket HQ runtime freeze (2026-10-08, D-2043)

A player's corrected rc5 battery save reproduces a freeze in melonDS 1.1 at map 247 (17,4), before the camera ambush. Released English rc5, English WIP and untouched Chinese v4.0.3 share an ARM9 data-abort signature at `02024696`. DeSmuME passes this position in Chinese and English WIP. Preserve under D-1337; the exact model/texture asset remains unconfirmed. See [reproduction, ROM/save identities and CPU evidence](rocket_hq_freeze_repro_20261008.md).
