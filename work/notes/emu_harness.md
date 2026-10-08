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
    .venv/bin/python work/tools/emu_harness.py palpark --days Fri,Sun,Mon --count 8      # encounters in the park
    .venv/bin/python work/tools/emu_harness.py thief [--case air_balloon,...]            # Tier 4
    .venv/bin/python work/tools/emu_harness.py messages [--refs "457#123 48#20"]         # lines in the window, CN|EN
    .venv/bin/python work/tools/emu_harness.py drive --lang en gen:25,30 t43,73/120 s:party   # op language
    .venv/bin/python work/tools/emu_harness.py skitty                                    # D-0582: Route 8 scene, CN|EN
    .venv/bin/python work/tools/emu_harness.py guide0107 [--case pikachu,corner_kid,...] [--lang cn|en|both]  # guide 01-07
    .venv/bin/python work/tools/emu_harness.py guide0813 [--case ribbon,magcargo,...] [--lang cn|en|both]   # guide 08-13, known issues
    .venv/bin/python work/tools/emu_harness.py calendar [--case table,battle,volcanion,stale] [--lang cn|en|both]   # calendar hook
    .venv/bin/python work/tools/emu_harness.py hackbugs [--case tutor,coins,...] [--lang cn|en|both]   # open hack-finding records
    .venv/bin/python work/tools/emu_harness.py verify [--case bigtext,never,...] [--lang cn|en|both]   # open verify-in-game records
    .venv/bin/python work/tools/emu_harness.py sweeps --sweep trainers|desc|battle [--ids ...] [--lang cn|en|both] [--jobs 6] [--rejudge]   # text read-back, see 12
    .venv/bin/python work/tools/emu_harness.py open [--case arceus,thief,rockruff,primal,palpark[:variant+...]] [--lang cn|en|both]   # open points, see 13
    .venv/bin/python work/tools/emu_harness.py suite [--only unown,palpark,arceus,evolve,dex,skitty,guide0107,guide0813,calendar,hackbugs,verify,sweeps,open] [--jobs 4]
    .venv/bin/python work/tools/emu_harness.py cleanup [--kill [--all]]                   # leftover harness processes
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
  Fixed 2026-10-06: the permissions start after the header's extra section (u16 size at +0x12, 0x1234 magic
  before it): 0 bytes in most indoor maps, 8–72 bytes in many outdoor chunks (48 on Mt. Silver). Before the
  fix, outdoor grids were shifted, e.g. "grass" on Mt. Silver was a dirt path and walls were open.
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
  Correction (2026-10-06, item 5): the hack keeps the ability as a u16 at block B +0x1A (abilities go past 255);
  `encode_pokemon`/`edit_party_mon(slot, ability=)` write it and the summary shows it (all 327 abilities). The
  note that follows is about the unused vanilla byte. Not integrated: writing the ability byte (block A +0x0D) had no effect in battle; the hack computes the
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

### 2b. Running any event script, trainer battles (round 3, item 2)

Mechanism (observed): pressing A in the field goes through the field input handler in overlay 1. With a
person in front it calls `StartMapSceneScript(fsys, id, obj)` (arm9 0x0203F57C) from ov1 0x021E5D2C
(r1 = the person's script id); otherwise the bg-event lookup 0x0203D320 returns the id in r0 at ov1
0x021E5D5E (0xFFFF = nothing to read). `run_script` arms exec hooks there and rewrites the id on the next A
press, so any script starts in the current map's context, facing anything or nothing. Further hooks:

- the script loader 0x0203F870 (r2 = script file, r3 = message bank) can be pointed at any file, so
  `run_script(file=F, index=N, msg_bank=M)` runs script N of file F (id 2000 + N, whose default is file 3);
- after the jump to the script's start (0x0203F812, r4 = script context), context+0x08 is the script PC;
  `run_script(program=script_bytes(...))` writes our own commands there. `script_bytes` encodes commands
  by name with argument sizes from `work/tools/docs/script_cmds.json`.

Built on it: `warp(map, x, y)` (fade, `Warp`, fade: a normal map entry, people and map scripts load;
checked on map 315: a scientist appears and the player walks), `trainer_battle(id)` (`LockAll;
TrainerBattle id 0 0 0; ReleaseAll; End`, checked: Youngster 252 sends out his Magnemite with its Air
Balloon), a scripted `WildBattle`. Trainer ids 3000+ map to file 949 but run that file's script
<id − 3000>, not a battle, so the hack's own trainer scripts are not used for this.
`battle_turn(slot)` (FIGHT → move, B through the messages until the command menu or the field is back,
optional message screenshots) and `fight(plan)` drive battles using screen recognition (item 5).

### 3. Thief: is the stolen item kept? (Tier 4, observed, Chinese ROM)

`emu_harness.py thief`: a Lv100 Pokémon from the generator (Chansey, or Skarmory against the two hard
hitters) with Thief and Seismic Toss and no held item leads; `trainer_battle` against a trainer whose lead
holds the item; Thief on turns 1–2, then Seismic Toss until the battle is won; afterwards the lead's held
item and the bag are compared. Messages of the Thief turns: `work/build/harness/thief/thief_<case>_turn1.png`.

| item | trainer (holder) | what happened | after the battle |
|---|---|---|---|
| Air Balloon (576) | 252 (Magnemite Lv22) | Thief hits, "the foe's balloon popped!", nothing stolen (2 runs) | not obtained |
| Eviolite (584) | 452 (Rhydon Lv45) | stolen | **kept** (held by the thief) |
| Weakness Policy (600) | 207 (Mr. Mime Lv29) | stolen on turn 1 ("stole a Weakness Policy"); one earlier run flinched from Fake Out first | **kept** |
| Salac Berry (203) | 605 (Pinsir Lv25) | stolen ("stole a Salac Berry"); run 1 kept it, run 2 the thief dropped to low HP and ate it | **kept unless eaten in battle** |
| Petaya Berry (204) | 595 (Empoleon Lv58) | stolen | **kept** |

The bag never changed: the item stays on the Pokémon that stole it. Wild control: a scripted wild
Rattata given an Eviolite at the end of the wild finalizer (logged as holding 584) was hit by Thief twice
without a steal message. **Inconclusive**: the scripted wild battle probably sets the held item after that
point, so the control needs a different way to give a wild Pokémon an item. Settled in section 13: the item must be written into the
wild Pokémon's RAM copies (the finalizer's Pokémon is a temporary copy); in a wild battle the stolen item is kept and a
second one goes to the Bag (D-1569).

### 4. Cut-scene big text (Tier 5): rendered, all English lines fit

Running the scenes themselves was skipped: each needs its story state (flags, people placed by earlier
scripts, the right map) and most are long chains of movements. Instead `emu_harness.py messages` prints
every referenced line with a one-off script in the field's normal message window, on the Chinese ROM and
the English WIP build: `show_message(bank, id)` loads the message bank through the script-file override
and runs `SetVar 0x8000 id; NonNPCMsgVar 0x8000; WaitButton; CloseMsg; SetVar 0x40FE 0x5A5A; …` (the
sentinel var tells the harness the window has closed; it is restored afterwards). The text's own control
codes (the 200 % size, colours, page breaks) render exactly as in a scene. What is not reproduced: the
scene's buffers (speaker names stored in {VAR} buffers are empty, so lines that start with a buffered
name show ": …" in English and "『…" in Chinese), the camera and any special window.
46 lines, both ROMs, about 4 minutes; pairs in `work/build/harness/messages/` (`sheet_*.png` overview).

| decision | lines | result (English WIP build of Sep 30) |
|---|---|---|
| D-0541 | 0313 #28, 0314 #14, #28 | fit; #28 "Whoooooa!!!" without label. The Chinese #28 itself runs to the box edge. |
| D-0553 | 0457 #123, 0319 #26, 0048 #5/#6/#20, 0321 #27 | fit, every 2× line on one row; 0321 #27 "Did someone say Pokémon food?!" ends close to the edge but inside |
| D-0571 | 0476 #14 #19 #69 #74 #85 #102, 0356 #4 #10 #70–81 #84 | fit. 0356 #70/#79/#81 page 2 is "!" alone because the winner's name is a buffer (Chinese "选手!" the same) |
| D-0719 | 0511 #153 | fits ("Moltres!") |
| D-0744 | 0124 #124/#125 | fit |
| D-0853 | 0547 #7, 0053 #1/#39, 0546 #12/#48, 0090 #141 | fit |
| D-0903 | 0599 #45/#56 | fit; the label is the player's name buffer (shown here as ": ") |
| D-0983 | 0081 #25, 0377 #136 | fit ("Celebi, you say?" on one row in this build) |
| D-0550 / D-0746 | 0457 #140, #172, 0126 #100 | the placeholders render as "---!", "---", "---" (Chinese 空!, 空, 空。); whether the scenes ever print them was not checked |

Observed for the window rendering; whether the scenes use the same window is inferred (the lines come
from ordinary message commands in their scripts). The WIP build predates later bank edits (e.g. D-0983's
{NEWLINE} split is not in it), so rerun `messages` on a fresh build.

`run_script(file=F, index=N, msg_bank=M)` also runs real scripts: index is the scriptdump number − 1
(checked: file 12 index 3 shows Pal Park's "Would you like to retire?" with its YES/NO menu).

### 5b. Screen recognition, the shared battery file, Pokédex tools, `suite` (round 3, item 5)

- **Root cause of the "wrong save (map 500)" runs** (found here, fixed): DeSmuME keeps the battery in
  `$XDG_CONFIG_HOME/desmume/<rom name>.dsv` and reads the emulated flash from that file. Every harness
  process opened its ROM as `game.nds`, so all of them shared `~/.config/desmume/game.dsv`; parallel runs
  read each other's saves (both Unown suite runs booted the unedited Poké Mart save). Each Harness now sets
  a private `XDG_CONFIG_HOME` in its temporary directory (as memcheck.py already did). The stale
  `~/.config/desmume/game.dsv` (a battery copy written by earlier harness runs) was left in place.
- **Screen recognition**: `SCREENS_KNOWN` + `on_screen(name)` / `wait_screen` compare a few pixels
  (battle command menu: red FIGHT, blue INFO). Fixed waits replaced where it mattered: battle turns end on
  the command menu or the field, `flee` and `continue_game` poll for the field (overlay 2 loaded; Continue
  no longer fails under load), `show_message` ends on a sentinel var, `walk_to`/`step_dir` check the live
  position, `emu_dex` checks the dex number by OCR.
- **Pokédex tools** (from the Pokédex hunt agent, `work/tools/emu_dex.py`): `fill_dex_ram`, `open_dex_list`,
  `goto(n)`, `detail_page(tab)`, `back_to_list`, `capture_entries`, digit OCR. The digit templates are
  game font pixels, so they are not in git: `open_dex_list` learns them from entries 0001–0010 and caches
  them in `work/build/harness/dex_digit_templates.json`. `EMU_HARNESS_DATA=<checkout>/work` points copies
  outside the repo at the ROMs and saves.
- **`emu_harness.py suite [--only ...] [--jobs 4]`** (default 4; emulators capped at 6 machine-wide): runs each check on the Chinese ROM and the English
  build in parallel child processes and writes `work/build/harness/suite/suite_report.json`; exit 1 on any
  failure. Checks and expectations:

| check | what | expected | time (parallel) |
|---|---|---|---|
| unown | 6 wild Unown in the hall | final form A for all, decoder check | 35–70 s |
| palpark | encounter record per weekday | 141 … 147 | 2 min |
| arceus | 16 Plates through Bag → Give | the 16 forms | 1.7 min |
| evolve | Petilil day + Sun Stone, Petilil night, Rockruff 12/18/22 h | 548/1 → 549/1; no evolution; 0/2/1 | 2.2 min |
| dex | Pokédex entry panels 1–30, number read back | pixel-identical to the approved baseline (`baselines/dex_<rom>/`; created on the first run) | 20 s |
| skitty | Route 8 Skitty scene (D-0582, `emu_skitty.py`), see below | cries, sprite 761 = Skitty, trainer 277 leads Skitty form 0, all 18 lines shown, EN text says Skitty | 1.1 min |
| guide0107 | 9 guide-claim cases (`emu_guide0107.py`: pikachu, electrode, misty_date, azure_flute, koga, giovanni, sabrina, kecleon, promo_flag), see 7 | each keeps its observed verdict (`SUITE_EXPECT`); promo_flag writes the Pokédex seen bit of No. 1335 and doesn't repeat | about 4 min |
| guide0813 | 12 guide-claim cases (`emu_guide0813.py`: ribbon (Arthur + control), magcargo, white_flute, radio_quiz, fortune, sprout, kiln, whirl, bugsy, dance, morty, blackthorn), see 8 | each keeps its observed verdict (`SUITE_EXPECT`) | about 5 min |
| calendar | calendar hook table (`emu_calendar.py`, case `table`), see 9 | for all 8 entries: the loaded buffer equals the ROM record the day before and record + configured slot-11 word(s) on the date | 2.5 min |
| hackbugs | 22 hack-finding cases (`emu_hackbugs.py`, `SUITE_EXPECT`), see 10 | each keeps its observed verdict | about 6 min |
| verify | placeholders never printed, Gym statue branches, costume nurse (`emu_verify.py`), see 11 | never_printed / confirmed / confirmed | about 1 min |
| sweeps | text read-back subsets (`emu_sweeps.py SUITE_SUBSETS`), see 12: 6 trainer intros, 6 bag + 4 move + 4 ability descriptions, 2 battles | EN rows `ok` (item 4 `past_panel`), CN rows captured | about 2 min |
| open | open points (`emu_open.py SUITE_EXPECT`), see 13: Arceus flame/zap, wild Thief (Miltank), Rockruff 12:00/18:00 after a battle, Groudon + Red Orb | plate_type ×2, kept, midday/dusk, no_reversion | about 3 min |

  Result (observed): all 10 (5 checks × 2 ROMs) pass, 2 min 13 s wall time with `--jobs 10`. A first run
  before the battery fix failed unown (both ROMs) and palpark (English) on the shared battery file, and one
  rockruff_12 run did not evolve.
  With `skitty` added (2026-10-05): all 12 pass, 2 min 10 s with `--jobs 10`.
  With `guide0107` added (2026-10-06): all 14 pass, 3 min 7 s with `--jobs 14`.
  With `guide0813` added (2026-10-06): all 16 pass, 5 min 17 s with `--jobs 16`.
  With `calendar` added (2026-10-06): all 18 pass, 6 min 1 s with `--jobs 18`.
  With `hackbugs` added (2026-10-06): all 20 pass, 9 min 54 s with `--jobs 20`.

### 6. Route 8 Skitty scene (D-0582): observed, the fix holds

`emu_harness.py skitty` (module `work/tools/emu_skitty.py`) runs the real scene of script file 188 (bank
a027/0331) on both ROMs in two emulator runs each:

- run a: flags 1636 set, 1163 clear, 1568 set, var 16576 = 1; `warp` to Route 8 (map 16) and talk to
  object 3 (script 4, #3) and object 1 (script 3 → part 1, L980); then step onto the coord trigger
  (1384, 242) (script 5, var 16576 = 0 after part 1) until the game's TrainerBattle 276 + 277 starts;
- run b: flags 1163 and 1636 set, 1568 clear, var 16576 = 0 (the state after part 1): talk to the meadow
  Skitty (object 14, script 7) and its trainer (object 15, script 12, #48), then part 3 (after the battle):
  script 5 started with `run_script(script_id=5, program=GoTo)` jumping to the first command after the
  battle check (offset 2300, found from the script data), so the scene's own bytes run from there.

Hooks: the PlayCry handler's call of the cry routine (0x020487F0, r1 = species), the cry routine itself
(0x0200629C, every cry incl. battle send-outs), NPCMsg / GenderMsgBox (overlay 1 0x021EE288 / 0x021EE388,
message id at the script PC), CloseMsg 0x020408A4 and TrainerBattle 0x02048B64. Pages are screenshotted when
the text area stops changing. Live map objects (`live_objects`: 0x12C-byte LocalMapObjects, +8 id, +0xC map,
+0x10 sprite, +0x1C flag, +0x20 script, +0x64 x, +0x6C z) give each object's sprite; the sprite → species map
is the game's own pairing (`sprite_species_table`: objects whose talk script plays one literal cry; sprite
761 appears with cry 300 in four objects across the game, nothing else). Opponent parties are found in RAM
as Party structs and compared with the ROM's trainer data.

Observed on the Chinese ROM and on the English build (CRC32 2A4FF4DB), identical: script cries part 1
[53, 300, 300], part 2 [53, 53, 300], Skitty talk [300], part 3 [53, 300, 53, 300]; battle send-out cries 53
and 300; no Glameow (431) cry anywhere; objects 2 and 14 sprite 761 = Skitty (Persian objects 4/13: 482 = 53);
trainer 277's party in battle Skitty (form 0, Lv28), Chansey, Wormadam; trainer 276 Persian, Swellow,
Girafarig. The battle shows 向尾喵 / "Skitty". All 18 lines that name the Skitty or write its cry (#3–#6,
#8, #17, #18, #19, #21, #24, #26, #31, #33–#35, #37, #38, #48) were printed by the scene and fit;
the English says Skitty with Skitty-style cries. CN|EN pairs: `work/build/harness/skitty/`.

### 7. Guide chapters 01–07: the hedged claims (`emu_guide0107.py`, 2026-10-06)

`emu_harness.py guide0107` runs one recipe per claim that guide chapters 01–07 marked "not confirmed in game"
(or "probably" about behaviour). Each recipe sets the state the guide's *Source:* line names (flags, vars,
badges, clock, party), runs the hack's own script (talking to the object, stepping on the trigger, or a GoTo
into the script's own bytes at the named label with `run_from`) and reads back flags, vars, party, bag, live
map objects, the message ids printed, battles and memory writes. Variants (controls) run in separate child
processes; a judge per case gives `confirmed` / `contradicted` / `observed` / `blocked`. Screenshots:
`work/build/harness/guide01_07/<cn|en>/`; reports `report_*.json` there. Every case was run on the Chinese
ROM and on the English WIP build (Oct 5): same results on both.

| guide claim | recipe (case) | result |
|---|---|---|
| 01 Viridian Pikachu thief: back at its first spot after you leave | pikachu: Yes at the first spot → object 5 at 1008,235; warp to Route 1 and back → 1033,247 | **confirmed** |
| 01 Pidgeot loan: "Lv. 20, IVs 31, your name as OT" | pidgeot: lend a Lv60 Pidgeot with Leftovers through the party menu (it leaves the party), set 2404, take it back | **contradicted** in part: Lv20, IVs 6×31, moves 28/16/98/18, no item, trade record 6's PID, but OT ID 0x761510F0 (ID No. 04336) and an empty OT name (D-1552) |
| 01 Victory Road Electrode: fleeing (probably) removes it; losing keeps it | electrode: Ninjask Lv100 flees → flag 1241 set, ball gone; a Memento lead (rest at 0 HP) loses → Pokémon Center, ball still there | **confirmed** (an Electrode that explodes counts as a win too) |
| 01 "Meet my mom" plays Cynthia's version | mom_visit: Yellow partner, 739 L10063 → zone 504 scene; control with flag 106 clear | **confirmed** (D-1553) |
| 01 Living together blocked for everyone | living: 2F PC at 0x40B5 = 6 with the Cascade Badge prints nothing, player walks on; control (106 clear) starts the love letter | **confirmed** (D-1553) |
| 02/04 Misty missing after a won Resort date | misty_date: 809 script 15 from L4312 → Gym with var 4; object 6 absent, also after re-entering; Cape object 35 absent | **confirmed** (D-1554) |
| 03 Losing the clash resets the side choice; switching locks both | clash: trigger → flags at the first battle; re-choice with Green from that state | **confirmed up to the battle** (the Multi Battle loss with an AI partner not played; D-1555) |
| 03 Blue's free Shoal Salt uses the Captain's HM01 check | ssanne: real boarding at Vermilion Harbor, arrival scene, Captain's speech; control with flag 1440 set | same gate **confirmed**; new: a real boarding leaves 1440 clear, so neither gives anything (D-1549, open) |
| 03 Corner kid loss jumps into the "Pikachu" kid's dialogue | corner_kid: loss with a Splash-only party; controls `TrainerBattle 606 0 1 0` and `… ; WhiteOut` | **contradicted**: the game freezes (black screen, CPU in heap memory); controls behave (D-1548) |
| 03 Sabrina only "in training" while the story value is 0 | sabrina: var 0x40AF = 0 → 53#210, = 5 → 53#149 (script 23 started directly: another object stands in front) | **confirmed** |
| 03 Celadon Dept. Store 3F S.S. Anne passengers: gone after a Rock Tunnel rescue "if Rock Tunnel can be reached in that window" | – | **blocked**: a story-order question (can Rock Tunnel be reached between arriving in Vermilion and saving the ship), not a game state the harness can build or observe |
| 04 Tony's roof scene before the Route 7 scene; Suzie's prices | tony: Suzie's paid offer, roof trigger, Beedrill won, var 2 when Jessie & James start; from that state Suzie is free | **confirmed**; whether the roof is reachable that early is not checked |
| 04 Pal Park Monday: which time check | monday: seven pinned hours | **resolved**: `ScrCmd_522` = hour; 7–18 → A+D, else E+H (D-1551) |
| 04 Saffron takeover step 5: Blue's scene | blue_saffron: coord script 5 of file 827 with a Lv100 lead, three battles won | **confirmed**: lines 20–44 (32/34 female versions; 24 unused) |
| 06 Kecleon needs Alomomola, not Noctowl | kecleon: Alomomola lead → Noctowl cry, Kecleon battle; Noctowl lead → only line 33 | **confirmed** (D-1556) |
| 06 Azure Flute unobtainable after the HQ report | azure_flute: var 0x40B7 = 4 → "keep it safe"; = 3 → flute lent | gate **confirmed**; "the report always comes first" read from the scripts (D-1557) |
| 07 Giovanni's rematch opens with Mewtwo and Tyranitar | giovanni: `TrainerBattle 402 402 0 0` | **confirmed**: double battle, cries 150 then 248, one team in RAM |
| 07 Koga in the League gate 18:00–20:59, east side | koga: 17, 18, 20, 21 h | **confirmed**: present at 17,10 (by the Route 22 door) at 18 and 20, absent at 17 and 21; photo offer 354#12 |
| known issues, D-1333 out-of-range flags | promo_flag, mortar_flag: write and read hooks on the byte | **observed**: both land in the Pokédex block (array 6): 7286 = seen bit of No. 1335 (never read by the Pokédex or Trainer Card), 4461 = caught bit of No. 110 Weezing (D-1550) |

New harness pieces (in `emu_guide0107.py`, reusable):

- `run_from(h, file, script, label)`: start a map script and jump to a label of its own bytes.
- Losing and winning: `weak_party` (every party Pokémon knows only Splash; HP and count stay real),
  `doomed_party` (plus 1 HP lead / 0 HP others, only for a wild battle the foe could otherwise end by
  exploding), `lose_battle` (forced-switch party list and its submenu handled, "no will to fight" skipped),
  `turn` / `win_battle` (double-battle target screens: first foe, then own side panels).
- `safe_warp` (retries after white-outs and long scenes), `finish_scene`, `set_badge` (badges 0–7 at
  PlayerProfile +0x20, 8–15 at +0x23, found with CheckBadge), `player_ot` (name +4, ID +0x14), `money`
  (+0x18), `mon_details` (OT ID, IVs, moves, OT name).
- The save array table at save+0x2E01C has 16-byte rows {offset, crc, next id, size of the next array}:
  array 6 (Pokédex) is 0x13A8 + 0x374, right after array 5 (0x1324 + 0x84).
- `CheckBattleWon` treats a flee as a win (Electrode). A scripted `TrainerBattle a b 0 0` that is lost does
  not restore the field; the next command runs without it (corner kid freeze). With the third argument 1
  (`TrainerBattle a b 1 0`) the field comes back.
- `SCREENS_KNOWN["battle_menu"]` now samples INFO at (244, 203): the English build's INFO label covers the old
  sample since the 2026-10-05 label fix, so English battle recipes never saw the command menu.

### 8. Guide chapters 08–13 and known issues (`emu_guide0813.py`, 2026-10-06)

`emu_harness.py guide0813` runs one recipe per claim that guide chapters 08–13 and `known-issues.md` marked
"not confirmed in game" (or "probably"/"may" about behaviour), skipping what section 7 already covered. Same
approach and helpers as section 7. Screenshots: `work/build/harness/guide08_13/<cn|en>/`; reports there. Every
case ran on the Chinese ROM and the English WIP build (Oct 5): same verdicts on both.

New piece: **`OpTrace`**, a hook on the script interpreter itself. `RunScriptContext` (arm9 0x0203F474) reads
each opcode and, if it is below the context's command count (ctx +0x60, table at +0x5C), calls the handler
(dispatch at 0x0203F4CE: r1 = opcode, r4 = context); otherwise (0x0203F4C4) it asserts and sets the context's
mode to 0, which stops the script. ctx +8 is the script PC and ctx +0x7C the loaded script file, so every
command executed is logged as (name, file offset, first argument bytes); bad opcodes are logged separately.
A hook in CompareVarToValue (0x0204021C, r0 = `GetVarPointer` result) also logs the value it read, which shows
special vars (0x8000+) at a given offset. With it a recipe can say which branch ran and whether a script ended
or died. Other new helpers: `talk_through` (answers Yes/No and touch menus by DOWN presses, B or a touch
position once the screen is stable, handles battles), `goto_obj`, `talk`, `session`, `set_money`, `add_item` /
`remove_item`, `menu_opens`, `window_open`, `save_prompt`, `one_mon_party` (slots emptied as ZeroMonData does).

| guide claim | recipe (case) | result |
|---|---|---|
| known issues: weekday siblings' ribbon gift "can freeze the game" (D-1331) | ribbon: all seven siblings on their day, var 0x4094 = 7, lead without ribbons; control: daily gift (var 6) | **contradicted**: the ribbon is given, the script dies on opcode 2009 with its message left on screen, but the player walks, X opens the menu and SAVE works (D-1558) |
| 09 / known issues: fortune-teller takes $10,000 after checking $300 | fortune: $5,000 / $20,000 | **confirmed**: $5,000 → $0 with the item; $20,000 → $10,000 (agrees with D-1545) |
| known issues: S.S. Anne shop TM checks $400, takes $4,000 | ssanne_tm: shop script 20 started directly, TM63 button touched; $1,000 / $5,000 | **confirmed**: $1,000 → $0, $5,000 → $1,000 |
| known issues: Sprout Tower monk's offering without a money check | sprout: $1,000 / $5,000, Yes | **confirmed**: $1,000 → $0; $5,000 → $2,000 |
| known issues: Charcoal Kiln apprentice takes HM01 unchecked | kiln: with / without HM01, Yes | **confirmed**: Leek both times; HM01 taken when held |
| known issues: Whirl Islands Challenge pays again after one island | whirl: flags 2094 + 2097 only; report, accept, report | **confirmed**: two prizes |
| 11 / known issues: Jirachi stone, 7 repairs, no Star Piece needed | jirachi: var 0x408C = 17; no Star Pieces / 10 | **confirmed**: the 7th repair starts the scene both times; 7 Star Pieces used when held |
| known issues: Frontier Access Cut man without HM01 | cutman: with / without HM01 (var 0x40E5 = 1 skips the first-visit scene) | **confirmed**: without HM01 L1491 runs and a photo is taken |
| 09 / known issues: radio quiz, B counts as right (D-1479) | radio_quiz: B on all five touch menus; control: wrong answer | **contradicted**: B returns the last button (3), so question 2 fails (D-1561) |
| 09 / known issues: Buena's lottery line after a point | buena: from L4353 with var 0x413A = 1 | **confirmed**: lines 81 then 32 (the lottery line), points 2 |
| known issues: Morty's Lv. 1 Pokémon | morty: `TrainerBattle 31 31` | **confirmed**: Lv. 80/80/80/1/1/1 in the battle party |
| 11: Chuck's badge battle is a 4-on-4 Double | chuck: `TrainerBattle 34 34` | **confirmed**: one copy of the 4-Pokémon team, first two send-outs = his first two |
| known issues: Elite Four practice names | e4names: trainers 703 / 705 | **observed**: CN "四天王阿桔" / "四天王梨琳" under Agatha's / Lance's pictures; EN "Elite Four Agatha" / "Lance" (D-1496 fix) |
| known issues: Misty's Cerulean Cape photo hidden at every hour | misty_cape: 12, 14, 15 h, flag 2261 | **confirmed**: absent at all three; the hour compares read 12, 14/14, 15 |
| known issues: Petrel's Chatot never catchable | petrel: flag 500 set / clear | **confirmed**: hidden when set; shown when clear but no catch offer |
| 11 / known issues: Satsuki's short menu takes the Ho-Oh path | satsuki: from L4299, var 0x40A9 = 11 | **confirmed** (menu part): msg 87, var → 7 |
| 08: dream-world Entei, Lv. 90, one chance | entei: Yes, flee | **confirmed**: Lv. 90; after fleeing flag 2318 set and Entei gone |
| known issues: Bugsy's 4-Pokémon rule never applies | bugsy: fresh / after `SetVar 0x8005 5` in a previous script | **confirmed**, refined: 0x8005 reads 0 both times, six Pokémon accepted (D-1563) |
| known issues: Magcargo loss "may restart the battle" | magcargo: Splash-only party, from L2519 | **contradicted**: the script loops back to L2519 but the field never returns; black screen, CPU at 0x01FF8030 (D-1560) |
| 13: Clefairy dance also after midnight on Tuesday | dance: Tue 01 h, Tue 05 h, Mon 22 h seen, Mon 22 h seen → Tue 00:30 in game | **confirmed**: MoveWarp at Tue 01 h and after the day change (daily flag 2741 cleared), not at 05 h or when seen the same day |
| known issues: Blackthorn Gym trainers skipped after the farmer's Yes | blackthorn: var 0x40A3 = 5 / 1, talk to the entrance trainer | **confirmed** (Gym side): msg 13 and no battle at 5; battle 932 at 1 |
| 11: partner room shows only Blue | partner_room: as saved / flags 603 + 336 | **observed**: Yellow and Misty hidden after the Route 39 flags; Riley/Marley always hidden; Blue shown |
| known issues: Island Forest has no wild Pokémon without a panel (D-1430) | island_forest: 400 steps in grass, flags 2423–2426 clear / 2423 set | **contradicted**: 4–8 battles either way (D-1562) |
| known issues: Weezing caught bit from the expedition (D-1550) | weezing_dex: `SetFlag 4461` with No. 110 unseen; controls unseen / seen | **observed**: the Pokédex list leaves slot 0110 empty, same as unseen |
| 09: Dept. Store 6F Double Battle with one Pokémon | white_flute: one-Pokémon party / six (control) | **contradicted**: the battle starts with a broken second ally and hangs at FIGHT; the control plays the turn (D-1559) |
| 10 / known issues: MooMoo farmer never offers the cure again | moomoo: flag 744 clear with 2289 set / clear | **confirmed** (farmer side): L903 (greeting) vs L925 (investigation) |
| 12: Petrel scene starts on entry with 0x40B2 = 4 | petrel_scene: var 4 / 3 | **confirmed**: frame script 2 runs at 4, not at 3 |
| 08 Primo passwords; 09 radio show hours, lottery digit order; 12 Whirlpool without the move; 13 Forest of Time route; Goh's lure-scene loss | – | **blocked**: Easy Chat input, the Pokégear radio, the daily lottery number, a whirlpool tile and long maze/scene setups are not driven by the harness yet (time-boxed) |
| known issues: story-order entries (Pokéathlon Dome tree, bug-hunt counters, Burned Tower, Giratina, Ho-Oh panel, Will and Karen, Radio Tower gap, red envelope, …) | – | not run: the open question is whether the story order allows the state, not what the game does in it |

Suite (`SUITE_EXPECT`, 12 cases; ribbon runs Arthur and his control only): ribbon, magcargo, white_flute,
radio_quiz keep `contradicted`; fortune, sprout, kiln, whirl, bugsy, dance, morty, blackthorn keep `confirmed`.
With `guide0813` added (2026-10-06): all 16 checks pass, 5 min 17 s with `--jobs 16`.

### 9. Calendar encounters (`emu_calendar.py`, 2026-10-06)

`emu_harness.py calendar` replays the calendar hook found statically in
`chinese_source_rom_verify_calendar.md` (loader arm9 0x0203AD24, table 0x020F6A64, slot-11 words at buffer
+0x2A/+0x42/+0x5A for morning/day/night). Hooks: the loader's return (0x0203ADA8: r4 = map, r5 = the 0xC4-byte
encounter buffer, copied as the game built it) and, for the forced-slot cases only, the two land slot pickers
(ov2 0x02247A0C and the visible-spawn picker arm9 0x02019E3A, both `cmp r0, #0x14` with r0 = Random % 100):
r0 is set to 99, which selects slot 11. Nothing else is changed: walking, the walk-rate roll, the wild
finalizer, the battle and the catch are the game's own. Lead: generator Ninjask Lv100, party count lowered to
1 so the catch lands in the party; 50 Master Balls in the Balls pocket (save edit). The catch goes through the
battle bag by touch (BAG (36, 165) → Poké Balls (192, 56) → first ball (64, 28) → Use (100, 173)), then A
through the Pokédex page and "joined the party" (no nickname prompt appeared). Encounter tiles come from
`MapGrid` (behaviours 0x02 tall grass, 0x03, 0x08 forest/cave floor; Ilex Forest has only 0x08), limited
to the matrix chunks whose zone header is the map. Every case ran on the Chinese ROM and the English WIP
build (Oct 5) with the same results. Report: `work/build/harness/calendar/report_all_both.json`; screenshots
`work/build/harness/calendar/<cn|en>/<entry>_<period>_{battle,catch_*,summary_1,summary_2}.png`.

| entry (date, map) | table (control day / date) | forced-slot battle (observed) | after the catch |
|---|---|---|---|
| Keldeo (Jun 23, 181) | ROM slot 11 (175 / 1 / 778) / 647 in all three | Keldeo Lv5 at 06:00, 12:00, 22:00 | 647 form 0 Lv5; stats fit personal 647 |
| Meloetta (Jul 14, 117) | 928 / 928 / 420 / 648 ×3 | Meloetta Lv6 (walk rate 5: 250–850 steps) | 648/0 Lv6 |
| Genesect (Aug 11, 113) | 175 / 679 / 636 / 649 ×3 | Genesect Lv5 | 649/0 Lv5 |
| Floette (Oct 16, 96) | 204 / 204 / 213 / 670 form 5 ×3 | Floette form 5 Lv14 | 670 form 5; stats fit personal 1222 (Eternal Flower), not 670; summary: Fairy only |
| Diancie (Jul 19, 492) | 676 ×3 / 719 form 4 ×3 | Diancie form 4 Lv17 | 719 **form 4** kept; stats fit base personal 719, not Mega 1242; normal sprite, Rock/Fairy (D-1489) |
| Hoopa (Jul 18 morning, 90) | 706 / 706 / 571 / 720 morning, 706 day, 720 form 1 night | 04:00, 06:00, 09:59: Hoopa Lv50; 10:00, 12:00, 19:59: Goodra (706) Lv50 | 720/0 |
| Hoopa Unbound (Jul 18 night, 90) | (same buffer) | 20:00, 22:00, 03:59: Hoopa form 1 Lv50 | 720 form 1; stats fit personal 1243; Unbound sprite, Psychic/Dark |
| Volcanion (Apr 16, 88) | 0 ×3, walk rate 0 / 721 ×3, walk rate 0, level 0 | no grass or cave tiles in the map; 400 steps per period on land with the slot forced: 0 battles | – (D-1488) |

- **Table**: one emulator per ROM; per entry the clock is pinned to the day before, a `warp` onto an encounter
  tile loads the map, then the clock is pinned to the date and a second warp reloads it. Control = the ROM's
  record byte for byte; date = record + the configured word(s) only. **Confirmed for all 8, both ROMs** (also
  the RAM table equals the ROM table). This is the suite check.
- **Period windows** (observed at Mt. Silver on July 18): 03:59 night, 04:00 and 09:59 morning, 10:00 and 19:59
  day, 20:00 night, i.e. morning 4–9, day 10–19 (evening counts as day), night 20–3; the date must still be
  July 18 at 03:59.
- **Stale buffer** (`stale`, D-1564): Mt. Silver loaded on July 17 22:00, clock then pinned to July 18 22:00
  without leaving: the forced slot-11 encounter is the night table's normal Zoroark (571); the loader did not
  run again, also not after that battle; after re-entering (warp) the same slot gives Hoopa Unbound. The date
  is read only when the map's encounter data loads.
- **Visible spawns**: with the visible picker forced too, the overworld Pokémon walking in the grass looked like the
  calendar species (screenshot after a Keldeo catch in Koga's preserve), so the entry can also appear as a visible spawn. Not
  measured: how often with the real 1% roll.
- **Volcanion**: static scan (`volcanion_static`) of every script (GiveMon, GiveEgg, WildBattle, SetVar with
  721), all encounter records (land, Surf, Rock Smash, fishing, swarm, Hoenn/Sinnoh sound), headbutt trees,
  the Bug-Catching Contest table and NPC trades: no 721 anywhere except the calendar row.
- Seen once on the English build in Koga's preserve (map 181, around (59, 42)): a battle against a Lv48
  Typhlosion that the wild finalizer did not build and that RUN could not end (probably a trainer who saw the
  player after the warp). Not investigated; the battle recipe now starts on the first grass pair and gives up
  on a battle it can't flee.
- Harness fix found here: `MapGrid` read outdoor permissions from the wrong offset (see 1b).

### 10. Open hack-finding records (`emu_hackbugs.py`, 2026-10-06)

`emu_harness.py hackbugs` observes the open hack-finding records of the decision register that make a claim
about behaviour (scripts, code, data), skipping those already observed (sections 7–9, D-1485/D-1486/D-1487/
D-1501/D-1523). Same approach and helpers as sections 7 and 8; every case ran on the Chinese ROM and the English
WIP build (Oct 5) with the same verdict. Screenshots: `work/build/harness/hackbugs/<cn|en>/`; reports
`report_*.json` there. Evidence was appended to each record's rationale ("Observed in the emulator
2026-10-06").

New pieces: `run_from_with(h, file, label, pre=[...], anywhere=)` (a few commands of our own, e.g. the special
var a skipped menu would set (0x800C = the chosen party slot), then a GoTo into the script's bytes; `anywhere`
loads the file through the script loader, for maps that start a scene on entry such as the Hall of Fame),
`face_obj` (re-warps until a wandering NPC is still in front), `mon()` (moves, IVs, block-A ability byte,
party-extension HP and stats), `battle_parties_raw` (foe party in RAM with moves/IVs/form), coins at save
array 1 +0x24 (`coins`/`set_coins`; script command 119 GetCoinAmount crashes this hack, and the coin commands
only work after `ScriptOverlayCmd 3 0`), `summary_shot`, `two_forms`, `set_fateful` (block B +0x18 bit 0),
`battle_turn_named` + `text_sheet` (a turn's text boxes stacked into one image).

| record | claim | case (method) | result |
|---|---|---|---|
| D-1305 | Blackthorn tutor teaches Flail | tutor: from L1900 with 0x800C = 0, pupil with 3 / 4 moves | **confirmed**: 175 (抓狂) both paths; the forget screen names it |
| D-1347 | Dojo "Lightning Whip": Charge on ≤ 3 moves | tutor: from L3446 | **confirmed**: 3 moves → 268 Charge, 4 → 521 Volt Switch, $10,000 both |
| D-1338 | Rock Tunnel "Signal Beam" tutor gives Pollen Puff | tutor: from L4252 | **confirmed**: 676 both paths, one Dusk Ball taken |
| D-1408 | Close Combat fee skipped when replacing | tutor: from L4077 | **confirmed**: 3 Rare Candies taken / none |
| D-1404 | Route 26 "Have it" keeps the Nugget | nugget: talk, menu 1 / 0 | **confirmed** |
| D-1399 | Friend Ball never taken | friendball: talk, Yes | **confirmed** (still 1 when the scene's battle starts) |
| D-1425 | TM74 not taken | gyroball: talk, Yes | **confirmed** |
| D-1415 | 50 coins for $50000 | coins: from L7575 / L7501 | **confirmed** |
| D-1502 | Lara gives one Heart Scale | lara: from L3524 | **confirmed** |
| D-1421 | merchant prints a menu label | merchant: from L2891, 4th item | **confirmed** (msg 40) |
| D-1492, D-1335 | HoF checks S.S. Ticket 456; legendaries respawn | ssticket: file 822 from L154, 456 / 478 held, hide flags set | **confirmed**: 456 → L603, 478 → L175; hide flags cleared |
| D-1403 | Fuchsia man checks HM04 | hm04: with / without | **confirmed** |
| D-1444 | Veteran Dawn checks only badge 4 | dawn: badge 4 only / all but 4 | **confirmed** |
| D-1439 | Uxie Q4 accepts only 14 | uxie: from L1205, each choice and B | **confirmed**; B returns 3 (fails) |
| D-1334 | Cameron never on Route 34 | cameron: Wed/Thu, 16 badges, warp in | **confirmed** (CheckBadge 18 → 0, flag 638 set) |
| D-1394 | Diglett's Cave Brock never shown | brock_cave: 17, 18, 19 h | **confirmed** |
| D-1336 | Route 36 gatehouse line stuck | gatehouse: flag 450 clear / set | **confirmed** (gatehouse only) |
| D-1424 | Museum Brock sets 1323 | museum: talk | **confirmed** |
| D-1410, D-1447 | Lex Doubles single; Yellow Singles double | battle_type: send-outs before the first menu | **confirmed** |
| D-1497, D-1342, D-1498 | trainer IVs; duplicate moves; Deoxys form 4 | trainer: `TrainerBattle t 0 0 0`, foe party in RAM | **confirmed** (HP IV 10/20/31, others iv·31/255; duplicates loaded; form 4 kept, odd small sprite) |
| D-1341 | stored trainer ability used? | trainer 146 / 376 leads with stored Snow Warning / Drought | **observed**: hail / harsh sunlight on entry, so the stored ability is used |
| D-1448 | Crystal Onix can learn no TM | crystal_onix: TM13/TM11/TM39 on form 1 and form 0 | **contradicted**: it uses personal 1439's list (Ice Beam yes, Sunny Day no) (D-1565) |
| D-1443, D-1491 | Darumaka form 1 = base data; evolves into Zen Mode | darumaka: summary, Rare Candy at 34 | **confirmed** |
| D-1481 | Pancham never evolves | pancham: Lv31 + Umbreon, Rare Candy | **confirmed** |
| D-1319, D-1318, D-1311 | Volt Tackle recoil; Blast Burn recharge; Lunar Dance | move: scripted WildBattle, text sheets, HP | **observed**: no recoil; no recharge (Hyper Beam control has one); Lunar Dance raises Spe/SpA, no faint |
| D-1428 | field moves without the move | cut: std 10000, Splash-only party | **confirmed** for Cut (slot 0 read, prompt shown) |
| D-1332 | National Park gatehouse exit warp | gatehouse_warp: exit / entrance | **confirmed**, latent: player stuck at x 16384, y 59693; entrance tiles blocked |
| D-1417 | Palkia cabin door | palkia_cabin: walk onto it | **confirmed** |
| D-1400 | Route 17 Shiny Stone hidden by 1890 | shinystone: 1890 clear / set | **confirmed** (Mt. Moon part static) |
| D-1412 | Rocky Helmet sets 2104 | rockyhelmet: talk | **confirmed** (flag part) |
| D-1420 | graffiti loss keeps 1742 | graffiti: doomed party, from @3390, lose, talk | **confirmed** |
| D-1490 | Gracidea can't change the gift Shaymin | gracidea: GiveMon, Gracidea; control with fateful bit | **confirmed** |

Also marked observed from section 8 runs: D-1440 (morty), D-1407 (satsuki), D-1478 (buena), D-1441 (misty_cape).

Not run, with reasons: D-1339, D-1343, D-1344, D-1345, D-1493, D-1494, D-1427, D-1423 (claims that something
is never given/placed/triggered: a negative over the whole ROM, static); D-1348–D-1352 (comparisons with the
author's spreadsheets); D-1393, D-1397, D-1401, D-1405, D-1406, D-1413, D-1416, D-1422, D-1429, D-1431 (shared
flags/vars whose effect depends on story order); D-1398 (romance mail, needs the partner stages); D-1426
(species blacklists, hundreds of species); D-1359 (phone), D-1460 (wireless), D-1418 and D-1445 (dead branches,
static); D-1355, D-1381, D-1475, D-1477, D-1503 and other text-only records.

Harness notes from this round: in a Double Battle `lose_battle` stalls on "has no will to fight" when the
forced switch offers a fainted slot, so the graffiti case uses `doomed_party`; editing a wild Pokémon's moves at
the wild finalizer does not hold (the battle reloads them); the summary-screen move picker takes A, A for the
first move. The battle RNG is not reproducible between runs: in one CN run Blast Burn
KO'd the Blissey with a critical hit (the judge then says 'unclear' for D-1318), so `move` is not in the suite;
the D-1318 reading comes from the runs where the turn ended at the command menu (CN once, EN twice).

### 11. Open verify-in-game records (`emu_verify.py`, 2026-10-06)

`emu_harness.py verify [--case bigtext,never,statue:badge+misty,...] [--lang cn|en|both]` reaches the screen or
scene line that a translator's "check in game" record names, on the Chinese ROM and the English build, and
writes CN|EN pairs to `work/build/harness/verify/pairs/` (`<case>_<variant>.png`; message lines: top screen,
menus and apps: both screens) plus `report_*.json`. Run on build CRC32 405146C4 (all 20 cases, both ROMs,
6 min 36 s with `--jobs 14`); CN and EN behaved the same in every case.

New pieces:

- **`MsgLog`**: hooks the three MsgData readers (arm9 0x0200BB0C `ReadMsgDataIntoString`, 0x0200BB40
  `NewString_ReadMsgData`, 0x0200BB94). `NewMsgDataFromNarc` (0x0200BA98) stores the NARC id at MsgData +4 and
  the file at +6 in every mode, so each row is (narc, bank, id); a027 is NARC 27. Scripts, menus and apps (bag,
  Pokégear, move relearner, the New Game notice) all read their text this way, so "is this string ever shown on
  this screen" becomes a lookup. Found by disassembling the NPCMsg handler (ov1 0x021EE288 → 0x021EE448 →
  0x021EE658 → 0x0200BB0C). The English build patches `NewMsgDataFromNarc`'s first bytes (type forced), the
  +4/+6 fields are the same.
- `scene_line`: warp into the zone, `run_from_with` the label of the message command (with a few buffer
  commands first), press A and screenshot every page until the next command runs; `capture_message`,
  `static_refs` (commands of a script file that name a message id; SetVar only for vars a *MsgVar prints).
- `run_scene` / `play`: start any script (talk, `run_script`, `run_from_with`), answer menus, screenshot every
  distinct screen, with OpTrace and MsgLog; `hide_flags(zone)`: the test saves' people overflow the sprite table
  on Route 2, Route 3, Route 34 and Mt. Moon Square too (crash on entry, as Goldenrod, D-1547), so those lines run
  with the zone's hide flags set; on Routes 2/3 the player stands below a door (a trainer sees the first object's
  tile).

| record | what it asked | case | result |
|---|---|---|---|
| D-0541, D-0553, D-0571, D-0719, D-0744, D-0853, D-0903, D-0983 | SIZE-200% lines fit at 2x | bigtext (38 lines run from their message commands in the real maps) | all fit; 0314 #14, 0476 #85 printed by no command (rendered with `show_message`, fit) |
| D-0550, D-0746 | `---` placeholders shown in the scenes? | never | not printed (scene prints 139 → 141 and 101 → 99 → 102); no command names them |
| D-0504 | New Game notice width | notice | all five pages, timer and QR caption fit |
| D-0560 | Gym statue layout | statue (no badge / badge / flag 1042) | #6 / #7 / #53, same pages as the Chinese |
| D-0575 | who is the Bonsly trader | trade | object 1 (sprite 50, hiker-type), not Brock (object 7) |
| D-0622 | what Yes to 赞赏 does | tip | shows a WeChat tip QR code, then #31 |
| D-0623 | prize menu | prize | touch-button list, one line each, fits |
| D-0661 | Pal Park prompt | palpark | ENTER/INFO/EXIT menu follows; the added question fits |
| D-0762, D-0936 | Pokégear gift / Running Shoes giver | mom, lines | Mom gives the Running Shoes (only GiveRunningShoes); 0537 #8, 0542 #7 never printed |
| D-0781 | which situation prints 0044 #144 | nurse | Rocket costume (player state 3) at the nurse |
| D-0829 | berry tags 0243 shown? | berrybag | not read by the bag; no script uses the bank |
| D-0855 | what the seal is | seal | notice on a barrier, bg event (21,18) of zone 72 |
| D-0884 | Special Ball item/sprite | ball | ordinary Poké Ball sprite 87, no item |
| D-0955 | Alph hint lines | ruins, lines | puzzles read bank 0002, never 0073/0075; 0083 #0 statue line fits |
| D-1076 | psychic vs Magician | psychic | both versions say 魔术师 / Magician in the prompt; kept |
| D-1103 | 0123 #30 speaker; 0106 labels | elm, lines | script 4 used by no event (never shown); 0106 #95–97 fit |
| D-1138 | Move Reminder prompts | relearner, lines | the app reads bank 0736; 0626 #40 fixed to one line |
| D-1153 | which map spot shows #68/#117 | gearmap | Resort Zone and Route 48; fit |
| D-0880, D-1072 | trade species; scratch-off line | static | lines printed by no command; no Celebi/Milotic trade |
| D-0511, D-0518, D-0522, D-0913, D-1192 | – | – | **blocked** (screen not found; panel descriptions and battle bag paths not driven; content question; phone call) |

Suite: `verify` (SUITE_EXPECT: never → never_printed, statue and nurse → confirmed).

### 12. Text sweeps: read back what the screen shows (`emu_text.py`, `emu_sweeps.py`, item 5, 2026-10-06)

`emu_text.py` decodes a text window from a screenshot with the ROM's own font: the game prints 2bpp glyphs
from `a/0/1/6` at a fixed origin, one 16-px row per line, advancing by the width table, so the window's ink
(every pixel that is not the window background) parses exactly into glyphs (rows 1–14 compared, so ruled
panels don't disturb it; identical bitmaps such as O/● resolve to the letter). A decoded line is the text the
game printed, its rendered width, whether ink reaches the window's last column, and U+FFFD for pixels that
start no glyph (garble, a window drawn over the text). Lines are compared with the bank string (buffers
filled where known, otherwise any text; `{CLEAR}` repeats handled). English fonts only; CN runs give the
CN|EN pairs.

`emu_harness.py sweeps --sweep trainers|desc|battle [--ids] [--lang cn|en|both] [--jobs 6]` runs the work in
child processes (one emulator each, a field savestate reloaded per item); reports and screenshots in
`work/build/harness/sweeps/<sweep>/` (`report.json`, `<lang>/`, CN|EN `pairs/` of every EN row that is not
`ok`), per-child progress files so a dead child loses nothing; `--rejudge` re-reads the saved EN screenshots
after a decoder or bank change. Run on build CRC32 588D0B73 (bank fixes below included):

| sweep | what | coverage | result (EN) | time |
|---|---|---|---|---|
| trainers | `TrainerBattle id 0 0 0` for all 1023 trainers of trainers.json; intro read back; MsgLog gives the string (2#482 for all), class (a027/0720) and name (0719) the game read | 1023 / 1023 both ROMs | **all 1023 ok**; widest intro line 125 px of 216; no garble, no cut name (10-character compressed names fit). The rival (class 23, 8 trainers) prints "Redhead" alone: the test save's rival name is empty, CN the same | 10 min (16 jobs); rerun with `--jobs 8` under the 6-emulator cap: 18 min, same result |
| desc | bag: every item of items.json (582) in the Items pocket, cursor stepped through the pages, description panel (x 40, y 144, 200 px to the frame); summary skills page: ability description (top, x 8, 139 px to the divider) and the four move descriptions (bottom, x 136, 120 px), set with `edit_party_mon(moves=, ability=)` | 582 items, 902 moves, 327 abilities, both ROMs | moves 902 ok (widest 120 px), abilities 327 ok (widest 136 px), items 504 ok + **78 `past_panel`**: a line of 201–215 px runs into the bag frame (last letters hidden behind it), exactly QA's `line_past_frame` list (D-1534 counts 81; 3 of them are not obtainable). No blank panel, no garble | 4.4 min (16 jobs) |
| battle | 24 scripted battles (`BATTLES`: weather ×4, stat stages, poison/sleep/burn/paralysis/confusion, crit, no effect, not very effective, level-up + Exp. Share, Leftovers, Life Orb, Sitrus, Intimidate/Drizzle/Drought/Speed Boost, a foe's Intimidate, switching, fainting + forced switch, Master Ball catch, escape, a trainer battle won); every stable page of the battle window decoded and matched with the battle_string (or a027, trainer line 0718) read before it | 87 of 2858 battle_string ids read, 79 printed and checked; 626 pages | **all 24 ok**: 614 pages match, 12 covered by the level-up stats window (by design) | 3 min (16 jobs) |

Issues found and fixed (before → after, rebuilt and swept again):
- 2#32 `{nick} wants to learn {move}...` cut at the window edge ('Maximilian wants to learn DragonBreath..'), and
  page 2 'Should another move be forgotten to' ran its 'o' under the YES/NO prompt icons (x 211–228) →
  `{nick} wants to learn{NEWLINE}{move}...{SCROLL}Should another move be forgotten{NEWLINE}to make room for {move}?`.
- 2#73 'Would you like to forfeit the match and' (208 px) under the prompt icons → 'Would you like to forfeit the' /
  'match and quit now?'.
- 1#1464–1466 'The wild Kangarooey took the Future Sig' cut → 'took the{NEWLINE}{move} attack!' like #1467.

QA rules added (`qa_config.json`, `qa.py`): `prompt_icon_overlap` (battle category, `prompt_px` 195: the lines of
the view that ends with `{VAR:0200:..}`); battle_string buffer widths for {VAR:0107} move and {VAR:0106} ability
(48/72 px) and {VAR:010C} nickname (54/60): QA had measured the battle's move buffer as 42/48 px. 56 more battle
strings now warn `line_may_overflow` (a long nickname with a 12-character move): D-1566 (proposal: a break
before the move buffer, as 1#1467). Numbers in battle text use the full-width digit codes (7–8 px), as in the
Chinese ROM: D-1567. Seen once: the player's Pokémon hit by a wild foe's Future Sight got the "The wild"
string (1#1465): D-1568 (CN not seen).

Not covered: the HP-box name plates (species/nickname ≤ 10 characters, QA-enforced), contest and Pokéathlon
text, battle bag item use, double-battle target prompts; most of the 2858 battle_string ids need specific
moves, abilities or items (a scenario per family; add rows to `BATTLES`).

Harness pieces from this round: `encode_pokemon(ability=)` (block B +0x1A, see the correction under "Integrated
from the UI hunt agent"); a page watcher for the battle window (`PageWatch`: a page counts when unchanged for 3 looks); `BattleLog` (battle_string and
a027 reads with frames); `run_child` finds `RESULT` mid-line (DeSmuME sometimes prints without a newline).

**guide0107 `electrode` flake (fixed).** The suite once failed `electrode` on the Chinese ROM under load: in the
lose variant the doomed lead (Splash, 1 HP) let the Lv70 Electrode act first, and its moves are Explosion, Zap
Cannon, Gyro Ball and Mirror Coat. When the battle RNG picked Explosion before a damaging move, both sides
fainted, the game counted it as a win (flag 1241 set, ball gone, as the guide notes) and the judge said
'contradicted' (the failed run's screenshot shows the ball gone after the "loss"). The wild Pokémon's PID is
identical across runs (main RNG reproducible), but the battle RNG is not (see section 10), so the outcome
depended on the run. The lose variant now uses `memento_party`: a Lv100 Ninjask that knows only Memento leads
and every other party Pokémon has 0 HP, so the player's side faints on turn 1 before the Electrode moves; the
loss no longer depends on any random choice. Observed: 8 CN runs of the old variant all passed (the flake is
rare); the new variant is confirmed on both ROMs, alone (4 runs × both ROMs × both variants on 2026-10-06, all confirmed) and in the full suite.

**Child processes (2026-10-06, coordinator request).** A calendar child (`battle@keldeo:day`, stuck in a battle
it could not flee) kept running at 100 % CPU for about 4 hours after its parent was gone. Now every fan-out
goes through `spawn()`:
- Per-child wall-clock timeout. It starts when the child gets an emulator slot; on expiry SIGTERM, then
  SIGKILL of the child's process group; `spawn` raises `ChildTimeout` and the case gets verdict `timeout`
  (sweep rows: status `timeout`), so a suite run fails instead of hanging. Sweep children get
  600 s + a per-item budget (trainers 20 s, descriptions 15 s, battles 300 s).
- Process groups. A top-level parent starts each child in its own session; the child's own children stay in
  that group, so stopping a child stops its whole tree, and the group is SIGKILLed once the child has exited.
- Parent exit. All tracked children are stopped at exit (atexit) and on SIGINT/SIGTERM/SIGHUP. Run as a
  script, `emu_harness.py` registers itself as the module `emu_harness`, so the recipe modules
  (`import emu_harness as E`) share the one child registry; before that fix SIGINT/SIGTERM on a `sweeps`
  parent left its children running (they used a second copy of the module).
- Orphans. A child whose parent died (also by SIGKILL) stops itself within 5 s (watchdog thread).
- Checked on 2026-10-06 with a `sweeps --sweep trainers --ids 1-60 --lang both --jobs 2` parent: `kill -9`,
  `-INT`, `-TERM` and `-HUP` of the parent each left no emu_harness process after 12 s; `spawn(..., timeout=25)`
  on a 59-trainer child raised `ChildTimeout` after 25 s and left nothing behind.
- Live emulators are capped machine-wide at `EMU_HARNESS_MAX_EMULATORS` (default 6; lock files in
  `$TMPDIR/emu_harness_slots`), so a big fan-out queues instead of opening 20 emulators. `--jobs` defaults:
  4 for suite, guide0107/0813, calendar; 6 for sweeps.
- `emu_harness.py cleanup` lists running `python … emu_harness.py` processes (orphans marked; test files and
  editors that only name the file are not listed) and removes slot markers of dead children; `--kill` stops
  the orphans, `--kill --all` every one (also another session's runs: check the list first).

Full suite after these changes (2026-10-06, `suite --jobs 4`, 12 checks × 2 ROMs, build CRC32 588D0B73): all 24
pass in 19 min 55 s; no emu_harness process left afterwards.

### 13. Open points: Arceus in battle, wild Thief, Rockruff after a battle, Primal orbs, Pal Park prize (`emu_open.py`, item 6, 2026-10-06)

`emu_harness.py open [--case arceus,thief,rockruff,primal,palpark[:variant+...]] [--lang cn|en|both]` (module
`work/tools/emu_open.py`, one child per case/variant/ROM, `--jobs 4`). Every case ran on the Chinese ROM and the English
build (CRC32 of `origin_hg_v4.0.3_en_wip.nds` of Oct 6 06:55) with identical verdicts; 44 runs in one `--lang both` call.
Report `work/build/harness/open/report_all_both.json`; screenshots and battle-message sheets (`*_pages.png`) in
`work/build/harness/open/<cn|en>/`.

**Wild held items and moves (harness finding).** The wild finalizer's Pokémon (`WildLog`, r2) is a temporary copy: the
BattleSetup party copy already exists when the finalizer ends, and about 130 frames later the battle overlay copies
that party twice (memcpy from ~0x02215000). So the earlier Thief control, which gave the item at the finalizer, never
reached the battle. `emu_open.wild_battle(h, species, level, item=, moves=, form=)` starts a scripted `WildBattle` and,
right after the finalizer, rewrites every RAM copy with the wild Pokémon's PID (`pid_copies`); observed: all four copies
in battle hold the item and the moves, and the foe uses the move. `encode_pokemon(moves=)` replaces only the slots it
is given: use `emu_open.moveset([...], [...])` (pads to four slots) for a fixed moveset. The scripted `WildBattle`
does roll held items itself: a wild Shuckle held Berry Juice, a Miltank Moomoo Milk (personal item 1 = item 2).
No plain `BattleMon` struct with the moves was found in RAM (searched by PID and by the move ids), so the battle's own
type field was not read; types come from the INFO panel and from effectiveness messages instead.

**Battle message events.** `battle_events(ml)` groups the MsgLog battle_string reads per "used" message (1#2179 own,
#2180 wild, #2181 trainer's), with the move name read from a027 bank 739 and the effectiveness: 2#74 super, 2#75 not
very, 1#8–39 the targeted forms, 1#288–291 no effect, 1#292–295 missed.

| point | method (case) | result (both ROMs) |
|---|---|---|
| 1. Arceus in-battle type (D-1501) | arceus: generator Arceus Lv100, Plate through Bag → Give (stored form as in round 2), Splash + Judgment; scripted wild foe Lv50 with one probe move. flame: Tangela / Water Gun; splash: Magmar / ThunderShock; zap: Psyduck / Earthquake (Mud-Slap made Judgment miss once); dread: Drowzee / Karate Chop; fist (control): Rattata / Gust | **observed, follows the Plate**: INFO panel type Fire / Water / Electric / Dark / Fighting with Multitype and the Plate; every probe super effective (as for the Plate type; the personal entry of the stored form, Water / Grass / Psychic / Fairy, would give not very effective or neutral); Judgment super effective on every foe (Fire, Water, Electric, Dark, Fighting). The stored-form mismatch has no in-battle effect. |
| 2. Thief in a wild battle | thief: Chansey Lv100 (Thief, Seismic Toss, no item); miltank: wild Miltank Lv20 with the game's own Moomoo Milk; eviolite: wild Rattata Lv20 with an Eviolite in its copies; control: Miltank, Seismic Toss only | **observed**: "stole" (1#1432) both times; after the win the thief **holds** the item **and the Bag has one more** (Moomoo Milk +1, Eviolite +1); control: Bag unchanged, nothing held. Trainer battles (section 3) only leave it on the thief: the wild case duplicates the item (D-1569, hack-finding). |
| 3. Rockruff after a battle win (D-1486) | rockruff: Rockruff Lv24 with exp 15,624 (Lv25 = 15,625, Medium Fast; `with_exp` edits block A +8), Tackle only; scripted wild Rattata Lv2 / Pidgey Lv3 / Sentret Lv2; only A pressed (B would cancel the evolution); hook 0x02074B0E | **observed**: evolves after the battle at Lv25; byte written 0 and Midday Form at 12:00 ×3 and 15:00 ×3; 18:00 → 2 Dusk, 22:00 → 1 Midnight. With the Rare Candy runs: 15 of 15 daytime evolutions Midday. |
| 4. Nanab Berry, Pal Park prize | palpark fixed: Friday 12:00, $50,000, 99 Master Balls, Ninjask lead; talk to the receptionist (zone 479, object 6), take part → Fixed Catch → Yes; catch on the field grass. palpark stocked: the same after six Pokémon (Rattata, Pidgey, Spearow, Sentret, Raticate, Pidgeotto) are written into save array 28 (the GBA-migrated Pokémon, `SaveArray_Get(save, 28)` = 0x0202756C, 6 × 236 bytes) | fixed: real entry (809 #46, #48, $10,000 taken, warp), countdown and `PalParkAction 0` run (file 12 script 2), stocked species 0 ×6; six wild catches (Master Balls 98 → 93): caught flags at 0x021D3214 +0x30 stay 0, file 12 script 3 never runs, no score, no prize. **BLOCKED for Fixed Catch**: the flags are set only by 0x02054C38 for the entry the show's own step encounter picked (0x02054B8C), which needs stocked entries (loaded by 0x02054A70 from array 28; 0x0205493C inits). stocked: the normal show runs (no Fixed Catch prompt), stocked Pokémon appear through the step encounter (not the wild finalizer), each catch sets a flag (Caterpie / Weedle never appeared on the field grass, so field species were used), after the sixth script 3 runs, warp to the reception, score 320 (file 809 script 2), prize routine L4435 → L4974 → one Berry (Pecha CN, Cheri EN, random). The 3,300–3,499 tier (Nanab 1 in 7, L5171) was not reached: the score was not steered. D-1570; site note for Nanab updated (normal show with GBA-migrated Pokémon only). |
| 5. Primal Groudon/Kyogre | primal: own Groudon / Kyogre Lv100 (Splash) vs wild Rattata; wild Groudon / Kyogre Lv70 with the orb in their copies vs Ninjask | **observed**: the Red / Blue Orb's Bag menu has no Give (only Move/Return), so the orb was set directly; no Primal (1#1666–1671) or Mega string read, battle copies keep form 0, party form 0 afterwards (D-1571). |

Suite (`SUITE_EXPECT`): arceus flame/zap `plate_type`, thief miltank `kept`, rockruff 12a `midday` and 18 `dusk`, primal
groudon_own `no_reversion` (palpark is too slow for the suite: 6–10 min per run). Full suite with `open` added
(2026-10-06, `suite --jobs 4`, 13 checks × 2 ROMs): all 26 pass in 22 min 6 s; `open` about 2 min per ROM.

### 14. The verify queue of the 2026-10-06 triage (`emu_vqueue.py`, 2026-10-06)

`emu_harness.py vqueue [--case ssanne_story,new_captain,...[:variant+...]] [--lang cn|en|both] [--jobs 4]` (module
`work/tools/emu_vqueue.py`) answers the open records of the triage's verify bucket (D). One child per case, variant
and ROM (`run_child`, 2400 s timeout); reports `work/build/harness/verifyqueue/report_<cases>[_both].json`,
screenshots and battle-message sheets in `work/build/harness/verifyqueue/<cn|en>/`. All cases were rerun on the
Chinese ROM and the English build CRC32 576E1E55 with the same verdicts on both.

| record | question | case (method) | result |
|---|---|---|---|
| D-1549 | how a normal first voyage reaches HM01 and the party | ssanne_story: Vermilion arrival flags, every S.S. Anne flag/var at its new-game value, real boarding (zone 387 sailor, `ScrCmd_723`), arrival scene and speech, a write watch on flag 1440's byte; variants oldboy_first / honey_first / blue_first | **observed**: no write to 1440 (only 156 @6350 sets it, at the hijack), so the voyage runs in the party state: Captain 253#62, no HM01. Old boy (sets 1424) then Honey → announcement 255#18, Water Stone, var 0x40A4 = 3, hall trigger speech. Honey first or Blue first (sets 1423) → nothing ever starts the party, exit blocked: softlock (hack bug) |
| D-1549 | second HM01 source; Cut without HM01 | new_captain (zone 308 object 14, without / with HM01); cut_yes (Route 10 tree, Cascade Badge, Splash-only party, no HM01) | **observed**: '1000th visitor' line 69 + HM01 without one, line 68 with one; the tree is cut (flag 16 set, object gone) |
| D-0905 | is the author's notice 0065#62 reachable | notice: Goodshow at 0x40A2 = 13, flag 106 set / clear | **unreachable**: #51 with the starter flag, #62 only without it |
| D-1475 | which shop the 0573#46 sign labels | sign: read it (MsgLog), photograph the street | the sign beside the Flower Shop door |
| D-0501 | context of 0272 #46 / #54 | banner: zone 385, SAVE window | #46 'Boot Camp Ruins' on the save window; #54 used by no map header |
| D-1499 | B at the memory-rematch Doubles menu | rematch_b: file 78 from L832, B | **exits**: B returns 7 ('Never mind'), script to 813, no TrainerBattle |
| D-1377 | traded Pokémon Exp. | exp: Mewtwo Lv50 vs wild Chansey Lv10, own OT / other OT (read back, checksum valid) | 62 Exp. both, 2#29 both: no boost |
| D-1350 | Bounce one-turn? | probe bounce / fly (control), wild Shuckle with Splash | **one turn**: 'used Bounce!', no 'sprang up' (1#734), no miss, the foe acts the same turn; Fly prints 1#714 and strikes next turn |
| D-1568 | 'The wild' string on the player's Pokémon | probe fs_foe (wild Mewtwo's Future Sight on the player's Chansey) / fs_own | foe's Future Sight on the player's Pokémon → 1#1465 ('The wild …') on **both ROMs**; the player's on the wild one → 1#1464: the string follows the user's side (game logic) |
| D-1461 | Soak / Protean type-change message | probe soak (wild Geodude) / protean (Greninja, Quick Attack) | **reproduced**: Soak → 1#1213 with the move name in the type slot; Protean → 1#1212 with the move name |
| D-1191 | which follower reacts in the Celadon Gym | follow: Venonat / Tangela / Pikachu, three talks each | Tangela 0258#725; Venonat and Pikachu 0258#205 |
| D-1458 | R/L on the stats page by button mode | buttons: every Options row once (options word diff); bits 8–9 forced to 0/1/2, R then L | no BUTTON MODE row; rows flip bits 0, 6, 9 (BATTLE BG = bit 9); with bits 8–9 = 0/1/2, R does nothing, L opens the panel every time |
| D-0522 | battle bag NEXT, 'Shrouded in mist!', APPEAL | battlebag: restore pocket with two pages, Guard Spec. used, party → CHECK MOVES → move detail | 0005 #21, #35 and 0006 #57 never read: pages use arrows and '2/2'; Guard Spec. prints battle_string 2#26 / 2#139; the move-detail page has no APPEAL |
| D-0521 | Pokédex Front/Back, #179, language labels | dex: No. 421, every tab, forms-page buttons | #164/#165 are the FORMS tab's front/back sprite entries; #179 the DATA tab's MOVE header; #2–7 read on no tab |
| D-0518 | INFO panel description width/lines | infopanel: Tyranitar (Sand Stream), INFO, RIGHT, A | popup of three ~198 px lines; a 201 px line lost its period → bank 0 lines ≥ 200 px shortened |

New pieces: `FlagWatch` (a write hook on one flag's byte: frame, PC, bit after), `board()` (the real ferry boarding
with timed walks, since `position()` lags after `ScrCmd_723`), `set_ot` (OT ID edit with the checksum and
encryption redone). Suite (`SUITE_EXPECT`): cut_yes `cut`, new_captain `confirmed`, notice `unreachable`,
rematch_b `exits`, follow (Venonat 205, Tangela 725).

Found on the way: on the summary's SKILLS panel (L on the stats page) the English 'Sp. Atk' label covers the first
IV digit (D-1574).

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

- `position()` also lags after `ScrCmd_723` (the ferry boarding); the S.S. Anne recipe uses timed walks.
- A Multi Battle with an AI partner can't simply be lost with a weak party (the partner fights on); the
  clash recipe stops at the first battle.
- Menu navigation is timing-based (fixed waits and touch coordinates). It worked in every run here, but a
  new screen or a different save can need different waits; each new recipe needs one look at its
  screenshots. There is no screen recognition yet, only the overlay-2 check for "in the field".
- Teleporting through Continue skips on-entry map scripts, and the new map's NPCs are whatever the map
  spawns by itself. The live player position is not read (the Pal Park start tile could not be checked).
- The pinned clock does not advance.
- `generate_pokemon` overwrites party slot 6 when the party is full; the generator reuses one PID.
- Wild-battle recipes depend on random encounters (single or double battle, CN vs EN differ), so screen
  pairs of battles are not pixel-identical between runs.
- Not built: contests. (Trainer battles, scripted NPC state, winning battles and the Pal Park show: see 2b, 7, 13.)

## Proposal: an automated regression suite (first version built: `suite`, see 5b)

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

## Texture bounds regressions: Rocket HQ, Five Island, Seven Island and Bell Tower

`texture-bounds` runs four permanent checks for the invalid overworld texture-frame lookup at
ARM9 `0202467C` / `02024696`. DeSmuME tolerates the original null read, so these tests use read-only
instruction hooks to prove that the failing path was exercised. They do not infer safety from a
responsive screenshot alone. The original behavior must produce the expected out-of-range request
and a null load; the fixed behavior must still exercise that request, retain valid texture updates,
and produce **zero** null loads. Unexpected locations, branch bytes or hook failures fail the run.

The fix is `work/patches/overworld-texture-frame-bounds` (one byte, `08 D2` -> `2C D2`); a normal build has it,
`build.py --without overworld-texture-frame-bounds` does not. Run from the repository root. The primary checkout supplies the existing virtualenv,
ROM and raw 512 KiB battery save; use absolute input paths because the emulator uses a private working
directory. No downloads are needed. Substitute your local paths below, and choose new output folders:

```sh
<primary-checkout>/.venv/bin/python work/tools/emu_harness.py texture-bounds \
  --rom <primary-checkout>/work/rom/origin_v4.0.3_cn.nds \
  --sav <absolute-path-to-raw-save.sav> \
  --out work/build/texture-bounds-original --case all --expect original

<primary-checkout>/.venv/bin/python work/tools/emu_harness.py texture-bounds \
  --rom <absolute-path-to-fixed-build.nds> \
  --sav <absolute-path-to-the-same-raw-save.sav> \
  --out work/build/texture-bounds-fixed --case all --expect fixed
```

`--case` accepts `all` or a comma-separated subset of `rocket_hq,five_island,seven_island,bell_tower`.
Both commands return zero only when every requested expectation passes. `--expect original` means
successful reproduction of the defect, not that the original ROM is safe. A fresh `report.json`
contains input SHA-256 hashes, setup flag values, target and observed positions, bounded register
samples, request/null-load counters, screenshot paths, pass/fail reasons and an input-unchanged check.
Existing reports are not overwritten. Screenshots, reports and any emulator states stay in ignored
`work/build/`; do not commit input ROMs or saves.

| Case | Map and position | Explicit RAM setup | Expected bad texture index/count |
|---|---|---|---|
| `rocket_hq` | 247 (17,4) | Clear hide flag355 | 4 / 1 |
| `five_island` | 154 (104,54) | Clear hide flag2173 | 4 / 1 |
| `seven_island` | 163 (245,104) | Clear hide flag2198 | 11 / 1 |
| `bell_tower` | 340 (15,17) | Clear hide flag1140 | 15 / 1 |

These are deterministic synthetic visibility fixtures. They import an existing save, capture a
private baseline state from the ROM under test, and restore that same baseline before every case.
Each case changes the listed visibility flag in disposable emulator RAM and uses the game's
scripted map warp. This prevents earlier cases' flag or map-script changes carrying into later
cases; it does not claim to complete each location's story prerequisite. Bell Tower in particular requires the
visibility setup for the supplied saves. The ROM and original battery file are never intentionally
edited or exported over. This checks the shared bounds guard across four known failing resources;
it does not replace end-to-end story playthroughs or reproduce the full reporter's travel route.
