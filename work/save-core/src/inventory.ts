import { readSave } from './save.js';
import { applyEditorTransaction } from './transaction.js';

export const MONEY_MAX = 9_999_999;
export const MONEY_OFFSET = 0x78;
export const BAG_OFFSET = 0x644;
export const REGISTERED_OFFSET = 0xea4;
export const POCKETS = Object.freeze(([
  {id:'items', label:'Items', offset:0x644, capacity:165, maxQuantity:999, nativeId:0},
  {id:'keyItems', label:'Key items', offset:0x8d8, capacity:50, maxQuantity:999, nativeId:7},
  {id:'tmHm', label:'TMs & HMs', offset:0x9a0, capacity:151, maxQuantity:99, nativeId:3},
  {id:'mail', label:'Mail', offset:0xbfc, capacity:12, maxQuantity:999, nativeId:5},
  {id:'medicine', label:'Medicine', offset:0xc2c, capacity:40, maxQuantity:999, nativeId:1},
  {id:'berries', label:'Berries', offset:0xccc, capacity:64, maxQuantity:999, nativeId:4},
  {id:'balls', label:'Poké Balls', offset:0xdcc, capacity:24, maxQuantity:999, nativeId:2},
  {id:'battle', label:'Battle items', offset:0xe2c, capacity:30, maxQuantity:999, nativeId:6},
] as const).map(p => Object.freeze(p)));
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
