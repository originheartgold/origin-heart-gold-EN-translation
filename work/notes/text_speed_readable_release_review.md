# Independent high-effort review: readable text speeds

Reviewed 2026-10-06 in `/private/tmp/poke-text-speed-research`, branch
`codex/text-speed-research`, starting at `f74c0aa`. This review concerns the
SLOW/MEDIUM/FAST revision, rather than the earlier unreleased INSTANT experiment.
The coordinator is adding further harness coverage concurrently; this document
separates the checks run by this reviewer from that additional work.

## Recommendation and findings

No confirmed defect in the shipped native feature was found. The implementation
is suitable for an RC release after the coordinator's final checks and packaging
receipt. This is an engineering review and bounded emulator evidence, not a claim
that all scenes or physical DS/flashcart configurations have been certified.

Two meaningful coverage gaps were identified:

1. Existing Options checks changed text speed and verified neighboring bits, but
   did not change the actual MUSIC SPEED row across all text speeds or exercise
   commits on the five other original rows. The added `music_interaction.py`
   regression addresses this through native menu inputs; all cases passed.
2. The original fallback matrix tested explicit delays, invalid modes and missing
   runtime state, but not an actual non-null callback/busy callback or held A/B
   input. The coordinator added a passing 16-case callback/input matrix and
   made execution-hook exceptions propagate out of ctypes callbacks. I reviewed
   that error propagation and independently ran its unit tests. Assertions inside
   a ctypes callback must not be considered reliable unless collected or propagated.

These were test coverage gaps, not reproduced defects in the ROM. No native code,
labels, save format or migration logic was changed by this reviewer.

## Identity and scope

Exact candidate independently hashed:

- ROM SHA256: `a087c44bd3dcca42d7cf1fe9db82e838d38ac8c79e846f6318bbcb617b342f9e`.
- Native payload: 760 bytes.
- Canonical pinned payload digest:
  `6a5acbbf84b4e7608b0f3202f0b03d7b002d65865d012bcf311b4291f9b34ab7`.
- Read-only trainer battery SHA256:
  `7ae2158658ae55755ef5be2157b7343741ad61d36954ddfa83409488c5726fd5`.

Reviewed `native.c`, `labels.h`, compiled payload, `text_speed_patch.py`, build
composition, standalone artifact verification and tests. Read the maintained
Options, lifecycle, save persistence, blank-battery default, dialogue/control,
fallback and battle harnesses and their candidate-bound reports. Independently
disassembled the candidate printer constructor, original task, renderer dispatcher,
initializer and Options initialization/getter/setter with Capstone.

## Native implementation assessment

**Private printer storage.** The sole patched constructor allocation increases
from `0x34` to `0x38`. The original constructor still copies the same original
fields and calls initialization before either its asynchronous or synchronous
branch. The wrapper calls the original initializer, which writes zero to the
owned focus-indicator pointer at `+0x30`, and independently clears `+0x34`.
This avoids aliasing existing state such as scroll distance. A reused heap slot
therefore cannot inherit the previous printer's fractional phase. The extension
is four bytes aligned; only one byte is used. The new allocation/init sites are
protected by the full reviewed ARM9 hash and individual expected instructions.

**Lifetime and batching.** Ordinary callback-free delay-one asynchronous printers
have zero in the low seven delay bits after the constructor subtracts one.
Those printers use the selected bounded budget. Explicit slower printers and
callbacks still delegate to the original task, including its callback-wait state.
SLOW toggles its own phase only when the task produced dirty output. Rendering
completion destroys the original printer ID and returns immediately; no private
phase or window access follows destruction. Synchronous speed 0/255 construction
retains its original loop and free path.

**Control handling.** The accelerated path calls the original renderer dispatcher,
which retains its repeat processing for newline and controls. The extra loop
stops on nonzero results, printer state/delay changes and known upcoming control
barriers. Each task has a finite budget of at most three renderer successes.
Timed pauses, scroll/prompt states and callbacks are not implemented again in the
payload. The color table is initialized before rendering, and the original color
controls handle subsequent changes. Completed text equivalence alone does not
prove timing; separate control, fallback and battle evidence is correctly needed.

**Save and initialization.** Fresh Options are cleared by the original two-byte
initializer before the new instruction sets bit 2. Later original initialization
preserves that bit and produces `0x0204` (MEDIUM). The save record size and checksum
mechanism are unchanged. Old valid music values 0/1/2 leave text bits 2–3 zero and
therefore select SLOW. The narrowed music getter and setter use only the low two
bits. Text confirmation changes only mask `0x000c`, and cancellation bypasses the
write. Raw reserved value 3 delegates rendering, displays MEDIUM, remains intact
on Cancel and is repaired by Confirm. There is no INSTANT label, mode detection,
version test or migration branch. Unreleased WIP saves are outside support scope.

**Runtime readiness.** The selected accessor uses the runtime SaveData global,
which is published after block metadata and loaded/new Options are ready. An
absent runtime delegates to the original printer. The cartridge-save-exists flag
is intentionally not used as a readiness check. This permits initialized new
games to use MEDIUM before the first save.

**Options integration.** Seven setting records plus the existing confirmation
record fit the original three-bit cursor. The patch expands the allocation,
relocates subsequent metadata, adjusts bounds, updates both touch-map aliases
and calls the text-speed commit before freeing menu state. Runtime strings fit
their allocations and existing English font. The compact layout was inspected in
the candidate Options screenshot: SLOW, MEDIUM and FAST remain legible alongside
the original MUSIC SPEED row. No new graphics or game data are committed.

**Placement and guards.** The payload resides in the extended startup-loaded ITCM
section, with its arena lower bound rounded up beyond the extension. Main code,
DTCM and main BSS layout remain unchanged. Thumb entry points, branch encodings
and ABI usage match the inspected call sites. Source reproduction matches the
cached bytes and exported symbols. Unknown original binaries, stale/mutated
payloads and double application fail closed; the demand-loading fix remains a
required and verified instruction.

## Verification contract

The build receipt contains full patched ARM9 and Options-overlay hashes. Ordinary
stale or unrelated receipts fail those comparisons; old native revisions also
fail the independent current-payload comparison. Guarded `apply()` cannot produce
a successful current receipt while skipping the allocation/init/default patches.
No ordinary stale-metadata or incomplete-feature false pass was found.

The coordinator additionally strengthened verification during this review. It
now independently checks the ITCM section layout and aligned arena boundary,
task pointer, enlarged allocation, initializer hook, MEDIUM default and narrowed
music getter/setter instructions. I reviewed those exact checks and independently
ran the added mutation test, which deliberately refreshes the receipt hash after
corrupting a critical instruction. Every corruption is rejected. This is useful
protection against future build-composition mistakes; no existing product defect
was needed to justify it.

## Independently executed checks

- 14 focused text-speed tests passed with the local binary fixture enabled;
  zero failures, errors or skips. Includes payload recompilation/equality,
  corruption rejection before ROM access, allocation/default guards, overlay
  tables, original layout preservation and artifact mutation detection.
- 16 shared-harness unit tests passed, including fatal callback-error propagation,
  first-error preservation, suppression of later instrumentation mutations and
  successful execution/unregistration behavior. Zero failures/errors/skips.
- 23 standalone-artifact unit tests passed; zero failures, errors or skips.
  Includes missing/stale metadata, false opt-out, source mutation, missing
  compiler, reproduction failure and source-preservation cases.
- Independently hashed the deliverable ROM and checked existing runtime report
  identities. Dialogue corpus, Options, lifecycle, fallback, persistence,
  blank-battery initialization and three new-speed battle reports bind to the
  exact candidate above. Authored-control reports correctly bind to a separate
  modified fixture, and old-INSTANT comparisons bind to the historical ROM.

The new independently executed `music_interaction.py` run passed on the exact
candidate, using the strengthened callback wrapper:

- All nine music/text combinations committed and reopened correctly, with the
  expected complete Options values 512–514, 516–518 and 520–522.
- For each combination, changed all seven setting rows, canceled with B, and
  reopened to prove the complete pending edit was discarded.
- Individually committed and reopened changes to BATTLE SCENE, BATTLE STYLE,
  TITLE SCREEN, BATTLE BG and FRAME, then restored each through the real menu.
  MUSIC SPEED and TEXT SPEED remained intact.
- 29,000 observed native music-getter returns matched the low two saved bits and
  stayed within valid values 0/1/2.
- 3,695 clean heap walks; corruption, allocation failure, null-write, capacity and
  instrumentation-error collections were empty. ROM and source battery hashes
  remained unchanged. No direct Options RAM writes were used.

Evidence: `work/build/text-speed/release-strengthening/music/report.json`.
The source regression lives at `work/research/text_speed/music_interaction.py`.

The prior completed runtime evidence is useful and correctly bounded: 63 real
message pages, 18 authored-control pages, all three save/reset modes, initialized
blank-save Options, reused allocation initialization, and nine battle turns.
This reviewer did not rerun all of those original suites or claim them as newly
executed independent tests.

## English pacing assessment

The user-approved labels describe an increasing sequence without claiming a
whole-page instant mode. MEDIUM is a reasonable English starting point and the
new-game default. Observed ordinary 54-glyph spans are 55/48/34 emulator frames
for SLOW/MEDIUM/FAST, versus 62 for the original fallback; they are not guaranteed
hardware rates or proof of player consensus. SLOW is modestly faster than the
original as requested.

Removing INSTANT adds visible reading time in battle while retaining original
battle waits. The sampled short failure message still has only about 24 stable
frames after the final transfer allowance. That limit is explicitly documented;
this feature does not guarantee comfortable reading of every automatic message.
The shared setting and preservation of native pauses match the agreed scope.
Device feedback should remain focused on short battle failures/status messages
and sustained play. No separate battle-speed or timing change was introduced.
