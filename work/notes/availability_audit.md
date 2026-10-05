# Pokémon availability audit (2026-10-05)

Which of the 1,440 species and forms in the game data a player can actually meet in the untouched Chinese v4.0.3 ROM
(`work/rom/origin_v4.0.3_cn.nds`). Static analysis of data and code (Capstone, `.venv`); nothing here was replayed in
an emulator unless stated.

**User rule (2026-10-05):** Pokémon a player meets only on trainers' teams or only in battle are "in the game, not
obtainable" and stay on the website. Pokémon a player can never meet come off the website.

**Result (first pass; see the later sections for the current lists):** 576 entries are never met and are listed in `work/tools/site/not_in_game.json` (the site exporter skips
them). 864 remain. 48 entries get verified sources, battle-only labels or notes from
`work/tools/site/extra_sources.json`. Giratina Origin and 16 Arceus types were added to the held-item form list in
`site/src/lib/verified-mechanics.ts`; the Diancie calendar entry is now "configured" and Volcanion's was removed.

## Verification

Three passes, each by a different agent, all against the ROM: the first audit, an independent recheck of every
"absent" verdict (all agreed), and an independent trace of every out-of-battle and regional form (then rechecked).

Sources checked (no unsourced species or form found on any of them unless listed below):
- All 149 wild encounter records (linked or not; every slot, radio, swarm, time of day), Headbutt, Bug-Catching Contest
  (incl. contestant data), the unused SoulSilver set `a/1/3/6`.
- Safari Zone `a/2/3/0`: all species #455 or lower. (The first audit's quick pair scan misread object-requirement bytes
  as species; the correct layout and a layout-free raw scan both find nothing new.)
- Battle Frontier sets `a/2/0/3`, `a/1/2/9`, `a/2/0/4` (species #1–#488, no forms); all 1,024 trainer parties with form
  bits; in-game trades both ways; fossils; roamers (243, 244, 380, 381); Primo password rewards (Mareep, Wooper, Slugma Eggs).
- Every script: GiveMon/GiveEgg/WildBattle/form commands, runtime species resolved (Oak's starters, Game Corner prizes
  Mr. Mime, Eevee, Porygon, Abra, Ekans, Dratini, Sandshrew, Cinnabar fossils), plus a raw byte scan of all 966 files.
  Script command 686 (fateful battle) is unused.
- Breeding roots (`poketool/personal/pms.narc`), evolution chains with the hack's evolution form code, every
  create-Pokémon call site and every form write (the form field is 5 bits, so forms above 31 can't exist).
- Calendar encounters (arm9 `0x020F6A64`, loader `0x0203AD24`) and the Pal Park weekday tables (below).
- Not scanned: Pokéwalker courses. Its `a/2/5/x` files are byte-identical to vanilla and it needs the IR device.

## Mechanisms found in this audit

- **Pal Park "Fixed Catch mode"** (script file 809, $10,000, own Balls, used when no GBA Pokémon are stocked): the map's
  wild table is record 142 + weekday − 1 (arm9 `0x0203A7B0`), so Sunday 141 … Saturday 147. Stunfisk is in Friday's
  record 146. Off by one (D-1484). Not in the guide yet.
- **Form lookup** `0x020721C0` returns the base personal index for an undefined (species, form): Diancie's calendar form 4
  is a normal Diancie (D-1489).
- **Held-item forms:** Charizardite, Steel Armor, Ninja Scroll (hack), Griseous Orb and Plates (vanilla, `0x02070E44`,
  `0x02070D66`; no Fairy case). No Primal, Mega Ring or Dynamax code.
- **Script form changes:** Rotom's Room (file 835), Route 3 meteorites for Deoxys (file 175, ScrCmd_518).
- **Evolution forms:** Lycanroc by hour (D-1486); the form table at `0x020740A4` is off by one (D-1485), which changes the
  Hisuian Lilligant route; evolution and breeding otherwise keep the mother's/pre-evolution's form.
- **Battle forms** (overlay 14): Castform, Cherrim, Darmanitan Zen Mode, Aegislash, Mimikyu are labelled "seen only in
  battle". Relic Song is implemented but no Pokémon can learn it, so Meloetta Pirouette never appears.
- **Shaymin Sky Forme:** the Gracidea needs the fateful flag, which the gift Shaymin lacks (D-1490).
- **Unown:** every wild Unown becomes A (D-1487). Letters B–? stay on the site as "no confirmed way to get it".
- Other findings: Volcanion's calendar entry can never fire (D-1488); Ice Path Darmanitan stays in Zen Mode (D-1491, D-1443).

## Never met (576), by reason

- **No wild encounter, gift, trade, one-time battle, evolution or breeding route, and no trainer uses it.** (247): Victini, Patrat, Watchog, Pansage, Simisage, Pansear, Simisear, Panpour, Simipour, Blitzle, Zebstrika, Woobat, Swoobat, Throh, Sawk, Maractus, Dwebble, Crustle, Sigilyph, Solosis, Duosion, Reuniclus, Vanillite, Vanillish, Vanilluxe, Klink, Klang, Klinklang, Elgyem, Beheeyem, Cryogonal, Druddigon, Bouffalant, Cobalion, Terrakion, Virizion, Tornadus, Thundurus, Reshiram, Zekrom, Landorus, Kyurem, Litleo, Pyroar, Skiddo, Gogoat, Pancham, Pangoro, Espurr, Meowstic, Spritzee, Aromatisse, Swirlix, Slurpuff, Inkay, Malamar, Tyrunt, Tyrantrum, Hawlucha, Klefki, Pumpkaboo, Gourgeist, Xerneas, Yveltal, Zygarde, Oricorio, Wishiwashi, Comfey, Oranguru, Passimian, Wimpod, Golisopod, Type: Null, Silvally, Minior, Turtonator, Tapu Koko, Tapu Lele, Tapu Bulu, Tapu Fini, Cosmog, Cosmoem, Solgaleo, Lunala, Nihilego, Buzzwole, Pheromosa, Xurkitree, Celesteela, Kartana, Guzzlord, Necrozma, Magearna, Marshadow, Poipole, Naganadel, Stakataka, Blacephalon, Zeraora, Meltan, Melmetal, Grookey, Thwackey, Rillaboom, Scorbunny, Raboot, Cinderace, Sobble, Drizzile, Inteleon, Rookidee, Corvisquire, Corviknight, Nickit, Thievul, Gossifleur, Eldegoss, Yamper, Boltund, Silicobra, Sandaconda, Cramorant, Clobbopus, Grapploct, Sinistea, Polteageist, Runerigus, Falinks, Pincurchin, Stonjourner, Eiscue, Indeedee, Morpeko, Cufant, Copperajah, Dracozolt, Arctozolt, Dracovish, Arctovish, Duraludon, Zacian, Zamazenta, Eternatus, Kubfu, Urshifu, Zarude, Regieleki, Regidrago, Glastrier, Spectrier, Calyrex, Enamorus, Sprigatito, Floragato, Meowscarada, Fuecoco, Crocalor, Skeledirge, Quaxly, Quaxwell, Quaquaval, Lechonk, Oinkologne, Tarountula, Spidops, Nymble, Lokix, Pawmi, Pawmo, Pawmot, Fidough, Dachsbun, Squawkabilly, Nacli, Naclstack, Garganacl, Charcadet, Armarouge, Ceruledge, Tadbulb, Bellibolt, Wattrel, Kilowattrel, Maschiff, Mabosstiff, Shroodle, Grafaiai, Toedscool, Toedscruel, Klawf, Rellor, Rabsca, Flittle, Espathra, Wiglett, Wugtrio, Bombirdier, Finizen, Palafin, Varoom, Revavroom, Cyclizar, Orthworm, Greavard, Houndstone, Flamigo, Cetoddle, Cetitan, Veluza, Dondozo, Tatsugiri, Clodsire, Great Tusk, Scream Tail, Brute Bonnet, Flutter Mane, Slither Wing, Sandy Shocks, Iron Treads, Iron Bundle, Iron Hands, Iron Jugulis, Iron Moth, Iron Thorns, Gimmighoul, Gholdengo, Wo-Chien, Chien-Pao, Ting-Lu, Chi-Yu, Roaring Moon, Iron Valiant, Koraidon, Miraidon, Walking Wake, Iron Leaves, Okidogi, Munkidori, Fezandipiti, Ogerpon, Archaludon, Gouging Fire, Raging Bolt, Iron Boulder, Iron Crown, Terapagos, Pecharunt
- **No source in the game, and no code ever gives a Pokémon this form.** (162): Alolan Rattata, Alolan Raticate, Alolan Diglett, Alolan Dugtrio, Alolan Meowth, Alolan Persian, Galarian Ponyta, Galarian Rapidash, Galarian Slowpoke, Galarian Slowbro, Galarian Farfetch’d, Alolan Grimer, Alolan Muk, Galarian Mr. Mime, Galarian Articuno, Galarian Zapdos, Galarian Moltres, Galarian Slowking, Galarian Corsola, Burmy (Sandy Cloak), Burmy (Trash Cloak), Wormadam (Sandy Cloak), Wormadam (Trash Cloak), Shellos (East Sea), Gastrodon (East Sea), Basculin (Blue-Striped Form), Galarian Darumaka, Galarian Darmanitan, Galarian Darmanitan (Zen Mode), Deerling (Summer Form), Deerling (Autumn Form), Deerling (Winter Form), Sawsbuck (Summer Form), Sawsbuck (Autumn Form), Sawsbuck (Winter Form), Keldeo (Resolute Form), Vivillon (Polar Pattern), Vivillon (Tundra Pattern), Vivillon (Continental Pattern), Vivillon (Garden Pattern), Vivillon (Elegant Pattern), Vivillon (Meadow Pattern), Vivillon (Modern Pattern), Vivillon (Marine Pattern), Vivillon (Archipelago Pattern), Vivillon (High Plains Pattern), Vivillon (Sandstorm Pattern), Vivillon (River Pattern), Vivillon (Monsoon Pattern), Vivillon (Savanna Pattern), Vivillon (Sun Pattern), Vivillon (Ocean Pattern), Vivillon (Jungle Pattern), Vivillon (Fancy Pattern), Vivillon (Poké Ball Pattern), Flabébé (Yellow Flower), Flabébé (Orange Flower), Flabébé (Blue Flower), Flabébé (White Flower), Floette (Yellow Flower), Floette (Orange Flower), Floette (Blue Flower), Floette (White Flower), Florges (Yellow Flower), Florges (Orange Flower), Florges (Blue Flower), Florges (White Flower), Furfrou (Heart Trim), Furfrou (Star Trim), Furfrou (Diamond Trim), Furfrou (Debutante Trim), Furfrou (Matron Trim), Furfrou (Dandy Trim), Furfrou (La Reine Trim), Furfrou (Kabuki Trim), Furfrou (Pharaoh Trim), Toxtricity (Low Key Form), Alcremie (form 7), Alcremie (form 8), Alcremie (form 9), Alcremie (form 10), Alcremie (form 11), Alcremie (form 12), Alcremie (form 13), Alcremie (form 14), Alcremie (form 15), Alcremie (form 16), Alcremie (form 17), Alcremie (form 18), Alcremie (form 19), Alcremie (form 20), Alcremie (form 21), Alcremie (form 22), Alcremie (form 23), Alcremie (form 24), Alcremie (form 25), Alcremie (form 26), Alcremie (form 27), Alcremie (form 28), Alcremie (form 29), Alcremie (form 30), Alcremie (form 31), Alcremie (form 32), Alcremie (form 33), Alcremie (form 34), Alcremie (form 35), Alcremie (form 36), Alcremie (form 37), Alcremie (form 38), Alcremie (form 39), Alcremie (form 40), Alcremie (form 41), Alcremie (form 42), Alcremie (form 43), Alcremie (form 44), Alcremie (form 45), Alcremie (form 46), Alcremie (form 47), Alcremie (form 48), Alcremie (form 49), Alcremie (form 50), Alcremie (form 51), Alcremie (form 52), Alcremie (form 53), Alcremie (form 54), Alcremie (form 55), Alcremie (form 56), Alcremie (form 57), Alcremie (form 58), Alcremie (form 59), Alcremie (form 60), Alcremie (form 61), Alcremie (form 62), Hisuian Voltorb, Hisuian Electrode, Paldean Tauros (Combat Breed), Paldean Tauros (Blaze Breed), Paldean Tauros (Aqua Breed), Hisuian Typhlosion, Dialga (Origin Forme), Palkia (Origin Forme), Hisuian Samurott, Basculin (White-Striped Form), Hisuian Zorua, Hisuian Zoroark, Hisuian Braviary, Hisuian Sliggoo, Hisuian Goodra, Hisuian Avalugg, Hisuian Decidueye, Ursaluna (Bloodmoon), Basculegion (female), Dudunsparce (Three-Segment Form), Maushold (Family of Three), Pikachu (form 8), Pikachu (form 9), Pikachu (form 10), Pikachu (form 11), Pikachu (form 12), Pikachu (form 13), Pikachu (form 14), Pikachu (form 15)
- **Its base Pokémon is not in the game.** (88): Tornadus (Therian Forme), Thundurus (Therian Forme), Landorus (Therian Forme), White Kyurem, Black Kyurem, Kyurem (form 3), Kyurem (form 4), Meowstic (female), Xerneas (Active Mode), Zygarde (10% Forme), Zygarde (Complete Forme), Zygarde (Complete Forme), Oricorio (Pom-Pom Style), Oricorio (Pa’u Style), Oricorio (Sensu Style), Wishiwashi (School Form), Silvally (Fighting type), Silvally (Flying type), Silvally (Poison type), Silvally (Ground type), Silvally (Rock type), Silvally (Bug type), Silvally (Ghost type), Silvally (Steel type), Silvally (Fire type), Silvally (Water type), Silvally (Grass type), Silvally (Electric type), Silvally (Psychic type), Silvally (Ice type), Silvally (Dragon type), Silvally (Dark type), Silvally (Fairy type), Minior (Red Core), Minior (Orange Core), Minior (Yellow Core), Minior (Green Core), Minior (Blue Core), Minior (Indigo Core), Minior (Violet Core), Dusk Mane Necrozma, Dawn Wings Necrozma, Ultra Necrozma, Ultra Necrozma, Magearna (Original Color), Cramorant (Gulping Form), Cramorant (Gorging Form), Eiscue (Noice Face), Indeedee (female), Morpeko (Hangry Mode), Zacian (Crowned Sword), Zamazenta (Crowned Shield), Urshifu (Rapid Strike Style), Ice Rider Calyrex, Shadow Rider Calyrex, Enamorus (Therian Forme), Oinkologne (female), Palafin (Hero Form), Tatsugiri (Droopy Form), Tatsugiri (Stretchy Form), Squawkabilly (Blue Plumage), Squawkabilly (Yellow Plumage), Squawkabilly (White Plumage), Gimmighoul (Roaming Form), Ogerpon (Wellspring Mask), Ogerpon (Hearthflame Mask), Ogerpon (Cornerstone Mask), Ogerpon (form 4), Ogerpon (form 5), Ogerpon (form 6), Ogerpon (form 7), Ogerpon (form 8), Ogerpon (form 9), Ogerpon (form 10), Ogerpon (form 11), Terapagos (Terastal Form), Terapagos (Stellar Form), Gigantamax Melmetal, Gigantamax Rillaboom, Gigantamax Cinderace, Gigantamax Inteleon, Gigantamax Corviknight, Gigantamax Sandaconda, Gigantamax Copperajah, Gigantamax Duraludon, Eternamax Eternatus, Gigantamax Urshifu (Single Strike Style), Gigantamax Urshifu (Rapid Strike Style)
- **Its Mega Stone is not in the game. Charizardite is the only Mega Stone.** (45): Mega Venusaur, Mega Blastoise, Mega Beedrill, Mega Pidgeot, Mega Alakazam, Mega Slowbro, Mega Gengar, Mega Kangaskhan, Mega Pinsir, Mega Gyarados, Mega Aerodactyl, Mega Mewtwo X, Mega Mewtwo Y, Mega Ampharos, Mega Steelix, Mega Scizor, Mega Heracross, Mega Houndoom, Mega Tyranitar, Mega Sceptile, Mega Blaziken, Mega Swampert, Mega Gardevoir, Mega Sableye, Mega Mawile, Mega Aggron, Mega Medicham, Mega Manectric, Mega Sharpedo, Mega Camerupt, Mega Altaria, Mega Banette, Mega Absol, Mega Glalie, Mega Salamence, Mega Metagross, Mega Latias, Mega Latios, Mega Rayquaza, Mega Lopunny, Mega Garchomp, Mega Lucario, Mega Abomasnow, Mega Gallade, Mega Audino
- **The game has no Dynamax.** (24): Gigantamax Venusaur, Gigantamax Charizard, Gigantamax Blastoise, Gigantamax Butterfree, Gigantamax Pikachu, Gigantamax Meowth, Gigantamax Machamp, Gigantamax Gengar, Gigantamax Kingler, Gigantamax Lapras, Gigantamax Eevee, Gigantamax Snorlax, Gigantamax Garbodor, Gigantamax Orbeetle, Gigantamax Drednaw, Gigantamax Coalossal, Gigantamax Flapple, Gigantamax Appletun, Gigantamax Toxtricity, Gigantamax Toxtricity (Low Key Form), Gigantamax Centiskorch, Gigantamax Hatterene, Gigantamax Grimmsnarl, Gigantamax Alcremie
- **The game has no Primal Reversion.** (2): Primal Kyogre, Primal Groudon
- **Its only entry (Lake of Rage, April 16) replaces a grass slot on a map with no grass encounters, so it never appears.** (1): Volcanion
- **The Gracidea only works on an event Shaymin, and the game's only Shaymin (Forest of Time) isn't one.** (1): Shaymin (Sky Forme)
- **There's no Pixie Plate in the game, and Arceus's form code has no Fairy case.** (1): Arceus (Fairy type)
- **Only by breeding Runerigus, which is not in the game.** (1): Galarian Yamask
- **Stunfisk is only in its normal form (Pal Park).** (1): Galarian Stunfisk
- **No Pokémon can learn Relic Song, so Meloetta never changes form.** (1): Meloetta (Pirouette Forme)
- **Diancie's calendar encounter loads as a normal Diancie; nothing produces Mega Diancie.** (1): Mega Diancie
- **Only by breeding Clodsire, which is not in the game.** (1): Paldean Wooper

## Open

- Emulator checks worth doing: Hisuian Lilligant route, Pal Park Friday Stunfisk, daytime Lycanroc form, Unown letters.
- The guide has no section on Pal Park's Fixed Catch mode.

## Follow-up changes (2026-10-05, later)

- **Pal Park weekday tables in the docs and site.** `gen_docs.py` `ENC_WEEKDAY` replaces map 109's single record with
  the seven weekday records (142 + weekday − 1); the encounters page, the location page (one block per day plus a note)
  and the Pokémon "how to get it" text (e.g. "Pal Park, Fixed Catch mode (Fridays)") use them. Stunfisk's hand-written
  source was dropped from `extra_sources.json` because the generated one now covers it.
- **Runtime-species gifts.** `romdata.index_scripts` now resolves every constant a variable species can hold for
  GiveMon, GiveEgg and WildBattle (`alt0`), so Oak's starters (Bulbasaur, Charmander, Pikachu) and the Game Corner prizes
  (Celadon: Eevee, Mr. Mime, Porygon; Goldenrod: Abra, Dratini, Ekans, Sandshrew) are listed as gifts.
- **Guide:** new section "Resort Zone: the Pal Park's Fixed Catch mode" (04-celadon-fuchsia-saffron.md) with the
  entry rules ($10,000, six free PC slots, no GBA Pokémon stocked) and the 8 groups of 6 standing Pokémon (file 12,
  scripts 7–54, hide flags 2124–2131), two groups per weekday. Monday's pair depends on a saved-clock field
  (ScrCmd_522 → 0x0205475C, field +0x14) compared with 7–18; probably the hour, not confirmed.
- **Not done:** emulator tests. No battery save is near Pal Park, Ice Path, the Ruins of Alph or a Petilil; all four
  open points were confirmed by two independent static passes and are labelled "not tested in game" on the site.

## Items (2026-10-05)

262 items had no source on the site. One agent classified them; an independent recheck agreed with 261 and moved
Nanab Berry from absent to unsure. Result:

- **187 never obtainable**, listed in `work/tools/site/items_not_in_game.json` and left out by the exporter: the five
  Mail (only in Mart lists 4/16/19/24–26, which no clerk opens; D-1343), TM46 Thief and Grip Claw (unplaced item balls;
  D-1339, D-1494), S.S. Ticket (D-1492), Oval Charm, Photo Album, Apicot/Lansat and other berries, the Scarves, Sinnoh
  and hack key items, and every remaining Gen 5+ item. Checked against every script give/take, item balls, hidden
  items, every reachable Mart list, held items of obtainable Pokémon, trainer items, Pickup, Rock Smash, Bug Contest
  prizes, scratch-off cards, Athlete Shop (all 14 lists), phone gifts (`tel/pmtel_book.dat` +12), Mom's tables, Kurt,
  Pal Park prizes, Spin Trade, Primo passwords and all 26 bag-add call sites. There are no berry trees or soil; the
  only trees are the 37 Apricorn trees.
- **58 got verified sources** in `work/tools/site/items_extra_sources.json`: Battle Frontier Scratch-Off Cards (Qualot,
  Tamato, Occa–Chilan; ov84 0x021E736C), Mom's random berry purchases (Occa–Chilan ×5; arm9 0x02092874, table
  0x02106F8C), Chilan from wild Rattata/Raticate, Pickup (Pearl String, Comet Shard, Big Nugget, Bottle Cap, Gold Bottle
  Cap; ov14 0x0222BD26), the 7 Apricorns (trees, std 2800; Athlete Shop, ScrCmd 771) and Data Cards 01–27
  (ScrCmd 772). The charms, Chain Logger and EV Allocator were already sourced by `verified-mechanics.ts`.
- **12 kept with a note** (hidden by default): Air Balloon, Eviolite (584), Weakness Policy, Salac, Petaya (only on
  trainers' Pokémon; keeping a stolen item is unconfirmed), Nanab (maybe a Pal Park prize; unconfirmed) and the six
  Spin Trade berries (wireless play with other people only).
- **Knock-on:** item evolutions now count only if the item can be obtained (`gen_docs.evo_works`, methods 6, 7, 16–19,
  37). This removed Flapple, Appletun and Alcremie (D-1493), and Pokémon pages mark such evolutions "not possible in
  this game: needs a … which can't be obtained". Guide examples that used Flapple/Appletun were updated.

## Review fixes (2026-10-05)

An independent high-effort review found these, now fixed:
- **Wormadam (Trash Cloak) restored.** A corrected trainer parser (form read from byte 2) shows four placed trainers use
  it (parties 129, 174, 562, 835). Test `TestSiteLists` in `test_gen_docs.py` now fails if a placed trainer's Pokémon or
  held item is on a removal list.
- **Arceus Plates (D-1501).** The Plate routine writes Gen 4 type numbers as the form, but the form table uses the
  newer order, so seven Plates store another type's form and the Dread Plate stores the Fairy entry. The form-change list
  now shows what each Plate really produces; the Fairy entry is back and the Fire entry (never produced) is removed.
- **Evolutions:** blocked evolutions stay visible ("not possible in this game: the item it needs … can't be obtained"),
  including targets that have no page (Applin → Flapple/Appletun, Milcery → Alcremie). Petilil's Black Belt evolution
  is marked not possible via `evoBlocked` in `extra_sources.json`. New notes on Rockruff, Lycanroc and Darumaka.
- Stunfisk added to the gym species-list examples; Pal Park's Sunday table no longer shows Rock Smash (the park has no
  rocks; `gen_docs.ENC_MAP_LACKS`); guide wording for the one-time $10,000 fee; TM46 marked "can't be obtained" in the
  TM tables; new known issue "Things you can't get, although the game has them"; stale intro text, Oval Charm hedge,
  duplicate-name item notes, Pal Park region, guide index counts and D-1492's item id fixed.
- Lists now: 578 Pokémon/forms and 187 items never met in normal play. The hack's built-in Pokémon generator
  (SELECT + X, see the FAQ) can create anything; "never met" always means in normal play.
- Not done (another agent owns the file): `TrainerCard.astro` links held items by name, so duplicate-name items
  (Air Balloon 252/576, Eviolite 110/584, Weakness Policy 111/600, Rocky Helmet 324/590) should link by id.

## Emulator results (2026-10-05, harness branch worktree-agent-a4b139276ed03996d)

- D-1487 Unown: 65 wild Unown on the CN ROM, 9 on the EN WIP, all A. Site says "tested in an emulator".
- D-1484 Pal Park: map 109 loads record 141 (Sun) … 147 (Sat). Per-day encounters not sampled.
- D-1485 Petilil: Black Belt by day → Petilil form 1 ("Petilil evolved into Petilil"); Sun Stone → Hisuian Lilligant.
- D-1486 Rockruff: Rare Candy evolutions gave Midday in the day (9/9), Dusk at 18:00, Midnight at 22:00/02:00.
- D-1501 Arceus: stored forms are as predicted, but the summary shows the Plate's type and colours for all 16 Plates.
  The site's form-change list went back to the visible types: Fire form restored, Fairy form removed again, and the
  known-issues bullet dropped.
- Screens (EN WIP): options, EV screen, Pokédex letter grid fit (D-0503/0506/0520 resolved); new layout issues
  D-1504 (info panel "Harsh Sunlight 5 turns" cut), D-1505 (garbled Pokédex search button bar), D-1506 (FIGHT under
  the Pokémon icon).
