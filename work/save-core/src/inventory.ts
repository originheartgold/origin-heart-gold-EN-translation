import { MONEY_OFFSET, REGISTERED_OFFSET, POCKETS } from './layout.js';
import { readSave } from './save.js';
import { applyEditorTransaction } from './transaction.js';
import type { EditorOperation } from './transaction.js';

export const MONEY_MAX = 9_999_999;
export { MONEY_OFFSET, BAG_OFFSET, REGISTERED_OFFSET, POCKETS } from './layout.js';
export type PocketId = typeof POCKETS[number]['id'];
export function isPocketId(value: string): value is PocketId { return POCKETS.some(p => p.id === value); }
export interface ItemStack { id: number; quantity: number }
export interface ItemMetadata { id: number; name: string; pocket: PocketId }
export interface InventoryData { readonly items: readonly ItemMetadata[]; getItem(id: number): ItemMetadata | undefined }
export interface Inventory { money: number; pockets: Record<PocketId, ItemStack[]>; registeredItems: number[] }
/** Inspection is permissive about existing item IDs and quantities; mutation
 * validates the selected pocket. Other pockets remain byte-for-byte untouched. */
export function readInventory(input: Uint8Array): Inventory {
  const save = readSave(input);
  const view = new DataView(save.bytes.buffer);
  const pockets: Record<PocketId, ItemStack[]> = {items: [], keyItems: [], tmHm: [], mail: [], medicine: [], berries: [], balls: [], battle: []};
  for (const pocket of POCKETS) {
    const entries: ItemStack[] = [];
    for (let i = 0; i < pocket.capacity; i++) {
      const offset = save.generalOffset + pocket.offset + 4 * i;
      const id = view.getUint16(offset, true), quantity = view.getUint16(offset + 2, true);
      if (id || quantity) entries.push({id, quantity});
    }
    pockets[pocket.id] = entries;
  }
  return {money:view.getUint32(save.generalOffset + MONEY_OFFSET, true), pockets,
    registeredItems:[view.getUint16(save.generalOffset + REGISTERED_OFFSET,true),view.getUint16(save.generalOffset + REGISTERED_OFFSET + 2,true)]};
}
export function patchMoney(input: Uint8Array, money: number): Uint8Array {
  return applyEditorTransaction(input,[{type:'setMoney',money}]).bytes;
}
export function patchInventoryPocket(input: Uint8Array, pocketId: PocketId, items: readonly ItemStack[], data: InventoryData): Uint8Array {
  return applyEditorTransaction(input,[{type:'replacePocket',pocket:pocketId,items,data}]).bytes;
}

/** Fill available slots without removing existing items or touching key items.
 * One transaction: all pockets change together or not at all. */
export function fillBag(input: Uint8Array, data: InventoryData): {bytes: Uint8Array; omitted: number} {
  let omitted = 0;
  const inventory = readInventory(input), operations: EditorOperation[] = [];
  for (const pocket of POCKETS) {
    if (pocket.id === 'keyItems') continue;
    const stacks = inventory.pockets[pocket.id].map(item => ({...item, quantity: pocket.maxQuantity}));
    const present = new Set(stacks.map(item => item.id));
    for (const item of data.items) {
      if (item.pocket !== pocket.id || !item.name || item.name.startsWith('Item #') || present.has(item.id)) continue;
      if (stacks.length >= pocket.capacity) { omitted++; continue; }
      stacks.push({id: item.id, quantity: pocket.maxQuantity}); present.add(item.id);
    }
    operations.push({type: 'replacePocket', pocket: pocket.id, items: stacks, data});
  }
  return {bytes: applyEditorTransaction(input, operations).bytes, omitted};
}
