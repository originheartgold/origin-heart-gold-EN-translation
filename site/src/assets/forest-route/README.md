# Forest of Time screenshots

Captured locally from the existing English preview ROM using the melonDS 1.1
backend on 2026-10-09. These are unaltered 256×384 dual-screen captures;
`ForestRoute.astro` displays the top screen and adds a separate HTML exit marker.
No game artwork was generated or redrawn.

The capture used a disposable copy of the harness save at the entrance clearing,
with the quest in its post-Grunt-battle state (0x4099 = 5). Every transition was
walked in the emulator and checked against the expected arrival coordinates.
The original save and ROM were not modified.

Route: entrance top-middle, top-middle, top-right (walk right), top-left
(walk left), top-middle. End: upper forest, map 327 at (15,39).

Local capture recipe, positions, and original output are in the worktree's
`work/build/forest-capture/` (ignored). The source is the existing
`work/build/origin_hg_v4.0.3_en_wip.nds` in the main checkout; no ROM was built.
