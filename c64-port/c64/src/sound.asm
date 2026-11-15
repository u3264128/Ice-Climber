; ---------------------------------------------------------------------------
; Sound: the original NES sound engine, with the NES APU emulated on the SID
; ---------------------------------------------------------------------------
; The original engine ($F91E, transplanted into build/nes_sound.inc) runs 60
; times a second as on the NES, in the main loop (sound_frame: six ticks in
; five PAL frames). The game requests sounds as the original does, by
; storing into snd_music_req ($FB), snd_sfx1_req ($FC, noise), snd_sfx2_req
; ($FE, pulse 2) and snd_sfx3_req ($FF, pulse 1 and the triangle); the
; transplanted object code stores into the same bytes.
;
; The engine only writes APU registers (snd_apu). The parts of the 2A03 it
; uses are emulated here, in the order of its frame counter, which $F91E
; resets every NMI ($4017 = $FF: the reset clocks a quarter and a half frame
; at once, then quarter frames follow at 1/4, 2/4 and 3/4 of the frame and
; a half frame at 2/4):
;
;   the engine's writes, a quarter frame, the SID update, then two more
;   quarter frames and a half frame, and the next NMI's quarter and half
;   frame.
;
; This costs more than the engine, so it runs in the frame's spare time
; (sound_idle, from wait_frame) for all the ticks since the last update
; (apu_batch); one tick at a time it is exactly the above.
;
; Envelopes, sweeps and the linear counter follow the 2A03; the length
; counters are left out (the engine loads 254 or holds them, and each of its
; sounds reaches volume 0 before one would end it). A channel's NES volume
; becomes its SID voice's sustain level (attack, decay and release 0, which
; also keeps the SID's ADSR delay away from note starts; a louder value
; starts the voice again, since the SID sustain only falls), periods become
; SID frequencies:
;
;   pulse 2 (melody, effects $FAC4)   -> SID voice 1
;   pulse 1 (harmony, effects $F9EB)  -> SID voice 2
;   triangle (bass, the bear's jump)  -> SID voice 3
;   noise (blocks, game over: $FBA1)  -> voice 2, or voice 3 when pulse 1
;                                        sounds as the noise starts
;
; The $4011 DAC ramp is not emulated (it only lowers the triangle and noise
; level slightly during the logo music).

; Original music requests ($FB) and sound effects.
MUSIC_PREVIEW = $01
MUSIC_BACKGROUND = $02
MUSIC_LOGO = $04
MUSIC_COMPLETE = $10
MUSIC_PAUSE = $20
MUSIC_UNPAUSE = $40
MUSIC_OFF = $80
SFX3_DEATH = $01                ; $D45E: an object touched the climber
SFX3_JUMP = $04                 ; $CE58
SFX2_TICK = $08                 ; $EA31 the tally, $F55A the mountain number
SFX2_FRUIT = $10                ; $D3A7
SFX1_GAME_OVER = $01            ; $ED10
SFX1_BLOCK = $02                ; $DDA9: a block breaks
SFX1_BUMP = $04                 ; $DDE6: the mallet hits outside the floor

; K/x: the SID frequency of an NES pulse period x-1 (also K/p for the noise
; period p): NTSC CPU clock * 2^20 / PAL CPU clock.
SND_K = 1904811

.segment "DATA"
.include "../build/nes_sound.inc"

.segment "CODE"
; Once per PAL frame (main loop): the engine, six ticks in five frames (60
; Hz, so the music keeps its time; it costs little). The APU and the SID
; follow in the frame's spare time (sound_idle) for all the ticks since,
; or here once SOUND_FORCED ticks have waited.
sound_frame:
        inc snd_quiet
        dec snd_phase
        bpl @one
        lda #4
        sta snd_phase
        jsr sound_engine        ; the sixth tick
        inc snd_debt
@one:   jsr sound_engine
        inc snd_debt
        lda snd_debt
        cmp #SOUND_FORCED
        bcc :+
        lda #$80                ; forced: the SID only after three quiet frames
        sta snd_hurry
        jmp apu_batch
:       rts

; wait_frame: the APU and the SID for the ticks since the last update, when
; the beam is above line SOUND_LAST_LINE (an update takes about 15 lines
; with the raster IRQs; one that runs past line 250 commits in wait_frame's
; late window), or the update is still in its commit's own border.
sound_idle:
        lda snd_debt
        bne :+
@done:  rts
:       lda frame_ticks
        sec
        sbc commit_ticks
        beq @run                ; a whole frame ahead
        cmp #1
        bne @done               ; late
        bit $D011
        bmi @done               ; lower border: the commit is due
        lda RASTER
        cmp #FRAME_IRQ_LINE
        bcc @done               ; the top border of a later frame: late
        cmp #SOUND_LAST_LINE
        bcs @done
        lda #$40                ; the SID while the beam leaves time
        .byte $2C               ; (BIT skips the next two bytes)
@run:   lda #0                  ; a whole frame ahead: the SID too
        sta snd_hurry           ; (on into apu_batch)

; The APU for the snd_debt engine ticks since the last batch: their writes,
; 4n-3 quarter frames and 2n-2 half frames, the SID update, three more
; quarter frames and two half frames. One tick is exactly the 2A03's: its writes, a quarter frame, the
; update (as $F91E resets the frame counter every NMI: the rest of the frame
; and the next NMI's reset follow). Several (spare time came late) take
; their writes together.
apu_batch:
        lda snd_debt
        asl
        asl
        sec
        sbc #3
        sta snd_q
        jsr apu_clocks          ; (all the quarter frames)
@early: dec snd_debt            ; the half frames of the ticks before the
        beq @last               ; last come before the SID update
        jsr apu_sweeps
        bne @early              ; (always: X ends at $FF)
@last:  bit snd_hurry           ; 0: the SID now; $40 (spare time): while the
        bmi @forced             ; beam leaves time; $80: see sound_frame
        bvc @update
        bit $D011
        bmi apu_sweeps
        lda RASTER
        cmp #SOUND_OUT_LINE
        bcs apu_sweeps
        bcc @update
@forced:
        lda snd_quiet
        cmp #3
        bcc apu_sweeps
@update:
        lda #0
        sta snd_quiet
        jsr apu_output          ; then the last tick's half frames

apu_sweeps:                     ; a tick's two half frames
        ldx #1
@sweep: lda snd_sw_reload,X
        bne @slow
        lda snd_sw_div,X        ; a running divider at 2 or more: it only
        cmp #2                  ; counts down
        bcc @slow
        sbc #2
        sta snd_sw_div,X
        bcs @next
@slow:  jsr sweep_clock
        jsr sweep_clock
@next:  dex
        bpl @sweep
        rts

; The engine's writes, then snd_q quarter frames, the volumes the SID update
; uses, and three more. $4001/$4005 reload the sweep; $4003, $4007, $400B
; and $400F restart the envelope or reload the linear counter and leave the
; period's high bits. (The length counters are not emulated: the engine
; loads 254 or holds them, and every sound ends at volume 0 first.)
apu_clocks:
        lda snd_apu_w+1
        ora snd_apu_w+3
        ora snd_apu_w+5
        ora snd_apu_w+7
        ora snd_apu_w+11
        ora snd_apu_w+15
        beq @quarters
        ldx #3
@written:
        ldy snd_reg,X
        lda snd_apu_w+1,Y
        beq @load
        sta snd_sw_reload,X     ; (nonzero)
        lda #0
        sta snd_apu_w+1,Y
@load:  lda snd_apu_w+3,Y
        beq @later
        sta snd_start,X
        lda #0
        sta snd_apu_w+3,Y
        lda snd_apu+3,Y
        and #7
        sta snd_apu+3,Y
@later: dex
        bpl @written
@quarters:
        ldx #3
@channel:
        cpx #2
        beq @triangle
        ldy snd_reg,X
        lda snd_start,X
        bne @work
        lda snd_apu,Y           ; V, decay and divider 0: the envelope
        and #$0F                ; rests, silent
        ora snd_decay,X
        ora snd_div,X
        beq @rest
@work:  lda snd_q
        jsr env_run
        jsr env_level
        lda #3
        jsr env_run
        jmp @next
@rest:  sta snd_vol,X
@next:  dex
        bpl @channel
        rts
@triangle:                      ; the engine never sets the control bit:
        lda snd_linear          ; a reload lasts one quarter frame
        ldy snd_start+2
        beq @count
        ldy #0
        sty snd_start+2
        lda snd_apu+8
        and #$7F
        clc
        adc #1                  ; (the reload is the first quarter frame)
@count: sec
        sbc snd_q
        bcs :+
        lda #0
:       ldy #0                  ; full while the counter runs
        cmp #1
        bcc :+
        ldy #15
:       sty snd_vol+2
        sbc #3                  ; three more quarter frames (carry from cmp)
        bcs :+
        lda #0
:       sta snd_linear
        bpl @next               ; (always: below 128)

; X = pulse or noise, Y = its registers, A = quarter frames (1 or more): its
; envelope after them (a restart is the first). Each turn skips a divider's
; whole count and takes one step of the decay level.
env_run:
        sta snd_c
        lda snd_start,X
        beq @loop
        lda #0
        sta snd_start,X
        lda #15
        sta snd_decay,X
        lda snd_apu,Y
        and #15
        sta snd_div,X
        dec snd_c
        beq @done
@loop:  lda snd_div,X
        beq @step
        cmp snd_c
        bcs @only               ; the divider outlasts them
        eor #$FF                ; down to 0 first
        sec
        adc snd_c
        sta snd_c
@step:  jsr env_decay           ; at 0: a step, and V again
        lda snd_apu,Y
        and #15
        sta snd_div,X
        dec snd_c
        bne @loop
@done:  rts
@only:  sbc snd_c               ; (carry set)
        sta snd_div,X
        rts

.segment "EXTRA"
; X = pulse or noise, Y = its registers: the volume (constant, or the
; envelope's decay level).
env_level:
        lda snd_decay,X
        sta snd_vol,X
        lda snd_apu,Y
        and #$10
        beq :+
        lda snd_apu,Y
        and #15
        sta snd_vol,X
:       rts

.segment "HELPERS"
; X = pulse or noise: a step of the decay level. (The engine sets the loop
; flag only with constant volume, on sounds that end at volume 0 before the
; envelope is used again, so it is not emulated.)
env_decay:
        lda snd_decay,X
        beq :+
        dec snd_decay,X
:       rts
.segment "CODE"

; X = pulse: one half frame of its sweep unit.
sweep_clock:
        ldy snd_reg,X
        lda snd_sw_div,X
        bne @count
        lda snd_apu+1,Y
        bpl @reload             ; disabled
        and #7
        beq @reload             ; no shift
        jsr pulse_muted
        bcs @reload             ; muted: the period stays
        jsr sweep_target
        lda snd_t
        sta snd_apu+2,Y
        lda snd_t+1
        sta snd_apu+3,Y
@reload:
        lda snd_apu+1,Y
        lsr
        lsr
        lsr
        lsr
        and #7
        sta snd_sw_div,X
        lda #0
        sta snd_sw_reload,X
        rts
@count: lda snd_sw_reload,X
        bne @reload
        dec snd_sw_div,X
        rts

; X = pulse, Y = its registers (both kept): carry set when the channel is
; muted (period below 8; or, adding, a sweep target above $7FF, even with
; the sweep disabled). No sweep moves a muted period, so the last muted
; period and sweep register are remembered until the engine writes others.
pulse_muted:
        lda snd_apu+3,Y
        bne @wide
        lda snd_apu+2,Y
        cmp #8
        bcc @muted
        clc
        rts
@wide:  cmp #4
        bcc @heard              ; below $400 a target stays below $800
        lda snd_apu+1,Y
        and #8
        bne @free               ; negated: never above
        lda snd_apu+2,Y
        cmp snd_mute_lo,X
        bne @work
        lda snd_apu+3,Y
        cmp snd_mute_hi,X
        bne @work
        lda snd_apu+1,Y
        cmp snd_mute_r1,X
        beq @heard              ; (carry set: the same muted state)
@work:  jsr sweep_target
        bcc @heard
        lda snd_apu+2,Y
        sta snd_mute_lo,X
        lda snd_apu+3,Y
        sta snd_mute_hi,X
        lda snd_apu+1,Y
        sta snd_mute_r1,X
@muted: sec
        rts
@free:  clc
@heard: rts

; X = pulse, Y = its register offset (both kept). snd_t = the sweep target
; (period +/- period >> shift; pulse 1 negates with one more subtracted).
; Carry set when the target is above $7FF, which mutes the channel even
; with the sweep disabled.
sweep_target:
        lda snd_apu+2,Y
        sta snd_c
        lda snd_apu+3,Y
        sta snd_c+1
        lda snd_apu+1,Y
        and #7
        beq @shifted
        tay
@shift: lsr snd_c+1
        ror snd_c
        dey
        bne @shift
        ldy snd_reg,X
@shifted:
        lda snd_apu+1,Y
        and #8
        bne @negate
        lda snd_apu+2,Y
        clc
        adc snd_c
        sta snd_t
        lda snd_apu+3,Y
        adc snd_c+1
        sta snd_t+1
        cmp #8
        rts
@negate:
        cpx #1                  ; pulse 1: carry clear, one more
        lda snd_apu+2,Y
        sbc snd_c
        sta snd_t
        lda snd_apu+3,Y
        sbc snd_c+1
        sta snd_t+1
        clc
        rts

; The SID update: the pulses' muting (period below 8, sweep target above
; $7FF), the noise's voice, then the three voices.
apu_output:
        ldx #1
@mute:  lda snd_vol,X
        beq @next
        ldy snd_reg,X
        jsr pulse_muted
        bcc @next
        lda #0
        sta snd_vol,X
@next:  dex
        bpl @mute
        lda snd_vol+3
        bne :+
        sta snd_noise_voice     ; silent: both voices are free
        beq @voice1
:       lda snd_noise_voice
        bne @voice1             ; it keeps the voice it started on
        lda #7                  ; voice 2, or voice 3 while pulse 1 sounds
        ldx snd_vol
        beq :+
        lda #14
:       sta snd_noise_voice
@voice1:
        lda snd_vol+1           ; voice 1: pulse 2
        ldx #4
        ldy #0
        jsr pulse_out
        ldy #7                  ; voice 2: pulse 1 or the noise
        lda snd_noise_voice
        cmp #7
        beq @noise2
        lda snd_vol
        ldx #0
        jsr pulse_out
        jmp @voice3
@noise2:
        jsr noise_out
@voice3:
        ldy #14                 ; voice 3: the triangle or the noise
        lda snd_noise_voice
        cmp #14
        jeq noise_out
        lda snd_vol+2
        sta snd_v
        lda #$10
        jsr sid_level
        beq @done
        lda snd_apu+11
        ora #2<<3               ; (the source)
        sta snd_t+1
        lda snd_apu+10
        sta snd_t
        jsr sid_pitch_same
        beq @done
        lda snd_apu+10          ; x = 2*(period+1): one octave below a pulse
        sec
        adc #0
        sta snd_x
        lda snd_apu+11
        adc #0
        sta snd_x+1
        asl snd_x
        rol snd_x+1
        jmp voice_freq
@done:  rts

.segment "DATA"
; Y = voice: SND_K / snd_x into its frequency.
voice_freq:
        tya
        pha
        jsr freq_of
        pla
        tay
        lda snd_f
        sta SID+0,Y
        lda snd_f+1
        sta SID+1,Y
        rts

; A = level, X = the pulse's registers (0, 4), Y = its SID voice offset.
pulse_out:
        sta snd_v
        lda #$40
        jsr sid_level
        beq @done
        txa                     ; the source (pulse 1 or 2), the duty and
        asl                     ; the period
        asl
        asl
        ora snd_apu+3,X
        sta snd_t+1
        lda snd_apu,X
        and #$C0
        ora snd_t+1
        sta snd_t+1
        lda snd_apu+2,X
        sta snd_t
        jsr sid_pitch_same
        beq @done
        sty snd_u
        lda snd_apu,X           ; the pulse width
        rol
        rol
        rol
        and #3
        tay
        lda snd_duty,Y
        ldy snd_u
        sta SID+3,Y
        lda snd_apu+2,X
        sec
        adc #0
        sta snd_x
        lda snd_apu+3,X
        adc #0
        sta snd_x+1
        jmp voice_freq
@done:  rts

.segment "CODE"
SOUND_LAST_LINE = 232
SOUND_OUT_LINE = 240             ; the SID update starts before it
SOUND_FORCED = 6                ; ticks without the APU: run it now, spare time or not

.segment "HIGH"
noise_out:                      ; Y = voice
        lda snd_vol+3
        sta snd_v
        lda #$80
        jsr sid_level
        beq @done
        lda #3<<3
        sta snd_t+1
        lda snd_apu+14
        and #15
        sta snd_t
        jsr sid_pitch_same
        beq @done
        lda snd_t
        asl
        tax
        lda snd_noise_freq,X
        sta SID+0,Y
        lda snd_noise_freq+1,X
        sta SID+1,Y
@done:  rts

.segment "DATA"
; snd_f = SND_K / snd_x (30..4096; below 30 the SID's top), by linear
; interpolation in a 33-entry table of SND_K/(256+8j) after normalising x
; into 256..511 (the bits shifted out are kept as a fraction).
freq_of:
        lda #0
        sta snd_frac
        sta snd_shl
        sta snd_shr
        lda snd_x+1
        bne @wide
        lda snd_x
        cmp #30
        bcs @small
        lda #$FF
        sta snd_f
        sta snd_f+1
        rts
@small: ldy #0
:       iny
        asl
        bcc :-
        sty snd_shl
        sta snd_x
        jmp @norm
@wide:  cmp #2
        bcc @norm
        lsr snd_x+1
        ror snd_x
        ror snd_frac
        inc snd_shr
        lda snd_x+1
        jmp @wide
@norm:  lda snd_x               ; m = 256 + snd_x
        lsr
        lsr
        lsr
        tax                     ; j
        lda snd_frac
        lsr
        lsr
        lsr
        sta snd_u
        lda snd_x
        asl
        asl
        asl
        asl
        asl
        ora snd_u
        sta snd_u               ; the fraction between j and j+1, /256
        lda snd_freq_lo,X       ; the step to the next entry (below 256)
        sec
        sbc snd_freq_lo+1,X
        sta snd_c
        lda #0
        ldy #8
        lsr snd_u
@mul:   bcc :+
        clc
        adc snd_c
:       ror
        ror snd_u
        dey
        bne @mul
        sta snd_c               ; delta * fraction / 256
        lda snd_freq_lo,X
        sec
        sbc snd_c
        sta snd_f
        lda snd_freq_hi,X
        sbc #0
        sta snd_f+1
        ldy snd_shl
        beq @right
:       asl snd_f
        rol snd_f+1
        dey
        bne :-
        rts
@right: ldy snd_shr
        beq @done
:       lsr snd_f+1
        ror snd_f
        dey
        bne :-
@done:  rts

.segment "EXTRA"
snd_reg:     .byte 0, 4, 8, 12
.segment "HELPERS"
snd_duty:    .byte $02, $04, $08, $0C      ; 12.5, 25, 50, 75 % pulse width
.segment "DATA"
; Y = SID voice offset (0, 7, 14), A = waveform, snd_v = level (0: off):
; the gate and the sustain level, written only when they change. A louder
; level starts the voice again (the SID sustain only falls), as does
; another waveform. Y kept; Z set when the voice is off.
sid_level:
        sta snd_wave
        ora snd_v               ; the level and waveform as last set (kept
        cmp snd_sid+0,Y         ; in the frequency's unused shadow byte)
        beq @same
        sta snd_sid+0,Y
        lda snd_v
        beq @off
        asl
        asl
        asl
        asl
        sta snd_sr
        lda snd_sid+4,Y
        lsr
        bcc @start              ; not playing
        lda snd_sid+4,Y
        and #$F0
        cmp snd_wave
        bne @start              ; another channel's sound
        lda snd_sr
        cmp snd_sid+6,Y
        beq @on
        bcs @start              ; louder
        sta SID+6,Y
        sta snd_sid+6,Y
@on:    lda #1                  ; Z clear: playing
        rts
@start: lda snd_sid+4,Y
        and #$FE
        sta SID+4,Y             ; released, then started again
        lda snd_sr
        sta SID+6,Y
        sta snd_sid+6,Y
        lda snd_wave
        ora #1
        sta SID+4,Y
        sta snd_sid+4,Y
        rts
@same:  lda snd_v                 ; Z set when off
        rts
@off:   lda snd_sid+4,Y
        lsr
        bcc @silent
        asl
        sta SID+4,Y
        sta snd_sid+4,Y
@silent:
        lda #0                  ; Z set: off
        rts

; Y = voice, snd_t = the pitch signature (low byte; high bits, source and
; duty), kept in the voice's unused shadow bytes (pulse width low, AD): Z set
; when the voice already plays it, else it is remembered.
sid_pitch_same:
        lda snd_t+1
        cmp snd_sid+5,Y
        bne @new
        lda snd_t
        cmp snd_sid+2,Y
        beq @same
@new:   lda snd_t+1
        sta snd_sid+5,Y
        lda snd_t
        sta snd_sid+2,Y
        lda #1
@same:  rts

snd_freq_lo:                    ; SND_K/(256+8j), rounded (and j = 32 for
.repeat 33, J                   ; the last step)
        .byte <((SND_K + 128+4*J) / (256+8*J))
.endrepeat
snd_freq_hi:
.repeat 32, J
        .byte >((SND_K + 128+4*J) / (256+8*J))
.endrepeat
snd_noise_freq:                 ; SND_K/p for the 16 NTSC noise periods (the
        .word $FFFF, $FFFF, $FFFF        ; first three above the SID's top)
        .word (SND_K+16)/32, (SND_K+32)/64, (SND_K+48)/96, (SND_K+64)/128
        .word (SND_K+80)/160, (SND_K+101)/202, (SND_K+127)/254, (SND_K+190)/380
        .word (SND_K+254)/508, (SND_K+381)/762, (SND_K+508)/1016
        .word (SND_K+1017)/2034, (SND_K+2034)/4068

.segment "STARTUP"              ; only boot calls it
; The NES at reset: all sound RAM zero; the SID silent with
; attack, decay and release 0 on every voice and full volume.
sound_init:
        lda #$00
        ldx #24
:       sta SID,X
        dex
        bpl :-
        ldx #snd_vars_end-snd_vars-1
:       sta snd_vars,X
        dex
        bpl :-
        ldx #$13-$06            ; the engine's $F0-$FF (see nes_sound.inc)
:       sta $06,X
        dex
        bpl :-
        sta $15
        sta $3E
        ldx #9                  ; the envelopes and SID arguments ($80-$89,
:       sta snd_div,X           ; $98-$9C)
        dex
        bpl :-
        ldx #4
:       sta snd_vol,X
        dex
        bpl :-
        lda #$0F
        sta SID+$18
        rts

.segment "CODE"
