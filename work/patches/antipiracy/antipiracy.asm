; antipiracy - Real hardware: the six DS Protect entry points return the genuine-cart values. D-1616, D-1617
; (main checkout's register). Why and what: fix.toml next to this file; work/notes/hardware_support.md.
;
; Overlay 114 is the hack's copy of Nintendo's DS Protect (card-mirror, emulator and integrity checks). Its six
; entry points are ARM code, reached only by 18 Thumb `blx` calls from overlays 1, 5, 28, 31 and 115. Each takes
; a callback in r0 and runs it when its result means "detected" (the bad entries) or "genuine" (the good ones);
; the "detected" callbacks leak heap 3 and start endless tasks, the "genuine" ones are a bare `bx lr`.
; Each stub returns what the untouched hack returns on a genuine cart or an emulator (DeSmuME: 0,1,0,1,0,1) and
; skips the callback. The integrity checks cover the check bodies only, not these prologues.

.nds
.arm
.include "../include/guards.inc"

PROLOGUE_0 equ 0xE92D47F0       ; push {r4-r10, lr}
PROLOGUE_1 equ 0xE24DD080       ; sub sp, sp, #0x80

GENUINE_ANY_BAD  equ 0          ; "any check detects": 0 on a genuine cart
GENUINE_ALL_GOOD equ 1          ; "all checks pass":   1 on a genuine cart

.macro stub, value
.area 8
    expect32 PROLOGUE_0
    expect32_at 4, PROLOGUE_1
    mov     r0, #value
    bx      lr
.endarea
.endmacro

.open "overlay114.bin", 0x02263200

.org 0x02263A64                 ; +0x864: card mirror + integrity, any bad
    stub GENUINE_ANY_BAD
.org 0x02263B4C                 ; +0x94C: card mirror + integrity, all good
    stub GENUINE_ALL_GOOD
.org 0x02263C34                 ; +0xA34: emulator + integrity, any bad
    stub GENUINE_ANY_BAD
.org 0x02263D1C                 ; +0xB1C: emulator + integrity, all good
    stub GENUINE_ALL_GOOD
.org 0x02263E04                 ; +0xC04: empty check list, any bad (already always 0)
    stub GENUINE_ANY_BAD
.org 0x02263ECC                 ; +0xCCC: empty check list, all good (already always 1)
    stub GENUINE_ALL_GOOD

.close
