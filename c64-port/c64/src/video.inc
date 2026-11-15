; VIC bank 1 keeps display RAM separate from the growing program/assets.
SCREEN  = $4000
CHARSET = $4800
SPRITES = $5000

.macro video_init
        sei
        cld
        ldx #$FF
        txs
        lda #$7F
        sta $DC0D
        sta $DD0D
        lda $DC0D
        lda $DD0D
        lda #$35                ; all RAM except I/O; assets and world cache
        sta $01
        lda #$00
        sta $D01A               ; raster IRQ off (polled frame loop)
        sta $D011               ; blank until graphics are ready
        sta $D015
        sta $D010
        sta $D017               ; no inherited sprite expansion/priority
        sta $D01B
        sta $D01C
        sta $D01D
        sta $D020
        sta $D021
        sta $DC02               ; joystick port 2 inputs
        sta $DC03
        ldx #0
@runtime:
        sta $0200,X
        sta $0300,X
        sta $0600,X
        sta $0700,X
        inx
        bne @runtime
        ldx #$7D                ; all game variables $02..$7F
@clear: sta $02,X
        dex
        bpl @clear
        lda $DD02
        ora #$03
        sta $DD02
        lda $DD00
        and #$FC
        ora #$02                ; VIC bank $4000-$7FFF
        sta $DD00
        lda #$02                ; screen $4000, charset $4800
        sta $D018
        lda #$08                ; hires, 40 columns, X scroll zero
        sta $D016
        lda #<@nmi
        sta $FFFA
        sta $FFFE
        lda #>@nmi
        sta $FFFB
        sta $FFFF
        jmp @ready
@nmi:   rti
@ready:
.endmacro

; Sprite source is PackBits: low 7 bits +1 is length; high bit repeats
; the following byte, otherwise the packet contains literal bytes.
; Shared by the game and the title demo. No ROM/KERNAL calls are used.
.macro unpack_blocks source_address, target_address, target_end
        lda #<source_address
        sta src
        lda #>source_address
        sta src+1
        lda #<target_address
        sta dst
        lda #>target_address
        sta dst+1
        ldy #0
@pair:  lda (src),Y
        inc src
        bne @control
        inc src+1
@control:
        cmp #$80
        bcs @repeat
        tax
        inx
@literal:
        lda (src),Y
        inc src
        bne @store
        inc src+1
@store: sta (dst),Y
        inc dst
        bne @literal_count
        inc dst+1
@literal_count:
        dex
        bne @literal
        jmp @more
@repeat:
        and #$7F
        tax
        inx
        lda (src),Y
        sta tmp
        inc src
        bne @run
        inc src+1
@run:   lda tmp
        sta (dst),Y
        inc dst
        bne @count
        inc dst+1
@count: dex
        bne @run
@more:  lda dst+1
        cmp #>(target_end)
        bne @pair
.endmacro

.macro load_sprites
        unpack_blocks sprites_src, SPRITES, SPRITES+SPRITE_PAGES*256
.endmacro
