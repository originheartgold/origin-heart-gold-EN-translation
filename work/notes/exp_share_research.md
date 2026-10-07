# Optional EXP Share disabling — research, 2026-10-04

## Result

Origin HeartGold v4.0.3 has a party-wide EXP eligibility function that unconditionally returns true. It does not read an option, item, script flag, or button. Its existing participant-only branch works when that return value is changed to false. The change also disables EV awards to nonparticipants. It does not redistribute their forfeited EXP to participants.

A four-line Action Replay code was tested through DeSmuME's actual AR engine on the original Chinese ROM and the current English WIP. A build-time alternative fits the existing code-patch JSON without any Python changes. A new in-game Options toggle remains a separate implementation task.

Production patch configuration, tools, translation banks, and ROM files were not modified. Research scripts, states, logs, and a sample config are in ignored `work/build/exp-share-research/`.

## Binary evidence

- Battle overlay: 14, RAM base `0x022007E0`, length 337216.
- EXP Share getter: `0x022157C0`, overlay-relative offset `0x14FE0`.
- Original instructions: `movs r0, #1; bx lr` (`01 20 70 47`).
- Proposed instructions: `movs r0, #0; bx lr` (`00 20 70 47`).
- Caller: `0x022289EA`, inside per-recipient EXP calculation `0x022289B4`.
- Participation check: `0x02216C38`, called immediately before the getter. It searches the defeated Pokémon's participation list.
- At `0x02228A2E–0x02228A38`, neither participant nor sharing-enabled means return with zero EXP. Otherwise participants get their normal amount; nonparticipants follow the half-EXP path at `0x02228A56–0x02228A62`.
- Eligibility helper `0x0221F6EC` excludes entries with zero EXP before the EXP and EV application paths. Thus this switch disables both for nonparticipants.
- Actual EXP application: `0x0222AC30`. EV application: `0x0222AC50`.
- Adjacent function at `0x022157C4` returns 100 (`64 20 70 47`). This is used as an additional cheat guard. The combined eight-byte signature at this address matches only overlay 14 among all 120 overlays, in both ROMs.
- The switch, calculation (`0x0222897C–0x02228C00`), distribution (`0x0221F4A0–0x0221F900`), and application (`0x0222AC30–0x0222ACB0`) ranges match byte-for-byte between the tested CN and EN ROMs.

This is stronger evidence than the absence of a translated menu label: the normal battle calculation itself has no user-configurable switch.

## Action Replay code

Disable party-wide EXP/EV sharing:

```text
522157C4 47702064
522157C0 47702001
122157C0 00002000
D2000000 00000000
```

The first two lines check both function signatures. The third writes one halfword in RAM; the last ends the conditional block. It applies when the battle overlay is present and can apply again after that overlay is reloaded. It does not alter the ROM on disk.

Enter as one AR cheat and enable before fighting. To restore ordinary behavior reliably, disable the cheat, restart the emulated game, and load an in-game save. Merely unticking a cheat does not reverse a memory write; a save state may retain patched memory. EXP/EV already missed are not awarded retroactively.

AR syntax reference: [Kodewerx DS documentation](https://doc.kodewerx.org/hacking_nds.html). The test invoked the installed DeSmuME library's `CHEATS::add_AR`, not a Python reimplementation of AR conditions. [DeSmuME cheat API source](https://github.com/TASEmulators/desmume/blob/master/desmume/src/cheatSystem.h).

## Controlled runtime results

Fixture: trainer Bidoof level 4; two level-9 Charmander party slots. The second slot was created by cloning the first in emulator RAM before battle, solely for a controlled comparison. Slot 1 participated; slot 2 stayed benched. Both began with 506 total EXP and 1 HP EV. The same pre-battle state and inputs were used for each language's control/treatment runs.

| ROM / setting | Participant EXP | Benched EXP | Participant HP EV | Benched HP EV |
| --- | ---: | ---: | ---: | ---: |
| CN, ordinary | 506 → 532 (+26) | 506 → 519 (+13) | 1 → 2 | 1 → 2 |
| CN, AR enabled | 506 → 532 (+26) | 506 → 506 (+0) | 1 → 2 | 1 → 1 |
| EN, ordinary | 506 → 532 (+26) | 506 → 519 (+13) | 1 → 2 | 1 → 2 |
| EN, AR enabled | 506 → 532 (+26) | 506 → 506 (+0) | 1 → 2 | 1 → 1 |

Checked both execution traces and decrypted, checksum-validated copies of final party data. All four battles completed and returned to the overworld. The English treatment enabled AR before the battle overlay loaded. The Chinese treatment enabled it with the battle already loaded.

Logs: `baseline.log`, `cheat.log`, `baseline-stats.log`, `cheat-stats.log`, `en-baseline.log`, `en-cheat.log`. Harness: `probe.py`. Images/states remain local in the same scratch directory.

Limits: DeSmuME 0.9.12 ARM64 only; physical Action Replay/flashcart and other emulators not tested. No broad regression claim for doubles, eggs, fainted recipients, level-100 recipients, or switching multiple participants. The original eligibility checks remain in place, but those cases need coverage before claiming release-level validation.

ROM SHA-256:

- CN: `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`
- EN WIP: `caf987949ea7e208f8cae1c49c76b1cf3fd596338cafeb7270693116bb448b3b`

## Build-time config option

The existing `work/tools/hardcoded.py` checks and applies the `[[code]]` entries of the enabled fixes in `work/patches/<fix-id>/fix.toml` (see `work/tools/fixes.py`). This proposed entry (when written, the code patch was a `code_patches.json` entry) dry-ran successfully against both ROMs. As a fix it would be its own folder, e.g. `work/patches/optional-exp-share-off/fix.toml` with `kind = "code"`, `enabled = false` and this entry:

```toml
[[code]]
id = "optional-exp-share-off"
file = "overlay14"
offset = "0x14FE0"
expect = "0x2001"
value = "0x2000"
notes = "Optional gameplay change: disables party-wide EXP and EV awards to nonparticipants."
```

This is a build choice: changing `enabled` (or `build.py --only/--without`) requires rebuilding and replacing the ROM. It is not a player-facing in-game setting. Leave it absent/disabled for the default faithful translation. Sample, not installed: `work/build/exp-share-research/build-option.json`.

## In-game Options toggle

The EXP side is small: redirect the four-byte BL at `0x022289EA` to a helper that returns a persisted setting. The remaining work is the interface and storage, not rewriting the EXP formula.

The Chinese Options menu is overlay 50, RAM base `0x021E4980`, size 5632. It has six setting rows plus confirmation. Its choice-count table is at overlay offset `0x1294` / RAM `0x021E5C14`: `3,2,2,2,3,20,2`. Touch hitboxes start at offset `0x1334`. It initializes its local settings explicitly and writes them back through individual getters/setters. Bank `a027/0043` names MUSIC SPEED, BATTLE SCENE, BATTLE STYLE, TITLE SCREEN, BATTLE BG, FRAME; there is no EXP row.

A seventh setting therefore needs row storage, choice counts, labels/help text, cursor and touch navigation, layout, load/confirm/cancel handling, and persisted storage. It cannot be added by inserting a text string alone.

The [upstream Options struct](https://github.com/pret/pokeheartgold/blob/master/include/options.h) has a spare high bit, and the [upstream menu implementation](https://github.com/pret/pokeheartgold/blob/master/src/options_app.c) explains the fixed tables. These are design references, not proof that the hack leaves that bit unused. The hack repurposes existing options. A full audit of that bit's use is still required before selecting it as save storage. Encoding zero as the existing enabled behavior would preserve old-save defaults if the bit is verified unused.

Alternatives:

| Option | Work / cost | Player control | Status |
| --- | --- | --- | --- |
| AR code | Four lines; no ROM change | Emulator/cheat menu | Tested in CN + EN |
| Build config | One JSON entry; two changed ROM bytes | Choose a build | Existing patcher dry-run passed |
| Replace an existing Options row | Reuse row geometry, but implement setting storage and battle helper | In-game | Feasible design; sacrifices an existing setting; not implemented |
| Add EXP SHARE row | Menu/table/layout changes, persistence, helper, regression tests | In-game, preserving other options | Scoped design; not implemented; no honest small-patch claim yet |

Recommendation: offer the AR code first. If a native toggle is desired, add a dedicated row with default ON after auditing save storage. Treat that as an optional feature, separate from translation fidelity, rather than silently changing the base release.
