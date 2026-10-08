# Rocket HQ texture-frame fix experiment (D-2043)

Branch: `codex/rocket-hq-freeze`. The user explicitly requested an attempted fix in a worktree after reproduction on 2026-10-08. This authorizes this isolated experiment despite the standing D-1337 policy; it does not change that policy for other hack bugs or publish a release.

## Result

A one-byte ARM9 change lets released English rc5 pass the reproducible Rocket HQ freeze in melonDS 1.1, reach the camera double battle, and open Raichu's move-selection menu. The same corrected save and emulator settings that previously froze were used, from a fresh boot. The patch is opt-in via `work/tools/rocket_texture_fix.py`; the normal release builder is unchanged.

See [original reproduction report](rocket_hq_freeze_repro_20261008.md) for save/ROM hashes, emulator settings, the wrong rc55 save distinction, and original crash evidence. The original saves and input ROMs remain unchanged.

## Additional findings

The crash is an invalid animation-frame lookup, not malformed texture bytes:

- The active model matches `a/0/8/1` member **269**, a BMD0 resource with material texture name `sppoke4.1`.
- The separate active texture matches member **243**, a BTX0 resource containing one texture named `stop` and one palette. Its pixel data depicts a barrier.
- Both resources are byte-identical to the user's vanilla USA ROM. The same members are present in the hack's two clothing archives, `data/clothes1/a081.narc` and `data/clothes2/a081.narc`.
- The active texture animation data matches the 68-byte members **280 and 286** (identical data, so a byte comparison alone cannot distinguish which was loaded). It has 16 keys with texture indices `0,8,9,10,11,12,13,14,15,1,2,3,4,5,6,7`, and palette index zero throughout. This is incompatible with a one-texture dictionary for every nonzero selection.
- At the failing call the requested texture index is **4**, while the dictionary count is **1**. The shared animation caller is `02024604`; it obtains the frame from `02027254` and calls the texture updater at `02024654`, followed by the palette updater at `02024758`.
- This is consistent with a static barrier receiving an animation/facing selection that asks for a nonexistent frame. The exact higher-level object configuration responsible for that assignment is not yet traced. No claim is made that the artwork itself needs replacing.

Resource identification used exact byte comparisons against the supplied ROM and live memory. Read-only DeSmuME hooks recorded object structures, animation data, null-load registers and call stacks. No state editing was used for these observations.

## Patch and semantics

The routine already checks the requested index against the texture count. Its unsigned bounds branch is wrong in effect: it goes to a path that assigns NULL, which then reaches an unconditional load.

```text
02024678  ldrb r3,[r3]       ; texture count
0202467A  cmp  r2,r3         ; requested index against count
0202467C  bhs  02024690      ; original bytes 08 D2
...
02024690  movs r0,#0
02024692  b    02024696
02024696  ldr  r0,[r0]       ; null dereference
...
020246D8  pop  {r3-r7,pc}    ; existing balanced epilogue
```

Change `08 D2` to **`2C D2`** at ARM9 address **`0202467C`**, so the existing `bhs` targets **`020246D8`**. In all three tested ROM layouts this is file offset **165500 (`0x2867C`)**. Only the low byte differs; ROM length, header, files, saves, script state and artwork are untouched.

For a valid index the original path is unchanged. For an invalid index the updater returns without modifying the material's current texture binding. This is suitable for the observed static barrier: its valid existing frame remains bound. The routine has no consumed return value at the observed caller; the caller still performs the palette update, whose index here is valid (zero).

This is a defensive bounds fix, not a correction of the higher-level animation assignment. Other invalid texture requests also skip their update, so further maps should be checked before shipping. Null model/resource pointers and invalid palette selections are separate cases and are not addressed by this branch change.

## Verification

- **Before:** original Chinese, released rc5 and English WIP all froze in melonDS at map 247 `(17,4)` with abort CPSR `60000097`, saved PC `FFFF0108`, abort LR `0202469E`.
- **After, melonDS rc5:** reached map 247 `(23,4)`, triggered the ambush, entered the double battle and opened the move menu. Saved state `fixed_rc5.ml1` contains the corrected branch `2cd2`, CPSR `0000001F` (system mode), saved PC `020D2D24`; it is not in the abort handler.
- **After, DeSmuME rc5:** 436 out-of-range requests safely skipped, 8,423 valid requests retained, **zero null loads** at `02024696` during the scripted walk/battle-menu check.
- **After, DeSmuME Chinese:** 443 out-of-range requests safely skipped, 8,550 valid requests retained, **zero null loads**; reached the battle at `(23,4)`.
- **After, DeSmuME English WIP:** 454 out-of-range requests safely skipped, 8,765 valid requests retained, **zero null loads**; reached the battle at `(23,4)`.
- The patcher's three unit tests cover branch condition/target, one-byte change, rejection of already-patched or unexpected code, wrong epilogue, truncated headers and invalid ROM bounds.
- The tool successfully verifies and patches the instruction signature in all three ROM versions. It refuses in-place output, existing output paths and unsupported instruction layouts.

This run does not claim battle completion, post-battle saving/reloading, Five Island coverage, Android/iOS or real-hardware testing. The observed failure is fixed through the battle menu on desktop melonDS. The original report's save-transfer workaround remains unverified.

## Reproduce the patch

Run from this worktree root; provide a local ROM and a new output path:

```sh
python3 -m unittest discover -s work/tools -p test_rocket_texture_fix.py
python3 work/tools/rocket_texture_fix.py INPUT.nds work/build/fixed.nds
```

Use the original battery save beside the patched ROM with the matching basename and `.sav` extension. Boot the patched ROM afresh: old emulator save states contain the old ARM9 code and are unsuitable for validating the ROM change.

Local ignored evidence is in `work/build/rocket-fix/`: patch hash reports, `fixed_rc5.ml1`, decoded `melonds_fixed_result.json`, trace/register snapshots, and DeSmuME screenshots/results. Earlier evidence is in the primary checkout's `work/build/rocket-repro-20261008/`. Redundant test ROM copies were removed to reclaim space; original ROMs, save inputs and crash states were retained.

No downloads, commits, uploads, releases, or changes to the primary translation/build pipeline were made.

## Five Island follow-up (2026-10-08)

The subsequent [Five Island investigation](five_island_freeze_20261008.md) reproduces the same abort and verifies this same guard in melonDS using a completed in-game save after a disposable scripted warp. The code investigation now resolves the higher-level cause: sprite349 with movement17 forces facing3/right, selecting absent frame4; configured animation member280 is selected through descriptor23. This extends the earlier coverage statement above; exact reporter bridge/Surf routing and mobile testing remain outstanding.

## Additional-location follow-up (2026-10-08)

The [broader binary search](texture_additional_repro_20261008.md) reproduces Seven Island frame11/count1 as an actual melonDS abort and verifies this same one-byte guard loads the identical save and permits movement. A diagnostic Bell Tower visibility setup also produces frame15/count1 NULL loads, eliminated by the guard. Separate palette/overlay87 candidates remain unproven and outside this patch.

## Production integration authorized (2026-10-08)

The subsequent user request to put all four reproducers in the harness and build fixes supersedes the earlier opt-in-only scope. The shared guard is now enabled in this worktree’s normal code-patch configuration. All four cases reproduce on original Chinese/rc5 and pass on production-stage patched ROMs. See [integration and validation](texture_regression_integration_20261008.md). Earlier statements above describe the initial experiment, not current build integration.

## Ported to the per-fix format (2026-10-08)

The fix is now `work/patches/overworld-texture-frame-bounds/` (fix.toml and an armips source that guards the whole routine and changes the one branch), not a `code_patches.json` entry; the build applies it like every other code fix and `build.py --without overworld-texture-frame-bounds` leaves it out. Its build is byte-identical to develop `dfe8ba2` plus the `code_patches.json` entry above (ROM SHA-1 `df28a14f…`, work/notes/toolchain.md). The standalone patcher `rocket_texture_fix.py` and its tests, and `test_texture_build_patch.py` (the old `hardcoded.py` path), were not carried over: the build and the release xdelta apply the fix, and `test_emu_texture_bounds.py` and `test_asmpatch.py` (GOLDEN) check the same bytes. Commands above that name them refer to the `codex/rocket-hq-freeze` worktree.
