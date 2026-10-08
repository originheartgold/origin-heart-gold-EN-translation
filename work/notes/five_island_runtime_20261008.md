# Five Island runtime investigation (2026-10-08)

Worktree: `codex/rocket-hq-freeze`. Disposable save warps and isolated investigation authorized by the user. No input save or ROM changed.

## Established findings

A normal scripted warp to Five Island (map154,104,54), using player B's supplied HQ save with its existing story flags, loads the Snorlax-area barrier and reproduces the exact invalid texture lookup seen in Rocket HQ in untouched Chinese v4.0.3. DeSmuME continues despite the null load; melonDS validation is recorded separately by the coordinating agent.

Read-only hooks at `0202467C` and `02024696` record requested texture index4, dictionary count1, and NULL loads. Live material bytes include `sppoke4.1`, matching the Rocket HQ barrier resource. A separate matched control sets only hide flag2173 in the disposable save: after the same scripted warp there are zero invalid requests/null loads. This flag hides both the barrier and Snorlax, so by itself it isolates the pair; static resource/event evidence identifies the barrier.

The existing guard-patched Chinese ROM has305 invalid requests safely skipped and zero NULL loads during the matched warp/wait/input sequence. These are read-only hook observations; the only memory alteration is the harness's normal scripted warp setup, not renderer state.

## Fixture caveats

The stock `SaveFile.place_player` location-only fixture is unsuitable here: removing old saved map objects does not construct the new map objects on Continue, and the player cannot move normally. Those initial tests and JSONs (`visible_original`, `visible_patched`, `hidden_original`, `bridge_original`) are setup failures, **not** evidence of a passing map or patch.

A first normal-save export (`playerb_five_ingame.sav`) happened before all storage writes finished: mirror0 general counter4 is valid but storage remains counter2 with an invalid CRC; the game falls back to the old mirror3 HQ save. That fixture is **invalid**. It is retained only as a diagnostic and must not be distributed or used for testing. The replacement `playerb_five_complete.sav` waits5000 frames and has valid general/storage mirror0 blocks both at counter4, CRC19916/53238. Old mirror1 blocks both remain valid counter3. SHA256: `5bcfdabbff93d42d331f4a176fd6770ee736d6bbf8ad4e9eb947cf05aa672e65`. This is the usable fixture.

## Scope

The report mentions crossing a bridge or Surfing across a river but does not specify coordinates. We identified a visible bridge at(122,62), east of the Snorlax barrier, and traversed nearby positions under DeSmuME after a scripted warp; the barrier remained active and invalid requests occurred. We have not reconstructed the reporter's exact approach, proved which bridge they meant, or tested Surf input. A successful near-barrier reproduction establishes the same failure class on Five Island; it does not prove the report's complete route.

All three supplied save states inspected (player B's named HQ save, player B's hash-named save, player A's corrected save) have flag2173 clear naturally. Hash save begins at map29(1357,48), not Five Island. Original flags remain unchanged in the main fixture; setting2173 is explicitly a separate diagnostic control.

## Local evidence

Ignored scratch: `work/build/five-runtime/`.

- `five_null_trace.json`, `five_null_trace_full.json`: initial live warp trace.
- `hidden_warp_original.json`: hidden pair control,0 invalid/0null.
- `visible_warp_patched.json`: existing guard,305 invalid/0null.
- `probe_warp.py`: matched instrumentation recipe.
- `save_fixture.py`: normal in-game save recipe with full write wait.
- `trace/warp56.png`, `trace/npc_south.png`, `trace/bridge_clean.png`, `trace/bridge_walk.png`: screenshots.

## Matched final results

| Setup (Chinese v4.0.3, DeSmuME) | Invalid requests | NULL loads | Valid updates |
|---|---:|---:|---:|
| Scripted warp, original |305|305|7712|
| Same warp, existing guard patch |305|0|7712|
| Same warp, hide2173 control, original |0|0|7407|
| Complete genuine battery save, fresh original boot |574|574|13776|
| Same complete battery save, fresh guard-patched boot |574|0|13776|

Final fresh-boot fixture correctly reports map154(104,54) at Continue and loads the Snorlax scene. Counts include boot/wait and ten UP inputs. UP is blocked by the NPC immediately north, so these counts establish renderer behavior, not traversal; the independent earlier scripted-warp walk moved from(103,56) to(103,53), and bridge walk from(122,62) to(122,66). First failing fresh-boot request occurs at frame3471.

Machine-readable final files: `visible_warp_original.json`, `visible_warp_patched.json`, `hidden_warp_original.json`, `complete_reboot.json`, `complete_reboot_patched.json`. Same valid-update counts in the original/guard pairs support that valid texture updates remain unaffected for these test sequences. This is not exhaustive gameplay testing.
