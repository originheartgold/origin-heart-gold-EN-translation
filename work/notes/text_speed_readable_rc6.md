> Superseded — historical record; see text_speed_release.md

# Readable text speeds — RC6 WIP revision, 2026-10-06

This revision supersedes NORMAL / FAST / INSTANT from the previous RC6 WIP.
The older review and release notes describe that historical candidate, not these
new settings. The user's device feedback was that INSTANT is especially abrupt
for automatically advancing battle messages. One shared setting remains.

## Behaviour and save compatibility

| Choice | Ordinary printer budget | Intended use |
| --- | --- | --- |
| SLOW | Alternating one and two glyphs per eligible task | A modest increase over the Chinese original |
| MEDIUM | Up to two glyphs per eligible task | Default for new games; recommended starting point |
| FAST | Up to three glyphs per eligible task | Faster reading, with visible text animation |

These are task budgets, not guaranteed glyphs per frame or speed multipliers.
Game scheduling and renderer control states affect elapsed time. No whole-page
INSTANT setting remains. Battle animations, existing post-message waits, page
confirmation and explicitly requested printer delays retain native behaviour.
Callbacks retain the original task. Banks remain demand-loaded.

The two-byte Options save structure is unchanged. Music keeps bits 0–1 and text
speed keeps bits 2–3. Existing pre-feature saves select SLOW without conversion.
Unreleased WIP saves are not a supported migration target. There is no INSTANT
label, mode, version detection or migration branch in the shipped native code;
stored values 0/1/2 directly mean SLOW/MEDIUM/FAST. Historical comparisons below
are research evidence only, not a release compatibility promise.
New games initialize MEDIUM; loading a battery save preserves its stored value.
Reserved value 3 uses the original printer, displays MEDIUM in Options, stays
unchanged on Cancel and normalizes on Confirm. Downgrading a new save to an old
patch is outside the agreed support scope.

## Implementation review

SLOW's alternating phase belongs to each printer. Its allocation grows from
0x34 to 0x38 bytes, with the new byte at +0x34 initialized to zero every time,
including reused heap allocations. No existing printer field is repurposed.
The original initializer still resets its owned pointer at +0x30. SLOW toggles
phase only after an invocation produces output. Completion returns immediately
after destruction; no phase write follows the free.

Exact original-byte guards cover the allocation immediate at 0x020208EA,
initializer call at 0x02020962 and Options initialization at 0x0202B176. The
initializer runs after the original two-byte clear, sets bit 2 and preserves the
original defaults for every other setting. Existing whole-section verification,
ITCM arena reservation, payload pinning and source reproduction remain required.
The compiled initializer and Options instructions were disassembled and checked
against those operations. The 760-byte payload reproduces exactly:
`6a5acbbf84b4e7608b0f3202f0b03d7b002d65865d012bcf311b4291f9b34ab7`.

## Evidence and interpretation

Exact candidate ROM SHA256:
`a087c44bd3dcca42d7cf1fe9db82e838d38ac8c79e846f6318bbcb617b342f9e`.
Ignored evidence directory: `work/build/text-speed/readable-validation/`.

- Full tooling suite: 488 tests passed, no failures/errors/skips. Binary tests
  include printer allocation/init guards and the unchanged save-structure size.
- Payload recompilation, build verification and standalone artifact verification
  passed. The artifact check uses `--ws work/translate/banks`; an initial run
  mistakenly pointed at its parent and was rejected, not treated as evidence.
- Native Options: eight groups of checks, including both input methods, row/value
  wrapping, Confirm/Quit/B behaviour, neighbouring bits and reserved-value repair.
  652 clean heap walks.
- Legacy battery -> native Options -> actual in-game save -> reset/Continue:
  all three choices persist, with Options values 520 / 516 / 512. Input ROM and
  source battery hashes remain unchanged.
- Blank-battery read-only observation: Options is 516 (MEDIUM) before runtime
  publication; all earlier runtime pointers remain null. No cartridge save is
  needed for initialized Options to become usable.
- Allocation lifecycle: poison only the new private byte before initialization;
  verify both phase and original focus pointer reset, including reused slots.
  Callback errors are collected and asserted outside emulator callbacks.
- Six real dialogue messages, 21 pages per speed: 63 completed pages have identical
  glyph counts, layout and text pixels. Pages do not advance while waiting for
  input. 5,216 clean heap walks across this corpus.
- A separately generated authored-control fixture (not the deliverable ROM)
  exercises scroll/clear controls, enlarged font and an explicit 60-tick pause.
  All 18 pages match across speeds; the observed pause gap is 64 frames in every
  mode. 1,760 clean heap walks.
- Controlled fallback matrix: invalid value, unavailable runtime, legacy music
  settings and explicit delay 3. The last delegates every task to the original
  implementation with identical timing in all three modes. Null-pointer test
  instrumentation adds instructions, so fallback task cadence is compared exactly
  and display frame boundaries allow one frame of variation.
- The same 54-glyph dialogue in that matrix spans 55 / 48 / 34 emulated frames
  for SLOW / MEDIUM / FAST, versus 62 for the original fallback. Actual glyph
  batches are 18 single + 18 double, 27 double, and 18 triple batches respectively.
  These are observed intervals, not advertised hardware rates.
- Three automatically advancing turns at each speed, with no A/B during the
  battle, cover move announcements plus observed Leech Seed, sleep, misses,
  effectiveness and critical-hit/affection messages. Nine turns produce 35 tracked
  messages and 910 clean heap walks. These use the native TrainerBattle command
  against trainer 1; they do not claim natural overworld encounter coverage.
- The prior INSTANT candidate is exercised separately for comparison. Battle RNG
  can differ between runs, so whole-turn durations are not a controlled benchmark.
  Compare matching message types and treat the results as illustrative.

The shared harness battle-menu detector previously sampled the English INFO
lettering. It now samples blue background clear of the text; the first failed
battle run was a false negative, confirmed by its screenshot. Successful runs
also require actual move messages, completed turns and memory checks.

Battle dwell is observed from the unchanged text-region pixels after the final
character and display transfer, not inferred from printer destruction. A short
failed Sleep Powder message has about 24 stable frames after a three-frame
transfer allowance at MEDIUM, FAST and the previous INSTANT setting. Printing
that message spans 17 / 11 / 1 frames respectively. Thus removing INSTANT adds
reading time, but does not solve every short native battle pause. This is why
MEDIUM is the recommended default and device feedback remains necessary.

This is an engineering recommendation, not a measured consensus about an
“average ROM-hack player.” SLOW/MEDIUM/FAST communicates increasing pacing in
plain English; the labels fit the existing font and Options row. A real-device
playthrough should particularly assess short failed-move and status messages.
The patch does not silently add battle-specific delays or split the setting.

Remaining limits: no hardware certification, no exhaustive callback/scene audit,
no complete battle-message catalogue, and no claim that heap checks prove absence
of every memory fault. Earlier high-effort reviews apply to the previous revision;
the current revision now also has the independent high-effort review and final
strengthening pass linked below.

## Device candidate

Patch: `work/release/v1.0.0-rc6-wip-readable/Origin_HeartGold_v4.0.3_EN_v1.0.0-rc6-wip-readable.xdelta`.
Apply to clean USA HeartGold, CRC32 `C180A0E9`. Patch SHA256:
`8d9b31edecb624c3fdec77ae58513c798c430095385db0b71894c53ac2df6c2e`.
The packaged patch was independently decoded with xdelta3 and matches the exact
candidate hash above. Local device copy: `work/build/text-speed/readable-build/Origin_HeartGold_rc6_wip_readable.nds`.
Neither ROM nor game data is committed or published. The older RC6 files remain
available separately.

## Final release-strengthening pass — 2026-10-06

[Independent high-effort review](text_speed_readable_release_review.md): no
confirmed native defect or release blocker. The reviewer independently passed
53 focused tests and the native Options music/text regression. See
[the RC validation recipe](text_speed_release_checks.md) for repeatable gates.
Unreleased WIP migration is not supported or implemented.

The coordinator strengthened the shared harness so exceptions in emulator
execution callbacks cannot be swallowed by ctypes. Failures stop the run, retain
the original exception and block later hook mutation. Three unit tests cover this
contract. The native artifact verifier additionally checks the exact critical
instructions and ITCM layout independently of build-receipt hashes; a regression
mutates each critical instruction and refreshes the receipt to prove rejection.
These changes do not alter the candidate ROM or payload.

Final full tooling suite: **492 passed**, zero failures/errors/skips. The standalone
artifact verifier passes on the exact candidate with the stronger checks and
payload reproduction. New evidence is under
`work/build/text-speed/release-strengthening/`:

- `music/report.json`: all nine music/text combinations, native getter returns,
  Cancel across all seven setting rows, and commit/reopen/restore for the five
  other rows. 29,000 correct getter observations and 3,695 clean heap walks.
- `callbacks/report.json`: sixteen controlled callback/busy/held-A/held-B cases
  against the original task. Every case prints exactly 54 glyphs with matching
  final pixels/layout; callback modes preserve callback events and task cadence.
  Each case also has a clean end-of-case heap snapshot.
- `battle-medium/report.json`: the default MEDIUM three-turn battle passes again
  using the fail-closed callback wrapper.
- `corpus/report.json`: the full 63-page corpus passes again using the same
  wrapper, with 5,216 clean heap walks. The final receipt verifies its successful
  completion and exact candidate identity.

Existing save/reset, blank-battery initialization, lifecycle and authored-control
results remain applicable because the native binary is unchanged. The packaged
xdelta still decodes to the exact tested SHA256 above. Physical-device readability
and long-play experience remain the user's playthrough check, especially short
automatic battle failure/status messages. No battle-specific pause was added.
