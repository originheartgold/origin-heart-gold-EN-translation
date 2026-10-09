# Origin Save Editor prototype

A local TypeScript browser editor for **English Pokémon Origin HeartGold v4.0.3**.
Select one raw 512 KiB `.sav` file or a DeSmuME `.dsv` save, edit your party, money
and bag, and download a separate copy. No ROM selection, upload, account or backend is needed. Names and
verified reference tables are included with the editor; saves stay in the browser.

Party moves/PP/PP Ups, level, nature, separate IV/EV changes, shiny state, Pokérus,
money and all eight bag pockets are implemented. Search moves and items by English name. Held-item
editing is a potential next addition. PC boxes, story flags, quests and progression
editing are out of scope.

## Run from the worktree root

Node.js 22+ is required. Development tools are pinned to TypeScript 5.8.3,
ESLint 9.28.0 and typescript-eslint 8.34.0 (a compatible peer-version set). This
worktree uses existing local installations; no dependencies were downloaded.

```sh
npm --prefix work/save-editor install # only on a fresh setup, when desired
npm --prefix work/save-editor start
npm --prefix work/save-editor run check # typecheck, typed source lint, build and tests
```

Open http://127.0.0.1:4173. `PORT` overrides the loopback port. The server serves
only the page, stylesheet and compiled modules, never local fixtures or ROMs.
The browser application has no external requests or telemetry. Its pure binary
implementation is shared with the Python harness in [`../save-core`](../save-core/README.md);
the build compiles that package before the editor. Node is only a development
and harness runtime, never a browser backend.

## Editing contract

- Supported scope: English Origin v4.0.3 saves, either raw 512 KiB (melonDS, flashcart
  dumps and other raw saves) or DeSmuME `.dsv` (raw data plus a 122-byte
  footer). The format is detected from content, not the extension. Downloads keep
  the input's format, and a `.dsv` footer is kept byte for byte. Other versions/hacks
  and emulator save states are unsupported. Structural validation is not
  language detection or cryptographic proof of the game's identity.
- The editor selects the newest valid generation whose general and storage blocks
  share a mirror and counter, matching the verified native loader. It can fall back
  to an older coherent generation. Equal counters select the first mirror, and
  the native FFFFFFFF-to-zero rollover is supported. Saves without a coherent
  valid pair are rejected; native assertion and corrupt-storage edge paths are
  deliberately not writable. Only the selected general block is edited.
- Save and party Pokémon checksums are verified. Unknown current IDs are preserved
  and shown with diagnostic identifiers; unnamed entries cannot be newly chosen.
- New move choices fill base PP and reset PP Ups; selecting the existing move is
  a no-op. Empty move slots clear PP and PP Ups. Learnset legality is not enforced.
- IVs: 0–31 each. EVs: 0–255 each and 510 total. IV, EV, level/nature, money and
  pocket changes apply separately; other pending drafts survive.
- Level changes set the exact bundled experience threshold; an unchanged level
  preserves experience progress. Nature override preserves PID. Current HP follows
  native recalculation, including fainted Pokémon. Eggs cannot be stat-edited yet.
- Shiny: uses Origin's native override, preserving PID, nature, gender, ability and
  all identity-dependent data. Naturally shiny Pokémon cannot be made non-shiny;
  that would require identity changes. Existing shiny state reapplied is a no-op.
- Pokérus: None, Infected or Cured. Changing to Infected starts a one-day infection;
  existing strain is kept, or strain 1 is used for a Pokémon with no strain. Cured
  retains the strain with zero days. None clears it. Reapplying the current status
  preserves existing duration/strain exactly, including unusual imported values.
  Elapsed days since the last in-game save may cure an infection immediately on load.
  Shiny and Pokérus apply independently and preserve other pending drafts.
- Money: 0–9,999,999. TM/HM quantities: 1–99; other pockets: 1–999. Use Remove
  to delete stacks. Duplicate and wrong-pocket items are rejected. Item obtainability
  is not enforced, and the game's metadata includes placeholder entries.
- TM/HM and berry insertion sorting matches the game. Removing a registered item
  clears its shortcut. Key-item edits do not change story flags. Coins, Battle Points,
  Apricorn-box counters and held mail contents are outside scope.
- Equal-counter save mirrors can be inspected, but editing requires saving once
  in-game first. Every edit entry point enforces this, including no-op writes.
- Unrelated bytes, backup mirrors, counters and PC storage are preserved. Stat edits
  also recalculate encrypted party stats. Apply/discard drafts before switching party
  members or exporting edits. Export unchanged always returns the original bytes.
- Importing an invalid or unreadable replacement preserves the current save,
  applied edits and pending drafts. Only a fully validated replacement becomes
  active; an older pending read cannot overwrite a newer selection.
- Downloads are separate copies. Keep a backup before replacing a battery save.

## Bundled reference data

The user explicitly authorized a narrow exception to the repository's game-data
rule: include the editor-required **English names and numeric metadata** for this
version. ROMs, patches, sprites, dialogue and other game assets remain excluded.
See `AGENTS.md` and `verification-reference.md` for the exact scope and checks.
The developer ROM parser remains available for reproducible generation and parity
verification; it is not imported by the browser application.

Names retain the English build's in-game abbreviations. The bundle includes only
species names, move names/properties, item names/pockets, base stats, form lookup
and experience thresholds consumed by the editor, with schema/version/provenance.
Refreshing reference data is an explicit developer action against a verified local
English build, never a request made to the user at runtime.

## Verification

Run `npm --prefix work/save-editor run check` for all local gates, or `typecheck`,
`lint` and `test` separately. Lint runs against handwritten TypeScript with actual
type-aware ESLint rules; generated reference data is excluded from lint but remains
compiler- and schema-tested. See `verification-typescript.md` for typed-error and
import-session regression coverage, tool versions and current browser limits.

See `verification-export.md` for the actual browser download → reopen → native
game save/reset/reload check, and `verification-traits.md` for shiny/Pokérus checks. Run the complete automated suite using the command above. Synthetic tests cover
save CRC/mirror selection, all Pokémon shuffle selectors, encrypted round trips,
byte-preserving no-ops, mutation allowlists, independent drafts, stats, inventory,
name selection and invalid inputs. `verification-reference.md` covers the bundled
provider, deterministic generation, exhaustive local-ROM equivalence and the new
save-only browser workflow. Earlier evidence remains in `verification-names.md`,
`verification-inventory.md` and the `research-*.md` files; those historical milestones
used locally selected ROMs and do not describe the current setup flow.

Optional local fixture checks (output directory must be new and under ignored `local/`):

```sh
node work/save-editor/scripts/verify-local.mjs /path/to/saves work/save-editor/local/fixtures-new
node work/save-editor/scripts/verify-stats-local.mjs /path/to/English.nds /path/to/saves work/save-editor/local/stats-new
node work/save-editor/scripts/verify-inventory-local.mjs /path/to/English.nds /path/to/saves work/save-editor/local/inventory-new
```

The last two are developer comparisons with a local ROM. Existing native emulator
checks verified edits surviving save/reset/reload in the English build. To repeat:

```sh
/path/to/poke/.venv/bin/python work/save-editor/scripts/verify-runtime.py \
  --repo /path/to/poke --rom /path/to/English.nds \
  --save work/save-editor/local/inventory-new/full_bag_6mons.sav \
  --expect work/save-editor/local/inventory-new/full_bag_6mons.sav.moves.json \
  --expect-inventory work/save-editor/local/inventory-new/full_bag_6mons.sav.inventory.json \
  --out work/save-editor/local/runtime-new --persistence --timeout 480
```

Use only existing local ROMs/emulator tools. Native reports and saves stay ignored.
Actual in-app browser downloads have been reopened in the editor and verified
in the English game through save/reset/reload, with matching file hashes and
preserved edits. The browser download-event observer can still time out after a
successful download, so the page correctly reports “Download requested”. See
`verification-export.md` for the artifact chain, repeatable procedure and limits.

## Guide website

The Astro guide exposes this same editor as a native Starlight page at
`save-editor/`, using the guide's layout, controls and light/dark colors. It has
no iframe or separate embedded document. See `verification-site.md` for the
minimal site overlay, reproducible integration build and verification limits.
This partial worktree does not contain a standalone copy of the entire guide.
