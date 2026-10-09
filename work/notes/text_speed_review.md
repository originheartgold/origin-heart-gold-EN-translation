# Independent text-speed RC review — 2026-10-05

**Resolution:** the review probes under `work/research/text_speed/review/` were removed in the 2026-10-09 cleanup (git history keeps them). All three findings below are addressed by the [subsequent fixes and rebuilt candidate](text_speed_fixes.md). This report preserves the original review evidence and pre-fix artifact identity.

Reviewed in `/private/tmp/poke-text-speed-research`, branch `codex/text-speed-research`. This review did not modify the native implementation, cached payload, patcher, build pipeline, translation banks, source ROMs or saves. Review scripts and ignored emulator artifacts are separate from release inputs. No downloads, commits or publication occurred.

The reviewed clean-build candidate is `work/build/text-speed/full-build/origin_hg_v4.0.3_en_wip.nds`, SHA-256 `78a19fbc9431bbddc0802cde1d587db2149cd69518199223263e53a77fa65ad2`. The parent review independently rehashed it after the test runs and confirmed it remained unchanged. Controlled task experiments use the native-v5 ROM and its matching original checkpoint, with the same reviewed native payload.

## Recommendation

Do not promote this candidate unchanged. Resolve the save-exists guard below and wire the feature's verification into the standalone artifact gate. The currently checked-in compiled payload reproduces correctly; making that a mandatory RC check addresses the separate cached-payload validation gap. Hardware/second-emulator and broader battle/callback coverage remain release sign-off work, not demonstrated defects.

**Existing valid old saves → new ROM are compatible by design and by the tested examples.** There is no required conversion or pre-upgrade NORMAL selection. The old menu only writes music values 0–2 into the old nibble, so the newly assigned bits 2–3 are zero; new code sees NORMAL and retains the existing music setting. The Options record and save checksum format are unchanged. This conclusion concerns in-game saves, not emulator save states containing old executable memory. Universal compatibility with externally edited/corrupt saves is not claimed.

The user explicitly does not require **new-save → old-ROM downgrade support**. The existing recommendation to select NORMAL before downgrading is not a release blocker or an additional implementation requirement in this review.

## Actionable findings

### P2 — save-exists is used as runtime Options readiness

**Location:** `work/patches/text-speed/native.c:13` (and the fallback at line 23).

`0x02027958` is a getter for `SaveData + 4`, the cartridge-save-exists flag. It is not a test that the current in-memory Options record is initialized. The native mode lookup returns NORMAL whenever that flag is zero, even if live Options contains FAST or INSTANT.

Independent binary evidence:

- SaveData construction at `0x02027624` initializes this flag to zero (`0x02027646–48`).
- A successful load sets it to one (`0x0202768E–9A`).
- A successful save sets it to one (`0x020278D2–DC`, conditional on success result 2).
- New-game block initialization at `0x02027920` initializes the blocks and new-game state without setting this flag.

A controlled emulator experiment reproduces the resulting native behavior, using the same before-talk checkpoint with naturally confirmed INSTANT Options value 520. The experiment changes only this RAM flag; it does not edit or resave the checkpoint, ROM or battery save:

| Flag | Saved Options | Calls to original task | Glyph frame span |
| --- | --- | --- | --- |
| 1 | 520 | 0 | 2 |
| 0 | 520 | 231 | 54 |

Both runs render the same 58 recorded glyph events; some are scene text outside the 54-glyph dialogue page, so the task trace and span are the useful comparison. The eligible task has no callback and zero stored glyph delay. Script: `work/research/text_speed/review/mode_guard_probe.py`. Reports: `work/build/text-speed/review/mode-guard-0/report.json` and `mode-guard-1/report.json`.

Separate natural blank-battery playback of the clean-build candidate observes a non-null runtime SaveData pointer and flag zero throughout startup, tutorials, character creation and entry into the starting bedroom. It uses only ordinary input and read-only observation (`new_game_probe.py`), unlike the deliberately controlled flag experiment. Evidence: `work/build/text-speed/review/new-game/field2.png`, `field-menu2.png` and the final `report.json`. No mandatory save occurs before the bedroom. The early-story menu is still locked there; the bounded run stops before its unlock. Therefore the wrong gate and its live-printer effect are proven, but selecting FAST/INSTANT naturally after menu unlock while this flag remains zero is not yet demonstrated. Check that reachability before calling this a fully reproduced end-to-end player bug; even if a later hack script forces a save before unlocking Options, cartridge-save existence is an unnecessary and fragile prerequisite for reading initialized runtime options.

**Fix:** use actual runtime initialization/readiness, not cartridge-save existence, to decide whether Options can be read. Verify the non-null global SaveData publication occurs after block metadata initialization. Regenerate/reproduce the native payload. Add a regression that confirms FAST and INSTANT before the first save, verifies actual acceleration, then saves/restarts and checks persistence. Keep NORMAL fallback for truly absent Options.

### P2 — standalone artifact verification omits this feature

**Locations:** `work/tools/build.py:338–344`; `work/tools/artifact_check.py:71–77` and `98–100`.

`build.main` invokes `text_speed_patch.verify` after `verify_rom`, but `artifact_check.check` calls only `build.verify_rom`. Consequently the normal standalone artifact/quality path never calls the native feature verifier or checks its source/payload association. Its fingerprint inventory also omits `text_speed_patch.py`, `native.c`, `labels.h` and `payload.json`.

The parent review reproduced this using the actual clean candidate and correct workspace/export inputs: making `text_speed_patch.verify` raise still leaves artifact checking passed with the verifier called zero times. Evidence: `work/build/text-speed/review/root-audit/artifact-check-correct-input/report.json`. The earlier wrong-workspace attempt is a discarded setup error.

The full-ROM identity check and final hardcoded ARM9 hash still provide useful protection; this is not a claim that arbitrary changes to the ROM evade those checks. The missing check is feature-aware verification against current source/payload/layout, and the omission makes the standalone gate weaker than the build's verification.

**Fix:** compose feature verification into the shared verification entry point or explicitly invoke it from the artifact checker with `prior['text_speed']`. Preserve explicit opt-out behavior and require corresponding metadata for enabled builds. Include the feature inputs in fingerprints. Add a regression proving the standalone gate fails on a feature-verifier rejection and a stale native source/payload association.

### P2 hardening — source digest alone does not authenticate cached code/symbols

**Location:** `work/tools/text_speed_patch.py:64–73`, `102–105`, and `187–198`.

The source digest says which C/header files the JSON claims to represent; it does not validate the cached machine-code bytes or exported symbol values. `apply` uses those values and emits hashes of its own output; `verify` compares against those output hashes and the same cache. Thus a modified cache with an unchanged source digest can pass both functions.

The parent review reproduced both an infinite-loop first instruction and a `print_task` symbol redirected to the original task, using the actual loader with an isolated temporary copy of ASSETS. Both pass apply/verify. The real cache and source ROM are unchanged. Reproducer: `work/research/text_speed/review/root_audit/payload_guard_probe.py`; results: `work/build/text-speed/review/root-audit/payload-guard.json`.

**Current candidate is not known-bad:** the cached payload independently recompiles byte-for-byte from the reviewed C/header source; its entry points are Thumb addresses within the reserved code. The complete tooling suite also exercises this test. This finding is a release-process gap, not evidence of corruption in the delivered xdelta.

**Fix:** make payload reproduction and entry-point validation a required, non-skippable RC gate, or validate cached code plus symbol metadata against a separately reviewed expected digest before using it. A hash stored beside the same mutable bytes without an independent reference would not add the claimed source correspondence. Ordinary end-user builds may still consume a reviewed cache without requiring clang.

## Areas independently checked without another confirmed defect

- **Printer lifecycle:** constructor semantics and original task disassembly match the offsets used in C. The original task is called for NORMAL, non-null callbacks and nonzero stored glyph delay. Native destruction receives the printer ID and returns immediately, avoiding a new use-after-free. The bounded fast loop does not invoke the constructor's unsafe synchronous printer path.
- **Control handling:** the native renderer retains page states, scroll steps, delay state 6 and control dispatch. The loop stops before sentinel/control introducers and after non-glyph results/state/delay changes. Newlines run through the existing repeat dispatcher. Color controls regenerate colors immediately inside the original renderer, so batching does not leave a stale color table. The source's claim that explicit pacing remains authoritative is consistent with the inspected machine code.
- **Input:** the implementation delegates held-button and page-prompt behavior to the original renderer rather than directly advancing pages. Existing held-A/B fixture evidence is bounded and should not be promoted to an exhaustive input proof.
- **Save bits:** initialization clears the full old nibble. New getter/setter masks select music bits 0–1 and preserve text bits 2–3. Confirmation modifies only those two text bits; Cancel does not call that write. The direct getter callers identified in the reviewed binaries are audio update and Options initialization; the setter is called by Options confirmation. Existing music-quarter and persistence evidence agrees. No save format expansion is introduced.
- **ABI/native code:** the cached code recompiles exactly with the local ARMv5TE Thumb clang configuration. Function pointers use the Thumb bit and generated branches are within range. The reviewed interfaces and stack-passed draw-label arguments match the original call sites. No unresolved helper/runtime relocation was observed.
- **ITCM:** the payload occupies an extension of the existing loaded ITCM section. ARM-mode disassembly confirms the patched literal is the SDK's initial ITCM arena lower bound, now `0x01FF8900`. The reviewed sections retain main address/length, main BSS bounds and DTCM data/BSS. The startup section stream has the extended ITCM data, not an uninitialized code cave. No new main heap allocation is used for native code.
- **Options layout:** allocation grows from `0x324` to `0x378`; the additional `0x54` row moves trailing metadata. Audited instruction replacements include the previously missed nonadjacent offset constructions. Seven setting rows and confirmation row fit the existing three-bit selection field (0–7). Up/down wrapping, confirmation comparisons, row initialization/free loops, frame arrows and both touch-map pointer aliases are patched consistently. New labels use existing font/palette resources and are bounded by their String capacities. The reviewed screenshot shows all three values fitting.
- **Build composition:** prior hardcoded edits are verified before the native stage; their original stage hashes are retained, and the expected final ARM9 hash is updated while the later verifier retains individual string/pointer/instruction checks. The full build and patch round trip passed for this artifact. The separate artifact integration omission above still needs correction.
- **Memory-loading protection:** the demand-loading instruction remains `0x2501` at `0x0200BA9A`. No whole-bank loading has been restored. Loading a complete requested message and rendering its characters remain separate paths.

## Test/evidence audit

This reviewer independently ran the text-speed, hardcoded and build-path suites: 23 tests, 21 passed, two initially skipped for an absent fixed Chinese-ROM fixture. The parent review then exposed the already-existing local Chinese ROM and extract directory through ignored worktree symlinks and ran **all 461 tooling tests: 461 passed, zero failures/errors/skips**. Result: `work/build/text-speed/review/root-audit/tool-suite-all-fixtures.json`. The transient hardcoded scan failure with no extract fixture is not an implementation regression.

The existing runtime reports were inspected, including native timing, persistence, clean-build trainer battle, authored controls, held buttons, music/options regressions, menu and summary regressions. The menu/summary stdout contains early unarmed snapshots, but the final parsed records are armed, script-complete and have nonzero heap walks; they are not false passes caused by those early lines. The reviewed full-runtime screenshot genuinely reaches battle move selection. Older screenshot names that incorrectly implied battle entry are already disclaimed in the release notes.

All constructor events recorded in the reviewed native scenario reports have callback zero and speeds 0, 1 or 255. Therefore those scenarios do **not** constitute runtime coverage of non-null callbacks or explicit asynchronous delays greater than one. The fallback is straightforward and matches the original path, but that is static evidence, not a runtime test of these cases.

The custom native probe's final pass/fail concerns sampled memory checks. It does not automatically prove every intended screen transition, saved value, or text timing; those require report/screenshot assertions or manual review. Older reports predating `memory_status` must be assessed from their actual error fields. The controlled flag experiment is not memory-regression certification and must not be merged into the read-only runtime-evidence claim.

## Remaining release work after fixes

1. Fresh-game pre-save Options/printing, all three text choices, original music values 0/1/2, and existing-save upgrades with changed neighboring options. Confirm persistence and Cancel independently.
2. Regenerate the payload, build a fresh candidate, run the required reproduction/tooling and corrected artifact gates, then rerun targeted native persistence/controls/battle tests against that exact new hash.
3. Add representative non-null callback and explicit-delay runtime cases with assertions that original pacing is retained; cover wild/double battles, battle-ending dialogue and long sessions. No failure in those untested scenarios is asserted by this review.
4. Complete second-emulator and DS/flashcart smoke tests, including held A/B and menus/dialogue/battle transitions. DeSmuME-only results do not certify hardware timing or every emulator implementation.

No finding concerns unsupported downgrades, translation wording, or unrelated hack gameplay bugs.
