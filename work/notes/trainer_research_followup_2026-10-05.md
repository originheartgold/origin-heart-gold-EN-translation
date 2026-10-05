# Trainer research follow-up — 2026-10-05

The corrected research bundle is regenerated directly from the untouched local Chinese v4.0.3 ROM into ignored `work/build/difficulty-trainers-v3/`. The reusable entry point is `work/research/trainer_verification/refresh.py`; its README documents the artifacts and verification commands. The old research task's checkout is preserved.

The fresh-ROM comparison covers all 1,023 populated teams and 3,891 Pokémon. Raw party hashes are unchanged from v2. Parsed differences are exactly 21 form corrections, 1,129 EV-order corrections, and separate HP IV values for all 3,891 slots. The new bundle includes source, script, and artifact hashes and can be regenerated without the old dump.

Independent subagent reviews covered encounter entry linkage, facility runtime construction and selection, and the export/validation pipeline. Of 941 battle callsites, 914 have a static map/standard-script root and three more have a verified engine trainer-sight entry. The remaining 24 are classified rather than declared inaccessible. Separating map-header data from executable scripts explains 1,372 of the old 1,379 decoder gaps; the seven remaining gaps coincide with documented weekday-ribbon script bugs.

The phone-rematch trace links trainers 440 and 609 to a rematch table, but finds no current caller for their contacts. They remain among the 15 records without an indexed encounter reference. A table reference is not proof of a playable encounter. Details and the remaining world-state limitations are in `trainer_reachability.md`.

The facility inventory covers 3,002 archive members, including 2,380 Pokémon sets. The runtime supplement verifies form bits, EV allocation, shared construction, and multiple distinct selection policies against guarded original-ROM code. Facility constructors set all six IVs and do not inherit the ordinary trainer loader's HP-IV bug. Stored items can be replaced by fallback items, and levels and IVs depend on callers; the inventory must not be presented as a fixed team list. See `trainer_facility_runtime.md` for dispatch evidence and unresolved facility modes.

This completes regeneration and a substantially deeper static review. It does not establish full world-state encounter reachability or exhaustive facility selection across every mode, rank, and saved session. Those limitations are explicit in the machine-readable bundle. No ROM, translation behavior, or public guide data is changed by this follow-up.

Validation: the integrated refresh passes fresh-ROM and old-roster comparison; all 20 research tests pass. Facility evidence is guarded by 26 code-region hashes and two script-member hashes. The decision register validates with zero errors or warnings, including the suspected doubles-menu fallthrough recorded as D-1499. Model tests verify the transcribed rules; they do not replace emulator execution.
