; The NES mountain has green, brown and blue altitude bands. Switch the
; two VIC shared shades on the same pixel boundaries as the committed view.
.segment "EXTRA"
terrain_palette_latch:
        lda #0
        sta terrain_top_colour
        lda state
        cmp #3
        beq @snow
        lda visual_camera+1
        bne @snow
        lda visual_camera
        cmp #57
        bcc @brown
        inc terrain_top_colour
@brown: sec
        sbc #4                 ; row31 top: camera-1, IRQ three lines early
        bcc @early
        cmp #53
        bcs @middle
@early: lda #53
@middle:
        sta split_irq_lines
        lda visual_camera
        clc
        adc #140               ; row13 top: camera+143
        bcs @bottom
        cmp #245
        bcc @ground
@bottom:lda #246                ; sentinel: boundary below the visible window
@ground:sta split_irq_lines+1
        rts
@snow: lda #1
        sta terrain_top_colour
        lda #246
        sta split_irq_lines
        sta split_irq_lines+1
        rts

terrain_palette_top:
        lda #8                 ; brown mountain: yellow/orange/brown
        ldx #9
        ldy terrain_top_colour
        beq @set
        lda #14                ; snowy mountain: white/light blue/blue
        ldx #6
@set:   sta $D022
        stx $D023
        rts

; X=split stage0/1. Poll the boundary to keep sprite IRQ traffic from
; moving a palette change into a visible row. The IRQ only uses A/X/Y.
terrain_palette_split:
        lda split_irq_lines,X
        cmp #246
        beq @skip               ; no offscreen colour changes or busy wait
        clc
        adc #2
        tay
@wait:  cpy $D012
        bcs @wait
        cpx #0
        bne @green
        lda #8
        ldx #9
        bne @set
@green: lda #13
        ldx #5
@set:   sta $D022
        stx $D023
@skip:
        inc split_done
        rts
.segment "CODE"
