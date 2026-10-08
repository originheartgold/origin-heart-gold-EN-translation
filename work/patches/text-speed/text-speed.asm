; text-speed - Options TEXT SPEED (NORMAL / FAST), 30 fps printer catch-up, Pokégear calls wait for A/B.
; D-1604, D-1601, D-1603, D-1600 (hack finding D-1599), D-1575.
; Why and what: fix.toml next to this file; work/notes/text_speed_release.md; toolchain: work/notes/toolchain.md.
;
; The new code is native.c, compiled by clang into payload.json (the reviewed compiler output, pinned by
; sha256 in work/tools/text_speed_patch.py). The build writes its bytes to ../native/text-speed.bin before
; armips runs; this source places them in the ARM9 ITCM block and hooks the game into them. The labels below
; are the payload's symbols (payload.json "symbols", Thumb bit cleared; `fixes.py check` compares them):
; Thumb entry points, except text_speed_state (the zeroed runtime frame state, the last 52 bytes).

.nds
.thumb
.include "../include/guards.inc"

.definelabel frame_end,         0x01FF8620
.definelabel print_task,        0x01FF874C
.definelabel load_rows,         0x01FF8A0C
.definelabel load_choice,       0x01FF8A3C
.definelabel load_label,        0x01FF8A80
.definelabel commit_speed,      0x01FF8AA8
.definelabel exit_free,         0x01FF8AD4
.definelabel draw_label,        0x01FF8B10
.definelabel setup_sprites,     0x01FF8B34
.definelabel pass_end,          0x01FF8B88
.definelabel call_print,        0x01FF8E2C
.definelabel text_speed_state,  0x01FF8F88

THUMB equ 1                     ; bit 0 of a code pointer: Thumb

; ---------------------------------------------------------------------------------------------------------
; ITCM: the payload is appended to the hack's ITCM autoload block (0x01FF8000, 0x620 bytes), which the SDK
; copies to ITCM at boot. The block ends 32-byte aligned; it may reach 0x01FFA000 at most ([[grow]] itcm).

.open "itcm.bin", 0x01FF8000

.org 0x01FF8620
.area 0x01FFA000 - 0x01FF8620
    expect_end                                  ; guard: the hack's ITCM block still ends here
TextSpeed_Payload:
    .incbin "../native/text-speed.bin"
    .if text_speed_state != org() - 52
      .error "payload.json symbols do not match its bytes: text_speed_state must be the last 52 bytes"
    .endif
    .align 32, 0
TextSpeed_ItcmEnd:
.endarea

.close

; ---------------------------------------------------------------------------------------------------------
; ARM9

.open "arm9.bin", 0x02000000

; Game loop NitroMain (0x02000C88): its last call before the VBlank wait goes through pass_end, which makes
; that call (0x020272D4) first, measures the end of the frame, then gives every printer task one extra turn
; per missed screen refresh (30 fps catch-up, D-1603).
.org 0x02000DE0
.area 4
    expect32 0xFA78F026                         ; bl 0x020272D4
    bl      pass_end
.endarea

; Printer constructor: the task it adds for a text printer is print_task (NORMAL: the original task
; 0x02020A1D; FAST: batched glyphs within the frame, D-1601).
.org 0x02020A18
.area 4
    expect32 0x02020A1D                         ; .word 0x02020A1D (original print task, Thumb)
    .word   print_task + THUMB
.endarea

; Options init (new games): the 4-bit field the hack cleared now gets TEXT SPEED = FAST (bits 2-3 = 1);
; MUSIC SPEED (bits 0-1) stays 0. Existing saves read as NORMAL.
.org 0x0202B176
.area 4
    expect16_at 0, 0x200F                       ; mov r0, #0xF
    expect16_at 2, 0x4381                       ; bic r1, r0
    mov     r0, #1 << 2
    orr     r1, r0
.endarea

; MUSIC SPEED getter and setter: only bits 0-1, so TEXT SPEED (bits 2-3) survives.
.org 0x0202B1C6
.area 4
    expect16_at 0, 0x0700                       ; lsl r0, r0, #28
    expect16_at 2, 0x0F00                       ; lsr r0, r0, #28
    lsl     r0, r0, #30
    lsr     r0, r0, #30
.endarea

.org 0x0202B1D2
.area 2
    expect16 0x220F                             ; mov r2, #0xF   (bits cleared before the new value)
    mov     r2, #3
.endarea

.org 0x0202B1DA
.area 2
    expect16 0x210F                             ; mov r1, #0xF   (the new value's mask)
    mov     r1, #3
.endarea

; SDK arena bounds table: the ITCM arena starts after the payload.
.org 0x020D1A28
.area 4
    expect32 0x01FF8620
    .word   TextSpeed_ItcmEnd
.endarea

.close

; ---------------------------------------------------------------------------------------------------------
; Overlay 50: the Options menu, from six rows (+ the confirm row) to seven. The menu's work struct gets one
; more per-row record (0x54 bytes), so every field after the records moves by 0x54.

RECORD_SIZE equ 0x54

; Stop the build: the mov/lsl pair at `addr` builds `built`, not the field offset `offset`.
.macro relocate_failed, addr, built, offset
    .error "relocate_field at " + tohex(addr, 8) + ": the old mov/lsl build " + tohex(built) + ", not " + tohex(offset)
.endmacro

; A field offset built as `mov rN, #imm` + `lsl rN, rN, #shift` (shift 2 or 4) is rebuilt with shift 2.
.macro relocate_field, addr, reg, old_mov, lsl_addr, old_lsl, offset
    .if ((old_mov & 0xFF) << ((old_lsl >> 6) & 0x1F)) != offset
      relocate_failed addr, (old_mov & 0xFF) << ((old_lsl >> 6) & 0x1F), offset
    .endif
    .if (offset + RECORD_SIZE) % 4 || (offset + RECORD_SIZE) / 4 > 255
      .error "field offset " + tohex(offset + RECORD_SIZE) + " cannot be encoded as mov #imm8 + lsl #2"
    .endif
.org addr
.area 2
    expect16 old_mov
    mov     reg, #(offset + RECORD_SIZE) / 4
.endarea
.org lsl_addr
.area 2
    expect16 old_lsl
    lsl     reg, reg, #2
.endarea
.endmacro

.open "overlay50.bin", 0x021E4980

; The work struct's size: 0x324 -> 0x378 (allocation and clear).
.org 0x021E4994
.area 2
    expect16 0x21C9                             ; mov r1, #0xC9   (<< 2 = 0x324)
    mov     r1, #(0x324 + RECORD_SIZE) / 4
.endarea
.org 0x021E49A0
.area 2
    expect16 0x22C9                             ; mov r2, #0xC9   (<< 2 = 0x324)
    mov     r2, #(0x324 + RECORD_SIZE) / 4
.endarea

; Every access to a field after the records (offsets 0x2D0-0x324): address, register, old mov, address
; of its lsl, old lsl, old offset.
    relocate_field 0x021E4A46, r1, 0x2132, 0x021E4A48, 0x0109, 0x320
    relocate_field 0x021E4BC8, r0, 0x20B5, 0x021E4BCA, 0x0080, 0x2D4
    relocate_field 0x021E4BD4, r0, 0x20B5, 0x021E4BD6, 0x0080, 0x2D4
    relocate_field 0x021E4BF4, r0, 0x20B5, 0x021E4BF6, 0x0080, 0x2D4
    relocate_field 0x021E4C04, r0, 0x20B5, 0x021E4C06, 0x0080, 0x2D4
    relocate_field 0x021E4C14, r0, 0x20B5, 0x021E4C16, 0x0080, 0x2D4
    relocate_field 0x021E4C4A, r0, 0x20B5, 0x021E4C4C, 0x0080, 0x2D4
    relocate_field 0x021E5552, r1, 0x21BB, 0x021E5554, 0x0089, 0x2EC
    relocate_field 0x021E5564, r1, 0x212F, 0x021E5566, 0x0109, 0x2F0
    relocate_field 0x021E56E8, r0, 0x20BE, 0x021E56EA, 0x0080, 0x2F8
    relocate_field 0x021E5710, r0, 0x20BD, 0x021E5712, 0x0080, 0x2F4
    relocate_field 0x021E5758, r0, 0x20BD, 0x021E575A, 0x0080, 0x2F4
    relocate_field 0x021E5766, r0, 0x20BD, 0x021E5768, 0x0080, 0x2F4
    relocate_field 0x021E57E6, r0, 0x2032, 0x021E57EA, 0x0100, 0x320
    relocate_field 0x021E5812, r0, 0x20BE, 0x021E5814, 0x0080, 0x2F8
    relocate_field 0x021E5854, r0, 0x2032, 0x021E5858, 0x0100, 0x320
    relocate_field 0x021E5880, r0, 0x20BD, 0x021E5882, 0x0080, 0x2F4
    relocate_field 0x021E58F8, r0, 0x2032, 0x021E58FC, 0x0100, 0x320
    relocate_field 0x021E5964, r0, 0x20BD, 0x021E5966, 0x0080, 0x2F4
    relocate_field 0x021E5970, r0, 0x20BE, 0x021E5972, 0x0080, 0x2F8
    relocate_field 0x021E597E, r0, 0x20BD, 0x021E5980, 0x0080, 0x2F4
    relocate_field 0x021E598A, r0, 0x20BE, 0x021E598C, 0x0080, 0x2F8
    relocate_field 0x021E59AE, r0, 0x20BD, 0x021E59B0, 0x0080, 0x2F4
    relocate_field 0x021E59BA, r0, 0x20BE, 0x021E59BC, 0x0080, 0x2F8
    relocate_field 0x021E5A08, r1, 0x212D, 0x021E5A0A, 0x0109, 0x2D0
    relocate_field 0x021E5A14, r7, 0x27B5, 0x021E5A16, 0x00BF, 0x2D4
    relocate_field 0x021E5A6E, r1, 0x212D, 0x021E5A70, 0x0109, 0x2D0
    relocate_field 0x021E5A7E, r0, 0x202D, 0x021E5A80, 0x0100, 0x2D0
    relocate_field 0x021E5AA6, r1, 0x212D, 0x021E5AAA, 0x0109, 0x2D0
    relocate_field 0x021E5AB6, r0, 0x202D, 0x021E5AB8, 0x0100, 0x2D0
    relocate_field 0x021E5AC0, r0, 0x20B5, 0x021E5AC4, 0x0080, 0x2D4
    relocate_field 0x021E5AD8, r0, 0x202D, 0x021E5ADC, 0x0100, 0x2D0
    relocate_field 0x021E5ADA, r1, 0x21B5, 0x021E5ADE, 0x0089, 0x2D4
    relocate_field 0x021E5AEE, r1, 0x21B6, 0x021E5AF0, 0x0089, 0x2D8
    relocate_field 0x021E5AFE, r0, 0x20B6, 0x021E5B00, 0x0080, 0x2D8
    relocate_field 0x021E5B14, r0, 0x20BD, 0x021E5B16, 0x0080, 0x2F4
    relocate_field 0x021E5B32, r0, 0x20B6, 0x021E5B34, 0x0080, 0x2D8
    relocate_field 0x021E5B56, r0, 0x20B6, 0x021E5B5C, 0x0080, 0x2D8
    relocate_field 0x021E5B7C, r0, 0x20BD, 0x021E5B7E, 0x0080, 0x2F4
    relocate_field 0x021E5B8A, r0, 0x20BE, 0x021E5B8C, 0x0080, 0x2F8

; The confirm row's selection field (literal pool word): 0x27E -> 0x2D2. 0x27E is now TEXT SPEED's value.
.org 0x021E53E8
.area 4
    expect32 0x0000027E
    .word   0x27E + RECORD_SIZE
.endarea

; Row counts: six setting rows -> seven (the confirm row is now 7, the row count 8).
.org 0x021E4E24
.area 2
    expect16 0x2F06                   ; cmp r7, #6
    cmp     r7, #7
.endarea
.org 0x021E528E
.area 2
    expect16 0x2C06                   ; cmp r4, #6
    cmp     r4, #7
.endarea
.org 0x021E52FA
.area 2
    expect16 0x2C07                   ; cmp r4, #7
    cmp     r4, #8
.endarea
.org 0x021E538C
.area 2
    expect16 0x2806                   ; cmp r0, #6
    cmp     r0, #7
.endarea
.org 0x021E55A0
.area 2
    expect16 0x2906                   ; cmp r1, #6
    cmp     r1, #7
.endarea
.org 0x021E56C8
.area 2
    expect16 0x2906                   ; cmp r1, #6
    cmp     r1, #7
.endarea
.org 0x021E5746
.area 2
    expect16 0x2906                   ; cmp r1, #6
    cmp     r1, #7
.endarea
.org 0x021E594A
.area 2
    expect16 0x2C06                   ; cmp r4, #6
    cmp     r4, #7
.endarea
.org 0x021E59DC
.area 2
    expect16 0x2806                   ; cmp r0, #6
    cmp     r0, #7
.endarea
.org 0x021E5658
.area 2
    expect16 0x2107                   ; mov r1, #7
    mov     r1, #8
.endarea
.org 0x021E565E
.area 2
    expect16 0x1D80                   ; add r0, r0, #6
    add     r0, r0, #7
.endarea
.org 0x021E568E
.area 2
    expect16 0x2107                   ; mov r1, #7
    mov     r1, #8
.endarea

; Row pitch of the label windows: 24 -> 20 px, so seven rows fit.
.org 0x021E5268
.area 2
    expect16 0x2018                   ; mov r0, #0x18
    mov     r0, #20
.endarea
.org 0x021E53F6
.area 2
    expect16 0x2018                   ; mov r0, #0x18
    mov     r0, #20
.endarea

; Opaque background (palette colour 2) behind the compact rows, so they stay legible.
.org 0x021E512E
.area 2
    expect16 0x2100                   ; mov r1, #0
    mov     r1, #0x22
.endarea
.org 0x021E540E
.area 2
    expect16 0x2100                   ; mov r1, #0
    mov     r1, #0x22
.endarea
.org 0x021E5534
.area 4
    expect32 0x00010200
    .word   0x00030200
.endarea
.org 0x021E553C
.area 4
    expect32 0x000F0200
    .word   0x00010200
.endarea

; Row 6 (TEXT SPEED) label pitch 32: its choices at x 108 and 188, as the two-choice rows 2 and 3.
.org 0x021E5BAE
.area 1
    .if readu8(outputname(), org() - headersize()) != 0
      .error "guard failed at " + tohex(org(), 8)
    .endif
    .byte   0x20
.endarea

; The row buttons (graphics reused): y 24, 48, 72, 96, 120, 144, 144 -> 24, 44, 64, 84, 104, 124, 124.
; Entries of 40 bytes from 0x021E5E04; y at +6.
.org 0x021E5E32
.area 2
    expect16 48
    .halfword 44
.endarea
.org 0x021E5E5A
.area 2
    expect16 72
    .halfword 64
.endarea
.org 0x021E5E82
.area 2
    expect16 96
    .halfword 84
.endarea
.org 0x021E5EAA
.area 2
    expect16 120
    .halfword 104
.endarea
.org 0x021E5ED2
.area 2
    expect16 144
    .halfword 124
.endarea
.org 0x021E5EFA
.area 2
    expect16 144
    .halfword 124
.endarea

; Calls into the payload.
.org 0x021E4B5A
.area 4
    expect32 0xFB29F622                         ; bl 0x020071B0 (overlay data free)
    bl      exit_free                           ; commit TEXT SPEED (Confirm), then free
.endarea
.org 0x021E4D7C
.area 4
    expect32 0xFADAF000                         ; bl 0x021E5334 (row loader)
    bl      load_rows                           ; the six rows, then TEXT SPEED's value
.endarea
.org 0x021E4DA2
.area 4
    expect32 0xFE93F000                         ; bl 0x021E5ACC (sprite setup)
    bl      setup_sprites
.endarea
.org 0x021E5264
.area 4
    expect32 0xFC52F626                         ; bl 0x0200BB0C (message load into string)
    bl      load_label                          ; row labels, TEXT SPEED from the payload
.endarea
.org 0x021E5284
.area 4
    expect32 0xFAD6F63B                         ; bl 0x02020834 (add printer)
    bl      draw_label
.endarea
.org 0x021E5366
.area 4
    expect32 0xFBEBF626                         ; bl 0x0200BB40 (message load new string)
    bl      load_choice                         ; choice labels, NORMAL / FAST from the payload
.endarea

; The menu's tables, moved to the appended block (below) with a row for TEXT SPEED.
.org 0x021E501C
.area 4
    expect32 0x021E5BF8                         ; label x offsets
    .word   Options_LabelOffsets
.endarea
.org 0x021E53E0
.area 4
    expect32 0x021E5C14                         ; choices per row
    .word   Options_ChoiceCounts
.endarea
.org 0x021E592C
.area 4
    expect32 0x021E5CB4                         ; touch boxes
    .word   Options_TouchBoxes
.endarea
.org 0x021E5930
.area 4
    expect32 0x021E5CF8                         ; touch box -> (row, choice)
    .word   Options_TouchMap
.endarea
.org 0x021E5938
.area 4
    expect32 0x021E5CFC                         ; the same table, from its second word
    .word   Options_TouchMap + 4
.endarea
.org 0x021E59D0
.area 4
    expect32 0x021E5BF8                         ; label x offsets (second user)
    .word   Options_LabelOffsets
.endarea

; Appended to the overlay ([[grow]] overlay50).
.org 0x021E5F80
.area 0x200
    expect_end                                  ; guard: the hack's overlay still ends here
Options_ChoiceCounts:                           ; per row; TEXT SPEED (row 6) has NORMAL and FAST
    .word   3, 2, 2, 2, 3, 20, 2, 2
Options_LabelOffsets:                           ; row label x offsets: pitch 20 instead of 24
    .word   -8, -28, -48, -68, -88, -108, -128, -156
Options_TouchBoxes:                             ; top, bottom, left, right; rows 1-5 moved up 4 px per row
    .byte   26, 46, 112, 151,   26, 46, 160, 200,   26, 46, 208, 248     ; row 0
    .byte   46, 66, 112, 151,   46, 66, 160, 200                         ; row 1 (was y 50-70)
    .byte   66, 85, 112, 167,   66, 85, 192, 247                         ; row 2 (was 74-93)
    .byte   86, 105, 112, 167,  86, 105, 192, 247                        ; row 3 (was 98-117)
    .byte   106, 126, 112, 151, 106, 126, 160, 200, 106, 126, 208, 248   ; row 4 (was 122-142)
    .byte   126, 146, 110, 150, 126, 146, 208, 253                       ; row 5 (was 146-166)
    .byte   172, 191, 128, 180, 172, 191, 183, 255                       ; confirm buttons (unchanged)
    .byte   146, 166, 112, 167, 146, 166, 192, 247                       ; row 6 TEXT SPEED (columns of rows 2, 3)
    .byte   255, 0, 0, 0                                                 ; end
Options_TouchMap:                               ; (row, choice) per touch box
    .word   0, 0,  0, 1,  0, 2
    .word   1, 0,  1, 1
    .word   2, 0,  2, 1
    .word   3, 0,  3, 1
    .word   4, 0,  4, 1,  4, 2
    .word   5, 3,  5, 4
    .word   7, 5,  7, 6                         ; confirm buttons: row 6 -> 7
    .word   6, 0,  6, 1                         ; TEXT SPEED: NORMAL, FAST
.endarea

.close

; ---------------------------------------------------------------------------------------------------------
; Overlay 92 (Pokégear): the phone-call page printer (0x021F11E8, outgoing and incoming calls) adds its
; printer through call_print, which clears the auto-advance the hack's battle code leaves on (D-1599) and
; then calls AddTextPrinterParameterized unchanged: every call page waits for A/B (D-1600).

.open "overlay92.bin", 0x021E67C0

.org 0x021F1228
.area 4
    expect32 0xFB04F62F                         ; bl 0x02020834 (AddTextPrinterParameterized)
    bl      call_print
.endarea

.close
