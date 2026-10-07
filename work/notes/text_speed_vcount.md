# Text speed: frame-aware batching (D-1601)

The native batching loop in `work/patches/text_speed/native.c` stops drawing
further glyphs in a task when the current frame is nearly used up. This note
records why, how the rule and its two constants were derived, and what was
measured before and after. Branch `codex/text-speed-research`.

## The problem

An independent review measured, deterministically, that in ordinary 60 fps field
dialogue the game drops frames while a task draws two or three glyphs:

- The game loop wakes at VBlank (display line 192) and runs the field work first;
  the printer task starts late in the frame, at about line 150-180. If the loop is
  still running when the next VBlank starts, the game waits for the one after, and
  that frame is dropped (no game update; the printer task does not run).
- Each glyph costs about 10 display lines. Most of that is not drawing: the
  hack's font is read lazily from the cartridge, two card transfers per glyph
  (109 card transfers for the 54-glyph trainer page). The window copy to VRAM is
  already done once per task (2-3 lines).
- So a task that starts at line 163 has room for one glyph, a task at line 155 for
  two. The previous loop drew its whole budget (2 or 3) regardless, ended at about
  line 190-200 and the game ran at 30 fps while printing. Trainer page, 54 glyphs:
  SLOW / MEDIUM / FAST 37 / 38 / 34 frames with 1 / 11 / 16 dropped frames; the
  original printer (one glyph per task) 55 frames with 1 dropped frame.

## The rule

Every task still draws at least one glyph (or handles one control), exactly like
the original printer, so no setting can be slower per task than the original.
Before each further glyph the loop reads VCOUNT (I/O register `0x04000006`, the
current display line; read only, so it is not ARM9 code and needs no reviewed
dependency range) and computes the lines left until the next VBlank starts:

    left = 192 - line            for line 0..191
    left = 192 + 263 - line      for line 192..262 (in VBlank: a whole frame ahead)

It stops when `FRAME_LOST_LINES <= left < MIN_LINES_FOR_GLYPH`, i.e. when one more
glyph would not fit before the VBlank but stopping now still would. With
`left >= MIN_LINES_FOR_GLYPH` the glyph fits. With `left < FRAME_LOST_LINES` the
loop cannot reach the halt before VBlank even if it stops now: the frame is lost
anyway, the deadline becomes the following VBlank (a whole frame away), and the
batch may continue. The per-task budgets (SLOW 1/2, MEDIUM 2, FAST 3) stay the
maxima, so a batch can never run long.

Field and battle differ, and the rule is correct in both because it is relative to
the next VBlank, not to an absolute line:

- Field (60 fps): tasks start at about lines 150-180, so the rule is active.
- Battle: the printer task runs in VBlank (lines 220-260), right after the loop
  wakes; `left` is 195-235 and the whole budget is drawn, as before. An absolute
  "stop in VBlank" rule (tried first) made every battle speed as slow as the
  original printer (SLOW identical to the original over battle start and two turns).
- Heavy field scenes where even the original printer drops every other frame (the
  script-injected corpus messages after the Options menu): the first glyph often
  ends at line 182-197. Stopping there no longer saves the frame, so the
  `FRAME_LOST_LINES` zone lets the batch continue. Two earlier variants failed
  there: "stop when `left < 22` or when a VBlank started during the task" made FAST
  take 74 frames for a message the original prints in 81 and SLOW 83; "stop when
  `left < 22`" made MEDIUM slower than SLOW on another message (190 / 187 frames).
- VCOUNT wrap: there is no start-of-task reference to go wrong. After a VBlank has
  started during a task, `left` is again the distance to the next VBlank (200+
  lines), which is the right deadline once the frame is lost; the budget (at most
  three glyphs, about 30 lines) bounds the batch.

SLOW's phase: SLOW alternates one- and two-glyph tasks. If a two-glyph task is
stopped by the frame rule, the phase is not flipped, so the next task keeps the
two-glyph turn. Without that, in the trainer scene every two-glyph turn fell on a
late task and SLOW printed exactly as slowly as the original (55 frames).

## Deriving the constants

Measured with the review probe (per frame: task entry, each glyph, each VCOUNT
check, window copy, idle halt) on the trainer page:

| From the VCOUNT check | Lines |
| --- | --- |
| stop now: window copy + rest of the game loop up to the idle halt | 7-8 |
| one more glyph (two cartridge font reads), then stop | 16-18 |
| first glyph after task entry (includes the colour setup) | 12-13 |

- `MIN_LINES_FOR_GLYPH = 20`: one more glyph costs at most 18 lines from the check,
  and the loop must reach its halt by line 191, so the check may be at line 173
  (19 lines left) at the latest; one line of margin gives 20. Measured: a check
  with 19 lines left ended the loop at line 190-191, with 22 left at 186-188.
  Margins compared on the trainer page (SLOW / MEDIUM / FAST frames, every speed
  with the original's 1 dropped frame): 22 → 37 / 37 / 36 (MEDIUM ties SLOW),
  21 → 37 / 37 / 36, 20 → 37 / 36 / 35, 19 → 37 / 35 / 33 (no margin left).
  20 is the smallest value with a margin and gives the strict order.
- `FRAME_LOST_LINES = 7`: the least measured cost of stopping. With 6 or fewer lines
  left a stop ends the loop at line 193 or later: the frame is lost either way.

Both are named constants in `native.c` and are pinned again independently in
`work/tools/text_speed_checks.py`; a unit test keeps the two equal. The gates check
every VCOUNT decision of the binary against that model (see below), so a changed
threshold in the payload fails the gates.

Limits: the costs were measured in DeSmuME in two field scenes. A scene whose
remaining loop work after the printer task is heavier than measured can still drop
a frame the original would not; the gates require every speed to drop at most one
frame more than the original in every measured message. Hardware card timing may
differ from DeSmuME's; a device check is still needed.

## Before and after

Frames from the first to the last glyph (sum of page spans for multi-page
messages) and dropped frames (frames inside that span in which the printer's task
did not run), original printer / SLOW / MEDIUM / FAST. Before: candidate
`e9aedbb1…2d13` (no frame rule). After: the payload in this commit.

| Scene | Before: frames | Before: dropped | After: frames | After: dropped |
| --- | --- | --- | --- | --- |
| Natural trainer page (54 glyphs) | 54 / 36 / 37 / 33 | 1 / 1 / 11 / 16 | 54 / 37 / 36 / 35 | 1 / 1 / 1 / 1 |
| Fallback scene, same page | 54 / 36 / 28 / 29 | 1 / 1 / 2 / 12 | 54 / 37 / 35 / 31 | 1 / 1 / 1 / 1 |
| Corpus 48#20 | 81 / 55 / 41 / 27 | 38 / 27 / 20 / 13 | 81 / 54 / 45 / 35 | 38 / 25 / 20 / 16 |
| Corpus 48#26 | 268 / 184 / 141 / 91 | 126 / 89 / 70 / 45 | 270 / 179 / 141 / 96 | 128 / 83 / 67 / 45 |
| Corpus 48#60 | 531 / 353 / 261 / 173 | 265 / 176 / 130 / 86 | 531 / 353 / 261 / 173 | 265 / 176 / 130 / 86 |
| Corpus 457#123 | 115 / 75 / 55 / 35 | 57 / 37 / 27 / 17 | 115 / 75 / 55 / 35 | 57 / 37 / 27 / 17 |
| Corpus 718#160 | 163 / 107 / 79 / 51 | 81 / 53 / 39 / 25 | 163 / 107 / 79 / 51 | 81 / 53 / 39 / 25 |
| Corpus 718#1093 | 513 / 341 / 251 / 169 | 256 / 170 / 125 / 84 | 513 / 341 / 251 / 169 | 256 / 170 / 125 / 84 |
| Controls fixture 718#160 | 205 / 161 / 139 / 111 | 64 / 46 / 38 / 24 | 205 / 158 / 145 / 119 | 64 / 43 / 38 / 25 |
| Battle segment 0 | 31 / 21 / 15 / 10 | 0 / 0 / 0 / 0 | 31 / 21 / 15 / 10 | 0 / 0 / 0 / 0 |
| Battle segment 1 | 47 / 31 / 22 / 14 | 0 / 0 / 0 / 0 | 47 / 31 / 22 / 14 | 0 / 0 / 0 / 0 |
| Battle segment 2* | 154 / 101 / 73 / 46 | 0 / 0 / 0 / 0 | 72 / 47 / 34 / 22 | 0 / 0 / 0 / 0 |
| Battle segment 3* | 114 / 75 / 54 / 34 | 0 / 0 / 0 / 0 | 87 / 57 / 40 / 25 | 0 / 0 / 0 / 0 |

\* Battle turns 2 and 3 are different battles before and after (the RNG follows
frame timing from the checkpoint on), so only their after values compare with each
other. In every battle segment every pause, dwell and printer removal equals the
original printer's exactly, before and after.

Field scenes trade a few frames for no dropped frames: in the controlled fallback
scene MEDIUM took 28 frames before with 2 dropped (most second glyphs happened to
fit) and takes 35 now, FAST 29 before with 12 dropped (slower than MEDIUM) and 31
now; all speeds now drop exactly the original's one frame and are strictly ordered.

The corpus and controls messages run in a heavy scene (after the Options menu,
via an injected script) where even the original printer drops about every other
frame; "dropped" there counts those frames too, for every mode alike. In that scene
the frame rule makes FAST a little slower than before on two messages (48#20: 27 →
35 frames, 48#26: 91 → 96; controls: 111 → 119), because stopping there costs
about 10-11 lines rather than the 7-8 measured in the trainer scene, so some stops
in the 7-10 line zone do not save the frame. A `FRAME_LOST_LINES` of 11 was faster
there (48#20 FAST 26 frames) with no extra dropped frames in the measured scenes,
but would give up frames that stopping saves in the trainer scene; the constant is
kept at the measured minimum.

Natural trainer page: the speeds are strictly ordered, 54 / 37 / 36 / 35 frames,
and no speed drops a frame more than the original (1). The scene leaves room for
about 1.5 glyphs per frame (two glyphs in a frame whose task starts near line 155,
one near line 163), so the speeds are close together there; the differences come
from tasks whose second or third glyph just fits. The gates allow a tie between two
speeds only when the faster one stopped on the frame limit
(`text_speed_checks.frame_order`); any inversion fails. In lighter scenes (battle,
the corpus messages) the speeds keep their full budgets.

## How the gates check it

`gate_common.PrinterTrace` finds the VCOUNT read in the payload by disassembly and
hooks the instruction after it, so it sees exactly the line the code compared. For
every native task `text_speed_checks.task_errors` requires: at least one render; a
frame check after every glyph that has budget left and no control next; the next
glyph exactly when the model allows it (`frame_stop`); and a reason for every task
that drew less than its budget (control next, render result, or a frame stop).
SLOW's phase must flip after a task that drew, except after a frame stop.
Fault fixtures `vcount-ignored` and `vcount-zero-glyph` prove the check is not
vacuous.
