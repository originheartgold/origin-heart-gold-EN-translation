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
/** General-block chunks from the native save table (ARM9 0x020f30cc): [offset, size].
 * Each chunk is followed by a CRC16 slot and two padding bytes. Native saves keep
 * that inner CRC only for some chunks (Mystery Gift among them); the others hold
 * zero. Writers keep an inner CRC current only where it was already valid. */
export const GENERAL_CHUNKS: readonly (readonly [number, number])[] = [[0,0x5c],[0x60,0x2c],[0x90,0x5b0],[0x644,0x864],[0xeac,0x474],[0x1324,0x80],[0x13a8,0x370],[0x171c,0x1e0],[0x1900,0x880],[0x2184,0x2f8],[0x2480,0x1400],[0x3884,0x20],[0x38a8,0x834],[0x40e0,0x460],[0x4544,0x108],[0x4650,0x620],[0x4c74,0x1c0],[0x4e38,0x170],[0x4fac,0x3ec],[0x539c,0x1694],[0x6a34,0x10],[0x6a48,0x68],[0x6ab4,0xf8],[0x6bb0,0xbc8],[0x777c,0xea0],[0x8620,0x8c0],[0x8ee4,0xff8],[0x9ee0,0x1680],[0xb564,0x688],[0xbbf0,0x28],[0xbc1c,8],[0xbc28,0x40],[0xbc6c,8],[0xbc78,8],[0xbc84,0x658],[0xc2e0,0x5fc],[0xc8e0,0x1294],[0xdb78,0xb80],[0xe6fc,0x80],[0xe780,0x134],[0xe8b8,0xf00]];
/** PC storage (relative to the storage block): 24 boxes of 30 boxed records,
 * one 0x1000-byte stride per box, then box metadata. */
export const STORAGE_FOOTER = STORAGE_SIZE - FOOTER_SIZE;
export const STORAGE_CHUNK_SIZE = 0x183f4;
export const BOX_COUNT = 24;
export const BOX_CAPACITY = 30;
export const BOX_STRIDE = 0x1000;
/** Native per-box "modified" bits; the game sets a box's bit when it changes. */
export const BOX_MODIFIED_OFFSET = 0x18004;
export const BOX_NAMES_OFFSET = 0x18008;
export const BOX_NAME_STRIDE = 40;
export const BOX_WALLPAPERS_OFFSET = 0x183c8;
/** Player profile (general +0x64). Origin badge bytes: IDs 0–7 at +0x80, 8–15 at +0x83. */
export const TRAINER_NAME_OFFSET = 0x64;
export const TRAINER_TID_OFFSET = 0x74;
export const TRAINER_SID_OFFSET = 0x76;
export const TRAINER_GENDER_OFFSET = 0x7c;
export const TRAINER_LANGUAGE_OFFSET = 0x7d;
export const BADGES_OFFSET = 0x80;
export const BADGES_2_OFFSET = 0x83;
export const COINS_OFFSET = 0x84;
export const PLAY_TIME_OFFSET = 0x86;
/** Pokédex chunk: marker 0xBEEFCAFE, caught bits at +4, seen bits at +0xCC. */
export const DEX_OFFSET = 0x13a8;
export const DEX_MARKER = 0xbeefcafe;
export const DEX_MAX = 1025;
export const DEX_CAUGHT = 4;
export const DEX_SEEN = 0xcc;
/** Mystery Gift chunk: 2048 receipt bits, 8 pending gifts at +0x100 (stride 0x104),
 * 3 Wonder Cards at +0x920 (stride 0x358). */
export const MG_OFFSET = 0x9ee0;
export const MG_SIZE = 0x1680;
export const MG_GIFTS = 0x100;
export const MG_GIFT_STRIDE = 0x104;
export const MG_GIFT_COUNT = 8;
export const MG_CARDS = 0x920;
export const MG_CARD_SIZE = 0x358;
export const MG_CARD_COUNT = 3;
export const MG_RECEIPTS = 2048;
