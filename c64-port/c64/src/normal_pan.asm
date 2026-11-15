; Normal-stage camera: actual NES D7DE/D81F/D82F ordering. A grounded
; handler1 at the upper visible floor arms the pan AFTER that logic tick.
; Next twelve ticks freeze player/NPC handlers and move the view4pixels.
.segment "HIGH"
normal_pan_try:
        lda normal_pan_t        ; $D7DE: $8C, a pan is running
        jne @done
        lda bear_timer          ; $D7E2: the generic timer $3D, borrowing
        bne @find_start         ; from $2C, then the bear phase $7C
        lda bear_timer+1
        beq @bear
        dec bear_timer+1
        lda #$FF
        sta bear_timer
        rts
@bear:  lda NES_BEAR_PHASE
        bne @leave
        inc NES_BEAR_PHASE      ; $D7F5: request the bear
        rts
@leave: cmp #$80                ; $D816: the bear jumped, raise the view
        bne @find_start
        lda #0
        sta NES_BEAR_PHASE      ; $E215
        lda cam
        cmp #MAX_CAM
        jcs @done
        jmp normal_pan_start
@find_start:
        lda cam
        cmp #MAX_CAM
        jcs @done
        lda #0
        sta player_index
        tax
@find: lda PLAYER_STATES,X     ; lives: negative only when out
        jmi @next
        lda PLAYER_STATES+8,X
        cmp #1                  ; original handler1; handler3 is still stopping
        jne @next
        lda PLAYER_STATES+7,X
        sec
        sbc cam
        cmp #3
        jne @next
        ldy player_index
        lda GROUND_SWING,Y
        jne @next
        lda #1                  ; $D80F: a climber raised the view
        sta NES_PAN_FLAG
        jmp normal_pan_start
@next: txa
        clc
        adc #PLAYER_SIZE
        tax
        inc player_index
        lda player_index
        cmp player_count
        bcc @find
        lda #0
        sta player_index
@done: rts

normal_pan_start:
        lda #0
        sta tick_debt           ; no deferred old-frame logic may bypass the pan
        sta normal_pan_high
        sta normal_pan_high+1
        sta normal_pan_dead
        sta normal_pan_dead+1
        lda #12
        sta normal_pan_t
        inc cam
        lda #0
        sta player_index
        tax
@shift:
        lda PLAYER_STATES,X     ; out: negative lives
        bmi @shift_next
        lda PLAYER_STATES+5,X
        clc
        adc #48
        sta PLAYER_STATES+5,X
        bcc @previous
        ldy player_index
        lda #1
        sta normal_pan_high,Y
@previous:
        lda PLAYER_STATES+6,X
        clc
        adc #48
        sta PLAYER_STATES+6,X
        ldy player_index
        lda PLAYER_LAND_AGE,Y
        beq @shift_next
        lda PLAYER_LAND_Y,Y
        clc
        adc #48
        sta PLAYER_LAND_Y,Y
@shift_next:
        txa
        clc
        adc #PLAYER_SIZE
        tax
        inc player_index
        lda player_index
        cmp player_count
        bcc @shift
        lda #0
        sta player_index
        jmp context_load

normal_pan_step:
        jsr environment_timers  ; CB9D generic timers continue while8C freezes
        lda timer_divider
        bne @camera
        lda bear_timer          ; source generic3D stops at0; no D7DE borrow
        beq @camera
        dec bear_timer
@camera:
        jsr normal_pan_deaths   ; source CC5E D463 runs before this step's D82F
        lda normal_camera
        clc
        adc #4
        sta normal_camera
        bcc @players
        inc normal_camera+1
@players:
        ldx #0
        ldy #0
@player:
        lda PLAYER_STATES+25,X
        beq @skid
        dec PLAYER_STATES+25,X
@skid: lda PLAYER_STATES+24,X
        beq @stored
        dec PLAYER_STATES+24,X
@stored:
        txa
        clc
        adc #PLAYER_SIZE
        tax
        iny
        cpy player_count
        bcc @player
        lda PLAYER_STATES       ; all other player0 fields stayed frozen
        sta lives
        lda PLAYER_STATES+25
        sta invul_t
        lda PLAYER_STATES+24
        sta skid_t
        lda #0
        sta player_index
        sta input_fire
        sta input_fire+1
@count:jsr nes_pan_tick         ; $D82F: $EC51 and, last, the $D861 loop
        dec normal_pan_t
        bne @done
        ldx #0
@hide_dead:
        lda normal_pan_dead,X
        beq @next_dead
        lda #1
        sta player_hidden,X
@next_dead:
        inx
        cpx player_count
        bcc @hide_dead
        jsr reset_bear_timer    ; original D857 completes the pan, then D8FD
        lda maxfloor
        sta last_climb
@done: rts

.segment "CODE"
normal_pan_deaths:
        lda normal_pan_t
        asl
        asl
        sta work2               ; remaining camera distance (48..4 pixels)
        lda #0
        sta player_index
        tax
@player:
        lda PLAYER_STATES,X     ; out: negative lives
        bmi @next
        ldy player_index
        lda normal_pan_dead,Y
        bne @next
        lda PLAYER_STATES+5,X
        sec
        sbc work2
        sta tmp
        lda normal_pan_high,Y
        sbc #0
        bne @next
        lda tmp
        cmp #240
        bcc @next
        cmp #249                ; source bodyY+25 in $F1 <= Y < $FA
        bcs @next
        dec PLAYER_STATES,X
        lda #1
        sta normal_pan_dead,Y
@next: txa
        clc
        adc #PLAYER_SIZE
        tax
        inc player_index
        lda player_index
        cmp player_count
        bcc @player
        lda #0
        sta player_index
        rts
.segment "CODE"
