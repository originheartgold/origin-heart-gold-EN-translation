# Findings from the tooling rollout

**Status (2026-10-09): historical.** The rc5 quality tools this note describes (qa_warning_inventory, review_site, the static text checks) were removed in the 2026-10-09 cleanup; the release gate is `check.py --full --strict-release` plus `--emu`. The findings below stay as the record; `git log --diff-filter=D -- work/tools` finds the scripts.

These findings concern the English artifact and test coverage. They are not original-hack bug fixes.
No ROM, translation bank, graphics asset or game code patch was changed during
this investigation.

## Static consumer and control coverage (2026-10-04)

The `text_static` developer gate now checks every message record in both the
existing candidate and a fresh workspace export, plus four known hardcoded
labels. Its per-string ledger explicitly retains unknown consumers and
unproven variable bounds. See the final consumer-contract validation in
[tooling_rollout.md](tooling_rollout.md).

(Resolved for rc5, 2026-10-04, D-1483: the 50 blanked entries are translated from
the Japanese with their codes kept, and 0616#37 is one 200% line again; the safety
check has 0 control failures.) New review items were 50 intentionally blanked entries (banks 0034/0035/0041/0267)
whose Chinese-hack unreachability is unproven, and the documented SIZE reset in
0616#37. These fail source-control preservation; they are not newly confirmed
game bugs. Existing QA ignores do not waive this independent check. Native
formatter inspection also establishes that variable-kind labels cannot supply
safe expansion bounds: runtime slots and their producers must be traced.

The current ROM and workspace differ in 28 banks. The gate checks both and
reports the mismatch. No translations or ROMs were changed by this QA phase.

## Current priority: faithful translation warning review (2026-10-04)

The user made the translation-warning backlog the project's highest priority.
The Chinese hack is the source of truth; QA must detect omissions, changed
quantities, names and meaning without modifying game behavior. Tooling rollout
completion did not mean the translation warnings had been accepted or resolved.
The original baseline contains 16,023 warnings on 13,271 strings, with zero
issues classified as errors. "Unchanged baseline" was not an acceptance waiver.

The first audit uses independent checker, number and glossary reviewers, plus
coordinator layout review. Every baseline warning is retained in an indexed
ledger. Classifications such as spelling equivalent, common-word collision or
unknown UI width are not blanket permission to suppress a warning. Corrections
to checker logic are tested against real mismatches; translations are unchanged.

### Translation-fidelity findings for editor/developer correction

| Ref | Finding | Required constraint |
| --- | --- | --- |
| a027/0038#73 | Source ordinal (third Pokemon) became a cardinal claim about three beings | Preserve the ordinal and the source's creator ambiguity; neighboring inscriptions are context |
| a027/0116#8 | Missing proposal to replace Machop with Machoke | Preserve both the workload complaint and proposed replacement; reply #9 argues against it |
| a027/0189#428, #429 | Explicit one-stage Sp. Def reduction omitted | Retain the stated 20%/10% chances and restore the magnitude |
| a027/0189#436, #437 | Explicit one-stage boosts omitted | Preserve both named stats and the one-stage magnitude |
| a027/0563#60 | Explicit critical-hit +1 magnitude omitted | Preserve D-0980's Air Cutter/Solar Blade source contradiction; do not alter the tutor |
| a027/0367#1 | Comparison with Route 29 omitted | Restore the named comparison; do not substitute neighboring Route 46 |
| a027/0137#12 | Three-Pokemon relay count omitted | Retain the 90-second duration and three participants |
| a027/0144#11, #12 | Three-circle choice loses its explicit count | Preserve the source's choice among three circles |
| a027/0106#57 | Chinese Single Battle became English Multi Battle despite a contradictory two-Pokemon/friend requirement | Review source fidelity; suspected hack contradiction recorded as D-1433, no gameplay fix |

The first eight rows cover eleven concrete fidelity omissions/changes. The last
row is a source-policy review rather than authorization to correct the hack.
Each needs text-only correction, contextual rereading, actual menu/box wrapping
and QA before acceptance. No proposed English has been applied by this QA task.

### Remaining review boundaries

The numeric audit covers all 1,022 baseline flags (834 strings). Written-number
matches remain candidates: a word such as "three" can be present while its
referent or ordinal meaning is wrong. Twenty-two team-count omission candidates
and other unresolved numeric cases remain open. Scoped digit rules D-0811 and
D-0825 must not be generalized into a ban on spelled-out numbers everywhere.

The glossary audit covers all 4,460 baseline flags. It identifies 304 reviewed
checker-noise cases, four exact provisional-decision exceptions, three legacy
move-name scope conflicts and 4,149 open cases. Not all reviewed exceptions are
encoded into automatic rules. Bind/Wring Out at a027/0003#1134–1136 corresponds
to move slot 378 and D-0012; relabeling it Bind based only on a modern substring
match is not justified. Common nouns and species-name substrings need context.

All 3,300 baseline layout/font/punctuation flags remain accounted for: 2,771
relative-width, 290 relative-line-count, 114 full-width punctuation/spacing,
86 source-also-multiline, 28 sentence/page breaks, nine terminal layout changes
and two font-dependent widths. Unknown UI dimensions require screen evidence.
For example, a027/0004#5 measures 760 px without explicit English newlines,
versus four source newlines; this is a high-priority rendering investigation,
not yet a confirmed in-game clipping finding. Ideographic alignment spaces must
not be globally removed (D-1299).

Detailed source-text evidence stays ignored under `work/build/qa-warning-audit/`:
`numbers/audit.json`, `numbers/summary.json`, `glossary/ledger.json`,
`glossary/HANDOFF.md`, and `layout/ledger.json`. The repeatable
`work/tools/qa_warning_inventory.py` reconciles baseline/current reports with
these indexed reviews, preserving duplicates and newly exposed warnings. Its
ledger explicitly grants no translation acceptance.

### First warning-audit validation and outstanding work

Final report: `work/build/quality/20261004T105139.806182Z/qa.json`.
268 tooling tests and 25 documentation tests pass with no skips/failures/errors.
Translation QA still checks all 76,862 strings in 821 banks, with zero errors
and **9,123 open warnings affecting 7,009 strings**. All 821 bank-file SHA-256
identities match the pre-audit snapshot: none of this reduction came from text
edits or new suppressions.

The exact reconciliation is 9,117 retained baseline warnings, 6,906 no longer
emitted after checker corrections, and six newly exposed warnings. Net reduction
is 6,900, not 6,900 accepted translations. The new cases are one trailing space,
three properly separated TM-price amounts (comma-grouped English numbers), and
two parts of a Chinese 600 split across a newline at a027/0792#240. These are
retained for review; token-boundary handling does not claim semantic inference.

| Current warning family | Count |
| --- | ---: |
| Glossary | 4,226 |
| Relative UI width | 2,771 |
| Missing-number checks | 1,024 |
| Whitespace | 573 |
| Relative line count | 290 |
| Other layout/font/punctuation | 239 |

All 573 remaining spacing flags also have per-entry review in
`numbers/whitespace.json`: 557 likely typography cleanup candidates, four
deliberate button separators supported by source formatting, and twelve cases
requiring fragment/alignment context. They remain open, not automatically trimmed.

The complete immutable-index reconciliation is
`work/build/qa-warning-audit/final/ledger.json`; its compact counts are in
`final/summary.json`. Baseline-indexed numeric, glossary, layout and spacing
reviews cover 9,354 baseline findings; every other baseline finding remains in
the ledger with its emission state, and every new warning is separately listed.
Detailed classification is not exhaustive semantic acceptance of those entries.

Next work stays on translation fidelity: contextual text corrections for the
eleven concrete findings above; explicit review of the D-1433 source contradiction;
then the remaining numeric/name candidates, menu wording constraints and actual
screen dimensions. No game-logic change is an acceptable way to resolve these
translation warnings. The earlier tooling hardening completion must not be used
as a claim that this outstanding translation review is complete.

## F001: blank English item descriptions

Status: fixed for rc5 (2026-10-04). The 17 descriptions were shortened to fit
the 114-unit buffer; the 2026-10-04 rc5 gate reports 0 buffer overflows and the
`bag_full` scenario passes with no rejected copies
(`work/build/rc5-release-check2/quality/report.json`). History below.

Original status: confirmed English regression; a guarded capacity check now fails it.
Game-data fixes require discussion with the user.

The `bag_full` scenario, using the unchanged `full_bag_6mons.sav` fixture, shows
Scope Lens's description in the Chinese ROM and a blank description area in the
English ROM. The difference persists in the `open` and `item_menu` screenshots.
The English Chain Logger description is visible in the separate `bag_townmap`
scenario, so the description area is not universally missing.

Evidence is local and ignored:

- `work/build/runtime-rollout-all/bag_full_zh_open.png`
- `work/build/runtime-rollout-all/bag_full_en_open.png`
- `work/build/runtime-rollout-all/bag_full_zh_item_menu.png`
- `work/build/runtime-rollout-all/bag_full_en_item_menu.png`
- `work/build/runtime-rollout-all/report.json`

The relevant description is `a027/0218#232`. Its Chinese text encodes to 24
16-bit units including the terminator; English encodes to 120. The longest
English description in bank 0218 also has 120 stored units. There are no variable
tags in this bank's English descriptions.

Runtime tracing on the unchanged ROMs confirms that the destination capacity is
114 units. Chinese copies 24 units and leaves a 23-character string. English
attempts to copy 120 units, takes the checked rejection branch, and leaves a
zero-length string whose first unit is the terminator. Allocation and heap
integrity checks remain clean.

The bag allocates this destination at overlay 17 address `0x021FD8CE`, file offset
`0x51EE`: `movs r0, #114`, followed by heap 6 and `String_New`. The bounded-copy
guard is at ARM9 address `0x02026ED4`. Another 114-unit allocation at `0x021FE0C4`
serves formatted menu text; it has not been implicated in this item-description
failure.

A read-only call-site audit found four direct item-description consumers: bag
(overlay 17, capacity 114), shop (overlay 3, capacity 114), overlay 9 (capacity
114, likely battle bag but screen context unconfirmed), and PC (overlay 16,
capacity 1024). Runtime
tracing also confirms the shop's 114-unit capacity. A bag-only capacity increase
would leave two affected consumers. The separate formatted-menu allocation is
excluded from the proposed change.

`text_buffer_check.py` reads capacity from the guarded allocation instruction and
checks all four consumers and the stored units, including terminators. On the current ROM and workspace,
it fails the same 17 descriptions: IDs 95, 97, 111, 218, 230, 231, 232, 233, 239,
245, 246, 288, 295, 314, 326, 352 and 389. All 791 Chinese descriptions fit; the
longest has 45 stored units. All 791 English ROM descriptions match the workspace.
The checker accepts a recognized future capacity change and refuses unrecognized
allocation or copy-guard code.

Additional ignored tracing evidence:

- `work/build/item_description_repro/runtime.py`
- `work/build/item_description_repro/zh_runtime.json`
- `work/build/item_description_repro/en_runtime.json`
- `work/build/item_description_repro/static_check_en.json`
- `work/build/item_description_repro/static_check_zh.json`

All 17 existing scenario pairs completed without allocation failures, low-address
writes or detected heap corruption. That result does not prove that text was
displayed: a checked copy can reject oversized input without corrupting memory.

The strengthened runtime detector now catches this failure directly. A paired
`bag_full` run on the unchanged ROMs observed 1,041 bounded copies per ROM.
Chinese had zero rejected copies; English rejected Scope Lens twice and Sticky
Barb once. Memory status passed, text status failed, and the unified runtime
gate correctly failed the new English rejections. Evidence:
`work/build/runtime-text-copy-bag-full/report.json`.

## F002: existing RC4 Chain Logger tile allocation defect

Status: fixed for rc5 (2026-10-04). The rc5 build's link-capture screen stays
within the 48 loaded tiles (highest 47) and the artifact gate passes
(`work/build/rc5-release-check2/quality/report.json`). History below.

Original status: confirmed, already documented; current source assets are corrected, but
the tested RC4 ROM and release packages retain the old graphic.

See [Graphics allocation audit](graphics_layout_audit.md). The current English
ROM has SHA-1 `7234f7b34933e0dc8902d1d079e4747490241a2d` and matches its existing
build report. Its `data/linkcapture.narc` screen member 25 references tile 74,
while the consumer loads only tiles 0–47 from character member 26. The Chinese
screen's highest reference is 46; the regenerated production asset's is 47.

The read-only artifact gate fails on this defect. Matching recorded graphics
hashes alone passes; the runtime allocation rule supplies the additional check.
The gate retains the failure rather than suppressing it or rebuilding the ROM.

Local unified report:
`work/build/quality/20261002T161736.946440Z/report.json`.

## Initial validation scope (historical)

The 17 scenario pairs ran 233,396 frames and 7,118 heap inspections, with 132
screenshots and no memory findings, skips or timeouts. Screenshots were
spot-checked, not exhaustively reviewed. Only the summary scenario currently
asserts its expected resource loads; the other scripts do not yet prove every
intended menu or interaction was reached.

The user's next-step decision is to investigate these findings and add regression
checks first, then discuss fixes before changing game data.

## F003: battle scenario does not demonstrate all claimed interactions

Status: test coverage gap, not a game regression. The scenario's clean memory
result must not be treated as proof that every interaction in its description
was reached.

The prior `battle_en_moves.png` shows the party-selection screen, not the move
menu. The `summary_switched` screenshot still shows the same Pokémon. The battle
fixture is `trainer.sav`, distinct from the two-Pokémon route fixture; its party
screenshot shows only one occupied slot. The `end` screenshot shows a party
action menu rather than evidence of the scripted fight.

The bag, party and summary screens have screenshot and resource-load evidence.
Pokémon switching, the move menu and the fight do not. Local screenshots and
the paired load-timing audit remain ignored under `work/build/runtime-rollout-all`
and `work/build/checkpoint-audit/prior_evidence.json`.

The user chose to leave battle coverage incomplete and strengthen other scenarios
first. Do not repair that script or alter its fixtures as part of this stage.

## QA handoff after hardening (2026-10-04)

The original five-point hardening plan now has implementations for non-battle
entry coverage, guarded Pokemon/party/move state assertions, raw text-copy
rejection detection, selected blank-description rendering checks, and automatic
input-integrity/emulator-environment evidence. See stages 10–15 of
[the rollout record](tooling_rollout.md) for final acceptance results and scope.
This replaces the initial coverage description above, not the known findings.

(Superseded 2026-10-04: F001 and F002 are fixed in the rc5 build; see their
status lines above.) At the time of this handoff, F001 remained a failing developer
acceptance check. Runtime checks independently
detect the rejected English copies and the blank Scope Lens description region;
capacity checks still identify all 17 oversized descriptions. F002 still fails
the artifact gate on the current ROM. Neither failure has been suppressed or
fixed by QA. Developers can run the candidate ROM through the same gates after
their changes, using its matching build report:

```sh
.venv/bin/python work/tools/quality_runner.py --checks text_static artifacts buffers runtime \
  --rom <candidate.nds> --build-report <matching-build-report.json> \
  --runtime-scenarios bag_full,bag_townmap,mart_full,summary,summary_full \
  --timeout 1200
```

That targeted acceptance run is not exhaustive gameplay certification. Rendering
checks prove selected-region presence only; save/reload persistence, additional
navigation assertions and deterministic clock/RNG control remain outside the
completed plan. F003 remains explicitly deferred pending the user's decision.

## Battle navigation follow-up (2026-10-04, approved warning follow-up)

The user subsequently authorized continuing all remaining investigations. The
battle script's final extra touch at (230,178) reopened the party screen just
before the intended Fight touch. Removing that touch reaches the actual
four-move menu. The corrected isolated Chinese and English runs show the move
menu, an attack/experience sequence, and return to the field. The existing
single-Pokémon save cannot establish active-Pokémon switching.

The corrected scenario now has temporal resource expectations for the bag,
party, summary, moves, attack and field-return intervals. Its description and
checkpoint names no longer imply that the one-Pokémon summary changed Pokémon.
These resource assertions are deliberately not promoted to exact battle UI
state assertions; screenshots remain supporting visual evidence. The scenario
therefore retains explicit coverage gaps until those state checks and a suitable
switching fixture are present. Evidence stays under ignored
`work/build/approved-warning-followup/investigations/`.

One exploratory Chinese run sampled a broken heap-5 free-list back link while
opening the battle bag. The identical repeat had 320 clean heap checks, as did
the English run. No allocation failures, null writes or rejected text copies
occurred. This non-reproduced observation is retained in the exploratory report;
it is not classified as a confirmed original-hack defect or an English regression.

A separate `trainer_2mons.sav` fixture was subsequently composed from the existing
valid two-Pokémon party and the trainer checkpoint, then saved by the native game
and reloaded. Original saves stayed byte-identical. `battle_switch` now exercises
SHIFT; screenshots show Caterpie replacing Blazor as the active battler. Its
ordered-party checks certify two valid slot identities, not the active battler.

The final combined paired repeat remained incomplete: English returned to the
field without the expected extra bank-38 NPC dialogue load, and Chinese had
reopened the party screen before the intended post-switch move-menu capture.
There were no memory/text findings. Those missing temporal expectations are
preserved in `investigations/battle-pair-final/report.json`; the earlier successful
captures do not erase them. The test needs state-driven navigation and a native
active-battler assertion before those coverage gaps can be closed reliably.
