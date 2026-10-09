# Website source and page-family coverage

Completed phases 3–5 and all six Astra review fixes, 2026-10-09. Worktree: `codex/website-completion`.
This register records source accounting, content review and completed integration
validation below. It does not certify gameplay or a manual reread of every
generated row. Source/runtime evidence limits remain explicit.

## Source reconciliation

The three supplied EN workbooks retain their original SHA-256 identities in
`work/tools/site/reference_coverage.json`. All **8,074 nonempty data/note rows**
have distinct workbook/sheet/row identities; headers and blank rows are excluded.
The eight supplied screenshots are duplicate sheet representations. No workbook
or screenshot is copied into git. `reference_content.json` contains only useful
normalized English facts and attribution, using the existing translated source
survey where the EN Items workbook is mixed-language or mangled.

`included` means the row has an explicit disposition and its supported content is
accounted for, not that every claim was verified. `unresolvedFields` retains
runtime, acquisition, access and comparison limitations even on included rows.
There are **7,673 included and 401 unresolved rows**. Twenty-one included item
rows are explicitly documented unnamed reserved slots, with raw-slot evidence;
they have no useful gameplay notes and do not create invented usable items.

| Source sheet | Rows | Included | Unresolved | Comparison performed |
|---|---:|---:|---:|---|
| Pokémon Data | 821 | 723 | 98 | Canonical/form identity, six stats, types, ability slots, hidden ability and supplied evolution constraints |
| Move Changes | 56 | 53 | 3 | Type, category, power, accuracy, PP and known targeting meanings; effect prose remains author claims |
| New TMs | 55 | 40 | 15 | 38 item/move mappings and shop claims; 17 trailing map/location notes |
| Ability Changes | 59 | 59 | 0 | Canonical identity/alias and attributed claim retention; no runtime proof |
| Ability Applicability | 23 | 23 | 0 | 36 named move claims: 13 Mega Launcher and 23 Sharpness; flags kept separate |
| Map Overview | 142 | 114 | 28 | Configured encounter-method species sets/forms across candidate area tables |
| Encounter Index | 141 | 111 | 30 | Method sets, forms and configured species counts; candidate tables recorded |
| Encounter Details | 6,159 | 5,932 | 227 | Exact bank/method/slot/species/form against configured tables |
| Items (3.2 source sheet) | 618 | 618 | 0 | Usable item/tutor/legend/standalone/reserved dispositions; attributed field claims and known audit corrections |

Pokémon matching preserves gender symbols and canonical base identities, and
resolves reordered regional names and named forms without renaming game records.
The duplicated Greninja source identity resolves to Ash-Greninja using its exact
six stats and ability slots. Of 421 nonempty evolution/location claims, 392 match
supplied constraints, 26 conflict, and three remain uncomparable (Bent Key,
Sea Incense breeding and the dusk window). Calendar/native transformation claims
use the existing verified-mechanics register. A constraint match does not imply
that the source prose lists every requirement. Stats/types/ability differences
remain visible alongside configured data.

Encounter detail rows retain **47 mapped EN/configured conflicts** and **180
rows in five tables with no map reference**. The latter remain discoverable on
`/reference-sources/` without invented locations, levels or rates. Five index rows
also lack map references. The Map Overview label “Sootopolis Sea” has no supported
area mapping. Alias normalization covers route names and Seafoam cave/forest
labels; it does not turn a broad area match into a precise room or access proof.

All 38 new TM item/move mappings agree. Thirty-two source shop claims agree;
six EN shop claims differ (TM97/123/126: Goldenrod versus configured Saffron;
TM120/124/128: Lilycove versus configured Azalea). The source map locator
“Violet 500” names zone 500, which is configured Viridian; both values are shown.
Move conflicts include Skull Bash power, Cross Chop accuracy and Rock Wrecker
targeting; unknown effect semantics remain explicit. `before` remains null on
all change notes because no valid earlier-version comparison was performed.

## Reference content and evidence

All 769 named items retain readable game descriptions, configured source/use
links and availability reasons. Added English source material comprises 450
item summaries, 199 original-game source notes, two original-game use notes,
79 tutor rows, the rarity legend and the standalone trade-goods note. Legacy
source/repeatability notes are scoped to the original-game/older survey and are
not current-hack availability claims. Of 769 acquisition clauses, 531 have a
configured source in the stated area and 238 remain author-only; this comparison
does not verify story flags, weekdays, quantities or repeatability. Effects and
use restrictions remain game-text or author-note evidence unless an existing
specific audit supplies stronger evidence.

Thirty-three known item contradictions carry concrete configured corrections
where their notes appear, including the standard Poké Mart Quick Ball claim,
unreachable berry/held-item sources and the anti-aging spray recipe requiring Fresh
Water plus $10,000. Original-game acquisition prose is preserved with its scope,
not silently promoted to a hack claim. Item evolution, exact tutor-payment and
stored trainer-equipment links are separate; stored equipment is not an item
acquisition route.

The 79 source tutor rows attach to the actual configured taught moves, across
85 configured tutor entries. Seventy-five source move identities match and four
conflict: Psychic Noise/Poltergeist, Brave Bird/Sky Attack, Giga Drain/Mega Drain,
and Play Rough/Flail. The known Blackthorn Flail behavior remains intact. Fifty-
three cost claims match, three conflict, and 23 are conditional/uncomparable.
Sixty-nine places match the configured area. Ancient Power's EN Big Nugget versus
configured Rare Bone and Extreme Speed's EN Energy Drink versus Lemonade are
shown explicitly. Empty configured costs display Free; absent costs display
Cost unknown. Eligibility, access and vague prerequisites retain their source
scope. Trainers now label stored party/script evidence; no earlier-party baseline
exists, so no invented before/after hack-party changes are displayed.

Ability/move notes preserve all 56/38/59 rows and highlighted author changes.
Water Veil's Aqua Ring claim is shown beside game text covering burn immunity.
Bounce's two-turn description versus cleared charge flag carries the prior audit
conflict; the flag is not runtime proof. Existing #327 author alias, 23 Sharpness
claims plus nine other slicing moves, and 13 Mega Launcher claims remain intact.

## Existing findings versus EN source conflicts

The existing [spreadsheet cross-reference](spreadsheet_crossref.md),
[mismatch verification](sheet_mismatch_verification.md) and
[move audit](move_data_audit.md) primarily researched the older Chinese source
survey. Their exact evidence is reused for specific item/tutor/move corrections.
They are not blanket proof that the supplied EN workbooks agree. For example,
the older shop audit reports 38/38 agreement, while the EN workbook has the six
shop-name differences above. EN encounter row 33 names Rookidee where raw slot
731 is Pikipek; row 260 names Dusknoir where slot 356 is Dusclops. These are source
conflicts, not new proven hack bugs. Author behavior claims without decoded or
tested evidence are runtime unknowns; they are not unreviewed content or bugs.

## Page-family review register

| Family | Reference review performed | Remaining work |
|---|---|---|
| Items index/details (769) | Game effect text, English author/source scope, known contradictions, evolution/tutor/trainer links, source availability retained | Representative browser/filter QA complete; author-only runtime/repeatability limits above |
| Locations index/details (138) | Configured method/time/rate/level/form data retained; source discrepancies, local tutors, gifts/trades/calendar/items crosslinks | Representative browser QA complete; missing-map tables stay unassigned |
| Tutors index/detail panels | Actual taught move, cost/access/source conflicts, eligibility links; unknown costs explicit | Representative browser QA complete; conditional access cannot be inferred from area matching |
| Trainers/cards (1,023) | Stored party/script evidence and Pokémon/move/ability/item links | Representative browser QA complete; no old-party baseline |
| Pokémon details (1,440 records/forms) | Source identity/data/evolution comparison notes alongside configured rules | Representative browser QA complete; 98 source rows retain field conflicts/unknowns |
| Moves/TMs/abilities | Full author-note coverage, specific stale/conflicting descriptions, aliases/flags/evidence retained | Representative browser/filter QA complete; runtime claims remain unknown |
| Reference sources | Source hashes/counts, dispositions, trailing notes and all five unmapped encounter tables | Representative browser QA complete |
| Guide/static/credits/tool instructions | Phase 4 structured review of every chapter/quest entry; targeted full prose and existing audit checks; static prose and local tool instruction review below | Build/link and representative browser/filter QA complete; documented source/runtime limits remain |

## Validation

Focused Python comparator and battle-reference suites: 17 tests passed. Site
suite with built-page checks enabled: 44 passed. Template compilation built
3,628 pages successfully. The
importer check reports 8,074 rows unchanged; exporter check reports 13 files,
zero changed. Focused compiled-content checks cover the new source page, tutor discrepancies
and known item corrections. The existing Vite astro:head-inject warnings persist.
Final built-page/link/browser/filter validation after guide/static changes
is completed in Phase 5 below. No battle/capture tests, ROM edits,
translation edits, downloads, commits or publishing were performed.


## Phase 4 guide and static-content review (2026-10-09)

Method: enumerated every numbered chapter's quest entry and inspected its heading,
prerequisite/starter/gender/timing fields, warning/reward/retry/repeatability text,
with a second structured scan of conditions in steps and Notes. Checked the
README/index and known-issues regional consequences and warning index. Targeted
full prose/source reads covered discrepancies, existing review findings and the
reference links changed below. This is a structured content/consistency review,
not a fresh line-by-line translation review of all prose, re-decoding of all
scripts, complete playthrough, or blanket runtime verification. Long technical
source paragraphs were inspected separately where relevant. No chapter was
skipped. Existing detailed uncertainty statements and intentional hack behavior
remain; quest headings and explicit metadata match the pre-edit snapshot exactly.

The earlier October 4 chapter reviews, editorial review, Chinese-source reviews,
availability audit and current exported references were used as evidence leads.
They are dated, scoped evidence rather than proof of every current branch.

| Chapter | Entries | Actual review focus / change | Explicit evidence limits retained |
|---|---:|---|---|
| 01 Pallet–Pewter | 22 | Send-off closure; three starter thieves; Academy deadline; Pidgeot loan; confession/final-Hall-of-Fame distinction. Fixed contradictory “all three pay out the same way” above differing Ball rewards; linked Light Ball. | Romance shared-state/move-in limitations; directions and unplayed branches |
| 02 Pewter–Vermilion | 23 | Brock/Mt. Moon prerequisites; Ralts/Charmander/Cascade deadlines; shelter/burglary; Bicycle timing; one-shot Bruno; linked Helix Fossil. | Full fossil-restoration gates/leave-return/party requirements not established by the older source lead; no new walkthrough invented |
| 03 Vermilion–Celadon | 30 | Construction choice; S.S. Anne order/bomb risk; Gloom funds/eligible Pokémon; Lavender curse and repeatable Heart Scale trade; Magma Stone timing/link. | Source conflicts, Rock Tunnel loss freeze and unplayed optional branches retained; Heart Scale addition from earlier audit already present |
| 04 Celadon–Saffron | 37 | Grooming and Shota deadlines; marathon win/loss/White Flute; Snorlax/Birch; Lost-Pokémon required loss; takeover closures; linked Lucky Egg. | Pal Park never-ending show and Safari freeze stay documented; no gameplay fix |
| 05 Saffron–Cinnabar/islands | 38 | Dojo free-slot Charge versus Volt Switch; lab before Sabrina; Treecko Egg deadline; Articuno/TM14; Five Island Elder order, Mew and Latios/Latias; linked Volt Switch. | Crystal Onix one chance, unreplayed branch details and source-only directions stay scoped |
| 06 Sevii/Indigo | 27 | Granny Mae partner gate; Janine branches; Mystery Stone sale; pilgrimage/Six Island omission; biker bribe; Deoxys and Azure Flute; linked Miracle Seed. | Azure Flute postgame gift remains unreachable; no invented usable Arceus path |
| 07 League–Cherrygrove | 21 | First/final Hall of Fame; Cerulean Cave starter condition; rehabilitation; investigations; Berry Pots; Mewtwo deadline/confessions; linked Charizardite. | Story branch/runtime limits retained; no claim of all investigation paths played |
| 08 Cherrygrove–Azalea | 42 | Orphanage/Route 46/Sprout chain; Chikorita one chance; Marill; storm deadline; HM08 quiz closure; type-rule lists; linked Shell Smash. | Accepted-list quirks and reversed Green/Red dating gate remain explicit |
| 09 Ilex–Goldenrod | 28 | Bug hunt order/shared-state warnings; Houndour timing; one Shaymin/Celebi and return visit; recording/Plain Badge; romance central entry; linked Gracidea. | Untested complete romance paths and per-entry conditions retained; no global behavior guarantee |
| 10 Ecruteak–Olivine | 37 | Weekday contest; Ecruteak/Morty rule; Miltank round-3 gate; Gold deadline; beast-release warning; Jasmine Defense list; rod/Lighthouse; linked actual Flail. | Bug Contest prize identities still unconfirmed; specific prior tests are not exhaustive |
| 11 Cianwood–Mahogany | 25 | Amphy/Chuck gates; Close Combat conditional payment; Whirl payout; HM08/Mr. Pokémon deadline; expedition; Jirachi repairs; Lugia one chance; linked Close Combat. | Battle Tower partners unavailable; exact gameplay scope and shared-record warnings retained |
| 12 Lake of Rage–Sinjoh | 31 | Route 46 romance rescue; Rising Badge/Den; legendary prerequisites/one chance; Anti-Age Spray recipe; Wednesday gate; unavailable Sinjoh path; linked Outrage. | Distortion World table gives warp destinations, not a walked route; flute-gated events remain inaccessible |
| 13 Dungeons/common | 6 | Clefairy midnight repeat; chamber walls; Forest of Time maze; Wednesday reload; Badge/learned-move distinctions. Linked Cut, Surf and Fly detail pages. | HM-free scripted obstacles distinguished from learned party-menu moves; remaining paths not replayed |
| README | Index | Source wording scoped to quest evidence; new move/ability/TM/item/source links; starter and first/final Hall-of-Fame conventions retained. | Approximate directions and unplayed steps explicit |
| Known issues | Regional + common | Reviewed consequence/priority structure against chapter warnings; linked tested changed moves. Replaced stale “256”/excluded-system summary with current availability labels; corrected berry warning using expanded audit. | Harmless/unreachable content remains labelled; no suspected hack bug fixed or source discrepancy promoted to a bug |

All **367 numbered-chapter entries** were included in the structural pass. Counts
are current headings, not the older October 4 audit's 359-entry snapshot.

### Static pages and tool instructions

| Page/family | Actual review and changes | Limits |
|---|---|---|
| Home | Removed ROM-only framing; evidence card and reference-source entry; retained new moves/abilities/TM navigation | Final build/link QA complete; representative visual checks below |
| FAQ | Read story, patch, mechanics, nickname/evolution and generator answers; removed stale optional-speed-switch promise; narrowed old trade-evolution claim; added evidence/availability and battery-save workflow; Synchronize detail link | Exact combined shiny odds and unsupported gameplay paths remain explicit |
| Mechanics | Reviewed controls, EXP/EV, chains, allocator, charms, visible shinies, evolution/forms, item restoration/breeding, HM distinctions against existing verified-mechanics scope; new move/ability/TM crosslinks | No new runtime tests; existing exceptions remain |
| Calendar | Reviewed annual date, map-entry reload, 1% slot, time windows, Diancie fallback and unavailable Volcanion wording against existing test scope; source/ordinary-table crosslinks | Modifier interactions and unforced overall encounter rates remain untested |
| About/credits | Explained configured data / game text / author notes / specific tests, 8,074-row accounting (7,673 included; 401 unresolved comparisons), remaining runtime/access fields; expanded reference links; PokéAPI HOME/artwork attribution | No invented asset licence; original hack/v4/v3/hg-engine credits preserved |
| Contribution instructions | Generated-data description includes attributed notes/abilities/TMs; source-conflict reporting asks for label and row; footer claim scoped to guide/reference pages | GitHub account requirement preserved; no messages sent |
| Patcher | Compared `.nds`/ZIP, clean USA size/CRC/SHA checks, final SHA, worker/local-file behavior and site manifest against Patcher.astro + patch-tool; replaced live “latest” claim with patch published with site | No real ROM patched; no emulator/platform compatibility claim broadened |
| Save editor | Compared `.sav`/valid `.dsv` (512 KiB battery data), unsupported states, container-preserving export/Undo and badge-bit scope against save-container/save-import/app; added backup/export help in FAQ and empty state, corrected artwork README | Native load of created/edited records is not established; image/font requests are distinct from save uploads |
| Camera codes | Read full instructions; compared 17 presets, guard/address/constants, scopes and 4:3/16:9 toggle values with camera-codes.mjs and existing cheat test log; no code/prose correction needed | DeSmuME evidence stays scoped; melonDS/DS/TWiLight use untested |
| Site maintenance README | Source table now includes translated text/curated facts; importer/output ownership described | No new tool functionality or release changes |

### Narrow reference reconciliation correction

The old Saffron-shop audit note for Qualot/Tamato incorrectly said no reachable
v4 source existed anywhere, despite current configured Scratch-Off routes. Updated
only those two curated `reference_content.json` notes to scope the absent seller
to **Saffron** and mention the separate configured prize route; normal importer
and exporter regenerated facts/items. Known issues now distinguishes Qualot /
Tamato prizes, tested Salac / Petaya Trainer theft, and still-unsourced Apicot /
Lansat. Existing Scratch-Off and theft evidence comes from
`availability_audit.md` / `items_extra_sources.json`. Focused reference regression
asserts both the configured prize source and the narrowed note, preventing their
future contradiction. Original-game shop notes remain attributed older claims.

### PDF and focused verification

Regenerated all 15 guide pages and the ignored offline PDF with existing
Pandoc/Typst: **238 A4 pages, 3,474,800 bytes**. Rendered all 238 pages with Poppler,
visually inspected all 15 contact sheets for page flow/margins/table placement,
and inspected contents/intro (page 2) and the corrected berry warning (page 237)
at readable resolution. No clipping, overlap, blank accidental pages or missing
image was visible in that inspection. This is a layout/structure inspection,
not a full readable-size proofread of every PDF page. Technical Source paragraphs
remain excluded; web-only reference links become plain text because the local
build had no GUIDE_PUBLIC_URL. No PDF or source attachment added to git.

Focused results: 19 patcher tests and 9 reference-content tests passed;
`sync_guide.py --check`: 15 pages, zero changed; importer `--check`: 8,074 rows
unchanged; exporter `--check`: 13 files, zero changed; `git diff --check` passed.
All changed reference link paths resolve to exported record slugs/routes. A
pre/post comparison confirms all guide `##` headings and explicit quest metadata
unchanged. No broad build/browser/full-suite repetition here: final integration
subsequently completed compiled-page internal-link, base-path, URL/filter,
browser/layout and local CI-equivalent checks (Phase 5 below). Source/runtime
uncertainties remain distinct from this completed integration work. No blocking missing dependency,
download, ROM build/modification, translation edit, commit or publication.


## Phase 5: integrated implementation and final QA (2026-10-09)

Implementation and planned QA are complete. Index searches, all select/checkbox
filters and sorting are URL-backed. One index uses `q`, filter `data-key` names
and `sort=<zero-based column>-asc|desc`; multiple tables namespace keys with
`<table-id>.`. Values combine with AND, and pipe-separated row attributes match
individual tokens. Invalid values use defaults. Reset clears owned state and
restores original row order, retaining unrelated parameters and hashes. Typing
pushes one meaningful state per edit session, replacing subsequent keystrokes;
leading whitespace does not overwrite the initial Back state. Select/sort/Reset
changes push distinct states; Back/Forward restore controls, rows and ordering.
Sort buttons work with Enter/Space, numeric columns sort numerically, equal keys
retain original order, headers expose `aria-sort` and counts announce sorting.
Live counts and explicit empty results accompany Reset. All content remains
accessible without JavaScript. Filtering owns direct table-body rows or outer
list records, avoiding nested party-row counts/reparenting.

Legacy `/moves/#move-N` and `#tm-list` links remain reachable. Explicit filters
stay AND: a filtered-out anchor target requires Reset; a fragment does not override
an explicit filter. This is navigation semantics, not an evidence uncertainty.
Quest setup/completion localStorage and the technical-source toggle still work.

All move and ability details now have an explicit Changes section/TOC entry.
Absent comparisons state that no change is documented, without implying unchanged
behavior. Sharpness's highlighted applicability additions have their own truthful
summary/link and qualify for the index's changes/additions filter; unhighlighted
applicability alone does not qualify.

The fresh link scan identified 2,547 item-equipment links targeting ordinary teams
absent from the curated trainer index. Added 1,023 small `/trainers/records/<id>/`
reference pages using the existing party card and encounter evidence; item links
now use the exact record route. Curated guide-order sections and legacy trainer
anchors remain. Teams without identified scenes explicitly retain unconfirmed
availability; stored equipment is not an acquisition source.

The requested generator check initially found 17 stale tracked outputs (16 generated docs and their crossref)
within the 18-output docs family, including trainer/encounter/availability
organization. Refreshed mechanically with existing readers;
the large documentation diff is a baseline catch-up, not newly authored prose or
new gameplay research. `.gitattributes` scopes `whitespace=-blank-at-eol` to
`work/docs/*.md` because the generator deliberately emits two-space Markdown hard
breaks. All other whitespace checks remain enabled. Local dependency symlinks and
QA artifacts are ignored. No download/install or source-asset acquisition occurred.

### Phase 5 outcomes (before the Astra review fixes)

| Check | Exact outcome |
|---|---|
| `python3 work/tools/site/build.py --check` | 18 docs, 13 data exports and 15 guide pages: zero changed after mechanical docs refresh |
| Supplied-workbook importer `--check` using local attachments | 8,074 rows unchanged |
| CI no-ROM Python suites, including comparator/battle-reference | 63 passed; numeric fixtures/local committed facts; no workbooks/ROM needed in CI |
| Production Astro build with `GUIDE_BASE=/poke/` | 4,651 pages; success; existing Vite astro:head-inject warnings only |
| `GUIDE_TEST_DIST=1 npm --prefix site test` after final build | 53 passed, zero failed/skipped; compiled all-record changes sections/equipment references and 7 production-JS DOM regressions included |
| `npm --prefix work/save-editor test` with existing compiler path | TypeScript build + 54 synthetic tests passed; local dependencies had no `.bin`, so an ignored compiler shim was used |
| Primo reference encoder | 720,896 passwords, zero mismatches/data problems |
| Full `check_site.py --base /poke/` | 4,651 pages, 598,895 links, zero broken |
| Installed Chromium browser smoke | 221 assertions passed; 52 mobile theme/page checks across 26 representative routes; zero uncaught page errors |
| `git diff --check` | Passed with the narrowly scoped intentional Markdown hard-break rule above |

CI now includes the comparator/battle-reference Python suites. Site tests run after
Astro build with `GUIDE_TEST_DIST=1`; existing save-editor and Primo checks remain.
The optional browser runner is `site/tests/browser-smoke.mjs`, using existing
Playwright via `PLAYWRIGHT_MODULE` and `GUIDE_PREVIEW_URL` (no installed dependency
or CI download added). Its saved detailed layout results are ignored.

Browser coverage includes the Pokémon/moves/abilities/TM indexes, combined
multivalue and hidden-ability filters, query reload/invalid/reset/empty cases,
Back/Forward, stable signed numeric sorting and Enter/Space; base Bulbasaur,
Mega Venusaur and Mew; Sharpness, Mega Launcher and unnamed #327; Water Gun and
Luster Purge conflicts; TM93 and unavailable TM46; reference sources; Qualot/Tamato
Scratch-Off versus absent Saffron seller notes; known issues; items/locations/tutors/
trainers and ordinary stored team #105; About/patch documentation. All 26 routes
were checked at 390×844 in light/dark for page overflow and clipped filter controls,
and representative desktop/table/evidence screenshots were visually inspected.
Actual base/form/Mew hero images rendered with explicit dimensions; blocked primary
and fallback URLs produced an accessible unavailable placeholder. All 1,440/920/
327/138 index rows and the hidden-holder list remained accessible with JS disabled.
No-JS reference navigation blocks remote resources and uses DOM-ready timing.

Camera preset/flat/reset/copy controls, save-editor theme/open/disabled export and
synthetic invalid-save rejection, quest setup/completion persistence and `tech=1`
passed. The local patch build has no release payload: its manual fallback was
inspected, then a synthetic manifest enabled the invalid-file worker rejection
check. No valid ROM was supplied, patched, constructed or downloaded. These checks
do not claim real patching, valid edited-save native gameplay or emulator tests.
No browser case was skipped in the final successful run. Earlier test-fixture
assumptions/navigation timing were corrected; no unresolved browser failure remains.

Preview: `http://127.0.0.1:4327/poke/`, Astro preview daemon PID **35616**.
Astro 7 daemonizes preview: the launcher exited successfully and has no ongoing
exec session ID. The browser used this running daemon through final validation.
Ignored screenshots and results under `work/build/website-qa/`:
`pokemon-mobile-light.png`, `water-gun-mobile-dark.png`, `sharpness-desktop.png`,
`browser-results.json`. The previously verified 238-page PDF remains at
`site/public/downloads/origin-heartgold-guide.pdf` (3,474,800 bytes), served in the
preview at `/poke/downloads/origin-heartgold-guide.pdf`; no unnecessary PDF rebuild.

### Remaining evidence limits

The **401 unresolved source comparisons** remain explicit source/configuration or
mapping/field limitations, not unfinished UI work. The **7,673 included rows** are
accounted-for dispositions, not universal runtime proof. Additional author-only
claims exist within included rows, including 238 item acquisition clauses without
a configured same-area source, conditional access/repeatability, tutor restrictions,
unknown effect/target semantics and author ability interactions. No before-values
or baseline behavior were invented. The 367-entry guide review remains structured
plus targeted prose/evidence review, not a 96k-word line-by-line retranslation or
full playthrough. No ROM edits/builds, translation changes, emulator/runtime
reverse engineering, commits, push or publishing were performed.


## Astra review fixes and final revalidation — 2026-10-09

All six P2 findings in `website_astra_review.md` are addressed at their source.
The original review evidence remains in that report; its resolution section and
this section supersede the earlier validation totals and source dispositions.
No game behavior, ROM, translation bank or guide chapter was changed. Existing
uncommitted work was preserved; no download, installation, commit or deployment.

1. `romdata.parse_move` decodes byte 19 with signed `s8` semantics (native getter
   LDRSB at `0x0201A3EE`). Negative values −25/−33/−50 remain signed in raw exports
   and render as HP loss/cost fields with basis and timing explicitly undecoded.
   Positive healing remains separate. The docs regeneration found no downstream
   Markdown changes; only the site summaries/technical records use this field.
2. Stat-change summaries omit probability for a zero chance field; they neither
   say 0% nor infer universal 100%. Raw values and genuine nonzero chances remain.
   Compiled-page regressions scan every move, Pokémon and item page for the old
   false zero/healing sentences, including learning tables.
3. Known tutor sources render independently from enumerated learners. Headbutt,
   Frenzy Plant, Blast Burn, Hydro Cannon, Charge and Surf retain place, cost,
   quest, warning and author notes. All six participate in the Tutor filter.
   Script-specific eligibility stays explicitly unenumerated and adds no invented
   species to the learner count. Empty learner tables are omitted.
4. Salac/Petaya corrections now reject only the obsolete Celadon shop source and
   point to their existing configured theft routes and separately recorded berry-
   retention emulator tests. Qualot/Tamato corrections and the separate unresolved
   Apicot/Lansat source cases remain intact.
5. New curated `move_tested_notes.json` records scoped existing results for Volt
   Tackle, Blast Burn, Lunar Dance and Bounce, with method/provenance and a link to
   the guide's existing test section. Conflict fields remain. The three stale
   blanket requests for a test were replaced with scoped uncertainty; Frenzy Plant,
   Hydro Cannon and Rock Wrecker still explicitly require tests. Author claims are
   described separately from these recorded results. No fresh emulator test was run.
6. Evolution comparison retains explicit use, holding and level-up-holding
   operations. Bare item claims still supply item identity without inventing an
   operation. All eight operation-bearing source claims were inspected: five
   comparisons now carry explicit constraints, two native transformations remain
   governed by the existing transformation matcher, and Sea Incense breeding stays
   uncomparable. Only Ursaring changes disposition. About now derives its public
   totals from the generated coverage JSON rather than hardcoded prose.

### Complete changed-operation review

| Pokémon sheet row | Record | Explicit operation | Result after fix |
|---|---|---|---|
| 232 | Ursaring #217 | Use Moon Stone at night | Conflict with level-up-holding; included → unresolved; new visible author discrepancy |
| 493 | Leafeon #470 | Use Leaf Stone | Still matches both configured incoming use-stone edges |
| 494 | Glaceon #471 | Level up during day holding Never-Melt Ice | Evolution still matches; row remains unresolved for other existing fields |
| 568 | Hisuian Lilligant #1361 | Hold Black Belt during day | Supplied hold/time constraints still match; no inferred complete rule |
| 775 | Perrserker #863 | Meowth holding Metal Coat during day | Supplied hold/time constraints still match; row remains unresolved for other existing fields |

Current totals: **8,074 source rows; 7,673 included, 401 unresolved**. Pokémon
sheet: **723 included / 98 unresolved**. Evolution/location claims: **392 matching,
26 conflicting, 3 uncomparable** of 421. All source hashes/identities are unchanged.
No other coverage comparisons changed. Generated facts affect five site outputs:
`moves`, `species`, `items`, `battle_notes` and `reference_coverage`.

### Final checks and reproducible commands

Run from the isolated worktree root. The Python workbook importer uses the existing
bundled openpyxl runtime; all workbook reads remain bounded and read-only.

```sh
python3 -m unittest work/tools/docs/test_gen_docs.py work/tools/docs/test_trainer_guide.py work/tools/docs/test_trainer_runtime.py work/tools/site/test_wild_held.py work/tools/site/test_safari_held.py work/tools/site/test_reference_compare.py work/tools/site/test_battle_reference.py
/Users/simonvergauwen/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/tools/site/reconcile_references.py --source-dir /Users/simonvergauwen/Downloads --check
python3 work/tools/site/build.py --check
GUIDE_BASE=/poke/ npm --prefix site run build
GUIDE_TEST_DIST=1 npm --prefix site test
python3 work/tools/site/check_site.py --base /poke/
PLAYWRIGHT_MODULE=/Users/simonvergauwen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs node site/tests/review-fixes-browser.mjs
git diff --check
```

| Final check | Result |
|---|---|
| CI Python suites | **68 passed** |
| Fresh production build | **4,651 pages**, successful; existing Vite head-injection warnings only |
| Site tests against built HTML | **58 passed**, zero failed/skipped |
| Full internal link audit | **598,911 links**, zero broken across 4,651 pages |
| Deterministic content check | **18 docs, 13 JSON outputs, 15 guide outputs unchanged** |
| Workbook reconciliation repeat | **8,074 source rows unchanged** |
| Focused Chromium review-fix probe | **177 assertions**, **62 mobile light/dark containment checks** over 31 navigations / 27 distinct paths, no uncaught browser errors; external requests blocked |
| Whitespace | `git diff --check` passed |

The focused browser script is retained at `site/tests/review-fixes-browser.mjs`;
results are ignored at `work/build/website-qa/astra-fixes/browser-results.json`.
Initial new test-fixture assumptions about linked item markup, existing price
formatting, theft source field placement, and exact zero-versus-10% matching were
corrected; there is no skipped or unresolved test failure. Existing save-editor
and broad tool/browser suites were not repeated because these fixes do not change
those implementations; their earlier scoped results remain recorded above.

Preview verified serving the new build at **http://127.0.0.1:4327/poke/**,
existing daemon **PID 35616**. Guide Markdown did not change in this fix pass, so
its existing 238-page PDF remains current without a refresh. Remaining uncertainty
is source/gameplay evidence: unknown restricted compatibility, HP basis/timing,
untested conditions/related moves and the explicit 401 unresolved source rows.

## Player-focused reference presentation — 2026-10-09

The default reference pages now explain gameplay for players: move stats/effects,
learning routes, ability holders/interactions, item uses/acquisition and tutor
requirements. Repeated decoding, export, configured-field and universal-test
boilerplate was removed from the default reading flow. This is a presentation
change; no parser, comparison, game behavior or translation was changed.

- Shared move stats show plain effect notes, a player-friendly unknown target and
  only relevant power/accuracy legends. Priority explanation belongs in About.
  Raw flags, effect IDs, signed HP cost fields and original configured summaries
  remain in closed source panels. Disputed effects are not promoted to advice;
  negative HP fields with unknown basis/timing are not given invented percentages.
- Four existing move results have curated `playerSummary` and `limitation` fields.
  Volt Tackle retains its KO context, Blast Burn/Lunar Dance their wild-battle
  context, and Bounce its one-turn outcome plus stale-description warning. One
  concise limitation is visible; original protocols, controls, method, both-ROM
  evidence, unresolved fields and guide links remain expandable. Related moves
  without tests still have a visible uncertainty warning.
- Water Gun/Luster Purge stale descriptions, author stat/payment/shop differences,
  restricted-tutor eligibility, current berry routes and Ursaring's use-versus-hold
  evolution disagreement stay visible in useful language. All six restricted
  tutors remain discoverable without invented compatible Pokémon or counts.
- Author wording, workbook cells/rows, comparison fields and prior audits remain
  in source details. Ability applicability distinguishes the author's 23 Sharpness
  moves from nine other possible slicing moves; battle uncertainty stays explicit.
- Pokémon, move, ability, TM, item, tutor and trainer introductions help players
  browse. Home and mechanics reference links use the same language. Calendar
  tables show dates, places and practical restrictions while keeping full test
  notes closed. Artwork keeps linked PokéAPI attribution and explicit mismatching
  base-form art labels; URL/fallback pipeline details are closed.

`move_tested_notes.json` was updated and `export_data.py` regenerated **only
moves.json**. Existing data/evidence contracts were extended, not replaced. The
8,074 source rows and all prior source dispositions are unchanged. Existing guide
chapters and PDF did not change in this pass. Nothing was downloaded, installed,
committed or deployed; no ROM, save, translation bank or hack behavior was edited.

| Final check | Result |
|---|---|
| CI Python suites | **68 passed** |
| Final `/poke/` production build | **4,651 pages**, successful |
| Compiled site regression tests | **61 passed**, no failed/skipped tests |
| Complete internal link audit | **600,351 links**, zero broken |
| Generated content freshness | **18 docs / 13 JSON / 15 guide outputs unchanged** |
| Updated six-fix Chromium suite | **183 assertions / 62 mobile checks**, no browser errors |
| Player presentation Chromium suite | **239 assertions / 88 desktop/mobile light/dark checks**, no browser errors; native source disclosure and four complete no-JS catalogs checked |
| Whitespace | `git diff --check` clean |

Browser scripts block all external requests; artwork checks in this pass use the
local fallback layout rather than testing remote availability. Final screenshots
of Blast Burn, Sharpness, Salac Berry and Ursaring at desktop/mobile sizes and
light/dark themes are in ignored `work/build/website-qa/player-reference/`. Agent
and coordinator inspected meaningful viewports. Playwright used the pre-existing
module at `/Users/simonvergauwen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs`.

Reproducible presentation checks (run from the isolated worktree root):

```sh
GUIDE_BASE=/poke/ npm --prefix site run build
GUIDE_TEST_DIST=1 npm --prefix site test
python3 work/tools/site/check_site.py --base /poke/
python3 work/tools/site/build.py --check
PLAYWRIGHT_MODULE=/Users/simonvergauwen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs node site/tests/review-fixes-browser.mjs
PLAYWRIGHT_MODULE=/Users/simonvergauwen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs node site/tests/player-reference-browser.mjs
```

The new test fixtures initially used an overly broad zero-chance regex and an
unscoped nested-source selector. Both fixtures were corrected; the final passing
runs above contain no skipped or unresolved failures. No workbook reimport or
emulator run was needed for this presentation-only pass. Remaining limits are the
existing source uncertainties, not hidden claims of universal verification.


## Plain player guide correction — 2026-10-09

This supersedes the preceding "Player-focused reference presentation" approach.
The user's follow-up rejected research commentary even in collapsed panels on
ordinary gameplay pages. Presentation now separates the ordinary player guide
from the existing central `/reference-sources/` research page.

### Presentation and preserved information

- Move pages have one current Effect paragraph, ordinary stats, concrete
  highlighted change values where supplied, ability interactions and complete
  learning routes. Blast Burn says: "Unleashes a blast of flame with a 10% chance
  to burn the target. Attack again on the next turn—no recharge needed."
  Its change list shows the source-highlighted Power: 100, without an invented
  before-value. It leads with its tutor rather than a misleading zero learner
  count. Volt Tackle retains the wild-KO condition; Lunar Dance and Bounce have
  concise practical effects. Original game, author and tested paragraphs no
  longer repeat the effect on the same gameplay page.
- Water Gun and Luster Purge show their current usable effects instead of the
  stale Scald/Moonblast descriptions, with a brief outdated-description note.
  Unknown target fields are omitted. The legacy `#description`, `#changes`,
  `#move-N`, `#tm-list` and other browse/detail anchors remain stable. Ability
  interaction TOC entries and rendered sections use the same condition.
- Ability pages/indexes and Pokémon ability summaries use normal readable effect
  wording. Added moves remain marked separately; Sharpness's nine additional
  possible moves stay distinct from its 23 listed moves, without flag terminology.
  Water Veil retains the specific uncertainty about added Aqua Ring healing.
- Pokémon, item, TM/HM, tutor, trainer and location pages retain statistics,
  full learning/compatibility lists, acquisition, costs, conditions and practical
  availability reasons. All provenance panels, raw JSON, record ID explanations,
  evidence badges, comparison boilerplate and test narratives are removed from
  gameplay HTML, including closed details. Useful shop/team/list expanders remain.
- Six restricted tutors remain discoverable and retain the unknown compatible
  list, actual costs and quest/location requirements. Salac/Petaya keep Thief or
  Covet instructions and holding the berry after battle; Qualot/Tamato retain
  Scratch-Off prizes. Ursaring displays only level-up holding Moon Stone at night,
  without presenting the contradictory use-stone operation as an alternative.
- Form artwork says "Artwork shows [Pokémon]’s standard form." Existing availability
  and evolution notes retain actual bugs, time windows and acquisition gates;
  their emulator/code commentary is removed only by presentation helpers.
- Home, FAQ, calendar and mechanics introductions/instructions use ordinary guide
  language. Detailed prior mechanics/calendar commentary is retained centrally.
  About and the source reference continue to explain sourcing. No quest chapter
  retranslation, guide source edit or PDF rebuild was needed.

The central research page now retains original move descriptions, author notes,
raw effect fields, full scoped tests and limitations, ability applicability,
Pokémon evolution/source differences, item effects/acquisition/older source notes,
tutor comparisons, encounter differences, and calendar/form research. No new audit
routes or downloads were added. Normalized/curated records and all six prior
parser/data/comparison fixes remain intact; this pass changed presentation code
and static website copy, not generated game/reference data or source dispositions.
The original 8,074 workbook identities and 7,673/401 dispositions remain unchanged.

### Final validation

| Check | Result |
|---|---|
| `GUIDE_BASE=/poke/ npm --prefix site run build` | 4,651 pages; successful, existing Vite head-injection warnings only |
| `GUIDE_TEST_DIST=1 npm --prefix site test` | 61 passed, zero failures/skips; prior factual assertions retained and their research expectations moved centrally |
| Existing Python data/parser/comparator suites | 68 passed |
| `python3 work/tools/site/build.py --check` | 18 docs, 13 data exports and 15 guide pages: zero changed |
| `python3 work/tools/site/check_site.py --base /poke/` | 594,509 links, zero broken |
| `player-reference-browser.mjs` | 349 assertions, 104 desktop/mobile light/dark layout checks, zero browser errors; complete no-JS catalogs and central native research details |
| `review-fixes-browser.mjs` | 120 factual assertions, 28 mobile layout checks, zero browser errors |
| All compiled gameplay pages, including closed details | Zero audit panels/raw records; zero configured/decoded/audit/tested/recorded/source-comparison/author-claim/effect-field wording in moves/abilities/items/Pokémon/locations/tutors/trainers main content |
| `git diff --check` | Passed |

The initial link-check invocation used the checker's default `/` base on a `/poke/`
build and therefore reported 535,772 false missing-page links. A retry setting
`GUIDE_BASE` alone had the same setup mismatch: the checker reads its `--base`
argument, not that environment variable. The corrected `--base /poke/` run above
passed. This was a validation setup error, not a product link defect.

Fresh screenshots and results are ignored under
`work/build/website-qa/plain-player-guide/`: Blast Burn, Sharpness, Salac Berry and
Ursaring at 1440/390 widths in light/dark themes, plus `browser-results.json`.
The coordinator visually reviewed Blast Burn desktop/mobile, Sharpness desktop
and Salac mobile and approved the plain-player presentation. The implementation
agent also inspected Blast Burn desktop/mobile. The factual probe's current
results remain at `work/build/website-qa/astra-fixes/browser-results.json`.
Preview remains `http://127.0.0.1:4327/poke/` (existing daemon PID 35616).
No downloads, installs, gameplay research, ROM/translation changes, commits or
publication; the original dirty checkout was untouched.

## Original move comparisons restored — 2026-10-09

This supersedes the preceding correction’s overly sparse move Changes sections.
Gameplay pages retain complete current effects, stats and learning methods, with
short original-versus-hack comparisons and no research panels. Blast Burn now
shows Special → Physical, power 150 → 100, accuracy 90% → 100%, PP 5 → 10, removal
of recharge and the added 10% burn chance. Current Effect remains complete.

An explicit optional importer reads the existing untouched USA HeartGold ROM
(CRC32 C180A0E9) without changing it. Its normalized, deterministic numeric
facts cover original move IDs 1–467. Record 0 and trailing records 468–470 are
excluded. No original descriptions or ROM bytes were copied into the repository.
CI and ordinary exporters use the normalized input, without new local-ROM or
workbook requirements. Reimport to `/private/tmp` matched the normalized file
byte for byte. Existing source workbooks and their 8,074 dispositions are unchanged.

`move_comparisons.py` compares type, category, power, accuracy, PP, signed priority
and known target meanings, normalizing equivalent 0/101 accuracy sentinels and
the differing target enums. The original type #9 is `???`, verified from the local
US type bank; Curse’s change to Ghost is retained. Project-written effect notes
in `move_change_notes.json` keep author/configured/tested evidence separate.
Blast Burn’s tested recharge removal and configured burn chance use separate
entries; untested recharge removal is not asserted for Hydro Cannon, Frenzy Plant
or Rock Wrecker. Volt Tackle keeps its wild-Pokémon KO condition.

All 56 supplied move-change rows have concrete numeric, effect or uncertain
comparisons. Luster Purge is included despite absent workbook highlights: power
70 → 95 and Sp. Def drop chance 50% → 30%. Dragon Claw’s stats are unchanged;
its advertised critical-hit boost is explicitly unconfirmed, and the Effect
section no longer states that boost as fact. It remains discoverable among change
notes. Play Rough has only “Accuracy changed to 100%”, without an invented
pre-HG baseline. New TM notes alone do not classify a move as modified. The same
comparison records drive detail pages and the changed filter: 152 entries
(151 original moves, including the uncertain Dragon Claw claim, and Play Rough).

Validation after the final implementation:

| Check | Result |
|---|---|
| CI Python suites, including four new original-table tests | 72 passed; no ROM required |
| Production build, `GUIDE_BASE=/poke/` | 4,651 pages; successful |
| Compiled site tests, `GUIDE_TEST_DIST=1 npm --prefix site test` | 64 passed, zero skipped |
| `python3 work/tools/site/build.py --check` | 18 docs, 13 data files, 15 guide pages unchanged |
| `python3 work/tools/site/check_site.py --base /poke/` | 594,509 links, zero broken |
| Local player-browser regression | 402 assertions, 116 desktop/mobile light/dark layout checks, no browser errors |
| Optional local original-fact reimport + `cmp` | Identical normalized facts |
| Whitespace | Clean |

Regression coverage checks Blast Burn values/effects, Bounce’s one-turn change,
Lunar Dance’s purpose, Luster Purge without highlights, unchanged Water Gun versus
its stale description, missing later-move baselines, uncertain Dragon Claw,
TM-only notes, and exact agreement between the changed filter and displayed
comparisons. Browser checks include filter reload, complete no-JS catalogs and
no-JS Blast Burn comparisons. All six earlier Astra fixes remain covered.

Fresh screenshots/results are under ignored
`work/build/website-qa/plain-player-guide/`. The implementation agent and
coordinator visually approved Blast Burn desktop/mobile and Luster Purge mobile.
Representative paths: `moves-blast-burn-1440-light.png`,
`moves-blast-burn-390-light.png`, `moves-luster-purge-390-dark.png`; additional
Bounce/Lunar Dance screenshots cover both sizes/themes. Preview remains
`http://127.0.0.1:4327/poke/`, existing daemon PID 35616.
No downloads, installs, new emulator research, ROM or translation changes, commits
or publication. The original dirty checkout was untouched.
