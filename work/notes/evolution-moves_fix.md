# Evolution moves fix (`evolution-moves`, D-2276)

Fixed 2026-10-09 at the user's request ("We want to fix these bugs, so for each issue create a worktree per
issue, and use a separate subagent to fix, test and review."). It is an exception to D-1337 and answers the
hack finding D-1602; the investigation is in [evolution_moves_investigation.md](evolution_moves_investigation.md).

## Symptom

Reported on Discord by several players: Crobat does not learn Cross Poison, Charizard does not learn Air Slash,
Gyarados does not learn Bite when they evolve. The untouched Chinese v4.0.3 does the same (D-1602), so it is a
bug of the hack, not of the translation.

## Cause

The hack's learnsets (`a/0/3/3`, 1441 files) are modern-style `u16 level, u16 move` pairs, sorted by level and
ended by level `0xFFFF`. 415 species start with one or two **level-0** entries (426 entries): the moves modern
games teach on evolution, e.g. Charizard `(0, 403 Air Slash)`, Crobat `(0, 440 Cross Poison)`, Gyarados
`(0, 44 Bite)`, Raichu `(0, 9 Thunder Punch)`. Vanilla HeartGold has no such entries: its learnsets pack
`move | level << 9` and the USA ROM has 0 level-0 entries in its 508 lists. Vanilla HGSS, on evolution, only
offers the new species' moves of the current level; teaching evolution moves is modern (Gen 7+) behaviour,
which the hack's data expects but its code never got.

The hack kept HeartGold's level-up routine at `0x02070870` (pokeheartgold `MonTryLearnMoveOnLevelUp(mon,
&index, &move)`): it loads the learnset (`0x02071238`), walks it from `*index` to the first entry whose level
equals the Pokémon's level (`GetMonData` field `0xA1`), stores the move, advances the index and calls
`MonTryLearnMove` (`0x020706B8`), which returns the move, `0xFFFE` (already known) or `0xFFFF` (four moves
known). Its caller repeats the call with the same index until it returns 0. Four calls, all in arm9 (no overlay
calls it): the evolution scene `0x02074BD4`, level-up `0x020806F2`, the day care `0x0206B236`/`0x0206B252`.
No level ever equals 0, so the evolution scene never offers a level-0 move.

## Fix

`work/patches/evolution-moves/` (armips, arm9; [listing](../patches/evolution-moves/evolution-moves.listing)):

- The routine is rewritten in its own 0xB4 bytes (`0x02070870`-`0x02070923`, literal pool included). The old
  entry starts with `mov r3, #0`; a new entry `TryLearnOnEvolution` (`0x02070900`) does `mov r3, #1` and
  branches to the shared body. The body pushes `{r3-r7, lr}` as before, so the flag is on the stack at
  `[sp + 0x10]`. An entry matches when its level is the Pokémon's level (as before) or when it is 0 and the
  flag is set. Everything else is the hack's routine: the same heap allocation (0xA8 bytes), `GetMonData`
  fields, learnset loader, index handling and return values; only the two duplicated "end of list" exits the
  compiler emitted are shared, which makes room for the new instructions.
- The evolution scene's call at `0x02074BD4` goes to `TryLearnOnEvolution` (`F7FB FE4C` -> `F7FB FE94`).

Because the list is sorted, one forward pass offers the level-0 moves first and then the moves of the new
level, each through the scene's own flow: "learned", "already knows" (skipped silently), or "wants to learn ...
However, X already knows four moves. Make it forget another move?" with the move-selection screen. Every
evolution runs this scene (Rare Candy, level-up after a battle, stones, trade, friendship and the others), so
all of them are covered by the one call site. Level-up without evolution and the day care still enter at
`0x02070870` with the flag 0 and match exactly the entries they matched before.

The new bytes were also written out by hand from this design and compared with armips' output
(`test_asmpatch.RealFixes.test_evolution_moves_bytes`).

## Evidence

Emulator scenario `evolution` (`emu_fixes.observe_evolution`, `emu_harness.py fixes --case evolution-moves`),
DeSmuME, hooks on the scene's learn call (return `0x02074BD8`: `r0` and the move at `sp + 0xE`) and on the
Rare Candy level-up's learn call (return `0x020806F6`). Cases: Charmeleon Lv35 with one move and with four
moves (forget Tackle), Charmeleon Lv38 (Air Slash and the Lv39 Scary Face), Magikarp Lv19, Golbat Lv29 with
friendship 255, Pikachu Lv20 with a Thunder Stone, and Charizard Lv40 levelling to 41 (no evolution: no Air
Slash offered). Results are in the "Results" section below.

melonDS 1.1 has no execution hooks, so the scenario runs on DeSmuME; a separate melonDS run of the Charmeleon
cases (party moves read from RAM, ARM9 exception record) is in "Results" too. The change is plain ARM9 logic
with no new memory access pattern, so no emulator-specific behaviour is expected.

## Results (2026-10-09)

DeSmuME, scenario `evolution`, one session per ROM (save `full_bag_6mons.sav`; party moves after each case;
"offered" = the scene's learn call returned that move, or `0xFFFF` with it):

| Case | Chinese ROM | Build without the fix (control) | Build with the fix |
|---|---|---|---|
| Charmeleon Lv35, Tackle -> Charizard | Tackle only | Tackle only | Tackle, **Air Slash** |
| Charmeleon Lv35, four moves -> Charizard | unchanged, nothing offered | unchanged, nothing offered | `0xFFFF` / Air Slash offered, "Forget a move!", Tackle forgotten: **Air Slash**, Growl, Ember, Scratch |
| Charmeleon Lv38 -> Charizard Lv39 | Tackle, Scary Face | Tackle, Scary Face | Tackle, **Air Slash**, Scary Face |
| Magikarp Lv19 -> Gyarados | Tackle only | Tackle only | Tackle, **Bite** |
| Golbat Lv29 (friendship 255) -> Crobat | Tackle only | Tackle only | Tackle, **Cross Poison** |
| Pikachu Lv20 + Thunder Stone -> Raichu | Tackle only | Tackle only | Tackle, **Thunder Punch** |
| Charizard Lv40 -> 41 (no evolution) | Tackle only, no scene | Tackle only, no scene | Tackle only, no scene (no Air Slash) |

Every checksum valid. Judge: Chinese `original`, control `original`, build `fixed`. The harness command
`emu_harness.py fixes --case evolution-moves` (fixed ROM and a freshly built control) reports PASS.

melonDS 1.1 (no execution hooks; the save's lead turned into Metapod Lv9 before boot, Rare Candy -> Butterfree,
whose level-0 move is Gust): the build learns Gust (one move: Tackle, Gust; four moves: the forget-a-move flow
replaces Tackle with Gust); the Chinese ROM and the control evolve without Gust. No ARM9 exception in any run.

Regression: the `evolve` cases of the suite (Petilil with and without a Sun Stone, Rockruff at three times of
day: the form chosen on evolution) pass on the build with the expected species and forms.
`check.py --full` passes (nontext SHA-1 recorded; the text hashes in expected.toml were already stale on
develop and are left for the coordinator).

Not tested directly: level-up evolution after a battle and trade evolution. They run the same evolution scene
(the only call of the learning routine that runs on evolution is 0x02074BD4), so they get the same behaviour.
