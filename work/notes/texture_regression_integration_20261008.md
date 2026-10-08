# Four texture regressions and build integration (2026-10-08)

The user explicitly requested permanent harness reproducers and built fixes for all four demonstrated locations. This authorizes integrating the shared guard into builds in this worktree, superseding the earlier opt-in-only experiment. Branch: `codex/rocket-hq-freeze`. Nothing is committed, merged or published.

## Implementation

`work/tools/emu_harness.py texture-bounds` invokes `emu_texture_bounds.py` for `rocket_hq`, `five_island`, `seven_island`, and `bell_tower`. Each case restores a freshly booted baseline from the same tested ROM, clears its documented visibility flag in disposable RAM, performs a normal scripted warp, and observes360 settled frames. It verifies target position, ROM instruction signature, expected invalid frame/count pair, positive valid updates, and null-load expectations. Missing trigger, hook error, map mismatch, incorrect branch, or input hash changes fail the run. Reports retain hashes, counts, bounded register samples and screenshots. Inputs are never exported over or changed.

The enabled `overworld-texture-frame-bounds` entry in `work/translate/hardcoded/code_patches.json` is consumed by normal `build.py` stage3c. One shared fix covers all four failures: the out-of-range branch returns without changing the current texture binding. The config verifies the entire134-byte routine including its return, and changes exactly one byte. No map scripts, object movement, palettes or save logic are patched.

## Built artifacts and verification

The actual production `hardcoded.apply` / `hardcoded.verify` path built local `work/build/texture-regression/production_cn.nds` and `production_rc5.nds`. Verification was repeated after reopening them. Both preserve source size and differ from their input at only byte165500. These are targeted builds from supplied CN/rc5 ROMs through the new production patch entry, not a full rebuild of current translation assets. Normal future full builds include the entry unless hardcoded patches are explicitly disabled.

All16 runtime assertions passed: four cases × original/fixed × Chinese/English rc5. Both languages produced the same table:

| Case | Invalid requests before/after | Original null loads | Fixed null loads | Valid updates before/after |
|---|---:|---:|---:|---:|
| Rocket HQ |180 /180|180|0|3240 /3240|
| Five Island |180 /180|180|0|4320 /4320|
| Seven Island |180 /180|180|0|900 /900|
| Bell Tower |720 /720|720|0|1080 /1080|

All four reports verify unchanged input hashes. Reports: `work/build/texture-regression/{harness_cn_original,harness_cn_fixed,rc5-original,rc5-fixed}/report.json`. Build identities and production-stage report: `production_build.json` in the same directory.

Unit checks:38 existing harness tests,13 focused texture tests (6 regression oracle,4 production integration,3 standalone patcher), and10 existing hardcoded tests passed. Two other hardcoded tests were skipped because their default local ROM fixtures are absent in this worktree. `git diff --check` passed. Independent review checked baseline isolation, unsupported-code rejection, non-vacuous pass conditions and input/output collision protection.

## Running

Run from this worktree root with a local raw battery save (tested with player B's HQ save):

```sh
<primary-checkout>/.venv/bin/python work/tools/emu_harness.py texture-bounds --rom ORIGINAL.nds --sav INPUT.sav --out work/build/check-original --expect original
<primary-checkout>/.venv/bin/python work/tools/emu_harness.py texture-bounds --rom FIXED.nds --sav INPUT.sav --out work/build/check-fixed --expect fixed
```

`--case` accepts a comma-separated subset. An original run passing means it reproduced the defect; a fixed run passing means it exercised the same invalid requests without null loads. This DeSmuME hook regression is not itself a visible-hang test. Earlier melonDS original/fixed demonstrations remain in [Rocket HQ](rocket_hq_freeze_fix_20261008.md), [Five Island](five_island_freeze_20261008.md), and [Seven Island](texture_additional_repro_20261008.md). Bell Tower remains a constructed visibility case. No full quest progression or mobile/hardware coverage is claimed.

The full CLI/setup documentation is in [emu_harness.md](emu_harness.md). All game data and generated evidence stay ignored. Unrelated work in the primary checkout is untouched.

## Ported to the per-fix format (2026-10-08)

The fix is now `work/patches/overworld-texture-frame-bounds/` (fix.toml and an armips source that guards the whole routine and changes the one branch), not a `code_patches.json` entry; the build applies it like every other code fix and `build.py --without overworld-texture-frame-bounds` leaves it out. Its build is byte-identical to develop `dfe8ba2` plus the `code_patches.json` entry above (ROM SHA-1 `df28a14f…`, work/notes/toolchain.md). The standalone patcher `rocket_texture_fix.py` and its tests, and `test_texture_build_patch.py` (the old `hardcoded.py` path), were not carried over: the build and the release xdelta apply the fix, and `test_emu_texture_bounds.py` and `test_asmpatch.py` (GOLDEN) check the same bytes. Commands above that name them refer to the `codex/rocket-hq-freeze` worktree.
