# Emulator test harness (`work/tools/emu_harness.py`)

Some questions about the hack can only be settled in game. This harness answers them without a playthrough:
it edits the battery save (teleport, flags), pins the game clock, creates Pokémon with the hack's own
generator, walks, logs every wild Pokémon the game builds, flees, and takes screenshots. It runs the
untouched Chinese ROM by default (behaviour reference, D-1002) and works unchanged on our English build.

Proof of concept: D-1487 (wild Unown are always A) was **observed in the emulator**, see below.

## Running it

Use the project venv (py-desmume 0.0.9, capstone, ndspy, pillow). ROMs, saves, screenshots and reports
stay out of git: the defaults point at `work/rom/`, `work/build/memcheck/*.sav` and `work/build/harness/`
of the main checkout (also when run from an agent worktree).

    .venv/bin/python work/tools/emu_harness.py unown [--count 20] [--clock 2026-10-09T12:00:00]
    .venv/bin/python work/tools/emu_harness.py wild --map 109 --x 16 --y 14 --clock 2026-10-09T12:00:00
    .venv/bin/python work/tools/emu_harness.py info [--sav S] [--clock ISO]
    .venv/bin/python work/tools/emu_harness.py palpark            # D-1484: record per weekday
    .venv/bin/python work/tools/emu_harness.py arceus             # D-1501: 16 Plates through the bag
    .venv/bin/python work/tools/emu_harness.py evolve --species 548 --level 10 --item 241 --stone 80 --clock 2026-10-09T12:00:00
    .venv/bin/python work/tools/emu_harness.py screens [--only options,ev,dex,battle]   # CN|EN pairs
    python3 -m unittest discover -s work/tools -p test_emu_harness.py      # pure parts, no ROM needed

A boot plus teleport takes about 15 s; 20 Unown encounters take about 2–3 minutes (headless, ~300 fps).
`--state FILE` writes a DeSmuME savestate right after the teleport; `Harness(rom, savestate=FILE)` then
starts there in under a second.

## Library API

```python
from emu_harness import Harness, SaveFile, WildLog
sf = SaveFile("work/build/memcheck/full_bag_6mons.sav")   # newest general block, CRC fixed on write
sf.place_player(315, 17, 24)        # map, x, y: Location + saved player/follower objects, old NPCs dropped
sf.set_flag(2423); sf.set_var(0x4000, 1)
sf.write(tmp)                        # never next to the original
with Harness(rom, tmp, out=dir) as h:          # rom: Chinese (default) or English build
    h.set_clock(datetime(2026, 10, 9, 12))     # pinned: date, weekday and time
    h.boot_to_menu(); h.continue_game()        # title -> Continue -> field; checks code signatures
    h.location(); h.get_flag(n); h.set_flag(n); h.get_var(v); h.set_var(v, x)   # live, in RAM
    h.party()                                  # decrypted: pid, species, item, form, level, checksum_ok
    h.generate_pokemon(548, level=30, item=241, form=0)   # the hack's SELECT+X generator -> party slot 6
    h.edit_party_mon(0, item=241)              # direct struct edit, re-encrypted, checksum fixed
    log = WildLog(h)                           # hooks the wild finalizer; log.rows
    h.walk("LEFT", 3); h.press("A"); h.touch(x, y); h.hold(...); h.release(...)
    h.flee(); h.in_field(); h.run_until(cond, max_frames)
    h.on_exec(addr, fn); h.on_frame(fn); h.read/u8/u16/u32/write/w8/w16/w32
    h.screenshot("name"); h.save_state(p); h.load_state(p)
```

## How each part works, and why

### Teleport: battery save, not RAM

- **RAM edits at the Continue menu don't work**: choosing Continue reloads the save from flash, so a
  Location written into the in-RAM save data is overwritten (tried; the map reverted to 500).
- **Location alone is not enough**: Continue restores the player and NPCs from the saved map objects. With
  only the Location changed, the game loaded map 315 but put the player at the old coordinates (4, 6) with
  the Poké Mart's NPCs. `SaveFile.place_player` therefore also moves the player (id 0xFF) and follower
  (id 0xFD) objects and clears the old map's NPC objects. The new map's own objects (Unown statues) still
  appear. Map scripts that run on a normal map entry don't run (the game thinks it was saved there).
- A runtime warp (hook the hack's Warp script command, or rewrite a warp event in RAM and step on it) would
  give a fully normal map entry. Not needed for the POC, not built.

### Battery save layout

From the local save-editor research (`~/Developer/poke-save-editor/work/save-editor/research-layout.md`),
rechecked here: two mirrors at 0 and 0x40000; general block 0xF7CC bytes incl. a 16-byte footer
{u32 counter, u32 size, u32 magic 0x20060623, u16 block id, u16 CRC}; CRC = `binascii.crc_hqx(payload, 0xFFFF)`.
The game picks the mirror with the higher counter; the harness edits that one and recomputes its CRC.

Array offsets inside the general block equal the in-RAM offsets: `SaveArray_Get` (arm9 0x02027740) returns
`save + 0x10 + table[id].offset`, table at `save + 0x2E01C`, 16-byte rows. Read from RAM and checked at
every boot (`ARRAY_OFFSETS`):

| id | offset | content | how found |
|---|---|---|---|
| 2 | 0x90 | party: +4 count, +8 six × 236-byte Pokémon | wrapper 0x0207365C, memcheck.py |
| 4 | 0xEAC | vars (u16, id − 0x4000) and flags at +0x2E0 (bit flag%8 of byte flag/8) | flag getter 0x0204F8E4 |
| 5 | 0x1324 | LocalFieldData: +0 current Location {s32 map, warp, x, y, dir}; +0x14, +0x28, +0x3C, +0x50 more Locations | wrapper 0x0203AEBC + accessors 0x0203AE50–0x0203AEB8; FieldSystem+0x20 points here |
| 10 | 0x2480 | saved map objects, 64 × 0x50: +8 id, +0x10 map, +0x12 sprite, +0x20 s16 initX, initY, initZ, curX, curY, curZ | found by searching the save for the mart NPCs' event coordinates |

Other RAM: `0x021D11B4` holds the SaveData pointer (found by scanning RAM for the pointer that
`SaveArray_Get` receives); FieldSystem was at 0x022A0EFC in one session (+0x0C save, +0x20 Location*), not
used by the harness.

### Clock

DeSmuME uses the host clock and py-desmume has no RTC setting. The game caches the RTC in the GF_RTC work
area at `0x021CFE8C` (+0x10 RTCDate {u32 year−2000, month, day, weekday 0=Sunday}, +0x20 RTCTime
{hour, minute, second}); an async read refreshes it about every 10 frames through the callback at
0x02014280. `set_clock` writes the wanted date/time and re-writes it from an exec hook at the end of that
callback (0x020142B2), so every reader (`GF_RTC_CopyDate` 0x0201436C, `CopyTime` 0x02014338, the Pal Park
weekday getter 0x0203A7B0) sees the pinned value. Time doesn't advance while pinned. Found by searching RAM
for the host date, then following code literals that point at it. Not checked: code that reads the RTC
hardware directly instead of the cache.

### Wild encounters

`WildLog` hooks the overlay-2 wild finalizer (ov2 0x022489DC, r2 = the new Pokémon): entry, the Unown
letter write (0x02248A40, r2 = &letter), the first instruction after it (0x02248A44, form re-read), the
write-back (0x02248AD4, sp+8 = saved form) and the end (0x02248AFE, final Pokémon decrypted). The
Pokémon is decrypted in Python (Gen 4 layout: PID, checksum, 4 shuffled 32-byte blocks, LCG
0x41C64E6D/0x6073; species = block A +0, item = block A +2, form = block B +0x18 >> 3; party extension
keyed by the PID, level at +4). **The decoder is checked in game**: right after the hack writes the letter
the decoded form equals that letter for every Unown (`decoder_check`).

Encounters come from walking back and forth (`--walk`, `--span`); nothing about rates is changed. Battles
are left by touching RUN (128, 178) until overlay 2 is back (`in_field()` compares ov2 code bytes; battles
unload it). Double wild battles happen in the hack (two Unown at once) and are handled.

### Pokémon creation: the hack's generator

The hack ships the debug "create Pokémon" menu (field: hold SELECT, press X; FAQ). Pages (L/R): species,
level, exp, OT ID, PID, gender, nature / status, friendship, Pokérus, egg, fateful, nickname / moves,
held item, ability / IVs and EVs / contest stats / met level, ball, country, **form number (型号No)** /
met locations and dates. START adds the Pokémon to the party, or the PC when the party is full.

The menu keeps one u32 per row in a heap array. `generate_pokemon` opens the menu, finds the array by its
initial Bulbasaur values (1, 1, 0, …, moves Tackle 33 / Growl 45 at rows 7–8), writes species (row 0),
item (11) and form (47), and sets the level through the menu (A, UP, A on row 1) because only a level
edited in the menu recomputes the experience (a level written directly gives a level-1 Pokémon). The
ability is recomputed by the menu too. Checked in game: Petilil Lv30 holding Black Belt (item 241), and
Unown form 5 (F), both decoded from the party afterwards. The menu reuses the same PID every time.
With `free_slot` (default) the party count is lowered to 5 first so the new Pokémon replaces slot 6.

### Code signatures

Before trusting an address the harness compares code bytes in RAM (`CODE_SIG` for arm9 after boot,
`OV2_SIG` in the field). Both ROMs match. A different build fails loudly instead of logging nonsense.

## Result: D-1487, wild Unown (Chinese ROM, observed)

Save `full_bag_6mons.sav` edited: map 315 (MAP_RUINS_OF_ALPH_UNDERGROUND_HALL, the hall with encounter
record 10: 12 × Unown Lv5, walk rate 15) at (17, 24), flags 2423–2426 set (the encounter gate ov2
0x02248420 needs one of them on maps 315 and 490–492; the letter picker reads which puzzles are solved),
clock pinned to Friday 2026-10-09 12:00.

Three runs on the Chinese ROM: 20 (host clock), 24 and 21 (pinned clock) wild Unown, single and double
battles:

- Letters the game picked, e.g. `OSRZLYAWTBCKTBBMGBYUE` (final run, `work/build/harness/unown_cn_report.json`).
- Form of every finished Unown: `A` (65 of 65).
- With the clock pinned, both runs started with the same letters (`OSRZLYAWTBCK…`): the game seeds its RNG
  from the clock, so pinned runs are reproducible until the inputs diverge.
- Screenshots (`work/build/harness/unown_cn_encounter_*.png`) show A-shaped Unown sprites, e.g. a double
  battle where the game had picked R and Z.
- English WIP build, 9 Unown: picked `MUQEMUSBY`, all A. Same behaviour.

So the hack picks a letter, writes it, then overwrites it with the saved slot form 0. Letters B–Z, !, ?
can't be caught in the wild. D-1487 can be marked as tested in game.

## Results, round 2

### 1. Pal Park weekday table (D-1484): observed

`emu_harness.py palpark` teleports to map 109 once per weekday (clock pinned to 12:00 on 2026-10-04 Sun …
2026-10-10 Sat, one child process per day) and hooks the map-109 return of the encounter-bank getter
(arm9 0x0203A7D6, `pop {r4, pc}` with r0 = record). The getter runs once when the map loads.

| pinned day | Sun | Mon | Tue | Wed | Thu | Fri | Sat |
|---|---|---|---|---|---|---|---|
| record loaded | 141 | 142 | 143 | 144 | 145 | 146 | 147 |

Observed in the Chinese ROM (7 runs, `work/build/harness/palpark_weekdays.json`): record = 142 + weekday − 1,
so Sunday loads 141 (Cerulean Cave's table) and record 148 is never used. D-1484 holds. Friday = 146
(Stunfisk's table).

Encounters per day were not confirmed. The earlier Friday run got 2 encounters in 3000 steps (Makuhita and
Numel, both only in record 146 among 141–148). A second try at (20, 14) got none in 600 steps: the teleport
target is not a grass tile the player can pace on (the screenshot shows the camera over trees). The
player's live position is not read by the harness yet (see limits), so the start tile can't be checked
automatically.

### 2. Arceus Plates (D-1501): observed, the picture and summary are right

`emu_harness.py arceus`: one child builds a savestate with an Arceus Lv50 from the generator in party slot 6;
then one child per Plate puts that Plate first in the Items pocket (RAM), opens the bag by touch, Plate →
Give (带上) → Arceus (the game's own give path, so the party-menu form code at 0x0207ACB8/0x0207ACF0 runs),
reads the stored form, then opens the summary and takes a screenshot. 16 runs, about 90 s in total.

| Plate | Flame | Splash | Zap | Meadow | Icicle | Fist | Toxic | Earth | Sky | Mind | Insect | Stone | Spooky | Draco | Dread | Iron |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stored form | 10 | 11 | 13 | 12 | 15 | 1 | 3 | 4 | 2 | 14 | 6 | 5 | 7 | 16 | 17 | 8 |
| summary type | Fire | Water | Electric | Grass | Ice | Fighting | Poison | Ground | Flying | Psychic | Bug | Rock | Ghost | Dragon | Dark | Steel |

- The stored forms are exactly the values D-1501 predicted (Gen 4 type numbers). **Observed.**
- The summary page shows the Plate's type and a sprite in the Plate's colours for all 16
  (`work/build/harness/arceus/arceus_summary_sheet.png`, `arceus_type_sheet.png`, one full screenshot per
  Plate). **Observed.** So the picture is not wrong: the sprite archive uses the same order as the Plate code.
- What is still mismatched (static, checked again here): the form table maps form *n* to personal entry
  1153 + *n*, and those entries are in the newer order (form 9 Fire, 10 Water, …, 17 Fairy). With a Flame
  Plate (form 10) the game would read the Water entry wherever it uses the form's personal data. All
  Arceus personal entries are alike except their types, so this only matters where the type is read from
  personal data rather than the Plate type getter. Not observed: the in-battle type (needs a battle with
  Arceus in the lead and a type-effectiveness check). D-1501 should be narrowed: the picture and summary
  are correct.

### 3. Petilil + Black Belt by day, then Sun Stone (D-1485): observed

`emu_harness.py evolve --species 548 --level 10 --item 241 --stone 80 --clock 2026-10-09T12:00:00`:
generator Petilil Lv10 holding a Black Belt, clock pinned, Rare Candy used through Bag → Medicine → Use
(the game's own level-up and evolution path), then a Sun Stone through Bag → Items → Use.

| run | after Rare Candy | after Sun Stone |
|---|---|---|
| 12:00 (day) | species 548 form 1, Lv11, Black Belt consumed; the scene says "Petilil evolved into Petilil" | species 549 form 1: summary shows 裙儿小姐 (Lilligant), Grass/Fighting |
| 12:00, no stone | 548 form 1; summary: Petilil, Grass, no item | – |
| 22:00 (control) | 548 form 0, Lv11, still holding the Black Belt (no evolution) | – |

All observed in the Chinese ROM (screenshots `work/build/harness/evolve/petilil_*`). D-1485 holds: by day the
Black Belt evolution gives a form-1 Petilil (looks and types like a normal Petilil), and only the Sun Stone
then makes the Grass/Fighting Lilligant (Hisuian). The summary sprite of species 549 form 1 was not compared
with the official Hisuian artwork.

### 4. Rockruff's evolution form by time (D-1486): observed, daytime gave Midday every time

`emu_harness.py evolve --species 744 --level 24 --clock <time>`: generator Rockruff, Rare Candy through the
bag. A hook on the form write in the evolution code (0x02074B0E, `SetMonData(mon, FORM, sp+0xC)`) logs the
byte the game writes. The hack's time periods (table 0x020F2A94): 4–9 morning, 10–16 day, 17–19 evening,
20–23 night, 0–3 late night; evening writes 2, night and late night write 1, other periods write the
untouched stack byte.

| pinned time | 06:00 | 12:00 | 15:00 | 18:00 | 22:00 | 02:00 |
|---|---|---|---|---|---|---|
| form written / stored | 0 | 0 | 0 | 2 (Dusk) | 1 (Midnight) | 1 (Midnight) |

Six more daytime runs with other inputs (12:00 Lv30, 15:00 Lv50, 13:30 Lv40, 16:59 Lv24; saves
`full_bag_6mons`, `trainer`, `market`, `protographer`; party slot 2 or 6): form 0 every time. So 9 of 9
morning/day evolutions gave Midday Form (summary sprites: `work/build/harness/evolve/rockruff_sheet.png`
shows Midday, Dusk, Midnight). **Observed.** The stack byte is not written by the evolution code (static,
still true), but on the Rare Candy path it was always 0. Not tested: evolution after a battle (a different
caller, so a different stack history), which is where a non-zero byte could still appear.

### 1b. Live position, targeted walking, scripted warps, Pal Park encounters (round 3)

- **Live position** (observed): LocalFieldData's current Location (save array 5, +0 map, +8 x, +0xC y) is
  updated on every step, so `h.position()` reads it. Found by diffing RAM while walking (x 17 → 15 → 12).
  The live player object also holds init/prev/current tile coordinates and FX32 positions (0x22A2D40 in one
  session; not used). The Location's direction field is not updated while walking (facing is not read).
- **Map data** (`MapGrid`): map header table 0x020F37C4 (0x18 bytes, +4 matrix id) → matrix a/0/4/1 →
  land data a/0/6/5 (32×32 u16 per chunk after a 0x14 header; low byte behaviour, bit 15 blocked).
  `walk_to(x, y)` walks a BFS path and checks each step against the live position.
- **Why the save teleport failed in Pal Park**: the map is only playable in the hack's Fixed Catch mode.
  With the save teleport the player was frozen and invisible (and without a pinned clock Continue even
  came back in the Poké Mart). The script runner (item 2) now enters the park the way the gate script
  (file 809) does: `SetVar 16565 3`, the day's standing-Pokémon flags (2126/2130 cleared, the other six of
  2124–2131 set; with all eight set the player stays locked), fade, `Warp 109 (24, 46)`, fade in.
  Outdoor saves also store a height (curY 2 on Route 1), which `place_player(height=)` now accepts.
- **Pal Park encounters (observed, Chinese ROM)**: `palpark --days Fri,Sun,Mon --count 8`: clock pinned,
  Ninjask Lv100 from the generator as lead (so RUN always works; with the Lv9 party fleeing failed and the
  lead fainted), scripted entry, pacing on two tall-grass tiles (16, 40)/(17, 40):

| day | record loaded | wild Pokémon seen (species ids) | all in that record? |
|---|---|---|---|
| Fri | 146 | Corphish 341, Meditite 307, Baltoy 343 (and Numel 322 + Torchic 255 in a test run) | yes |
| Sun | 141 | Machoke 67, Kadabra 64 ×3, Golbat 42, Electrode 101, Parasect 47, Alakazam 65 | yes (Cerulean Cave's table) |
| Mon | 142 | Sableye 302, Snivy 495 ×2, Tropius 357 | yes |

  Encounters are slow in the park (3–8 per ~900 steps); battles include double battles. D-1484 is now
  confirmed by real encounters too: Sunday's park really uses Cerulean Cave's table.

### Integrated from the UI hunt agent

- `encode_pokemon(..., moves=, pp=)` / `edit_party_mon(slot, moves=[...])`: block B +0 four u16 move ids,
  +8 four u8 PP (the hunt agent verified them in the summary and in battle; round-trip unit test here).
  Not integrated: writing the ability byte (block A +0x0D) had no effect in battle; the hack computes the
  ability elsewhere (still to find; needed for Zen Mode or hidden-ability tests). Writing moves into the
  generator's rows 7–10 before START does nothing (the menu resets them): set moves after creation.
- Touch coordinates: field touch menu POKéDEX (43, 33), POKéMON (43, 73), BAG (43, 113), POKéGEAR
  (43, 153), trainer card (123, 33), SAVE (123, 73), OPTIONS (123, 113) (the old POKéMON (40, 100) missed);
  Pokégear tabs; battle BAG (36, 165), POKéMON (200, 165), INFO (225, 15; LEFT/RIGHT cycle Pokémon).
- `run_ops` / `emu_harness.py drive`: the hunt agent's op language (keys, waits, touches, screenshots,
  savestates, generator) plus `moves:`, `script:`, `prog:`, `warp:` and `walk:`. Example:
  `drive --lang en gen:25,30 moves:5,85,86,87,98 t43,73/120 s:party_menu`.
- Gotcha reported by the hunt agent: one parallel run booted the unedited location (map 500). Each Harness
  already uses its own temporary directory and battery copy. The same symptom appeared here only for the
  save teleport into Pal Park (Continue came back in the Poké Mart), which is game logic for that map.
  `start_at` raises when a requested teleport did not land, so check the map when you rely on it.

### 5. Screen checks on the English WIP build (Tier 3)

`emu_harness.py screens [--only options,ev,dex,battle]` runs each screen recipe on the Chinese ROM and on
`work/build/origin_hg_v4.0.3_en_wip.nds` (one child process per recipe and ROM, about 2 minutes for all) and
writes CN|EN pairs to `work/build/harness/screens/*_pair.png` (overview: `all_pairs.png`). Recipes are a few
lines each (`h.field_menu("options")`, `h.open_bag()`, `h.mark("name")` …). Whether text fits is judged by
looking at the pairs; the pixel-difference figure in `screens_report.json` is only useful against a
baseline of the same ROM (see the proposal below). All observations below are from these screenshots.

| screen | decision | English result |
|---|---|---|
| Options (X → OPTIONS) | D-0506 | Fits, one tight cell: MUSIC SPEED / BATTLE SCENE / BATTLE STYLE / TITLE SCREEN / BATTLE BG / FRAME and their values all fit. **NORMAL** fills its value cell completely (last letter touches the cell's right edge). What the options do was not tested. |
| EV Allocator (key item 745, Bag → Key Items → Use) | D-0503 | Fits with room: Atk/Def/SpA/SpD/Spe, "EVs left to allocate", the X/Y and SELECT/START help lines. The label column is about 50 px wide, so full names such as "Attack" or "Sp. Atk" would probably fit too (not tried). |
| Pokédex search (Pokédex → Y) | – | Labels fit (ORDER, Numerical, NAME, TYPE, HT, WT, AREA, FORM). **Bug: the button bar at the bottom (RESET / START / CANCEL) is garbled in English**: stray tiles over and around the buttons. Clean in Chinese. |
| Search by letter (search → NAME) | D-0520 | The screen shows A–Z in the hack's kana grid (columns of five: A–E, F–J, …, Z at the top of column 6); the remaining 18 buttons are blank, as decided. Selecting a letter was not tried. **The same garbled bottom bar (OK / CANCEL).** |
| Battle command menu (in sun) | – | BAG, RUN, POKéMON, INFO and the weather badge SUN fit. **FIGHT is partly covered by the lead Pokémon's icon** (the F sits under it); in Chinese the icon sits left of 战斗. |
| Battle info panel (INFO, Groudon with Drought) | D-0518 | Ability: Drought fits. **"Harsh Sunlight 5 turns" overflows**: the line ends at the panel edge as "5 turn". The Chinese puts the label left and 5回合 right-aligned. |

Not reached: the contest/APPEAL and NEXT labels (D-0522); contests need a contest entry and NEXT's screen
is unknown. The Pokédex bar and the info-panel overflow are new findings for the translation, not hack
bugs. Both are visible in `work/build/harness/screens/`.

## What the harness can do now

- **State**: `SaveFile` (teleport, flags, vars, bag pockets, map objects, CRC), `start_at(map, x, y, flags=,
  vars=, clock=, edit=, hooks=)` → a `Harness` standing in the field; savestates for fast reruns.
- **Clock**: `set_clock(datetime)` pins date, weekday and time; `clock()`.
- **Pokémon**: `generate_pokemon(species, level, item, form)` via the hack's generator, `party()` (decrypted,
  with level), `edit_party_mon`, `swap_party`.
- **Menus** (touch/key sequences): `field_menu(entry)`, `open_bag`, `bag_pocket`, `bag_put_first`,
  `give_from_bag`, `use_from_bag`, `level_up_with_candy`, `open_summary_from_bag`.
- **Battles**: `walk_until_battle`, `WildLog`, `flee`, `in_field`.
- **Observation**: `on_exec(addr, fn)` hooks (e.g. the encounter-bank getter, the Lycanroc form write),
  `screenshot`, `mark` (screen-check points), `screen_diff`.
- **Commands**: `unown`, `wild`, `palpark`, `arceus`, `evolve`, `screens`, `info`.
- **Isolation**: `run_child`: one emulator per process (a second DeSmuME instance in the same process
  crashes with SIGSEGV).

## Limits

- Menu navigation is timing-based (fixed waits and touch coordinates). It worked in every run here, but a
  new screen or a different save can need different waits; each new recipe needs one look at its
  screenshots. There is no screen recognition yet, only the overlay-2 check for "in the field".
- Teleporting through Continue skips on-entry map scripts, and the new map's NPCs are whatever the map
  spawns by itself. The live player position is not read (the Pal Park start tile could not be checked).
- The pinned clock does not advance.
- `generate_pokemon` overwrites party slot 6 when the party is full; the generator reuses one PID.
- Wild-battle recipes depend on random encounters (single or double battle, CN vs EN differ), so screen
  pairs of battles are not pixel-identical between runs.
- Not built: trainer battles (Thief test), talking to NPCs with scripted state (Pal Park prize), winning a
  battle, contests.

## Proposal: an automated regression suite

Run per English build (a release candidate or a nightly), headless, on the Mac that builds it:

1. **Screens (about 2 min for 6 screens, ~20 s per screen and ROM):** the `screens` recipes plus the memcheck
   menu scenarios, English only, compared with `screen_diff` against **approved English baselines** from the
   previous build. 0 % difference passes; anything else produces a diff mask and a CN|EN pair for review.
   Approving a change copies the new screenshot to the baseline folder (outside git, or as hashes in git).
   Add a recipe whenever a translated graphic or a long text box is changed (Pokédex search bar, info panel).
2. **Behaviour checks (about 5 min):** `unown` (20 encounters, ~2.5 min), `palpark` (7 days, ~1.5 min),
   `arceus` (16 Plates, ~1.5 min), `evolve` Petilil day/night and Rockruff at 4 hours (~25 s each). Each
   has an expected result (all A; records 141–147; the 16 forms; 548/1 then 549/1; 0/2/1). They prove the
   English build did not change behaviour (D-1002). Run them on both ROMs and compare.
3. **Memcheck** (existing `memcheck.py run`) for heap headroom.

Make it one command (`emu_harness.py suite`) that runs the children in parallel (each is a separate
process, the Mac has the cores), writes one JSON report and exits non-zero on a failed expectation. A full
run would take about 5 minutes in parallel, about 10 minutes sequentially. Saves stay in
`work/build/memcheck/`; outputs in `work/build/harness/`; nothing goes into git except the recipes and
expected values.
