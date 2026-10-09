# RC6 and published-main integration

Integration branch: `merge/main-rc6`. Parents: RC6 `a657a13941fadd14ab373dbfcbb5cf347af9d9a3` and published main `19e999ef0b302b36014ae73da3000ec7e8f8f47f`.

The merge preserves the RC6 game, translations, patch definitions and expected hashes. Published-main website features and the expanded save-editor UI use the reviewed shared TypeScript save core. No held-back gameplay fixes are included. The RC6 tag and release package remain unchanged.

## Resolution and review

- The editor's compatibility modules moved into `src/core`; save checksums, mirror selection, Pokemon record encoding and transactions remain in `work/save-core`.
- New editor operations (trainer, Pokedex, Mystery Gift, storage and Pokemon metadata) use shared-core transactions. Fixture edits retain their explicit separate policy.
- Native coherent save-generation selection and rejection of tied generations are retained. Older editor fixtures and expectations were adapted to that policy.
- Restored retained codec, stat, trait, reference-parser and import regression tests. They caught an unnecessary growth-table requirement on party IV/nature edits, which was corrected; boxed-stat edits still require a verified growth curve.
- Failed imports roll back the previous session, selections and original DOM nodes, retaining unsaved draft values and event listeners.
- The architecture guard checks the moved wrappers, missing modules and accidental duplicate root-level save modules.
- Independent review confirmed the incoming website data is retained: 138 areas, 769 items, Pickup and all 1,440 species entries. Only the four intended RC6 evolution notes differ from published main.
- Trainer-name changes already present in RC6 remain; the approved Harrison name is retained instead of the older Leif text.

## Release identity

ROM SHA-1: `ca55846b7748ed251680f9b65e84acd59f387b54`.
Xdelta SHA-1: `27a78eea7823956352a3bc0fc31306d16ac00a7f`.
Release artifacts remain in the `poke-rc6` worktree under `work/release/v1.0.0-rc6/` (ignored).

The distributed reference docs still describe the untouched Chinese ROM's evolution tables; the README, website and RC6 notes explain the Boldore/Gurdurr level-up exceptions. This existing packaging limitation is not a ROM or merge change.

## Final validation

- `check.py --full --strict-release`: all steps pass on the final tree. The second build changes paths and environment and reproduces the ROM, xdelta and report exactly. The suite includes 938 tool tests, 43 documentation tests and 43 site tests, with GOLDEN assembly checks.
- `check.py --staged`: passes against the staged merge, including the restored tests.
- Emulator gate (`--emu-only fixes,scenarios,freeze`): passes with zero failures and zero pending approvals. All 32 covered fix cases pass against controls; the report also lists two unchanged graphics fixes without scenarios. All five scenario groups pass. All three melonDS freeze cases pass (Rocket HQ and both Bulbasaur reflection routes). Text-fit was not rerun: game and translation bytes are identical to the gate-tested RC6 candidate.
- Save editor: 453 tests pass, one optional English-ROM test skipped; type checking and lint pass; all eight mutation tests are caught. The portable Python save-harness suite passes 287 tests including image checks.
- Browser checks cover real and synthetic save import/edit/export, failed-import rollback, preserved draft DOM and undo. Website browser tests cover encounters, Pickup, quest filters and no-JavaScript fallbacks.
- Site: 4,651 pages build; 603,945 links checked with zero broken links; 75 built-site tests pass. Generated content and guide checks are current.
- Existing release zip integrity and manifest hashes verified. No ROM, save, xdelta or build outputs are added to git.

Publishing remains the user's step; this integration does not move the RC6 tag or push branches.
