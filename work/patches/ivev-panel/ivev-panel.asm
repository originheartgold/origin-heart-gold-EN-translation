; ivev-panel - Summary IV/EV panel: the IV column clears the English stat labels. D-1574.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md.
;
; L on the summary stats page opens the hack's IV/EV panel, drawn by the hack's arm9 routine 0x0208C1A8
; (called only from the summary screen, at 0x02087EDC, 0x02088130 and 0x02089744). It prints the IV numbers
; right-aligned by 0x0208C154 at x = r2 + 24. With r2 = 0x1A they end at x 50, and the English labels
; ('Sp. Atk', 'Defense' = 41 px; bank 0295 #110-115, shared with the stats page) run into them.
; Both edits move the IV column and its header 6 px right. The labels and the EV column (r2 = 0x40 at
; 0x0208C278, 'EVs' header x 0x43 at 0x0208C210) are unchanged.

.nds
.thumb
.include "../include/guards.inc"

IV_SHIFT equ 6                  ; px: two-digit IVs clear 'Defense' by 3 px

.open "arm9.bin", 0x02000000

.org 0x0208C1E2                 ; the 'IVs' header (0295 #195)
.area 2
    expect16 0x2322             ; mov r3, #0x22   (x)
    mov     r3, #0x22 + IV_SHIFT
.endarea

.org 0x0208C262                 ; the IV numbers
.area 2
    expect16 0x221A             ; mov r2, #0x1A   (x - 24 of the right edge)
    mov     r2, #0x1A + IV_SHIFT
.endarea

.close
