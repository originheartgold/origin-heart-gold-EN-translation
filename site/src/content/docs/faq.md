---
title: FAQ
description: Answers to the questions players ask most about Origin HeartGold in English, from patching errors and game speed to natures, nicknames, evolutions and the story spots where people get stuck.
---

The questions players ask most, with short answers and links to the full details.

## Stuck in the story?

The story often moves on only after you talk to the right person, sometimes someone you've already talked to. If Blue or Green tells you to "ask around", talk to everyone in town again, inside buildings too. These are the places where most players get stuck:

| Where you're stuck | What to do |
|---|---|
| Pewter City: Brock keeps leaving the Gym | Follow him to the north-east house, the museum (answer his siblings' quizzes) and the flower garden. [Finding Brock](../guide/pewter-to-vermilion/#pewter-city-finding-brock-the-gym-leaders-errands) |
| Mt. Moon: guards block the way | [What opens the roadblock](../guide/pewter-to-vermilion/#mt-moon-what-opens-the-fake-guards-roadblock) |
| Vermilion City: "ask around town some more" | Talk to all six people involved, including Granny Kin right next to Lt. Surge at the construction site, then go back to Blue or your friend in the Pokémon Center. [The construction-site dispute](../guide/vermilion-to-celadon/#vermilion-city-the-construction-site-dispute-choose-a-side) |
| Lavender Town: nothing happens at the Pokémon Tower | Go to Mr. Fuji's Pokémon House and talk to the Cubone. [Pokémon Tower](../guide/vermilion-to-celadon/#pokémon-tower-side-battles-and-extras) |
| Lavender Town: "I want to see you..." and you can't leave town | The Lavender curse: buy the fortune-teller's 10 Cleanse Tags and use them at an exit. [The girl who waits](../guide/vermilion-to-celadon/#route-10--lavender-town-the-girl-who-waits-the-lavender-curse) |
| Celadon City: where is Erika's Gloom? | [The stolen Gloom](../guide/vermilion-to-celadon/#celadon-city-the-stolen-gloom-story-chain-easy-to-get-stuck) |
| Celadon Rocket base: the Persian statue password | The password changes with the day of the week and the hour. [How to read it](../guide/vermilion-to-celadon/#celadon-rocket-warehouse-the-secret-passage-and-the-persian-statue-password) |
| Saffron City: a barrier blocks every gate | Talk to someone at the north, south and west gates, then go back to Sabrina at the east gate (Route 8). [Getting past the barrier](../guide/celadon-fuchsia-saffron/#saffron-city-takeover-getting-past-the-barrier-into-the-city) |

Some story choices only come once, like the [bomb on the S.S. Anne](../guide/vermilion-to-celadon/#ss-anne-defuse-the-bomb-or-the-ship-sinks-one-chance). Missable rewards are marked in the guide; [Known issues](../guide/known-issues/) lists the ones that can close for good.

## Getting the game running

### Which HeartGold do I need?

**Pokémon HeartGold Version (USA)**, a clean, untrimmed copy (CRC32 `C180A0E9`). European, Japanese, Korean and already-patched files won't work. The [patcher on this site](../patch/) checks your file for you and accepts both `.nds` and `.zip`.

### The patch fails: "not a VCDIFF input", "source file too short", "secondary decompressor" or "file too big"

Use the [patcher on this site](../patch/): it handles zipped files and tells you what's wrong with your file. If you patch by hand, these errors usually mean one of these:

- **The two files are swapped.** Your HeartGold `.nds` is the source (original) file, the `.xdelta` is the patch.
- **A file is still zipped.** Unzip both first.
- **Wrong or modified HeartGold file.** Get a clean USA copy, not a "Rev 1", European or already-patched file.
- **The patching tool is too old.** Some tools, including Rom Patcher JS and some phone apps, can't read this patch. [xdelta-wasm](https://kotcrab.github.io/xdelta-wasm/) works.

### Can someone send me the patched game?

No. Sharing ROMs isn't allowed, here or on the Discord. The patch is all you need, plus your own HeartGold (USA) file.

### Which emulator should I use?

The translation is tested in [melonDS](https://melonds.kuribo64.net/) (automated tests also run in DeSmuME). Players also use DraStic, Lemuroid and others, but those aren't tested. Real DS and 3DS hardware isn't tested either. Players report extra crashes and speed problems there that don't happen on an emulator.

### How do I update to a new version without losing my progress?

1. Patch your **original** HeartGold (USA) file again with the new version. A patch can't be applied on top of an already-patched game.
2. **Save in game** before you switch. Emulator save states don't carry over between versions.
3. Give your save file the same name as the new game file (for example `Origin_HeartGold_EN.nds` and `Origin_HeartGold_EN.sav`), or import it in your emulator.

The translation doesn't change any game data, so your save keeps working.

### The game crashes after Misty's Gyarados, when I open the Bag or a Pokémon's summary, or at the move reminder

You're on an old version of the patch (before rc4). Those crashes, including the freeze at Mr. Psychic's move reminder in Saffron City, are fixed in the current release. Update as described above and keep your save.

### There are several English patches. Which one is this?

This site covers the English translation, which keeps the Chinese hack exactly as it was made. Other community patches, such as ones that add level caps or a hard mode, are shared on the Discord. This guide doesn't cover their changes. Each patch has to be applied to a clean HeartGold (USA) file; you can't stack them.

## Game settings and speed

### Why does the game run fast, and slow down in towns?

The original Chinese hack runs the overworld at a higher speed (a "60 fps" feature). It's busier in towns with many characters on screen, so it feels slower there. It's part of the hack, not the translation. The translation keeps it for now, and an optional switch is being looked into. Make sure your emulator itself is set to normal (1×) speed.

### Is there a text speed setting?

No. The hack replaced the TEXT SPEED option with MUSIC SPEED.

### Why does Kanto play the Johto battle music?

Until you first arrive in Vermilion City, wild and Trainer battles in Kanto use the Johto themes. From then on they switch to the Kanto themes. The rule comes from HeartGold, where you first reach Kanto by ship at Vermilion; the hack starts you in Kanto but kept it. The original Chinese game does the same.

### Some moves have no sound. Is my game broken?

No. In the original hack these newer moves have no sound effect: Electro Ball, Soak, Flame Charge, Coil, Low Sweep, Acid Spray, Foul Play, Simple Beam, After You, Round, Echoed Voice, Chip Away, Clear Smog, Synchronoise and Venom Drench. Terrain Pulse has no animation at all. Wild Pokémon don't cry when they faint, either. Moves from the original games, like Vine Whip, keep their sounds; if one of those is silent for you, check your emulator's audio settings.

### Can I turn off the shared EXP, or set a level cap?

Not in this translation. Your whole party shares EXP and EVs automatically and there is no setting for it ([details](../mechanics/#automatic-exp-and-ev-sharing)). There are no level caps.

## Training your Pokémon

### How do I see IVs and EVs?

Open a Pokémon's summary, go to the stats page and press **L**. More controls are on [Mechanics and controls](../mechanics/#information-screen-controls).

### Are shiny odds increased? What are the catch-chain thresholds?

**Yes, the verified wild-encounter code adds a boosted shiny check even without a chain.** That check starts at **1 in 4,096**, or **1 in 2,048** with the [Shiny Charm](../items/shiny-charm/). The bonuses increase after **6, 10 and 20 completed catches** of the same species and form, and apply when the next encounter is generated.

| Completed catches | Extra shiny check: no charm | Extra shiny check: Shiny Charm |
|---|---:|---:|
| 0–5 | 1 in 4,096 | 1 in 2,048 |
| 6–9 | 49 / 65,536 (about 1 in 1,337) | 1 in 1,024 |
| 10–19 | 81 / 65,536 (about 1 in 809) | 97 / 65,536 (about 1 in 676) |
| 20+ | 113 / 65,536 (about 1 in 580) | 1 in 512 |

**These are the extra check's odds, not exact overall encounter odds.** The fractions count successful values out of the random number generator's 65,536 possible outputs. If that check fails, ordinary Pokémon generation can still produce a shiny; its interaction with the extra check has not been fully quantified. We therefore cannot yet give one exact combined rate for each tier. The Chain Logger's fractions differ slightly because it displays a rounded divisor rather than accounting for every successful random value.

The in-game range labels are also inaccurate at 10 and 20: use the thresholds above. There is no further increase beyond 20 catches in this check. See [capture chains](../mechanics/#capture-chains) for chain resets, IV and Hidden Ability bonuses, and the encounter types verified so far. These rates should not be assumed for starters, gifts or Eggs.

### Can I change natures and abilities?

Yes, in shops:

- **Mints** (change the nature's stat effect): $9,000 each at the Celadon Department Store 4F and the Goldenrod Department Store 1F. For example the [Adamant Mint](../items/adamant-mint/).
- [Ability Capsule](../items/ability-capsule/) ($25,000) and [Ability Patch](../items/ability-patch/) ($50,000): Celadon Department Store 4F.
- **Hidden Abilities** also come from catch chains with the [Chain Logger](../mechanics/#capture-chains).

### Why do all my wild catches have the same nature?

Your first party Pokémon has the ability Synchronize. In this hack Synchronize **always** passes its nature to wild Pokémon (in HeartGold it works half the time), including shinies. It counts even if that Pokémon has fainted. Synchronize Pokémon include Abra, Kadabra, Alakazam, Natu, Xatu, Espeon, Umbreon, Baltoy, Claydol, Munna and Musharna. Put a Pokémon without Synchronize first for random natures, or lead with a Synchronize Pokémon of the nature you want. Gift and event Pokémon aren't affected.

### How do I nickname a Pokémon I caught?

Wild catches don't ask for a nickname in this hack (gifts do). Visit the Name Rater in the north-east house of Viridian City.

### How do I evolve trade evolutions like Haunter, Kadabra or Machoke?

No Pokémon needs trading. The old trade evolutions level up while holding an item, often only by day or by night (Haunter holding a Spell Tag at night, for example). Every [Pokémon page](../pokemon/) shows how it evolves, and the rules are on [Mechanics and controls](../mechanics/#evolution). Some evolutions changed completely: Karrablast and Shelmet simply evolve at Lv. 25.

### Can other Pokémon Mega Evolve?

No. Charizard is the only Pokémon that can Mega Evolve, holding the Charizardite: Mega Charizard Y with a Timid or Modest nature, Mega Charizard X with any other nature ([held-item forms](../mechanics/#held-item-forms)).

### Where do I get a Light Ball?

- Pikachu starters get one as a [send-off gift in Pallet Town](../guide/pallet-to-pewter/#pallet-town-send-off-gifts-one-per-starter-before-viridian). Get it before you go to Viridian City.
- Lt. Surge's Gym in Vermilion City, [after the construction-site clash](../guide/pewter-to-vermilion/#vermilion-city-after-the-construction-site-clash).
- Wild [Pikachu](../pokemon/pikachu/) can hold one.

### Why can't I use a Full Heal or a Revive in battle?

The original hack leaves most medicine out of the battle Bag: status heals, Full Restore, Max and Hyper Potions, Revives and Ethers. This may be intended. Carry status-healing Berries (Lum, Pecha, Cheri and others) or the Blue, Yellow and Red Flutes, which do work in battle. The full list is in [Known issues](../guide/known-issues/#status-medicine-in-battle).

### Why can't I find a Pokémon or event someone else got?

Many events and some wild Pokémon depend on your starter (Charmander, Pikachu or Bulbasaur). Pick your starter at the top of any quest page and the guide shows only what your game can get.

## Cheats and extras

### Is there a cheat menu?

The original hack has a built-in Pokémon generator: in the field, **hold SELECT and press X**. Choose the species, level, nature, IVs, held item and more (L and R switch pages), then press **START** to create it. It was made by the Chinese developers, not added by the translation. Whether you use it is up to you. The [save editor](../save-editor/) on this site can also change your save.

## About the translation

### Is the whole game translated?

Yes, from start to end, including the post-game. If you find a mistake, please [report it](../contribute/) with a screenshot.

### Does it have fakemon or changed Pokémon?

No fakemon. The hack does change many Pokémon's stats, abilities, moves and evolutions. Each [Pokémon page](../pokemon/) shows the hack's data.

### How mature is the story?

The story follows the Pokémon anime and the Pokémon Adventures manga, with the hack's own scenes added. Some lines include swearing, dark humour and violence. The translation keeps the original's tone and doesn't tone it down.
