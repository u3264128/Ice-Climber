; Included from game.asm after the other sources.
.segment "STARTUP"
; Everything that runs once at power-up. It stays in the load buffer
; (VIDEO), which the title screen overwrites afterwards: the stack is
; reset here, so start jumps in and this jumps back.
boot:
        video_init
        lda #<nmi_rti           ; the vectors must not point into this buffer
        sta $FFFA
        sta $FFFE
        lda #>nmi_rti
        sta $FFFB
        sta $FFFF
        jsr install_helpers
        jsr runtime_init
        lda #$FF
        sta joyprev

        jsr unpack_game_sprites
        jsr topi_special_init
        lda #0
        sta topi_art_scene      ; the freshly unpacked Topi bank is normal
        sta condor_art_scene    ;source3E/46, before any preview XOR

        ; Player: three hires layers; Topi/bird: hires and MC.
        lda #$50                ; Sprites 4 and 6 use MC
        sta SPRMC
        lda #$01
        sta SPRMC1
        sta SPRCOL0             ; Player white details
        lda #14
        sta $D026
        lda #1
        lda #$0A
        sta $D029               ; Player skin
        sta $D02B               ; Topi details (individual MC colour)
        sta $D02D               ; Bird details
        sta $D02E               ; Sprite 7: hammer (NES palette value 3)
        lda #$0E
        sta $D028
        lda #$03
        sta $D02A               ; Topi seal colour
        lda #$04
        sta $D02C

        jsr sound_init
        jmp start_main
.segment "CODE"
nmi_rti:
        rti
