import { MONEY_OFFSET, REGISTERED_OFFSET, POCKETS } from './layout.js';
import { readSave } from './save.js';
import { applyEditorTransaction } from './transaction.js';

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
