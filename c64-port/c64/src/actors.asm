; Logical sprites are grouped and scheduled onto the eight VIC channels.
; Players have priority. Enemy order rotates to reproduce bounded flicker
; when more than eight physical sprites would occupy one raster band.
REUSE = 46              ; lines between two sprites on one VIC sprite: 21
                        ; shown, then 24 lines for its next event (8 at once: 18)
TOPI_SPECIAL_PTR = FRUIT_L_1_0_0
TOPI_SPECIAL_VIC = $4000+TOPI_SPECIAL_PTR*64
TOPI_SPECIAL_RAM = $D100        ; spare I/O shadow pages $D1,$D2,$D3,$D5
TOPI_SPECIAL_LAST = $D500       ; avoid the game's SID address range at $D4
        .assert TOPI_SPECIAL_PTR = $AC .and FRUIT_L_8_0_0 = $BA,error,"Topi overlays fruit types 1..8"
.segment "EXTRA"
vic_bits:    .byte 1,2,4,8,16,32,64,128
vic_notbits: .byte $FE,$FD,$FB,$F7,$EF,$DF,$BF,$7F
popo_details:
        .byte POPO_R_WALK0_DETAIL,POPO_L_WALK0_DETAIL
        .byte POPO_R_WALK1_DETAIL,POPO_L_WALK1_DETAIL
        .byte POPO_R_JUMP_DETAIL,POPO_L_JUMP_DETAIL
        .byte POPO_R_HAMMER_DETAIL,POPO_L_HAMMER_DETAIL
        .byte POPO_R_ATTACK_DETAIL,POPO_L_ATTACK_DETAIL

.segment "CODE"
actors_reset:
        sei
        lda #0
        sta $D015
        sta $D01A
        jsr normal_condor_art
        jsr topi_sprite_scene
        lda #0
        sta fruit_seeded
        ldx #3
:       sta BONUS_SORT_COUNT,X
        dex
        bpl :-
        sta PLAYER_LAND_AGE
        sta PLAYER_LAND_AGE+1
        sta irq_count
        sta irq_index
        sta irq_start
        sta back_base
        sta logical_count
        sta scheduled_count
        sta pending_count
        sta pending_batch
        sta EVENT_BATCH
        sta EVENT_BATCH+EVENT_HALF
        sta actors_pan_active
        lda #<raster_irq
        sta $FFFE
        lda #>raster_irq
        sta $FFFF
        lda #1
        sta $D019
        lda #14
        sta $D026
        jsr priority_reset
        cli
        rts

actor_append:
        lda actor_yhi
        bne @no
        lda actor_y
        cmp #35                 ;21px sprite can enter the visible band at55
        bcc @no
        cmp #247                ;VIC border clips the bottom, not whole actors
        bcs @no
        lda actor_mask
        and actor_category
        beq @no
        ldx logical_count
        cpx #32
        bcs @no
        lda actor_xlo
        sta LOG_X,X
        lda actor_xhi
        sta LOG_XHI,X
        lda actor_y
        sta LOG_Y,X
        lda actor_ptr
        sta LOG_PTR,X
        lda actor_colour
        sta LOG_COL,X
        lda actor_mc
        sta LOG_MC,X
        lda actor_kind
        sta LOG_GROUP,X
        inc logical_count
        sec
        rts
@no:    clc
        rts

; Two-layer hires/MC object. X=body colour, Y=detail colour.
actor_pair:
        lda #1                  ; the detail layer is multicolour
        jmp pair_append

.segment "DATA"
; Both layers of a two-layer object at once: actor_append's checks once,
; then both entries (the second uses actor_ptr+1). X = first colour, Y =
; second colour, A = the second layer's multicolour flag. Leaves what two
; actor_append calls leave: actor_ptr+1, the last colour, kind 1, mc 0.
pair_append:
        sta pair_mc
        stx actor_colour
        sty actor_offset
        lda actor_yhi
        bne @done
        lda actor_y
        cmp #35                 ;21px sprite can enter the visible band at55
        bcc @done
        cmp #247
        bcs @done
        lda actor_mask
        and actor_category
        beq @done
        ldx logical_count
        cpx #31
        bcs @edge               ; room for one layer at most
        lda actor_xlo
        sta LOG_X,X
        sta LOG_X+1,X
        lda actor_xhi
        sta LOG_XHI,X
        sta LOG_XHI+1,X
        lda actor_y
        sta LOG_Y,X
        sta LOG_Y+1,X
        lda actor_ptr
        sta LOG_PTR,X
        clc
        adc #1
        sta LOG_PTR+1,X
        sta actor_ptr
        lda actor_colour
        sta LOG_COL,X
        lda actor_offset
        sta LOG_COL+1,X
        sta actor_colour
        lda pair_mc
        sta LOG_MC+1,X
        lda #0
        sta LOG_MC,X
        sta LOG_GROUP+1,X
        lda #2
        sta LOG_GROUP,X
        inx
        inx
        stx logical_count
@done:  lda #1
        sta actor_kind
        lda #0
        sta actor_mc
        rts
@edge:  lda #0                  ; the first layer alone, as actor_append does
        sta actor_mc
        lda #2
        sta actor_kind
        jsr actor_append
        bcc @done
        inc actor_ptr
        lda actor_offset
        sta actor_colour
        lda pair_mc
        sta actor_mc
        lda #0
        sta actor_kind
        jsr actor_append
        jmp @done
.segment "CODE"

; Logical coordinates (py, land_py ...) put the terrain 4 lines lower than
; the display does (VIEW_BIAS 7, cache row 6F+2); sprites follow the terrain.
SPRITE_VIEW_SHIFT = 4

; actor_y += view_delta (visual - target camera - SPRITE_VIEW_SHIFT, set
; once per frame by actors_prepare).
actor_view_y:
        lda actor_y
        clc
        adc view_delta
        sta actor_y
        lda actor_yhi
        adc view_delta+1
        sta actor_yhi
        rts
view_shift:
        lda actor_y
        sec
        sbc #SPRITE_VIEW_SHIFT
        sta actor_y
        bcs @done
        dec actor_yhi
@done:  rts

; A/X = unwrapped height above the current stage's ground.
actor_height:
        sta work_lo
        stx work_hi
        lda visual_camera
        clc
        adc #216
        sta actor_y
        lda visual_camera+1
        adc #0
        sta actor_yhi
        lda actor_y
        sec
        sbc work_lo
        sta actor_y
        lda actor_yhi
        sbc work_hi
        sta actor_yhi
        jmp view_shift

actors_prepare:
        lda state
        cmp #1
        bne @fresh
        lda normal_pan_t
        ora pan_step_frame      ; includes the last frozen step (timer now 0)
        beq @fresh
        lda actors_pan_active
        beq @first_pan
        jmp actors_pan_reuse
@first_pan:
        lda #1
        sta actors_pan_active
        bne @remember
@fresh: lda #0
        sta actors_pan_active
@remember:
        lda visual_camera
        sta actors_camera
        lda state
        cmp #1
        bne @camera_base
        lda cam                 ; logical floor jumps48 before its12tick pan
        asl
        sta work_lo
        asl
        clc
        adc work_lo
        asl
        asl
        asl
        sta work_lo             ; cam*48, up to240
        lda #0
        sta work_hi
        beq @delta
@camera_base:
        lda target_camera
        sta work_lo
        lda target_camera+1
        sta work_hi
@delta:
        lda visual_camera
        sec
        sbc work_lo
        tax
        lda visual_camera+1
        sbc work_hi
        sta view_delta+1
        txa
        sec
        sbc #SPRITE_VIEW_SHIFT
        sta view_delta
        bcs :+
        dec view_delta+1
:       lda #0
        sta logical_count
        sta scheduled_count
        sta player_index
        lda state
        jeq @schedule
        cmp #2
        jeq @schedule
        cmp #4
        bne @player
        jsr actor_preview
        jmp @schedule
@player:
        lda player_index        ; player 0 is already in zero page
        beq @loaded
        ldx #PLAYER_SIZE
        jsr actor_fields
@loaded:
        lda lives               ; negative: out of the game
        bpl @visible_player
        lda state
        cmp #1
        bne @next_player
        lda normal_pan_t
        beq @next_player
        ldx player_index
        lda normal_pan_dead,X   ;source OAM drifts off after its life is counted
        beq @next_player
@visible_player:
        ldx player_index
        lda state
        cmp #3
        bne @alive
        lda bonus_out,X
        bne @next_player
@alive: lda invul_t
        beq @draw
        lda logic_frame
        and #4
        beq @next_player
@draw:  jsr actor_player
@next_player:
        inc player_index
        lda player_index
        cmp player_count
        bcc @player
        ldx #0
        stx player_index
        lda player_count
        cmp #2
        bne @world
        jsr actor_fields        ; X = 0: restore what Nana's sprites overwrote
@world: lda logical_count
        sta player_sprites
        lda state
        cmp #3
        beq @bonus
        jsr actor_nes_objects
        lda state
        cmp #1
        bne @schedule
        jsr actor_debris
        jmp @schedule
@bonus: jsr actor_condor
        jsr actor_fruits
; One climber draws three exact hires layers. Nine or more sprites would
; make the multiplexer leave an enemy out: actor_player then draws the
; climber in the two layers that two climbers always use. It decides from
; the last frame's count, which falls by at most one per frame: enemies
; missing for a single frame do not bring the three layers back just
; before they return (nine sprites, one left out).
@schedule:
        lda logical_count
        sec
        sbc player_sprites
        bcs :+
        lda #0                  ; (no climbers drawn: player_sprites is stale)
:       cmp mux_others
        bcs @count
        dec mux_others          ; (fewer than last frame: one less)
        bcc @scheduled          ; (always)
@count: sta mux_others
@scheduled:
        jmp schedule_actors

; Original EC51 shifts existing OAM while D111 freezes the actor handlers.
; Keep its poses, ordering and blink phase; only move/clip existing sprites.
actors_pan_reuse:
        lda visual_camera
        sec
        sbc actors_camera
        sta work_lo
        lda visual_camera
        sta actors_camera
        ldx #0
        ldy #0
@sprite:
        cpx logical_count
        bcs @done
        lda LOG_Y,X
        clc
        adc work_lo
        bcs @next
        cmp #247
        bcs @next
        sta LOG_Y,Y
        lda LOG_X,X
        sta LOG_X,Y
        lda LOG_XHI,X
        sta LOG_XHI,Y
        lda LOG_PTR,X
        sta LOG_PTR,Y
        lda LOG_COL,X
        sta LOG_COL,Y
        lda LOG_MC,X
        sta LOG_MC,Y
        lda LOG_GROUP,X
        sta LOG_GROUP,Y
        iny
@next:  inx
        bne @sprite
@done:  sty logical_count
        stx tmp
        cpy tmp
        bne :+                  ; a sprite left the screen: schedule again
        jmp pan_shift_events
:       jmp schedule_actors

.segment "DATA"
; Pan frames after the first, with every sprite still on the screen: all
; moved by work_lo, so the schedule is the shown one (last frame's) with Y
; and the start lines moved too. Order, drops, VIC sprites and register
; values depend only on height differences; initial events keep line 0.
pan_shift_events:
        ldy irq_start           ; the shown schedule's batch
        lda EVENT_BATCH,Y
        sta pending_batch
        ldy back_base
        sta EVENT_BATCH,Y
        lda irq_count
        sec
        sbc irq_start
        sta scheduled_count
        sta pending_count
        beq @done
        ldx irq_start
        ldy back_base
@event: lda EVENT_SLOT,X
        sta EVENT_SLOT,Y
        lda EVENT_Y,X
        clc
        adc work_lo
        sta EVENT_Y,Y
        lda EVENT_LINE,X
        beq :+
        clc
        adc work_lo
:       sta EVENT_LINE,Y
        lda EVENT_X,X
        sta EVENT_X,Y
        lda EVENT_PTR,X
        sta EVENT_PTR,Y
        lda EVENT_COL,X
        sta EVENT_COL,Y
        lda EVENT_MSB,X
        sta EVENT_MSB,Y
        lda EVENT_MC,X
        sta EVENT_MC,Y
        lda EVENT_BG,X
        sta EVENT_BG,Y
        lda EVENT_ENA,X
        sta EVENT_ENA,Y
        inx
        iny
        cpx irq_count
        bne @event
@done:  rts
.segment "CODE"

; X = context offset: just the fields actors_prepare and actor_player read.
; game_tick ends with player 0's whole context loaded into zero page.
actor_fields:
        lda PLAYER_STATES+0,X
        sta lives
        lda PLAYER_STATES+3,X
        sta pxlo
        lda PLAYER_STATES+4,X
        sta pxhi
        lda PLAYER_STATES+5,X
        sta py
        lda PLAYER_STATES+8,X
        sta onground
        lda PLAYER_STATES+10,X
        sta face
        lda PLAYER_STATES+12,X
        sta hammer_t
        lda PLAYER_STATES+13,X
        sta attack_t
        lda PLAYER_STATES+14,X
        sta air_init
        lda PLAYER_STATES+20,X
        sta move_dir
        lda PLAYER_STATES+22,X
        sta walk_frac
        lda PLAYER_STATES+25,X
        sta invul_t
        rts

actor_player:
        ldx player_index
        lda nes_dying,X
        beq actor_player_alive
        ldy state
        cpy #1
        bne actor_player_alive
        jmp actor_player_dying
actor_player_alive:
        lda py
        sta work_lo             ; renderY may retain the original landing OAM
        lda #1
        sta actor_category
        sta actor_kind
        lda #0
        sta actor_mc
        sta animidx
        ldx player_index
        ldy PLAYER_LAND_AGE,X
        beq @physical_pose
        lda onground
        bne @latched_pose
        lda air_init
        and #$0F
        bne @jump               ; ordinary flight ignores previous OAM cache
@latched_pose:
        lda PLAYER_LAND_Y,X
        sta work_lo
        tya
        bpl @air_age_pose
        lda #18                 ; source CFC6 stop pose5, CHR$74
        jmp @set_attack
@physical_pose:
        lda onground
        beq @jump
@ground_pose:
        lda move_dir
        beq @idle
        jsr player_walk_pose
        sta animidx
        jmp @hammer
@idle:  ldx player_index
        lda GROUND_SWING,X
        beq @idle_foot
        cmp #2                  ; CDB0 entry draws the ordinary ground pose
        bne @hammer
        lda input_joy,X
        and #12
        cmp #12
        bne @hammer             ; held direction skips the original idle foot
@idle_foot:
        lda #16                 ; original idle foot patch from $CE29
        sta animidx
        bne @hammer
@jump:  lda state
        cmp #3
        beq @raised_jump
        lda air_init
        and #$0F                ; high bits are source head/foot flags
@air_age_pose:
        beq @ground_pose        ; CDB0 renders before accepting initial A
        cmp #12                 ; original $D04F uses pose6 for11ticks
        bcs @raised_jump
        lda #4
        bne @jump_pose
@raised_jump:
        lda #6                  ; original bonus $D552 uses pose7 ($92)
@jump_pose:
        sta animidx
@hammer:
@attack:
        ldx player_index
        lda GROUND_SWING,X       ; UP uses the actual A-jump body/mallet
        beq @pose
        cmp #2                  ; input entry precedes the D05D sequence
        beq @pose
        lda attack_t
        cmp #2                  ; original elapsed20 has returned to idle
        bcs @attack_phase
        cmp #1
        bne @pose
        lda #0                  ; original ground-B exits inpose0 evenifwalking
        beq @set_attack
@attack_phase:
        cmp #11                 ; original attack counter11..19: pose10
        bcc @strike
        cmp #15                 ; original counter7..10: pose9
        bcc @windup
        lda #6                  ; original counter1..6: pose7
        bne @set_attack
@windup:
        lda #8
        bne @set_attack
@strike:
        lda #10
@set_attack:
        sta animidx
@pose:  lda animidx
        ora face
        sta animidx
        tax
        lda popo_frames,X
        sta actor_ptr
        lda pxlo
        sta actor_xlo
        lda pxhi
        sta actor_xhi
        lda #0
        sta actor_yhi
        lda popo_y,X
        bpl @body_y
        dec actor_yhi
@body_y:
        clc
        adc work_lo
        sta actor_y
        lda actor_yhi
        adc #0
        sta actor_yhi
        jsr actor_player_view_y
        ldx animidx
        cpx #2
        bcc @compact_colour
        cpx #10
        bcc @layers
        cpx #12
        bcs @compact_colour
        ; Original $D17C lifts only the body eight pixels in pose10.
        ; Physical py and the separately positioned mallet do not move.
        lda actor_y
        sec
        sbc #8
        sta actor_y
        lda actor_yhi
        sbc #0
        sta actor_yhi
        jmp @compact_colour
@layers:
        lda player_count
        cmp #2
        beq @compact
        lda mux_others          ; five other sprites last frame: three layers
        cmp #5                  ; and a mallet would make nine
        bcs @compact
        lda #$11                ; white (the VIC reads four bits); $11 tells
        sta actor_colour        ; sched_drop that logical 0..2 are these
        jsr actor_append
        inc actor_ptr
        lda #14
        sta actor_colour
        jsr actor_append
        inc actor_ptr
        lda #10
        sta actor_colour
        jsr actor_append
        jmp @mallet
@compact:
        inc actor_ptr           ; the original blue hires layer
@compact_colour:
        lda #14
        ldx player_index
        beq @colour
        lda #4                  ; Nana's pink/purple parka
@colour:
        sta actor_colour
        jsr actor_append
        ldx animidx
        cpx #10
        bcc @detail_table
        inc actor_ptr           ; compact strike details follow its parka
        lda actor_ptr
        bne @detail_ready
@detail_table:
        lda popo_details,X
@detail_ready:
        sta actor_ptr
        jsr player_detail_offset
        lda #1
        sta actor_mc
        lda #10
        sta actor_colour
        jsr actor_append
        lda #0
        sta actor_mc
@mallet:
        lda state
        cmp #3
        beq @no_mallet          ; original bonus $D507 hides the mallet
        ldx animidx
        cpx #4                  ; idle/walking body already carries its club
        bcc @no_mallet
        cpx #12
        bcs @no_mallet
        lda mallet_frames,X
        sta actor_ptr
        lda pxlo
        clc
        adc mallet_xlo,X
        sta actor_xlo
        lda pxhi
        adc mallet_xhi,X
        sta actor_xhi
        lda #0
        sta actor_yhi
        lda mallet_y,X
        bpl @mallet_y
        dec actor_yhi
@mallet_y:
        clc
        adc work_lo
        sta actor_y
        lda actor_yhi
        adc #0
        sta actor_yhi
@mallet_view:
        jsr actor_player_view_y
        lda #10
        sta actor_colour
        jmp actor_append
@no_mallet:
        rts

; Original $D0AA: the last pose stays while the timer $32 is at least $10,
; then pose 11 (CHR $00); falling, $D086 turns CHR $68-$6D every fourth
; tick; nothing is drawn below the screen. One white hires layer.
actor_player_dying:
        cmp #3
        bcs @none               ; below the screen
        cmp #2
        beq @spin
        lda nes_death_t,X
        cmp #$10
        bcc @pose11
        jmp actor_player_alive
@pose11:
        ldy face
        lda death_frames,Y
        sta actor_ptr
        lda death_frames_y,Y
        jmp @draw
@spin:  ldy nes_spin,X
        lda death_spin_frames,Y
        sta actor_ptr
        lda death_spin_y,Y
@draw:  sta tmp                 ; signed offset, as popo_y
        clc
        adc py
        sta actor_y
        lda #0
        adc #0
        sta actor_yhi
        lda tmp
        bpl :+
        dec actor_yhi
:
        lda pxlo
        sta actor_xlo
        lda pxhi
        sta actor_xhi
        jsr actor_player_view_y
        lda #1
        sta actor_colour
        sta actor_kind
        sta actor_category
        lda #0
        sta actor_mc
        jmp actor_append
@none:  rts
death_frames: .byte DEATH_R, DEATH_L
death_frames_y: .byte DEATH_R_Y, DEATH_L_Y
death_spin_frames:
        .byte FRUIT_L_0_0_0, FRUIT_L_0_0_0+1, FRUIT_L_9_0_0, FRUIT_L_9_0_0+1
death_spin_y:
        .byte DEATH_SPIN0_Y, DEATH_SPIN1_Y, DEATH_SPIN2_Y, DEATH_SPIN3_Y

actor_player_view_y:
        lda state
        cmp #1
        bne @delta
        lda normal_pan_t
        beq @delta
        ldx player_index
        lda normal_pan_high,X   ;logicalpy crossed256 at the start of the pan
        beq @delta
        inc actor_yhi
@delta: jmp actor_view_y

topi_special_frames:
        .repeat 4,I
        .byte TOPI_SPECIAL_PTR+I*4,TOPI_SPECIAL_PTR+I*4+2
        .endrep

bear_top_frames:
        .byte BEAR_R_WALK0_0_0,BEAR_L_WALK0_0_0
        .byte BEAR_R_WALK1_0_0,BEAR_L_WALK1_0_0
        .byte BEAR_R_WALK2_0_0,BEAR_L_WALK2_0_0
        .byte BEAR_R_WALK1_0_0,BEAR_L_WALK1_0_0
        .byte BEAR_R_JUMP_0_0,BEAR_L_JUMP_0_0
bear_bottom_frames:
        .byte BEAR_R_WALK0_0_16,BEAR_L_WALK0_0_16
        .byte BEAR_R_WALK1_0_16,BEAR_L_WALK1_0_16
        .byte BEAR_R_WALK2_0_16,BEAR_L_WALK2_0_16
        .byte BEAR_R_WALK1_0_16,BEAR_L_WALK1_0_16
        .byte BEAR_R_JUMP_0_16,BEAR_L_JUMP_0_16
; The original objects ($EB2E): 0 Nitpicker, 1 bear, 2-4 seals, 5-7 ice
; blocks, 8-10 icicles. $03E8 holds the sprite slot (0: none, bit 7: being
; retired), $03DD the first CHR tile, $BD the direction. An original pixel
; at OAM (X, Y) is drawn at logical (X+56, Y+18), as for the climbers.
actor_nes_objects:
        lda frame
        and #7
        sta nes_draw            ; rotate the order for the multiplexer
        sta nes_draw_left       ; (the first object, where the round ends)
        tax
@object:
        lda NES_OBJ_ATTR,X      ; an object with a sprite slot (no retired
        beq @next               ; block, attribute bit 7)
        bmi @next
        and #$1F
        beq @next
        stx nes_draw
        jsr actor_nes_object
        ldx nes_draw
@next:  inx
        cpx #NES_OBJECTS
        bcc :+
        ldx #0
:       cpx nes_draw_left
        bne @object
        lda #0
        sta actor_mc
        lda #1
        sta actor_kind
        rts

; X = object with a sprite slot (actor_nes_objects checks its attribute).
actor_nes_object:
        lda NES_OBJ_X,X         ; art with a four-pixel margin: X+52
        clc
        adc #52
        sta actor_xlo
        lda #0
        adc #0
        sta actor_xhi
        ldy #0                  ; NES Y already follows each EC51 pan step.
        lda NES_OBJ_Y,X         ; Apply only the fixed C64 display origin.
        clc
        adc #16-SPRITE_VIEW_SHIFT
        sta actor_y
        bcc :+
        iny
:       sty actor_yhi
        lda NES_OBJ_ANIM,X
        sta tmp
        lda #1
        sta actor_kind
        lda #0
        sta actor_mc
        txa
        jeq nes_draw_bird
        cmp #1
        jeq nes_draw_bear
        cmp #5
        jcc nes_draw_topi
        jmp nes_draw_ice
@none:  rts

; $E0/$E4 flapping, $B2 falling. $BD bit 7 set: flying right.
nes_draw_bird:
        lda #2
        sta actor_category
        ldy #0
        lda tmp
        cmp #$E4
        bne :+
        ldy #2
:       cmp #$B2
        bne :+
        ldy #4
:       lda NES_OBJ_DIR
        bmi :+
        iny                     ; left
:       lda bird_frames,Y
        sta actor_ptr
        cpy #4
        bcs @falling
        ldx #4
        ldy #10
        jmp actor_pair
@falling:
        lda #1
        sta actor_mc
        lda #4
        sta actor_colour
        jmp actor_append

; Walking $18/$20/$28, jumping $98; 16x32 in two multicolour halves.
nes_draw_bear:
        lda actor_xlo           ; multicolour art without a margin: X+56
        clc
        adc #4
        sta actor_xlo
        bcc :+
        inc actor_xhi
:       lda actor_y
        clc
        adc #2
        sta actor_y
        bcc :+
        inc actor_yhi
:       ldy #8
        lda tmp
        cmp #$98
        beq @dir
        sec
        sbc #$18
        lsr
        lsr
        tay                     ; $18,$20,$28 -> 0,2,4
@dir:   lda NES_OBJ_DIR+1
        bpl :+
        iny                     ; walking left
:       sty byteidx
        lda bear_top_frames,Y
        sta actor_ptr
        lda #8
        sta actor_category
        lda #1
        sta actor_mc
        lda #$8A                ; $C777: normal ground objects behind terrain
        sta actor_colour
        jsr actor_append
        lda actor_y
        clc
        adc #16
        sta actor_y
        bcc :+
        inc actor_yhi
:       ldx byteidx
        lda bear_bottom_frames,X
        sta actor_ptr
        jmp actor_append

; Walking $A0/$A4/$A8; stunned $06 (the stars pose of the Topi pages).
nes_draw_topi:
        tax
        lda #2
        sta actor_category
        lda NES_OBJ_DIR,X
        bmi @left
        lda #0
        beq @facing
@left:  lda #1
@facing:
        sta byteidx
        lda tmp
        cmp #$06
        bne @walk
        ldy byteidx             ; the stars pose: right, left
        lda topi_special_frames,Y
        bne @pose
@walk:  sec
        sbc #$A0
        lsr                     ; $A0,$A4,$A8 -> 0,2,4
        ora byteidx
        tay
        lda topi_frames,Y
@pose:  sta actor_ptr
        jmp actor_topi_pair

; The original block debris (OAM $02D0-$02E7, $D91C/$D9CC), normal play
; only: 8x8 pieces in the condor blocks (debris_scene_art), tiles $0A and
; $0B in their four flips. Palette 2 is ice; palette 3 grass, or earth
; once $D9AD reloaded it. Drawing notes whether any piece still flies.
; The original drops the last OAM entries first on a crowded line; here
; the debris take only free hardware sprites. More than eight sprites need
; the multiplexer, whose time a frame with two logic ticks does not have.
actor_debris:
        lda debris_any          ; only a new piece sets it
        beq @done
        lda actor_mask          ; (the tests' category mask, actor_append)
        and #8
        beq @done
        lda #0
        sta debris_any
        ldy #24
@next:  dey
        dey
        dey
        dey
        bpl @slot
@done:  rts
@slot:  lda NES_DEBRIS_OAM,Y
        cmp #$F8
        beq @next
        sta debris_any
        ldx logical_count       ; free hardware sprites only
        cpx #8
        bcs @done
        clc                     ; EC95 already moves debris with the screen.
        adc #18-SPRITE_VIEW_SHIFT
        sta LOG_Y,X
        bcs @next
        cmp #35
        bcc @next
        cmp #247
        bcs @next
        lda NES_DEBRIS_OAM+3,Y  ; X+56
        clc
        adc #56
        sta LOG_X,X
        lda #0
        adc #0
        sta LOG_XHI,X
        lda NES_DEBRIS_OAM+2,Y  ; flips (bits 6-7) pick the block
        asl
        rol
        rol
        and #3
        sta tmp
        lda NES_DEBRIS_OAM+1,Y
        lsr                     ; C = tile $0B: four blocks on
        lda tmp
        bcc :+
        adc #3
:       adc #DEBRIS_BLOCK
        sta LOG_PTR,X
        lda NES_DEBRIS_OAM+2,Y
        lsr
        lda #14                 ; palette 2 ($3F18: $30 $21 $12)
        bcc @colour
        lda #5                  ; palette 3 ($3F1C: $38 $29 $0A)
        bit debris_brown
        bvc @colour
        lda #8                  ; $D9AD: $27 $17 $07
@colour:sta LOG_COL,X
        lda #1
        sta LOG_MC,X
        sta LOG_GROUP,X
        inc logical_count
        jmp @next

; Ice blocks ($AC, shards $12/$14) and icicles ($10/$0E/$0C).
nes_draw_ice:
        lda actor_xlo           ; multicolour art without a margin
        clc
        adc #4
        sta actor_xlo
        bcc :+
        inc actor_xhi
:       lda actor_y
        clc
        adc #2
        sta actor_y
        bcc :+
        inc actor_yhi
:       ldy #5
@art:   lda tmp
        cmp nes_ice_tiles,Y
        beq @found
        dey
        bne @art                ; (unknown tiles show the ice block)
@found: lda NES_OBJ_DIR,X       ; $C7C1 mirrors when $BD is positive
        asl                     ; C = negative
        tya
        rol
        eor #1                  ; 2*tile, +1 when mirrored
        clc
        adc #TOPI_SPECIAL_PTR+4 ; Topi pages 1-3
        sta actor_ptr
        lda #8
        sta actor_category
        lda #1
        sta actor_mc
        lda #6                  ; NES palette 2: white, light blue, dark blue
        cpx #8                  ; ground ice behind; falling icicles in front
        bcs :+
        ora #$80
:
        sta actor_colour
        jmp actor_append
; Pages 1-3 hold each tile unmirrored, then mirrored ($BD positive).
nes_ice_tiles: .byte $AC,$10,$0E,$0C,$12,$14

condor_left:
        .byte CONDOR_R_FLAP0_0_0,CONDOR_L_FLAP0_0_0
        .byte CONDOR_R_FLAP1_0_0,CONDOR_L_FLAP1_0_0
        .assert CONDOR_R_FLAP0_24_0=CONDOR_R_FLAP0_0_0+1,error,"Condor halves must be consecutive"
        .assert CONDOR_L_FLAP0_24_0=CONDOR_L_FLAP0_0_0+1,error,"Condor halves must be consecutive"
        .assert CONDOR_R_FLAP1_24_0=CONDOR_R_FLAP1_0_0+1,error,"Condor halves must be consecutive"
        .assert CONDOR_L_FLAP1_24_0=CONDOR_L_FLAP1_0_0+1,error,"Condor halves must be consecutive"
; Original $F7A2: the condor is drawn (at source Y $D7 = $15, screen-fixed)
; only while the stage shows its top (scroll 0, page 0: camera 240).
actor_condor:
        lda bonus_camera
        cmp #240
        beq :+
        rts
:       jsr normal_condor_art
        lda #4
        sta actor_category
        lda #1
        sta actor_kind
        sta actor_mc
        lda #10
        sta actor_colour
        lda condor_xlo
        sta actor_xlo
        lda condor_xhi
        sta actor_xhi
        lda condor_dir
        eor #1
        sta tmp
        lda logic_frame
        lsr
        lsr
        and #2
        ora tmp
        tax
        lda condor_left,X
        sta actor_ptr
        lda #<426               ; at camera 240: C64 sprite Y = source Y+5
        ldx #>426
        jsr actor_height
        jsr actor_append
        lda actor_xlo
        clc
        adc #24
        sta actor_xlo
        lda actor_xhi
        adc #0
        sta actor_xhi
        inc actor_ptr
        jsr actor_append
        lda #0
        sta actor_mc
        rts

fruit_frames:
        .byte FRUIT_L_0_0_0,FRUIT_L_1_0_0,FRUIT_L_2_0_0,FRUIT_L_3_0_0,FRUIT_L_4_0_0
        .byte FRUIT_L_5_0_0,FRUIT_L_6_0_0,FRUIT_L_7_0_0,FRUIT_L_8_0_0,FRUIT_L_9_0_0
fruit_colours: .byte 6,8,8,7,2,7,13,5,8,2
fruit_details:.byte 4,5,4,5,5,5,5,5,5,7
; Preview objects are screen-relative source OAM, independent of the
; continuously ascending mountain. Source$C3CC fixes condorX at$70.
actor_preview:
        lda preview_anim_frame
        cmp #2
        beq @third
        jsr normal_condor_art
        lda preview_anim_frame
        asl
        ora #1                 ;left-facing source3E/46
        bne @frame
@third: lda #1
        jsr set_condor_art
        lda #1                 ;third wing pose is in the left FLAP0 slots
@frame: tax
        lda condor_left,X
        sta actor_ptr
        lda #4
        sta actor_category
        lda #1
        sta actor_kind
        sta actor_mc
        lda #10
        sta actor_colour
        lda #164
        sta actor_xlo
        lda #0
        sta actor_xhi
        sta actor_yhi
        lda preview_bird_y
        clc
        adc #30                ;preview frames the192line VIC viewport
        sta actor_y
        jsr actor_append
        lda #188
        sta actor_xlo
        inc actor_ptr
        jsr actor_append
        lda #174
        sta actor_xlo
        lda preview_bird_y
        clc
        adc #44                ;source carriedfruit birdY+14, viewport+30
        sta actor_y
        lda completed_mountains
@mod10: cmp #10
        bcc @type
        sbc #10
        bcs @mod10
@type:  tax
        lda fruit_frames,X
        sta actor_ptr
        lda fruit_colours,X
        pha
        lda fruit_details,X
        tay
        pla
        tax
        jmp actor_pair

normal_condor_art:
        lda #0
set_condor_art:
        cmp condor_art_scene
        beq @done
        sta condor_art_scene
        lda #2                 ;same lossless256byte XOR decoder asTopi
        jmp xor_topi_patch
@done:  rts

.segment "DATA"
; X is animidx. Only the MC detail layer moves; body and mallet stay exact.
player_detail_offset:
        lda popo_detail_x,X
        beq @done
        inc actor_xlo
        bne @done
        inc actor_xhi
@done:  rts
.segment "PRIOCODE"
popo_detail_x:
        .byte POPO_R_WALK0_DETAIL_X,POPO_L_WALK0_DETAIL_X
        .byte POPO_R_WALK1_DETAIL_X,POPO_L_WALK1_DETAIL_X
        .byte POPO_R_JUMP_DETAIL_X,POPO_L_JUMP_DETAIL_X
        .byte POPO_R_HAMMER_DETAIL_X,POPO_L_HAMMER_DETAIL_X
        .byte POPO_R_ATTACK_DETAIL_X,POPO_L_ATTACK_DETAIL_X
        .byte POPO_R_STRIKE_DETAIL_X,POPO_L_STRIKE_DETAIL_X
        .byte POPO_R_WALK2_DETAIL_X,POPO_L_WALK2_DETAIL_X
        .byte POPO_R_WALK0_DETAIL_X,POPO_L_WALK0_DETAIL_X
        .byte POPO_R_IDLE_DETAIL_X,POPO_L_IDLE_DETAIL_X
        .byte POPO_R_STOP_DETAIL_X,POPO_L_STOP_DETAIL_X
.segment "DATA"
actor_fruits:
        lda #4
        sta actor_category
        lda actor_mask
        and #4
        bne :+
        rts
:       ; Shared append flags stay constant for all four fruit.
        ; The four fruit share one type, and one world-to-screen base.
        jsr fruit_get_type
        lda visual_camera
        clc
        adc #216-SPRITE_VIEW_SHIFT
        sta bonus_base
        lda visual_camera+1
        adc #0
        sta bonus_base+1
        lda #1
        sta actor_kind
        lda #0
        sta actor_mc
        sta ui_index
@fruit: lda ui_index
        clc
        adc frame
        and #3
        tax
        stx ui_col
        lda fruit_mask
        and fruit_bits,X
        beq @next
        lda bonus_base
        sec
        sbc fruit_hlo,X
        sta actor_y
        lda bonus_base+1
        sbc fruit_hhi,X
        bne @next
        lda actor_y
        cmp #35
        bcc @next
        cmp #247
        bcs @next
        ldx logical_count
        cpx #31
        bcc @pair
        bne @next
        jsr fruit_append_single ; preserve actor_pair's final half at slot31
        jmp @next
@pair:  jsr fruit_append_pair
@next:  inc ui_index
        lda ui_index
        cmp #4
        bcc @fruit
        rts

.segment "EXTRA"
; X=logical count<31; actor_y is visible, category4 is enabled. Both
; layers have the same coordinates, so clipping is performed only once.
fruit_append_pair:
        ldy ui_col
        lda fruit_x,Y
        sta LOG_X,X
        sta LOG_X+1,X
        lda actor_y
        sta LOG_Y,X
        sta LOG_Y+1,X
        txa
        lsr
        bcc :+
        lda #0                  ; odd synthetic prefixes can overwrite seed pairs
        sta fruit_seeded
:
        lda fruit_seeded
        beq @constants
        cpx #6
        bcc @constants
        cpx #14
        bcc @done
@constants:
        jsr fruit_pair_constants
@done:  inx
        inx
        stx logical_count
        rts

.segment "CODE"
fruit_pair_constants:
        lda #0
        sta LOG_XHI,X
        sta LOG_XHI+1,X
        sta LOG_MC,X
        sta LOG_GROUP+1,X
        lda #1
        sta LOG_MC+1,X
        lda #2
        sta LOG_GROUP,X
        ldy animidx
        lda fruit_frames,Y
        sta LOG_PTR,X
        clc
        adc #1
        sta LOG_PTR+1,X
        lda fruit_colours,Y
        sta LOG_COL,X
        lda fruit_details,Y
        sta LOG_COL+1,X
        rts

.segment "HELPERS"
fruit_get_type:
        lda completed_mountains
@mod10: cmp #10
        bcc @type
        sbc #10
        bcs @mod10
@type:  sta animidx
        rts

; In2P bonus each player has at most two body layers and no mallet,
; followed by at most two condor layers. Only fruit can write slots6..13.
; Seed their type-dependent fields after actors_reset; coordinates remain
; fresh on every append. Lower slots and arbitrary larger counts retain
; full writes, including the slot31 partial-pair path.
.segment "EXTRA"
fruit_seed_init:
        lda player_count
        cmp #2
        bne @done
        jsr fruit_get_type
        ldx #6
@pair:  jsr fruit_pair_constants
        inx
        inx
        cpx #14
        bne @pair
        inc fruit_seeded
@done:  rts

fruit_append_single:
        ldx ui_col
        lda fruit_x,X
        sta actor_xlo
        lda #0
        sta actor_xhi
        sta actor_yhi
        ldx animidx
        lda fruit_frames,X
        sta actor_ptr
        lda fruit_details,X
        tay
        lda fruit_colours,X
        tax
        jmp actor_pair

.segment "DATA"
; The raster events of this frame's logical sprites (the back half).
; Eight or fewer: logical sprite k is VIC sprite k, all installed by the
; frame IRQ. More: sorted by height (top of the screen first when built),
; overloaded windows lose their latest sprite, and every event reuses the
; first VIC sprite free again. tools/test_scheduler.py checks every
; schedule of real play against test_game's scheduler model.
schedule_actors:
        lda logical_count
        cmp #9
        bcs schedule_multiplex
        sta scheduled_count
        sta pending_count
        sta pending_batch       ; all of them: the frame IRQ's batch, which
        ldy back_base           ; reads only Y, X, pointer and colour, and
        sta EVENT_BATCH,Y       ; the bits after its last event
        ldx #0
        stx event_msb
        stx event_mc
        cmp #0
        beq @direct_done        ; Y = event entry, X = logical = VIC sprite
@direct:
        lda LOG_Y,X
        sta EVENT_Y,Y
        lda LOG_X,X
        sta EVENT_X,Y
        lda LOG_PTR,X
        sta EVENT_PTR,Y
        lda LOG_COL,X
        sta EVENT_COL,Y
        lda LOG_XHI,X           ; each VIC sprite once: only set bits change
        beq :+
        lda event_msb
        ora vic_bits,X
        sta event_msb
:       lda LOG_MC,X
        beq :+
        lda event_mc
        ora vic_bits,X
        sta event_mc
:       iny
        inx
        cpx logical_count
        bne @direct
        lda event_msb
        sta EVENT_MSB-1,Y
        lda event_mc
        sta EVENT_MC-1,Y
        lda direct_ena-1,X
        sta event_ena
        sta EVENT_ENA-1,Y
@direct_done:
        jmp packet_priority
; $D015 after logical sprites 0..k: bits 0..k.
direct_ena: .byte $01,$03,$07,$0F,$1F,$3F,$7F,$FF

; Nine or more. The order (LOG_ORDER from the lowest sprite up, equal
; heights with the later logical sprite first) is the insertion sort's; a
; two-layer object (group 2, then group 0 at the same height) moves as one
; block of two.
schedule_multiplex:
        lda #0
        sta scheduled_count
        sta sched_i
        jsr bonus_sort_try
        bcc :+
        jmp schedule_overload
:       jsr bonus_pair_sort
        bcs @sorted
@sort:  ldx sched_i
        cpx logical_count
        bcs @sorted
        lda LOG_Y,X
        sta tmp
        lda LOG_GROUP,X
        cmp #2
        bne @single
        inx                     ; its second layer: the next sprite, same Y
        cpx logical_count
        bcs @single
        lda LOG_GROUP,X
        bne @single
        lda LOG_Y,X
        cmp tmp
        bne @single
        ldy scheduled_count
        beq @put2
@insert2:
        ldx LOG_ORDER-1,Y
        lda tmp                 ; stop below a higher sprite; equal heights
        cmp LOG_Y,X             ; keep the newer one below
        bcc @put2
        txa
        sta LOG_ORDER+1,Y       ; two places up
        dey
        bne @insert2
@put2:  ldx sched_i
        txa
        sta LOG_ORDER+1,Y       ; [second layer, first layer]
        inx
        txa
        sta LOG_ORDER,Y
        inx
        stx sched_i
        inc scheduled_count
        inc scheduled_count
        jmp @sort
@single:
        ldy scheduled_count
        beq @put
@insert:
        ldx LOG_ORDER-1,Y       ; equal heights keep their old order (layer
        lda tmp                 ; priority): the newer one goes below them
        cmp LOG_Y,X
        bcc @put
        txa
        sta LOG_ORDER,Y
        dey
        bne @insert
@put:   lda sched_i
        sta LOG_ORDER,Y
        inc scheduled_count
        inc sched_i
        jmp @sort
@sorted:
        jsr bonus_sort_save     ; cache the full order before overload drops
schedule_overload:
        jsr schedule_mode
sched_recheck:
        lda scheduled_count
        sec
        sbc #8
        jcc @allocate           ; eight or fewer always fit
        jeq @allocate
        sta work2               ; windows k = 0 .. count-9
        ldx sched_band
@fit:   cpx work2
        jcs @allocate
        ldy LOG_ORDER,X
        lda LOG_Y,Y
        ldy LOG_ORDER+8,X
        sec
        sbc LOG_Y,Y
        cmp sched_gap
        bcc @crowded
        inx
        bne @fit
@crowded:
        bit sched_boot
        bmi @drop
        ; The shorter window is only used when the entire packet fits.
        ; Overload pruning never drops a climber; a pair goes as a whole.
        lda #REUSE
        sta sched_gap
        dec sched_boot          ; 0 -> $FF: standard reuse
        bne sched_recheck
@drop:  jmp sched_drop          ; X = k (in MUXCODE, below)
@allocate:
        lda sched_gap
        sec
        sbc #22
        sta sched_release
        lda #0
        sta event_msb
        sta event_mc
        sta event_ena
        .repeat 8,I
        sta HW_END+I
        .endrep
        sta pending_batch       ; (standard reuse: found at the end)
        lda back_base
        sta event_build_count   ; absolute entry in the back half
        lda sched_boot          ; short reuse: the top eight sprites first, on
        bne @event              ; VIC sprites 0-7 from line 0
        jsr sched_rotate
        lda back_base
        bne :+
        jsr initial_batch_lo
        jmp @event
:       jsr initial_batch_hi
@event: ldx scheduled_count     ; top of the screen first
        jeq @finished
        dex
        stx scheduled_count
        ldy LOG_ORDER,X         ; Y = logical sprite
        lda LOG_Y,Y
        sta actor_y
        ; (initial channels were all placed by initial_batch_lo/hi)
        ; the first VIC sprite whose last use has ended (HW_END <= y)
        .repeat 8,I
        cmp HW_END+I
        bcs .ident(.sprintf("@slot%d", I))
        .endrep
        jmp @event              ; (cannot happen: every window fits)
        .repeat 8,I
.ident(.sprintf("@slot%d", I)):
        ldx #I
        .if I = 0
        beq @found
        .else
        bne @found
        .endif
        .endrep
@found: lda HW_END,X             ; 0: the VIC sprite's first use this frame,
        beq @event_line         ; installed as early as the order allows
        sbc sched_release       ; (carry set) its last sprite ended: old y+22
        sta work2               ; its registers may change from this line
        lda actor_y
        sec
        sbc #28
        cmp work2
        bcs @event_line
        lda work2
        bcc @event_line
@event_line:
        sta work2
        lda actor_y
        clc
        adc sched_gap
        bcc @end
        lda #$FF
@end:   sta HW_END,X
        ; $D010, $D01C and $D015 after this event (X = VIC sprite)
        lda LOG_XHI,Y
        beq @low
        lda event_msb
        ora vic_bits,X
        bne @msb
@low:   lda event_msb
        and vic_notbits,X
@msb:   sta event_msb
        lda LOG_MC,Y
        beq @hires
        lda event_mc
        ora vic_bits,X
        bne @mc
@hires: lda event_mc
        and vic_notbits,X
@mc:    sta event_mc
        lda event_ena
        ora vic_bits,X
        sta event_ena
        txa
        ldx event_build_count   ; X = event entry
        sta EVENT_SLOT,X
        lda actor_y
        sta EVENT_Y,X
        lda work2               ; 28 lines early, or after the previous use
        sta EVENT_LINE,X
        lda LOG_X,Y
        sta EVENT_X,X
        lda LOG_PTR,Y
        sta EVENT_PTR,X
        lda LOG_COL,Y
        sta EVENT_COL,X
        lda event_msb
        sta EVENT_MSB,X
        lda event_mc
        sta EVENT_MC,X
        lda event_ena
        sta EVENT_ENA,X
        inc event_build_count
        jmp @event
@finished:
        lda event_build_count
        sec
        sbc back_base
        sta scheduled_count
        sta pending_count
        ldx pending_batch       ; the frame IRQ's batch: every leading event
@run:   cpx pending_count       ; on its first VIC sprite use from line 0,
        bcs @run_done           ; on VIC sprites 0, 1, 2 ...
        txa
        clc
        adc back_base
        tay
        lda EVENT_LINE,Y
        bne @run_done
        txa
        cmp EVENT_SLOT,Y
        bne @run_done
        inx
        bne @run
@run_done:
        stx pending_batch
        txa
        ldy back_base
        sta EVENT_BATCH,Y
        jmp packet_priority

.segment "MUXCODE"
; schedule_overload's window k (X) is crowded. Popo in three layers
; (logical 0..2; actor_player @layers marks the white layer with colour
; $11, white to the VIC) first takes the parka and multicolour details of
; a crowded frame (@compact): then no other sprite needs to be left out.
; This is the frame's first drop, so sched_band is still 0.
sched_drop:
        lda LOG_COL
        cmp #$11
        bne @victim
        ldy animidx
        lda popo_details,Y
        sta LOG_PTR+2
        inc LOG_MC+2
        ldy #$FF
        sty LOG_COL             ; (once)
        sty LOG_Y               ; (a pan's rescheduling leaves it out)
@white: iny
        lda LOG_ORDER,Y         ; the white layer's place
        bne @white
        beq @one                ; (always)
        ; Entries k .. k+8 (k: the lowest on the screen). Never a climber
        ; (logical 0 .. player_sprites-1, at most six of the nine): the
        ; lowest other sprite on even frames, the highest on odd ones, so
        ; two crowded figures take turns and each shows every other frame.
@victim:
        stx sched_band
        lda frame
        lsr
        txa
        tay
        bcc @lower
        adc #7                  ; (carry set: k+8)
        tay
@upper: ldx LOG_ORDER,Y
        cpx player_sprites
        bcs @chosen
        dey
        bpl @upper              ; (always)
@lower: ldx LOG_ORDER,Y
        cpx player_sprites
        bcs @chosen
        iny
        bne @lower              ; (always)
@chosen:
        lda LOG_GROUP,X         ; X: the logical sprite, Y: its place
        beq @second             ; second layer of a pair: its first layer
        cmp #2                  ; is the next entry (ties: newer below)
        bne @one
        dey                     ; first layer: its second is the one before
        inx                     ; (never below window k, which then would
        txa                     ; be no more crowded than window k-1)
        cmp LOG_ORDER,Y
        beq @two
        iny
        bne @one
@second:
        dex
        txa
        cmp LOG_ORDER+1,Y
        bne @one
@two:   jsr @remove             ; entries Y and Y+1
@one:   jsr @remove
        jmp sched_recheck
@remove:                        ; entry Y leaves the order
        tya
        tax
        dec scheduled_count
@down:  cpx scheduled_count
        bcs @done
        lda LOG_ORDER+1,X
        sta LOG_ORDER,X
        inx
        bne @down
@done:  rts

.segment "DATA"
; The frame IRQ's batch (EVENT_BATCH events from irq_start: first uses of
; VIC sprites 0, 1, .. from line 0), stored without the per-event raster
; checks, from the highest VIC sprite down. They all end long before Y35,
; the first partially visible sprite, and before the first palette split
; (line 53 or later), so $D010, $D01C and $D015 are stored once, from the
; last event. irq_index = the event after the batch.
irq_initial_batch:
        ldy irq_start
        ldx EVENT_BATCH,Y
        bne :+
        rts
:       txa
        clc
        adc irq_start
        sta irq_index           ; the later events follow the batch
        tay
        lda EVENT_MSB-1,Y       ; the batch's last event holds the bits
        sta $D010
        lda EVENT_MC-1,Y
        sta $D01C
        lda EVENT_BG-1,Y
        sta $D01B
        dey
        lda @entry_hi-1,X
        pha
        lda @entry_lo-1,X
        pha
        rts                     ; VIC sprite X-1 first, down to sprite 0
        .repeat 8, I
.ident(.sprintf("@slot%d", 7-I)):
        lda EVENT_PTR,Y
        sta SCREEN+$3F8+7-I
        sta BACK_SCREEN+$3F8+7-I
        lda EVENT_COL,Y
        sta $D027+7-I
        lda EVENT_X,Y
        sta $D000+2*(7-I)
        lda EVENT_Y,Y
        sta $D001+2*(7-I)
        dey
        .endrep
        ldy irq_index
        lda EVENT_ENA-1,Y
        sta $D015               ; (tools/verify_mux_timing.py hooks this store)
        rts
@entry_lo:
        .lobytes @slot0-1, @slot1-1, @slot2-1, @slot3-1, @slot4-1, @slot5-1, @slot6-1, @slot7-1
@entry_hi:
        .hibytes @slot0-1, @slot1-1, @slot2-1, @slot3-1, @slot4-1, @slot5-1, @slot6-1, @slot7-1

; Reuse mode for 9..12 sprites (scheduled_count): short reuse, 28+count
; lines (37..40: each later event after the batch of eight adds a line),
; when every window fits; else standard reuse (46 lines, sched_boot = $FF).
schedule_mode:
        lda #0
        sta sched_band          ; windows before this one already fit
        sta sched_boot
        lda scheduled_count
        cmp #13
        bcs @standard
        adc #28                 ; (carry clear)
        sta sched_gap
        rts
@standard:
        lda #REUSE
        sta sched_gap
        dec sched_boot          ; standard reuse: $FF
        rts

; Short reuse: events 7 and 8 (LOG_ORDER count-8 and count-9) may be layers
; of one figure (equal Y and X low byte; LOG_ORDER holds a figure's layers
; from its back one up). Its back layers then end the batch, on the last VIC
; sprites, and its front ones become the first later events, which reuse
; lower VIC sprites: every layer keeps its priority over the ones behind.
sched_rotate:
        lda scheduled_count
        sec
        sbc #8
        tax                     ; event 7
        stx sched_band
        ldy LOG_ORDER,X
        lda LOG_Y,Y
        sta tmp
        lda LOG_X,Y
        sta work2
        dex                     ; event 8
        jsr @same
        bne @done
@down:  dex                     ; lo: the figure's back layer
        bmi @bottom
        jsr @same
        beq @down
@bottom:
        inx
        stx sched_i
        ldx sched_band
@up:    inx                     ; hi: its front layer
        cpx scheduled_count
        bcs @top
        jsr @same
        beq @up
@top:   dex
        stx sched_end
        txa
        sec
        sbc sched_band          ; its layers in the batch, less one
        sta sched_band
@rotate:
        ldx sched_i             ; lo..hi turns by one: the back layer up
        ldy LOG_ORDER,X
@shift: lda LOG_ORDER+1,X
        sta LOG_ORDER,X
        inx
        cpx sched_end
        bne @shift
        tya
        sta LOG_ORDER,X
        dec sched_band
        bpl @rotate
@done:  lda #8                  ; the batch: always eight
        sta sched_end
        rts
@same:  ldy LOG_ORDER,X         ; Z: entry X is a layer of the figure
        lda LOG_Y,Y
        cmp tmp
        bne :+
        lda LOG_X,Y
        cmp work2
:       rts

; The initial channels of a short-reuse schedule, the same events the
; generic loop builds (fresh VIC sprites: only set bits change), indexed by
; the event entry B+k for VIC sprite k. The frame IRQ draws them as its
; batch (pending_batch): line 0 and VIC sprite k are implied, and only the
; last one stores $D010/$D01C/$D015.
.macro initial_batch B
        lda sched_end           ; the batch size
        clc
        adc #B
        sta sched_end
        ldx #B
@next:  ldy scheduled_count
        beq @done
        dey
        sty scheduled_count
        lda LOG_ORDER,Y
        tay                     ; Y = logical sprite
        lda LOG_Y,Y
        sta EVENT_Y,X
        clc
        adc sched_gap
        bcc :+
        lda #$FF
:       sta HW_END-B,X
        lda LOG_X,Y
        sta EVENT_X,X
        lda LOG_PTR,Y
        sta EVENT_PTR,X
        lda LOG_COL,Y
        sta EVENT_COL,X
        lda LOG_XHI,Y
        beq :+
        lda event_msb
        ora vic_bits-B,X
        sta event_msb
:       lda LOG_MC,Y
        beq :+
        lda event_mc
        ora vic_bits-B,X
        sta event_mc
:       inx
        cpx sched_end
        bne @next
@done:  stx event_build_count
        lda event_msb           ; the batch's last event holds the bits
        sta EVENT_MSB-1,X
        lda event_mc
        sta EVENT_MC-1,X
        lda direct_ena-B-1,X
        sta event_ena
        sta EVENT_ENA-1,X
        txa
        sec
        sbc #B
        sta sched_boot
        sta pending_batch
        rts
.endmacro
initial_batch_lo:
        initial_batch 0
initial_batch_hi:
        initial_batch EVENT_HALF

.segment "CODE"
slot_offsets: .byte 0,2,4,6,8,10,12,14

commit_actors:
        lda state
        beq @off
        cmp #2
        beq @off
        sei
        lda #0
        sta $D01A
        sta $D015
        lda back_base           ; the half just built becomes the shown one
        sta irq_start
        sta irq_index
        clc
        adc pending_count
        sta irq_count
        lda back_base
        eor #EVENT_HALF
        sta back_base
        lda #FRAME_IRQ_LINE
        sta $D012
        lda #1
        sta frame_due
        sta $D019
        sta $D01A
        cli
        rts
@off:   lda #0
        sta $D015
        sta $D01A
        rts

.segment "EXTRA"
; The original walk cycle is $5C,$62,$5C,$56, two physics ticks each.
; The original walking OAM clock is retained across the initial jump tick.
player_walk_pose:
        lda hammer_t            ; repurposed local r6C/r60 clock0..7
        lsr
        tax
        lda player_walk_poses,X
        rts
.segment "CODE"
player_walk_poses: .byte 0,2,0,12
.segment "EXTRA"

; While the NES object code runs with RAM at $D000 ($01 = $34), the vector
; points here instead (nes_ram_on/nes_ram_off): switch the I/O in and let
; the handler's RTI return through raster_irq_ram_exit, which switches it
; out again. Ordinary IRQs pay nothing for it.
raster_irq_ram:
        pha
        lda #$35
        sta $01
        lda #>raster_irq_ram_exit
        pha
        lda #<raster_irq_ram_exit
        pha
        php
; Frame IRQ and sprite events share two palette boundaries. No score-panel
; IRQs or mid-screen D011 mode changes interrupt sprite register batches.
raster_irq:
        pha
        txa
        pha
        tya
        pha
        lda #1
        sta $D019
        lda frame_due           ; the frame IRQ: armed as such and early in
        beq @resume             ; the frame (a stray IRQ later must not
        lda $D011               ; restart the sprites)
        bmi @resume
        lda $D012
        cmp #50
        bcs @resume
        inc frame_ticks
        lda #0
        sta frame_due
        sta split_done
        sta $D015
        lda irq_start
        sta irq_index
        lda split_open         ;one24row playfield for the whole frame
        sta $D011
        lda screen_buffer
        asl
        asl
        asl
        asl
        ora #GAME_CHARSET
        sta $D018
        jsr terrain_palette_top
        jsr irq_initial_batch
@resume:
        ldy irq_index
@actor: lda $D011
        jmi @frame             ;9bit raster: low-byte wrap cannot replay events
        ldx split_done
        cpx #2
        beq @event
        lda $D012
        cmp split_irq_lines,X
        bcc @event
        jsr terrain_palette_split
        ldy irq_index
        jmp @actor
@event: cpy irq_count
        jcs @finished
        lda EVENT_LINE,Y
        cmp $D012
        jcc @draw
        jeq @draw
        ldx split_done
        cpx #2
        beq @schedule
        cmp split_irq_lines,X
        bcc @schedule
        lda split_irq_lines,X
@schedule:
        ldx #1                  ; a $D012 write on the current line latches
        stx $D019               ; the IRQ flag: drop any such stale flag
        sta $D012
        cmp $D012               ; the beam may have reached it meanwhile
        jcc @actor
        jeq @actor
        jmp @return
@draw:  ldx EVENT_SLOT,Y        ; register values were prepared by the
        lda EVENT_PTR,Y         ; scheduler: the IRQ only stores them
        sta SCREEN+$3F8,X
        sta BACK_SCREEN+$3F8,X
        lda EVENT_COL,Y
        sta $D027,X
        lda slot_offsets,X
        tax
        lda EVENT_X,Y
        sta $D000,X
        lda EVENT_Y,Y
        sta $D001,X
        lda EVENT_MSB,Y
        sta $D010
        lda EVENT_MC,Y
        sta $D01C
        lda EVENT_BG,Y
        sta $D01B
        lda EVENT_ENA,Y
        sta $D015
        iny
        sty irq_index
        jmp @actor
@finished:
        ldx split_done
        cpx #2
        beq @frame
        lda split_irq_lines,X
        jmp @schedule
@frame: lda #1
        sta $D019               ; no stale flag may follow into the next IRQ
        lda #FRAME_IRQ_LINE
        sta $D012
        sta frame_due           ; (non-zero)
@return:
        pla
        tay
        pla
        tax
        pla
        rti
.assert >raster_irq_ram = >raster_irq, error, "nes_ram_on swaps only the vector's low byte"
.segment "HELPERS"
raster_irq_ram_exit:
        lda #$34
        sta $01
        pla
        rti
.segment "EXTRA"

.segment "CODE"

; A cold bonus permutation still consists of equal-Y two-layer blocks in
; 2P. Verify that shape, then move whole blocks through the same stable
; insertion order. Any other input retains the general one-entry sort.
.segment "HELPERS"
bonus_pair_sort:
        lda state               ; normal play: whenever the shape holds
        cmp #1
        beq @shape
        lda world_ptr           ; bonus_sort_try: eligible bonus count9..16
        beq @miss
        lda player_count
        cmp #2
        bne @miss
@shape: lda logical_count
        lsr
        bcs @miss
        ldy logical_count
@pair:  dey
        lda LOG_Y,Y
        dey
        cmp LOG_Y,Y
        bne @miss
        cpy #0
        bne @pair
        jmp bonus_pair_sort_valid
@miss:  clc
        rts

.segment "CODE"
bonus_pair_sort_valid:
        lda #1
        sta sched_i             ; each block is [later layer, earlier layer]
@sort:  ldx sched_i
        cpx logical_count
        bcs @done
        lda LOG_Y,X
        sta tmp
        ldy scheduled_count
        beq @put
@insert:
        ldx LOG_ORDER-1,Y
        lda LOG_Y,X
        cmp tmp
        beq @shift
        bcs @put
@shift: lda LOG_ORDER-2,Y
        sta LOG_ORDER,Y
        txa
        sta LOG_ORDER+1,Y
        dey
        dey
        bne @insert
@put:   lda sched_i
        sta LOG_ORDER,Y
        sec
        sbc #1
        sta LOG_ORDER+1,Y
        adc #2                  ; i-1 with carry set: next odd index i+2
        sta sched_i
        sbc #0                  ; carry is clear: i+1 entries now sorted
        sta scheduled_count
        jmp @sort
@done:  sec
        rts

; Fruit source order rotates over four frames. Retain a complete sorted
; permutation for each phase, but use it only when every fresh Y and every
; equal-Y source tie still has exactly the order insertion sort would give.
; Geometry changes fall back to the original sort and refresh that phase.
.segment "EXTRA"
bonus_sort_try:
        lda #0
        sta world_ptr           ; zero also tells bonus_sort_save to skip
        lda state
        cmp #3
        bne @miss
        lda logical_count
        cmp #17
        bcs @miss
        lda frame
        and #3
        tax
        asl
        asl
        asl
        asl
        ora #<BONUS_SORT_ORDER
        sta world_ptr
        lda #>BONUS_SORT_ORDER
        sta world_ptr+1
        lda BONUS_SORT_COUNT,X
        cmp logical_count
        bne @promote
        jmp bonus_sort_validate
@miss:  clc
        rts
@promote:
        jmp bonus_sort_promote

; Try the common transition from twelve sprites to fourteen as the
; condor enters at the top. This lift always produces a permutation;
; fresh height and tie validation decides whether it can actually be used.
.segment "CODE"
bonus_sort_promote:
        cmp #12
        bne @miss
        lda logical_count
        cmp #14
        bne @miss
        sta BONUS_SORT_COUNT,X
        ldy #13
        lda #4
        sta (world_ptr),Y
        dey
        lda #5
        sta (world_ptr),Y
        dey
@lift:  lda (world_ptr),Y
        cmp #4
        bcc @store
        adc #1                  ; CMP set carry: insert two logical indices
@store: sta (world_ptr),Y
        dey
        bpl @lift
        jmp bonus_sort_validate
@miss:  clc
        rts

.segment "HIGH"
bonus_sort_validate:
        ldy #0
        lda #$FF
        sta tmp
        lda #32
        sta work2
@next:  lda (world_ptr),Y
        tax
        lda LOG_Y,X
        cmp tmp
        bcc @ordered
        bne @miss
        txa
        cmp work2               ; ties put the later source index first
        bcs @miss
        lda tmp
@ordered:
        sta tmp
        txa
        sta work2
        sta LOG_ORDER,Y
        iny
        cpy logical_count
        bne @next
        sty scheduled_count
        sec
        rts
@miss:  clc
        rts

.segment "DATA"
bonus_sort_save:
        lda world_ptr
        beq @done
        lda frame
        and #3
        tax
        lda logical_count
        sta BONUS_SORT_COUNT,X
        tay
@next:  dey
        lda LOG_ORDER,Y
        sta (world_ptr),Y
        cpy #0
        bne @next
@done:  rts
.segment "CODE"

; The original switches four lower body tiles in the bonus round. Patch
; those bytes in place, so both climbers keep their own parka colour and
; the bank still holds the same128 VIC sprite blocks. XOR is reversible.
normal_player_art:
        lda #0
        beq set_player_art
bonus_player_art:
        lda #1
set_player_art:
        cmp player_art_scene
        beq @done
        sta player_art_scene
        lda #<player_bonus_patch
        sta src
        lda #>player_bonus_patch
        sta src+1
        ldy #0
@record:
        jsr player_art_byte
        beq @done
        sta dst+1
        lda #0
        sta dst
        lsr dst+1
        ror dst
        lsr dst+1
        ror dst
        lda dst
        ora #24                 ; only sprite bytes24..63 can differ
        sta dst
        lda dst+1
        clc
        adc #$40                ; VIC sprite pointer in bank$4000
        sta dst+1
        ldx #5
@mask:  jsr player_art_byte
        sta tmp
        lda #8
        sta work2
@bit:   asl tmp
        bcc @next
        jsr player_art_byte
        eor (dst),Y
        sta (dst),Y
@next:  inc dst
        bne @same
        inc dst+1
@same:  dec work2
        bne @bit
        dex
        bne @mask
        jmp @record
@done:  rts

player_art_byte:
        lda (src),Y
        inc src
        bne @ready
        inc src+1
@ready: cmp #0
        rts

.segment "DATA"
player_bonus_patch:
        .incbin "../build/player_bonus_patch.bin"
.segment "CODE"

.segment "HELPERS"
; Topi has two exact hires masks: cyan body and single-pixel white detail.
actor_topi_pair:
        ldx #$83                ; $C777: normal Topis are behind foreground
        ldy #$81
        lda #0                  ; both layers hires
        jmp pair_append

.segment "PRIOCODE"
; Build priority masks after channel allocation, including short-reuse
; batches whose initial slots are implied. Reused channels can change role.
packet_priority:
        lda state
        cmp #1
        bne @done               ; other scenes keep the reset masks
        lda pending_count
        beq @done
        lda #0
        sta event_bg
        ldx #0
        ldy back_base
@event: cpx pending_batch
        bcc @slot
        ldx EVENT_SLOT,Y
@slot:  lda event_bg
        and vic_notbits,X
        sta event_bg
        lda EVENT_COL,Y
        bpl @store
        lda event_bg
        ora vic_bits,X
        sta event_bg
@store: lda event_bg
        sta EVENT_BG,Y
        iny
        tya
        sec
        sbc back_base
        tax
        cpx pending_count
        bne @event
@done:  rts
; Scene entry hides sprites first. Clear both packet halves once, so bonus
; and preview frames pay no per-event priority cost in their main loop.
priority_reset:
        lda #0
        sta $D01B
        ldx #63
@clear: sta EVENT_BG,X
        dex
        bpl @clear
        rts
.assert packet_priority >= $EB80 .and * <= $EC00, error, "Priority code overlaps cache scratch"
.segment "HELPERS"

.segment "STARTUP"
; Build four complete poses at startup with the display and IRQs masked.
; The ordinary walk pages are never patched. Only the preview condor still
; uses the same XOR decoder on a visible-bank sprite page.
topi_special_init:
        lda $01
        pha
        and #$FC
        sta $01
        ldx #0
@seed:  lda $4000+TOPI_R_WALK0*64,X
        sta TOPI_SPECIAL_RAM,X
        inx                     ; (pages 1-3: install_helpers)
        bne @seed
        lda #1                  ; stars: the stunned seal, CHR $06
        jsr xor_topi_patch
        pla
        sta $01
        rts

.segment "CODE"
; Normal play draws the block debris in the eight condor blocks: clear
; them and copy the 8x8 pieces (RAM under I/O, $01 = $34 here). Every other
; scene unpacks them again from the resident sprite stream: from the
; packet at the first condor byte up to page $6B, where the bytes after the
; blocks are the original fruit again.
debris_scene_art:
        lda #0
        sta condor_art_scene    ; no preview XOR on either art
        lda topi_overlay_mode
        bne @install
        jmp debris_condor       ; (RAM under I/O, $01 = $34 here)
@install:
        tax
        dex                     ; X = 0, A = 0
        txa
@clear: sta $4000+DEBRIS_BLOCK*64,X
        sta $4000+DEBRIS_BLOCK*64+$100,X
        inx
        bne @clear
        tay                     ; pieces 0-3 in the first page, 4-7 in the second
@row:   lda debris_art,X
        sta $4000+DEBRIS_BLOCK*64,Y
        lda debris_art+32,X
        sta $4000+DEBRIS_BLOCK*64+$100,Y
        inx
        iny
        iny
        iny
        txa
        and #7
        bne @row
        tya
        clc
        adc #64-24
        tay
        cpx #32
        bne @row
        rts
.segment "IOMIDCODE"
debris_condor:
        lda #<condor_rle
        sta src
        lda #>condor_rle
        sta src+1
        lda #<(SPRITES+DEBRIS_RLE_DST)
        sta dst
        lda #>(SPRITES+DEBRIS_RLE_DST)
        sta dst+1
        lda #$6B
        sta work2
        jmp unpack_asset_data
.segment "CODE"
        .assert SPRITES+DEBRIS_RLE_DST = $4000+DEBRIS_BLOCK*64, error, "restore starts at the condor blocks"
        .assert $4000+(DEBRIS_BLOCK+8)*64 <= $6B00, error, "restore ends at page $6B"

; Scene entry disables sprites before swapping the two banks. Only normal
; play displays the Topi pages; preview and bonus display the same fruit.
topi_sprite_scene:
        ldx #0
        lda state
        cmp #1
        bne :+
        inx
:       txa
        cmp topi_overlay_mode
        beq @done
        sta topi_overlay_mode
        lda #>TOPI_SPECIAL_RAM
        sta src+1
        lda #>TOPI_SPECIAL_VIC
        sta dst+1
        lda #0
        sta src
        sta dst
        tay
        ldx #4
        php
        sei
        lda $01
        pha
        and #$FC
        sta $01
@byte:  lda (src),Y
        pha
        lda (dst),Y
        sta (src),Y
        pla
        sta (dst),Y
        iny
        bne @byte
        inc src+1
        lda src+1
        cmp #$D4
        bne :+
        inc src+1
:       inc dst+1
        dex
        bne @byte
        ldy #127                ; the original death spin over fruit 0 and 9
@spin:  lda $4000+FRUIT_L_0_0_0*64,Y
        tax
        lda death_spin_art,Y
        sta $4000+FRUIT_L_0_0_0*64,Y
        txa
        sta death_spin_art,Y
        lda $4000+FRUIT_L_9_0_0*64,Y
        tax
        lda death_spin_art+128,Y
        sta $4000+FRUIT_L_9_0_0*64,Y
        txa
        sta death_spin_art+128,Y
        dey
        bpl @spin
        jsr debris_scene_art
        pla
        sta $01
        plp
@done:  rts
.segment "SWAP"
death_spin_art:                 ; normal play: fruit 0 and 9 rest here
        .incbin "../build/death_spin.bin"
.segment "CODE"

.segment "HELPERS"
xor_topi_patch:
        tax
        dex
        lda topi_patch_lo,X
        sta src
        lda topi_patch_hi,X
        sta src+1
        lda topi_patch_page,X
        sta dst+1
        lda #0
        sta dst
        tax                     ; X = 0: (src,X) reads the patch stream
        tay                     ; Y = byte in the 256-byte sprite page
@group: lda (src,X)             ; mask of the group's 8 bytes, bit 7 first
        inc src
        bne :+
        inc src+1
:       sta tmp
        sty work2
@bit:   asl tmp
        bcc @next
        lda (src,X)
        inc src
        bne :+
        inc src+1
:       eor (dst),Y
        sta (dst),Y
@next:  iny
        lda tmp
        bne @bit                ; stop after the group's last changed byte
        lda work2
        clc
        adc #8
        tay
        bne @group              ; 32 groups
        rts
        .assert <($4000+TOPI_R_WALK0*64)=0,error,"Topi WALK0 patch requires a sprite page"
        .assert <($4000+TOPI_R_WALK1*64)=0,error,"Topi WALK1 patch requires a sprite page"
.segment "HELPERS"
.segment "DATA"
topi_patch_lo: .byte <topi_stun_patch,<condor_preview_patch
topi_patch_hi: .byte >topi_stun_patch,>condor_preview_patch
topi_patch_page: .byte >TOPI_SPECIAL_RAM,>($4000+CONDOR_L_FLAP0_0_0*64)
condor_preview_patch:
        .incbin "../build/condor_preview_patch.bin"
topi_stun_patch:
        .incbin "../build/topi_stun_patch.bin"
.segment "CODE"
