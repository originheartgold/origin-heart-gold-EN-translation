; naming-keyboard - English naming keyboard: ABC page first, pinyin IME off. D-1039, D-1002.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md.
; The tab labels (ABC / abc / QWE) are the graphics fix gfx-naming-tabs, which requires this fix.
;
; The hack's keyboard (Japanese base) has four tabs. Page N types the keys of the rows
; sKeyboardLayoutPtrs[N][0..4] (5 row pointers per page); a row is 13 key codes and an 0xFFFF end.
; The screen opens on page 0, which ran the hack's pinyin IME; page 2 typed full-width letters.
;
;   tab  page  hack                                  now
;   1    0     pinyin IME (QWERTY into a pinyin       ABC: A-M, N-Z, a-m, n-z, 0-9 . ,
;              buffer, hanzi candidates in rows 1-2)
;   2    1     a-z / A-Z / 0-9                        unchanged (abc)
;   3    2     full-width ＡＢＣ, ａｂｃ, ０-９            QWE: blank, 1-0, QWERTYUIOP, ASDFGHJKL ’ -, ZXCVBNM , .
;   4    3     1/♪ symbols                            unchanged
;
; Putting ABC on page 0 makes it the default without touching the init code (changing the default
; page would need 5+ patches).

.nds
.thumb
.include "../include/guards.inc"
.include "../include/charmap.inc"

.definelabel sKeyboardLayoutPtrs, 0x0210F688     ; const u16 *[4 pages][5 rows]
.definelabel NamingScreen_InsertKey, 0x02083CF8  ; the normal "insert key" path of the key handler

; The current address is row `row` of page `page`: the pointer table points here.
.macro keyboard_row, page, row
  expect32_abs sKeyboardLayoutPtrs + 4 * ((page) * 5 + (row)), org()
.endmacro

; The keys at the current address are k0..k6 (keys 1-7 of the row).
.macro keys_were_1to7, k0, k1, k2, k3, k4, k5, k6
  expect16_at  0, k0
  expect16_at  2, k1
  expect16_at  4, k2
  expect16_at  6, k3
  expect16_at  8, k4
  expect16_at 10, k5
  expect16_at 12, k6
.endmacro

; Keys 8-13 of the row at the current address are k7..k12, and the row ends with 0xFFFF.
.macro keys_were_8to13, k7, k8, k9, k10, k11, k12
  expect16_at 14, k7
  expect16_at 16, k8
  expect16_at 18, k9
  expect16_at 20, k10
  expect16_at 22, k11
  expect16_at 24, k12
  expect16_at 26, 0xFFFF
.endmacro

; Each row below: the pointer to it, its old keys (1-7, 8-13), then `.area 26` with the 13 new keys
; (7 + 6 per line). The row's 0xFFFF end stays.

.open "arm9.bin", 0x02000000

; ---------------------------------------------------------------------------------------------
; IME off. In the key handler (hack 0x02083814; US arm9 0x02084884, pret NamingScreen_HandleCharacterInput),
; 'cmp r0, #0; bne NamingScreen_InsertKey' sends keys on pages 1-3 to the normal insert path and keys
; on page 0 into the hack's pinyin IME (pinyin buffer at data+0x5E4, candidate lookup 0x020835E4 over
; a/0/3/1 #19/#20). An unconditional branch makes every page insert the key directly; the IME never
; starts. Keys >= 0x1FF (hanzi) would still take the hack's commit path, but no page has them any more.
.org 0x02083C24
.area 2
    expect16_at -2, 0x2800      ; cmp r0, #0   (r0 = page != 0)
    expect16 0xD168             ; bne NamingScreen_InsertKey
    b       NamingScreen_InsertKey
.endarea

; ---------------------------------------------------------------------------------------------
; Tab 1 / page 0 (opens first): pinyin page -> ABC, the hack's own ABC layout in Western codes.

.org 0x02100CE4
    keyboard_row 0, 0           ; was: pinyin candidate row 1 (blank)
    keys_were_1to7  CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE
    keys_were_8to13 CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE
.area 26
    .halfword CH_A, CH_B, CH_C, CH_D, CH_E, CH_F, CH_G
    .halfword CH_H, CH_I, CH_J, CH_K, CH_L, CH_M
.endarea

.org 0x02100D00
    keyboard_row 0, 1           ; was: pinyin candidate row 2 (blank)
    keys_were_1to7  CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE
    keys_were_8to13 CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE
.area 26
    .halfword CH_N, CH_O, CH_P, CH_Q, CH_R, CH_S, CH_T
    .halfword CH_U, CH_V, CH_W, CH_X, CH_Y, CH_Z
.endarea

.org 0x02100D1C
    keyboard_row 0, 2           ; was: Q W E R T Y U I O P _ _ _
    keys_were_1to7  CH_Q, CH_W, CH_E, CH_R, CH_T, CH_Y, CH_U
    keys_were_8to13 CH_I, CH_O, CH_P, CH_SPACE, CH_SPACE, CH_SPACE
.area 26
    .halfword CH_LC_A, CH_LC_B, CH_LC_C, CH_LC_D, CH_LC_E, CH_LC_F, CH_LC_G
    .halfword CH_LC_H, CH_LC_I, CH_LC_J, CH_LC_K, CH_LC_L, CH_LC_M
.endarea

.org 0x02100C90
    keyboard_row 0, 3           ; was: _ A S D F G H J K L _ and the candidate arrows ← →
    keys_were_1to7  CH_SPACE, CH_A, CH_S, CH_D, CH_F, CH_G, CH_H
    keys_were_8to13 CH_J, CH_K, CH_L, CH_SPACE, CH_ARROW_LEFT, CH_ARROW_RIGHT
.area 26
    .halfword CH_LC_N, CH_LC_O, CH_LC_P, CH_LC_Q, CH_LC_R, CH_LC_S, CH_LC_T
    .halfword CH_LC_U, CH_LC_V, CH_LC_W, CH_LC_X, CH_LC_Y, CH_LC_Z
.endarea

.org 0x02100CC8
    keyboard_row 0, 4           ; was: _ _ Z X C V B N M _ _ _ _
    keys_were_1to7  CH_SPACE, CH_SPACE, CH_Z, CH_X, CH_C, CH_V, CH_B
    keys_were_8to13 CH_N, CH_M, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE
.area 26
    .halfword CH_0, CH_1, CH_2, CH_3, CH_4, CH_5, CH_6
    .halfword CH_7, CH_8, CH_9, CH_PERIOD, CH_COMMA, CH_SPACE
.endarea

; ---------------------------------------------------------------------------------------------
; Tab 3 / page 2: full-width ＡＢＣ -> QWE (QWERTY in Western codes).

.org 0x02100DFC
    keyboard_row 2, 0           ; was: Ａ-Ｍ
    keys_were_1to7  FW_A, FW_B, FW_C, FW_D, FW_E, FW_F, FW_G
    keys_were_8to13 FW_H, FW_I, FW_J, FW_K, FW_L, FW_M
.area 26
    .halfword CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE
    .halfword CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE, CH_SPACE
.endarea

.org 0x02100E34
    keyboard_row 2, 1           ; was: Ｎ-Ｚ
    keys_were_1to7  FW_N, FW_O, FW_P, FW_Q, FW_R, FW_S, FW_T
    keys_were_8to13 FW_U, FW_V, FW_W, FW_X, FW_Y, FW_Z
.area 26
    .halfword CH_1, CH_2, CH_3, CH_4, CH_5, CH_6, CH_7
    .halfword CH_8, CH_9, CH_0, CH_SPACE, CH_SPACE, CH_SPACE
.endarea

.org 0x02100E50
    keyboard_row 2, 2           ; was: ａ-ｍ
    keys_were_1to7  FW_LC_A, FW_LC_B, FW_LC_C, FW_LC_D, FW_LC_E, FW_LC_F, FW_LC_G
    keys_were_8to13 FW_LC_H, FW_LC_I, FW_LC_J, FW_LC_K, FW_LC_L, FW_LC_M
.area 26
    .halfword CH_Q, CH_W, CH_E, CH_R, CH_T, CH_Y, CH_U
    .halfword CH_I, CH_O, CH_P, CH_SPACE, CH_SPACE, CH_SPACE
.endarea

.org 0x02100E6C
    keyboard_row 2, 3           ; was: ｎ-ｚ
    keys_were_1to7  FW_LC_N, FW_LC_O, FW_LC_P, FW_LC_Q, FW_LC_R, FW_LC_S, FW_LC_T
    keys_were_8to13 FW_LC_U, FW_LC_V, FW_LC_W, FW_LC_X, FW_LC_Y, FW_LC_Z
.area 26
    .halfword CH_SPACE, CH_A, CH_S, CH_D, CH_F, CH_G, CH_H
    .halfword CH_J, CH_K, CH_L, CH_SPACE, CH_APOSTROPHE, CH_HYPHEN
.endarea

.org 0x02100EA4
    keyboard_row 2, 4           ; was: ０-９ ． ， and an ideographic space
    keys_were_1to7  FW_0, FW_1, FW_2, FW_3, FW_4, FW_5, FW_6
    keys_were_8to13 FW_7, FW_8, FW_9, FW_PERIOD, FW_COMMA, FW_SPACE
.area 26
    .halfword CH_SPACE, CH_SPACE, CH_Z, CH_X, CH_C, CH_V, CH_B
    .halfword CH_N, CH_M, CH_SPACE, CH_SPACE, CH_COMMA, CH_PERIOD
.endarea

.close
