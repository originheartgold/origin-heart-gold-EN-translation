# Heap audit: English text vs the screens' memory

**Status (2026-09-30): fixed in the WIP build (code patch `msgload-all`), checked with `memcheck.py run`; waiting for a melonDS check.** Found after rc3 testers reported crashes (bag, Pokémon summary, Pallet Town photo).

## The crash class

The hack's code comes from the Japanese HeartGold. Each screen gets a fixed-size heap, and many screens load whole message banks into it (`NewMsgDataFromNarc` type 0, hack address `0x0200BA98`). Our English banks are 1.5–3× the size of the Chinese ones. On a screen that had little room to spare in Chinese, the English text uses it up. An allocation then returns NULL, and the next file read goes to address 0. That address mirrors the ARM9's fast code memory (ITCM), so the interrupt handler at `0x01FF8000` is overwritten. melonDS crashes; DeSmuME hangs.

This is not a hack bug (D-1002): the untouched Chinese ROM does not crash with the same save.

## Confirmed and suspected cases (rc3)

| Screen | Heap | Whole banks on it | Spare room, zh → en | Result |
|---|---|---|---|---|
| Summary, skills page, switch to another Pokémon | 19 | 0295 (+3,056 B), 0739 move names (+11,790 B) | 208 → **−124** | **Crash, reproduced** (2 and 6 Pokémon). `a/1/1/4` #259 (6,448 B) no longer fits. Reverting 0295 or 0739 to Chinese fixes it. |
| Bag (field, and Poké Mart SELL) | 6 | 0010, 0219 item names (+11,134 B total) | 23,208 → **108** (2 items); 25,860 → 2,980 (every pocket full) | Near the limit. The tightest moment depends on the bag's contents and the pocket shown; likely the first tester's crash. |
| Pallet Town photo | – | – | – | No problem found in DeSmuME (photo taken, no allocation below 4 KB). The melonDS report is not reproduced. |

Party (2 and 6 Pokémon), Pokédex, trainer card, Pokégear, options, save prompt, a trainer battle (battle bag, Pokémon list, summary, moves) and the Poké Mart buy list: no heap below 4 KB spare.

## The check: `work/tools/memcheck.py`

Needs a venv with py-desmume and capstone (see the tool's docstring).

- `memcheck.py static`: every call site in arm9 and all 120 overlays that loads a whole `a/0/2/7` bank, with call site, heap id and the bank's Chinese and English size, biggest growth first (87 banks at 146 call sites; +288 KB in English). The 20 call sites whose arguments are not constant are listed separately.
- `memcheck.py run`: plays each scenario in `memcheck_scenarios.json` on the Chinese ROM and on our build. It hooks the allocator (`AllocFromHeapInternal`, `0x0201B258`) and records, per heap, the smallest spare room at any allocation (largest free block minus the request). **FAIL** means an allocation failed or something wrote to address 0–0x3F. **WARN** means English spare room is under 4 KB and smaller than in Chinese. **PRED** lines flag banks on a measured heap that grew by more than the Chinese spare room. Exit status 1 on any FAIL.
- Test saves (`work/build/memcheck/`, gitignored, local only; each scenario names its save):
  - `route1_path_2mons.sav`: Route 1 sand path, 0 badges, Charmander + Caterpie. It stands away from tall grass because the wild Pokémon that walk around the map start battles at random (DeSmuME's clock is real time).
  - `protographer.sav`, `trainer.sav`, `market.sav`: made by the user in melonDS, facing the Pallet Town photographer, an unbeaten Route 1 trainer and a Poké Mart clerk.
  - `full_bag_6mons.sav`: `market.sav` with every pocket filled (longest item descriptions first) and 6 Pokémon with 10-letter nicknames, held items and 4 long move names. Built in the emulator by writing the bag and party in RAM and saving in game. Bag layout in the hack (pret order, TMs pocket enlarged): items 165, key items 50, TMs/HMs 151, mail 12, medicine 40, berries 64, balls 24, battle items 30 slots of (u16 item, u16 count), right after the 6-slot party (+0x5B4); pocket sizes from the table at ov17 `0x021FFBD8`. Item pockets come from `a/0/1/7` (34-byte records, bits 7–10 of the halfword at +8).

Run it before every rc:

```
<venv>/bin/python work/tools/memcheck.py run
```

## Gaps

- Not covered: PC boxes, the photo album viewer, Pokéathlon, link and Wi-Fi screens, contests, the Battle Frontier. The static list names the banks and heaps involved there.
- Spare room depends on the save's contents and on the exact screen state. A passing run is evidence, not proof; keep a margin (the WARN threshold).

## Fix (in `work/translate/hardcoded/code_patches.json`)

- **`msgload-all`** (arm9 `0xBA9A`, `adds r5, r0, #0` → `movs r5, #1`): `NewMsgDataFromNarc` always creates an on-demand message handle (type 1), whatever type the caller asks for. No text bank is loaded whole into a screen's heap any more (149 call sites in rc3, `memcheck.py static` now lists 0). Safe at the code level: every MsgData function switches on the type and handles both, and no code outside them calls the whole-bank helpers. The handle itself is 0x54 bytes (`NARC_New`, `0x02007590`). Cost: one small ROM read per line instead of a memory read; the game already reads text this way at 186 call sites.
- **`msgload-summary-*` / `msgload-bag-*`**: the same change at the five measured call sites (`movs r0, #0` → `#1`), kept as a second layer in case `msgload-all` is ever disabled.

Result (`memcheck.py run`, all 16 scenarios, DeSmuME): no failed allocation, no crash write, no heap below 4 KB that is more than 256 bytes under the Chinese figure.

| Scenario | Spare room: zh → rc3 → fix |
|---|---|
| Summary, switch Pokémon (2 Pokémon) | 208 → −124 (crash) → 10,376 |
| Summary (6 Pokémon) | 18,412 → crash → 10,376 |
| Bag | 23,208 → 108 → 55,540 |
| Bag, every pocket full | 25,860 → 2,980 → 58,192 |

Heap-by-heap figures move with the timing of allocations (the tightest moment changes when banks are no longer loaded up front); small heaps such as 64 vary by ~70 bytes between runs in Chinese too.

## Other options considered

- Enlarging the screen's heap (the fix a Reddit user tried for the summary): it only works if the parent heap has the extra room everywhere the screen opens (field, battle, PC, trades, contests), which is unmeasured, and it needs a new size per screen. It adds demand instead of removing it.
- Shortening the text: not realistic for official names.

## Second crash class: double-size text with a line break (Misty scene, rc3) — fixed (D-1389)

`{VAR:FF01:200}` switches the message font to 200 % and `{VAR:FF01:100}` back. In this hack 200 % text is twice as **tall** but not wider (seen in game; the Chinese 16-glyph 200 % shouts only fit the 216 px box at normal width). A 200 % line is 32 px tall, the full height of the 216×32 px field message box. The text printer does not clip at the bottom of the window: a second line inside the 200 % span (`{NEWLINE}` or `{CLEAR}`) is drawn below the window's pixel buffer, over the heap block headers behind it. The game crashes later, whenever that heap is next used (melonDS: at the Route 3 Misty scene, bank 0319 #26).

- **Proof** (DeSmuME, heap walk every 10 frames while bank 0718 #160 is on screen, test ROMs built from the WIP build): `{big}Misty: Stop,{NEWLINE}Gyarados!{norm}` corrupts a free-block header of heap `0x022C0F00` (signature `0xFF21`, text pixels) as soon as it prints. The same text on one line, a short 200 % line, the Chinese line and the fixed English lines leave every heap intact.
- **Chinese:** 200 % text is always one line per page (93 spans). The only line breaks next to it are a `{SCROLL}` that ends the page (Pokéathlon, bank 0302; the US game does the same).
- **English (rc3):** 27 strings broke a line inside the 200 % span (banks 0048, 0053, 0058, 0081, 0090, 0319, 0321, 0377, 0441, 0457, 0462, 0476, 0546, 0547, 0597, 0599, 0616, 0617, 0733).
- **Fix (D-1389):** one 200 % line per page, like the Chinese. 26 of the 27 now fit on one line with the same wording; Pryce (0616 #37) is split at the sentence boundary into two 200 % pages (`…{VAR:FF01:100}{SCROLL}{VAR:FF01:200}…`), which `qa.py` treats as one SIZE span.
- **Checks:** `textmetrics.page_lines` counts a 200 % line as two line slots (the next line starts two slots lower), so `qa.py check` reports this as a `too_many_lines` error; `textmetrics.measure_lines` no longer doubles the width of 200 % text. `memcheck.py run` walks every live heap (from the game's heap table at `0x021D050C`) every 30 frames from frame 600 and fails on a corrupted block list. Walking every `EXPH` signature in RAM gave a false positive on the trainer card: a destroyed heap leaves its stale header behind.
- **The reporter's patch** (`NoBigText.xdelta`, applies to the US ROM) removes the size tags from these strings and joins the lines, so they print at normal size. That avoids the crash but drops the hack's emphasis, and the same patch has whole-file differences in `a/0/1/2`, `a/0/4/3`, `a/0/6/5`. **Audit correction (2026-10-05):** member-level and script-control-flow inspection found only equivalent script reordering/padding, with unchanged trainer member payloads; those differences do not establish a difficulty/level-cap mod. See [the lineage audit](bradams_lineage_analysis.md). Not merged.
- **Related, not proven:** 86 `too_many_lines` warnings (Chinese has as many lines; banks 0267, 0216, 0020, 0246, probably taller boxes) and 290 `more_lines_than_zh` warnings in UI banks with unknown box heights (e.g. 0295 summary labels, 0189 field menu). Any of them that overflows its window would corrupt memory the same way; the heap walk in `memcheck.py run` catches it on the screens it visits.
