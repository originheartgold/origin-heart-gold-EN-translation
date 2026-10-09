# Poliwag nickname prompt said Poliwhirl (fix/poliwhirl-text)

User approval 2026-10-09 (D-1496 case): "You get a Poliwag but the game asks 'Give Poliwhirl a nickname?'
(CN says Poliwhirl too). Fix = say Poliwag". Finding D-2281 (from hack_findings_import.jsonl), resolved
with D-1496.

## Cause

Hack text error. Pallet Town, player's house 1F, script file 842 (bank a027/0537). The Poliwag gift
branch (label L6280) prints #85 "Take Poliwag along…", #86 "Poliwag joined your party!", runs
`GiveMon [60, 5, …]` (species 60 = Poliwag) at 6361 and then `NPCMsg 87` at 6375, whose Chinese is
要给蚊香蛙起昵称吗？ (蚊香蛙 = Poliwhirl). #84 (cry label) and #88 (party full) say 蚊香蝌蚪 (Poliwag).
The other branch (L6155: #74, #76, `GiveMon [61, 10, …]`, #77) is the Poliwhirl gift and correctly says
Poliwhirl; it is left unchanged, as are #73–#79.

## Fix

a027/0537#87 en: "Give Poliwhirl a nickname?{VAR:0200:0}{SCROLL}" → "Give Poliwag a nickname?{VAR:0200:0}{SCROLL}".
Only the species name changes (D-1500). No ROM code or script change. qa.py check: 0 errors (the expected
glossary warning 蚊香蛙 → Poliwhirl on #87 remains, as for the other D-1496 fixes).

## Evidence

`emu_harness.py messages --refs "537#84 … 537#88"` (DeSmuME; message window, field script):
- Chinese ROM: 要给蚊香蛙起昵称吗？
- control (develop build of 2026-10-06): "Give Poliwhirl a nickname?"
- fixed build: "Give Poliwag a nickname?", one row, 2 pages as in the Chinese.
The full gift scene was not played (it needs the story state at the start of the game).
