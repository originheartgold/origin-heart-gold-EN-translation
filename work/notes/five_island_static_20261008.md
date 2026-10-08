# Five Island freeze: static investigation (2026-10-08)

This is a targeted comparison with the reproduced Rocket HQ texture-frame abort, not by itself proof of the reported Five Island crash.

## Concrete candidate

Five Island is zone **154**, matrix **308**, event member **149** in `a/0/3/2`, script member **58** in `a/0/1/2`, message bank **87**. Coordinates below are world tile X/Z, not the town-map position (46,16).

| Map | Object | Sprite | Movement | Hide flag | Position |
|---|---:|---:|---:|---:|---|
| Five Island | 12 | 349 | 17 | 2173 | (103,52) |
| Rocket HQ B1F | 13 | 349 | 17 | 355 | (51,4) |

Both use exactly the same sprite and movement fields. Other HQ barriers (objects 0–4) use sprite349 with movement0. The HQ investigation identified a one-frame barrier texture receiving nonzero texture requests. This makes Five Island object12 a strong candidate for the same invalid animation selection; a static match alone cannot establish which HQ object issued the recorded request or what movement17 means at runtime.

Five Island object11 at (102,53) is sprite395 (Snorlax), shares hide flag2173, and has movement0. NPC10, sprite220, stands at (104,53). Script58 entry18 begins at651 and checks flag2173 at659. The snack quest sets flag2173 at4760 after the Snorlax interaction, hiding both Snorlax and barrier. Thus the candidate exists before that quest is completed. Do not infer a save's state from badge count alone.

Suggested runtime setup: warp a disposable save to zone154 at (104,54), immediately below the monk, then approach the barrier at (103,52), log calls at02024654 and02024696. Repeat with flag2173 set (candidate hidden) and clear (candidate shown); record synthetic flag changes explicitly. The earlier suggested (103,60) is blocked trees/water, so it is not a useful walking start. The runtime investigation has observed the same null loads on the untouched Chinese ROM. Approach screenshots are needed to determine whether this matches the reporter's bridge/river crossing. Nearby coordinate events are (122,62), (94,48), (82,57), (94,85), and (71,17).

## Wider scan

The same sprite349/movement17 pair also occurs at Radio Tower zone112 object36 (3,45), Mahogany interior zone116 objects1–3 (7,3),(8,4),(7,4), and Whirl Islands zone244 objects6–10 around (15–17,16–17). These are untested candidates, not confirmed crashes. Movement14,15,16 occur on other barriers too. The presence of these combinations does not yet establish failure: visibility, resource selection, distance, facing, and story state can matter.

Read-only extraction from the supplied untouched Chinese ROM produced `work/build/five-static/events.json`, with all Five Island events and all sprite349 occurrences, including raw event words. No ROM or save edits, downloads, production script changes, or shared decision edits were made by this static investigation.
