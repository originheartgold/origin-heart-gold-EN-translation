# Dungeons, Battle Tower and game-wide events

[← Guide index](README.md)

**Quests on this page:**

- [Mt. Moon Square: the Clefairy dance (Monday nights)](#mt-moon-square-the-clefairy-dance-monday-nights)
- [Ruins of Alph: the four stone panels and the chamber walls (continues Cherrygrove City to Azalea Town's Ruins of Alph entries)](#ruins-of-alph-the-four-stone-panels-and-the-chamber-walls-continues-cherrygrove-city-to-azalea-towns-ruins-of-alph-entries)
- [Forest of Time: the maze of clearings (continues Ilex Forest and Goldenrod City's Forest of Time entries)](#forest-of-time-the-maze-of-clearings-continues-ilex-forest-and-goldenrod-citys-forest-of-time-entries)
- [Lake of Rage: when the "calm day" happens (continues Lake of Rage, Blackthorn City and beyond's lake trio and calm-day visitors)](#lake-of-rage-when-the-calm-day-happens-continues-lake-of-rage-blackthorn-city-and-beyonds-lake-trio-and-calm-day-visitors)
- [Field moves: which Badge each one needs](#field-moves-which-badge-each-one-needs)
- [Small extras](#small-extras)

## Mt. Moon Square: the Clefairy dance (Monday nights)

**Where:** the small cave entrance between Mt. Moon and Mt. Moon Square.

**Who gets it / when:** every week, on **Monday from 8:00 p.m. to 11:59 p.m.** or **Tuesday from midnight to 3:59 a.m.**, by the DS clock.

**How it works:**
1. At that time, the doorway from the entrance into the Square takes you to a copy of the Square where six Clefairy dance around a rock. The game picks the doorway's destination when you enter the entrance cave, so if 8 p.m. passes while you're standing in it, go out and back in.
2. Walk in and head west, past the "Closed" sign. The scene plays when you reach the far west side of the area, about ten steps west and a few steps south of that sign.
3. When the dance ends, a **Moon Stone** appears where they danced, a few steps north-east of where you stand. Pick it up **before you leave**: if you go out and come back, the stone is gone and the doorway leads to the normal Square for the rest of that day.

**Reward:** Moon Stone.

**Notes:** once you've seen the dance, the doorway leads to the normal Square again until the day changes. The dance and a new Moon Stone come back **every Monday night**. Because the day changes at midnight, the dance can also play once more between midnight and 3:59 a.m. on Tuesday, even if you saw it on Monday evening (tested in an emulator: with the dance marked as seen at 10 p.m. on Monday the doorway leads to the normal Square, and once the clock passes midnight it leads to the dance again). The rest of the time the Square is the normal map with Asher's gang ([Pewter City to Vermilion City](02-pewter-to-vermilion.md)). This is the original game's event, kept by the hack.

*Source:* script file 8 (map 448; `GetWeekday` = 1 with time period 3, or = 2 with period 4, moves the Square warps to map 513 unless flag 2741 is set), file 10 (map 513; script 1 sets flag 664 on every entry and hides the Clefairy outside those times, script 3 dance triggered at ≈8,16, L309 clears flag 664 to show the Moon Stone ball at ≈11,12, L775 sets 2741; script 4 gives item 81). Time periods: arm9 hour table 0x020F2A94 (period 3 = 20:00–23:59, 4 = 00:00–03:59). Flag 2741 is a daily flag: arm9 0x0203FBAC clears flags 2720–2911 on each new day.

## Ruins of Alph: the four stone panels and the chamber walls (continues Cherrygrove City to Azalea Town's Ruins of Alph entries)

**Where:** the four small chambers of the Ruins of Alph. Each has a stone panel in the middle of the room and a carved back wall behind it.

| Chamber | Panel | What opens the back wall |
|---|---|---|
| Kabuto chamber (north-east, the one with the researcher) | Kabuto | standing right in front of the wall, facing it, and using an **Escape Rope** from the Bag |
| Aerodactyl chamber (south-east) | Aerodactyl | standing right in front of the wall, facing it, and using **Flash** from the party menu |
| Omanyte chamber (south-west) | Omanyte | standing right in front of the wall, facing it, and using a **Water Stone** from the Bag |
| Ho-Oh chamber (north-west) | Ho-Oh | examining the wall with **Ho-Oh in your party** |

**How it works:**
1. **Panels:** examine the panel and rotate and slide the pieces until the picture is complete. When it's solved, the floor gives way and you drop into the **Underground Hall**. From then on, wild Unown appear in the Underground Hall. Nothing else is given.
2. **Walls:** examining a wall only shows a short line of Unown writing on a stone tablet. It gives no hint in words (tested in an emulator, all four chambers). Do what the table says and the wall crumbles. Tested in an emulator: the Escape Rope, Flash and the Water Stone each opened their wall when used while facing it, and you stay in the chamber (the Escape Rope doesn't take you out). A Water Stone used two steps back from the wall did nothing.
3. **Behind every wall** is the same place: the hall of the dream world from the Molly chapter ([Cherrygrove City to Azalea Town](08-cherrygrove-to-azalea.md)). This is the way back in for the post-game **Entei** rematch in [Cherrygrove City to Azalea Town](08-cherrygrove-to-azalea.md)'s "Ruins of Alph: small extras". Any of the four walls works, not just the Kabuto one. Whichever wall you came through, the hall's exit door at the bottom always leads back to the **Kabuto chamber**.
4. **Unown Report:** the researcher at the Research Center never writes any notes in your Unown Report. He only ever says that the ruins are "about 1,500 years old" (see [the known issue](known-issues.md#unown-report-notes)).

**Reward:** Unown in the ruins; access to the dream-world hall.

**Notes:** at the end of the Molly chapter the Kabuto wall closes again, so you have to reopen it. In the original game, each wall led to a small room with Unown writing. Those rooms are still in the game data, but nothing leads to them now. An earlier version of this guide said Island Forest on Six Island has no wild Pokémon until you've solved a panel; that's not so (see [the known issue](known-issues.md#island-forest-wild-pokémon)).

*Source:* script files 39 (Kabuto: `AlphPuzzle 0`, flag 2423; wall script 3 sets 539; script 4 researcher), 41 (Aerodactyl: `AlphPuzzle 1`, flag 2424; script 3 field-move message bank 209#28, sets 541), 43 (Omanyte: `AlphPuzzle 2`, flag 2425; script 3 sets 543), 45 (Ho-Oh: `AlphPuzzle 3`, flag 2426; script 2 `PlayerHasSpecies 250`, sets 545), chamber events (panel at 6,6; wall warp (6,2) → map 324 warp 0 in all four; map 324 door (6,17) → map 312), file 38 (Research Center, L804–L2321: notes need var 0x40EC ≥ 1, which nothing reachable raises, D-1427), Island Forest encounter gate (ov2 0x02248420, D-1430), file 51 L4269 (clears 539, at the end of the Molly chapter after the Unown Report). Walls: object 0 at 6,2, script 2 `OpenAlphHiddenRoom` (emulator, CN all four chambers and EN Kabuto/Aerodactyl, 2026-10-06, work/build/harness/guide-review-20261006/ch13/walls_*: an Unown-letter tablet, no a027 string read; the riddle lines 72#2, 73#0, 75#0, 76#0 are never shown, see D-0955). Wall items/move (emulator, CN and EN, 2026-10-06, work/build/harness/guide-review-20261006/pass2-C/walls_{rope,flash,stone,stone_away}_*: standing at 6,3 facing the wall, Escape Rope (item 78) from the Bag sets 539, Flash from the party menu sets 541, Water Stone (item 84) from the Bag sets 543, the player stays on the map; Water Stone at 6,5 leaves 543 clear).

## Forest of Time: the maze of clearings (continues Ilex Forest and Goldenrod City's Forest of Time entries)

**Where:** the Forest of Time, between its entrance clearing (where the ranger and Celebi are) and the upper forest with the shrine.

**Who gets it / when:** every time you go north through the forest: in the Sammy chapter ([Ilex Forest and Goldenrod City](09-ilex-goldenrod.md), "Sammy and the injured Celebi", step 5) and for the shrine (Shaymin, Celebi).

**How it works:** each clearing has six exits: bottom-middle, bottom-left, top-left, top-middle, top-right and bottom-right. Most send you to another clearing. The way through:

| From | Take the exit | You arrive in |
|---|---|---|
| Entrance clearing | **top-middle** | clearing 2 |
| Clearing 2 | **top-middle** | clearing 3 |
| Clearing 3 | **top-right** | clearing 4 |
| Clearing 4 | **top-left** | clearing 5 |
| Clearing 5 | **top-middle** | the upper forest (shrine path) |

**Notes:**
- You arrive standing on an exit. Step off it before you choose the next one.
- The top-left and top-right exits take you only when you walk sideways into them (left or right). Walking up onto them does nothing.
- Wrong exits either loop you between clearings or drop you back at the entrance clearing.
- While the ranger has sent you for the medicine in the Sammy chapter, the last exit sends you back to the entrance clearing instead. The same happens from the moment Bugsy gives you the Honey for his bug hunt in Ilex Forest, and it goes on after the hunt until the old ranger in Ilex Forest starts the Sammy chapter. There's nothing for you at the shrine before that chapter anyway.
- During the Sammy chapter, Sammy, Celebi and the ranger stand on the entrance clearing's top-middle exit and block it until their scene moves on.
- Don't enter the Forest of Time in the middle of Bugsy's bug hunt: the two share their progress, and the wrong scene may play (see [the known issue](known-issues.md#forest-of-time-during-the-bug-hunt)).
- Tested in an emulator: the route above leads to the upper forest once the Sammy chapter is over. During the medicine errand, and after the bug hunt has ended, the last exit puts you back at the bottom of the entrance clearing.

*Source:* script file 106 (map 462; coord triggers at 49,13 on var 0x4099 = 2 or 4 → back to the entrance at 17,82; 49,50 on 0x4099 = 4), events bank 416 (36 warps with their destination indexes; route 327 w3 → 462 w6 → w9 → w30 → w34 → w19 → w20 → w17 → w15 → 327 w6), map 327 events bank 298 (warp 3 at 17,77 → map 462 warp 6; warp 6 at 15,39 ← map 462 warp 15), file 52 L2875 (sets 0x4099 = 4 when the ranger asks for the medicine), file 92 L6516 (Bugsy hands over the Honey: 0x4099 = 2; the hunt then sets 3/4/5 at L10693/L10735/L2209/L2398), L5713 (hunt reward: back to 2), L5372 (ranger's Sammy scene, script 16 on var 0x40A2 = 17: 0x4099 = 3), D-1429. Emulator (CN and EN, 2026-10-06): the route walked with 0x4099 = 6, 4 and 2, work/build/harness/guide-review-20261006/ch13/maze_*.

## Lake of Rage: when the "calm day" happens (continues Lake of Rage, Blackthorn City and beyond's lake trio and calm-day visitors)

**Where:** Lake of Rage.

**Who gets it / when:** on **Wednesdays**, once you've cleared the Team Rocket HQ in Mahogany Town (the scene where Green or Red goes home at the end of the HQ) **and** seen the Petrel scene at the lake guardian's house ([Lake of Rage, Blackthorn City and beyond](12-lake-of-rage-to-sinjoh.md)).

**How it works:**
1. The game checks when you **enter the Lake of Rage or Route 43** from another map. If it's Wednesday (by the DS clock) and the Rocket HQ is done, it marks the day as calm. On any other day it clears the mark.
2. On a calm day, once you've seen the Petrel scene, the lake shows Fisherman Carson (Red Scale), Wesley (the Wednesday sibling) and an item on the ground, and the lake trio's first encounter starts (Uxie, Mesprit and Azelf: see that entry in [Lake of Rage, Blackthorn City and beyond](12-lake-of-rage-to-sinjoh.md)). Before the Petrel scene none of them appear, even on a calm Wednesday.
3. The item on the ground is a **PP Max** if you pick it up between 7:00 p.m. and 6:59 a.m. by the DS clock, and a **Heart Scale** the rest of the day. It comes back on later calm Wednesdays, as long as you've visited the lake on a day other than Wednesday in between.

**Notes:** if you're already at the lake when the day changes, leave and come back so the check runs again. Prof. Hale's line that "the downpour over the Lake of Rage stops for one day every Wednesday" is accurate. Tested in an emulator: on a Wednesday after the Rocket HQ and the Petrel scene, Carson, Wesley, the item and the trio appear when you enter the lake. Before the Petrel scene, or on a Thursday, they don't. Entering Route 43 on a Wednesday also marks the day, entering on a Thursday clears the mark, and without the Rocket HQ no Wednesday is calm. The item's two time windows were not tested.

*Source:* emulator (Chinese ROM; the Wednesday case also on the English build; 2026-10-06, work/build/harness/guide-review-20261006/ch13/calm_* and calm2_*: var 0x4037 and hide flags 508/510/586 after a warp into map 88 or 45). Game code (arm9 function at 0x0203A580: needs flag 202, map 88 or 45, weekday 3; it then writes var 0x4037 = 0xF229 through the event-slot setter at 0x02065EB8, table at 0x020FB2BC), file 90 L2861 (Rocket HQ B2F sets flag 202), file 934 script 1 (L126: 0x40B2 < 5 hides flags 508/510/586–588; L1749: 0x4037 = 0xF229 → L5595 clears 508 (Carson, Wesley), 510 (item, unless flag 327) and 586 (trio, unless 649); otherwise clears 327), file 935 L551 (Petrel scene sets 0x40B2 = 5), file 934 script 27 (item-ball object ≈539,73; `ScrCmd_522` hour 19–23 or 0–6 → item 53 PP Max, else 93 Heart Scale), bank 71#59 (Prof. Hale's line).

## Field moves: which Badge each one needs

**Where:** anywhere you meet an obstacle, and in the party menu. The hack changed the original Badge requirements to its own Badge order.

**How it works:** examining an obstacle offers the move only if you have the Badge. Without it you only get the description ("This tree looks like it can be cut down!"); at the water nothing happens at all. Moves you pick from a Pokémon's party menu (Fly, Flash and the rest) check the same Badges.

| Move | Badge needed |
|---|---|
| Rock Smash | Boulder Badge (Brock) |
| [Cut](/moves/cut/) | Cascade Badge (Misty) |
| Strength | Thunder Badge (Lt. Surge) |
| [Surf](/moves/surf/) | Rainbow Badge (Erika) |
| [Fly](/moves/fly/) | Marsh Badge (Sabrina) |
| Whirlpool | Volcano Badge (Blaine) |
| Waterfall | Earth Badge (Giovanni) |
| Rock Climb | Rising Badge (Clair) |
| Flash, Headbutt | no Badge |

**Notes:**
- **You don't need a Pokémon that knows the move** when you examine an obstacle or the water. With the right Badge, the game uses your first healthy Pokémon, whatever its moves. The party menu still only shows moves a Pokémon knows, so Fly and Flash do need a Pokémon that knows them. HM-free obstacle use is an intended v4 feature. The precise behavior above was checked in the game code; every obstacle and party-menu path has not been replayed (see [the behavior note](known-issues.md#field-moves-without-the-move)).
- Surf and Rock Climb can't be used while someone is walking with you.
- Tested in an emulator: at the Lake of Rage shore the Surf question appears with the Rainbow Badge as your only Badge, and nothing happens with no Badges.

*Source:* emulator (Chinese ROM, 2026-10-06, work/build/harness/guide-review-20261006/ch13/surf_*: badge 3 only → bank 209#14; no badges → no message). Script file 146 (`CheckBadge` 1 Cut L105, 0 Rock Smash L674, 2 Strength L1327, 15 Rock Climb L1873, 7 Waterfall L2402, 6 Whirlpool L2559; Surf script 5 and Headbutt script 15 have none). Badge ids from the `GiveBadge` scenes: 0 Boulder (file 750), 1 Cascade (758), 2 Thunder (776), 3 Rainbow (853), 4 Marsh (826), 6 Volcano (15), 7 Earth (741 L2863), 15 Rising (112). Party-menu checks: arm9 field-move table 0x020FB5D0 (Cut 1, Fly 4, Surf 3, Strength 2, Rock Smash 0, Waterfall 7, Rock Climb 15, Whirlpool 6; Flash check 0x0206773C has no Badge test). Water prompt: ov1 0x021E65E4 (Badge 3 only). `GetPartySlotWithMove` (cmd 141, 0x0204C8D4) ignores the move and returns the first healthy party slot (ov1 0x02205200 → arm9 0x02053500), D-1428.

## Small extras

- **Olivine Lighthouse 5F:** a photographer stands in the south-west corner on **Wednesdays and Saturdays**. He takes a photo of you for your photo album. He's away from the end of Jasmine's Gym battle until you start the Amphy medicine errand. Tested in an emulator: there on a Wednesday and a Saturday, gone on a Thursday and during that gap.
- **Olivine Lighthouse 4F:** the gap in the east wall, a few steps east of the stairs that come up from 3F on the east side, drops you onto the outside ledge.
- **Ice Path B1F:** the four holes in the middle of the floor, between the stairs, drop you to B3F.
- **Tohjo Falls:** an item ball a few steps west of the entrance to the hidden room holds a **Dawn Stone**.
- **Cerulean Cave B1F:** an item ball in the south-east corner, about 20 steps south of the east-side passage, holds a **Splash Plate**.

*Source:* Lighthouse 5F: script file 65 (`CameronPhoto`; on-load script 2: flag 477 clear → hidden, else weekday 3 or 6 clears his hide flag 638), photographer ≈2,14. Flag 477 is set at new game (file 149 @82) and on Route 39 (file 249 @4122), cleared at the end of Jasmine's Gym battle (file 909 @16062) and during the Lighthouse scene (file 66 @1175/@1396), set again at @1848 and when the medicine errand starts (@2515). Emulator (CN, 2026-10-06, work/build/harness/guide-review-20261006/ch13/photo_cn: flag 638 after entering 5F; Wed/Sat with 477 set → shown, Thu → hidden, Wed with 477 clear → hidden). Lighthouse 4F: file 64 (coord script 1 at ≈16,9, the opening in the east wall; `Warp` to map 221) → file 63; 3F stairs at ≈10,7. The Trainer at ≈15,8 (object 1) has hide flag 477, so he isn't always there. Ice Path B1F: file 100, holes at ≈11,10, 10,18, 18,7, 19,19. Tohjo Falls: file 113, ball at ≈23,12. Cerulean Cave B1F: file 11, ball at ≈57,39.

See [Known issues](known-issues.md#dungeons-battle-tower-and-game-wide-events) for suspected hack bugs in this area.
