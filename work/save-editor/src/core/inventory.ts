import { EditorError } from './errors.js';
import { readSave, patchGeneralRegion } from './save.js';

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
function integer(value: number, minimum: number, maximum: number, label: string): void {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) throw new EditorError('invalid-input', `${label} must be an integer from ${minimum} to ${maximum}.`);
}
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
  integer(money, 0, MONEY_MAX, 'Money');
  const bytes = new Uint8Array(4); new DataView(bytes.buffer).setUint32(0,money,true);
  return patchGeneralRegion(input, MONEY_OFFSET, bytes);
}
export function patchInventoryPocket(input: Uint8Array, pocketId: PocketId, items: readonly ItemStack[], data: InventoryData): Uint8Array {
  const pocket = POCKETS.find(p => p.id === pocketId);
  if (!pocket) throw new EditorError('invalid-input', 'Unknown inventory pocket.');
  if (!Array.isArray(items) || items.length > pocket.capacity) throw new EditorError('invalid-input', `${pocket.label} holds at most ${pocket.capacity} different items.`);
  if (!data || typeof data.getItem !== 'function') throw new EditorError('invalid-input', 'Reference data unavailable. Reload the editor before editing inventory.');
  const before = readInventory(input);
  const previousIds = new Set(before.pockets[pocket.id]!.map(item => item.id));
  // Native insertion sorts TMs/HMs and berries; quantity-only edits preserve order.
  const ordered = (pocket.nativeId === 3 || pocket.nativeId === 4) && items.some(item => item && !previousIds.has(item.id))
    ? [...items].sort((a,b) => a.id - b.id) : items;
  const seen = new Set<number>();
  const replacement = new Uint8Array(pocket.capacity * 4);
  const view = new DataView(replacement.buffer);
  Array.from(ordered).forEach((item, index) => {
    if (!item || typeof item !== 'object') throw new EditorError('invalid-input', 'Invalid item stack.');
    integer(item.id,1,790,'Item ID'); integer(item.quantity,1,pocket.maxQuantity,'Quantity');
    const metadata = data.getItem(item.id);
    if (!metadata || metadata.pocket !== pocket.id) throw new EditorError('invalid-input', `Item #${item.id} does not belong in ${pocket.label}.`, {kind: 'wrong-pocket', itemId: item.id, pocketLabel: pocket.label});
    if (seen.has(item.id)) throw new EditorError('invalid-input', `Item #${item.id} occurs more than once. Change its quantity instead.`, {kind: 'duplicate-item', itemId: item.id});
    seen.add(item.id);
    view.setUint16(index * 4,item.id,true); view.setUint16(index * 4 + 2,item.quantity,true);
  });
  // Exact no-op preserves unusual but harmless slot gaps rather than compacting.
  const existing = before.pockets[pocket.id]!;
  if (items.length === existing.length && items.every((item,index) => item.id === existing[index]!.id && item.quantity === existing[index]!.quantity)) return readSave(input).bytes;
  let result = patchGeneralRegion(input,pocket.offset,replacement);
  // Clear only shortcuts for items actually removed from this pocket.
  const removed = new Set(before.pockets[pocket.id]!.filter(item => !seen.has(item.id)).map(item => item.id));
  const registered = before.registeredItems.some(id => removed.has(id))
    ? before.registeredItems.filter(id => id && !removed.has(id)) : [...before.registeredItems];
  while (registered.length < 2) registered.push(0);
  if (registered.some((id,index) => id !== before.registeredItems[index])) {
    const bytes = new Uint8Array(4), shortcuts = new DataView(bytes.buffer);
    registered.forEach((id,index) => shortcuts.setUint16(index * 2,id,true));
    result = patchGeneralRegion(result,REGISTERED_OFFSET,bytes);
  }
  return result;
}

/** Fill available slots without removing existing items or touching key items. */
export function fillBag(input: Uint8Array, data: InventoryData): {bytes: Uint8Array; omitted: number} {
  let bytes = input, omitted = 0;
  const inventory = readInventory(input);
  for (const pocket of POCKETS) {
    if (pocket.id === 'keyItems') continue;
    const stacks = inventory.pockets[pocket.id].map(item => ({...item, quantity: pocket.maxQuantity}));
    const present = new Set(stacks.map(item => item.id));
    for (const item of data.items) {
      if (item.pocket !== pocket.id || !item.name || item.name.startsWith('Item #') || present.has(item.id)) continue;
      if (stacks.length >= pocket.capacity) { omitted++; continue; }
      stacks.push({id: item.id, quantity: pocket.maxQuantity}); present.add(item.id);
    }
    bytes = patchInventoryPocket(bytes, pocket.id, stacks, data);
  }
  return {bytes, omitted};
}
