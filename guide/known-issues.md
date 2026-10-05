# Known issues

[← Guide index](README.md)

These are suspected bugs in the original Chinese hack, found by reading its game files. The translation keeps the hack's behaviour exactly as it is, so they are reported here, not fixed. Most haven't been confirmed in game yet; the entries that were tested in an emulator say so.

Each entry says what you would do in game, what goes wrong, and how to avoid it or recover. Most entries are about a missed item, scene or battle. A few can freeze the game (the weekday siblings' ribbon gifts, a lost battle in Rock Tunnel), and two scenes write past the end of the game's story records into your Pokédex data (see [Out-of-range story records](#out-of-range-story-records-save-data)).

## Check these first

These entries can freeze the game, cost you something, or close a quest or battle for good. Everything else on this page is cosmetic, in your favour, or can't happen in normal play.

- **Can freeze the game:** [Rock Tunnel corner kid loss](#rock-tunnel-corner-kid-loss), [Arthur's ribbon freeze](#arthurs-ribbon-freeze), [Santos's and Wesley's ribbon freeze](#santoss-and-wesleys-ribbon-freeze).
- **Writes to your Pokédex data:** [Out-of-range story records (save data)](#out-of-range-story-records-save-data).
- **Can take more money or items than it should:** [S.S. Anne TM price](#ss-anne-tm-price), [Sprout Tower offerings](#sprout-tower-offerings), [Fortune-teller's price](#fortune-tellers-price), [Game Corner 500-coin option](#game-corner-500-coin-option), [Charcoal Kiln HM01](#charcoal-kiln-hm01), [Pidgeot loan returns a different Pidgeot](#pidgeot-loan-returns-a-different-pidgeot).
- **Lost for good unless you act first:** [Bruno's Pewter City challenge](#brunos-pewter-city-challenge), [Pikachu starters' Charmander quest](#pikachu-starters-charmander-quest), [Virtue trial and the four-leaf clover](#virtue-trial-and-the-four-leaf-clover), [Cerulean burglary deadline](#cerulean-burglary-deadline), [Route 5 shelter raid](#route-5-shelter-raid), [Pokémon Tower Magcargo is missable](#pokémon-tower-magcargo-is-missable), [Misty's Gyarados and the Viridian Gym trials](#mistys-gyarados-and-the-viridian-gym-trials), [Switching sides at the construction clash](#switching-sides-at-the-construction-clash), [Swimmer Marina and the Dragonair delivery](#swimmer-marina-and-the-dragonair-delivery), [Losing on the Celadon roof](#losing-on-the-celadon-roof), [Sitrus Berries and the eating contest](#sitrus-berries-and-the-eating-contest), [Grandma's treats deadlines](#grandmas-treats-deadlines), [Cynthia and Steven in Fuchsia City](#cynthia-and-steven-in-fuchsia-city), [Misty missing from Cerulean Gym](#misty-missing-from-cerulean-gym), [TM14 Blizzard](#tm14-blizzard), [Crystal Onix](#crystal-onix), [Cinnabar graffiti couple](#cinnabar-graffiti-couple), [TM86 Grass Knot](#tm86-grass-knot), [Bikers' red envelope and Big Sis](#bikers-red-envelope-and-big-sis), [Cherrygrove Wooper boy and the clover hunter](#cherrygrove-wooper-boy-and-the-clover-hunter), [Pokémon Academy class and Youngster Ward](#pokémon-academy-class-and-youngster-ward), [Losing to Goh in Union Cave](#losing-to-goh-in-union-cave), [HM08 and Mr. Pokémon's quiz](#hm08-and-mr-pokémons-quiz), [Pewter Museum Brock and the Route 30 Chikorita](#pewter-museum-brock-and-the-route-30-chikorita), [Koume, Sakura and the bug hunt](#koume-sakura-and-the-bug-hunt), [Rocky Helmet and the bug hunt](#rocky-helmet-and-the-bug-hunt), [Purugly quest and the bug hunt](#purugly-quest-and-the-bug-hunt), [Forest of Time during the bug hunt](#forest-of-time-during-the-bug-hunt), [Dream World battles before the old man](#dream-world-battles-before-the-old-man), [Pokéathlon Dome and the Route 36 tree](#pokéathlon-dome-and-the-route-36-tree), [MooMoo Farm Miltank fall sick again](#moomoo-farm-miltank-fall-sick-again), [Burned Tower beasts scene and the expedition leader](#burned-tower-beasts-scene-and-the-expedition-leader), [Jirachi stone and the story counter](#jirachi-stone-and-the-story-counter), [Durin Berries for the Anti-Age Spray](#durin-berries-for-the-anti-age-spray), [Blackthorn Gym Trainers](#blackthorn-gym-trainers).
- **One chance only (save first):** [Lugia: one chance](#lugia-one-chance), [Uxie, Mesprit and Azelf: one chance](#uxie-mesprit-and-azelf-one-chance), [Raikou: one chance](#raikou-one-chance), [Dialga and Palkia: one chance](#dialga-and-palkia-one-chance), [Giratina after Lance's visit](#giratina-after-lances-visit), [Arceus and Regigigas out of reach](#arceus-and-regigigas-out-of-reach).

## Pallet Town to Pewter City

[Quests on this page](01-pallet-to-pewter.md)

### Mankey thief quest and Blue's Viridian scene

**Blue's scene in Viridian City could end the Mankey thief quest, but in practice it can't.** If Blue's farewell scene in Viridian City played while the Mankey quest was still open, the Mankey would vanish and the Fast Ball would be lost. In normal play Blue's scene always comes first: it blocks the only way north from the Route 1 gatehouse, before you can reach the street-light keeper. The Route 1 tutorial has also already closed the same step, so nothing changes. Harmless. Not confirmed in game.

*Source:* file 739 script 14 (block L3274, `SetFlag 1330` at @3339). Step trigger at ≈1023–1026,266 (var 0x4075 == 0) across the only path north from the Route 1 gatehouse; the keeper stands at ≈1019,255. The quest's other flags (1335/1336) aren't touched by the scene. Path read from the map's collision data (ledges and HM obstacles not modelled).

### Unused thief-quest version

**The game holds an unused version of the thief quest.** In it the Pikachu or Mankey runs off, and on Route 22 an angry man wants to kill the Mankey ("Stop him?"). No player can see it. One of its unused scenes even plays Arcanine's cry for the Mankey, with a "Meowth: Meo-!" line. Harmless.

*Source:* file 739 scripts 27 (Pikachu runs off, flag 1336) and 30 (Mankey runs off; `PlayCry 59` Arcanine with msg 59 "Meowth: Meo-!", then msg 63), and file 212 scripts 9, 10 (Route 22 chase, msg 59 "Stop him?", msg 41/43). No object, coord trigger or map-script header uses them (Viridian header runs only script 9; Route 22 header only script 2). Corrected: the old list also named 739 scripts 26 and 31, which are unused weekday copies (clear flag 638 on Wednesday/Friday), not part of the quest.

### Pidgeot loan returns a different Pidgeot

**The Viridian Forest Pidgeot loan gives you back a different Pidgeot.** The flower keeper borrows your Pidgeot. When he returns it, you get a fixed Lv. 20 Pidgeot instead of your own, although he says he's giving yours back. Lend him a Pidgeot you don't mind losing (see [Viridian Forest: lend her a Pidgeot](01-pallet-to-pewter.md#viridian-forest-lend-her-a-pidgeot-pikachu-starters-only)). Tested in an emulator: the returned Pidgeot is Lv. 20 with no item, a blank OT and ID No. 04336.

*Source:* file 115 L4827 (party selection), L5794 (return: `GiveLoanMon 6, 20, 75`, trade record 6); D-1392.

### Pidgeotto or Pidgeot request

**The same request names a Pidgeotto, then a Pidgeot.** The flower keeper says he needs "a Pidgeotto", then asks "If you have a Pidgeot...". Only a Pidgeot is accepted. The Chinese says the same. Cosmetic.

*Source:* bank 0130#149 (比比鸟 Pidgeotto, then 比雕 Pidgeot); D-1195.

### Poliwag nickname prompt says Poliwhirl

**After you receive Poliwag, the game asks "Give Poliwhirl a nickname?"** The Chinese names Poliwhirl too. You do get a Poliwag. Cosmetic. A separate Poliwhirl gift in the same house can't be reached.

*Source:* bank 0537#87; file 842 L6375 (`GiveMon 60` then msg 87); the Poliwhirl gift is script 9, unreachable.

### Unused Route 2 eavesdropping scene

**An unused Route 2 scene would end the Viridian Forest flower quest.** The files hold a scene where Jessie, James and Meowth eavesdrop on you. It would mark the flower quest's Spearow step as done, closing the quest (and its 2 Honey) unplayed. Jessie and James never appear on Route 2, so the scene can't start. Harmless.

*Source:* file 169 script 4 (L354–L674) is the talk script of Route 2 objects 14/15 (Jessie/James sprites), whose hide flag is 1366 (the hack's always-set scratch flag; cleared only for a moment in cutscenes); nothing shows objects 14/15. It ends with `SetFlag 1062`, which the flower keeper (file 115 L622) treats as quest done; the real quest sets 1062 at file 115 @2800 after giving 2 Honey (item 94).

### Yellow's and Cynthia's dates skip the partner check

**Yellow's and Cynthia's dates don't check who you confessed to.** They only check that you confessed to someone and that their own route isn't locked. This doesn't matter in practice: every Dream World ending locks every partner except the one you picked.

*Source:* files 739 L2297, 859 L715 check the global confession flag 1645 and their own lock flag; Dream World locks in file 898 L2046–L2638.

### The two rescued Charmanders

**The two rescued Charmanders share one switch, but it does no harm.** The Route 2 Charmander that later waits in the Pewter Pokémon Center and the Route 3 "letter" Charmander use the same on/off switch. The Route 3 one can never appear anyway (see [Pewter City to Vermilion City](#pewter-city-to-vermilion-city)), and taking the Pokémon Center one removes it for good, as intended. If you don't take it, it stays in the Pokémon Center after the Cascade Badge.

*Source:* flag 1360 is the hide flag of Pewter Pokémon Center object 13 (file 751 script 11, `HidePerson 13` when taken). Cleared by the Route 2 East rescue (file 170 @2290, @3013), set by file 170 @2630 and by the unreachable Route 3 letter scene (file 175 @2266); file 115 sets it in the Viridian Forest setup (@5712/@5763/@6977). The Cascade Badge (file 758 @3887, after `GiveBadge 1`) sets flag 1367, which hides only the Route 2 East field Charmander (zone 414 object 3) and the Pewter Pokémon Center Trainer (object 12).

### Route 22 grunt and Victory Road Blue share a record

**Beating the Route 22 grunt and helping Blue correctly on Victory Road are stored as one thing.** No visible effect was found: the grunt leaves Route 22 when you go through Viridian Forest, and Brock's Badge scene resets the record long before Victory Road, which sets it again either way. Harmless.

*Source:* flag 1521: set by the Route 22 grunt win (file 212 script 8, @705, trainer 172; his hide flag 1235 is cleared on Route 1, file 168 @650, and set in the Viridian Forest scene, file 115 @5616), cleared by Brock's Badge scene (file 750 @651, after TM80), set or cleared by the Victory Road Blue scene (file 109 @4273 / @10996). Blue's confession (file 109 L1025) needs it set.

### Friend Ball never taken

**The Apricorn Ball maker never takes the Friend Ball he asks for.** You only need to have one in your Bag, and you keep it.

*Source:* file 170 L165 `HasItem 497` (Friend Ball) with no `TakeItem` anywhere in the file; D-1399.

### Moving in with your partner

**Moving in with your partner looks impossible for everyone.** At the stage where you check the Mailbox on the PC upstairs at home, the game stops for every player who has picked a starter, which is everyone, before it looks at your partner. So the love letter and the move-in scenes after it never play. For the same reason, Mom's visit at each partner's fifth stage always plays Cynthia's version. Tested in an emulator with Yellow as the partner: Cynthia comes to the house, and the PC upstairs does nothing at the move-in stage.

*Source:* file 843 script 1 (2F PC, zone 64): at var 0x40B5 = 6 it jumps to L363, which checks flag 106 (got a starter; set at file 738 @3946/@4080 and file 840 @238, never cleared) and goes to `End` at L4292. Stage 7 is only set inside the partner branches after that check (file 843 @1668/@1911/@2159/@2400), so the stage-8 scene (file 843 script 4, frame table 0x40B5 = 8; it would also test 106 first and play Cynthia's version, L1041) can't be reached. Each partner's stage-5 Mom visit (file 736 script 4, frame table 0x40B5 = 5) also tests 106 first and plays Cynthia's version (L559) (D-1391). Emulator: `emu_harness.py guide0107 --case mom_visit,living` (with 106 cleared as a control, Yellow's visit and the love letter play).

### Romance Mail mismatches

**The romance Mail requests don't match what is taken.** If moving in could be reached, some partners would ask for one Mail and take another, and two of those Mails can't be obtained anywhere. Red has no love-letter scene at all. Only matters if moving in is ever reachable (see the entry above). Cynthia's "Rest in my room" has its own entry in [Ilex Forest and Goldenrod City](#ilex-forest-and-goldenrod-city).

*Source:* 2F PC love letter (file 843 L363 branches): Yellow checks and takes Heart Mail (143, L1345/@2836); Green checks and takes Grass Mail (137, L1372/@3234); Misty checks Grass Mail (137, L1399) but takes Bubble Mail (139, @3637); Cynthia checks Snow Mail (144, L1318) but takes Heart Mail (143, @2438). 1F "Rest in my room" (file 842 script 15): Yellow 143/143, Green 137/137, Misty 139/139, Cynthia checks 144 (L7063) but takes 139 (@8417). Red has no love-letter branch, and his script-13 menu has no "Rest in my room" option (537#210 unreachable). Bubble Mail and Snow Mail have no source in the game (site/src/data/items.json: no sources) (D-1398, D-1343).

### Virtue trial and the four-leaf clover

**Yellow's Virtue trial shares a switch with the Five Island four-leaf clover story.** Talking to the Virtue trial examiner at the Viridian Gym door, before you've helped Yellow, hides the sick Trainer on Five Island and stops the clover hunter's scene. It comes back after the scene with the old monk in the house by the One Island ferry (see [Five Island: the four-leaf clover](05-saffron-cinnabar.md#five-island-the-four-leaf-clover-speak-up-for-him)). If you meet the examiner again after that scene, before helping Yellow and before the clover scene, the sick Trainer is gone again. To be safe, help Yellow straight after talking to the examiner, or finish the Five Island clover scene before you go to the Viridian Gym. In the other direction, the clover scene can make Yellow ask for help in Viridian City even if you never met the examiner. Not confirmed in game.

*Source:* flag 1228 is the hide flag of the Five Island sick Trainer (file 58 object 23) and gates the hunter's scene (file 58 script 15, L543/L571: set → L2051, line 70 or 69). Set by the Virtue examiner on every talk while flag 1695 (Yellow not yet helped) is set (file 741 @1226), by the clover scene (file 58 @4421) and its ending (@7736); cleared by the ferry-house monk scene (file 737 @3408, runs while flag 1604 is clear). Yellow (file 739 script 11, L621) offers "Help her out?" while 1228 is set. Corrected: the old entry said the flag hid a Union Cave B2F object; no Union Cave object uses 1228.

### Pokémon Academy resets after the Apricorn quest

**Finishing the Apricorn Ball maker's quest turns the Pokémon Academy back to its early state.** After the quest, the teacher (Earl) goes back to asking you to beat the two exchange students, although Steven and Cynthia have left (so players who never did that challenge can't finish it now), and two pupils go back to their lines from before Cynthia left. Cosmetic.

*Source:* flag 1057 is both the "Parcel + Route 22 done" flag (set by file 738 @1651 / file 212 @1931 / file 739 @985, together with the students' hide flag 1244) and the Apricorn man's hide flag (Pewter Northeast house, file 754 object 3). His quest clears it (file 170 @3782/@4355). The Academy (file 859) checks 1057: script 1 L111 (set → lessons menu; clear → exchange-student challenge, students hidden by 1244 which stays set), script 4 L222 and script 8 L455 (pupils' lines).

## Pewter City to Vermilion City

[Quests on this page](02-pewter-to-vermilion.md)

### Route 3 letter Charmander

**The Route 3 "letter" Charmander never appears.** Its wild battle (Lv. 15) and its letter can't be reached. The Ralts version of the same scene works. Side effect: the Pewter Pokémon Center Charmander isn't removed by it (see [Pallet Town to Pewter City](#pallet-town-to-pewter-city)).

*Source:* file 175 object 4 (script 7, L2160) is hidden by flag 1366, the scratch flag the hack keeps set and only clears for a moment in cutscenes. Nothing shows object 4. The Ralts copy (object 3, flag 1361) works.

### Unused Route 3 roadblock scene

**An unused Route 3 scene would have been a second way past the Mt. Moon roadblock.** In it Steven would join the roadblock group straight from Route 3. Nothing in the game starts it, so beating Steven in the Pewter Museum and then talking to him inside Mt. Moon is the only way. Harmless.

*Source:* file 175 script 14 (same lines as Steven's inner-cave talk, file 133) would set 1312, clear 1358 (Steven at the roadblock) and hide objects 26/27; no object, coord trigger (Route 3 has only script 17) or map script runs it. The working path: Pewter Museum win clears 1312 (file 753 @4110), the Mt. Moon inner-cave talk sets 1312 and clears 1358 (file 133 @1598/@1602).

### Bruno's Pewter City challenge

**Losing to Bruno in Pewter City still counts as done.** He never offers the challenge again, win or lose, and he leaves Pewter City for good after the Mt. Moon roadblock. Save before you talk to him. Possibly intended (a one-shot challenge).

*Source:* file 751 L616 sets the challenge flag 1328 before the battle (script 8, L323 → L601 praise). 1328 is cleared again by the Ruins of Alph Molly scene (file 51 @4281), but Bruno and his Pupitar (Pewter Pokémon Center objects 10/11) are hidden by flag 1311, set at the end of the Mt. Moon roadblock (file 7 @2938, file 9 @5498) and never cleared, so the challenge can't return.

### Pikachu starters' Charmander quest

**Pikachu starters can miss their Charmander quest without warning.** Winning the Cascade Badge removes the Trainer in the Pewter Pokémon Center who starts it. Do that quest before Misty's Gym (see [Pallet Town to Pewter City](01-pallet-to-pewter.md)).

*Source:* file 758 L3887 sets flag 1367.

### Route 9 mushroom picker for Pikachu starters

**Pikachu starters never meet the Route 9 mushroom picker.** Players with other starters find him from the start. For Pikachu players he is removed in the Mt. Moon Square scene and nothing brings him back.

*Source:* his hide flag 2274 is set by the Mt. Moon Rocket battles (file 7 @2056), cleared at the end of the roadblock (file 7 @2930) and set again for Pikachu starters only in the Mt. Moon Square scene (file 9 @5969). Nothing clears it after that.

### Mt. Moon battle records reused

**Two Mt. Moon battle records are reused later.** One is reused by the Magnet that a Vermilion City resident gives you after the construction-site clash. Getting it before Mt. Moon is impossible, because Vermilion City can't be reached before the Mt. Moon roadblock is cleared. The other is reused by Lt. Surge's gift scene after the Thunder Badge, and it is also what makes the runaway Teddiursa appear in the S.S. Anne kitchen during the party. If you could leave the ship after Teddiursa runs off and win the Thunder Badge before fetching it, Teddiursa would vanish. Fetch Teddiursa as soon as it runs off. Not confirmed in game.

*Source:* file 774 L1545/@4127 (Vermilion City resident, needs the construction clash flag 1056; gives item 242 Magnet) uses 2271 as its "given" flag. Lt. Surge's post-badge scene (file 776, L1351 → @1518; gives item 236 Light Ball, or 83 Thunder Stone for Pikachu starters, plus his number) sets 2272. Both are cleared at the end of the roadblock (file 7 @2918/@2922). 2272 is also the hide flag of the S.S. Anne B1F kitchen Teddiursa (file 162 object 14, script 5; set when you talk to it, @1646), cleared when it runs off at the party (file 156 @1726). Corrected: the Magnet is not Lt. Surge's gift.

### Cerulean burglary deadline

**The Cerulean burglary can't be finished after Sabrina's scene in Lavender Town.** If you haven't beaten the Team Rocket grunt on Route 24 by then, the TM Case and TM28 ×5 are lost. If you beat him but didn't go back to the officer, only the 2 Cheri Berries are lost. Finish the burglary before you go to Lavender Town.

*Source:* the takeover scene sets 1024 ("case closed", file 17 @12111) and hides the grunt (1033, @12115). The dizzy man (file 756 script 16) checks 1039 and 1024 first, so the only code that brings the grunt back (756 @2131, `ClearFlag 1033`) is never reached again.

### Route 5 shelter raid

**The Route 5 shelter raid can be walked around, and it closes at the same Sabrina scene.** The raid starts when you cross one spot about 11 steps north of the shelter's door; walking down either side lane skips it. If the raid hasn't happened by Sabrina's scene in Lavender Town, it's lost: the Bulbasaur and Growlithe on Route 5 disappear and there's no reward.

*Source:* Route 5 coord trigger script 3 at x 1297–1302, z 160 (var 0x409E == 0), 11 steps north of the Route 5 House door (1297,171); side lanes x≈1291–1293 and x≈1306–1308 (from the earlier collision read, not re-checked). At the takeover, file 17 L12165 tests 0x409E ≠ 1, then sets 1043, clears 1045 and 305, sets 0x409E = 1 and sets 1037/1038 (the Bulbasaur and Growlithe, Route 5 objects 0/3).

### Misty's Cerulean Cape photo

**Misty's Cerulean Cape photo can never appear for players who didn't confess to her.** After your final Hall of Fame entry, Misty is meant to stand at the tip of Cerulean Cape on Route 25 for a friendly photo if you never confessed to anyone or her romance is closed. The game seems to allow her only during one hour of the afternoon, but the check is written so that she is hidden at every hour. Nothing else brings her there. Players on Misty's romance route get her date photo as normal. Not confirmed in game.

*Source:* file 216 map script (header on-load scripts 4/9 → L3164): after flag 2261, if flag 1645 is clear or 2142 is set it goes to L8294: `ScrCmd_522` → `CompareVarToValue 0x4000, 14` → `GoToIf ≠` L8288 (`SetFlag 598`), then the same for 15, so 598 (hide flag of Route 25 object 35, Misty, script 41 → L7584 friendly photo, `CameronPhoto 84`) is always set. ScrCmd_522 is read as the hour: file 172 (script 13) compares it with every value 0–23. Only file 758 @6735 clears 598 (Misty's date start), and the map script sets it again on entry (D-1441).

## Vermilion City to Celadon City

[Quests on this page](03-vermilion-to-celadon.md)

### Vermilion Fan Club: Green and Red

**Green and Red never appear in the Vermilion Fan Club.** Their two lines (one per player gender) and the Ivysaur standing with them can't be seen. Harmless.

*Source:* file 780 objects 6 (Green/Red, script 12, `GenderMsgBox 22, 23`) and 7 (Ivysaur, script 11) are hidden by flag 1366, the scratch flag the hack keeps set; nothing on this map clears it.

### S.S. Anne TM price

**The S.S. Anne ship shop's TM checks for $400 but takes $4,000.** With $400–$3,999 you can still buy it; what happens to your money then isn't known (probably $0). The menu says "TM63" (the Chinese too), but you get **TM21 Frustration**. Have at least $4,000 before buying.

*Source:* file 156 L4328 `HasEnoughMoneyImmediate 400`, L4349 `SubMoneyImmediate 4000`; bank 252#31 ("Frustration TM63, $4000"); item 348.

### Archie's Walrein cry

**Archie says "Walrein", but you hear Wailord's cry.** Cosmetic.

*Source:* file 157 L853/L1392, `PlayCry 321` (Wailord).

### S.S. Anne records reused

**Several S.S. Anne records are reused elsewhere, probably harmlessly.** They are reset when the S.S. Anne party starts, and the other places that use them come later in the story, so nothing you'd notice was found. One possible side effect: if the grandfather's Water Stone gift or the Raticate gentleman's battle on the ship happened after the Route 7 scene, the Flareon Trainer and his Flareon on Route 7 would vanish. Not confirmed in game.

*Source:* 1516 is the grandfather's Water Stone flag (file 161 L1235–L1269, item 84) and Gentleman Norris's battle flag (file 156 script 31, L1816/L1866, trainer 156); it is cleared when the party starts (file 157 L582, file 161 L1933) and by the Route 7 scene (file 186 L1799), and it is also the hide flag of Route 7 objects 6/7 (Flareon man and Flareon, scripts 5/7). 1421–1425 are cleared at the party start (157 L562–L578, 161 L1913–L1929) and reused by Victory Road 3F (file 110 L5256/L5260), the Indigo Plateau maps that use the vanilla Goldenrod Dept. Store 5F and Ecruteak Southwest House slots (files 900, 923; 1421/1422 are hide flags there); 1423 also by Celadon City (file 783, hide flag of Green and Ivysaur, objects 35/36) and Victory Road (file 109 L201); 1424 also by the Saffron takeover (file 17 L12081), Route 8 gatehouse (file 189 L107), Saffron City (file 824 L6985, hide flag of object 3) and Silph Co. (file 834 L6052); 1425 (bomb defused, file 162 L2154) is read by the Ilex Forest Celebi scene (file 52 L4247).

### Unused Regice scene copy

**The game holds an unused copy of the Rock Tunnel Regice scene.** Harmless.

*Source:* file 129 script 23 duplicates script 22 (Regice, `GiveMon 378, 90`); only script 22 has a sign event (zone 342, bg at 18,115); nothing uses script 23.

### Unreachable Dark Cave copy

**An unreachable copy of Dark Cave holds leftover scenes.** Nothing leads into it. Harmless.

*Source:* file 964 (Dark Cave, Route 31 side, map/zone 176). No warp in any map's event data leads to 176, and its script refers to message ids up to 114 in a 49-string bank (338, shared with the Power Plant, file 196); the file is a duplicate of Route 41's file 960 (vanilla HeartGold's Route 41 file was 964) and its ids fit Route 41's bank 735.

### Mushroom picker keeps your Repel

**The Route 9 mushroom picker never takes your Repel.** He asks for a Repel, but tries to take Oak's Parcel instead, so you keep the Repel and get the Zinc for free. (Pikachu starters never meet him; see [Pewter City to Vermilion City](#pewter-city-to-vermilion-city).)

*Source:* file 190 checks item 79 (Repel) but runs `TakeItem 484` (Oak's Parcel) at L5333.

### Marisa's Badge check

**Marisa on Route 11 asks for seven Badges but only checks for the Marsh Badge.** She only appears after the Radio Tower Observation Deck scene in Goldenrod City, long after you've earned the Marsh Badge, so it changes nothing.

*Source:* file 197 script 13 L840 `CheckBadge 4` only (badge 4 = Marsh Badge, given by Sabrina in file 826 `GiveBadge 4`); refusal msg 97 ("at least seven Badges"). Her hide flag 759 is cleared only by the Radio Tower Observation Deck scene (file 34 L6136, zone 190) and set at new game (file 842 L4984).

### Veteran Dawn's Badge check

**Veteran Dawn on Route 9 only needs the Marsh Badge.** She tells you to come back once you've "collected a few more" Badges, but the only Badge she checks is the Marsh Badge. Possibly intended. Low priority.

*Source:* file 190 script 20 L1252 `CheckBadge 4` (badge 4 = Marsh Badge, file 826 `GiveBadge 4`) → L3929; refusal msg 137; battle `TrainerBattle 977` at L5932 (Doubles 977 ×2 at L5992). Object 33 has no hide flag (D-1444).

### Pokémon Tower Magcargo battle loop

**Losing to the Magcargo in Pokémon Tower may restart the battle straight away.** After a lost battle the fight starts again instead of sending you to a Pokémon Center, which could repeat with a fainted party. Heal and save before you challenge it. Not confirmed in game.

*Source:* file 17 L2529 `WildBattle 219`; on a loss L2546 jumps back to L2519.

### Pokémon Tower Magcargo is missable

**The Pokémon Tower Magcargo is easy to miss.** Knocking it out, catching it or running away removes it for good, and so does leaving the floor by any staircase before you deal with it. Answering No to "Catch it?" is safe while you stay on the floor. The prompt doesn't warn you. Catch it on your first try.

*Source:* file 17: the Team Magma scene that reveals it (script 31 branch, L2459–L2517) sets its hide flag 1155 at L2493 but only `ShowPerson`s it, so any reload hides it; the Magcargo is object 8 (script 10, catch prompt L671 → L2519). A knockout, catch or flee sets 1155 again and hides it (L2553); only a loss restarts the fight. 1155 is otherwise only set by the Rock Tunnel rescue (file 129 L1109) and cleared by Mr. Fuji's house (file 769 L2399), both earlier.

### Romance and Pokémon Tower counter

**The romance date counter is also the Pokémon Tower story counter, harmlessly.** Beating Blue in Pokémon Tower is required: the Team Rocket HQ scene only starts after it. The same counter later drives the Route 25 scene and the post-game dates, which come long after, and the tower scene can't replay.

*Source:* beating Blue in the tower sets var 0x40B5 = 1 (file 17 L3796); the Rocket HQ B3F coord trigger (file 91, script 1 at 38,23) needs 0x40B5 == 1, and script 22 sets 2 (L2562). Route 25 sets 3 (file 216 L12222); the date scripts (739, 758, 859, 228, 809, 843, 842, 736) use 3–11 and need the final Hall of Fame (e.g. 739 L2286, flag 2261). Never reset to 0. Side note: the Safari Zone Gate still has the vanilla Pal Park coord trigger on 0x40B5 == 0 (file 809, script 4), which can't fire once the tower is done.

### Sabrina's tower task record reset

**Two later scenes reset the record of Sabrina's Pokémon Tower task, probably harmlessly.** Answering No to Sabrina's plan on Route 8 during the Team Rocket takeover, and the post-game Route 25 scene with Misty, Brock and Curtis, both reset it. By the time either can happen Sabrina has left the tower, so the task is over, and her own scene in the Saffron Gym after Saffron is freed resets it anyway. Not confirmed in game.

*Source:* flag 1504 is set when she gives the task (file 17 L7426) and checked by her and the tower Ghosts (L1372, L1487, L1563, L1612). It is cleared on Route 8 (file 188 script 16, both "No" answers → L1957; the plan only proceeds with 1504 set, L626), on Route 25 (file 216 script 41 L11142, set again at L11203), in the Saffron Gym (file 826 L920) and in file 912 L3775 (zone 228, Cerulean Cave). The takeover hides the tower Sabrina (file 17 L12069, object 38, hide flag 1100).

### Route 11 girl and Swablu

**The Route 11 girl may mourn a Swablu you never saw taken.** If you skipped the Route 5 shelter raid, she cries "Little Swablu got taken away!", although that scene never played. Cosmetic.

*Source:* file 17 L12165–L12204 (takeover fallback when var 0x409E ≠ 1) clears 1045 but leaves Swablu's hide flag 1160 set (set for everyone in the Mt. Moon Square scene, file 9 @5578; only the raid clears it, file 179 L1538). The girl (file 197 script 8, object 1) then goes L684 → L1755 → 1160 set → L3111 (msg 88).

### Unused Zapdos and Lum Berry scenes

**Two unused scenes are left in the files.** A wild Zapdos (Lv. 50) on Route 10 and a Lum Berry from the Route 9 Squirtle for non-Pikachu players can't be reached; the Squirtle only appears for Pikachu starters. Harmless.

*Source:* Route 10 (file 191) script 4 (`WildBattle 145, 50`) isn't used by any object or sign. Route 9 (file 190) script 6 L656 → L3284 gives item 157 only when flag 1288 (Pikachu starter, set in file 738 L3891) is clear, but the Squirtle (object 10, hide flag 1096, set by Mt. Moon Square file 9 @5550) is only shown by the Pikachu-only trap scene (script 3, L164/L230) and its follow-up (script 20 L4624).

### Early Lavender curse

**Reaching Lavender Town before Prof. Hale's Rock Tunnel scene would start the Lavender curse early.** Every exit on foot would pull you back ("A mysterious force pulled you closer!"), as in the curse side quest, but without its normal setup. Fly still gets you out. Probably impossible in normal play, since the way in from Route 10 runs through Rock Tunnel. Not confirmed in game.

*Source:* file 765 script 10 coord triggers (north, west and south exits) fire on var 0x40BA == 0, its value from new game. The Rock Tunnel rescue sets it to 1 (file 129 L1189); the fortune-teller's reading sets it back to 0 to start the curse (file 771 L1082/L1386) and lifting the curse sets 1 (file 771 L1208). With 10 Cleanse Tags bought (flag 2003) the trap still pulls you back (765 L547–L592). The curse quest is described in 03-vermilion-to-celadon.md.

### Misty's Gyarados and the Viridian Gym trials

**Misty's Gyarados is lost if you finished the early Viridian Gym trials.** Misty's Gyarados gift is for male players who chose Bulbasaur. If such a player met Giovanni at the end of those trials, he never gets the Gyarados. Misty's goodbye still says "Keep that Gyarados of mine", and it says so to anyone who finished the trials. The same mix-up also blocks a trade on One Island (see [Sevii Islands and Indigo Plateau](#sevii-islands-and-indigo-plateau)).

*Source:* the gift (file 172 script 28, L2415–L2513: needs flag 1289 = Bulbasaur starter, male player, and 1081 clear; `GiveLoanMon 8, 20, 101`) sets 1081, which file 741 script 7 L511 (Giovanni's virtue check) also sets; goodbye at file 853 L3484 (1081 set → msg 106 "Keep that Gyarados of mine", else msg 85). File 845 (One Island) also uses 1081.

### Auction room and Blastoise

**The auction room calls a lone Blastoise "common as stray dogs".** If Blastoise is your only Pokémon from the Kanto starter lines, the "sell" check misses it. The other Kanto starter-line Pokémon work. Use a different one.

*Source:* file 798 L590–L742: species 1–8 each branch to L791, but L742 `PlayerHasSpecies 9` has no compare or branch after it and falls into msg 9.

### Celadon street photographer

**The Celadon street photographer never appears.** He would need the day to be Tuesday and Friday at once. The photographer on Department Store 2F (Fridays) works.

*Source:* file 783 L1984 clears flag 638 only if the weekday is 2 **and** 5 at once (two "≠" jumps to L4250), so it stays set (638 is the shared hide flag of every photo-spot man, object 13 here). The Department Store 2F copy (file 788 L442, weekday 5 only) works.

### Celadon Gym sneak-in friend

**On your first try to sneak into Celadon Gym, the friend at the door is always Misty, even for Charmander starters.** Charmander players see Green only after a failed attempt. Cosmetic.

*Source:* both branches on Department Store 5F clear Misty's hide flag 1174 (file 791 script 7: L983 → L1546 for flag 1287 = Charmander, else L994), and Green's hide flag 1423 stays set from the earlier Celadon scene (file 783 L3547). After a failed attempt file 783 L8258 clears 1423 for Charmander players instead (L8277); L7414 also clears it.

### Waiter Grant's Gloom leads

**Waiter Grant needs both Gloom leads, not just one.** Collect both before you talk to him.

*Source:* file 797 script 3 L91–L231: 1479 set → L212 needs 1480; 1480 set → L227 needs 1479; only then L311. An earlier note said "1479 or 1480".

### Eviolite man's thanks

**The Eviolite man thanks you for driving out Team Rocket even if you haven't yet.** He hands over his 5 Eviolites at any time. Cosmetic.

*Source:* file 783 script 4 (object 8, no hide flag) only checks his own flag 1523 before giving item 110 ×5 (Eviolite).

### Gloom-lead records reused

**Some Gloom-lead records are reused by later scenes, probably harmlessly.** All of those scenes come after the Celadon City story, when Waiter Grant no longer checks them.

*Source:* 1479 is set by the eating contest (file 803 L271) and by Bugsy's Gym (file 866 L4372); 1480 by file 787 L157 and the post-game Cerulean Cape scene (file 216 L11158); 1481 by Celadon (file 783 L6068), Cerulean Cape (216 L11154) and Ilex Forest (file 92 L6595, cleared L5797). Victory Road 3F clears all three (file 110 L5422–L5430). Grant skips the checks once flag 1702 is set (file 797 L73).

### Lt. Surge's thank-you line

**Lt. Surge never says his thank-you line for siding with the law.** Players who sided with Blue at the construction clash hear the townsfolk line too. Cosmetic.

*Source:* the side choice in the Vermilion Pokémon Center sets 1064 (Blue, file 777 L614) or 1065 (Green, L651). Surge's post-badge line checks 1064 (file 776 @917 → msg 18), but the construction clash (file 774 script 44, L2664/L2668 and L4909/L4913) clears both before the battle, and only 1065 is set again (L9403), so 478#18 is unreachable (D-1393).

### Brock in Diglett's Cave

**Brock never appears in Diglett's Cave.** He would need the hour to be 17, 18 and 19 at once. Not confirmed in game.

*Source:* file 5 L608 clears his hide flag 610 (object 7) only if `ScrCmd_522` returns 17 **and** 18 **and** 19 (three "≠" jumps to L711) (D-1394). `ScrCmd_522` returns the current hour (observed in an emulator at 0, 6, 7, 12, 18, 19 and 23 o'clock, `emu_harness.py guide0107 --case monday`); across the ROM it is only compared with values 3–22.

### Rock Tunnel corner kid loss

**Losing to the corner kid in Rock Tunnel freezes the game.** His battle doesn't send you to a Pokémon Center: the game goes on with the disguised "Pikachu" kid's dialogue before the field has come back, and the screen stays black. Save before you talk to him and make sure you can win. Tested in an emulator (Chinese ROM and English build).

*Source:* file 129 script 25: Youngster Willy (trainer 606, L2879); on a loss L2897 jumps to L3782 (Poké Kid Ernie's "Don't throw Poké Balls at people!" menu, trainer 194). Yes → L4368, Yes → L5166 sets Ernie's flag 1554 without a battle; Willy's flag 1966 stays clear (D-1395). Observed instead: the `TrainerBattle 606 0 0 0` loss doesn't restore the field before L3782, msg 46 is never printed and the CPU ends up running in heap memory (black screen). Controls: `TrainerBattle 606 0 1 0` returns to Rock Tunnel; with `WhiteOut` after it the player wakes in the Pokémon Center. `emu_harness.py guide0107 --case corner_kid`; D-1548.

### Switching sides at the construction clash

**Switching sides after losing the Vermilion construction clash locks out both partners.** Every loss sends you to a Pokémon Center and lets you choose a side again, but the romance lock from your first choice stays. If you then pick the other side, both partners tied to the clash are locked. Only the wish in Island Forest on Six Island can undo it (see [Saffron City to Cinnabar Island](#saffron-city-to-cinnabar-island)). Stick with your first choice. Not confirmed in game.

*Source:* the choice is made in the Vermilion Pokémon Center (file 777 script 11): Blue's side sets 1064 + 2141 (L614), Green's side sets 1065 + 2153 (L651); neither clears the other lock. A lost clash whites out (file 774 L6321) and the clash restart (774 L2623) shows Green and Blue again (clears 1058), so switching sets both (D-1397). Undo: file 55 L3017–L3075.

## Celadon City, Fuchsia City and Saffron City

[Quests on this page](04-celadon-fuchsia-saffron.md)

### Swimmer Marina and the Dragonair delivery

**Beating Swimmer Marina on Route 41 before the Secret Potion delivery kills the Dragonair.** The Cycling Road "too late" check looks at whether you've beaten Marina, probably by mistake, instead of a Cycling Road biker. If you have beaten her, the delivery fails. Do the Secret Potion delivery before you battle her.

*Source:* file 211 L530 checks flag 1689 (trainer 329, Swimmer Marina, Route 41), not a Cycling Road biker (1674–1682, 1687, 1692, 1693).

### Secret Potion hand-over check

**The Secret Potion hand-over doesn't check that you carry one.** Safari Zone Warden Baoba "takes" the Secret Potion at the Cycling Road gate without checking that you have it. Harmless in normal play: the scene only starts while you're on the delivery, and you can't get rid of the potion.

*Source:* file 211 script 5 (Cycling Road gate, zone 423): `TakeItem 464` at L289/L391/L460 with no `HasItem` before it. The same script also sets flag 1207 (L201), which hides Cynthia and Steven in Fuchsia City (see below).

### Sound Designer's Badge check

**The Game Freak Club Sound Designer asks for all eight Kanto Badges but only checks for the Earth Badge.** He gives you GB Sounds as soon as you have Giovanni's Earth Badge, whatever other Badges you hold. Harmless.

*Source:* file 796 L476 `CheckBadge 7` (Earth Badge, given by Giovanni at file 741 L2863), then GB Sounds (item 502) at L865; refusal msg 7.

### Losing on the Celadon roof

**Losing to Jessie & James on the Celadon roof still completes Tony and Mary's grooming quest.** You're sent to a Pokémon Center and miss the ending, but the scene doesn't replay, and Suzie's massage is free from then on. Only losing to the Beedrill first replays the scene. Save before the roof if you want to see the ending.

*Source:* file 792 sets var 0x40D0 = 2 (@1530), sets flags 1544/1545 and clears 1535 (L1933–L1945) before `TrainerBattle 460 461`; a loss whites you out (L2849). The roof scene is a coord trigger at 4,5 on var 0x40D0 == 0 (script 21); Suzie (file 794 L758) gives the free massage at value 2. Beedrill is trainer 462; losing to it leaves the var at 0, so the scene replays.

### Celadon roof scene before Route 7

**You might reach the Celadon roof scene before its Route 7 scene, but only in a short window.** The roof scene is meant to come after the Route 7 scene and Suzie's free massage, but nothing stops it from playing earlier if you reach the roof first. The Underground Path lets you skip the Route 7 scene, but its doors are only open between the Rock Tunnel rescue and Sabrina's call. If it happens, the later Route 7 scene and Suzie's massage set the roof scene up again, so it may try to replay with Tony and Mary already gone. Other ways to the roof weren't checked. Not confirmed in game.

*Source:* the roof's coord trigger (file 792 script 21, at 4,5, var 0x40D0 == 0) can fire while the var is still at its starting value 0. The Route 7 scene sets it to 1 (file 186 L1819, coord trigger at x 1271), Suzie's massage sets it back to 0 (file 794 L1402, only while flag 1535 is set), the roof sets 2 (file 792 @1530). The Underground Path exit on Route 7 (warp at 1261,247) lies west of the Route 7 trigger, but every Underground Path door is blocked by flag 1226 (set at file 9 @5598, cleared by the Rock Tunnel rescue, file 129 L1141, set again at the Saffron takeover, file 17 @12023). Erika's perfume scene in Celadon (file 783 L4521–L4612) closes the quest: it hides Tony and Mary (1544/1545), clears 1535 and sets the var to 1 unless it is already 2.

### Sitrus Berries and the eating contest

**Holding ten or more Sitrus Berries silently blocks the eating-contest prize.** The rule is only hinted at ("eat all the Sitrus Berries you win"). Store extra Sitrus Berries in the PC first.

*Source:* file 803 L444 `HasItem 158 ×10` → L828 (rules msg 13) instead of the prize at L465.

### Grandma's treats deadlines

**Grandma's treats for Shota have deadlines nobody mentions.** The delivery closes when Team Rocket takes over Saffron City, because Shota disappears. Grandma's reward (the Master Ball, or 2 Rare Candies if you keep the truth from her) is lost if you haven't reported back to her before Saffron is freed. Do both right away.

*Source:* Shota (file 762 object 6) is hidden by flag 1226 (set at the takeover, file 17 @12023). Grandma is file 794 script 13: at var 0x40CF = 2 her menu gives the Master Ball (item 1, L1108) or 2 Rare Candies (item 50, L948). The liberation (file 834 @5994) sets the var to 5, which only gives a closing line (L861).

### Lass Eve's incense

**Lass Eve on Route 13 offers "incense", then gives a Miracle Seed.** The Chinese says incense too. Cosmetic.

*Source:* bank 343#32 (熏香); file 201 L1818 gives item 239 (Miracle Seed).

### Lara's Pretty Scales

**Lara on Route 14 promises "these Pretty Scales" but gives one Heart Scale.** The Chinese says the same. Cosmetic.

*Source:* bank 344#62 (这几个漂亮鳞片); file 202 L3529 gives item 93 (Heart Scale) ×1.

### Cynthia and Steven in Fuchsia City

**Cynthia and Steven leave Fuchsia City when Team Rocket takes over Saffron City, and in the usual order they don't come back.** They appear when you get the Soul Badge, and the takeover removes them. Only the Soul Badge scene brings them back, so if you already have the badge when the takeover starts (the usual order), they're gone for good. Battle them before Sabrina's call in Pokémon Tower. The Secret Potion hand-over at the Cycling Road gate also removes them, so if you deliver it after the Soul Badge they're gone too (not confirmed in game).

*Source:* flag 1207 hides both (Cynthia: file 804 object 34; Steven: file 119 object 8, Safari Zone entrance building). It's set at file 17 L12127 (takeover), file 9 L5586 (Mt. Moon) and file 211 L201 (Secret Potion hand-over), and its only clear is Koga's Soul Badge scene (file 806 @1981; the badge is `GiveBadge 5` at L407).

### Unreachable second Silph Co. ending

**A second Silph Co. ending with extra rewards can't be reached.** In it Lance would give you an **Exp. Share and 10 Rare Candies**. You get the Vs. Recorder instead. In normal play it can't start: during the takeover you only enter the president's office as part of the finale, which marks it done before you can move again.

*Source:* file 795 script 7 (coord trigger at 9,11–13 in the president's office, zone 377, on var 0x40A6 == 0; Rocket Boss trainer 402 at L1530, then item 216 ×1 and item 50 ×10 at L2549/L2565). During the takeover the office door (Silph Co. HQ warp at 1,41) is blocked by Ariana (object 22, hide flag 1208, cleared at the takeover, file 17 L11991). Her battle (file 834 L1401) warps you into the office inside the finale script, which sets 0x40A6 = 1 (L5074/L5215) before the warp to the Pokémon Center. Before the takeover the door is open (1208 set at file 9 L5590) and 0x40A6 is 1 (file 9 L5634); the S.S. Anne B1F Teddiursa scene sets it to 0 (file 162 L1658), whose order relative to the takeover wasn't traced.

### Sub. Doll not checked

**The Saffron finale never checks that you carry the Sub. Doll.** Harmless: the scene plays the same way with or without it.

*Source:* file 834 L6010 `TakeItem 451` with no `HasItem`. The doll comes from the man in the house next to the one Sabrina teleports you into (file 830 script 2, L410; he hands one out whenever you talk to him during the takeover). Sabrina's Route 8 teleport also runs `TakeItem 451` (file 188 L2775).

### Fuchsia "Surf TM" man

**The man in the Fuchsia City southwest house asks about the "Surf TM" but checks for HM04 Strength.** His line also talks about moving the big boulder in his house, which is Strength's job. The Chinese has the same slip. Only his line changes; nothing is given. Cosmetic.

*Source:* file 810 script 3 @98 `HasItem` item 423 (HM04) → L334 (line 509#6, 冲浪技能机); otherwise msg 5. No item is given on either path. His door is ≈1222,435 (Fuchsia Southwest house), not the rangers' room (D-1403).

### Route 17 Shiny Stone

**The Shiny Stone on Route 17 never appears.** Its item ball is removed during the Mt. Moon roadblock scene, long before you can reach Route 17, and nothing brings it back.

*Source:* object 21 at 1143,402 (file 209 script 4, item 107) is hidden by flag 1890, which the Mt. Moon roadblock scene sets (file 9 @5522) and nothing clears (D-1400).

### Colette and the Cycling Road record

**The people who show up after the Cycling Road gang leaves share a record with Medium Colette in Pokémon Tower.** These are the Route 16 Quick Ball kid, the Route 18 Air Slash tutor and the ordinary Route 17 cyclists. If you haven't beaten Colette, they already stand there before the gang is driven off. If you beat her later, they disappear, and they come back when the gang is driven off or after Sabrina's Marsh Badge. In the usual order (Colette first) it works as intended. If they're there and you haven't beaten Colette yet, talk to them first. Low impact.

*Source:* flag 1580 is trainer 220's (Colette's) defeat flag (Pokémon Tower object 3, script 3219) and the hide flag of Route 16 object 0, Route 17 objects 22–27 and Route 18 object 3 (D-1401). It is cleared by beating Roughneck Paxton (file 210 L1625), by the Saffron Gym (file 826 L1003/L1406) and by the leftover Route 38 test character (file 248 L204/L277).

### Misty missing from Cerulean Gym

**Winning Misty's Resort Zone date leaves her missing from Cerulean Gym, and her romance stalls.** Starting the date removes Misty from the Gym. After a win the date ends in the Gym, but she doesn't reappear there or at Cerulean Cape, so her next date ("I want you to meet my mom"), which only she can offer in the Gym, never starts. Every other scene that brings her back to the Gym is part of the main story, which is over before the dates unlock after your final Hall of Fame entry, so nothing found undoes this. If you lose one of the date's battles instead, Misty waits at the tip of Cerulean Cape: take her photo there, the Cape date plays again, and she's back in the Gym ([Resort Zone: Misty's date](04-celadon-fuchsia-saffron.md#resort-zone-mistys-date-the-pal-park-and-the-couples-double-battle)). Save before the date. Suspected hack bug. Tested in an emulator: after the date's ending Misty is neither in the Gym, also after leaving and coming back, nor at the Cape.

*Source:* D-1402. Misty's hide flag 595 is set when the Resort Zone date starts (file 758 @7636). The win ending (file 809 L4324–L4360) warps you to the Gym and sets var 0x40B5 = 4 but never clears 595; the Gym's var-4 step is her "meet my mom" talk (758 @3687 → L6462), and the Gym's on-load clear (758 @6412, after the final Hall of Fame) only runs when flag 1645 is clear or 2142 (Misty's lock) is set (at hours 14–15 it sets 595 instead, 758 L7038). The Cape needs var 0x40B5 = 3 and 595 set (216 @3197–@3221), so after a win she isn't there either. A loss in any of the date's four Multi Battles whites you out (809 L4885) with 0x40B5 still 3 (set when the date starts, 809 @592), and the Cape date's end clears 595 (216 @12236). The other clears of 595 are one-time story scenes before the final Hall of Fame: Radio Tower Observation Deck (file 34 @3795), Seafoam Islands Blue Orb scene (file 195 script 12 @1850, needs var 0x408C = 14 from Misty's Gym send-off, 758 @6372), Sea Cottage virus battle (file 217 @1398), Silph Co. aftermath (files 795 @2860, 834 @5956), Celadon Rocket base aftermath (file 853 @3778), Cerulean Cave / Prof. Oak (file 912 @3767) and Blue's Champion battle before the Hall of Fame (file 821 script 1, Blue's object, hidden by flag 1496 from the Hall of Fame on, file 822 @86; → @2513). The Seafoam scene can't be pending after the final Hall of Fame: the League HQ round-2 report needs var 0x408C = 15 (file 31 @2039), which only that scene sets (195 @1854).

## Saffron City to Cinnabar Island

[Quests on this page](05-saffron-cinnabar.md)

### TM14 Blizzard

**TM14 Blizzard can be missed.** The only TM14 comes from Articuno's no-Poké-Ball battle in the Seafoam Islands: beat it, choose to catch it, and the researcher stops you and gives you TM14. The post-game Team Rocket scene there (Lawrence and Archie) removes Articuno until Lance visits your home after the final Hall of Fame, and after that only the catch battle is left. Get TM14 before that Team Rocket scene. Before it, Articuno is there for everyone.

*Source:* file 195 @957 hides Articuno with `HidePerson` (object 2, hide flag 1368); file 842 @2177 clears 1368 (needs flag 2261). Articuno's script (195 script 10) runs the no-Poké-Ball battle (trainer 505) only while 2261 is clear; after 2261 it offers only "Catch Articuno?" (L2249; the catch battle sets 1368 at L2696). The researcher's TM14 (item 341) is at L2960, flag 1483. The Route 3 painter's Ralts scene that also sets 1368 (file 175 script 16, L1145) is never triggered (D-1423), and file 115 L5744 is the early Viridian Forest Eevee rescue (D-1422).

### Moltres and the S.S. Anne guest

**An S.S. Anne guest's battle shares a record with the post-game Moltres, harmlessly.** Moltres can only be challenged after your first final Hall of Fame entry, which resets that record. Later Hall of Fame entries don't, so a caught, defeated or fled-from Moltres is gone for good. If you never battled that guest, Moltres already stands at the volcano before then, but you can't reach it.

*Source:* flag 1517 is Moltres's hide flag (file 812 object 8) and the S.S. Anne party guest's battle flag (trainer 157; files 156 L1932, 158 L305). The lava-edge spots (812 script 6) need flag 2261; the same one-time block of the final Hall of Fame that sets 2261 clears 1517 (file 822 L2458/L2474; later entries take the flag-2404 branch). Moltres sets 1517 after the battle (812 L7914).

### Route 21 Lairon called Onix

**The Route 21 Trainer's Lairon is called Onix once, and you hear Onix's cry.** You don't battle him; his Lairon stands next to him trying to break Mr. Mime's barrier. The Chinese says Onix in that line too. Cosmetic.

*Source:* bank 0732#18/#19 say Lairon (可多拉) and #21 says Onix (大岩蛇); the cry is species 95 (Onix) (file 957 L260/L610; D-0691).

### Unused Cinnabar riddle menu

**An unused riddle menu in Cinnabar Island shows the wrong lines.** Its answer options are Amber's lines. Nothing leads to it. Harmless.

*Source:* file 812 script 7 (L919): menu items 9–12 are Amber's messages; no object or sign on the map uses script 7.

### Seafoam Islands ice (not a bug)

**The ice in the Seafoam Islands does not come back after the Team Rocket scene.** This isn't a bug: an earlier note said the ice returns after Lawrence's Moltres melts it, but removing the ice blocks in that scene marks them as melted for good, the same as melting them with your own Magcargo or Moltres.

*Source:* file 195 L797–L825 hides the ice objects 4–6 with `HidePerson`; their hide flag is 1500, and `HidePerson` sets an object's hide flag permanently (engine note in work/notes/guide_errata.md). The lead-Pokémon paths set 1500 explicitly (L2086, L2207, L2645).

### Mismatched Pokémon cries

**Some Pokémon cries don't match the Pokémon.** You hear Ursaring for "Zangoose: Zaaaa-go!" and Flygon for "Shiftry" in Island Forest, Spinda for "Butterfree" on Two Island and Poliwhirl for "Manaphy". Cosmetic.

*Source:* file 55 script 7 (Ursaring cry, bank 0084#20); file 55 script 12 (Flygon cry, 0084#61); file 734 script 17 (Spinda cry, 0440#73); file 965 script 10 (species 61 Poliwhirl, 0393#76).

### Island Forest wish

**The Island Forest wish undoes romance choices that other scenes treat as final.** Wishing "I want to be more attractive" reopens every partner, including Blue's Victory Road lock and the Vermilion construction-site locks, as long as you haven't talked to the Dream World old man. It works once. It may be an intended second chance.

*Source:* file 55 L3017–L3075 clears 2141–2145 and 2153–2157, unless flag 2300 is set (the old man sets it on your first talk, file 898 L59; MooMoo Farm's dream scene can clear it again, file 251 L872). Any wish sets flag 0x892 (2194) at L3094, so it works once.

### Crystal Onix

**The Crystal Onix is only Lv. 40, and you get one try.** Every Trainer on its island is Lv. 62 or higher, so the level looks like a leftover. Whatever happens in the battle (caught, knocked out, run away or you lose), the Onix is gone afterwards. Bring Poké Balls and save first.

*Source:* file 24 L88 (`WildBattle 2143` = Onix form 1, level `0xff28` = 40); flag 2912 (the Onix's hide flag) is set before the battle (L84), and a loss whites you out (L972).

### Manaphy at Lv. 1

**Manaphy is given at Lv. 1.** Most legendary gifts are Lv. 80–95 (Jirachi is Lv. 5). Possibly intended ("just hatched").

*Source:* file 965 L543 `GiveMon 490, 1`. Other gifts: Regis 90 (file 129), Latias/Latios 80 (file 239), Shaymin/Celebi 90 (file 52), Mew 90 (file 58), Ho-Oh 95 (file 21), Jirachi 5 (file 81 L1259).

### Cinnabar graffiti couple

**Losing to the Cinnabar graffiti couple counts as letting them carve their names.** You can't retry. Save before the battle.

*Source:* flag 1742 is set before the Double Battle (file 812 @3390, trainers 982/983) and only cleared on a win (L3453); a loss whites you out (L4661) and the couple then take the "carved" branch (L1394 → L3216) (D-1420).

### Choice-item merchant's goodbye

**"Nothing, thanks" at the Saffron Choice-item merchant shows a menu label instead of his goodbye.** You see "The Pokémon League's reforms" instead of "If you're interested, come back next time!" The same happens if you back out of the menu. Cosmetic.

*Source:* file 824 L2989 shows 521#40 instead of 521#23 after menu item 22 (D-1421).

## Sevii Islands and Indigo Plateau

[Quests on this page](06-sevii-islands-indigo.md)

### Pilgrimage skips Six Island

**You can finish the island pilgrimage without doing the Six Island trial.** That also skips the Deoxys theft. Seven Island's final trial never checks Six Island; every other island's trial is checked.

*Source:* Seven Island's final-trial gate (file 870 L1364) tests `0x40a2 >= 3`, which is always true once the pilgrimage has started (it needs `0x40a2 >= 19`). Every other island has its own check (0x40b2, 2346, 0x40b3, 0x409e, 2175). It was probably meant to be the Six Island var 0x40b4 (≥ 3) or flag 2195.

### TM86 Grass Knot

**TM86 Grass Knot can be lost.** The Roserade woman on One Island, its only source, acts as if you've already traded if you got Misty's Gyarados (male Bulbasaur players) or finished the early Viridian Gym trials. She then only explains how Grass Knot works and never offers the trade. Nothing can undo this.

*Source:* file 845 script 6 (L331 `CheckFlag 1081` → L1205, msg 12; the trade at L1223–L1318 takes item 239 Miracle Seed, gives item 413 TM86 and sets 1081). The same flag is set by Misty's Gyarados gift (file 172 script 28 L2507, needs flag 1289 = Bulbasaur starter and a male player; also L11039) and the early Viridian Gym trials (file 741 L511). Nothing clears 1081. items.json lists the One Island gift as TM86's only source.

### Six Island Shell Bell price

**The Six Island Shell Bell costs $200, not the $5,000 the menu says.** In your favour.

*Source:* file 943 L3288 checks and L3314 takes $200; menu bank 625#48.

### Four Island chief's Doubles

**Choosing "Doubles" against the Four Island chief makes you fight Gentleman Bernard's team (as a Double Battle) instead of the chief's.** "Singles" gives the right battle. Pick Singles if you want to fight the chief.

*Source:* file 861 L1985 → L2429 starts `TrainerBattle 378, 378` (Bernard) instead of 845 (the chief, Tian, used by Singles at L2496).

### Seven Island Kecleon

**The Seven Island Kecleon scene wants an Alomomola in the lead, but plays Noctowl's cry.** After the tourist complains that her snacks keep vanishing, the invisible blocker only reacts if the first healthy Pokémon in your party is an Alomomola. You then hear Noctowl's cry with your Alomomola's name and a "Nooo-tow!" line. It was probably meant to be Noctowl, but only an Alomomola works, so put one first. Tested in an emulator: with an Alomomola the scene and the Kecleon battle play; with a Noctowl nothing happens.

*Source:* file 870 script 9 (tourist, sets 2197), script 12 (blocker, Seven Island object 16, hide flag 2198) → L1038–L1054 (`GetPartyLeadAlive`, `CompareVarToValue` species 594, Alomomola in this ROM) → L1500, `PlayCry 164` (Noctowl) ×3 with msg 34 "{lead}: Nooo-tow!"; Kecleon `WildBattle 352` at L1703, then item 42 (Lava Cookie).

### Unused One Island biker scene

**An unused restaurant scene duplicates the One Island biker request.** The working one is in the One Island Pokémon Center. Harmless.

*Source:* file 894 script 16 (sets 2021) is not used by any object, sign or trigger in its map (zone 205); the working copy is file 889 script 6 (One Island Pokémon Center, object 9, sets 2021 at L442).

### Bikers' red envelope and Big Sis

**Taking the bikers' red envelope even once means Big Sis never switches sides.** In the Shipyard Ruins on Three Island, the Chief offers you a red envelope ($200,000). If you accept, a League inspector later fines you on One Island, and after that Paxton's final battle always treats Big Sis as untaught: even if you taught her to ride, she fights against you. She has already left her house by then, so you can't teach her again. If you want her on your side, choose "I'll teach you to ride a bike" with Big Sis and refuse the envelope. This may be intended as a penalty for taking the bribe, rather than a bug. Not confirmed in game.

*Source:* Big Sis (file 782 script 20, object 19 in the Three Island house, hide flag 2019): "I'll teach you to ride a bike" sets var 0x4097 = 5 (L2893); every real choice ends at L5861 `SetFlag 2019` + `HidePerson 19`, and nothing clears 2019 after that (only the earlier "send the bikers to Alto Mare" choice, file 826 L983). Bribe: file 879 msg 17 Yes → L1490, $200,000 (4 × `AddMoney 50000`), var 0x4097 = 6 (L1915); the Shipyard Ruins bikers stay (hide flag 1663 is only set by the gauntlet's end, L2420), so the scene can be replayed. One Island coord trigger (file 845 script 20, 146,160, var 0x4097 == 6) → fine 8 × `SubMoneyImmediate 50000` (L1533–L1575), then L1612 `SetVar 0x4097, 1`. The switch check at file 879 L1283 (`0x4097 == 5` → L1931, msg 52) then always fails. Edge case: a player who takes the bribe before ever visiting Big Sis can still set 5 with her afterwards (the inspector then doesn't trigger). Matches guide chapter 06 "Shipyard Ruins" Notes.

### Azure Flute after the Hall of Fame

**The Azure Flute can't be obtained after the Hall of Fame.** The Seven Island shrine keeper only ever says to keep it safe. Without it the Ruins of Alph replay and the Sinjoh Ruins stay locked (see [Lake of Rage, Blackthorn City and beyond](#lake-of-rage-blackthorn-city-and-beyond)). The keeper's check was tested in an emulator: after the League HQ report she only says to keep it safe, and one story step earlier she lends it. That the report always comes first is read from the scripts.

*Source:* file 942 script 4 (L104/L110): the "keep it safe" branch fires on `0x40b7 >= 4`, but League HQ (file 31 L3316) already sets 0x40b7 = 4 before the Hall of Fame, so the post-game offer at L263, the only place that gives item 536 and sets 0x40b7 = 5 (L539), can't be reached. Locks file 49 L694 and file 131. The check probably should be `>= 5`.

### Victory Road guard's Badge check

**The Victory Road guard asks for eight Badges but only checks for the Earth Badge.** With the Earth Badge he lets you through, however many other Badges you have.

*Source:* file 763 script 3, L361 `CheckBadge 7` (Earth Badge, given at file 741 L2863); the same single check repeats at L2761, L2839, L2917; refusal msg 22 ("eight or more Badges").

### Two Janine reveals

**Two disguised staff members can both reveal themselves as Janine.** This only happens for a male Charmander player who sided with the environmentalist on Route 11 and let the S.S. Anne sink: Ruin Maniac Axel and Aroma Lady Wendy on Victory Road both give the reveal. Harmless.

*Source:* file 110 script 36: male players go to L8952 (Axel, trainer 569) and L9087 (Wendy, trainer 567). With flag 1287 (Charmander starter, file 738 L4031) set, 1610 clear (didn't side with the grass-cutter, file 197 L2390), 1895 set (sided with the environmentalist, file 197 L2640) and 1093 set (S.S. Anne sank, file 157 L2852; also set in Rock Tunnel at file 129 L1212), both branches reach the Janine reveal (L10000 → L10147 and L9177 → L10147, msg 3).

## Pokémon League, Mt. Silver and New Bark Town

[Quests on this page](07-league-to-cherrygrove.md)

### Yellow's Champion room Singles

**Yellow's "Singles" in the Champion's room is a Double Battle.** When you call Yellow to the Champion's room with "Call a Trainer", both options give the same Double Battle. Yellow's Singles on Mt. Silver is correct.

*Source:* D-1447. File 821 L3742 and L3791: both menu choices start `TrainerBattle 951, 951`. Blue and Gold use `x, 0` for singles, and on Mt. Silver (file 107 L6518) Yellow's singles uses `951, 0`.

### Luxio and Luxray

**The Sinnoh traveller calls her Pokémon "Luxio" after you answer "Luxray".** The Chinese says Luxio there too. Cosmetic.

*Source:* bank 0536#49 says 我的这只电光狮 (Luxio); the quiz menu (file 841 L916–L940; Prof. Elm's Lab 2F) accepts index 2 = 0536#35 雷电狮 (Luxray) at L984 → L2395, and the cry line 0536#55 says Luxray.

### Leech Seed tutor line

**The Leech Seed tutor in the Cherrygrove Pokémon Center says your Pokémon "already knows Baton Pass".** The line was copied from the New Bark Town Baton Pass tutor. Cosmetic.

*Source:* bank 0544#11 (已经会接力棒了), shown at file 849 L398 after `MonHasMove … 73` (Leech Seed) at L331.

### Elite Four practice names

**The Elite Four practice rematches probably show another Trainer's name.** In the post-game practice battles, Agatha or Lance does the talking, but the battle uses another Trainer's data, so the opponent is probably named Koga in Agatha's room and Lorin in Lance's room. The first-run battles use the right Trainers. Cosmetic. Not confirmed in game.

*Source:* Agatha's room (file 818 L1509) starts trainer 703, named Koga (阿桔); Lance's room (file 820 L1479, Doubles L1545) starts trainer 705, named Lorin (梨琳). Agatha's Doubles: L1575 (703 ×2). Agatha's intro line before the battle: 818 L1502. The first-run battles use 247 Agatha and 246 Lance (D-1442).

### Uncle Apricorn's box

**Uncle Apricorn doesn't check that you have Kurt's Apricorn Box.** He admires "that thing you're holding" and buys it whether or not you carry one. Harmless: everyone gets the box, and key items can't be thrown away.

*Source:* file 225 script 15 (Route 29): no `HasItem`; each of the three offers runs `TakeItem 468` (L3692, L3737, L3782) and then gives item 468 back with the money.

### Route 26 Nugget

**The Route 26 Phanpy Trainer gives you TM41 for your Nugget but lets you keep the Nugget.** This happens when you choose to give it to him; selling it to him works normally. In your favour.

*Source:* file 218: the give path (L1551) gives item 368 (TM41) and sets flag 1111 but has no `TakeItem`; the sell path (L1522) takes item 92 (D-1404).

### Cherrygrove Wooper boy and the clover hunter

**The Cherrygrove Wooper boy and the Five Island clover hunter share a switch.** Talking to the crying boy in Cherrygrove City (whose Poké Ball the Wooper snatched) also removes the clover hunter on Five Island, the man who finds the four-leaf clover. If you haven't done the Five Island clover scene yet, it can't be started until the Ruins of Alph scene where you promise Molly to look for Prof. Hale, which brings him back. Nothing is lost unless that Ruins of Alph scene never happens; the Mt. Silver Revival Herbs (which need the Five Island scene) just wait. Do the Five Island clover scene before you talk to the boy. Side effect: if you forced the sale on Five Island, the hunter comes back after the Ruins of Alph scene and just repeats a line. Cosmetic.

*Source:* flag 1973 is the hunter's hide flag (Five Island object 24, file 58 script 15; set when the sale is forced, L7740) and the Wooper quest's "talked to the boy" flag (file 847 L1106, checked by the Poké Ball at L1133). Cleared by the Ruins of Alph Molly scene (file 51 L4289, with 1975/1978). The Mt. Silver Turtwig owner who gives the Revival Herbs is shown by the Five Island "Forget it" path (file 58 L4425 clears his hide flag 1530) (D-1405).

## Cherrygrove City to Azalea Town

[Quests on this page](08-cherrygrove-to-azalea.md)

### Union Cave Marill choice

**Letting Yamamoto catch Marill in Union Cave still counts as saving it.** Even if you answer No to "Step in and stop Marill from being caught?", the owner and her Marill reappear in Violet City after Crystal's scene at the end of Ilex Forest, and she thanks you for stepping in. Harmless.

*Source:* file 56 L785–L989: the No path sets the quest var 0x40AD = 8 (L969) like the Yes path (L2838), only without clearing flags 1528/1825. The Ilex Forest Crystal scene (file 92 L10515 → L10927) clears 1825 and 1528 whenever the var is already 8, so Violet City (file 854 L1810) shows the thank-you line 548#113.

### Marill owner's Azumarill

**The Marill owner mourns "my Azumarill".** Her Pokémon is a Marill everywhere else. You only see this line if you never met her Marill in Union Cave. Cosmetic.

*Source:* bank 548#114 (玛力露丽), shown by file 854 L3837 when flag 1528 is set (set by the Ilex Forest Crystal scene, file 92 L10528–L10534, when the quest var isn't 8); 548#113 also misspells it (玛丽露).

### Pokémon Academy class and Youngster Ward

**Some answers in the Pokémon Academy class make losing to Youngster Ward cost you the reward.** Your answers in the class decide the teacher's gift: most answers lead to TM67 Recycle, and only a full set of "safe" answers gives 2 Big Pearls instead. The answers that lead to TM67 also mark the class as finished, so if you then lose to Ward, the teacher only repeats his closing line and you get nothing. If you lose after only "safe" answers, the class simply starts again. Ward's Pokémon are Lv. 4–5, so losing is unlikely. Save before the class.

*Source:* file 82 (Violet City, east house): flag 1858 is both "class finished" (scripts 6–12 check it) and "give TM67". It is set by Limber answers 0–2 (L963), Sylveon answers 0–2 (L1119), "Yep, I cheated all the way" (L1275) and beginner-Pokémon answers 0, 1, 3 (L1646/L1673/L1700). `TrainerBattle 752` (Youngster Ward) at L1727; a loss jumps to L1904 `WhiteOut`. After a win, L1837: flag set → item 394 (TM67), clear → L1910 item 89 ×2 (Big Pearl).

### Sprout Tower offerings

**The Sprout Tower monks take their offering even if you can't pay.** When a monk on the ground floor asks for an offering and you say Yes, you're let through with too little money; what happens to your money then isn't known (probably $0). Answering No means battling him instead. The Elder on 3F does check your money before selling his sutras. Not confirmed in game.

*Source:* file 16 L1022, L1110, L1216 use `SubMoneyImmediate` ($3,000 / $5,000 / $10,000) with no money check (Yes paths L973/L1053/L1167; No starts `TrainerBattle 747` etc.). 3F (file 18 L2384/L2480) uses `HasEnoughMoneyImmediate 5000`.

### Ruins of Alph Potion girl

**The Ruins of Alph Potion girl thanks you for a Potion you never gave.** Her request, and her "Liar. You don't even have a Potion." line, can't be seen. The statue quest itself still works. Cosmetic.

*Source:* file 37 script 19 (bank 70#50–#54) runs on var 0x4079, an earlier story counter (set to 0/1/2 in Kanto by files 739, 212, 115): Prof. Elm's Lab (file 840 L3184/L3314) sets it to 3 before you reach Johto, so she always starts at stage 3 (#54).

### Route 32 Igglybuff counter

**The Route 32 Igglybuff storm scene shares a progress counter with earlier story scenes, harmlessly.** Several Kanto story scenes also change this counter, but they all happen before you reach Route 32 and leave it at a "not started" value, so the storm scene starts normally when you talk to Nurse Joy or the Igglybuff Trainer.

*Source:* var 0x40A6 is set to 1 by Mt. Moon Square (file 9 L5634), the S.S. Anne (files 156 L426, 157 L1512, 162 L459) and Silph Co. (files 795 L2208, 834 L5074/L5215), and to 0 by the S.S. Anne B1F (file 162 L1658) and the Saffron takeover (file 17 L12045). The quest uses 2–5: the Igglybuff Trainer (file 232 L1516–L1562) sets 2 from any value below 3; Nurse Joy (file 233) treats 0, 1 and 5 alike before her request flag 1983 is set. The earlier note said "set to 0 by Sprout Tower 2F", which is wrong.

### Bugsy's four-Pokémon rule

**Bugsy's "no more than four Pokémon" rule probably never applies.** You can likely bring six. The check reads a number left over from whatever happened just before, so in rare cases he might refuse you anyway; if he does, talk to him again. Not confirmed in game.

*Source:* file 866 script 2 → L367 compares var 0x8005 with 5 and 6 (→ L4470, msg 12), but never loads the party count (no `GetPartyCount`, unlike the rematch at L4541). 0x8005 is a scratch variable.

### Bugsy's rematch line

**After you win a Bugsy rematch, he gives his refusal line.** You see "None of your Pokémon can have a type that's strong against Bug…" instead of a victory line. Cosmetic.

*Source:* file 866 L4530 and L4590 show message 22 after `TrainerBattle 713` (L4505, Doubles L4565).

### Charcoal Kiln HM01

**The Charcoal Kiln apprentice takes HM01 without checking you have it.** At "Give him the TM for Cut?" → Yes, players without HM01 still get the Leek, and players with it lose their HM01. If you still need HM01, answer No. Not confirmed in game.

*Source:* file 871 L602 (msg 51) → L1428–L1804: every path ends in L1773 (Leek, item 259) and L1796 `TakeItem 420` (HM01) with no `HasItem` check; sets flag 1984.

### Air Cutter or Solar Blade

**The Charcoal Kiln master praises Air Cutter but teaches Solar Blade.** The Chinese says Air Cutter in that line too; the rest of his lines say Solar Blade. Cosmetic.

*Source:* bank 563#60 (真空斩); the tutor teaches move 669 (Solar Blade; file 871 L1964/L2499), and messages 63–72 say Solar Blade (日光刃).

### Losing to Goh in Union Cave

**Losing to Goh in Union Cave can repeat the lure scene.** If you lose, answering Yes to "Help Goh move the rock?" starts the lure scene over, and No doesn't record the outcome. Win the battle. Not confirmed in game.

*Source:* file 56: the Goh battle (L3512 `TrainerBattle 755, 0, 1, 0`, no white-out) jumps to L4012 on a loss; Yes at L4419 and L4533 jumps to L1587 (the start of the lure scene) instead of L3588 (Goh's catch ending); the No path (L4550–L4604) sets no flag or var (var 0x40A8 = 2 and flags 762/677 are set elsewhere at L2367–L2377).

### Kurt's five Tidal Bells

**Kurt gives you five Tidal Bells.** Probably copied from his Apricorn Ball gifts. Harmless.

*Source:* file 60 (Slowpoke Well B1F) L3457–L3469 sets item 503 count 0x8005 = 5.

### Route 30 dates (pointer)

**Green's and Red's Route 30 dates have the opposite confession check.** See [Ilex Forest and Goldenrod City](#ilex-forest-and-goldenrod-city) for the full entry.

*Source:* file 228 L761 and L789; details in the Ilex Forest and Goldenrod City entry.

### HM08 and Mr. Pokémon's quiz

**Holding HM08 Rock Climb skips Mr. Pokémon's quiz for good.** His quiz (prize: Exp. Share) only opens after the Dark Cave trouble is over. Once you carry HM08, which the Mt. Mortar Hiker gives you for his Map (see [Mt. Mortar: the runaway Hitmontop and the Hiker's map](11-cianwood-mahogany.md#mt-mortar-the-runaway-hitmontop-and-the-hikers-map--hm08-rock-climb)), he only gives a Rock Climb tip. Do his quiz before you hand over the Map. Other Exp. Shares can be had in Viridian City and at Silph Co. Possibly deliberate (a late-game tip replaces the quiz).

*Source:* file 229 script 1: L30 `HasItem 427` (HM08) → L88 (msg 29) before any other check; the quiz needs flag 1808 (L51) and gives item 216 once (flag 2335, L607–L625). HM08's only source is the Mt. Mortar Map exchange (site/src/data/items.json).

### Crystal's walk

**Crystal's "Let's go for a walk together" leads nowhere.** It shows one line and ends. Crystal has no date scenes or progress, although you can confess to her.

*Source:* file 851 L966 (menu 96, shown once flag 1645 is set and Crystal's lock 2145 is clear) → L1676: one message (100), then `End`.

### Pewter Museum Brock and the Route 30 Chikorita

**Talking to Brock in the Pewter Museum can make the Route 30 Chikorita disappear.** If you talk to him after the Cherrygrove orphanage scene but before the Route 30 Chikorita scene, while his siblings' quiz is unfinished, the Chikorita is gone for good. Do the Route 30 scene first.

*Source:* flag 1323 hides the Chikorita and its Trainer (Route 30 objects 25/26) and marks the scene done (file 227 L1026, set at L4192). It is cleared once by file 851 @492 and set by Brock on every talk while his siblings' quiz isn't finished (file 753 L683/L3496 → L3506) (D-1424).

### Gyro Ball TM kept

**The Violet City Forretress kid lets you keep the Gyro Ball TM.** In your favour.

*Source:* file 854 L535 `HasItem 401` (TM74); the hand-over L3872–L3895 only sets flag 1850; the file has no `TakeItem 401` (D-1425).

### Falkner's, Bugsy's and the fire-breather's type rules

**Falkner's, Bugsy's and the Route 32 fire-breather's type rules let through Pokémon they shouldn't, and Falkner refuses some he should accept.** Their checks are lists of banned Pokémon that stop at the Sinnoh Pokédex, so many later Pokémon get in (for example Yungoos or Gumshoos with Falkner). Falkner refuses Rotom even in its Flying form (Fan Rotom). Bugsy lets in Hippowdon. The fire-breather lets in Carnivine and Magnezone.

*Source:* Falkner (file 856 L971–L14807, 692 species; 226 later non-Flying species pass); fire-breather (file 232 script 13, 457 species up to #493: every non-Fire species except Carnivine and Magnezone, nothing later); Bugsy (file 866, 203 species: Hippowdon and 55 later Fire/Flying/Rock species pass) (D-1426). Re-counted against site/src/data/species.json.

## Ilex Forest and Goldenrod City

[Quests on this page](09-ilex-goldenrod.md)

### Celebi's Sitrus Berries

**Celebi's treatment never checks or takes the 10 Sitrus Berries the ranger asks for.** Only the 10 Fresh Water are checked, and nothing is taken. In your favour.

*Source:* file 52 L2885 and L3574 are both `HasItem 30 ×10` (Fresh Water); bank 81#13, #107 ask for Sitrus Berries (大树果); file 52 has no `TakeItem`.

### Koume, Sakura and the bug hunt

**Talking to Koume, Sakura or the fire ranger during the Ilex Forest bug hunt can break the hunt.** They share the bugs' progress counters, so a bug could become catchable without Honey, or Bugsy's "all done" check could never pass. Their requests are meant for after the hunt, but they're already around during it. Finish the bug hunt before talking to them. Not confirmed in game.

*Source:* file 92: Kricketune's state (var 0x409A) is also Koume's quest var (Koume, Ilex Forest script 19, checks 2/3/4); Sakura in the north gatehouse (file 869 L120–L198) sets it to 3 or 4. Burmy's state (var 0x409B) is also the Houndour ranger's var (script 31, L4155 sets 2). Both are visible during the hunt (Koume/Sakura hide flag 2033 is only set at L8232). The hunt's end (L5669–L5737) resets 0x409A/0x409B to 1, the quests' start value. Flags 2101/2102.

### Noah and Flo

**Fisherman Noah and Ace Trainer Flo in Ilex Forest count as one Trainer.** Beat one and the other only says the after-battle line. You lose one battle's prize money.

*Source:* file 92 scripts 24 (trainer 100, Noah) and 26 (trainer 119, Flo) both check and set flag 1460 (L1229/L1279, L1314/L1364).

### Haircut Brother's price

**The younger Haircut Brother needs $500 but charges $300.** In the US game he checks and charges $300; the hack raised only the check. Have $500 on you.

*Source:* file 94 L2806 (`HasEnoughMoneyImmediate 500`) / L2912 (`SubMoneyImmediate 300`).

### Goldenrod clerk's warehouse line

**The Goldenrod clerk's "secret deals in the warehouse" line can never be seen.** After the photo case he always says "North of Azalea, Mary's the prettiest!" Flavour only.

*Source:* file 882 L2238–L2277: the three checks on var 0x4098 (≠ 0, ≠ 1, ≠ 2 → L15727, msg 99) exclude every value, so 573#93 is unreachable.

### Radio Tower grunt and the old man

**One Radio Tower takeover conversation may jump into the wrong scene.** In Goldenrod City during the takeover, a Team Rocket grunt is bullying an old man at his barricade. If you answer Yes to "Teach this Team Rocket grunt a lesson?" while standing in the gap between the two of them, the game would start the Extreme Speed tutor's Lemonade lesson instead of the battle. Whether you can step into that gap wasn't checked. Not confirmed in game.

*Source:* file 882 script 38 (grunt object 36 at 369,355 and old man object 39 at 369,357, hide flag 441; barricade object 37 at 368,356): L1659 → L2572 `GetPlayerCoords`; at player Y = 356 it jumps to L2193, the Extreme Speed tutor's Lemonade check (`HasItem 32`). The earlier note said someone stands on that row; only the barricade does, west of the gap.

### Radio quiz B button

**In the Radio Tower 1F radio quiz, pressing B on a question counts as a right answer.** Each question only checks for the three wrong choices, so backing out of the menu moves on as if you had answered right. Pressing B on all five questions wins the radio upgrade. In your favour. Not confirmed in game.

*Source:* file 29 script 3: the five menus (L327, L419, L511, L603, L695) are `MenuInit [1, 1, 0, 1, 0x800C]` (cancellable, B result 0xFFFE); each tests only the three wrong indices (L375–L407, L467–L499, L559–L591, L651–L683, L743–L775) and falls through otherwise. D-1479.

### Buena's lottery line

**After a right password that doesn't bring a prize, Buena's scene ends with the lottery attendant's line.** You see "The winning number is [your name]! Does it match the ID No. of any of your Pokémon? Let's check!", then Buena walks back. In the US game she says "Tune in to my show again tomorrow!" here. Your point is still saved. Cosmetic. Not confirmed in game.

*Source:* file 29 L5656 (reached from L4574, L4890, L5204, L5396, L5506 when var 0x413A isn't a prize total) shows bank 0063#32, Felicity's lottery line; buffer 0 last holds the player's name (L3859). Vanilla Radio Tower 2F (file 30 L1384) shows msg 32 of its own bank, Buena's "Tune in to my show again tomorrow!"; the hack moved the script into the 1F file and changed only the prize path to msg 87 (L5675). D-1478.

### Bike Shop owner's lines

**The Bike Shop owner's lines don't match what he checks.** He thanks you for beating the bikers and says "You already have a Bicycle", but only checks whether you already have the Pass. Harmless.

*Source:* file 887 script 1: L18 `HasItem 480` (Pass) is the only check; msgs 0 and 1 then give item 480.

### Fortune-teller's price

**The fortune-teller's ideal-Pokémon reading checks for $300 but charges $10,000.** With $300–$9,999 you still get the item, and your money probably drops to $0. Have $10,000 before asking. Not confirmed in game.

*Source:* file 895 L228 `HasEnoughMoneyImmediate 300`; `SubMoneyImmediate 10000` at L313/L537/L589.

### Green's and Red's Route 30 dates

**Confessing to anyone closes Green's and Red's Route 30 dates.** This is the opposite of every other partner's dates, which need a confession. On top of that, the male-player branch checks the wrong thing, so Green's own lock is never checked: a male player who never confessed gets Green's dates whatever he picked in the Dream World.

*Source:* file 228 L761: `CheckFlag 1645` → `GoToIf [1]` sends you to the plain "How've you been?" talk when you **have** confessed, the opposite of every other date script (739 L2301, 859 L719, 851 L930, 758 L3645, 216 L2786). For male players L789 checks flag 106 (got a starter, always set) where the female branch checks Red's lock 2154, so Green's lock 2141 is never checked.

### Female players and Red's confession

**A female player can never confess to Red after the Dream World.** Red's confession checks Green's lock instead of Red's, and every Dream World choice a female player can make locks Green, including choosing Red.

*Source:* file 109 script 21 (Victory Road 2F object 15) L2369 checks only flag 2141 for both genders; nothing in file 109 checks Red's lock 2154. Every female choice sets 2141 (file 898 L2392–L2632, including "Red" at L2443–L2475, the only block that leaves 2154 clear).

### Love readings and confessions

**Any finished love reading counts for the confessions, even "Just friends is better" or wrong answers.** This only matters for partners reopened after the Dream World.

*Source:* file 895 L430/L989/L1497 set flag 1618 for every finished reading; the confessions (files 109, 110, 758, 923) check only 1618, not the "near future" flag 1619 (set only at L993; read by file 895 L601 and the MooMoo Farm, file 251 L861).

### Battle Tower partner room (pointer)

**The Battle Tower partner-room scenes that would reopen Yellow and Misty can't be reached.** See [Battle Frontier, Cianwood City and Mahogany Town](#battle-frontier-cianwood-city-and-mahogany-town) for the full entry.

*Source:* file 75 L1521, L1658; file 249 L4250–L4254; details in the Battle Frontier, Cianwood City and Mahogany Town entry.

### Dream World battles before the old man

**If you fight Will or Karen in the Dream World before talking to the old man, you lose the partner choice.** He disappears after either battle, and leaving through the broken statue then locks every partner. Talk to the old man first. Probably intended, but easy to miss.

*Source:* file 898: both battle endings (L1261 Will, L1757 Karen) go to L2307, which sets flag 2300 (the old man's hide flag; he is object 0, script 2). The statue (object 3, script 6, with the Lunar Wing → L1763) jumps to L2337 and locks 2141–2145 and 2153–2157 unless the old man's choice set 2302 (L1808).

### Rocky Helmet and the bug hunt

**Taking the Rocky Helmet in Ilex Forest before the bug hunt is over spoils the hunt.** The Helmet man is tied to the hunt's Ariados. If you take the Helmet first, the Ariados rock does nothing and the hunt counts the Ariados without crediting you. The hunt can still be finished, but you can deal with at most two bugs yourself, so you miss the top reward. If you find the Ariados first, he won't give the Helmet until the hunt ends. A Helmet taken mid-hunt means you can get a second one later. Finish the bug hunt first.

*Source:* file 92 script 20 checks and sets flag 2104 (@985/@1056, gives item 324), the Ariados "done" flag: the Honey spot ignores you once it's set (L1927 → L4344) without adding to your count, but every end-of-hunt check (L4490, L4608, L9322, L9722) only needs 2104, and Skorupi's rock also resolves a still-hidden Ariados (L9976–L10004), so the hunt ends with at most two bugs credited (no top reward, PP Max + Heart Scale). 2104 is cleared at the hunt end (L5709) (D-1412).

### Purugly quest and the bug hunt

**Leaving Ilex Forest mid-hunt can scramble the Goldenrod Purugly quest.** The Team Rocket act may start as soon as you enter the girl's house, skip the clinic choice or count as "Purugly kept", and finishing the bug hunt later wipes your Purugly progress. Finish the bug hunt first. Not confirmed in game.

*Source:* var 0x409D is both the Ariados state (file 92, values 1–5) and the Purugly quest state (file 897, values 2–6); the hunt end resets it to 1 (file 92 L5737) (D-1413).

### Friday's Daily Drawing prize

**Friday's Daily Drawing prize isn't the one announced.** The attendant announces a Cherish Ball, but the 1st prize is an Old Gateau. The Chinese says Cherish Ball too.

*Source:* file 901 L1946 (1st prize) → weekday chain L2792 → L4034 gives item 54 (Old Gateau) on Fridays; bank 589#42 (D-1414).

### Game Corner 500-coin option

**At the raised Game Corner price, "500 coins for $50000" gives only 50 coins.** Choose "50 coins for $5000" instead, as often as you need.

*Source:* file 903 L6374–L6455 (menu 94/95) → L7575: `HasEnoughMoneyImmediate 50000`, `SubMoneyImmediate 50000`, `GiveCoins 50` (L7596–L7623) (D-1415).

### Cynthia's Rest in my room

**Cynthia's "Rest in my room" asks for a Snow Mail but would take a Bubble Mail.** At home in Pallet Town, Cynthia only adds "Rest in my room" to her menu if you carry a Snow Mail, but choosing it tries to take a Bubble Mail instead. In practice the option never appears: it needs the move-in step, which no player can finish, and neither Mail can be obtained anywhere in the game (see [Pallet Town to Pewter City](#pallet-town-to-pewter-city), which also lists the other Mail mismatches). In the same menu, "I'm busy" shows Misty's goodbye line instead of Cynthia's. Harmless.

*Source:* file 842 script 15 (1F, Cynthia object 8, hide flag 422): L1064 needs var 0x40B5 ≥ 7 → L7063 `HasItem 144` (Snow Mail) → menu 537#197 "Rest in my room" → L7154 → L8417 `TakeItem 139` (Bubble Mail; result not checked) → warp to 2F, 0x40B5 = 8 (L8473). "I'm busy" (L7161) shows 537#212 (Misty) instead of #218. 0x40B5 = 7 is only set in file 843 (2F), whose PC script (script 1, L41 → L363) ends at L4292 for every player with a starter (flag 106) while the var is 6, the value Mom's visit leaves (file 736 script 4). Items 139/144 have no source (site/src/data/items.json; D-1398).

## Radio Tower, Ecruteak City and Olivine City

[Quests on this page](10-ecruteak-olivine.md)

### Pokéathlon Dome and the Route 36 tree

**Visiting the Pokéathlon Dome at the wrong moment could block the road to Ecruteak City.** If your first trip into the Dome falls between the Plain Badge and the odd-tree scene on Route 36, Crystal disappears from the tree. Only her scene moves the tree, so the road west stays blocked. Do the Route 36 tree scene before you enter the Pokéathlon Dome. Not confirmed in game.

*Source:* flag 551 hides Crystal, Gold, Bayleef and Quilava at the tree (file 243 objects 3, 11–13; set at new game, file 149 L178; cleared by the Plain Badge, file 883 L621; set by the tree scene, file 243 L1179). The unchanged vanilla Dome 1F first-visit scene (file 123 script 1 → L981/L1046, var 0x40E2 = 0) clears 551 for its own cutscene and sets it again at the end (L3276/L3679). The tree (object 4, script 1) is hidden only by flag 463, set only by the tree scene (file 243 L1175); talking to the tree itself never moves it (L1541 only reacts to the Rock Incense).

### Puppy-love quest counter

**The puppy-love quest shares a progress counter with the Goldenrod Gym story, probably harmlessly.** The Gym story is always over before the quest can start.

*Source:* var 0x408D: the quest uses values 5–9 (files 245 L778/L1076 and 25 L2510/L4192/L5289), the Gym chain 1–4 (files 32 L2650, 883 L673/L1012/L1846, 888, 890). The mother stands in the Route 36 National Park gatehouse (file 245, zone 104), which you can only reach after the Plain Badge (sets the var to 4) opens Routes 35 and 36.

### Route 35 Pidgey letter

**Reading the Route 35 Pidgey's letter doesn't let Viridian City's Nurse Joy give her gift again.** The two share a switch, but harmlessly: that Nurse Joy is gone by then and nothing brings her back.

*Source:* flag 1061 is cleared by file 240 L4099 (Pidgey), checked by file 925 L648 (the writer) and file 742 L238–L279 (Viridian Pokémon Center Nurse Joy, object 8, 2 Paralyze Heals); file 883 L613 (Plain Badge) sets it. Her object is hidden by flag 1244 (set at file 738 L1655 and file 212 L1935, never cleared). The letter can't be read before the Plain Badge.

### Prof. Birch and the unmasked Sudowoodo

**Players who didn't save Prof. Birch on Route 12 see the unmasked Sudowoodo early, and Birch's memory of the rescue follows the Sudowoodo instead.** If you didn't save him, the Sudowoodo stands near the National Park gatehouse even before the odd-tree scene. After the Plain Badge, Birch in the Goldenrod friendship checker's house no longer "remembers" being rescued, even if you did save him. Finishing the Route 36 Sudowoodo story makes him "remember" it again, even if you never saved him. Cosmetic.

*Source:* flag 111 is the unmasked Sudowoodo's hide flag (file 243 object 20) and "saved Prof. Birch" (set at file 199 L2249; read at file 888 L272). The Plain Badge clears it (file 883 L617), and the end of the Route 36 Sudowoodo story sets it again (file 243 L3814).

### Will and Karen's National Park challenge

**Will and Karen may skip their National Park challenge if you did certain other scenes first.** Gold's Game Corner scene and the uncut-stone gamble in an Islander's House count as beating them, and he then just says "Beating us makes you feel pretty good about yourself, huh?". It also works the other way: beating Will and Karen skips Gold's Game Corner scene. The Plain Badge and Silver's Route 37 scene reset all this, so only scenes in between count. Cosmetic. Not confirmed in game.

*Source:* flag 1604 is set by file 25 L2668 (Will and Karen beaten), file 903 L3184 (Gold's Game Corner scene, which is itself skipped when 1604 is set, L2003) and file 737 L3404 (Islander's House, zone 507); read at file 25 L478/L796 (→ L2585, msg 123), file 737 L442 and file 58 L2051 (only a check, not a set). Cleared by the Plain Badge (file 883 L649) and the Route 37 scene (file 246 L331).

### Arthur's ribbon freeze

**Arthur's ribbon gift on Route 36 can freeze the game.** This is the freeze shared by all seven weekday siblings. Arthur gives his ribbon on Thursdays once you've met all seven. Save before you talk to him then.

*Source:* file 243 script 2 (weekday 4, var 0x4094 = 7) → L1617 → L2301–L2342: undecoded bytes after `PlayFanfare [20]` (D-1331; work/notes/softlock_audit.md).

### Morty's post-game challenge size

**Morty's post-game challenge asks for three Pokémon but requires six.** If you come back after the final Hall of Fame without the Fog Badge, Morty asks for a 3-on-3, then says "Please use at least six Pokémon". The battle is still a 6-on-6 Double Battle. Bring six Pokémon.

*Source:* file 918 L500 → L1055: 605#79 (3-on-3), then the main-story check prints 605#20. Trainer 31 ×2.

### Morty's Lv. 1 Pokémon

**Morty's Gym team has three Lv. 1 Pokémon.** His team data has Gengar, Dusclops and Mismagius at Lv. 80, plus Mimikyu, Dhelmise and Sinistcha at Lv. 1, six Pokémon in all. If the battle really uses this team, half of his side faints almost at once. Not confirmed in game.

*Source:* trainer 31 (Morty) party data, party count 6 (site/src/data/trainers.json, exported from the ROM); used by the Gym battle `TrainerBattle 31, 31` in file 918 (D-1440).

### Morty's Ghost rule

**Morty's "weak to Ghost" rule refuses some Pokémon it shouldn't and lets others in.** It refuses Exeggutor and Rotom, which are Psychic or Ghost in this hack. It lets in Stunfisk, Yungoos and Gumshoos, which aren't. (Golduck and Noctowl are Psychic in this hack, so they're correct.)

*Source:* file 918 L1140–L13661 is a fixed list of 660 banned species, not a type check (all jump to L14645). Refused: Exeggutor (103), Rotom (479), also Meloetta (648, not obtainable). The list is incomplete past #493.

### Lantern riddle 2 (not a bug)

**Lantern riddle 2's answer is correct.** This isn't a bug. The clue "Round head, round hands, a body round too, round eyes, and antennae poking through" fits Ledyba, No. 165, so the answer is 5.

*Source:* file 916 L6188 (bank 603#126); menu index 4 ("5") is the only option that doesn't jump to the failure chain (L7067). Ledyba is #165. Earlier versions of this page listed it as unconfirmed.

### MooMoo Farm Miltank fall sick again

**If you finish the Dream World before the League HQ's third order, the MooMoo Farm Miltank fall sick again for good.** The third order at the League HQ makes them sick again, but the farmer only asks you to investigate once, and the Dream World is the only cure. Afterwards the milk stall, the farm's Seal girl and the Sunflora lady stay closed. If you can, do the MooMoo Farm investigation after that third order. Suspected hack bug. Not confirmed in game.

*Source:* flag 744 (Miltank healthy) is set at new game (file 149 @492) and by the Dream World cure (file 898 @2329, with 2289 at @2321), cleared on arrival in Johto (file 840 @3194/@3324) and by the League HQ round-3 order (file 31 @4666) with no condition. The farmer skips the investigation once 2289 is set (file 251 @106 → L903); the stall, Seal girl and Sunflora lady check 744 (file 251 @117/@147/@214; file 249).

### Dozen Moomoo Milk

**The MooMoo Farm farmer promises a dozen Moomoo Milk but gives one.** The Chinese says "a dozen" too. Cosmetic.

*Source:* bank 391#15 (一打哞哞牛奶); file 251 L1370 shows msg 15, then L1375–L1387 gives item 33 (Moomoo Milk) ×1 via `CallStd 2033`, flag 2301.

### Jasmine's Defense rule

**Jasmine's Defense rule refuses Aegislash and lets several weak Pokémon in.** Her rule is three Pokémon with a base Defense of 130 or higher. Aegislash is refused although Doublade is allowed; Stunfisk, Yungoos and Gumshoos get in. Same gap as Morty's list.

*Source:* file 909 L839–L14918 is a list of 742 banned species (→ L15137), correct for #1–#493 but patchy after: Aegislash (#681, base Def 140) refused; Stunfisk, Yungoos and Gumshoos (Def 30–84) pass among Pokémon you can get. Rule text 607#30.

### Jasmine's cut-off TM line

**Jasmine's "And this TM, too..." is cut off and no TM is given at the Gym.** TM91 Flash Cannon comes later, at the Lighthouse, after you bring the Secret Potion. Probably intended (the Lighthouse emergency interrupts her), but it looks lost.

*Source:* file 909 L14988 (msg 3), then L15154 ("Lady Jasmine! Trouble!!!"); the TM (item 418) is given at file 66 L3606.

### Unused Olivine port Machine Part

**An unused Machine Part scene at the Olivine port can't be reached.** The Café's Machine Part is the working one. Harmless.

*Source:* file 152 script 6 gives a Machine Part (item 481), sets flag 458 and hides object 3, but zone 240 has only objects 0–2 and nothing runs it. The Café copy is file 915 L1968–L1986.

### Café Machoke record reset

**Two story scenes reset whether you fed the Café Machoke, harmlessly.** Both happen before you can reach the Café.

*Source:* flag 458 is cleared by file 246 L303 (Route 37 scene) and file 23 L3547 (Burned Tower scene), and set by file 915 L1986 (Café Machine Part) and file 152 L222 (unused copy).

### Route 38 gatehouse test character

**A leftover test character could break the Alto Mare Bikers' story if it ever appeared.** It sits hidden in the Route 38 gatehouse to Ecruteak City and offers to "Send them to Alto Mare" or "Keep them in Kanto". It should stay hidden. Harmless in normal play.

*Source:* file 248 script 4 (Route 38 Ecruteak gatehouse object 2, hide flag 1366) rewrites flags 2013–2023, 1109, 1663, 1673, 1580 and var 0x4097 (L145–L208, menu 248 msgs 3–5; see [Saffron City to Cinnabar Island](05-saffron-cinnabar.md) and [Sevii Islands and Indigo Plateau](06-sevii-islands-indigo.md)).

### Will and Karen, fake grunt and Chimchar record

**Declining Will and Karen, beating the Route 39 fake grunt and getting Prof. Rowan's Chimchar are all stored as one thing.** In normal play this does nothing: Rowan is gone after the Plain Badge, and Route 39 can only be reached after Silver's Route 37 scene, which removes Will and Karen. Not confirmed in game.

*Source:* flag 1620 is set by file 25 L2654/L2763/L5333 (No to Will and Karen; scripts 7/8 then jump to the "need evidence" line), file 249 L776/L2122 (fake grunt) and file 890 L2175 (Chimchar; script 10 checks it at L343), and cleared by the Plain Badge (file 883 L653) and the Route 37 scene (file 246 L327) (D-1431).

### Olivine Leppa Berry menu

**The Olivine salesman's Leppa Berry menu never appears.** He always sells Weakness Policies.

*Source:* file 907 L2237 jumps to the Leppa Berry branch (L3165) only while flag 106 (got a starter) is clear; 106 is set when you get your starter (file 738 L3946/L4080, file 840 L238) and never cleared (D-1418).

### Lantern riddle failure order

**A wrong answer at the 4th or 5th lantern riddle makes Grandpa ask riddles 2–5 again before telling you that you failed.** Cosmetic.

*Source:* file 916 L6631–L6715 and L6809–L6893 jump to L6935, the failure chain's riddle 2, instead of its riddle 5 (L7331) or the failure line (L7463) (D-1419).

## Battle Frontier, Cianwood City and Mahogany Town

[Quests on this page](11-cianwood-mahogany.md)

### Whirl Islands Challenge payout

**The Whirl Islands Challenge pays out after only one island, again and again.** After visiting just the northwest island you can claim a prize, accept the challenge again and report straight back for another prize. Not confirmed in game.

*Source:* file 872 L2417–L2450 tests flag 2097 four times instead of 2097/2098/2099/2100, then clears 2094 and offers the challenge again.

### Northeast island quiz answer

**The northeast island's quiz accepts Azalea Town, not Ecruteak City, as the other place tied to Lugia.** Possibly intended (the Tidal Bell under Slowpoke Well).

*Source:* file 960 L1397–L1491 (and the copy at L2878): bank 0735#53–57; options 1–3 jump to the failure line L2952, so only option 0 (Azalea Town) passes.

### Lugia: one chance

**Lugia is gone for good once you catch it, knock it out or run away.** Only a loss lets you try again. Save before the battle.

*Source:* file 104 L3915 `WildBattle 249`; `CheckBattleWon` is false only on a loss or draw (→ L4216 `WhiteOut`). Any other result sets flag 579 (Lugia's hide flag), hides the sisters' summoning circle and sets 265 (L3939–L3967); the sisters then leave (flag 581, L4154). The only clear of 579 is inside the summoning cutscene (L3616), and Satsuki's dance-theater offer (file 924 L4299) is closed by 265.

### Mt. Mortar statue and the Lustrous Orb

**The Mt. Mortar statue says it resonated with your Lustrous Orb without checking that you have one.** It opens after the final Hall of Fame, not the first, and takes you to Palkia's space.

*Source:* file 98 script 3 L137–L179: needs flag 2261 only, no `HasItem`; then `Warp 521`.

### Dark Cave copy of the Whirl Islands Challenge

**The unreachable Dark Cave copy also holds a copy of the Whirl Islands Challenge.** Nothing leads into that cave. Harmless.

*Source:* file 964 (zone 176, Dark Cave Route 31 side) checks the same flags 2094–2100 (L104–L385, L2650/L2661). No map warp and no script `Warp` leads into zone 176.

### Yellow and Misty in the Battle Tower partner room

**Yellow and Misty never appear in the Battle Tower partner room.** So the scenes that would reopen their romance can't be reached. They are removed when Gold's scene on Route 39 plays, which you always see before the Battle Frontier opens; Yellow also leaves at your first Trainer House visit.

*Source:* file 75 objects 2 (Yellow, flag 603) and 5 (Misty, flag 336). 603 is set by file 249 L4250 (Route 39 Gold scene) and file 746 L80 (first Trainer House visit); 336 by file 249 L4254; nothing clears either. The scenes would clear the romance locks 2143/2142 (file 75 L1521, L1658).

### Jirachi stone without Star Pieces

**The Jirachi stone can be "repaired" without any Star Pieces.** Choose Yes repeatedly to repair the stone. Each repair takes a Star Piece if you have one, but still counts if you have none. In your favour. Not confirmed in game.

*Source:* file 81 script 10 → L1588 (menu) → L1801–L1861: `TakeItem 91` (Star Piece) runs with no `HasItem` check and its result is ignored; `AddVar 0x408C, 1` always follows.

### Jirachi stone and the story counter

**The Jirachi stone counts its repairs on a story counter, and its scene overwrites that story's progress.** If you've finished the legendary story that ends with Crystal taking Suicune to the orphanage in Cherrygrove City, the stone needs exactly seven repairs. If you haven't, it needs more, and when the stone turns into Jirachi the scene overwrites that story's progress, so its remaining scenes may never play. Finish that story before you start repairing the stone. The seven-repair figure is not confirmed in game.

*Source:* file 81 L1849 `AddVar 0x408C, 1`, L1855 Jirachi appears at ≥ 24 (→ L1985). 0x408C is the legendary-investigation story var (values 0–17: files 739, 738, 212, 178, 853, 923, 900, 815, 899, 31, 129, 758, 195, 851); its highest value is 17, set in Cherrygrove when Crystal takes Suicune to the orphanage (file 847 L5336). Repairs needed: 24 − current value (7 at 17). The Jirachi scene sets 0x408C = 23 before the Team Rocket battle (L2637, trainers 629/630) and 25 after it (L2868); story checks still waiting for 3, 12 or 15 (files 178, 758, 129, 31, 133, 195) can then never pass. The stone needs flag 2261 (final Hall of Fame).

### Battle Frontier Cut man without HM01

**Without HM01, the Battle Frontier Cut man starts the photographer's routine instead.** Almost every player has HM01 by then. Not confirmed in game.

*Source:* file 81 script 6 L1043–L1057: without item 420 (HM01) it jumps to L1491, inside the Tuesday/Saturday photographer's photo routine (weekday check at L1377).

### Doubles memory battle announcement

**The Doubles memory battle announces a Single Battle.** Cosmetic.

*Source:* file 78 L1033 shows msg 32 ("the Single Battle in your memories") before `TrainerBattle x, x` (Double); msg 33 ("Double Battle") is unused.

### Cianwood Pharmacy after the Amphy crisis

**Gold and Crystal stay in the Cianwood Pharmacy for good and keep handing out Secret Potions.** Once the Olivine Lighthouse emergency starts, the pharmacist never sells his Energy Powder, Energy Root, Heal Powder or Revival Herbs again. Talking to Gold or Crystal without a Secret Potion replays the scene and gives you another one.

*Source:* file 878: the shop (script 1) only opens while flag 471 is set; Gold, Crystal and their Pokémon (objects 1–4) are hidden by 471. It is set by the Route 39 Gold scene (file 249 L4118), cleared when the Amphy crisis starts (file 66 L2507) and never set again. The gift (item 464, L1170) has no flag; scripts 2/3 only test `HasItem 464`.

### Lure Ball kept

**The Lure Ball girl "receives" your Lure Ball but you keep it.** In your favour.

*Source:* file 872 L3369–L3396 thanks you and gives her reward, with no `TakeItem` (the file's only `TakeItem` is the Close Combat tutor's at L5159).

### Chuck's Fighting rule

**Chuck's Fighting-only rule refuses Staraptor and lets a few non-Fighting Pokémon in.** Staraptor is Fighting/Flying in this hack, yet it's refused. Stunfisk, Braviary, Yungoos and Gumshoos get in.

*Source:* file 874 L1213–L14950 is a list of 724 banned species (→ L15233) covering every non-Fighting Pokémon through Gen 4 but missing many later ones; it bans species 398 (D-1409). Most missing later species (Patrat, Woobat, Klink and others) can't be obtained in this hack; the obtainable ones that pass are 618, 628, 734, 735.

### Green and Silver by the Persian statue (not a bug)

**Green, Silver and their Pokémon by the Persian statue leave for good after their scene.** This isn't a bug. An earlier version of this page said they might come back on every visit, but the scene's ending removes them permanently.

*Source:* file 881 objects 10–13 (zone 385) use hide flag 2235, which no `SetFlag` touches, but script 13 ends with `HidePerson 10–13` (L1317–L1329), and `HidePerson` sets the object's hide flag permanently (engine note in work/notes/guide_errata.md).

### Petrel's Chatot

**Petrel's Chatot can never be caught.** The Chatot, Lance, Pryce and the others nearby apparently stay on Team Rocket HQ B2F for good. Not confirmed in game.

*Source:* file 90 script 6 (L888 / L2874–L3674) offers the catch (bank 111#99, wild Chatot Lv. 10) only if flag 500 is **set**, but the Chatot (B2F object 31) is hidden while 500 is set. 500 is set at new game (file 149 L320), cleared in Archer's room (file 933 L2062) and set again only after the catch (L3674); objects 29–41 share it.

### Unused Mahogany Silver Wing gift

**An unused Silver Wing gift in Mahogany Town can't be reached.** Harmless.

*Source:* file 933 script 7 gives a Silver Wing (item 482), sets flag 2336 and hides object 25, but zone 133 (Mahogany East House, Archer's room) has only objects 0–24 and nothing runs script 7. Flag 2336 is also set at the Bell Tower roof (file 21 L5896).

### Pryce's weather rule

**Pryce's weather rule bans by Pokémon, not by Ability.** His rule is "no Pokémon whose Abilities change the weather". It bans Probopass (whose Abilities here are Sturdy, Magnet Pull and Power Spot) and bans Charizard, Wailord and the others even without a weather Ability. Charizard's normal Abilities here (Solar Power, Blaze, Tough Claws) include no weather Ability; only a special form has Drought. Vanilluxe (Snow Warning) isn't banned, but it can't be obtained.

*Source:* file 928 L269–L782: 28 species checks (→ L1083, msg 14). Banned without a weather Ability: Charizard (6), Probopass (476).

### Burned Tower beasts scene and the expedition leader

**The Entei, Raikou and Suicune scene in the Burned Tower can be lost.** After [Lance visits your house](01-pallet-to-pewter.md#pallet-town-lances-visit-home-after-the-final-hall-of-fame), see the [Burned Tower release scene](10-ecruteak-olivine.md#burned-tower-prof-hale-molly-and-the-three-beasts-post-game-frees-entei-suicune-raikou) before you rematch the [Mt. Mortar expedition leader](11-cianwood-mahogany.md#mt-mortar-the-five-member-expedition-the-way-to-the-altar-needed-in-the-final-chapter). If you beat him in that window, his "Please join my expedition" resets the expedition, and the release scene doesn't play. To avoid the battle, answer No when he asks "Are you a really strong Trainer?". Not confirmed in game.

*Source:* var 0x409F: Lance's visit (file 842 @2223) sets 11, the Burned Tower scene (file 23 script 14) needs 11 and sets 12 (file 23 L6953). The leader (file 962 script 2) runs his first-meeting path for any value other than 3, 5 or 10; winning `TrainerBattle 897` (Psychic Hewitt, L2706) leads to the join, and either answer ends at L3482 `SetVar 0x409F, 3` (D-1406).

### Satsuki's Lugia option

**Satsuki's "Lugia" option can lead to the Ho-Oh path and a second Ho-Oh.** If you've caught Ho-Oh but not Lugia, her first menu is "I want to see Lugia / Never mind", and choosing Lugia gives the Ho-Oh line ("the Clear Bell is still in Morty's hands"). Talk to her again and pick Lugia from the full menu instead. The wrong option also re-opens Morty's Clear Bell battle and the Bell Tower, so a second Ho-Oh can be caught, again and again while Lugia is uncaught. Not confirmed in game.

*Source:* file 924 L4299 (var 0x40A9 ≥ 11) → short menu at L4915; choice 0 jumps to L4968 (609#87) and sets var 0x40A9 = 7; Morty (file 918) checks 7; Ho-Oh `GiveMon 250, 95` at file 21 @6116 (D-1407).

### Close Combat tutor's fee

**The Close Combat tutor is free if your Pokémon has to forget a move.** He still says he'll take the 3 Rare Candies. In your favour.

*Source:* file 872 checks them at @3410 but takes them only on the free-slot path (@5159); the forget-a-move path ends at L5393 with the same line and no `TakeItem` (D-1408).

### Lex's Doubles

**Lex's "Doubles" on Route 41 is a Single Battle.** Both options give the same Single Battle; Doubles only adds a party-size check.

*Source:* file 960 script 2: menu L583–L604; both paths start `TrainerBattle 823, 0` (Swimmer Lex, L2332/L2392); Doubles adds `GetPartyCount` (L2368) (D-1410).

### Boot Camp Ruins password lines

**In the Boot Camp Ruins, female players see one of Silver's lines in the wrong place, and the digits read out are wrong.** When Green tries the number from the crumpled paper, she reads out 0-7-3-2-2, which matches neither the paper (325003225300469) nor the real password 14246. Female players see Silver's "This crumpled paper says..." line there instead. Use 14246.

*Source:* file 881 @3792 `GenderMsgBox 90 91`: female players see 572#91 out of place; 572#90 reads out 0-7-3-2-2 (D-1411; the merged speaker label is D-1121).

## Lake of Rage, Blackthorn City and beyond

[Quests on this page](12-lake-of-rage-to-sinjoh.md)

### Lake guardian's quiz answers

**Two of the lake guardian's quiz answers look wrong.** For the Koffing question, both 0 and 2 fit (10 Mankey, Koffing and Mareep with 26 legs allows 0–3 Koffing), but only 2 is accepted. The Pikachu question accepts 14, although four moves can be learned in 24 orders, and 24 isn't one of the options (12, 14, 16, 18). The Chinese may carry a hidden rule. Answer 2 and 14.

*Source:* bank 0618#8–12 and #28–32; file 935 L1111–L1198 (Q4: D-1439).

### Uxie, Mesprit and Azelf: one chance

**Uxie, Mesprit and Azelf are gone for good once you catch them, knock them out or run away.** Only a loss lets you try again. Save before each battle.

*Source:* file 934 scripts 29–31 (`WildBattle` 480/481/482 at L1563/L1636/L1709): `CheckBattleWon` is false only on a loss or draw (command 220 → 0x0205172C), so a catch, knockout or flee hides the guardian and sets its hide flag (586/587/588) and "trial" flag (649/651/652). Only the lake trials in file 935 (L795, L1404, L1517) clear 649/651/652, and they advance var 0x4098 so they can't be repeated.

### Anti-Age Spray never used up

**The Anti-Age Spray is never used up.** One bottle works forever. Because the old man won't make another while you have one ("Don't you already have an Anti-Age Spray? Use that one up first."), you can never get a second. In your favour.

*Source:* file 101 L5813–L5872 checks item 429 and shows "used the Anti-Age Spray!" but no script takes item 429; 0121#151 says one bottle is one trip; the maker's `HasItem 429` refusal is L5984 → L7021 (msg 152).

### Durin Berries for the Anti-Age Spray

**The Anti-Age Spray needs 20 Durin Berries, but the game hands out only 16.** Swinub has to eat 10 before the old man will make the spray, and the spray itself takes another 10. The Mahogany Pokémon Center gives 15 and Fuchsia City 1. You need the spray to follow Giovanni in the final chapter, so plant Durin Berries to grow more if you're short. Possibly intended.

*Source:* file 101 L5640 (and L6733, L6873) takes 10 for Swinub, which sets the recipe flag 2249 (L7013, checked at L3961/L4224); L6005/L6110 checks and takes 10 for the spray (plus 5 Rare Candies, Sacred Ash, Fresh Water, $10,000). Gifts: 15 in Mahogany (file 931 L402), 1 in Fuchsia (file 804 L4158). No other script gives item 182.

### Blackthorn Gym Trainers

**The Blackthorn Gym Trainers may never battle you.** If you accept the MooMoo Farm farmer's request to look into his sick Miltank (the request that leads into the Dream World) before you reach Blackthorn City, the four Gym Trainers are skipped and the entrance Trainer just says "Welcome to the Blackthorn Gym, Champion." Clair can still be challenged. To get the Gym Trainer battles, do Blackthorn City before helping MooMoo Farm. Not confirmed in game.

*Source:* file 939 coord triggers (scripts 7, 8, 10) need var 0x40A3 = 1, 2, 3 in turn (script 7 L346 falls back to msg 13 at L14262); trainers 932–935. The var is set to 1 only at the end of the Vermilion construction clash (file 774 L1161), to 5 when you answer Yes to the MooMoo farmer (file 251 L1423, offered whenever flag 744 is clear, i.e. from your arrival in Johto) and to 6 in the Dream World (file 898 L2307). Earlier text named only the Dream World.

### Clair's Dragon rule

**Clair's Dragon-only rule lets many non-Dragon Pokémon in.** Many Pokémon from after the Sinnoh Pokédex get in; of those you can get, Snivy, Excadrill, Stunfisk, Amaura, Yungoos and Gumshoos do. Among older Pokémon, Seadra is allowed but Horsea isn't; Magmar, Porygon, Kecleon, Corphish, Shieldon and Drapion are allowed; Trapinch and Swablu aren't.

*Source:* file 939 L853–L14096 is a list of 698 banned species (`PlayerHasSpecies`), not a type check; checked against site/src/data/species.json types. Non-Dragon species up to #493 that pass: Charmander line, Rhydon, Kangaskhan, Seadra, Magmar, Gyarados, Lapras, Porygon line, Aerodactyl, Dunsparce, Corphish, Crawdaunt, Kecleon, Cranidos line, Shieldon line, Drapion. 225 non-Dragon species from #494–#1025 pass.

### Santos's and Wesley's ribbon freeze

**Santos's ribbon gift (and Wesley's at the Lake of Rage) can freeze the game.** It's the freeze shared by all seven weekday siblings. They only offer the ribbon once you've met all seven, on their own day. Save before you talk to them from then on.

*Source:* file 937 script 7: ribbon branch when var 0x4094 = 7 and weekday 6 (L197 → L1611 → L2751); L2774 `GiveRibbon` 64, then undecoded bytes after `PlayFanfare [20]` at L2780. Wesley: file 934 L5643 `GiveRibbon` 61, same bytes (@5653). D-1331; work/notes/softlock_audit.md.

### Play Rough tutor teaches Flail

**The Blackthorn "Play Rough" tutor teaches Flail.** The runaway Dragonair Trainer's father promises Play Rough, and every line says Play Rough, but your Pokémon learns Flail.

*Source:* file 944 script 8: `MonHasMove`/`SetMonMove` use move 175 (Flail; Play Rough is 583) at L1925 and L3461 (D-1305; 626#62).

### Gallade's Berry Juice

**The Route 48 Gallade "takes" your Berry Juice but you keep it.** In your favour.

*Source:* file 261 L1239 `HasItem 43` (Berry Juice); the file has no `TakeItem` at all.

### Dragon's Den Elder's quiz record

**A wrong answer in the Dragon's Den Elder's quiz is noted but nothing uses it.** Probably a removed reward (in HeartGold it decided the Dratini gift). Harmless.

*Source:* file 112 L1318 sets flag 219 on every "Hah? I didn't quite catch that..." branch; no script checks 219.

### Unused Dragon's Den scene and item

**An unused Dragon's Den scene and item ball are left in the files.** They can't be reached. Harmless.

*Source:* file 111 script 5 (a Silver / Lance / Clair Multi Battle, `MultiBattle 736, 733, 734` at L1212, vanilla leftover) moves objects 9–12, but map 253 has only objects 0–9 and nothing runs script 5. Script 11 (a Dragon Scale item ball, item 235, using script 10's flag 2256) is attached to no object either.

### Raikou: one chance

**Raikou on Route 47 is gone for good once you catch it, knock it out or run away.** Only a loss lets you try again. Save before the battle. It may be intended (same as Lugia).

*Source:* file 260 L5082 `WildBattle 243`; `CheckBattleWon` is false only on a loss or draw, so any other result sets flag 2320 and hides it (L5106/L5110). The only clear of 2320 is the one-time Burned Tower beasts scene (file 23 L6949, var 0x409F 11 → 12).

### Dialga and Palkia: one chance

**Dialga and Palkia are gone for good once you catch them, knock them out or run away.** Only a loss lets you try again. Save before each battle.

*Source:* file 130 scripts 10/11: `WildBattle 483` at L2706 sets flag 2342 and `WildBattle 484` at L2748 sets 2343 on any result but a loss or draw. Lance's post-League visit (file 842 L2193/L2197) is the only clear, and it plays once (after the final Hall of Fame).

### Route 45 Senior Trainer's line

**The Route 45 Senior Trainer's "I've only got 1 left" line can't be seen.** Harmless.

*Source:* file 258 script 4 L221 → L2047 (msg 51) runs only when flag 234 is set, but 234 (set at L7201 after his gift) is also his own hide flag (Route 45 object 3).

### Arceus and Regigigas out of reach

**Arceus can't be summoned in practice, because the Azure Flute can't be obtained after the Hall of Fame.** Arceus needs the flute, and the centre circle of the Mystri Stage only reacts if your flute came from the Seven Island shrine keeper's post-game gift, which can't be reached (see [Sevii Islands and Indigo Plateau](#sevii-islands-and-indigo-plateau)). The same flute is the way back into the temple after the story, so the post-game Regigigas there is out of reach too.

*Source:* file 131: the centre-circle coord trigger (16,14, script 10) needs var 0x40B7 = 5, set only at file 942 L539 (the shrine keeper's gift), which is the unreachable Azure Flute offer (file 942 L104). Script 10 L579–L661 then also needs flag 2261, item 536 and species 483/484/487 in the party; Arceus is script 11 (L1335, flag 2306). Regigigas: script 9 (L1008, flag 2305, cleared by the final Hall of Fame, file 822 L2498); post-game temple access needs the flute (file 49 L694). Earlier text cited L590 for the var check; L590 is the flute `HasItem`.

### Unused Kyogre room in Reversal Cave

**A second Reversal Cave room with a Kyogre is still in the files, but nothing leads there.** Harmless.

*Source:* file 134 (map 525, "Reversal Cave" Kyogre room, wild Kyogre Lv. 50 at L178, needs the Blue Orb, item 535, at L85); no map or script warps into 525; Route 47 (map 151) only warps to map 526.

### Palkia's space cabin

**The cabin in Palkia's space can't be entered.** So its Abra man and Cynthia scenes never play, and the Mystri Stage Arceus-circle scene can't be seen. Harmless.

*Source:* zone 521's cabin door (20,25 → zone 523) has no door behaviour and 20,26 is blocked; no script warps in (D-1417, from the map's collision data). File 132's Cynthia (object 0, hide flag 733) would also need 733 cleared: new game (file 149 L464) sets 732, not 733, and 733 is set in the Ruins of Alph (file 53 L752); only file 132 itself clears it. File 131 scripts 4–6 also need an event Arceus as your only Pokémon.

### Giratina after Lance's visit

**Lance's visit could allow a second Giratina, but probably can't in practice.** Lance's visit brings Giratina back. It plays only once, as soon as you get home after the final Hall of Fame, and Giratina can only be summoned after that same Hall of Fame entry, so there's no chance to fight it in between. Not confirmed in game.

*Source:* file 135 L2400–L2528 needs flag 2261 and sets Giratina's "done" flag 2340 on any result but a loss or draw (catch, knockout or flee); Lance's visit (file 842 script 7 → L1083, `ClearFlag 2340` at L2201) clears it. The visit runs from the home map's frame script on var 0x4106 = 3, which only the first Hall of Fame (file 822 L175, before 2261 is set) and the final one (L2558, same block that sets 2261) set; later Hall of Fame entries (L322 path) don't. Earlier text said 2340 is set "only on a catch or win".

### Route 45 Dragonite counter

**The Route 45 Dragonite quest shares a progress counter with early Kanto scenes, harmlessly.** The S.S. Anne party scenes, the Vermilion construction clash and the Saffron City scenes use the same counter, and Team Rocket's Saffron takeover resets it. All of these are over before you can reach Route 45, so this can't cause trouble in normal play.

*Source:* var 0x40A5: file 258 (L2386 = 2 battle pending, L2851 = 3, L732 ≥ 3 → Outrage tutor; Route 45 coord script 14 on value 2). Other writers, all Kanto: S.S. Anne files 156 (L420/L809/L6488; coord script 18 on value 0), 157 (L590/L1506), 161 (L1947), 162 (L1664); Vermilion file 774 L1267; Saffron file 755 L3152 (coord script 16 on value 0); reset at the takeover, file 17 L12039 (D-1416). Earlier text said "Olivine Lighthouse and S.S. Aqua"; no Olivine Lighthouse file uses this var.

## Dungeons, Battle Tower and game-wide events

[Quests on this page](13-dungeons-and-common.md)

### Unown Report notes

**The Ruins of Alph Research Center never gives any Unown Report notes.** The researcher only ever says his "about 1,500 years old" line. The hidden rooms the later notes depend on can't be reached either: the four chamber walls now lead to the dream-world hall. Whether the ! and ? Unown depend on this wasn't checked.

*Source:* file 38 L804–L929: every note branch needs var 0x40EC ≥ 1 (L877–L922, L1495, L1519), and the hack's only `AddVar 0x40EC` commands are in unreachable blocks (file 41 @562–620, file 45 @540–598) (D-1427). Notes advance var 0x403E (L2304), so it stays 0. The chamber walls warp to map 324 and nothing leads to the hidden rooms (files 40, 44, 46, 47; maps 313, 317, 319, 320 have no incoming warp), so var 0x40F1 never rises (file 38 L1437–L1476). Notes 71#34–#45 can't be seen.

### Hidden Ruins of Alph rooms' exit

**A leftover exit in the hidden Ruins of Alph rooms points into Island Forest.** It can't be used: the rooms can't be reached. Harmless.

*Source:* the rooms' exits warp to map 492 when 0x403E ≥ 7 (files 40/44/46/47 L386 → L452 `Warp 492`); the hack reused map 492 as Island Forest. 0x403E never leaves 0.

### Ho-Oh panel and Silver's battle

**Solving the Ho-Oh panel early might make the Molly chapter's dream world skip Silver's battle.** Solving the stone panel in the Ho-Oh chamber (north-west) is treated as "Silver's battle done" in that dream world. It depends on whether the Ho-Oh chamber can be reached before the Molly chapter. If you want to be safe, leave the Ho-Oh panel until after the Molly chapter. Not confirmed in game.

*Source:* file 45 L182 (panel solved, after `AlphPuzzle 3` and flag 2426) clears flag 565, which is set at new game (file 149 L190) and which the dream world (file 50) uses to mark Silver as finished: objects 14/15, checks at L2556, L2686, L2745, L2944, L3486; cleared at L3224 after his Multi Battle.

### Field moves without the move

**Surf, Waterfall and the other field moves work without a Pokémon that knows them.** You only need the Badge; your first healthy Pokémon is used. The party menu still only lists moves a Pokémon knows. This is an intended HM-free feature, not itself a bug. The obstacle behavior is verified in the game code; every field-move and party-menu path has not been replayed.

*Source:* the hack's script command 141 (`GetPartySlotWithMove`, handler 0x0204C8D4) returns the first healthy non-Egg slot; the water check (ov1 0x021E65E4) only needs the Rainbow Badge and the Waterfall check (ov1 0x021E5C86) always passes (D-1428). Not re-checked in this review (code analysis).

### Forest of Time during the bug hunt

**Entering the Forest of Time during the Ilex Forest bug hunt may play the wrong scene.** The two share a progress counter: the Sammy arrival scene could play with its actors missing, the maze traps could apply, or the Marauder scene could start early. Finish the bug hunt first. Not confirmed in game.

*Source:* var 0x4099 is set to 3/4/5 by the hunt (file 92 @10693/@10735/@2209; reset to 2 at the hunt end, L5713) and also drives the Celebi story (L5372 = 3). The Forest of Time (map 327, file 52) has coord triggers on 0x4099 = 3 (script 1) and = 5 (script 3); the other Ilex Forest copy (map 462, file 106) triggers on 2 and 4 (D-1429).

### Island Forest wild Pokémon

**Island Forest on Six Island has no wild Pokémon in the grass or water until you've solved a Ruins of Alph panel.** Fishing works. Solve any one Ruins of Alph panel first. Not confirmed in game.

*Source:* map 492 is still inside the original game's Ruins of Alph encounter check (ov2 0x02248420: maps 490–492 need one of flags 2423–2426) (D-1430). Not re-checked in this review (code analysis).

### Evolutions that cannot happen

**A few Pokémon have an evolution method that the game never checks, so they can't evolve that way.** Pancham never becomes Pangoro, and Gimmighoul, Kubfu, Galarian Yamask, White-Striped Basculin, Pawmo, Rellor and Finizen never evolve at all through the evolution their data gives them. Galarian Farfetch'd can't become Sirfetch'd by landing critical hits; a regular Farfetch'd still evolves into Sirfetch'd at Lv 40. Eevee can't become Leafeon at a Moss Rock and Nosepass can't become Probopass in a magnetic field, but a Leaf Stone and a Thunder Stone still work. Most of these Pokémon can't be met in the game anyway. Each Pokémon's page (for example [Eevee](/pokemon/eevee/#evolution)) marks these as not possible and lists any method that still works. Verified in the game code; not tried in game.

*Source:* D-1481. Evolution table `a/0/3/4` (10 slots × 6 bytes), evolution check arm9 0x020700FC: in the level-up switch methods 31–36 fall through to "no evolution" and methods 38+ fail the bound check (`cmp r0, #0x25`); methods 24–26 compare a map evolution code that is always 0 (stub 0x0203AAA0, copied into the battle setup at 0x020511B8). Trade context handles only methods 5–6, item use only 7, 16, 17.

### Things you can't get, although the game has them

**A few items and forms exist in the game's data but can't be obtained.** Read from the game code; not tried in game.
- **TM46 (Thief):** its item ball is never placed on a map.
- **Flapple, Appletun and Alcremie:** Applin needs a Tart Apple or Sweet Apple and Milcery a Sweet, and none of these items can be obtained.
- **Shaymin's Sky Forme:** the Gracidea only works on an event Shaymin, and the Shaymin from the Forest of Time isn't one.
- **Unown letters:** every wild Unown comes out as A (tested in an emulator: 65 wild Unown, all A).

*Source:* D-1339 (TM46 item ball, std 7136 unused), D-1493 (Tart Apple, Sweet Apple, Sweets have no source), D-1490 (Gracidea check arm9 0x02071024 needs the fateful flag), D-1487 (wild Unown form written back at ov2 0x02248AD4).

### Out-of-range story records (save data)

**Two scenes write past the end of the game's story records.** The Viridian Mart promoter on Route 1, who gives you a Berry Juice, and the end of the Mt. Mortar expedition each note that they've happened in a spot beyond the space the save keeps for story progress. Both scenes still play normally once. Measured in an emulator, both notes land in your save's Pokédex data. The promoter's sets a "seen" mark for entry No. 1335, past the end of the Pokédex; opening the Pokédex or the Trainer Card never reads it, so nothing visible changes. The expedition's sets the "caught" mark of Weezing (No. 110) without its "seen" mark; how the Pokédex shows that wasn't checked. There's no way to avoid it: the expedition is needed in the final chapter.

*Source:* D-1333; work/notes/softlock_audit.md. File 168 script 4 `CheckFlag 7286` (0x1C76) at @235, `SetFlag 7286` at @1954 (Route 1 Viridian Mart promo, Berry Juice item 43); file 962 @1819 `SetFlag 4461` (0x116D) at the end of the expedition, next to `SetFlag 675`. The hack has 3,232 flags: arm9 `GetFlagAddr` (0x0204F8E4) bounds the byte index at 0x194 and still forms base + 0x2E0 + index past the bound; block size 0x474 (0x0204F840). Vanilla layout: 0x116D → Pokédex caught bit for species 110, 0x1C76 → a Pokédex language byte. Probably typos for 0x0C76 / 0x016D. Observed in the hack (`emu_harness.py guide0107 --case promo_flag,mortar_flag`, both ROMs): the SetFlag handler (PC 0x0204F8B6) writes save offset 0x151A bit 6 (7286) and 0x13B9 bit 5 (4461); both are inside save array 6 (offset 0x13A8, 0x374 bytes, magic 0xBEEFCAFE, the Pokédex): +0x172 = seen bit of No. 1335 (seen bits +0xCC, 200 bytes), +0x11 = caught bit of No. 110 (caught bits +0x4). With the bit cleared first, the promoter's scene plays (lines 2–7, Berry Juice), sets it, and the next talk shows line 1 only. Read hooks while the Pokédex and Trainer Card were open: no read of the No. 1335 word (control: the caught word of No. 1 is read). D-1550.
