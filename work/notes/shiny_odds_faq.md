# Shiny odds FAQ verification

2026-10-05. Documentation-only follow-up to M-04 in
`work/notes/chinese_source_rom_verify_mechanics.md`. No ROM, tools or translation
bank changes; no emulator encounter-frequency test.

Rechecked the saved disassembly against bytes freshly loaded with ndspy from
the untouched `work/rom/origin_v4.0.3_cn.nds`. Exact matches for ARM9 ranges
`0x02019EB8–0x02019F48`, `0x02020480–0x020204A4`,
`0x0206D394–0x0206D3D6`, `0x0206F42C–0x0206F454`, and overlay 2
`0x02247D74–0x02247F10` (ends exclusive). Existing English parity evidence is
in the earlier audit; this pass did not recheck a current English release.

## Exact success counts for the extra check

ARM9 `0x02019EB8` selects multiplier 1/3/5/7 at completed capture counts
0/6/10/20, adds 1 for Shiny Charm item 743, and computes integer divisor
`d = floor(4096 / multiplier)`. The call at `0x02019F2C` obtains an RNG output
from `0x02020480`. That helper advances the 32-bit LCG and returns the upper
16 bits. The check succeeds when `output % d == 0`, including output zero.

For uniformly distributed 16-bit outputs, the exact success probability is
`(floor(65535 / d) + 1) / 65536`. Enumerated all 65,536 possible outputs for
each divisor with Python to verify these counts:

| Catches | Multiplier, no charm / charm | Divisor, no charm / charm | Successful outputs, no charm / charm |
|---|---|---|---|
| 0–5 | 1 / 2 | 4096 / 2048 | 16 / 32 |
| 6–9 | 3 / 4 | 1365 / 1024 | 49 / 64 |
| 10–19 | 5 / 6 | 819 / 682 | 81 / 97 |
| 20+ | 7 / 8 | 585 / 512 | 113 / 128 |

Thus the displayed denominators 1365, 819, 585 and 682 are not exact
reciprocal probabilities even for this check alone. The FAQ uses successful
output fractions and rounded reciprocal approximations. Uniform RNG output
is the probability model, not a claim that successive game encounters are
independent or that a particular seeded playthrough has this frequency.

## Why a single exact overall rate remains unresolved

Overlay 2 `0x02247D9C` invokes the extra check and on success routes to the
forced-shiny constructor `0x02247C64`. On failure the ordinary constructor
continues, including lead-ability and other conditional branches. The path
at `0x02247ED2` calls ARM9 `0x0206D394`, which generates a PID using successive
RNG outputs and rejects candidates until their nature matches. The real OT
ID is then set at `0x02247EE8–0x02247EEE`. The shiny predicate at
`0x0206F42C` retains the XOR threshold of 8. Failure of the extra check does
not establish that the final Pokémon cannot be shiny.

Do not add an assumed independent 1/8192 probability and call the result
exact. RNG correlations, nature conditioning, lead-ability branches and
special encounter construction need fuller analysis. The extra check itself
is already active at zero catches, supporting the FAQ's increased-odds answer
for the verified wild path. Do not extend this table to every starter, gift,
Egg or special encounter.
