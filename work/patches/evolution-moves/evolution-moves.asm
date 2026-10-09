; evolution-moves - Evolution: an evolved Pokemon is offered its evolution moves (learnset level 0). D-2276, D-2277.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md; work/notes/evolution-moves_fix.md.
; The hack finding this answers: D-1602 (work/notes/evolution_moves_investigation.md).
;
; The hack's learnsets (a/0/3/3) are u16 pairs (level, move), ended by level 0xFFFF and sorted by level; 415
; species start with level-0 entries, the moves modern games teach on evolution (Charizard: Air Slash). The
; learning routine 0x02070870 (pokeheartgold's MonTryLearnMoveOnLevelUp(mon, &index, &move)) walks the list
; from *index and stops at the first entry whose level is the Pokemon's level: it calls MonTryLearnMove,
; which returns the move, 0xFFFE (already known) or 0xFFFF (no free slot), and its caller asks again with the
; same index until it returns 0. Four calls: day care (0x0206B236, 0x0206B252), level-up (0x020806F2) and the
; evolution scene (0x02074BD4). No entry ever matches level 0, so the evolution moves are never offered.
;
; The fix rewrites the routine in its own space (0xB4 bytes) with one more condition: an entry of level 0
; also matches when the routine was entered at TryLearnOnEvolution, which only the evolution scene calls.
; The flag rides in r3, which the routine already pushes ({r3-r7, lr}); it is read back from the stack.
; One forward pass over the sorted list offers the level-0 moves first, then the moves of the new level,
; each through the scene's own learn / 'forget a move?' flow. On evolution a move of the new level that is
; also a level-0 entry (Toucannon: Beak Blast at 0 and 28) was offered already and is skipped, so a move the
; player declined is not asked for twice; level-up and the day care never take that path. The other three
; callers keep 0x02070870, which now starts with 'mov r3, #0': the same entries as before match there.
; The rewrite also shares the two 'end of list' exits the hack's compiler duplicated; nothing else changes
; (heap, calls, index, results).

.nds
.thumb
.include "../include/guards.inc"

.definelabel TryLearnOnLevelUp,     0x02070870   ; (mon, &index, &move) -> move / 0xFFFE / 0xFFFF / 0
.definelabel TryLearn_End,          0x02070924   ; the next routine (a hack hook: ldr r3, =...; bx r3)
.definelabel EvolutionScene_Learn,  0x02074BD4   ; the evolution scene's call    <- the second edit
.definelabel Heap_AllocAtEnd,       0x0201B2AC   ; (heap, size)
.definelabel Heap_Free,             0x0201B33C
.definelabel GetMonData,            0x0206D848   ; (mon, field, NULL): 5 species, 0x70 form, 0xA1 level
.definelabel MonTryLearnMove,       0x020706B8   ; (mon, move)
.definelabel LoadLevelUpLearnset,   0x02071238   ; (species, form, buffer)

LEARNSET_END   equ 0xFFFF   ; level of the end entry
LEARNSET_BYTES equ 0xA8     ; the buffer the routine allocates: 42 entries (the longest list has 32)

.open "arm9.bin", 0x02000000

; The routine as the hack has it (all of it is replaced below).
.org TryLearnOnLevelUp
    expect16_at 0x00, 0xB5F8    ; push  {r3, r4, r5, r6, r7, lr}
    expect16_at 0x02, 0xB084    ; sub   sp, #0x10
    expect16_at 0x04, 0x1C07    ; adds  r7, r0, #0
    expect16_at 0x06, 0x1C0D    ; adds  r5, r1, #0
    expect16_at 0x08, 0x2000    ; movs  r0, #0
    expect16_at 0x0A, 0x21A8    ; movs  r1, #0xa8
    expect16_at 0x0C, 0x9200    ; str   r2, [sp]
    expect16_at 0x0E, 0x9002    ; str   r0, [sp, #8]
    expect16_at 0x10, 0xF7AA    ; bl    Heap_AllocAtEnd  (1/2)
    expect16_at 0x12, 0xFD14    ;                       (2/2)
    expect16_at 0x14, 0x1C04    ; adds  r4, r0, #0
    expect16_at 0x16, 0x1C38    ; adds  r0, r7, #0
    expect16_at 0x18, 0x2105    ; movs  r1, #5
    expect16_at 0x1A, 0x2200    ; movs  r2, #0
    expect16_at 0x1C, 0xF7FC    ; bl    GetMonData  (1/2)
    expect16_at 0x1E, 0xFFDC    ;                       (2/2)
    expect16_at 0x20, 0x0400    ; lsls  r0, r0, #0x10
    expect16_at 0x22, 0x0C00    ; lsrs  r0, r0, #0x10
    expect16_at 0x24, 0x9001    ; str   r0, [sp, #4]
    expect16_at 0x26, 0x1C38    ; adds  r0, r7, #0
    expect16_at 0x28, 0x2170    ; movs  r1, #0x70
    expect16_at 0x2A, 0x2200    ; movs  r2, #0
    expect16_at 0x2C, 0xF7FC    ; bl    GetMonData  (1/2)
    expect16_at 0x2E, 0xFFD4    ;                       (2/2)
    expect16_at 0x30, 0x9003    ; str   r0, [sp, #0xc]
    expect16_at 0x32, 0x1C38    ; adds  r0, r7, #0
    expect16_at 0x34, 0x21A1    ; movs  r1, #0xa1
    expect16_at 0x36, 0x2200    ; movs  r2, #0
    expect16_at 0x38, 0xF7FC    ; bl    GetMonData  (1/2)
    expect16_at 0x3A, 0xFFCE    ;                       (2/2)
    expect16_at 0x3C, 0x0600    ; lsls  r0, r0, #0x18
    expect16_at 0x3E, 0x0E06    ; lsrs  r6, r0, #0x18
    expect16_at 0x40, 0x9801    ; ldr   r0, [sp, #4]
    expect16_at 0x42, 0x9903    ; ldr   r1, [sp, #0xc]
    expect16_at 0x44, 0x1C22    ; adds  r2, r4, #0
    expect16_at 0x46, 0xF000    ; bl    LoadLevelUpLearnset  (1/2)
    expect16_at 0x48, 0xFCBF    ;                       (2/2)
    expect16_at 0x4A, 0x6828    ; ldr   r0, [r5]
    expect16_at 0x4C, 0x4A18    ; ldr   r2, [pc, #0x60]
    expect16_at 0x4E, 0x0080    ; lsls  r0, r0, #2
    expect16_at 0x50, 0x5A21    ; ldrh  r1, [r4, r0]
    expect16_at 0x52, 0x4291    ; cmp   r1, r2
    expect16_at 0x54, 0xD105    ; bne   #0x20708d2
    expect16_at 0x56, 0x1C20    ; adds  r0, r4, #0
    expect16_at 0x58, 0xF7AA    ; bl    Heap_Free  (1/2)
    expect16_at 0x5A, 0xFD38    ;                       (2/2)
    expect16_at 0x5C, 0xB004    ; add   sp, #0x10
    expect16_at 0x5E, 0x2000    ; movs  r0, #0
    expect16_at 0x60, 0xBDF8    ; pop   {r3, r4, r5, r6, r7, pc}
    expect16_at 0x62, 0x428E    ; cmp   r6, r1
    expect16_at 0x64, 0xD00E    ; beq   #0x20708f4
    expect16_at 0x66, 0x6828    ; ldr   r0, [r5]
    expect16_at 0x68, 0x1C40    ; adds  r0, r0, #1
    expect16_at 0x6A, 0x6028    ; str   r0, [r5]
    expect16_at 0x6C, 0x0080    ; lsls  r0, r0, #2
    expect16_at 0x6E, 0x5A21    ; ldrh  r1, [r4, r0]
    expect16_at 0x70, 0x4291    ; cmp   r1, r2
    expect16_at 0x72, 0xD105    ; bne   #0x20708f0
    expect16_at 0x74, 0x1C20    ; adds  r0, r4, #0
    expect16_at 0x76, 0xF7AA    ; bl    Heap_Free  (1/2)
    expect16_at 0x78, 0xFD29    ;                       (2/2)
    expect16_at 0x7A, 0xB004    ; add   sp, #0x10
    expect16_at 0x7C, 0x2000    ; movs  r0, #0
    expect16_at 0x7E, 0xBDF8    ; pop   {r3, r4, r5, r6, r7, pc}
    expect16_at 0x80, 0x428E    ; cmp   r6, r1
    expect16_at 0x82, 0xD1F0    ; bne   #0x20708d6
    expect16_at 0x84, 0x428E    ; cmp   r6, r1
    expect16_at 0x86, 0xD10C    ; bne   #0x2070912
    expect16_at 0x88, 0x1820    ; adds  r0, r4, r0
    expect16_at 0x8A, 0x8841    ; ldrh  r1, [r0, #2]
    expect16_at 0x8C, 0x9800    ; ldr   r0, [sp]
    expect16_at 0x8E, 0x8001    ; strh  r1, [r0]
    expect16_at 0x90, 0x6828    ; ldr   r0, [r5]
    expect16_at 0x92, 0x9900    ; ldr   r1, [sp]
    expect16_at 0x94, 0x1C40    ; adds  r0, r0, #1
    expect16_at 0x96, 0x6028    ; str   r0, [r5]
    expect16_at 0x98, 0x8809    ; ldrh  r1, [r1]
    expect16_at 0x9A, 0x1C38    ; adds  r0, r7, #0
    expect16_at 0x9C, 0xF7FF    ; bl    MonTryLearnMove  (1/2)
    expect16_at 0x9E, 0xFED4    ;                       (2/2)
    expect16_at 0xA0, 0x9002    ; str   r0, [sp, #8]
    expect16_at 0xA2, 0x1C20    ; adds  r0, r4, #0
    expect16_at 0xA4, 0xF7AA    ; bl    Heap_Free  (1/2)
    expect16_at 0xA6, 0xFD12    ;                       (2/2)
    expect16_at 0xA8, 0x9802    ; ldr   r0, [sp, #8]
    expect16_at 0xAA, 0xB004    ; add   sp, #0x10
    expect16_at 0xAC, 0xBDF8    ; pop   {r3, r4, r5, r6, r7, pc}
    expect16_at 0xAE, 0x46C0    ; mov   r8, r8
    expect32_at 0xB0, 0x0000FFFF    ; literal pool: end of learnset
.area TryLearn_End - TryLearnOnLevelUp
    mov     r3, #0                  ; level-up / day care: level-0 entries do not match
TryLearn_Body:
    push    {r3-r7, lr}             ; [sp + 0x10] after the sub: the level-0 flag
    sub     sp, #0x10               ; [sp] &move, [sp+4] species, [sp+8] result, [sp+0xC] form
    add     r7, r0, #0              ; r7 = mon
    add     r5, r1, #0              ; r5 = &index
    mov     r0, #0
    mov     r1, #LEARNSET_BYTES
    str     r2, [sp]
    str     r0, [sp, #8]            ; result = 0 (nothing to learn)
    bl      Heap_AllocAtEnd
    add     r4, r0, #0              ; r4 = learnset buffer
    add     r0, r7, #0
    mov     r1, #5
    mov     r2, #0
    bl      GetMonData              ; species
    lsl     r0, r0, #0x10
    lsr     r0, r0, #0x10
    str     r0, [sp, #4]
    add     r0, r7, #0
    mov     r1, #0x70
    mov     r2, #0
    bl      GetMonData              ; form
    str     r0, [sp, #0xC]
    add     r0, r7, #0
    mov     r1, #0xA1
    mov     r2, #0
    bl      GetMonData              ; level
    lsl     r0, r0, #0x18
    lsr     r6, r0, #0x18           ; r6 = level
    ldr     r0, [sp, #4]
    ldr     r1, [sp, #0xC]
    add     r2, r4, #0
    bl      LoadLevelUpLearnset
    ldr     r2, =LEARNSET_END
TryLearn_Entry:
    ldr     r0, [r5]
    lsl     r0, r0, #2              ; r0 = index * 4: the entry (level, move)
    ldrh    r1, [r4, r0]            ; r1 = its level
    cmp     r1, r2
    beq     TryLearn_Done                  ; end of the list: result 0
    ldr     r3, [sp, #0x10]         ; r3 = the level-0 flag
    cmp     r1, r6
    beq     TryLearn_Level                 ; the Pokemon's level (as before; on evolution: no repeat, below)
    cmp     r1, #0
    bne     TryLearn_Next
    cmp     r3, #0
    bne     TryLearn_Match                 ; level 0, called by the evolution scene (new)
TryLearn_Next:
    ldr     r0, [r5]
    add     r0, r0, #1
    str     r0, [r5]
    b       TryLearn_Entry
TryLearn_Match:
    add     r0, r4, r0
    ldrh    r1, [r0, #2]            ; r1 = the move
    ldr     r0, [sp]
    strh    r1, [r0]                ; *move
    ldr     r0, [r5]
    add     r0, r0, #1
    str     r0, [r5]                ; index past this entry
    add     r0, r7, #0
    bl      MonTryLearnMove         ; (mon, move)
    str     r0, [sp, #8]
TryLearn_Done:
    add     r0, r4, #0
    bl      Heap_Free
    ldr     r0, [sp, #8]
    add     sp, #0x10
    pop     {r3-r7, pc}
TryLearnOnEvolution:
    mov     r3, #1                  ; evolution scene: level-0 entries match too
    b       TryLearn_Body
TryLearn_Level:                            ; an entry of the Pokemon's level; r0 = index * 4
    cmp     r3, #0
    beq     TryLearn_Match                 ; level-up, day care: offered, exactly as before
    add     r1, r4, r0
    ldrh    r1, [r1, #2]            ; r1 = its move
    add     r3, r4, #0              ; r3 = the first entry: the level-0 entries lead the sorted list
TryLearn_EvoMove:
    ldrh    r2, [r3]
    cmp     r2, #0
    bne     TryLearn_Match                 ; past the level-0 entries: not an evolution move, offered
    ldrh    r2, [r3, #2]
    add     r3, #4
    cmp     r2, r1
    bne     TryLearn_EvoMove
    ldr     r2, =LEARNSET_END       ; an evolution move, offered already (learned, known or declined):
    b       TryLearn_Next                  ; this level's repeat of it is skipped
.pool
    .fill   TryLearn_End - ., 0     ; the rest of the old routine: unused
.endarea

; The evolution scene asks for the moves of its new species through the new entry.
.org EvolutionScene_Learn
.area 4
    expect16_at 0, 0xF7FB           ; bl TryLearnOnLevelUp  (1/2)
    expect16_at 2, 0xFE4C           ;                       (2/2)
    bl      TryLearnOnEvolution
.endarea

.close
