; The preview streams a 64-row ring: normal ground height0, bonus ground
; height384. Once row64 enters at the top, row0 is already off screen.
preview_last_row = $025C
preview_render_row = $025D
preview_height_lo = $025E
preview_height_hi = $025F

.segment "HIGH"
scene_tick:
        lda state
        cmp #4
        beq @preview
        jmp game_tick
@preview:
        sta scene_before
        jsr preview_tick
        lda preview_done
        beq @done
        lda #0
        sta $D011
        sta $D015
        sta $D01A
        lda #1
        sta state
        jsr setup_level
        lda #MUSIC_BACKGROUND   ; original gameplay music after C1D7 reset
        sta snd_music_req
@done:  rts

preview_cache_init:
        ; The original flyover hides sprite clouds; our software cloud
        ; equivalents must be absent too. Walls and numbered ledges remain.
        lda #<WORLD_CACHE
        sta src
        lda #>WORLD_CACHE
        sta src+1
        ldx #8
        ldy #0
@cell:  lda (src),Y
        cmp #CLOUD_FIRST
        bcc @next
        cmp #112
        bcs @next
        lda #BLANK
        sta (src),Y
@next:  iny
        bne @cell
        inc src+1
        dex
        bne @cell
        lda #0
        ldx #63
@flags: sta SAME2,X
        sta PATCH_FLAG,X
        dex
        bpl @flags
        sta patch_any
        lda #49                 ; F2EC replaces row50 with the bonus ground
        sta preview_last_row
        rts

preview_cache_stream:
        lda view_row
        clc
        adc #25                 ; include the next prefetch row
        cmp preview_last_row
        jcc @done
        jeq @done
        inc preview_last_row
        lda preview_last_row
        sta preview_render_row
        sec
        sbc #50
        sta preview_height_lo
        lda #0
        sta preview_height_hi
        asl preview_height_lo
        rol preview_height_hi
        asl preview_height_lo
        rol preview_height_hi
        asl preview_height_lo
        rol preview_height_hi
        lda preview_render_row
        and #63
        tax
        lda #ROW_EMPTY
        sta ROW_KIND,X
        sta SAME2,X
        txa
        and #7
        asl
        asl
        asl
        asl
        asl
        sta dst
        sta colptr
        txa
        lsr
        lsr
        lsr
        clc
        adc #>WORLD_CACHE
        sta dst+1
        clc
        adc #>(COLOUR_CACHE-WORLD_CACHE)
        sta colptr+1
        ldy #31
@clear: lda #BLANK
        sta (dst),Y
        lda #0
        sta (colptr),Y
        dey
        bpl @clear
        lda bonus_platform_ptr
        sta world_ptr
        lda bonus_platform_ptr+1
        sta world_ptr+1
        lda #0
        sta bonus_copy_index
@ledge:
        lda bonus_copy_index
        cmp bonus_platform_count
        jeq preview_cache_stream
        asl
        asl
        tay
        iny
        lda (world_ptr),Y
        sec
        sbc #4
        sta colw
        iny
        lda (world_ptr),Y
        sec
        sbc #4
        sta gapw
        iny
        lda (world_ptr),Y
        cmp preview_height_lo
        bne @next
        iny
        lda (world_ptr),Y
        cmp preview_height_hi
        bne @next
        lda preview_render_row
        and #63
        tax
        lda #ROW_FULL
        sta ROW_KIND,X
        ldy colw
@tile:  lda #STONE
        sta (dst),Y
        lda #9
        sta (colptr),Y
        iny
        cpy gapw
        bcc @tile
@next:  inc bonus_copy_index
        jmp @ledge
@done:  rts
.segment "CODE"
