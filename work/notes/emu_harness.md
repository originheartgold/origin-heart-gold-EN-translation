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

## Pal Park weekday table (D-1484): first try, not conclusive

`wild --map 109 --x 16 --y 14 --clock 2026-10-09T12:00:00` (a Friday) produced only 2 encounters in 3000
steps: Makuhita (296) and Numel (322). Of records 141–148 only 146 (= 142 + 5 − 1, the D-1484 formula for
Friday) contains both, which fits the finding, but two samples are not enough and the start tile was not
checked (grass tiles from the land data: x 11–29, y 13–15 in the first chunk; the field screenshot did not
show the player clearly). Next: confirm the position from the screenshot, pick a tile in the middle of the
grass, run 20+ encounters on a Friday and on a Sunday (expect record 141, Cerulean Cave's table).

## Extending it to the other open points

- **Petilil + Black Belt by day, then Sun Stone (D-1485).** `generate_pokemon(548, level=N, item=241)`
  with `set_clock(...12:00)`. Level-up trigger still needed: either give a Rare Candy (bag via
  `SaveFile`/RAM, then drive the bag menu with `press`/`touch`) or win a battle. Expected (static): a
  Petilil with form 1 (`party()[5]["form"] == 1`), and a Sun Stone then gives species 549 form 1. Hook the
  evolution setup 0x02074048/0x02074148 and completion 0x02074AD2 to log the target species/form directly.
- **Rockruff daytime form (D-1486).** `generate_pokemon(744, level=24)`, clock 12:00, level up; read
  `party()[5]["form"]`. The form comes from an unwritten stack byte (0x02074AE4, sp+0xC), so repeat from a
  savestate with different preceding actions; an exec hook at 0x02074AE4 can log the byte each time.
- **Pal Park Friday table (D-1484).** See above; also hook the bank getter 0x0203A7B0 (return value) to log
  the record number directly. Fixed Catch mode (script file 809) may set state the plain walk doesn't.
- **Thief keeps the item (Air Balloon / Eviolite / Weakness Policy / Salac).** Needs a trainer battle whose
  Pokémon holds one: teleport next to such a trainer (trainer data a/0/5/5 + events), give the lead Thief
  via the generator's move rows (7–10, untested), fight, then check `party()` items after the battle.
- **Pal Park Fixed Catch prize (Nanab).** Script-driven: teleport to the Pal Park counter, set the vars the
  prize script checks (`set_var`), talk (`press("A")`), and compare the bag before and after.

Limits: teleporting skips on-entry map scripts; the clock doesn't advance while pinned; RUN touch and menu
key sequences are timing-based (they worked in every run here, but a new screen needs a screenshot check);
the generator overwrites party slot 6 when the party is full.
