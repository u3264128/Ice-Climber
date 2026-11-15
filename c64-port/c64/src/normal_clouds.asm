; Original $E662: two independent normal clouds, each wrapping in the
; complete 256-pixel NES world. Slot F+8 holds the second cloud of floor F.
GLYPH_PHASE2 = $0640
GLYPH_SHOWN2 = $0648
CLOUD_FIRST = 56
CLOUD_SECOND = 84
BONUS_CLOUD_FIRST = 128 ; eight immutable five-glyph phases, shared by all clouds
CLOUD_ATLAS_WORK = 52   ; four temporary glyphs while the screen is masked

.segment "DATA"
normal_cloud_init:
        ldy #0                  ; CLOUD_FLOORS: the cloud floors, top first
        ldx #7
@floor: lda floor_types,X
        and #$E0
        cmp #$60
        bcc :+
        txa
        sta CLOUD_FLOORS,Y
        iny
:       lda #0
        sta cloud_frac,X
        sta cloud_frac+8,X
        sta cloud_motion,X
        sta cloud_motion+8,X
        sta cloud_subpixel,X
        sta cloud_subpixel+8,X
        sta GLYPH_PHASE2,X
        lda #$FF
        sta GLYPH_SHOWN2,X
        sta clouds_cam          ; nes_export_clouds: new floor types
        lda floor_types,X
        and #$10
        eor #$10               ; E676: cloud direction is inverse of belt bit
        sta cloud_dir,X
        sta cloud_dir+8,X
        lda #33                ; original first X=$E8, plus4 view columns
        sta cloud_x,X
        lda floor_types,X
        and #$E0
        cmp #$C0
        beq @left
        cmp #$E0
        beq @random
        lda #4                 ; original second X=$00
        bne @store
@left: lda #34                 ; type C0: original second X=$F0
        bne @store
@random:
        lda #2                 ; same LFSR seed as the extracted lower ice:
        sta cloud_subpixel+8,X ; final random[1]=$D2 => X=$80+$12=$92
        lda #22
@store:sta cloud_x+8,X
        dex
        bne @floor
        lda #0
        sta CLOUD_FLOORS,Y
        rts

cloud_make_glyphs2:
        ldx cache_world
        lda cloud_subpixel+8,X
        sta GLYPH_PHASE2,X
        txa
        asl
        asl
        clc
        adc #CLOUD_SECOND-4
        sta cloud_glyph
        rts

; Joined floors draw two original 24-pixel clouds whose sprites overlap
; one character cell: 24 pixels apart ($E8/$00, cell 3 under cell 0) or
; 8 pixels apart on type C0 ($E8/$F0, cell 1 under cell 0). The NES shows
; both sprites there, but one screen code can show only one glyph, and the
; second cloud used to replace the first one's edge pixels: a gap of up to
; seven pixels opened and closed in the middle of the cloud. Both clouds
; always share the phase, so the union is a glyph the first cloud already
; has. Role 3 (end of the middle tile) plus the next cloud's role 0 (start
; of the middle tile) is role 2. Role 1 already holds the next cloud's role
; 0. Capped E0 clouds are 73-104 pixels apart and never share a cell.
; A = code in the cell (a cloud), X = role being painted. C set: keep cell.
.segment "LOWCODE"
cloud_join:
        cpx #0
        bne @paint              ; only a cloud's first cell can land on another
        cmp #CLOUD_SECOND
        bcs @paint              ; a stale second-cloud cell
        pha
        and #3                  ; CLOUD_FIRST is a multiple of four
        cmp #3
        pla
        bcc @keep
        sbc #1                  ; C set: role 3 becomes role 2
        sta (dst),Y
@keep:  sec
        rts
@paint: clc
        rts

.segment "EXTRA"
commit_clouds:
        lda state
        beq @off
        cmp #2
        beq @off
        cmp #4                  ; the flyover has no cloud glyphs on screen
        beq @off
        cmp #3
        beq :+
        jmp cloud_commit_normal
:       ldx bonus_cloud_count
        jmp cloud_commit_slots
@off:  rts
.segment "HIGH"
; Bonus clouds (one-based slots X..1).
cloud_commit_slots:
@slot: stx cloud_slot
        jsr bonus_cloud_in_view
        jcs @next
        lda bonus_cloud_x-1,X
        cmp BONUS_CLOUD_DRAWN_X-1,X
        beq :+
        dex                     ; painter uses zero-based bonus cloud indices
        jsr bonus_cloud_paint
        ldx cloud_slot          ; commit traversal retains the one-based slot
:
        lda GLYPH_PHASE,X
        sta GLYPH_SHOWN,X
@next: dex
        jne @slot
@done: rts

.segment "DATA"
; Normal play: the cloud floors of CLOUD_FLOORS, top first (the top
; cloud's screen codes follow its glyphs before that row is displayed).
cloud_commit_normal:
        ldy #0
@slot:  ldx CLOUD_FLOORS,Y
        bne :+
        rts
:       sty cloud_iter
        stx cloud_slot
        txa
        asl
        adc cloud_slot
        asl
        adc #CACHE_FLOOR_ROW
        sec
        sbc last_view_row
        cmp #25                 ; screen rows0..24, including clouds entering at the top
        jcs @next
        lda GLYPH_PHASE,X
        cmp GLYPH_SHOWN,X
        beq @second             ; unchanged (every cloud during a pan)
        ldy GLYPH_SHOWN2,X      ; ($FF: the second set must be copied)
        iny
        beq @reload
        clc                     ; both clouds share frac and direction: the
        adc GLYPH_SHOWN2,X      ; same step for both (phase+shown2 equals
        sta old_cloud_phase     ; phase2+shown) shifts both glyph sets at
        lda GLYPH_PHASE2,X      ; once
        clc
        adc GLYPH_SHOWN,X
        cmp old_cloud_phase
        bne @reload
        lda GLYPH_PHASE,X
        ldy GLYPH_SHOWN,X
        sta GLYPH_SHOWN,X
        jsr cloud_shift_both    ; C clear: both live glyph sets show it
        bcs @copy_first         ; (C set: copy each, as below)
        lda GLYPH_PHASE2,X
        sta GLYPH_SHOWN2,X
        jmp @second
@reload:
        lda GLYPH_PHASE,X
        ldy GLYPH_SHOWN,X
        sta GLYPH_SHOWN,X
        jsr cloud_shift_first   ; C clear: the live glyphs show it
        bcc @second
@copy_first:
        asl                     ; atlas entry: profile*32 + phase*4
        asl
        sta old_cloud_phase
        lda floor_types,X
        and #$E0
        cmp #$E0
        bne :+
        lda #64                 ; E0 has a separate capped cloud (profile 2)
        bne :++
:       lda #0                  ; joined left cloud
:       ora old_cloud_phase
        tay
        txa
        asl
        asl
        asl
        asl
        asl
        tax
        jsr cloud_copy_first
@second:
        lda GLYPH_PHASE2,X
        cmp GLYPH_SHOWN2,X
        beq @patch
        ldy GLYPH_SHOWN2,X
        sta GLYPH_SHOWN2,X
        jsr cloud_shift_second
        bcc @patch
        asl
        asl
        sta old_cloud_phase
        lda floor_types,X
        and #$E0
        cmp #$E0
        bne :+
        lda #64                 ; capped (profile 2)
        bne :++
:       lda #32                 ; joined right cloud (profile 1)
:       ora old_cloud_phase
        tay
        txa
        asl
        asl
        asl
        asl
        asl
        tax
        jsr cloud_copy_second
@patch: jsr normal_cloud_patch_row
@next:  ldy cloud_iter
        iny
        jmp @slot
.segment "CODE"
cloud_copy_atlas_glyph:
        ldy #7
@row:  lda (src),Y
        sta (dst),Y
        dey
        bpl @row
        rts
; Atlas phase p of a cloud is its 24-pixel row shifted right p pixels as
; one 32-bit row (cloud_generate_normal), so phase p+1 is phase p shifted
; right once and p-1 is p shifted left once. A one-pixel move within the
; character shifts the four live glyphs in place (about 350 cycles) instead
; of copying four atlas glyphs (about 830).
CLOUD_LIVE1 = CHARSET+CLOUD_FIRST*8-32  ; slot F: four glyphs at +32*F
CLOUD_LIVE2 = CHARSET+CLOUD_SECOND*8-32
.segment "DATA"
; A = new phase (not the shown one), Y = the phase the live glyphs show
; ($FF: none), X = slot. C set: copy them (A = new phase). C clear: X =
; 32*slot, A = the direction (N: left) and work_hi = the passes after the
; first (a move of two pixels takes two).
cloud_shift_dir:
        cpy #$FF
        beq @copy               ; (C set)
        sty work2
        tay
        sec
        sbc work2
        cmp #1
        beq @one
        cmp #$FF
        beq @one
        cmp #2
        beq @two
        cmp #$FE
        beq @two
        tya
        sec
@copy:  rts
@two:   ldy #1
        bne @passes
@one:   ldy #0
@passes:
        sty work_hi
        pha
        txa
        asl
        asl
        asl
        asl
        asl
        tax
        clc
        pla
        rts

; One pixel of all eight rows of a cloud's four glyphs (one 32-bit row each).
.macro shift_right live
        .repeat 8, R
        lsr live+R,X
        ror live+8+R,X
        ror live+16+R,X
        ror live+24+R,X
        .endrepeat
.endmacro
.macro shift_left live
        .repeat 8, R
        asl live+24+R,X
        rol live+16+R,X
        rol live+8+R,X
        rol live+R,X
        .endrepeat
.endmacro

cloud_shift_done:
        ldx cloud_slot
        clc
cloud_shift_copy:
        rts

cloud_shift_first:
        jsr cloud_shift_dir
        bcs cloud_shift_copy
        bpl @right
        jmp @left
@right: shift_right CLOUD_LIVE1
        dec work_hi
        bmi @done
        jmp @right
@left:  shift_left CLOUD_LIVE1
        dec work_hi
        bmi @done
        jmp @left
@done:  jmp cloud_shift_done

.segment "CODE"
cloud_shift_both:
        jsr cloud_shift_dir
        bcc :+
        rts                     ; (C set: copy)
:       bpl @right
        jmp @left
@right: shift_right CLOUD_LIVE1
        shift_right CLOUD_LIVE2
        dec work_hi
        bpl @right_again
        jmp cloud_shift_done
@right_again:
        jmp @right
@left:  shift_left CLOUD_LIVE1
        shift_left CLOUD_LIVE2
        dec work_hi
        bpl @left_again
        jmp cloud_shift_done
@left_again:
        jmp @left
.segment "DATA"

cloud_shift_second:
        jsr cloud_shift_dir
        bcc :+
        rts                     ; (C set: copy)
:       bpl @right
        jmp @left
@right: shift_right CLOUD_LIVE2
        dec work_hi
        bmi @done
        jmp @right
@left:  shift_left CLOUD_LIVE2
        dec work_hi
        bmi @done
        jmp @left
@done:  jmp cloud_shift_done

; The atlas entry's four glyphs as charset addresses (make_cloud_art.py).
cloud_phase_addr_lo:
        .incbin "../build/normal_cloud_phase_addr.bin", 0, 96
cloud_phase_addr_hi:
        .incbin "../build/normal_cloud_phase_addr.bin", 96, 96

; Y = atlas entry (profile*32 + phase*4): its four glyph addresses.
cloud_copy_pointers:
        lda cloud_phase_addr_lo,Y
        sta src
        lda cloud_phase_addr_hi,Y
        sta src+1
        lda cloud_phase_addr_lo+1,Y
        sta dst
        lda cloud_phase_addr_hi+1,Y
        sta dst+1
        lda cloud_phase_addr_lo+2,Y
        sta world_ptr
        lda cloud_phase_addr_hi+2,Y
        sta world_ptr+1
        lda cloud_phase_addr_lo+3,Y
        sta tmplo
        lda cloud_phase_addr_hi+3,Y
        sta tmphi
        rts

.macro copy_glyphs live
        jsr cloud_copy_pointers
        ldy #7
        .repeat 8, R
        lda (src),Y
        sta live+7-R,X
        lda (dst),Y
        sta live+15-R,X
        lda (world_ptr),Y
        sta live+23-R,X
        lda (tmplo),Y
        sta live+31-R,X
        .if R < 7
        dey
        .endif
        .endrepeat
        ldx cloud_slot
        rts
.endmacro
; Y = atlas entry, X = 32*slot: copy the slot's live glyphs from the atlas.
cloud_copy_first:
        copy_glyphs CLOUD_LIVE1
cloud_copy_second:
        copy_glyphs CLOUD_LIVE2

.segment "CODE"
cloud_profile_offset: .byte 0,32,64

; The top cloud's screen codes must reach the VIC just after its glyphs.
; Waiting for all lower cloud glyphs can miss this row's badline.
normal_cloud_patch_row:
        lda patch_any
        beq @done
        txa
        asl
        adc cloud_slot          ; X is the floor, so both shifts clear carry
        asl
        adc #CACHE_FLOOR_ROW
        tax
        lda PATCH_FLAG,X
        beq @restore
        jsr patch_one_row
@restore:
        ldx cloud_slot
@done:  rts

.segment "EXTRA"
; A = phase, X = original profile, Y = first live glyph. Every phase,
; including a column crossing, copies four already formed source glyphs.
cloud_glyph_update:
        pha
        jsr cloud_charset_pointer
        pla
        asl
        asl
        ora cloud_profile_offset,X
        tax
@tile:  lda normal_cloud_phase_codes,X
        tay
        lsr
        lsr
        lsr
        lsr
        lsr
        ora #>CHARSET           ; character bank starts on a 2KB boundary
        sta src+1
        tya
        asl
        asl
        asl
        sta src
        jsr cloud_copy_atlas_glyph
        lda dst
        clc
        adc #8                  ; four aligned glyphs never cross a page
        sta dst
        inx
        txa
        and #3
        bne @tile
        ldx cloud_slot
        rts

.segment "DATA"
; Bonus uses only stone and sky from the ordinary background. Reserve40
; unused glyphs for all eight exact five-role phases once at view_init.
; Moving clouds select their phase through character codes, so no visible
; charset bytes need to change during play.
bonus_cloud_glyph_cache_init:
        lda #7
        sta bonus_work_index
@phase:
        lda bonus_work_index
        asl
        asl
        clc
        adc bonus_work_index
        adc #BONUS_CLOUD_FIRST
        tay
        ldx #2
        lda bonus_work_index
        jsr cloud_generate_normal
        dec bonus_work_index
        bpl @phase
        rts

.segment "CODE"
; X is the one-based bonus cloud slot. Carry set means outside the
; cached 25-row viewport; positions and collision clocks still advance.
bonus_cloud_in_view:
        lda BONUS_CLOUD_CACHE_ROW-1,X
        sec
        sbc last_view_row
        cmp #25
        rts

normal_cloud_phase_codes:
        .incbin "../build/normal_cloud_phase_codes.bin"

.segment "EXTRA"
; Prepare the immutable atlas in unused character slots with DEN off.
; The four temporary glyphs are never used in the playfield.
normal_cloud_font_init:
        ldx #0
@phase: stx cloud_slot
        txa
        lsr
        lsr
        and #7
        pha
        txa
        .repeat 5
        lsr
        .endrep
        tax
        pla
        ldy #CLOUD_ATLAS_WORK
        jsr cloud_generate_normal
        lda #<(CHARSET+CLOUD_ATLAS_WORK*8)
        sta src
        lda #>(CHARSET+CLOUD_ATLAS_WORK*8)
        sta src+1
@tile:  ldy normal_cloud_phase_codes,X
        cpy #$FF
        beq @next
        jsr cloud_charset_pointer
        jsr cloud_copy_atlas_glyph
@next:  lda src
        clc
        adc #8
        sta src
        inx
        txa
        and #3
        bne @tile
        cpx #96
        bne @phase
        rts

; A=phase0..7, X=original profile, Y=first of four character glyphs.
; Shift the three original sprite masks as one24-bit row, retaining the
; fourth spill byte. This preserves all24x8 source pixels at every phase.
cloud_generate_normal:
        sta old_cloud_phase
        jsr cloud_charset_pointer
        lda cloud_mask_lo,X
        sta src
        lda cloud_mask_hi,X
        sta src+1
        ldy #0
@row:  lda (src),Y
        sta work_lo
        tya
        clc
        adc #8
        tay
        lda (src),Y
        sta work_hi
        sta cache_layer         ; unshifted FF for wide bonus middle tiles
        tya
        clc
        adc #8
        tay
        lda (src),Y
        sta work2
        tya
        sec
        sbc #16
        tay
        lda #0
        sta chartmp
        ldx old_cloud_phase
        beq @put
@shift:lsr work_lo
        ror work_hi
        ror work2
        ror chartmp
        dex
        bne @shift
@put:  lda work_lo
        sta (dst),Y
        tya
        clc
        adc #8
        tay
        lda work_hi
        sta (dst),Y
        tya
        clc
        adc #8
        tay
        lda state
        cmp #3
        bne @cap
        lda cache_layer
        ldx old_cloud_phase
        beq @repeat
@rotate:
        lsr
        bcc :+
        ora #$80
:       dex
        bne @rotate
@repeat:
        sta (dst),Y             ; fifth bonus role: repeated FF tile
        tya
        clc
        adc #8
        tay
@cap:  lda work2
        sta (dst),Y
        tya
        clc
        adc #8
        tay
        lda chartmp
        sta (dst),Y
        lda state
        cmp #3
        bne @normal_end
        tya
        sec
        sbc #31
        bne @row_end
@normal_end:
        tya
        sec
        sbc #23
@row_end:
        tay
        cpy #8
        jne @row
        ldx cloud_slot
        rts

cloud_charset_pointer:
        tya
        lsr
        lsr
        lsr
        lsr
        lsr
        clc
        adc #>CHARSET
        sta dst+1
        tya
        asl
        asl
        asl
        sta dst
        rts
cloud_mask_lo:
        .byte <original_cloud_masks,<(original_cloud_masks+24),<(original_cloud_masks+48)
cloud_mask_hi:
        .byte >original_cloud_masks,>(original_cloud_masks+24),>(original_cloud_masks+48)
original_cloud_masks:
        .incbin "../build/original_cloud_masks.bin"
.segment "CODE"
