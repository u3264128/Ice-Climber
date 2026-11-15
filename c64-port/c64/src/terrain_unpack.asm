; The lossless assets share one decoder. It runs only with the
; display masked, leaving RAM for the time-critical gameplay routines.
.macro unpack_asset source_address, target_address, target_end
        lda #<source_address
        sta src
        lda #>source_address
        sta src+1
        lda #<target_address
        sta dst
        lda #>target_address
        sta dst+1
        lda #>(target_end)
        sta work2
        jmp unpack_asset_data
.endmacro
.segment "DATA"
unpack_terrain:
        unpack_asset terrain_packed_src, CHARSET, CHARSET+$800
unpack_title_colours:
        unpack_asset colram_src, $D800, $DC00
unpack_title_screen:
        unpack_asset screen_src, SCREEN, SCREEN+$400
.segment "CODE"
unpack_title_font:
        unpack_asset title_charset_src, CHARSET, CHARSET+$400
.segment "STARTUP"              ; boot only (the condor blocks have their own stream)
unpack_game_sprites:
        .assert SPRITE_PAGES = 32, error, "two 4KB sprite halves"
        .assert sprites_hi_src+0 >= $5000 && sprites_hi_src+0 < $6000, error, "upper stream below its output"
        .assert sprites_lo_src+0 < $5000, error, "lower stream below the sprites"
        lda #<sprites_hi_src
        sta src
        lda #>sprites_hi_src
        sta src+1
        lda #<(SPRITES+$1000)
        sta dst
        lda #>(SPRITES+$1000)
        sta dst+1
        lda #>(SPRITES+$2000)
        sta work2
        jsr unpack_asset_data
        unpack_asset sprites_lo_src, SPRITES, SPRITES+$1000
.segment "DATA"
unpack_asset_data:
        ldy #0
@pair:  lda (src),Y
        inc src
        bne @control
        inc src+1
@control:
        cmp #$80
        bcs @repeat
        tax
        inx
@literal:
        lda (src),Y
        inc src
        bne @store
        inc src+1
@store: sta (dst),Y
        inc dst
        bne @literal_count
        inc dst+1
@literal_count:
        dex
        bne @literal
        jmp @more
@repeat:
        and #$7F
        tax
        inx
        lda (src),Y
        sta tmp
        inc src
        bne @run
        inc src+1
@run:   lda tmp
        sta (dst),Y
        inc dst
        bne @count
        inc dst+1
@count: dex
        bne @run
@more:  lda dst+1
        cmp work2
        bne @pair
        rts
.segment "CODE"
