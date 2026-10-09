# Safari Zone: wild Double Battle with a junk second opponent (freeze)

2026-10-09. Fix: `work/patches/safari-no-wild-double/` (20 bytes in overlay 2), D-2289 (user-approved exception
to D-1337), answering the hack finding D-1535. Branch `fix/safari-double`.

## Reports

- Discord: "Some encounter in the Safari [Zone] freezes the game."
- D-1535 (2026-10-05): a player's save on the untouched Chinese ROM (a Lv15 Geodude double during the warden's
  test), and a DraStic report (a Lv79 paralysed opponent, then a crash).

## The code (untouched Chinese ROM, overlay 2 loaded at 0x02245F40)

The walk/surf wild encounter (overlay 2, 0x02246F6C) chooses the battle setup after its encounter checks:

| Address | What |
|---|---|
| 0x022470C4 | the hack's random double: `[sp+0x10] = 1` when `rand() % 4 == 0`, at least two Pokémon can fight (arm9 0x02053570) and `[sp+0x25] == 0` |
| 0x022470F8 / 0x02247100 | `[sp+0x1C]` = sys flag 0x967 (Safari Zone game), `[sp+0x18]` = sys flag 0x996 (Bug-Catching Contest) |
| 0x02247106 | `r7` (a partner follows) → always the double setup (vanilla) |
| 0x0224710A | `r1 = 1` Safari, `2` Contest, else `0` (the edit) |
| 0x0224711E | `[sp+0x10]` set → `BattleSetup_New(11, 0x4A)`, the double setup, whatever `r1` is |
| 0x02247130 | else `Encounter_NewSetup` (0x022486C4): Safari setup (0x02050DBC), Contest setup (0x02050DD0) or `BattleSetup_New(11, 0)` |
| 0x02247176 | Safari → 0x02247790, Contest → 0x022477AC: **one** wild Pokémon; otherwise the double flag → 0x02247F24 twice (two), else 0x02247770 (one) |

So in the Safari Zone, with two Pokémon that can fight, one encounter in four builds a double setup but only
one wild Pokémon. The second opponent slot is uninitialised: on DeSmuME it shows as "eeeeee Lv2" with a status
and no sprite, and the battle stays at the command menu (RUN does nothing): a soft lock on DeSmuME, a data
abort on melonDS (see "melonDS" below).

Surfing never rolls the double: the encounter-type helper (0x02247998) writes `[sp+0x25] = 1` on water
(arm9 0x0205A828), the roll needs `[sp+0x25] == 0`, and water encounters branch to 0x0224722A (the 5-slot surf
table). So the bug, and the fix, only concern land encounters, in every Safari Zone area (the fix keys on the
Safari game flag, not on the map or the area).

No other encounter path has the random double: a scan of overlay 2 finds one `rand` + `% 4` + 0x02053570
sequence (this one); fishing (0x022472D4) and the other entry points call `Encounter_NewSetup` directly.

### The Bug-Catching Contest is not affected

The Contest goes through the same branch, but the National Park gate script (file 151, L577-L596:
`ScriptOverlayCmd 1, 0`, `BugContestAction 0, 0x4000`, `SetFlag 2454`) leaves only the chosen Pokémon in the
party for the contest. With one Pokémon the random double is never rolled. Observed on DeSmuME (Chinese ROM,
2026-10-09, `route1_path_2mons.sav`, a Saturday, the roll forced to 0): party 2 → 1 after `BugContestAction 0`,
a forced roll in the contest grass gave `[sp+0x10] = 0`, the Contest setup (battle type 0x1000), one wild
Pokémon, RUN back to the field. The fix leaves the Contest exactly as the hack has it.

## The fix

The 20 bytes at 0x0224710A test the Safari flag first and branch to `Encounter_NewSetup` with `r1 = 1` before the
double flag is read. The Contest (`r1 = 2`) and every other encounter (`r1 = 0`) fall through to the double check
as before:

```
- ldr r0,[sp,#0x1C]; mov r1,#0; cmp r0,#0; beq +; mov r1,#1; b check; +: ldr r0,[sp,#0x18]; cmp r0,#0; beq check; mov r1,#2
+ ldr r0,[sp,#0x1C]; mov r1,#1; cmp r0,#0; bne single; mov r1,#0; ldr r0,[sp,#0x18]; cmp r0,#0; beq check; mov r1,#2; nop
```

Not changed: the roll itself, random wild doubles outside the Safari Zone, the partner double, the Contest. The
disabled prototype on branch `worktree-agent-a685bbb86f819d86f` (2026-10-05) also sent the Contest to its single
setup; that part was dropped after the Contest check above.

## Evidence

Builds of this branch, 2026-10-09 (`build.py --no-patch`): fixed = SHA-1 `f188fdf5…` (= the `check.py --full`
build, `nontext_sha1` `8adbef4d…`); control = `--without safari-no-wild-double`, SHA-1 `d01ada95…`, identical to
the branch's build before the fix (its `nontext_sha1` is the previously recorded `910f82c8…`). The two differ only
in overlay 2, inside 0x11CA-0x11DD; overlay 2 of the fixed build has SHA-1 `6d1ad40a…` (GOLDEN). Untouched Chinese
ROM: `origin_v4.0.3_cn.nds`.

DeSmuME, `emu_harness.py fixes-child --scenario safari` (the fix scenario, `emu_fixes.observe_safari`): from
`route1_path_2mons.sav` (Charmander Lv9, Caterpie Lv2) on Route 1 grass; the random roll is forced (`r0 = 0` after
`rand`, 0x022470CC); case `wild`: a Route 1 encounter; case `safari`: the gate's own commands (`SetVar 0x40E3 1`,
`SafariZoneAction 0 0`, script file 119 L2135-L2141), a warp to the Safari Zone grass (357: 48,40), walk.

| ROM | Route 1 (forced) | Safari Zone (forced) |
|---|---|---|
| untouched Chinese | double setup 0x4A, two wild Pokémon, fled | double setup 0x4A, **one** wild Pokémon, junk second opponent, RUN never returns: **freeze** |
| control (without the fix) | double 0x4A, two, fled | double 0x4A, one, **freeze** ("eeeeee Lv2 PSN", no sprite) |
| fixed | double 0x4A, two, fled | double rolled (`[sp+0x10] = 1`) but the Safari setup (battle type 0x20), one wild Pokémon, a normal single battle, fled |

melonDS 1.1: see "melonDS" below.

## melonDS

melonDS has no execution hooks, so the roll cannot be forced in a run and `run_script`/`warp` are not available.
The test uses throw-away ROM copies (made by a scratch script, not committed; game data, never shipped):
the roll's `bne` at 0x022470D8 is a `nop` (every eligible encounter rolls the double), and Route 1's script file
(a/0/1/2 #168) holds the same gate commands and warp as the DeSmuME scenario, started by reading the Route 1
sign at (1037,338). Then walk in the Safari grass, run the battle to the command menu, touch RUN.

Runs (melonDS 1.1 shim of the main checkout, RTC 2026-10-09 12:00, `route1_path_2mons.sav`): walk two tiles left and
right in the Safari grass (357: 46-48, 40) until a battle starts, run 1200 frames, touch RUN up to eight times,
then `hang_report(240)`; up to three encounters.

| Test ROM made from | Result |
|---|---|
| untouched Chinese ROM | **hang**: data abort while the battle starts (frame 4885), fault PC 0x0221E6B4, abort LR 0x0221E6BC (overlay 14, battle), CPSR 0x97; the top screen stays light blue, the bottom black |
| control (without the fix) | **hang**: the same abort (frame 5337, same PC, LR and CPSR) |
| fixed | **pass**: encounter 1 a normal single Safari battle, RUN back to the field; encounter 2 a single battle (Raticate) that went on normally (the escape failed and the battle continued to the party screen); no abort, the screen keeps changing |

So the freeze is a soft lock on DeSmuME (it reads the junk and keeps drawing) and a crash on melonDS. Real
hardware is untested; the DraStic report (a crash) fits the melonDS behaviour.

## Tests

- `emu_harness.py fixes --case safari-no-wild-double` (scenario `safari`), 2026-10-09 on the `check.py --full` build
  with a control built by `--build-controls`: PASS (fixed ROM: fixed, control: original), 50 s.
- `test_emu_fixes.py`: the judge on recorded observations; the hooked addresses against the asm labels.
- `test_asmpatch.py`: GOLDEN overlay 2 (alone and with every fix), 47 code regions.
- `check.py --full`: PASS after `--update-expected` (nontext moves only by this fix: the control's nontext is the
  previously recorded one).
