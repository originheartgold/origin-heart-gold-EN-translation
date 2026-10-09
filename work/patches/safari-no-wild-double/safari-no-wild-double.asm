; safari-no-wild-double - Safari Zone: a wild encounter is always a single battle (no frozen double battle
; with a junk second opponent). D-2289 (user-approved exception to D-1337; answers the hack finding D-1535).
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md; work/notes/safari-double_fix.md.
;
; The walk/surf wild encounter (overlay 2, 0x02246F6C) picks the battle setup at 0x0224710A. The hack added a
; random double battle in front of it (0x022470C4): rand % 4 == 0, at least two Pokemon that can fight
; (arm9 0x02053570) and [sp+0x25] == 0 set [sp+0x10]. The setup choice then runs
;   r1 = 1 when the Safari Zone flag is set ([sp+0x1C], sys flag 0x967),
;        2 when the Bug-Catching Contest flag is set ([sp+0x18], sys flag 0x996), else 0;
;   if [sp+0x10]: BattleSetup_New(11, 0x4A), a double battle setup, whatever r1 says;
;   else: Encounter_NewSetup (0x022486C4) -> the Safari (r1 1), Contest (r1 2) or normal (r1 0) setup.
; After that the Safari and Contest paths create ONE wild Pokemon (0x02247790 / 0x022477AC -> 0x02248204);
; only the normal path creates two for a double (0x02247F24 twice). So with two usable Pokemon one Safari
; encounter in four is a double battle with an uninitialised second opponent, and the game
; freezes at the command menu.
;
; The Bug-Catching Contest takes the same path but is not affected: the contest leaves one Pokemon in the party
; (BugContestAction 0), so the double needs two that can fight and is never rolled there (checked in the emulator:
; work/notes/safari-double_fix.md). It is left exactly as the hack has it.
;
; The fix: the Safari check branches straight to Encounter_NewSetup with r1 = 1 before the double flag is read;
; every other encounter (Contest r1 = 2, others r1 = 0) reaches the double check exactly as before, so the hack's
; random wild doubles elsewhere are unchanged. Same 20 bytes, same registers.

.nds
.thumb
.include "../include/guards.inc"

.definelabel Encounter_Roll,           0x022470C4   ; [sp+0x10] = random double (the hack's)
.definelabel Encounter_Kind,           0x0224710A   ; r1 = 1 Safari, 2 Contest, 0 other  <- the edit
.definelabel Encounter_DoubleCheck,    0x0224711E   ; if [sp+0x10]: double setup
.definelabel Encounter_SingleSetup,    0x02247130   ; Encounter_NewSetup(r0 field, r1 kind, r2 &setup)
.definelabel Encounter_SetupDone,      0x02247144
.definelabel Encounter_CreateSafari,   0x0224717C   ; one wild Pokemon (0x02247790)
.definelabel Encounter_NewSetup,       0x022486C4

.open "overlay2.bin", 0x02245F40

; Read-only guards (nothing is written here): the double roll, the setup branches after the edit, and the
; Safari / Contest creation, which builds one wild Pokemon.
.org Encounter_Roll
    expect16_at 0x00, 0x2000    ; mov   r0, #0
    expect16_at 0x02, 0x9004    ; str   r0, [sp, #0x10]         no double
    expect16_at 0x04, 0xF5D9    ; bl    rand  0x02020480       (1/2)
    expect16_at 0x06, 0xF9DA    ;                               (2/2)
    expect16_at 0x08, 0x0FC1    ; lsr   r1, r0, #31
    expect16_at 0x0A, 0x0782    ; lsl   r2, r0, #30
    expect16_at 0x0C, 0x1A52    ; sub   r2, r2, r1
    expect16_at 0x0E, 0x201E    ; mov   r0, #30
    expect16_at 0x10, 0x41C2    ; ror   r2, r0
    expect16_at 0x12, 0x1888    ; add   r0, r1, r2              rand % 4
    expect16_at 0x14, 0xD10A    ; bne   0x022470F0
    expect16_at 0x16, 0x9805    ; ldr   r0, [sp, #0x14]
    expect16_at 0x18, 0xF60C    ; bl    0x02053570              (1/2)  two Pokemon can fight
    expect16_at 0x1A, 0xFA48    ;                               (2/2)
    expect16_at 0x1C, 0x2800    ; cmp   r0, #0
    expect16_at 0x1E, 0xD005    ; beq   0x022470F0
    expect16_at 0x20, 0xA809    ; add   r0, sp, #0x24
    expect16_at 0x22, 0x7840    ; ldrb  r0, [r0, #1]
    expect16_at 0x24, 0x2800    ; cmp   r0, #0
    expect16_at 0x26, 0xD101    ; bne   0x022470F0
    expect16_at 0x28, 0x2001    ; mov   r0, #1
    expect16_at 0x2A, 0x9004    ; str   r0, [sp, #0x10]         random double
    expect16_at 0x2C, 0x68E8    ; ldr   r0, [r5, #0xC]          0x022470F0
    expect16_at 0x2E, 0xF608    ; bl    0x0204F858              (1/2)
    expect16_at 0x30, 0xFBB1    ;                               (2/2)
    expect16_at 0x32, 0x9008    ; str   r0, [sp, #0x20]
    expect16_at 0x34, 0xF61E    ; bl    0x02065B08              (1/2)  flag 0x967: Safari Zone
    expect16_at 0x36, 0xFD06    ;                               (2/2)
    expect16_at 0x38, 0x9007    ; str   r0, [sp, #0x1C]
    expect16_at 0x3A, 0x9808    ; ldr   r0, [sp, #0x20]
    expect16_at 0x3C, 0xF61E    ; bl    0x02065B18              (1/2)  flag 0x996: Bug-Catching Contest
    expect16_at 0x3E, 0xFD0A    ;                               (2/2)
    expect16_at 0x40, 0x9006    ; str   r0, [sp, #0x18]
    expect16_at 0x42, 0x2F00    ; cmp   r7, #0                  partner following: always double
    expect16_at 0x44, 0xD117    ; bne   0x0224713A

.org Encounter_DoubleCheck
    expect16_at 0x00, 0x9804    ; ldr   r0, [sp, #0x10]
    expect16_at 0x02, 0x2800    ; cmp   r0, #0
    expect16_at 0x04, 0xD005    ; beq   Encounter_SingleSetup
    expect16_at 0x06, 0x200B    ; mov   r0, #11
    expect16_at 0x08, 0x214A    ; mov   r1, #0x4A               double battle setup
    expect16_at 0x0A, 0xF609    ; bl    BattleSetup_New 0x02050C34 (1/2)
    expect16_at 0x0C, 0xFD84    ;                               (2/2)
    expect16_at 0x0E, 0x900B    ; str   r0, [sp, #0x2C]
    expect16_at 0x10, 0xE009    ; b     Encounter_SetupDone
    expect16_at 0x12, 0x1C28    ; add   r0, r5, #0              Encounter_SingleSetup
    expect16_at 0x14, 0xAA0B    ; add   r2, sp, #0x2C
    expect16_at 0x16, 0xF001    ; bl    Encounter_NewSetup      (1/2)
    expect16_at 0x18, 0xFAC6    ;                               (2/2)
    expect16_at 0x1A, 0xE004    ; b     Encounter_SetupDone

.org Encounter_CreateSafari
    expect16_at 0x00, 0xA813    ; add   r0, sp, #0x4C
    expect16_at 0x02, 0x9000    ; str   r0, [sp]
    expect16_at 0x04, 0xA80C    ; add   r0, sp, #0x30
    expect16_at 0x06, 0x9001    ; str   r0, [sp, #4]
    expect16_at 0x08, 0x9A0B    ; ldr   r2, [sp, #0x2C]
    expect16_at 0x0A, 0x1C28    ; add   r0, r5, #0
    expect16_at 0x0C, 0x1C31    ; add   r1, r6, #0
    expect16_at 0x0E, 0x1C23    ; add   r3, r4, #0
    expect16_at 0x10, 0xF000    ; bl    0x02247790              (1/2)  Safari: one wild Pokemon
    expect16_at 0x12, 0xFB00    ;                               (2/2)
    expect16_at 0x14, 0xE079    ; b     0x02247286
    expect16_at 0x16, 0x9806    ; ldr   r0, [sp, #0x18]
    expect16_at 0x18, 0x2800    ; cmp   r0, #0
    expect16_at 0x1A, 0xD00A    ; beq   0x022471AE              (not the Contest: normal, maybe two)
    expect16_at 0x1C, 0xA813    ; add   r0, sp, #0x4C
    expect16_at 0x1E, 0x9000    ; str   r0, [sp]
    expect16_at 0x20, 0xA80C    ; add   r0, sp, #0x30
    expect16_at 0x22, 0x9001    ; str   r0, [sp, #4]
    expect16_at 0x24, 0x9A0B    ; ldr   r2, [sp, #0x2C]
    expect16_at 0x26, 0x1C28    ; add   r0, r5, #0
    expect16_at 0x28, 0x1C31    ; add   r1, r6, #0
    expect16_at 0x2A, 0x1C23    ; add   r3, r4, #0
    expect16_at 0x2C, 0xF000    ; bl    0x022477AC              (1/2)  Contest: one wild Pokemon
    expect16_at 0x2E, 0xFB00    ;                               (2/2)

; The edit: the Safari Zone goes to its own single setup before the double flag is read. The Contest and every
; other encounter set r1 as before (2 / 0) and reach the double check unchanged.
.org Encounter_Kind
.area 20
    expect16_at 0x00, 0x9807    ; ldr   r0, [sp, #0x1C]
    expect16_at 0x02, 0x2100    ; mov   r1, #0
    expect16_at 0x04, 0x2800    ; cmp   r0, #0
    expect16_at 0x06, 0xD001    ; beq   0x02247116
    expect16_at 0x08, 0x2101    ; mov   r1, #1
    expect16_at 0x0A, 0xE003    ; b     Encounter_DoubleCheck
    expect16_at 0x0C, 0x9806    ; ldr   r0, [sp, #0x18]
    expect16_at 0x0E, 0x2800    ; cmp   r0, #0
    expect16_at 0x10, 0xD000    ; beq   Encounter_DoubleCheck
    expect16_at 0x12, 0x2102    ; mov   r1, #2
    ldr     r0, [sp, #0x1C]     ; Safari Zone?
    mov     r1, #1
    cmp     r0, #0
    bne     Encounter_SingleSetup
    mov     r1, #0
    ldr     r0, [sp, #0x18]     ; Bug-Catching Contest?
    cmp     r0, #0
    beq     Encounter_DoubleCheck
    mov     r1, #2
    nop
.endarea

.close
