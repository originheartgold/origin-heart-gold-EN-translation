# Evolution moves skipped — D-1602

Investigated 2026-10-07. **Reproduced in both the untouched Chinese v4.0.3 and the local English WIP.** This is an original-hack gameplay bug.

**Update 2026-10-09: fixed** at the user's request (D-2287, an exception to D-1337; D-1602 resolved). The fix is `work/patches/evolution-moves/`; see [evolution-moves_fix.md](evolution-moves_fix.md). The text below is the investigation as it was.

## Player report

A player report on Discord (2026-10-07) reports Crobat missing Cross Poison, Charizard missing Air Slash, and the same problem with Gyarados. It does not name Gyarados's missing move, identify the patch/emulator, supply a save, or say whether evolution followed a battle or a Rare Candy. Bite is the Gyarados evolution entry found in the ROM and tested here, not a move named by the reporter.

Source: a player report on Discord, 2026-10-07.

## Reproduction

Used the existing DeSmuME harness and ROMs, with isolated copies of the harness battery save. Created each pre-evolution with the hack's generator, set its moves to Tackle plus three empty slots, and removed held items. Golbat's friendship was set to 255. Applied a Rare Candy through the ordinary Bag interface, then read the evolved party member and checked its checksum. No evolution or move-learning code was changed. The test moveset isolates free-slot learning; it does not reproduce the reporter's unknown party setup.

| Test | Chinese | English WIP |
|---|---|---|
| Golbat Lv29 → Crobat Lv30 | Evolves; no Cross Poison | Evolves; no Cross Poison |
| Charmeleon Lv35 → Charizard Lv36 | Evolves; no Air Slash | Evolves; no Air Slash |
| Magikarp Lv19 → Gyarados Lv20 | Evolves; no Bite | Evolves; no Bite |
| Positive control: Charmeleon Lv38 → Charizard Lv39 | Learns Scary Face; skips Air Slash | Learns Scary Face; skips Air Slash |

All six original cases retained `[33, 0, 0, 0]` (Tackle and three empty slots). Both controls finished with `[33, 184, 0, 0]` (Tackle and Scary Face). All resulting checksums were valid. The control establishes that learning after evolution works when the move's entry matches the current level.

Local reproduction script (one emulator process per invocation):

```sh
.venv/bin/python work/build/evolution-moves-repro/repro.py cn crobat
.venv/bin/python work/build/evolution-moves-repro/repro.py en crobat
```

Replace `crobat` with `charizard`, `gyarados`, or `charizard_control` for the other cases. Run from the repository root. The emulator required execution outside the macOS sandbox; its initial sandboxed launch aborted during startup.

## Cause

The `a/0/3/3` learnsets store pairs of 16-bit values `(level, move)`. Crobat begins with `(0, 440)` for Cross Poison, Charizard with `(0, 403)` for Air Slash, and Gyarados with `(0, 44)` for Bite. Each also repeats that move at level 1.

The evolution state machine calls the learning function at `0x02070870` from `0x02074BD4`. That function obtains the Pokémon's current level through field `0xA1` at `0x020708A8`, loads its learnset, and compares each entry's level against the current level at `0x020708D2` / `0x020708F0`. Nonmatching entries are skipped. There is no special acceptance of level 0. Thus evolution at levels 30, 36, or 20 skips both the level-0 and level-1 copies.

The positive-control execution hooks observed the Charizard entry `(0, 403)` compared against current level 39 and skipped; the level-39 entry for Scary Face was learned. Hooks observed registers and memory only. The hook API reports the PC ahead of the registered instruction, so the trace's `pc` is not the hook-registration address.

The learnset archive, learning function bytes (`0x02070870–0x0207091F`), and evolution call-site bytes (`0x02074BCA–0x02074BD9`) are identical in both tested ROMs. This establishes the shared mechanism as well as the shared symptom. Other level-0 evolution entries are likely affected by the same mechanism, but were not individually tested.

## Evidence and limits

### Workaround verified

The Move Reminder successfully taught Cross Poison to the evolved Crobat, Air Slash to Charizard, and Bite to Gyarados in the English WIP. Each Pokémon gained the expected move in its second slot and retained a valid checksum. These checks loaded the post-evolution test states and invoked the original Blackthorn Move Reminder script from file 944, offset 214, with the test party slot selected. This exercises the real move-selection/teaching app; it does not verify reaching Blackthorn or the preceding NPC dialogue/payment path. Results and screenshots are saved as `en/<case>/reminder-result.json` and `reminder_*.png`.

### Artifacts and coverage

All binary evidence, saves, screenshots, test scripts and JSON reports stay in ignored `work/build/evolution-moves-repro/`. Each `<language>/<case>/result.json` records before/after party data; the controls also record the learnset scan. `binary-evidence.json` contains ROM and code hashes, and `learning-disassembly.txt` contains the inspected instructions.

| Artifact | SHA-256 |
|---|---|
| Untouched Chinese ROM | `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8` |
| English WIP tested | `6fa7b4e739391ca9ea9bfcf90d83eec6407c3c04102e52432bb41bc8ae44a7d3` |
| Learnset archive, both ROMs | `b3e7cbfdc4908b7565bc9c9a6250bcbe9c6eeb6a64030c674afebb3778d84fc5` |

The reporter's exact release, emulator, save and evolution trigger are unknown. These runs reproduce the symptom via Rare Candy; battle-triggered evolution and full movesets were not separately tested. No ROM was built, no gameplay fix was applied, and no report was posted externally.
