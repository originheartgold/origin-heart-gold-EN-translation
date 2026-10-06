# Graphics credits

Graphics in this folder that did not come from the user's own USA HeartGold ROM.

**Status (reviewed 2026-09-29): current.**

| File | Used for | Source | Commit | Terms |
|---|---|---|---|---|
| `vendor/hg-engine/battle_gfx_8_236.NCGR` | FAIRY type icon, battle move selection / summary (`a/0/0/8` #236) | hg-engine, `rawdata/battle_gfx/8_236` — https://github.com/BluRosie/hg-engine/blob/4d316b4eff0bd9f2869c86c8785878eaf3d7d367/rawdata/battle_gfx/8_236 | `4d316b4eff0bd9f2869c86c8785878eaf3d7d367` (2026-09-27) | See below |
| `vendor/hg-engine/dex_gfx_8_123.NCGR` | FAIRY Pokédex type badge (`a/0/6/8` #123) | hg-engine, `rawdata/dex_gfx/8_123` — https://github.com/BluRosie/hg-engine/blob/4d316b4eff0bd9f2869c86c8785878eaf3d7d367/rawdata/dex_gfx/8_123 | same | See below |
| `weather_en/battle_graphics_0033.png` … `0041.png` (odd numbers; made from hg-engine's `8_346_sun.png`, `8_349_rain.png`, `8_351_sandstorm.png`, `8_353_hail.png`, `8_355_fog.png`, kept unmodified in the repo in `vendor/hg-engine/weather_icons/`, where `gfx.py make-weather-banners` reads them; the `weather_en/` outputs themselves are git-ignored and rebuilt by `build.py`) | English letters SUN / RAIN / SAND / HAIL / FOG of the battle weather banners (`battle/battle_graphics.narc` #33–#41 odd). Only the letter pixels are used; the banner art and colours are the hack's own. | hg-engine, `rawdata/weather_icons/` — https://github.com/BluRosie/hg-engine/tree/4d316b4eff0bd9f2869c86c8785878eaf3d7d367/rawdata/weather_icons | `4d316b4eff0bd9f2869c86c8785878eaf3d7d367` | See below |
| `dex_type_list_en.png` (FAIRY row only; git-ignored, rebuilt by `build.py`) | Pokédex type-label list (`a/0/6/8` #131) | letters taken from the hg-engine FAIRY icon above; all other rows are built from the USA ROM's battle type-icon letters | – | See below |

## Other sources (no third-party art)

- **USA HeartGold ROM** (the user's own dump): Pokédex header/buttons letters (the detail-page tab row AREA / DATA / SIZE / FORMS / BACK uses only USA letters: A R E S I Z F O M B C K from the USA area-page buttons, D and T from the USA list page's DETAILS button; "DATA" for the hack's 详细 tab is a user-approved composed label, D-1542), naming-keyboard BACK/OK, trainer-card background, Pokégear weekday sheets, bag HM/SET labels, Pokéathlon SWITCH labels; pass 3: battle HP-box status icons PAR/FRZ/SLP/PSN/BRN (raw tiles from USA overlay 12), WIN/LOSE/DRAW labels (`a/1/0/4` #5), CANCEL buttons (`a/1/1/3` #30), START button (`a/2/1/5` #16) and the Pokéathlon instruction screens (`a/2/1/9`).
- **The game's own font** (`a/0/1/6` file 0 of the hack ROM): the title subtitle "Origin HeartGold", the weather labels SNOW / DOWNPOUR / HARSH SUN / WINDS, the trainer-card "/", "W", "L", the link-capture labels DETAILS / INFO / EXIT and the battle info-panel labels EXIT / SWAP (next to the hack's own Ⓑ and ✚ icons; D-1109).
- **Hand-drawn in this project:** the naming-keyboard tab letters "QWE" / "abc" (`gfx.TAB_FONT`, in the style of the existing "ABC" tab). (Until 2026-10-06 also the Pokédex button letter "N" of the tab label "INFO"; replaced by "DATA" from USA letters, D-1542.)
- **pret/pokeheartgold** (https://github.com/pret/pokeheartgold, commit `9d8b7591f09b65804da2fb2dfd56f320633e0d36`): used only as a code reference (which screens and character sets the Pokédex draws together; the font glyph format). No pret files are shipped.

## Searched, nothing usable (pass 3)

- hg-engine, all branches at the time of the search (main, ai-dev, item-dev, move-dev, sprite-dev, workflows/assets), listed with the GitHub tree API: no status icons, no battle-panel "exit/switch" labels, no extra weather labels, no Pokédex type-list sheet.
- pret/pokeheartgold: only vanilla assets, which are the same as the USA ROM.
- hg-engine for the Pokédex detail tab row (D-1542), main at `eb219cf764ff751160c2a30cc3732ad5ca1effc1` (2026-10-05) and all other branches, via the GitHub tree API: `rawdata/dex_gfx/` holds only `8_003` (caught-ball icon) and `8_123` (FAIRY badge); the tab-row graphic (`a/0/6/8` #4, screen #11) and the 详细 label are not in hg-engine (it keeps the vanilla screen), so nothing to adopt.

## hg-engine terms

hg-engine has no LICENSE file. Its README ("Disclaimer") says, quoted verbatim:

> This repository and its assets are a community endeavor. By its nature, using it and subsequently profiting off of it is profiting on the backs of all of our work, all of which is intended to be used to further hobbies and for everyone to have fun. You have my blessing to use code and assets from this repository as you please as long as there is *no money involved*, including optional donations through whichever platform to play your hack. The creations that stem from this repository must be freely accessible and not hidden at all behind any paywall, including those that prompt the player to pay optionally (Ko-Fi's style comes to mind here). The Credits should also be replicated in your hack's repository and/or the post to your hack--we all sit on the shoulders of giants here.

Obligations for this patch:
- The release must be free, with no donation links.
- The release post or readme must reproduce hg-engine's CREDITS.md, or link to it: https://github.com/BluRosie/hg-engine/blob/4d316b4eff0bd9f2869c86c8785878eaf3d7d367/CREDITS.md
- The Chinese hack itself is built on hg-engine, so the release has to credit hg-engine anyway.

Upstream history: only the 2026-09-27 commit was checked (a shallow clone). hg-engine's CREDITS.md does not name who drew the FAIRY icons. Credit them as "hg-engine contributors".
