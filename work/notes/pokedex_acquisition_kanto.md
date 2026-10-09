# Pokédex acquisition audit: early Kanto

Audited 2026-10-09 against the untouched Chinese v4.0.3 ROM using the existing `romdata`, `gen_docs`, and `scriptdump` readers. No ROM built or game behavior changed.

Coverage: 50 raw generated rows, 47 distinct species/file/kind/level rows, 6 excluded rows. Files 169–199 and 733–809, plus all acquisition commands in 115 and 842. Inventory assertion checks exact equality against the generator’s whole scoped output, including variable-species starter and prize commands.

## Findings

- Starter restrictions apply to scripted gifts and encounters; this audit does not infer starter restrictions on ordinary grass/surf/fishing encounter tables.
- Exclude Route 3 letter Charmander, Route 10 Lv. 50 Zapdos, Power Plant Grimer/Electrode/Magneton, and house Poliwhirl.
- Keep both Ralts methods: before the Cascade Badge as a gift, after it as a catchable letter encounter if the gift was not taken. The unused Ralts death cutscene does not make the actual letter encounter unreachable.
- Oak starter GiveMon instructions are mutually exclusive branches; duplicate generated rows must not imply extra gifts.
- Honey-tree encounters are repeatable weekday encounters, not one-time static spawns.
- D-2292 records the Bellsprout seller’s missing money deduction and one-time flag; this is original-hack behavior and is documented, not fixed.
- Power Plant/Seafoam legendary acquisition requires the FINAL Hall of Fame, not the first entry. Zapdos is not reset on subsequent ordinary entries.
- Fearow’s pre-Volcano-Badge quest has no starter gate; Pikachu only gates the later Pidgeot loan branch.

## Reviewed inventory

### File 115 · Fearow · static Lv. 20

Before the Volcano Badge, help the woman protect her flower garden and beat the Spearow flock. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file115 script11 @603 CheckBadge6 → post-badge branch; @2627 wild Fearow; no starter requirement on pre-badge path.; guide/01-pallet-to-pewter.md: flower garden.; acquisition offsets [2627].

### File 115 · Scyther · static Lv. 15

Use one Honey on the shining Honey tree on Sunday. Repeatable with more Honey; the DS clock determines the weekday.

Evidence: CN file115 script16 @5008, weekday branches @6074–6242.; guide/01-pallet-to-pewter.md: Honey tree.; acquisition offsets [6242].

### File 115 · Pinsir · static Lv. 15

Use one Honey on the shining Honey tree on Tuesday. Repeatable with more Honey; the DS clock determines the weekday.

Evidence: CN file115 script16 @5008, weekday branches @6074–6242.; guide/01-pallet-to-pewter.md: Honey tree.; acquisition offsets [6102].

### File 115 · Eevee · gift Lv. 5

After the Route 2 and Viridian Forest Team Rocket rescue story, talk to the healed Eevee in the forest’s far northeast and accept it. Leave a free party slot.

Evidence: CN file115 script10 @2181; flag411.; guide/01-pallet-to-pewter.md: rescued Eevee.; acquisition offsets [2181].

### File 115 · Yanma · static Lv. 15

Use one Honey on the shining Honey tree on Saturday. Repeatable with more Honey; the DS clock determines the weekday.

Evidence: CN file115 script16 @5008, weekday branches @6074–6242.; guide/01-pallet-to-pewter.md: Honey tree.; acquisition offsets [6214].

### File 115 · Pineco · static Lv. 15

Use one Honey on the shining Honey tree on Friday. Repeatable with more Honey; the DS clock determines the weekday.

Evidence: CN file115 script16 @5008, weekday branches @6074–6242.; guide/01-pallet-to-pewter.md: Honey tree.; acquisition offsets [6186].

### File 115 · Heracross · static Lv. 15

Use one Honey on the shining Honey tree on Monday. Repeatable with more Honey; the DS clock determines the weekday.

Evidence: CN file115 script16 @5008, weekday branches @6074–6242.; guide/01-pallet-to-pewter.md: Honey tree.; acquisition offsets [6074].

### File 115 · Nincada · static Lv. 15

Use one Honey on the shining Honey tree on Thursday. Repeatable with more Honey; the DS clock determines the weekday.

Evidence: CN file115 script16 @5008, weekday branches @6074–6242.; guide/01-pallet-to-pewter.md: Honey tree.; acquisition offsets [6158].

### File 115 · Volbeat · static Lv. 15

Use one Honey on the shining Honey tree on Wednesday. Repeatable with more Honey; the DS clock determines the weekday.

Evidence: CN file115 script16 @5008, weekday branches @6074–6242.; guide/01-pallet-to-pewter.md: Honey tree.; acquisition offsets [6130].

### File 171 · Doduo · gift Lv. 20

Charmander starter only. Take the live Poké Ball in the Rocket warehouse on Route 2 East before the Celadon Rocket hideout finale. Leave a free party slot.

Evidence: CN file171 script3 @1300; guide/01-pallet-to-pewter.md: Rocket warehouse Poké Ball; file853 @3782 sets hide flag1473.; acquisition offsets [1300].

### File 171 · Barboach · gift Lv. 20

Bulbasaur or Pikachu starter only. Take the live Poké Ball in the Rocket warehouse on Route 2 East before the Celadon Rocket hideout finale. Leave a free party slot.

Evidence: CN file171 script3 @321; Charmander branch gives Doduo @1300.; guide/01-pallet-to-pewter.md: Rocket warehouse Poké Ball; file853 @3782 sets hide flag1473.; acquisition offsets [321].

### File 175 · Charmander · static Lv. 15

EXCLUDED: Unused letter Charmander scene; it cannot appear in normal play.

Evidence: CN file175 script7 @2242; object4 hide flag1366 never cleared to expose this encounter.; guide/known-issues.md: Route 3 letter Charmander.; acquisition offsets [2242].

### File 175 · Scyther · static Lv. 15

Charmander starter only. Talk to Bug Catcher Kenji to reveal the Scyther on the ledge, then challenge it. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file175 scripts30/31 @3512, @3633; clears2268 to show Scyther.; guide/02-pewter-to-vermilion.md: Scyther chase.; acquisition offsets [3633].

### File 175 · Ralts · gift Lv. 15

Before the Cascade Badge, give the Route 3 painter one Fresh Water, then accept his Ralts. Leave a free party slot.

Evidence: CN file175 script9 @2582; flag1390 redirects to the letter after the painter dies.; guide/02-pewter-to-vermilion.md: painter Ralts; file758 @3883 sets1390.; acquisition offsets [2582].

### File 175 · Ralts · static Lv. 15

After the Cascade Badge, if you did not accept the painter’s gift, read the letter beside Ralts and agree to take it. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file175 @2278–2377; object3 flag1361 is live (unlike Charmander object4).; guide/02-pewter-to-vermilion.md: painter Ralts.; acquisition offsets [2360].

### File 183 · Bulbasaur · gift Lv. 15

Pikachu starter only. After the Cascade Badge, intervene in the Route 5 shelter raid and win, then accept the rescued Pokémon inside the house. Refusing the rescue loses it. Complete the raid before making Sabrina laugh in Pokémon Tower. Leave a free party slot.

Evidence: CN file179 raid outcome; file183 @268/@456.; guide/02-pewter-to-vermilion.md: Pokémon shelter raid; file17 @12165 closes unfinished raid.; acquisition offsets [268].

### File 183 · Growlithe · gift Lv. 15

Bulbasaur or Charmander starter only. After the Cascade Badge, intervene in the Route 5 shelter raid and win, then accept the rescued Pokémon inside the house. Refusing the rescue loses it. Complete the raid before making Sabrina laugh in Pokémon Tower. Leave a free party slot.

Evidence: CN file179 raid outcome; file183 @268/@456.; guide/02-pewter-to-vermilion.md: Pokémon shelter raid; file17 @12165 closes unfinished raid.; acquisition offsets [456].

### File 190 · Squirtle · gift Lv. 5

Pikachu starter only. Recover your stolen Pokédex from the Squirtle Squad, then choose to save them from Team Rocket and accept Squirtle. Missable: advance through the grunt rescue before making Sabrina laugh in Pokémon Tower; refusing to help loses this gift. Leave a free party slot.

Evidence: CN file190 @5762; file17 closes the Route9 quest at inactive stages.; guide/03-vermilion-to-celadon.md: Squirtle Squad.; acquisition offsets [5762].

### File 191 · Zapdos · static Lv. 50

EXCLUDED: Unused vanilla Route 10 encounter; the catchable Zapdos is inside the Power Plant at Lv. 90.

Evidence: CN Route10 zone18 has no object/background/coordinate calling script4; header436 calls only2/5.; guide/known-issues.md: unused Route10 Zapdos.; acquisition offsets [230].

### File 192 · Bellsprout · gift Lv. 5

Accept the Route 10 Pokémon Center seller’s offer. Repeatable with a free party slot. Although he advertises $5,000, the original script does not charge money.

Evidence: CN file192 script2 → @265–354: party check then GiveMon @312; no money check, deduction or one-time flag.; D-2292; script audit, not emulator-tested.; acquisition offsets [312].

### File 195 · Articuno · static Lv. 90

After the final Hall of Fame entry and Lance’s visit to your home in Pallet Town. Melt the Seafoam Islands ice barriers to reach Articuno. Earlier trainer-style battles cannot catch it. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file195 @2672 gated by2261; Rocket scene sets1368; file842 @2177 clears1368 during Lance visit.; guide/05-saffron-cinnabar.md: Articuno; guide/01-pallet-to-pewter.md: Lance visit.; acquisition offsets [2672].

### File 195 · Kyogre · static Lv. 95

After the final Hall of Fame entry, bring the Blue Orb from Lance’s visit to the Seafoam Islands pedestal. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file195 script14 @2851; final Hall of Fame2261, Blue Orb, flag2288.; guide/05-saffron-cinnabar.md: catching Kyogre.; acquisition offsets [2851].

### File 196 · Magneton · static Lv. 55

EXCLUDED: Unused Power Plant encounter script; no event or map trigger starts it.

Evidence: CN file196 script5; zone489 event441 object/background/coordinate scripts omit2/4/5; header441 is empty (00000000).; Direct CN event/script inventory; no GoToStd/CallStd link to these map-local scripts.; acquisition offsets [378].

### File 196 · Grimer · static Lv. 25

EXCLUDED: Unused Power Plant encounter script; no event or map trigger starts it.

Evidence: CN file196 script4; zone489 event441 object/background/coordinate scripts omit2/4/5; header441 is empty (00000000).; Direct CN event/script inventory; no GoToStd/CallStd link to these map-local scripts.; acquisition offsets [225].

### File 196 · Electrode · static Lv. 55

EXCLUDED: Unused Power Plant encounter script; no event or map trigger starts it.

Evidence: CN file196 script2; zone489 event441 object/background/coordinate scripts omit2/4/5; header441 is empty (00000000).; Direct CN event/script inventory; no GoToStd/CallStd link to these map-local scripts.; acquisition offsets [288].

### File 196 · Zapdos · static Lv. 90

After the final Hall of Fame entry following Giovanni’s defeat at League HQ. Earlier Zapdos battles are trainer battles and cannot catch it. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file196 @1693 requires2261; @1717 sets1786. Final-only file822 @2478 clears1786 once.; guide/07-league-to-cherrygrove.md: Hall of Fame distinguishes final vs first.; acquisition offsets [1693].

### File 199 · Snorlax · static Lv. 35

Bring Mr. Fuji’s Poké Flute and wake the Snorlax blocking Silence Bridge on Route 12. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file199 script6 @1440; guide/04-celadon-fuchsia-saffron.md: wake Snorlax.; acquisition offsets [1440].

### File 199 · Torchic · gift Lv. 5

Rescue Prof. Birch from Poochyena on Route 12, then accept Torchic. Missable: collect it before the Rainbow Badge ceremony hides Birch. Wake the blocking Snorlax to reach him in time. Leave a free party slot.

Evidence: CN file199 @2321; file853 @3790–3802 hides Birch/Poochyena.; guide/04-celadon-fuchsia-saffron.md: Prof. Birch Torchic.; acquisition offsets [2321].

### File 199 · Poochyena · static Lv. 5

Before the Rainbow Badge ceremony, stop the Poochyena chasing Prof. Birch on Route 12. Wake the blocking Snorlax to reach it in time. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file199 script17 @2376; file853 @3790–3802.; guide/04-celadon-fuchsia-saffron.md: Prof. Birch Torchic.; acquisition offsets [2376].

### File 199 · Milotic · static Lv. 40

Talk to the fisherman about the fish-zapper, then refuse to battle Hugo. When shiny Milotic appears, choose to stop it. Guaranteed shiny. One chance: refusing, catching, defeating, fleeing or losing ends its appearance.

Evidence: CN file199 @4445 WildBattle [350,40,1]; hide flag1159 set before battle.; guide/04-celadon-fuchsia-saffron.md: shiny Milotic.; acquisition offsets [4445].

### File 734 · Piplup · gift Lv. 5

Earn the Mineral Badge, then pass the Two Island captain’s Water-type quiz. Answers: 29; Quagsire; Marill; Gastrodon; Armaldo holding a Passho Berry. One gift per save. Leave a free party slot.

Evidence: CN file734 script1 @905–2484, GiveMon @973; flags1119/1646.; guide/05-saffron-cinnabar.md: captain Water-type quiz.; acquisition offsets [973].

### File 738 · Bulbasaur · gift Lv. 5

Choose this Pokémon as your initial starter at Professor Oak’s Lab. You receive only one of Bulbasaur, Charmander or Pikachu.

Evidence: CN file738 starter variable controls GiveMon @3924/@4058; these are alternate dialogue branches, not additional gifts.; acquisition offsets [3924, 4058].

### File 738 · Charmander · gift Lv. 5

Choose this Pokémon as your initial starter at Professor Oak’s Lab. You receive only one of Bulbasaur, Charmander or Pikachu.

Evidence: CN file738 starter variable controls GiveMon @3924/@4058; these are alternate dialogue branches, not additional gifts.; acquisition offsets [3924, 4058].

### File 738 · Pikachu · gift Lv. 5

Choose this Pokémon as your initial starter at Professor Oak’s Lab. You receive only one of Bulbasaur, Charmander or Pikachu.

Evidence: CN file738 starter variable controls GiveMon @3924/@4058; these are alternate dialogue branches, not additional gifts.; acquisition offsets [3924, 4058].

### File 739 · Pikachu · static Lv. 5

Bulbasaur starter only. After the Route 1 tutorial, talk to the Viridian Mart clerk and follow the thief quest in Viridian City. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file739 thief scripts and starter flags1287/1288/1289; Route1 file168 sets quest setup.; guide/01-pallet-to-pewter.md: Viridian thief quests.; acquisition offsets [4315].

### File 739 · Meowth · static Lv. 5

Charmander starter only. After the Route 1 tutorial, talk to the resident who reports the Meowth thief and follow the thief quest in Viridian City. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file739 thief scripts and starter flags1287/1288/1289; Route1 file168 sets quest setup.; guide/01-pallet-to-pewter.md: Viridian thief quests.; acquisition offsets [3762].

### File 739 · Mankey · static Lv. 5

Pikachu starter only. After the Route 1 tutorial, talk to the street-light keeper and follow the thief quest in Viridian City. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file739 thief scripts and starter flags1287/1288/1289; Route1 file168 sets quest setup.; guide/01-pallet-to-pewter.md: Viridian thief quests.; acquisition offsets [3087].

### File 751 · Charmander · gift Lv. 10

Pikachu starter only. After the Viridian Forest Rocket scene, hear the Pewter Pokémon Center Trainer brag, rescue the abandoned Charmander on Route 2 East, and defeat its former Trainer. Missable: rescue it before the Cascade Badge. Once in the Pokémon Center, Charmander waits for you. Leave a free party slot.

Evidence: CN file751 @522, file170 @2290; file758 @3887 sets roadside/Trainer hide1367, but not Center Charmander hide1360.; guide/01-pallet-to-pewter.md: abandoned Charmander.; acquisition offsets [522].

### File 755 · Lapras · gift Lv. 70

During the Saffron Rocket takeover, speak to the cafeteria hostage after Jessie, James and Maxie. Missable: collect Lapras before the Rocket Boss battle; the hostages leave afterward, win or lose. Leave a free party slot.

Evidence: CN file755 script28 @3245; file834 @5066/@5207 sets hostage hide1208.; guide/04-celadon-fuchsia-saffron.md: employee Lapras.; acquisition offsets [3245].

### File 769 · Cubone · gift Lv. 5

After Agatha breaks up Team Rocket in Pokémon Tower, accept Cubone from Mr. Fuji’s Volunteer Pokémon House. Leave a free party slot.

Evidence: CN file769 @657; file17 @8203 reveals Cubone.; guide/03-vermilion-to-celadon.md: Mr. Fuji gifts.; acquisition offsets [657].

### File 774 · Horsea · gift Lv. 25

Side with the townsfolk in the Vermilion construction-site clash, then have Ryochi ask you for Horsea. Before obtaining the Good Rod, speak to the fisherman by the water without Oak’s Parcel. If the wild Horsea is already gone, he gives you one; otherwise he fishes up the wild encounter. Leave a free party slot.

Evidence: CN file774 @7575; fisherman checks1056,1065,1419, no484 and1867 clear.; guide/02-pewter-to-vermilion.md: Horsea.; acquisition offsets [7575].

### File 774 · Horsea · static Lv. 25

Feed the waterfront Horsea five Yache Berries, then agree to catch it. Alternatively, the fisherman can fish it up during Ryochi’s Good Rod quest if you sided with the townsfolk. One encounter; catching, defeating or fleeing removes it.

Evidence: CN file774 @7901; guide/02-pewter-to-vermilion.md: Horsea.; acquisition offsets [7901].

### File 802 · Mr. Mime · gift Lv. 15

Exchange 3,333 Coins at the Celadon Prize Corner. Repeatable with enough Coins and a free party slot.

Evidence: CN file802 script2 menu @2076–2092, GiveMon @2359; TakeCoins @2400/@2423/@2433 and loop to2068.; acquisition offsets [2359].

### File 802 · Eevee · gift Lv. 15

Exchange 6,666 Coins at the Celadon Prize Corner. Repeatable with enough Coins and a free party slot.

Evidence: CN file802 script2 menu @2076–2092, GiveMon @2359; TakeCoins @2400/@2423/@2433 and loop to2068.; acquisition offsets [2359].

### File 802 · Porygon · gift Lv. 15

Exchange 9,999 Coins at the Celadon Prize Corner. Repeatable with enough Coins and a free party slot.

Evidence: CN file802 script2 menu @2076–2092, GiveMon @2359; TakeCoins @2400/@2423/@2433 and loop to2068.; acquisition offsets [2359].

### File 842 · Poliwag · gift Lv. 5

Bulbasaur starter only. After talking to Mom following your starter choice, accept the Poliwag by the kitchen sink. Missable: collect it before Blue’s farewell scene in Viridian City; take it before leaving Pallet Town. Leave a free party slot.

Evidence: CN file842 script10 @6361; flags106,768,1088,1289 and2285; Blue scene file739 @3335 sets1088.; guide/01-pallet-to-pewter.md: send-off gifts, map reachability emulator verification.; acquisition offsets [6361].

### File 842 · Poliwhirl · gift Lv. 10

EXCLUDED: Unused Poliwhirl gift; the actual house gift is Poliwag.

Evidence: CN file842 GiveMon @6236 belongs to unused script9; zone63 object1 invokes Poliwag script10; header617 runs11/1/7.; guide/01-pallet-to-pewter.md: send-off gifts.; acquisition offsets [6236].

## Boundaries

The other acquisition agents/coordinator cover script files outside these ranges (including later Kanto, Sevii, caves, trades/loans, fossils, and ordinary wild encounter mechanics). The trade-table Pidgeot replacement in file115 is not a GiveMon acquisition and is documented separately in the guide; its loan restrictions should remain visible on the trade/loan source. No new bug decision was filed for unused remnants, which do not themselves harm gameplay.

## Fossil acquisition supplement

File905 @2586 is the only raw GiveMon/WildBattle/GiveEgg command across the entire indexed ROM for which the existing scanner cannot resolve species alternatives. The dedicated GetFossilPokemon handler supplies all seven species: Aerodactyl (Old Amber), Omanyte (Helix Fossil), Kabuto (Dome Fossil), Lileep (Root Fossil), Anorith (Claw Fossil), Shieldon (Armor Fossil), Cranidos (Skull Fossil). Each arrives at Lv.20. The live scientist is zone412 object19 at (4,4), no hide flag, script14. No badge or starter check exists on that script path. Bring the fossil to the west-side door on Cinnabar, return later after processing, and leave a free party slot. Receiving it clears pending species0x407F, so the service is repeatable. The original dialogue requests returning later; the exact processing/flag1 reset timing has not been emulator-tested in this audit.

These seven records are in the metadata’s `fossils` section rather than `entries`, because generic static_mons cannot enumerate the dynamic species variable. Integrate into the existing fossil availability branch so item availability still gates revival and no duplicate generic source remains.
