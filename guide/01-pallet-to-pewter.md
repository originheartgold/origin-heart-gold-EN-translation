# Pallet Town to Pewter City

[← Guide index](README.md)

**Quests on this page:**

- [Pallet Town: send-off gifts (one per starter, before Viridian)](#pallet-town-send-off-gifts-one-per-starter-before-viridian)
- [Viridian City: the would-be professor's quiz](#viridian-city-the-would-be-professors-quiz)
- [Viridian City: the Meowth thief (Charmander starters only)](#viridian-city-the-meowth-thief-charmander-starters-only)
- [Viridian City: the Pikachu thief (Bulbasaur starters only)](#viridian-city-the-pikachu-thief-bulbasaur-starters-only)
- [Viridian City: the Mankey thief (Pikachu starters only)](#viridian-city-the-mankey-thief-pikachu-starters-only)
- [Viridian City: Yellow's first Pokémon (the Gym's Virtue trial)](#viridian-city-yellows-first-pokémon-the-gyms-virtue-trial)
- [Viridian Gym: the Wisdom quiz (two ways to pass)](#viridian-gym-the-wisdom-quiz-two-ways-to-pass)
- [Viridian City: Pokémon Academy exchange students (missable early)](#viridian-city-pokémon-academy-exchange-students-missable-early)
- [Route 2: the Rocket warehouse Poké Ball (starter-dependent gift)](#route-2-the-rocket-warehouse-poké-ball-starter-dependent-gift)
- [Route 2 East: the abandoned Charmander (Pikachu starters only)](#route-2-east-the-abandoned-charmander-pikachu-starters-only)
- [Route 2 East: Nidoran♀ and the Apricorn Ball maker (non-Pikachu starters)](#route-2-east-nidoran-and-the-apricorn-ball-maker-non-pikachu-starters)
- [Route 2: the Magcargo fan (show a Pokémon)](#route-2-the-magcargo-fan-show-a-pokémon)
- [Viridian Forest: the runaway Snubbull ($20,000, one-time choice)](#viridian-forest-the-runaway-snubbull-20000-one-time-choice)
- [Viridian Forest: the flower garden and the Spearow (missable)](#viridian-forest-the-flower-garden-and-the-spearow-missable)
- [Viridian Forest: lend her a Pidgeot (Pikachu starters only)](#viridian-forest-lend-her-a-pidgeot-pikachu-starters-only)
- [Viridian Forest: the Honey tree (weekday Bug Pokémon)](#viridian-forest-the-honey-tree-weekday-bug-pokémon)
- [Viridian Forest: the rescued Eevee (optional)](#viridian-forest-the-rescued-eevee-optional)
- [Pewter City: Sitrus Berries → Hard Stone → TM69](#pewter-city-sitrus-berries--hard-stone--tm69)
- [Victory Road: "Which one is the real Blue?"](#victory-road-which-one-is-the-real-blue)
- [Victory Road 1F: the fake item ball (Lv. 70 Electrode)](#victory-road-1f-the-fake-item-ball-lv-70-electrode)
- [Romance route: Victory Road confessions, Yellow's dates and your house](#romance-route-victory-road-confessions-yellows-dates-and-your-house)
- [Pallet Town: Lance's visit home (after the final Hall of Fame)](#pallet-town-lances-visit-home-after-the-final-hall-of-fame)

## Pallet Town: send-off gifts (one per starter, before Viridian)

**Where:** Pallet Town and your house.

**Who gets it / when:** each starter gets one gift. The gifts open once you have done **both** of these, in either order: talk to Mom after getting your starter (she gives you the Running Shoes and offers to save your money), and get the Town Map from Daisy. The game won't let you leave Pallet Town northward before that anyway. (Bulbasaur players: Mom's talk alone is enough.) All gifts close for good once Blue's scene in Viridian City has played (Blue stops you just west of the Pokémon Center, gives you his number and leaves for Indigo Plateau). That scene comes soon after you reach Viridian, so collect your gift before you leave Pallet Town.

| Starter | Who | Gift | Extra condition |
|---|---|---|---|
| Pikachu | Man with the Eevee at the north edge of town, a few steps north-west of the door to Blue's house | **Light Ball** | none |
| Charmander | Man by the south fence, south-west of Oak's Lab | **Charcoal** | none |
| Bulbasaur | The Poliwag in your house, 1F, by the kitchen sink in the top-left corner (next to Mr. Mime) | **Poliwag, Lv. 5** ("Take Poliwag along on your journey?" → Yes) | party not full |

**Notes:** Talking again after you get the gift, or after the Viridian scene, gives only flavour lines. The game also contains an unused Lv. 10 Poliwhirl gift for the same house that nobody in the house offers, so only the Poliwag can be obtained.

*Source:* script files 733 (Pallet Town; Eevee man script 1 checks flags 1088, 768, 408 = Town Map; fence man script 13 checks 1804 (set at the opening), 1088, 1287, 768), 842 (house 1F: scripts 9/10 check 106, 768, 1088, 1289, flag 2285; Poliwag at 2,5; Mom L6053 clears 767, L7422 clears 768 for Bulbasaur, L8826 clears 768 and sets var 0x4073 = 2 if the Town Map is held), 736 (Daisy L452: clears 768 and sets var 0x4073 = 2 only if 767 is clear), 733 coord trigger (north exit, var 0x4073 == 0), 739 (flag 1088, Blue's scene L3274–L3335). Positions: Eevee man ≈1041,360, south-fence man ≈1041,382.

## Viridian City: the would-be professor's quiz

**Where:** the house north-west of Viridian Gym. Use its upper (north) door, just west of the woman worried about the Meowth thief; the lower door leads to the nickname man's room. The mother says her son dreams of becoming a Pokémon Professor. Talk to the son and answer Yes to start the quiz.

**How it works:** he asks five questions and only tells you at the end whether one of your answers was wrong. He doesn't say which one. You can try again at once. Answer all five correctly to get his prize: an **Exp. Share** (one time).

| # | Question | Answer | Position in the list |
|---|----------|--------|----------------------|
| 1 | How many Pokémon types are there? | **18** | 2nd |
| 2 | How much damage does a type with the advantage deal? | **2x** | 4th |
| 3 | What are the three categories of Pokémon moves? | **Physical, Special, Status** | 1st |
| 4 | What are the core elements of a move? | **Type, Power, Accuracy, Effect** | 4th |
| 5 | How many Badges do you need to be ranked a Senior Trainer? | **8** | 3rd |

Question 4 is the usual trap: "Type, Power, Accuracy, PP" looks right, but the game only accepts "Effect".

*Source:* script file 744 (script 6, L358–L849; Exp. Share = item 216, flag 1221). Door: Viridian City warp at 1034,235 leads to the son's room (zone 497 warp 1). The English options are listed in the same order as the Chinese ones.

## Viridian City: the Meowth thief (Charmander starters only)

**What it is:** a small side quest. A resident says a Meowth keeps sneaking into people's homes all over Viridian City to steal things, and asks you to teach it a lesson.

**Who gets it:** only players who chose **Charmander** in Oak's lab. Viridian has one "thief" quest per starter, and all three pay out the same way:

| Starter | Thief | Reward |
|---------|-------|--------|
| Charmander | Meowth, stealing from homes | Lure Ball |
| Bulbasaur | Pikachu, stealing food from the Viridian Mart | Lure Ball |
| Pikachu | Mankey, breaking the street lights | Fast Ball |

With any other starter, the Meowth resident only says a general line about living alongside Pokémon, and the Meowth never appears.

**How it works:**

1. Finish the catching tutorial on Route 1. That makes the quest available.
2. Talk to the resident in the north of town, standing just east of the upper door of the house north-west of the Gym. They ask you to deal with the Meowth, and the Meowth appears.
3. The Meowth sits on the west side of town, level with the Pokémon Center and next to the Super Fang tutor. Talk to it and answer **Yes** to "Teach Meowth a lesson?". It attacks first: a wild battle against a **Lv. 5 Meowth**. If you answer No, nothing happens and you can come back later.
4. Beat it, catch it or run away: the game only checks whether you lost. If you black out, the Meowth stays and you can try again.
5. Go back to the resident for the reward: one **Lure Ball**.

**Why it matters:** the Super Fang tutor on the west side of Viridian teaches Super Fang for one Lure Ball. This quest is an early way to get that ball.

*Source:* script file 739 (resident script 24, Meowth script 28 → L3718, reward L5040: item 494; flags 1335/1336/1337). Oak's lab script (file 738) sets the starter flags, and the Route 1 script (file 168, L586–L602) sets the quest flags. Positions: resident ≈1038,236; Meowth ≈1015,266.

## Viridian City: the Pikachu thief (Bulbasaur starters only)

**Where:** the shop clerk standing a few steps east of the Viridian Mart door.

**Who gets it / when:** players who chose **Bulbasaur**, after the Route 1 catching tutorial. Before the quest opens, the clerk only advertises the Mart.

**How it works:**
1. Talk to the clerk. They say a Pikachu keeps stealing food from the Mart, and the Pikachu appears a few steps south-west of the house door just north of the Pokémon Academy.
2. Talk to the Pikachu and answer **Yes** to "Teach Pikachu a lesson?". It is "wary of you" and runs off to the **far northwest corner of town**.
3. Follow it and talk to it again (Yes). It runs to the **east edge of town, south-east of the Poké Mart** (next to a street light).
4. Talk to it there, from directly north or south. This time it lunges at you: a wild battle against a **Lv. 5 Pikachu**. Beat it, catch it or run away.
5. Go back to the clerk for the reward.

**Reward:** 1 **Lure Ball**, which is what the Super Fang tutor on the west side of Viridian charges.

**Notes:** Answering No does nothing, so you can try again. If you black out, Pikachu stays where it was. If you talk to it from the wrong side at a spot, it just runs back to the northwest spot. Its chase positions aren't saved: if you leave Viridian and come back, it is back at its first spot (tested in an emulator).

*Source:* script file 739 (scripts 3 and 23, flags 1334/1335/1336; the chase moves object 5 with `MovePersonFacing`, which a map reload undoes). Route 1 file 168 sets the quest flags. Positions: clerk ≈1046,253; Pikachu ≈1033,247, then ≈1008,235, then ≈1053,269. Emulator: `emu_harness.py guide0107 --case pikachu` (after the first chase and a trip to Route 1, object 5 is at 1033,247 again).

## Viridian City: the Mankey thief (Pikachu starters only)

**Where:** the street-light keeper on the west side of town, north-west of the Pokémon Center door.

**Who gets it / when:** players who chose **Pikachu**, after the Route 1 tutorial.

**How it works:**
1. Talk to the keeper. A naughty Mankey keeps breaking the street lights. The Mankey appears on the east side of town, south-east of the Gym door, beside a street light (a few steps south-east of the Trainer with the Politoed).
2. Talk to it and answer **Yes** to "Mankey is practicing its punches on a street light. Stop it?". It gets furious: a wild battle against a **Lv. 5 Mankey**. Beat it, catch it or run away.
3. Go back to the keeper.

**Reward:** 1 **Fast Ball**. The Quiver Dance tutor on Route 2 charges one Fast Ball.

**Notes:** Losing leaves Mankey in place, so you can try again. Blue's scene in Viridian (he stops you west of the Pokémon Center and gives you his number) hides the Mankey. If it played while the quest was running, the Fast Ball would be lost. In practice that scene always plays before you can reach the keeper (see [Known issues](known-issues.md#pallet-town-to-pewter-city)), so this shouldn't happen.

*Source:* script file 739 (scripts 12 and 29, reward L5100: item 492; Blue scene L3339 sets flag 1330, and the keeper then pays only if 1336 is clear). Positions: keeper ≈1019,255; Mankey ≈1050,246.

## Viridian City: Yellow's first Pokémon (the Gym's Virtue trial)

**Where:** Yellow, the girl standing with her uncle and his Doduo just south of the Viridian Mart.

**Who gets it / when:** anyone, once the Viridian Gym has reopened. Until then the man at the Gym door says Giovanni is away; the Gym reopens after Granny Mae's ultimate-move trial on Two Island, when Blue says he's heading to the Viridian Gym ([Two Island: Granny Mae's ultimate-move trial](06-sevii-islands-indigo.md#two-island-granny-maes-ultimate-move-trial)). Then talk to the man just inside the Gym door again: he is now the **Virtue examiner**. Before that, Yellow only chats about her uncle's Doduo.

**How it works:**
1. The examiner says you must help someone in Viridian City.
2. Talk to Yellow and answer **Yes** to "This little girl wants a Pokémon. Help her out?".
3. You need a plain **Poké Ball** in your Bag. It is taken and handed to Yellow. Without one, your character goes off to buy one; come back and ask again.
4. You're taken to Route 2 and battle a **Lv. 5 Rattata** (a scripted battle, so you have to win). Yellow throws the ball and catches it.
5. Back in Viridian, Yellow gives you her thanks gift.

**Reward:** 1 **Big Pearl**, and the examiner now lets you through ("That's proof enough of your virtue").

**Notes:** This is the Gym's first trial. The Wisdom quiz and the Skill trainers come next (next entry). Yellow's story continues later (Viridian Forest rescue, [romance route](#romance-route-victory-road-confessions-yellows-dates-and-your-house)).

*Source:* script files 739 (script 11, L4727, L6951; Yellow ≈1041,260; checks flag 1228), 741 (Gym guard, script 2: checks flag 1705; the examiner sets flag 1228 at L1226). Flag 1705 is set only in file 782 (Two Island, after Granny Mae's trial, L5318/L5370).

## Viridian Gym: the Wisdom quiz (two ways to pass)

**Where:** the second examiner inside the Viridian Gym, after the Virtue trial.

**How it works:** five questions. Any wrong answer and he still asks the rest, then turns you away at the end without saying which one was wrong. You can retry at once. There are **two** valid answer sets. The honest one:

| # | Question | Answer | Position |
|---|---|---|---|
| 1 | Why do you want to be a Pokémon Trainer? | **It's my childhood dream** | 2nd |
| 2 | What do you think catching Pokémon depends on? | **Mutual trust** | 4th |
| 3 | As a Pokémon Trainer, what's the key to beating your opponent? | **Bonds with Pokémon** | 3rd |
| 4 | How do you see Pokémon? | **Partners in battle** or **Family I live with** | 1st or 2nd |
| 5 | What matters most in holding together an organization as big as the Pokémon League? | **Shared ideals** | 4th |

The Team Rocket set ("You ignored the empty slogans and told the truth... worthy of meeting Lord Giovanni!"): **To make money** (4th), **Force and conquest** (2nd), **Powerful Pokémon** (1st), **Tools for my goals** (3rd), **Big cash rewards** (3rd).
**Reward:** passage to the Skill trial and Giovanni. Both answer sets count as a pass.

*Source:* script file 741 (script 6, L1293/L3339, flag 1631).

## Viridian City: Pokémon Academy exchange students (missable early)

**Where:** the Pokémon Academy (the school building south of the northeast house).

**Who gets it / when:** anyone, but only in the early game. Steven and Cynthia leave, and the teacher changes to Earl's lessons, once you have **both delivered Oak's Parcel and beaten Blue on Route 22**.

**How it works:**
1. Talk to the teacher at the front of the classroom. The Academy has two exchange students, and you're asked to beat them for Kanto's honour.
2. Battle both, in either order: **Cynthia** (Gible Lv. 5, Riolu Lv. 5, Amaura Lv. 5) and **Steven** (Beldum Lv. 5, Aron Lv. 5, Tinkatink Lv. 5). If you haven't talked to the teacher, they just chat.
3. Go back to the teacher.

**Reward:** **2 Ultra Balls, 1 Level Ball, 1 Lure Ball**.

**Follow-up:** Cynthia also waits in **Viridian Forest**, about a dozen steps east of the north exit, whether or not you met her at the Academy. Only her greeting changes. She offers a battle (Gible Lv. 9, Riolu Lv. 8, Budew Lv. 6); beat her for **5 × TM54 False Swipe**. She leaves afterwards.

*Source:* script files 859 (scripts 1, 9, 10; trainers 3 and 2; flags 1057/1244 end the early lessons and are set by whichever of file 738 L1651 (parcel) or file 212 L1931 (Route 22 Blue) comes second; the teacher sets flag 1218), 115 (script 3, trainer 65, flag 1063; Cynthia ≈51,34).

## Route 2: the Rocket warehouse Poké Ball (starter-dependent gift)

**Where:** the small house on Route 2 East that Team Rocket uses as a warehouse (the fake police block the road next to it).

**How it works:** the room is full of Poké Balls. All but one only say "A Poké Ball with a Pokémon inside." The live one is in the second row, just right of where the grunt first stands. Take it (Yes).

**Reward:** **Charmander starters get Doduo, Lv. 20; everyone else gets Barboach, Lv. 20.**

**Notes:** one-time. If your party is full it says so and you can come back. The ball can be taken before or after the battle. The battle starts only when you talk to the grunt: he asks who you are, and **"I came to take down Team Rocket"** starts it (the grunt, then Ariana). **"I got lost and wandered in"** avoids it; he just tells you to leave.

**Missable:** take the ball before the [Celadon Rocket hideout finale](03-vermilion-to-celadon.md#celadon-rocket-warehouse-the-secret-passage-and-the-persian-statue-password), which empties the warehouse.

*Source:* script file 171 (script 3, flag 1473; the live ball is at 6,4; it checks only the menu answer, party size and starter). The grunt (zone 417 object 17, hide flag 308) has object type 0 and sight 0, so he never spots you; script 2 menu @114/@122: battle 274 then Ariana 443, or "I got lost". Ariana's pack-up hides objects 0–16 except the ball (8). File 853 @3782/@3786 (Celadon hideout finale) sets 1473 and 308.

## Route 2 East: the abandoned Charmander (Pikachu starters only)

**Where:** a weak Charmander near the north end of Route 2 East, a couple of steps north-west of the door of the Viridian Forest north gatehouse.

**Who gets it / when:** Pikachu starters. It appears after the Viridian Forest Team Rocket scene. You must first hear a Trainer in the **Pewter City Pokémon Center** brag about dumping his "garbage" Charmander by the road. Before that, Charmander "doesn't seem to want to be caught" and nothing happens.

**How it works:**
1. Talk to the Pewter Pokémon Center Trainer (only there for Pikachu starters).
2. Talk to the Charmander and say Yes to "Try to catch it?". You carry it to the Pewter Pokémon Center and Nurse Joy heals it.
3. Its old Trainer turns up: battle **Guitarist Del** (Shinx Lv. 12, Swinub Lv. 11, Nidoran♂ Lv. 10). After he loses, Charmander turns on him and he runs off.
4. Talk to Charmander in the Pokémon Center: "Take it with you?" → Yes.

**Reward:** **Charmander, Lv. 10**.

**Missable:** do this before you win the Cascade Badge. That scene removes the roadside Charmander and the bragging Trainer. Once Charmander is in the Pewter Pokémon Center, it waits there.

**Notes:** Del's battle is a scripted win-or-white-out. Taking Charmander from the Pokémon Center removes it for good.

*Source:* script files 170 (script 3, L787, L2290; Charmander ≈1026,136; checks flag 1348), 751 (Pewter Pokémon Center scripts 10/11; the Trainer sets flag 1348 at L430), 115 (L5748 decides which Route 2 event you get). The roadside Charmander (zone 414 object 3) and the Pokémon Center Trainer (zone 475 object 12) share hide flag 1367, set by the Cascade Badge scene (758 @3887) and cleared only by 115 @6981 (Viridian Forest setup). The Pokémon Center Charmander (object 13) uses flag 1360, which 1367 doesn't touch. The Route 3 letter Charmander (file 175, hide flag 1366) never appears, so it can't hide this one.

## Route 2 East: Nidoran♀ and the Apricorn Ball maker (non-Pikachu starters)

**Where:** a man and an abandoned Nidoran♀ at the north end of Route 2 East, a few steps north-east of the door of the Viridian Forest north gatehouse.

**Who gets it / when:** Bulbasaur and Charmander starters, after the Viridian Forest Team Rocket scene.

**How it works:**
1. The man wants to catch the Nidoran♀ but has no ball. Give him a **Friend Ball** (Yes). Pewter City gives you two.
2. A cutscene follows. The breeder who released it shows up and orders it around, then decides to take it to a PC box. The game asks "Stop Nidoran♀ from being taken away?"
3. Answer **Yes** and battle the breeder (**Guitarist Del**: Shinx Lv. 12, Swinub Lv. 11, Nidoran♂ Lv. 10). Nidoran♀ chooses to stay with the man.

**Reward:** no item. The man moves to the **small house in the southwest of Pewter City** (about 11 steps west and 5 steps south of the Pokémon Center door) and turns your Apricorns into Apricorn Balls for free from then on.

**Failure:** answering **No** lets the breeder take Nidoran♀. You lose the Apricorn Ball service for good. The man is in Pewter but only sighs about Nidoran♀, and his mother says he's been down.

**Pikachu starters** get no Nidoran♀ story, but the man is in Pewter from the start and makes Apricorn Balls anyway ([Pewter City to Vermilion City](02-pewter-to-vermilion.md#pewter-city-the-apricorn-ball-maker)).

*Source:* script files 170 (scripts 4/5, L3021, L3881; man and Nidoran♀ ≈1031–1032,133; flag 1349 = Apricorn service), 754 (east room of the map named "Pewter Northeast house", entered from the southwest city door at 1037,111; [Pewter City: the Apricorn Ball maker](02-pewter-to-vermilion.md#pewter-city-the-apricorn-ball-maker)).

## Route 2: the Magcargo fan (show a Pokémon)

**Where:** the gatehouse at the north end of Route 2's eastern path, the one that leads on to Route 2 East (not the Viridian Forest gatehouse next to it).

**How it works:** a man wants to touch a Magcargo. Have **Magcargo** in your party and talk to him.

**Reward:** **2 Rawst Berries** (one time). He gets burned.

*Source:* script file 173 (script 6, flag 309; item 152 × 2). The man stands at 38,7 in zone 419, the room joining Route 2 (1050,192) and Route 2 East (1050,183).

## Viridian Forest: the runaway Snubbull ($20,000, one-time choice)

**Where:** the owner stands in the south gatehouse (Route 2 side). The Snubbull is in the middle of Viridian Forest, playing with a Pidgey.

**How it works:**
1. Talk to the owner in the gatehouse. He offers **$20,000** to bring his Snubbull back. The Snubbull just cries until you've talked to him.
2. Find Snubbull in the forest and talk to it: "Snubbull seems to be having a lot of fun. Take it back with you?"
3. **Yes:** you're taken back to the gatehouse and paid **$20,000**. The owner muses about "hunger training or pain training", and the Pidgey is left alone.
4. **No:** Snubbull stays with its friend for good. There's no reward and it can't be taken back later.

*Source:* script files 173 (script 4; sets flag 1237), 115 (scripts 12/13, L2869; Snubbull checks flag 1237).

## Viridian Forest: the flower garden and the Spearow (missable)

**Where:** the woman by the flowers on the far east side of the forest, north-east of the south entrance (head east from the entrance, past the Trainer standing there).

**Who gets it / when:** before you have the **Volcano Badge** (badge 6).

**How it works:** answer **Yes** to help scare off the Spearow. The Spearow flock attacks: a double battle against **Spearow Lv. 7** (the flock's team has three), then their leader, a wild **Fearow Lv. 20**. Losing either battle means a white-out and the quest stays open.

**Reward:** **2 Honey** (used by the Honey tree and the Mega Drain tutor below).

**Missable:** once you have the Volcano Badge she says the Spearow are already gone, even if you never helped. Pikachu starters get the Pidgeot loan (next entry) instead.

*Source:* script file 115 (script 11, L2318: `TrainerBattle [59, 59]`, trainer 59 = 3 × Spearow Lv. 7; flag 1062; woman ≈90,72).

## Viridian Forest: lend her a Pidgeot (Pikachu starters only)

**Who gets it / when:** Pikachu starters who have the Volcano Badge, but not the Earth Badge, and haven't become Champion yet.

**How it works:** she asks to borrow a Pidgeot (her line says "Pidgeotto" first, but only a **Pidgeot** is accepted). Pick it from your party. You need at least one other Pokémon. It stays next to her in the forest.

**Getting it back:** only after you've entered the Hall of Fame. Talk to her with a free party slot.

**Watch out:** she doesn't return *your* Pidgeot. She hands you a fixed loan Pokémon: a **Lv. 20 Pidgeot** with all IVs 31, no held item and the moves Sand Attack, Gust, Quick Attack and Whirlwind. Its OT is blank and its ID No. is 04336, so it isn't yours either. Whatever level, moves, EVs or item your own Pidgeot had are gone (tested in an emulator).

*Source:* script file 115 (L2225, L4827, L5794: `ReturnLoanMon` takes your Pidgeot, `GiveLoanMon [6, 20, 75]` gives the replacement from trade record 6; return needs game-clear flag 2404). Emulator (`emu_harness.py guide0107 --case pidgeot`, both ROMs): a generator Pidgeot Lv60 with Leftovers lent through the party menu is removed from the party; after 2404 the returned Pidgeot has trade record 6's PID, Lv20, IVs 6×31, moves 28/16/98/18, no item, OT ID 0x761510F0 (ID No. 04336), an empty OT name (summary: OT blank, ID No. 04336). D-1392, D-1552.

## Viridian Forest: the Honey tree (weekday Bug Pokémon)

**Where:** the glistening tree trunk in the south-west of the forest, west of the south entrance. A man near the north exit hints about it.

**How it works:** check the trunk with **Honey** in your Bag and answer Yes to spread it (1 Honey used). A Bug Pokémon attacks right away, Lv. 15, depending on the day of the week set on your DS clock:

| Day | Pokémon |
|---|---|
| Sunday | Scyther |
| Monday | Heracross |
| Tuesday | Pinsir |
| Wednesday | Volbeat |
| Thursday | Nincada |
| Friday | Pineco |
| Saturday | Yanma |

**Notes:** repeatable as long as you have Honey. The Mega Drain tutor in the south-west corner, a few steps south-west of the tree, also charges 1 Honey.

*Source:* script file 115 (script 16, L5008). Positions: tree 41,79; Mega Drain tutor ≈35,82.

## Viridian Forest: the rescued Eevee (optional)

**Where:** where Nurse Joy healed Eevee, in the far north-east corner of the forest (well east of the north exit), after the Team Rocket Eevee story on Route 2 and in the forest.

**How it works:** talk to the Eevee: "Eevee seems to really like you. Catch it?" → Yes.

**Reward:** **Eevee, Lv. 5**. If you say No or your party is full, it waits for you.

*Source:* script file 115 (script 10, flag 411; Eevee ≈91,33).

## Pewter City: Sitrus Berries → Hard Stone → TM69

**Where:** a hiker standing just south-west of the Pewter Poké Mart door, and a man with a Sudowoodo on the east side of town (east of the Mart).

**How it works:**
1. Anemone's flower garden on the hill, east of the Pokémon Center, gives 2 Sitrus Berries, Berry Pots and the Squirt Bottle. Answer **Yes** when she asks if you came to see the flowers; No only gets a teasing line, and you can ask again.
2. The hiker wants 3 Sitrus Berries, but he only asks when you have **at least 10** in your Bag. Say Yes: he takes 3 and gives you **2 Hard Stones**.
3. Give a Hard Stone to the Sudowoodo owner (Yes). He gives you **TM69 Rock Polish**.

**Notes:** any Hard Stone works for step 3. There are other sources, e.g. Route 36. Both are one-time.

*Source:* script file 748 (scripts 10, 15, 18; flags 1306, 1308). Positions: hiker ≈1058,98; Sudowoodo man ≈1077,102; Anemone ≈1064,107.

## Victory Road: "Which one is the real Blue?"

**Where:** Victory Road 1F, during the final Team Rocket chapter. Blue is stuck in a stalemate against a Team Rocket fake of himself.

**How it works:** you are asked which Blue is real.

**Warning:** the wrong answer can't be undone. It makes you fight the real Blue as well, and for female players it closes Blue's romance route.

- **"The right one is the real Blue"** is correct. You fight only the impostor (Blue's team: Blastoise Lv. 97, Arcanine Lv. 96…) and Blue thanks you.
- **"The left one..."** is wrong. You attack the real Blue first (Umbreon Lv. 96, Pidgeot Lv. 97…) and then the impostor. Blue ends up angry, and for female players **Blue's romance route closes**.

*Source:* script file 109 (script 12, L3922 vs L3967/L3983, L10465–L10992; wrong answer sets flag 2153).

## Victory Road 1F: the fake item ball (Lv. 70 Electrode)

**Where:** an item ball on the west side of Victory Road 1F, level with the spot where Blue stands (about 20 steps west of him).

**How it works:** checking it starts a wild battle against an **Electrode, Lv. 70**. Winning, catching or fleeing removes it. Losing means a white-out and it stays (fleeing and losing tested in an emulator).

*Source:* script file 109 (script 9, flag 1241; ball at 21,40; `CheckBattleWon` counts a flee as a win). Emulator: `emu_harness.py guide0107 --case electrode`.

## Romance route: Victory Road confessions, Yellow's dates and your house

This entry covers only the steps that happen on this page's maps (Victory Road, Viridian City and your house). How the route is switched on, how your one partner is chosen in the Dream World and what locks a partner out are explained in [the central romance entry](09-ilex-goldenrod.md#romance-route-how-its-unlocked-how-your-partner-is-chosen-and-what-locks-a-partner-out-central-entry).

**1. Confession (Victory Road, final chapter, before your final Hall of Fame entry):** after each companion's fight, they stay behind to heal. Talk to them again and you get a confession scene if three things are true: the romance route is on, they haven't been locked out, and you haven't confessed to anyone yet. The scene heals your party.

**Warning:** you get **one confession per game**. Talking to the wrong companion first uses it up, so only talk to your chosen partner again after their fight.

| Where | Partner | Player gender |
|---|---|---|
| 1F, north-west part, about a dozen steps south of the stairs up to 2F | Yellow | male |
| 1F, middle of the east side (where Blue stands with his Blastoise), after the "real Blue" choice | Blue | female; needs the correct choice ([see above](#victory-road-which-one-is-the-real-blue)) |
| 2F, west side, a short way east of the stairs down to 1F | Green / Red | either (Green for male, Red for female) |
| 2F, east side, a few steps east of the stairs up to 3F | Gold | female |

Misty ([Cerulean Gym](02-pewter-to-vermilion.md#cerulean-gym--cerulean-cape-mistys-romance)), Steven and Cynthia ([Indigo Plateau slope](07-league-to-cherrygrove.md#indigo-plateau-slope-final-chapter-stevens-and-cynthias-confessions)), and Silver and Crystal ([Victory Road 3F](06-sevii-islands-indigo.md#victory-road-3f-final-chapter-silvers-and-crystals-confessions)) have their own confession scenes. Each one uses up your one confession.

**2. Yellow's dates (Viridian City, after your final Hall of Fame entry):** Yellow waits just south of the Mart. She only offers dates if you have made your final Hall of Fame entry, have confessed to someone, and haven't locked her out. Otherwise she just says she's an Ace Trainer now. Menu:
- **Let's have a battle:** Singles or Doubles against Yellow (Pikachu Lv. 92, Omastar Lv. 91, …). Repeatable.
- **Let's go for a walk** (date 1): a trip to the Mt. Silver summit and the hot-spring lodge. Heals your party.
- **Let's go for a walk** (date 2, after date 1): a trip to the Resort Zone with **four Multi Battles in a row** at Yellow's side. Your party is healed before the first and after the last, **not between them**. Losing means a white-out and you replay the date.
- **I want you to meet my mom** (after date 2): she comes to Pallet Town, meets Mom, and leaves Viridian for good. Because of a hack bug, this visit plays Cynthia's version of the scene whoever your partner is: tested in an emulator with Yellow as the partner, Cynthia walks in (see [Known issues](known-issues.md#pallet-town-to-pewter-city)).

Cynthia's dates run the same way at the Pokémon Academy in Viridian City. Other partners have theirs in their own towns (see the central entry). Date progress is shared by all partners, so only your chosen partner's dates count.

**3. Living together (your house):** after the Mom visit, your partner is meant to move into your house, with a "Rest in my room" option that costs a Mail. This step is blocked for every player in the original hack: checking the PC upstairs at that stage does nothing (tested in an emulator; see [Known issues](known-issues.md#pallet-town-to-pewter-city)).

**Notes:** the dates only check that you haven't locked your partner out and that you have confessed to *someone*. They don't check that you confessed to that partner (see [Known issues](known-issues.md#pallet-town-to-pewter-city)).

*Source:* script files 109 (scripts 14, 18, 21, 24; confession spots 1F 20,17 and 43,40, 2F 16,32 and 57,37), 739 (script 40, L4140/L5395/L5333; Yellow ≈1041,261; checks flag 2261 = final Hall of Fame, set in file 822; flag 1645 = confessed; flag 2143 = Yellow excluded; date 2: HealParty @10519, MultiBattle @11662, @11800, @11963, @12101 with no heal between (each loss → L4959), next HealParty @12969), 859 (script 18, Cynthia's dates), 736 (script 4: @165 `CheckFlag 106` → L559, Cynthia's version, before the 2143 Yellow check), 843 (script 1 L363 `CheckFlag 106` → L4292 End before any partner branch; 106 is set with the starter, 738 @3946/@4080, and never cleared; hack finding D-1391; script 4, house 2F scene), 842 (scripts 12–15, "Rest in my room": L6462 Heart Mail 143, L6707 Grass Mail 137, L6887 Bubble Mail 139, L7063 checks Snow Mail 144 but L8417 takes Bubble Mail 139). Flag 1645 is also set by files 758 (Cerulean Gym, Misty), 923 (zone 85: the Indigo Plateau slope in this hack, Steven/Cynthia) and 110 (Victory Road 3F). Date progress is var 0x40b5: date 1 sets it to 3, date 2 (at 3) to 4, the Mom visit runs at 4 (stage 5→6). Emulator (`emu_harness.py guide0107 --case mom_visit,living`): with Yellow as the partner and flag 106 set as every save has it, 739 L10063 → zone 504 scene shows lines 442#58–62 and object 7 (Cynthia); with 106 cleared the same run shows Yellow (object 4, lines 25–31). At var 0x40b5 = 6 the 2F PC (with the Cascade Badge) shows nothing and the player can walk on; with 106 cleared it starts the love-letter scene (537#22–24).

## Pallet Town: Lance's visit home (after the final Hall of Fame)

**Where:** your house in Pallet Town, ground floor.

**Who gets it / when:** everyone, once, after your **final** Hall of Fame entry (the one after you beat Giovanni at League HQ; see [The Hall of Fame: what your two entries unlock](07-league-to-cherrygrove.md#the-hall-of-fame-what-your-two-entries-unlock)). The scene starts on its own as soon as you're on the ground floor of your house. Many "after the final Hall of Fame" quests in later pages wait for it.

**How it works:**
1. Mom asks whether you've recovered from fighting Team Rocket and invites you to watch President Goodshow's live speech on TV. He reports on the Team Rocket affair.
2. Back at home, Lance drops by. President Goodshow sent him with the legendary items seized from captured Team Rocket members.
3. You tell Mom you'll set out again to catch the legendary Pokémon scattered across the regions.

**Reward:** seven key items, one each:

| Item | Used for |
|---|---|
| **Silver Wing** | [Lugia in the Whirl Islands](11-cianwood-mahogany.md#whirl-islands-catch-lugia-after-the-final-hall-of-fame) |
| **Rainbow Wing** | [Ho-Oh at the Bell Tower](10-ecruteak-olivine.md#dance-theater--bell-tower-catch-ho-oh-after-the-final-hall-of-fame) |
| **Red Orb** | [Groudon in Mt. Moon](02-pewter-to-vermilion.md#mt-moon-groudon-post-game-red-orb); with the Blue Orb, [Deoxys on Six Island](06-sevii-islands-indigo.md#six-island-deoxys-and-the-lucky-meowth-god-post-game) |
| **Blue Orb** | [Kyogre in the Seafoam Islands](05-saffron-cinnabar.md#seafoam-islands-team-rocket-and-kyogre-league-hq-investigation-and-catching-kyogre) |
| **Jade Orb** | [Rayquaza at Sky Pillar Peak](06-sevii-islands-indigo.md#sky-pillar-peak-rayquaza-post-game-jade-orb) |
| **Adamant Orb**, **Lustrous Orb** | [Dialga, Palkia and Giratina](12-lake-of-rage-to-sinjoh.md#dialga-palkia-and-giratina-catch-them-after-lances-visit) |

**What else it changes:**
- **Articuno** is back in the Seafoam Islands, as a catchable Pokémon ([Seafoam Islands: Articuno](05-saffron-cinnabar.md#seafoam-islands-the-ice-walls-articuno-and-the-researcher-tm14-blizzard)).
- **Cresselia and Darkrai** are back in the [Dream World](09-ilex-goldenrod.md#dream-world-cresselia-and-darkrai-post-game).
- **Dialga, Palkia and Giratina** can be found again, and the **Fallen Red Star** on Six Island is back for Deoxys.
- It sets up the [Burned Tower scene with Prof. Hale and the three beasts](10-ecruteak-olivine.md#burned-tower-prof-hale-molly-and-the-three-beasts-post-game-frees-entei-suicune-raikou).

**Notes:** the Griseous Orb is not among the gifts.

*Source:* script file 842 (script 7, a map script that runs when var 0x4106 = 3, set by the Hall of Fame in file 822 @2558; `CheckFlag 2261` (final Hall of Fame, 822 @2458) → L1083: Mom, warp to the Pokémon League building for Goodshow's speech, back home; Lance @1707; items @1868–@1976: 482 Silver Wing, 483 Rainbow Wing, 534 Red Orb, 535 Blue Orb, 532 Jade Orb, 135 Adamant Orb, 136 Lustrous Orb; then clears 1368 (Articuno), 2317 (Burned Tower objects), 2290/2291 (Cresselia/Darkrai), 2342/2343/2340 (Dialga/Palkia/Giratina), 2188 (Six Island Red Star); sets 1855, 2310, var 0x4106 = 4 (plays once) and var 0x409f = 11 (Burned Tower scene, file 23 script 14) @2223). Level script table: script file 617.

See [Known issues](known-issues.md#pallet-town-to-pewter-city) for suspected hack bugs in this area.
