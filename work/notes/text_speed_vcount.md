# Text speed: frame-aware batching with measured costs (D-1601)

The native batching loop in `work/patches/text_speed/native.c` stops drawing
further glyphs in a task when one more glyph would make the game miss the next
VBlank. Since 2026-10-07 (second revision) it predicts that from costs it measures
itself while the game runs, not from fixed constants. This note records why, how
the rule works and was derived, what was measured, and how the gates check it.
Branch `codex/text-speed-research`.

**Since D-1604 (2026-10-07) TEXT SPEED is NORMAL / FAST.** NORMAL is the hack's
original printer task (no batching) plus the printer catch-up below; FAST is the
batching loop this note describes (budget 3) plus the catch-up. SLOW and MEDIUM are
gone, and with them SLOW's phase byte, the SLOW floor and the three-speed order.
Paragraphs and tables below that mention SLOW or MEDIUM record the three-speed
revision of the same day and are historical; the frame rule itself is unchanged
except for the short-history rest floor ([below](#short-history-rest-floor-d-1604)).

## The problem

The game loop (NitroMain, `0x02000C88`) wakes at the start of VBlank (display line
192), runs the field or battle work, the task queues (the text printer is one of
those tasks), then a few post steps, and finally waits for the next VBlank
(`OS_WaitIrq` at `0x02000DE8`). If the loop is still running when that VBlank
starts, the wait misses it and waits for the one after: the frame is dropped (no
game update; the printer task does not run).

Each glyph costs about 9-12 display lines; 7-9 of them are one lazy cartridge read
of the glyph's font data (`NARC_ReadFromAbsOffset`, `0x02007784`; one read per
glyph). The window copy to VRAM is done once per task (about 2-3 lines).

The first frame rule (`cc36910`..`cf50a23`) stopped before another glyph when
`7 <= 192 - line < 20`: two fixed constants measured in two DeSmuME scenes. An
independent review found it failing in busy 60 fps scenes: in Goldenrod Dept. Store
6F MEDIUM took 85 frames for message 718#160 against SLOW's 84; many stops did not
save the frame; speeds collapsed in Celadon Gym, after the Options menu and on an
idle Route 1. A constant cannot follow scenes whose costs differ, and the constants
were calibrated in one emulator only.

## The rule

Every task still draws at least one glyph (or handles one control), exactly like
the original printer. Before each further glyph (budget left, no control next) the
loop predicts where the game loop will end if it draws one more glyph:

    draw   if  left >= glyph + rest + MARGIN          (it fits)
    draw   if  left <  low                            (the frame is lost anyway)
    stop   otherwise

- `left`: lines until the next VBlank starts, from VCOUNT (`0x04000006`) read right
  after the previous glyph: `192 - line` before VBlank, `192 + 263 - line` in VBlank
  (a VBlank-time task, as in battle, or a frame already lost: the next VBlank is a
  whole frame away).
- `glyph`: the largest of the last eight measured extra-glyph costs: lines from the
  reading after one glyph to the reading after the next, the exact quantity being
  predicted. A task's first glyph is not a sample (it runs after the field work with
  cold caches and costs about two lines more). With no sample since power-on:
  `GLYPH_SEED` 13.
- `rest`: the largest of the last eight measured rests: lines from the end of a
  batch that drew to the end of its game-loop pass (window copy, task exit and
  everything the loop still does before its wait). With no sample: `REST_SEED` 20,
  and no frame is declared lost.
- `low`: the shortest of those rests. If even that does not fit (`left < low`), a
  stop could not reach the wait before VBlank: the frame is dropped whatever the
  batch does, the next deadline is the following VBlank, and the batch may use the
  time (still within its budget).
- `MARGIN` 1: VCOUNT counts whole lines, so the current line can be up to one line
  later than read; the maxima of eight samples already include the rounding of the
  two costs.

The budget stays the maximum (FAST 3), so a batch can never run long. (Historical:
the three-speed revision had SLOW 1/2 by phase and MEDIUM 2; a frame stop kept
SLOW's two-glyph turn.)

### Short-history rest floor (D-1604)

While the rest history holds fewer than `SHORT` (3) measured rests, the rest counts
at least `SHORT_REST` (7) lines, the typical rest: `rest = max(largest rest, 7)`.
With no rest measured the seed (20) applies as before; from three rests on the
largest measured rest alone.

Why: in the full run of 2026-10-07 FAST dropped a frame the original printer did not
drop (Route 1 promoter: 2 against 1, flagged as dropped only because of the batch's
extra glyphs). The history then held a single rest of 6 lines; the real rest was 8,
and the pass ended one line after VBlank. Measured with the payload of that run over
the 17 scenes (FAST; each rest sample against the largest rest measured before it in
the same history; all 432 samples were 6, 7 or 8 lines: 47, 371 and 14):

| rests in the history | samples | next rest above the largest so far | above max(largest, 7) |
| --- | --- | --- | --- |
| 1 | 17 | by 2 lines once (Route 1 promoter: 6, then 8), by 1 once | by 1 once |
| 2 | 17 | by 1 once (Goldenrod Dept. Store 6F: 7, 6, then 8) | by 1 once |
| 3 to 7 | 85 | never (3-6), by 1 once (7) | (no floor) |
| 8 (full) | 296 | by 1 line 7 times | (no floor) |

`MARGIN` (1) covers an excess of one line (the full-history case, no dropped frame in
any scene); only a single low first sample left an excess of two. A floor, not an
extra line of margin: a first try with one more line of margin while the history is
short (the review's suggestion) stopped FAST on Route 1 with 18 lines left after a
single rest of 7 (glyph 10 + rest 7 + 2 = 19), a stop the product rule flags as
giving up a glyph that would have fitted (the pass ended 11 lines before VBlank, the
median extra glyph costs 9.5). The floor changes only histories whose largest rest is
below 7; a short history of typical rests decides exactly as before. The gates check
both sides (no extra dropped frame, no stop that would have fitted), and fault
`short-history-unguarded` (floor removed) must fail the scenes gate.

### Measuring the rest

The payload hooks the game loop's last call before its VBlank wait: the `bl
0x020272d4` (a 3D swap request) at `0x02000DE0` now calls `frame_end`, which makes
that call first and then reads VCOUNT and the SDK's VBlank counter
(`HW_VBLANK_COUNT_BUF`, `0x027FFC3C`, the word `OS_GetVBlankCount` reads; it steps
at line 192). A batch that drew records the line and the counter's low byte at its
end. `frame_end` measures the rest from there, but keeps the sample only if the
counter agrees with the lines: one VBlank in between if the interval crossed line
192, none otherwise. A loop that waited for VBlank elsewhere in between (the save
code does) gives no sample. If no batching task ran for 60 loop passes (`STALE`,
about a second without text: a map change), the rest history is cleared, because a
new scene's loop may be heavier; a printer waiting for a button still runs its task
and keeps the history. Neither VCOUNT nor the VBlank counter is ARM9 code, so neither
has a reviewed dependency range.

### State and RAM

One global `struct frame_state` of 24 bytes (glyph[8], rest[8], two ring indexes,
the open mark, the idle count, the mark's line and counter byte, the 'ran' flag),
zero at boot, the last 24 bytes of the payload block in ITCM; the SDK ITCM arena
starts after the block. Glyph costs do not depend on the printer and the rest
belongs to the loop pass, so the state is global; the per-printer SLOW phase stays
in the printer's private byte `+0x34`. Payload 1240 bytes, ITCM extension
`01FF8620`-`01FF8B00`. `text_speed_patch.py` checks that the state symbol is the
zeroed tail of the block; the gates compare the fixed bytes before it.

ARM9 guard: the edit at `0x02000DE0` is in `apply()`'s edit list and `verify()`'s
critical bytes; the whole game loop (`0x02000C88`-`0x02000E38`) and the called
routine (`0x020272D4`-`0x020272F8`) are reviewed dependencies, both re-derived from
the base ARM9 by the unit tests, so no code patch may overlap them.

## Deriving the constants

Measured in DeSmuME across the 17 scenes below (`work/research/text_speed/scene_pacing.py`):

| Quantity | Measured |
| --- | --- |
| extra glyph (reading to reading) | 7-11 lines, median 10; cheap glyphs 2-5 |
| first glyph of a task (from before its render) | 11-13 lines |
| rest (batch end to loop end, with window copy) | 5-10 lines, 6-8 typical; a waiting task (no copy): 1 |

- `GLYPH_SEED` 13: the largest glyph cost seen anywhere, first glyphs included.
- `REST_SEED` 20: about twice the largest rest. It only applies to a printer's first
  decision after a second without text; it costs at most one glyph there (seen: two
  frames on a two-page message in two 30 fps scenes).
- `SLOTS` 8: the maxima follow a scene within eight samples, and an outlier is
  forgotten after eight.
- `MARGIN` 1: see the rule.

How the rule got there (probe runs over the same scenes; SLOW / MEDIUM / FAST
frames on the trainer page after Options, then Celadon Gym):

1. One line of margin per reading (3), first glyphs as samples, every empty slot
   counted as the seed: 42 / 43 / 39 (MEDIUM slower than SLOW). Too conservative:
   a first glyph costs about two lines more than an extra one.
2. Margin 1: 38 / 37 / 36; Celadon Gym 54 / 57 / 55 with a dropped frame the
   original printer does not drop.
3. Only extra glyphs as samples: Celadon still dropped that frame. Cause: tasks that
   only wait for a button gave rest samples of about 1 line (no window copy), so after
   every page wait the rule drew glyphs that did not fit.
4. Rest samples only from batches that drew: no extra dropped frames anywhere, but
   the rest history was cleared during every page wait (no rest sample there), so
   each page started with the seed.
5. A task that runs (also while waiting) keeps the history fresh; seeds 13 and 20,
   empty slots ignored once a sample exists: the final rule, 37 / 35 / 33 and
   54 / 52 / 46.

Every frame decision of the binary is checked against a line-for-line mirror of
this model (`text_speed_checks.FrameModel`), and the payload's state against the
costs the gate measured itself; a unit test keeps the constants equal to `native.c`.

## Scenes before and after

D-1604 (NORMAL / FAST, short-history rest floor; dirty candidate `8867d27d`, run
`work/build/text-speed/nf2`): printing frames / dropped frames per scene. NORMAL equals
the original printer (value 3) in every scene; FAST has no more dropped frames than
NORMAL anywhere (Route 1 promoter: 1, was 2 before the floor).

| Scene | original | NORMAL | FAST |
| --- | --- | --- | --- |
| trainer-fresh | 53 / 1 | 53 / 1 | 21 / 1 |
| trainer-after-options | 53 / 1 | 53 / 1 | 31 / 1 |
| route1-idle | 54 / 24 | 54 / 24 | 20 / 7 |
| pallet-house-2f | 81 / 0 | 81 / 0 | 25 / 0 |
| ecruteak-theater | 81 / 0 | 81 / 0 | 25 / 0 |
| pokeathlon-gatehouse | 81 / 0 | 81 / 0 | 25 / 0 |
| mt-moon | 81 / 0 | 81 / 0 | 25 / 0 |
| celadon-gym | 81 / 0 | 81 / 0 | 44 / 0 |
| goldenrod-dept-6f | 81 / 27 | 81 / 27 | 34 / 11 |
| route1 | 81 / 0 | 81 / 0 | 44 / 0 |
| route1-30fps | 81 / 40 | 81 / 40 | 25 / 12 |
| viridian-city | 83 / 42 | 83 / 42 | 27 / 13 |
| viridian-forest | 83 / 41 | 83 / 41 | 28 / 14 |
| ss-anne | 83 / 41 | 83 / 41 | 27 / 13 |
| route1-promoter | 82 / 1 | 82 / 1 | 46 / 1 |
| route1-promoter-30fps | 93 / 46 | 93 / 46 | 31 / 15 |
| seven-island-tourist | 66 / 0 | 66 / 0 | 21 / 0 |

The tables below are historical (SLOW / MEDIUM / FAST revision).

Printing frames (sum of page spans: first to last glyph of each page) and dropped
frames inside those spans (frames in which the printer's task did not run), original
printer / SLOW / MEDIUM / FAST. Before: the `cf50a23` candidate (`8c6e97f9…fb86c`,
fixed rule). After: this payload. Both measured with the same scene procedures
(`scene_pacing.py`: cold boot, the scene's setup, one checkpoint, then the four modes).

| Scene | Before: frames | Before: dropped | After: frames | After: dropped |
| --- | --- | --- | --- | --- |
| Trainer page, fresh boot (Route 1) | 54 / 36 / 27 / 22 | 1 / 1 / 1 / 1 | 54 / 36 / 27 / 21 | 1 / 1 / 1 / 1 |
| Trainer page after the Options menu | 54 / 36 / 36 / 35 | 1 / 1 / 1 / 1 | 54 / 37 / 35 / 33 | 1 / 1 / 1 / 1 |
| Trainer page after 35 s idle on Route 1 | 85 / 57 / 55 / 39 | 32 / 22 / 20 / 14 | 88 / 61 / 62 / 44 | 35 / 25 / 26 / 18 |
| 718#160 Pallet Town house 2F | 82 / 54 / 40 / 26 | 0 / 0 / 0 / 0 | 82 / 54 / 40 / 26 | 0 / 0 / 0 / 0 |
| 718#160 Ecruteak Dance Theater | 82 / 54 / 40 / 26 | 0 / 0 / 0 / 0 | 82 / 54 / 40 / 26 | 0 / 0 / 0 / 0 |
| 718#160 Pokéathlon gatehouse | 82 / 54 / 40 / 26 | 1 / 1 / 1 / 1 | 82 / 54 / 40 / 26 | 1 / 1 / 1 / 1 |
| 718#160 Mt. Moon | 82 / 54 / 40 / 26 | 0 / 0 / 0 / 0 | 82 / 54 / 40 / 26 | 0 / 0 / 0 / 0 |
| 718#160 Celadon Gym | 82 / 54 / 52 / 47 | 0 / 0 / 0 / 0 | 82 / 54 / 52 / 46 | 0 / 0 / 0 / 0 |
| 718#160 Goldenrod Dept. Store 6F | 122 / 84 / 85 / 62 | 40 / 27 / 28 / 20 | 122 / 85 / 85 / 63 | 40 / 28 / 28 / 20 |
| 718#160 Route 1 (60 fps) | 82 / 55 / 53 / 50 | 0 / 0 / 0 / 0 | 82 / 54 / 52 / 46 | 0 / 0 / 0 / 0 |
| 718#160 Route 1 after a warp (30 fps) | 163 / 107 / 79 / 51 | 81 / 53 / 39 / 25 | 163 / 107 / 81 / 53 | 81 / 53 / 40 / 26 |
| 718#160 Viridian City (30 fps) | 165 / 109 / 81 / 53 | 83 / 55 / 41 / 27 | 165 / 109 / 81 / 53 | 83 / 55 / 41 / 27 |
| 718#160 Viridian Forest (30 fps) | 163 / 107 / 79 / 53 | 81 / 53 / 39 / 26 | 163 / 107 / 81 / 53 | 81 / 53 / 40 / 26 |
| 718#160 S.S. Anne (30 fps) | 165 / 109 / 81 / 53 | 83 / 55 / 41 / 27 | 165 / 109 / 81 / 53 | 83 / 55 / 41 / 27 |
| Route 1 promoter talk (60 fps) | 83 / 57 / 53 / 52 | 1 / 1 / 1 / 1 | 83 / 56 / 52 / 48 | 1 / 1 / 1 / 1 |
| Route 1 promoter talk after a warp (30 fps) | 189 / 127 / 93 / 61 | 94 / 63 / 46 / 30 | 189 / 127 / 93 / 61 | 94 / 63 / 46 / 30 |
| Seven Island tourist talk | 67 / 45 / 33 / 22 | 0 / 0 / 0 / 0 | 67 / 45 / 33 / 22 | 0 / 0 / 0 / 0 |

(The original printer's own numbers differ between the two builds in the idle
Route 1 scene: there the loop ends within a line of VBlank, see below, and the two
ROMs differ slightly before the message, so the same scene drops different frames.
Each speed is compared with the original printer of its own ROM.)

No speed drops more frames than the original printer in any scene, and no speed
drops a frame only because of its extra glyphs (the gates check both). In 15 of the
17 scenes the speeds are strictly ordered. Two are not, and cannot be without making
glyphs cheaper (the glyph cache):

- **Goldenrod Dept. Store 6F: SLOW = MEDIUM.** The loop passes alternate: a task at
  about line 167 has room for exactly one glyph (it ends at 180, the loop at 189; a
  second glyph would end it at 199); a task at about line 175 ends its first glyph at
  188, so that frame is lost anyway (the original printer drops it too). MEDIUM
  draws 1 and 2 there, its physical maximum: a second glyph in the 167 pass would
  drop a frame the original keeps. SLOW also draws 1 and 2, because its two-glyph
  turn, kept by the frame stop in the 167 pass, falls into the lost pass. Both are at
  the maximum the frames allow; the gate shows that no frame stop gave up a glyph
  that would have fitted.
- **Idle Route 1: MEDIUM one frame slower than SLOW.** The same structure one line
  from the edge: a task at about line 169 ends its single, mandatory glyph at 182 and
  the loop at 191-193, so whether that frame drops is decided by the original glyph
  alone (the original printer drops 35 of its 88 frames). SLOW and MEDIUM draw
  exactly the same per pass (1, then 2 in the lost pass); MEDIUM's run had one more of
  those forced drops. Without forced drops both take the same number of frames. This
  is an inversion of one frame that the batching cannot influence.

The gates accept a tie or inversion between two speeds only at this physical cap:
neither speed stopped a glyph that would have fitted (judged from the observed frame
ends), and the faster speed's frames without its forced drops are at most the slower
one's. Everything else must be strictly ordered.

Light 60 fps scenes leave room for two or three glyphs per frame and every speed
keeps its full budget. In 30 fps scenes (Route 1 after a warp, Viridian, the forest,
the S.S. Anne) the field work takes longer than a frame, so the printer task runs
after a lost VBlank with most of a frame ahead; every speed keeps its full budget
there too. MEDIUM and FAST are two frames slower than before on two 30 fps messages:
the printer's first decision after a second without text uses `REST_SEED`.

## Battle

Battle text runs in VBlank (the loop pass starts at line 192, the task runs at about
line 220-260 and the pass ends before the next VBlank), so every speed keeps its
budget. The battle gate (`battle_pacing.py`) now plays seven battles (trainers 1, 2
Steven, 5 Picnicker Amelia, 30 Whitney, 8 Rival Blue, 40 and 50: battle start and
three turns each, or until the battle ends). Fisherman Noah (100), Cynthia (3),
Youngster Sol (6) and Rich Boy Howard (10) are excluded: the fixture's only Pokémon
(Lv 9) faints and the black-out waits for a button, with the original printer too.

The review saw pauses after a message differ from the original's by a frame and
suspected double printer runs. What was found:

- **Frames versus loop passes.** A battle pass runs from one VBlank start to the
  next, but emulator frames are scans (lines 0-262). When a pass ends after line 0,
  one emulator frame holds two loop passes and two printer task runs, so an interval
  counted in frames can be one shorter than in passes, and where a batch ends decides
  in which of the two runs a step falls. In the final run, last glyph to printer
  removal differed between frames and passes in 28 of 308 removals (the trainers'
  opening lines, removed by the battle about 100 frames later); for every other
  message both were 1. So the gate compares the battle's waits in loop passes.
- **The pauses themselves.** Measured in passes, a pause can still differ from the
  original printer's by one or two passes. The original printer alone does the same:
  replayed from the same checkpoint with its start delayed by 1-40 frames, the pause
  after "Blazor used Scratch!" (trainer 1, turn 3) is 249 or 250 frames depending
  only on the delay (249 at delays 0, 4, 8, 17, 21, 30, 34, 38). In those replays the
  RAM of a 0- and a 1-frame-delayed run differs during the whole pause only in the
  sound library's work area (`0x021DC4A0`.., initialised by the NITRO sound code at
  `0x020C6BE0`) and two timer words (the RTC refresh counter `0x021CFE94`, the
  loop-pass counter `0x021D00C0`), until the pass in which one run moves on. The
  game's LC random number generator is identical. So the battle waits for its sound
  effect or cry to end, and the sound engine runs on the ARM7's own sound-frame clock
  (about 5.2 ms), not on video frames: the pass in which the battle sees the sound
  end depends on the absolute timing, which faster text changes. (Aligning only the
  end of the message is not enough: SLOW, delayed so that it finishes the message on
  the original's frame, still paused 250 against 249.)

Rule (`text_speed_checks.battle_pacing_errors`): the first glyph and the end-of-text
step must be exactly as many passes after the printer's start and last glyph as with
the original printer. The pause after each message (passes) and the completed text's
on-screen dwell (frames) must equal the original's, or be a value the original
printer itself shows when its run is replayed from the same checkpoint with its start
delayed by 1-12 frames (the gate runs those replays whenever a value differs).
In the final run 14 of 231 pauses of the three speeds differed from the original printer's (by +1, -1 or -2 passes), all values the original itself shows in its replays; 217 were equal. Each segment must also be shorter by exactly the printing frames saved
plus those pause differences, with an identical lead-in.

## How the gates check it

Model (`text_speed_checks.task_errors` with `gate_common.PrinterTrace`): the trace
hooks every load in `print_task` and `frame_end` and keeps those whose effective
address is VCOUNT or the VBlank counter, so it sees exactly the values the payload
reads. It mirrors the payload's frame state from those readings only and compares it
with the payload's RAM before every reading; each task's decisions must equal the
mirror's (`FrameModel.decide`), a task draws at least once, reads the line after every
render, marks its end once if it drew, stops only for a reason (budget, control,
render result, frame stop). NORMAL (and the unknown value 3) must delegate every task
to the original printer task.

Product (`text_speed_checks.order_errors`, in every gate that compares speeds, and
the `scenes` gate over the 17 scenes above), per message (D-1604):

- NORMAL equals the original printer (value 3) exactly: frames, dropped frames,
  printing and glyph tasks, pages, every glyph task's slack;
- frames: FAST at most NORMAL's, strictly fewer when any NORMAL glyph task's pass
  had room for one more glyph (slack of at least FAST's median extra-glyph cost + 2);
- FAST drops no more frames than NORMAL;
- no frame is dropped only because of the batch's extra glyphs (the pass, without
  the extra glyphs' lines, would have ended before VBlank);
- no frame stop gave up a glyph that would have fitted: with one more glyph of the
  message's median measured cost the pass would still have ended two or more lines
  before VBlank (stops taken before any cost of the scene was measured are exempt).

(Historical, removed with SLOW: the SLOW floor and the original > SLOW > MEDIUM >
FAST order.)

These rules use only observed frame ends, not the model's constants, so a payload
that is too conservative, or the fixed `cf50a23` rule, fails even when the gate's
model is changed to match it (fault matrix in [the recipe](text_speed_release_checks.md)).

## Printer catch-up in 30 fps maps (D-1603, provisional)

Measured 2026-10-07: in most outdoor maps the hack (and the English build) printed
about 2.0 frames per glyph against vanilla US FAST 0.98. The cause is the game loop
(`NitroMain`, CN/EN `0x02000D90`-`0x02000E10`, US `0x02000DAC`-`0x02000E42`):

- US: logic, main tasks, print queue (`gSystem+0x24`), then a VBlank wait unless the
  VBlank handler already counted one during the pass (`gSystem+0x30`, incremented at
  `0x0201A0AE`), then render, the 3D swap request, the print queue **again**, and the
  wait. Logic is capped at 30 fps, the print queue runs twice per pass.
- CN/EN: logic, main tasks, print queue, render, swap request, one wait. Logic is
  uncapped; when a pass spans two VBlanks (most outdoor maps, 320-340 lines even
  without text) the printer runs once per two frames.

The loop came with the hack's base build, not a byte patch: the ROM header is
`NTR-IPKJ-JPN` (Japanese HeartGold), every ARM9 function after the loop is shifted
(e.g. US `0x02000E6C` = CN `0x02000E38`) and the literal pool follows the loop with no
gap. No Japanese ROM is available to confirm that the retail Japanese loop is the same.

Print queue audit (CN ARM9 and all 120 overlays): tasks reach `gSystem+0x24` only through
`0x0200DEAC`, called by the printer slot allocator `0x02020728` (one caller,
`0x020209A6` in AddTextPrinter, task function the printer task `0x02020A1D`, which the
payload redirects to `print_task`) and by overlay 68 (`0x0220FCB6`, a sprite render task
`0x0220FE09`; the same call exists in US overlay 71, so it is not hack-added). At run
time (Route 1, Viridian, Viridian Forest, Routes 29/30, New Bark, Cherrygrove and its
Pokémon Center, Violet, every X-menu screen, saving, a trainer battle, NPC talk, the
Pokéathlon gate, the Ecruteak theater) the queue held only printer tasks.

Design: `pass_end` (the loop's redirected call before its wait) calls `frame_end`, then,
if a VBlank passed during this pass (the VBlank counter moved by two or more since the
previous pass end: the frame is lost anyway), runs each text printer task once more,
where vanilla makes its second queue run. Only printer tasks run (the 8 slots at
`0x021D0EFC`), only tasks present before the catch-up, only printers whose next step
draws a glyph (RenderText state 0, next unit past newlines not a control): prompts,
scrolls, page clears, button waits and the end of the text keep one step per pass, so
input is polled exactly as before. The catch-up starts only if one glyph and the
measured rest fit before the next VBlank, so it never pushes the pass past a VBlank,
and a catch-up batch's end is not a rest sample. Passes within one frame (60 fps
scenes) are unchanged. All four settings (and reserved value 3, the original printer)
get it. Consequences: explicit text pauses and auto-advance waits counted in printer
turns run at vanilla speed in 30 fps maps (half as long as in the hack); script waits
counted in frames do not change; scripts synchronise with text by waiting for the
message, not by time.

Gate `field-rate` (`field_rate.py`) compares, per scene from one checkpoint, the
catch-up on and off (off: a hook clears the state's `ended` byte at `pass_end` entry).
Fault `no-catch-up` (catch-up never runs) must fail it with 'frames per glyph'.

## Limits

- Hardware: the costs are measured at run time, so different card or CPU timing on a
  real DS changes the samples, not the rule. The seeds, the margin and the stale
  period were chosen from DeSmuME measurements, and the frame-end hook's own cost (a
  few dozen cycles per loop pass) was not measured on hardware. A device check is
  still needed.
- The VBlank branch of `left` (`192 + 263 - line`) is the correct deadline for a task
  that runs in VBlank, but in every measured VBlank-time task (battle, lost frames)
  the deadline was 200 or more lines away, so the unsigned value of `192 - line`
  would decide the same. No gate can tell the two apart; it only matters if a
  VBlank-time pass needs nearly a whole frame after the text task.
- Two scenes reach the physical cap (above); MEDIUM is one frame slower than SLOW on
  idle Route 1 because of forced drops. Only cheaper glyphs (the glyph cache) can
  change that.
- The sound rule accepts a battle pause only if the original printer shows that
  value in 12 delayed replays; a value it would show only with other delays fails the
  gate (none seen).
