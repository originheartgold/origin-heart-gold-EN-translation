# Code-proven receiving buffers and numeric expansion

**Status (2026-10-09): historical.** The rc5 quality tools this note describes (text_buffer_check, text_consumer_check, the static text checks) were removed in the 2026-10-09 cleanup; the release gate is `check.py --full --strict-release` plus `--emu`. The findings below stay as the record; `git log --diff-filter=D -- work/tools` finds the scripts.

Verified against the untouched Chinese v4.0.3 ROM and the approved-review candidate on 2026-10-04. These are specific consumer contracts, not a declaration that every possible consumer is safe. No ROM, translation, or gameplay code changes are involved.

`text_capacity_proofs.py` fingerprints complete relevant native routines and their literals. `text_consumer_check.py` applies the resulting contracts to shipped records; `text_safety_check.py` also applies them to the fresh workspace export. A changed allocation, source-bank literal, destination-field offset, call target, formatter, or numeric producer invalidates its proof and reports incomplete coverage. Known consumer success never removes the global consumer-discovery gap.

## Direct receiving buffers

| Consumer | Bank | Capacity including EOS | Candidate maximum | Entries |
| --- | --- | ---: | ---: | ---: |
| Move-description screen, overlay 65 | `a027/0738` | 256 units | 107 | 921 |
| Pokédex-description reader, overlay 5 | `a027/0791` | 256 units | 122 | 1,441 |

For moves, overlay 65 initialization at `021E4F3C` allocates `String_New(256, 66)` at `021E4F66` and stores its pointer in the screen object's `+0x100` field. The complete consumer at `021E594C` selects bank 738 using the literal at `021E5AA4`, retrieves that same field at `021E5A1A`, and passes it directly to `ReadMsgDataIntoString` at `021E5A20`. The entire initializer and consumer, including bank literal, are guarded. The shared message constructor accepts only the reviewed Chinese form or the rc4 form whose single instruction forces on-demand mode; both preserve bank and destination semantics. All bank entries are checked conservatively; this does not claim every entry is reachable from that screen.

For the Pokédex, overlay 5 `021E4A14` selects bank 791 in its local-language branch, then passes that bank and the entry ID into `021E4A68`. This helper allocates a 256-unit String at `021E4A86`, preserves the returned pointer in r5, and passes that exact pointer as destination at `021E4A94`. Both full functions and selector literals are guarded.

The shared native reader (`0200BB0C`, on-demand path `0200B89C`) copies decrypted **stored** units into these Strings via `02026EB8`. It does not decompress compressed names or format placeholders. `02026ED4–D8` checks capacity: an oversized copy asserts and skips the copy, potentially retaining stale content; it is not successful truncation and must fail verification. Units include the terminating `FFFF`. Compressed and expanded lengths are separate stages and are not certified by these stored-stage contracts.

## Actual formatter destination and slot producer

Move-screen templates `a027/0736#29` and `#30` have a separate **expanded-stage** contract:

- Overlay 65 initialization creates the default eight-slot formatter at object `+0xFC`, with 32-unit scratch/slot Strings, and a 256-unit destination at `+0x100`.
- The guarded consumer passes template IDs 29/30 and numeric width 3 into helper `021E5350`. This helper reads bank 736, writes numeric slot **0**, then calls the native formatter `0200C738` into the proven `+0x100` destination.
- Numeric producer `0200BF1C` calls conversion `02026974`, then copies its result into that slot through `0200BD98`. The full conversion and copy routines, template loader and both eager/on-demand allocating-read branches, command argument reader, and formatter are guarded.
- Width 3 is an actual output bound here, not a minimum display width: the native conversion indexes the power table at `020F2F8C` to get 100, and executes at most three positions (100, 10, 1), dividing by 10 each time. A quotient beyond a decimal digit becomes `?`; it does not add more positions. Negative values add one sign. Thus the slot has at most **4 units excluding EOS**, safely within its actual 32-unit allocation. The relevant power-table entries and complete division implementation are guarded too.
- Only command `0134` with exact argument `[0]` receives that bound. A changed slot, different substitution, or compressed template remains unresolved. Repeated occurrences are counted separately. No global bound is inferred from a command's low byte or nominal slot capacity.

Both current templates require at most 5 expanded units including EOS. Numeric overflow's displayed meaning is outside this memory bound; neither value correctness nor arbitrary other callers is certified.

## Verification and remaining work

The new tests exercise exact 256-unit limits and one-unit overflow, numeric expansion that crosses the limit despite a short placeholder, wrong slots, unknown producers, compressed templates, and loss of proof status. Native mutation counterexamples change allocation immediates, source-bank literals, destination field accesses, call targets, numeric width, formatter code, constructor parameters, and the numeric power table; every affected contract must become incomplete. Native fixture tests skip explicitly when the local Chinese ROM is unavailable; no game bytes are embedded in the tests.

Reproduce from the repository root:

```sh
.venv/bin/python -m unittest discover -s work/tools -p 'test_text*check.py'
.venv/bin/python -m unittest discover -s work/tools -p 'test_text_capacity_proofs.py'
.venv/bin/python work/tools/static_text_check.py --candidate work/build/approved-review-20261004/candidate/origin_hg_v4.0.3_en_wip.nds --output work/build/buffer-limit-verification/static-rerun
```

The phase-one native loading sweep uses oracle-sized decompression destinations. It does not prove the actual receiving capacities of all compressed trainer/Pokémon names. Those callers and arbitrary runtime substitutions remain gaps. These new direct description and narrow numeric contracts do not resolve the existing 51 control-contract failures, prove the 50 blanked messages unreachable, or replace gameplay rendering tests.

Final run: `work/build/buffer-limit-verification/static-complete/report.json` inventories all 76,862 entries in 821 banks. All 2,364 new per-consumer checks pass in both the candidate and fresh workspace export, with zero capacity failures. The aggregate remains failed for the same 51 pre-existing control-contract failures; unresolved coverage remains incomplete. A compact result is in `work/build/buffer-limit-verification/summary.json`. The 108 existing text-check tests and 14 new proof/boundary tests pass.

## Approved-warning follow-up (2026-10-04)

A further guarded contract covers stored reads of all six certificate messages
in bank `0004`, including the corrected friendship certificate `0004#5`.
Overlay 75 creates the bank-4 handle at `021E4E3A` and stores it at object
`+0x38`. Function `021E50E8` allocates two 512-unit Strings at `021E50F4` and
`021E511C`; header IDs 0/4 use the second, and body IDs 1/2/5 plus footer ID 3
use the first. Both complete routines and the common copy path are guarded.
The contract is stored-stage only: header substitutions still need their own
expansion bounds. Mutation tests invalidate changed bank selection, allocation,
message ID, destination transfer and read calls, and test 512-unit boundaries.

A direct Thumb-call survey of the candidate found the compressed append routine
at `0202703C` called by the formatter at `0200C782` and by the font-validation
wrapper at `02002F34`. Three direct wrapper callers were found in overlay 41
(`0222D0A2`, `02240ABA`, `02240B4A`); each passes a 64-unit temporary String.
This narrows the investigation, but does not establish all producer bounds or
exclude indirect/ARM/tail calls. No new overflow is demonstrated, and this is
not a universal compressed-name capacity proof. Local disassembly evidence is
under `work/build/approved-warning-followup/`.

## Ordinary NPC message buffers: three original-script bindings

The follow-up traces NPCMsg (opcode 45) through the original Chinese code:
command-table entry `020F79F0` selects overlay 1 handler `021EE288`, which
reads the one-byte message ID and the script context's `+0x78` bank handle.
`021EE448` gathers the script-manager members using `021EE58C`. Getter IDs
17 and 18 resolve to manager fields `+0x48` and `+0x4C`; initialization at
`0203F68A` and `0203F696` allocates **1024 units each, including EOS**.
`021EE658` loads the unexpanded record into `+0x4C` at `021EE662`, then formats
into `+0x48` at `021EE66C`. Page breaks do not divide these allocations.

`inspect_field_proofs` guards the dispatcher, context/bank construction,
map-header getters, member getter, allocation and complete transfer routines.
It also guards the actual map-header rows and full original script members,
checking each reviewed NPCMsg opcode/operand. The narrow bindings are:

- Map 187, script 31 at offsets 2026/4464/4504: `a027/0065#60`.
- Map 398, script 829 at offset 3353: `a027/0525#57`.
- Map 43, script 249 at offset 2587: `a027/0389#56`.

The candidate records require 1242, 1114 and 1094 stored units respectively.
All three now fail the actual 1024-unit consumer contract in the ROM and fresh
workspace checks. The original-script binding is stronger than injecting those
strings into another field scene: it establishes that their original NPCMsg
instructions select this same native consumer. It does not prove every story
branch is reachable from a particular save or supply bounds for other messages.

Mutation tests change allocations, pointer transfers, dispatch, map getters,
map script/bank pairs, whole script hashes, opcodes and IDs. Each affected proof
must become incomplete. Exact 1024-unit strings pass; 1025 fail. Both original
Chinese and current candidate code/data bindings validate. These are stored-stage
contracts only; arbitrary runtime expansion remains a separate obligation.
