; battle-message-error-marker - the battle text's error marker (错误) reads "(Error) " in English. D-2284
; (user-approved exception to D-1337; the logic that makes it appear is the hack's, D-2285).
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md;
; work/notes/battle-text-chinese_fix.md.
;
; The hack's battle message formatter (overlay 14, BattleMsg_Format 0x02225A3C) expands a battle_string
; template into the output String (r5) one control code at a time. For the Pokemon-name tags (0x0101 and
; 0x0102, jump-table cases 1 and 2) it calls a helper with the message's Pokemon reference
; (BattleMsg_BufferMonName1 0x02225978 / BattleMsg_BufferMonName2 0x022259C4). The helper accepts references
; 1..25; for 0 or > 25, or one that resolves to nothing, it buffers reference 1 instead and returns 0. On a 0
; the formatter appends four hardcoded characters to the output, '(' 错 误 ')' ("(error)") through
; String_AddChar (arm9 0x02026FDC), one 'ldr r1, =char; add r0, r5, #0; bl String_AddChar' per character, the
; codes in a shared literal pool (0x02225C10-0x02225C1C), and then goes on to the common tail (0x02225BBA),
; which appends the name buffer. So the marker prints in front of a name, the name being what the fallback
; buffered (observed: the player's first party Pokemon, also while another one is fighting). It is the only
; Chinese the battle prints outside battle_string.narc (work/notes/battle-text-chinese_fix.md 'Sweep').
;
; The fix keeps the logic (when the marker prints, and which name follows it, are the hack's) and only
; changes the text: case 1's 34 bytes become a loop that appends a 0xFFFF-terminated English string, and
; case 2's first instruction branches to it; the English sits in the next 18 bytes of case 2. r4 (the tag's
; buffer index, read again at the tail) is saved around the loop; r5 (the output) is not changed. The loop
; ends with the same branch to the tail as before. The literal pool is left as it is (no longer read).

.nds
.thumb
.include "../include/guards.inc"
.include "../include/charmap.inc"

.definelabel BattleMsg_Format,          0x02225A3C   ; (fmt, params, String *out, template) - not changed
.definelabel BattleMsg_BufferMonName1,  0x02225978   ; tag case 1 helper: 0 = bad reference
.definelabel BattleMsg_BufferMonName2,  0x022259C4   ; tag case 2 helper: 0 = bad reference
.definelabel BattleMsg_Case1,           0x02225B04   ; jump-table case 1 (tag 0x0101)
.definelabel BattleMsg_Case1Error,      0x02225B16   ; four AddChar calls: ( 错 误 )   <- rewritten
.definelabel BattleMsg_Case2,           0x02225B38   ; jump-table case 2 (tag 0x0102)
.definelabel BattleMsg_Case2Error,      0x02225B4A   ; four AddChar calls: ( 错 误 )   <- rewritten
.definelabel BattleMsg_TagDone,         0x02225BBA   ; common tail: append the tag's buffer (r4) to r5
.definelabel BattleMsg_ErrorPool,       0x02225C10   ; literal pool: 0x1B9 0xCED 0xBDD 0x1BA
.definelabel String_AddChar,            0x02026FDC   ; arm9: (String *, u16 char)

.open "overlay14.bin", 0x022007E0

; Read-only guards: the two cases up to their error branches and the literal pool.
.org BattleMsg_Case1
    expect16_at 0x00, 0x00A0    ; lsl   r0, r4, #2
    expect16_at 0x02, 0x5838    ; ldr   r0, [r7, r0]            params[r4]: the Pokemon reference
    expect16_at 0x04, 0x1C21    ; add   r1, r4, #0
    expect16_at 0x06, 0x0600    ; lsl   r0, r0, #0x18
    expect16_at 0x08, 0x0E00    ; lsr   r0, r0, #0x18
    expect16_at 0x0A, 0xF7FF    ; bl    BattleMsg_BufferMonName1 (1/2)
    expect16_at 0x0C, 0xFF33    ;                                (2/2)
    expect16_at 0x0E, 0x2800    ; cmp   r0, #0
    expect16_at 0x10, 0xD151    ; bne   BattleMsg_TagDone       name buffered: no marker
.org BattleMsg_Case2
    expect16_at 0x00, 0x00A0    ; lsl   r0, r4, #2
    expect16_at 0x02, 0x5838    ; ldr   r0, [r7, r0]
    expect16_at 0x04, 0x1C21    ; add   r1, r4, #0
    expect16_at 0x06, 0x0600    ; lsl   r0, r0, #0x18
    expect16_at 0x08, 0x0E00    ; lsr   r0, r0, #0x18
    expect16_at 0x0A, 0xF7FF    ; bl    BattleMsg_BufferMonName2 (1/2)
    expect16_at 0x0C, 0xFF3F    ;                                (2/2)
    expect16_at 0x0E, 0x2800    ; cmp   r0, #0
    expect16_at 0x10, 0xD137    ; bne   BattleMsg_TagDone
.org BattleMsg_ErrorPool
    expect32_at 0x0, 0x000001B9 ; (
    expect32_at 0x4, 0x00000CED ; 错
    expect32_at 0x8, 0x00000BDD ; 误
    expect32_at 0xC, 0x000001BA ; )

; Case 1's error path: a loop over ErrorMarker_Text.
.org BattleMsg_Case1Error
.area 0x22
    expect16_at 0x00, 0x493E    ; ldr   r1, =0x1B9              (
    expect16_at 0x02, 0x1C28    ; add   r0, r5, #0
    expect16_at 0x04, 0xF601    ; bl    String_AddChar          (1/2)
    expect16_at 0x06, 0xFA5F    ;                               (2/2)
    expect16_at 0x08, 0x493D    ; ldr   r1, =0xCED              错
    expect16_at 0x0A, 0x1C28
    expect16_at 0x0C, 0xF601
    expect16_at 0x0E, 0xFA5B
    expect16_at 0x10, 0x493C    ; ldr   r1, =0xBDD              误
    expect16_at 0x12, 0x1C28
    expect16_at 0x14, 0xF601
    expect16_at 0x16, 0xFA57
    expect16_at 0x18, 0x493B    ; ldr   r1, =0x1BA              )
    expect16_at 0x1A, 0x1C28
    expect16_at 0x1C, 0xF601
    expect16_at 0x1E, 0xFA53
    expect16_at 0x20, 0xE040    ; b     BattleMsg_TagDone
ErrorMarker:
    push    r4                              ; r4 = the tag's buffer index, read again at BattleMsg_TagDone
    add     r4, pc, ErrorMarker_Text - ((. + 4) & ~3)
@@next:
    ldrh    r1, [r4]
    add     r0, r1, #1
    lsr     r0, r0, #16                     ; 1 only for the 0xFFFF end
    bne     @@end
    add     r0, r5, #0                      ; the output String
    bl      String_AddChar
    add     r4, #2
    b       @@next
@@end:
    pop     r4
    b       BattleMsg_TagDone
    .fill BattleMsg_Case1Error + 0x22 - ., 0x00   ; unused (never reached)
.endarea

; Case 2's error path: the same loop. The English follows the branch, in the bytes up to 0x02225B5E; the
; rest of case 2's old error path (0x02225B5E-0x02225B6B, now dead) is left as it is, so the type-name case of
; the type-change-message fix can live there.
.org BattleMsg_Case2Error
.area 0x14
    expect16_at 0x00, 0x4931    ; ldr   r1, =0x1B9              (
    expect16_at 0x02, 0x1C28    ; add   r0, r5, #0
    expect16_at 0x04, 0xF601    ; bl    String_AddChar          (1/2)
    expect16_at 0x06, 0xFA45    ;                               (2/2)
    expect16_at 0x08, 0x4930    ; ldr   r1, =0xCED              错
    expect16_at 0x0A, 0x1C28
    expect16_at 0x0C, 0xF601
    expect16_at 0x0E, 0xFA41
    expect16_at 0x10, 0x492F    ; ldr   r1, =0xBDD              误
    expect16_at 0x12, 0x1C28
    b       ErrorMarker
    .align 4, 0x00
ErrorMarker_Text:
    ; "(Error) ": 错误 = error; the space separates it from the name after it. 0xFFFF ends it.
    .halfword CH_LPAREN, CH_E, CH_LC_R, CH_LC_R, CH_LC_O, CH_LC_R, CH_RPAREN, CH_SPACE, 0xFFFF
.endarea

.close
