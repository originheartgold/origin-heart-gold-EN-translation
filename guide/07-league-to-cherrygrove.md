# Pokémon League, Mt. Silver and New Bark Town

[← Guide index](README.md)

**Quests on this page:**

- [Cerulean Cave: Giovanni's duel and the Charizardite](#cerulean-cave-giovannis-duel-and-the-charizardite)
- [Mt. Silver lodge: the rehabilitation (how to move it along)](#mt-silver-lodge-the-rehabilitation-how-to-move-it-along)
- [New Bark Town Guesthouse: the Sinnoh traveller's quiz (→ Shinx)](#new-bark-town-guesthouse-the-sinnoh-travellers-quiz--shinx)
- [Route 29: Casey's Pokéathlon question (→ Electirizer)](#route-29-caseys-pokéathlon-question--electirizer)
- [Route 29: Uncle Apricorn wants Kurt's Apricorn Box (say No twice)](#route-29-uncle-apricorn-wants-kurts-apricorn-box-say-no-twice)
- [Cherrygrove City: the Berry Pots girl (→ 6 PP Up; one chance)](#cherrygrove-city-the-berry-pots-girl--6-pp-up-one-chance)
- [Cherrygrove City: the Wooper and the lost Poké Ball (→ Focus Band)](#cherrygrove-city-the-wooper-and-the-lost-poké-ball--focus-band)
- [Route 27 → Ecruteak City: the outpost guard's letter to Momo (before the Mineral Badge)](#route-27--ecruteak-city-the-outpost-guards-letter-to-momo-before-the-mineral-badge)
- [Route 27: the musician's song or battle (→ Soothe Bell)](#route-27-the-musicians-song-or-battle--soothe-bell)
- [Route 26: the Phanpy trainer's Nugget (sell for $30,000 or give for TM41)](#route-26-the-phanpy-trainers-nugget-sell-for-30000-or-give-for-tm41)
- [Route 26: the item quiz in the weekday siblings' house (→ TM43)](#route-26-the-item-quiz-in-the-weekday-siblings-house--tm43)
- [Route 26: the old man's paid rest (unlocks Focus Sash sales)](#route-26-the-old-mans-paid-rest-unlocks-focus-sash-sales)
- [Tohjo Falls: the hermit in the hidden room (→ TM52)](#tohjo-falls-the-hermit-in-the-hidden-room--tm52)
- [New Bark Town: show Prof. Elm all eight Johto Badges (→ Rare Candy, PP Max)](#new-bark-town-show-prof-elm-all-eight-johto-badges--rare-candy-pp-max)
- [League HQ: the Trainer Affairs Department's investigations (where to go next)](#league-hq-the-trainer-affairs-departments-investigations-where-to-go-next)
- [Mt. Silver: the Turtwig owner's four-leaf clover](#mt-silver-the-turtwig-owners-four-leaf-clover)
- [Indigo Plateau (final chapter): Mewtwo joins you (take it before the Elite Four)](#indigo-plateau-final-chapter-mewtwo-joins-you-take-it-before-the-elite-four)
- [Indigo Plateau slope (final chapter): Steven's and Cynthia's confessions](#indigo-plateau-slope-final-chapter-stevens-and-cynthias-confessions)
- [Pokémon League (final chapter): the Elite Four rooms under Team Rocket](#pokémon-league-final-chapter-the-elite-four-rooms-under-team-rocket)
- [The Hall of Fame: what your two entries unlock](#the-hall-of-fame-what-your-two-entries-unlock)
- [League gate, Mt. Silver, Route 29 and Cherrygrove: small extras](#league-gate-mt-silver-route-29-and-cherrygrove-small-extras)

## Cerulean Cave: Giovanni's duel and the Charizardite

**Where:** Cerulean Cave, the hidden hall deep inside, after Nurse Joy's invitation letter.

**Who gets it / when:** after your first Hall of Fame (Giovanni congratulates you on becoming Champion). This is a story scene for every player. Only the Charizardite is restricted: it only happens if you **chose Charmander** in Oak's lab **and** still carry Mr. Fuji's **Mystery Stone** ([Lavender Town: Mr. Fuji's gifts](03-vermilion-to-celadon.md#lavender-town-mr-fujis-gifts-after-the-tower); don't sell it to the [Four Island buyer](06-sevii-islands-indigo.md#four-island-the-mystery-stone-buyer-dont-sell-it)).

**How it works:**
1. Giovanni battles you with his full **Lv. 100** team (Mewtwo, Tyranitar, Nidoking, Rhydon, Nidoqueen, Aerodactyl). Losing doesn't white you out. If you **win**, Mewtwo uses Recover and the same battle starts again, as often as you keep winning. The duel only moves on once you lose.
2. You wake up "at the bottom of the lake". With Charmander and the Mystery Stone, the stone reacts: it becomes a **Charizardite**. Without either, the scene just continues.
3. Rematch: a Double Battle against Giovanni's team, sent out two at a time; he opens with Mewtwo and Tyranitar (tested in an emulator). **A loss here whites you out.** Giovanni stays, but to retry you have to talk to him again and replay the whole scene: the duel, the collapse and the lake.
4. After the win you free Mewtwo and Giovanni escapes. You wake up at home, and Prof. Oak sends you to Mt. Silver (the rehabilitation below).
**Reward:** Charizardite (Charmander starters with the Mystery Stone only).

**Notes:** the [Dragon Shrine](12-lake-of-rage-to-sinjoh.md#dragon-shrine-the-mystery-stone-becomes-a-charizardite-and-the-dragon-rush-tutor) in Johto's Dragon's Den can also turn the Mystery Stone into a Charizardite. It works for any starter; only this cave scene checks for Charmander.

*Source:* script file 912 (L4818/L4922 `TrainerBattle 402` no-loss; a win jumps to L4855, Recover, and repeats the battle; a loss goes on at L4953; L5414 `CheckFlag 1287`, L5425 `HasItem 504`, L5497–L5517 gives item 325; L2559 double battle 402+402 (same id twice = a Double Battle against one trainer, one copy of the team; trainer 402 opens with Mewtwo and Tyranitar), a loss → L4849 `WhiteOut`; the rematch trigger at 45,5 can only be reached from the lake-bottom scene), file 112 L1201 (Dragon's Den, no starter check). Emulator (`emu_harness.py guide0107 --case giovanni`): `TrainerBattle 402 402 0 0` is a double battle, send-out cries 150 then 248, one team (150, 248, 34, 112, 31, 142) in RAM.

## Mt. Silver lodge: the rehabilitation (how to move it along)

**Where:** the hot-spring lodge on Mt. Silver and the hot spring just outside it. From the Mt. Silver Cave entrance, go west, then north (as the guard there tells you) to the exit in the cave's north-west corner. Outside, the lodge door is about 30 steps north; the hot spring is about ten steps west of the lodge door.

**Who gets it / when:** story, right after the Cerulean Cave duel. You can't go to Johto until it's done.

**How it works:** Sabrina runs a loop. Each round is **talk to Sabrina → battle → examine the hot spring → you rest a while → talk to Sabrina again**.
1. Talk to Sabrina. She tells you to try the hot spring first. Examine the spring (the game puts your walking Pokémon away first). This first soak moves the story on.
2. Round 1: **Brock**, then soak. Round 2: **Misty**, then soak. Round 3: **Blue**, then soak. Round 4: **Sabrina** herself, and in the same visit **Yellow** walks in and battles you straight away (no soak in between); she finishes the cure.
3. After each battle, Sabrina says "go soak in the hot spring". Until you do, she just repeats that line. Soaking puts you back in the lodge, having rested "a while longer", for the next round.
4. After Yellow, soak once more. Sabrina joins you in the spring, then you go home to Pallet Town.

Every loss whites you out. Talk to Sabrina to retry the round; losing to Yellow means redoing Sabrina's battle too.
**Reward:** the story continues (next: deliver the Pokédex to Prof. Elm in New Bark Town).

**Notes:** every soak fully heals your party. You can soak as often as you like; only the first soak after each battle moves the story on.

*Source:* script files 846 (lodge; L1579–L3288, var 0x4110 1→6, flag 609 "go soak"; trainers 994 Brock, 995 Misty, 261 Blue, 996 Sabrina, then 161 Yellow at L3024 in the same visit; L2648 `WhiteOut`), 844 (hot spring bg 39/40,25, lodge door ≈49,22; L1727–L3250; "a while longer" is message 539#13), 105 (cave entrance guard, flag 1501).

## New Bark Town Guesthouse: the Sinnoh traveller's quiz (→ Shinx)

**Where:** the New Bark Town Guesthouse, beside the reception desk: a woman with a Luxray, a few steps up and to the right of the entrance.

**Who gets it / when:** from your first visit to New Bark Town onward, including after the final Hall of Fame.

**How it works:** three questions about the Pokémon next to her. One wrong answer ends the round; talk to her again to retry.

| Question | Answer |
|---|---|
| What is this Pokémon? | **Luxray** |
| What type is it? | **Electric** |
| What special power does it have, according to the Pokédex? | **Sees through things** |

Then accept her offer.
**Reward:** **Shinx (Lv. 5).** You need a free party slot. If yours is full, she tells you to come back, and the offer stays open.

**Notes:** after the gift she only mentions heading for the Indigo Plateau.

*Source:* script file 841 (script 12, L903, L2395–L2715; flags 1833, 1961; `GiveMon 403, Lv. 5`). Woman ≈134,7 (guesthouse entrance ≈131,10, New Bark Town door ≈690,407).

## Route 29: Casey's Pokéathlon question (→ Electirizer)

**Where:** Route 29, a girl with an Elekid, about 20 steps south of the gatehouse to Route 46.

**How it works:** she asks whether you admire a Pokéathlon athlete who never gave up.

| Answer | Result |
|---|---|
| "Yes! Never giving up is admirable!" | a friendly battle (Elekid and Beedrill, Lv. 11–12); win or lose, she gives you an **Electirizer**. Losing doesn't white you out. |
| "Losers should just give up early." | a normal battle (a loss whites you out). She runs off crying; follow her west to the Apricorn tree, where she stands a few steps east of Uncle Apricorn, for a Double Battle. **No item.** |

**Reward:** Electirizer (the "Yes" answer only).

**Notes:** one chance: either answer ends it.

*Source:* script file 225 (script 3, L1253, L4128–L4166: `TrainerBattle [608, 0, 1, 0]` @4135 with no win check, then item 322 @4148; script 14 and L1324–L1408; flags 1962, 1969, 1970). Casey ≈624,409 (gatehouse door ≈626,389); after running off ≈590,392.

## Route 29: Uncle Apricorn wants Kurt's Apricorn Box (say No twice)

**Where:** Route 29, the man by the Apricorn tree, west of the Route 46 gatehouse.

**Who gets it / when:** any time. You carry Kurt's Apricorn Box from Oak's Parcel (Pallet Town).

**How it works:** he wants to buy Kurt's box and raises his offer each time you refuse:

| Offer | If you say Yes |
|---|---|
| 1st | $5,000 + one of his Apricorn Boxes |
| 2nd (after one No) | $10,000 + his box |
| 3rd (after two No's) | **$20,000 + his box + an Apricorn Ball set: 2 each of Fast, Level, Lure, Heavy, Love, Friend and Moon Ball** |
| No three times | you keep Kurt's box, no reward |

**Reward:** best is No, No, Yes: $20,000 and 14 Apricorn Balls.

**Notes:** you lose nothing by selling: his box is the same key item, so Apricorn picking still works. One chance either way.

*Source:* script file 225 (script 15, L3690/L3735/L3780–L3938; flag 1971; items 468, 492–498). Uncle Apricorn ≈599,393.

## Cherrygrove City: the Berry Pots girl (→ 6 PP Up; one chance)

**Where:** Cherrygrove City, a girl among the flowers at the south-east edge, a few steps south-west of the south-east house door.

**Who gets it / when:** when you carry the Squirt Bottle. She only checks for the Squirt Bottle, not the Berry Pots, but in normal play you get both together (Anemone's flower garden in Pewter City, see [Pewter City: Sitrus Berries → Hard Stone → TM69](01-pallet-to-pewter.md#pewter-city-sitrus-berries--hard-stone--tm69)). Without the Squirt Bottle she only talks about Berries.

**How it works:** she asks you to give her your Berry Pots.
- **Yes:** she takes the Berry Pots and gives you **6 PP Up**.
- **No:** she gives up for good. **One chance.**
**Reward:** 6 PP Up. You lose the Berry Pots, but you can buy them again at the Goldenrod Flower Shop for $5,000.

*Source:* script file 847 (script 15, L3585, L6837–L6868; flag 1972, also set by "No" at L3628; `HasItem 477` (Squirt Bottle) is the only check, `TakeItem 470`); Flower Shop: file 893. Girl ≈561,408 (house door ≈567,405).

## Cherrygrove City: the Wooper and the lost Poké Ball (→ Focus Band)

**Where:** Cherrygrove City's west shore: a boy, and about ten steps west of him on the water, a Poké Ball surrounded by Wooper and Quagsire.

**How it works:**
1. Talk to the boy: the Wooper snatched his Poké Ball (his Buizel is inside).
2. Examine the Poké Ball → "Take it back to the boy?" → Yes. The Wooper won't let you:

| Choice | Result |
|---|---|
| **Take it by force** | a local explains the Wooper ritual and offers "Wait for the ritual to end" / "**Take the Ball back now**". Taking it: beat him (**Fisherman Marcus**, Lv. 62–65), then the Quagsire (Lv. 40) and two Wooper (Lv. 20). Losing either battle whites you out; you can try again. You get the ball back, and the boy gives you a **Focus Band**. |
| Leave it alone / Wait for the ritual to end | nothing now. The boy gets his Buizel back later in the story (the Ruins of Alph chapter). **No reward.** |
| Trade an empty Ball | needs a Poké Ball; the Wooper aren't interested. Nothing is lost; you can choose again. |
| Let me think | nothing happens; you can choose again. |

**Reward:** Focus Band (the forceful path only).

**Notes:** after "Leave it alone" or "Wait for the ritual to end", the ball can't be taken any more. If you want the Focus Band, choose "Take it by force", then "Take the Ball back now".

*Source:* script file 847 (scripts 17, 18; L6876, L7621–L7841, L8181–L8573; `TrainerBattle 665`, `666`; flags 1973, 1974, 1975, 1978), file 51 L4285–L4318 (Ruins of Alph clears them). Boy ≈537,404; Poké Ball ≈527,407.

## Route 27 → Ecruteak City: the outpost guard's letter to Momo (before the Mineral Badge)

**Where:** the guard post house on Route 27, just south of the two Tohjo Falls entrances (guard Yuichi); Momo is one of the Kimono Girls at the Ecruteak Dance Theater.

**Who gets it / when:** getting the letter and handing it to Momo must happen before you earn the **Mineral Badge** (Olivine). If she doesn't have it by then, Yuichi only sighs about a love he never confessed, and Momo only mourns.

**How it works:**
1. Talk to the guard. "Headed to Johto?" → Yes. Agree to carry his letter: you get the **Guard Letter**.
2. Give it to **Momo** at the Ecruteak Dance Theater. She takes it, gives you a **Heart Scale**, and leaves to meet him.
3. Back at the Route 27 house, Momo is with Yuichi. Talk to him.
**Reward:** Heart Scale (Momo) and a **Lum Berry** (Yuichi).

**Notes:** get the letter and give it to Momo before you beat the Olivine Gym; after that, an undelivered letter can't be delivered. Once Momo has it, Yuichi's Lum Berry can be collected any time, even after the badge. (One caveat: the Route 37 scene with Silver resets Momo's "letter received" state. If that scene came after the delivery and before you collected the Lum Berry, the berry would be lost. In normal routing the Route 37 scene comes first.)

*Source:* script file 222 (script 2; `CheckBadge 13`, but with the badge L283 still checks flags 583/576 and gives the berry; L212–L281 gives item 452; L170 item 157; flags 576, 583), file 924 (Momo: `CheckBadge 13`, L3757–L4707 `TakeItem 452`, item 93, sets 576, clears 599). Flag 576 is cleared again by the Route 37 Silver scene.

## Route 27: the musician's song or battle (→ Soothe Bell)

**Where:** Route 27, a musician about 40 steps east of the guard post house (towards New Bark Town).

**How it works:** "Are you here to hear me play a song?" Yes plays a tune. **No** starts a battle against **Guitarist Shawn** (Lv. 62–65; a loss whites you out); win the first time for a **Soothe Bell**. Repeatable battle afterwards, no further item.

*Source:* script file 221 (script 7; `TrainerBattle 12`; item 218; flag 1042). Musician ≈790,407 (guard post door ≈751,400).

## Route 26: the Phanpy trainer's Nugget (sell for $30,000 or give for TM41)

**Where:** Route 26, a man next to his Phanpy, about 10 steps south and 10 steps east of the weekday siblings' house door.

**Who gets it / when:** carry a **Nugget**.

**How it works:** he wants a Nugget to train his Phanpy's treasure-sniffing:

| Choice | Result |
|---|---|
| "Sure, I'll sell it to you" | **$30,000** |
| "You want it that much? Have it" | **TM41 Torment**. He never actually takes the Nugget: you keep it |
| "Let me think about it" | nothing; ask again later |

**Notes:** one trade only.

*Source:* script file 218 (script 7, L930, L1522–L1580; flag 1111; item 368; only the "sell" branch L1535 has `TakeItem 92`, the "have it" branch L1551 doesn't (hack finding)). Phanpy man ≈917,375 (siblings' house door ≈907,365).

## Route 26: the item quiz in the weekday siblings' house (→ TM43)

**Where:** the house on Route 26 where the weekday siblings' mother lives (the notebook on the table lists which sibling stands where on each day).

**How it works:** five questions; she tells you only at the end whether you got any wrong. Retry as often as you like.

| Question | Answer |
|---|---|
| Held item that boosts a Guts Pokémon's damage most? | **Flame Orb** |
| Which item is single-use? | **Weakness Policy** |
| Which item makes a move's effect last more turns? | **Light Clay** |
| Which item does Stealth Rock affect the most? | **Focus Sash** |
| Which item has no effect in battle? | **Soothe Bell** |

**Reward:** **TM43 Secret Power** (once).

*Source:* script file 220 (script 2, L145–L1030; flag 1112; item 370).

## Route 26: the old man's paid rest (unlocks Focus Sash sales)

**Where:** the house at the north end of Route 26.

**How it works:** he charges **$2,000** to rest (full heal). After your first paid rest he offers to sell **Focus Sashes at $500 each** (1, 5, 10 or 20). From then on he offers the sashes or a rest each time you talk to him.

**Notes:** his lines also mention a Weakness Policy, but that branch can't be reached in normal play.

*Source:* script file 219 (L162–L240 flag 1110; L333, L617, L695–L1309; item 275).

## Tohjo Falls: the hermit in the hidden room (→ TM52)

**Where:** the hidden room in Tohjo Falls (Surf/Waterfall): its cave door is about 11 steps north and 3 steps west of the western entrance from Route 27. Inside, a Black Belt with a Hitmontop.

**How it works:** accept his battle: **Black Belt Bruce** (Hitmontop, Hitmonchan, Machamp, Lucario, Heracross, Hariyama, Lv. 81–82). A loss whites you out.

**Reward:** **TM52 Focus Blast** the first time. Rematches any time, no further item.

*Source:* script file 114 (script 5, L883–L951; `TrainerBattle 275`; item 379; flag 1635).

## New Bark Town: show Prof. Elm all eight Johto Badges (→ Rare Candy, PP Max)

**Where:** Prof. Elm in his lab.

**How it works:** talk to him once you have all eight Johto Badges (Zephyr to Rising). He praises your progress. With some but not all of them, he tells you to come back with all eight for a present; with none, he only asks how your journey is going.

**Reward:** **5 Rare Candy and 5 PP Max** (once).

*Source:* script file 840 (script 1 → L2729–L2934; `CheckBadge 8`–`15`; flag 220; items 50, 53; missing badge → L3401, message 535#33 "come see me once you've collected all eight"; 535#32 is the no-badge line).

## League HQ: the Trainer Affairs Department's investigations (where to go next)

**Where:** the Pokémon League administration hall at the Indigo Plateau, the Trainer Affairs Department: walk straight north from its signs by the hall entrance to the desk at the back.

**Who gets it / when:** after the Silver Conference, when President Goodshow tells you to go there. This is the main post-Silver-Conference story; the desk tells you where to go, and you must come back to report after finishing **every** lead of a round.

| Round | Leads the desk gives you |
|---|---|
| 1 | suspicious people at the **[Power Plant](03-vermilion-to-celadon.md#power-plant-zapdos-and-the-ecologist)** (then [Cinnabar Island](05-saffron-cinnabar.md#cinnabar-island-lawrence-and-moltres-league-hq-investigation-and-catching-moltres)); a secret group in **[Rock Tunnel](03-vermilion-to-celadon.md#rock-tunnel-regirock-regice-and-registeel-league-hq-investigation)** |
| 2 | suspicious people at the **Pewter Museum** exhibition; strangers at the **Cerulean Gym** water ballet (continues at the [Seafoam Islands](05-saffron-cinnabar.md#seafoam-islands-team-rocket-and-kyogre-league-hq-investigation-and-catching-kyogre)) |
| 3 | check the **[Jade Orb at the Violet Gym](08-cherrygrove-to-azalea.md#violet-city-the-stolen-trophy-and-the-jade-orb-league-hq-round-3)**; legendary tracks near **New Bark Town and Cherrygrove City** (ask Gold and Crystal); people in black in **[Ilex Forest](09-ilex-goldenrod.md#ilex-forest--forest-of-time-sammy-and-the-injured-celebi-league-hq-round-3)**; ghostly rumours at **[MooMoo Farm (Route 39)](10-ecruteak-olivine.md#moomoo-farm-the-sick-miltank-investigation-from-your-first-visit-leads-to-the-dream-world)** |
| 4 | **[Bell Tower](10-ecruteak-olivine.md#bell-tower-ho-oh-is-stolen-league-hq-round-4-continues-pokémon-league-mt-silver-and-new-bark-towns-league-hq-entry)** (Ecruteak) and **Whirl Islands** (Ho-Oh, Lugia); bring the orb from **Dark Cave** back to HQ; check the **[Lake of Rage](12-lake-of-rage-to-sinjoh.md#lake-of-rage-petrel-at-the-lake-guardians-house-league-hq-round-4-continues-pokémon-league-mt-silver-and-new-bark-towns-league-hq-entry)** |

After round 4, Goodshow sends you to the Alto Mare Islands: sign up for the Island Pilgrimage on Seven Island as cover ([Seven Island: the Island Pilgrimage](06-sevii-islands-indigo.md#seven-island-the-island-pilgrimage-start-and-final-trial)). The pilgrimage ends at the [Ritual Shrine](06-sevii-islands-indigo.md#ritual-shrine-seven-island-giovanni-takes-the-azure-flute), and the trail leads on to the [Ruins of Alph](08-cherrygrove-to-azalea.md#ruins-of-alph-giovanni-catches-arceus-league-hq-lead).
**Notes:** if a report is incomplete, the desk just repeats the current leads. In round 3 the New Bark scene has Gold and you fight Cassidy and Butch in a Multi Battle before Raikou picks Gold as its Trainer; in Cherrygrove, Suicune picks Crystal after her duel with Eusine.

*Source:* desk ≈57,5 (Trainer Affairs signs ≈57,21 and ≈60,21). Script file 31 (script 4; L2251 sets 0x40a2 = 15; report checks L2145 `0x408c = 12, 0x4078 = 5`, L2039 `0x408c = 15, 0x4078 = 6`, L1891 flags 2110, 2289, 2292, 2293, 2294 and `0x4078 = 10`, L1702 `0x40a4 = 8, 0x40a9 = 5, 0x40af = 13, 0x40b2 = 5`), file 839 (Raikou, L1407–L3711, flag 2292), file 847 (Suicune, L3704–L5328, flag 2294).

## Mt. Silver: the Turtwig owner's four-leaf clover

Continues [Five Island: the four-leaf clover](05-saffron-cinnabar.md#five-island-the-four-leaf-clover-speak-up-for-him).

**Where:** the foot of Mt. Silver, south-west of the Pokémon Center (about 15 steps west and 13 steps south of its door).

**Who gets it / when:** only if you **didn't** win the clover for him on Five Island (you answered No; see [Five Island: the four-leaf clover](05-saffron-cinnabar.md#five-island-the-four-leaf-clover-speak-up-for-him)). He then moves here to keep searching. You also need **Mew** ([Mew: the long hunt](05-saffron-cinnabar.md#mew-the-long-hunt-five-island-finale)).

**How it works:** talk to him with **Mew leading your party** (the first Pokémon that isn't fainted). Mew finds a four-leaf clover.

**Reward:** **3 Revival Herbs.** He then stays nearby with a healthy Turtwig.

**Notes:** if you did win the clover on Five Island, he's already here with a healthy Turtwig and just thanks you (no item).

*Source:* script file 945 (script 17, L1178–L1447; `GetPartyLeadAlive` + species 151; item 37 ×3; flags 1530, 1531), file 58 L4425/L7744 (Five Island clears 1530 or 1531). Turtwig owner ≈807,278 (Pokémon Center door ≈822,265).

## Indigo Plateau (final chapter): Mewtwo joins you (take it before the Elite Four)

**Where:** the Indigo Plateau slope, after the spatial-barrier scene with Cyrus and Charon. Mewtwo stays in the middle of the path, about 28 steps straight north of the Victory Road exit.

**Who gets it / when:** final chapter, after Mewtwo breaks Palkia's barrier and you win the Multi Battle at its side. It says "Once you have sorted out your team... come find me here."

**How it works:** talk to Mewtwo → "Add Mewtwo to your party?" → Yes. You need a free slot; otherwise it waits.

**Reward:** **Mewtwo, Lv. 95.**

**Notes:** **missable.** The final Hall of Fame removes it for good, and once you walk into the Elite Four's rooms you can't come back out. Take it before entering.

*Source:* script file 923 (script 31, L2266–L2395, `GiveMon 150, Lv. 95`; obj 42 at ≈912,243 hidden by flag 2310), file 822 L2470 (Hall of Fame sets 2310).

## Indigo Plateau slope (final chapter): Steven's and Cynthia's confessions

Part of the romance route; the rules are in the [central romance entry](09-ilex-goldenrod.md#romance-route-how-its-unlocked-how-your-partner-is-chosen-and-what-locks-a-partner-out-central-entry).

**Where:** the Indigo Plateau slope, about nine steps north of Mewtwo, where Steven (right) and Cynthia (left) rest side by side after the Mewtwo scene.

**Who gets it / when:** the romance must be unlocked (any finished love reading from the Goldenrod fortune-teller), you must not have confessed to anyone yet, and that partner's route must still be open.

| Partner | Player | Closed by |
|---|---|---|
| **Steven** | female | at the Indigo Conference, "Cheer for Misty" or "No, get ready for my match" (only "Cheer for Steven" keeps it open, [the Indigo Conference](06-sevii-islands-indigo.md#indigo-plateau-the-indigo-conference-main-tournament-and-the-who-do-you-cheer-for-choice-romance)); in the Dream World, every outcome except picking Steven, including leaving through the statue without picking anyone (see the [central romance entry](09-ilex-goldenrod.md#romance-route-how-its-unlocked-how-your-partner-is-chosen-and-what-locks-a-partner-out-central-entry)) |
| **Cynthia** | male | in the Dream World, every pick except Cynthia (see the [central romance entry](09-ilex-goldenrod.md#romance-route-how-its-unlocked-how-your-partner-is-chosen-and-what-locks-a-partner-out-central-entry)) |

Both can be reopened once by the [Island Forest wish](05-saffron-cinnabar.md#island-forest-six-island-before-the-lucky-meowth-god) on Six Island, unless you've already been to the Dream World.

**How it works:** talk to them. A long scene follows ending in a mutual confession. It heals your party and uses up your one confession.

**Notes:** otherwise they just wish you luck.

*Source:* script file 923 (script 29 Steven: `GetPlayerGender`, flags 1618, 2155, 1645; script 30 Cynthia: flags 1618, 2144, 1645; L7122 sets 1645; Steven ≈913,234, Cynthia ≈910,234, Mewtwo ≈912,243); file 900 L1678/L2778 set 2155; file 55 L3024–L3071 (the wish clears 2141–2145 and 2153–2157 unless flag 2300, set by the Dream World, file 898).

## Pokémon League (final chapter): the Elite Four rooms under Team Rocket

**Where:** the League entrance and the Elite Four's rooms, final chapter.

**How it works:**
- **No healing inside.** Once you go through the Elite Four door you can't come back, and the room attendants can't heal you. In the entrance hall a Rocket nurse heals your party for **$10,000** a time.
- In each room two Executives wait. Each room words the choice differently, but it's always the same two options: fight them **one after the other**, or **one Double Battle** against both. The rewards are the same.

| Room | Executives | "One at a time" / "together" answers |
|---|---|---|
| Lorelei's | Archie + Charon | "Let my battling do the talking" / "You losers, come at me together" |
| Agatha's | Maxie + Cyrus | "Your space power is no big deal" / "All talk. Come at me together" |
| Bruno's | Proton + Petrel | "One at a time, then" / "Come at me together" |
| Lance's | Marauder + Lawrence | "Try it, if you think you can win" / "Even both of you can't beat me" |

- Then Archer and Ariana (Double Battle), then Giovanni in the Hall of Fame, three battles in a row: a single battle (Arceus, Dialga, Nidoking, Empoleon …), a Double Battle against Giovanni and his Cerulean Cave double (Mewtwo, Rhydon, Tyranitar, Arcanine …), and finally a single battle against a lone **Lv. 100 Beedrill**.

*Source:* script file 816 (script 12, L1556–L1632, $10,000 heal; script 9 door), files 817–820 (menus: 817 515#21/22, 818 516#22/23, 819 517#22/23, 820 518#23/24; doubles 817 L595 557+863, 818 L646 864+558, 819 L598 498+487, 820 L615 865+544; e.g. 817 L1104/L1251 singles), 821 (L622 `TrainerBattle 479 503`), 822 (L1152 trainer 244, L1399 `288 287`, L1828 trainer 289).

## The Hall of Fame: what your two entries unlock

**First entry (end of the Kanto League):**
- During the title run itself, each Elite Four member and Blue let you choose **Singles or Doubles**.
- It marks the game as cleared. That opens the extras earlier pages describe as "after your first Hall of Fame", e.g. Sabrina's and [Blaine's rematches](05-saffron-cinnabar.md#cinnabar-gym-blaine-rematch-after-your-first-hall-of-fame). These are not post-game: the guide uses "post-game" only for things after the final entry.
- From then on the **Elite Four** offer a repeatable **Singles or Doubles practice battle** in their rooms (Lv. 91–95). Between rooms the attendant offers "Heal Pokémon / Go to the next room".
- The **Champion's room** attendant offers "Heal my Pokémon", "**Call a Trainer here to battle**" (Singles or Doubles, repeatable; losing whites you out). Right after your first Hall of Fame only **Blue** can be called. Once Prof. Oak has sent you to Johto with Prof. Elm's Pokédexes, **Yellow** joins the list; with the Rising Badge, **Gold** too. Yellow always battles you in a Double Battle, even if you pick Singles and "Enter the Hall of Fame".

**Final entry (after beating Giovanni at League HQ):** this is what the guide means by "post-game" or "after the final Hall of Fame" (Yellow's dates, Zapdos, Moltres, Rayquaza, Deoxys…). It also:
- opens the **Zapdos** (Power Plant) and **Moltres** (Cinnabar) encounters. Later Hall of Fame entries don't reset them: once you catch them, knock them out or run, they're gone for good;
- puts the **Elite Four** and the room attendants back in place (they're gone during the final chapter), so the practice battles and the Champion's room service work again;
- puts Gold back in New Bark Town (repeatable Singles/Doubles battle, Lv. 96–97; losing whites you out) and Crystal in Cherrygrove City;
- leads to [Lance's visit to your home in Pallet Town](01-pallet-to-pewter.md#pallet-town-lances-visit-home-after-the-final-hall-of-fame), where he hands over the legendary items seized from Team Rocket.

*Source:* script file 822 (first entry L20–L316, no explicit `SetFlag 2404`: the game sets it when you enter the Hall of Fame; the final-chapter path is L870 (var 0x409e = 18); final entry L2450–L2582 sets 2261 and clears 1517, 1786 (Zapdos), 302, 1607, 2089, 517, 1005, 499, 1964 …), file 196 (Zapdos: before 2261 the object starts a Rocket battle, after it L1693 `WildBattle 145` and L1717 sets 1786 for good), files 817–820 (practice menus at L747 behind `CheckFlag 2404` at L155; trainers 702–705), 821 (L1331 attendant, L1860 `CheckBadge 15` → Blue/Yellow/Gold at L2567, else var 0x408b ≠ 1 → Blue/Yellow at L2667, else Blue only; 0x408b = 1 from Route 1 (168 @576) until Oak's Pokédex errand (738 @3591 sets 2); Yellow's Singles still runs `TrainerBattle 951 951` at L3742), 839 (L1357, L2263 Gold). First entry = flag 2404, final entry = flag 2261.

## League gate, Mt. Silver, Route 29 and Cherrygrove: small extras

- **League reception gate (Route 26), Koga's photo:** after the final Hall of Fame, Koga trains in the gate from 18:00 to 20:59 (DS clock) and offers a souvenir photo. He stands on the **east (Route 22) side** of the gate, near the Route 22 exit. (Tested in an emulator: there at 18:00 and 20:00, gone at 17:00 and 21:00.)
- **Mt. Silver photographers:** photo spots at the foot of Mt. Silver (Wednesdays and Fridays) and in Mt. Silver Cave 1F (Thursdays). The one at the foot of the mountain isn't there while the Silver Conference crowd is gathered outside the Pokémon Center.
- **Route 29, Tuscany (Tuesdays):** the weekday sister gives a Scope Lens. Her ribbon gift for meeting all seven siblings has the known freeze; save first.
- **Cherrygrove City, Crystal's sale:** 10 Poké Balls for $800 during her tour; if you can't pay she gives you one free.

*Source:* Koga: file 213 script 16 (photo) and L523 (map load: needs flag 2261, visible when the hour is 18, 19 or 20, otherwise hide flag 624 is set; object at ≈17,10 next to the Route 22 door ≈21,8; emulator `emu_harness.py guide0107 --case koga`: object 12 present at 18:00 and 20:00 at 17,10, talk → 354#12, absent at 17:00 and 21:00). Photographers: file 945 L864 (weekday 3 or 5) and script 2 (if flag 1339 is clear, i.e. from the League HQ scene until the end of the Silver Conference, the photographer stays hidden), file 105 L244 (weekday 4). Tuscany: file 225 script 4; freeze is decision D-1331. Crystal's sale: file 847 L7064, L7956.

See [Known issues](known-issues.md#pokémon-league-mt-silver-and-new-bark-town) for suspected hack bugs in this area.
