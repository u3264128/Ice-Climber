; Shared text routines write both display buffers. The logo keeps its font.
ui_text:
        lda #UI_FONT
        ldx state
        bne @font
        lda #TITLE_UI_FONT
@font:  sta ui_base
        ldx ui_row
        lda screen_row_lo,X
        clc
        adc ui_col
        sta dst
        sta scrptr
        sta colptr
        lda screen_row_hi,X
        adc #0
        sta dst+1
        clc
        adc #4
        sta scrptr+1
        lda dst+1
        clc
        adc #$98
        sta colptr+1
        ldy #0
@char:  lda (ui_ptr),Y
        beq @done
        cmp #'A'
        bcc @number
        cmp #'Z'+1
        bcs @blank
        sec
        sbc #'A'
        clc
        adc ui_base
        bne @put
@number:
        cmp #'0'
        bcc @blank
        cmp #'9'+1
        bcs @blank
        sec
        sbc #'0'
        ldx state
        bne @put
        clc
        adc #96
        bne @put
@blank: lda #BLANK
        ldx state
        bne @put
        lda #0
@put:   sta (dst),Y
        sta (scrptr),Y
        lda ui_colour
        sta (colptr),Y
        iny
        bne @char
@done:  rts

title_menu:
        ldx #0
@clear: lda #0
        sta SCREEN+13*40,X
        lda #1
        sta $D800+13*40,X
        inx
        bne @clear
        ldx #184
@tail:  lda #0
        sta SCREEN+13*40+255,X
        lda #1
        sta $D800+13*40+255,X
        dex
        bne @tail
        ldx #0
@font:  lda ui_font_src,X
        sta CHARSET+TITLE_UI_FONT*8,X
        inx
        cpx #208
        bne @font
        ldx #79
@digits:
        lda charset_src,X
        sta CHARSET+96*8,X
        dex
        bpl @digits
        ldx #7
@arrow: lda menu_arrow,X
        sta CHARSET+90*8,X
        dex
        bpl @arrow
        lda #1
        sta ui_colour
        lda #14
        sta ui_row
        lda #11
        sta ui_col
        lda #<menu_one
        sta ui_ptr
        lda #>menu_one
        sta ui_ptr+1
        jsr ui_text
        inc ui_row
        inc ui_row
        lda #<menu_two
        sta ui_ptr
        lda #>menu_two
        sta ui_ptr+1
        jsr ui_text
        ldy #0
        lda game_mode
        beq @one
        ldy #80
@one:   lda #0
        sta SCREEN+14*40+9
        sta SCREEN+16*40+9
        lda #90
        sta SCREEN+14*40+9,Y
        lda #1
        sta $D800+14*40+9,Y
        lda #21
        sta ui_row
        lda #<menu_keys_one
        sta ui_ptr
        lda #>menu_keys_one
        sta ui_ptr+1
        jsr ui_text
        lda game_mode
        beq @done
        inc ui_row
        lda #<menu_keys_two
        sta ui_ptr
        lda #>menu_keys_two
        sta ui_ptr+1
        jsr ui_text
@done:
        rts
menu_one: .byte "1 PLAYER",0
menu_two: .byte "2 PLAYERS",0
menu_keys_one:.byte "P1 WAD SPACE",0
menu_keys_two:.byte "P2 IJL RSHIFT",0
menu_arrow:.byte 0,$10,$18,$1C,$18,$10,0,0

binary_digits:
        ldx #0
@ten:   cmp #10
        bcc @done
        sec
        sbc #10
        inx
        bne @ten
@done:  rts

highscore_update:
        lda score_mil
        cmp high_score_mil
        bcc @done
        bne @save
        lda score_top
        cmp high_score_top
        bcc @done
        bne @save
        lda score_hi
        cmp high_score_hi
        bcc @done
        bne @save
        lda score_lo
        cmp high_score_lo
        bcc @done
@save:  lda score_lo
        sta high_score_lo
        lda score_hi
        sta high_score_hi
        lda score_top
        sta high_score_top
        lda score_mil
        sta high_score_mil
@done:  rts

; Add a six-digit BCD amount: A=low, X=middle, Y=high.
score_add:
        sta work_lo
        stx work_hi
        sty work2
        sed
        lda score_lo
        clc
        adc work_lo
        sta score_lo
        lda score_hi
        adc work_hi
        sta score_hi
        lda score_top
        adc work2
        sta score_top
        bcc @fits
        lda score_mil           ; the millions digit: the original's six BCD
        adc #0                  ; digits count tens, up to 9,999,990
        cmp #$10
        bcs @full
        sta score_mil
        bcc @fits
@full:  lda #9
        sta score_mil
        lda #$99
        sta score_lo
        sta score_hi
        sta score_top
@fits:
        cld
        jmp highscore_update

.segment "DATA"
; The last life is gone: GAME OVER with the final score(s), then the title
; after fire or about five seconds (results_tick, phase 1: no tally).
enter_game_over:
        sei
        lda #0
        sta $D015
        sta $D01A
        sta player_index
        lda #2
        sta state
        lda #1
        sta result_phase
        sta result_game_over
        lda #250
        sta result_delay
        jsr ui_restore_font
        lda #2
        sta $D018
        lda #$1B
        sta $D011
        lda #MUSIC_LOGO         ; the title theme carries on into the title
        sta snd_music_req
        jsr result_clear
        lda #1
        sta ui_colour
        lda #7
        sta ui_row
        lda #15
        sta ui_col
        lda #<result_game_over_text
        sta ui_ptr
        lda #>result_game_over_text
        sta ui_ptr+1
        jsr ui_text
        lda #11
        sta ui_row
        lda #12
        sta ui_col
        lda #<result_p1_score
        sta ui_ptr
        lda #>result_p1_score
        sta ui_ptr+1
        jsr ui_text
        lda #<(SCREEN+11*40+22)
        sta dst
        lda #>(SCREEN+11*40+22)
        sta dst+1
        lda PLAYER_STATES+30
        jsr result_mil
        lda PLAYER_STATES+31
        ldx #0
        jsr result_bcd
        lda PLAYER_STATES+2
        ldx #2
        jsr result_bcd
        lda PLAYER_STATES+1
        ldx #4
        jsr result_bcd
        lda player_count
        cmp #2
        bne @hi
        lda #13
        sta ui_row
        lda #<result_p2_score
        sta ui_ptr
        lda #>result_p2_score
        sta ui_ptr+1
        jsr ui_text
        lda #<(SCREEN+13*40+22)
        sta dst
        lda #>(SCREEN+13*40+22)
        sta dst+1
        lda PLAYER_STATES+PLAYER_SIZE+30
        jsr result_mil
        lda PLAYER_STATES+PLAYER_SIZE+31
        ldx #0
        jsr result_bcd
        lda PLAYER_STATES+PLAYER_SIZE+2
        ldx #2
        jsr result_bcd
        lda PLAYER_STATES+PLAYER_SIZE+1
        ldx #4
        jsr result_bcd
@hi:    lda #16
        sta ui_row
        lda #<result_hi_score
        sta ui_ptr
        lda #>result_hi_score
        sta ui_ptr+1
        jsr ui_text
        lda #<(SCREEN+16*40+22)
        sta dst
        lda #>(SCREEN+16*40+22)
        sta dst+1
        lda high_score_mil
        jsr result_mil
        lda high_score_top
        ldx #0
        jsr result_bcd
        lda high_score_hi
        ldx #2
        jsr result_bcd
        lda high_score_lo
        ldx #4
        jsr result_bcd
        rts

result_game_over_text: .byte "GAME OVER",0
result_p1_score: .byte "P1 SCORE",0
result_p2_score: .byte "P2 SCORE",0
result_hi_score: .byte "HI SCORE",0
.segment "CODE"

enter_results:
        sei
        lda #0
        sta $D015
        sta $D01A
        sta result_phase
        sta tally_player
        sta player_index
        sta result_ticks
        ldx #5
@clear: sta result_pending,X
        dex
        bpl @clear
        lda #2
        sta state
        jsr ui_restore_font
        lda #100
        sta result_delay
        lda #2
        sta $D018
        lda #$1B
        sta $D011
        lda #MUSIC_OFF          ; $D4F5: no music on the result screen
        sta snd_music_req
@prize: jsr context_load
        lda completed_mountains ; NES $EA8E counts progress, not menu selection
        cmp #10
        bcc @type
        lda #9
@type:  tay
        lda fruit_points_hi,Y
        sta work_hi
        ldx player_index
        lda fruit_counts,X
        sta bonus_copy_count
        txa
        asl
        clc
        adc player_index
        tax
@fruit: lda bonus_copy_count
        beq @condor
        sed
        lda result_pending+1,X
        clc
        adc work_hi
        sta result_pending+1,X
        lda result_pending+2,X
        adc #0
        sta result_pending+2,X
        cld
        dec bonus_copy_count
        jmp @fruit
@condor:
        lda player_index
        clc
        adc #1
        cmp bonus_winner
        bne @life
        sed
        lda result_pending+1,X
        clc
        adc condor_prize_hi,Y
        sta result_pending+1,X
        lda result_pending+2,X
        adc condor_prize_top,Y
        sta result_pending+2,X
        cld
@life:  jsr result_normal_points
        ldx player_index
        lda completed_mountains
        cmp #4                 ; fruit on the fifth completed attempt
        bne @store
        lda fruit_counts,X
        beq @store
        lda extra_life_given,X
        bne @store
        lda #1
        sta extra_life_given,X
        lda lives
        cmp #9
        bcs @store
        inc lives
@store: jsr context_store
        inc player_index
        lda player_index
        cmp player_count
        jcc @prize
        lda #0
        sta player_index
        jsr context_load
        jmp result_draw

; NES $E9CE tallies normal-stage events here, rather than awarding height
; or seal-contact points during play. Ice blocks scale with mountain number.
.segment "EXTRA"
result_normal_points:
        lda player_index
        asl
        asl
        clc
        adc player_index
        sta ui_index
        lda player_index
        asl
        clc
        adc player_index
        sta bonus_copy_index
        ldx ui_index
        lda SCORE_COUNTS+2,X
        sta bonus_copy_count
        lda #0
        sta work_lo
        lda #4                 ; carried ice:400; icicles do not score
        sta work_hi
        jsr result_repeat_points
        ldx ui_index
        lda SCORE_COUNTS+3,X
        sta bonus_copy_count
        lda #8                 ; Nitpicker:800; seals have no score counter
        sta work_hi
        jsr result_repeat_points
        lda mountain
        ldx phase_counter
        beq @number
        dex
        beq @number
@cycle: clc
        adc #32
        dex
        bne @cycle
@number:
        jsr binary_digits
        stx work_hi
        asl
        asl
        asl
        asl
        sta work_lo
        ldx ui_index
        lda SCORE_COUNTS+4,X
        sta bonus_copy_count
        ; fall through
result_repeat_points:
        lda bonus_copy_count
        beq @done
        ldx bonus_copy_index
@add:   sed
        lda result_pending,X
        clc
        adc work_lo
        sta result_pending,X
        lda result_pending+1,X
        adc work_hi
        sta result_pending+1,X
        lda result_pending+2,X
        adc #0
        sta result_pending+2,X
        cld
        dec bonus_copy_count
        bne @add
@done:  rts

.segment "CODE"
results_tick:
        lda result_phase
        beq @tally
        lda firehit
        bne @next
        dec result_delay
        bne @done
@next:  lda result_game_over
        beq @mountain
        lda #0
        sta result_game_over
        jmp enter_title
@mountain:
        jmp next_mountain
@done:  rts
@tally: lda firehit
        beq @step
        lda #0
        sta player_index
@fast:  jsr context_load
        lda player_index
        asl
        clc
        adc player_index
        tax
        lda result_pending+2,X
        tay
        lda result_pending+1,X
        sta work_hi
        lda result_pending,X
        sta work_lo
        lda #0
        sta result_pending,X
        sta result_pending+1,X
        sta result_pending+2,X
        ldx work_hi
        lda work_lo
        jsr score_add
        jsr context_store
        inc player_index
        lda player_index
        cmp player_count
        bcc @fast
        jmp @complete
@step:  lda tally_player
        cmp player_count
        bcs @complete
        sta player_index
        jsr context_load
        lda player_index
        asl
        clc
        adc player_index
        tax
        lda result_pending,X
        ora result_pending+1,X
        ora result_pending+2,X
        bne @amount
        inc tally_player
        jmp @restore
@amount:
        lda #1
        sta work_hi
        lda result_pending+2,X
        bne @thousand
        lda result_pending+1,X
        cmp #$10
        bcc @hundreds
@thousand:
        lda #$10
        sta work_hi
@subtract:
        sed
        lda result_pending+1,X
        sec
        sbc work_hi
        sta result_pending+1,X
        lda result_pending+2,X
        sbc #0
        sta result_pending+2,X
        cld
        lda #0
        ldx work_hi
        ldy #0
@add:   jsr score_add
        jsr context_store
        lda #SFX2_TICK          ; $EA31: every tally step
        sta snd_sfx2_req
        jmp @restore
@hundreds:
        cmp #0
        bne @subtract           ; (A = the hundreds byte)
        lda result_pending,X    ; only tens and ones are left (ice blocks:
        pha                     ; ten points per mountain): all at once,
        lda #0                  ; or a hundreds step would borrow from an
        sta result_pending,X    ; empty total
        pla
        ldx #0
        ldy #0
        beq @add
@restore:
        lda #0
        sta player_index
        jsr context_load
        jmp result_draw
@complete:
        lda #1
        sta result_phase
        lda #75
        sta result_delay
        jmp @restore

.segment "DATA"
result_clear:
        ldx #0
@clear: lda #BLANK
        sta SCREEN,X
        sta SCREEN+$100,X
        sta SCREEN+$200,X
        sta SCREEN+$300,X
        sta BACK_SCREEN,X
        sta BACK_SCREEN+$100,X
        sta BACK_SCREEN+$200,X
        sta BACK_SCREEN+$300,X
        lda #1
        sta $D800,X
        sta $D900,X
        sta $DA00,X
        sta $DB00,X
        inx
        bne @clear
        rts
.segment "CODE"
result_draw:
        lda result_ticks
        bne @text
        inc result_ticks
        jsr result_clear
@text:
        lda #1
        sta ui_colour
        lda #4
        sta ui_row
        lda #11
        sta ui_col
        lda #<result_mountain
        sta ui_ptr
        lda #>result_mountain
        sta ui_ptr+1
        jsr ui_text
        lda mountain
        jsr binary_digits
        stx SCREEN+4*40+21
        sta SCREEN+4*40+22
        lda #6
        sta ui_row
        lda #<result_time
        sta ui_ptr
        lda #>result_time
        sta ui_ptr+1
        lda bonus_winner
        beq @reason
        lda #<result_condor
        sta ui_ptr
        lda #>result_condor
        sta ui_ptr+1
@reason:
        jsr ui_text
        lda #9
        sta ui_row
        lda #<result_p1
        sta ui_ptr
        lda #>result_p1
        sta ui_ptr+1
        jsr ui_text
        lda fruit_counts
        sta SCREEN+9*40+21
        lda #11
        sta ui_row
        lda #<result_score_text
        sta ui_ptr
        lda #>result_score_text
        sta ui_ptr+1
        jsr ui_text
        lda #<(SCREEN+11*40+18)
        sta dst
        lda #>(SCREEN+11*40+18)
        sta dst+1
        lda PLAYER_STATES+30
        jsr result_mil
        lda PLAYER_STATES+31
        ldx #0
        jsr result_bcd
        lda PLAYER_STATES+2
        ldx #2
        jsr result_bcd
        lda PLAYER_STATES+1
        ldx #4
        jsr result_bcd
        lda player_count
        cmp #2
        bne @footer
        lda #14
        sta ui_row
        lda #<result_p2
        sta ui_ptr
        lda #>result_p2
        sta ui_ptr+1
        jsr ui_text
        lda fruit_counts+1
        sta SCREEN+14*40+21
        lda #16
        sta ui_row
        lda #<result_score_text
        sta ui_ptr
        lda #>result_score_text
        sta ui_ptr+1
        jsr ui_text
        lda #<(SCREEN+16*40+18)
        sta dst
        lda #>(SCREEN+16*40+18)
        sta dst+1
        lda PLAYER_STATES+PLAYER_SIZE+30
        jsr result_mil
        lda PLAYER_STATES+PLAYER_SIZE+31
        ldx #0
        jsr result_bcd
        lda PLAYER_STATES+PLAYER_SIZE+2
        ldx #2
        jsr result_bcd
        lda PLAYER_STATES+PLAYER_SIZE+1
        ldx #4
        jsr result_bcd
@footer:
        lda #21
        sta ui_row
        lda #<result_continue
        sta ui_ptr
        lda #>result_continue
        sta ui_ptr+1
        jsr ui_text
        rts
; A = millions digit: drawn just left of the six digits at dst, only
; when there is one (the screen was cleared to BLANK).
result_mil:
        beq @none
        pha
        lda dst
        bne :+
        dec dst+1
:       dec dst
        pla
        ldy #0
        sta (dst),Y
        inc dst
        bne @none
        inc dst+1
@none:  rts

result_bcd:
        pha
        lsr
        lsr
        lsr
        lsr
        stx tmp
        ldy tmp
        sta (dst),Y
        pla
        and #15
        iny
        sta (dst),Y
        rts
result_mountain: .byte "MOUNTAIN",0
result_condor: .byte "CONDOR CAUGHT",0
result_time: .byte "BONUS OVER",0
result_p1: .byte "P1 FRUIT",0
result_p2: .byte "P2 FRUIT",0
result_score_text: .byte "SCORE",0
result_continue: .byte "FIRE TO CONTINUE",0

; Gameplay uses the source terrain font throughout the viewport.
playfield_font:
        lda #$18
        sta $D016
        jmp unpack_terrain
ui_restore_font:
        ldx #79
@digit: lda charset_src,X
        sta CHARSET,X
        dex
        bpl @digit
        ldx #207
@font:  lda ui_font_src,X
        sta CHARSET+UI_FONT*8,X
        dex
        bne @font
        lda ui_font_src
        sta CHARSET+UI_FONT*8
        rts

