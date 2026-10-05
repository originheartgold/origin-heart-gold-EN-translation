# Graphics inventory: baked-in Chinese (and other non-English) graphics

**Status (reviewed 2026-09-29): current (pass 3 is the latest audit).**

Status date: 2026-09-29 (pass 3: full re-audit). Compared: `work/rom/origin_v4.0.3_cn.nds` vs the user's USA HeartGold ROM.

## Method

1. **Diff the file systems.** The hack has 48 added files, 121 changed files and 262 identical files. Only changed or added files can hold new text art.
2. **Diff every graphics NARC member by member.**
3. **Render every changed or added NCGR.** Any 8×8 tile identical to a tile in the US member is dimmed, so only newly drawn tiles stand out.
4. **Check by eye**, then confirm US-vs-hack side by side.
5. **Reproduce it:** `python3 work/tools/gfx.py scan --out <dir>` writes `scan.tsv` plus one PNG per member.
6. **Pass 3 re-audit (screens and cells):** `python3 work/tools/gfx.py audit --rom <ROM> --out <dir>` renders every screen (NSCR) and every cell (NCER) of each NARC that has a changed NCGR, using the nearest NCGR/NCLR of the same NARC, and keeps only renders that differ from the USA ROM. Costume copies are compared with the ROM's own `a/X/Y/Z`. The sheets were read by eye, once for the Chinese hack and once for the built ROM, so rows already marked fixed were re-checked in the build. Pass 1 only looked at tile sheets, where OBJ labels are cut into 8×8 pieces. That is how the JP labels in #27–#30 were missed.
7. **Graphics inside code.** Some tiles are not in any NARC. The battle HP-box status icons are raw 4bpp tiles in the battle overlay (pret `gBattleHpBar_RawGraphicComponents`, USA overlay 12, the hack's overlay 14), so no NARC scan can see them (row #25). A heuristic scan of every USA overlay and arm9 for tile-like runs that changed in the hack turned up only this table (the other hits were code).
8. **Japanese leftovers.** The hack's header game code is `IPKJ`: it is built on the **Japanese** ROM. Graphics that the Chinese team did not redraw are therefore often the Japanese art, where the USA ROM has English. These count as untranslated too (rows #27–#30) whenever the USA ROM has English in the same slot.

Skipped as sprite-only: Pokémon, trainer and overworld sprite archives (`a/0/0/4`, `a/0/0/6`, `a/0/5/8`, `a/0/1/8`, `a/0/2/0`, `data/pokepic_*`, `data/pokeicon.narc`), `extra/new_battle_bg.narc` (battle backgrounds) and `a/2/6/4` members 14+ (the animated intro/title frames). They were spot-checked and hold no text.

**Costume copies.** The hack keeps per-costume copies of several NARCs: `data/clothes1/aXYZ.narc` and `data/clothes2/aXYZ.narc`, mirroring `a/X/Y/Z`. Any fix to such a NARC must also go into its copies. The build step does this through `"also"` and checks that the copies are identical first.

**Priority**
- **P0:** seen in the first hour or in every battle.
- **P1:** common menus.
- **P2:** rarer screens.
- **P3:** unused or debug data, or Japanese leftovers from the base game. No action planned.

## Table

| # | File / member | What it is | Where it appears | Chinese? | Fix strategy | Prio | Status |
|---|---|---|---|---|---|---|---|
| 1 | `a/0/0/8` #219–235, #237–241 (LZ10 NCGR) | Type icons (17 types) and contest-type icons (COOL/BEAUTY/CUTE/SMART/TOUGH). Palette #74 has 3 rows. | Battle move selection, summary moves page, move relearner, contest moves | y | Restore from US | P0 | **fixed** |
| 2 | `a/0/0/8` #236 | ??? slot, which is the hack's type 9 (FAIRY; hg-engine `TYPE_FAIRY 9`). Drawn as 妖. | As #1 | y | hg-engine FAIRY icon (tiles only). Keeps the hack's pink palette: #74 row 2, idx 10–12. | P0 | **fixed** |
| 3 | `a/0/0/8` #244–246 | Category icons (physical/special/status) | Battle, summary | n (pictograms, unchanged) | – | – | ok |
| 4 | `a/0/6/8` #131 (hack-added, 4×40 tiles, palette #130) | Coloured 32×16 type badges, 18 labels in the order NORMAL…DRAGON, FAIRY | Pokédex entry / registration page after a catch (the reported 普通) | y | New sheet `work/graphics/dex_type_list_en.png`, generated from the US battle-icon letters recoloured with the hack's label colours. The FAIRY row uses hg-engine letters. | P0 | **fixed** |
| 5 | `a/0/6/8` #36–52 | Pokédex type badges, 48×16 | Pokédex search / type pages | y | Restore from US | P0 | **fixed** |
| 6 | `a/0/6/8` #123 (hack-added) | Pokédex FAIRY badge (妖) | As #5 | y | hg-engine `dex_gfx/8_123` (tiles only) | P0 | **fixed** |
| 7 | `a/1/5/2` #1 | Touch-screen YES/NO buttons (是/否). Screens #2–9 have identical tile maps. | Poké Mart buy confirmation, nickname prompt, many yes/no prompts | y | Restore from US | P0 | **fixed** |
| 8 | `a/0/3/9` #64 | Status-condition icons (中毒 麻痹 冰冻 睡眠 烧伤 濒死) | Party screen, summary | y | Restore from US | P0 | **fixed** |
| 9 | `a/0/3/9` #0 | Summary sheet: contest condition labels (帅气度 可爱度 聪明度 美丽度 强壮度) | Summary, condition page | y | Restore from US. Only label tiles differ; the hack's NSCR #3 change touches other tiles. | P2 | **fixed** |
| 10 | `a/0/3/9` #135 | POKéRUS badge (病毒) | Summary | y | Restore from US | P2 | **fixed** |
| 11 | `a/2/6/4` #8 (+ screens #2–4, palette #1; hack-added NARC) | Title logo 口袋妖怪 起源心金 | Title screen | y | **User decision: bilingual.** Logo kept; "Origin HeartGold" in font-0 glyphs (gold, dark-brown shadow) at screen x=146, y=118, as in the mock-up. The logo layer is 8bpp NCGR #8 through screen #3 with palette #0, shown 10 px higher; the two colours go into palette slots 150/240, which no title or intro graphic uses. **One removable manifest entry** (`a/2/6/4`, note "OPTIONAL"; `gfx.py make-title-subtitle`). | P0 | **fixed** (`pass2_title.png`) |
| 12 | `a/0/6/8` #1 (+ `data/clothes*/a068` #1) | Pokédex header: 全国 / 城都 图鉴 (NATIONAL / JOHTO POKéDEX) | Pokédex top screen | y | **Layout check:** the maps differ, so a US restore is not possible. The hack shrank overlays #7/#8 to 80×24, and they only cover the first two characters. Fix: redrawn in the hack's layout (`gfx.py make-dex-labels`). The overlays show the US letters "JOHTO" or "NATIONAL" (NATIONAL condensed from 81 to 73 px). Screen #0 shows the US "POKéDEX" plate part after the overlay and the US "NATIONAL ◀ ▶ JOHTO" row. Tiles are re-allocated only among tiles that #1's own screens (#0/#7/#8, per pret) stop using. | P0 | **fixed** (`pass2_pokedex_splash.png`) |
| 13 | `a/0/6/8` #4 (+ copies) | Pokédex button labels 搜索 打开 结束 叫声 详细 分布 大小 样子 返回 | Pokédex bottom screen (see `graphics_dex_area_zh_buttons.png`) | y | Screens #5/#6 have US geometry and now show the US buttons. The hack's area page (#11) has **5** buttons (the US has 4). It keeps that geometry, with US-style letters: AREA, **INFO** (for 详细; DETAILS does not fit), SIZE, FORMS, BACK. Same generator as #12. The list bar #71 (CRY/DETAILS greyed) is the USA art too; the search bars #69/#70 keep the hack's frames (labels are text). Re-tiling never touches tiles no screen shows: the search page copies #4 tiles 98/101 as its label background (garbled bars until 2026-10-05, D-1505). | P0 | **fixed** (`pass2_pokedex_list.png`, `pass2_pokedex_area.png`) |
| 14 | `a/0/3/1` #10 and `data/namein.narc` #2/#10/#11 (+ `data/clothes*/a031`) | Naming keyboard tabs and buttons in a **Japanese** layout (かな/カナ/ABC/もどる/おわり), replacing the US UPPER/lower/Others/BACK/OK | Naming screen (player name, nicknames) | kana, not hanzi | Edited in place (`tile_range_from_png`, tiles 0–207 of #10, identical in all four NARCs). The pages are rearranged by the `naming-*` code patches (see `hardcoded_text.md`, "Naming keyboard"). Tab 1 (page 0, was the pinyin page かな) is now ABC and shows the hack's own "ABC" tab art. カナ (a–z/A–Z page) → **abc**. Tab 3 (was the full-width ＡＢＣ page) is now QWERTY → **QWE**. "1/♪" is unchanged. もどる/おわり → US **BACK**/**OK** tiles (same cells and palette). | P0 | **fixed** (`naming_fix_*.png`) |
| 15 | `battle/battle_graphics.narc` #33–49, odd members (hack-added, hg-engine-style) | Weather/terrain banners: 晴天 雨天 沙暴 冰雹 雾天 雪景 始源之海 终结之地 德尔塔气流 | Battle, while weather is active | y | Hack art and colours kept; only the label band changes (`gfx.py make-weather-banners`). SUN/RAIN/SAND/HAIL/FOG use hg-engine's English letter pixels. The others use font-0 lettering: **SNOW**, **DOWNPOUR** (Primordial Sea), **HARSH SUN** (Desolate Land) and **WINDS** (Delta Stream). The label is 50 px wide at most, so the full names do not fit. | P1 | **fixed** (not seen in the emulator: needs a weather battle) |
| 16 | `a/0/4/9` #41 (+ `data/clothes*/a049`) | Trainer card small labels (元 只 年月日 胜 负 …) | Trainer card | y | **Layout check:** US #41 fits the hack's screens, **but** the hack dropped the US format strings (bank 0717 has no `$…`, date or W/L strings) and baked the units into the card, so a plain restore would lose them. Fix (`gfx.py make-trainer-card`): each unit box gets the US background. 元 只 回 → blank, 年/月 → "/", 日 → blank, so dates read 26/09/28. 胜/负 → **W**/**L**. The hack's "TRAINER'S CARD" header is kept. | P1 | **fixed** (`pass2_trainer_card_*.png`) |
| 17 | `a/1/4/3` #6–11 | Pokégear clock/calendar: 星期一…日, dates 年 月 日 | Pokégear top screen | y | **Layout check:** only the NCGRs differ; the NCERs match the US. Restored from the US. | P1 | **fixed** (`pass2_pokegear.png`, shows MONDAY) |
| 18 | `a/0/1/5` #37 | Bag labels: 秘传, ①登录 ②登录 (HM, 1 SET, 2 SET) | Bag: HM pocket and registered items | y | Same 26-tile layout as the US. Restored from the US. | P1 | **fixed** (not seen: needs HMs or registered items) |
| 19 | `a/1/7/8` #17, `a/2/3/2` #8, `a/2/4/0` #16 | SWITCH button → 交换 | Pokéathlon / minigame screens | y | Only the SWITCH label tiles are copied from the US (`tiles_from_us`). a/1/7/8 #17 has other small hack edits, which stay. a/2/3/2 and a/2/4/0 are LZ11; `gfx.lz11_compress` was added. | P2 | **fixed** (not seen in the emulator) |
| 20 | `data/linkcapture.narc` #26 (hack-added) | Menu labels (读取 / 信息 / 退出 …) | Hack's link/capture feature | y | Font-0 labels **DETAILS**, (X):**INFO**, (Y):**EXIT**. Corrected 2026-10-02: the 96-tile file has only 48 runtime-loaded tiles; the generator now stays within 0–47. See `graphics_layout_audit.md`. | P2 | **fixed** (Python DeSmuME, supplied RC4 state; closed/reopened from Bag) |
| 21 | `a/0/4/6` #1, #3, #15 | Old title logos (口袋妖怪 灵魂之银 / 起源心金) and the "VER.SPECIAL Developed by 雁南飞" strip | Probably unused now (the title uses `a/2/6/4`) | y | Confirm in the emulator first. If shown, #15 can be relettered as "Developed by Yannanfei TB". | P2 | verify |
| 22 | `a/0/6/7` #28, #90, #96 | Old DP-style Pokédex sheet. The US ROM has **Japanese** here too, so it is unused. | – | y | none | P3 | – |
| 23 | `a/0/0/7` #26 | Sample move menu (火焰放射 高压水泵 …). The US ROM also has Japanese here, so it is unused. | – | y | none | P3 | – |
| 24 | `pbr/*.narc` (bag_gra, batt_obj, pst_gra, zukan, poketch) | PBR-link copies, Japanese kana | Not used in normal play | kana | none | P3 | – |
| 25 | **overlay 14** (USA overlay 12), file offset 0x4C0A8, 480 bytes: raw tiles, pret components 41–55 | **Battle HP-box status icons** 麻痹 冰冻 睡眠 中毒 灼伤 (PAR FRZ SLP PSN BRN; 3 tiles each; there is no FNT in battle) | Every battle, next to the HP bar (user report) | y | Restore from USA (op `code_from_us`: same layout, and the 38 other components are identical except the hack's "HP:"). No other copy exists in any overlay, arm9 or file. | P0 | **fixed** (`status_icons_battle_hpbox.png`) |
| 26 | `battle/battle_graphics.narc` #18 (cells NCER #19.0 / #19.1; hack-added; palette #17) | Hack's in-battle panel labels **Ⓑ退出** (B: exit) and **✚✚切换** (two D-pad icons, left/right and up/down lit: switch) | Battle: the hack's field/status info panel (overlay 12; its text is `battle_string/0000`). From code reading (not yet confirmed in game): opened from the battle command screen by tapping the top-right corner of the touch screen (ov14 hit-rect y 0–34, x 180–252, result 1 → ov14 0x022022F8 case 1 → ov12 0x021E4DA0). Inside, left/right cycle the battlers, B or Y closes. | y | **Exception: in-battle panel labels (D-1109).** No sourced art exists (USA ROM has no such panel; hg-engine has none on any branch), so the user approved composing the labels from the game's own letters. `gfx.py make-battle-panel-labels`: the hack's Ⓑ and both ✚ icons stay unmoved, palette/tiles/cells unchanged, and only the Chinese is replaced with font-0 letter pixels (white 3, grey shadow 4, the hack's label colours): **Ⓑ EXIT** and **✚✚ SWAP**. There are 22 px after Ⓑ and 24 px after the two crosses. "SWITCH" needs 34 px and "Switch" 31, so neither fits; "SWAP" is the closest 24-px fit (other options are "NEXT", or "Switch" if one cross is dropped). The colon of "B: EXIT" does not fit and the Ⓑ icon already stands for the key. | P0 | **fixed** (`battle_panel_labels.png`; not seen in the emulator) |
| 27 | `a/1/0/4` #5 | Battle result labels 胜 / 负 / 平 | Result display of link or facility battles (not seen) | y | USA WIN / LOSE / DRAW (`copy_us`; NCER #6 identical) | P2 | **fixed** (`pass3_restores.png`) |
| 28 | `a/1/1/3` #30 | CANCEL buttons shown as Japanese やめる (JP art) | Main menu / Mystery Gift / wireless screens | kana | `copy_us` (only the 12 label tiles differ) | P2 | **fixed** (`pass3_restores.png`) |
| 29 | `a/2/1/5` #16 | START button shown as Japanese スタート (JP art) | Minigame start screen (not seen) | kana | `copy_us` (only the label tiles differ) | P2 | **fixed** (`pass3_restores.png`) |
| 30 | `a/2/1/9` #12–21, #44, #45, #48–51 | Pokéathlon instruction screens: こうたい, まい, ポケスロン, JP player names, "POKETHLON" (JP art) | Pokéathlon event instructions | kana | `copy_us`: SWITCH, Pcs., YOU / Eoin / Aven / Shania, POKéATHLON. Only the label tiles differ. | P2 | **fixed** (`pass3_pokeathlon.png`) |
| 31 | `data/clothes1/a046.narc` #15, `data/clothes2/a046.narc` #15 | Costume variants of #21's strip: "VER.WUYIN / VER.ORIGIN Developed by 雁南飞" | Same as #21 (probably unused) | y | Same as #21: confirm in the emulator first | P2 | verify |
| 32 | `a/1/5/5` #2–46 (hack-added; the USA NARC has 1 member) | Japanese minigame title cards (きのみとり, ボールはこび, マラソン …) | Probably unused (no known screen) | kana | none unless seen in game | P3 | – |
| 33 | `a/1/7/8` #1, `a/2/2/4` #13/#17 | "POKETHLON", "GET!" (JP-ROM spellings in Latin letters) | Pokéathlon | n (Latin) | none (already English letters) | P3 | – |

**Status-condition icon sets (pass 3):**
- `a/0/3/9` #64: party screen and summary (PSN PAR SLP FRZ BRN FNT, plus PKRS). Fixed in pass 1; checked again in the build (`status_icons_party_summary.png`).
- Battle HP box: overlay 14 raw tiles (#25). Fixed in pass 3.
- `pbr/pst_gra.narc` #64: PBR copy, Japanese, unused (#24).
- There are no others. A palette-independent tile search of every NCGR in both ROMs found no further copy. The PC box, trade screen and move relearner show no status icons. The hack's HP-box component table has the vanilla size, so there are no extra statuses (TOX, frostbite, drowsy).

**Not graphics** (checked; these are message-bank text or have no text):
- The hack's notice pages: text is in a bank; the QR code graphic in `extra/intro_data.narc` has no hanzi.
- The outfit chooser 形象1/2/3/确认 (`a/2/6/5` holds only the background).
- The "Touch"/"CHECK"/"NEXT" buttons (already English).
- `a/0/1/4` #8, `a/1/0/9`, `a/1/2/0`, `a/2/6/5` and all sprite NARCs.

## Summary by priority

| Priority | Total | Fixed | Open |
|---|---|---|---|
| P0 | 14 | 13 fixed (#1, #2, #4–8, #11–14, #25, #26); #3 was already English | 0 |
| P1 | 4 | 4 (#15–18) | 0 |
| P2 | 10 | 8 (#9, #10, #19, #20, #27–30) | 2 (#21, #31 verify: old title strips, probably unused) |
| P3 | 6 | – | no action (#22–24, #32, #33) |

## Build step

- **Generated inputs are not in git.** `work/graphics/generated/*.bin`, `work/graphics/weather_en/*.png`, `work/graphics/dex_type_list_en.png` and `work/graphics/naming_labels_en.png` hold Nintendo and hack art (the title logo with the official Chinese Pokémon logo, the Pokédex header, the trainer card and so on), so `.gitignore` keeps them out of the public repo. `build.py` stage 3a ("regen") rebuilds them before every build by running all the `gfx.py make-*` generators from the two ROMs (`gfx.regenerate()`, or by hand `python3 work/tools/gfx.py regenerate`). The generators are deterministic: a fresh clone builds the same ROM and patch, byte for byte (checked 2026-10-04: same ROM and `.xdelta` SHA-1 with and without the old files). The hg-engine inputs in `work/graphics/vendor/` stay tracked (licensed and credited). The generators need no Pillow either (pure-Python PNG writer). `--no-regen-graphics` uses the files already on disk.
- **Stage:** `work/tools/build.py` stage 3b, "graphics", runs `gfx.apply_patches()` with `work/graphics/patches.json`.
- **Operations:**
  - `copy_us`: copy a NARC member from the USA ROM.
  - `tiles_from_file`: keep the hack's container and swap in the tiles of a vendored NCGR.
  - `tiles_from_png`: read tiles from an indexed PNG. The PNG reader is pure Python, so the build needs no Pillow.
  - `tiles_from_us`: copy only the listed tile ranges from the USA member.
  - `tile_range_from_png`: replace a tile range with the tiles of an indexed PNG strip.
  - `code_from_us`: copy a byte range of tile data from a USA code file (arm9/overlay, decompressed) into the hack's uncompressed code file, guarded by the SHA-1 of both ranges (battle HP-box status icons).
  - `member_from_file`: replace members with generated files, but only while the hack's member still has the SHA-1 the file was made from. The generators are `gfx.py make-dex-labels`, `make-title-subtitle`, `make-trainer-card`, `make-linkcapture` and `make-battle-panel-labels` (the PNG inputs come from `make-dex-type-list`, `make-naming-labels` and `make-weather-banners`); all of them run in stage 3a. They redraw into the hack's own layout, and `retile()` only overwrites tiles that no unchanged cell still shows.
- **Safety checks:** graphics format, compression, character depth/count/mapping, screen dimensions and palette size must match. `also` copies must be identical to the main NARC's member (except explicitly checked tile-range edits). Every changed screen map needs an entry in `work/graphics/layout_checks.json`; the build checks references against the runtime-loaded tile count and verifies the audited loader code has not changed. See `graphics_layout_audit.md`.
- **Verify step:** re-reads every patched member and every code range and checks their SHA-1.
- **Dry run:** `python3 work/tools/gfx.py check`.
- **Review sheet:** `gfx.py sheet ROM out.png` (needs Pillow).
- **Credits:** `work/graphics/CREDITS.md` records the hg-engine assets (commit `4d316b4e`, README terms: free, no donations, credit hg-engine).

## Emulator notes (pass 2)

- **Blank player name in DeSmuME screenshots is a harness artefact.** With the scripted touch input, the name buffer holds the right codes: 0x012B 0x013D ("AS", vanilla Latin), at 0x022E14F8 while naming. DeSmuME still prints the name as a blank gap ("Your name is  ?"). The user confirmed that **melonDS shows the name correctly** on the English build, so no fix was made. Nothing was changed in the keyboard, charmap or fonts for it.
- The DeSmuME battery save for a ROM file name lives in `~/.config/desmume/<rom name>.dsv`, not in the temporary directory. Savestates made with an older build go black when a screen loads new files, because the FAT offsets change. Boot a new build from scratch.

## Assets generated in this project (not sourced)

The user's rule (pass 3) is to search for existing English art instead of drawing. These earlier assets were generated from USA letter pixels, font 0 glyphs or hand-placed pixels. Search result for a sourced replacement (pass 3):

| Asset | Made from | Sourced replacement found? |
|---|---|---|
| `dex_type_list_en.png` (`a/0/6/8` #131, hack-added type list) | USA battle type-icon letters, recoloured; FAIRY letters from hg-engine | No. hg-engine `dex_gfx` holds only `8_003` (a USA-identical header) and `8_123` (the FAIRY badge already used). |
| Weather labels SNOW / DOWNPOUR / HARSH SUN / WINDS | font 0 glyphs | No. hg-engine `rawdata/weather_icons` (every branch) has only sun, rain, sandstorm, hail, fog, terrain and mega/primal HUD icons. |
| Naming-keyboard tabs "QWE" / "abc" (plus the tab-0 copy of the hack's "ABC") | hand-drawn 4-px letters (`gfx.TAB_FONT`) | No. The USA keyboard has UPPER/lower/Others tabs in a different layout, and neither hg-engine nor pret has these labels. |
| Pokédex header overlays JOHTO / NATIONAL (and INFO, the letter "N") | USA letters re-laid out; "N" hand-drawn; NATIONAL condensed | Partly. The USA letters are sourced; only the layout and the "N" are new. No fully sourced version exists for the hack's shrunken overlay. |
| Trainer-card unit edits ("/", "W", "L", blanks) | USA background plus font 0 glyphs | No (the hack removed the USA format strings) |
| Link-capture bar DETAILS / INFO / EXIT | font 0 glyphs | No (hack-only screen) |
| Battle info-panel labels Ⓑ EXIT / ✚✚ SWAP (#26) | font 0 glyphs next to the hack's own button icons (user exception D-1109) | No (hack-only panel; USA ROM and all hg-engine branches checked) |
| Title subtitle "Origin HeartGold" | font 0 glyphs (user decision D-0767) | Not applicable (the user asked for original lettering) |

Searched: the USA ROM; hg-engine (github.com/BluRosie/hg-engine, all 6 branches, by tree listing); pret/pokeheartgold (vanilla assets only, which are the same as the USA ROM); a GitHub repository search for the hack's name (no English asset repositories). Nothing was swapped.
