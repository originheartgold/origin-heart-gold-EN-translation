; pcbox-name-width - PC box header: species-name window wide enough for 10 characters. D-1537, D-1511.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md.
;
; The PC box top screen builds its windows from a WindowTemplate table in overlay 16 (8 bytes each:
; bg, x, y, width, height, palette, base tile; all in tiles). The hack (Japanese base) makes the
; species-name window 7 tiles (56 px) wide, so 'Charmeleon' shows as 'Charmeleor'. The new values are
; the USA ones (US overlay14+0x12BB4 for [0]-[8], US overlay14+0x12C3C for [17]-[19]): the name window is 8 tiles
; (64 px, ending at the gender icon at x 128), and the bg-4 windows after it move their first tile up
; by 2, so bg-4 tiles run to 288 as in the USA ROM. Nothing else on the screen changes.

.nds
.thumb
.include "../include/guards.inc"

.definelabel PcBox_TopScreenWindows, 0x021F781C   ; WindowTemplate[22] (overlay 16 + 0x12E9C)

; struct WindowTemplate { u8 bg, x, y, width, height, palette; u16 baseTile; }
.macro window, bg, x, y, w, h, pal, base
  .byte bg, x, y, w, h, pal
  .halfword base
.endmacro

; The template at the current address is this one.
.macro window_was, bg, x, y, w, h, pal, base
  expect32_at 0, (bg) | (x) << 8 | (y) << 16 | (w) << 24
  expect32_at 4, (h) | (pal) << 8 | (base) << 16
.endmacro

.open "overlay16.bin", 0x021E4980

;                                  bg   x   y   w  h  pal  base
.org PcBox_TopScreenWindows + 0 * 8
.area 9 * 8
    window_was                      4,  8,  5,  7, 2, 15, 0x069   ; [0] species name: 7 tiles
    window                          4,  8,  5,  8, 2, 15, 0x069   ;     -> 8 tiles (64 px)
    window_was                      4,  1,  7,  8, 2, 15, 0x077   ; [1]
    window                          4,  1,  7,  8, 2, 15, 0x079   ;     base + 2
    window_was                      4,  4,  9,  6, 2, 15, 0x087   ; [2]
    window                          4,  4,  9,  6, 2, 15, 0x089
    window_was                      4,  1,  0, 30, 3, 15, 0x00F   ; [3] unchanged (its tiles come before the name)
    window                          4,  1,  0, 30, 3, 15, 0x00F
    window_was                      4, 16,  5,  2, 2, 15, 0x093   ; [4]
    window                          4, 16,  5,  2, 2, 15, 0x095
    window_was                      4,  1,  5,  6, 2, 15, 0x097   ; [5]
    window                          4,  1,  5,  6, 2, 15, 0x099
    window_was                      4,  1, 13,  8, 2, 15, 0x0A3   ; [6]
    window                          4,  1, 13,  8, 2, 15, 0x0A5
    window_was                      4,  1, 17, 11, 2, 15, 0x0B3   ; [7]
    window                          4,  1, 17, 11, 2, 15, 0x0B5
    window_was                      4,  1, 21, 12, 2, 15, 0x0C9   ; [8]
    window                          4,  1, 21, 12, 2, 15, 0x0CB
.endarea

; [9]-[16] are bg-6 windows: unchanged. The second bg-4 group follows.
.org PcBox_TopScreenWindows + 17 * 8
.area 3 * 8
    window_was                      4,  1, 11,  8, 2, 15, 0x0E1   ; [17]
    window                          4,  1, 11,  8, 2, 15, 0x0E3
    window_was                      4,  1, 15, 11, 2, 15, 0x0F1   ; [18]
    window                          4,  1, 15, 11, 2, 15, 0x0F3
    window_was                      4,  1, 19, 12, 2, 15, 0x107   ; [19]
    window                          4,  1, 19, 12, 2, 15, 0x109
.endarea

.close
