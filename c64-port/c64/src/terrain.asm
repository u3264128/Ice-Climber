; NES mountain sections from $E79D-$E87C. The wall is six tile rows high,
; with a sloping inner edge, rock texture, a two-tile floor number, and
; a separate fluted wall on cloud-only floors. Cache rows grow upwards.
.segment "DATA"

cache_mountain_walls:
        lda #1
        sta cache_world         ; numbered sections 1..8, above floor F-1
@section:
        ldx cache_world
        lda mountain_width-1,X
        sta cache_wrap_min
        lda #<mountain_rock
        sta src
        lda #>mountain_rock
        sta src+1
        ; NES $E64E selects descriptor F-2; only types $A0..$E0 use
        ; the vertical cloud wall ($E791), not mixed ice/cloud floors.
        lda floor_types-1,X
        and #$E0
        cmp #$A0
        bcc @plain
        lda #<mountain_cloud
        sta src
        lda #>mountain_cloud
        sta src+1
@plain: jsr cache_pointer
        lda dst
        sec
        sbc #32                 ; lower ice of floor F = cache row 6F+1
        sta dst
        sta colptr
        bcs @first
        dec dst+1
        dec colptr+1
@first: lda #0
        sta cache_layer         ; source row R; cache row = 6F+1-R
@row:   lda #15                 ; MC individual colour 7: yellow highlight
        ldx cache_world
        cpx #6
        bcc @colour
        lda #9                  ; sections 6..8 occupy cache rows 32..49
@colour:
        sta blank_colour
        lda #6
        sec
        sbc cache_wrap_min
        sta tmp
        asl
        clc
        adc tmp
        asl
        clc
        adc cache_layer
        sta tmp                 ; omit outer source columns on low floors
        lda #0
        sta cell_column
@left:  jsr mountain_put
        lda cell_column
        cmp cache_wrap_min
        bcc @left
        lda #32
        sec
        sbc cache_wrap_min
        sta cell_column
        lda cache_layer
        clc
        adc #36
        sta tmp
@right: jsr mountain_put
        lda cell_column
        cmp #32
        bcc @right
        ; Original floor digits occupy rows 2/3, two tiles high.
        lda cache_layer
        cmp #2
        bcc @next_row
        cmp #4
        bcs @next_row
        ldx cache_world
        dex
        cmp #3
        beq @lower_digit
        lda mountain_number_top,X
        jmp @number
@lower_digit:
        lda mountain_number_bottom,X
@number:
        pha
        lda cache_wrap_min
        sec
        sbc #3
        tay
        pla
        sta (dst),Y
        pha
        lda #34
        sec
        sbc cache_wrap_min
        tay
        pla
        sta (dst),Y
        lda blank_colour
        and #7                 ; original narrow digit, hires on black
        sta (colptr),Y
        lda cache_world
        asl
        clc
        adc cache_world
        asl
        clc
        adc #1
        sec
        sbc cache_layer
        tax
        lda cache_wrap_min
        sec
        sbc #3
        asl
        asl
        asl
        asl
        ora #ROW_WALLS|ROW_NUMBER
        ora blank_colour
        sta ROW_KIND,X
        lda cache_wrap_min
        sec
        sbc #3
        tay
        lda blank_colour
        and #7
        sta (colptr),Y
@next_row:
        inc cache_layer
        lda cache_layer
        cmp #6
        beq @next_section
        lda dst
        sec
        sbc #32
        sta dst
        sta colptr
        bcs @same_page
        dec dst+1
        dec colptr+1
@same_page:
        jmp @row
@next_section:
        inc cache_world
        lda cache_world
        cmp #9
        beq @water
        jmp @section
@water:
        ldx #31
@surface:
        lda #WATER
        sta WORLD_CACHE,X       ; the water directly below the starting ledge
        lda #3
        sta COLOUR_CACHE,X
        dex
        bpl @surface
        rts

mountain_put:
        ldy tmp
        lda (src),Y
        ldy cell_column
        sta (dst),Y
        lda blank_colour
        sta (colptr),Y
        lda tmp
        clc
        adc #6
        sta tmp
        inc cell_column
        rts

mountain_width: .byte 4,4,5,5,5,6,6,6
; The side rock is immutable. Full floor redraws and single-cell repairs
; leave its extra columns in place as the mountain widens.
terrain_floor_bounds:
        ldx cache_world
        lda cache_layer
        beq @width
        txa
        clc
        adc #9
        tax
@width: lda terrain_floor_widths,X
        sta cache_wrap_min
        eor #$FF
        clc
        adc #33
        sta cache_wrap_max
        rts
terrain_floor_widths:
        .byte 4,4,5,5,5,6,6,6,4 ; upper layer, next section's stone ledge
        .byte 4,4,4,5,5,5,6,6,6 ; lower layer, this section's first row
mountain_number_top:
        .byte NES_TILE_EC,NES_TILE_EE,NES_TILE_F0,NES_TILE_F2
        .byte NES_TILE_F4,NES_TILE_F6,NES_TILE_F8,NES_TILE_FA
mountain_number_bottom:
        .byte NES_TILE_ED,NES_TILE_EF,NES_TILE_F1,NES_TILE_F3
        .byte NES_TILE_F5,NES_TILE_F7,NES_TILE_F9,NES_TILE_FB

; Columns, six rows each. Every section ends with a stone ledge ($EB).
mountain_rock:
        .byte NES_TILE_A4,NES_TILE_A5,NES_TILE_A6,NES_TILE_A7,NES_TILE_A8,NES_TILE_EB
        .byte NES_TILE_AA,NES_TILE_AB,NES_TILE_AC,NES_TILE_AD,NES_TILE_AE,NES_TILE_EB
        .byte NES_TILE_B0,NES_TILE_B1,NES_TILE_B2,NES_TILE_B3,NES_TILE_B4,NES_TILE_EB
        .byte NES_TILE_B6,NES_TILE_B7,NES_TILE_B8,NES_TILE_B9,NES_TILE_BA,NES_TILE_EB
        .byte NES_TILE_BC,NES_TILE_BD,NES_TILE_BE,NES_TILE_BF,NES_TILE_C0,NES_TILE_EB
        .byte NES_TILE_C2,NES_TILE_C3,NES_TILE_C4,NES_TILE_C5,NES_TILE_C6,NES_TILE_EB
        .byte NES_TILE_C8,NES_TILE_C9,NES_TILE_CA,NES_TILE_CB,NES_TILE_CC,NES_TILE_EB
        .byte NES_TILE_CE,NES_TILE_CF,NES_TILE_D0,NES_TILE_D1,NES_TILE_D2,NES_TILE_EB
        .byte NES_TILE_D4,NES_TILE_D5,NES_TILE_D6,NES_TILE_D7,NES_TILE_D8,NES_TILE_EB
        .byte NES_TILE_DA,NES_TILE_DB,NES_TILE_DC,NES_TILE_DD,NES_TILE_DE,NES_TILE_EB
        .byte NES_TILE_E0,NES_TILE_E1,NES_TILE_E2,NES_TILE_E3,NES_TILE_E4,NES_TILE_EB
        .byte NES_TILE_E6,NES_TILE_E7,NES_TILE_E8,NES_TILE_E9,NES_TILE_EA,NES_TILE_EB
mountain_cloud:
        .repeat 5
        .byte NES_TILE_42,NES_TILE_43,NES_TILE_44,NES_TILE_45,NES_TILE_46,NES_TILE_EB
        .endrep
        .byte NES_TILE_48,NES_TILE_49,NES_TILE_4A,NES_TILE_4B,NES_TILE_4C,NES_TILE_EB
        .byte NES_TILE_4E,NES_TILE_4F,NES_TILE_50,NES_TILE_51,NES_TILE_52,NES_TILE_EB
        .repeat 5
        .byte NES_TILE_9D,NES_TILE_9E,NES_TILE_9F,NES_TILE_A0,NES_TILE_A1,NES_TILE_EB
        .endrep

.segment "CODE"
