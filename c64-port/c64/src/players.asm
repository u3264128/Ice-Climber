; Independent player contexts; world, camera and enemies are shared.
context_vars:
        .byte lives,score_lo,score_hi,pxlo,pxhi,py,prevpy,curfloor
        .byte onground,vy,face,maxfloor,hammer_t,attack_t,air_init,fall_int
        .byte fall_frac,y_frac,rise_int,rise_frac,move_dir,walk_time,walk_frac,air_xfrac
        .byte skid_t,invul_t,pleft,pright,flow_frac,bonus_plat
        .byte score_top         ; (+30: score_mil, outside zero page)
CONTEXT_LEN = *-context_vars
        .assert CONTEXT_LEN <= PLAYER_SIZE, error, "Player context grew"

.segment "STARTUP"
runtime_init:
        lda #$22                ; original gravity $C839[0]
        sta nes_gravity
        lda #0
        sta fruit_seeded
        sta demo_round
        ldx #63
@patches:
        sta PATCH_FLAG,X        ; RAM above the loaded program starts random
        dex
        bpl @patches
        ldx #7
@glyphs:
        sta GLYPH_PHASE,X
        dex
        bpl @glyphs
        lda #1
        sta player_count
        sta selected_mountain
        lda #$FF
        sta input_prev
        sta input_prev+1
        sta input_joy
        sta input_joy+1
        sta stop_down
        sta last_view_row
        sta actor_mask
        rts
.segment "CODE"

context_store:
        lda player_index
        asl
        asl
        asl
        asl
        asl
        tax
        lda lives
        sta PLAYER_STATES+0,X
        lda score_lo
        sta PLAYER_STATES+1,X
        lda score_hi
        sta PLAYER_STATES+2,X
        lda curfloor
        sta PLAYER_STATES+7,X
        lda maxfloor
        sta PLAYER_STATES+11,X
        lda invul_t
        sta PLAYER_STATES+25,X
        lda pleft
        sta PLAYER_STATES+26,X
        lda pright
        sta PLAYER_STATES+27,X
        lda flow_frac
        sta PLAYER_STATES+28,X
        lda score_top
        sta PLAYER_STATES+31,X
        lda score_mil
        sta PLAYER_STATES+30,X
context_store_mutable:
        lda pxlo
        sta PLAYER_STATES+3,X
        lda pxhi
        sta PLAYER_STATES+4,X
        lda py
        sta PLAYER_STATES+5,X
        lda prevpy
        sta PLAYER_STATES+6,X
        lda onground
        sta PLAYER_STATES+8,X
        lda vy
        sta PLAYER_STATES+9,X
        lda face
        sta PLAYER_STATES+10,X
        lda hammer_t
        sta PLAYER_STATES+12,X
        lda attack_t
        sta PLAYER_STATES+13,X
        lda air_init
        sta PLAYER_STATES+14,X
        lda fall_int
        sta PLAYER_STATES+15,X
        lda fall_frac
        sta PLAYER_STATES+16,X
        lda y_frac
        sta PLAYER_STATES+17,X
        lda rise_int
        sta PLAYER_STATES+18,X
        lda rise_frac
        sta PLAYER_STATES+19,X
        lda move_dir
        sta PLAYER_STATES+20,X
        lda walk_time
        sta PLAYER_STATES+21,X
        lda walk_frac
        sta PLAYER_STATES+22,X
        lda air_xfrac
        sta PLAYER_STATES+23,X
        lda skid_t
        sta PLAYER_STATES+24,X
        lda bonus_plat
        sta PLAYER_STATES+29,X
        lda score_top           ; preserve the complete API's final A/N/Z
        rts

context_load:
        lda player_index
        asl
        asl
        asl
        asl
        asl
        tax
        lda PLAYER_STATES+1,X
        sta score_lo
        lda PLAYER_STATES+2,X
        sta score_hi
        lda PLAYER_STATES+7,X
        sta curfloor
        lda PLAYER_STATES+11,X
        sta maxfloor
        lda PLAYER_STATES+25,X
        sta invul_t
        lda PLAYER_STATES+26,X
        sta pleft
        lda PLAYER_STATES+27,X
        sta pright
        lda PLAYER_STATES+28,X
        sta flow_frac
        lda PLAYER_STATES+30,X
        sta score_mil
        lda PLAYER_STATES+31,X
        sta score_top
context_load_mutable:
        lda PLAYER_STATES+0,X
        sta lives
        lda PLAYER_STATES+3,X
        sta pxlo
        lda PLAYER_STATES+4,X
        sta pxhi
        lda PLAYER_STATES+5,X
        sta py
        lda PLAYER_STATES+6,X
        sta prevpy
        lda PLAYER_STATES+8,X
        sta onground
        lda PLAYER_STATES+9,X
        sta vy
        lda PLAYER_STATES+10,X
        sta face
        lda PLAYER_STATES+12,X
        sta hammer_t
        lda PLAYER_STATES+13,X
        sta attack_t
        lda PLAYER_STATES+14,X
        sta air_init
        lda PLAYER_STATES+15,X
        sta fall_int
        lda PLAYER_STATES+16,X
        sta fall_frac
        lda PLAYER_STATES+17,X
        sta y_frac
        lda PLAYER_STATES+18,X
        sta rise_int
        lda PLAYER_STATES+19,X
        sta rise_frac
        lda PLAYER_STATES+20,X
        sta move_dir
        lda PLAYER_STATES+21,X
        sta walk_time
        lda PLAYER_STATES+22,X
        sta walk_frac
        lda PLAYER_STATES+23,X
        sta air_xfrac
        lda PLAYER_STATES+24,X
        sta skid_t
        lda PLAYER_STATES+29,X
        sta bonus_plat
        lda score_top           ; preserve the complete API's final A/N/Z
        rts

; Only game_tick uses these entry points. Bonus setup/results retain the
; complete public context API. Its immutable fields stay in PLAYER_STATES;
; zero page retains player 0's values while player 1 advances. Lives is
; still loaded because game_tick checks it before the bonus handler.
play_context_store:
        lda state
        cmp #3
        beq @bonus
        jmp context_store
@bonus: lda player_index
        asl
        asl
        asl
        asl
        asl
        tax
        jmp context_store_mutable

.segment "DATA"
play_context_load:
        lda state
        cmp #3
        beq @bonus
        jmp context_load
@bonus: lda player_index
        asl
        asl
        asl
        asl
        asl
        tax
        jmp context_load_mutable

.segment "DATA"
players_setup:
        lda #0
        sta player_index
        sta player_hidden
        sta player_hidden+1
        sta bonus_out
        sta bonus_out+1
        jsr context_store
        lda game_mode
        clc
        adc #1
        sta player_count
        lda PLAYER_STATES+PLAYER_SIZE
        sta saved_nana
        lda PLAYER_STATES+PLAYER_SIZE+1
        sta saved_nana+1
        lda PLAYER_STATES+PLAYER_SIZE+2
        sta saved_nana+2
        lda PLAYER_STATES+PLAYER_SIZE+31
        sta saved_nana+3
        lda PLAYER_STATES+PLAYER_SIZE+30
        sta saved_nana_mil
        ldx #PLAYER_SIZE-1
@clone: lda PLAYER_STATES,X
        sta PLAYER_STATES+PLAYER_SIZE,X
        dex
        bpl @clone
        lda #220
        sta PLAYER_STATES+PLAYER_SIZE+3
        lda #1
        sta PLAYER_STATES+PLAYER_SIZE+10
        lda new_game
        bne @fresh
        lda saved_nana
        sta PLAYER_STATES+PLAYER_SIZE
        lda saved_nana+1
        sta PLAYER_STATES+PLAYER_SIZE+1
        lda saved_nana+2
        sta PLAYER_STATES+PLAYER_SIZE+2
        lda saved_nana+3
        sta PLAYER_STATES+PLAYER_SIZE+31
        lda saved_nana_mil
        sta PLAYER_STATES+PLAYER_SIZE+30
        jmp @done
@fresh: lda #3
        sta PLAYER_STATES+PLAYER_SIZE
        lda #0
        sta PLAYER_STATES+PLAYER_SIZE+1
        sta PLAYER_STATES+PLAYER_SIZE+2
        sta PLAYER_STATES+PLAYER_SIZE+30
        sta PLAYER_STATES+PLAYER_SIZE+31
@done:  lda #0
        sta new_game
        rts

.segment "CODE"
; Preserve the original entry for the VICE input fixture.
read_joy:
        lda $DC00
        sta input_joy
read_joy2:
        lda $DC01
        sta input_joy+1
        lda #$FF
        sta $DC02
        lda #0                  ; all rows: no key and no stick 1 line low
        sta $DC00               ; means no row has one either
        sta stop_down
        ldy #0                  ; (pause_down)
        lda $DC01
        cmp #$FF
        beq @no_key
        ldx #9                  ; W A S D SPACE: 1; I J K L right SHIFT: 2
@key:   lda key_rows,X
        sta $DC00
        lda $DC01
        and key_columns,X
        bne @up
        txa                     ; keys 5-9 belong to player 2
        cmp #5
        lda #0
        rol
        tay
        lda input_joy,Y
        and key_masks,X
        sta input_joy,Y
@up:    dex
        bpl @key
        ldy #0                  ; movement keys are not the pause key
        lda #$DF                ; P: pause
        sta $DC00
        lda $DC01
        and #2
        bne @stop
        iny
@stop:  lda #$7F                ; RUN/STOP: return to title
        sta $DC00
        lda $DC01
        and #$80
        eor #$80
        sta stop_down
@no_key:sty pause_down
@restore:
        lda #$FF
        sta $DC00
        lda #0
        sta $DC02
        ldx #1
@edge:  lda #0
        sta input_fire,X
        lda input_joy,X
        eor #$FF
        and input_prev,X
        ldy state
        cpy #1
        beq @play_edge
        cpy #3
        bne @menu_edge
@play_edge:
        and #$11                ; UP = jump + hammer; FIRE = ground swing
        bpl @action_edge
@menu_edge:
        and #$10                ; menu UP must never start the game
@action_edge:
        sta input_fire,X
@save:  lda input_joy,X
        sta input_prev,X
        dex
        bpl @edge
        lda pause_down
        beq @pause_save
        lda pause_prev
        bne @pause_save
        lda state
        cmp #1
        beq @pause
        cmp #3
        bne @pause_save
@pause: lda paused
        eor #1
        sta paused
        beq @unpause
        lda #MUSIC_PAUSE        ; $C0FA: the pause jingle; the music stops
        bne @request
@unpause:
        lda #MUSIC_UNPAUSE      ; $C0F1: the jingle, then the music again
@request:
        sta snd_music_req
@pause_save:
        lda pause_down
        sta pause_prev
        lda input_joy
        sta joy
        lda input_fire
        sta firehit
        jmp title_controls

; read_joy2: keyboard row, column and the joystick bit each key clears
; (up, left, down, right, fire).
.segment "DATA"
key_rows:    .byte $FD,$FD,$FD,$FB,$7F,$EF,$EF,$EF,$DF,$BF
.segment "HELPERS"
key_columns: .byte $02,$04,$20,$04,$10,$02,$04,$20,$04,$10
key_masks:   .byte $FE,$FB,$FD,$F7,$EF,$FE,$FB,$FD,$F7,$EF
.segment "CODE"

game_tick:
play_tick:
        jsr demo_input
        bcs @return
        lda paused
        beq @go
@return:rts
@go:    inc logic_frame
        lda state
        sta scene_before
        cmp #3
        beq @bonus_world
        lda normal_pan_t
        beq @normal_world
        jsr normal_pan_step
        rts
@normal_world:
        jsr environment_tick
        jmp @players
@bonus_world:
        lda bonus_reason        ; $CCED: after a catch or the timeout every
        beq @bonus_run          ; thing holds still for $4D slow ticks
        lda logic_frame
        lsr
        bcc :+
        dec bonus_end_wait
:       lda bonus_end_wait
        bne @held
        jmp enter_results
@held:  rts
@bonus_run:
        jsr bonus_world_tick
@players:
        lda #0
        sta player_index
@player:
        lda player_index        ; the preceding tick/render leaves P0 fully loaded
        beq @loaded
        jsr play_context_load
@loaded:
        ldx player_index
        lda input_joy,X
        sta joy
        lda input_fire,X
        sta firehit
        lda nes_dying,X         ; the original death runs instead ($D0AA)
        beq @living
        lda state
        cmp #1
        bne @living
        jsr player_dying_tick
        jmp @store
@living:
        lda lives               ; negative: out of the game
        bmi @store
        lda cam
        sta camera_before
        lda state
        cmp #3
        beq @bonus_player
        lda player_hidden,X
        beq @normal
        lda #0
        sta player_hidden,X
        lda normal_pan_dead,X
        beq @new_death
        lda #0
        sta normal_pan_dead,X
        lda lives               ; D463 already counted this life during the
        bpl @pan_respawn        ; pan; $EB8E brings back only a climber that
        lda player_count        ; is not out (lives not negative)
        cmp #2
        beq @camera             ; the other climber goes on
        jsr enter_game_over
        jmp @camera
@pan_respawn:
        jsr respawn_player
        jmp @camera
@new_death:
        jsr player_died
        jmp @camera
@normal:
        jsr normal_player_tick
@camera:
        jsr share_camera
        jmp @store
@bonus_player:
        jsr bonus_player_tick
@store: jsr play_context_store
        inc player_index
        lda player_index
        cmp player_count
        bcc @player
        lda state
        cmp #1
        beq @objects
        cmp #3
        bne @restore_p0
        jsr nes_bonus_bump      ; original $CCBC: $D212 after both climbers
        jsr bonus_after_players ; then the condor, fruit, timer, falls, camera
        jmp @restore_p0
@objects:
        jsr nes_objects_tick_all ; original $EFEC..$F838 after both players
@restore_p0:
        lda #0
        sta player_index
        sta input_fire
        sta input_fire+1
        lda player_count        ; one climber never left zero page
        cmp #2
        bne @loaded_back
        jsr play_context_load
@loaded_back:
        lda input_joy
        sta joy
        lda state
        cmp #3
        bne @normal_end
        lda bonus_reason        ; a catch or timeout ends after its wait
        bne @request
        lda bonus_out
        beq @request
        lda player_count
        cmp #1
        beq @bonus_failed
        lda bonus_out+1
        beq @request
@bonus_failed:
        lda #3
        sta bonus_reason
@results:
        jmp enter_results
@normal_end:
        cmp #1
        bne @done
        lda PLAYER_STATES       ; lives: negative only when out
        bpl @request
        lda player_count
        cmp #1
        beq @game_over
        lda PLAYER_STATES+PLAYER_SIZE
        bpl @request
@game_over:
        jmp enter_game_over
@request:
        lda state
        cmp #1
        bne @bonus_request
        jsr normal_pan_try
@bonus_request:
        lda bonus_requested
        beq @done
        lda #0
        sta bonus_requested
        jsr enter_bonus
@done:  rts

share_camera:
        lda player_count
        cmp #2
        bne @done
        lda cam
        sec
        sbc camera_before
        beq @done
        bcc @done
        sta work2
        lda player_index
        eor #1
        tax
        lda #0
        sta dst
        txa
        asl
        asl
        asl
        asl
        asl
        sta dst
        lda #>PLAYER_STATES
        sta dst+1
@shift: ldy #5
        lda (dst),Y
        clc
        adc #48
        bcs @lost
        cmp #232
        bcs @lost
        sta (dst),Y
        iny
        lda (dst),Y
        clc
        adc #48
        sta (dst),Y
        dec work2
        bne @shift
        rts

@lost:  lda #1
        sta player_hidden,X
@done:  rts

.include "normal_pan.asm"
