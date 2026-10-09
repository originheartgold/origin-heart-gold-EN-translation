# Chinese (错误) and the wrong Pokémon in battle text (fixes `battle-message-error-marker`, `battle-message-references`)

**Status (2026-10-09): fixed on branch `fix/battle-text-chinese`.** D-2276 (the marker's English), D-2278 (the two
root causes), both user-approved exceptions to D-1337; D-2277 (the hack finding) is resolved by D-2278.

## Reports

- Discord, rc6: "Fighting a Nuzleaf (holding a Quick Claw) in a trainer battle just past the bridge in Cerulean
  City, it said 'the foe (2 Chinese characters) Pikachu's accuracy...'. The 2 Chinese characters were in
  parentheses. Despite Pikachu being named, I was fighting it with a Linoone, though I did switch Pikachu out the
  turn prior. The Nuzleaf didn't use an accuracy-related move."
- Discord, rc6: "an untranslated Chinese word after attract/infatuation" (DraStic screenshot, not seen).
- Older: in double battles with an ally, the ally's Pokémon is called "Foe's" during move use (see 'Ally').

## How battle messages are built

- The hack builds most battle messages as records: MsgRec_Init (0x02225DC0: record, type, id) and MsgRec_AddArg
  (0x02225DEC). Type 1 prints battle_string bank 2 (plain lines); type 2 prints bank 1 (own / wild / foe /
  trainer variants, chosen from a battler). Other lines go straight into the server-to-client stream
  (0x02224C50: op 2 = bank 2, op 3 = bank 1 with a variant battler).
- The arguments are the template's buffers. A Pokémon-name buffer (tags 0x0101 species, 0x0102 nickname) needs a
  Pokémon reference 1..25 (observed: 1-6 the player's party, 7-12 an ally trainer's, 13-18 the foe's, 19-24 a
  second foe's).
- The client's formatter (overlay 14, 0x02225A3C) turns a bad reference (0, or > 25, or one that resolves to
  nothing) into reference 1, the player's first party Pokémon, and puts four hardcoded characters in front of it:
  '(' 0x0CED 0x0BDD ')' = (错误), "error", appended with String_AddChar at 0x02225B16 (tag 0x0101) and 0x02225B4A
  (tag 0x0102). That is the Chinese the players saw. It is not message text, so the translation and the
  hardcoded-string scan (0xFFFF-terminated strings only) both missed it.

## Root causes (D-2277, fixed by D-2278)

| Message | Built by | Bug | Fix |
|---|---|---|---|
| Nature Power: "turned into {move}" | 0x0223F070: MsgRec_Init(rec, 2, 120), AddArg(battle var 0x29 = the called move) | message 120 with a move is bank 2's 2#120 'Nature Power turned into {move}!', but type 2 printed bank 1's 1#120 '{Pokémon}'s accuracy rose drastically!' with the move id as the Pokémon (Earthquake = 89 on Route 24). That is report 1, with the foe variant from the Nuzleaf and the fallback Pikachu | 0x0223F084 `movs r1, #2` → `#1` |
| Infatuation, every turn the infatuated Pokémon tries to move: 1#452-455 '{1}让{0}着迷了' ({0} = the infatuated Pokémon, which also picks the variant; {1} = the one it is in love with) | 0x0221DAEC: emit(op 3, 452, variant = self, args (Condition_GetData(self, 7), self)) | condition 7's data field is always 0; the attracter is the condition's source, word 0 of its 8-byte entry (Pokémon + 0x38 + 7 × 8 = + 0x70; observed 0x0D for a wild attracter, 0x01 for the player's). The arguments were also in the wrong order. That is report 2 | 0x0221DAFC: `bl Condition_GetData` + mask → `ldr r4, [r5, #0x70]` + the same byte mask + nop; 0x0221DB20: the two argument stores swapped |

## Fixes

- **`battle-message-references`** (code, overlay 14, 14 bytes in 3 regions): the two root causes above. Message
  ids, the variant battler, when the lines appear and the condition logic are unchanged.
- **`battle-message-error-marker`** (code, overlay 14, 54 bytes in 2 regions): the marker reads "(Error) " as a
  safety net.
  - 0x02225B16–0x02225B37 (the tag 0x0101 error path, 34 bytes): a loop that appends a 0xFFFF-terminated string
    (r4 saved, r5 the output), ending with the old branch to the tail 0x02225BBA.
  - 0x02225B4A–0x02225B5D (20 bytes): `b 0x02225B16`, then "(Error) " + 0xFFFF.
  - Not touched: 0x02225B5E–0x02225B6B (dead after the branch) and the jump table. The `type-change-message` fix
    (branch fix/type-change-message) uses exactly those (see 'Together with type-change-message').
- Text: battle_string 1#121-123 and 1#453-455 break earlier so the line still fits with the 46-px marker and a
  10-character nickname. Without this, #454 cut 'with' off at the window edge in the emulator.

## Audit: other messages that can reach the fallback

- **Static audit** of every record (284 MsgRec_Init sites, 394 AddArg) and every direct stream message (103
  emits) in overlay 14. For each one I checked the type or op against the bank and the arguments in the template's
  Pokémon-name slots. Script: `audit.py`, in the session scratchpad.
  - Two sites put something other than a reference in a name slot: Nature Power (a move id) and the infatuation
    check (a condition's data field). Both are fixed.
  - Three sites only looked short of arguments. They add their arguments after a branch (2#10 sent out, 2#481
    sent to the PC, 1#594 Frisk), and they print correctly in game.
  - Many arguments come from registers set outside the analysed window, so this is not a proof.
- **Dynamic checks** (DeSmuME, fixed build): no marker in any of these, besides the scenario that forces one.
  - the 24 scripted battles of `sweeps --sweep battle` (all ok);
  - Nature Power and Attract, both sides, wild and trainer;
  - a multi battle (partner Green against Camper Ward and Bug Catcher Tommy) with Attract on a second-slot foe.

## Ally ("Foe's" in a partner battle)

- **Not reproduced.** In a multi battle with a partner trainer (`MultiBattle 1, 960, 109`), the partner's
  Pokémon are references 7-12. Their lines use the plain variant: "Bulbasaur used Leech Seed!", "Bulbasaur
  flinched and couldn't move!", "Jigglypuff used Perish Song!".
- No "The foe's" was seen on an ally line. The variant choice is 0x02225E40 (own when the battler is the player's
  side, else wild or foe after a side check).
- The report might come from a different battle type (a scripted partner such as Steven or a link battle); not
  set up.

## Evidence (2026-10-09)

Scripts in the session scratchpad; screenshots and logs in `work/build/repro/` and `work/build/harness/` of the
worktree (not in git).

**Chinese ROM (DeSmuME):**
- "(错误)直冲熊的命中率巨幅提高了！" after Nature Power.
- "长臾叶让对手的(错误)吉利蛋着迷了！" (infatuation).
- Traced records: Nature Power MsgRec_Init(type 2, 120, arg 0x59); infatuation emit(452, variant 0x0D, args 0,
  0x0D); condition 7's entry word 0 = the attracter's reference.

**Develop build before the fixes:**
- Report 1 word for word: "The foe’s (错误)Pikachu’s accuracy rose drastically!" (Pikachu switched out for
  Linoone).
- "The foe’s (错误)Linoone fell in love with Nuzleaf!"

**Fixed build (DeSmuME):**
- "Linoone used Nature Power!" → "Nature Power turned into / Earthquake!" (also after the foe's Nature Power).
- "The foe’s Nuzleaf / fell in love with Chansey!"
- "Tauros fell in love with / Chansey!" (the player infatuated by a wild Chansey).
- "The wild Sunkern / fell in love with Chansey!"
- Multi battle: "The foe’s Butterfree / fell in love with Chansey!" (second foe, reference 19).

**`--without battle-message-references`:** "(Error) Tauros fell in love with Tauros!", "(Error) …’s accuracy rose
drastically!".

**Fix scenarios** (`emu_harness.py fixes`): `battle-references` PASS, `battle-error-marker` PASS (forced
reference: "Ward sent out (Error) Linoone!" fixed, ( 错 误 ) on the control and the Chinese ROM).

**melonDS 1.1** (wild battle in Route 24 grass, Nature Power):
- Chinese ROM: "(错误)Maximilian的命中率巨幅提高了！".
- `--without battle-message-references`: "(Error) Maximilian’s accuracy…".
- Fixed: "Nature Power turned into…".
- No ARM9 abort or undefined instruction on any of them.

**Byte compare:** the full build differs from each `--without` build only in that fix's regions.

## Sweep for hardcoded Chinese

I checked every `bl String_AddChar` with a constant character in arm9 and all 120 overlays. The only hanzi are
the marker's (错, 误 at both sites); the other constant is 0xE000, a line break in overlay 103. All 2881
battle_string strings have English.
