; World tile/colour caches grow upwards, 32 NES columns by 64 rows.
; Cache row 0 lies below the ground; floor F has its upper ice in row 6F+2.
; At rest (view_fine 7) screen rows 0..23 exactly fill the visible window.
CACHE_FLOOR_ROW = 2
VIEW_BIAS = 7           ; view_row/view_fine = (visual_camera + 7) / 8, mod 8
PAN_SPEED = 4           ; shown normal pan: pixels per PAL frame
PAN_CHASE_LIMIT = 97    ; a larger camera change is shown at once
CHASE_MAX = 2           ; bonus camera: fastest eased speed (pixels/frame);
                        ; one row per 4 frames leaves a frame per copy step
.include "normal_clouds.asm"
.segment "EXTRA"
cache_floor_lo:
        .repeat 9,I
        .byte <(WORLD_CACHE+(I*6+CACHE_FLOOR_ROW)*32)
        .endrep
.segment "CODE"
cache_floor_hi:
        .repeat 9,I
        .byte >(WORLD_CACHE+(I*6+CACHE_FLOOR_ROW)*32)
        .endrep
screen_row_lo:
        .repeat 25,I
        .byte <(SCREEN+I*40)
        .endrep
screen_row_hi:
        .repeat 25,I
        .byte >(SCREEN+I*40)
        .endrep

view_init:
        lda #0
        sta visual_camera
        sta visual_camera+1
        sta target_camera
        sta target_camera+1
        sta screen_buffer
        sta pending_buffer
        sta packet_ready
        sta copy_stage
        sta colour_ready
        sta tick_debt
        sta chase_speed
        lda #$FF
        sta last_view_row
        sta back_view           ; neither buffer holds a known view yet
        ldx #7
@glyphs:
        sta GLYPH_SHOWN,X       ; cloud glyphs are copied at the first commit
        dex
        bpl @glyphs
        lda #1
        sta view_dirty
        jsr split_latch
        ldx #7
@copy:  lda cache_copy_template,X
        sta CACHE_COPY,X
        dex
        bpl @copy
        ; copy_setup emits every executed operand/opcode; only these STA
        ; opcodes remain static. Unsigned carry handles indices144..0.
        ldx #24*6
@stores:
        lda #$9D
        sta COPY_BODY+3,X
        sta COPY_COLOURS+3,X
        txa
        sec
        sbc #6
        tax
        bcs @stores
        jsr playfield_font
        lda state
        cmp #3
        bne @normal_font
        jsr bonus_cloud_glyph_cache_init
        jmp @clear_view
@normal_font:
        jsr normal_cloud_font_init
@clear_view:
        ; Border columns and both pointer blocks are kept outside the cache.
        ldx #0
        lda #BLANK
@clear: sta SCREEN,X
        sta SCREEN+$100,X
        sta SCREEN+$200,X
        sta SCREEN+$300,X
        sta BACK_SCREEN,X
        sta BACK_SCREEN+$100,X
        sta BACK_SCREEN+$200,X
        sta BACK_SCREEN+$300,X
        inx
        bne @clear
        rts

cache_clear:
        ldx #0
@byte:  lda #BLANK
        .repeat 8,I
        sta WORLD_CACHE+I*256,X
        .endrep
        lda #0
        .repeat 8,I
        sta COLOUR_CACHE+I*256,X
        .endrep
        inx
        bne @byte
        lda #64
        sta cache_rows
        lda #ROW_EMPTY
        ldx #63
@kinds: sta ROW_KIND,X
        dex
        bpl @kinds
        lda #1
        sta view_dirty
        rts

; SAME2[r]: cache row r has the characters of row r-2 and neither needs
; all colours (only walls, or empty). Such rows never change after the
; cache is built. Full-colour rows and constant-colour clouds are excluded.
cache_same2:
        ldx #63
@row:   lda #0
        sta SAME2,X
        cpx #2
        bcc @next
        lda ROW_KIND,X
        cmp #ROW_FULL
        beq @next
        and #ROW_CONSTANT
        bne @next
        lda ROW_KIND-2,X
        cmp #ROW_FULL
        beq @next
        and #ROW_CONSTANT
        bne @next
        txa
        and #7
        asl
        asl
        asl
        asl
        asl
        sta src
        sec
        sbc #64
        sta dst
        txa
        lsr
        lsr
        lsr
        clc
        adc #>WORLD_CACHE
        sta src+1
        sta dst+1
        lda src
        cmp #64
        bcs :+
        dec dst+1               ; row r-2 starts on the previous page
:       ldy #31
@cell:  lda (dst),Y
        sta tmp
        lda (src),Y
        cmp tmp
        bne @next
        dey
        bpl @cell
        lda #1
        sta SAME2,X
@next:  dex
        bpl @row
        rts

cache_normal:
        jsr cache_clear
        ; Colour commit: ice rows 6F+1/6F+2 need all 32 colours, the rows
        ; between floors only their rock walls (blank cells show no colour).
        ldx #63
        ldy #63 .mod 6
@kind:  lda #ROW_FULL
        cpx #51
        bcc :+
        lda #ROW_EMPTY
        beq @set_kind
:
        cpy #1
        beq @set_kind
        cpy #2
        beq @set_kind
        lda #ROW_WALLS|9        ; white snow, multicolour
        cpx #32
        bcs @set_kind
        lda #ROW_WALLS|15       ; yellow highlights, multicolour
@set_kind:
        sta ROW_KIND,X
        dey
        bpl @kind_next
        ldy #5
@kind_next:
        dex
        bpl @kind
        lda #0
        sta cache_world
@floor: lda cache_world
        jsr cache_normal_floor
        inc cache_world
        lda cache_world
        cmp #9
        bne @floor
        jsr cache_mountain_walls
        jsr cache_stone_columns
        jsr cache_constant_rows
        lda #ROW_FULL           ; water has its own hires cyan
        sta ROW_KIND
        jmp cache_same2

.segment "DATA"
; E05E draws each raw4 post as five vertical EB tiles, including the
; three rows below the two floor planes. Collision already uses that height.
cache_stone_columns:
        ldy levelidx
        lda T_DEFA,Y
        sta tmplo
        lda T_DEFA+1,Y
        sta loopidx
@post:  lda loopidx
        cmp tmplo
        beq @done
        tax
        lda T_DF1B,X
        and #31
        clc
        adc #4
        sta coltmp
        lda T_DF1B,X
        lsr
        lsr
        lsr
        lsr
        lsr
        sta cache_world
        jsr cache_pointer
        jsr floor_row
        stx rowidx
        lda #5
        sta chartmp
        ldy coltmp
@row:   lda #STONE
        sta (dst),Y
        lda #15
        ldx rowidx
        cpx #32
        bcc :+
        lda #9
:       sta (colptr),Y
        lda #ROW_FULL
        sta ROW_KIND,X
        lda dst
        sec
        sbc #32
        sta dst
        sta colptr
        bcs :+
        dec dst+1
        dec colptr+1
:       dec rowidx
        dec chartmp
        bne @row
        dec loopidx
        bne @post
@done:  rts
.segment "CODE"

cache_pointer:
        ldx cache_world
        lda cache_floor_lo,X
        sta dst
        sta colptr
        lda cache_floor_hi,X
        sta dst+1
        clc
        adc #$10
        sta colptr+1
        rts

cache_normal_floor:
        sta cache_world
        sta wrld
        jsr cache_pointer
        ldx cache_world
        lda floor_offsets,X
        sec
        sbc #4
        sta src
        lda #4
        sbc #0
        sta src+1
        lda #0
        sta cache_layer
        lda floor_types,X
        and #$E0
        cmp #$60
        lda #0
        bcc @plain
        lda #1                  ; cloud floor: its sky cells are white, so a
@plain: sta blank_colour        ; moving cloud never changes colour RAM
@layer: jsr terrain_floor_bounds
        ldy cache_wrap_min
@cell:  lda (src),Y
        jsr floor_cell_char
        sta (dst),Y
        jsr terrain_color
        sta (colptr),Y
        iny
        cpy cache_wrap_max
        bne @cell
        lda cache_layer
        bne @number
        inc cache_layer
        lda #0
        sta blank_colour
        inc src+1
        lda dst
        sec
        sbc #32
        sta dst
        sta colptr
        bcs @layer
        dec dst+1
        dec colptr+1
        jmp @layer
@number:
        ldx cache_world
        lda floor_types,X
        and #$E0
        cmp #$60
        bcc @dirty
        jsr cloud_make_glyphs
        jsr cache_floor_clouds
@dirty: jsr floor_row           ; patch upper ice row 6F+2 and the row below
        jsr patch_full_row
        dex
        jmp patch_full_row

; A = map value (0 air, 1/2 ice, 3 stone) on floor cache_world, layer
; cache_layer (0 upper, 1 lower): its character (belt ice on conveyor floors).
floor_cell_char:
        tax
        lda cache_layer
        beq @upper
        lda lower_tiles,X
        rts
@upper: lda upper_tiles,X
        cpx #1
        beq @flow
        bne @done               ; upper2 is the original conditional stone post
@flow:  pha
        ldx cache_world
        lda floor_types,X
        and #$E0
        beq @ordinary
        cmp #$80
        bcs @ordinary
        pla
        lda floor_types,X
        and #$10
        beq @right
        lda #CONVEYOR_L
        rts
@right: lda #CONVEYOR_R
        rts
@ordinary:
        pla
@done:  rts

; wrld/colw as for cell_index: one map cell changed (broken or repaired).
; Only its two cache cells are rebuilt and patched, whether or not the
; floor is on screen; clouds are drawn again over a new gap.
cache_cell:
        jsr cell_index
        jcs @done
        stx cell_map
        lda wrld
        sta cache_world
        jsr cache_pointer
        lda colw
        sec
        sbc #4
        sta cell_column
        ldx cache_world
        lda floor_types,X
        and #$E0
        cmp #$60
        lda #0
        bcc @plain
        lda #1
@plain: sta blank_colour
        lda #0
        sta cache_layer
        jsr terrain_floor_bounds
        ldy cell_column
        cpy cache_wrap_min
        bcc @lower
        cpy cache_wrap_max
        bcs @lower
        ldx cell_map
        lda floor_upper,X
        jsr floor_cell_char
        ldy cell_column
        sta (dst),Y
        jsr terrain_color
        sta (colptr),Y
@lower: lda #1
        sta cache_layer
        lda #0
        sta blank_colour
        ldx cell_map
        lda floor_lower,X
        jsr floor_cell_char
        pha
        lda dst                 ; lower ice row
        sec
        sbc #32
        sta dst
        sta colptr
        bcs @same
        dec dst+1
        dec colptr+1
@same:  pla
        pha
        jsr terrain_floor_bounds
        ldy cell_column
        pla
        cpy cache_wrap_min
        bcc @patched
        cpy cache_wrap_max
        bcs @patched
        sta (dst),Y
        jsr terrain_color
        sta (colptr),Y
@patched:
        jsr floor_row
        lda #PATCH_CHARS|PATCH_COLOURS
        jsr patch_mark
        dex
        jsr patch_mark
        ldx cache_world
        lda floor_types,X
        and #$E0
        cmp #$60
        bcc @done
        jsr cloud_make_glyphs
        jsr cache_floor_clouds  ; only a new gap can change
@done:  rts

; X = cache row, Y = column, A = PATCH_* bits: widen that row's patch.
patch_mark:
        sta patch_kind
        lda PATCH_FLAG,X
        bne @extend
        tya
        sta PATCH_LO,X
        sta PATCH_HI,X
        jsr patch_note
        jmp @flag
@extend:
        and #PATCH_WRAP
        beq @span
        jmp patch_mark_wrap     ; a wrapped character span (moving clouds)
@span:  tya
        cmp PATCH_LO,X
        bcs @not_lower
        sta PATCH_LO,X
@not_lower:
        cmp PATCH_HI,X
        bcc @flag
        sta PATCH_HI,X
@flag:  lda patch_kind
        ora PATCH_FLAG,X
        sta PATCH_FLAG,X
        sta patch_any
        rts

; X = cache row: all 32 characters. Bonus cloud colours are immutable.
patch_full_chars:
        lda #0
        sta PATCH_LO,X
        lda #31
        sta PATCH_HI,X
        lda #PATCH_CHARS
        bne patch_full_flags
; X = cache row: all 32 cells, characters and colours.
patch_full_row:
        lda #0
        sta PATCH_LO,X
        lda #31
        sta PATCH_HI,X
        lda #PATCH_CHARS|PATCH_COLOURS
patch_full_flags:
        pha
        lda PATCH_FLAG,X
        bne :+
        jsr patch_note
:       pla
        ora PATCH_FLAG,X
        and #(PATCH_CHARS|PATCH_COLOURS) ; full rows replace any wrapped span
        sta PATCH_FLAG,X
        sta patch_any
        rts

; X = cache row whose flag goes from 0 to set: remember it, so that
; commit_patches visits the dirty rows instead of all 64 flags. A is
; changed; X and Y are kept. A full list makes the commit scan every row.
.segment "DATA"
patch_note:
        txa
        ldx patch_count
        cpx #PATCH_LIST_SIZE
        bcs @full
        sta PATCH_LIST,X
        inc patch_count
        tax
        rts
@full:  ldx #$FF
        stx patch_count
        tax
        rts

; Normal play: patch the listed rows (rows whose flag is already clear,
; committed early with their cloud glyphs, are skipped).
commit_listed_rows:
        lda patch_count
        cmp #$FF
        beq @all
        tay
        beq @listed
@entry: dey
        ldx PATCH_LIST,Y
        lda PATCH_FLAG,X
        beq @skip
        sty patch_iter
        jsr patch_one_row
        ldy patch_iter
@skip:  tya
        bne @entry
@listed:
        sty patch_count
        rts
@all:   ldx #63
@row:   lda PATCH_FLAG,X
        beq @next_row
        jsr patch_one_row
@next_row:
        dex
        bpl @row
        lda #0
        sta patch_count
        rts

; X = cache row of the upper ice of floor cache_world.
floor_row:
        lda cache_world
        asl
        clc
        adc cache_world
        asl
        adc #CACHE_FLOOR_ROW
        tax
        rts
.segment "CODE"
; A = the beam line / 2 (0..155). X is changed. (A line 255/256 or 311/0
; boundary inside these four cycles reads 128 half lines off: rare, and it
; only misjudges one sixth tick.)
beam_half:
        lda $D011
        ldx RASTER
        asl
        txa
        ror
        rts
.segment "CODE"

 ; Two independent original cloud positions on this floor's upper row.
.segment "DATA"
cache_floor_clouds:
        jsr cache_pointer
        lda #0
        sta cache_wrap_min
        lda #3                  ; original24px cloud, plus spill cell
        sta cache_cloud_width
        lda #32
        sta cache_wrap_max
        jsr cloud_make_glyphs
        ldx cache_world
        lda cloud_x,X
        sec
        sbc #4
        sta colw
        jsr cache_cloud
        jsr cloud_make_glyphs2
        ldx cache_world
        lda cloud_x+8,X
        sec
        sbc #4
        sta colw
        jmp cache_cloud
.segment "CODE"

; A cloud of floor A crossed a character this tick. The four cells of both
; clouds before the tick (old_cloud_col, old_cloud_col2) are cleared, both
; silhouettes are painted again (shared cells join) and the row is patched.
cloud_step:
        sta cache_world
        jsr cache_pointer
        lda old_cloud_col
        jsr cloud_clear_cells
        lda old_cloud_col2
        jsr cloud_clear_cells
        jsr cache_floor_clouds  ; rebuild both overlapping source silhouettes
        ldx cache_world         ; the changed cells lie within the old and
        lda old_cloud_col       ; new four cells of both clouds
        sta work_lo
        sta work_hi
        lda old_cloud_col2
        jsr @range
        lda cloud_x,X
        jsr @range
        lda cloud_x+8,X
        jsr @range
        lda work_hi
        sec
        sbc work_lo
        cmp #28
        bcc @marked
        lda #$FF                ; the clouds straddle column 31: count the
        sta work_lo             ; columns left of it one row on (x+32)
        lda #0
        sta work_hi
        lda old_cloud_col
        jsr @wrap_range
        lda old_cloud_col2
        jsr @wrap_range
        lda cloud_x,X
        jsr @wrap_range
        lda cloud_x+8,X
        jsr @wrap_range
@marked:
        jsr floor_row
        jmp patch_cloud_span
@wrap_range:
        cmp #20
        bcs @range
        adc #32                 ; (carry clear)
@range: cmp work_lo
        bcs :+
        sta work_lo
:       cmp work_hi
        bcc :+
        sta work_hi
:       rts
.segment "DATA"
; A = floor with two separate clouds (E0: they never share a cell), X = 0
; (first cloud) or 8 (second): only that one crossed a character. Its four
; old cells are cleared, it is painted again, and only its old and new
; cells are patched.
cloud_step_one:
        sta cache_world
        stx cloud_which
        jsr cache_pointer
        lda #0
        sta cache_wrap_min
        lda #3                  ; original24px cloud, plus spill cell
        sta cache_cloud_width
        lda #32
        sta cache_wrap_max
        ldx cloud_which
        bne @second
        lda old_cloud_col
        sta work_lo
        jsr cloud_clear_cells
        jsr cloud_make_glyphs
        ldx cache_world
        lda cloud_x,X
        jmp @paint
@second:
        lda old_cloud_col2
        sta work_lo
        jsr cloud_clear_cells
        jsr cloud_make_glyphs2
        ldx cache_world
        lda cloud_x+8,X
@paint: sta work_hi
        sec
        sbc #4
        sta colw
        jsr cache_cloud
        lda work_lo             ; old and new columns: lo, hi
        cmp work_hi
        bcc :+
        ldx work_hi
        sta work_hi
        stx work_lo
:       lda work_hi
        sec
        sbc work_lo
        cmp #28
        bcc :+
        lda work_lo             ; across column 31 (35 to 4): hi, lo+32
        adc #32-1               ; (carry set)
        ldx work_hi
        sta work_hi
        stx work_lo
:       jsr floor_row
        jmp patch_cloud_span

; X = cache row (floor_row): the changed cloud cells are columns work_lo-4
; to work_hi-1 (cloud_x values; columns wrap at 32). Cells round column 31
; become one wrapped span (PATCH_WRAP: LO..31 and 0..HI) instead of the
; whole row, and a cloud interval joins a wrapped span as a whole interval.
; A row that already has colours to patch is patched whole.
patch_cloud_span:
        lda work_hi
        cmp #33
        bcs @wrapped
        lda PATCH_FLAG,X
        and #PATCH_WRAP
        bne @into_wrap
        ldy work_lo
        dey
        dey
        dey
        dey
        lda #PATCH_CHARS
        jsr patch_mark
        ldy work_hi
        dey
        lda #PATCH_CHARS
        jmp patch_mark
@into_wrap:                     ; (a wrapped row has characters only)
        lda PATCH_LO,X
        sta patch_wrap_lo
        lda PATCH_HI,X
        sta patch_wrap_hi
        lda work_lo
        sec
        sbc #4
        sta span_a
        ldy work_hi
        dey
        sty span_b
        jmp @union
@wrapped:
        sec
        sbc work_lo
        cmp #28                 ; the two intervals would meet
        bcs @full
        lda work_hi
        sbc #33-1               ; (carry clear) work_hi-33
        sta patch_wrap_hi
        lda work_lo
        sec
        sbc #4
        sta patch_wrap_lo
        lda PATCH_FLAG,X
        bne @merge
        jsr patch_note
        lda #0
@store: ora #PATCH_CHARS|PATCH_WRAP
        sta PATCH_FLAG,X
        sta patch_any
        lda patch_wrap_lo
        sta PATCH_LO,X
        lda patch_wrap_hi
        sta PATCH_HI,X
        rts
@full:  jmp patch_full_chars
@merge: and #PATCH_COLOURS
        beq :+
        jmp patch_full_row
:       lda PATCH_FLAG,X
        and #PATCH_WRAP
        bne @both
        lda PATCH_LO,X          ; the row's interval
        sta span_a
        lda PATCH_HI,X
        sta span_b
@union: lda span_b              ; span_a..span_b inside 0..hi or lo..31?
        cmp patch_wrap_hi
        bcc @keep
        beq @keep
        lda span_a
        cmp patch_wrap_lo
        bcs @keep
        lda span_b              ; else grow the side that adds fewer cells
        sec
        sbc patch_wrap_hi
        sta patch_grow          ; hi up to its end
        lda patch_wrap_lo
        sec
        sbc span_a              ; lo down to its start
        cmp patch_grow
        bcc @down
        lda span_b
        sta patch_wrap_hi
        jmp @check
@down:  lda span_a
        sta patch_wrap_lo
        jmp @check
@both:  lda PATCH_LO,X          ; two wrapped spans: the outer ends
        cmp patch_wrap_lo
        bcs :+
        sta patch_wrap_lo
:       lda PATCH_HI,X
        cmp patch_wrap_hi
        bcc @check
        sta patch_wrap_hi
@check: lda patch_wrap_hi
        clc
        adc #1
        cmp patch_wrap_lo
        bcs @full               ; the intervals meet: every column
@keep:  lda PATCH_FLAG,X
        jmp @store

; patch_mark on a row with a wrapped character span (LO..31 and 0..HI).
; Colours cannot join it, and a column outside it may be one end of a span
; across the gap: the row is patched whole then, as before wrapped spans.
patch_mark_wrap:
        lda patch_kind
        and #PATCH_COLOURS
        bne @whole
        tya
        cmp PATCH_LO,X
        bcs @inside
        cmp PATCH_HI,X
        bcc @inside
        beq @inside
        jmp patch_full_chars
@whole: jmp patch_full_row
@inside:
        lda patch_kind
        ora PATCH_FLAG,X
        sta PATCH_FLAG,X
        sta patch_any
        rts

; A = cloud_x: clear the cloud glyphs of its four cells (wrapping at 32).
cloud_clear_cells:
        sec
        sbc #4
        tay
        cpy #29
        bcs @wraps
        .repeat 4, K
        lda (dst),Y
        cmp #CLOUD_FIRST
        bcc .ident(.sprintf("@keep%d", K))
        cmp #CLOUD_SECOND+28
        bcs .ident(.sprintf("@keep%d", K))
        lda #BLANK
        sta (dst),Y
.ident(.sprintf("@keep%d", K)):
        iny
        .endrep
        rts
@wraps: ldx #4
@cell:  lda (dst),Y
        cmp #CLOUD_FIRST
        bcc @next
        cmp #CLOUD_SECOND+28
        bcs @next
        lda #BLANK
        sta (dst),Y
@next:  iny
        cpy #32
        bcc :+
        ldy #0
:       dex
        bne @cell
        rts
.segment "CODE"


; Normal cloud slot F uses four glyphs at CLOUD_FIRST+4*(F-1). The bonus
; painter selects its own phase from the shared immutable font.
cloud_make_glyphs:
        ldx cache_world
        lda cloud_subpixel,X
        sta GLYPH_PHASE,X
        txa
        asl
        asl
        clc
        adc #CLOUD_FIRST-4
        sta cloud_glyph
        rts

cache_cloud:
        ldy colw
        cpy #29                 ; four cells without wrapping (normal clouds)
        bcs @slow
        lda cache_cloud_width
        cmp #3
        bne @slow
        lda cache_wrap_max
        cmp #32
        beq @fast
@slow:  jmp @general
@fast:
        .repeat 4, K
        lda (dst),Y
        cmp #BLANK
        beq .ident(.sprintf("@paint%d", K))
        cmp #CLOUD_FIRST
        bcc .ident(.sprintf("@skip%d", K))
        cmp #CLOUD_SECOND+28
        bcs .ident(.sprintf("@skip%d", K))
        ldx #K
        jsr cloud_join          ; C set: a shared cell already shows both
        bcs .ident(.sprintf("@skip%d", K))
.ident(.sprintf("@paint%d", K)):
        lda cloud_glyph
        .if K > 0
        clc
        adc #K
        .endif
        sta (dst),Y
        lda #1
        sta (colptr),Y
.ident(.sprintf("@skip%d", K)):
        iny
        .endrep
        rts
@general:
        ldx #0
@tile:  lda (dst),Y
        cmp #BLANK
        beq @paint
        cmp #CLOUD_FIRST
        bcc @next
        cmp #CLOUD_SECOND+28
        bcs @next
        jsr cloud_join          ; C set: a shared cell already shows both
        bcs @next
@paint: txa
        clc
        adc cloud_glyph
        sta (dst),Y
        lda #1
        sta (colptr),Y
@next:  iny
        cpy cache_wrap_max
        bcc @nowrap
        ldy cache_wrap_min
@nowrap:
        inx
        cpx cache_cloud_width
        bcc @tile
        beq @tile               ; the spill cell is always there (blank at
@done:  rts                     ; subpixel 0): only column changes repaint

; Collision reads the world, independently of the displayed camera/buffer.
world_get_char:
        lda rowidx
        clc
        adc cam
        sta wrld
        cmp #9
        bcs @blank
        lda coltmp
        sta colw
        jsr support_wall_column  ; DBB4/DBB0 share the floor-specific margins
        bcs @wall
        jsr cell_index
        lda break_layer
        beq @upper
        lda floor_lower,X
        tax
        lda lower_tiles,X
        rts
@upper: lda floor_upper,X
        tax
        lda upper_tiles,X
        rts
@wall:  lda #STONE             ; outside the floor's cavity is solid rock
        rts
@blank: lda #BLANK
        rts

; target_camera: 48 pixels per floor, or the bonus stage's pixel camera.
camera_target:
        lda state
        cmp #3
        beq @bonus
        cmp #4
        beq @preview
        lda normal_camera
        sta target_camera
        lda normal_camera+1
        sta target_camera+1
        rts
@preview:
        lda preview_camera
        sta target_camera
        lda preview_camera+1
        sta target_camera+1
        rts
@bonus: lda bonus_camera
        sta target_camera
        lda bonus_camera+1
        sta target_camera+1
        rts

view_tick:
        lda #0
        sta chunk_frame
        lda state
        jeq @done
        cmp #2
        jeq @done
        jsr camera_target
@move:  lda visual_camera
        sta old_visual
        lda visual_camera+1
        sta old_visual+1
        lda view_fine
        sta old_fine
        lda view_row
        sta old_view_row
        ; Normal pans run one 4px logic step per PAL frame. The display
        ; follows that pace and can catch up by at most 4px after a hold.
        ; The flyover also runs one tick per frame (2px during its climb).
        lda state
        cmp #4
        jeq @snap
        cmp #3
        jeq @bonus_chase
        lda target_camera       ; normal: distance = target - visual
        sec
        sbc visual_camera
        sta work_lo
        lda target_camera+1
        sbc visual_camera+1
        bmi @normal_down
        jne @snap               ; 256+: a new stage or a reset
        lda work_lo
        jeq @row
        cmp #PAN_CHASE_LIMIT
        jcs @snap
        cmp #PAN_SPEED+1
        jcc @snap
        lda visual_camera
        clc
        adc #PAN_SPEED
        sta visual_camera
        jcc @row
        inc visual_camera+1
        jmp @row
@normal_down:
        cmp #$FF
        jne @snap
        lda work_lo
        cmp #256-PAN_CHASE_LIMIT+1
        jcc @snap
        cmp #256-PAN_SPEED
        jcs @snap
        lda visual_camera
        sec
        sbc #PAN_SPEED
        sta visual_camera
        jcs @row
        dec visual_camera+1
        jmp @row
@bonus_chase:
        jsr bonus_chase
        jmp @row
@snap:  lda target_camera
        sta visual_camera
        lda target_camera+1
        sta visual_camera+1
@row:   lda visual_camera
        clc
        adc #VIEW_BIAS
        sta work_lo
        lda visual_camera+1
        adc #0
        sta work_hi
        lda work_lo
        and #7
        sta view_fine
        lsr work_hi
        ror work_lo
        lsr work_hi
        ror work_lo
        lsr work_hi
        ror work_lo
        lda work_lo
        sta view_row
        lda state
        cmp #4
        bne :+
        jsr preview_cache_stream
:               lda screen_buffer
        sta pending_buffer
        lda last_view_row
        cmp #$FF
        bne @stream
        lda view_row
        sta copy_target_row
        sta last_view_row
        lda #0
        sta patch_any
        ldx #63
@fresh: sta PATCH_FLAG,X        ; the full copy already shows every row
        dex
        bpl @fresh
        sta view_dirty
        lda #$FF
        sta back_view
        lda screen_buffer
        eor #1
        sta pending_buffer
        jsr copy_setup
        lda #31
        ldx #$FF
        inc chunk_frame         ; this frame copies columns
        jsr CACHE_COPY_RUN
        lda #1
        sta colour_ready
        jmp @ready
@stream:
        ; The wanted back-buffer row is the one the camera waits for, or,
        ; within the shown row, the one needed two render steps from now.
        lda view_row
        cmp last_view_row
        jne @need
        lda state
        cmp #3
        bne @predict
        ; Bonus: the back buffer always holds the next row the camera moves
        ; to, built in three light steps (setup, two halves) on frames of
        ; their own, ahead of the eased 1..2-pixel camera.
        lda view_dirty
        bne @predict
        lda player_count
        cmp #2
        beq @bonus_budget       ; four small stages must progress every PAL frame
        lda late_commit         ; behind time: continue in a later frame
        jne @ready
        lda logic_phase         ; 0: this frame ran two ticks (main_loop)
        jeq @ready
@bonus_budget:
        lda target_camera+1
        cmp visual_camera+1
        bcc @bonus_down
        bne @bonus_up
        lda target_camera
        cmp visual_camera
        bcc @bonus_down
@bonus_up:
        ldx view_row
        cpx #((256+VIEW_BIAS)/8)
        bcc @bonus_next
        lda target_camera+1
        jeq @ready              ; targets below256 cannot enter the next row
        cmp #1
        bne @bonus_next
        lda target_camera
        jeq @ready              ; target256 cannot enter the next row
@bonus_next:
        txa                     ; synthetic targets retain the generic pipeline
        clc
        adc #1
        jmp @need
@bonus_down:
        lda view_row
        sec
        sbc #1
        jmp @need
@predict:
        lda visual_camera
        sta work_lo
        lda visual_camera+1
        sta work_hi
        lda target_camera+1
        cmp work_hi
        bcc @predict_down
        bne @predict_up
        lda target_camera
        cmp work_lo
        bcc @predict_down
        beq @rest
@predict_up:
        lda work_lo
        clc
        adc #4
        sta work_lo
        bcc @limit_up
        inc work_hi
@limit_up:
        lda work_hi
        cmp target_camera+1
        bcc @predict_row
        bne @limit_target
        lda work_lo
        cmp target_camera
        bcc @predict_row
        bcs @limit_target
@predict_down:
        lda work_lo
        sec
        sbc #4
        sta work_lo
        lda work_hi
        sbc #0
        sta work_hi
        bmi @limit_target
        cmp target_camera+1
        bcc @limit_target
        bne @predict_row
        lda work_lo
        cmp target_camera
        bcs @predict_row
@limit_target:
        lda target_camera
        sta work_lo
        lda target_camera+1
        sta work_hi
@rest:  ; Camera at rest: build the row above in advance, so a climb
        ; starts scrolling at once (a descent still waits for its row).
        lda view_dirty
        bne @predict_row
        lda colour_frame        ; the just-swapped row already covers this view
        jne @ready              ; defer speculative prefetch on its colour commit
        lda late_commit         ; behind time: build it in a later frame
        jne @ready
        lda view_row
        clc
        adc #1
        jmp @need
@predict_row:
        lda work_lo
        clc
        adc #VIEW_BIAS
        sta work_lo
        lda work_hi
        adc #0
        sta work_hi
        lsr work_hi
        ror work_lo
        lsr work_hi
        ror work_lo
        lsr work_hi
        ror work_lo
        lda work_lo
@need:  sta work2
        lda copy_stage
        beq @choose
        lda work2
        cmp copy_target_row
        beq @chunk              ; keep building the wanted row
@choose:
        ; A row the camera no longer heads for is dropped, even when
        ; finished; otherwise a reversal would freeze camera and refreshes.
        lda copy_stage
        beq :+
        lda #$FF                ; the back buffer is partly overwritten
        sta back_view
:       lda #0
        sta copy_stage
        lda work2
        cmp last_view_row
        bne @start_copy
        lda view_dirty
        jeq @ready
        lda view_row
@start_copy:
        sta copy_target_row
        lda #1
        sta copy_stage
        lda #0
        sta view_dirty
        lda state
        cmp #3
        bne @full_setup
        lda player_count
        cmp #2
        bne @full_setup
        jsr bonus_copy_setup_first
        inc copy_stage         ;2:finish setup,3:firsthalf,4:secondhalf,5:ready
        inc chunk_frame
        jmp @hold
@full_setup:
        jsr copy_setup          ; once per row: the chunks only pick columns
        lda state
        cmp #3
        bne @chunk
        inc chunk_frame         ; copy_setup costs about one chunk
        lda view_row
        cmp last_view_row
        jeq @ready              ; bonus: the halves follow on later frames
@chunk: lda state
        cmp #3
        bne @generic_chunk
        lda player_count
        cmp #2
        jeq @bonus_chunk
@generic_chunk:
        lda copy_stage
        cmp #3
        beq @available
        lda state
        cmp #1
        beq :+
        cmp #3
        bne @partial
:       lda view_row
        cmp last_view_row
        beq @partial
        ; Physics is frozen during a 12-tick, 48-pixel normal pan. Complete
        ; the new coarse row now so a sixth NTSC tick cannot stall the view.
        inc chunk_frame
        ldy copy_stage          ; finish only the columns still outstanding
        lda copy_starts-1,Y
        ldx #$FF
        jsr CACHE_COPY_RUN
        lda #3
        sta copy_stage
        jmp @available
@partial:
        lda copy_stage
        tay
        ldx copy_stops-1,Y
        lda copy_starts-1,Y
        inc chunk_frame         ; this frame copies columns
        jsr CACHE_COPY_RUN
        inc copy_stage
@available:
        lda copy_stage
        cmp #3
        bne @hold
@accept:
        lda copy_target_row
        cmp view_row
        bne @hold
        ldx last_view_row       ; the shown buffer becomes the back buffer
        stx back_view
        sta last_view_row
        lda #1
        sta colour_ready
        lda #0
        sta copy_stage
        lda screen_buffer
        eor #1
        sta pending_buffer
        jmp @hold
@bonus_chunk:
        lda copy_stage
        cmp #5
        beq @accept
        cmp #2
        beq @bonus_finish_setup
        sec
        sbc #3
        tay
        ldx copy_bonus_stops,Y
        lda copy_bonus_starts,Y
        inc chunk_frame
        jsr CACHE_COPY_RUN
        inc copy_stage
        lda copy_stage
        cmp #5
        beq @accept
        jmp @hold
@bonus_finish_setup:
        ; Patches and actor preparation overwrite the ordinary scratch
        ; bytes between frames. The second entry reconstructs all of them.
        jsr bonus_copy_setup_second
        inc copy_stage
        inc chunk_frame
@hold:  lda view_row
        cmp last_view_row
        beq @ready
        ; Keep sprites and VIC fine scrolling on the completed viewport.
        lda old_visual
        sta visual_camera
        lda old_visual+1
        sta visual_camera+1
        lda old_fine
        sta view_fine
        lda old_view_row
        sta view_row
@ready: lda #1
        sta packet_ready
@done:  rts
; Normal/preview/one-player bonus copy 14 then 18 columns. Two-player bonus
; runs setup separately and leaves more time for sprites in its first chunk.
; The second start is also the first stop (exclusive; X counts down).
copy_starts: .byte 31,17
copy_stops = copy_starts+1
        .byte $FF
copy_bonus_starts: .byte 31,19
copy_bonus_stops = copy_bonus_starts+1
        .byte $FF
.segment "CODE"

; Bonus camera: the shown camera eases after the logical one, which the
; climber pushes up at his jump speed (aliased 6:5 onto PAL frames). The
; speed aims at a quarter of the distance, at most CHASE_MAX, and changes
; by one pixel per frame; it never overshoots.
bonus_chase:
        lda target_camera
        sec
        sbc visual_camera
        tax
        lda target_camera+1
        sbc visual_camera+1
        sta work_hi             ; bit 7: the target is below
        bpl @up
        cmp #$FF
        bne @snap
        txa
        eor #$FF
        tax
        inx                     ; distance 1..256 (0 = 256)
        beq @snap
        bne @distance
@up:    bne @snap               ; 256 pixels or more
        txa
        beq @rest
@distance:
        stx work_lo
        txa
        clc
        adc #3
        ror                     ; ceil(distance/4), carry included
        lsr
        cmp #CHASE_MAX+1
        bcc :+
        lda #CHASE_MAX
:       cmp chase_speed
        beq @move
        bcc @slower
        inc chase_speed
        bne @move
@slower:dec chase_speed
@move:  lda chase_speed
        cmp work_lo
        bcc :+
        lda work_lo
:       bit work_hi
        bmi @down
        clc
        adc visual_camera
        sta visual_camera
        bcc @done
        inc visual_camera+1
@done:  rts
@down:  sta work_lo
        lda visual_camera
        sec
        sbc work_lo
        sta visual_camera
        bcs @done
        dec visual_camera+1
        rts
@snap:  lda target_camera
        sta visual_camera
        lda target_camera+1
        sta visual_camera+1
@rest:  lda #0
        sta chase_speed
        rts


.segment "HIGH"
; Patch the runtime copy once for each coarse camera row. Cache rows wrap
; within their 64-row ring; the flyover can stream the upper mountain in.
COPY_BODY = CACHE_COPY+8
COPY_COLOURS = COPY_BODY+25*6
        .assert >COPY_COLOURS = >(CACHE_COPY+2), error, "Copy tail must share page"
        .assert (SCREEN & 7) = 0, error, "Screen rows must be eight-byte aligned"
.segment "DATA"
cache_row_lo:
        .repeat 64,I
        .byte <(WORLD_CACHE+I*32)
        .endrep
cache_row_hi:
        .repeat 64,I
        .byte >(WORLD_CACHE+I*32)
        .endrep
.segment "HIGH"
copy_setup:
        lda #25
        sta copy_setup_stop
        lda #0
        sta copy_row
        tax
        beq copy_setup_start
bonus_copy_setup_first:
        lda #12
        sta copy_setup_stop
        lda #0
        sta copy_row
        tax
        beq copy_setup_start
bonus_copy_setup_second:
        lda #25
        sta copy_setup_stop
        lda #12
        sta copy_row
        ldx copy_bodyidx
copy_setup_start:
        lda copy_target_row
        clc
        adc #24
        sec
        sbc copy_row
        and #63
        sta copy_crow
        lda screen_buffer
        eor #1
        asl
        asl
        sta tmp
        lda #0
        sta skip_rows
        sta byteidx             ; bonus rows are all constant-colour: zero pairs
        lda back_view
        bmi :+
        clc
        adc #2
        cmp copy_target_row
        bne :+
        lda #$FF
        sta skip_rows
:
@row:   ldy copy_crow
        lda SAME2,Y
        and skip_rows
        bne @colour            ; identical rows emit no per-column work
        lda #$BD
        sta COPY_BODY,X
        lda cache_row_lo,Y
        sta work_lo
        sta COPY_BODY+1,X
        lda cache_row_hi,Y
        sta work_hi
        sta COPY_BODY+2,X
        ldy copy_row
        lda screen_row_lo,Y
        ora #4                  ; 40-byte row stride leaves bit 2 clear
        sta COPY_BODY+4,X
        lda screen_row_hi,Y
        ora tmp
        sta COPY_BODY+5,X
        txa
        clc
        adc #6
        tax
@colour:
        ldy copy_crow
        lda ROW_KIND,Y
        cmp #ROW_FULL
        bne @next
        stx work2
        ldx byteidx
        lda #$BD
        sta COPY_COLOURS,X
        lda work_lo
        sta COPY_COLOURS+1,X
        lda work_hi
        clc
        adc #>(COLOUR_CACHE-WORLD_CACHE)
        sta COPY_COLOURS+2,X
        ldy copy_row
        lda screen_row_lo,Y
        ora #4                  ; carry remains clear from the cache-page add
        sta COPY_COLOURS+4,X
        lda screen_row_hi,Y
        adc #>(COLOUR_BACK-SCREEN)
        sta COPY_COLOURS+5,X
        txa
        clc
        adc #6
        sta byteidx
        ldx work2
@next:  dec copy_crow
        bpl :+
        lda #63
        sta copy_crow
:       inc copy_row
        lda copy_row
        cmp copy_setup_stop
        jne @row
        stx copy_bodyidx
        lda copy_setup_stop
        cmp #25
        bne @done               ; partial template is not executed yet
        cpx #25*6
        beq @colours            ; all25 pairs already fall into COPY_COLOURS
        lda #$4C
        sta COPY_BODY,X
        lda #<COPY_COLOURS
        ldy byteidx
        bne :+
        lda #<(CACHE_COPY+2)    ; empty colour list: skip its JMP per column
:
        sta COPY_BODY+1,X
        lda #>COPY_COLOURS
        sta COPY_BODY+2,X
@colours:
        ldx byteidx
        lda #$4C
        sta COPY_COLOURS,X
        lda #<(CACHE_COPY+2)
        sta COPY_COLOURS+1,X
        lda #>(CACHE_COPY+2)
        sta COPY_COLOURS+2,X
@done:  rts
.segment "CODE"

CACHE_COPY_RUN:
        clc
        adc #1
        sta CACHE_COPY+1
        stx CACHE_COPY+4
        jmp CACHE_COPY

; Runs in the lower border. The new buffer, its colours (commit_colours) and
; the playfield YSCROLL used by the raster split all take effect together.
commit_view:
        lda state
        beq @done
        cmp #2
        beq @done
        lda packet_ready
        beq @done
        lda pending_buffer
        sta screen_buffer
        asl
        asl
        asl
        asl
        ora #GAME_CHARSET
        sta $D018
        jsr split_latch
        lda #0
        sta packet_ready
@done:  rts

; Latch one playfield fine scroll for the whole 24-row viewport.
split_latch:
        lda view_fine
        and #7
        ora #$10
        sta split_open
        jmp terrain_palette_latch

; Runtime header only. view_init supplies STA opcodes; copy_setup writes
; every executed pair, the packed-body jump and the colour-list tail.
; Unused bytes may contain arbitrary RAM and are never executed.
cache_copy_template:
        .byte $A2,32            ; ldx #first+1
        .byte $CA,$E0,$FF       ; loop: dex / cpx #stop
        .byte $D0,$01,$60       ; bne body / rts
cache_copy_template_end:
CACHE_COPY_TEMPLATE_SIZE = cache_copy_template_end-cache_copy_template
        .assert CACHE_COPY_TEMPLATE_SIZE = 8, error, "Copy header changed"

.segment "HIGH"
; Lower border, right after the buffer swap: cloud glyph phases and every
; changed world row become visible in the same frame. A row is copied into
; the shown buffer and into the one under construction; colours go where
; the next frame reads them (COLOUR_BACK when commit_colours follows).
commit_patches:
        jsr commit_clouds
        lda state
        beq @done
        cmp #2
        beq @done
        cmp #4
        beq @done
        lda patch_any
        beq @done
        lda #0
        sta patch_any
        lda state
        cmp #3
        bne :+
        jmp bonus_commit_patches
:
        jmp commit_listed_rows
@done:  rts

patch_one_row:
        sta patch_kind
        lda PATCH_LO,X
        sta patch_lo
        lda PATCH_HI,X
        sta patch_hi
        lda #0
        sta PATCH_FLAG,X
        stx copy_row
        lda last_view_row       ; shown buffer: colours straight to colour RAM
        ldy screen_buffer       ; (commit_colours has already run)
        jsr patch_target
        bcs @back
        jsr patch_row
@back:  lda copy_stage
        beq @patched
        cmp #4
        bcs @write_back
        lda state
        cmp #3
        bne @write_back
        lda player_count
        cmp #2
        ; In the split setup, no columns have been copied before stage 4.
        ; Every cloud row is emitted, so those columns will read the patch
        ; directly from the cache. The visible buffer was patched above.
        beq @patched
@write_back:
        lda screen_buffer
        eor #1
        tay
        lda copy_target_row
        jsr patch_target
        bcs @patched
        lda colptr+1
        clc
        adc #$EC-$D8
        sta colptr+1
        jsr patch_row
@patched:
        ldx copy_row
        rts

.segment "CODE"
; Bonus stone never changes. Only the at most five private cloud rows can
; be dirty, so visit those directly instead of scanning all64 cache flags.
bonus_commit_patches:
        lda bonus_cloud_count
        sta ui_index
@next:  dec ui_index
        bmi @done
        ldy ui_index
        ldx BONUS_CLOUD_CACHE_ROW,Y
        lda PATCH_FLAG,X
        beq @next
        jsr patch_one_row
        jmp @next
@done:  rts

.segment "EXTRA"
; A=view row of the buffer, Y=buffer, copy_row=cache row. Carry set if the
; row is off screen; otherwise src/work_lo = cache rows, dst/colptr = screen
; row in that buffer and in colour RAM.
patch_target:
        sta tmp
        lda copy_row
        sec
        sbc tmp
        cmp #25
        bcs @off
        eor #$FF
        sec
        adc #24                 ; screen row 24-(row-view)
        tax
        lda screen_row_lo,X
        clc
        adc #4
        sta dst
        sta colptr
        lda screen_row_hi,X
        adc #0
        sta colptr+1
        cpy #0
        beq @front
        clc
        adc #>(BACK_SCREEN-SCREEN)
@front: sta dst+1
        lda colptr+1
        clc
        adc #>($D800-SCREEN)
        sta colptr+1
        lda copy_row
        lsr
        lsr
        lsr
        clc
        adc #>WORLD_CACHE
        sta src+1
        adc #>(COLOUR_CACHE-WORLD_CACHE)
        sta work_hi
        lda copy_row
        and #7
        asl
        asl
        asl
        asl
        asl
        sta src
        sta work_lo
        clc
@off:   rts

; Cells patch_lo..patch_hi: characters, and colours for PATCH_COLOURS.
patch_row:
        ldy patch_hi
        lda patch_kind
        and #PATCH_WRAP
        jne patch_row_wrap
        lda patch_kind
        and #PATCH_COLOURS
        beq @chars
@both:  lda (src),Y
        sta (dst),Y
        lda (work_lo),Y
        sta (colptr),Y
        cpy patch_lo
        beq @done
        dey
        bcs @both
@chars: jmp patch_row_chars
@done:  rts

.segment "CODE"
; Wrapped character patches contain two intervals:0..hi and lo..31.
; Keep all metadata intact so the same patch also reaches the back buffer.
patch_row_wrap:
        lda patch_lo
        pha
        lda #0
        sta patch_lo
        jsr patch_row_chars
        pla
        sta patch_lo
        ldy #31
        jmp patch_row_chars

; Full character rows are the common moving-cloud patch. Copy pairs so
; neither target buffer spends a comparison and two branches on each cell.
patch_row_chars:
        lda patch_lo
        bne @single
        cpy #31
        bne @single
@pair:  lda (src),Y
        sta (dst),Y
        dey
        lda (src),Y
        sta (dst),Y
        dey
        bpl @pair
@done:  rts
@single:                        ; cells patch_lo..Y: an odd count first
        tya                     ; copies the top cell alone, then pairs
        sec                     ; with one comparison each
        sbc patch_lo
        lsr
        bcs @pairs
        lda (src),Y
        sta (dst),Y
        cpy patch_lo
        beq @done
        dey
@pairs: lda (src),Y
        sta (dst),Y
        dey
        lda (src),Y
        sta (dst),Y
        cpy patch_lo
        beq @done
        dey
        bcs @pairs              ; (Y > patch_lo: carry set)

.segment "HIGH"
; Row-major colour commit for a swapped buffer, from the lower border on;
; it stays ahead of the beam. ROW_KIND skips colours that cannot be seen:
; blank cells between floors (rock walls only) and the bonus stage's sky.
commit_colours:
        lda #0
        sta colour_frame
        lda state
        jeq @done
        cmp #2
        jeq @done
        lda colour_ready
        jeq @done
        lda #0
        sta colour_ready
        lda #1
        sta colour_frame
        lda last_view_row
        clc
        adc #24
        and #63
        tax
        lda ROW_KIND,X
        beq @skip0
        ldy #0
        cmp #ROW_FULL
        bne @walls0
        jsr colour_full_0
        jmp @skip0
@walls0:
        jsr colour_walls_0
@skip0:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X
        beq @skip1
        ldy #40
        cmp #ROW_FULL
        bne @walls1
        jsr colour_full_0
        jmp @skip1
@walls1:
        jsr colour_walls_0
@skip1:
        dex
        bpl :+
        ldx #63
:               lda ROW_KIND,X          ; screen row 2
        beq @skip2
        ldy #0
        cmp #ROW_FULL
        bne @walls2
        jsr colour_full_2
        jmp @skip2
@walls2:
        jsr colour_walls_2
@skip2:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 3
        beq @skip3
        ldy #40
        cmp #ROW_FULL
        bne @walls3
        jsr colour_full_2
        jmp @skip3
@walls3:
        jsr colour_walls_2
@skip3:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 4
        beq @skip4
        ldy #80
        cmp #ROW_FULL
        bne @walls4
        jsr colour_full_2
        jmp @skip4
@walls4:
        jsr colour_walls_2
@skip4:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 5
        beq @skip5
        ldy #120
        cmp #ROW_FULL
        bne @walls5
        jsr colour_full_2
        jmp @skip5
@walls5:
        jsr colour_walls_2
@skip5:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 6
        beq @skip6
        ldy #160
        cmp #ROW_FULL
        bne @walls6
        jsr colour_full_2
        jmp @skip6
@walls6:
        jsr colour_walls_2
@skip6:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 7
        beq @skip7
        ldy #200
        cmp #ROW_FULL
        bne @walls7
        jsr colour_full_2
        jmp @skip7
@walls7:
        jsr colour_walls_2
@skip7:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 8
        beq @skip8
        ldy #240
        cmp #ROW_FULL
        bne @walls8
        jsr colour_full_2
        jmp @skip8
@walls8:
        jsr colour_walls_2
@skip8:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 9
        beq @skip9
        ldy #0
        cmp #ROW_FULL
        bne @walls9
        jsr colour_full_9
        jmp @skip9
@walls9:
        jsr colour_walls_9
@skip9:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 10
        beq @skip10
        ldy #40
        cmp #ROW_FULL
        bne @walls10
        jsr colour_full_9
        jmp @skip10
@walls10:
        jsr colour_walls_9
@skip10:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 11
        beq @skip11
        ldy #80
        cmp #ROW_FULL
        bne @walls11
        jsr colour_full_9
        jmp @skip11
@walls11:
        jsr colour_walls_9
@skip11:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 12
        beq @skip12
        ldy #120
        cmp #ROW_FULL
        bne @walls12
        jsr colour_full_9
        jmp @skip12
@walls12:
        jsr colour_walls_9
@skip12:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 13
        beq @skip13
        ldy #160
        cmp #ROW_FULL
        bne @walls13
        jsr colour_full_9
        jmp @skip13
@walls13:
        jsr colour_walls_9
@skip13:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 14
        beq @skip14
        ldy #200
        cmp #ROW_FULL
        bne @walls14
        jsr colour_full_9
        jmp @skip14
@walls14:
        jsr colour_walls_9
@skip14:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 15
        beq @skip15
        ldy #240
        cmp #ROW_FULL
        bne @walls15
        jsr colour_full_9
        jmp @skip15
@walls15:
        jsr colour_walls_9
@skip15:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 16
        beq @skip16
        ldy #0
        cmp #ROW_FULL
        bne @walls16
        jsr colour_full_16
        jmp @skip16
@walls16:
        jsr colour_walls_16
@skip16:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 17
        beq @skip17
        ldy #40
        cmp #ROW_FULL
        bne @walls17
        jsr colour_full_16
        jmp @skip17
@walls17:
        jsr colour_walls_16
@skip17:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 18
        beq @skip18
        ldy #80
        cmp #ROW_FULL
        bne @walls18
        jsr colour_full_16
        jmp @skip18
@walls18:
        jsr colour_walls_16
@skip18:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 19
        beq @skip19
        ldy #120
        cmp #ROW_FULL
        bne @walls19
        jsr colour_full_16
        jmp @skip19
@walls19:
        jsr colour_walls_16
@skip19:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 20
        beq @skip20
        ldy #160
        cmp #ROW_FULL
        bne @walls20
        jsr colour_full_16
        jmp @skip20
@walls20:
        jsr colour_walls_16
@skip20:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 21
        beq @skip21
        ldy #200
        cmp #ROW_FULL
        bne @walls21
        jsr colour_full_16
        jmp @skip21
@walls21:
        jsr colour_walls_16
@skip21:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 22
        beq @skip22
        ldy #240
        cmp #ROW_FULL
        bne @walls22
        jsr colour_full_16
        jmp @skip22
@walls22:
        jsr colour_walls_16
@skip22:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 23
        beq @skip23
        ldy #0
        cmp #ROW_FULL
        bne @walls23
        jsr colour_full_23
        jmp @skip23
@walls23:
        jsr colour_walls_23
@skip23:
        dex
        bpl :+
        ldx #63
:       lda ROW_KIND,X          ; screen row 24
        beq @skip24
        ldy #40
        cmp #ROW_FULL
        bne @walls24
        jsr colour_full_23
        jmp @skip24
@walls24:
        jsr colour_walls_23
@skip24:
        dex
@done:  rts

colour_full_0:
        .repeat 32,I
        lda COLOUR_BACK+4+I,Y
        sta $D800+4+I,Y
        .endrep
        rts
colour_walls_0:
        bmi @walls
        and #$0F
        jmp colour_constant_0
@walls:
        and #$0F
        .repeat 6,I
        sta $D800+4+I,Y
        sta $D800+4+26+I,Y
        .endrep
        lda ROW_KIND,X
        and #ROW_NUMBER
        beq @done
        lda #<($D800+0*40+4)
        sta colptr
        lda #>($D800+0*40+4)
        sta colptr+1
        jmp colour_wall_digits
@done:  rts
colour_full_2:
        lda COLOUR_BACK+2*40+4+0,Y
        sta $D800+2*40+4+0,Y
        lda COLOUR_BACK+2*40+4+1,Y
        sta $D800+2*40+4+1,Y
        lda COLOUR_BACK+2*40+4+2,Y
        sta $D800+2*40+4+2,Y
        lda COLOUR_BACK+2*40+4+3,Y
        sta $D800+2*40+4+3,Y
        lda COLOUR_BACK+2*40+4+4,Y
        sta $D800+2*40+4+4,Y
        lda COLOUR_BACK+2*40+4+5,Y
        sta $D800+2*40+4+5,Y
        lda COLOUR_BACK+2*40+4+6,Y
        sta $D800+2*40+4+6,Y
        lda COLOUR_BACK+2*40+4+7,Y
        sta $D800+2*40+4+7,Y
        lda COLOUR_BACK+2*40+4+8,Y
        sta $D800+2*40+4+8,Y
        lda COLOUR_BACK+2*40+4+9,Y
        sta $D800+2*40+4+9,Y
        lda COLOUR_BACK+2*40+4+10,Y
        sta $D800+2*40+4+10,Y
        lda COLOUR_BACK+2*40+4+11,Y
        sta $D800+2*40+4+11,Y
        lda COLOUR_BACK+2*40+4+12,Y
        sta $D800+2*40+4+12,Y
        lda COLOUR_BACK+2*40+4+13,Y
        sta $D800+2*40+4+13,Y
        lda COLOUR_BACK+2*40+4+14,Y
        sta $D800+2*40+4+14,Y
        lda COLOUR_BACK+2*40+4+15,Y
        sta $D800+2*40+4+15,Y
        lda COLOUR_BACK+2*40+4+16,Y
        sta $D800+2*40+4+16,Y
        lda COLOUR_BACK+2*40+4+17,Y
        sta $D800+2*40+4+17,Y
        lda COLOUR_BACK+2*40+4+18,Y
        sta $D800+2*40+4+18,Y
        lda COLOUR_BACK+2*40+4+19,Y
        sta $D800+2*40+4+19,Y
        lda COLOUR_BACK+2*40+4+20,Y
        sta $D800+2*40+4+20,Y
        lda COLOUR_BACK+2*40+4+21,Y
        sta $D800+2*40+4+21,Y
        lda COLOUR_BACK+2*40+4+22,Y
        sta $D800+2*40+4+22,Y
        lda COLOUR_BACK+2*40+4+23,Y
        sta $D800+2*40+4+23,Y
        lda COLOUR_BACK+2*40+4+24,Y
        sta $D800+2*40+4+24,Y
        lda COLOUR_BACK+2*40+4+25,Y
        sta $D800+2*40+4+25,Y
        lda COLOUR_BACK+2*40+4+26,Y
        sta $D800+2*40+4+26,Y
        lda COLOUR_BACK+2*40+4+27,Y
        sta $D800+2*40+4+27,Y
        lda COLOUR_BACK+2*40+4+28,Y
        sta $D800+2*40+4+28,Y
        lda COLOUR_BACK+2*40+4+29,Y
        sta $D800+2*40+4+29,Y
        lda COLOUR_BACK+2*40+4+30,Y
        sta $D800+2*40+4+30,Y
        lda COLOUR_BACK+2*40+4+31,Y
        sta $D800+2*40+4+31,Y
        rts
colour_walls_2:
        bmi @walls
        and #$0F
        jmp colour_constant_2
@walls:
        and #$0F
        sta $D800+2*40+4+0,Y
        sta $D800+2*40+4+1,Y
        sta $D800+2*40+4+2,Y
        sta $D800+2*40+4+3,Y
        sta $D800+2*40+4+4,Y
        sta $D800+2*40+4+5,Y
        sta $D800+2*40+4+26,Y
        sta $D800+2*40+4+27,Y
        sta $D800+2*40+4+28,Y
        sta $D800+2*40+4+29,Y
        sta $D800+2*40+4+30,Y
        sta $D800+2*40+4+31,Y
        lda ROW_KIND,X
        and #ROW_NUMBER
        beq @done
        lda #<($D800+2*40+4)
        sta colptr
        lda #>($D800+2*40+4)
        sta colptr+1
        jmp colour_wall_digits
@done:  rts
colour_full_9:
        lda COLOUR_BACK+9*40+4+0,Y
        sta $D800+9*40+4+0,Y
        lda COLOUR_BACK+9*40+4+1,Y
        sta $D800+9*40+4+1,Y
        lda COLOUR_BACK+9*40+4+2,Y
        sta $D800+9*40+4+2,Y
        lda COLOUR_BACK+9*40+4+3,Y
        sta $D800+9*40+4+3,Y
        lda COLOUR_BACK+9*40+4+4,Y
        sta $D800+9*40+4+4,Y
        lda COLOUR_BACK+9*40+4+5,Y
        sta $D800+9*40+4+5,Y
        lda COLOUR_BACK+9*40+4+6,Y
        sta $D800+9*40+4+6,Y
        lda COLOUR_BACK+9*40+4+7,Y
        sta $D800+9*40+4+7,Y
        lda COLOUR_BACK+9*40+4+8,Y
        sta $D800+9*40+4+8,Y
        lda COLOUR_BACK+9*40+4+9,Y
        sta $D800+9*40+4+9,Y
        lda COLOUR_BACK+9*40+4+10,Y
        sta $D800+9*40+4+10,Y
        lda COLOUR_BACK+9*40+4+11,Y
        sta $D800+9*40+4+11,Y
        lda COLOUR_BACK+9*40+4+12,Y
        sta $D800+9*40+4+12,Y
        lda COLOUR_BACK+9*40+4+13,Y
        sta $D800+9*40+4+13,Y
        lda COLOUR_BACK+9*40+4+14,Y
        sta $D800+9*40+4+14,Y
        lda COLOUR_BACK+9*40+4+15,Y
        sta $D800+9*40+4+15,Y
        lda COLOUR_BACK+9*40+4+16,Y
        sta $D800+9*40+4+16,Y
        lda COLOUR_BACK+9*40+4+17,Y
        sta $D800+9*40+4+17,Y
        lda COLOUR_BACK+9*40+4+18,Y
        sta $D800+9*40+4+18,Y
        lda COLOUR_BACK+9*40+4+19,Y
        sta $D800+9*40+4+19,Y
        lda COLOUR_BACK+9*40+4+20,Y
        sta $D800+9*40+4+20,Y
        lda COLOUR_BACK+9*40+4+21,Y
        sta $D800+9*40+4+21,Y
        lda COLOUR_BACK+9*40+4+22,Y
        sta $D800+9*40+4+22,Y
        lda COLOUR_BACK+9*40+4+23,Y
        sta $D800+9*40+4+23,Y
        lda COLOUR_BACK+9*40+4+24,Y
        sta $D800+9*40+4+24,Y
        lda COLOUR_BACK+9*40+4+25,Y
        sta $D800+9*40+4+25,Y
        lda COLOUR_BACK+9*40+4+26,Y
        sta $D800+9*40+4+26,Y
        lda COLOUR_BACK+9*40+4+27,Y
        sta $D800+9*40+4+27,Y
        lda COLOUR_BACK+9*40+4+28,Y
        sta $D800+9*40+4+28,Y
        lda COLOUR_BACK+9*40+4+29,Y
        sta $D800+9*40+4+29,Y
        lda COLOUR_BACK+9*40+4+30,Y
        sta $D800+9*40+4+30,Y
        lda COLOUR_BACK+9*40+4+31,Y
        sta $D800+9*40+4+31,Y
        rts
colour_walls_9:
        bmi @walls
        and #$0F
        jmp colour_constant_9
@walls:
        and #$0F
        sta $D800+9*40+4+0,Y
        sta $D800+9*40+4+1,Y
        sta $D800+9*40+4+2,Y
        sta $D800+9*40+4+3,Y
        sta $D800+9*40+4+4,Y
        sta $D800+9*40+4+5,Y
        sta $D800+9*40+4+26,Y
        sta $D800+9*40+4+27,Y
        sta $D800+9*40+4+28,Y
        sta $D800+9*40+4+29,Y
        sta $D800+9*40+4+30,Y
        sta $D800+9*40+4+31,Y
        lda ROW_KIND,X
        and #ROW_NUMBER
        beq @done
        lda #<($D800+9*40+4)
        sta colptr
        lda #>($D800+9*40+4)
        sta colptr+1
        jmp colour_wall_digits
@done:  rts
colour_full_16:
        lda COLOUR_BACK+16*40+4+0,Y
        sta $D800+16*40+4+0,Y
        lda COLOUR_BACK+16*40+4+1,Y
        sta $D800+16*40+4+1,Y
        lda COLOUR_BACK+16*40+4+2,Y
        sta $D800+16*40+4+2,Y
        lda COLOUR_BACK+16*40+4+3,Y
        sta $D800+16*40+4+3,Y
        lda COLOUR_BACK+16*40+4+4,Y
        sta $D800+16*40+4+4,Y
        lda COLOUR_BACK+16*40+4+5,Y
        sta $D800+16*40+4+5,Y
        lda COLOUR_BACK+16*40+4+6,Y
        sta $D800+16*40+4+6,Y
        lda COLOUR_BACK+16*40+4+7,Y
        sta $D800+16*40+4+7,Y
        lda COLOUR_BACK+16*40+4+8,Y
        sta $D800+16*40+4+8,Y
        lda COLOUR_BACK+16*40+4+9,Y
        sta $D800+16*40+4+9,Y
        lda COLOUR_BACK+16*40+4+10,Y
        sta $D800+16*40+4+10,Y
        lda COLOUR_BACK+16*40+4+11,Y
        sta $D800+16*40+4+11,Y
        lda COLOUR_BACK+16*40+4+12,Y
        sta $D800+16*40+4+12,Y
        lda COLOUR_BACK+16*40+4+13,Y
        sta $D800+16*40+4+13,Y
        lda COLOUR_BACK+16*40+4+14,Y
        sta $D800+16*40+4+14,Y
        lda COLOUR_BACK+16*40+4+15,Y
        sta $D800+16*40+4+15,Y
        lda COLOUR_BACK+16*40+4+16,Y
        sta $D800+16*40+4+16,Y
        lda COLOUR_BACK+16*40+4+17,Y
        sta $D800+16*40+4+17,Y
        lda COLOUR_BACK+16*40+4+18,Y
        sta $D800+16*40+4+18,Y
        lda COLOUR_BACK+16*40+4+19,Y
        sta $D800+16*40+4+19,Y
        lda COLOUR_BACK+16*40+4+20,Y
        sta $D800+16*40+4+20,Y
        lda COLOUR_BACK+16*40+4+21,Y
        sta $D800+16*40+4+21,Y
        lda COLOUR_BACK+16*40+4+22,Y
        sta $D800+16*40+4+22,Y
        lda COLOUR_BACK+16*40+4+23,Y
        sta $D800+16*40+4+23,Y
        lda COLOUR_BACK+16*40+4+24,Y
        sta $D800+16*40+4+24,Y
        lda COLOUR_BACK+16*40+4+25,Y
        sta $D800+16*40+4+25,Y
        lda COLOUR_BACK+16*40+4+26,Y
        sta $D800+16*40+4+26,Y
        lda COLOUR_BACK+16*40+4+27,Y
        sta $D800+16*40+4+27,Y
        lda COLOUR_BACK+16*40+4+28,Y
        sta $D800+16*40+4+28,Y
        lda COLOUR_BACK+16*40+4+29,Y
        sta $D800+16*40+4+29,Y
        lda COLOUR_BACK+16*40+4+30,Y
        sta $D800+16*40+4+30,Y
        lda COLOUR_BACK+16*40+4+31,Y
        sta $D800+16*40+4+31,Y
        rts
colour_walls_16:
        bmi @walls
        and #$0F
        jmp colour_constant_16
@walls:
        and #$0F
        sta $D800+16*40+4+0,Y
        sta $D800+16*40+4+1,Y
        sta $D800+16*40+4+2,Y
        sta $D800+16*40+4+3,Y
        sta $D800+16*40+4+4,Y
        sta $D800+16*40+4+5,Y
        sta $D800+16*40+4+26,Y
        sta $D800+16*40+4+27,Y
        sta $D800+16*40+4+28,Y
        sta $D800+16*40+4+29,Y
        sta $D800+16*40+4+30,Y
        sta $D800+16*40+4+31,Y
        lda ROW_KIND,X
        and #ROW_NUMBER
        beq @done
        lda #<($D800+16*40+4)
        sta colptr
        lda #>($D800+16*40+4)
        sta colptr+1
        jmp colour_wall_digits
@done:  rts
colour_full_23:
        lda COLOUR_BACK+23*40+4+0,Y
        sta $D800+23*40+4+0,Y
        lda COLOUR_BACK+23*40+4+1,Y
        sta $D800+23*40+4+1,Y
        lda COLOUR_BACK+23*40+4+2,Y
        sta $D800+23*40+4+2,Y
        lda COLOUR_BACK+23*40+4+3,Y
        sta $D800+23*40+4+3,Y
        lda COLOUR_BACK+23*40+4+4,Y
        sta $D800+23*40+4+4,Y
        lda COLOUR_BACK+23*40+4+5,Y
        sta $D800+23*40+4+5,Y
        lda COLOUR_BACK+23*40+4+6,Y
        sta $D800+23*40+4+6,Y
        lda COLOUR_BACK+23*40+4+7,Y
        sta $D800+23*40+4+7,Y
        lda COLOUR_BACK+23*40+4+8,Y
        sta $D800+23*40+4+8,Y
        lda COLOUR_BACK+23*40+4+9,Y
        sta $D800+23*40+4+9,Y
        lda COLOUR_BACK+23*40+4+10,Y
        sta $D800+23*40+4+10,Y
        lda COLOUR_BACK+23*40+4+11,Y
        sta $D800+23*40+4+11,Y
        lda COLOUR_BACK+23*40+4+12,Y
        sta $D800+23*40+4+12,Y
        lda COLOUR_BACK+23*40+4+13,Y
        sta $D800+23*40+4+13,Y
        lda COLOUR_BACK+23*40+4+14,Y
        sta $D800+23*40+4+14,Y
        lda COLOUR_BACK+23*40+4+15,Y
        sta $D800+23*40+4+15,Y
        lda COLOUR_BACK+23*40+4+16,Y
        sta $D800+23*40+4+16,Y
        lda COLOUR_BACK+23*40+4+17,Y
        sta $D800+23*40+4+17,Y
        lda COLOUR_BACK+23*40+4+18,Y
        sta $D800+23*40+4+18,Y
        lda COLOUR_BACK+23*40+4+19,Y
        sta $D800+23*40+4+19,Y
        lda COLOUR_BACK+23*40+4+20,Y
        sta $D800+23*40+4+20,Y
        lda COLOUR_BACK+23*40+4+21,Y
        sta $D800+23*40+4+21,Y
        lda COLOUR_BACK+23*40+4+22,Y
        sta $D800+23*40+4+22,Y
        lda COLOUR_BACK+23*40+4+23,Y
        sta $D800+23*40+4+23,Y
        lda COLOUR_BACK+23*40+4+24,Y
        sta $D800+23*40+4+24,Y
        lda COLOUR_BACK+23*40+4+25,Y
        sta $D800+23*40+4+25,Y
        lda COLOUR_BACK+23*40+4+26,Y
        sta $D800+23*40+4+26,Y
        lda COLOUR_BACK+23*40+4+27,Y
        sta $D800+23*40+4+27,Y
        lda COLOUR_BACK+23*40+4+28,Y
        sta $D800+23*40+4+28,Y
        lda COLOUR_BACK+23*40+4+29,Y
        sta $D800+23*40+4+29,Y
        lda COLOUR_BACK+23*40+4+30,Y
        sta $D800+23*40+4+30,Y
        lda COLOUR_BACK+23*40+4+31,Y
        sta $D800+23*40+4+31,Y
        rts
colour_walls_23:
        bmi @walls
        and #$0F
        jmp colour_constant_23
@walls:
        and #$0F
        sta $D800+23*40+4+0,Y
        sta $D800+23*40+4+1,Y
        sta $D800+23*40+4+2,Y
        sta $D800+23*40+4+3,Y
        sta $D800+23*40+4+4,Y
        sta $D800+23*40+4+5,Y
        sta $D800+23*40+4+26,Y
        sta $D800+23*40+4+27,Y
        sta $D800+23*40+4+28,Y
        sta $D800+23*40+4+29,Y
        sta $D800+23*40+4+30,Y
        sta $D800+23*40+4+31,Y
        lda ROW_KIND,X
        and #ROW_NUMBER
        beq @done
        lda #<($D800+23*40+4)
        sta colptr
        lda #>($D800+23*40+4)
        sta colptr+1
        jmp colour_wall_digits
@done:  rts
.segment "CODE"

.segment "CODE"
; Number rows need only two hires colour cells, rather than32cached bytes.
; X is the cache row; colptr/Y address the screen row's first world column.
colour_wall_digits:
        sty tmp
        lda ROW_KIND,X
        pha
        and #$30
        lsr
        lsr
        lsr
        lsr
        sta work2
        tya
        clc
        adc work2
        tay
        pla
        and #7
        sta (colptr),Y
        pha
        lda tmp
        clc
        adc #31
        bcc :+
        inc colptr+1           ; last grouped row crosses a page on the right
:       sec
        sbc work2
        tay
        pla
        sta (colptr),Y
        rts

.segment "CODE"
; Ice colours depend on altitude, not on broken/repaired cells. Upper
; cloud rows retain their colour cache because they mix hires and MC.
cache_constant_rows:
        lda #0
        sta cache_world
@floor: jsr floor_row
        ldy cache_world
        lda floor_types,Y
        and #$E0
        cmp #$60
        bcs @lower
        jsr @mark
@lower: dex
        jsr @mark
        inc cache_world
        lda cache_world
        cmp #9
        bne @floor
        rts
@mark:  lda #ROW_CONSTANT|15
        cpx #32
        bcc :+
        lda #ROW_CONSTANT|9
:       sta ROW_KIND,X
        rts

.segment "HIGH"
colour_constant_0:
        .repeat 32,I
        sta $D800+0*40+4+I,Y
        .endrep
        rts
colour_constant_2:
        .repeat 32,I
        sta $D800+2*40+4+I,Y
        .endrep
        rts
colour_constant_9:
        .repeat 32,I
        sta $D800+9*40+4+I,Y
        .endrep
        rts
colour_constant_16:
        .repeat 32,I
        sta $D800+16*40+4+I,Y
        .endrep
        rts
colour_constant_23:
        .repeat 32,I
        sta $D800+23*40+4+I,Y
        .endrep
        rts

.segment "CODE"
