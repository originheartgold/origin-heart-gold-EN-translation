# Integrity audit: did our text changes break anything? (Phase A, steps 2–3)

**Status (reviewed 2026-09-29): current (Phase A record; the one bug it found, D-1326, is fixed in rc2).**

Status: 2026-09-29, agent phaseA1. The audit compared three ROMs:
- the untouched hack, `work/rom/origin_v4.0.3_cn.nds`;
- our release candidate, `work/build/origin_hg_v4.0.3_en_wip.nds`, which is byte-identical to US + `work/release/v1.0.0-rc1/*.xdelta` (checked with xdelta3 and cmp);
- the US base.

Scripts were read with a disassembler built from pret's `asm/macros/script.inc`. The hack's script command table (arm9 `0x020F793C`) has 843 entries: the JP base lacks the US-only commands 843–852 (the `*Indef` / plural buffers). Commands 0–842 have the same numbers as in pret. Code was read with capstone, against the pret C sources.

**Result: one real bug caused by our build (trainer names in battle, D-1326).** Everything else is in scope or safe.

## 1. Proof of scope (file-by-file diff)

| What | How verified | Result |
|---|---|---|
| File table | ndspy: 551 files in both ROMs, identical names | OK |
| Event scripts `a/0/1/2`, map data, trainer/encounter/item data | Byte compare of every FAT file | **Identical.** No script or map file differs. |
| Text: `a/0/2/7` (790 of 817 banks), `battle/string/battle_string.narc` (4/4) | Member diff; per-bank string counts | Only these changed. Every bank has the same string count as the hack, so script message ids still line up. |
| Fonts `a/0/1/6` members 0, 1, 2, 4 | Glyph-level diff | Only glyphs and widths `01AF` … `01B4` “ `01B5` ” changed |
| Graphics: 25 NARCs (`a/0/0/8`, `a/0/1/5`, `a/0/3/1`, `a/0/3/9`, `a/0/4/9`, `a/0/6/8`, `a/1/0/4`, `a/1/1/3`, `a/1/4/3`, `a/1/5/2`, `a/1/7/8`, `a/2/1/5`, `a/2/1/9`, `a/2/3/2`, `a/2/4/0`, `a/2/6/4`, `battle_graphics`, `linkcapture`, `namein`, clothes1/2 copies of a031/a049/a068) | Changed members vs `work/graphics/patches.json` (members + `files`; now the `[[graphics]]` entries of `work/patches/gfx-*`) | Every changed member is covered by a patch entry. Nothing else changed. |
| arm9 | Byte runs vs `code_patches.json` (now `work/patches/*/fix.toml` `[[code]]`) | 75 runs, all inside the 16 arm9 patches (5 namelen + IME + 10 keyboard rows); the other 3 of the 19 code patches are in overlays 44 and 49 |
| overlay 44, 49 | Byte runs | `namelen-kind7`; `namelen-player-intro` / `namelen-rival-intro` only |
| overlay 58 | Byte runs + overlay table | Chooser strings (0x6F0–0x70B blanked or rewritten, pointers +0x7C0/4/8, 56 bytes appended at 0x7E0). The ov58 table entry size/ramSize is 2016 → 2072. As documented. |
| overlay 14 | Byte runs | Only 0x4C0A8–0x4C287 (480 bytes = the `code_from_us` HP-box status tiles) |
| arm7, arm7 overlay table, other overlays | Compare | Identical |
| Header | Raw diff of 0x0000–0x3FFF | 0x31 (arm7 offset), 0x41 (FNT), 0x49 (FAT), 0x69 (banner offset), 0x80–0x82 (used ROM size), 0x15E (header CRC), 0x1000 (RSA-signature offset that ndspy writes). These are all fields ndspy rewrites. |

**Nothing unexpected.**

## 2. Text that the game compares, copies or stores

| What | How verified | Result |
|---|---|---|
| In-game trades: nicknames and OT names | Hack bank **0198** (US 0200), 13 trades. `_CreateTradeMon` copies them into nickname u16[11] / OT u16[8]. `MonIsInGameTradePoke` (hack 0x0206CD14) reads bank 0xC6 into String(12)/String(8) and compares. | EN nicknames ≤10 (Butterfree and Orochimaru are exactly 10); OTs ≤7 (Wendell is exactly 7). The OT of trades 1 and 6 (bank strings #14 and #19) is the literal `{VAR:0103:0}`, the same as in the hack. OK. |
| Loan Pokémon (GiveLoanMon trade 6 in script #115, trade 8 in #172) | Script disassembly | The hack's scripts never use CheckReturnLoanMon (the text-comparing command). `MonIsInGameTradePoke` is still used by the Hall of Fame met-location label, and English-vs-English still matches. OK. |
| Species names used as default nicknames | `GetSpeciesNameIntoArray` copies with **no** limit into 11-unit buffers | Bank 0232: 1439 names, max 10 units. OK. |
| **Trainer names in battle** | Hack `EnemyTrainerSet_Init` 0x02072544: `CopyStringToU16Array(name, trainer.name, 8)`. Trainer data (a/0/5/5) members are 20 bytes, so the name is never initialised elsewhere. | **BROKEN by our build**: 58 names in 0719 are 8–10 units (see §4, D-1326). |
| Battle Frontier trainer names | Hack bank 0026 (US 0027), `CopyStringToU16Array(…, 8)` after a clear | All ≤7. OK. |
| Default box names | arm9 0x02072A36: 24 boxes from 0023 #6–23 and #94–99, 20-unit slots, unbounded copy | "BOX 1"–"BOX 24", ≤6 units. OK. |
| Default player/rival names | Bank 0247 #0–35, #84, copied into nameInputFlat (limit 10) → save (8) | ≤5 units (Red, Ash, Dummy, Heart, Green, Leaf, Soul). OK. |
| Rocket HQ passwords (D-1112/D-1113) | Script #91 (bank 0112) | Flag-based: 211/502 set when the player hears the password. **No typing and no text compare.** OK. |
| Voice-lock door (D-1111) | Script #90 (bank 0111 #100–102), Chatot scene #165 | Yes/No + flags; the Chatot recording commands only check that a recording exists. No text compare. OK. |
| Boot Camp Ruins PC puzzle (D-1114) | Script #881: five 0–7 digit menus built from 0572 #72–79 (copies of "0"–"7") | Index-based; the accepted code is **1-4-2-4-6**. The translation can't break it. D-1114 wrongly says 07322 (D-1327). |
| Buena's Password | Scripts #29/#30; `GetBuenasPassword` = base #40 + 3·(set/3), answer = set%3. The radio reads #40+set. | Index-based. EN 0063 #40–69 == 0064 #40–69, and no triplet has duplicate options. OK. The hack's Chinese differs at #53 (D-1328, harmless). |
| Primo Easy Chat passwords | Script #857: PromptEasyChat → PrimoPasswordCheck1/2 compare **word ids** (derived from the Trainer ID) | Language-independent. The Easy Chat words differ from the US words for 48 ids (hack-driven wording), so US password generators may name words that don't exist here. Low priority; see the checklist. |
| Quizzes | 22 quiz menus found (radio quiz #29, #220, #229, #734, #744, #753, #792, #905, #922) | Every option's English matches its own zh id, so the order is kept. The digits of all 2022 script menu options match zh↔en; the 49 differences are only formatting ("1个" dropped, TM5→TM05). OK. |
| Name Rater / script nicknames | 33 NicknameInput uses → `CallTask_NamingScreen` (maxLen = patched 10). Result check: kind 1 compares against the old nickname (String 12). | OK. |
| Group names | kind 5: `sub_0202C88C` duplicate check, stored with CopyStringToU16Array(…, 8) | maxLen 7 (patched) fits. OK. |
| Mystery Gift (#144) | MysteryGift commands only | No text keys. OK. |
| Record mixing / text as flags | Scan of script commands | HGSS has no record mixing. No script command compares message text. OK. |

## 3. Naming-screen callers (NamingScreen_CreateArgs, hack 0x02081DA4)

| Caller | Kind | Hack → our build | US | Save buffer |
|---|---|---|---|---|
| ov49 0x021E49D2 (Oak's speech) | player | 5 → **7** | 7 | profile name u16[8] |
| ov49 0x021E49EA | 3 (rival kind in Oak's speech) | 5 → **7** | 7 | rival u16[8] |
| arm9 0x0203EE2E (script CallTask_NamingScreen; maxLen patched at 0x02042862/892/91E, 0x020490DA) | player / rival / nickname / group | 5 → 7/7/**10**/7 | same | 8 / 8 / 11 / 8 |
| arm9 0x02090946 (egg hatch) | nickname | 5 → **10** | 10 | 11 |
| ov16 0x021E7DDC (PC box) | box | 8 | 8 (US ov14) | 20 |
| ov44 0x02228DAE | kind 7 | 5 → **7** | 7 (US ov43) | – |
| ov77 0x02228BCC | kind 0, maxLen 8 | 8 (unchanged) | 8 (US ov80) | – |
| Battle capture | – | removed by the hack (D-1040) | ov12, 10 | – |

Every caller now matches US, and every save buffer holds its limit + EOS. Nothing overflows. The hack's String_New size profile matches US (e.g. trade compare 12/8), so the JP-base code keeps the US buffer sizes. The hack has no script uses of NamePlayer (172) or NameRival (143).

## 4. What our build broke, and the proposed fix

**Trainer names of 8–10 characters (D-1326, high).**
- Where: 58 entries in 0719, e.g. Giovanni ×8, Lawrence ×6, Lt. Surge ×3, Impostor ×3, Marauder ×3, Prof. Oak, Weepinbell, Kangaskhan, Granny Mae ×2, Mean Birds, Wild Birds, Dragonite.
- Why it breaks: the battle copies the name into `u16 name[8]`. If the name doesn't fit, the copy is skipped, and GF_AssertFail only resets during a link. The trainer then shows uninitialised stack data as a name, which can be garbage or blank.
- How US avoids it: all 0729 names are stored `{COMPRESSED}` (0xF100 + 9-bit packing). That fits ≤10 characters into 7 units.
- The hack keeps `String_Cat_HandleTrainerName` (0x0202703C), which the message formatter (0x0200C782) calls, so compressed names expand on display.
- All 58 names are ≤10 characters and use only codes < 0x1FF, so they can all be compressed.
- **Fix:** in build.py, encode every string of bank 0719 with `{COMPRESSED}` (msgtool `compress_codes`). Add a QA rule: 0719 ≤10 characters, codes < 0x1FF.
- The fallback, shortening the names to 7, would lose official names.
- Then check one Giovanni and one Lt. Surge battle in melonDS.

**Status (agent fixA1, 2026-09-29): fixed.** `ws.export` writes 0719 `{COMPRESSED}` (qa_config.json `compressed_banks`; ids 707–711, the Frontier Brains, stay plain like US 0729 because hack ov77 0x0223616A prints them without the formatter). `build.py` verifies every stored name fits u16[8] and decompresses to the English. QA: categories `trainer_names` (0719) and `frontier_names` (0026, ≤7). DeSmuME test ROM: the old rc1 shows "Rocket Boss <garbage>", the new build shows Giovanni, Lt. Surge and Kangaskhan. D-1329, D-1330.

## 5. Emulator checks (headless DeSmuME, my own driver in the scratchpad)

| Check | Result |
|---|---|
| New game → notices → Oak's speech → outfit chooser (English "Outfit 1–3 / OK") → player naming | The keyboard opens on ABC. The entry field has 7 slots. After the 7th letter the cursor jumps to OK. "Your name is AAAAAAA?" → "AAAAAAA! Are you ready?" shows the full 7 characters. |
| Rival naming | Not in the hack's intro (it goes straight to the bedroom). No script calls NameRival, so this wasn't reachable. |
| Script nickname, in-game trade, password | Not practical headless: they need hours of play. The passwords turned out to be flag/menu based, with nothing to type. |

Note: DeSmuME keeps a battery save from an earlier session at `~/.config/desmume/origin_hg_v4.0.3_en_wip.dsv`. "Continue" loads it. I didn't save in game.

## 6. New items for `ingame_checklist.md` (since added there, section "Integrity audit")

- **Trainer names 8–10 characters in battle (D-1326, supersedes D-0496):** after the 0719 compression fix, battle Giovanni (any), Lt. Surge and Prof. Oak. Check the intro "…would like to battle", the send-out lines and the defeat line.
- **Loan Pokémon / Hall of Fame:** the Pokémon from GiveLoanMon (#115 trade 6 = "Pidgeot", #172 trade 8) shows the nickname and OT correctly, and the Hall of Fame shows its met label.
- **In-game trade** (any of the 11): the received Pokémon's nickname and OT (e.g. Butterfree, Orochimaru with 10 characters, OT Wendell with 7) show in full on the summary.
- **Boot Camp Ruins PC:** the code 1-4-2-4-6 opens the passage (D-1327).
- **Buena's Password:** the radio word appears among the three booth options, and choosing it scores.
- **Easy Chat (Primo, Violet Pokémon Center):**
  - Does the word picker's alphabetical / initial mode still use the JP kana grouping or order?
  - Do the words read OK?
- **Name Rater (Viridian):** a 10-character nickname; picking the same name gives the "same name" reply.
- **Chinese saves:** Pokémon caught in a Chinese save keep Chinese nicknames and OTs (expected; not a bug).
