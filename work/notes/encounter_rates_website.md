# ROM encounter rates on the website

User request, 2026-10-09: scan the actual ROM for all Pokémon encounters and
show their rates in the applicable website pages. The starter suggestions were
examples, not requested changes to the game's encounter tables.

The scan used the untouched `work/rom/origin_v4.0.3_cn.nds`, SHA-256
`4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`.
No ROM was built or modified.

## Coverage

- Ordinary encounters: all 149 records in `a/0/3/7`, mapped to the hack's actual
  locations using the existing map index. Unused/placeholder records are excluded
  by the existing docs reader; Pal Park's weekday mapping is retained.
- Headbutt: all 540 records in `a/2/5/2`, selecting maps with actual trees and
  retaining common, rare and special tree conditions.
- Safari Zone: all 12 area records in `a/2/3/0`, retaining area, method, time,
  level and whether object requirements apply.
- Bug-Catching Contest: the four sets in `data/mushi/mushi_encount.bin`.
- Calendar encounters: the existing reader of the ROM's eight date rules,
  excluding the unreachable rule on a map without land encounters.

The export contains 4,905 deduplicated rows across 560 species/forms:
4,121 percentage rows, 40 contest-weight rows and 744 rows without established
percentages. This includes seven calendar entries and 742 Safari candidates.
Species/form IDs stay separate; existing gifts, trades and evolution information
remain available independently of random encounter tables.

Examples checked against the ROM: Bulbasaur is level 5 at 1% during the day in
Fuchsia City's forest preserve; Charmander is level 5 at 1% in the morning in
Rock Tunnel. Their suggested Viridian Forest/Cinnabar placements are not in the
ROM and are not added to the website.

## Presentation and limits

The existing “Where to find it” section shows location, method/time/conditions,
level and rate, with a search filter for longer lists. Duplicate location summaries
and the separate wild-rate heading are removed; non-wild acquisition details remain. Location pages retain their existing percentage tables
and now also list Safari candidates. Item pages share the same encounter source
index, and no longer mislabel raw contest weights as percentages.

Percentages apply after an encounter occurs, for the listed method and conditions;
they are neither per-step probabilities nor catch rates. Radio, swarm and night
fishing rows describe replacement slots, rather than a recalculated combined
table. Safari's final odds depend on configuration and are not inferred from its
candidate list. Contest weights are reported as stored, without inferring odds.
Scripted wild battles remain item sources but are not assigned random encounter
percentages on Pokémon pages.

Regenerate with `python3 work/tools/site/export_data.py`. No downloads are needed
when the existing local ROMs, extraction inputs and website dependencies are present.

## Validation

- Website production build: 4,651 pages.
- Website tests, including built-page and complete encounter-index coverage: 70 passed.
- Encounter/held-item and Safari parser tests: 9 passed.
- Generated-data freshness check: no changes.
- Internal links: 599,075 checked, none broken.
- Ruff and `git diff --check`: passed.
- Browser checks: desktop and 390px mobile, light/dark layout, filtering, no-JS
  content and no page errors. Local screenshots are under
  `work/build/encounter-rates-qa/`.

## Follow-up: sortable base stats

The Pokémon listing now exposes HP, Attack, Defense, Sp. Atk, Sp. Def and Speed,
plus BST, as numeric columns. Each heading toggles lowest/highest first using
existing accessible sorting, filters and URL state. Values come from the same
ROM export as individual Pokémon pages, in the display order established by
`romdata.personal_stats`.

The list links to Jasmine’s rule because her fixed species list has exceptions
and cannot be inferred solely from the Defense column. No gym logic changes.
The production build, 12 focused encounter/sorting tests, link checks and browser
checks passed after the follow-up. Browser checks compare both sort directions
for each stat against all 1,440 exported Pokémon/forms and verify mobile layout.


## Follow-up: gifts and NPC trades

The existing “Where to find it” section now shows 62 acquisition sources across
58 Pokémon: 36 gifts, 4 Eggs, 11 trades, 6 prizes, 3 starter choices, one loan
and one loan return. Locations, levels, species and trade partners come from
the original ROM scripts/trade archive; reviewed story requirements and guide
links live in `work/tools/site/pokemon_acquisition_notes.json`. Each exported
source retains file/PC evidence. Repeated script paths merge without losing
that evidence. No gift encounter percentages are invented.

Bulbasaur’s Route 5 gift explicitly requires the Pikachu starter, the Cascade
Badge, and the shelter raid, with the refusal/story cutoff retained. Oak’s
starter choice is a separate source. Other starter-dependent gifts receive
the same treatment. Trade entries show what the player must give; prizes show
Coin costs; Eggs and loans are labeled separately. Evolution, fossil revival,
breeding and one-time-battle summaries remain; duplicate gift/trade summaries
and unrelated gift quest links are removed.

Two stored sources are excluded as unreachable: Pallet’s old Poliwhirl gift
(file 842 entry 9, no event calls it), and the alternate Goldenrod Sandshrew
prize. CN ARM9 command 495’s handler at `0x02044c6c` hardcodes version 7
(`movs r1, #7` at `0x02044c7e`); file 903 @1640 thus selects the Ekans menu
at 2940, not Sandshrew’s menu at 5277. They are also removed from area gift
lists. The fossil reviver’s unresolved GiveMon variable remains covered by the
existing fossil-table sources; no GiveTogepiEgg/GiveSpikyEarPichu opcodes occur
in the decoded script index.

New hack finding **D-2281**: the Route 10 Bellsprout seller asks for $5,000 but
never checks/deducts it (file 192 entry 2, subroutine 265, GiveMon at 312).
The website describes the actual behavior; the game is unchanged.

Validation: 73 website tests and 11 focused Python reader/index tests passed;
4,651 pages built; 599,139 links checked with none broken. The source-coverage
test checks every gift/Egg/trade area row against its Pokémon entry, including
trade direction, prizes, exclusions and Bulbasaur’s starter requirement.
Browser checks also passed on desktop/mobile in light/dark themes and with
JavaScript disabled; screenshots show the gift list and wild table under the
same heading. All six stat-column sorts still pass in both directions.


## Follow-up: Pickup items and rates

The read-only workbook audit confirmed all 22 item IDs and 220 rates against
fresh CN ROM bytes. The workbook mislabels ID 53 as Thunderstone; it is PP Max.
The website uses its existing canonical item names and does not depend on the
workbook or on scratch audit files.

`work/tools/site/pickup.py` now reads overlay 14 directly: IDs at 0x0224E3AC,
item-major weights at 0x0224E3D8, and the reviewed 10% gate instruction at
0x0222BD2A. It rejects a changed gate, duplicate IDs, truncated weights and
level-band totals other than 100. Exported `pickup.json` drives both the chart
and all 22 item sources, replacing the five manual Pickup source rows in the
website export without changing other acquisition sources.

The full ten-band chart lives at `/mechanics/#pickup`, linked from the Pickup
ability page and each item page. Item pages show only nonzero level ranges,
merge adjacent equal rates, and distinguish conditional item selection from
approximate overall chance (activation × selection). Mechanics explains that
30% becomes about 3% per eligible check, not 30% per battle. Bag deposit and
held-item behavior remain documented. No new claims about special-battle
eligibility or full-Bag handling are made.

Validation: 75 website tests, including every Pickup item at every level and
chart-to-item links, plus two synthetic parser tests passed. The build contains
4,651 pages; 599,332 internal links resolve. Generated-data freshness and Ruff
checks passed. Browser screenshots are in `work/build/pickup-website-qa/`.
Desktop/mobile light and dark checks passed with JavaScript disabled, including
native keyboard scrolling of the chart and PP Max's merged 51–70 level band.
