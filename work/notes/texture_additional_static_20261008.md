# Additional texture-frame crash candidates: static audit (2026-10-08)

Read-only binary extraction from the supplied untouched Chinese v4.0.3 ROM. All entries below are candidates unless backed by a separate runtime report. No new crash is established by a matching descriptor alone.

## Runtime follow-up status

Two additional candidates have now produced the same invalid texture requests and null loads in the runtime investigation on the original ROM:

- **Seven Island163 at(245,104):** unmodified source save flags, 293 invalid requests/null loads; first index11 against texture count1. [Recorded trace](../build/additional-runtime/seven_original.json).
- **Bell Tower340 at(15,17):** synthetic setup explicitly clears hide flag1140 to expose the barriers; 1,174 invalid requests/null loads; first index15 against texture count1. [Recorded trace](../build/additional-runtime/bell_visible_original.json).

These establish the invalid-memory behavior in those runtime fixtures. Separate emulator crash/fix results belong in the runtime report; this static note does not turn untested matches into confirmed crashes. Remaining rows below, including the scripted Mt. Moon case, retain candidate status unless the runtime report says otherwise.

## Sprite349 occurrence scan

The event archive contains **73 sprite349 records across 25 zones**. Movement types: 54 type0, 5 type14, 1 type15, 2 type16, and 11 type17. Every record has initial facing field zero (the signed halfword at event offset12). Thus there are no additional nonzero initial-facing variants of sprite349 in this archive. Sprite349 is the barrier implicated in the Rocket HQ and Five Island runtime investigations.

| Priority | Zone / event member | Objects | Movement | Hide flag | Object coordinates | Suggested test position |
|---|---|---|---|---|---|---|
| High, same type17 | Radio Tower112 /109 | 36 |17|441|(3,45)|(3,46)|
| High, same type17 | Mahogany116 /113 |1–3|17|1366|(7,3),(8,4),(7,4)|(8,5)|
| High, same type17 | Whirl Islands244 /230 |6–10|17|579|(15,17),(17,17),(15,16),(16,16),(17,16)|(16,18)|
| Distinct type16 | Bell Tower340 /311 |23–24|16|1140|(14,16),(16,16)|(15,17)|
| Distinct type15 | Seven Island163 /157 |16|15|2198|(245,103)|(245,104)|
| Distinct type14/control | Route17 zone25 /22 |8–12|14|1673|(1141–1145,404)|(1143,405)|

Test positions are adjacent tile suggestions from static object coordinates, not verified walkable routes. Mahogany's three objects have vertical-position high word1; its interior elevation may require a normal entrance rather than a direct positional save edit. Flag clear makes each listed object eligible for appearance; flag set hides it. Other startup scripts may also alter visibility. Preserve the source save and disclose any synthetic setup flag changes.

The same-type17 group is the strongest initial scan because the exact sprite/movement pair matches both known locations. Types15/16 merit separate checks; type14 provides a useful directional control. This static audit intentionally does not assign descriptive movement names without verified runtime/source mapping.

## Complete records

| Zone | Event member | Object | Movement | Hide flag | Position |
|---|---:|---:|---:|---:|---|
| 13 Route 5 | 10 | 22 | 0 | 1226 | (1306,186) |
| 14 Route 6 | 11 | 10 | 0 | 1226 | (1309,266) |
| 14 Route 6 | 11 | 20 | 0 | 1226 | (1309,266) |
| 15 Route 7 | 12 | 22 | 0 | 1226 | (1261,248) |
| 16 Route 8 | 13 | 9 | 0 | 1226 | (1354,238) |
| 25 Route 17 | 22 | 8 | 14 | 1673 | (1141,404) |
| 25 Route 17 | 22 | 9 | 14 | 1673 | (1142,404) |
| 25 Route 17 | 22 | 10 | 14 | 1673 | (1143,404) |
| 25 Route 17 | 22 | 11 | 14 | 1673 | (1144,404) |
| 25 Route 17 | 22 | 12 | 14 | 1673 | (1145,404) |
| 36 Route 32 | 33 | 19 | 0 | 1904 | (476,305) |
| 36 Route 32 | 33 | 20 | 0 | 1904 | (477,305) |
| 52 Cerulean City | 49 | 7 | 0 | 783 | (1290,108) |
| 76 Goldenrod City | 73 | 37 | 0 | 441 | (368,356) |
| 76 Goldenrod City | 73 | 38 | 0 | 441 | (369,356) |
| 91 Route 19 | 88 | 4 | 0 | 1804 | (1203,458) |
| 91 Route 19 | 88 | 5 | 0 | 1804 | (1205,458) |
| 91 Route 19 | 88 | 6 | 0 | 1804 | (1204,458) |
| 91 Route 19 | 88 | 7 | 0 | 1804 | (1206,458) |
| 112 Radio Tower | 109 | 36 | 17 | 441 | (3,45) |
| 116 Mahogany Town | 113 | 1 | 17 | 1366 | (7,3) |
| 116 Mahogany Town | 113 | 2 | 17 | 1366 | (8,4) |
| 116 Mahogany Town | 113 | 3 | 17 | 1366 | (7,4) |
| 126 Tohjo Falls | 123 | 0 | 0 | 0 | (63,8) |
| 154 Five Island | 149 | 12 | 17 | 2173 | (103,52) |
| 163 Seven Island | 157 | 16 | 15 | 2198 | (245,103) |
| 200 Goldenrod City | 193 | 9 | 0 | 0 | (19,15) |
| 200 Goldenrod City | 193 | 10 | 0 | 0 | (20,15) |
| 200 Goldenrod City | 193 | 11 | 0 | 0 | (20,16) |
| 200 Goldenrod City | 193 | 12 | 0 | 0 | (3,13) |
| 200 Goldenrod City | 193 | 13 | 0 | 0 | (4,13) |
| 200 Goldenrod City | 193 | 14 | 0 | 0 | (4,14) |
| 200 Goldenrod City | 193 | 15 | 0 | 0 | (6,17) |
| 200 Goldenrod City | 193 | 16 | 0 | 0 | (7,17) |
| 200 Goldenrod City | 193 | 17 | 0 | 0 | (7,18) |
| 201 Goldenrod City | 194 | 29 | 0 | 0 | (1,14) |
| 201 Goldenrod City | 194 | 30 | 0 | 0 | (13,8) |
| 201 Goldenrod City | 194 | 31 | 0 | 0 | (1,8) |
| 201 Goldenrod City | 194 | 32 | 0 | 0 | (7,14) |
| 201 Goldenrod City | 194 | 33 | 0 | 0 | (13,14) |
| 201 Goldenrod City | 194 | 34 | 0 | 0 | (21,14) |
| 244 Whirl Islands | 230 | 6 | 17 | 579 | (15,17) |
| 244 Whirl Islands | 230 | 7 | 17 | 579 | (17,17) |
| 244 Whirl Islands | 230 | 8 | 17 | 579 | (15,16) |
| 244 Whirl Islands | 230 | 9 | 17 | 579 | (16,16) |
| 244 Whirl Islands | 230 | 10 | 17 | 579 | (17,16) |
| 247 Team Rocket HQ | 233 | 0 | 0 | 355 | (14,8) |
| 247 Team Rocket HQ | 233 | 1 | 0 | 355 | (15,8) |
| 247 Team Rocket HQ | 233 | 2 | 0 | 355 | (16,8) |
| 247 Team Rocket HQ | 233 | 3 | 0 | 355 | (49,14) |
| 247 Team Rocket HQ | 233 | 4 | 0 | 355 | (50,14) |
| 247 Team Rocket HQ | 233 | 13 | 17 | 355 | (51,4) |
| 300 Pokémon League | 271 | 12 | 0 | 2311 | (19,24) |
| 301 Pokémon League | 272 | 3 | 0 | 529 | (5,2) |
| 301 Pokémon League | 272 | 4 | 0 | 529 | (7,2) |
| 302 Pokémon League | 273 | 3 | 0 | 530 | (5,2) |
| 302 Pokémon League | 273 | 4 | 0 | 530 | (7,2) |
| 340 Bell Tower | 311 | 23 | 16 | 1140 | (14,16) |
| 340 Bell Tower | 311 | 24 | 16 | 1140 | (16,16) |
| 365 Vermilion City | 322 | 0 | 0 | 794 | (5,8) |
| 365 Vermilion City | 322 | 1 | 0 | 794 | (6,8) |
| 365 Vermilion City | 322 | 2 | 0 | 794 | (7,8) |
| 365 Vermilion City | 322 | 3 | 0 | 794 | (5,10) |
| 365 Vermilion City | 322 | 4 | 0 | 794 | (6,10) |
| 365 Vermilion City | 322 | 5 | 0 | 794 | (7,10) |
| 449 Mt. Moon | 404 | 0 | 0 | 0 | (19,4) |
| 506 Three Island | 458 | 10 | 0 | 1663 | (171,122) |
| 506 Three Island | 458 | 11 | 0 | 1663 | (171,121) |
| 506 Three Island | 458 | 12 | 0 | 1663 | (166,111) |
| 506 Three Island | 458 | 13 | 0 | 1663 | (167,111) |
| 506 Three Island | 458 | 14 | 0 | 1663 | (179,140) |
| 506 Three Island | 458 | 15 | 0 | 1663 | (179,139) |
| 506 Three Island | 458 | 16 | 0 | 1663 | (179,138) |

Raw event words and parsed metadata are retained locally in `work/build/five-static/events.json`. The binary parser reads 32-byte records after background events and object count; fields are object ID +0, sprite +2, movement +4, hide flag +8, script +10, signed initial facing +12, X +24, Z +26. Script-driven later movement/facing is outside this initial-record scan; movement0 objects are not claimed safe under every possible scripted action.

The code investigator separately audits other descriptors with small texture dictionaries and analogous bounds-to-null instructions. Further sprite IDs from that audit should be joined against the event archive before claiming this list exhaustive for the bug class.

## Other single-texture descriptors

The code investigator identified additional sprite descriptors with one texture and generic animation280. Joining those sprite IDs against decoded binary event records yields these nondefault movement candidates (all initial facing0):

| Zone | Event | Object | Sprite | Movement | Hide flag | Position |
|---|---:|---:|---:|---:|---:|---|
| Rock Tunnel342 |313|20|85|17|0|(14,10)|
| Rock Tunnel342 |313|5|85|15|16|(7,83)|
| Rock Tunnel342 |313|6|85|15|17|(44,90)|
| Route6 zone14 |11|3|87|16|1051|(1299,258)|
| Route32 zone36 |33|5|87|16|1314|(456,337)|
| Route10 zone388 |345|3|87|16|1887|(1428,202)|
| Cinnabar Island71 |68|13|87|15|1581|(29,94)|

These may have specialized handlers that bypass generic facing animation; descriptor/event matches alone do not prove a fault. Full matching event data is `work/build/five-static/additional_candidates.json`.

## Typed script operand scan

The existing disassembler was used on each zone's associated script bank. This scan matched object IDs only in the first operand of ApplyMovement, MovePersonFacing, SetObjectMovementType and SetObjectFacing. It did not grep arbitrary numeric operands. Names are taken from `bank_maps.json`.

- **Mt. Moon449, script9, object0:** MovePersonFacing at146 and936 places sprite349 at(28,42) with facing1. Its initial record is(19,4), movement0, flag0. Entry3 starts at125 and is an initialization candidate. Its actual talk entry2 begins103 and has **FacePlayer at112**, another potential rotation trigger. Test after startup near(28,43), interact from differing sides, and record the actual post-init location. This is a newly identified scripted candidate, not a confirmed crash.
- **Goldenrod200, script95:** numerous MovePersonFacing calls on objects9–17 all specify final facing0. Three ApplyMovement calls on objects12–14 use action10, repeat2.
- **Goldenrod201, script96:** barrier objects29–34 have ApplyMovement action14 or15, repeat2, for the puzzle. Scripted action numbers are different from event movement types14–17.
- **Whirl244, script104:** objects6–10 receive ApplyMovement action3, repeat1, at3648..3680.
- **HQ247, script89:** existing barriers have scripted actions including0,12–15,75; the original crash's general reproduction is already recorded elsewhere.
- No decoded SetObjectMovementType or SetObjectFacing commands directly targeting sprite349 object IDs were found in the associated zone banks.

A direct talk-entry scan found FacePlayer only for the Mt. Moon barrier among sprite349 records with nonzero talk script. This is a bounded scan of decoded commands and direct talk-entry regions, not a proof about every indirect subroutine, variable object operand, dynamically changed sprite, or standard script. Exact matched operands and movement action lists are in `work/build/five-static/scripted_barriers.json`.
