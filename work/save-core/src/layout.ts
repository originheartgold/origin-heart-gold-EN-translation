/** Origin v4.0.3 save layout. Every offset is relative to its general block,
 * except the outer container/mirror/storage constants. Keep independent test
 * oracles literal so layout changes cannot silently rewrite their expectations. */
export const SAVE_SIZE = 0x80000;
export const MIRROR_OFFSET = 0x40000;
export const GENERAL_SIZE = 0xf7cc;
export const STORAGE_OFFSET = 0xf800;
export const STORAGE_SIZE = 0x18408;
export const FOOTER_SIZE = 16;
export const GENERAL_FOOTER = GENERAL_SIZE - FOOTER_SIZE;
export const PARTY_CAPACITY_OFFSET = 0x90;
export const PARTY_COUNT_OFFSET = 0x94;
export const PARTY_OFFSET = 0x98;
export const PARTY_STRIDE = 236;
export const BOXED_SIZE = 136;
export const FLAGS_OFFSET = 0x118c;
export const VARS_OFFSET = 0xeac;
/** Native GetFlagAddr bounds: 0x194 bytes; following padding is not flags. */
export const SAVED_FLAG_COUNT = 0xca0;
export const SAVED_VAR_BASE = 0x4000;
export const SAVED_VAR_COUNT = 0x170;
export const LOCATION_OFFSET = 0x1324;
export const LOCATION_STRIDE = 20;
export const LOCATION_COUNT = 5;
export const OBJECTS_OFFSET = 0x2480;
export const OBJECT_STRIDE = 80;
export const OBJECT_COUNT = 64;
export const MONEY_OFFSET = 0x78;
export const BAG_OFFSET = 0x644;
export const REGISTERED_OFFSET = 0xea4;
export const POCKET_NAMES = ['items','key','tm','mail','medicine','berries','balls','battle'] as const;
export const POCKETS = Object.freeze(([
  {id:'items', label:'Items', offset:BAG_OFFSET, capacity:165, maxQuantity:999, nativeId:0},
  {id:'keyItems', label:'Key items', offset:0x8d8, capacity:50, maxQuantity:999, nativeId:7},
  {id:'tmHm', label:'TMs & HMs', offset:0x9a0, capacity:151, maxQuantity:99, nativeId:3},
  {id:'mail', label:'Mail', offset:0xbfc, capacity:12, maxQuantity:999, nativeId:5},
  {id:'medicine', label:'Medicine', offset:0xc2c, capacity:40, maxQuantity:999, nativeId:1},
  {id:'berries', label:'Berries', offset:0xccc, capacity:64, maxQuantity:999, nativeId:4},
  {id:'balls', label:'Poké Balls', offset:0xdcc, capacity:24, maxQuantity:999, nativeId:2},
  {id:'battle', label:'Battle items', offset:0xe2c, capacity:30, maxQuantity:999, nativeId:6},
] as const).map(p => Object.freeze(p)));
