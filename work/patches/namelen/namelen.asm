; namelen - Name lengths: US limits (7 characters for trainers, 10 for Pokémon). D-0858.
; Why and what: fix.toml next to this file; overview work/patches/FIXES.md.
;
; The hack is built on the Japanese HeartGold, so every naming-screen call passes maxLen = 5 in r3:
; the direct calls of NamingScreen_CreateArgs (hack 0x02081DA4, US 0x020830D8) in Oak's speech, the
; egg hatch and kind 7, and the script commands' calls of CallTask_NamingScreen (hack 0x0203EDEC).
; The save buffers already have the US sizes; only the limit is Japanese. Each edit below changes the
; one instruction that loads maxLen.
; Box names (8) are unchanged; the hack has no battle-capture nickname prompt (D-1040).

.nds
.thumb
.include "../include/guards.inc"

TRAINER_NAME_LEN equ 7          ; US PLAYER_NAME_LENGTH: player, rival, group, kind 7
POKEMON_NAME_LEN equ 10         ; US POKEMON_NAME_LENGTH: nicknames

; ---------------------------------------------------------------------------------------------
; Oak's speech (hack overlay 49; US overlay 53)
.open "overlay49.bin", 0x021E4980

.org 0x021E49CE                 ; NamingScreen_CreateArgs(heap, NAME_SCREEN_PLAYER, 0, maxLen)
.area 2
    expect16 0x2305             ; mov r3, #5
    mov     r3, #TRAINER_NAME_LEN
.endarea

.org 0x021E49E6                 ; NamingScreen_CreateArgs(heap, NAME_SCREEN_RIVAL, 0, maxLen)
.area 2
    expect16 0x2305             ; mov r3, #5
    mov     r3, #TRAINER_NAME_LEN
.endarea

.close

; ---------------------------------------------------------------------------------------------
; Script commands and the egg hatch (arm9)
.open "arm9.bin", 0x02000000

.org 0x02042862                 ; script 'name player': CallTask_NamingScreen(.., PLAYER, 0, maxLen) (US 0x020431D6)
.area 2
    expect16 0x2305             ; mov r3, #5
    mov     r3, #TRAINER_NAME_LEN
.endarea

.org 0x02042892                 ; script 'name rival'
.area 2
    expect16 0x2305             ; mov r3, #5
    mov     r3, #TRAINER_NAME_LEN
.endarea

.org 0x0204291E                 ; script 'nickname Pokémon': gift/starter Pokémon, Name Rater (US 0x02043292)
.area 2
    expect16 0x2305             ; mov r3, #5
    mov     r3, #POKEMON_NAME_LEN
.endarea

.org 0x020490DA                 ; script 'name group' (kind 5): r1 holds 5 here
.area 2
    expect16 0x1C0B             ; add r3, r1, #0   (maxLen = r1 = 5)
    mov     r3, #TRAINER_NAME_LEN
.endarea

.org 0x02090944                 ; egg hatch: CreateArgs(heap, NAME_SCREEN_POKEMON, species, maxLen) (US 0x020911C4)
.area 2
    expect16 0x2305             ; mov r3, #5
    mov     r3, #POKEMON_NAME_LEN
.endarea

.close

; ---------------------------------------------------------------------------------------------
; Naming kind 7 (hack overlay 44; US overlay 43 0x0222CD5C; pret calls it NAME_SCREEN_UNK7)
.open "overlay44.bin", 0x02225F40

.org 0x02228DAC                 ; NamingScreen_CreateArgs(heap, 7, 0, maxLen)
.area 2
    expect16 0x2305             ; mov r3, #5
    mov     r3, #TRAINER_NAME_LEN
.endarea

.close
