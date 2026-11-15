; Takeoff grace for a joystick: UP is both the jump and a stick direction.
; The NES latches the jump's horizontal motion when A is pressed, while the
; D-pad is usually already held. A diagonal push on a C64 stick or keyboard
; often reports UP one PAL frame before LEFT/RIGHT, which turned the jump
; into a vertical one that falls short of the ledge. When a jump left the
; ground without a direction and none was held, a direction arriving in its
; first three air ticks replays the original takeoff walk step ($CD95) and
; the missed air ticks. From then on the state equals a jump that had the
; direction at takeoff. Falls ($CD3B, air_init bit 7) and jumps from a stop
; with a held direction keep the original rules.
.segment "LOWCODE"
begin_jump:
        lda #0
        sta air_init
        sta onground
        lda #3
        sta rise_int
        lda #$A8
        sta rise_frac
        txa
        pha
        ldx player_index
        lda #0
        sta jump_grace,X
        lda move_dir            ; the takeoff step already latched it
        bne @armed
        jsr input_direction     ; held without motion: a stop keeps vertical
        bne @armed
        lda #3
        sta jump_grace,X
@armed: pla
        tax
        rts

; move_horizontal's air branch: A = move_dir, Z set when it is zero.
air_grace:
        lda move_dir
        bne @done
        ldx player_index
        lda jump_grace,X
        beq @none
        dec jump_grace,X
        lda air_init            ; a fall uses the original late steering
        bmi @none
        jsr input_direction
        beq @none
        sta move_dir            ; $CD95 at takeoff: new direction, one tick
        jsr face_motion
        lda hammer_t
        clc
        adc #1
        and #7
        sta hammer_t
        lda #1
        sta walk_time
        lda #2                  ; air ticks already flown without it
        sec
        sbc jump_grace,X
        tay
        lda #0
        sta jump_grace,X
        ldx #1
        lda walk_frac
        clc
        adc #$20
        sta walk_frac
        bcc :+
        inx
:       jsr horizontal_steps
@missed:
        dey
        bmi @moving
        lda air_xfrac           ; walk_time 1: the $45 standing-jump speed
        clc
        adc #$45
        sta air_xfrac
        bcc @missed
        jsr air_horizontal_step ; keeps Y
        jmp @missed
@moving:
        lda move_dir
        rts
@none:  lda #0
@done:  rts
.segment "CODE"
