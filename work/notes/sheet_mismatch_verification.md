# Sheet mismatches re-verified against the original hack (Phase B2 verification)

> **Update 2026-09-29:** the three docs bugs in §6 are fixed in `work/tools/docs/` (mart calls via CallStd 2052 / SpecialMartBuy, the list-3 override at 0x020F8B3E, item-ball script 141 excluded); `items.md` is regenerated.

**Status (2026-09-29, agent verifyB2): current.** Audit only: no bank, build or tool file was changed. The only new tool is the independent checker `work/tools/audit/verify_sheet_rows.py`.

Question: are the 76 class-(a) and 15 class-(b) mismatches in [spreadsheet_crossref.md](spreadsheet_crossref.md) real, or did our build or our extraction cause them? Each row was re-read from a freshly patched original ROM with a parser that shares no code with `gen_docs.py`/`romdata.py`, and compared with the v3 hack.

**Result.**
- The freshly patched original is byte-identical to our CN copy.
- None of the game data the docs use differs between our build and the original.
- Every ROM value reported in spreadsheet_crossref.md was confirmed.
- No row was caused by us.
- The comparison with v3 changes the verdict for 21 rows. The sheet shows the v3 value, so the sheet is outdated (18 rows) or v4 broke something v3 had (3 rows).
- 2 rows are not mismatches at all (Bounce, Spoils).
- Separately, the audit found 2 bugs in our item docs (§6) and one audit-tool mistake of my own, fixed before the results (§3).

## 1. The fresh original equals our CN copy

| File | SHA-1 |
|---|---|
| `work/rom/Pokemon - HeartGold Version (USA).nds` (base; CRC32 `C180A0E9`) | `4fcded0e2713dc03929845de631d0932ea2b5a37` |
| `Pokémon Origin HeartGold v4.0.3 Cn.delta` | `ac8e1749e45cf962020c2d96b1d748f6bbf6e238` |
| fresh `xdelta3 -d -s US v4.delta` → `<scratchpad>/verifyB2/fresh_v4.nds` | `b69dc16be246658e3b29027698878d7ec560a1f6` |
| `work/rom/origin_v4.0.3_cn.nds` | `b69dc16be246658e3b29027698878d7ec560a1f6` (and `cmp`: identical) |
| `Pokémon Origin HeartGold v3 Cn Origins.delta` | `26fb118cefd300750dc3c3e39b3b87db6f641220` |
| fresh v3 → `<scratchpad>/verifyB2/fresh_v3.nds` | `2f0c337bdd5f9f2b02df0c1dc0314274c615f88d` (= `work/rom/origin_v3_cn.nds`) |

## 2. Build vs original: game data

Our build `work/build/origin_hg_v4.0.3_en_wip.nds` (16:42) is newer than the newest bank edit (16:32), so I did not rebuild. I compared every FAT file with ndspy and every NARC member.

- **Same file table.** No file was added or removed.
- **28 named files differ,** exactly the text, font and graphics set listed in [integrity_audit_text.md](integrity_audit_text.md) §1:
  - text: a/0/2/7 (790 of 817 members), battle_string;
  - fonts: a/0/1/6;
  - graphics: 25 NARCs, counting the clothes copies.
- **Every data source the docs use is byte-identical:**
  - species `a/0/0/2`, learnsets `a/0/3/3`, evolutions `a/0/3/4`;
  - `extra/new_move_data.narc`, `data/tutor_moves.narc`, `data/egg_moves.narc`;
  - encounters `a/0/3/7`, `a/2/5/2` and `data/mushi/mushi_encount.bin`;
  - trainers `a/0/5/5` and `a/0/5/6`, trades `a/1/1/2`;
  - scripts `a/0/1/2`, events `a/0/3/2`, items `a/0/1/7`.
- **arm9:** the size is unchanged (1,117,496 bytes). There are 75 differing byte runs, spanning `0x42862`–`0x100EBE`. Every run lies inside one of the 16 arm9 entries of `code_patches.json` (now the `[[code]]` entries of `work/patches/namelen` and `work/patches/naming-keyboard`). The data tables are therefore untouched:
  - shops `0x0210EAEC` and `0x020F8B3E`;
  - badge list `0x020F8D3A`;
  - hidden items `0x020F7194`;
  - TM tables `0x020FFFAC`/`0x020FFFF8`;
  - forms `0x020FEDC0`;
  - map headers `0x020F37C4`.
- **Overlays:** only the documented runs differ:
  - ov14: `0x4C0AB`–`0x4C287`;
  - ov44: `0x2E6C`;
  - ov49: `0x4E`, `0x66`;
  - ov58: `0x6F0`–`0x7CA`, plus the 56 appended bytes.
- **arm7:** identical.

**No game data differs.** Raw result: `<scratchpad>/verifyB2/build_diff.json`.

## 3. How the rows were re-derived

`python3 work/tools/audit/verify_sheet_rows.py --v4 fresh_v4.nds --v3 fresh_v3.nds --cache <dir> --out result.json`. (removed on 2026-10-09 with the rest of `work/tools/audit/`; in git history)

The checker reads the sheets itself (openpyxl) and re-reads the ROMs from bytes:

- **Text:** its own Gen 4 message decoder (pret `msgenc` key schedule). It uses the Xzonn charmap for v4 and the ACG charmap for v3. The v4 output equals the bank JSON `zh` for banks 0232, 0739, 0711 and 0219. Names are resolved through the ROM's own name banks.
- **Species:**
  - Layout: pret `BaseStats` (HP/Atk/Def/Spe/SpA/SpD at 0–5, types at 6–7). v4 widens the abilities to u16 at `0x16`/`0x18`, with the hidden ability at `0x1A`. I validated this against US HeartGold: types agree for 417 of 493 species, and Bulbasaur's abilities are 65/34.
  - Forms: found by structure scan, 415 × {species, personal index, form} at `0x020FEDC0`.
  - v3 forms: pret's fixed indices 496–507.
- **Evolutions:** pret `{u16 method, param, target}`.
- **Moves:**
  - v4 uses the Gen 5 move record. Validated against US `a/0/1/1`: type 456/467, effect 461/467, category 465/467.
  - Target byte mapping from the same comparison: US 0→0, 4→5, 8→4, 16→7, 64→10.
  - Flag bit 1 is the charge flag. It is set on exactly 13 moves: Fly, Solar Beam, Dig, Dive, Shadow Force, Sky Drop, Freeze Shock, Ice Burn, Phantom Force, Geomancy, Solar Blade, Meteor Beam and Electro Shot.
  - v3 uses pret `MoveTbl`.
- **Encounters:** pret HGSS `ENC_DATA`. Maps come through the pret `MapHeader` table, found by structure at `0x020F37C4` (v4, 540 maps) and `0x020F6390` (v3); 539 of 540 headers are equal.
- **Item sources.** The scan is written from scratch. Script command sizes come from pret `script.inc`, as tabulated in `script_cmds.json`; that file is data only.
  - Scripts are walked only through reachable code, with constant propagation of `SetVar`.
  - The effects of std scripts are resolved: 2033/2008 give `0x8004`; 2052 buys from special mart `0x8004`; 2048–2050 are the badge-tier MartBuy.
  - Hidden items, special marts, the badge list and the std table are located by structure.
  - Hidden bg events use script 8000+n. The game looks n up by the record's flag-index field, not by position: arm9 `0x0203FCB4` compares `ldrh [rec,#6]` with script−8000. My first draft used the position, which was wrong; the checker now follows the code.
  - The hack's `SpecialMartBuy` (arm9 `0x0204787C`) is decoded by hand: `if (id == 3) list = 0x020F8B3E else list = table[id]`. v3 has no such case.
- **Docs cross-check:**
  - All 1,440 personal records in `work/docs/pokemon_*.md` (stats, types) and all 920 rows of `moves.md` (type, category, power, accuracy, PP) equal the independent parse.
  - The audited evolution, encounter and tutor lines in the docs equal the fresh v4 values.

## 4. Verdicts

| Verdict | Rows | Meaning |
|---|---|---|
| **Sheet outdated from v3** | 18 | The sheet has the v3 value. The hack changed it in v4, and the sheet was not updated. |
| **v4 regression** | 3 | The sheet has the v3 value or intent. v4 broke it: an old v3 id or name was left behind. |
| **Mixed** | 1 | Rapidash: the type matches v3, the stats match neither. |
| **Neither: sheet error** | 42 | The ROM agrees with itself, with v3 and/or the official value. The sheet is wrong. This covers 14 of the 15 class-(b) rows (all but Porygon2) and 28 class-(a) rows. |
| **Neither: undetermined** | 25 | The ROM (v3 and v4 alike, or v4 only for species v3 lacks) differs from the sheet with no evidence either way. Either the ROM lacks a change the author planned, or the sheet is wrong. Includes the hack oddities #327 and TM46. |
| **Matches v4: our classification was wrong** | 2 | Bounce (data agrees with the sheet), Spoils (the sheet itself notes the rename). |
| **Our bug** | 0 | None of the 91 rows comes from our build or our extraction. |

"docs" = the value in `work/docs/`. In every row it equals the fresh v4 value, so the column is omitted where it would only repeat v4.

### 4.1 Species (4.0精灵数据): 31 (a) + 6 (b)

Stats are given as sheet / v4 / v3. "—" means the species or form does not exist in v3. Evidence: `a/0/0/2` [personal index].

| Row | Species | Field | Sheet | Fresh v4 | v3 | Verdict |
|---|---|---|---|---|---|---|
| 10 | Blastoise [9] | Atk, SpA | 73, 90 | 78, 85 | 83, 85 | sheet error (not a column swap, as D-1349 says) |
| 30 | Alolan Sandshrew [1035] | types | Ice | Ice/Steel | — | sheet error (official Ice/Steel) |
| 32 | Alolan Sandslash [1036] | Def | 110 | 120 | — | sheet error (official 120) |
| 61 | Golduck [55] | Atk/Def/SpD | 78/80/82 | 82/78/80 | 82/78/80 | sheet error |
| 79 (b) | Tentacool [72] | Atk/Def | 35/40 | 40/35 | 40/35 | sheet error (swap) |
| 84 (b) | Ponyta [77] | HP/SpA | 65/50 | 50/65 | 50/65 | sheet error (swap) |
| 85 | Rapidash [78] | types; Def, SpA | Fire; 75, 60 | Fire/Fairy; 70, 65 | Fire; 70, 80 | **mixed**: types = v3 (v4 added Fairy); stats neither |
| 93 | Seel [86] | SpA | 75 | 45 | 45 | sheet error |
| 155 | Galarian Articuno [1065] | Def/SpA/SpD/Spe | 100/95/125/85 | 85/125/100/95 | — (v3 Kanto = 100/95/125/85) | sheet error: the Galarian row carries the official Kanto stats. Row 154 (Kanto) equals v4 [144] exactly. |
| 246 | Phanpy [231] | SpA | 20 | 40 | 40 | sheet error |
| 289 | Ludicolo [272] | Def | 80 | 70 | 70 | sheet error |
| 304 | Slakoth [287] | HP | 60 | 45 | 60 | **sheet outdated from v3** |
| 325 | Medicham [308] | HP, Atk | 80, 80 | 60, 60 | 60, 60 | undetermined |
| 379 | Glalie [362] | types | Ice/Dark | Ice | Ice | undetermined |
| 404 | Deoxys, Normal [386] | Atk/Def/SpA/SpD | 150/50/150/50 | 180/20/180/20 | 150/50/150/50 | **sheet outdated from v3**. The v4 base record now has the Attack Forme stats (the same as form 1 [1132]). |
| 417 | Staravia [397] | HP/Atk/SpA/SpD | 60/85/35/55 | 55/75/40/40 | 55/75/40/40 | undetermined |
| 418 | Staraptor [398] | types | Normal/Flying | Fighting/Flying | Normal/Flying | **sheet outdated from v3** |
| 430 | Shieldon [410] | Atk/SpA | 22/62 | 42/42 | 42/42 | sheet error |
| 461 | Bonsly [438] | HP/Atk/SpD | 60/85/55 | 50/80/45 | 50/80/45 | undetermined |
| 462 | Mime Jr. [439] | Atk/SpA/Spe | 15/80/65 | 25/70/60 | 25/70/60 | undetermined |
| 473 | Hippowdon [450] | types | Ground | Ground/Rock | Ground | **sheet outdated from v3** |
| 494 | Glaceon [471] | HP | 80 | 70 | 65 | undetermined (v4 changed 65 → 70) |
| 511 | Dialga [483] | Atk/SpD | 120/100 | 100/120 | 120/100 | **sheet outdated from v3** (v4 swapped them) |
| 513 | Palkia [484] | Atk/Spe | 120/100 | 100/120 | 150/70 | undetermined |
| 517 (b) | Origin Giratina [1152] | abilities | Pressure ×2, — | Levitate ×3 | Contrary ×2 [501] | sheet error (v4 = official) |
| 518 (b) | Altered Giratina [487] | abilities | Levitate ×3 | Pressure ×2, — | Cursed Skin ×2 | sheet error (v4 = official) |
| 519 | Cresselia [488] | hidden ability | 月光守护 | #327: bank 0711 has only 327 names (0–326); description at 0712#327 | — (no hidden abilities) | undetermined: hack oddity (D-1346) |
| 528, 529 | Servine [496], Serperior [497] | types | Grass | Grass/Dragon | — | undetermined |
| 554 | Conkeldurr [534] | SpD | 75 | 65 | — | sheet error (official 65) |
| 597 | Sawsbuck [586] | Def/SpD | 75/80 | 70/70 | — | sheet error (official 70/70) |
| 630 | Braviary [628] | types | Fighting/Flying | Normal/Flying | — | undetermined |
| 654 | Diggersby [660] | Atk | 76 | 56 | — | sheet error (official 56) |
| 676 (b) | Helioptile [694] | Atk/Def | 33/38 | 38/33 | — | sheet error (swap) |
| 680 | Sylveon [700] | Def | 80 | 70 | — | undetermined |
| 731 | Bewear [760] | Def/SpD | 90/80 | 80/60 | — | sheet error (official 80/60) |
| 747 (b) | Hakamo-o [783] | Atk/SpA | 65/75 | 75/65 | — | sheet error (swap) |

Rows 528/529 are two sheet rows; the class-(a) count of 31 counts them separately. The docs equal v4 for every record.

### 4.2 Evolutions: 15 (a) + 2 (b)

Evidence: `a/0/3/4` [species].

| Row | Species | Sheet | Fresh v4 | v3 | Verdict |
|---|---|---|---|---|---|
| 3 | Ivysaur [2] | 36 | Lv 32 | Lv 32 | sheet error (official 32) |
| 105 | Krabby [98] | 26 | Lv 28 | Lv 26 | **sheet outdated from v3** |
| 109 | Exeggcute [102] | 35 | Leaf Stone; Dragon Scale → [1057] | Leaf Stone | sheet error |
| 213 | Misdreavus [200] | 25 | Dusk Stone | Dusk Stone | sheet error |
| 413 | Piplup [393] | 20 | Lv 16 | Lv 16 | sheet error |
| 414 | Prinplup [394] | 45 | Lv 36 | Lv 36 | sheet error |
| 481 | Mantyke [458] | 30 | method 21, Remoraid in party | Lv 30 | **sheet outdated from v3** |
| 547 | Boldore [525] | 35 | trade (5) | — | undetermined |
| 553 | Gurdurr [533] | 40 | trade (5) | — | undetermined |
| 587 | Zorua [570] | 48 | Lv 30 | — | sheet error (official 30) |
| 718 | Mareanie [747] | 38 | Lv 30 | — | undetermined (the sheet has the official 38) |
| 737 | Sandygast [769] | 32 | Lv 42 | — | sheet error (official 42) |
| 779 | Milcery [868] | 35 | method 37 + one of the 7 Sweets (615–621) | — | undetermined |
| 787 | Kleavor [900] | 35 (from Scyther) | none; Scyther → Scizor only (18, Metal Coat). Kleavor is wild on Route 42 at night. | Scyther → Scizor | undetermined |
| 680 | Sylveon (from Eevee [133]) | Fairy move, friendship 150 | method 27, param 9 (knows a Fairy-type move; the record has no friendship field) | — | undetermined (a friendship check in code was not examined) |
| 248 (b) | Porygon2 [233] | 聚焦镜片 Zoom Lens, by day | item **232** 焦点镜片 Scope Lens | item **276** 聚焦镜片 Zoom Lens | **sheet outdated from v3**. Was a (b) slip: the reclassification is new. |
| 386 (b) | Relicanth [369] | 500 | none | none | sheet error |

### 4.3 Moves: 5 (a) + 1 (b)

v4 evidence: `extra/new_move_data.narc` [move] (Gen 5 layout). v3 evidence: `a/0/1/1` [move].

| Row | Move | Field | Sheet | Fresh v4 | v3 | Verdict |
|---|---|---|---|---|---|---|
| 招式变动 10 | Skull Bash [130] | power | 100 | 120 | 130 | sheet error (100 is vanilla) |
| 招式变动 25 | Cross Chop [238] | accuracy | 90 | 100 | 80 | undetermined |
| 招式变动 40 | Dragon Claw [337] | crit | "easily crits" | crit byte 14 = 0; ROM description has no crit | effect 0 | undetermined |
| 招式变动 50 | Rock Wrecker [439] | target | 双 (both foes) | 0 (single) | 0 | undetermined |
| 招式变动 42 | Bounce [340] | one-turn | "(one-turn move)" | charge flag (bit 1) **clear**; effect 263 | vanilla two-turn (85/85/5) | **matches v4: our classification was wrong** (see note) |
| 技能机 34 (b) | Meteor Beam [800] | accuracy | 95 | 90 | — | sheet error (official 90) |

Bounce: in v4 the charge flag is cleared on exactly the moves whose v4 descriptions call them one-turn: Skull Bash (effect 145, also a vanilla two-turn id), Razor Wind and Sky Attack. The real two-turn moves keep the flag. Bounce belongs to the first group, so the data agrees with the sheet. Only its description (0738#340, "turn 1 jump, turn 2 attack") is stale, like the other stale descriptions in D-1308 to D-1319. An in-game test is still useful, because the effect id is the vanilla two-turn script.

### 4.4 Abilities: 2 (a)

| Ability | Sheet | Fresh v4 | v3 | Verdict |
|---|---|---|---|---|
| Water Veil (0712#41) | adds an Aqua Ring effect | description "不会陷入烧伤状态。" (prevents burns only) | same text | undetermined (battle code not examined) |
| #327 月光守护 | Cresselia's hidden ability | description only (0712#327); bank 0711 has 327 strings | not present | undetermined: hack oddity (D-1346) |

### 4.5 Encounters: 3 (a)

Evidence: map header → `a/0/3/7` record. The Growlithe mismatch is in the form bits: the sheet's form column is filled for 21 slots, and the ROM has 24 non-zero forms. The extra 3 are exactly these Growlithe slots.

| Sheet row | Map → record | Slot | Sheet | Fresh v4 | v3 | Verdict |
|---|---|---|---|---|---|---|
| 5420 | Route 24 (map 28) → 130 | surf 4 | Mareanie | Squirtle Lv 10 | Seaking Lv 10 | undetermined (the sheet is v4 data otherwise; this slot matches neither) |
| 1238 | Route 36 (map 40) → 25 | night 6 | Growlithe form 0 | Growlithe form 1 (Hisuian) | form 0 | **sheet outdated** (form = v3; the rest of the table is v4) |
| 4784–4785 | Route 7 (map 15) → 117 | night 4–5 | Growlithe form 0 | form 1 | form 0 | **sheet outdated** (same) |

### 4.6 Items: 13 (a) + 1 (a, rarity S) + 3 (a, names) + 3 (b)

"No source" means that none of the following gives the item, in reachable code only:

- item balls (file 141 and local scripts);
- hidden items;
- `GiveItem`, or std 2033/2008 with a constant `0x8004`;
- special marts (with the id-3 override) and the badge list.

The raw byte scan was run too, as a cross-check for anything the reachability walk might miss. It found the dead Saffron berry-seller code (§5) and a few `SetVar` coincidences.

| Row | Item | Sheet | Fresh v4 sources | v3 sources | Verdict |
|---|---|---|---|---|---|
| 173 | Qualot Berry #171 | Saffron shop | **none** | Saffron list 5 (map 409) | **sheet outdated from v3** |
| 176 | Tamato Berry #174 | Saffron shop | **none** | Saffron list 5 | **sheet outdated from v3** |
| 171 | Pomeg/Kelpsy/Hondew/Grepa #169/170/172/173 | Saffron shop; Fuchsia shard exchange | Fuchsia exchange only (file 804, map 56) | same + Saffron list 5 | **sheet outdated from v3** |
| 203 | Liechi/Ganlon #201/202 | Celadon 5F | S.S. Anne vendor ₽800 (file 156, map 307) | same + Celadon list 22 (map 374) | **sheet outdated from v3** |
| 205 | Salac/Petaya/Apicot/Lansat #203–206 | Celadon 5F | **none** | Celadon list 22 | **sheet outdated from v3** |
| 211 | Micle/Custap #209/210 | Route 9 girl; Celadon 5F | Route 9 vendor ₽1500 (file 190, map 17) | same + Celadon list 22 | **sheet outdated from v3** |
| 17 | Quick Ball #15 | regular shops | Saffron list 15 (map 409); Route 16 gift. The standard clerks' `SpecialMartBuy(3)` uses the fixed list at `0x020F8B3E`, which has no Quick Ball. | table list 3, used by the standard clerks (23 call sites, 27 maps), **includes Quick Ball** | **sheet outdated from v3** |
| 288 | Grip Claw #286 | item ball, Goldenrod B1F | **none**. B1F (map 200) has TM60, Revival Herb, Max Elixir and a hidden Parlyz Heal. | none | sheet error |
| 34 | Lemonade #32 | Azalea shop | vending machines only. Azalea (file 864) uses lists 3 and 45; list 27, which has Lemonade, is called by no script. | same | sheet error |
| 88 | TinyMushroom #86 | Azalea shop | hidden ×15, Route 9 gift; list 28 is unused | same | sheet error |
| 244 | Magnet #242 | Union Cave Saturday vendor | Goldenrod list 46 (map 191); gifts at maps 308, 41, 54, 183. Nothing in Union Cave (file 57). | gifts only | sheet error |
| 375 | TM46 #373 | Six Island Meowth reward | **none** (raw scan also 0) | only list 14, which no script uses | undetermined: hack oddity (D-1339) |
| 157 | Oran Berry #155 | ₽50 | New Bark ₽100 (841+0x8F7), Goldenrod ₽80 (890+0x8A1), Viridian list 30 at item price ₽20 | identical | sheet error |
| S | Full Restore, X Attack/Def/Spe/Acc/SpA/SpD, Guard Spec., Dire Hit | "no source" | Full Restore: item balls, hidden, Goldenrod list 48. X items / Guard Spec. / Dire Hit: Saffron list 5 + Celadon list 22 (and hidden). | Full Restore: balls + hidden; X items etc.: hidden | sheet error (v3 had sources too) |
| 116 | #114 | ？？？ | 钢铁铠甲 Steel Armor (gift, map 71) | ？？？ | **sheet outdated from v3** |
| 431 | #429 | 宝物袋, "renamed to 抗老喷雾" | name ？？？ (0219#429) | name **抗老喷雾** | **v4 regression**: v3 had the name, v4 lost it (D-1346) |
| 481 | #479 | 遗失物品, note "已改名战利品" | 战利品 Spoils | 战利品 | **matches v4: not a mismatch.** The sheet's own 变更情况 column records the rename. |
| 483 (b) | Machine Part #481 | Goldenrod cafeteria | Olivine (maps 231, 240) | same | sheet error |
| 372 (b) | TM43 #370 | Route 27 house | Route 26 house (file 220, map 297) | same (plus unused list 14) | sheet error |
| 431 (b) | anti-aging spray | Rare Candy, Sacred Ash, Lemonade | 101+0x1760..0x17FE: Durin ×10, Rare Candy ×5, Sacred Ash, Fresh Water (月见山泉水), ₽10000 | identical | sheet error |

### 4.7 Tutors: 3 (a) + 3 (b)

Evidence: `SetMonMove` / `TakeItem` in the tutor script files.

| Row | Tutor | Sheet | Fresh v4 | v3 | Verdict |
|---|---|---|---|---|---|
| 585 | Blackthorn (file 944) | Play Rough, free | teaches move 175 = 抓狂 Flail (0xD85, 0xE23) | move 175 = **嘻闹 Play Rough** (v3 reused the slot) | **v4 regression** (D-1305): v4 moved Play Rough to its own id and left 175 |
| 554 | Saffron Dojo (file 829) | Volt Switch, ₽10000 | 521 Volt Switch only when replacing a move on the first try (0x1155). The free-slot path (0x18E0) and the retry after cancelling (0x1A5C) teach 268 = 充电 Charge. ₽10000 afterwards. | 268 = **伏特替换 Volt Switch** on all paths | **v4 regression** (D-1347, its text already names both paths) |
| 588 | Dragon's Den (file 112) | free | takes 1 MysteryStone (0x4B1…) | same | sheet error |
| 590 (b) | Six Island (file 943) | Heavy Ball | takes Lure Ball (0x1945, 0x1A38) | same | sheet error |
| 605 (b) | Cliff Cave (file 880) | free | takes Moon Ball (0x30D, 0x400) | no tutor in v3 | sheet error |
| 571 (b) | Ecruteak (file 925) | free | HasItem/TakeItem Moomoo Milk ×10 (0x447/0x46D) | same | sheet error |

### 4.8 Totals

| | (a) | (b) | Total |
|---|---|---|---|
| Sheet outdated from v3 | 17 (species 5, evolutions 2, wild 2, items 7, name 1) | 1 (Porygon2) | **18** |
| v4 regression (sheet = v3 intent) | 3 (#429, Blackthorn, Saffron Dojo) | 0 | **3** |
| Mixed (Rapidash) | 1 | 0 | **1** |
| Neither: sheet error | 28 | 14 | **42** |
| Neither: undetermined | 25 | 0 | **25** |
| Matches v4: our classification wrong | 2 (Bounce, #479) | 0 | **2** |
| Our bug | 0 | 0 | **0** |
| | **76** | **15** | **91** |

Counted per crossref row. "Undetermined" includes the hack oddities #327, TM46 and Water Veil.

## 5. Other facts found on the way

- **Saffron's berry vendor is dead code.** Saffron (map 409, script file 825) still contains a ₽1000 berry vendor for Pomeg to Tamato at `0xCE`–`0x21C`. No script entry or jump reaches it, in v3 or in v4, so it does not count as a source. The berries came from shop list 5 in v3.
- **Standard Poké Marts in v3 and v4 don't use `MartBuy`.** std 2011 only prints the greeting "欢迎！要买东西是吧？". The standard clerks then do `SetVar 0x8004 3; CallStd 2052` (`SpecialMartBuy`): 23 call sites in v3 and v4. Other clerks in the same buildings use their town's list. No script calls std 2048–2050, the badge-tier `MartBuy`: 0 calls in v3 and v4, against 14 in US. The badge-tier list at `0x020F8D3A` is dead data in both hacks.
- **v4 redirects `SpecialMartBuy(3)`** to a fixed 18-item list at `0x020F8B3E`: Poké/Great/Ultra Ball, Potion to Max Potion, Revive, the status heals, Full Heal, Repel/Super/Max Repel, Escape Rope. Table entry 3 (medicine only) is unused. v3 used table entry 3: Poké/Great/Ultra/Quick Ball, Max Repel, Escape Rope, Potion, Super Potion, Antidote, Parlyz Heal, Awakening.
- **Deoxys:** the v4 base record [386] has the Attack Forme stats 50/180/20/180/20/150, the same as form 1 [1132]. v3 had the Normal Forme stats there.

## 6. Our bugs (proposed fixes, not applied)

None of these touches the ROM or the translation. They are errors in the generated player docs (`work/docs/items.md`, from `work/tools/docs/gen_docs.py`), found while re-checking the shop claims.

1. **Spurious "Poké Mart (standard clerk)" badge-tier section and "Poké Mart (from tier N)" sources.**
   - What is wrong: `mart_calls()` (gen_docs.py ~l.1071) treats `CallStd 2011` as a badge-tier mart call, but std 2011 is only the greeting. The badge list is never used (§5). As a result, items.md §Shops lists a 19-item badge-tier stock (with Full Restore from tier 6) at 27 places, and items such as Escape Rope and Repel get a "Poké Mart (from tier 2)" source.
   - Fix: drop the 2011 → 'badge' rule. Treat the badge list as used only if a reachable `CallStd 2048/2049/2050` or `MartBuy` exists (none in v4). Remove the §Shops tier table, or mark it unused.
2. **Shop list 3 shows the wrong items.**
   - What is wrong: items.md "(list 3)" prints table entry 3 (Potion … Full Heal). The game's `SpecialMartBuy` uses the fixed list at `0x020F8B3E` for id 3 (§5), so the standard clerks really sell Poké/Great/Ultra Balls, Repels and Escape Rope, and the docs miss those shop sources.
   - Fix: in `romdata.special_marts()`, or where list 3 is used, substitute the list at `0x020F8B3E` for id 3. Document the override (`0x0204787C`) in work/docs/README.md "Data sources".
3. **"bought/exchanged, script file 141 (no map)" on 68 items.**
   - What is wrong: this comes from the item-ball std script's shared `GiveItem(0x8004)` in file 141. `script_gifts()` (l.1034–1037) lists each possible item with the placeholder `pay=['(one of several…)']`, and the non-empty `pay` is then printed as "bought/exchanged". The real item-ball sources are already listed per map.
   - Fix: skip `ctx.ball_file` (file 141) in `script_gifts()`. Print menu-choice gifts as "gift (one of several)", not "bought/exchanged".

My own first draft also mapped hidden items by table position. That was wrong, and `gen_docs.py`'s mapping by the flag-index field is right: it matches the game code at `0x0203FCB4`.

## 7. Register updates (source agent:verifyB2)

I changed the texts of D-1345, D-1346, D-1349, D-1350 and D-1352 with `decisions.py set … --reason`, adding the v3 verdicts above. The texts of D-1347, D-1348, D-1351, D-1305 and D-1339 stay as they are: the verification confirms them unchanged.
