; Floor motion, idle bear, falling ice, and ROM-driven Nitpicker flight.
.segment "DATA"
flow_fraction:
        .byte $80,$A0,$C0,$E0,$00,$40,$80,$00
.segment "CODE"
flow_integer:
        .byte 0,0,0,0,1,1,1,2

environment_init:
        lda #0
        sta last_climb
        sta timer_divider
        jsr reset_bear_timer
        lda #$A5
        sta ice_seed
        jmp nes_stage_init      ; original seals, ice, bear phase and bird

random_step:
        lda ice_seed
        lsr
        bcc @save
        eor #$B8
@save:  sta ice_seed
        rts

environment_timers:
        jsr random_step
        ldx #1                  ; original $CB9D: the push timers $3A/$3B
@fast:  lda NES_PUSH_T,X        ; every tick
        beq :+
        dec NES_PUSH_T,X
:       dex
        bpl @fast
        inc timer_divider
        lda timer_divider
        cmp #11
        bcc @done
        lda #0
        sta timer_divider
        ldx #7                  ; original $CB9D: $48-$4F every eleventh tick
@slow:  lda NES_TIMERS,X
        beq @next
        dec NES_TIMERS,X
@next:  dex
        bpl @slow
@done:  rts

environment_tick:
        jsr environment_timers
        jsr cloud_update
        lda logic_frame
        and #7
        bne @bear
        ldx #7
@belt:  lda CHARSET+CONVEYOR_R*8,X
        lsr                     ; one multicolour pixel = two bits
        bcc :+
        ora #$80
:      
        lsr
        bcc @right
        ora #$80
@right: sta CHARSET+CONVEYOR_R*8,X
        lda CHARSET+CONVEYOR_L*8,X
        asl
        bcc :+
        ora #1
:
        asl
        bcc @left
        ora #1
@left:  sta CHARSET+CONVEYOR_L*8,X
        dex
        bpl @belt
@bear:  jmp bear_tick

; Floors 1-7: the two clouds of a cloud floor (slots F and F+8) move, then
; the floor is drawn once. Both clouds share the floor's flow, fraction and
; direction, so they move the same pixels (at most three: one character
; crossing at most) and a joined pair repaints once.
; Floors without clouds keep motion 0 (normal_cloud_init); the cloud
; floors are listed in CLOUD_FLOORS.
.segment "DATA"
cloud_update:
        ldy #0
@floor: ldx CLOUD_FLOORS,Y
        bne @cloud
        rts
@next:  ldy cloud_iter
        iny
        bne @floor
@cloud: sty cloud_iter
        lda floor_types,X
        and #7
        tay
        lda cloud_frac,X
        clc
        adc flow_fraction,Y
        sta cloud_frac,X
        sta cloud_frac+8,X
        lda flow_integer,Y
        adc #0
        bne @moves
        sta cloud_motion,X      ; no pixel this tick: nothing else changes
        sta cloud_motion+8,X
        beq @next
@moves: sta tmp
        stx cloud_slot
        lda cloud_x,X
        sta old_cloud_col
        lda cloud_x+8,X
        sta old_cloud_col2
        lda #0
        sta work2               ; character crossings
        lda cloud_dir,X         ; (both clouds share it)
        bne @left
        lda tmp
        sta cloud_motion,X
        sta cloud_motion+8,X
        clc
        adc cloud_subpixel,X
        cmp #8
        bcc :+
        sbc #8
        inc work2
        inc cloud_x,X
        ldy cloud_x,X
        cpy #36
        bcc :+
        pha
        lda #4
        sta cloud_x,X
        pla
:       sta cloud_subpixel,X
        lda tmp
        clc
        adc cloud_subpixel+8,X
        cmp #8
        bcc :+
        sbc #8
        inc work2               ; (second cloud: +2)
        inc work2
        inc cloud_x+8,X
        ldy cloud_x+8,X
        cpy #36
        bcc :+
        pha
        lda #4
        sta cloud_x+8,X
        pla
:       sta cloud_subpixel+8,X
        jmp @moved
@left:  lda #0
        sec
        sbc tmp
        sta cloud_motion,X
        sta cloud_motion+8,X
        lda cloud_subpixel,X
        sec
        sbc tmp
        bcs :+
        adc #8
        inc work2
        dec cloud_x,X
        ldy cloud_x,X
        cpy #4
        bcs :+
        pha
        lda #35
        sta cloud_x,X
        pla
:       sta cloud_subpixel,X
        lda cloud_subpixel+8,X
        sec
        sbc tmp
        bcs :+
        adc #8
        inc work2
        inc work2
        dec cloud_x+8,X
        ldy cloud_x+8,X
        cpy #4
        bcs :+
        pha
        lda #35
        sta cloud_x+8,X
        pla
:       sta cloud_subpixel+8,X
@moved: lda cloud_subpixel,X    ; new phases (also set again by a repaint)
        sta GLYPH_PHASE,X
        lda cloud_subpixel+8,X
        sta GLYPH_PHASE2,X
        lda work2
        bne @repaint
        jmp @next
@repaint:
        txa                     ; the cloud row below the view is never
        asl                     ; shown again (the view only rises)
        adc cloud_slot
        asl
        adc #CACHE_FLOOR_ROW
        cmp last_view_row
        bcs :+
        jmp @next
:       lda floor_types,X       ; two separate clouds (E0, never sharing a
        and #$E0                ; cell) when only one crossed: that one
        cmp #$E0
        bne @both
        lda work2
        cmp #3
        beq @both
        lsr                     ; C: the first cloud crossed
        ldx #0
        bcs :+
        ldx #8
:       lda cloud_slot
        jsr cloud_step_one
        ldx cloud_slot
        jmp @next
@both:  txa
        jsr cloud_step
        ldx cloud_slot
        jmp @next

normal_cloud_contact:
        ldx wrld
        lda cloud_x,X
        sec
        sbc #4
        asl
        asl
        asl
        clc
        adc cloud_subpixel,X
        sec
        sbc cloud_motion,X      ; original contact precedes this tick's motion
        sta gapw
        lda #26
        sta tmp
        jsr @one
        bcs @done
        lda cloud_x+8,X
        sec
        sbc #4
        asl
        asl
        asl
        clc
        adc cloud_subpixel+8,X
        sec
        sbc cloud_motion+8,X
        sta gapw
        lda floor_types,X
        and #$E0
        cmp #$C0
        lda #28
        bcc @width
        lda #27
@width:sta tmp
        jsr @one
@done: rts
@one:  lda gapw
        clc
        adc tmp
        sta work_hi             ; right endpoint also wraps as an NES byte
        lda #9
        ldy onground
        bne @offset
        ldy rise_int            ; source DC0E offsets only handlers2/4
        beq @default            ; head-hit handlers6/8 keep the centre probe
        ldy move_dir
        beq @offset
        lda cloud_dir,X
        beq @rightward
        cpy #1                  ; jumping right against a left-moving cloud
        bne @default
        lda #20
        bne @offset
@rightward:
        cpy #2                  ; jumping left against a right-moving cloud
        bne @default
        lda #4
        bne @offset
@default:
        lda #9
@offset:
        clc
        adc pxlo
        sec
        sbc #52
        cmp gapw
        bcc @no
        cmp work_hi
        bcc @yes
@no:   clc
        rts
@yes:  sec
        rts
.segment "CODE"

surface_motion:
        lda onground
        beq @done
        ldx curfloor
        lda floor_types,X
        and #$E0
        beq @done               ; ordinary ice has neither carry nor conveyor
        ; Use the player's completed move or landing probe. Rechecking
        ; after carrying would evaluate a different edge than NES $CD62.
        lda supflag
        cmp #2
        bne @belt
        lda cloud_motion,X
        jmp add_player_x
@belt:  lda floor_types,X
        and #$E0
        beq @done
        cmp #$80
        bcs @done
        lda floor_types,X
        and #7
        tay
        lda floor_types,X
        and #$E0
        cmp #$60
        bne @flow
        dey
        dey
        bpl @flow
        ldy #6
@flow:  lda flow_frac
        clc
        adc flow_fraction,Y
        sta flow_frac
        lda flow_integer,Y
        adc #0
        sta tmp
        lda floor_types,X
        and #$10
        beq @positive
        lda tmp
        eor #$FF
        clc
        adc #1
        jmp add_player_x
@positive:
        lda tmp
        jmp add_player_x
@done:  rts

add_player_x:
        sta tmplo
        lda #0
        ldx tmplo
        bpl @high
        lda #$FF
@high:  sta tmphi
        lda pxlo
        clc
        adc tmplo
        sta pxlo
        lda pxhi
        adc tmphi
        sta pxhi
        jmp clamp_x

bear_tick:
        lda maxfloor
        ldx player_count
        cpx #2
        bne @progress
        cmp PLAYER_STATES+32+11
        bcs @progress
        lda PLAYER_STATES+32+11
@progress:
        cmp last_climb
        bcc @timer
        beq @timer
        sta last_climb
        jsr reset_bear_timer
@timer: lda timer_divider       ; original $CB9D: $3D every eleventh tick;
        bne @done               ; $D7DE (normal_pan_try) borrows and spawns
        lda bear_timer
        beq @done
        dec bear_timer
@done:  rts

reset_bear_timer:
        ldx completed_mountains
        cpx #5
        bcc @value
        ldx #4
@value: lda original_bear_lo,X
        sta bear_timer
        lda #1
        sta bear_timer+1
        rts
original_bear_lo: .byte $80,$5D,$3E,$1F,$02

; NES $CC7E advances raw mountain0..98; its displayed layout cycles32.
original_advance_mountain:
        inc completed_mountains
        inc mountain
        lda mountain
        cmp #33
        bcc @limit
        lda #1
        sta mountain
        inc phase_counter
@limit: lda phase_counter
        cmp #3
        bcc @done
        lda mountain
        cmp #4
        bcc @done
        lda #0
        sta phase_counter
        lda #1
        sta mountain
@done:  rts
.segment "CODE"
