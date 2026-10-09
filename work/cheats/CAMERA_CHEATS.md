# Origin HeartGold camera cheats (Action Replay)

Action Replay codes for the overworld camera in Origin HeartGold: widescreen, real 3D inside buildings,
the game's built-in camera presets, and a fully custom camera. Every address below was read out of the
game's own code and tested in an emulator (see [How this was verified](#how-this-was-verified)).

**Works on:** English v1.0.0-rc5 and v1.0.0-rc6, and the untouched Chinese 起源心金 v4.0.3.
These builds have identical camera code and tables. **Doesn't work on:** vanilla HeartGold, Sacred Gold or
other hacks. Their addresses differ (see [Why the US code doesn't work in Origin](#why-the-us-code-doesnt-work-in-origin)).

The ready-made cheat list is `origin-heartgold-rc5-widescreen.xml` in this folder.

---

## 1. Ready-to-use codes

### Widescreen 16:9: ON / OFF

```
Widescreen ON (16:9)        Widescreen OFF (back to 4:3)
52023640 00001555           52023640 00001C72
02023640 00001C72           02023640 00001555
D2000000 00000000           D2000000 00000000
```

Set the emulator's top screen to 16:9 (ON) or 4:3 (OFF). Turn on only one of the two at a time. The change
applies the next time a camera is built: load the save with the code already on, or go through a door.

### Real 3D inside buildings (recommended for the melonDS Vulkan problem)

Almost every interior (305 of 540 maps: houses, Pokémon Centers, marts, labs) uses a **flat (orthographic)
camera**. That is the "2D-looking" view. These codes switch only those interiors to a real 3D camera.
Routes, towns, caves and the gyms with their own camera angles are not touched.

**A. Same framing as the original, but real 3D.** It looks almost identical to the normal game, with slight
depth on walls and furniture:

```
521E9C54 B084B5F8
02205448 02810000
022055D4 02810000
D2000000 00000000
```

**B. Indoors use the normal outdoor camera.** This is what the US "Normal 3D" code (value 0) does, but
only inside buildings:

```
521E9C54 B084B5F8
0220543C 0029AEC1
02205440 0000DD62
02205448 05C10000
02205450 004B0000
022055C8 0029AEC1
022055CC 0000DD62
022055D4 05C10000
022055DC 004B0000
D2000000 00000000
```

To turn either off: disable the code and go through any door. The game reloads the original camera table
on every map change.

> These were tested in DeSmuME, not in melonDS. They replace the flat camera with a 3D one, which is what
> fixed the Vulkan problem in Sacred Gold, but please confirm in melonDS.

### Force one camera preset everywhere (port of the US "Normal 3D" code)

```
621CFF30 00000000
B21CFF30 00000000
20001308 000000XX
D2000000 00000000
```

`XX` picks one of the game's 17 camera presets, `00` to `10` (hex). See the [preset table](#4-the-17-camera-presets).
Useful values:

| XX | Look |
|---|---|
| `00` | the normal outdoor camera, everywhere (= US "Normal 3D") |
| `02` | same distance, lower angle (40° instead of 49°) (= US "Slightly lower like Gen 5") |
| `06` | slightly lower (45°), sees a bit further |
| `09` | steeper, more top-down (60°) |
| `0A` | close-up with a wide lens (strong perspective) |
| `03` | very low (19°), cinematic. Shows a lot of map edge |

This forces the preset on **every** map, including gyms and towers that normally have their own angle.
For interiors only, use the codes above.

### Custom camera (tune it yourself)

This template copies the normal outdoor camera into preset 6 (which no map uses) and forces preset 6
everywhere. Change the commented values (see [Tuning the camera](#5-tuning-the-camera)):

```
521E9C54 B084B5F8
02205484 0029AEC1   <- distance (zoom)
02205488 0000DD62   <- tilt (look-down angle)
02205490 05C10000   <- field of view (first 4 digits) + 3D/flat (last 4 digits)
02205494 00096000   <- near clip
02205498 004B0000   <- far clip (draw distance)
0220549C 00000000   <- look-at shift left/right
022054A0 00000000   <- look-at shift up/down
022054A4 00000000   <- look-at shift forward/back
D2000000 00000000
621CFF30 00000000
B21CFF30 00000000
20001308 00000006
D2000000 00000000
```

(Leave out the `<- …` notes when you type the code in.) Three tested examples. Replace the matching lines:

| Example | Line(s) to change |
|---|---|
| Lower "Gen 5" angle, 35°, with more draw distance | `02205488 0000E71C`, `02205498 005DC000` |
| Zoomed out ~20% | `02205484 00320000`, `02205498 005DC000` |
| Wider lens (20° instead of 16°) | `02205490 071C0000` |
| 45° tilt | `02205488 0000E000` |

To get your normal camera back, disable the code and go through a door.

---

## 2. How the US code works, line by line

The US HeartGold code from the DeadSkullzJr list:

```
621D10EC 00000000   if the 32-bit value at 0x021D10EC is not 0 ...
B21D10EC 00000000   ... load that value as the "offset" (it is a pointer)
20001218 00000000   write 1 byte to offset + 0x1218: the value written is the camera preset
D2000000 00000000   end of code, reset the offset
```

- `0x021D10EC` holds a pointer into the save data in RAM (the play-time counter's pointer to the
  play-time field). It is 0 until a save is loaded, which is why the code checks for 0 first.
- From that pointer, `+0x1218` lands on one byte in the "current location" save block (the same block
  that stores your map and position). That byte is **the camera preset of the current map**.
- Every time you enter a map, the game copies the map's own preset (from its map header) into that byte.
  A few frames later the field camera is built from it. The cheat rewrites the byte every frame, so the
  camera is built from your value instead.
- The value is an index into a table of 17 camera presets. The "last character of the second-last
  line" that changes the view is that index.

## 3. Why the US code doesn't work in Origin

Origin is built on the **Japanese** HeartGold and enlarges the save, so both parts of the code move:

| | US HeartGold | Origin (rc5) |
|---|---|---|
| play-time pointer | `0x021D10EC` | `0x021CFF30` |
| location save block (from the save start) | `0x1234` | `0x1324` (+0xC8: the hack's bigger bag) |
| pointer → camera byte | `+0x1218` | `+0x1308` |

In Origin, `0x021D10EC` holds unrelated data that isn't a pointer, so the US code's write lands outside
RAM and nothing happens. Don't use the US code on Origin; use the port above. The preset table itself is
byte-for-byte the same as US HeartGold, so preset numbers mean the same thing in both games.

## 4. The 17 camera presets

From the game's camera table (overlay 1, `0x022053AC`, 0x24 bytes per preset). "Tilt" is how far the
camera looks down. FOV is the full vertical angle.

| Preset | Type | Distance | Tilt | FOV | Clip near–far | Look-at shift (up, fwd) | Table row | Used by |
|---|---|---|---|---|---|---|---|---|
|  0 (`00`) | 3D | 667 | 49° | 16° | 150–1200 | 0, 0 | `022053AC` | 216 maps: routes, towns, caves, most outdoor areas |
|  1 (`01`) | 3D | 404 | 40° | 27° | 134–1200 | 37, −15 | `022053D0` | Violet Gym |
|  2 (`02`) | 3D | 667 | 40° | 16° | 150–1200 | 0, 0 | `022053F4` | Goldenrod Gym |
|  3 (`03`) | 3D | 667 | 19° | 16° | 150–1200 | 30.6, −12 | `02205418` | Lighthouse exterior, Celadon Condominiums roof |
|  4 (`04`) | **flat** | 1564 | 50° | 7° | 150–1735 | 0, 0 | `0220543C` | 305 maps: nearly all interiors |
|  5 (`05`) | 3D | 466 | 48° | 24° | 150–1160 | 0, −24 | `02205460` | Azalea Gym |
|  6 (`06`) | 3D | 667 | 45° | 16° | 150–1500 | 0, 0 | `02205484` | no map (used for the custom camera) |
|  7 (`07`) | 3D | 667 | 42° | 16° | 150–1200 | 23.8, −22.6 | `022054A8` | Pokéathlon Dome 2F |
|  8 (`08`) | 3D | 515 | 55° | 21° | 150–900 | 0, 0 | `022054CC` | Battle Frontier, Frontier Access |
|  9 (`09`) | 3D | 668 | 60° | 16° | 150–1200 | 0, 0 | `022054F0` | Vermilion Gym |
| 10 (`0A`) | 3D | 317 | 46° | 35° | 150–1700 | 12.4, −37.8 | `02205514` | Whirl Islands B3F |
| 11 (`0B`) | 3D | 534 | 40° | 20° | 150–1200 | −8, 0 | `02205538` | no map |
| 12 (`0C`) | 3D | 667 | 45° | 16° | 150–1700 | 0, −32 | `0220555C` | Whirl Islands, Lugia's cave |
| 13 (`0D`) | 3D | 667 | 19° | 16° | 150–1700 | 30.6, −30 | `02205580` | Bell Tower roof |
| 14 (`0E`) | 3D | 667 | 61° | 16° | 150–1200 | 0, 0 | `022055A4` | Fuchsia Gym |
| 15 (`0F`) | **flat** | 1564 | 50° | 7° | 150–1735 | 0, −46 | `022055C8` | Ecruteak Dance Theater |
| 16 (`10`) | 3D | 667 | 59° | 16° | 150–900 | 0, 0 | `022055EC` | Battle Tower and the four Frontier facilities |

Values above `10` (16) are invalid: the game reads past the end of the table.

## 5. Tuning the camera

Each preset row is 0x24 bytes. Offsets are from the row address in the table above:

| Offset | Size | Field | Encoding |
|---|---|---|---|
| +0x00 | 32-bit | distance (zoom) | fixed point: value = units × 4096 (`0x1000` = 1.0). Bigger = further away |
| +0x04 | 16-bit | tilt (pitch) | angle: 0x10000 = 360°. Value = 65536 − degrees_down × 182.04 |
| +0x06 | 16-bit | yaw (turn) | same unit. Keep 0: turning the camera makes the D-pad feel rotated |
| +0x08 | 16-bit | roll | keep 0 |
| +0x0C | 16-bit | projection | `0000` = 3D (perspective), `0001` = flat (orthographic) |
| +0x0E | 16-bit | field of view | **half** the vertical angle, same angle unit: value = full_FOV_degrees × 91.02 |
| +0x10 | 32-bit | near clip | fixed point (×4096) |
| +0x14 | 32-bit | far clip / draw distance | fixed point (×4096) |
| +0x18 | 32-bit | look-at shift X (left/right) | fixed point, signed (negative: `FFFFFFFF` − n + 1) |
| +0x1C | 32-bit | look-at shift Y (up/down) | fixed point, signed |
| +0x20 | 32-bit | look-at shift Z (forward/back) | fixed point, signed |

The 32-bit word at +0x0C holds both projection and FOV: `FFFF PPPP` = FOV (upper 4 digits), projection
(lower 4 digits). The word at +0x04 holds tilt in the lower 4 digits and yaw in the upper 4 (keep `0000`).

**Quick conversions**

| Tilt (looking down) | 30° | 35° | 40° | 45° | 49° (normal) | 55° | 60° |
|---|---|---|---|---|---|---|---|
| value | `EAAB` | `E71C` | `E38E` | `E000` | `DD62` | `D8E4` | `D555` |

| FOV (full) | 16° (normal) | 20° | 24° | 30° |
|---|---|---|---|---|
| value | `05C1` | `071C` | `0889` | `0AAB` |

| Distance / clip | 500 | 667 (normal) | 800 | 1000 | 1200 | 1500 | 2000 |
|---|---|---|---|---|---|---|---|
| value | `001F4000` | `0029AEC1` | `00320000` | `003E8000` | `004B0000` | `005DC000` | `007D0000` |

**Tips**

- Lower tilt or zooming out shows more of the map. Raise the far clip as well (e.g. `005DC000`), or distant
  ground gets cut off.
- The game only loads the map blocks around you. Very low angles or big zoom-outs show the edge of the
  loaded area, and NPCs pop in late. Presets `03`/`0D` and the 35° example already show some of this.
- Wider FOV with a shorter distance gives strong perspective (like preset `0A`). Narrow FOV with a long
  distance looks almost flat (like the interiors).
- Widescreen and camera codes are independent: use them together.

## 6. Things to know

- **When changes apply:** the camera is built when you enter a map, so a change shows after the next door,
  warp or save load, not instantly.
- **The forced preset is saved.** The "force preset" code writes into the save data. If you save with it
  on and later load without it, the game keeps that preset on the map you load into, until you go through
  a door. The table codes (interior 3D, custom) don't touch the save.
- **Turning things off:** disable the code, then go through a door. Widescreen is the exception: use its
  OFF code, because the 16:9 setting stays in memory until the game restarts.
- **Battles:** the camera codes change only the overworld camera table and the map's preset; battles use
  their own camera. Battles weren't tested with these codes.
- **The `521E9C54 B084B5F8` line** checks that the overworld code is loaded at that address before writing
  to the camera table. Other screens load different code at the same addresses, and the check keeps the code from
  writing into them. Keep it.
- **Only tested in DeSmuME (emulator).** Not tested in melonDS, on real hardware or with TWiLight Menu++
  cheats. These codes use only standard code types (0, 2, 5, 6, B, D2), which those all support.

## How this was verified

- Addresses were found in the game's code: the camera builder (overlay 1, `0x021E9C54`) indexes the preset
  table with the byte read by `0x0203AE9C` (`location + 0x6A`). The map-entry code at `0x020522D2` copies the
  map header's preset into that byte (header bits 12–17 of word +0x14).
- Map usage was counted from the 540 map headers in the RC5 ROM.
- Each code was run in the project's emulator harness on the RC5 ROM in a mart (preset 4) and on Route 1
  (preset 0): all 17 forced presets, both interior variants, the custom template and its examples. The camera
  byte, the table in RAM and screenshots were checked. Turning the table codes off and changing map restores
  the original table. A save with a forced preset keeps it on load and resets at the next door.
- The US code was decoded against the decompressed US HeartGold code. Its pointer belongs to the
  play-time counter, and US and Origin save layouts were compared in RAM.
