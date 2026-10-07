# Origin HG Save Editor

A standalone, browser-only save editor for **Pokémon Origin HeartGold v4.0.3 (English)**.
Open a raw `.sav` (512 KiB) or DeSmuME `.dsv`, edit, export. Nothing is uploaded.

Four views: **Party**, **PC**, **Trainer**, and **Bag**. PC storage has 24 boxes
with 30 slots each. Select a boxed Pokémon to edit its moves, ability, held item,
shiny status, Pokérus, nature, level, IVs and EVs. Empty slots support adding a
Pokémon; occupied slots support removal. All edits use the shared Undo and Export.
Boxed stats are calculated from experience and training values; they have no cached
battle HP. Adding requires one hatched party Pokémon as the trainer template.

The save-format code in `src/core/` is lifted from `work/save-editor` in the
EN-translation repo (CRC, mirror selection, Pokémon encryption, stat recalculation,
bag pockets). The UI is new. Sprites load from the PokéAPI sprites repository.

## What you can edit

| Party Pokémon | Trainer |
| --- | --- |
| **Add Pokémon** (any of 1025 species) / remove from party | Money, Game Corner coins, play time |
| **Ability**: species slots 1 / 2 / hidden, or any of Origin's 326 abilities | |
| Moves, PP, PP Ups | All 8 bag pockets (add, remove, quantities) |
| Level, nature, IVs, EVs (stats recalculated) | Badge toggles (Kanto first), with undo |
| **Hidden Power type** (shifts the fewest IVs by 1) | |
| Held item, shiny, Pokérus | |

Species types (from the ROM's personal table, Fairy included) are shown on the
Pokémon card, on every move, and next to the Hidden Power selector.

## Run

```sh
npm install   # TypeScript only, no runtime deps
npm start     # builds and serves on http://127.0.0.1:4180
npm test
```

To host it, build (`npm run build`) and upload `index.html`, `styles.css`,
`favicon.svg`, `assets/` and `dist/` to any static host.

### GitHub Pages

In the repository's **Settings → Pages**, set **Source** to **GitHub Actions**.
The workflow in `.github/workflows/deploy-pages.yml` installs dependencies, builds
the editor, then deploys the static site on every push to `main`.
You can also run it manually from the **Actions** tab. The deployment's
`github-pages` environment links to the published site.

## How abilities are stored (Origin-specific)

Vanilla Gen IV keeps an 8-bit ability ID in block A. Origin has 326 abilities, so it stores:

- **block B +0x1A (u16)**: the ability ID the game uses
- **block A +0x0D (u8)**: which species slot it came from (0, 1, 2 = hidden)

The editor writes both for a species ability. A custom ability writes only the ID and
leaves the slot alone, so evolving may switch it back to the species' slot ability.
This layout was confirmed against a real save (every party member's ID matched its
species' ability for its stored slot). Behaviour in battle hasn't been checked in an emulator yet.

## Adding a Pokémon

A new party member is built from scratch, with trainer data copied from your first
hatched party Pokémon: OT ID and name, language, origin game, met location and
the party mail/capsule bytes. That way it counts as yours, not a traded Pokémon.
You pick species, level, nature, ability slot, gender, shiny and random or perfect IVs.
The personality value is chosen to match the nature and gender, and is never
naturally shiny (shiny uses Origin's override flag). It starts with the last four
moves it would know by level-up in Origin (from the ROM's learnsets), in a Poké Ball,
with the species' base friendship. Removing a Pokémon shifts the rest up and
blanks the freed slot exactly as the game does. Only base forms can be added.

## Regenerating ROM data

`src/core/generated-extras.ts` (ability names/descriptions, type names, per-species
types, abilities, gender ratio, base friendship, level-up learnsets) comes from your own ROM:

```sh
npm run gen:extras -- /path/to/Origin_HeartGold_v4.0.3_EN.nds
```

`generated-reference.ts` (species/move/item names, base stats, growth) is unchanged from the original editor.

Badge editing changes only the selected badge bit and repairs the active general block CRC. It preserves the backup mirror and does not change gym battle or story flags. Origin’s audited gym scripts use IDs 0–7 for Kanto and 8–15 for Johto; the badge rows are displayed as Kanto then Johto.

HGSS badge sprites are bundled in `assets/badges/` and embedded in `src/ui/badge-sprites.ts` so existing static servers can display them; see [asset credits](assets/badges/README.md). Pokémon and item sprites continue to load from PokéAPI.

## PC storage format

Origin expands the HGSS PC to 24 boxes: storage blocks at `0xF800` and `0x4F800`,
size `0x18408`. Each box occupies `0x1000` bytes (30 encrypted 136-byte Pokémon
plus 16 bytes of padding). Names follow at `+0x18008` (40 bytes per box).
PC edits select storage mirrors by their own counters, validate the footer and CRC,
set the edited box's modified flag at `+0x18004`, and repair the active storage CRC.
General blocks, storage metadata and the backup storage mirror are preserved.
The layout follows the HGSS [storage struct](https://github.com/pret/pokeheartgold/blob/master/include/pokemon_storage_system.h),
with Origin's expanded count checked against the local save. Equal-counter ambiguous
mirrors and corrupt storage are rejected. In-game loading has not been verified yet.

The compact PC browser uses original Gen IV/HGSS wallpapers from [PKHeX](https://github.com/kwsch/PKHeX/tree/master/PKHeX.Drawing.Misc/Resources/img/box), embedded for offline use. It reads the wallpaper assigned to each box; names appear in tooltips and accessibility labels instead of beneath sprites. See `assets/wallpapers/README.md` for credits.

The Bag view uses one pocket icon selector, a scrollable item list, and a selected-item panel for quantities and removal. Add items from the footer; bulk quantity changes apply only to the current pocket.

## Guide integration

This is the `sv` editor, served full-width at `/save-editor/` by `site/src/pages/save-editor/index.astro`. Astro bundles the TypeScript directly; no separate editor build is required for the guide. The standalone build still works with `npm start`.

The theme button switches between light and dark and remembers the choice locally. Initially it follows the system theme.

Run `npm test` for typechecking and tests. Real-save tests skip when no local fixture is available. To include them, set `OHG_SAVE_FIXTURE=/absolute/path/to/test.sav` or place a save at `local/fixture.sav` (gitignored). Never commit save files.

Badge state is read from the active save's Origin-specific bytes at general `+0x80` and `+0x83`. It is never inferred from party levels, story progress, or previous files. Neighboring profile bytes do not affect badges. The theme control uses sun/moon icons with accessible labels and tooltips.

## Selected species and bulk bag edits

The species selector changes only the selected party or PC Pokémon, retains identity and training, uses the selected form, and preserves its level while recalculating stats. Custom nicknames, moves and abilities are retained. Eggs must hatch first.

“Add all items ×999” maximizes existing stacks and adds missing named items until each pocket is full, without changing key items. TMs/HMs use the supported maximum of 99. The result reports items that do not fit. Undo reverses the whole action.

The add and species selectors include all 16 Hisuian forms listed in the guide. They store the native base species plus form 1, and use form-specific stats, abilities and learnsets. Form mappings and base stats were checked against the local rc5 ROM. In-game loading of newly created Hisuian Pokémon remains unverified.

The Pokémon header includes icon-only gender editing for party and PC Pokémon, limited to genders supported by the species. See FEATURE_COMPARISON.md for the comparison with Light Platinum and PKHeX.

## Advanced tools

The hero’s compact male/female toggle sits directly below the shiny button. The selected icon is highlighted and the other is dim. Always-visible bento cards contain nickname/flag, direct experience, friendship, OT gender and encounter/egg fields. The species picker includes 383 native forms, including the 16 Hisuian forms.

PC tools move, copy or clone into free slots, fill free box slots with distinct PIDs, sort by species, maximize IVs/friendship and search across the loaded save. Individual file, Showdown, ribbon/marking and compatibility panels are hidden from the Pokémon UI. Trainer includes editable player profile and a Pokédex card with seen/caught progress and species status controls; Mystery Gift and the Save file card are hidden. The item reference is in Bag.

Both inner chunk and main save checksums are repaired. Undo remains available for complete save operations. See FEATURE_COMPARISON.md for supported features and practical limits, and NATIVE_LAYOUT.md for format provenance. Compatibility findings are partial Origin checks, not a complete legality verdict. Native game loading remains to be verified.

The Bag uses compact pocket cards and a scrollable inventory list. Selected-item price, held-effect, Fling and use metadata appear beside the quantity controls; there is no separate collapsed item-reference panel. The layout stacks on narrow screens.
