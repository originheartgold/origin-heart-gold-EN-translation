# Pallet Town solo-photo report: fresh-game harness reproduction

Test date: 2026-10-08 (Europe/Brussels). Reporter uses **Manic Emulator on iOS**; app version and patched-ROM version have not been supplied. These tests use the existing local **DeSmuME 0.9.12, py-desmume harness**, not Manic.

## English WIP: crash not reproduced

ROM: `work/build/origin_hg_v4.0.3_en_wip.nds`, CRC32 `F7430513`, SHA-256 `6fa7b4e739391ca9ea9bfcf90d83eec6407c3c04102e52432bb41bc8ae44a7d3`.

Started without an imported battery save or savestate. Chose the male player and outfit 1, entered the bedroom, went downstairs, completed the mandatory Mom conversation, exited the house and spoke to Cameron. No starter was collected, and no party, story flag, script or ROM edits were made. Navigation included turns around the house and flowerbed; no other NPC conversation or story event intervened.

The harness read an empty party in the bedroom, after Mom, at the photographer and after the photo. Accepted YES, advanced “All right, then! Get yourselves ready!”, observed the photo sequence, then “Good, good! We've got a nice picture!” and “You can see all the pictures on your PC.” Dismissed the final message and successfully walked right: position changed from `(49, 1031, 367)` to `(49, 1033, 367)`. Thus this run covers the complete interaction and return of player control, unlike the existing memcheck prompt-only scenario. Viewing the stored picture in the PC was not tested.

## Untouched Chinese: crash not reproduced

ROM: `work/rom/origin_v4.0.3_cn.nds`, CRC32 `59CBBDAA`, SHA-256 `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`.

Repeated with a separate fresh game, male player/outfit 1, the mandatory Mom conversation and no starter or state edits. Cameron completed the photo and both completion messages. Party was empty before the interaction and afterward. Walking right after dismissing the final message changed `(49, 1031, 367)` to `(49, 1033, 367)`, confirming returned control. Chinese screenshots and bedroom/Mom/pre-photo checkpoints are under `cn/` in the same evidence directory. The two runs approached Cameron from different sides; both used his normal interaction.

## Evidence and limits

Local, gitignored evidence: `work/build/photo-empty-repro/`. `roms.json` records input hashes. `en/bedroom.dst`, `en/momdone.dst` and `en/before-photo.dst` preserve checkpoints. Screenshots include `floor1.png` (Mom), `momdone.png`, `cameron.png`, `offer.png`, `accepted.png`, `capture.png`, `after-photo.png` and `completed.png`. `drive.py` is the scratch interactive harness driver; it does not alter the harness implementation.

This is a passing run in DeSmuME, not a fix and not a disproof of the Manic report. No new ROM was built. Manic/iOS behavior remains untested, as do other builds, female-player behavior and album viewing. The October 5 script audit still establishes that the inspected English WIP lacked Speedoption's empty-party guard; successful execution here does not establish that a guard or other specific fix was added.
