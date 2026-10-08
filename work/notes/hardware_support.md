# Real-hardware support: the anti-piracy bypass

**Status (2026-10-07): patch designed and checked statically and in DeSmuME; not yet run on any real console or flashcart.** User decision D-1616 (built into the single English patch, no separate hardware patch); fidelity rule D-1617. The patch is the fix `work/patches/antipiracy/` (fix.toml: regions `antipiracy-ov114-0x864` … `antipiracy-ov114-0xCCC`; `antipiracy.asm`: the six stubs in armips, ARM mode); until 2026-10-08 they were entries of `work/translate/hardcoded/code_patches.json`.

Sources: a static and emulator analysis of the untouched Chinese ROM, US HeartGold and our WIP build (2026-10-07; decrypter, disassembly and DeSmuME probe logs kept outside git), and an earlier read-only audit of the Bradams fork's builds (2026-10-05, also outside git). Labels: **[P]** proven from bytes, disassembly or an emulator run; **[I]** inference.

## Why real hardware freezes

The hack is built on the Japanese HeartGold (game code `IPKJ`) and keeps Nintendo's DS Protect library, the SDK's anti-piracy kit. DS Protect does not stop the game at boot. It plants bugs: when a check fails, the game keeps running but leaks memory and starts tasks that never end, so it freezes later, at a menu, a map change or a battle. That matches what testers on real hardware report: the game boots, plays for a while and then hangs.

Emulators (melonDS, DeSmuME) pass every check, which is why the translation has never shown these freezes in testing. [P]

## What DS Protect does in this hack

### The overlay

Overlay 114 (RAM `0x02263200`, `0x1320` bytes) holds the checks; it is US overlay 123 in the hack's numbering (the CN overlays 106–113 match US 114–121 by size; US 122 has no counterpart). Overlay 115 is one of the consumers. Overlays 114 and 115 are byte-identical in the Chinese ROM and our build; only their file offsets in the ROM moved. [P]

The US copy is encrypted as a whole and compressed; the hack's copy has plain entry code and 18 RC4-encrypted blocks that decrypt themselves in place, run and re-encrypt. So no US offset or byte pattern applies to the hack. [P]

### The checks

| Check | What it tests | Fails on |
|---|---|---|
| Card mirror ("Magicon") | Reads six 512-byte blocks of the card (below and above `0x8000`) with raw card-bus commands and compares their CRC32s. A genuine cart mirrors every read below `0x8000`. | Flashcarts and loaders that return real data below `0x8000`. |
| Emulator | Reads the console's MAC address and owner info. | MAC `00:09:BF:00:00:31` with a 1/1 birthday and no nickname (old emulator defaults), or an all-zero MAC (some loaders). |
| Integrity | Compares the prologues of the four check bodies with the original bytes. | Anyone patching inside the checks. It does not cover the six entry points. |

Each check exists as a "bad" predicate and a "good" twin. [P]

### The six entry points

| File offset | Entry | Combines | Genuine-cart return |
|---|---|---|---|
| `0x864` | mirror-bad + integrity-bad | any nonzero | **0** |
| `0x94C` | mirror-good + integrity-good | all nonzero | **1** |
| `0xA34` | emu-bad + integrity-bad | any nonzero | **0** |
| `0xB1C` | emu-good + integrity-good | all nonzero | **1** |
| `0xC04` | empty list | any → always 0 | **0** |
| `0xCCC` | empty list | all → always 1 | **1** |

Each entry takes a callback in r0 and runs it when its result means "detected" (bad entries) or "genuine" (good entries). In the untouched Chinese ROM under DeSmuME, which behaves like a genuine cart, the entries returned exactly 0, 1, 0, 1, 0, 1. [P]

### Callers and punishments

A scan of arm9 and all 120 overlays finds exactly 18 call sites, all direct `blx` into the six entries, in six consumers. No other code points at the entries. [P]

| Consumer | When it runs | On a failed check |
|---|---|---|
| Overlay 115 | Once, right after Continue | Two heap-3 allocations of 20,000 bytes × badges (at least 20,000), never freed, plus a 1,000-byte leak |
| Overlay 1, field start | Every return to the field (after Continue, each menu, each battle) | Two endless tasks that call the RNG every frame, plus a 1,000-byte leak |
| Overlay 1, field exit | Every time the field closes (Pokégear, Trainer Card, Pokédex, Party, Bag, battle start) | Two more endless tasks |
| Overlay 28 | Right after the field exit | 1,000-byte heap-3 leaks |
| Overlays 5 and 31 | When certain apps close | 1,000-byte heap-3 leaks |

Each consumer folds the results into a checksum that is zero only on the genuine path. [P]

With the mirror check forced to fail in DeSmuME: two 20,000-byte leaks at Continue, then four endless tasks and two or three 1,000-byte leaks per menu round trip. [P] The main task queue has 160 slots, so after roughly 35–40 menus or battles new tasks fail and the game freezes. The leaks also starve the Bag and Summary heaps, which live inside heap 3, and the extra RNG calls change random results. [I] This is why the freeze comes after some minutes of play rather than at boot, and why more badges make it come sooner.

## The patch

Six code patches in overlay 114, one per entry. Each replaces the entry's first 8 bytes (`push {r4-r10,lr}; sub sp,sp,#0x80`) with `mov r0,#imm; bx lr`, where imm is the genuine-cart value from the table above. The check bodies stay in the file but can no longer run.

Why it is safe, including on emulators:

- Every entry returns what the untouched hack returns on a genuine cart or an emulator, so every consumer checksum stays at zero and no leak or task is ever created. [P]
- The stubs skip the callback. Every callback passed to a "genuine" entry is a bare `bx lr`, so skipping it changes nothing; the callbacks of the "detected" entries are the leaks. [P]
- The integrity checks only cover the check bodies, not the entry prologues. [P]
- The callers are Thumb `blx` into ARM code, so `bx lr` returns correctly. [P]
- The two empty-list entries (`0xC04`, `0xCCC`) already return a constant; they are patched for parity with a build known to run on hardware. [P]
- There are no other call sites, no checksum over overlays 114/115 and no anti-piracy code in arm9. [P]
- The six stubs match byte for byte the overlay 114 of the Bradams "Speedoption" build, the community build that runs on New 2DS XL. [P]

So on emulators and genuine carts the game behaves exactly like the untouched Chinese hack (D-1002); the bypass is not a hack-bug fix (D-1337) and does not reopen that policy (D-1617).

## Why loaders don't fix it themselves

- TWiLight Menu++ / nds-bootstrap applies anti-piracy fixes from its `apfix.pck` list, keyed by game code **and** header CRC16 (also from `sd:/_nds/nds-bootstrap/apFix/<rom name>.ips` or `<TID>-<CRC>.ips`; see `retail/arm9/source/pck_load.cpp` in the nds-bootstrap repository). The hack's header CRC (`F6D2` in Chinese, `BD29` in the current English build, and it can change with each build) is in no list, so it gets no fix. Vanilla HeartGold works because its CRC is listed. [P for the keying, I for the effect]
- Wood R4, YSMenu and AKAIO carry built-in anti-piracy patches per game. If one keys on the game code alone, it would apply Japanese-retail offsets to the hack, whose overlays 1, 5, 28 and 31 differ: that could corrupt code. Not verified either way. [I]
- US-offset patches can't match: different game code, overlay numbering, file offsets and encryption form. [P]

Hence the fix ships in our patch, and players must not add another anti-piracy patch or apFix `.ips` on top (D-1616).

## Proven vs untested

Proven:
- what each check, entry and consumer does, and the genuine values (static and DeSmuME);
- the punishment on a failed mirror check (DeSmuME, forced);
- the stubs equal the Speedoption bytes.

Not yet tested:
- any run of our patched build on a real console or flashcart;
- that the patched build shows no leaks and no extra tasks over a long session in an emulator (hook the heap-3 allocator and task creation, as the earlier probe did);
- DS mode. The Bradams anti-piracy build still froze on an original DS with R4/YSMenu and on a DSi with DSPico, but that fork also changed heaps, the task queue and other code, so those reports don't isolate the cause. No DS-mode memory problem is known: the highest overlay ends at `0x02264920`, nothing is placed at or above `0x02400000`, the root heaps are only 45 KiB larger than US, and DeSmuME runs the game with 4 MiB of main RAM. The only DSi register access is inside the anti-piracy card read, which the stubs no longer reach. DS-mode and flashcart status is **unknown** until tested. [I]
- ROM size: the used size is about 261 MiB, above 256 MiB (capacity code 12). Some old flashcart kernels mishandle ROMs over 256 MiB. One flashcart test should cover this; it is not an anti-piracy issue.

## Hardware test matrix

Test the same build and the same save on each row. "Pass" = two hours of normal play, at least 60 menu or battle transitions, with no freeze.

| Device | Loader | Mode / settings | Expectation | Result |
|---|---|---|---|---|
| New 3DS / New 2DS XL | TWiLight Menu++ + nds-bootstrap (current) | Run in DSi mode, VRAM DSi | Should work (the community AP build works here) | |
| Old 3DS / 2DS | TWiLight Menu++ + nds-bootstrap | Run in DSi mode, VRAM DSi | Should work | |
| 3DS / 2DS | TWiLight Menu++ + nds-bootstrap | Run in DS mode | Unknown | |
| DSi | TWiLight Menu++ + nds-bootstrap (SD card) | DSi mode, then DS mode | Unknown | |
| DSi | DSPico | default | Unknown | |
| DS Lite / original DS | R4 with Wood R4 | default | Unknown; check the kernel's own AP patch is not applied | |
| DS Lite / original DS | R4 with YSMenu | default | Unknown | |
| DS Lite / original DS | Acekard / R4 with AKAIO | default | Unknown | |
| any | any flashcart | — | ROM over 256 MiB loads at all | |
| PC | melonDS | default | Regression: same as before the patch | |
| PC | DeSmuME | default | Regression; also run the probe for leaks and extra tasks | |
| iPhone | Delta | default | Regression | |

## Triage of hardware reports

Ask for: device, loader and its version (TWiLight Menu++ and nds-bootstrap separately), per-game settings (DS/DSi mode, CPU speed, VRAM), patch version, where and when it froze, time played since the last power-on, badge count, black screen vs frozen picture, and a RAM dump if possible (nds-bootstrap in-game menu: L + Down + Select; the dump is saved to `sd:/_nds/nds-bootstrap/ramDump.bin`; see the nds-bootstrap controls page on the DS-Homebrew wiki for the dump option).

| Pattern | Likely cause | Action |
|---|---|---|
| Freezes after a while at a menu, a map change or a battle start, later each time after a reset, sooner with more badges | Anti-piracy leak still active (an older patch, or another AP patch or apFix stacked on top), or another memory leak | Check the patch version and that nothing else patches the game. With a RAM dump, look for the 20,000-byte heap-3 blocks and a full task queue. |
| Freezes at the same spot every time, quickly, regardless of play time | An event or script problem | Reproduce on melonDS with the player's save. If the untouched Chinese hack does the same on an emulator, it's a hack bug: log it and report it, don't fix it (D-1002, D-1337). If only our build does, it's ours: fix it. |
| Freezes only on hardware at a fixed spot, never on an emulator | Timing, DSi/DS mode or loader | Retry with the other mode and current loader versions; record it in the matrix. |
| White or black screen at boot, or the loader refuses the file | Loader or flashcart (ROM size, header) | Not anti-piracy. Record loader and version. |
| Slowdown, sound crackle | 3DS in DS mode (67 MHz) or the hack's 60 fps overworld | Suggest DSi mode; not a bug. |

Report the confirmed results in this note's matrix and in the FAQ's hardware section.
