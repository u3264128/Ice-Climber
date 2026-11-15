; The original NES enemy objects: Topi with its ice blocks, the polar bear,
; the three icicles, Nitpicker and every hammer and touch hit box.
; tools/transplant_objects.py copies the original instructions from
; bank_FF.asm into ../build/nes_objects.inc and moves their RAM operands
; to the C64 addresses in ../build/nes_symbols.inc. That code runs from RAM
; under the I/O area: callers switch $01 to $34 around it (nes_ram_on),
; and meanwhile raster_irq_ram switches the I/O in for each IRQ. This file
; holds the C64 side: the NES view of the players and clouds before a
; tick, and their changes after it.

NES_OBJECTS = 11                ; 0 bird, 1 bear, 2-4 seals, 5-7 ice, 8-10 icicles
NES_ALL_RAM = $34               ; $01: RAM everywhere, for the code under I/O
NES_IO      = $35

; The vector first: an IRQ between the two stores already switches the
; I/O back in for itself.
.macro nes_ram_on
        lda #<raster_irq_ram
        sta $FFFE
        lda #NES_ALL_RAM
        sta $01
.endmacro

; Both together: neither order is safe against an IRQ in between.
.macro nes_ram_off
        php
        sei
        lda #NES_IO
        sta $01
        lda #<raster_irq
        sta $FFFE
        plp
.endmacro

.segment "IOCODE"
.include "../build/nes_objects.inc"     ; ends in segment IODATA

.segment "HELPERS"
; Stage start, original $C1F8-$C297: clear the object state and arm the
; original seal, icicle, bear and bird delays.
nes_stage_init:
        nes_ram_on
        lda #0
        ldx #NES_OBJ_DIR+11-NES_UPPER_FLOOR-1
@zp:    sta NES_UPPER_FLOOR+1,X ; NES $91-$C7
        dex
        bpl @zp
        sta NES_BEAR_PHASE
        ldx #$03F2-$0381
@objects:
        sta NES_PAN_FLAG+$0381-$0376,X
        dex
        bpl @objects
        ldx #nes_spin_t+1-nes_dying
@death: sta nes_dying,X         ; no climber is dying on a new mountain
        dex
        bpl @death
        sta NES_PUSH_T
        sta NES_PUSH_T+1
        ldx #NES_MIRROR_END-NES_MIRROR_FIRST-1
@mirrors:
        sta NES_MIRROR_FIRST,X
        dex
        bpl @mirrors
        jsr nes_export
        lda #$FF                ; (the mirrors were just cleared)
        sta stones_floor
        jsr nes_stones_seen     ; $C2A4: this mountain's stone posts
        jsr nes_debris_init
        ldx #2
@icicles:
        jsr nes_icicle_reset
        dex
        bpl @icicles
        lda #$1A                ; seal delays
        sta NES_TIMERS+2
        lda #$21
        sta NES_TIMERS+3
        lda #$80                ; Nitpicker delay
        sta NES_TIMERS+6
        jsr nes_bird_init
        nes_ram_off
        rts

; $E002 builds the visible stone posts: X at $0600-$060A (0: none).
; Remember whether there is any, for the tick's $E0B9. Its tables depend
; only on $90 (the top floor) and the mountain ($59), and nothing else
; writes them: the same inputs (every tick of a pan) rebuild the same bytes.
nes_stones_seen:
        lda NES_UPPER_FLOOR
        cmp stones_floor
        bne @scan
        lda NES_RAW_MOUNTAIN
        cmp stones_mountain
        beq @known
@scan:  lda NES_UPPER_FLOOR
        sta stones_floor
        lda NES_RAW_MOUNTAIN
        sta stones_mountain
        jsr nes_stones_init
        lda #0
        ldx #10
@any:   ora NES_STONES,X
        dex
        bpl @any
        sta nes_stones_any
@known: rts

.segment "CODE"
; One logic tick of the normal stage after both players, original $CBFB:
; $EFEC $E189 $DE22 $EE0D $EF9A $F10B $D3AC $D212 $D301 $F838 $E0B9 and
; the object half of $EB2E.
nes_objects_tick_all:
        nes_ram_on
        jsr nes_export
        jsr nes_debris_start    ; $D91C of this tick's bricks
        jsr nes_mallets         ; A <> 0: some mallet can hit
        sta nes_hammer
        jsr nes_topi_spawn
        jsr nes_bear_tick
        jsr nes_ice_blocks
        jsr nes_objects_tick
        jsr nes_bear_drop
        jsr nes_icicles_tick
        lda nes_hammer          ; $D3B3 does nothing unless a climber
        beq :+                  ; jumps (4) or swings at pose 9 (5)
        jsr nes_hammer_hits
:       jsr nes_bump
        ldx #NES_OBJECTS-1      ; $D308 can only touch through $DB1D,
@hostile:                       ; which needs a state with bit 7
        lda NES_OBJ_STATE,X
        bmi @touch
        dex
        bpl @hostile
        bmi @bird
@touch: jsr nes_touch_hits
@bird:  ldx #1                  ; $EC23 (respawn checks) leaves X = 1 and
        jsr nes_bird_tick       ; $F87C uses it for its random byte
        lda nes_stones_any      ; ($D493 top floor, $E29A clouds: C64 code)
        ora NES_PUSH_T          ; $E0B9 does nothing without a stone post
        ora NES_PUSH_T+1        ; or a running push
        beq :+
        jsr nes_stone_push
:       lda debris_any          ; $D9CC moves nothing without debris
        beq :+
        jsr nes_debris_tick
:       jsr nes_retire
        jsr nes_import
        nes_ram_off
        jmp nes_apply

.segment "HELPERS"
; Pan ticks: $EC51 moves the objects four lines; the last one runs the
; $D861 loop that hides objects four floors below the new top floor.
nes_pan_tick:
        nes_ram_on
        lda cam
        clc
        adc #4
        sta NES_UPPER_FLOOR
        jsr nes_stones_seen     ; $D836: the posts of the visible floors
        jsr nes_pan_objects
        jsr nes_debris_pan      ; $EC95 for the debris entries
        lda player_count        ; $D841/$D846: $D111 for both climbers; an
        cmp #2                  ; absent player 2 has $32 = 0
        bne @release
        lda nes_dying
        cmp #1
        bne @release
        lda nes_dying+1
        cmp #1
        beq @frozen
@release:
        jsr nes_release_frozen
@frozen:
        lda normal_pan_t
        cmp #1
        bne @done
        jsr nes_pan_end
@done:  nes_ram_off
        rts

.segment "CODE"
; Original $EB2E retires an object whose attribute has bit 7 (an ice block
; that filled its hole) and clears attributes without a sprite slot.
.segment "DATA"                 ; (normal RAM only: runs anywhere)
nes_retire:
        ldx #NES_OBJECTS-1
@object:
        lda NES_OBJ_ATTR,X
        beq @next
        and #$1F
        beq @clear
        lda NES_OBJ_ATTR,X
        bpl @next
        lda #0
        sta NES_OBJ_STATE,X
@clear: lda #0
        sta NES_OBJ_ATTR,X
@next:  dex
        bpl @object
        rts
.segment "CODE"

; The NES state of the players, clouds, camera and random bytes.
nes_export:
        inc NES_FRAME
        lda #1                  ; $55: normal stage
        sta NES_PHASE
        lda phase_counter       ; raw mountain counter 0..98
        asl
        asl
        asl
        asl
        asl
        clc
        adc mountain
        sec
        sbc #1
        sta NES_RAW_MOUNTAIN
        lda cam
        clc
        adc #4
        sta NES_UPPER_FLOOR
        jsr random_step
        sta NES_RANDOM
        jsr random_step
        sta NES_RANDOM+1
        jsr random_step
        sta NES_RANDOM+2
        jsr nes_export_clouds
        ldx #1
@player:
        lda #0
        sta NES_PLAYER_FLOOR,X
        sta NES_HANDLER,X
        sta NES_IMMUNE,X
        cpx player_count
        jcs @next
        txa
        asl
        asl
        asl
        asl
        asl
        tay                     ; PLAYER_STATES offset
        lda PLAYER_STATES,Y     ; lives (negative: out)
        jmi @next
        lda NES_UPPER_FLOOR     ; $D1E5/$D1F9: the floor of body Y+$18,
        sta NES_PLAYER_FLOOR,X  ; also in the air (C64 py = Y+$18)
        lda PLAYER_STATES+5,Y
        cmp #$4A
        bcc @floor
        dec NES_PLAYER_FLOOR,X
        cmp #$7A
        bcc @floor
        dec NES_PLAYER_FLOOR,X
        cmp #$AA
        bcc @floor
        dec NES_PLAYER_FLOOR,X
        cmp #$DA
        bcc @floor
        dec NES_PLAYER_FLOOR,X
@floor: lda NES_PLAYER_FLOOR,X
        bne :+
        inc NES_PLAYER_FLOOR,X  ; never floor 0 while on the screen
:       jsr nes_export_player
        lda nes_dying,X
        beq @next
        cmp #3
        bcc @dead
        lda #0                  ; $D463: below the screen, floor 0
        sta NES_PLAYER_FLOOR,X
        beq @next
@dead:  lda #7                  ; $D446: handler 7 until then
        sta NES_HANDLER,X
@next:  dex
        jpl @player
        rts

; X = player, Y = PLAYER_STATES offset: the climber as the objects and
; $D212 see it.
nes_export_player:
        lda PLAYER_STATES+3,Y
        sec
        sbc #52
        sta NES_PLAYER_X,X
        lda PLAYER_STATES+5,Y
        sec
        sbc #24
        sta NES_PLAYER_Y,X
        lda #1
        sec
        sbc PLAYER_STATES+10,Y  ; face 0 = right; NES $62 1 = right
        sta NES_FACING,X
        lda PLAYER_STATES+20,Y
        sta NES_PUSH_DIR,X
        lda PLAYER_STATES+15,Y  ; fall_int
        sta NES_FALL,X
        lda PLAYER_STATES+16,Y  ; fall_frac
        sta NES_FALL_FRAC,X
        lda PLAYER_STATES+25,Y  ; respawn immunity
        beq :+
        lda #1
:       sta NES_IMMUNE,X
        jsr nes_handler
        sta NES_HANDLER,X
        lda nes_pose
        sta NES_PLAYER_POSE,X
        rts

; Original $CCBC: the bonus stage bumps the climbers too. $C399 puts both
; on floor 1 and only a fall out of the bonus ($D73A) clears it, so there
; $D212 measures only their distance ($D2D9: X within 10, Y within $15).
; That test comes first here: the bonus ticks have little time to spare.
nes_bonus_bump:
        lda player_count
        cmp #2
        bne @done
        lda bonus_out
        ora bonus_out+1
        bne @done
        lda PLAYER_STATES+3     ; NES X differs by the same byte
        sec
        sbc PLAYER_STATES+PLAYER_SIZE+3
        jsr @abs
        cmp #10
        bcs @done
        lda PLAYER_STATES+5
        sec
        sbc PLAYER_STATES+PLAYER_SIZE+5
        jsr @abs
        cmp #$15
        bcs @done
        nes_ram_on
        ldx #1
        ldy #PLAYER_SIZE
@player:
        lda #1
        sta NES_PLAYER_FLOOR,X
        jsr nes_export_player
        ldy #0
        dex
        bpl @player
        jsr nes_bump
        jsr nes_import
        nes_ram_off
        jmp nes_apply
@abs:   bpl @done               ; $D2F9
        eor #$FF
        clc
        adc #1
@done:  rts

; Y = PLAYER_STATES offset: A = original handler, nes_pose = $60.
nes_handler:
        lda #0
        sta nes_pose
        lda PLAYER_STATES+8,Y   ; onground: 1 handler 1, 2 handler 3
        beq @air
        lda PLAYER_STATES+13,Y  ; attack_t counts the twenty ticks down
        cmp #2
        bcc @ground
        lda #21
        sec
        sbc PLAYER_STATES+13,Y
        sta nes_pose
        lda #5
        rts
@ground:
        lda PLAYER_STATES+8,Y
        cmp #2
        bne @walk
        lda #3
        rts
@walk:  lda #1
        rts
@air:   lda PLAYER_STATES+14,Y  ; air_init bit 7: a fall from a ledge
        bpl @jump
        lda #2
        rts
@jump:  lda PLAYER_STATES+18,Y  ; rise_int: zero after a head hit
        beq @head
        lda #4
        rts
@head:  lda #6
        rts

; Original cloud objects $0786: the floors with clouds from the bottom
; visible floor to one above the top, two at most.
nes_export_clouds:
        lda cam                 ; the floors change only with cam
        cmp clouds_cam
        beq @known
        sta clouds_cam
        lda #0
        sta clouds_floor
        sta clouds_floor+1
        ldy #0
        ldx cam
@find:  cpx #8                  ; cloud floors are 1..7
        bcs @known
        lda floor_types,X
        and #$E0
        cmp #$60
        bcc :+
        txa
        sta clouds_floor,Y
        iny
        cpy #2
        bcs @known
:       inx
        txa
        sec
        sbc cam
        cmp #5
        bcc @find
@known: ldy #0
        sty NES_CLOUD_OBJ
        sty NES_CLOUD_OBJ+1
@floor: ldx clouds_floor,Y
        beq @done
        txa
        clc
        adc #1                  ; NES floors count from one
        sta NES_CLOUD_OBJ,Y
        lda cloud_x,X
        sec
        sbc #4
        asl
        asl
        asl
        clc
        adc cloud_subpixel,X
        sta NES_CLOUD_OBJ+2,Y   ; first cloud X
        lda cloud_x+8,X
        sec
        sbc #4
        asl
        asl
        asl
        clc
        adc cloud_subpixel+8,X
        sta NES_CLOUD_OBJ+6,Y   ; second cloud X
        iny
        cpy #2
        bcc @floor
@done:  rts

; Original OAM entries 7/8: the mallet sprite of each player, from the
; same pose code that draws it ($F8: not drawn). Only a jumping climber
; (handler 4) or a swing at pose 9 (handler 5) lets $D3B3 test it; A <> 0
; when one of them can.
nes_mallets:
        lda #$F8
        sta NES_MALLET_OAM
        sta NES_MALLET_OAM+4
        lda #0
        sta nes_hammer
        ldx #1
@check: lda NES_HANDLER,X
        cmp #4
        beq @jump
        cmp #5
        bne @next_check
        lda NES_PLAYER_POSE,X
        cmp #9
        bne @next_check
@any:   inc nes_hammer
@next_check:
        dex
        bpl @check
        lda nes_hammer
        beq @done
        jmp nes_mallet_oam
; $D3D9: a jumping mallet tests only Nitpicker (when flying) and icicles
; (hanging, state 2, or falling) through $DB1D.
@jump:  lda NES_OBJ_STATE
        bmi @any
        ldy #2
@icicle:
        lda NES_OBJ_STATE+8,Y
        bmi @any
        cmp #2
        beq @any
        dey
        bpl @icicle
        bmi @next_check
@done:  rts

; The entry of each climber that $D3B3 tests (nes_mallets), as
; actor_player draws its mallet: a jump's raised mallet (pose 6 for eleven
; air ticks, then pose 7; the first air tick still draws the walk) or the
; windup of a ground swing (pose 9). OAM = logical position -52/-18.
nes_mallet_oam:
        ldx #1
@player:
        cpx player_count
        bcs @next
        txa
        beq :+
        lda #PLAYER_SIZE
:       tay                     ; PLAYER_STATES offset
        lda NES_HANDLER,X
        cmp #4
        beq @jump
        cmp #5
        bne @next
        lda NES_PLAYER_POSE,X
        cmp #9
        bne @next
        lda #8                  ; windup
        bne @face
@jump:  lda PLAYER_STATES+14,Y  ; air age
        and #$0F
        beq @next
        cmp #12
        lda #4
        bcc @face
        lda #6
@face:  ora PLAYER_STATES+10,Y
        stx work2
        tax
        lda PLAYER_STATES+5,Y
        clc
        adc mallet_y,X
        sec
        sbc #18
        sta tmp
        lda PLAYER_STATES+3,Y
        clc
        adc mallet_xlo,X
        sec
        sbc #52
        pha
        lda work2
        asl
        asl
        tay
        pla
        sta NES_MALLET_OAM+3,Y
        lda tmp
        sta NES_MALLET_OAM,Y
        ldx work2
@next:  dex
        bpl @player
        lda nes_hammer
        rts

; Original $D212, after the hammer hits and before the touch hits: two
; climbers that touch push each other apart, or trade their fall speeds
; when both are in the air. Its Y nudges, the fall speeds $E6/$E8, the
; walk speed $6E and the cleared latches $86/$88 go back to the players
; here; X, $62 and $68 come back with nes_import.
.segment "DATA"
nes_bump:
        lda NES_PLAYER_FLOOR    ; $D212's own first test: without both
        and NES_PLAYER_FLOOR+1  ; climbers on the screen it does nothing
        beq @done
        jsr N_D2D9              ; nor when they are apart ($D2D9 only reads)
        bcs @done
        lda #$FF                ; it stores $6E only when it bumps and
        sta NES_WALK            ; clears $86 only when both are in the air
        sta NES_WALK+1
        sta NES_LATCH
        jsr nes_body_bump
        lda NES_WALK
        and NES_WALK+1
        and NES_LATCH
        cmp #$FF
        beq @done               ; no bump
        inc nes_dirty
        ldx #1
        ldy #PLAYER_SIZE
@player:
        lda NES_PLAYER_Y,X
        clc
        adc #24
        sta PLAYER_STATES+5,Y
        lda NES_FALL,X
        sta PLAYER_STATES+15,Y
        lda NES_FALL_FRAC,X
        sta PLAYER_STATES+16,Y
        lda NES_WALK,X
        cmp #$FF
        beq :+
        sta PLAYER_STATES+21,Y  ; walk_time
:       lda NES_LATCH
        bne :+
        lda PLAYER_STATES+14,Y  ; air_init: bit 7 $86, bits 4-6 $88
        and #$0F
        sta PLAYER_STATES+14,Y
:       ldy #0
        dex
        bpl @player
@done:  rts
.segment "CODE"

; The original block debris: $D91C starts a piece when the mallet breaks
; a brick, $D9CC (transplanted, in the lower stack page) moves the six
; OAM entries $02D0-$02E7 (NES_DEBRIS_OAM) every tick, and $EC95 moves
; them with each pan tick. actor_debris draws them.
.segment "LOWCODE"
nes_debris_init:
        lda #$F8                ; stage start: no piece ($C26B clears $063F)
        ldy #20
:       sta NES_DEBRIS_OAM,Y
        dey
        dey
        dey
        dey
        bpl :-
        lda #0
        sta debris_pend
        sta debris_pend+1
        sta debris_brown
        sta debris_any
        rts

.segment "HIGH"
; break_block, before the cell clears, X = its map index: what $D91C needs
; from the brick. Its floor $D7 is wrld+1: palette 2 from floor 6, else 3,
; with $D9AD's earth colours from floor 3. $DAF2's $063E picks tile $0B for
; an original value 2 (here only a lower-plane value 2).
debris_note:
        lda wrld
        cmp #5
        lda #2
        bcs @tile               ; $D7 >= 6
        lda wrld
        cmp #2
        lda #3
        bcc @tile               ; $D7 < 3
        lda #$43
@tile:  ldy break_layer
        beq @upper
        ldy floor_lower,X
        cpy #2
        bne @upper
        ora #$80
@upper: ldy player_index
        sta debris_pend,Y
        rts
.segment "CODE"

; Original $D91C for the bricks broken in this tick (debris_note): the
; first free slot starts at the mallet's OAM entry, eight pixels up and
; eight ahead ($D918), rising two pixels per tick ($FE) and stepping one
; pixel per tick the way the climber faces. The players' handlers run
; before the objects in the original tick as well. A brick breaks only in
; the air, so the mallet entry is actor_player's raised one: pose 6 for
; eleven air ticks, then pose 7 (mallet_xlo/mallet_y, OAM = logical -52/-18).
nes_debris_start:
        lda debris_pend
        ora debris_pend+1
        bne :+
        rts
:       ldx #0
@player:
        lda debris_pend,X
        jeq @next
        ldy #0
@slot:  lda NES_DEBRIS_OAM,Y
        cmp #$F8
        beq @free
        iny
        iny
        iny
        iny
        cpy #24
        bcc @slot
        jcs @clear              ; all six fly ($D955)
@free:  sty tmp
        lda debris_pend,X       ; bit 7 tile $0B, bit 6 earth, bits 0-1 palette
        and #$40
        beq :+
        sta debris_brown        ; $D9AD
:       lda debris_pend,X
        and #3
        sta NES_DEBRIS_OAM+2,Y
        lda debris_pend,X
        asl
        lda #$0A
        adc #0
        sta NES_DEBRIS_OAM+1,Y
        stx work2
        txa
        beq :+
        lda #PLAYER_SIZE
:       tay
        lda PLAYER_STATES+14,Y  ; air age
        and #$0F
        cmp #12
        lda #4
        bcc :+
        lda #6
:       ora PLAYER_STATES+10,Y  ; face
        tax
        lda PLAYER_STATES+5,Y   ; Y: py + mallet_y - 18, then 8 up
        clc
        adc mallet_y,X
        sec
        sbc #18+8
        pha
        lda PLAYER_STATES+3,Y   ; X: pxlo + mallet_xlo - 52, then 8 ahead
        clc
        adc mallet_xlo,X
        sec
        sbc #52-8               ; $D918: +8 facing right
        pha
        txa
        lsr                     ; C = face 1: -8 facing left
        pla
        bcc :+
        sbc #16
:       ldy tmp
        ldx work2
        sta NES_DEBRIS_OAM+3,Y
        pla
        sta NES_DEBRIS_OAM,Y
        tya
        lsr
        lsr
        tay
        lda #0
        sta NES_DEBRIS+$10,Y    ; $0650 speed fraction
        sta NES_DEBRIS,Y        ; $0640 Y fraction
        sta NES_DEBRIS+$20,Y    ; $0660 age (flips)
        lda #$FE
        sta NES_DEBRIS+8,Y      ; $0648 speed -2
        lda NES_FACING,X
        bne :+
        lda #$FF
:       sta NES_DEBRIS+$18,Y    ; $0658 step +1 or -1
        sta debris_any
@clear: lda #0
        sta debris_pend,X
@next:  inx
        cpx #2
        jcc @player
        rts

.segment "STACKCODE"
; Original $D9CC with the same bytes every tick, faster: each piece in
; flight (Y not $F8) moves by its 8.8 speed ($FE.00, +$40 per tick while
; below 5) and one pixel sideways, and disappears from Y $F4. Its age picks
; the next of four flips ($D9C4, the other order for a left step) on the
; first tick and every sixteenth; in between the original rewrites the
; same attribute.
nes_debris_tick:
        ldy #20
@piece: lda NES_DEBRIS_OAM,Y
        cmp #$F8
        beq @next
        tya
        lsr
        lsr
        tax
        lda NES_DEBRIS+$10,X    ; $0650 + $0640: Y fraction
        clc
        adc NES_DEBRIS,X
        sta NES_DEBRIS,X
        lda NES_DEBRIS_OAM,Y
        adc NES_DEBRIS+8,X      ; $0648 speed
        sta NES_DEBRIS_OAM,Y
        cmp #$F4
        bcs @gone
        lda NES_DEBRIS+$18,X    ; $0658 step, C clear
        adc NES_DEBRIS_OAM+3,Y
        sta NES_DEBRIS_OAM+3,Y
        inc NES_DEBRIS+$20,X    ; $0660 age
        lda NES_DEBRIS+$20,X
        cmp #1
        beq @flip
        and #$0F
        bne @speed
@flip:  lda NES_DEBRIS+$20,X
        and #$30
        lsr
        lsr
        lsr
        lsr
        sta tmp
        lda NES_DEBRIS+$18,X
        bpl :+
        lda tmp                 ; a left step: entries 4-7
        ora #4
        sta tmp
:       stx work2
        ldx tmp
        lda NES_DEBRIS_OAM+2,Y
        and #3
        ora debris_flips,X
        sta NES_DEBRIS_OAM+2,Y
        ldx work2
@speed: lda NES_DEBRIS+8,X
        cmp #5
        bpl @next
        lda NES_DEBRIS+$10,X
        clc
        adc #$40
        sta NES_DEBRIS+$10,X
        bcc @next
        inc NES_DEBRIS+8,X
@next:  dey
        dey
        dey
        dey
        bpl @piece
        rts
@gone:  lda #$F8
        sta NES_DEBRIS_OAM,Y
        lda #0
        sta NES_DEBRIS_OAM+3,Y
        beq @next

; Original $EC95 for the debris entries: each pan tick moves every OAM
; entry four lines down; from $F2 on it parks at $F8.
nes_debris_pan:
        ldy #20
@slot:  lda NES_DEBRIS_OAM,Y
        cmp #$F2
        bcc :+
        lda #$F4
:       clc
        adc #4
        sta NES_DEBRIS_OAM,Y
        dey
        dey
        dey
        dey
        bpl @slot
        rts
.segment "CODE"

; After a tick: ended attacks, pushes and sound go back to the players.
nes_import:
        ldx #1
@player:
        cpx player_count
        bcs @next
        txa
        asl
        asl
        asl
        asl
        asl
        tay
        lda PLAYER_STATES,Y     ; out (negative lives): not exported either
        bmi @next
        lda nes_attack_end,X
        beq @push
        lda #0
        sta nes_attack_end,X
        sta PLAYER_STATES+13,Y  ; original D07C: handler 1, pose 0
        sta GROUND_SWING,X
        inc nes_dirty
@push:  lda PLAYER_STATES+3,Y   ; a bear touch or a stone post moves the
        sec                     ; player
        sbc #52
        cmp NES_PLAYER_X,X
        beq @turn
        lda NES_PLAYER_X,X
        clc
        adc #52
        sta PLAYER_STATES+3,Y
        lda #0
        adc #0
        sta PLAYER_STATES+4,Y
        inc nes_dirty
@turn:  lda NES_PUSH_DIR,X      ; $D383 (bear) and $E176 (stone post) turn
        cmp PLAYER_STATES+20,Y  ; the climber
        beq @face
        sta PLAYER_STATES+20,Y
        inc nes_dirty
@face:  lda #1
        sec
        sbc NES_FACING,X
        cmp PLAYER_STATES+10,Y
        beq @next
        sta PLAYER_STATES+10,Y
        inc nes_dirty
@next:  dex
        bpl @player
@done:  rts                     ; (the objects' sound requests go to the engine)

; Back in I/O mode: an object touched a player ($D446): the original death
; starts (player_dying_tick). Ended attacks and pushes reload zero page.
nes_apply:
        ldx #1
@player:
        lda nes_killed,X
        beq @next
        lda #0
        sta nes_killed,X
        sta nes_spin,X
        sta nes_spin_t,X
        lda #1
        sta nes_dying,X
        lda #$40                ; $D45C: the fast timer $32
        sta nes_death_t,X
@next:  dex
        bpl @player
        lda nes_dirty
        beq @done               ; nothing changed: zero page is still current
        lda #0
        sta nes_dirty
        sta player_index
        jmp play_context_load
@done:  rts

; Original $D111: when a climber's timer $32 has run out, objects frozen by
; a touch ($20) move again.
.segment "HELPERS"
nes_release_frozen:
        ldy #NES_OBJECTS-1
@object:
        lda NES_OBJ_STATE,Y
        cmp #$20
        bne @next
        lda #$FF
        sta NES_OBJ_STATE,Y
@next:  dey
        bpl @object
        rts
.segment "CODE"

; Original death ($D0AA) after an object touched the climber ($D446): 64
; frozen ticks, pose 11 for the last ones, then $D127/$D133 every tick:
; a 1.5-line rise against the original gravity, through every floor, while
; $CD95 turns the sprite every fourth tick. Below the screen ($D463) a life
; is lost unless the climber is protected, and $3F waits eight slow ticks
; before $EB8A brings it back on its death floor. Zero page holds it.
player_dying_tick:
        ldx player_index
        lda nes_dying,X
        cmp #2
        beq @fall
        bcs @gone
        dec nes_death_t,X       ; $CB9D runs the timer before $D0AA
        bne @done
        inc nes_dying,X         ; falling
        lda #0
        sta air_init            ; $D0C0 cleared $E0: $C83D starts a new fall
        jsr nes_release_frozen
@fall:  lda #1                  ; $D127 every tick
        sta rise_int
        lda #$80
        sta rise_frac
        lda #$17                ; $2F = 1: the death gravity $C839[1]
        sta nes_gravity
        lda py
        sta prevpy
        jsr vertical_step       ; $D133/$C83D
        lda #$22
        sta nes_gravity
        ldx player_index
        inc nes_spin_t,X        ; $CD95 with Y=3
        lda nes_spin_t,X
        cmp #4
        bcc @below
        lda #0
        sta nes_spin_t,X
        lda nes_spin,X
        clc
        adc #1
        and #3
        sta nes_spin,X
@below: lda py                  ; $D463: body Y+25 below the screen
        cmp #240
        bcc @done
        lda invul_t             ; $D47D: a protected climber keeps the life
        bne :+
        dec lives
        bpl :+
        lda #SFX1_GAME_OVER     ; $ED10: this climber is out
        sta snd_sfx1_req
:       lda #3
        sta nes_dying,X
        lda #8                  ; $D483: $3F
        sta nes_death_t,X
@done:  rts
@gone:  lda timer_divider       ; $3F counts every eleventh tick
        bne @done
        dec nes_death_t,X
        bne @done
        ldy nes_dying,X
        lda #0
        sta nes_dying,X
        lda lives               ; $EB8E: a climber with no spare life (0)
        bpl @respawn            ; still comes back; negative is out
        lda player_count
        cmp #2
        beq @done               ; the other climber goes on
        jmp enter_game_over
@respawn:
        cpy #4                  ; a fall: respawn_player reads the body Y
        beq @place
        lda NES_OBJ_0382,X      ; $EBBE: the death floor, clamped to the
                                ; three lower visible floors
        sec
        sbc #1
        sec
        sbc cam
        bcc @bottom
        cmp #3
        bcc :+
        lda #2
:       tay
        lda respawn_band,Y
        bne @band
@bottom:lda respawn_band
@band:  sta py                  ; respawn_player picks the floor from py
        lda #0
        sta normal_pan_high,X
@place: jmp respawn_player
respawn_band: .byte 200,150,72

; Original $D463 for a climber whose body fell below the screen: a life is
; lost unless it is protected ($2D), and $3F waits eight slow ticks before
; $EB8A brings it back (nes_dying 4: the floor follows from its body Y).
player_fell:
        lda invul_t
        bne :+
        dec lives
        bpl :+
        lda #SFX1_GAME_OVER     ; $ED10: this climber is out
        sta snd_sfx1_req
:       ldx player_index
        lda #4
        sta nes_dying,X
        lda #8
        sta nes_death_t,X
        rts

; --- called from the original code ---------------------------------------
; Original $D446 with X = player: handler 7 and the death floor in $0382.
.segment "IOCODE"               ; only the code under I/O calls it
glue_kill_player:
        lda #7
        sta NES_HANDLER,X
        lda NES_PLAYER_FLOOR,X
        sta NES_OBJ_0382,X
        lda #1
        sta nes_killed,X
        lda #SFX3_DEATH         ; $D45E
        sta snd_sfx3_req
        rts
.segment "CODE"

; Original $D9C4: the flips of a right-moving, then a left-moving piece.
.segment "IODATA"
debris_flips: .byte $00,$40,$C0,$80,$40,$00,$80,$C0
; Original $D41C/$D07C: the hammer hit an object; the attack ends.
.segment "IODATA"               ; only the code under I/O calls it
glue_end_attack:
        lda #1
        sta NES_HANDLER,X
        lda #0
        sta NES_PLAYER_POSE,X
        lda #1
        sta nes_attack_end,X
        rts
.segment "CODE"

; Original $DE4B wrote ice into the upper plane: repaint that cell.
.segment "IOMIDCODE"            ; only the code under I/O calls it
glue_ice_filled:
        lda NES_ICE_FLOOR
        sec
        sbc #1
        sta wrld
        tya
        clc
        adc #8
        sta colw
        jmp cache_cell
.segment "CODE"

; Original $DEDB/$DEE1 read the block planes. NES air is $FF and the lower
; stone post is 4; the C64 planes use 0 and 3.
glue_lower_cell:
        lda (NES_TEMP+3),Y
        beq glue_air
        cmp #3
        bne glue_cell
        lda #4
glue_cell:
        ora #0
        rts
glue_upper_cell:
        lda (NES_TEMP+3),Y
        beq glue_air
        cmp #2                  ; C64 upper 2 is the NES stone post 4
        bne glue_cell
        lda #4
        rts
glue_air:
        lda #$FF
        rts
