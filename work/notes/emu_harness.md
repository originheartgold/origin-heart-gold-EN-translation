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
    .venv/bin/python work/tools/emu_harness.py suite [--only unown,palpark,arceus,evolve,dex,skitty,guide0107,guide0813] [--jobs 10]
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
point, so the control needs a different way to give a wild Pokémon an item.

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
- **`emu_harness.py suite [--only ...] [--jobs 10]`**: runs each check on the Chinese ROM and the English
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

  Result (observed): all 10 (5 checks × 2 ROMs) pass, 2 min 13 s wall time with `--jobs 10`. A first run
  before the battery fix failed unown (both ROMs) and palpark (English) on the shared battery file, and one
  rockruff_12 run did not evolve.
  With `skitty` added (2026-10-05): all 12 pass, 2 min 10 s with `--jobs 10`.
  With `guide0107` added (2026-10-06): all 14 pass, 3 min 7 s with `--jobs 14`.
  With `guide0813` added (2026-10-06): all 16 pass, 5 min 17 s with `--jobs 16`.

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
| 01 Victory Road Electrode: fleeing (probably) removes it; losing keeps it | electrode: Ninjask Lv100 flees → flag 1241 set, ball gone; doomed party loses → Pokémon Center, ball still there | **confirmed** (an Electrode that explodes counts as a win too) |
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
- Not built: trainer battles (Thief test), talking to NPCs with scripted state (Pal Park prize), winning a
  battle, contests.

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
