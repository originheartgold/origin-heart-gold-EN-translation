; msgload - Text banks are read line by line (fixes the summary and bag memory crashes). D-1390, D-1002.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md; work/notes/heap_audit.md.
;
; NewMsgDataFromNarc(type, narc, bank, heap) (hack arm9 0x0200BA98) loads a message bank in one of two ways:
;   MSGDATA_LOAD_DIRECT (0)  the whole bank is read into the caller's heap
;   MSGDATA_LOAD_LAZY   (1)  a NARC handle; each line is read when it is asked for
; The English banks are 1.5-3x the size of the Chinese ones, so screens with a fixed-size heap that load
; whole banks ran out of memory (summary screen: -124 bytes, then a write through NULL into ITCM).
; Every MsgData function handles both types, and nothing outside them reads a loaded bank, so type 1 is
; safe everywhere. Same text; only where it is read from.

.nds
.thumb
.include "../include/guards.inc"

MSGDATA_LOAD_LAZY equ 1

.open "arm9.bin", 0x02000000

; All screens: NewMsgDataFromNarc keeps type 1 whatever the caller asked for (149 call sites used 0 in rc3).
.org 0x0200BA9A
.area 2
    expect16 0x1C05             ; add r5, r0, #0   (r5 = type)
    mov     r5, #MSGDATA_LOAD_LAZY
.endarea

; Second layer, kept in case the line above is ever dropped: the five call sites that were measured
; (memcheck.py) pass type 1 themselves.

.org 0x0208799A                 ; summary screen (heap 19): bank 0295, summary labels, 6916 -> 9972 bytes in English (call at 0x020879A0)
.area 2
    expect16 0x2000             ; mov r0, #0
    mov     r0, #MSGDATA_LOAD_LAZY
.endarea

.org 0x02087A0C                 ; summary screen (heap 19): bank 0739, move names, 15226 -> 27016 bytes (call at 0x02087A12)
.area 2
    expect16 0x2000             ; mov r0, #0
    mov     r0, #MSGDATA_LOAD_LAZY
.endarea

.close

.open "overlay17.bin", 0x021F86E0  ; the bag

.org 0x021F9020                 ; bag (heap 6): bank 0010, bag labels (call at 0x021F9028)
.area 2
    expect16 0x2000             ; mov r0, #0
    mov     r0, #MSGDATA_LOAD_LAZY
.endarea

.org 0x021F9050                 ; bag (heap 6): bank 0219, item names, 14252 -> 22524 bytes (call at 0x021F9058)
.area 2
    expect16 0x2000             ; mov r0, #0
    mov     r0, #MSGDATA_LOAD_LAZY
.endarea

.org 0x021F9062                 ; bag (heap 6): bank 0739, move names for the TM pocket; bank = 0xBE*4-0x15 (call at 0x021F906A)
.area 2
    expect16 0x2000             ; mov r0, #0
    mov     r0, #MSGDATA_LOAD_LAZY
.endarea

.close
