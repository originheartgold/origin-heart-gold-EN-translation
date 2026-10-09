# Enlarged text verification (2026-10-04)

**Status (2026-10-09): historical.** The rc5 quality tools this note describes (size_render_check, size_render_validation, size_render_gallery) were removed in the 2026-10-09 cleanup; the release gate is `check.py --full --strict-release` plus `--emu`. The findings below stay as the record; `git log --diff-filter=D -- work/tools` finds the scripts.

Scope: the approved-review candidate ROM, SHA-256
`27d76d83e72d3fb60c8782b1cd8509c18b0a539e11e5f541cdfe85c2a08d8ca9`.
No production banks or ROM were changed by this audit. Local evidence contains
ROM-derived text and stays under ignored `work/build/text-exception-verification/`.

## Final result

Both final native runs and their independent validators passed: 87 production
entries, 16 wide-name variants, two normal controls and two deliberately broken
controls (107 case runs). Both broken controls reproduced heap corruption. All
positive cases had clean sampled heaps and verified rendering/reset evidence.
The searchable local gallery contains 105 cases after deduplicating the controls.
The production ROM hash remained unchanged. See `verification-summary.json`,
`runtime/final-ordinary/report.json`, and
`runtime/final-extra-corrected/report.json` in the local evidence directory.

An exploratory wide-name Pokéathlon case originally used the wrong lifecycle
and corrupted its appended same-printer sentinel. The corrected run preserves
that entry's native no-reset lifecycle, observes a newly initialized printer,
and passes. The superseded `runtime/final-extra` report is retained for diagnosis
but is not used as final evidence. Native scripts are archived with hashes so
later test-tool maintenance does not erase the exact code used for these runs.

## What the tests exercise

`work/tools/size_render_check.py` places each exact candidate string into an
isolated trainer-dialogue ROM. Each case runs in a fresh emulator process from
the same pre-dialogue save state. The game executes its native text printer.
Hooks record SIZE transitions, glyph coordinates, font selection and new printer
initialization. Every page is captured; heap integrity is sampled every ten
frames. An ordinary-font sentinel follows balanced strings without an injected
SIZE reset, and its screenshot crop must match the normal control.

The deliberately broken Misty line is a negative control. It must reproduce heap
corruption; a timeout or generic failure is not sufficient. Pryce's extra reset
must produce the actual sequence 200 → 100 → 200 → 100, then normal sentinel
glyphs. `size_render_validation.py` independently checks the raw evidence,
coverage, controls and input hashes. Missing evidence fails validation.

The inventory contains 87 entries, with 94 English enlarged spans versus 93 in
the Chinese hack. The extra span is Pryce's second page. Seventy-four entries
have balanced resets; thirteen Pokéathlon entries intentionally end enlarged,
matching the source. Those thirteen are tested with their native font selection
and separately verified native window bounds. Fresh-printer initialization and
subsequent ordinary glyphs check that the setting does not leak between printers.
The test fixture still uses a field window, not the original Pokéathlon screen.

Sixteen strings contain the player-name variable. The trainer fixture does not
populate this story-specific variable. Additional cases substitute seven wide
`W` glyphs to exercise worst-case geometry. These cases do not prove the original
story formatter populates the name correctly.

## Native code evidence

`native-size-semantics.json` records ROM hashes, code signatures and disassembly.
SIZE belongs to each printer instance; the standard constructors initialize it
to normal. SCROLL clears the window and resets its cursor while retaining SIZE.
The explicit reset before Pryce's page break and re-enable on the second page
therefore match the actual renderer state model.

All thirteen Pokéathlon consumers were traced in the Chinese hack. Their recorded
overlay code ranges match the candidate. Titles 0302#166–175 use font 4 in a
144×32 pixel window (candidate widths 57–105 pixels). Announcements 0302#2, #26
and #31 use font 1 in a 216×32 window (maximum line width 208 pixels). Enlarged
glyphs are 32 pixels tall. Both paths create a fresh printer. Native scene
navigation has not been observed.

## Blanked-entry reachability remains unproved

No unreachable exception is justified for any of the fifty entries yet.
`blank-reachability/report.json` and `refinements.json` preserve the evidence:

- Banks 0034 (23 entries) and 0035 (4): no map/standard-script mappings or direct
  constant loads found. Generic computed loaders are not fully bounded.
- Bank 0041 (19): standard scripts 9800–9849 map to this bank and script archive
  166, which directly refers to failing entries #131, #132, #151, #152 and #212.
  No literal invocation of those standard scripts was found, including a raw
  scan across decoder gaps. Native/computed invocation remains unresolved.
- Bank 0267 (4): actual Pokéwalker consumers exist in ARM9 and overlay 103.
  An overlay 103 dispatch-table handler explicitly selects #147 and calls the
  renderer using the bank-267 handle. Its top-level trigger remains unproved.
  Dynamic selector ranges are not completely proved for the other entries.
  See `blank-reachability/pokewalker-followup.json`.

Absence of a direct reference is not proof of unreachability. US HGSS blankness
is not evidence that the Chinese hack cannot use an entry. No suppression or
exception was added. Closing these findings requires complete selector/caller
bounds in the Chinese hack, or restoring faithful text through the review flow.

## Reproduction

Run from the repository root using the emulator-enabled virtual environment:

```sh
.venv/bin/python work/tools/size_render_check.py --rom work/build/approved-review-20261004/candidate/origin_hg_v4.0.3_en_wip.nds --inventory work/build/text-exception-verification/size-inventory.json --mode ordinary --out work/build/text-exception-verification/runtime/final-ordinary
.venv/bin/python work/tools/size_render_check.py --rom work/build/approved-review-20261004/candidate/origin_hg_v4.0.3_en_wip.nds --inventory work/build/text-exception-verification/size-runtime-inventory.json --mode extra --out work/build/text-exception-verification/runtime/final-extra-corrected
.venv/bin/python work/tools/size_render_validation.py work/build/text-exception-verification/runtime/final-ordinary/report.json
.venv/bin/python work/tools/size_render_validation.py work/build/text-exception-verification/runtime/final-extra-corrected/report.json
.venv/bin/python -m unittest discover -s work/tools -p 'test_size_render*.py'
```

Use a new output directory to preserve an earlier run's captures. Final report
status and independent validation, not the existence of images, determine whether
a run passed. These are renderer tests, not end-to-end original story playthroughs.
