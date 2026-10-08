# Bulbasaur following: water-reflection NULL pointer (black screen / freeze over water)

2026-10-08. Fix: `work/patches/bulbasaur-reflection-boundary/` (one byte in overlay 1), D-2270 (user-approved
exception to D-1337). This re-creates a fix investigated on 2026-10-05/06 in a temporary worktree that was
never committed and is gone; the reproducer, the analysis and the runs below were redone from scratch on
the current develop.

## Player reports (described neutrally)

- A player on Delta (iOS): the game freezes above the light-blue water in Viridian City only when Bulbasaur
  follows; switching the lead from another Pokémon to Bulbasaur while standing above the water gives an
  immediate black screen.
- A bug report against the English rc5 (Delta and melonDS): on Route 22, after stepping onto a certain tile
  "next to Misty", the game freezes as soon as the player walks away, in any direction, before or after
  talking to Misty; it happened twice. The report's screenshot is not available locally, so the exact
  tile is not known. The user links this report to the Bulbasaur bug. The DeSmuME runs below show the
  same NULL path on the north shore of the Route 22 pond, right next to Misty and her Pokémon, which fits
  the report; that the reporter had Bulbasaur following is not stated in the report.

## The code (untouched Chinese ROM, overlay 1 loaded at 0x021E4980)

`ReflectionGfx_Get` (0x021F61E8, r0 = map object) returns the graphics object a map object's water
reflection draws with. It reads the sprite id (`0x0205E3D8`: `ldr r0, [r0, #0x10]`) and then:

- a few listed ids (0, 0x15, 0x61, 0x62, 0xB0, some of 0xB1-0xC9 by a jump table, 0xF8, 0xF9, 0x102-0x106) read
  the generic field `[object+0x10C]` (`0x021F628A`);
- every other id goes to `0x021F6294`: `mov r1, #0x6B; lsl r1, #2; cmp r0, r1` (428), `ble 0x021F62AC`
  (bytes `07 DD`), then `ldr r1, =0x766; cmp; bgt 0x021F62AC`, then `[object+0x108]` (`0x021F62A8`): the
  follower's own graphics pointer, for sprite ids 429..1894 (the following Pokémon);
- `0x021F62AC`: 0x106..0x10D go to `0x0206323C`; everything else reads `[object+0x10C]` (`0x021F62C6`).

`0x0205E588` is `mov r1, #0x42; lsl r1, #2; add r0, r0, r1; bx lr`, i.e. object + 0x108 (an older note of
the lost investigation said 0x168; that was an arithmetic slip, corrected there too).

Sprite 428 is Bulbasaur as a following Pokémon, the first follower sprite (Charmander follows as 432, Onix as
524; seen at run time). Because the bound is `ble`, 428 is excluded from the follower range and reads
`[object+0x10C]`, which is NULL for a follower object (seen at run time; `[object+0x108]` holds a valid
pointer in main RAM).

The resolver has six callers in overlay 1. The two reflection callbacks (`bl` at `0x021FCC88` and
`0x021FD19A`, return sites `0x021FCC8C` / `0x021FD19E`) pass the result straight to `0x0202451C` (u16 at
+0xB6) and `0x02024558` (u32 at +0xB8) without a NULL check. Both getters call the assertion handler
`0x02025B2C` for NULL, which returns in this build, and then read address 0xB6 / 0xB8. Under the game's
ARM9 protection-unit setup nothing is readable at address 0, so that read should be a data abort (inferred:
the same kind of NULL read aborts on melonDS 1.1 in the Rocket HQ texture bug,
`rocket_hq_freeze_repro_20261008.md`). DeSmuME does not emulate the protection unit, reads the address and
goes on, so the bug is invisible there. The other four callers (`0x021F9984`, `0x021F99D6`, `0x021F9A00`,
`0x0220092E`) were not traced; two of them check for NULL.

## The fix and why only Bulbasaur changes

`0x021F629A` `ble` -> `blt` (`07 DD` -> `07 DB`, overlay 1 file offset 0x1191A, the high byte at 0x1191B):
the same target for ids < 428 instead of <= 428. A signed `ble` and `blt` differ only when the operands are
equal. As a check, a small interpreter of the resolver's Thumb code (the listed-id dispatch, the jump table,
both bounds and the literals, read from the ROM) was run for every sprite id 0..65535 with the original and
the fixed byte: exactly one id changes path, 428 (`+0x10C` -> `+0x108`); 1466 ids read `+0x108` before (429..1894
and none other), 1467 after; 8 take the 0x106..0x10D special case in both.

The armips source guards, read-only, the code a sprite id above 0xF8 runs through: the entry, the dispatch
for ids > 0xF8, the range check, all three loads and the literal pool (`bulbasaur-reflection-boundary.asm`,
snapshot in `.listing`). It does not guard the arm9 helpers (`0x0205E3D8`, `0x0205E588`); the harness
checks their effect at run time (it requires the loaded field to be object+0x108 / +0x10C).

A community fork of the hack makes the same one-byte change (a local binary comparison of its patch found
only this byte different in overlay 1; its author describes it as an off-by-one for Bulbasaur at 428). This
port was reproduced and verified here independently; nothing else from that fork was taken.

## Runtime evidence (DeSmuME 0.9.12, `emu_harness.py reflection`)

`work/tools/emu_reflection.py`; how to run it: `emu_harness.md`, "Following-Pokémon water reflection". One
emulator per run; the baseline is `work/build/memcheck/market.sav` (Continue), the lead's species is set in
RAM and the party cut to one, then the game's Warp command enters the scene and the player walks four steps
along the dry shore (`SCENES`): the strip north of the Viridian City pond, and the north shore of the
Route 22 pond west of Misty. Counts are per case (reflection calls for the follower / NULL returns /
assertions):

| ROM | Scene | Bulbasaur | Charmander | Onix |
|---|---|---|---|---|
| untouched Chinese | Viridian | 63 / 63 / 126 (`+0x10C`) | 63 / 0 / 0 | 63 / 0 / 0 |
| untouched Chinese | Route 22 | 18 / 18 / 36 (`+0x10C`) | 18 / 0 / 0 | 18 / 0 / 0 |
| English, `--without bulbasaur-reflection-boundary` | Viridian | 63 / 63 / 126 | 63 / 0 / 0 | 63 / 0 / 0 |
| English, `--without bulbasaur-reflection-boundary` | Route 22 | 36 / 36 / 72 | 36 / 0 / 0 | 36 / 0 / 0 |
| English, full build | Viridian | 63 / 0 / 0 (`+0x108`) | 63 / 0 / 0 | 63 / 0 / 0 |
| English, full build | Route 22 | 24 / 0 / 0 (`+0x108`) | 24 / 0 / 0 | 25 / 0 / 0 |

All 18 cases met their expectation (`--expect original` on the first two ROMs, `--expect fixed` on the
full build); every step ended on the expected tile, and the input ROM and save hashes were unchanged. The
Route 22 counts differ between runs because the follower's timing on that shore varies; each run is
judged on its own chain. DeSmuME never froze or blacked out: it reads address 0xB6 and continues, as
expected.

ROM SHA-256 (local, ignored): untouched Chinese `4807ab2c…95c8`; `--without` build
`acd75bfe607faba7d1aff25c37606497486c879e9e19d62921d27c07319bda86`; full build
`c72ad3761a57a1f2aac81b112faade8e27568896530f453ca832b1c13e4d3eb7` (both built `--no-patch` from the same
workspace on branch `fix/bulbasaur-reflection`). Reports: `work/build/reflection/{cn-original,en-without,en-fixed}/report.json`.

## melonDS: not run yet

melonDS 1.1 is installed only as the GUI app, and driving it by hand is not wanted; a headless melonDS
backend for the harness is being built separately. What the check needs once it exists:

1. **Saves.** In-game saves (Save from the field menu in DeSmuME, battery exported) of the untouched Chinese
   ROM, one Pokémon in the party, standing on a pond shore; `work/build/reflection/melonds-fixtures/` (ignored):

   | Save | Where | SHA-256 |
   |---|---|---|
   | `viridian_bulbasaur.sav` | Viridian City, north shore of the pond, Bulbasaur following | `1584e896cbf65df40f3572761e449faf445350965db7acae5fd31fc749a82b6f` |
   | `viridian_charmander.sav` | same spot, Charmander (control) | `39765f1b2986f8c5e2f3dec194cf414d881d642217286f806303932ad07b656c` |
   | `route22_bulbasaur.sav` | Route 22, north shore of the pond, next to Misty, Bulbasaur following | `8eda2f87ba31857bfcc165f73077c10fc5f63c20b73dba6a2fbc95afe56a28ff` |
   | `route22_charmander.sav` | same spot, Charmander (control) | `733f0f7fce4ea83d9fbb1dba697164efd3b732bc258bf2d686f8fc0642ee0e87` |

   Booting them in DeSmuME and pressing Continue: with Bulbasaur on the `--without` build the reflection
   resolver returns NULL from the first frames after Continue (60 NULL returns / 120 assertions in 120
   frames on either save), before any input; on the full build 0. Same saves work with the Chinese ROM and
   both English builds (save format unchanged).
2. **Inputs.** Boot, title screen (A or Start), Continue (A), then wait about 300 frames; optionally one step
   LEFT and one RIGHT along the shore (the Route 22 report: the freeze comes when walking away).
3. **Detecting the failure.** The ARM9 enters the data-abort handler: CPSR mode 0x17 (abort), a branch-to-self
   loop (the Rocket HQ states had saved R15 0xFFFF0108, CPSR 0x60000097), and the abort LR = faulting
   instruction + 8: `0x02024530` for `ldrh r0, [r4]` at `0x02024528` (half getter, address 0xB6) or
   `0x0202456C` for `ldr r0, [r4]` at `0x02024564` (word getter, address 0xB8). The game's frame counter
   stops advancing and the screens go black or freeze. A breakpoint/
   watch on the reflection return sites `0x021FCC8C` / `0x021FD19E` with r0 == 0 identifies the cause
   before the abort.
4. **Expectations.** Chinese ROM and `--without` build with the Bulbasaur saves: abort; with the Charmander
   saves: no abort. Full build with every save: no abort, the player can walk along the shore.

## Limits

DeSmuME proves the NULL path and that the fix removes it; the black screen itself has not been reproduced
in any emulator here (melonDS pending, real hardware and Delta untested). Only Bulbasaur, Charmander and
Onix at two ponds were exercised; special follower forms and other reflective surfaces (puddles) were not.
