# Pokédex special-wild gates audit — 2026-10-09

Read-only native/script investigation of the untouched Chinese v4.0.3 ROM. No ROM patch or emulator save edit was made. These findings are static control-flow evidence, not new runtime tests. Native dumps: `work/build/source-verify-common/arm9.txt`, `work/build/source-verify-data/ov2.txt`; fresh CN overlays were loaded with ndspy and disassembled with Capstone in `work/build/pokedex_acquisition_other/`. The raw source ROM supplies overlay25 (contest) and overlay92 (Pokégear).

## Swarms are disabled (D-2293)

ARM9 `0x0202DC08` is exactly `movs r0,#0; bx lr` (bytes `00 20 70 47`). The ordinary grass substitution routine in ov2 calls it at `0x02246EFE`, compares zero, and exits at `0x02246F04` before checking the swarm map or changing either species. The Surf substitution routine has the same guard at `0x02246F40–0x02246F46`, before the record's offset0xBE species can be used.

The Pokégear bulletin also tests this function at ov92 `0x021F5EDE–0x021F5EE4` and skips the map/species lookup. All overlay call sites were scanned: only these three callers use the getter. There is no calendar or story value a normal player can set to make its literal-zero result true.

**Publication:** remove land and Surf swarm sections from `encounter_sections` and their species from `enc_species`; do not advertise them as a schedule that remains to be documented. Suggested player note: “The hack disables swarms; unused swarm-table entries are not listed.”

## Normal fishing does not read the alternative fields (D-2295)

Normal fishing ov2 `0x022472D4` selects one of record offsets `0x80`, `0x94`, `0xA8` for Old/Good/Super Rod. At `0x0224739E–0x022473BE` it copies exactly five ordinary slots. The call at `0x022473D6` passes those to `0x02247860`; the non-Safari path calls `0x02247F24`. Its fishing branch at `0x022480F8–0x02248146` uses ability/random selection (`0x022485D4`, `0x02247AD0`) and ordinary level selection (`0x02247BF8`). There is no time check or use of offset0xC0 (night replacement) or0xC2 (fishing-swarm replacement). The map-record loader's calendar redirect does not substitute these fields either.

The wild/trade agent and this agent independently reviewed this path. **Publication:** remove “Fishing at night” and “Swarm (fishing)” rows and remove their otherwise-unused species from availability. Keep ordinary rod slots and the separately verified calendar-dependent encounter-table redirects. Suggested player note: “Fishing uses the listed ordinary rod slots; the unused night-fishing and swarm replacements are not listed.”

## The National Dex getter is disabled: contest and radio (D-2294)

ARM9 `0x0202AA74` is exactly `movs r0,#0; bx lr`. The normal setter still exists at `0x0202AA54`, but the getter never reads the saved bit. Consequently, changing story progress or the stored dex flag cannot enable a caller that uses this getter.

### Bug-Catching Contest

Fresh ov25 constructor `0x0225BFEC–0x0225C006` gets the dex save block and calls the literal-zero getter at `0x0225BFF2`. It stores this result in bit1 of contest-state byte0x17. The constructor then immediately calls the encounter loader `0x0225C4EC` at `0x0225C018`. The loader checks bit1 at `0x0225C526–0x0225C52C`: zero sets table index0 at `0x0225C534`; nonzero would use weekday>>1 at `0x0225C52E–0x0225C530`. It copies 80 bytes (ten slots) from that selected set. There is no intervening setter that could alter the constructor's bit.

Thus **only set1 (zero-based0)** is used on Tuesday, Thursday and Saturday. The three later sets are unused normal-play sources. Registration is once per day, with one Pokémon and 20 Sport Balls; existing guide evidence: `guide/10-ecruteak-olivine.md:177`, files242/245/151, entered-today flag2727.

**Publication:** expose only the first ten-slot set in Pokédex, location data and generated documentation. Suggested replacement for `CONTEST_NOTE`: “The contest runs on Tuesdays, Thursdays and Saturdays, once per day. This hack always uses set1; its National Dex check is disabled, so the later encounter sets never activate.”

### Hoenn Sound / Sinnoh Sound

Fresh ov92 music constructor `0x021F4EEC–0x021F4F06` calls the same getter at `0x021F4EF2` and stores bit0 of music-state byte4. The Wednesday branch `0x021F4F66–0x021F4F7C` chooses special mode2 only if this bit is true; otherwise mode0. The Thursday branch `0x021F4F84–0x021F4F98` similarly chooses mode3 only if true; otherwise mode1. The music-ID table at `0x021F7A28` begins `[1100,1099,1169,1170]`; `0x021F4E88` selects the indexed music.

Ov2 encounter matcher `0x02254590` recognizes music1169 (`0x491`) as encounter mode3 and music1170 (`0x492`) as mode4. Its replacements are real code, but the radio scheduler cannot select those two music modes with the getter permanently false. The ordinary radio card is received with Lt. Surge's badge (`guide/02-pewter-to-vermilion.md:383`), but owning it does not repair this disabled condition.

**Publication:** remove both Hoenn Sound and Sinnoh Sound source rows and corresponding availability. Suggested note: “Hoenn Sound and Sinnoh Sound cannot activate in this hack, so their unused encounter slots are omitted.”

## Safari Zone base areas work; Object Arrangement is blocked (D-2296)

Baoba's ordinary tests remain: catch Geodude, wait for his next test/Area Customizer, then catch Sandshrew. The gate script119 reports the successful Sandshrew test and sets progress variable0x4057 to6 at offsets5078/5552. Base-area catches remain valid; the basic Safari entry and Area Customizer are not National-Dex-gated by this finding.

Object Arrangement is introduced only at progress7: script119 offsets1780/1786 branch to3771; messages43/44 introduce Object Arrangement and changing wild Pokémon with objects. A scan of all script `SetVar`/`SetOrCopyVar` writes finds only values1,2,3,5,6 for variable0x4057, never7.

The native phone scheduler `0x020924F0` reads this same progress via getter `0x02066110` (its literal var id at `0x0206611C` is0x4057). Progress3 can queue the second-test call without a National Dex. Progress>=6 reaches `0x02092560–0x02092570`, which calls `0x0202AA74` and exits to `0x020925CA` on zero **before** queuing the object unlock/update calls8–11. These calls therefore never start in normal play.

A scan of all overlays finds only two calls to progress setter `0x02066120`, both in ov92's Baoba phone handler: `0x021F3108` sets4 for the second test; `0x021F313A` sets7 for the object calls. This is the only identified normal path to7, and the scheduler blocks it.

**Publication:** keep basic Safari area encounter tables and remove object-dependent bonus rows as normal acquisition sources. Suggested player note: “Baoba unlocks the Area Customizer for his Sandshrew test after you complete the Geodude test. Object Arrangement never unlocks in the original hack because its National Dex check is disabled; object-dependent bonus encounters are omitted.” Do not add a gameplay fix; these findings concern accurate documentation.

## Remaining boundaries

These are native/script findings, with no new emulator test claim. Existing guide runtime observations remain as cited there. The Unown unused-map490/491 reachability audit is being handled separately by the wild/trade agent. Safari maturity scores can still be parsed for research but do not prove block encounters obtainable when the placement feature cannot unlock.
