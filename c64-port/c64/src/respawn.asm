; Original EBFE uses DEB9, rather than the conditional standing-foot probe.
; Query the upper raw plane at NES X=respawn_col on zero-based floor=wrld.
; Air and immutable raw3 ledges return0; raw0 rock/raw1 ice/raw4 posts return1.
.segment "CODE"
respawn_visible_cloud_mask:
        lda levelidx
        asl
        clc
        adc levelidx
        sta work_lo
        lda cam
        lsr
        php                     ; odd/even camera chooses the packed half
        clc
        adc work_lo
        tax
        lda respawn_cloud_masks,X
        plp
        bcc @low
        lsr
        lsr
        lsr
@low:   and #7
        rts

respawn_upper_probe:
        lda respawn_col
        cmp #32
        bcc @solid
        cmp #224
        bcs @solid              ; DEB9 margins are fixed, unlike DBB4 feet
        lsr
        lsr
        lsr
        sec
        sbc #4
        sta work_lo
        ldx wrld
        clc
        adc floor_offsets,X
        tax
        lda floor_upper,X
        beq @air
        cmp #3
        bne @solid              ; even an isolated raw4 post is accepted here
        lda wrld
        asl
        asl
        asl
        asl
        asl
        clc
        adc work_lo
        sta work_lo             ; key=floor*32+inner column
        ldx levelidx
        lda respawn_ledge_offsets+1,X
        sta respawn_count
        ldy respawn_ledge_offsets,X
@ledge: cpy respawn_count
        beq @solid
        lda work_lo
        sec
        sbc respawn_ledge_starts,Y
        bcc @next
        sta work_hi
        tya
        lsr
        lsr
        tax
        lda respawn_ledge_lengths,X
        sta chartmp
        tya
        and #3
        tax
        lda chartmp
        cpx #0
        beq @length
@shift: lsr
        lsr
        dex
        bne @shift
@length:
        and #3                  ; packed length minus1
        cmp work_hi
        bcs @air
@next:  iny
        bne @ledge
@solid: lda #1
        rts
@air:   lda #0
        rts
.segment "DATA"
respawn_ledge_offsets:
        .incbin "../build/nes_respawn_ledges.bin",0,33
respawn_ledge_starts:
        .incbin "../build/nes_respawn_ledges.bin",33,139
respawn_ledge_lengths:
        .incbin "../build/nes_respawn_ledges.bin",172,35
respawn_cloud_masks:
        .incbin "../build/nes_respawn_cloud_masks.bin"
respawn_floor_bits:
        .byte 1,2,4
.segment "CODE"
