# Pokédex acquisition corrections — 2026-10-09

Three research agents audited the untouched Chinese v4.0.3 ROM. The published
sources now use reviewed restrictions instead of treating every stored script
command and encounter table as reachable gameplay.

## Coverage and findings

- All 169 distinct fixed/resolved scripted acquisition identities reviewed,
  keyed by species, form, script file, kind and level. Eleven impossible sources
  excluded without removing other valid sources for the same Pokémon.
- All 13 trade records reviewed, including the permanently retained Gyarados
  and replacement Pidgeot. Seven fossil restoration mappings reviewed separately.
- Starter, gender, story, choice, item, party-space, weekday/hour, price,
  missability and retry conditions retained beside each scripted source.
- Ordinary wild rows retain exact map, method, period, weekday, level and slot
  weight. Charmander: Rock Tunnel, morning, Lv. 5, 1%, no starter gate on the
  inspected ordinary wild selection path. The Pewter rescue is Pikachu-only;
  Route 3's letter Charmander is unreachable.
- Disabled swarms, Hoenn/Sinnoh Sound, night-fishing replacements, contest sets
  2–4 and Safari block-dependent bonus slots excluded. Ordinary Safari area
  tables and contest set 1 remain. Unreachable Unown maps 490/491 excluded after
  script and collision checks.
- Illumise, Regigigas and Arceus lose their former asserted acquisition routes;
  their reference pages remain with no confirmed way to obtain them. Revive
  loses its false wild-held Linoone source. This is documentation of the
  original hack, not a change to gameplay.

## Implementation

`work/tools/docs/acquisition.py` joins the review files before acquisition and
evolution/breeding summaries are computed. The website and Markdown generator
share these restrictions. Species, location and wild-held-item pages use the
same filtered encounters. `safari_held.py` still parses the original bonus-slot
requirements for research, while the public exporter excludes inaccessible slots.

Review data: `work/tools/site/acquisition_kanto.json`, `acquisition_other.json`
and `acquisition_trades.json`. Evidence:

- [Kanto scripted sources](pokedex_acquisition_kanto.md)
- [Other scripted sources](pokedex_acquisition_other.md)
- [Wild encounters and trades](pokedex_wild_trade_audit.md)
- [Native activation gates](pokedex_wild_gates.md)
- [Unown chamber collision checks](pokedex_unown_access.md)

New original-hack findings: D-2292 through D-2296. No ROM, translation bank,
gameplay patch, download, commit or deployment was made.

## Validation

- 46 documentation/Python tests and 36 exporter/Python tests pass.
- 72 website tests pass with the built-page checks enabled.
- Production build generates 4,651 pages.
- Exporter and documentation freshness checks report zero changes.
- Generated HTML inspected for Charmander, Gyarados, Beldum, Illumise and Arceus.
  Browser automation stalled, so no new screenshot-based layout verification is
  claimed. Native/script findings are static verification, with earlier runtime
  evidence cited where applicable; every acquisition was not replayed in an emulator.

## Rebase onto published main — 2026-10-10

Isolated onto `codex/pokedex-acquisition-rebase` from `origin/main` (`34cd87f`). Preserved main’s Pokédex acquisition/encounter components, capture descriptions, Pickup data, Safari tables and Team Builder. Reviewed sources feed the existing acquisition schema; scripted encounters remain separate from random encounter odds. The original develop checkout and its unrelated edits were left intact. Findings D-2292–D-2296 were transferred through decisions.py.

Rebase validation: 46 documentation tests, 44 exporter tests, 101 website tests including built pages, production build (4,652 pages), and both generator freshness checks.
