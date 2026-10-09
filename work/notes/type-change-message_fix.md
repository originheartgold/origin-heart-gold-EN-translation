# Type-change battle messages name the move instead of the type (fix `type-change-message`)

**Status (2026-10-09): fixed on branch `fix/type-change-message`** (D-2276, a user-approved exception to D-1337;
answers the hack finding D-1461). The fix is `work/patches/type-change-message/` (overlay 14, 14 bytes in three
regions).

## Report

Discord: Kecleon's Color Change says it changed to the type of "[move used]": "Kecleon transformed into the Air
Slash type!". Earlier (D-1461): after Protean or Soak the message names the move ("…transformed into the Soak
type!"). The type change itself is right; only the word in the message is wrong.

## Cause

The hack's battle engine prints battle_string messages (narc `battle/string/battle_string.narc`, NARC table
index 277) through one word expander in overlay 14, `0x02225A3C`. The bank 1 builder (`0x02225EA8`, side
offset, then `GetMsg`) and the bank 2 builder (`0x022257F4`) both call it with the message's argument array
(r7). For each `{VAR:01xx:slot,0}` tag in the template it switches on the kind `xx` (0-15; jump table of
halfword offsets at `0x02225A9E`, `add pc, r0` at `0x02225A9C`, base `0x02225AA0`), buffers `args[slot]` into
the message slot with the matching arm9 function and then expands the slot into the output (`0x0200C7F0`):

| Kind | Case | Buffers with |
|---|---|---|
| 0 | `0x02225AE0` | trainer name (`0x0200C22C`) |
| 1 | `0x02225B04` | species, fallback 4 characters for an invalid Pokémon |
| 2 | `0x02225B38` | nickname, the same fallback |
| **3** | **none: `0x02225BBA`, the shared tail** | **nothing** |
| 6 | `0x02225B6C` | ability (`0x0200BFB0`, a027 bank 711) |
| 7 | `0x02225B8A` | move (`0x0200BF40`, a027 bank 739) |
| 9 | `0x02225BAE` | item (`0x0200C01C`) |
| 12 | `0x02225B7A` | party Pokémon's nickname (`0x02225A10`; Exp. messages) |
| 14 | `0x02225ABE` | trainer class |
| 15 | `0x02225B98` | number (`0x0200BF1C`) |

Kind 3 (`{VAR:0103}`, the type name) has no case, so the slot keeps the word the previous message buffered
there. In battle that is almost always the move of '… used Gust!', which is why the message names the move.
The Chinese template is the same (变成了{VAR:0103:1,0}属性), so the text is not at fault.

Only battle_string bank 1 #1212-#1219 use kind 3 (checked over all four banks): #1212-#1215 '{nickname}
transformed into the {type} type!' (own / wild / foe / partner trainer) and #1216-#1219 '{type} type was added
to {nickname}!'. #1212 is named once in overlay 14, by the type-change handler `0x0220E6E0`: it reads the new
type pair (`type1 | type2 << 5`), and when the Pokémon ends up with one type that differs from the old pair it
queues message 0x4BC with args (Pokémon, type1, 0xFFFF) (`0x02224C50`, the server's message queue). The
argument is the type; only the expander drops it. No caller of #1216 was found in overlay 14 by the fixer, but
the review run below shows Trick-or-Treat and Forest's Curse printing #1217 (they reach the builder through
another path). The bank 1 builder's side offset (`0x02225E40`) is only 0 (own side, also an ally's Pokémon), 1
(wild) or 2 (foe trainer), so the fourth form (#1215 / #1219, with the partner trainer's name) is never built.

`BufferTypeName` is arm9 `0x0200C084` (fmt r0, slot r1, type r2; a027 bank 724, NARC 0x1B), the same
signature as the move case's `0x0200BF40`.

## Fix

Three edits in overlay 14 (`work/patches/type-change-message/type-change-message.listing`):

1. `0x02225AA4` (file `+0x252C4`), the jump-table entry for kind 3: `0x011A` (tail) → `0x00BE` (`0x02225B5E`).
2. `0x02225B4A` (`+0x2536A`): the nickname case's fallback for an invalid Pokémon (four `String_AppendChar`
   calls with the literals 0x1B9, 0xCED, 0xBDD, 0x1BA, then `b tail`) is the same code as the species case's
   fallback at `0x02225B16` (same literals, same calls, same branch; only the PC-relative encodings differ).
   It now starts with `b 0x02225B16`. The same characters are appended; the nickname path for a valid
   Pokémon is untouched.
3. `0x02225B5E` (`+0x2537E`), the last 12 bytes of the freed copy: the type case, the move case's pattern with
   the type function: `lsl r2, r4, #2; ldr r0, [sp, #8]; ldr r2, [r7, r2]; add r1, r4, #0; bl 0x0200C084`. It
   falls into the copy's own `b tail` at `0x02225B6A`, unchanged.

The first 18 bytes of the freed copy (`0x02225B4C-0x02225B5D`) stay as they were and are unreachable. The
guards check the dispatch, both fallbacks, their literal pool, the move case and the tail. overlay 14 has a
.bss, so it cannot grow; the space comes from the duplicate fallback. The armips output was also compared with
the bytes encoded by hand (`test_asmpatch.py` GOLDEN, `overlay14` SHA-1 `4e6b2fc6…`).

## Evidence (DeSmuME, 2026-10-09)

Scenario `typechange` (`emu_fixes.py`, `emu_harness.py fixes --case type-change-message`): three scripted wild
battles from `full_bag_6mons.sav`: Kecleon (Color Change) with Splash hit by a wild Pidgey's Gust; Mewtwo's Soak
on a wild Geodude; Greninja (Protean) using Quick Attack on a wild Shuckle. Hooks: the bank 1 builder's `GetMsg`
call (`0x02225EC4`, the side's string id), the expander's return (`0x02225C00`, r5 = the finished String),
`BufferTypeName`. The judge compares the finished message with the type's and the move's names read from the
ROM's a027 banks 724 / 739.

| ROM | Color Change (1#1212) | Soak (1#1213) | Protean (1#1212) | BufferTypeName from the expander |
|---|---|---|---|---|
| untouched Chinese v4.0.3 | 变隐龙 变成了**起风**属性！ | 野生的小拳石 变成了**浸水**属性！ | 甲贺忍蛙 变成了**电光一闪**属性！ | never |
| build without the fix (`--without type-change-message`, = develop 207caca's build, SHA-1 `d01ada95…`) | Kecleon transformed into the **Gust** type! | The wild Geodude transformed into the **Soak** type! | Greninja transformed into the **Quick Attack** type! | never |
| full build (SHA-1 `a57e9813…`) | Kecleon transformed into the **Flying** type! | The wild Geodude transformed into the **Water** type! | Greninja transformed into the **Normal** type! | types 2, 11, 0, from `0x02225B6A` |

`emu_harness.py fixes --case type-change-message`: PASS (fixed ROM: fixed, control: original). The message
window sheets (`typechange_<case>.png`) show the same text on screen. Regression check: `vqueue --case probe`
(Bounce, Fly, Future Sight both ways, Soak, Protean) gives the same verdicts on the full build and the control
(`bounce one_turn, fs_foe [1465], fs_own [1464], soak [1213], protean [1212]`); every other message of the runs
(used …!, But nothing happened!, The wild … used …!) prints normally.

Review run (2026-10-09, DeSmuME; same hooks, more moves): on the fixed build Conversion (Porygon with Ice Beam
first: 1#1212 'Ice'), Camouflage (1#1212 'Normal'), Magic Powder (1#1213 'Psychic'), Trick-or-Treat and Forest's
Curse (1#1217 'Ghost' / 'Grass type was added to the wild Magikarp!') and Soak on a trainer's Glalie (1#1214
'The foe's Glalie transformed into the Water type!') all name the type, each through the new case (return
address 0x02225B6A); the control build and the Chinese ROM print the move's name in every one. Reflect Type
prints its own message (1#1476 '... became the same type as Magikarp!', no type tag), unchanged. melonDS
(no hooks; a wild Shroomish met in grass on map 109, Soak, read from the screen): fixed 'The wild Shroomish
transformed into the Water type!', control '... the Soak type!'; no ARM9 exception, no hang.

Not tested in game: #1215 / #1219 (never built, above) and the nickname case's fallback for an invalid Pokémon.
That fallback is the species case's code: both load the same four literals (each `ldr r1, [pc, #n]` resolves
to 0x02225C10 / C14 / C18 / C1C), call String_AppendChar with r0 = r5, and branch to the tail; neither reads
a register the other path sets differently, and nothing else branches into or points at the freed bytes
0x02225B4C-0x02225B69 (checked over all of overlay 14). So the output is the same.
