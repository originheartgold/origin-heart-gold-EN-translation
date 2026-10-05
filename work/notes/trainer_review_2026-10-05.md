# Trainers page review — 2026-10-05

## Result

Reviewed and corrected the documentation pipeline and Trainers page against the untouched Chinese v4.0.3 ROM. No ROM was changed or built, nothing was downloaded, and nothing was committed or published. Existing unrelated workspace changes were preserved.

Three subagents independently reviewed team data/runtime interpretation, encounter context, and page organization. Their evidence is in [runtime review](trainer_runtime_review.md), [encounter review](trainer_context_review.md), and [presentation review](trainer_page_review.md). The presentation report records the initial findings; the fixes below supersede its outstanding recommendations.

## Applied corrections

- Gym challenges now follow the walkthrough: Kanto (Brock, Misty, Lt. Surge, Erika, Koga, Blaine, Sabrina, Giovanni), then Johto (Falkner, Bugsy, Whitney, Morty, Jasmine, Chuck, Pryce, Clair). This is guide order, not a proven mandatory prerequisite chain.
- Initial challenges are separated from other leader encounters, rematches and partner appearances. Whitney's two challenge variants remain represented without duplicating her reused singles team. All Misty appearances share the leader grouping, while the exact in-game class stays on each card.
- Added missing named records for Red, Silver, Copycat and Rocket Elites. All 226 featured records render once. Unlocated named records appear in an explicitly unconfirmed section; the complete 1,023-team roster remains in generated trainers.md and trainers.json.
- Blue's obsolete Viridian Gym script is marked inactive; his lodge battle remains. Giovanni is the initial Viridian Gym opponent, and Blue's later Gym rematch remains available.
- Added 17 memory-rematch opponents, each with single and same-team double battle contexts, after the final Hall of Fame. Explained Janine's disguise in the extra Koga trial battle.
- Corrected 21 Pokémon form fields, 1,129 EV displays, and HP IV reporting for all 3,891 stored party slots by following the original trainer loader and stat calculator.
- Clarified generated natures, default moves and default abilities; marked the species-zero placeholder. Held-item links now lead to item pages when available. Partner-only cards are labelled and technical record IDs are hidden with the site's existing technical-source mechanism.
- Misty's Gym Starmie remains level 20, Illuminate, Wise Glasses. Its stored item is 267; misses alone do not establish Bright Powder. The original Illuminate description says it makes the Pokémon harder to hit.

Findings D-1497 (HP-only IV overwrite loop) and D-1498 (Deoxys form 4) were added through decisions.py. These document original-hack behavior; no gameplay fixes were applied.

## Recent research dump

Found the separate job at `/private/tmp/poke-difficulty-research`, outputs under its ignored `work/build/difficulty-trainers-v2/` directory. Independently checked:

- All 1,024 roster records including sentinel zero, 1,023 nonempty teams and 3,891 party slots against fresh ROM bytes; both research roster versions and their hashes agree.
- All 941 decoded battle callsites and 1,367 participant roles, 18 syntactic badge candidates, and 17 explicit memory-menu assignment paths.
- All 3,002 facility archive members, decoded fields, membership lists, bounds, hashes and Chinese/US comparisons across five archives.
- All 1,379 decoder-frontier observations and all 15 records lacking a decoded encounter reference.

The research rosters inherited the old form/EV/HP-IV interpretation errors. Their raw bytes and hashes remain valid; their parsed fields must be regenerated with the corrected reader before further use. The separate active research checkout was not overwritten. Reproducible audit scripts and machine-readable results are ignored under `work/build/trainer_review/data/` and `work/build/trainer-context-review/`.

## Validation and limits

41 documentation tests pass, including new form, EV order, HP-IV boundaries, source-code hash guards, Gym order, unique page teams, Misty partner separation, dormant Blue trigger and memory-rematch tests. Regenerated docs/site content are checked for synchronization; the Astro build and full internal-link check pass. Browser review covers rendered section order, expanding Misty's Gym team, corrected item/IV display and table layout.

Static references do not establish every object's visibility, every story route or full reachability. Facility inventory is verified, but runtime pool selection is not. Deoxys form 4 falls back to base personal stats; its sprite behavior remains unverified. No emulator playthrough was performed.
