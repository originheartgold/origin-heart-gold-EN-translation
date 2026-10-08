# Additional texture bug search and reproduction — 2026-10-08

User requested a binary search for further occurrences and reproduction of any findings. Work remains isolated on `codex/rocket-hq-freeze`; the existing experimental guard is unchanged.

## Search scope

The three agents scanned ARM9 plus all decompressed ARM9 overlays for the bounds-to-NULL-to-load instruction pattern, all1801 sprite descriptors, all73 sprite349 event records across25 zones,442 event records for related one-texture descriptors, and typed script operands for barrier changes.

See [binary audit](texture_additional_code_20261008.md), [event/script audit](texture_additional_static_20261008.md), and [runtime tests](texture_additional_runtime_20261008.md).

## Additional reproduced invalid accesses

| Location | Setup | Texture index / count | Invalid requests / null loads |
|---|---|---|---|
| Seven Island, zone163 at(245,104) | Scripted warp from copied Luke HQ save; story flags unchanged |11 /1|293 /293|
| Bell Tower, zone340 at(15,17) | Disposable diagnostic copy with barrier hideflag1140 cleared |15 /1|1174 /1174|

Seven Island object16 is sprite349/movement15 at(245,103), hideflag2198. Bell Tower objects23–24 are sprite349/movement16 at(14,16)/(16,16), hideflag1140. These confirm additional failing directions beyond the previous right-facing frame4 case. DeSmuME tolerates the invalid load, so these numbers alone establish the invalid access, not a visible emulator hang. The original Chinese ROM was used. Natural story progression to these setups was not played through.

## Other binary findings and limits

The signature scan found five sites, including the known texture updater. The palette updater has an analogous unchecked path at02024780→02024798, and overlay87 has another texture lookup at021EDB0A→021EDB26. Neither has a natural gameplay reproduction yet. Two other matches are inside loops already bounded by the same dictionary count and are not established bugs.

Radio Tower, Mahogany, Whirl Islands, Rock Tunnel, selected routes and a scripted Mt. Moon barrier remain separate candidates unless runtime results below establish otherwise. Static matches must not be presented as confirmed freezes. The current texture guard does not address invalid palette indices or overlay87.

No input saves/ROMs, production build scripts, or patch implementation were changed. Game data and snapshots remain ignored local evidence. No downloads, commits, or publishing.

## Completed Seven Island fixture

`work/build/additional-runtime/luke_seven_complete.sav` is524288 bytes, SHA256 `0f3dfe918d3ef5c7bbf8d3d199558e1af55cbe9a497a313701e09d3fdb95adb3`. It was made using a normal scripted warp and in-game save, waiting5000 frames after confirmation. Both active blocks have counter4, with general/storage CRC24701/53238; both older blocks remain valid atcounter3. Root independently verified all four CRCs and matching block-pair counters before preparing identical original/fixed copies.

## Seven Island melonDS reproduction

Fresh original English rc5 boot with the completed fixture produced a black-screen freeze. Captured `work/build/additional-melonds/original.ml1` has map163(245,104), PC`FFFF0108`, abort LR`0202469E`, CPSR`60000097`, requested texture index11/count1, original branch`08d2`. State SHA256 `5f2c4eb8f20d420f3ab880ec2b1cfe6a04a8e378db72d4a47234f2c107d874b4`. This is an actual emulator abort, independently confirming the DeSmuME invalid-load trace.

Fresh guard-patched rc5 boot with the identical battery save rendered the Seven Island barrier and allowed movement from(245,104) to(245,106). `fixed.ml1` contains PC`02071880`, LR`0206D87B`, CPSR`0000003F` (Thumb/system), branch`2cd2`; it is not in the abort handler. State SHA256 `5c11009c1178f48467437ecb19dc254c6971a1a517bbe0cb7b056f0595d7d8a7`. The ROM pair is byte-identical to the rc5 original/fixed pair documented in [Five Island verification](five_island_freeze_20261008.md). No new code change was necessary.

Bell Tower's guard run also completed:1168 invalid updates skipped,0 null loads,4110 valid updates. Original was1174 invalid/null and4119 valid; minor timing differences mean these counts are not frame-identical. There is no Bell Tower melonDS claim. Queued Rock Tunnel and remaining comparisons were canceled without running; all own harness jobs exited.

Temporary A/Start/Down bindings were restored; the saved melonDS keyboard configuration was verified to contain only the original unassigned values. Original input save hashes were rechecked unchanged.
