# In-game checklist (melonDS)

**Status (reviewed 2026-09-29): current (open checklist for melonDS; nothing ticked yet).**

Things only a playthrough can settle. They're grouped in play order, using `work/translate/play_order.json` and `bank_maps.json`. Each item gives the string ref (`bank#id`) and the decision id (`python3 work/tools/decisions.py show D-NNNN`). Tick an item when you've seen it. If something is wrong, record it with `decisions.py resolve D-NNNN --answer "..."` or tell the coordinator.

**Menu widths are measured, not guessed (D-1320).**
- Touch menus with 2–4 options have one line of 224 px per button.
- Touch menus with 5 options have 2 lines of 104 px; menus with 6–8 options have 2 lines of 96 px.
- Top-screen menus are sized to their widest option.

QA now enforces these widths. The menu items below are spot checks of that model.

## Any time (systems, UI, battle)

- [ ] **Naming screen:** English keyboard tabs, 7-character player name, 10-character nickname (code patches, D-0858). Reach it on the new-game intro, or at the Name Rater.
- [ ] **Options screen:** check what MUSIC SPEED, TITLE SCREEN and BATTLE BG do (0043 #1/#4/#5, D-0506). Reach it through Start → Options.
- [ ] **Trainer names of 8–10 characters in battle:** now stored {COMPRESSED} (D-1326, D-1329; supersedes D-0496). See "Integrity audit" at the end.
- [ ] **Battle info panel:** long labels such as "Extreme Sunlight" and "G-Max Steelsurge" fit (battle_string/0000, D-0518). Also check the hack's "B: EXIT / +: SWITCH" panel labels. Reach them in any battle with the info panel open.
- [ ] **Weather banners** (Sunny, Rain, Sandstorm, Hail, Fog, Snow, Primordial Sea, Desolate Land, Delta Stream) show the English labels (graphics inventory #15). Use a weather move in battle.
- [ ] **Move data** (see `move_data_audit.md`):
  - [ ] Volt Tackle recoil (D-1319).
  - [ ] Lunar Dance: whether it gives Sp. Atk/Speed +1 (D-1311).
  - [ ] Blast Burn, Hydro Cannon, Frenzy Plant and Rock Wrecker: whether the user has to recharge (D-1318).
- [ ] **Pokédex height/weight page:** full-width metric strings stay aligned (0799–0802, D-1297).
- [ ] **Pokédex search by letter:** A–Z, or a kana table (0790 #69–112, D-0520).
- [ ] **Label widths on three screens:**
  - [ ] EV screen stat labels Atk/Def/SpA/SpD/Spe; would the full names fit? (0815 #1–5, D-0503)
  - [ ] Box panel stat labels (0024 #41–47, D-0510).
  - [ ] Notice screen width (0816, D-0504).
- [ ] **Contest and battle labels** APPEAL, NEXT and "Shrouded in mist!" (0006 #57, 0005 #21/#35, D-0522).
- [ ] **Berry tag descriptions:** is the screen ever shown, and is the box 180 px × 3 lines? (0243, D-0829)
- [ ] **Walking Pokémon:**
  - [ ] 0258 #440: does the Yes/No box still appear (D-0919)?
  - [ ] 0258 #709 reads naturally (D-0920).
- [ ] **Link-battle menus:**
  - [ ] Cup names FANCY/PIKA/LITTLE/STANDARD/LIGHT CUP (0189 #25–29, D-0507).
  - [ ] "NO THANKS" keeps its 12 full-width padding spaces (0189 #172, D-0511).
- [ ] **Union Room menu** (top-screen window at x=24): "RECORD" was shortened from RECORDS, so the frame stays on screen (0189 #142, D-1320).
- [ ] **Pokégear phone:**
  - [ ] What {VAR:0103:3} prints in 0662 #11 and 0675 #11 (D-1192).
  - [ ] Koga is the registered caller for 0636 (D-1154).
  - [ ] Red's partner calls 0653 #7–9 now say "It's Ethan!", as the zh does (hack finding D-1324).
- [ ] **Pokégear map texts** 0266 #68/#117: which locations show them (D-1153).
- [ ] **Pokéwalker screens** (0267/0268, translated from the Japanese, D-1303). These are only reachable with Pokéwalker emulation; skip if melonDS can't do it.
- [ ] **Trainer battle line** 0718 #1396 was treated as a song lyric; is it really one? (D-0913)

- [ ] **Signposts with a map or route graphic (160 px box, D-1353):** the 62 DirectionSignpost type 0/1 messages now carry `"category": "sign"` and QA checks them at 160 px. In melonDS, read two of them and check that no line runs past the box and that the graphic on the left is not overlapped: the Lavender Town sign (0468 #4, 159 px, the tightest line) and the Cinnabar Island welcome sign (0511 #21, second page scrolls one line with {CLEAR}). Also note what the Pewter City town sign shows (0453 #20, the tutor line; hack finding D-1354).

## Kanto: Pallet Town → Cerulean

- [ ] **Pallet Town:** Mom gives the "Pokégear". Check that this item really is the Pokégear, not a Pokétch (0537 #8, D-0762).
- [ ] **Route 2:** SIZE-200% lines fit at 2x. 0313 #28 drops the James & Meowth label (0313 #28, 0314 #14, D-0541).
- [ ] **Pewter City:** 0457 #123 is a 200% line; is the "---" placeholder at #140 ever shown during the heist? (D-0553, D-0550)
- [ ] **Mt. Moon:**
  - [ ] 200% lines 0048 #5/#6/#20 (D-0553).
  - [ ] The fossil shop menu is now one line per option ("Helix Fossil, $5000", 0146 #16/#17).
- [ ] **Routes 3/4:** 200% lines 0319 #26 and 0321 #27 (D-0553).
- [ ] **Cerulean City:**
  - [ ] Gym statue layout (0462 #6/#7/#51/#52, D-0560).
  - [ ] Ball-for-shard menu (0460 #97–100) and TM shop menu (0461) use the new 2-line format.
- [ ] **Route 25:** 200% crowd lines 0356 #4/#10/#70–81/#84 (D-0571).

## Kanto: Vermilion → Cinnabar

- [ ] **Vermilion City:** 200% crowd lines 0476 #14/#19/#69/#74/#85/#102 (D-0571).
- [ ] **S.S. Anne:** 5-option shop menu 0252 #29–35 (item on line 1, price on line 2).
- [ ] **Diglett's Cave:** who is the Bonsly/Rhyhorn trader? The hack removed Brock's label (0045 #11–18, D-0575).
- [ ] **Route 9:** Butterfree menu. The zh options 0333 #107/#108 overflow by 3 px in Chinese too (D-1322).
- [ ] **Rock Tunnel:** menu options 0142 #113–115 fit (D-0854).
- [ ] **Power Plant:** the 200% line "Spare Zapdos!" (0338 #9, D-0584).
- [ ] **Lavender Town:**
  - [ ] Sabrina's menu options 0053 #154/#164/#170/#171 (D-0854).
  - [ ] 200% line 0053 #39 (D-0853).
- [ ] **Celadon City:**
  - [ ] 0547 #7 is a 200% line without the Ariana label (D-0853).
  - [ ] Is 0547 #105 a seal notice or a letter? (D-0855)
  - [ ] What does "show some appreciation" do? (0496 #29/#36, D-0622)
  - [ ] The Game Corner prize menu is now one line per option ("Mr. Mime, 3,333 Coins", 0502 #33–35, D-0623).
- [ ] **Fuchsia City:** 200% line 0090 #141 (D-0853).
- [ ] **Safari Zone Gate:** the added "Would you like to take part?" prompt (0508 #0/#1, D-0661).
- [ ] **Route 12:** which move TM08 teaches (0341 #7, D-0660).
- [ ] **Route 14:** which item "Pretty Scales" is (0344 #62, D-0688).
- [ ] **Saffron City:**
  - [ ] Which moves Ma Baoguo's tutor really teaches (0525, D-0689).
  - [ ] Whether Sabrina's gift for Fly is a TM or an HM (0523 #4, D-0690).
  - [ ] The Silph Co. elevator menu now has 2-line options (0531).
  - [ ] Radio music menu 0527 #12–16.
- [ ] **Cinnabar Island:**
  - [ ] 200% "Moltres!" without the Lawrence label (0511 #153, D-0719).
  - [ ] 200% lines 0546 #12/#48 (D-0853).
  - [ ] The Heat Rock price line is cut off in the hack's own menu (0594 #13, D-1322).

## Sevii Islands and Alto Mare

- [ ] **Island Cave:** which map actually runs the Burned Tower scene? (0059 #54–136, D-0878)
- [ ] **Five Island library:** which quiz answers count as right? (0384 #2–26, D-0881)
- [ ] **Four and Six Island trades:** the actual species traded (0554 #5, 0625 #4, D-0880).
- [ ] **Sky Pillar Peak:** "Special Ball" matches the item or sprite shown (0601 #32, D-0884).
- [ ] **One Island:** which item the "beach sunglasses" are (0540 #32, D-0763).
- [ ] **Two Island:** swap menu "Revival Herb ×2 / for Sacred Ash" (0440 #43–46).

## Kanto: League and after

- [ ] **Victory Road:** is the "---" placeholder in Crystal's ambush ever shown? (0126 #100, D-0746)
- [ ] **Route 26:**
  - [ ] Item quiz: which answers are correct? (0360 #4–28, D-0721)
  - [ ] Weakness Policy / Focus Sash menus now read "10 for $5000" (0359).
- [ ] **Route 27:** which item the "jingly bell" is (0362 #28, D-0722).
- [ ] **Mt. Silver:** 200% line 0124 #125 without Gold's label (D-0744).
- [ ] **Cerulean Cave:** 200% lines 0599 #45/#56 (D-0903).

## Johto: New Bark → Goldenrod

- [ ] **New Bark Town:** Sinnoh quiz answers (0536 #32–48, D-0764).
- [ ] **Cherrygrove City:** who hands over the Running Shoes? (0542 #7, D-0936)
- [ ] **Route 30:** Mr. Pokémon quiz answers (0370 #3–27, D-0935).
- [ ] **Violet City:**
  - [ ] Pokémon Academy Q&A answers (0103 #15–55, D-0935).
  - [ ] Falkner's honorific-free line (0550 #53, D-0936).
- [ ] **Route 32:** which item the "scorching-hot rock" is (0373 #8, D-0956).
- [ ] **Ruins of Alph:**
  - [ ] Where hint lines 0073 #0, 0075 #0 and 0083 #0 appear (D-0955).
  - [ ] The "seething-hot stone" (0071 #91, D-0956).
- [ ] **Azalea Town:**
  - [ ] The ＠０ item from Kurt (0563 #2, D-0981).
  - [ ] Slowpoke quiz answers (0556 #67–91, D-0984).
- [ ] **Ilex Forest:**
  - [ ] 200% "Celebi, you say?" (0081 #25, D-0983).
  - [ ] Which item "this helmet" is (0113 #121, D-0981).
- [ ] **Route 34:** 200% "Salamence: Saaa-la!!!" (0377 #136, D-0983).
- [ ] **Goldenrod City:**
  - [ ] Choice menus 0583, 0591, 0115 #74–76/#92 and 0579 #11–13 fit (D-0999; all measured ≤187 px of 224).
  - [ ] Is the 0589 copy of the Indigo semifinal ever run? (D-0998)
  - [ ] Whistle, "Storm No. 32" and Sport Ball (0589 #77, 0579 #33, 0115 #71, D-1000).
  - [ ] What the 3F "Berry Market" sells (0584, D-1001).
  - [ ] Pack menus in the new format ("Sitrus Berry / 10 for $10000", 0595).
- [ ] **Radio Tower:** radio quiz answers (0063 #4–25/#119–123, D-1015).

## Johto: Ecruteak → Dragon's Den

- [ ] **Ecruteak and Olivine:**
  - [ ] TM menus now read "Shadow Claw / TM65, $4000" (0604 #10, 0621 #10).
  - [ ] Which items the harbor worker's machine parts are (0602 #42, D-1077).
- [ ] **Battle Frontier:**
  - [ ] "Scratch-off" at the Exchange Service Corner (0098 #32, D-1072).
  - [ ] Castle prize: ribbon or prints (0107 #35, D-1073).
  - [ ] The Magician NPC (0100 #4, D-1076).
  - [ ] Battle Hall labels and store (0106 #95–97, D-1103).
- [ ] **Route 41 / Whirl Islands:**
  - [ ] Quiz menus 0735.
  - [ ] Speaker of 0123 #30 (D-1103).
- [ ] **Route 42 (Lapras lifeguard):** menu options 0393 #8/#13.
- [ ] **Boot Camp Ruins and Mahogany:**
  - [ ] Who says 0572 #90? (D-1121)
  - [ ] Is the cut-off line 0614 #6 used? (D-1122)
  - [ ] Gift items 0611 #31 and 0394 #11 (D-1123).
- [ ] **Blackthorn City:**
  - [ ] **Move Tutor bug:** it promises Play Rough but teaches Flail (script 944, D-1305).
  - [ ] Move Reminder and Draco Meteor prompts (0626 #16–24/#37–41, D-1138).
- [ ] **Dragon's Den and Route 46:**
  - [ ] Elder quiz (0128 #1–5).
  - [ ] Reward items and the "feather" (0399 #47, D-1136).

## Integrity audit (Phase A, `integrity_audit_text.md` §6)

- [ ] **Trainer names 8–10 characters in battle (D-1326, D-1329; supersedes D-0496):** battle Giovanni (any), Lt. Surge and Prof. Oak. Check the intro "…wants to battle!", the send-out lines and the defeat line. The intro and send-out lines were checked in DeSmuME on a test ROM for Giovanni, Lt. Surge and Kangaskhan; the defeat line and the real encounters are still open.
- [ ] **Frontier Brains on the VS screen:** Palmer, Argenta, Thorton, Dahlia and Darach (0719 #707–711) stay uncompressed, as in US, because this screen prints them without the formatter (D-1329).
- [ ] **Loan Pokémon / Hall of Fame:** the Pokémon from GiveLoanMon (#115 trade 6 = "Pidgeot", #172 trade 8) shows the nickname and OT correctly, and the Hall of Fame shows its met label.
- [ ] **In-game trade** (any of the 11): the received Pokémon's nickname and OT (e.g. Butterfree, Orochimaru with 10 characters, OT Wendell with 7) show in full on the summary.
- [ ] **Boot Camp Ruins PC:** the code 1-4-2-4-6 opens the passage, and Archer's diary hint reads ‘What it stands on’ (0572 #95, D-1114, D-1327).
- [ ] **Buena's Password:** the radio word appears among the three booth options, and choosing it scores.
- [ ] **Easy Chat (Primo, Violet Pokémon Center):**
  - [x] Does the word picker's alphabetical / initial mode still use the JP kana grouping or order? **Yes, confirmed by a player report (2026-10-04 screenshot):** ABC MODE shows the JP hiragana grid (あいうえお … わ！). Not text: no a027 bank holds it (0276 has only the labels) and no kana char table was found in arm9/overlays, so it is drawn by code or a JP graphic. A fix needs the US A–Z grid, its cursor layout and an initial→word index rebuilt from the English words. Open.
  - [ ] Do the words read OK?
- [ ] **Name Rater (Viridian):** a 10-character nickname; picking the same name gives the "same name" reply.
- [ ] **Chinese saves:** Pokémon caught in a Chinese save keep Chinese nicknames and OTs (expected; not a bug).

## Softlock checks (Phase A, `softlock_audit.md`)

Found by static analysis of the hack's scripts. Save before each check, and keep a savestate so a freeze costs nothing. Each behaves the same in the Chinese hack (D-1002): these are findings about the hack, not about our build.

- [ ] **Weekday siblings' ribbons (D-1331, suspected freeze):**
  - [ ] Set up: meet all seven weekday siblings (Route 40 Mon, Route 29 Tue, Lake of Rage Wed, Route 36 Thu, Route 32 Fri, Blackthorn Sat, Route 37 Sun), then talk to one on its day with a lead Pokémon that lacks that sibling's ribbon.
  - [ ] Expected from the scripts: the ribbon is given, a wrong jingle (sequence 20) may play, and the script stops. The text box stays open and the player can't move.
  - [ ] Note whether X (menu) still opens. If it does, saving and reloading unfreezes the player; if not, a reset is needed and the ribbon is lost.
  - [ ] Check whether the same sibling gives the ribbon again the same day (the daily flag is never set).
- [ ] **National Park north gatehouse (D-1332):** in the National Park, try to walk to the north gatehouse door at (33,15). Also try on a Bug-Catching Contest day. If you can enter the "Pokéathlon Dome" room, leaving it should crash or strand the player. Only enter from a savestate.
- [ ] **Route 34 photographer (D-1334):** on Cameron's weekdays, check whether Cameron ever appears on Route 34. The script hides him always.
- [ ] **Out-of-range flags (D-1333):**
  - [ ] Note the Pokédex caught count and whether Weezing (#110) is marked caught.
  - [ ] Finish the Mt. Mortar expedition (the Suicune / Route 42 Eusine scene) and check again.
  - [ ] Check whether the Viridian Mart promotion on Route 1 (free Berry Juice) runs only once.
- [ ] **Hall of Fame respawns (D-1335):** after catching Ho-Oh, Mewtwo, Articuno or Moltres and then entering the Hall of Fame, check whether the caught legendary reappears at its spot.
- [ ] **Blackthorn Move Tutor (D-1305, already listed under Blackthorn):** the Pokémon learns Flail, not Play Rough.
