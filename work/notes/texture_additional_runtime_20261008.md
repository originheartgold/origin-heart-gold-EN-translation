# Additional texture-bound failures: runtime tests (2026-10-08)

User requested broader binary investigation and reproduction. Tests use untouched Chinese v4.0.3, existing guard-patched Chinese ROM, read-only texture hooks at0202467C/02024696, and disposable copies/imports of player B's supplied HQ battery save. No original save or ROM is modified. A normal harness scripted warp initializes each map; direct location-only Continue fixtures are not used.

## Positive cases

- **Seven Island map163(245,104):** hide flag2198 is naturally clear in player B's input; no story flags changed. Original code records293 invalid texture requests(index11,count1),293 null loads and3823 valid updates. This is the barrier at(245,103), with movement15 in the event data. UP inputs are blocked by the object north; the test proves rendering failure, not traversal of the broader map.
- **Bell Tower map340(15,17):** diagnostic copy clears hide flag1140 only; the original input has this flag set. Original code records1174 invalid requests(index15,count1),1174 null loads and4119 valid updates. This exercises two barriers at(14,16)/(16,16), movement16. It establishes a reachable renderer failure under constructed visibility, not the original save's natural quest route.

Initial planned RadioTower112, Mahogany116 and Whirl244 probes were canceled while waiting for emulator slots to prioritize naturally visible candidates. Player B's input hides their candidate objects(flags441,1366,579 all set); no runtime conclusion is drawn for those maps. Bell's probe completed before cancellation. Separate visibility diagnostic save copies exist but were not executed for the canceled candidates.

## Evidence

Ignored `work/build/additional-runtime/` holds probe.py, per-case JSON counts/registers/locations and before/after screenshots. The existing one-byte guard is compared on identical inputs/routes; the normal release build is not changed. Seven Island genuine in-game saved fixture is produced by save_fixture.py with5000-frame wait after save confirmation, followed by paired general/storage CRC/counter checks.

Cross-emulator melonDS observations belong to the coordinating agent's report. Emulated game input and fixtures remain local, with no downloads or publication.

## Completed Seven Island battery fixture

`work/build/additional-runtime/playerb_seven_complete.sav` is produced through normal in-game Save, with5000 frames after confirmation and successful export. SHA256 `0f3dfe918d3ef5c7bbf8d3d199558e1af55cbe9a497a313701e09d3fdb95adb3`. Active general/storage blocks both have counter4 and valid CRC24701/53238. The previous general/storage pair remains valid counter3. Location163(245,104), original input's story flags preserved except normal game activity associated with map entry/save. Root uses this fixture for melonDS validation.

## Runtime limits and cleanup

Rock Tunnel original and matched Seven DeSmuME guard probes remained queued behind unrelated active emulator work and were canceled on the coordinator's instruction after two positive cases and the real Seven Island melonDS crash were established. No runtime claim is made for Rock Tunnel. Bell Tower acquired a slot just before cancellation and completed successfully:1168 invalid requests skipped,0 NULL loads; original1174 NULL loads. Small request-count difference reflects runtime timing, so identical frame counts are not claimed. Seven Island guard validation is handled in melonDS by the coordinator. All reproduction jobs started by this subagent were closed or canceled; unrelated processes were left running.

The coordinator independently reproduced the Seven Island failure in melonDS at map163(245,104), saved PCFFFF0108, abort LR0202469E, CPSR60000097, index11/count1. See the coordinator's additional-reproduction report for snapshots and patched comparison.
