# Graphics allocation audit

Checked 2026-10-02 against the untouched Chinese v4.0.3 ROM, verified English RC4
(SHA-1 `7234f7b34933e0dc8902d1d079e4747490241a2d`), and a local graphics-only test ROM.

## Chain Logger cause and fix

The bottom labels use `data/linkcapture.narc` character member 26 and screen member 25.
The file contains 96 4bpp tiles, but overlay 28's call at `0x0225FE30` loads only
`0x600` bytes: 48 tiles, starting at VRAM tile 50. The Chinese map references tiles
0–46. The RC4 generator allocated supposedly free file tiles and its map references
up to tile 74. Those tiles are not loaded; subsequent graphics occupy that VRAM.
This produces the striped letters reported by the tester.

The standalone RC4 asset renders correctly, so a file-format round trip or a contact
sheet alone cannot catch this. Runtime VRAM comparison showed tiles 0–47 matching
the resource, with later resource tiles absent. Restoring the original Chinese
members 25/26 in RC4 produced clear Chinese labels under the same code.

`make_linkcapture` now restricts its tile pool to 1–47 (tile 0 remains protected),
places DETAILS at x=16 and INFO at x=162, and checks the generated map before writing.
The English wording, icons, palette and game code are preserved. The regenerated
map's highest tile is 47. A local test ROM containing the regenerated production
assets displayed DETAILS, X:INFO and Y:EXIT correctly after opening the item from
Bag → Key Items → Chain Logger → USE.

The supplied 0.9.13 state needed a local compatibility copy for py-desmume's 0.9.12
core: decompress the state and replace incompatible chunks 61/91 with the Python
core's initial state chunks. The original state was untouched. Verification
included closing the logger and navigating back through the bag to reload its files.
Screenshots and investigation artifacts are ignored under `work/build/logger_repro/`.

## Scan scope and results

All 166 graphics patch entries were checked: 138 character members, 26 screen maps,
one palette and one raw code tile range. This includes costume copies. Every current
replacement preserves its consumer's graphics format, compression, character
depth/count/mapping, screen size and palette capacity. The raw code tile operation
already preserves length and guards source/target bytes with hashes.

Five character sheets change screen tile references. Their 32 screen/character
bindings, including costume copies and unchanged related screens, now have audited
allocation rules in `work/graphics/layout_checks.json`:

| Sheet | Runtime allocation | Check |
| --- | --- | --- |
| Pokédex header, a/0/6/8 #1 | Whole 280-tile sheet | Screens 0, 7, 8; three costume variants |
| Pokédex buttons, a/0/6/8 #4 | Whole 192-tile sheet | Screens 5, 6, 9, 10, 11, 69, 70, 71; three costume variants. Tiles no screen shows stay untouched: the search page copies tiles 98/101 into its label windows (D-1505, D-1536) |
| Trainer card units, a/0/4/9 #41 | Whole 416-tile 8bpp sheet | Screens 47, 48; three costume variants |
| Title logo/subtitle, a/2/6/4 #8 | Whole 768-tile 8bpp sheet | Screen 3 |
| Chain Logger, data/linkcapture.narc #26 | First 48 of 96 4bpp tiles | Screen 25 |

Code inspection found whole-member loads (size argument 0) for the Pokédex header
and buttons in overlay 5, trainer card in overlay 47, and title logo in overlay 56.
All nine identified Pokédex member-4 background load sites were checked. The loader
ranges are hashed in the rules so code changes require a new allocation audit.
The other character edits retain the original tile references and storage geometry;
they do not introduce references to previously unused tiles. No further instance of
the Chain Logger allocation defect was found in the current translation patches.

This is a structural and code allocation audit of translation changes, not an
emulator visit to every rare screen or proof that the original hack has no graphics
bugs. Unrelated VRAM collisions and runtime-dependent load paths still need in-game
testing when reported.

## Automatic gate and validation

`gfx.apply_patches` checks replacement geometry and runs the allocation checks before
writing patched NARCs. A changed screen map without an allocation rule is rejected.
`build.verify_rom` repeats the map checks on the serialized output ROM. The generator
also checks its own Chain Logger result.

Run the regular graphics dry run with the project's Python runtime dependencies:

```sh
python3 work/tools/gfx.py check
python3 work/tools/gfx.py check-layouts path/to/built.nds --json work/build/graphics_layouts.json
python3 -m unittest discover -s work/tools -p 'test_*.py'
```

Validation: unmodified RC4 is rejected for tile 74 exceeding the 48-tile load;
the fixed ROM passes all 32 bindings. All 121 tool tests pass, including eight new
regression tests for partial loads, 8bpp byte counts, flags, replacement geometry,
missing allocation rules and changed loader code. Production graphics assets were
regenerated; existing release packages were not replaced.
