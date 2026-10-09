# Chinese (错误) in battle text: the hack's error marker (fix `battle-message-error-marker`)

**Status (2026-10-09): fixed on branch `fix/battle-text-chinese`.** D-2276 (the fix, a user-approved exception to
D-1337), D-2277 (the hack logic behind it, open: reported, not changed).

## Reports

- Discord, rc6: "Fighting a Nuzleaf (holding a Quick Claw) in a trainer battle just past the bridge in Cerulean
  City, it said 'the foe (2 Chinese characters) Pikachu's accuracy...'. The 2 Chinese characters were in
  parentheses. Despite Pikachu being named, I was fighting it with a Linoone, though I did switch Pikachu out the
  turn prior. The Nuzleaf didn't use an accuracy-related move."
- Discord, rc6: "an untranslated Chinese word after attract/infatuation" (DraStic screenshot, not seen).
- Older, unreproduced: in double battles with an ally, the ally's Pokémon is called "Foe's" during move use. Not
  reproduced here (see 'Not covered').

## Cause

The two Chinese characters are 错误 ("error"). They are not message text: every battle_string and a027 string
has English, and none contains Chinese. The hack's battle message formatter (overlay 14, 0x02225A3C, called by
0x02225EA8 for every battle_string message) expands the template's control codes itself. For the Pokémon-name
tags 0x0101 and 0x0102 (jump-table cases 1 and 2) it calls a helper (0x02225978 / 0x022259C4) with the
message's Pokémon reference. A reference outside 1..25, or one that resolves to nothing, makes the helper
buffer reference 1 instead and return 0; on 0 the formatter appends four hardcoded character codes, '(' 0x0CED
0x0BDD ')' = (错误), with four `String_AddChar` calls (0x02225B16 for 0x0101, 0x02225B4A for 0x0102; the codes
sit in the literal pool at 0x02225C10), and then appends the name buffer as usual. The name that follows is
the fallback's: the player's first party Pokémon, also while another one is fighting (the report's Pikachu).
`hardcoded.py scan` looks for 0xFFFF-terminated strings, so four separate immediates were invisible to it.

Which messages reach it (hack logic, D-2277; identical on the untouched Chinese ROM):

| Trigger | Message read | Chinese ROM shows | English build (before) |
|---|---|---|---|
| Nature Power on Route 24 (the player's Linoone, or Camper Ward's Nuzleaf) | 1#120 / 1#122 (accuracy rose drastically; no "turned into" line before it; the move still hits) | (错误)直冲熊的命中率巨幅提高了！ | (错误)Linoone’s accuracy rose drastically! / The foe’s (错误)Pikachu’s accuracy rose drastically! |
| Attract: every turn the infatuated foe acts | 1#454 | 长臾叶让对手的(错误)吉利蛋着迷了！ | The foe’s (错误)Linoone fell in love with Nuzleaf! |

The report's "the foe" + Pikachu is the foe variant (the message's battler is Nuzleaf) with the fallback name.
The Quick Claw is unrelated (its own message, 1#1390, prints correctly).

## Fix

`work/patches/battle-message-error-marker/` (kind code, overlay 14, two 34-byte regions):

- 0x02225B16 (case 0x0101's error path): `push {r4}`, `adr r4, text`, a loop `ldrh r1, [r4]` / end at 0xFFFF /
  `bl String_AddChar(r5, r1)` / `r4 += 2`, `pop {r4}`, `b 0x02225BBA` (the same tail as before). r4 holds the
  tag's buffer index, which the tail reads, so it is saved; r5 (the output) is not touched.
- 0x02225B4A (case 0x0102's error path): `b 0x02225B16`, then the text: `(Error) ` (8 characters, 0xFFFF end).
- When the marker appears and which name follows it are unchanged. The literal pool stays (no longer read).

Text: six battle_string lines break earlier so the line still fits with the 46-px marker and a 10-character
nickname (QA worst case): 1#121-123 '…’s{NEWLINE}accuracy rose drastically!', 1#453-455
'…{NEWLINE}fell in love with …!'. Without the rewrap, 1#454 cut 'with' at the window edge in the emulator.

## Sweep

Every `bl String_AddChar` (0x02026FDC) in arm9 and all 120 overlays of the Chinese ROM, with the character
loaded into r1 just before it: the only hanzi are these four calls (错, 误 at both sites). The other caller with
a constant appends 0xE000 (a line break, overlay 103). Strings in other forms were covered by the earlier
`hardcoded.py scan` (work/notes/hardcoded_text.md). Every battle_string id has English (2881 strings, no
Chinese in `en`). So after this fix no battle message can print Chinese from the code or the banks.

## Evidence (2026-10-09)

Scripts and outputs in the session scratchpad and `work/build/repro/` of the worktree (not in git).

- DeSmuME, Chinese ROM: Nature Power and Attract as in the table (screenshots `cn_np3/shot46`,
  `cn_attract2/shot50`).
- DeSmuME, English build of develop 207caca (before): Camper Ward battle, Pikachu lead switched to Linoone:
  "The foe’s (错误)Pikachu’s accuracy rose drastically!" after the foe's Nature Power, exactly the report.
- `emu_harness.py fixes --case battle-message-error-marker` (scenario `battle-error-marker`): PASS. Fixed build:
  "(Error) " appended from 0x02225B28 with 1#120; control (`--without battle-message-error-marker`): ( 错 误 )
  from 0x02225B52/5A/62/6A; Chinese reference: ( 错 误 ).
- Fixed build, DeSmuME, by hand: "(Error) Linoone’s accuracy rose drastically!", "The foe’s (Error) Pikachu’s
  accuracy rose drastically!" (foe's Nature Power after a switch), "The foe’s (Error) Chansey fell in love with
  Nuzleaf!" (before the rewrap the line was cut after 'wi').
- melonDS 1.1, wild battle in Route 24 grass, Linoone with Nature Power: control '(错误)Maximilian’s accuracy
  rose drastically!', fixed '(Error) Maximilian’s accuracy rose drastically!'; the battle goes on, no data or
  prefetch abort, no undefined instruction on either build.
- The full build differs from the `--without` build only in overlay 14, the two regions (byte compare).

## Not covered

- The wrong subject (fallback name, no "Nature Power turned into" line, the infatuation message's argument) is
  the hack's logic, reported as D-2277 for the user to decide.
- The older "ally's Pokémon called Foe's in double battles" report was not reproduced. The formatter picks the
  own / wild / foe variant from the message's battler (0x02225E40: own if it is the player's battler, wild in a
  wild battle, else a side check 0x02228600); a tag battle with an ally was not set up.
