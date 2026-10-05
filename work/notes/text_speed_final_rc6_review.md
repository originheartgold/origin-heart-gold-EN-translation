# Final independent high-effort review for WIP RC6

Reviewed 2026-10-05 in `/private/tmp/poke-text-speed-research`.

**Recommendation: proceed with a WIP RC6 device/playthrough patch after the coordinator's fresh build, artifact gate and exact-candidate smoke checks. No new actionable code defect or release blocker was found.** This is a bounded code and evidence review, not hardware certification or a claim that every game path has been exercised.

## Review identity and scope

The implementation and harness reviewed were at `c70359c`, including implementation `6d925cf` and integration merge `ffc9058`. During review the coordinator merged translation-only increment `1c86d11` as `7e1f97e`. The native code, patcher, build integration and harness are unchanged by that merge. I did not edit product code, translation banks, ROMs or saves.

The existing runtime evidence was independently checked against the local candidate:

- `work/build/text-speed/merged-release/origin_hg_v4.0.3_en_wip.nds`
- SHA-256 `ef9ffc72a3dfd77565cc7f15146eaa544c6e2967f96d2985447f569ab4ebed2e`
- Payload canonical digest `a622530bc43d4736c91af9e6ede5f07b801e42d394a84a60c32cd8f12b9d58f5`, 716 bytes.

**That ROM is the pre-increment-2 candidate, not the final RC6 identity.** The coordinator must record the new hash and fresh checks in the release report. The broad existing corpus remains useful evidence for the unchanged native implementation; it must not be described as an exact-ROM corpus run on the newer translation build.

Read the earlier research, independent review, fixes and harness reports; reviewed all new native/payload/patcher code, build and standalone artifact integration, shared-harness changes, focused unit tests and the three maintained regression scripts. Re-disassembled relevant routines directly from the untouched Chinese ROM with the local Capstone installation, rather than relying solely on the earlier prose report. Reviewed the original Options overlay disassembly, renderer controls, asynchronous task and constructor, Options initialization/getter/setter, runtime SaveData publication and ARM-mode ITCM arena initialization.

## Findings

No additional confirmed defect requiring a fix was found. All three earlier findings are addressed:

1. Runtime mode lookup uses the main SaveData pointer published after construction. It no longer rejects initialized Options merely because the first cartridge save has not occurred.
2. The standalone artifact gate invokes the native feature verifier and mandatory payload reproduction. Native ROMs reject missing or disabled metadata; feature sources are fingerprinted and checked again after verification.
3. The independently pinned canonical digest binds source identity, code, base and every exported symbol. Both cached and explicitly supplied payloads are validated before ROM access. Required entry points are distinct, bounded Thumb addresses. A separate compilation reproduced the full payload and symbol map exactly.

## Code conclusions

- **Printer lifetime and fallback:** the original constructor stores callback at `+0x1c`, task ID at `+0x2c`, and asynchronous glyph delay in the low seven bits of `+0x29` after subtracting one. The native checks therefore select the intended ordinary callback-free, original-speed-one printers. NORMAL, invalid mode, absent runtime Options, callbacks and explicit asynchronous delay retain the original task. Completion invokes the original printer-ID destruction function and returns immediately. The accelerated branch does not use the synchronous constructor loop that can discard a waiting printer.
- **Rendering and controls:** the native loop batches only zero-result glyph rendering, has a finite per-task budget, transfers dirty pixels and stops on state/delay changes and non-glyph barriers. The original dispatcher handles newline/repeat, color/size changes, CLEAR/SCROLL, player prompts and timed states. A page wait returns a non-glyph result, so the added loop does not consume another page in that task. Original color controls regenerate the color table immediately. Callback state is excluded from acceleration. Existing pause and scroll transitions still run through the native renderer once per task.
- **Save compatibility:** old valid music values 0–2 leave the new bits 2–3 zero, so old battery saves enter NORMAL without conversion. Initialization clears the original nibble. The narrowed music getter/setter preserve the new text bits while retaining music values; confirmation changes only mask `0x000c`, and cancellation bypasses that write. The save record size and checksum mechanism do not change. This conclusion concerns battery/in-game saves, not old emulator savestates. New-save to old-ROM downgrade support remains explicitly outside scope.
- **Options integration:** allocation increases by exactly one `0x54` record (`0x324` to `0x378`). The patch handles both adjacent and nonadjacent metadata-offset constructions, the confirmation-value literal, row bounds, label/value creation and freeing, both touch-map aliases, sprite metadata and compact row coordinates. Eight selections (seven settings and confirmation) fit the existing three-bit cursor. The final row retains the original Chinese behavior: Quit is value zero; LEFT selects Confirm. The text row is initialized separately after the original row loader, and committed before the existing free-data call. Runtime labels fit their allocated String capacities.
- **Native placement and ABI:** the ITCM data section is actually extended and loaded at startup. The SDK arena lower bound moves from `0x01ff8620` to `0x01ff8900`; main/DTCM section layout and main BSS bounds remain intact. Thumb call encoding, literal function pointers and stack arguments agree with the original call sites. Reproduction rejects unsupported or unresolved allocated-section relocations. The pinned current payload has no unresolved runtime helper dependency.
- **Build composition:** full reviewed input hashes and per-write expected bytes guard fixed-address edits. The patch preserves the demand-loading instruction at `0x0200ba9a`. Hardcoded verification runs before native composition and retains individual string/pointer/instruction checks afterward; the composed final ARM9 hash is recorded. Unknown binary/payload input and double application fail closed. No source ROM file is modified by the patcher.
- **Harness reliability:** the new external-message command preserves the 16-bit message ID, including 1093. Arguments are validated before emulator mutation. The shared message helper rejects exhaustion and restores its sentinel on failure. The corpus checks nonempty rendering, exact expected glyph count, script completion, equal layouts and text pixels, idle page stability and nonzero clean heap walks. Controlled fallback runs use a fresh same-ROM checkpoint and verify its native executable bytes after restoration. Their deliberate test-RAM changes are correctly distinguished from natural gameplay and heap certification.

## Independent verification and evidence audit

Independently ran the focused text-speed, artifact, harness, hardcoded and build-path suites: **63 tests passed; zero failures, errors or skips.** The binary tests used the existing local demand-loaded English ROM fixture. Result: `work/build/text-speed/final-review/test-report.json`. Separately invoked `verify_reproducible_payload`; compilation and full code/symbol equality passed.

The previously completed full tooling report records 487 passing tests with zero failures/errors/skips. This reviewer did not rerun all 487; the coordinator separately reports a fresh full run after `7e1f97e`.

Independently rehashed the pre-increment-2 ROM and checked the completed runtime reports' identities and assertions:

- Corpus: three modes, six records per mode, 21 pages and 867 glyphs per mode; 5,216 total heap checks, with all recorded memory/probe error collections empty. The high-ID corpus is the corrected `corpus-wide`, not earlier superseded runs.
- Native trainer regression: report binds to the same ROM and passes all three modes; includes trainer battle startup rather than an extended battle.
- Options: the same input ROM hash; passing native button/touch navigation, wrap, Confirm/Quit, cancellation, repeated opening and unrelated-bit-preservation assertions.
- Controlled fallbacks: all ten cases pass on that hash. Invalid/null/old-music cases reproduce NORMAL's glyph timing. Delay 3 delegates every native invocation to the original task and has identical 165-frame glyph spans in all modes. NORMAL/FAST/INSTANT spans in the controlled fixture are 54/33/2; these are observed emulator intervals, not guaranteed hardware timings.
- Standalone artifact report passes and explicitly records native verification and payload reproduction.

## Residual gaps and RC6 interpretation

These are coverage limits, not newly reproduced bugs and not blockers to the requested WIP device/playthrough test:

- No DS/flashcart or second-emulator result is supplied by this review. User device testing is the next intended stage.
- Extended sessions, broad wild/double/battle-ending paths and natural callback-driven printers are not exhaustively covered. Callback safety currently relies on delegation to the original task plus static verification; the maintained controlled runtime suite tests explicit delay but does not add a non-null callback case.
- A full natural new-game route that unlocks Options and selects FAST/INSTANT before the first save has not been completed. Runtime publication order and the initialized-save-flag-zero rendering paths were separately verified; neither should be mislabelled as that complete natural route.
- Six sampled messages and sampled heap walks cannot certify every translated line or rare script. Existing hack-logic bugs remain out of scope under the project's behavior-fidelity rule.
- Final RC6 packaging must use the new frozen translation baseline, verify the new artifact and xdelta round trip against USA CRC32 `C180A0E9`, and bind fresh native menu/dialogue smoke results to its exact hash. Distribution remains xdelta only.
