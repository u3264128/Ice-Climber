; ---------------------------------------------------------------------------
; Ice Climber C64 graphics and audio demo.
;
; Demonstrates:
;   * NES title screen reconstructed from PPU scripts (mixed hires/MC font).
;   * Popo in three hires layers, with walking frames in both directions.
;   * SID playback of converted NES music streams.
;     The logo_start song loops.
;
; Build with python build.py build --demo from the repository root.
; ---------------------------------------------------------------------------

; --- Zero-page variables (leave the KERNAL IRQ area $A0-$FF free) --------------
src     = $02           ; memcpy source / read pointer
dst     = $04           ; memcpy destination
mbase   = $06           ; Music blob base address
mhdr    = $08           ; Current song descriptor (2 bytes)
p1p     = $0A           ; Voice 1 stream (pulse melody)
p2p     = $0C           ; Voice 2 stream (pulse harmony)
p3p     = $0E           ; Voice 3 stream (triangle bass)
t1      = $10           ; Note counters
t2      = $11
t3      = $12
pitch   = $13
frame   = $14
songcur = $15
tmp     = $16

; --- VIC-II / SID -----------------------------------------------------------
SPR0X   = $D000
SPR0Y   = $D001
VMCSB   = $D018
SPRENA  = $D015
SPRMC   = $D01C
SPRMC1  = $D025
SPRMC2  = $D026
SPRCOL0 = $D027
RASTER  = $D012
SID     = $D400

.include "video.inc"
.include "../build/sprite_frames.inc"

; Music blob (tools/convert_music_c64.py):
;   +0            Song count
;   +1 ..         Per song: p2, p1, triangle offsets (16-bit LE), loop flag
;   +29  (64 B)   SID pulse frequency table
;   +93  (64 B)   SID triangle frequency table
;   +157 ..       Event streams: (pitch, duration); pitch 0 ends the stream
TBL_PULSE = 29
TBL_TRI   = 93

.segment "LOADADDR"
        .byte <$0801, >$0801

.segment "BASIC"
; 10 SYS 2062 jumps to $080E
        .byte $0C,$08,$0A,$00,$9E,$20,$32,$30,$36,$32,$00,$00,$00

.segment "CODE"

; ---------------------------------------------------------------------------
start:
        video_init
        lda #$18
        sta $D016
        lda #$01
        sta $D022
        lda #$0E
        sta $D023
        lda #<charset_src
        sta src
        lda #>charset_src
        sta src+1
        lda #<CHARSET
        sta dst
        lda #>CHARSET
        sta dst+1
        ldx #4
        jsr memcpy
        lda #<screen_src
        sta src
        lda #>screen_src
        sta src+1
        lda #<SCREEN
        sta dst
        lda #>SCREEN
        sta dst+1
        ldx #4
        jsr memcpy
        lda #<colram_src
        sta src
        lda #>colram_src
        sta src+1
        lda #<$D800
        sta dst
        lda #>$D800
        sta dst+1
        ldx #4
        jsr memcpy
        load_sprites
        lda #$01
        sta $D027
        lda #$0E
        sta $D028
        lda #$0A
        sta $D029
        sta $D02E
        lda #167
        sta $D00F
        lda #160
        sta $D001
        sta $D003
        sta $D005
        jsr music_init
        lda #$1B
        sta $D011

main_loop:
        jsr wait_frame
        inc frame
        lda frame
        and #$7F
        cmp #$40
        bcc @right
        lda frame
        and #$3F
        eor #$3F
        clc
        adc #90
        sta $D000
        lda #1
        sta tmp
        jmp @position
@right: lda frame
        and #$3F
        clc
        adc #90
        sta $D000
        lda #0
        sta tmp
@position:
        lda $D000
        sta $D002
        sta $D004
        lda frame
        lsr
        lsr
        and #2
        ora tmp
        tax
        lda demo_frames,X
        sta SCREEN+$3F8
        clc
        adc #1
        sta SCREEN+$3F9
        adc #1
        sta SCREEN+$3FA
        lda demo_mallet_frames,X
        sta SCREEN+$3FF
        lda $D000
        clc
        adc demo_mallet_x,X
        sta $D00E
        lda #$87
        sta SPRENA
        jsr music_tick
        jmp main_loop

demo_frames:
        .byte POPO_R_WALK0, POPO_L_WALK0, POPO_R_WALK1, POPO_L_WALK1
demo_mallet_frames:
        .byte MALLET_R_CARRY, MALLET_L_CARRY, MALLET_R_CARRY, MALLET_L_CARRY
demo_mallet_x:
        .byte 12, $FC, 12, $FC

; ---------------------------------------------------------------------------
wait_frame:
        lda #$FA
@w1:    cmp RASTER
        bne @w1                 ; Wait for raster line $FA
@w2:    cmp RASTER
        beq @w2                 ; Wait until the line passes: next frame
        rts

; memcpy: copy X * 256 bytes from src to dst (rounded up; padding is safe)
memcpy:
        ldy #$00
@loop:  lda (src),Y
        sta (dst),Y
        iny
        bne @loop
        inc src+1
        inc dst+1
        dex
        bne @loop
        rts

; ---------------------------------------------------------------------------
; SID music player
; ---------------------------------------------------------------------------
music_init:
        lda #$00
        ldx #24
@clear_sid:
        sta SID,X
        dex
        bpl @clear_sid
        lda #<music_src
        sta mbase
        lda #>music_src
        sta mbase+1
        lda #$00                ; Song 0: logo_start
        jsr song_select
        lda #$0F                ; Master volume; filter off
        sta SID + $18
        ; Pulse widths: voice 1 at 50% ($0800), voice 2 at 25% ($0400)
        lda #$00
        sta SID + $02
        sta SID + $09
        lda #$08
        sta SID + $03
        lda #$04
        sta SID + $09
        ; Envelopes: plucked pulse on voices 1/2, plain triangle on voice 3
        lda #$09                ; attack 0, decay 9
        sta SID + $05
        sta SID + $0C
        lda #$86                ; sustain 8, release 6
        sta SID + $06
        sta SID + $0D
        lda #$00                ; v3: attack 0, decay 0
        sta SID + $13
        lda #$0F                ; sustain 15, release 15
        sta SID + $14
        rts

; A = song index; load three stream pointers from the blob descriptor
song_select:
        sta songcur
        sta tmp
        asl                     ; A = index * 8 - index = index * 7
        asl
        asl
        sec
        sbc tmp
        clc
        adc #$01                ; Skip the song-count byte
        adc mbase               ; mhdr = mbase + 1 + idx*7
        sta mhdr
        lda mbase+1
        adc #$00
        sta mhdr+1
        ; Pulse 2 descriptor (+0) -> p2p
        ldy #$00
        lda (mhdr),Y
        clc
        adc mbase
        sta p2p
        iny
        lda (mhdr),Y
        adc mbase+1
        sta p2p+1
        ; p1 (+2) -> p1p
        iny
        lda (mhdr),Y
        clc
        adc mbase
        sta p1p
        iny
        lda (mhdr),Y
        adc mbase+1
        sta p1p+1
        ; tri (+4) -> p3p
        iny
        lda (mhdr),Y
        clc
        adc mbase
        sta p3p
        iny
        lda (mhdr),Y
        adc mbase+1
        sta p3p+1
        ; The first tick starts note 1
        lda #$01
        sta t1
        sta t2
        sta t3
        rts

; Each frame: decrement counters and fetch the next note for each voice
music_tick:
        jsr voice1
        jsr voice2
        jsr voice3
        rts

; --- Voice 1: pulse melody ($D400/$D402/$D404) --------------------------------
voice1:
        lda t1
        cmp #$01
        bne @v1a
        lda #$40                ; Clear the gate before the next note
        sta SID + $04
@v1a:   dec t1
        bne @out
        ldy #$00
        lda (p1p),Y             ; Pitch (0 ends the stream)
        beq @end1
        sta pitch
        iny
        lda (p1p),Y             ; Duration in frames
        sta t1
        iny                     ; Advance the pointer by 2 bytes
        tya
        clc
        adc p1p
        sta p1p
        bcc @v1b
        inc p1p+1
@v1b:   lda pitch
        cmp #$20                ; 32 = rest (duration only; gate off)
        beq @r1x
        asl
        clc
        adc #TBL_PULSE
        sta tmp
        lda mbase
        clc
        adc tmp
        sta src
        lda mbase+1
        adc #$00
        sta src+1
        ldy #$00
        lda (src),Y
        sta SID + $00           ; freq lo
        iny
        lda (src),Y
        sta SID + $01           ; freq hi
        bne @n1                 ; High byte != 0: play note
        dey
        lda (src),Y
        beq @r1                 ; Both bytes zero: rest
@n1:    lda #$41                ; Pulse waveform and gate on
        sta SID + $04
        jmp @out
@r1x:                                   ; Rest: gate off
@r1:    lda #$40
        sta SID + $04
        jmp @out
@end1:  lda #$40                ; End of stream: silence (voice 2 restarts the song)
        sta SID + $04
@out:   rts

; --- Voice 2: pulse harmony ($D407/$D40A/$D40B) -------------------------------
voice2:
        lda t2
        cmp #$01
        bne @v2a
        lda #$40
        sta SID + $0B
@v2a:   dec t2
        bne @out
        ldy #$00
        lda (p2p),Y
        beq @end2               ; End of voice 2 restarts the song
        sta pitch
        iny
        lda (p2p),Y
        sta t2
        iny
        tya
        clc
        adc p2p
        sta p2p
        bcc @v2b
        inc p2p+1
@v2b:   lda pitch
        cmp #$20                ; Rest?
        beq @r2x
        asl
        clc
        adc #TBL_PULSE
        sta tmp
        lda mbase
        clc
        adc tmp
        sta src
        lda mbase+1
        adc #$00
        sta src+1
        ldy #$00
        lda (src),Y
        sta SID + $07
        iny
        lda (src),Y
        sta SID + $08
        bne @n2
        dey
        lda (src),Y
        beq @r2
@n2:    lda #$41
        sta SID + $0B
        jmp @out
@r2x:
@r2:    lda #$40
        sta SID + $0B
        jmp @out
@end2:  lda songcur             ; Loop: restart the song
        jsr song_select
@out:   rts

; --- Voice 3: triangle bass ($D40E/$D412) ------------------------------------
voice3:
        lda t3
        cmp #$01
        bne @v3a
        lda #$10
        sta SID + $12
@v3a:   dec t3
        bne @out
        ldy #$00
        lda (p3p),Y
        beq @end3
        sta pitch
        iny
        lda (p3p),Y
        sta t3
        iny
        tya
        clc
        adc p3p
        sta p3p
        bcc @v3b
        inc p3p+1
@v3b:   lda pitch
        cmp #$20                ; Rest?
        beq @r3x
        asl
        clc
        adc #TBL_TRI
        sta tmp
        lda mbase
        clc
        adc tmp
        sta src
        lda mbase+1
        adc #$00
        sta src+1
        ldy #$00
        lda (src),Y
        sta SID + $0E
        iny
        lda (src),Y
        sta SID + $0F
        bne @n3
        dey
        lda (src),Y
        beq @r3
@n3:    lda #$11                ; triangle + gate
        sta SID + $12
        jmp @out
@r3x:
@r3:    lda #$10
        sta SID + $12
        jmp @out
@end3:  lda #$10                ; The bass does not restart by itself
        sta SID + $12
@out:   rts

; ---------------------------------------------------------------------------
.segment "DATA"
charset_src:
        .incbin "../../converted/charset/title_charset.bin"
colram_src:
        .incbin "../../converted/screens/title_c64.col"
        .res 24, 0
screen_src:
        .incbin "../../converted/screens/title_c64.bin"
        .res 24, 0
sprites_src:
        .incbin "../build/game_sprites.rle"
music_src:
        .incbin "../../converted/music/c64_music.bin"
