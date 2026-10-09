# Independent Astra review of website completion

Reviewed 2026-10-09 with GPT-6 Astra at high effort. Worktree: `/Users/simonvergauwen/.codex/worktrees/website-completion/poke`, branch `codex/website-completion`, baseline `codex/website-rebase` (`3d3937c`). This is a review of the complete uncommitted website task, including new untracked implementation files. The original checkout was not modified.

> Resolution update, 2026-10-09: all six findings below have been fixed and revalidated. The original review and reproductions are preserved; see the resolution section at the end.

## Verdict

The implementation builds successfully and has broad structural coverage, but **six confirmed P2 defects should be addressed before treating the approved completion plan as fulfilled**. Two turn raw move fields into false player-facing effects, one hides known restricted tutors, two fail to reconcile already available evidence, and one falsely marks an evolution claim as matching. These are concrete content/data defects, not speculative gameplay bugs. No P0/P1, broken internal link, or additional confirmed UI regression was found in this review.

All findings below are high confidence. P2 means a material correction is needed in the normal development cycle; the labels do not imply save corruption or a release emergency. Reported page counts come from the fresh generated HTML where stated, not extrapolation from the number of species that might learn a move. No implementation, game data, or translation bank was changed. Only this report and ignored/local validation artifacts were written.

## Findings

### 1. P2 — Decode the HP-change field as signed before describing it as healing

**Locations:** `work/tools/docs/romdata.py:184`; `work/tools/site/battle_reference.py:51–52`.

The live move parser reads byte 19 as unsigned (`heal=b[19]`). The summary generator then calls every nonzero value healing. This renders Struggle as **“Configured healing: 231%.”**, Clangorous Soul as **223% healing**, and Chloroblast as **206% healing**.

This is a decoding defect, not just a conflict with familiar vanilla move behavior. The untouched hack's attribute getter loads this field with a signed byte instruction. At ARM9 address `0x0201A3EE`, the relevant Thumb bytes are `13 21 42 56`: `movs r1, #0x13; ldrsb r2, [r0, r1]`. The getter is the one identified at `0x0201A2E0` in `work/notes/move_data_audit.md:12`. The three actual byte values therefore decode to −25, −33, and −50. The existing game descriptions also describe user HP loss rather than healing. I inspected the original bytes read-only; I did not run these moves in an emulator during this review.

**Reproduction:** Open `/poke/moves/struggle/`, `/poke/moves/clangorous-soul/`, or `/poke/moves/chloroblast/`. The incorrect healing percentages are in ordinary visible effect summaries. The local Chromium probe independently reproduced Struggle's wording.

**Actual exposure:** The fresh build contains the erroneous phrases on exactly **three move detail pages and two Pokémon detail pages**: Kommo-o and Hisuian Electrode. Struggle does not appear in an ordinary learned-move table, so it would be wrong to describe this as affecting every Pokémon page.

**Proposed fix:** Decode byte 19 as signed, preserve that signed value in the exported technical record, and render positive healing separately from negative HP loss/cost. Only state a denominator or precise battle timing when supported by decoded behavior or a scoped test. Regenerate the affected JSON/docs/site output.

**Regression coverage:** Exercise raw bytes `0xE7`, `0xDF`, `0xCE`, a positive healing value, and zero through the parser and summary. Assert that the compiled pages cannot call these negative values healing. Existing tests validate many fields but do not catch this signedness error.

### 2. P2 — Do not present zero secondary-chance fields as literal 0% chances for stat moves

**Location:** `work/tools/site/battle_reference.py:54–57`.

Every stat-change record becomes “Configured …, N% chance,” even when the chance byte is zero and the record represents a stat-changing status move rather than a probabilistic secondary effect. Swords Dance consequently says **“Configured Attack change: +2 stage(s), 0% chance.”** Growl, Growth, and many other ordinary stat moves receive the same misleading interpretation.

The structured record and existing audit distinguish the move quality (`quality=2` for stat moves) from damage plus a secondary stat effect; the new sentence ignores that distinction. There is also project-specific runtime evidence that zero does not universally mean “never”: Lunar Dance's current stat-change fields have zero chances, while `guide/known-issues.md:1355–1358` records an emulator test in which its Speed and Sp. Atk increases occurred. I am not asserting that every zero field should automatically become 100%.

**Reproduction:** Open `/poke/moves/swords-dance/`. This is ordinary visible content, not merely an optional raw-data dump. The browser probe confirmed the exact sentence.

**Actual exposure:** A scan of the fresh HTML finds `, 0% chance.` on **57 move detail pages, 1,372 Pokémon detail pages, and 10 TM/item detail pages**. This counts distinct pages containing at least one affected summary; it is not a count of individual effect sentences or claims that all 1,372 Pokémon can be obtained.

**Proposed fix:** Use the supported effect/quality semantics when attaching a probability. Where a zero byte's meaning has not been established, omit the probability or explicitly leave it uninterpreted in the technical data. Do not convert unknown semantics into “0% chance” or blanket “100%.”

**Regression coverage:** Include Swords Dance/Growl-style status changes, Lunar Dance's scoped known behavior, and genuine 10%/30% damage-secondary effects. Verify the rendered learning tables as well as the move detail pages; a single exporter error spreads through all of them.

### 3. P2 — Keep restricted tutor sources visible independently of enumerated learners

**Locations:** `site/src/pages/moves/[slug].astro:15` and `:34`; `site/src/pages/moves/index.astro:20`. Relevant existing upstream behavior: `work/tools/docs/gen_docs.py:409–419`.

The move detail page removes every learner group with no enumerated species, then renders `TutorDetails` only inside the retained tutor group. The existing compatibility helper deliberately excludes tutor records whose eligibility is the sentinel `"restricted"`; it cannot safely enumerate their learners. That exclusion should not erase their known locations, prices, quest links, and restrictions from the new move page.

There are **six concrete restricted tutor records** in `site/src/data/tutors.json`:

| Move | Known source omitted from the move detail page |
|---|---|
| Headbutt | Route 25; free |
| Frenzy Plant | Two/Three Island houses; free; Granny Mae quest link |
| Blast Burn | Two/Three Island houses; free; Granny Mae quest link |
| Hydro Cannon | Two/Three Island houses; free; Granny Mae quest link |
| Charge | Saffron Fighting Dojo; ₽10,000; existing wrong-move branch warning and quest link |
| Surf | Route 19; free; Pikachu-specific quest and author note |

The index's `data-method` is built from enumerated species' learner methods only, so `/poke/moves/?method=tutor` also hides all six. Blast Burn, Hydro Cannon, and Frenzy Plant have no enumerated learners by the other methods either: their pages show a zero count and “No learners are listed” without the known tutor or linked quest that explains access.

**Reproduction:** Open `/poke/moves/blast-burn/`, then `/poke/moves/?method=tutor`. The detail page has no `.tutor-details`; the index row `#move-307` is hidden. Headbutt's `#move-29` is also hidden under the tutor filter. Hydro Cannon and Charge were separately checked in Chromium. The global tutor index still retains these records, so this is a failure of the new reciprocal discovery paths, not disappearance from the entire site.

**Proposed fix:** Render known tutor entries independently from concrete learner rows, explicitly distinguishing “script-specific eligibility; not enumerated” from “no known tutor.” Include known tutor sources in the method filter. Preserve unknown counts rather than fabricating compatibility; link the existing quests for the actual requirements.

**Regression coverage:** All six restricted records must remain discoverable through both the move page and tutor filter, with their prices/conditions intact. Keep the distinct-species learner count honest and do not count a restricted sentinel as a species.

### 4. P2 — Remove the stale global unavailability claim from Salac and Petaya Berry notes

**Locations:** `work/tools/site/reference_content.json:3371` and `:3394`; displayed as an audited finding by `site/src/components/ItemReferenceNotes.astro:15`.

Both new curated corrections state **“No reachable v4 source was found. The Celadon shop source belongs to v3.”** Their same item pages already list reachable theft routes and explicitly recorded emulator evidence that the player keeps the berry after battle:

- Salac: Team Rocket Grunt's Pinsir on the S.S. Anne (`work/tools/site/items_extra_sources.json:413–421`).
- Petaya: Swimmer♂ Ned's Empoleon on Route 21 (`work/tools/site/items_extra_sources.json:426–434`).

The updated known-issues guide also expressly removes these two from its unavailable list (`guide/known-issues.md:1402`). Thus this is a contradiction between current project sources, not a disagreement requiring new gameplay research. The generic author-note disclaimer does not resolve it: the bad sentence is separately promoted as **“Audited source discrepancy”** with a configured-data label.

**Reproduction:** `/poke/items/salac-berry/` shows the theft route near the top and the no-source assertion below it. The local browser probe confirmed both in the same visible page. Petaya has the equivalent contradiction.

**Actual exposure:** Exactly **two affected canonical item pages**. Qualot and Tamato already have appropriately narrowed wording and should not regress; Apicot and Lansat are separate unresolved-source cases and should not be given these theft routes by analogy.

**Proposed fix:** Limit the correction to the unsupported older Celadon shop claim and reconcile it with the existing theft source, retaining the distinction between configuration and the recorded scoped emulator test. Update the curated input and regenerate, rather than editing generated item JSON alone.

**Regression coverage:** Check all four corrected berries, including Salac/Petaya, against their current sources. The current browser fixture only singles out Qualot/Tamato and therefore misses this pair.

### 5. P2 — Reconcile move conflict warnings with already recorded scoped gameplay tests

**Location:** `work/tools/site/battle_reference.py:76–79`.

`AMBIGUOUS_EFFECTS` produces a blanket **“battle behavior needs an in-game test”** warning for moves with existing scoped gameplay results in the guide. The affected direct contradictions are:

- Volt Tackle: no recoil in the recorded KO scenario, with Double-Edge as control.
- Blast Burn: no recharge turn in the recorded scenario, with Hyper Beam as control.
- Lunar Dance: Speed and Sp. Atk rose and the user remained in battle.

The current guide supplies both the outcomes and method at `guide/known-issues.md:1352–1358`, naming `emu_harness.py hackbugs --case move`, both ROMs, and the tested circumstances. The new move pages reuse the older move-data audit's unresolved classification without presenting or linking this newer result. The Blast Burn browser probe confirmed the stale warning. I did not rerun those emulator tests; this finding is about failing to reconcile existing explicitly scoped evidence.

**Actual exposure:** **Three move detail pages** falsely imply that the relevant recorded behavior still lacks an in-game test. Bounce also has a useful tested result in that guide section that is not surfaced on its move page, but it is not one of these three blanket-warning contradictions. Do not infer that Frenzy Plant, Hydro Cannon, or Rock Wrecker were tested: the guide specifically says they were not.

**Proposed fix:** Preserve the effect-ID/field disagreement, attach a linked and scoped tested-behavior note for the cases actually tested, and state any remaining untested conditions precisely. Do not mark an entire move universally verified because one scenario was tested.

**Regression coverage:** Assert that the three pages surface the available scoped result and no longer request that same test as if none existed; preserve uncertainty for the explicitly untested related moves. This is central to the plan's requirement to distinguish configuration, game text, author claims, and tested gameplay.

### 6. P2 — Preserve explicit use-versus-hold operations in evolution reconciliation

**Locations:** `work/tools/site/reference_compare.py:68–73` and `:93–101`; downstream suppression in `work/tools/site/reconcile_references.py:151–158`.

The comparator records an item identity and time requirement but discards the source's explicit operation. In the actual supplied Pokémon workbook, `4.0 Pokémon Data!O232` for Ursaring says **“Use a Moon Stone at Night.”** The exported evolution is **“level up holding Moon Stone (night)”** to Ursaluna.

The coverage record nevertheless says `equal: true`, `status: "included"`, and `unresolvedFields: []`. Its only constraints are `time=night` and `item=81`; the explicit “Use” has vanished. Since Pokémon notes are emitted only for unresolved fields, this source discrepancy is not surfaced on `/poke/pokemon/ursaring/`.

**Reproduction:** Inspect row 232 in `work/tools/site/reference_coverage.json`; its recorded claim and matching edge show the contradiction directly. The source workbook cell was read independently using bounded, read-only openpyxl access. The generated Ursaring page has no author discrepancy note for it.

**Actual exposure:** **One confirmed supplied source row and its missing Ursaring discrepancy note.** This does not establish that every matched evolution row is wrong. The comparator deliberately allows omitted requirements and incoming/outgoing ambiguity, and a *bare item name* can appropriately remain ambiguous about use versus hold. This finding concerns an explicit operation that the parser silently ignores.

**Proposed fix:** Preserve explicit operations such as “use,” “hold,” and “level up holding,” matching them to the configured conditions. If wording cannot be compared conservatively, mark it unresolved rather than equal. Regenerate coverage and Pokémon source notes.

**Regression coverage:** Ursaring's explicit use claim must not match a holding/level-up edge. A direct-use stone evolution should still match; bare-item claims should retain their intentionally limited interpretation. Current comparator tests cover item identity and similarly named moves, but not this semantic distinction.

## Independent validation performed

| Check | Result and scope |
|---|---|
| Complete production build | `GUIDE_BASE=/poke/ npm --prefix site run build`: 4,651 pages built successfully. Existing Vite head-injection warnings remain; no new build failure. |
| Fresh compiled internal-link audit | `python3 work/tools/site/check_site.py --base /poke/`: 4,651 pages, 598,895 links, zero broken. This proves link targets, not gameplay truth. |
| Python suites used by site CI | 63 tests passed across the seven guide/trainer/held-item/comparator/battle-reference modules. |
| Site tests against fresh output | `GUIDE_TEST_DIST=1 npm --prefix site test`: 53 passed. |
| Save-editor tests | 54 passed using the already available local TypeScript compiler shim; no dependency installation. |
| Deterministic generator check | `python3 work/tools/site/build.py --check`: 18 docs, 13 JSON data outputs, and 15 guide outputs unchanged. |
| Workbook reconciliation check | Existing bundled Python/openpyxl with `reconcile_references.py --source-dir /Users/simonvergauwen/Downloads --check`: 8,074 accounted rows unchanged. Determinism does not validate the comparator's semantics. |
| Guide identity preservation | Compared all 13 chapter entry headings/metadata to the baseline: 367 entries, chapter counts 22/23/30/37/38/27/21/42/28/37/25/31/6, unchanged. |
| Independent local Chromium probe | 116 assertions passed, 40 mobile theme/page checks across 20 routes, zero uncaught browser errors. External requests blocked. |
| PDF structure and spot rendering | 238 pages, none with empty extracted text. Extracted pages 1, 2, 121, 237, 238; rendered and inspected pages 2 and 237. Contents and dense late known-issues layout are legible with no observed clipping. |
| Whitespace | `git diff --check` passed. The new hard-break exception is scoped to `work/docs/*.md`. |

Browser checks independently exercised combined Water/Special/TM/search filters using Scald, reload/reset/history restoration, all four complete no-JavaScript catalogs (1,440/920/327/138 rows), representative unnamed/form records, known defect reproductions, camera preset customization/reset, save-editor rejection of synthetic invalid bytes, and persistent quest/starter/technical-toggle state. A separate focused probe checked independent namespaced regular/hidden ability-holder search controls. Mobile checks covered Home, FAQ, mechanics, calendar, About, source coverage, items, moves, Pokémon/form, unnamed ability, TM, location, trainer record, tutor and guide page families. Layout assertions measure horizontal containment and single h1, not a complete accessibility audit.

The reproducible final browser probe is retained locally at `/private/tmp/website-astra-browser.mjs`; its result is ignored at `work/build/website-qa/astra-review/browser-results.json`, with `struggle-mobile.png`. Temporary PDF renders are `/private/tmp/astra-guide-page-2.png` and `/private/tmp/astra-guide-page-237.png`. Exploratory browser assertions were corrected where the review harness incorrectly assumed Water Gun was a TM or that camera reset meant the initial preset; these were harness assumptions, not product findings. Final reported counts are from the completed passing probe.

## Review coverage against the approved plan

| Required family | What was actually inspected | Result or limit |
|---|---|---|
| Data/export/import | All changed Python exporter/parser/comparator code, new curated inputs, generated schemas/joins, source dispositions, tests and CI integration. Read all curated item/tutor/legacy note fields and move/ability/TM/applicability note collections. Checked representative original workbook cells and deterministic import of all accounted rows. | Findings 1, 2 and 6. “Included” means accounted for under the present comparator, not that every claim is correct or tested. |
| Pokémon/forms/artwork/save editor | Changed detail/index templates, image helper/component, complete ID relationships and representative forms, evolution/level/TM/tutor/egg presentation, unavailable/calendar handling, Mew universal TM compatibility, save-editor artwork extraction and documentation. | Internal form IDs are not used as public artwork IDs. Forms currently use explicitly labeled base-species fallback art; this is not 415 independently verified matching form images. Restricted tutor coverage remains incomplete (finding 3). |
| Moves/abilities | All new templates/components, move slots, effect interpretation, ability holders, aliases, source changes, baseline labels and reciprocal applicability joins; representative named and unnamed pages. | 920 slots and 327 ability records are structurally retained. Findings 1, 2 and 5. Unsupported target/effect semantics remain labeled unknown; no independent verification of every battle effect. |
| TMs/items | 130 TM + 8 HM mapping, canonical item links, compatibility/reverse joins, source/price/condition rendering, legacy anchors, all curated English item note fields, representative generated item pages. | Finding 4. Raw hold-effect IDs remain raw rather than invented explanations. Older author repeatability/effect claims are still not runtime tests. |
| Locations/encounters/tutors | Changed location/tutor templates, generated method/time/level/form data, source comparisons, gifts/trades/calendar links, existing eligibility helpers and representative Route 19/other generated output. | Finding 3. Unmapped encounter tables remain disclosed rather than assigned to guessed maps. |
| Trainers | TrainerCard change, record routes, stored party joins and equipment/move/ability links; representative trainer route and complete link audit. | 1,023 record routes repair equipment destinations while retaining the curated trainer index. Stored party configuration is not a claim that every runtime branch was played. |
| Guide/quests/static pages | Read changes to every chapter, guide README and known issues; independently checked all 367 entry identities/metadata. Reviewed Home, FAQ, mechanics, calendar, About, contribute and patch prose changes and relevant existing tool pages/docs. | Existing quest IDs/progress structure preserved; findings 4/5 expose cross-page evidence inconsistencies. This was not a fresh translation or line-by-line verification of the entire roughly 96,000-word guide against scripts. |
| Tools/PDF | Reviewed patch/save-editor/camera/Primo integration and pertinent unchanged logic; save-editor suite and browser invalid-input check; camera and quest browser checks; PDF structure/text/layout spot checks. | No real ROM patched, real save edited, emulator gameplay run, or full 238-page visual inspection. Primo/browser patch application was not re-executed in this review. |
| Filters/base path/accessibility/mobile | All filter implementation and tests, base-path build, strict AND behavior, namespaced tables, sorting/reset/count/empty state/history logic, no-JS catalogs and representative mobile light/dark output. | Passing tests and probe support the tested behavior. Legacy anchors resolve when unfiltered; a conflicting active filter may hide its target by the established strict-AND design. No screen-reader or full keyboard/manual accessibility certification. |
| CI/reproducibility | Workflow diff, committed-data-only test/build boundary and fresh local build/generator checks. | No ROM/workbooks are required by the CI test/build path. Actual hosted Node 22/Linux CI was not run; local Node was v26.8.1. Existing CI dependency/PDF/release-patch downloads were inspected as code, not executed. |

## Remaining limits and completion implications

The completion report's 8,074 rows, 7,674 included and 400 unresolved are source-accounting results, not blanket fact verification. Additional `unresolvedFields` and caveats matter, and finding 6 shows that even a currently “equal” row can contain a missed explicit disagreement. The eight screenshot attachments were treated as duplicate representations according to the supplied task context, with workbook text preferred; I did not independently OCR and compare every screenshot. The curated English item survey was reviewed as a committed input, not freshly retranslated from every original Chinese cell.

The full generated corpus was checked structurally and for exact defect strings; representative records and pages were read in detail. I did not manually read all 4,651 pages. External artwork fetching was blocked in the independent browser probe, so it exercised local layout/fallback behavior rather than proving current remote image availability. No dependencies, datasets, ROMs, patches, or external media were downloaded.

The approved plan's remaining actionable gaps are the six findings above: supported effect semantics, discoverable restricted tutor routes, current evidence reconciliation, and honest evolution dispositions. The passing build/test/link checks are useful regression evidence, but their current fixtures do not cover these semantic cases. Address the curated/parser/template causes and add focused regressions before updating the completion claim; do not repair generated output alone or change hack behavior to match the documentation.


## Resolution of all six findings — 2026-10-09

The implementation agent fixed each reported cause in parsers, curated inputs,
comparison logic or templates, then regenerated the data. Original findings above
are preserved as review evidence, not current defect descriptions.

| Finding | Resolution and focused regression |
|---|---|
| 1 — unsigned HP field | Signed byte parser; negative HP loss/cost text with unknown basis/timing; raw signed values preserved. Synthetic −25/−33/−50/positive/zero parser cases and built-page scans cover propagation. |
| 2 — zero chance | Zero stat chance remains uninterpreted in raw data and is omitted from summaries; nonzero probabilities retained. Status/damage-secondary fixtures and every built learning-table page checked. |
| 3 — restricted tutors | All six render independently from learner enumeration and participate in the Tutor filter. Places, prices, quest links, restrictions, Charge warning and author notes retained; unknown compatibility not invented. |
| 4 — Salac/Petaya | Curated corrections narrowed to the obsolete Celadon shop claim and reconciled with existing theft/retention evidence. All four corrected berries plus Apicot/Lansat regression cases checked. |
| 5 — existing move tests | Four curated scoped test notes with evidence and guide links, including Bounce. Three stale blanket test requests replaced; unresolved fields and explicitly untested related moves retained. No new runtime claim. |
| 6 — explicit evolution operation | Use/hold/level-up-holding preserved; all five changed comparison records reviewed. Only Ursaring changes disposition; source discrepancy now shown. Direct-use and bare-item cases remain conservative. |

Final validation: **68 Python tests; 58 site tests; 4,651 pages; 598,911 links,
zero broken; deterministic 18-doc/13-data/15-guide and 8,074-row importer checks;
177 focused Chromium assertions and 62 mobile layout checks, no browser errors;
`git diff --check` clean**. The browser probe blocks external requests and is
retained in `site/tests/review-fixes-browser.mjs`. Exact commands, changed-operation
rows, remaining evidence limits and corrected fixture assumptions are documented
in `website_completion_coverage.md`, “Astra review fixes and final revalidation”.

Current source dispositions are **7,673 included / 401 unresolved**; Pokémon rows
**723 / 98**; evolution/location comparisons **392 matching / 26 conflicting / 3
uncomparable**. About derives counts from generated coverage. The comparison and
source-uncertainty cautions in the original review still apply.

No ROM, translation bank or guide chapter was changed. No dependencies/assets were
downloaded, no emulator was run, and nothing was committed or deployed. The
unchanged guide PDF remains current. Preview remains available at
`http://127.0.0.1:4327/poke/` on the existing daemon, PID 35616.


## Subsequent player-guide presentation — 2026-10-09

The six resolutions above remain preserved in data and regressions. The user
requested a simpler player guide after the initial evidence-panel refinement.
Gameplay pages now omit technical panels entirely; original records, tests and
limitations are centralized on `/reference-sources/`. No factual correction was
rolled back or source disagreement silently resolved. Restricted tutors remain
visible without false zero learner counts; berry theft/prizes and Ursaring's
actual evolution remain correct. Stats, complete joins and comparison records
stay intact. The refreshed factual browser probe passes 120 assertions / 28
layout checks; compiled site tests pass 61 and Python tests pass 68. Full link
check: 4,651 pages, 594,509 links, zero broken. Full correction scope and visual
review are recorded in `website_completion_coverage.md`.
