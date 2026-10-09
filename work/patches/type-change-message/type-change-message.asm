; type-change-message - Battle: type-change messages name the new type, not the last move used (Color Change,
; Protean, Soak, ...). D-2290 (user-approved exception to D-1337; answers the hack finding D-1461).
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md;
; work/notes/type-change-message_fix.md.
;
; The hack's battle engine prints its battle_string messages through a word expander in overlay 14
; (BattleWords_Expand, 0x02225A3C, called by the bank 1 and bank 2 message builders 0x02225EA8 / 0x022257F4).
; It copies the template and, at each {VAR:01xx:slot,0} tag, switches on the tag's kind xx (0-15, jump table
; at 0x02225A9E): it buffers args[slot] as that kind into the message slot (trainer, species, nickname,
; ability, move, item, party nickname, number, trainer class) and then expands the slot. Kind 3, the type
; name, has no case: its entry points at the shared tail, which expands the slot without buffering anything, so the slot
; still holds the last word put there, usually the move named by the message before ('Kecleon used Gust!').
; The only messages with that tag are battle_string bank 1 #1212-#1219 ('{nickname} transformed into
; the {type} type!', '{type} type was added to {nickname}!', each for own / wild / foe / partner trainer). Bank 1
; #1212-#1215 are built only by the type-change handler 0x0220E6E0 (Color Change, Protean, Soak, ...), with
; args (Pokemon, new type).
;
; The fix gives kind 3 a case like the move case: BufferTypeName(fmt, slot, args[slot]) (arm9 0x0200C084,
; a027 bank 724), then the shared tail. The 12 bytes it needs come from the nickname case's (kind 2) fallback
; for an invalid Pokemon: battle-message-error-marker (required) replaces both fallbacks' four literal
; characters with one '(Error) ' loop, entered from the nickname case by its 'b 0x02225B16' at 0x02225B4A, and
; leaves the old copy's last 14 bytes (0x02225B5E-0x02225B6B) dead; the type case takes their first 12 bytes,
; ending on that copy's branch to the tail.

.nds
.thumb
.include "../include/guards.inc"

.definelabel BufferTypeName,                0x0200C084  ; arm9: (fmt r0, slot r1, type r2), a027 bank 724
.definelabel BufferMoveName,                0x0200BF40  ; arm9: (fmt r0, slot r1, move r2), a027 bank 739
.definelabel String_AppendChar,             0x02026FDC  ; arm9: (String r0, character r1)
.definelabel BattleWords_Expand,            0x02225A3C  ; (fmt, args r7, ..., out String r5)
.definelabel BattleWords_KindTable,         0x02225A9E  ; u16[16]: case - 0x02225AA0, by tag kind
.definelabel BattleWords_KindBase,          0x02225AA0  ; 'add pc, r0' at 0x02225A9C reads pc = here
.definelabel BattleWords_KindTypeEntry,     0x02225AA4  ; [3], type name: the shared tail  <- edit 1
.definelabel BattleWords_Nickname,          0x02225B38  ; kind 2
.definelabel BattleWords_TypeCase,          0x02225B5E  ; new kind 3 case, in the freed copy  <- edit 2
.definelabel BattleWords_NicknameToTail,    0x02225B6A  ; the copy's 'b BattleWords_Tail', kept
.definelabel BattleWords_Move,              0x02225B8A  ; kind 7: the pattern the type case follows
.definelabel BattleWords_Tail,              0x02225BBA  ; expand the slot into the output, next tag

.open "overlay14.bin", 0x022007E0

; Read-only guards: the dispatch, the nickname case and the move case (nothing is written here). Both fallbacks
; (0x02225B16-0x02225B37, 0x02225B4A-0x02225B5D) belong to battle-message-error-marker, which guards them.
.org BattleWords_KindTable - 0x12
    expect16_at 0x00, 0x280F    ; cmp   r0, #0xF                tag kind
    expect16_at 0x02, 0xD900    ; bls   0x02225A92
    expect16_at 0x04, 0xE093    ; b     BattleWords_Tail        kind > 15
    expect16_at 0x06, 0x1800    ; add   r0, r0, r0
    expect16_at 0x08, 0x4478    ; add   r0, pc
    expect16_at 0x0A, 0x88C0    ; ldrh  r0, [r0, #6]            the table entry
    expect16_at 0x0C, 0x0400    ; lsl   r0, r0, #16
    expect16_at 0x0E, 0x1400    ; asr   r0, r0, #16
    expect16_at 0x10, 0x4487    ; add   pc, r0                  pc = BattleWords_KindBase + entry
    expect16_at 0x12, 0x0040    ; [0]  trainer        0x02225AE0
    expect16_at 0x14, 0x0064    ; [1]  species        0x02225B04
    expect16_at 0x16, 0x0098    ; [2]  nickname       BattleWords_Nickname
    expect16_at 0x18, 0x011A    ; [3]  type           BattleWords_Tail          <- edit 1
    expect16_at 0x1A, 0x011A    ; [4]                 BattleWords_Tail
    expect16_at 0x1C, 0x011A    ; [5]                 BattleWords_Tail
    expect16_at 0x1E, 0x00CC    ; [6]  ability        0x02225B6C
    expect16_at 0x20, 0x00EA    ; [7]  move           BattleWords_Move

.org BattleWords_Nickname
    expect16_at 0x00, 0x00A0    ; lsl   r0, r4, #2
    expect16_at 0x02, 0x5838    ; ldr   r0, [r7, r0]            args[slot]
    expect16_at 0x04, 0x1C21    ; add   r1, r4, #0
    expect16_at 0x06, 0x0600    ; lsl   r0, r0, #24
    expect16_at 0x08, 0x0E00    ; lsr   r0, r0, #24
    expect16_at 0x0A, 0xF7FF    ; bl    0x022259C4              valid Pokemon? (1/2)
    expect16_at 0x0C, 0xFF3F    ;                               (2/2)
    expect16_at 0x0E, 0x2800    ; cmp   r0, #0
    expect16_at 0x10, 0xD137    ; bne   BattleWords_Tail        valid: buffered; else the error marker

; the four literals the two fallbacks load (pool after the expander, 0x02225C10)
.org BattleWords_Expand + 0x1D4
    expect32_at 0x00, 0x1B9
    expect32_at 0x04, 0xCED
    expect32_at 0x08, 0xBDD
    expect32_at 0x0C, 0x1BA

.org BattleWords_Move
    expect16_at 0x00, 0x00A2    ; lsl   r2, r4, #2
    expect16_at 0x02, 0x9802    ; ldr   r0, [sp, #8]            fmt
    expect16_at 0x04, 0x58BA    ; ldr   r2, [r7, r2]            args[slot]
    expect16_at 0x06, 0x1C21    ; add   r1, r4, #0              slot
    expect16_at 0x08, 0xF5E6    ; bl    BufferMoveName         (1/2)
    expect16_at 0x0A, 0xF9D5    ;                               (2/2)
    expect16_at 0x0C, 0xE010    ; b     BattleWords_Tail

.org BattleWords_Tail
    expect16_at 0x00, 0x9802    ; ldr   r0, [sp, #8]
    expect16_at 0x02, 0x1C21    ; add   r1, r4, #0
    expect16_at 0x04, 0x1C2A    ; add   r2, r5, #0
    expect16_at 0x06, 0xF5E6    ; bl    0x0200C7F0              expand the slot into the output (1/2)
    expect16_at 0x08, 0xFE16    ;                               (2/2)

; Edit 1: the type name kind gets its own case.
.org BattleWords_KindTypeEntry
.area 2
    expect16 0x011A                             ; BattleWords_Tail - BattleWords_KindBase
    .halfword BattleWords_TypeCase - BattleWords_KindBase
.endarea

; Edit 2: the type case, in 12 bytes of the old copy that battle-message-error-marker leaves dead; the copy's
; own branch to the tail (BattleWords_NicknameToTail) follows it unchanged.
.org BattleWords_TypeCase
.area 12
    expect16_at 0x00, 0xF601                    ; bl String_AppendChar (1/2), the old copy's third character
    expect16_at 0x02, 0xFA3D                    ;                      (2/2)
    expect16_at 0x04, 0x492E                    ; ldr r1, =0x1BA
    expect16_at 0x06, 0x1C28                    ; add r0, r5, #0
    expect16_at 0x08, 0xF601                    ; bl String_AppendChar (1/2)
    expect16_at 0x0A, 0xFA39                    ;                      (2/2)
    expect16_at 0x0C, 0xE026                    ; BattleWords_NicknameToTail: b BattleWords_Tail (kept)
    lsl     r2, r4, #2
    ldr     r0, [sp, #8]                        ; fmt
    ldr     r2, [r7, r2]                        ; args[slot]: the new type
    add     r1, r4, #0                          ; slot
    bl      BufferTypeName
.endarea

.close
