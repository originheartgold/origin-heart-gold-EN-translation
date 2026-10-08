; guards.inc - check the bytes a fix replaces before it writes (armips v0.11.0).
;
; Every edit in a fix's .asm starts with a guard on the original bytes at the current address
; (org()). A guard reads the input file on disk (readu16 on outputname()), which still holds the
; original bytes while armips assembles: armips writes the file only after the last pass, and writes
; nothing at all when any .error fires. So if the Chinese ROM (or an earlier fix) changed these bytes,
; the build stops with the address and the bytes found, instead of patching the wrong code.
;
; File offset = address - headersize(): `.open "arm9.bin", 0x02000000` makes headersize() the load
; address of the opened file.
;
; Synthetic assembly: `asmpatch.py synthetic` (check.py, CI) assembles every source without the ROM, over
; zero-filled stand-ins of the right sizes (work/patches/sizes.toml), and passes `-definelabel GUARDS_OFF 1`
; so these guards check nothing there: it catches syntax errors and .area overflows, not wrong bytes. Nothing
; else may define GUARDS_OFF (fixes.py check refuses the name in every source and include, and asmpatch.py
; refuses it in a real build); the build never passes it, so its guards are always on.

; Stop the build: the bytes at `addr` are `found` (hex text), not `want` (hex text).
.macro guard_failed, addr, want, found
  .error "guard failed at " + tohex(addr, 8) + ": expected " + want + ", found " + found
.endmacro

; Stop the build: the opened file ends at `found` (hex text), not at the current address.
.macro end_guard_failed, found
  .error "guard failed at " + tohex(org(), 8) + ": the file ends at " + found + ", not here"
.endmacro

; The halfword at the current address + off must be `value`.
.macro expect16_at, off, value
  .if !defined(GUARDS_OFF) && readu16(outputname(), org() + (off) - headersize()) != (value)
    guard_failed org() + (off), tohex(value, 4), tohex(readu16(outputname(), org() + (off) - headersize()), 4)
  .endif
.endmacro

; The halfword at the current address must be `value` (one THUMB instruction or one u16).
.macro expect16, value
  expect16_at 0, value
.endmacro

; The word at the current address + off must be `value` (a pointer, or two halfwords).
.macro expect32_at, off, value
  .if !defined(GUARDS_OFF) && readu32(outputname(), org() + (off) - headersize()) != (value)
    guard_failed org() + (off), tohex(value, 8), tohex(readu32(outputname(), org() + (off) - headersize()), 8)
  .endif
.endmacro

; The word at absolute address `addr` must be `value` (read-only check of nearby data, e.g. a pointer table).
.macro expect32_abs, addr, value
  .if !defined(GUARDS_OFF) && readu32(outputname(), (addr) - headersize()) != (value)
    guard_failed addr, tohex(value, 8), tohex(readu32(outputname(), (addr) - headersize()), 8)
  .endif
.endmacro

; The word at the current address must be `value` (a pointer the edit replaces).
.macro expect32, value
  expect32_at 0, value
.endmacro

; The opened file must end at the current address: data appended here grows the file (and its overlay)
; from its original end, not from a size some other edit left behind.
.macro expect_end
  .if !defined(GUARDS_OFF) && filesize(outputname()) != org() - headersize()
    end_guard_failed tohex(filesize(outputname()) + headersize(), 8)
  .endif
.endmacro
