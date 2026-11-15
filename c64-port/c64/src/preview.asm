; Original title-start flyover: C3CC / C3E8 / D8EA / F737.
; The normal and bonus maps share height384. The preview advances638px,
; without running players, enemies, clouds, bonus timers or score counters.
; At preview_done, the caller masks the display and prepares normal play at
; the bottom, just as the NES returns through C1D7. There is no downward pan.
preview_camera = $0252
preview_camera_lo = $0252
preview_camera_hi = $0253
preview_bird_y = $0254
preview_anim_tick = $0255
preview_anim_frame = $0256
preview_hold = $0257
preview_timer_phase = $0258
preview_done = $0259
preview_scroll = $025A
preview_wraps = $025B

.segment "HIGH"
preview_init:
        jsr bonus_prepare_geometry
        lda #0
        ldx #7
@clear: sta preview_camera,X
        dex
        bpl @clear
        lda #224
        sta preview_bird_y
        lda #159
        sta preview_scroll
        lda #2
        sta preview_wraps
        lda #4
        sta state
        jmp topi_sprite_scene   ; the preview can draw any fruit type

; Once per logic tick. On PAL the flyover runs one tick per frame (not six
; per five), so the bird and the mountain move a constant 2 pixels a frame.
; The private descending timer reproduces CB9D without advancing NPC clocks.
preview_tick:
        lda preview_done
        beq :+
        rts
:       
        dec preview_timer_phase
        bpl @bird
        lda #10
        sta preview_timer_phase
        lda preview_hold
        beq @bird
        dec preview_hold
@bird: lda preview_bird_y
        cmp #29
        bcs :+
        jmp @hold
:       
        cmp #128
        bne @fly
        clc
        lda preview_camera_lo
        adc #2
        sta preview_camera_lo
        bcc :+
        inc preview_camera_hi
:       dec preview_scroll
        dec preview_scroll
        lda preview_scroll
        and #$F0
        cmp #$F0
        bne @last
        lda preview_scroll
        and #$EF
        sta preview_scroll
        dec preview_wraps
@last: lda preview_scroll
        cmp #2
        bcs @animate
        lda preview_wraps
        bne @animate
@fly:  dec preview_bird_y
        dec preview_bird_y
@animate:
        inc preview_anim_tick
        lda preview_anim_tick
        cmp #8
        bcc @return
        lda #0
        sta preview_anim_tick
        inc preview_anim_frame
        lda preview_anim_frame
        cmp #3
        bcc @return
        lda #0
        sta preview_anim_frame
@return:
        rts
@hold: lda preview_hold
        bne :+
        lda #16
        sta preview_hold
:       cmp #1
        bne @return
        sta preview_done
        rts
.segment "CODE"
