# Changelog

All notable changes to the English translation of 起源心金 (Pokémon Origin HeartGold) v4.0.3.
Patches apply to **Pokémon HeartGold (USA)**, CRC32 `C180A0E9`.

## [Unreleased]

### Added
- Options has a seventh row, TEXT SPEED: NORMAL or FAST (D-1604). NORMAL is the hack's original text speed. FAST prints up to three letters per frame when the frame has room and is never slower than NORMAL (D-1601). New games start on FAST; existing saves read as NORMAL. Text speed is an optional addition to the Chinese hack, so it is an exception to D-1002 (D-1575).

### Changed
- Text prints faster in towns and routes at both settings (D-1603). In maps where the hack's game loop runs at 30 fps, text used to print one letter every two frames; it now prints one per frame, as in the US game on FAST. Pauses counted in text printer turns, including auto-advance waits, are about half as long in those scenes.
- Pokégear calls wait for A or B on every page, also right after a battle (D-1600). The hack's battle code leaves auto-advance on (D-1599). Other text shown right after a battle may still advance by itself.
- Real DS, DSi and 3DS hardware support is being tested: six of the hack's anti-piracy checks now return the genuine-cartridge result (D-1616, D-1617). Nothing changes on emulators. Not yet tested on any real console or flashcart.

### Fixed
- Overworld freeze when certain objects come on screen: in the Team Rocket hideout under Mahogany Town (walking towards the camera ambush), on Five Island and on Seven Island. An object asked for an animation frame its texture doesn't have, and the game crashed (seen on melonDS and reported on iOS Delta; DeSmuME happened to keep going). Such an object now keeps the texture it already shows. A Bell Tower object can hit the same problem, but only in a state forced during testing. The untouched Chinese hack freezes in the same places, so this is a bug of the original hack; fixing it is a user-approved exception to "hack bugs are reported, not fixed" (D-2083, D-1337).
- Black screen or freeze with Bulbasaur as the following Pokémon next to water, e.g. at the Viridian City pond (reported on iOS Delta). A freeze reported on Route 22 next to Misty (Delta, melonDS) is probably the same bug: the faulty lookup shows at that pond with Bulbasaur following. The game looked up the wrong graphics for Bulbasaur's reflection in the water, one Pokémon off the range of following Pokémon, and read an empty pointer; Bulbasaur now uses its own graphics like every other following Pokémon, and no other Pokémon changes. Checked on melonDS (the game hung before the fix and no longer does) and DeSmuME; not tested on hardware. The untouched Chinese hack does the same, so this is a bug of the original hack; fixing it is a user-approved exception to "hack bugs are reported, not fixed" (D-2270, D-1337).
- Chinese characters and the wrong Pokémon in battle text: after Nature Power the game said "The foe's (错误)Pikachu's accuracy rose drastically!" (seen on Route 24, naming your first party Pokémon even when it was benched), and every turn a Pokémon was infatuated by Attract it said "The foe's (错误)<your Pokémon> fell in love with <the foe>!". Nature Power now says "Nature Power turned into Earthquake!" (or whichever move it calls), and the infatuation line names the infatuated Pokémon and the one it is in love with, on both sides, in wild, trainer and double battles. Both lines got the wrong data in the original hack (D-2277). (错误) means "error": it is the hack's own marker for a message that names no valid Pokémon, written into the battle code rather than the message text; it now reads "(Error) " should any other message still reach it. Checked on DeSmuME and melonDS. The untouched Chinese hack does the same, so these are bugs of the original hack; fixing them is a user-approved exception to "hack bugs are reported, not fixed" (D-2276, D-2278, D-1337). Six battle lines (accuracy rose drastically, fell in love with) now break earlier so they still fit with the marker.

### Added (tools)
- New patch format: every ROM change (code, data, strings and graphics fixes) lives in its own folder `work/patches/<id>/` with a `fix.toml` (why, what, decisions) and, for code, data and strings, an armips source and its disassembly snapshot. `work/patches/FIXES.md` lists them all, generated from the registry. `work/tools/check.py` is the one check entry point (registry and asm lint, ruff, unit tests; `--full` also builds the ROM and compares hashes).

### Known issues
- Downgrade: a save made with this version and then used in the Chinese hack or an older English patch may show an unusual MUSIC SPEED value, because text speed shares the old 4-bit options field. Set TEXT SPEED to NORMAL and save before downgrading.
- Tested with automated checks in DeSmuME; the overworld freeze and its fix were also checked in melonDS 1.1. Not covered: cutscenes, intro and credits, radio and TV, mail, the naming screen. No full second-emulator pass and no hardware test.

### Known issues in the original hack (reported, not fixed; D-1337)

- Evolution moves are skipped: reproduced Crobat missing Cross Poison, Charizard missing Air Slash and Gyarados missing Bite after Rare Candy evolution in both Chinese v4.0.3 and the English WIP. Their level-0 learnset entries are ignored by the evolution learning routine; ordinary current-level moves still work (D-1602; [investigation](work/notes/evolution_moves_investigation.md)).

## [1.0.0-rc5] - 2026-10-04

Tester release. 233 strings in 62 banks and one graphic differ from rc4: no code, script, map or Pokémon data changed.

### Fixed
- Blank item and move descriptions in the Bag, shops and the battle Bag: 17 English descriptions (Scope Lens, Sticky Barb, Lucky Egg, Soothe Bell, Focus Band, Shed Shell…) were longer than the 114-character buffer those screens copy into, so the game left the box empty. They are shortened to fit (F001); a new check (`text_buffer_check.py`) measures every description against the buffer read from the game's own code.
- Three long dialogues were longer than the 1,024-character buffer for field messages, so the game skipped them and could show missing or old text: the League briefing that sends you to the Bell Tower, Whirl Islands, Dark Cave and Lake of Rage (0065#60), the Lightning Whip lecture (0525#57) and the Marcel and Sunflora story (0389#56). Each one was retranslated from the Chinese with as few changes as possible to fit (D-1480).
- Chain Logger (link-capture) bar: the English graphic used tiles the screen never loads, so it drew garbage. It now stays within the loaded tiles, as the Chinese does (F002).
- Translation fixes from a review of the QA warnings against the Chinese (user-approved): the Plate inscription about a third Pokémon; the movers' Machop → Machoke option; four TM descriptions in the Battle Points prize list (Shadow Ball, Bulk Up, Calm Mind…) and the Air Cutter tutor now give the stat stages and critical-hit stage the Chinese gives; Curse now says "non-Ghost types"; the Route 29 comparison, the Relay Run's three Pokémon, the three circles, the Pokéathlon jump with three Pokémon; the Trainer House rules (one at a time, Pokémon under Lv. 50 unchanged); the Azalea Town TV top 3 (Sea Hare Well, Kurt the Poké Ball maker, D-1474); the Goldenrod sign now says Poké Mart, as the Chinese does (D-1475); the tackle-record announcements address you (D-1476); the Cerulean Gym clue; the bicycle commercial; the Battle Hall line now says Single Battle, as the Chinese does (D-1433).
- Easy Chat: 11 words that shared their English with another word (three "I"s, "YOU", "WOW", "OK"…) are now distinct, so passwords and the word picker are unambiguous (D-1462). New words: THIS GUY, THIS OLD MAN, YOURS TRULY, YOU THERE, LAD, OOOH, UH-HUH, HOWDY, I WON'T, COME ON IN, PERFECTION.
- Trainer names: Gus → Grady (no longer clashes with the other Gus, D-1434) and Nick → Nate (matches his dialogue, D-1116).
- The Mt. Moon couple's song is replaced with hum lines (song rule D-0368, D-1459). A line about the player is gender-neutral (D-1224), and the Route 11 grass-cutter is no longer called a boy (D-1435). The Quagsire thief's menu option now names Quagsire's Poké Ball (D-1482). Smaller fixes: a certificate's line breaks, MooMoo Farm, the debug slot labels.
- 50 Japanese leftover messages (Contest judging, dance and reception text; four Pokéwalker messages) were blank in English, as in US HeartGold. Blanking dropped the hack's control codes, including two YES/NO prompts, which could break a scene if one were ever shown. They are now translated from the Japanese with every code kept (D-1483). Pryce's double-size shout in the Mahogany Town hostage scene is one line on one page again, as in the Chinese (D-1389).

### Changed
- Anime and manga quotes now use the canon English wording (D-1436), checked against Bulbapedia. Team Rocket's motto, Cassidy & Butch's motto and their parodies use the original-series English dub lines ("Prepare for trouble!" … "Meowth! That's right!", D-1437); Team Rocket's defeat line is "Looks like Team Rocket's blasting off again!" (D-1438); Misty is a "Water Pokémon Master"; Crystal's Smoochum is Chumee (VIZ); Goh's catch line follows the dub.

### Added (tools)
- `work/tools/quality_runner.py`: one release gate with an auditable JSON report. It runs the tool and docs tests, translation QA, the build-artifact check, the description-buffer check, the static text checks (binary structure, change boundaries, control codes and buffer sizes for every message), the native text-loading sweep, and the emulator scenarios.
- Emulator scenarios (bag, full bag, Town Map, mart, party, summary, move order, card, battle…) that play the same save on the Chinese ROM and our build. They check the heaps, allocations, rejected text copies, the party and move state, and that text appears in selected screen regions.
- `qa_warning_inventory.py` (reconciles QA warnings against the reviewed ledgers) and a local review site for proposed fixes.

### Documentation
- `work/docs/` regenerated with fixes from a review against the scripts and the Chinese sources: species sources (771 of 1,025 national-dex species), items, trainers, encounters, trades and tutors. Evolutions the hack's code never checks are marked as not possible (D-1481).

### Known issues in the original hack, new since the rc4 notes (reported, not fixed; D-1337)
61 new findings, all in `work/translate/decisions/HACK_FINDINGS.md` and the register. Highlights:
- Evolution methods the code never checks: Nosepass and Eevee by location, Pancham, Galarian Farfetch'd and Yamask, Gimmighoul, Kubfu, White-Striped Basculin, Pawmo, Rellor and Finizen can't evolve that way (D-1481).
- After Protean or Soak, the type-change message names the move instead of the type (D-1461). The battle code is the hack's own.
- Radio quiz: pressing B on a question counts as a right answer (D-1479). Buena shows the lottery line after a right answer but gives no prize (D-1478). Uxie's quiz accepts 14 for question 4 (D-1439).
- Morty's optional 6-on-6 team has three Lv. 1 Pokémon (D-1440). Yellow's Singles option runs a Double Battle (D-1447), and Lex's Doubles option runs a Single Battle (D-1410). Agatha's and Lance's rematches show Koga's and Lorin's names (D-1442).
- Missables and shared flags: the Seafoam post-game Rocket scene removes the Articuno you could still catch before the Hall of Fame (TM14, D-1422); the Unown Report never progresses (D-1427); the Route 17 Shiny Stone can't be obtained (D-1400); several quests share one flag or variable (D-1401, D-1405, D-1412, D-1413, D-1416, D-1424, D-1429, D-1431).
- The Game Corner charges 50,000 for 50 coins (D-1415). Lantern riddles: a wrong answer at riddle 4 or 5 repeats riddles 2–5 (D-1419). The stats-page hint says L/R, but only L opens the IV/EV panel (D-1458).

### Known issues (ours)
- The battle emulator scenarios (`battle`, `battle_switch`) can't yet confirm every battle checkpoint; their memory and text checks pass.

### Verification
Release gate (`quality_runner.py`, all checks) on the rc5 build: 453 tool tests and 25 docs tests pass; translation QA 0 errors; 16 of 18 emulator scenarios pass and the 2 battle scenarios are incomplete, with 0 memory or text findings in any; the build artifact, description buffers (0 overflows) and native text loading (76,862 entries) pass; the static text check finds 0 control-code failures in 76,862 strings (it reports "incomplete" because it can't prove a maximum length for every runtime variable). The ROM differs from rc4 only in the message archive and the link-capture graphic. All 233 changed strings were reread against the Chinese (or the Japanese, for the leftovers).

## [1.0.0-rc4] - 2026-09-30

### Fixed
- Crash when switching Pokémon on the summary screen's skills page, and a bag that was 108 bytes from the same crash. The English text banks are up to 3× the size of the Chinese ones, and screens that loaded whole banks into their fixed memory ran out. Text is now always read line by line (code patch `msgload-all`, D-1390), so no screen loads a whole bank any more. See `work/notes/heap_audit.md`.
- Crash after double-size shouts (e.g. Misty and Gyarados on Route 3, Mt. Moon, Vermilion): 27 lines broke a line inside double-size text, which is drawn below the text box and corrupts memory. Each shout is now one line per page, as in the Chinese (D-1389). QA counts double-size lines as two lines.

### Added
- `work/tools/memcheck.py`: lists every whole-bank text load in the code, and plays menu scenarios on the Chinese ROM and our build in DeSmuME to compare how much memory each screen has left, and checks the game's heaps for corruption (run before every release).

## [1.0.0-rc3] - 2026-09-29

Tester release.

### Fixed
- Applied 390 line fixes (614 strings) from an external review. Most were official US lines kept although the hack had changed the Chinese. Highlights: the Lake of Rage Speed quiz now names Blaziken/Flaaffy, as in the game, so the answer matches; wrong species, move and item names (Muk, Aqua Jet, Ariados, Adrenaline Orb…); remaining softened swearing restored (D-0627); reversed or misleading instructions; inches → centimetres in fishing records.
- Renames to official names: A.J., Lara, Suzie, Bebe, Casey, and Kimono Girl Sakura (吔 renders as 樱). 精英训练家 is Ace Trainer everywhere.
- Town and route signposts with a map graphic now fit their 160 px box (62 signs).
- 85 lines where "Pokémon Center/League", Mt./Prof. or Lv. were split from the next word are rewrapped. Bare "Nidoran" now carries ♀/♂ as the Chinese does. 27 inconsistent renderings of identical Chinese are unified.
- Greetings follow the hack's Chinese ("Hello!"). A player-pronoun line is gender-neutral (D-1224).

### Added
- QA checks: split honorifics and abbreviations (error), species and move names not in the glossary (error), mid-sentence page breaks (warning), `qa.py variants` (identical Chinese, different English), and `decisions.py validate` (register references).

### Documentation (Phase B)
- Player documentation generated from the hack ROM's own data: Pokémon, moves, wild encounters, items, trainers, trades, tutors and the Move Reminder (`work/docs/`, regenerate with `work/tools/docs/gen_docs.py`).
- A row-by-row cross-check of the ROM against the hack team's spreadsheets (English versions of the sheets are kept local, not published) against the ROM (`work/notes/spreadsheet_crossref.md`) and a cross-reference of the docs against the scripts and dialogue (`work/notes/docs_crossref.md`).

### Known issues in the original hack found by Phase B (reported, not fixed)
- The Rock Tunnel move tutor promises Signal Beam but teaches Pollen Puff (D-1338).
- The Saffron Dojo tutor probably teaches Charge instead of Volt Switch to a Pokémon with fewer than four moves (D-1347, verify in game).
- TM46 Thief has no source in the game (D-1339), and 255 national-dex species from Gen 5 on can't be obtained (D-1344).

## [1.0.0-rc2] - 2026-09-29

### Fixed
- Trainer names longer than 7 characters (58 names, e.g. Giovanni, Lt. Surge, Prof. Oak) showed garbage in battle. They are now stored compressed, as in the US ROM, which fits up to 10 characters; the Frontier Brain VS-screen names stay plain. QA now enforces both limits.
- The Rocket HQ PC-puzzle hint now says ‘What it stands on’, matching the Chinese 立身之处 (the answer is the Pokémon's leg counts, 1-4-2-4-6).

### Known issues in the original hack (reported, not fixed; see `work/notes/softlock_audit.md`)
- The seven weekday siblings (Monica…Sunny) probably freeze the game when handing over their ribbon, once all seven have been met (D-1331).
- Two story flags are written past the flag array into save data, and one may mark Weezing as caught in the Pokédex (D-1333).
- The Blackthorn move tutor promises Play Rough but teaches Flail (D-1305).
- Legendary encounters come back after every Hall of Fame even if already caught (D-1335). A few NPC lines never appear (D-1334, D-1336).

### Verified (Phase A)
- Softlock audit: all 966 event-script files decoded; no dead end found on the main story path, and every menu that allows B releases the player.
- Only text, fonts, the listed graphics and the documented code patches differ from the Chinese hack. No event script, map, trainer or encounter data changed.
- In-game trade names, gift nicknames, passwords (all menu- or index-based), quiz answer order, and the naming-screen buffers all work with the English text. See `work/notes/integrity_audit_text.md`.

## [1.0.0-rc1] - 2026-09-29

First complete English release candidate. The final 1.0.0 follows after the script/quest integrity audit (see Known issues).

### Text
- Translated all Chinese text in the game's two message archives (`a/0/2/7`: 817 banks; `battle_string.narc`: 4 banks), 67,078 translatable strings (100%).
- **Story:** the whole Kanto half (Pallet Town → Indigo Plateau → Mt. Silver), the Alto Mare island chain, and the whole Johto half (New Bark → Sinjoh Ruins / Reversal Cave), including every partner, gender and choice branch.
- **Systems:** menus, battle messages (vanilla plus the hack's own), trainer names and classes, locations, Pokédex categories and all 1,440 Pokédex entries, and the move, item, ability and berry descriptions.
- **Side content:** trainer battle text, walking-Pokémon reactions, phone calls, radio, TV, Battle Frontier (facilities, Brains, trainer speeches), Pokéathlon, Easy Chat, mail, minigames and link/Wi-Fi screens, plus unused Diamond/Pearl/Platinum/SoulSilver leftovers.
- Hardcoded text outside the archives (the outfit chooser in overlay 58) is translated.
- Official US HeartGold text is kept wherever the hack left a line unchanged (17,237 strings), with names modernised.
- u/Shake69's partial v3 English was used as translation memory (with permission), and every line was reviewed and most were rewritten.

### Translation policy
- The English follows the hack's Chinese, not vanilla HeartGold. Tone is kept faithful: swearing, innuendo, dark and political content stay at full strength.
- Suspected bugs in the hack's own text are translated as written and listed in `work/translate/decisions/HACK_FINDINGS.md` (236 findings, including one gameplay bug: the Blackthorn move tutor teaches Flail instead of the promised Play Rough). Plain character typos are translated as intended and still listed.
- Modern official names in mixed case (Bulbasaur, Poké Ball). Menu labels use the US all-caps style.
- Song lyrics are never translated. They're replaced with short description lines. Team Rocket's and Cassidy & Butch's mottos use the project's own wording.
- All 1,325 decisions live in the decision register (`work/translate/decisions/`), with a review document (`DECISIONS.md`), a CSV and a change history.

### Graphics
- English type icons for battle, the summary screen and the move relearner. The FAIRY icon comes from hg-engine.
- Status icons (PAR/FRZ/SLP/PSN/BRN) on the battle HP box, party and summary screens.
- Pokédex type badges, header and buttons; touch YES/NO buttons; naming screen labels; trainer card; Pokégear calendar; bag labels; weather banners; battle info panel (Ⓑ EXIT / ✚✚ SWAP).
- Japanese leftovers from the hack's Japanese base were restored to US art: WIN/LOSE/DRAW, CANCEL, START, Pokéathlon instruction screens.
- Bilingual title screen: the original 起源心金 logo with an "Origin HeartGold" subtitle in the game's own font.
- Sources: the US ROM first, then hg-engine. A few labels (weather SNOW/DOWNPOUR/HARSH SUN/WINDS, some Pokédex and trainer-card letters) are composed from existing game glyphs because no English art exists; the naming tabs' QWE/abc letters and the Pokédex button "N" are drawn in the style of the existing labels. See `work/graphics/CREDITS.md`.
- Restored the US glyphs for … “ ”, which the hack had widened to 12 px.

### Gameplay changes (localisation only)
- Name lengths restored to US limits: 7 characters for trainers, 10 for Pokémon (the hack allows 5).
- Naming keyboard: the Chinese pinyin input is removed, and the keyboard opens on ABC. The tabs are ABC / abc / QWE / 1♪.
- No other behaviour changes. As in the original hack, there is no nickname prompt after catching a Pokémon (use the Name Rater).

### Tooling
- QA now enforces the real menu window widths (touch menus and window menus), measured from the game's code.
- `msgtool.py`: extract and insert the hack's text with its Chinese character table, round-tripping byte for byte.
- `ws.py`: the translation workspace. `qa.py`: pixel-accurate width and line checks per box type, tag checks, glossary checks and line wrapping.
- `decisions.py`: the decision register. `findings_report.py`: the hack-findings report.
- `build.py`: one reproducible build (text, glyphs, graphics, hardcoded strings, code patches, verification) that produces the xdelta patch.
- `gfx.py` and `hardcoded.py`: graphics and code patching, each checked against expected bytes.

### Known issues
- Some lines are checked only by tooling, not in game. `work/notes/ingame_checklist.md` lists 68 things to verify in melonDS.
- Not yet done (planned before 1.0.0): an audit of the event scripts for softlocks, and checks that trades, gifts, passwords and quests still work with the English text; plus Pokémon Legacy-style documentation generated from the ROM data and cross-checked against the author's spreadsheets.
- Move descriptions that disagree with the moves' real data are kept as the hack wrote them and listed in `work/notes/move_data_audit.md`.
- Foreign-language Pokédex text (FR/DE/IT/ES) that the game carries for traded Pokémon is left as is.

### Credits
Original hack: 雁南飞TB (Yannanfei TB). v4: Alex (hg-engine). Chinese patches: u/riap0526. v3 English: u/Shake69. Graphics: hg-engine contributors. Character table: Xzonn. See `README.md` and `work/notes/credits_and_sources.md`.
