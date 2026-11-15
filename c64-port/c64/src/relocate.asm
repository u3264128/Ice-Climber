; VIDEO is only a load buffer here; enter_title replaces it with the screen.
; Copy helpers before that, keeping the IRQ/NMI vectors and $FFF0 untouched.
.import __HELPERS_LOAD__, __HELPERS_RUN__, __HELPERS_SIZE__
.import __LOWCODE_LOAD__, __LOWCODE_RUN__, __LOWCODE_SIZE__
.import __IOCODE_LOAD__, __IOCODE_RUN__, __IOCODE_SIZE__
.import __IODATA_LOAD__, __IODATA_RUN__, __IODATA_SIZE__
.import __IOART_LOAD__
.import __STACKCODE_LOAD__, __STACKCODE_RUN__, __STACKCODE_SIZE__
.import __DEBRISART_LOAD__, __DEBRISART_RUN__
.import __IOMIDCODE_LOAD__, __IOMIDCODE_RUN__, __IOMIDCODE_SIZE__
.import __MUXCODE_LOAD__, __MUXCODE_RUN__, __MUXCODE_SIZE__
.import __PRIOCODE_LOAD__, __PRIOCODE_RUN__, __PRIOCODE_SIZE__
.segment "STARTUP"
install_helpers:
        lda #$34                ; the NES objects run from RAM under I/O
        sta $01
        lda #<__IOCODE_LOAD__
        sta src
        lda #>__IOCODE_LOAD__
        sta src+1
        lda #<__IOCODE_RUN__
        sta dst
        lda #>__IOCODE_RUN__
        sta dst+1
        ldx #>(__IOCODE_SIZE__+255)
        ldy #0
@io:    lda (src),Y
        sta (dst),Y
        iny
        bne @io
        inc src+1
        inc dst+1
        dex
        bne @io
        ldx #<__IODATA_SIZE__
@tables:
        lda __IODATA_LOAD__-1,X
        sta __IODATA_RUN__-1,X
        dex
        bne @tables
        ldx #64                 ; the debris art under I/O ($D000)
@debris:lda __DEBRISART_LOAD__-1,X
        sta __DEBRISART_RUN__-1,X
        dex
        bne @debris
        ldx #<__IOMIDCODE_SIZE__ ; and the condor restore ($D0D0)
@mid:   lda __IOMIDCODE_LOAD__-1,X
        sta __IOMIDCODE_RUN__-1,X
        dex
        bne @mid
        ldx #<__STACKCODE_SIZE__ ; the debris code in the lower stack page
@stack: lda __STACKCODE_LOAD__-1,X
        sta __STACKCODE_RUN__-1,X
        dex
        bne @stack
        ldx #0                  ; Topi pages 1-3: original ice and icicles
@art:   lda __IOART_LOAD__,X
        sta TOPI_SPECIAL_RAM+$100,X
        lda __IOART_LOAD__+$100,X
        sta TOPI_SPECIAL_RAM+$200,X
        lda __IOART_LOAD__+$200,X
        sta TOPI_SPECIAL_LAST,X
        inx
        bne @art
        lda #$35
        sta $01
        ldx #<__PRIOCODE_SIZE__
@priority:
        lda __PRIOCODE_LOAD__-1,X
        sta __PRIOCODE_RUN__-1,X
        dex
        bne @priority
        ldx #<__LOWCODE_SIZE__  ; $0740-$07FF: page 7 above the event table
@low:   lda __LOWCODE_LOAD__-1,X
        sta __LOWCODE_RUN__-1,X
        dex
        bne @low
        ldx #<__MUXCODE_SIZE__  ; the multiplexer's overload choices ($E984)
@mux:   lda __MUXCODE_LOAD__-1,X
        sta __MUXCODE_RUN__-1,X
        dex
        bne @mux
        lda #<__HELPERS_LOAD__
        sta src
        lda #>__HELPERS_LOAD__
        sta src+1
        lda #<__HELPERS_RUN__
        sta dst
        lda #>__HELPERS_RUN__
        sta dst+1
        ldy #0
@check: lda dst+1
        cmp #>(__HELPERS_RUN__+__HELPERS_SIZE__)
        bne @byte
        lda dst
        cmp #<(__HELPERS_RUN__+__HELPERS_SIZE__)
        beq @done
@byte:  lda (src),Y
        sta (dst),Y
        inc src
        bne @destination
        inc src+1
@destination:
        inc dst
        bne @check
        inc dst+1
        jmp @check
@done:  rts
.segment "CODE"
.segment "IOART"
        .incbin "../build/nes_ice_art.bin"
.segment "DEBRISART"
debris_art:
        .incbin "../build/debris_art.bin"
.segment "CODE"
