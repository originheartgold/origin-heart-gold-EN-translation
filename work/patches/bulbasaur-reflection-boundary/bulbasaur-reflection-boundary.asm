; bulbasaur-reflection-boundary - Following Pokemon: Bulbasaur's reflection in water no longer reads a NULL
; graphics pointer (black screen / freeze over water). D-2270 (user-approved exception to D-1337).
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md;
; work/notes/bulbasaur_reflection_fix.md.
;
; ReflectionGfx_Get (overlay 1, 0x021F61E8) returns the graphics object a map object's water reflection
; draws with. Its two callers, the reflection callbacks (bl at 0x021FCC88 and 0x021FD19A), pass the result
; straight to the graphics getters 0x0202451C / 0x02024558 without a NULL check; those assert (the handler
; returns in this build) and then read address 0xB6 / 0xB8.
; It reads the object's sprite id (0x0205E3D8: [object+0x10]); a few listed ids (0, 0x15, 0x61, 0x62, 0xB0,
; 0xB1-0xC9 by table, 0xF8, 0xF9, 0x102-0x106) take the generic field [object+0x10C]; every other id goes to
; ReflectionGfx_FollowerRange: 428..1894 (0x766), the following Pokemon, take the follower's own graphics
; pointer [object+0x108] (0x0205E588 returns object + 0x42 * 4); 0x106..0x10D a special case (0x0206323C);
; the rest the generic field. The lower bound is 'ble' after 'cmp r0, #428', so 428 itself, Bulbasaur, the
; first follower sprite, is left out and reads the generic field, which is NULL for a follower.
;
; The fix makes that bound 'blt' (07 DD -> 07 DB, one byte): the same target, taken for ids < 428 instead
; of <= 428. A signed ble and blt differ only when the two values are equal, so 428 is the only id whose
; path changes; it now reads [object+0x108] like every other follower. The guards below check the code
; 428 runs through: the entry, the dispatch for ids > 0xF8, the range check, both loads and the literals.

.nds
.thumb
.include "../include/guards.inc"

.definelabel ReflectionGfx_Get,            0x021F61E8   ; r0 = map object -> graphics object
.definelabel ReflectionGfx_Above0xF8,      0x021F6262   ; dispatch of sprite ids > 0xF8
.definelabel ReflectionGfx_FollowerRange,  0x021F6294   ; ids not listed: 428..1894 are followers
.definelabel ReflectionGfx_LowerBound,     0x021F629A   ; ble: id <= 428 is not a follower  <- the edit
.definelabel ReflectionGfx_NotFollower,    0x021F62AC   ; special case 0x106..0x10D, else generic field
.definelabel MapObject_GetSpriteId,        0x0205E3D8   ; arm9: [object+0x10]
.definelabel MapObject_GetGfxFields,       0x0205E588   ; arm9: object + 0x108

.open "overlay1.bin", 0x021E4980

; Read-only guards: the code a sprite id > 0xF8 runs through (nothing is written here).
.org ReflectionGfx_Get
    expect16_at 0x00, 0xB510    ; push  {r4, lr}
    expect16_at 0x02, 0x1C04    ; add   r4, r0, #0              r4 = map object
    expect16_at 0x04, 0xF668    ; bl    MapObject_GetSpriteId  (1/2)
    expect16_at 0x06, 0xF8F4    ;                               (2/2)   r0 = sprite id
    expect16_at 0x08, 0x28F8    ; cmp   r0, #0xF8
    expect16_at 0x0A, 0xDC36    ; bgt   ReflectionGfx_Above0xF8

.org ReflectionGfx_Above0xF8
    expect16_at 0x00, 0x4A1A    ; ldr   r2, =0x103
    expect16_at 0x02, 0x4290    ; cmp   r0, r2
    expect16_at 0x04, 0xDC08    ; bgt   0x021F627A
    expect16_at 0x06, 0xDA0F    ; bge   0x021F628A              0x103: generic field
    expect16_at 0x08, 0x28F9    ; cmp   r0, #0xF9
    expect16_at 0x0A, 0xDC01    ; bgt   0x021F6272
    expect16_at 0x0C, 0xD00C    ; beq   0x021F628A              0xF9: generic field
    expect16_at 0x0E, 0xE010    ; b     ReflectionGfx_FollowerRange
    expect16_at 0x10, 0x1E51    ; sub   r1, r2, #1
    expect16_at 0x12, 0x4288    ; cmp   r0, r1
    expect16_at 0x14, 0xD008    ; beq   0x021F628A              0x102: generic field
    expect16_at 0x16, 0xE00C    ; b     ReflectionGfx_FollowerRange
    expect16_at 0x18, 0x1C51    ; add   r1, r2, #1              0x021F627A
    expect16_at 0x1A, 0x4288    ; cmp   r0, r1
    expect16_at 0x1C, 0xDC01    ; bgt   0x021F6284
    expect16_at 0x1E, 0xD003    ; beq   0x021F628A              0x104: generic field
    expect16_at 0x20, 0xE007    ; b     ReflectionGfx_FollowerRange
    expect16_at 0x22, 0x1C91    ; add   r1, r2, #2              0x021F6284
    expect16_at 0x24, 0x4288    ; cmp   r0, r1
    expect16_at 0x26, 0xD104    ; bne   ReflectionGfx_FollowerRange   (428 goes here)
    expect16_at 0x28, 0x1C20    ; add   r0, r4, #0              0x021F628A: listed ids
    expect16_at 0x2A, 0xF668    ; bl    MapObject_GetGfxFields  (1/2)
    expect16_at 0x2C, 0xF97C    ;                               (2/2)
    expect16_at 0x2E, 0x6840    ; ldr   r0, [r0, #4]            generic field [object+0x10C]
    expect16_at 0x30, 0xBD10    ; pop   {r4, pc}
    expect16_at 0x32, 0x216B    ; mov   r1, #0x6B               ReflectionGfx_FollowerRange
    expect16_at 0x34, 0x0089    ; lsl   r1, r1, #2              r1 = 428
    expect16_at 0x36, 0x4288    ; cmp   r0, r1
    expect16_at 0x38, 0xDD07    ; ble   ReflectionGfx_NotFollower       <- the edit below
    expect16_at 0x3A, 0x490C    ; ldr   r1, =0x766              1894
    expect16_at 0x3C, 0x4288    ; cmp   r0, r1
    expect16_at 0x3E, 0xDC04    ; bgt   ReflectionGfx_NotFollower
    expect16_at 0x40, 0x1C20    ; add   r0, r4, #0
    expect16_at 0x42, 0xF668    ; bl    MapObject_GetGfxFields  (1/2)
    expect16_at 0x44, 0xF970    ;                               (2/2)
    expect16_at 0x46, 0x6800    ; ldr   r0, [r0]                follower graphics [object+0x108]
    expect16_at 0x48, 0xBD10    ; pop   {r4, pc}
    expect16_at 0x4A, 0x4909    ; ldr   r1, =0x106              ReflectionGfx_NotFollower
    expect16_at 0x4C, 0x4288    ; cmp   r0, r1
    expect16_at 0x4E, 0xDB06    ; blt   0x021F62C0
    expect16_at 0x50, 0x1DC9    ; add   r1, r1, #7
    expect16_at 0x52, 0x4288    ; cmp   r0, r1
    expect16_at 0x54, 0xDC03    ; bgt   0x021F62C0
    expect16_at 0x56, 0x1C20    ; add   r0, r4, #0              0x106..0x10D
    expect16_at 0x58, 0xF66C    ; bl    0x0206323C              (1/2)
    expect16_at 0x5A, 0xFFBF    ;                               (2/2)
    expect16_at 0x5C, 0xBD10    ; pop   {r4, pc}
    expect16_at 0x5E, 0x1C20    ; add   r0, r4, #0              0x021F62C0
    expect16_at 0x60, 0xF668    ; bl    MapObject_GetGfxFields  (1/2)
    expect16_at 0x62, 0xF961    ;                               (2/2)
    expect16_at 0x64, 0x6840    ; ldr   r0, [r0, #4]            generic field [object+0x10C]: NULL for a follower
    expect16_at 0x66, 0xBD10    ; pop   {r4, pc}
    expect16_at 0x68, 0x46C0    ; nop                           (padding)
    expect32_at 0x6A, 0x00000103    ; literal pool
    expect32_at 0x6E, 0x00000766
    expect32_at 0x72, 0x00000106

; The edit: 428 (Bulbasaur) is inside the follower range, like 429..1894.
.org ReflectionGfx_LowerBound
.area 2
    expect16 0xDD07             ; ble ReflectionGfx_NotFollower
    blt     ReflectionGfx_NotFollower
.endarea

.close
