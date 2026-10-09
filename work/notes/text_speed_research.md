# Text speed feasibility — 2026-10-05

Historical feasibility notes. Native implementation and current validation are documented in [text_speed_release.md](text_speed_release.md). The statements below describe the initial research stage.

Research branch: `codex/text-speed-research`, worktree `/private/tmp/poke-text-speed-research`, based on `0121c30`. All experimental outputs are under ignored `work/build/text-speed/`. No production patch, translation, save, or ROM was changed. This is a feasibility experiment, not an implemented Options setting or release certification.

## Result

NORMAL / FAST / INSTANT is feasible without undoing the RC4 memory fix. NORMAL should preserve the Chinese renderer. FAST should batch a small number of glyphs; INSTANT should reveal the current page while retaining player prompts, scripted waits, and callbacks. The experiment demonstrates ordinary field dialogue acceleration. A shipped implementation still needs native code, settings/menu integration, and broader runtime validation.

The Chinese text-speed getter at `0202B1C0` is `movs r0, #2; bx lr`. Its delay mapper at `0202B1E4` therefore returns 1 regardless of options. The original Options text-speed nibble is instead read by `0202B1C4` and exposed as MUSIC SPEED. Restoring vanilla's slow/medium/fast delay mapping would not supply faster-than-Chinese text: Chinese already selects its fastest conventional delay.

This does not mean every glyph always completes in exactly one emulated video frame. Rendering, transfers, and scheduler load also matter. English generally needs more glyphs for equivalent dialogue; this is a plausible contributor to perceived slowness, not an exhaustive performance diagnosis.

## Loading and printing are separate

`NewMsgDataFromNarc` at `0200BA98` creates message handles. RC4 changes `0200BA9A` from `051C` to `0125`, forcing demand loading. This reads a requested message into a String before printing; it does not read the message bank anew per displayed character. Keeping that change preserves the protection against large English banks exhausting screen heaps.

`AddTextPrinter` at `020208D4` takes an existing String, unwraps it at `02020952`, and stores its pointer. The asynchronous printer is `02020A1C`; `02020A88` dispatches rendering; glyph drawing occurs at `02002680`. These are separate from bank construction/reading. No loading-mode change is necessary to accelerate glyph drawing. This research did not benchmark flashcart I/O or prove demand loading has no latency cost.

Binary comparisons of the untouched Chinese ROM and the available English WIP found identical bytes in:

- Options speed functions: `0202B1C0–0202B200`.
- Printer construction/dispatch: `020208D4–02020A9A`.
- Renderer/control handling: `020022D0–02002B10`.
- The entire Options overlay 50.

The compared English WIP contains the demand-loading instruction. Its hash is `caf987949ea7e208f8cae1c49c76b1cf3fd596338cafeb7270693116bb448b3b`; Chinese is `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`. These identify tested artifacts; the branch's RC5 commit title does not establish that this local WIP is the packaged RC5 ROM.

## Controlled experiment

The exploratory harness was `work/research/text_speed/probe.py` (removed in the 2026-10-09 cleanup; git history keeps it). It uses the existing local Python/DeSmuME installation and machine-local input paths. Invoke it from this worktree root. It is deliberately a research harness, not a general patcher. Its hooks assume the reviewed binaries above and must not be reused against other binaries without checking addresses. It initializes DeSmuME's macOS graphics and needs execution outside the restricted sandbox on this machine.

Runs used the same `controlled-before.dst` checkpoint, the same ROM, and the same input sequence (one-frame A presses, 240 frames apart). Reports are `en-normal/report.json`, `en-fast/report.json`, `en-instant/report.json`; comparison is `controlled-summary.json`. There are two pages of trainer dialogue followed by transition into battle. Battle text itself was not validated.

| Experiment | Page 1: 54 glyphs | Page 2: 30 glyphs | Heap walks |
| --- | ---: | ---: | ---: |
| NORMAL, unmodified renderer | 54 frame intervals | 29 frame intervals | 72 |
| FAST, up to 3 glyphs per printer task | 25 | 12 | 72 |
| INSTANT prototype, budget 128 | 2 | 1 | 72 |

Times are last glyph frame minus first glyph frame, excluding message-load/startup time and user waiting. They are emulated frame intervals, not Python wall time. The INSTANT prototype is near-instant, not yet a guaranteed single-frame implementation.

Both pages rendered all 84 dialogue glyphs in every mode. Text pixels at crop `(8,153,236,182)` match NORMAL exactly on both pages; the animated prompt arrow outside that crop changes phase with completion time. The second page begins only after the next A press (frame 3665), so the page boundary is preserved in this fixture. All three runs have no detected heap corruption, allocation failure, null write, or text-capacity rejection. These are sampled checks on one fixture, not exhaustive safety proof.

The successful hook runs at `02020A94` after a render result. It changes PRINT to REPEAT only for a zero-delay, state-zero printer with **no callback**, within a bounded glyph budget. It stops before end-of-string, control introducers, and page-prompt characters, ensuring the last glyph is transferred through the ordinary task path. It leaves all callback printers at normal speed. Thus it proves callback-free field dialogue acceleration only; it does not claim battle acceleration or callback safety.

Earlier exploratory runs are excluded: `*-unpaired` did not share a checkpoint, `*-superseded` attempted ineffective PC redirection, and `cn-lazy` did not render dialogue. None is used as timing or safety evidence. Chinese runtime observation independently confirmed speed argument 1, but the paired timings above are English-only.

## Why not simply set speed to zero?

The constructor's speed 0 and 255 branches at `02020966–02020A0E` synchronously iterate rendering up to 1024 times, then free the printer. They do not run the normal per-frame callback dispatch. This is appropriate for existing static-label consumers but not a safe blanket replacement for dialogue. In particular, a prompt/wait can exhaust that loop and the printer is then discarded. Preserve the asynchronous state machine for user-selectable instant dialogue.

A production implementation should batch ordinary glyph rendering, transfer the completed batch once, and stop at prompts, delays, sound/callback barriers, or a bounded work budget. Do not accelerate the entire emulator, scene scripts, or battle animation timers. Explicit scripted pacing remains authoritative.

## In-game setting design and remaining work

Add a dedicated TEXT SPEED row with NORMAL / FAST / INSTANT, preserving MUSIC SPEED and other hack options. NORMAL is the compatibility default for existing saves and should execute the original rendering path unchanged. FAST can start with a three-glyph budget and be tuned from runtime tests. INSTANT means revealing the current page promptly, not automatically advancing it.

Overlay 50 starts at `021E4980`. Its current choice-count table at `021E5C14` is `3,2,2,2,3,20,2` (six settings and confirmation). Its local row records, allocation size, getter/setter mapping, selection bounds, drawing coordinates, and touch hitboxes are fixed. A seventh setting requires changing these together, plus labels/help and confirm/cancel behavior. It cannot be enabled by translating an unused label.

Persistence needs an audit before choosing bits. The inherited options record is two bytes. The high dummy bit alone cannot store three choices. The music field occupies four bits but offers three values; reserving two of its upper bits is a possible compact design **only after** auditing all music getters/setters and direct accesses, ensuring old saves/defaults, menu edits, and music behavior remain compatible. Do not assume unused values mean unused storage. Otherwise use independently verified reserved save storage, with explicit old-save default handling.

Before release:

1. Implement guarded native code injection and keep global demand loading enabled. The Python register hooks are not a deployable patch.
2. Add menu navigation, touch handling, preview/help, confirm/cancel, and save/reload tests for every mode, including old saves.
3. Test ordinary/multiple-page dialogue, CLEAR/SCROLL, timed waits, sound waits, special sizes, menus, and holding A/B. Verify text is neither lost nor auto-advanced.
4. Trace battle text callbacks and printer lifetimes before enabling acceleration there; include trainer/wild/double battles and battle-ending transitions.
5. Run existing heap/buffer checks and compare NORMAL against Chinese behavior. Test another emulator and hardware/flashcart timing before making broad performance claims.

Source references: repository `heap_audit.md` and `exp_share_research.md`; local ROM disassembly is authoritative. Upstream [text.c](https://github.com/pret/pokeheartgold/blob/master/src/text.c), [options.c](https://github.com/pret/pokeheartgold/blob/master/src/options.c), and [options.h](https://github.com/pret/pokeheartgold/blob/master/include/options.h) explain the inherited design but do not replace verification of the modified Japanese-base hack.
