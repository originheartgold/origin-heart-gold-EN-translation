# Boldore and Gurdurr evolve by level (fix `trade-evolutions-levelup`)

Decision D-2281 (user-approved exception to D-1337, 2026-10-09). Scope set by the user: data errors where the hack
author's own documentation proves the intended value and the bug blocks content. Everything else stays report-only.

## What the hack does

The evolution table `a/0/3/4` has one 60-byte member per species: 10 records of 6 bytes, `u16 method, u16 param,
u16 target`. Method 4 is the plain level-up (param = level), method 5 the trade.

| Member | Species | Record 0 (untouched Chinese ROM) | Meaning |
|---|---|---|---|
| 524 | Roggenrola | `04 00 19 00 0D 02` | level up at Lv 25 → 525 Boldore |
| 525 | Boldore | `05 00 00 00 0E 02` | **trade** → 526 Gigalith |
| 532 | Timburr | `04 00 19 00 15 02` | level up at Lv 25 → 533 Gurdurr |
| 533 | Gurdurr | `05 00 00 00 16 02` | **trade** → 534 Conkeldurr |

No other member evolves into 526 or 534. Member SHA-1s in the Chinese ROM: 525 `4cd8fb7ba6dc…`, 533 `fe6ee29b1f6e…`.

## Why it is a data error

The author's v4.0 species sheet (4.0精灵数据) lists Boldore at Lv 35 and Gurdurr at Lv 40 (D-1349;
`sheet_mismatch_verification.md` §4.2 rows 547 and 553, `spreadsheet_crossref.md` §1.2). The ROM kept the official
trade method. Boldore is wild in Dark Cave and Gigalith is not wild anywhere, so a player without a trade partner
cannot get Gigalith (Conkeldurr is also wild in Cerulean Cave). The hack's Linking Cord (item 635) is used by no
evolution record and cannot be obtained; it is not part of this fix.

## The fix

Kind `narc`, two `[[narc_bytes]]` entries (the new mechanism: `work/tools/narcpatch.py`, `work/notes/toolchain.md`
"NARC byte fixes"). Each is applied only when the member still has the recorded SHA-1 and the first 6 bytes are the
expected record:

- 525: `05 00 00 00 0E 02` → `04 00 23 00 0E 02` (level up, Lv 35, Gigalith)
- 533: `05 00 00 00 16 02` → `04 00 28 00 16 02` (level up, Lv 40, Conkeldurr)

Four bytes change in all. In the built ROM `a/0/3/4` differs from the Chinese ROM in members 525 and 533 only,
2 bytes each (checked 2026-10-09). Trading Boldore or Gurdurr no longer evolves them (their only record is now the
level-up one).

## Emulator results (2026-10-09)

Scenario `trade-evo` (`emu_harness.py fixes --case trade-evolutions-levelup`, DeSmuME, save
`full_bag_6mons.sav`): the hack's generator makes Boldore Lv 34, Gurdurr Lv 39 and Roggenrola Lv 24 (the check
that the candy and the evolution path ran), each with only Tackle; one Rare Candy each from the bag.

| ROM | Boldore Lv 34 → 35 | Gurdurr Lv 39 → 40 | Roggenrola Lv 24 → 25 | Judge |
|---|---|---|---|---|
| Build (all fixes) | Gigalith | Conkeldurr | Boldore | fixed |
| Control (`--without trade-evolutions-levelup`) | Boldore | Gurdurr | Boldore | original |
| Chinese v4.0.3 | Boldore | Gurdurr | Boldore | original |

`emu_harness.py fixes --case trade-evolutions-levelup` reports PASS (fixed ROM: fixed; control: original).

melonDS 1.1 (same cases; the hack's generator gives junk species under melonDS, so party slots 0-2 were turned into
the case species in RAM with the EXP and party level of the level before, Medium Slow for all three in the hack's
personal data): build Gigalith / Conkeldurr / Boldore (fixed); control and Chinese ROM Boldore / Gurdurr / Boldore
(original). All checksums valid.
