; battle-message-references - battle messages that named the wrong Pokemon (or printed the error marker):
; Nature Power's 'turned into' line and the per-turn infatuation line. D-2278 (user-approved exception to D-1337;
; resolves the hack finding D-2277).
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md; work/notes/battle-text-chinese_fix.md.
;
; The hack builds most battle messages as a message record (MsgRec_Init 0x02225DC0: record, type, message id;
; MsgRec_AddArg 0x02225DEC: one argument). Type 1 prints battle_string bank 2 (plain lines, the arguments are the
; template's buffers); type 2 prints bank 1 (own / wild / foe / trainer variants, chosen from a battler, the
; arguments again the buffers). A Pokemon-name buffer (tags 0x0101 / 0x0102) needs a Pokemon reference 1..25
; (1-6 the player's party, 13-18 the foe's, ...); anything else prints the error marker (see
; battle-message-error-marker) and the name of reference 1, the player's first party Pokemon.
;
; 1. Nature Power (NaturePower_ShowCalledMove 0x0223F070): the record is MsgRec_Init(rec, 2, 120) plus the called
;    move (battle var 0x29). Message 120 with one move argument is bank 2's 'Nature Power turned into {move}!'
;    (2#120); type 2 printed bank 1's 120, '{Pokemon}'s accuracy rose drastically!', with the move id as the
;    Pokemon reference (Earthquake 89 on Route 24). The fix: type 1.
; 2. Infatuation, every turn the infatuated Pokemon tries to move (Turn_CheckInfatuation 0x0221DAEC): it emits
;    1#452 '{1}让{0}着迷了' / 'The foe's {0} fell in love with {1}!' with the arguments (condition 7's data,
;    self). Condition 7's data field (0x02216D4C) is always 0 for infatuation; the Pokemon it is in love with is
;    the condition's source, word 0 of its 8-byte entry (Pokemon + 0x38 + 7 * 8 = + 0x70: observed 0x0D for a wild
;    attracter, 0x01 for the player's). And {0} is the infatuated Pokemon (the variant is chosen from it), {1}
;    the attracter, so the two arguments were also swapped. The fix: r4 = the source's low byte, then
;    (self, source).

.nds
.thumb
.include "../include/guards.inc"

.definelabel NaturePower_ShowCalledMove,  0x0223F070   ; battle event: Nature Power picked its move
.definelabel NaturePower_RecordType,      0x0223F084   ; movs r1, #2 (record type)  <- 1
.definelabel Turn_CheckInfatuation,       0x0221DAEC   ; condition 7 (infatuation) before the Pokemon moves
.definelabel Infatuation_ReadData,        0x0221DAFC   ; bl Condition_GetData(mon, 7)  <- ldr the source
.definelabel Infatuation_StoreArgs,       0x0221DB20   ; str r4, [sp] / str r0, [sp, #4]  <- swapped
.definelabel Condition_GetData,           0x02216D4C   ; (mon, condition) -> the entry's data field
.definelabel Mon_GetRef,                  0x022167A0   ; mon -> its Pokemon reference ([mon + 0x14])
.definelabel MsgRec_Init,                 0x02225DC0
.definelabel MsgRec_AddArg,               0x02225DEC
.definelabel BattleMsg_Emit,              0x02224C50   ; (stream, op, id, variant battler, args..., 0xFFFF)
.definelabel BattleVar_Get,               0x0220FCC0

.open "overlay14.bin", 0x022007E0

; 1. Nature Power: read-only guard of the routine, then the record type.
.org NaturePower_ShowCalledMove
    expect16_at 0x00, 0xB510    ; push  {r4, lr}
    expect16_at 0x02, 0x2006    ; movs  r0, #6
    expect16_at 0x04, 0x1C0C    ; adds  r4, r1, #0
    expect16_at 0x06, 0xF7D0    ; bl    BattleVar_Get           (1/2)
    expect16_at 0x08, 0xFE23    ;                               (2/2)
    expect16_at 0x0A, 0x4284    ; cmp   r4, r0
    expect16_at 0x0C, 0xD112    ; bne   (not this battler's move)
    expect16_at 0x0E, 0x2003    ; movs  r0, #3
    expect16_at 0x10, 0xF7D0    ; bl    BattleVar_Get           (1/2)  var 3: the message record
    expect16_at 0x12, 0xFE1E    ;                               (2/2)
    expect16_at 0x16, 0x2278    ; movs  r2, #0x78               message 120
    expect16_at 0x18, 0x1C04    ; adds  r4, r0, #0
    expect16_at 0x1A, 0xF7E6    ; bl    MsgRec_Init             (1/2)
    expect16_at 0x1C, 0xFE99    ;                               (2/2)
    expect16_at 0x1E, 0x2029    ; movs  r0, #0x29               var 0x29: the called move
    expect16_at 0x20, 0xF7D0    ; bl    BattleVar_Get           (1/2)
    expect16_at 0x22, 0xFE16    ;                               (2/2)
    expect16_at 0x24, 0x1C01    ; adds  r1, r0, #0
    expect16_at 0x26, 0x1C20    ; adds  r0, r4, #0
    expect16_at 0x28, 0xF7E6    ; bl    MsgRec_AddArg           (1/2)  the only argument
    expect16_at 0x2A, 0xFEA8    ;                               (2/2)

.org NaturePower_RecordType
.area 2
    expect16 0x2102             ; movs  r1, #2                  type 2: bank 1, variants
    mov     r1, #1              ; type 1: bank 2, 'Nature Power turned into {move}!'
.endarea

; 2. Infatuation: read-only guard of the message's emit, then the two edits.
.org Turn_CheckInfatuation
    expect16_at 0x00, 0x1C28    ; adds  r0, r5, #0              r5 = the Pokemon about to move
    expect16_at 0x02, 0x2107    ; movs  r1, #7
    expect16_at 0x04, 0xF7F9    ; bl    (has condition 7?)      (1/2)
    expect16_at 0x06, 0xF91A    ;                               (2/2)
    expect16_at 0x08, 0x2800    ; cmp   r0, #0
    expect16_at 0x0A, 0xD026    ; beq   (not infatuated)
    expect16_at 0x18, 0x1C28    ; adds  r0, r5, #0
    expect16_at 0x1A, 0x2107    ; movs  r1, #7
    expect16_at 0x1C, 0xF00C    ; bl    0x0222A434              (1/2)
    expect16_at 0x1E, 0xFC94    ;                               (2/2)
    expect16_at 0x26, 0x1C28    ; adds  r0, r5, #0
    expect16_at 0x28, 0xF7F8    ; bl    Mon_GetRef              (1/2)
    expect16_at 0x2A, 0xFE44    ;                               (2/2)
    expect16_at 0x2C, 0x1C07    ; adds  r7, r0, #0              r7 = variant battler: self
    expect16_at 0x2E, 0x1C28    ; adds  r0, r5, #0
    expect16_at 0x30, 0xF7F8    ; bl    Mon_GetRef              (1/2)
    expect16_at 0x32, 0xFE40    ;                               (2/2)  r0 = self
    expect16_at 0x3A, 0x2271    ; movs  r2, #0x71               (<< 2 = 452)
    expect16_at 0x40, 0x2103    ; movs  r1, #3                  op 3: bank 1, variants
    expect16_at 0x42, 0x0092    ; lsls  r2, r2, #2
    expect16_at 0x44, 0x1C3B    ; adds  r3, r7, #0
    expect16_at 0x46, 0xF007    ; bl    BattleMsg_Emit          (1/2)
    expect16_at 0x48, 0xF88D    ;                               (2/2)

.org Infatuation_ReadData
.area 8
    expect16_at 0, 0xF7F9       ; bl    Condition_GetData       (1/2)  the data field: 0
    expect16_at 2, 0xF926       ;                               (2/2)
    expect16_at 4, 0x0600       ; lsls  r0, r0, #0x18
    expect16_at 6, 0x0E04       ; lsrs  r4, r0, #0x18
    ldr     r4, [r5, #0x70]     ; condition 7's source: the Pokemon it is in love with
    lsl     r4, r4, #0x18
    lsr     r4, r4, #0x18
    mov     r8, r8              ; nop
.endarea

.org Infatuation_StoreArgs
.area 4
    expect16_at 0, 0x9400       ; str   r4, [sp]                {0} = the attracter
    expect16_at 2, 0x9001       ; str   r0, [sp, #4]            {1} = self
    str     r0, [sp]            ; {0}: self, the infatuated Pokemon
    str     r4, [sp, #4]        ; {1}: the Pokemon it is in love with
.endarea

.close
