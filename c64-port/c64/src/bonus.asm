.segment "EXTRA"

bonus_platform_lo:
        .repeat 8,I
        .byte <(bonus_platform_src+I*97)
        .endrep
bonus_platform_hi:
        .repeat 8,I
        .byte >(bonus_platform_src+I*97)
        .endrep
bonus_cloud_lo:
        .repeat 8,I
        .byte <(bonus_cloud_src+I*31)
        .endrep
bonus_cloud_hi:
        .repeat 8,I
        .byte >(bonus_cloud_src+I*31)
        .endrep

enter_bonus:
        sei
        jsr bonus_player_art
        lda #0
        sta $D011
        sta $D015
        sta $D01A
        sta bonus_camera
        sta bonus_camera+1
        sta fruit_counts
        sta fruit_counts+1
        sta bonus_out
        sta bonus_out+1
        sta BONUS_WALL_SKIP
        sta BONUS_WALL_SKIP+1
        sta bonus_winner
        sta bonus_reason
        sta bonus_requested
        lda #3
        sta state
        lda #40                 ; $F6A4: 40.00 counted down for 2395 ticks
        sta bonus_left
        lda #55
        sta bonus_ticks
        lda #0
        sta bonus_pan
        sta bonus_end_wait
        lda #15
        sta fruit_mask
        lda #168                ; $C3D1: condor X $70, $C379: flying left
        sta condor_xlo
        lda #0
        sta condor_xhi
        sta condor_dir
        jsr bonus_prepare_geometry
        jsr view_init
        jsr bonus_fruit_index
        jsr cache_bonus
        lda #0
        sta player_index
@player:
        lda player_count
        cmp #2
        bne @reset
        jsr context_load
@reset: lda #0
        sta pxhi
        sta curfloor
        sta air_init
        sta move_dir
        sta skid_t
        sta hammer_t
        sta attack_t
        sta vy
        sta walk_time
        ldx player_index
        lda lives               ; negative: out of the game
        bpl @live
        lda #1
        sta bonus_out,X
@live:
        lda #216
        sta py
        sta prevpy
        lda #100
        ldx player_index
        beq @position
        lda #220
@position:
        sta pxlo
        lda #1
        sta onground
        jsr context_store
        inc player_index
        lda player_index
        cmp player_count
        bcc @player
        lda #0
        sta player_index
        jsr context_load
        lda #MUSIC_LOGO        ; $C386: the bonus plays the logo theme
        sta snd_music_req
        jsr actors_reset
        jsr fruit_seed_init
        rts

.segment "HIGH"
; Geometry setup is shared by the original opening flyover and bonus play.
bonus_prepare_geometry:
        lda mountain
        sec
        sbc #1
        and #7
        tax
        lda bonus_platform_lo,X
        sta bonus_platform_ptr
        sta world_ptr
        lda bonus_platform_hi,X
        sta bonus_platform_ptr+1
        sta world_ptr+1
        ldy #0
        lda (world_ptr),Y
        sta bonus_platform_count
        lda bonus_cloud_lo,X
        sta src
        lda bonus_cloud_hi,X
        sta src+1
        lda (src),Y
        sta bonus_cloud_count
        iny
        ldx #0
@cloud: lda (src),Y
        sta bonus_cloud_hlo,X
        iny
        lda (src),Y
        sta bonus_cloud_hhi,X
        iny
        lda (src),Y
        sta bonus_cloud_speed,X
        iny
        lda (src),Y
        sta bonus_cloud_dir,X
        iny
        lda (src),Y
        sta bonus_cloud_width,X
        iny
        lda #232
        sta bonus_cloud_x,X
        lda #0
        sta bonus_cloud_frac,X
        sta bonus_cloud_motion,X
        inx
        cpx bonus_cloud_count
        bcc @cloud
        rts
.segment "EXTRA"

cache_bonus:
        jsr cache_clear
        ldx #7
@reset: lda #$FF
        sta BONUS_CLOUD_OLD_COL,X
        sta BONUS_CLOUD_DRAWN_X,X
        sta BONUS_CLOUD_CACHE_ROW,X
        lda #0
        sta BONUS_CLOUD_OLD_WIDTH,X
        sta BONUS_CLOUD_READY,X
        dex
        bpl @reset
        jsr bonus_cache_platforms
        jsr bonus_ledge_tables  ; world_ptr = this variant's ledge records
        jsr bonus_cache_clouds
        jsr bonus_cloud_height_index
        jmp cache_same2

bonus_row_pointer:
        sta work_lo
        stx work_hi
        lsr work_hi
        ror work_lo
        lsr work_hi
        ror work_lo
        lsr work_hi
        ror work_lo
        lda work_lo
        clc
        adc #CACHE_FLOOR_ROW
        sta work_lo
        sta bonus_update_row
        tax
        lda #ROW_CONSTANT|9     ; every visible stone cell has the same colour
        sta ROW_KIND,X
        lda #0                  ; and copy it (it may change)
        sta SAME2,X
        sta SAME2+2,X
        lda work_lo
        and #7
        asl
        asl
        asl
        asl
        asl
        sta dst
        sta colptr
        lda work_lo
        lsr
        lsr
        lsr
        clc
        adc #>WORLD_CACHE
        sta dst+1
        clc
        adc #$10
        sta colptr+1
        rts

bonus_cache_platforms:
        lda bonus_platform_ptr
        sta world_ptr
        lda bonus_platform_ptr+1
        sta world_ptr+1
        lda #0
        sta bonus_copy_index
@platform:
        lda bonus_copy_index
        asl
        asl
        tay
        iny
        lda (world_ptr),Y
        sec
        sbc #4
        sta colw
        iny
        lda (world_ptr),Y
        sec
        sbc #4
        sta gapw
        iny
        lda (world_ptr),Y
        sta work2
        iny
        lda (world_ptr),Y
        tax
        lda work2
        jsr bonus_row_pointer
        ldy colw
@tile:  lda #STONE              ; original F3F6 repeats background CHR $EB
        sta (dst),Y
        lda #9                  ; source rock palette with white highlights
        sta (colptr),Y
        iny
        cpy gapw
        bcc @tile
        inc bonus_copy_index
        lda bonus_copy_index
        cmp bonus_platform_count
        bcc @platform
        rts

bonus_cache_clouds:
        ldx #0
@cloud: jsr bonus_cloud_paint
        ; Sky and cloud cells stay hires white for the entire bonus stage.
        ; Initialise once; moving the cloud changes characters only.
        ldy #31
        lda #1
@white: sta (colptr),Y
        dey
        bpl @white
        inx
        cpx bonus_cloud_count
        bcc @cloud
        rts

; X = cloud: glyph phase from its pixel position (slot X+1).
bonus_cloud_phase:
        stx bonus_work_index
        lda bonus_cloud_x,X
        and #7
        sta cloud_subpixel+1,X
        sta GLYPH_PHASE+1,X
        asl
        asl
        clc
        adc cloud_subpixel+1,X
        adc #BONUS_CLOUD_FIRST
        sta cloud_glyph
        rts

; X = cloud. Its row is private: erase only its previous footprint when
; character column or width changes, then write the current shared roles.
; Subpixel moves also change character IDs. X is preserved.
.segment "CODE"
bonus_cloud_paint:
        jsr bonus_cloud_phase
bonus_cloud_paint_ready:
        lda #0
        sta cache_wrap_max       ; adjacent-footprint union is inactive
        lda BONUS_CLOUD_READY,X
        beq @row_pointer
        lda bonus_cloud_hlo,X
        cmp BONUS_CLOUD_HEIGHT_LO,X
        bne @row_pointer
        lda bonus_cloud_hhi,X
        cmp BONUS_CLOUD_HEIGHT_HI,X
        bne @row_pointer
        lda BONUS_CLOUD_DST_LO,X
        sta dst
        lda BONUS_CLOUD_DST_HI,X
        sta dst+1
        lda BONUS_CLOUD_CACHE_ROW,X
        sta bonus_update_row
        jmp @pointed
@row_pointer:
        lda bonus_cloud_hlo,X
        sta work2
        lda bonus_cloud_hhi,X
        tax
        lda work2
        jsr bonus_row_pointer
        lda #ROW_CONSTANT|1
        sta ROW_KIND,X
        txa
        ldx bonus_work_index
        sta BONUS_CLOUD_CACHE_ROW,X
        lda bonus_cloud_hlo,X
        sta BONUS_CLOUD_HEIGHT_LO,X
        lda bonus_cloud_hhi,X
        sta BONUS_CLOUD_HEIGHT_HI,X
        lda dst
        sta BONUS_CLOUD_DST_LO,X
        lda dst+1
        sta BONUS_CLOUD_DST_HI,X
@pointed:
        lda bonus_cloud_width,X
        lsr
        lsr
        lsr
        sta cache_cloud_width
        lda bonus_cloud_x,X
        lsr
        lsr
        lsr
        sta old_cloud_col
        lda BONUS_CLOUD_READY,X
        beq @paint
        lda BONUS_CLOUD_OLD_WIDTH,X
        cmp bonus_cloud_width,X
        bne @clear
        lda BONUS_CLOUD_OLD_COL,X
        cmp old_cloud_col
        beq @paint
        ldy bonus_update_row
        lda PATCH_FLAG,Y
        bne @clear              ; existing patches retain conservative merging
        lda old_cloud_col
        sec
        sbc BONUS_CLOUD_OLD_COL,X
        and #31
        cmp #1
        beq @right_union
        cmp #31
        bne @clear
        lda old_cloud_col        ; moving left: new column starts the union
        sta cache_wrap_min
        adc cache_cloud_width    ; CMP #31 left C=1: trailing old cell
        and #31
        tay
        bpl @erase_adjacent
@right_union:
        lda BONUS_CLOUD_OLD_COL,X
        sta cache_wrap_min
        tay                     ; moving right: leading old cell
@erase_adjacent:
        lda #1
        sta cache_wrap_max
        lda #BLANK
        sta (dst),Y             ; new glyphs overwrite the shared cells
        jmp @paint
@clear:ldy BONUS_CLOUD_OLD_COL,X
        lda BONUS_CLOUD_OLD_WIDTH,X
        lsr
        lsr
        lsr
        pha                     ; old span's last-column offset
        tax
        lda #BLANK
@blank:jsr bonus_cloud_put
        dex
        bpl @blank
        pla
        ldx bonus_work_index
        ldy BONUS_CLOUD_OLD_COL,X
        jsr bonus_cloud_span
@paint:lda old_cloud_col
        clc
        adc cache_cloud_width
        cmp #32
        bcs @wrapped
        ldy old_cloud_col
        lda cloud_glyph
        sta (dst),Y
        iny
        adc #1
        sta (dst),Y
        iny
        adc #1
        ldx cache_cloud_width
        dex
        dex
        dex
@repeat_direct:
        sta (dst),Y
        iny
        dex
        bne @repeat_direct
        adc #1
        sta (dst),Y
        iny
        adc #1
        sta (dst),Y
        jmp @painted
@wrapped:
        ldy old_cloud_col
        ; Its colour stays white; the shared font holds all eight phases.
        lda cloud_glyph
        jsr bonus_cloud_put
        clc
        adc #1
        jsr bonus_cloud_put
        clc
        adc #1
        ldx cache_cloud_width
        dex
        dex
        dex                     ; repeated middle: width/8 minus three
@repeat:
        jsr bonus_cloud_put
        dex
        bne @repeat
        clc
        adc #1
        jsr bonus_cloud_put
        clc
        adc #1
        jsr bonus_cloud_put
@painted:
        ldx bonus_work_index
        lda bonus_cloud_x,X
        sta BONUS_CLOUD_DRAWN_X,X
        lda old_cloud_col
        sta BONUS_CLOUD_OLD_COL,X
        lda bonus_cloud_width,X
        sta BONUS_CLOUD_OLD_WIDTH,X
        lda #1
        sta BONUS_CLOUD_READY,X
        lda cache_cloud_width
        ldy old_cloud_col
        ldx cache_wrap_max
        beq @mark_span
        ldy cache_wrap_min
        clc
        adc #1                  ; old/new adjacent footprints cover one extra cell
@mark_span:
        jsr bonus_cloud_span
        ldx bonus_work_index
        rts

; Y=first column,A=width/8 (the spill is one extra cell). Merge endpoints
; with an existing patch. One isolated wrapping interval stays split;
; combining wrapped intervals conservatively promotes to a full row.
.segment "EXTRA"
bonus_cloud_span:
        sta tmp
        tya
        clc
        adc tmp
        sta tmp
        cmp #32                 ; retain carry as the wrapped-span bit
        ldx bonus_update_row
        lda PATCH_FLAG,X
        bne @merge
        tya
        sta PATCH_LO,X
        lda tmp
        and #31
        sta PATCH_HI,X
        lda #PATCH_CHARS
        bcc @flag
        ora #PATCH_WRAP
@flag:
        sta PATCH_FLAG,X
        sta patch_any
        rts
@merge:bcs @full                 ; any earlier patch plus a wrapped span
        and #PATCH_WRAP
        bne @full
        lda #PATCH_CHARS
        jsr patch_mark
        ldy tmp
        lda #PATCH_CHARS
        jmp patch_mark
@full:
        jmp patch_full_chars

.segment "HIGH"
; Preserve A and X while advancing one character in the32-column world.
bonus_cloud_put:
        sta (dst),Y
        iny
        cpy #32
        bcc @done
        ldy #0
@done:  rts
.segment "EXTRA"

bonus_world_tick:
@clouds:
        ldx #0
@cloud: lda #0
        sta bonus_cloud_motion,X
        lda bonus_cloud_frac,X
        clc
        adc bonus_cloud_speed,X
        sta bonus_cloud_frac,X
        bcc @next
        lda bonus_cloud_dir,X
        bmi @cloud_left
        inc bonus_cloud_x,X
        lda #1
        bne @motion
@cloud_left:
        dec bonus_cloud_x,X
        lda #$FF
@motion:
        sta bonus_cloud_motion,X
        ; Character phases are presented once per PAL frame by commit_clouds.
        ; Original X/fraction/carry physics still advances on every logic tick.
@next:  inx
        cpx bonus_cloud_count
        bcc @cloud
        rts

bonus_player_tick:
        ldx player_index
        lda #0
        sta PLAYER_LAND_AGE,X
        lda bonus_out,X
        beq @active
        rts
@active:
        lda #0                  ; original $CDB0 accepts B only in normal stage
        sta attack_t
@motion:
        jsr move_horizontal     ; ledges use pxlo; no character columns
        pha
        lda onground
        beq @air_input
        pla
        cmp #3                  ; source CFC6 finished; A is ignored this tick
        beq @support
        cmp #2
        beq @stopping_jump
        lda firehit
        and #1
        bne @begin_jump          ; source CDB0 reads A before D59C support
        beq @support
@stopping_jump:
        lda firehit
        and #1
        beq @support
        lda #0
        sta skid_t
        sta move_dir
        sta walk_time
        sta hammer_t
        jmp @begin_jump
@support:
        ldx player_index
        lda BONUS_WALL_SKIP,X    ; source D5CE skips one full contact pass
        jne @collect
        lda #0
        sta bonus_support_mode
        jsr bonus_find_support
        lda bonus_support
        jne @collect
        lda #0
        sta onground
        lda #12
        sta air_init
        lda #3                  ; source D608: bonus walk-off is not CD3B
        sta fall_int
        sta rise_int
        lda #$A8
        sta rise_frac
        jmp @collect
@begin_jump:
        dec py                  ; original $CE4F: bonus starts one pixel up
        jsr begin_jump
        lda #SFX3_JUMP          ; $CE58
        sta snd_sfx3_req
        jmp @collect            ; $CDB0 changes handler; gravity starts next tick
@air_input:
        pla
@air:   lda py
        sta prevpy
        jsr vertical_step
        ldx player_index
        lda BONUS_WALL_SKIP,X
        bne @fall
        lda fall_int            ; $D625 accepts the late-rising/apex window
        cmp #3
        bcc @head
        lda #1
        sta bonus_support_mode
        jsr bonus_find_support
        lda bonus_support
        beq @head
        ldx player_index
        lda py                  ; D552 draws this integrated pose7 before D59C
        sta PLAYER_LAND_Y,X
        lda #12
        sta PLAYER_LAND_AGE,X
        lda bonus_check_y
        sta py
        lda #2                  ; original D62B enters stop handler3
        sta onground
        lda #0
        sta vy
        sta air_init
@head:  lda onground
        bne @fall
        lda fall_int
        cmp #4
        bcs @fall
        cmp #3
        lda #2                  ; source $D6E0: solid ledge/cloud underside
        sta bonus_support_mode
        bcc @full_head
        jsr bonus_find_support_reuse ; the missed foot probe retained this base
        jmp @fall
@full_head:
        jsr bonus_find_support
@fall:
@collect:
        jsr bonus_side_bounds
        jmp bonus_catch         ; $D507 after this climber's $D552/$D59C

.segment "DATA"
; Exact D648..D6DF side-wall interval, using the original normalized body
; coordinate W=447-height=231+py-camera and the source byte/page arithmetic.
bonus_side_bounds:
        ldx player_index
        lda #0
        sta BONUS_WALL_SKIP,X
        lda py
        clc
        adc #231
        sta work_lo
        lda #0
        adc #0
        sta work_hi
        lda work_lo
        sec
        sbc bonus_camera
        sta work_lo
        lda work_hi
        sbc bonus_camera+1
        sta work_hi
        lda pxlo
        sec
        sbc #52
        sta tmplo
        lda bonus_camera        ; source scroll byte is zero at camera 0
        beq :+                  ; (bottom page) and 240 (the top)
        cmp #240
        bne @taper
:
        lda work_hi
        bne @taper
        lda tmplo
        cmp #43
        jcc @outside
        cmp #198
        jcs @outside
        lda work_lo
        cmp #88
        bcc @done               ; open summit: source D665/D667
@taper: lda work_lo
        sec
        sbc #87
        bcc @borrow
        ldy work_hi
        beq @divide
        clc
        adc #32
        bne @divide
@borrow:
        ldy work_hi
        beq @bounds
        ldy #0                  ; D680 leaves source $09=0 on this path
        sty work_hi
@divide:
        ldy #0
@step: cmp #56
        bcc @page
        sbc #56
        iny
        bne @step
@page: lda work_hi
        beq @bounds
        iny
        iny
        iny
        iny
@bounds:
        tya
        asl
        asl
        asl
        sta tmp
        lda #168
        clc
        adc tmp
        sta gapw
        lda #72
        sec
        sbc tmp
        sta colw
        lda tmplo
        cmp gapw
        bcc @left
        lda #1
        sta face
        lda gapw
        bne @store
@left: cmp colw
        bcs @done
        lda #0
        sta face
        lda colw
@store:clc
        adc #52
        sta pxlo
        lda #0
        adc #0
        sta pxhi
@done: rts
@outside:
        ldx player_index
        inc BONUS_WALL_SKIP,X
        lda onground            ; source handler2 is already airborne
        beq @done
        lda #0
        sta onground
        lda #12
        sta air_init
        lda #3
        sta fall_int
        sta rise_int
        lda #$A8
        sta rise_frac
        rts
.segment "EXTRA"

; Query world height once, retaining the source record order. Foot probes
; accept height H..H+4; heads accept H+26..H+29 (clouds H+28..H+31).
; Only a candidate in that small interval needs its screen Y and edges.
.segment "DATA"
bonus_find_support:
        lda bonus_camera
        clc
        adc #216
        sta bonus_base
        lda bonus_camera+1
        adc #0
        sta bonus_base+1
        lda bonus_base
        sec
        sbc py
        sta bonus_base          ; world height at the player's body Y
        lda bonus_base+1
        sbc #0
        sta bonus_base+1
bonus_find_support_reuse:
        lda #0
        sta bonus_support
        sta support_offset
        lda bonus_support_mode
        beq @standing
        cmp #2
        beq @head_query
        lda #5
        bne @query_width
@standing:
        lda #1
        bne @query_width
@head_query:
        lda #26
        sta support_offset
        clc
        adc bonus_base
        sta bonus_base
        bcc :+
        inc bonus_base+1
:       lda #4
@query_width:
        sta land_target
        lda #0
        sta supflag             ; 0: generic scan,1: immutable height buckets
        lda bonus_index_count
        cmp bonus_platform_count
        bne @linear
        lda #0
        sec
        sbc bonus_base
        and #7                  ; distance to the next eight-pixel ledge height
        cmp land_target
        jcs @clouds             ; no aligned ledge can lie in this window
        clc
        adc bonus_base          ; low byte only:all height pages share a bucket
        lsr
        lsr
        lsr
        tax
        lda BONUS_HEIGHT_HEAD,X
        tax
        lda #1
        sta supflag
        bne @platform
@linear:
        ldx #0
@platform:
        cpx bonus_platform_count
        bcs @clouds
        lda BONUS_LEDGE_HLO,X
        sec
        sbc bonus_base
        cmp land_target
        bcs @next              ; nearly every record misses the small window
        sta bonus_check_y
        lda BONUS_LEDGE_HLO,X
        cmp bonus_base          ; recover the low subtraction's borrow
        lda BONUS_LEDGE_HHI,X
        sbc bonus_base+1
        beq @fixed_candidate
        cmp #$FF                ; original 8-bit Y differences can wrap
        bne @next
@fixed_candidate:
        jsr @candidate_y
        bcc @next
        stx bonus_copy_index
        lda BONUS_LEDGE_L,X
        pha
        lda BONUS_LEDGE_R,X
        tax
        pla
        jsr bonus_overlap
        ldx bonus_copy_index
        bcc @next
        lda bonus_support_mode
        cmp #2
        beq @fixed_hit
        stx bonus_plat
@fixed_hit:
        jmp @yes
@next:  lda supflag
        beq @linear_next
        lda BONUS_HEIGHT_NEXT,X
        tax
        jmp @platform
@linear_next:
        inx
        jmp @platform
@clouds:
        lda bonus_support_mode
        cmp #2
        bne :+
        lda #28                 ; original cloud underside is two pixels lower
        sta support_offset
        lda bonus_base
        clc
        adc #2
        sta bonus_base
        bcc :+
        inc bonus_base+1
:       lda BONUS_CLOUD_INDEX_COUNT
        bmi @cloud_linear       ; disabled/rejected counts retain the full API
        cmp bonus_cloud_count
        bne @cloud_linear
        lda #0
        sec
        sbc bonus_base
        and #7
        cmp land_target
        bcs @none
        clc
        adc bonus_base
        lsr
        lsr
        lsr
        tax
        lda BONUS_CLOUD_HEIGHT_INDEX,X
        tax
        jmp @cloud
@none:  rts
@cloud_linear:
        ldx #0
@cloud: cpx bonus_cloud_count
        bcs @none
        lda bonus_cloud_hlo,X
        sec
        sbc bonus_base
        cmp land_target
        bcs @next_cloud
        sta bonus_check_y
        lda bonus_cloud_hlo,X
        cmp bonus_base
        lda bonus_cloud_hhi,X
        sbc bonus_base+1
        beq @cloud_candidate
        cmp #$FF
        bne @next_cloud
@cloud_candidate:
        jsr @candidate_y
        bcc @next_cloud
        ldy #8
        lda bonus_support_mode
        cmp #2
        bne @cloud_edges
        ldy #10
@cloud_edges:
        sty colw                ; foot left-8; head left-10
        lda #16
        sec
        sbc colw
        sta gapw                ; foot right-8; head right-6
        lda pxlo
        sec
        sbc #52
        sta tmplo               ; original unsigned NES body X
        lda bonus_cloud_x,X
        sec
        sbc colw
        cmp tmplo
        bcs @next_cloud          ; original left-offset < bodyX
        lda bonus_cloud_x,X
        clc
        adc bonus_cloud_width,X
        sec
        sbc gapw
        cmp tmplo
        bcc @next_cloud          ; bodyX <= right-offset (no wrap interval)
        lda bonus_support_mode
        cmp #2
        beq @yes
        txa
        clc
        adc #24
        sta bonus_plat
        lda bonus_cloud_motion,X
        jsr add_player_x
        jmp @yes
@next_cloud:
        lda BONUS_CLOUD_INDEX_COUNT
        bmi @cloud_next_linear
        cmp bonus_cloud_count
        beq @none
@cloud_next_linear:
        inx
        jmp @cloud
@yes:   lda bonus_support_mode
        cmp #2
        bne @supported
        lda #4                  ; original $D71B/$D71F ceiling response
        sta fall_int
        lda #$20
        sta fall_frac
@supported:
        lda #1
        sta bonus_support
        rts

; A is the height difference's high byte (0 or$FF); bonus_check_y holds
; its low byte, already inside the query window. Keep the source's 8-bit
; difference wrap, but require the actual surface Y to remain in0..255.
@candidate_y:
        sta chartmp
        lda bonus_check_y
        clc
        adc support_offset
        sta work2
        lda py
        sec
        sbc work2
        sta bonus_check_y
        lda #0
        sbc #0                  ; true screen Y's borrow high byte
        sec
        sbc chartmp
        bne @miss
        sec
        rts
@miss:  clc
        rts

.segment "EXTRA"
; All original cloud heights are eight-pixel aligned and their low-byte
; buckets are unique. Arbitrary fixtures keep the exact linear fallback.
bonus_cloud_height_index:
        lda #$FF
        sta BONUS_CLOUD_INDEX_COUNT
        ldx #31
@clear:sta BONUS_CLOUD_HEIGHT_INDEX,X
        dex
        bpl @clear
        ldx bonus_cloud_count
        beq @ready
        cpx #9
        bcs @done
@cloud:dex
        lda bonus_cloud_hlo,X
        and #7
        bne @done
        lda bonus_cloud_hlo,X
        lsr
        lsr
        lsr
        tay
        lda BONUS_CLOUD_HEIGHT_INDEX,Y
        bpl @done              ; another page or duplicate needs record order
        txa
        sta BONUS_CLOUD_HEIGHT_INDEX,Y
        bne @cloud
@ready:lda bonus_cloud_count
        sta BONUS_CLOUD_INDEX_COUNT
@done: rts

; Copies the NES ledge records (left, right, height) into the lookup tables.
bonus_ledge_tables:
        ldx #0
        ldy #1
@ledge: cpx bonus_platform_count
        bcs @done
        lda (world_ptr),Y
        sta BONUS_LEDGE_L,X
        iny
        lda (world_ptr),Y
        sta BONUS_LEDGE_R,X
        iny
        lda (world_ptr),Y
        sta BONUS_LEDGE_HLO,X
        iny
        lda (world_ptr),Y
        sta BONUS_LEDGE_HHI,X
        iny
        inx
        bne @ledge
@done:  jmp bonus_height_index

; Bonus views use constant colour rows, leaving COLOUR_BACK free. Heads
; ignore the height high byte; the query still checks its exact16-bit Y.
; Build backwards so each linked list retains the original record order.
bonus_height_index:
        lda #$FF
        sta bonus_index_count
        ldx #31
@clear:sta BONUS_HEIGHT_HEAD,X
        dex
        bpl @clear
        ldx bonus_platform_count
        beq @ready
        cpx #33
        bcs @done
@ledge:dex
        lda BONUS_LEDGE_HLO,X
        and #7
        bne @done               ; arbitrary-height controlled fixtures stay generic
        lda BONUS_LEDGE_HLO,X
        lsr
        lsr
        lsr
        tay
        lda BONUS_HEIGHT_HEAD,Y
        sta BONUS_HEIGHT_NEXT,X
        txa
        sta BONUS_HEIGHT_HEAD,Y
        txa
        bne @ledge
@ready:lda bonus_platform_count
        sta bonus_index_count
@done: rts

; A/X = C64 character edges, right edge exclusive.
bonus_overlap:
        sta colw
        stx gapw
        lda pxlo
        sec
        sbc #52
        sta tmplo
        lda #8                  ; source left-8 < X <= right-8
        ldy bonus_support_mode
        cpy #2
        bne @offset
        lda #10                 ; underside left-10 < X <= right-6
@offset:sta work2
        lda colw
        asl
        asl
        asl
        sec
        sbc #32                 ; converted columns include4 C64 cells
        sec
        sbc work2
        cmp tmplo
        bcs @no
        lda #16
        sec
        sbc work2
        sta work2
        lda gapw
        asl
        asl
        asl
        sec
        sbc #32
        sec
        sbc work2
        cmp tmplo
        bcc @no
@yes:   sec
        rts
@no:    clc
        rts

.segment "HIGH"
; Bonus rows all use constant colours, leaving this COLOUR_BACK overlay
; available until the next scene. Fruit X windows never overlap.
bonus_fruit_index:
        lda #$FF
        ldx #0
@clear:sta BONUS_FRUIT_X,X
        inx
        bne @clear
        jmp bonus_fruit_index_fill

.segment "EXTRA"
; Original $DB1D box of objects 3..6 around the climber point X+8: fruit 0
; and 1 (x offset 8, half 8) for pxlo fruit_x-11..+3, fruit 2 and 3 (x
; offset 4) for fruit_x-15..-1 (C64 X: source X+52 climber, +56 object).
bonus_fruit_index_fill:
        ldx #14
@fill: lda #0
        sta BONUS_FRUIT_X+141,X
        lda #1
        sta BONUS_FRUIT_X+205,X
        lda #2
        sta BONUS_FRUIT_X+89,X
        lda #3
        sta BONUS_FRUIT_X+233,X
        dex
        bpl @fill
        rts

fruit_x:
        .byte 152,216,104,248
.segment "CODE"
; $F6F2 places them in the first (bottom) view: height 207-Y for source
; Y $10,$40,$98,$98, each on a ledge.
fruit_hlo:
        .byte <191,<143,<55,<55
.segment "EXTRA"
fruit_hhi:
        .byte >191,>143,>55,>55
; $DB1D Y: |fruit Y+offset - (climber Y+12)| < half: offsets 12/8, halves
; 11/8, as fruit y-py+bias < span.
fruit_ybias: .byte 10,10,3,3
fruit_yspan: .byte 21,21,15,15
fruit_bits = vic_bits             ; shared1,2,4,8 bit masks
        .export fruit_bits
.segment "EXTRA"
; --- after both climbers: original $CCBC..$D890 order -------------------
; $D212 (nes_bonus_bump) ran; then the condor ($F78B), fruit touches
; ($D301), the timer ($F6A4), falls out ($D724), the camera step ($D8AF)
; and a new camera pan ($D890).
bonus_after_players:
        jsr bonus_condor_move
        jsr bonus_fruits
        jsr bonus_timer
        jsr bonus_falls
        jsr bonus_pan_step
        jmp bonus_pan_start

; Original $F78B: one pixel a tick, wrapping round the 256-pixel source X
; (C64 X = source X+56); at source X $60 a random new direction.
bonus_condor_move:
        lda condor_dir
        bne @right
        lda condor_xlo
        bne :+
        dec condor_xhi
:       dec condor_xlo
        lda condor_xhi
        bne @check
        lda condor_xlo
        cmp #56
        bcs @check
        inc condor_xhi          ; source X 0 -> $FF
        bne @check
@right: inc condor_xlo
        bne :+
        inc condor_xhi
:       lda condor_xhi
        beq @check
        lda condor_xlo
        cmp #56
        bcc @check
        dec condor_xhi          ; source X $FF -> 0
@check: lda condor_xhi
        bne @done
        lda condor_xlo
        cmp #96+56
        bne @done
        jsr random_step
        and #1
        sta condor_dir
@done:  rts

; Original $D301 in the bonus: each climber in the stage (player 1 first)
; touches at most one fruit; $DB1D boxes per fruit (fruit_ybias/yspan).
bonus_fruits:
        ldx #$FF
@player:
        inx
        cpx player_count
        bcs @done
        lda fruit_mask
        beq @done
        lda bonus_out,X
        bne @player
        txa
        pha
        asl
        asl
        asl
        asl
        asl
        tay
        lda PLAYER_STATES+4,Y   ; pxhi: no fruit beyond X 255
        bne @next
        ldx PLAYER_STATES+3,Y
        lda BONUS_FRUIT_X,X
        bmi @next
        tax
        lda fruit_mask
        and fruit_bits,X
        beq @next
        lda bonus_camera        ; fruit screen y = camera+216-height
        clc
        adc #216
        sta work_lo
        lda bonus_camera+1
        adc #0
        sta work_hi
        lda work_lo
        sec
        sbc fruit_hlo,X
        sta work_lo
        lda work_hi
        sbc fruit_hhi,X
        bne @next
        lda work_lo
        sec
        sbc PLAYER_STATES+5,Y
        clc
        adc fruit_ybias,X
        cmp fruit_yspan,X
        bcs @next
        lda fruit_bits,X
        eor #$FF
        and fruit_mask
        sta fruit_mask
        pla
        pha
        tax
        inc fruit_counts,X
        lda #SFX2_FRUIT         ; $D3A7
        sta snd_sfx2_req
@next:  pla
        tax
        jmp @player
@done:  rts

; Original $F6A4: 40.00 seconds, the first step at once, then 39 more.
bonus_timer:
        dec bonus_ticks
        bne @done
        lda #60
        sta bonus_ticks
        dec bonus_left
        bne @done
        lda #2
        sta bonus_reason
        lda #110/2              ; $F6DB: music off, $4D = $0A slow ticks
        sta bonus_end_wait
        lda #MUSIC_OFF
        sta snd_music_req
@done:  rts

; Original $D724: a climber whose body Y reaches $D4 (C64 py 221) is out.
bonus_falls:
        ldx player_count
@player:
        dex
        bmi @done
        lda bonus_out,X
        bne @player
        txa
        asl
        asl
        asl
        asl
        asl
        tay
        lda PLAYER_STATES+5,Y
        cmp #212+9
        bcc @player
        lda #1
        sta bonus_out,X
        bne @player
@done:  rts

; Original $D8AF: a pan moves the camera four lines a tick, twelve times or
; up to the top (camera 240: source scroll 0, page 0). $EC51 moves both
; climbers' screen Y with it, and a fruit that reaches source Y $F8 below
; the screen is gone.
bonus_pan_step:
        lda bonus_pan
        bne :+
        rts
:       lda bonus_camera
        clc
        adc #4
        sta bonus_camera
        ldx player_count
@player:
        dex
        bmi @fruits
        lda bonus_out,X
        bne @player
        txa
        asl
        asl
        asl
        asl
        asl
        tay
        lda PLAYER_STATES+5,Y
        clc
        adc #4
        sta PLAYER_STATES+5,Y
        lda PLAYER_STATES+6,Y
        clc
        adc #4
        sta PLAYER_STATES+6,Y
        jmp @player
@fruits:
        lda player_count        ; one climber: its zero page is the context
        cmp #1
        bne :+
        lda PLAYER_STATES+5
        sta py
        lda PLAYER_STATES+6
        sta prevpy
:       ldx #3
@fruit: lda fruit_mask
        and fruit_bits,X
        beq @next_fruit
        lda bonus_camera        ; source Y = camera+207-height >= $F8
        clc
        adc #207
        sta work_lo
        lda #0
        adc #0
        sta work_hi
        lda work_lo
        sec
        sbc fruit_hlo,X
        sta work_lo
        lda work_hi
        sbc fruit_hhi,X
        bmi @next_fruit
        bne @gone
        lda work_lo
        cmp #$F8
        bcc @next_fruit
@gone:  lda fruit_bits,X
        eor #$FF
        and fruit_mask
        sta fruit_mask
@next_fruit:
        dex
        bpl @fruit
        lda bonus_camera
        cmp #240
        beq @stop
        dec bonus_pan
        bne @done
@stop:  lda #0
        sta bonus_pan
@done:  rts

; Original $D890: no pan running, not at the top, and a climber standing
; (handler 1: onground 1 or 3) above source Y $60: twelve steps ($D81F).
bonus_pan_start:
        lda bonus_pan
        bne @done
        lda bonus_camera
        cmp #240
        bcs @done
        ldx player_count
@player:
        dex
        bmi @done
        lda bonus_out,X
        bne @player
        txa
        asl
        asl
        asl
        asl
        asl
        tay
        lda PLAYER_STATES+8,Y   ; onground: 0 air, 2 stopping (handler 3)
        beq @player
        cmp #2
        beq @player
        lda PLAYER_STATES+5,Y
        sec
        sbc #9
        cmp #$60
        bcs @player
        lda #12
        sta bonus_pan
@done:  rts

; Original $D507 for the climber in zero page: the source scroll byte is
; zero, its body Y is above $26 and the condor's legs pass its X: window
; (condor X + 10 flying left, +5 right .. + width] with width 1, 2, 4, 4
; for (fruit of both climbers)/2. The climber then hangs at the window start.
bonus_catch:
        lda bonus_camera
        beq :+
        cmp #240
        bne @done
:       lda py
        sec
        sbc #9
        cmp #$26
        bcs @done
        lda condor_xlo          ; source condor X = C64 X-56 (low byte)
        sec
        sbc #56
        ldy condor_dir
        clc
        adc catch_offset,Y
        sta work_lo
        lda pxlo                ; source climber X = C64 X-52
        sec
        sbc #52
        sta work_hi
        lda work_lo
        cmp work_hi
        bcs @done
        lda fruit_counts
        clc
        adc fruit_counts+1
        lsr
        and #3
        tay
        lda work_lo
        clc
        adc catch_width,Y
        cmp work_hi
        bcc @done
        lda work_lo
        clc
        adc #52
        sta pxlo
        lda #0
        adc #0
        sta pxhi
        lda player_index
        clc
        adc #1
        sta bonus_winner
        sta bonus_reason
        lda #352/2              ; $D540: mountain-complete music, $4D = $20
        sta bonus_end_wait      ; slow ticks (352 frames) with all held still
        lda #MUSIC_COMPLETE
        sta snd_music_req
@done:  rts
catch_offset: .byte 10,5
catch_width:  .byte 1,2,4,4

; NES fruit values (hundreds) and condor prizes (thousands), clamped at 10.
fruit_points_hi:
        .byte $03,$05,$06,$07,$08,$10,$20,$30,$40,$50
condor_prize_hi:
        .byte $30,$50,$60,$70,$80,$00,$00,$00,$00,$00
condor_prize_top:
        .byte 0,0,0,0,0,1,2,3,4,5

bonus_platform_src:
        .incbin "../build/nes_bonus_platforms.bin"
bonus_cloud_src:
        .incbin "../build/nes_bonus_clouds.bin"
.segment "CODE"
