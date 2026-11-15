; Private verification codes and the original C460/C620 attract mode.
.segment "CODE"
title_reset:
        lda #0
        sta title_count
        sta title_timeout
        sta demo_active
        sta paused
        lda #15
        sta SID+$18
        lda #1
        sta selected_mountain
        rts

; Return a single matrix position, or FF on release. No text or sound.
title_key:
        lda #$FF
        sta $DC02
        ldx #0
        lda #$FE
title_key_row:   sta $DC00
        pha
title_key_columns:
        lda $DC01
        cmp #$FF
        bne title_key_column
        pla
        sec
        rol
        inx
        cpx #8
        bne title_key_row
        lda #$FF
        bne title_key_restore
title_key_column:
        ldy #0
title_key_bit:   lsr
        bcc title_key_found
        iny
        bne title_key_bit
title_key_found: pla
        txa
        asl
        asl
        asl
        sta tmp
        tya
        ora tmp
title_key_restore:
        pha
        lda #$FF
        sta $DC00
        lda #0
        sta $DC02
        pla
        rts

.segment "DATA"
title_code_tick:
        lda title_timeout
        beq @scan
        dec title_timeout
        bne @scan
        jsr title_reset
@scan:  jsr title_key
        cmp title_previous
        beq @done
        sta title_previous
        cmp #$FF
        beq @done
        ldx title_count
        bne @save
        ; W/S and I/K still select the player count; codes avoid these keys.
        cmp #9
        beq @done
        cmp #13
        beq @done
        cmp #33
        beq @done
        cmp #37
        beq @done
        cmp #60                ; SPACE / RUN/STOP / RSHIFT / P are controls
        beq @done
        cmp #63
        beq @done
        cmp #52
        beq @done
        cmp #41
        beq @done
        ldy #250               ; absolute five-second PAL deadline
        sty title_timeout
@save:  sta title_code,X
        lda #0
        sta attrlo
        sta attrhi
        inc title_count
        lda title_count
        cmp #4
        bne @done
        ldx #0
@code:  ldy #0
@char:  lda title_codes,X
        cmp title_code,Y
        bne @next
        inx
        iny
        cpy #4
        bne @char
        txa
        lsr
        lsr
        sta selected_mountain
        bne @clear
@next:  txa
        and #$FC
        clc
        adc #4
        tax
        bpl @code
        jsr title_reset
        rts
@clear: lda #0
        sta title_count
        sta title_timeout
@done:  lda title_count
        cmp #1                 ; suppress menu navigation during a code
        rts
title_codes:
.include "../build/title_codes.inc"

.segment "CODE"
demo_start:
        lda selected_mountain
        sta demo_saved
        lda demo_round
        and #3
        clc
        adc #1
        sta selected_mountain
        lda #0
        sta game_mode
        sta demo_index
        sta demo_remaining
        sta SID+$18            ; C460 mutes the demonstration
        lda #1
        sta demo_active
        jmp start_game

title_controls:
        lda state
        beq @done
        lda stop_down
        bne demo_return
        lda demo_active
        beq @done
        lda input_fire
        ora input_fire+1
        ora pause_down
        bne demo_return
@done:  rts

demo_return:
        lda demo_active
        pha
        jsr enter_title
        pla
        beq @clear
        inc demo_round
        lda demo_saved
        sta selected_mountain
@clear: lda #0
        sta input_fire
        sta input_fire+1
        sta firehit
        rts

; C620 runs before the original frame increment, with held AND pressed
; set to the scripted pad every tick. Translate A to UP and B to FIRE.
demo_input:
        lda demo_active
        beq @done
        lda state
        cmp #1
        bne @done
        lda py
        cmp #212+24
        bcs @end
        ldx demo_index
        lda demo_remaining
        bne @previous
        lda demo_pads,X
        pha
        and #$F0
        sta demo_remaining
        inx
        txa
        and #15
        sta demo_index
        pla
        jmp @decode
@previous:
        lda demo_pads-1,X
@decode:
        and #15
        tax
        lda demo_joy,X
@pad:   sta input_joy
        sta joy
        eor #$FF
        and #$11
        sta input_fire
        sta firehit
        lda logic_frame
        lsr
        bcs @done
        dec demo_remaining
@done:  clc
        rts
@end:   jsr demo_return
        sec
        rts
demo_joy:
        .byte $FF,$F7,$FB,$F3,$EF,$E7,$EB,$E3,$FE,$F6,$FA,$F2,$EE,$E6,$EA,$E2
        .byte $60              ; C60F: previous entry at a wrapped index0
demo_pads:
        .byte $11,$22,$11,$38,$29,$28,$19,$21
        .byte $1A,$28,$2A,$12,$2A,$22,$14,$12
.segment "CODE"
