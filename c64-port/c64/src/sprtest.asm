; Minimal sprite check: solid 24x21 hires block, white on black.
; Use this to isolate sprite setup problems from demo.asm.
;

.segment "LOADADDR"
        .byte <$0801, >$0801

.segment "BASIC"
        .byte $0C,$08,$0A,$00,$9E,$20,$32,$30,$36,$32,$00,$00,$00

.segment "CODE"
start:
        sei
        lda #$00
        sta $D020
        sta $D021
        lda #$3A                ; Screen $0C00, charset $2800 (as in the demo)
        sta $D018

        ; Sprite 0 data: solid block at $3000
        ldx #$00
        lda #$FF
@f:     sta $3000,X
        sta $3080,X             ; Frame 2 uses the same data
        inx
        cpx #$3F
        bne @f

        lda #$C0
        sta $0FF8               ; Sprite pointer -> $3000
        lda #$01
        sta $D015               ; Enable sprite 0
        lda #$01
        sta $D027               ; White
        lda #100
        sta $D000               ; X
        lda #100
        sta $D001               ; Y

loop:   jmp loop
