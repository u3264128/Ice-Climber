; Original $CD62 treats an isolated raw4 stone post as a non-supporting
; edge unless a neighbouring upper cell exists. Packed upper tag2 keeps
; that rule distinct from ordinary unbreakable rock (tag3).
.segment "EXTRA"
score_counts_reset:
        lda #0
        ldx #11                 ; both players' counters and ground swings
@clear: sta SCORE_COUNTS,X
        dex
        bpl @clear
        rts

; A=original result category. Store events until the mountain's results
; screen; physical landings and seals do not award invented point values.
score_event:
        sta work2
        lda player_index
        asl
        asl
        clc
        adc player_index
        clc
        adc work2
        tax
        lda work2
        cmp #4
        bne @count
        lda SCORE_COUNTS,X      ; $D91C caps broken-block count at99
        cmp #99
        bcs @done
@count: inc SCORE_COUNTS,X
@done:  rts

.segment "DATA"
; Original $D05D advances only its twenty-tick ground-B handler and pose.
; Keep the single-stick UP jump/hammer combination separate from optional B.
; C=1 suppresses ground movement, jump and retriggers for this logic tick.
ground_swing_tick:
        ldx player_index
        lda GROUND_SWING,X
        beq @input
        cmp #2
        bne @timer
        lda #1
        sta GROUND_SWING,X
@timer:
        lda attack_t
        cmp #2
        bcc @clear
        dec attack_t
        lda attack_t
        cmp #1
        bne @freeze
        lda hammer_t            ; D07C resets r60, retaining walk phase r6C
        and #6
        sta hammer_t
@freeze:
        lda skid_t              ; CB9D still runs during the frozen handler
        beq @frozen
        dec skid_t
@frozen:
        sec
        rts
@clear: lda #0
        sta attack_t
        sta GROUND_SWING,X      ; $D07C: handler 1 reads B in this tick
@input: lda firehit
        lsr                     ; a new UP wins ($CE43 follows $CDB0)
        bcs @normal
        lda onground
        beq @normal
        cmp #2
        beq @stop_b
        lda joy                 ; $CDB0 swings while B is held ($14)
        and #$10
        bne @normal
        lda #2                  ; CDB0 entry draws before the D05D sequence
        sta GROUND_SWING,X
        lda hammer_t
        and #1                  ; walking r60 is retained on normal B entry
        sta tmp
        lda #21
        sec
        sbc tmp
        sta attack_t
        jmp @freeze
@stop_b:
        lda firehit             ; $CFE2 reads a new press ($70)
        and #$10
        beq @normal
@stopping:
        jsr move_horizontal     ; CFC6 draws/steps before considering B
        cmp #2
        bne @frozen             ; finishing/lower stop ignores B this tick
        lda #0                  ; CFEF clears the old stop's run and clock
        sta skid_t
        sta move_dir
        sta walk_time
        sta hammer_t
        ldx player_index
        lda #1
        sta onground
        lda #2
        sta GROUND_SWING,X
        lda #21
        sta attack_t
        sec
        rts
@normal:
        clc
        rts
.segment "EXTRA"

; Original $CD3B: stepping off a platform keeps the vertical fraction,
; resets the airborne run-up to5 and advances two pixels in its latched
; direction. Treating it like a running jump made falls too fast sideways.
original_begin_fall:
        lda #0
        sta onground
        lda #$8C                ; age12 plus original $86 head-inhibit flag
        sta air_init
        lda #4
        sta fall_int
        lda #5
        sta fall_frac
        sta walk_time
        lda #3
        sta rise_int
        lda #$A8
        sta rise_frac
        ldx #2
        jmp horizontal_steps

support_upper_y:
        lda floor_upper,Y
        cmp #2
        bne @done
        lda floor_upper-1,Y
        ora floor_upper+1,Y
        beq @done
        lda #2
@done:  cmp #0
        rts
support_upper_x:
        lda floor_upper,X
        cmp #2
        bne @done
        lda floor_upper-1,X
        ora floor_upper+1,X
        beq @done
        lda #2
@done:  cmp #0
        rts

.segment "DATA"
air_horizontal_step:
        lda move_dir
        pha
        lda face                ; D648 can turn the body at a bonus wall
        clc
        adc #1
        sta move_dir
        ldx #1
        jsr horizontal_steps
        pla
        sta move_dir
        rts
.segment "CODE"
; A=C64 floor column; C=1 is the implicit stone outside source DBB4 bounds.
; Check the first foot before a cloud, then the second foot only if needed.
support_wall_column:
        sta coltmp
        lda #8
        ldx wrld
        cpx #2
        bcc @bound
        lda #9
        cpx #5
        bcc @bound
        lda #10
@bound:sta tmp
        lda coltmp
        cmp tmp
        bcc @wall
        lda #40
        sec
        sbc tmp
        cmp coltmp
        beq @wall
        bcc @wall
        clc
        rts
@wall: sec
        rts
