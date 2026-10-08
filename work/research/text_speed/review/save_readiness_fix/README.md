# Save readiness fix regression

The native reader no longer mistakes `SaveData + 4` (a cartridge save exists)
for initialized runtime Options. It retains the null runtime and null Options
fallbacks, plus invalid mode 3 → NORMAL.

The runtime accessor at `0x02001194` returns the main global at `0x021106C8`.
The sole ARM9 constructor call is at `0x02000CD4`; its returned SaveData is
published at `0x02000CDA`, after metadata initialization and either save loading
or new-game initialization. The constructor's earlier internal publication uses
a different global (`0x021D11B4`). This distinction makes the non-null runtime
pointer a valid readiness condition in the exact hash-guarded game binary.

`publication_probe.py` observes a blank-battery boot without memory writes and
asserts publication order, initialized block 1 metadata, default Options 512,
and save-exists flag zero. Its constructor-ready hook runs after the instruction
that assigns the returned SaveData to r0. The earlier exploratory hook immediately
before that instruction incorrectly sampled a temporary r0; it was corrected
and is not evidence about returned SaveData contents.

`mode_regression.py` uses a new checkpoint booted from the fixed ROM and an
existing old battery save. It asserts that checkpoint ITCM matches the fixed
payload exactly, preventing accidental testing of executable RAM from the old
ROM. These cases deliberately modify live RAM, not ROMs or saved files:

| Case | Flag | Expected/observed glyph frame span |
| --- | --- | --- |
| NORMAL | 0 | 54 |
| FAST | 0 | 21 |
| INSTANT | 0 | 2 |
| Invalid mode 3 | 0 | 54 (NORMAL fallback) |
| Null runtime during native mode lookup | 0 | 54 (NORMAL fallback) |
| Historical music values 0, 1, 2 | 1 | 54 each, unchanged Options |

The null-runtime case restores the pointer before the original printer runs;
it asserts no Options accessor was called while the pointer was masked. These
are controlled lookup/renderer regressions, not natural pre-first-save menu
reachability or full memory-safety certification. Each case asserts the initial
selected Options bits remain unchanged. The fresh checkpoint's normal probe also
passed its read-only sampled memory checks.

Outputs stay ignored under `work/build/text-speed/save-readiness-fix/`.
Run commands from the worktree root using the existing Python runtime. The
candidate is compiled from current C with `compile_payload`, then applied to
the existing local English input ROM; cached payload regeneration is owned by
the coordinator. To create the matching checkpoint:

```sh
python work/research/text_speed/native_probe.py \
  work/build/text-speed/save-readiness-fix/checkpoint \
  work/build/text-speed/save-readiness-fix/game.nds /path/to/trainer.sav \
  'fieldboot; shot before-talk; state before-talk; wait 10'
python work/research/text_speed/review/save_readiness_fix/publication_probe.py
python work/research/text_speed/review/save_readiness_fix/mode_regression.py instant
```

Run the latter for `normal`, `fast`, `instant`, `invalid`, `null`, `old-music-0`,
`old-music-1`, and `old-music-2`. On this Mac DeSmuME must run outside the sandbox
because its native macOS application initialization aborts inside it.
