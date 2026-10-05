# RC5 battle Status Healers investigation

2026-10-05. Finding D-1495. Confirmed original-hack behavior; no ROM, gameplay code, translation bank, or source save was changed.

## Result

The Status Healers pocket is empty when the player owns ordinary status medicines but no eligible Berries/flutes. This reproduces in the released RC5. With a mixed inventory, RC5 and untouched Chinese v4.0.3 show the same eligible items.

| Tested items | Battle menu result |
| --- | --- |
| Antidote, Burn Heal, Ice Heal, Awakening, Parlyz Heal, Full Heal, Full Restore, Lava Cookie | Absent; battle-pocket flags are zero |
| Cheri, Chesto, Pecha, Rawst, Aspear, Persim, Lum Berries | Present in Status Healers |
| Blue, Yellow, Red Flutes | Present in Status Healers |
| Heal Powder | Present in HP/PP Restore |
| Potion, Super Potion, Fresh Water, Soda Pop, Lemonade, Moomoo Milk, Berry Juice | Present in HP/PP Restore |
| Leppa, Oran, Sitrus Berries | Present in HP/PP Restore |
| Max Potion, Hyper Potion, EnergyPowder, Energy Root, Revive, Max Revive, Revival Herb, Ether, Max Ether, Elixir, Max Elixir, Sacred Ash | Absent; battle-pocket flags are zero |
| Guard Spec., Dire Hit, X Attack, X Defense, X Speed, X Accuracy | Present on first Battle Items page |

Practical alternative: carry the appropriate status-healing Berry (e.g. Pecha for poison, Cheri for paralysis, Lum for general status healing). Menu availability was tested here; individual cure effects were not exercised. Heal Powder's unexpected category is also inherited from the Chinese source.

Whether these restrictions are deliberate balancing or a source bug is not established. Preserve them under D-1002/D-1337.

## Evidence and method

- Exact released RC5: `work/build/rc5-release-check2/origin_hg_v4.0.3_en_wip.nds`, SHA-1 `6eecb13762af6893ba1ffeebb9142976f51807a5`, matching `work/release/v1.0.0-rc5/latest.json`.
- Chinese reference: `work/rom/origin_v4.0.3_cn.nds`, SHA-1 `b69dc16be246658e3b29027698878d7ec560a1f6`.
- Entire `a/0/1/7` item archive is byte-identical between those ROMs (791 records).
- ARM9 item attribute reader at `0x020764A8` extracts bits 11–15 of the halfword at item-record offset 8. Status-pocket flag is `0x08` after extraction, corresponding to record bit `0x4000`; standard status medicines lack it. Runtime menus corroborate the interpretation.
- DeSmuME 0.9.12 / py-desmume 0.0.9, existing `trainer.sav` fixture; inventories injected only into isolated emulator RAM through the native save-array getter for bag block 3. Each injected stack contains five items in the correct normal bag pocket.
- Mixed inventory: 50 item types on each ROM (IDs 17–44, 149–158, 54–61, 63, 65–67). Separate RC5 medicine-only run: IDs 17–44, 28 types. Corrected runs assert the full inventory injection completed.
- Mixed runs display two Status Healers pages with all seven status Berries and all three flutes. Medicine-only RC5 displays an empty Status Healers page while its HP/PP Restore pages still show eligible medicines.
- All three completed runs reported no heap corruption or text-copy rejections. This is a bounded trainer-battle menu check, not verification of every battle mode, acquisition path, item effect, or emulator.

Local ignored evidence: `work/build/status-healers-rc5/`. Use `en-mixed_*`, `cn-mixed_*`, and `en-medicine_*` screenshots and corresponding runtime JSON. Earlier `en_*`/`cn_*` exploratory images are not evidence for the final matrix. `runtime.py` reproduces the corrected test; logs and `item-audit.json` retain the supporting details.

## Release-note wording

Original-hack behavior: standard status medicines, Revives, Ethers and some stronger healing items are unavailable from the battle Bag. Status-healing Berries and colored flutes remain available; Heal Powder is listed under HP/PP Restore. The English patch preserves these restrictions.
