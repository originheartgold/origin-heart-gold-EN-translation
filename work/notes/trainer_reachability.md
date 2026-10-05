# Trainer encounter linkage review — 2026-10-05

The reproducible supplement is `work/research/trainer_verification/reachability.py`; run it from the repository root. Its raw output stays in ignored `work/build/trainer_verification/reachability/supplement.json`. The public API is `build(ctx)`, using the caller's freshly extracted Chinese-ROM context. Six regression tests are in `reachability_test.py`.

## Coverage and meaning

All **941 battle callsites** are included. **914** have a static path from a map object, background event, coordinate trigger, or map-header trigger, including standard-script dispatch. A further **3** have an original-ROM engine entry, for **917 linked callsites**. **24** have no root in this model: seven previously reviewed dormant calls, two calls in the known inaccessible Dark Cave zone, and fifteen additional local-entry candidates listed below.

“Linked” means that there is an executable entry route in a conservative control-flow graph. It does **not** prove the player can reach the map, satisfy all conditions together, activate an object's visibility flags, win earlier battles, or select every alternate route. Conditional branches and call continuation are overapproximated. The 24 remaining calls must not be described as 24 newly proven unused encounters.

The audit decodes **584 map-header trigger rows** across the zones. There are **466 header-format members** in the contiguous header block, including 450 used by map headers and 16 unassigned members. Treating these as executable pointer tables caused **1,372 of the original 1,379 decoder-frontier reports**. After separating formats, only seven real script frontiers remain.

## Generic trainer callers

**376 map objects**, representing **316 distinct trainer IDs**, bind standard trainer scripts to their caller IDs. In the original Chinese ARM9, `GetTrainerNum`'s handler is `0x02048B34`; it reads the current script ID and calls `0x0203FC04`. That conversion subtracts **2999** below script ID5000 and **4999** otherwise, exactly matching the map-object export. The latter routine's literal constants at `0x0203FC20` and `0x0203FC24` are 5000 and2999.

Script949's trainer-sight entry is **entry740**, starting at3780. The original Chinese engine loads standard script ID**3739** from ARM9 `0x020633A0` at `0x020632AA` and `0x02063350`, then calls the script-start routine `0x0203F57C` at `0x020632B0` and `0x02063356`. The ROM's standard-script table maps3000 to file949;3739 therefore selects entry740. Byte checks for both callsites and the literal are part of the supplement.

That entry reaches battle calls949:3908,949:4101 and949:4348. The script obtains trainer slot0/1 using `GetEyeTrainerNum`, copies those values into battle arguments, and supplies either one opponent or both. The command's CN handler at `0x02048AE0` reads the corresponding caller-context halfwords. This resolves why these three callsites had no map-event root; it does not enumerate all simultaneous two-object sight pairings or their world-state feasibility.

The ordinary conversation battle949:3123 also has a phone-rematch branch: `GetPhoneBookRematch` at3241 is copied through0x8007 to0x8004 at3398. The initial object ID alone is therefore **not** proof of every team selected by that call. The runtime phone-rematch table and its caller candidates are traced in the follow-up below; per-save selection feasibility remains separate from entry linkage.

## Remaining local entry candidates

| Script | Entry | Battle offsets | Map / classification |
|---|---:|---|---|
|18|3|730|Sprout Tower3F: no matching current event/header root|
|32|8|2012,2059|Radio Tower4F: no matching current event/header root|
|111|5|1212,1462,1759,1972|Dragon's Den: no matching current event/header root|
|156|42,43|5260,5379|S.S. Anne: no matching current event/header root|
|162|10,20,11,12,13|785,1268,2337,2490,2643|S.S. Anne B1F: no matching current event/header root|
|168|5|273|Route1: no matching current event/header root|
|741|1|151|Previously reviewed dormant Blue badge scene|
|816|7|333,735,1634|Previously reviewed dormant League entrance rival scene|
|847|4|351,2071,6590|Previously reviewed dormant Cherrygrove rival scene|
|964|2|2332,2392|Known inaccessible zone176; stale Route41 script copy|

For the first six rows, all current object/background/coordinate entries, map-header roots, and reachable `RunScript`/`CallStd` calls were checked. No new production dead-scene classification is applied: unknown script commands, engine dispatch and world state could require further analysis. The supplement also records five non-sentinel event roots in zone214 pointing outside file250's entry table; those are not silently ignored or converted into encounters.

## Seven real decoder stops

The remaining stops are225:3985,232:12121,243:2334,246:764,934:5653,937:2784 and958:1078. Each freshly read CN script has `GiveRibbon` with one of59–65, then `PlayFanfare20`, then opcode**2009**. The original CN command count at ARM9 `0x020F78CC` is**843**. These match the previously documented weekday-sibling bug **D-1331**, preserved under **D-1337**. No unexplained trainer-script decode frontier remains in this structural model.

## Menu fallback finding

**D-1499** records a newly isolated suspect original-hack path. File78's first Doubles opponent menu returns at913. Choice7 exits at813. Any value outside0–7 instead falls through1025 to battle1040 with the menu result still in0x800C, used for both opponents. Singles' equivalent fallback exits safely. Tests cover ordinary selections, explicit exit, and hypothetical unrecognized results8,65534 and65535.

The older audit associates B with0xFFFE, but its cited vanilla-style address is not sufficient proof for this particular Chinese-ROM touchscreen path. **The exact cancellation result and in-game effect remain unverified**, so this report does not assert a reproduced B-button crash. No game behavior was changed. The old audit checked final lock/release state; that check did not validate intervening battle arguments.

## Unreferenced records

The recomputed list remains exactly**15** trainer records:86,89,260,440,488,492,609,706,707,708,709,710,711,760,947. These have no known decoded fixed battle/map-object association under the current location exporter. Separating map headers and finding engine sight dispatch does not establish new fixed references to them. This is a reference-coverage result, not proof that all15 are globally unused.

## Validation

`python3 -m unittest work/research/trainer_verification/reachability_test.py` passes. Engine evidence was freshly read from the untouched CN ROM and inspected with the installed Xcode LLVM disassembler; only ignored extracted code slices/object wrappers were generated, not a ROM. No downloads, game modifications, or publication occurred.

## Phone-rematch runtime follow-up

`reachability_phone.py` exports a `build(ctx)` supplement, also included under `phone_rematches` by the main reachability `build(ctx)`. **Two of the15 encounter-unreferenced records do have engine-table references:440 and609.** Neither currently has an identified caller capable of selecting that row, so no guide encounter is added and the15 missing encounter associations are not reduced. Only13 records lack both a fixed encounter association and a phone-table reference.

The fresh CN opcode142 handler is ARM9 `0x02041F68`. It loads overlay27 and calls `0x020928EC`. That resolver first checks the contact's rematch state, has an additional contact16/context restriction, reads the contact's base trainer ID from offset4 of its20-byte record, and calls overlay27 `0x0225BFC0`. The contact loader at `0x02095520` reads `tel/pmtel_book.dat` (75 records).

Overlay27 searches **63 rows**, each **six trainer-ID halfwords**, at `0x0225C1CC`. The first value identifies the base trainer. `0x0225C010` scans later stages, skips0xFFFF placeholders, stops at a0 terminator or the first undefeated trainer, and caps the stage at5. `0x0225C05C` checks the corresponding progression flag through `0x0206596C` (flag base0x097B plus stage); if that gate fails, it steps back to an earlier non-placeholder stage. `0x0225C0BC` returns the selected table halfword. This is a bounded table selection, rather than an arbitrary trainer variable.

- Record440 occurs for **contact40, base trainer211, stage2**.
- Record609 occurs for **contact42, base trainer113, stage4**.
- Neither base211 nor113 has a current generic trainer map object. No decoded `RunScript`/`CallStd` directly invokes a3000–6999 trainer standard script.
- Besides generic949:3241, the only decoded `GetPhoneBookRematch` calls use fixed contacts**17,36,38**:829:265,776:684,909:308 and915:1778. None selects contact40 or42.

All contact rows, stage candidates and caller-presence evidence are exported to ignored `phone_supplement.json`. The regression asserts the two engine-table references and the absence of current caller candidates. Registration, rematch availability and progress flags are still save-state conditions, and no emulator witness is claimed.
