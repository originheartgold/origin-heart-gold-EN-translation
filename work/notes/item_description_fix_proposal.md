# Proposed fix for blank item descriptions

Status: proposal only. No game code patch, translation, graphics asset or ROM has
been changed. See [confirmed findings](tooling_findings.md).

Update: the user requested minimal wording alternatives and has deferred them
for [manual review](item_description_manual_review.md). Those alternatives fit
the existing buffers. The capacity increase below remains an alternative, not
an approved change; no game-data changes should be applied while review is pending.

## Recommended option: increase three description buffers to 128 units

The bag, shop and a third consumer in overlay 9 currently allocate 114 game-text
units. Nearby resources suggest the third consumer is the battle bag, but runtime
tracing has not confirmed that screen attribution. Seventeen English
descriptions exceed that capacity; the maximum is 120 including the terminator.
A 128-unit allocation fits every current description and adds 28 bytes to each
affected allocation. It preserves the translations and the bounded-copy
check. It is an English-required capacity change, consistent with D-1002.

The proposed bag entry is below, as a `[[code]]` entry for a new fix folder (`work/patches/<fix-id>/fix.toml`; written when the registry was `code_patches.json`).
**Since 2026-10-08 (step 2 of the patch refactor):** `[[code]]` entries no longer have `value`. A new code fix is an armips source, `work/patches/<fix-id>/<fix-id>.asm`, that writes the new bytes behind guards on the old ones, plus `asm = "<fix-id>.asm"` and `[[code]]` regions (file, offset, `expect` = original bytes) in its `fix.toml`; see `work/notes/toolchain.md`. The entries below are kept as written; read the replacement halfwords as what the asm would write.
Equivalent guarded entries are needed at overlay 3 address `0x02259B34`
(shop, heap 11) and overlay 9 address `0x021EC12A` (dynamic heap).
A bag-only change would leave two affected consumers.

| File | Offset | Expected halfwords | Replacement halfwords |
| --- | --- | --- | --- |
| overlay3 | `0x3554` | `2072 210B F5CC FE94` | `2080 210B F5CC FE94` |
| overlay9 | `0x738A` | `2072 3420 F63A FB99` | `2080 3420 F63A FB99` |
| overlay17 | `0x51EE` | `2072 2106 F628 FFC7` | `2080 2106 F628 FFC7` |

These use the patch file's halfword notation. The corresponding first two bytes
change from `72 20` to `80 20`; the surrounding instructions remain identical.

```toml
[[code]]
id = "bag-description-capacity"
file = "overlay17"
offset = "0x51EE"
expect = "2072 2106 F628 FFC7"
value = "2080 2106 F628 FFC7"
notes = "Bag item-description String: capacity 114 -> 128 stored units, including terminator; maximum current English description is 120. Guard the heap-6 argument and String_New call; leave the separate formatted-menu allocation unchanged."
```

Only the first halfword changes: `movs r0, #114` becomes `movs r0, #128` at
`0x021FD8CE`. The heap argument and call remain identical. The read-only buffer
checker derives all four capacities from guarded code, so a future build will be checked
against its actual allocation rather than a manually raised test threshold.

The PC consumer in overlay 16 already allocates 1024 units and needs no change.
The separate 114-unit formatted-menu buffer at `0x021FE0C4` is not part of this
proposal. All four description allocations match the Chinese baseline; the
proposed increases accommodate English text without changing gameplay logic.

## Alternative: shorten the 17 English descriptions

Each would need to fit 114 stored units including the terminator, while preserving
all Chinese meaning, numbers, terminology and layout. This avoids a capacity
patch but changes translation text and requires editorial review. It also needs
the capacity gate to prevent future overlong descriptions.

## Validation after approval

1. Apply the chosen change to the source data and build a local test ROM using the
   existing pipeline with `--work-dir work/build/item-description-fix-review`
   and `--no-patch`. This isolates exports, ROM and build report from RC4 evidence.
   Current regenerated Chain Logger graphics will be included;
   the existing RC4 ROM and release patch will remain untouched.
2. Run buffer and artifact gates. Expect all descriptions to fit and the 32
   graphics allocation bindings to pass.
3. Repeat the paired full-bag scenario, verify that Scope Lens's description is
   copied and visibly rendered, and check heap health. Inspect an unaffected item
   and the item-action menu as controls.
4. Check shop descriptions and investigate the overlay 9 consumer's screen before
   claiming complete runtime coverage. Visit Chain Logger in the local test build
   and inspect the corrected labels.
5. Run the normal quality gate and any additional scenarios justified by changes
   or findings. No release publication is part of this proposal.

The actual post-change rendering and heap behavior remain unverified until an
approved local build and runtime test are performed.
