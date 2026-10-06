# Calendar encounter hook verified in Chinese v4.0.3

2026-10-04. Findings-only supplement for COM-04 / REF-07. No guide, docs, production tools, translations or game data changed. Examined local `work/rom/origin_v4.0.3_cn.nds`, SHA256 `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`. Scratch extraction: `work/build/source-verify-quests/calendar-table.json` and `calendar-hook.txt`.

## Finding

**The author's special-calendar-date encounter claim is implemented in this ROM.** It is a native encounter-table override, not the weekly Lake of Rage event and not a collection of ordinary static-encounter event scripts. The existing extracted encounter tables omit it.

The encounter loader at **ARM9 0x0203AD24** clears a 0xC4-byte encounter buffer, obtains the map's encounter bank and reads its data. At **0x0203AD52** it calls the date/time reader `0x020142F4`. It then iterates **eight 8-byte records** from **0x020F6A64**, comparing current month, day and map ID at `0x0203AD5A–6E`.

Record structure is `{u8 month, u8 day, u16 map, u16 species, u8 form, u8 period_selector}`. Matching records pack `species | (form << 11)` and overwrite encounter-buffer species entries at offsets **0x2A / 0x42 / 0x5A**. Those are the final, zero-based slot11 of the morning/day/night land tables, respectively. The normal land slot weight there is1%. The hook leaves encounter rate and level bytes untouched. Period selector0 writes all three; selector1 writes morning only; any other value writes night only. No matching record changes a Surf or fishing slot.

The normal field map-data loading path calls this loader at **0x0203AB04**. Other native callers also exist. This is positive reachable native-code evidence, not merely an unused date table. Actual captures and exact interactions with later encounter modifiers have not been replayed.

## Decoded configuration

Dates recur by month/day: the hook does not compare year.

| Date | Exact map | Configured species / raw form | Period patched | Existing slot level / walk rate | Interpretation |
|---|---|---|---|---|---|
| June23 |181, Fuchsia City's Koga forest preserve (encounter19) |647 Keldeo /0 |Morning, day, night |Lv5 /15 |Positive configured calendar replacement. Use map181, not all Fuchsia maps. |
| July14 |117, Ilex Forest (encounter20) |648 Meloetta /0 |Morning, day, night |Lv6 /5 |Positive configured replacement. |
| August11 |113, Ruins of Alph exterior (encounter9) |649 Genesect /0 |Morning, day, night |Lv5 /10 |Exterior map, not every ruin room. |
| October16 |96, National Park (encounter23) |670 Floette /5 |Morning, day, night |Lv14 /25 |Form table maps670/form5 to personal1222 (Eternal Flower form). This is the normal park map; do not claim it overrides the separate contest encounter system. |
| July19 |492, Island Forest (encounter12) |719 Diancie /**4** |Morning, day, night |Lv17 /15 |Raw form4 is what the table writes. The global form table has719/form1 only; runtime resolution of form4 needs checking. Do not silently call this Mega Diancie or correct the field. |
| July18 |90, Mt. Silver exterior (encounter85) |720 Hoopa /0 |**Morning only** |Lv50 /25 |The day slot is not overwritten by either Hoopa record. |
| July18 |90, Mt. Silver exterior (encounter85) |720 Hoopa /1 |**Night only** |Lv50 /25 |Global form table maps720/form1 to personal1243 (Unbound). |
| April16 |88, Lake of Rage (encounter58) |721 Volcanion /0 |Morning, day, night |**Lv0 /0** |The hook configures a land-table replacement, but the baseline land rate and level are zero. This is **not proof of an attainable normal wild encounter**. Fresh visible land spawning also checks the same zero walk rate and exits (ARM9 0x02019A5C–62 → 0x02019AA2 → 0x02019C2A). Thus this calendar entry alone supplies neither an ordinary land encounter nor a fresh visible land spawn; another modifier would be needed. |

Morning/day/night names follow the existing encounter-layout parser; the independent time-boundary verification belongs to V04. The hook itself compares period table fields, not the player's current hour. On matching dates it prepares whichever tables the downstream encounter routine may use.

## Practical consequence for the findings register

Promote COM-04/REF-07's calendar mechanism from author-only lead to **confirmed missing runtime-table coverage**. Preserve the exact map IDs, dates and raw form fields as technical findings pending a capture test. Avoid describing all eight entries as proven obtainable Pokémon. In particular, keep Diancie's form4 as an open runtime question and report Volcanion's configured-but-zero-rate land source without silently repairing either. The visible-spawn audit confirms that a fresh land spawn also rejects walk rate0; a retained shiny path is separate and does not make this an ordinary acquisition route.

This also means ordinary 'no encounter source found' outputs can miss a real native calendar source. A future documentation generator can represent the eight configured rows separately from confirmed availability, with their native source address and qualification. No generator or guide changes were made in this pass.

## Search method and limits

First inspected the decoded event-command catalogue for month/date commands and identified only GetWeekday among explicit calendar readers. Then followed references to native RTC date readers across fresh ARM9/overlay disassemblies. The combined date/time reader's caller at0x0203AD52 exposed this table; direct reads and map metadata confirmed its structure and destinations. The weekly trio routine at0x0203A580 is separate and was not used as evidence for these month/day encounters.

This was static verification of the native loader and source table. It does not establish encounter-rate behavior after radio/swarm/ability/Safari modifiers, whether date changes without reloading the map refresh the buffer, successful capture of unusual forms, or persistence of visible spawns across midnight. The English patched ROM was not independently replayed in this supplement.

## Emulator replay (2026-10-06)

Replayed in the emulator on this ROM and on the English WIP build (`emu_harness.py calendar`, details in
`emu_harness.md` section 9). The loader's buffer matched this table for all eight rows (day before: the ROM
record; date: the configured slot-11 words only). With slot 11 forced for the test, every entry except
Volcanion appeared at the listed level and was caught with a Master Ball: Diancie form 4 is a normal Diancie
(base personal 719, normal sprite; the stored form stays 4, D-1489), Floette form 5 uses personal 1222 and
Hoopa form 1 personal 1243. Hoopa's windows were checked at 03:59, 04:00, 09:59, 10:00, 19:59 and 20:00
(morning 4–9, day 10–19, night 20–3). Lake of Rage has no grass, and 400 forced-slot steps per period on
April 16 gave no encounter (D-1488). The date is read only when the map's encounter data loads: a date
change while staying on the map, or a battle, does not refresh it (D-1564). Not tested: interactions with
other encounter modifiers (abilities, swarms, radio, Safari).
