# Trainer research verification

Run from the repository root, using the existing local ROMs and Python environment:

```sh
.venv/bin/python work/research/trainer_verification/refresh.py
.venv/bin/python -m unittest discover -s work/research/trainer_verification -p '*test*.py'
```

The refresh writes `work/build/difficulty-trainers-v3/`, which is ignored by Git. It does not download, modify, or build a ROM. It supersedes the parsed fields in the earlier difficulty research dump without modifying that task's checkout. Comparison with the old v2 roster is optional; extraction and validation work directly from the local source ROM.

The bundle contains:

- `roster.json`: all 1,024 records, including empty record zero, with corrected forms, displayed EV order, separate HP IVs, raw hashes, and indexed references.
- `encounters.json`, `badge_candidates.json`, `menu78_assignments.json`, and `unreferenced.json`: script callsites and bounded selection evidence. Unreferenced means absent from this encounter index, not absent from every engine table.
- `reachability.json`: map and standard-script entry linkage, trainer-sight dispatch evidence, remaining decoder gaps, and explicit uncertainty about world-state feasibility.
- `phone_rematches.json`: contact-book and rematch-table references, separated from evidence of an active caller.
- `facilities.json`: independent inventory of facility archives. These records use a separate namespace from story trainers.
- `facilities_runtime.json`: guarded analysis of reviewed facility constructors and selection paths, with unresolved coverage stated explicitly.
- `summary.json`, `validation.json`, and `manifest.json`: counts, fresh-ROM validation, and source/script/artifact hashes.

Entry linkage is not proof that the player can reach a battle in a particular save state. A reference in a phone-rematch or facility table likewise does not establish that a live caller selects it. The runtime supplement documents reviewed paths rather than asserting coverage of every facility mode.

See `work/notes/trainer_reachability.md` and `work/notes/trainer_facility_runtime.md` for evidence and remaining limits. Raw ROM-derived dumps and disassembly remain under ignored `work/build/`; only analysis tools and reports belong in version control.
