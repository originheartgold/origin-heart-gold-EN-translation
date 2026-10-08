; outfit-chooser-strings - English labels in the outfit chooser of Oak's speech (overlay 58). D-0830, D-0831.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md; work/notes/hardcoded_text.md.
;
; The hack's outfit chooser (overlay 58, RAM 0x021E83C0, 0x7E0 bytes, no .bss) keeps its four list labels
; inside the overlay, as 0xFFFF-terminated strings packed back to back. The code copies each label into a
; String of capacity 16 (String_New(0x10) + CopyU16ArrayToString), so a label may have 15 characters.
;   确认   confirm, last list item   slot of 2 characters   loaded from the literal pool at +0x4E4
;   形象1/3/2  outfit 1, 3, 2         slots of 3 characters  read through the pointer table at +0x7C0
; 'OK' fits its slot and is written in place. 'Outfit 1/2/3' do not fit, so they are appended to the end of
; the overlay, the pointer table is repointed and the old slots are blanked. The overlay grows from 0x7E0 to
; 0x818 bytes; fix.toml [[grow]] allows 64, and the build updates its ramSize in the y9 overlay table.
;
; The English here must equal `en` of the [[string]] entries in fix.toml (translators and the text checks
; read it there): fixes.py check compares the literals, the build compares the bytes.

.nds
.include "../include/guards.inc"
.loadtable "../include/charmap.tbl", "UTF-8"     ; .string: game character codes, 0xFFFF end

.definelabel OutfitChooser_ConfirmLabelRef, 0x021E88A4   ; +0x4E4: u16 *, ldr'd for the 确认 item
.definelabel OutfitChooser_ConfirmLabel,    0x021E8AB0   ; +0x6F0: u16[3] 确认
.definelabel OutfitChooser_Outfit1Label,    0x021E8AB6   ; +0x6F6: u16[4] 形象1
.definelabel OutfitChooser_Outfit3Label,    0x021E8ABE   ; +0x6FE: u16[4] 形象3
.definelabel OutfitChooser_Outfit2Label,    0x021E8AC6   ; +0x706: u16[4] 形象2
.definelabel OutfitChooser_OutfitLabels,    0x021E8B80   ; +0x7C0: u16 *[3], list items 1, 2, 3
.definelabel Overlay58_End,                 0x021E8BA0   ; +0x7E0: end of the hack's overlay

.open "overlay58.bin", 0x021E83C0

; 确认 -> OK, in place. Its pointer stays.
expect32_abs OutfitChooser_ConfirmLabelRef, OutfitChooser_ConfirmLabel
.org OutfitChooser_ConfirmLabel
.area 3 * 2
    expect32_at 0, 0x0BB809B9                     ; 确认
    expect16_at 4, 0xFFFF
    .string "OK"
.endarea

; 形象1, 形象3, 形象2: the English is too long for these slots and moves to the end of the overlay.
.org OutfitChooser_Outfit1Label
.area 3 * 8
    expect32_at  0, 0x0BFB05C5                    ; 形象
    expect32_at  4, 0xFFFF0122                    ;     1
    expect32_at  8, 0x0BFB05C5                    ; 形象
    expect32_at 12, 0xFFFF0124                    ;     3
    expect32_at 16, 0x0BFB05C5                    ; 形象
    expect32_at 20, 0xFFFF0123                    ;     2
    .fill 3 * 8, 0xFF                             ; blank (0xFFFF: empty strings)
.endarea

.org OutfitChooser_OutfitLabels
.area 3 * 4
    expect32_at 0, OutfitChooser_Outfit1Label
    expect32_at 4, OutfitChooser_Outfit2Label
    expect32_at 8, OutfitChooser_Outfit3Label
    .word Outfit1Label_EN, Outfit2Label_EN, Outfit3Label_EN
.endarea

; Appended to the overlay, in the hack's order (1, 3, 2).
.org Overlay58_End
.area 64                                          ; fix.toml [[grow]] max
    expect_end
Outfit1Label_EN:
    .string "Outfit 1"
Outfit3Label_EN:
    .string "Outfit 3"
Outfit2Label_EN:
    .string "Outfit 2"
    .align 4, 0xFF                                ; the overlay stays a multiple of 4 bytes
.endarea

.close
