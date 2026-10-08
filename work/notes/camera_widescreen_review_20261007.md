# Camera and widescreen page review — 2026-10-07

Reviewed `site/src/content/docs/camera-codes.mdx`, `CameraCodes.astro`, `CameraPresets.astro`,
`site/src/lib/camera-codes.mjs`, and the documentation/XML in `work/cheats/`.
Source at review: `dfe8ba2` on `develop`. Existing unrelated working-tree changes were left alone.
This is a review and retest; the page and cheat implementations have not been changed or deployed.

## Publication follow-up

At the user's subsequent request, the page and its assets were published to `origin/main` as
`b313abbf00a358e339ae40e35967e87de8f1b8a8`, with all three page findings below corrected. The earlier
review and test results remain the historical record. The code values themselves were unchanged.
The isolated main-branch build passed: 2,376 pages and 280,436 links, zero broken. Browser verification
confirmed one associated label for each slider and all 37 images loaded.

The publication commit's author and committer are both `originheartgold
<337671126+originheartgold@users.noreply.github.com>`. Git's exact SSH command authenticated as
`originheartgold` before the successful push. The existing repository SSH command already pinned the
dedicated key; a generic `ssh github.com` test initially measured the unrelated default account, and
that mistaken inference was corrected. The shared local Git configuration now uses the dedicated host
alias with an explicit Git SSH hostname. Local pre-commit/pre-push hooks reject a different effective
identity, a different push route, and outgoing commits with another author or committer. Negative tests
passed. These are local safeguards, not unbypassable server-side GitHub rules.

## Findings

### P2: the four camera sliders have no accessible names

`site/src/components/CameraCodes.astro:22–29` puts an `<output>` before the range input inside each
implicit `<label>`. The output receives the label association; the slider does not. In the actual
browser, all four sliders have `labels.length === 0`, no `aria-label`, and appear as unnamed sliders
in the accessibility snapshot. A screen-reader user cannot identify tilt, distance, FOV, and draw
distance reliably. Use explicit `for`/`id` associations with the range inputs, and keep the output
associated separately. Recheck the accessible names after the change.

### P2: widescreen also affects a menu's 3D model

`site/src/content/docs/camera-codes.mdx:10–12,144` describes the codes as changing only the overworld.
That is accurate for the preset-table changes, but not for the widescreen patch, which changes the
shared camera initializer's aspect-ratio constant. On released RC5, opening the Bag from the same
private savestate with and without widescreen changes the player model's horizontal projection:
3,747 pixels differ, confined to `(89, 0)–(172, 141)` on the top screen. The model is narrower in the
native 4:3 framebuffer; stretching the top screen to 16:9 compensates for that. The text and bottom
screen are identical. Explain this scope rather than promising an overworld-only effect for every code.

Evidence: `work/build/camera-review-20261007/menus/bag_normal.png`, `bag_wide.png`, and `report.json`.
The camera initializer at `0x020235F8` was also observed executing during Bag rendering with the patched
constant. Its execution during battle initialization alone does not prove a visible battle change;
the sampled RC5 battle screenshots with widescreen alone and widescreen + custom camera were each
pixel-identical to the normal battle screenshot.

### P2: make the widescreen reversal instructions complete

`site/src/content/docs/camera-codes.mdx:24,43–51` says to use OFF but does not explicitly say to disable
ON first, or to put the emulator's top screen back to 4:3. The XML already explains both steps.
The native Action Replay engine reproduced the conflict: enabling ON followed by OFF leaves
`0x1555` (4:3), while enabling OFF followed by ON leaves `0x1C72` (16:9). An OFF code can therefore seem
ineffective when ON remains enabled later in the cheat list. Specify mutually exclusive ON/OFF codes,
restore the display ratio, and change maps/reload to recreate the camera.

## Published page status

The [published camera URL](https://originheartgold.github.io/origin-heart-gold-EN-translation/camera-codes/)
returned the site's 404 page in the browser on October 7. The homepage loaded normally. The source is
present on local `develop`; this report does not treat the unpublished page as a runtime code failure.
The latest [website workflow inspected](https://github.com/originheartgold/origin-heart-gold-EN-translation/actions/runs/37663271358)
completed successfully for commit `598037d4ab188435e6c92865962af2731f96f9d5` (created 17:58:52 UTC),
which is not the reviewed camera-page commit. No deployment was initiated.

## Retest method and results

No ROM was built or downloaded. Existing local ROMs were used, with private copies of battery saves,
isolated emulator configuration, and ignored outputs under `work/build/camera-review-20261007/`.
The RC5 image's SHA-1 matches the published-release manifest stored locally.

| ROM | SHA-1 |
|---|---|
| English RC5 | `6eecb13762af6893ba1ffeebb9142976f51807a5` |
| Current English work build | `2a052d2f2d78f04596352797fd501cdad4c6381e` |
| Untouched Chinese v4.0.3 | `b69dc16be246658e3b29027698878d7ec560a1f6` |

The raw 17-row preset table, overworld guard word, and original aspect constant match across all three.
Codes were extracted from the actual page and generated by its actual JavaScript module. They were
registered with the installed DeSmuME library's native `CHEATS::add_AR` implementation, so these tests
exercise Action Replay parsing/execution, rather than a Python imitation of the cheat writes.

| Test | Coverage | Result |
|---|---|---|
| Forced presets | All 17 on Route 1 and in a Mart, on each ROM: 102 map/preset combinations | Correct selected byte; screenshots captured; RC5 contact sheet visually inspected |
| Disable forced preset | Each ROM, normal map entry | Returns to preset 00 on Route 1 |
| Two ready-made interior codes | Each ROM | All intended words match; disabling and changing map restores the complete original table |
| Generated custom camera | All 17 base presets, every-map scope, each ROM | All emitted writes match RAM and preset 06 is selected |
| Widescreen ON | Each ROM, indoor/outdoor transitions | Aspect becomes `0x1C72`; wider outdoor view visible |
| Disable ON alone | Each ROM | Patched value persists, as documented |
| Widescreen OFF | Each ROM | Aspect returns to `0x1555` |
| Wild battle and return | Normal, widescreen, custom preset 02, and widescreen + custom, each ROM | All 12 battles reach the command menu and return to the field; table guard does not match during battle |
| Saved forced preset | RC5, actual in-game save, battery export, reset, Continue without cheats | Battery preset 02; reload preset 02; next map preset 00 |
| Menu A/B screenshots | RC5 Bag, Pokédex, party, trainer card, Options from the same savestate | Only Bag differs; the other four screenshots are pixel-identical |

The main runtime reports contain 40 passing explicit checks plus four successful battle-entry/return
pairs per ROM. A separate report validation asserted these outcomes. No crash or failed return was
observed in those runs. Battle coverage is a short scripted Rattata encounter, not an exhaustive test
of trainer battles, special camera sequences, move animations, or the story.

### Website

- `npm --prefix site run build`: passed, 1,613 pages.
- `python3 work/tools/site/check_site.py`: passed, 211,906 links, zero broken.
- Tested the built local page in the in-app browser at `http://127.0.0.1:4321/camera-codes/`.
- Exercised all 17 preset selections in each of the two scopes, scope switching, the flat toggle,
  slider edits, minimum/maximum input limits, reset, and Copy code. Clipboard content matched the
  generated code on a separate read after the copy completed. No browser warnings/errors were recorded.
- All 37 page images loaded. At 390 × 844, document width was 390 with no horizontal page overflow;
  the builder was visually usable. The temporary viewport override was reset.
- Accessibility defect described above remains. Interior-scope reset intentionally selects perspective
  even for flat presets; this follows the existing UI implementation.

### Reproduction and artifacts

The local review folder contains `codes.json`, `static.json`, `retest.py`, `savecheck.py`, `menus.py`,
per-ROM JSON reports, native emulator logs, private savestates/battery export, and screenshots.
`rc5/presets_contact.png` shows all 34 RC5 map/preset screenshots. These artifacts remain ignored and
must not be added to git. The notes in this file contain no ROM data or copied game dialogue.

Run from the repository root, with the installed venv and native emulator permissions:

```sh
.venv/bin/python work/build/camera-review-20261007/retest.py rc5
.venv/bin/python work/build/camera-review-20261007/retest.py en
.venv/bin/python work/build/camera-review-20261007/retest.py cn
.venv/bin/python work/build/camera-review-20261007/savecheck.py
.venv/bin/python work/build/camera-review-20261007/menus.py
```

The first sandboxed emulator probe aborted before boot. The isolated emulator runs completed with
the required host permissions. An intermediate additional-test script used the wrong register accessor;
it was corrected and rerun successfully. Neither attempt changed source ROMs or user saves.

## Remaining coverage limits

melonDS/Vulkan, physical DS/DSi, flashcart cheat databases, TWiLight Menu++, and long play sessions were
not retested. The page's disclaimer about those platforms remains necessary. Native emulator results
do not establish that the reported Vulkan rendering problem is fixed. Slider extremes were checked in
the browser for generated output, not all rendered in-game; the existing clipping/map-edge caveat is
still relevant. Full story/save integrity was not claimed from these targeted tests.
