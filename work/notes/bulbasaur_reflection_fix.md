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

- a few listed ids (0, 0x15, 0x61, 0x62, 0xB0, some of 0xB1-0xC9 by a jump table, 0xF8, 0xF9, 0x102-0x105) read
  the generic field `[object+0x10C]` (`0x021F628A`);
- every other id goes to `0x021F6294`: `mov r1, #0x6B; lsl r1, #2; cmp r0, r1` (428), `ble 0x021F62AC`
  (bytes `07 DD`), then `ldr r1, =0x766; cmp; bgt 0x021F62AC`, then `[object+0x108]` (`0x021F62A8`): the
  follower's own graphics pointer, for sprite ids 429..1894 (the following Pokémon);
- `0x021F62AC`: 0x106..0x10D go to `0x0206323C`; everything else reads `[object+0x10C]` (`0x021F62C6`).

`0x0205E588` is `mov r1, #0x42; lsl r1, #2; add r0, r0, r1; bx lr`, i.e. object + 0x108 (an older note of
the lost investigation said 0x168; that was an arithmetic slip, corrected there too).

Sprite 428 is Bulbasaur as a following Pokémon, the first follower sprite (Charmander follows as 432, Onix as
524; seen at run time). The coordinator's review confirmed it statically: the follower sprite id comes from
arm9 `0x0206900C` with `pokemon_overworld_info.narc` at base 0, which makes 428 Bulbasaur's entry and also
the fallback sprite a follower gets when it has no entry of its own: such a follower draws as 428 and takes the
same path (not tested here; the fix covers it, since it keys on the sprite id).
The same review found no similar off-by-one at the other bounds. Because the bound is `ble`, 428 is excluded from the follower range and reads
`[object+0x10C]`, which is NULL for a follower object (seen at run time; `[object+0x108]` holds a valid
pointer in main RAM).

The resolver has six callers in overlay 1. The two reflection callbacks (`bl` at `0x021FCC88` and
`0x021FD19A`, return sites `0x021FCC8C` / `0x021FD19E`) pass the result straight to `0x0202451C` (u16 at
+0xB6) and `0x02024558` (u32 at +0xB8) without a NULL check. Both getters call the assertion handler
`0x02025B2C` for NULL, which returns in this build, and then read address 0xB6 / 0xB8. Under the game's
ARM9 protection-unit setup nothing is readable at address 0, so that read is a data abort on melonDS 1.1
(seen: fault `0x02024528`, r4 = 0xB6, below) and presumably on hardware (inferred, untested). DeSmuME does not emulate the protection unit, reads the address and
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

## melonDS 1.1 (headless backend, branch `hardening/melonds`)

Run 2026-10-08 with the headless melonDS 1.1 backend of `hardening/melonds` (worktree `poke-melon`, commit
`ebcf039`, `work/notes/melonds_backend.md`; DS mode, FreeBIOS, interpreter, software renderer, fixed RTC),
used read-only; outputs under that worktree's `work/build/bulba-melon/`. Two kinds of run:

- `emu_harness.py hang --case follower_viridian` (that branch's case): teleports an outdoor save
  (SHA-256 `0886514d…ebc9eb`) to the north shore of the Viridian City pond, sets the lead's species and walks
  DOWN, RIGHT, RIGHT, LEFT.
- The in-game fixture saves below, booted with Continue and walked LEFT, LEFT, RIGHT, RIGHT (Route 22) or
  LEFT, RIGHT, LEFT, RIGHT (Viridian), judged with the same `walk_case` / `judge` of `emu_hang.py` (a
  scratch driver, not committed).

| Run | ROM | Follower | Expect | Result |
|---|---|---|---|---|
| follower_viridian | `--without` build | Bulbasaur | hang | **hang**: data abort at frame 4272 on the first RIGHT step; fault `0x02024528` (`ldrh r0, [r4]`, r4 = 0xB6), abort LR `0x02024530`, CPSR `0x97`; the picture freezes (not black) |
| follower_viridian | `--without` build | Charmander | pass | pass: all four steps, no abort |
| follower_viridian | full build | Bulbasaur | pass | **pass**: all four steps, no abort, screen changing |
| follower_viridian | full build | Charmander | pass | pass |
| `route22_bulbasaur.sav` | untouched Chinese | Bulbasaur | hang | **hang**: data abort during Continue's map load (frame 3469), fault `0x02024528`, r4 = 0xB6; **both screens black** |
| `route22_bulbasaur.sav` | `--without` build | Bulbasaur | hang | **hang**, the same (frame 3468), both screens black |
| `route22_charmander.sav` | `--without` build | Charmander | pass | pass: four steps along the shore next to Misty |
| `route22_bulbasaur.sav` | full build | Bulbasaur | pass | **pass**: four steps, no abort |
| `viridian_bulbasaur.sav` | `--without` build | Bulbasaur | hang | **hang** during Continue (frame 3475), both screens black |
| `viridian_bulbasaur.sav` | full build | Bulbasaur | pass | **pass** |

The backend's author had already seen follower_viridian hang with Bulbasaur on the untouched Chinese ROM
and on develop, and pass with Charmander. So on melonDS 1.1 the NULL read is a data abort and the game hangs:
a frozen picture when it happens mid-walk, a black screen when it happens while the map loads (Continue
next to water; presumably also switching the lead to Bulbasaur there, as in the Viridian report). The fix
removes it in every run. Real hardware is inferred, not tested.

Fixture saves (in-game saves of the untouched Chinese ROM, one Pokémon in the party; ignored,
`work/build/reflection/melonds-fixtures/` of this branch's worktree):

| Save | Where | SHA-256 |
|---|---|---|
| `viridian_bulbasaur.sav` | Viridian City, north shore of the pond, Bulbasaur following | `1584e896cbf65df40f3572761e449faf445350965db7acae5fd31fc749a82b6f` |
| `viridian_charmander.sav` | same spot, Charmander | `39765f1b2986f8c5e2f3dec194cf414d881d642217286f806303932ad07b656c` |
| `route22_bulbasaur.sav` | Route 22, north shore of the pond, beside Misty, Bulbasaur following | `8eda2f87ba31857bfcc165f73077c10fc5f63c20b73dba6a2fbc95afe56a28ff` |
| `route22_charmander.sav` | same spot, Charmander | `733f0f7fce4ea83d9fbb1dba697164efd3b732bc258bf2d686f8fc0642ee0e87` |

## Limits

DeSmuME proves the NULL path and melonDS 1.1 the hang and black screen, both before and after the fix; real
hardware and Delta are untested. The Route 22 report's tile is inferred (beside Misty at the pond), not
known. Only Bulbasaur, Charmander and
Onix at two ponds were exercised; special follower forms and other reflective surfaces (puddles) were not.
