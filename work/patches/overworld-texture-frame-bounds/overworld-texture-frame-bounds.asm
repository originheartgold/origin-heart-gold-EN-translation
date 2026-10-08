; overworld-texture-frame-bounds - Overworld objects: a texture frame the texture does not have no longer
; crashes (Rocket HQ freeze). D-2043 (open, main checkout's register). The user requested this fix on
; 2026-10-08; the exception to D-1337 is not yet recorded in the register (D-2043 still says 'preserve
; under D-1337'), and the user must record it before release.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md;
; work/notes/rocket_hq_freeze_fix_20261008.md.
;
; ObjTexAnim_Apply (0x02024604) runs every frame for an overworld object with a texture animation: it gets
; the current frame (texture number, palette number) from 0x02027254 and calls
;   ObjTex_SetTexture(model r0, texture block r1, texture number r2)   0x02024654
;   ObjTex_SetPalette(model r0, texture block r1, palette number r2)   0x02024758
; ObjTex_SetTexture looks the texture up in the TEX0 block's texture dictionary (at +0x3C: u8 revision,
; u8 count, ..., u16 entry offset at +6) and binds it to every material of the model that uses it.
; It does check the number against the dictionary's count, but the out-of-range branch goes to the same
; 'no texture' path as a NULL block, r0 = 0, and the unconditional 'ldr r0, [r0]' after it reads address 0:
; a data abort on melonDS 1.1 (hardware presumably too, untested; DeSmuME reads it and goes on). Objects
; whose animation has more frames than their texture has textures hit it: the Rocket HQ B1F barrier (one
; texture, frames up to 15) asks for frame 4; Five Island 4, Seven Island 11; Bell Tower 15 only in a forced
; state (hide flag 1140 cleared), not shown to be reachable in normal play.
;
; The fix sends that branch to the routine's own return instead: an out-of-range frame keeps the texture
; that is already bound, a valid one takes the old path. Safe because everything before the branch only
; reads (no store, no call), the return 'pop {r3-r7, pc}' matches the routine's 'push {r3-r7, lr}', and
; the caller ignores the return value. The NULL-pointer paths (no model, no texture block) stay as they are.

.nds
.thumb
.include "../include/guards.inc"

.definelabel ObjTexAnim_Apply,              0x02024604  ; caller: texture, then palette
.definelabel ObjTex_SetTexture,             0x02024654
.definelabel ObjTex_SetTexture_BoundsCheck, 0x0202467C  ; bhs: frame >= texture count
.definelabel ObjTex_SetTexture_NoTexture,   0x02024690  ; r0 = NULL
.definelabel ObjTex_SetTexture_Load,        0x02024696  ; ldr r0, [r0]: the crash
.definelabel ObjTex_SetTexture_Return,      0x020246D8  ; pop {r3-r7, pc}
.definelabel ObjTex_SetPalette,             0x02024758

.open "arm9.bin", 0x02000000

; Read-only guard: the whole routine is still the hack's (nothing is written here). The edit relies on the
; reads-only prefix, the branch's two targets and the matching push/pop, so all of it is checked.
.org ObjTex_SetTexture
    expect16_at 0x00, 0xB5F8    ; push  {r3-r7, lr}
    expect16_at 0x02, 0x2800    ; cmp   r0, #0                  model
    expect16_at 0x04, 0xD004    ; beq   0x02024664
    expect16_at 0x06, 0x6883    ; ldr   r3, [r0, #8]
    expect16_at 0x08, 0x2B00    ; cmp   r3, #0
    expect16_at 0x0A, 0xD001    ; beq   0x02024664
    expect16_at 0x0C, 0x18C6    ; add   r6, r0, r3              r6 = model block
    expect16_at 0x0E, 0xE000    ; b     0x02024666
    expect16_at 0x10, 0x2600    ; mov   r6, #0
    expect16_at 0x12, 0x8830    ; ldrh  r0, [r6]
    expect16_at 0x14, 0x1834    ; add   r4, r6, r0              r4 = material list
    expect16_at 0x16, 0x2900    ; cmp   r1, #0                  texture block
    expect16_at 0x18, 0xD012    ; beq   0x02024694              (NULL block: r0 = 0, also crashes; not fixed)
    expect16_at 0x1A, 0x1C08    ; add   r0, r1, #0
    expect16_at 0x1C, 0x303C    ; add   r0, #0x3C               r0 = texture dictionary
    expect16_at 0x1E, 0xD00D    ; beq   ObjTex_SetTexture_NoTexture
    expect16_at 0x20, 0x1C0B    ; add   r3, r1, #0
    expect16_at 0x22, 0x333D    ; add   r3, #0x3D
    expect16_at 0x24, 0x781B    ; ldrb  r3, [r3]                r3 = texture count
    expect16_at 0x26, 0x429A    ; cmp   r2, r3
    expect16_at 0x28, 0xD208    ; bhs   ObjTex_SetTexture_NoTexture         <- the edit below
    expect16_at 0x2A, 0x3142    ; add   r1, #0x42
    expect16_at 0x2C, 0x8809    ; ldrh  r1, [r1]                entry offset
    expect16_at 0x2E, 0x1843    ; add   r3, r0, r1
    expect16_at 0x30, 0x5A40    ; ldrh  r0, [r0, r1]            entry size
    expect16_at 0x32, 0x1D1B    ; add   r3, r3, #4
    expect16_at 0x34, 0x1C01    ; add   r1, r0, #0
    expect16_at 0x36, 0x4351    ; mul   r1, r2
    expect16_at 0x38, 0x1858    ; add   r0, r3, r1              r0 = &entry[frame]
    expect16_at 0x3A, 0xE002    ; b     ObjTex_SetTexture_Load
    expect16_at 0x3C, 0x2000    ; mov   r0, #0                  ObjTex_SetTexture_NoTexture
    expect16_at 0x3E, 0xE000    ; b     ObjTex_SetTexture_Load
    expect16_at 0x40, 0x2000    ; mov   r0, #0
    expect16_at 0x42, 0x6800    ; ldr   r0, [r0]                ObjTex_SetTexture_Load: the data abort
    expect16_at 0x44, 0x2500    ; mov   r5, #0
    expect16_at 0x46, 0x0400    ; lsl   r0, r0, #16
    expect16_at 0x48, 0x0C07    ; lsr   r7, r0, #16             r7 = texture parameters
    expect16_at 0x4A, 0x7860    ; ldrb  r0, [r4, #1]            material count
    expect16_at 0x4C, 0x2800    ; cmp   r0, #0
    expect16_at 0x4E, 0xDD19    ; ble   ObjTex_SetTexture_Return
    expect16_at 0x50, 0x2C00    ; cmp   r4, #0                  loop over the materials
    expect16_at 0x52, 0xD00A    ; beq   0x020246BE
    expect16_at 0x54, 0x7860    ; ldrb  r0, [r4, #1]
    expect16_at 0x56, 0x4285    ; cmp   r5, r0
    expect16_at 0x58, 0xD207    ; bhs   0x020246BE
    expect16_at 0x5A, 0x88E0    ; ldrh  r0, [r4, #6]
    expect16_at 0x5C, 0x1821    ; add   r1, r4, r0
    expect16_at 0x5E, 0x5A20    ; ldrh  r0, [r4, r0]
    expect16_at 0x60, 0x1D0A    ; add   r2, r1, #4
    expect16_at 0x62, 0x1C01    ; add   r1, r0, #0
    expect16_at 0x64, 0x4369    ; mul   r1, r5
    expect16_at 0x66, 0x1851    ; add   r1, r2, r1
    expect16_at 0x68, 0xE000    ; b     0x020246C0
    expect16_at 0x6A, 0x2100    ; mov   r1, #0
    expect16_at 0x6C, 0x78CA    ; ldrb  r2, [r1, #3]
    expect16_at 0x6E, 0x2001    ; mov   r0, #1
    expect16_at 0x70, 0x4210    ; tst   r0, r2                  material uses this texture?
    expect16_at 0x72, 0xD003    ; beq   0x020246D0
    expect16_at 0x74, 0x1C30    ; add   r0, r6, #0
    expect16_at 0x76, 0x1C3A    ; add   r2, r7, #0
    expect16_at 0x78, 0xF000    ; bl    0x020246DC              bind (1/2)
    expect16_at 0x7A, 0xF806    ;                               bind (2/2)
    expect16_at 0x7C, 0x7860    ; ldrb  r0, [r4, #1]
    expect16_at 0x7E, 0x1C6D    ; add   r5, r5, #1
    expect16_at 0x80, 0x4285    ; cmp   r5, r0
    expect16_at 0x82, 0xDBE5    ; blt   0x020246A4
    expect16_at 0x84, 0xBDF8    ; pop   {r3-r7, pc}             ObjTex_SetTexture_Return

; The edit: frame >= texture count returns, keeping the texture already bound.
.org ObjTex_SetTexture_BoundsCheck
.area 2
    expect16 0xD208             ; bhs ObjTex_SetTexture_NoTexture
    bhs     ObjTex_SetTexture_Return
.endarea

.close
