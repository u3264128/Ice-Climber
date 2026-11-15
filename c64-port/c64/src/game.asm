.include "branches.inc"
; Ice Climber C64: 32 NES maps, shared-camera Popo/Nana, original bonus
; ledges/clouds, fruit/condor tally, Topi/Nitpicker/bear/falling ice.
; W/A/D + SPACE; I/J/L + right SHIFT; joystick ports 2 and 1; P pauses.
; PAL rendering at 50 Hz, six original physics ticks per five frames.
; Readonly code/assets are separate from mutable maps, video and IRQ packets.

; --- Zero-page variables ----------------------------------------------------
src     = $02
dst     = $04
; $06-$13 and $15: the original sound engine's $F0-$FF (nes_sound_symbols.inc)
frame   = $14
tmp     = $16
joy     = $17           ; Raw $DC00 input (active low)
state   = $18           ; 0=title, 1=game, 2=results
lives   = $19
curfloor= $1A           ; World floor (0=ground .. 8=summit)
onground= $1B
vy      = $1C           ; Signed vertical velocity
prevpy  = $1D
pxlo    = $1E           ; Sprite X (16-bit VIC coordinate)
pxhi    = $1F
epxlo   = $20           ; Enemy X (always < 256)
edir    = $21           ; 0=left, 1=right
py      = $22           ; sprite-Y
pleft   = $23           ; Character column under the left edge
pright  = $24           ; Character column under the right edge
score_lo= $25           ; BCD score
score_hi= $26
attrlo  = $27           ; Title attract counter
attrhi  = $28
joyprev = $29
firehit = $2A           ; 1 on the frame fire is pressed
face    = $2B           ; 0=right (frame A), 1=left (mirrored frame B)
maxfloor= $2C
rowidx  = $2D           ; Scratch floor index
coltmp  = $2E           ; Scratch column
chartmp = $2F
supflag = $30
scrptr  = $31           ; Screen pointer (2 bytes)
colptr  = $33           ; Colour pointer (2 bytes)
loopidx = $35
broke   = $36
tmplo   = $37
tmphi   = $38
ceilpy  = $39
cam     = $3A           ; Lowest visible world floor (0..5)
slot    = $3B           ; Player screen floor = curfloor - cam
e2pxlo  = $3C           ; Second enemy X
e2dir   = $3D
; $3E: sound engine $FF (snd_sfx3_req); $3F: event priority scratch
wrld    = $40           ; Scratch world floor
colw    = $41           ; Scratch column for bit operations
gapw    = $42
byteidx = $43
bitv    = $44
mountain= $46           ; Mountain number (difficulty and colour cycle)
icecol  = $47           ; Current mountain ice colour
levelidx= $48           ; NES mountain index 0..31
hammer_t= $49           ; original walking pose clock (r6C*2+r60),0..7
animidx = $4A
attack_t= $4B           ; Fire/Space: horizontal hammer swing
e_stun  = $4C           ; Topi/bird: brief pause after hammer hit
b_stun  = $4D
; $4F is reserved for the VICE test input latch.
score_top=$51           ; high two digits of six-digit BCD score
air_init= $52
fall_int= $53           ; NES $E6: unsigned accumulated gravity
fall_frac=$54           ; NES $E8
y_frac  = $55           ; NES $EA
rise_int= $56           ; NES $E4: upward velocity bias
rise_frac=$57           ; NES $E2
move_dir= $58           ; 0=stopped, 1=right, 2=left (latched in the air)
walk_time=$59           ; NES $6E, capped at 24
walk_frac=$5A           ; NES $76
air_xfrac=$5B           ; NES $72
skid_t  = $5C
logic_phase=$5D         ; 6 NES logic steps per 5 PAL frames
logic_frame=$5E
packed  = $60
break_layer=$61         ; 0=upper ice, 1=lower ice
blocked = $62
support_offset=$63      ; normal floor support remains at the upper surface
land_target=$64
cloud_slot=$65
cloud_delta=$66
map_index=$67
flow_frac=$68
invul_t = $69
respawn_count=$6A
respawn_col=$6B
t_state = $6C           ; Topi: 0 patrol,1 fetch,2 push,3 place,4 stunned,5 falling
t_target= $6D           ; repair column, or the original stunned movement speed
t_wait  = $6E           ; repair delay, or original stunned animation phase
t_floor = $6F           ; active world floor (cloud floors are skipped)
floor_upper=$0400       ; 9 x 24 cells: 0 air, 1/2 breakable ice, 3 stone
floor_lower=$0500
floor_types=$0600       ; 9 floor descriptors (7 from the ROM, ground/top=0)
SCORE_COUNTS=$0240      ; per-player five original result categories
GROUND_SWING=$024A      ; independent original ground-B attack handlers
cloud_x = $0610         ; software clouds in character columns
cloud_frac=$0620
cloud_dir=$0630
WORLD_TOP = 8
VISIBLE_FLOORS = 4
FLOOR_STEP = 48
MAX_CAM = WORLD_TOP - VISIBLE_FLOORS + 1

.include "runtime.inc"
.include "../build/nes_symbols.inc"
.include "../build/nes_sound_symbols.inc"
; Sound (sound.asm) in zero page that BASIC used: the envelopes and the SID
; arguments, the most used of its variables.
snd_div         = $80           ; envelope dividers (4)
snd_decay       = $84           ; envelope decay levels (4)
snd_v           = $88           ; sid_voice: level
snd_wave        = $89           ; sid_voice: waveform
snd_vol         = $98           ; each channel's volume at the SID update (4)
snd_sr          = $9C           ; sid_voice: sustain/release

; --- VIC-II / SID -------------------------------------------------------------
SPR0X   = $D000
SPR0Y   = $D001
VMCSB   = $D018
SPRENA  = $D015
SPRMC   = $D01C
SPRMC1  = $D025
SPRMC2  = $D026
SPRCOL0 = $D027
RASTER  = $D012
SID     = $D400
GAME_CHARSET = $02      ; $D018 charset bits: CHARSET $4800 in VIC bank 1
EXTRA_TICK_LATEST = 56  ; 2p sixth tick, up to 8 sprites: latest start line
EXTRA_TICK_MARGIN = 16   ; 1p sixth tick: half lines left beyond tick + sprites
FRAME_IRQ_LINE = 12     ; eight sprite writes finish before partially visibleY35

.include "video.inc"
.include "../build/sprite_frames.inc"
.include "../build/debris_blocks.inc"
.include "../build/terrain_tiles.inc"

ICE     = 218           ; Dedicated terrain glyphs after the NES charset
WALL_L  = 219
WALL_R  = 220
WATER   = 221
GROUND  = 222
ICE_LOW = 223
STONE   = 224
CLOUD   = 225
ICE_CHIP= 226
ICE_LOW_CHIP=227
BLANK   = 255           ; blank in both gameplay font banks

TBL_PULSE = 29
TBL_TRI   = 93

.segment "LOADADDR"
        .byte <$0801, >$0801

.segment "BASIC"
; 10 SYS 2062
        .byte $0C,$08,$0A,$00,$9E,$20,$32,$30,$36,$32,$00,$00,$00

.segment "CODE"
code_begin:
.segment "DATA"
assets_begin:           ; every readonly DATA byte, including helper tables
.segment "CODE"

; ---------------------------------------------------------------------------
start:
        jmp boot                ; one-time setup runs from the load buffer
start_main:
        jsr enter_title

; --- Main loop ---------------------------------------------------------------
main_loop:
        jsr wait_frame
        jsr commit_view         ; lower border: buffer swap and split values
        jsr commit_actors       ; re-arms the frame IRQ (FRAME_IRQ_LINE)
        jsr commit_colours      ; races the beam from the top
        jsr commit_patches      ; changed cells and cloud glyphs
        inc frame
        jsr read_joy
        lda state
        bne @notitle
        jsr title_tick
        jmp @music
@notitle:
        cmp #$02
        bne @game
        jsr win_tick
        jmp @music
@game:  ldx normal_pan_t
        stx pan_step_frame
        bne @pan                ; (no sixth tick during a pan)
        jsr beam_half
        sta beam_mark
        jsr scene_tick
        jsr beam_since          ; the sixth tick will take about as long
        sta tick_len
        jmp @phase
@pan:   jsr scene_tick
@phase: inc logic_phase
        lda logic_phase
        cmp #5
        bcc @music
        lda #0
        sta logic_phase
        sta firehit             ; a key edge must not trigger twice
        sta tick_debt           ; a direct sixth tick cancels older debt
        lda state
        cmp #4                  ; the flyover: one tick per frame, so the
        beq @music              ; mountain scrolls a constant 2 pixels
        cmp #1
        bne :+
        lda normal_pan_t
        ora pan_step_frame      ; one frozen 4px step per shown PAL frame
        bne @music
:       lda player_count        ; 60 Hz gameplay on the 50 Hz PAL C64
        cmp #2
        bne @sixth
        lda #1                  ; two climbers: see extra_tick
        sta tick_debt
        bne @music
@sixth: lda fixed_ticks         ; one climber: the sixth tick runs where the
        bne @direct             ; frame has time for it (extra_tick), or not
        inc tick_debt           ; at all: a slowdown instead of a missed frame
        bne @music
@direct:
        lda state
        cmp scene_before
        bne @music
        jsr scene_tick
@music: jsr sound_frame         ; the original engine's ticks fall due, also
                                ; while paused
@render:
        jsr view_tick
        jsr extra_tick
@actors:
        jsr beam_half
        sta beam_mark
        jsr actors_prepare
        jsr beam_since
        sta rest_len
        lda input_joy
        sta joyprev
        jmp main_loop

; A = half lines since beam_mark (within one frame).
.segment "DATA"
beam_since:
        jsr beam_half
        sec
        sbc beam_mark
        bcs :+
        adc #156
:       rts
.segment "CODE"

; Two climbers make a logic tick twice as long, so their sixth tick of five
; frames runs only in a frame that committed on time (line 250: the raster
; then tells how much is left), without scroll copying or colour swap; while
; the camera keeps scrolling, that tick is skipped (slowdown, no stutter).
; Sprites then use the camera the extra tick left behind.
; Returns carry set when it ran.
extra_tick:
        lda tick_debt
        beq @done
        lda chunk_frame
        ora colour_frame
        ora late_commit         ; a late update has no time to spare
        bne @done
        ldx logical_count       ; a crowded sprite list still has to be scheduled
        lda player_count
        cmp #2
        beq @two
        lda frame_ticks         ; one climber: before this display's frame IRQ
        sec                     ; (the commit's own border) the whole frame is
        sbc commit_ticks        ; left; after it, up to the latest start line
        beq @time
        lda $D011
        bmi @done
        jsr beam_half           ; half lines to line 6 of the next frame
        eor #$FF                ; (the last late commit): 159 - A
        clc
        adc #160
        sec
        sbc tick_len            ; the first tick of this frame
        bcc @done
        sbc rest_len            ; the last frame's sprites
        bcc @done
        cmp #EXTRA_TICK_MARGIN
        bcs @time
        bcc @done
@two:   cpx #9
        bcs @done               ; including when the beam is in the lower border
        lda $D011               ; and only with time left: lines 251..311,
        bmi @time               ; or early in the frame when the sprites
        lda RASTER              ; need no multiplexing (two climbers with
        cmp #251                ; 9+ sprites never fit two ticks: the game
        bcs @time               ; then runs at 50 ticks/s, without stutter)
        cmp #EXTRA_TICK_LATEST
        bcs @done
@time:  lda #0
        sta tick_debt
        lda state
        cmp #1
        beq @game
        cmp #3
        bne @done
@game:  cmp scene_before
        bne @done
        jsr game_tick
        jsr camera_target
        sec
        rts
@done:  clc
        rts

.include "title.asm"
.include "players.asm"

; --- tilstander ---------------------------------------------------------------
enter_title:
        sei
        lda #0
        sta $D01A
        sta bonus_requested
        lda #2
        sta $D018
        lda #$00
        sta $D011
        sta $D020
        sta SPRENA              ; Disable sprites on the title screen
        sta state
        sta attrlo
        sta attrhi
        sta hammer_t
        sta attack_t
        jsr title_reset
        lda #$FF
        sta title_previous
        jsr topi_sprite_scene
        lda #$18                ; Mixed hires/MC for the logo and menu
        sta $D016
        lda #$01
        sta $D022
        lda #$0E
        sta $D023
        jsr unpack_title_font
        ; Title screen -> SCREEN
        jsr unpack_title_screen
        ; Colours -> $D800
        jsr unpack_title_colours
        lda #MUSIC_LOGO         ; original $C1CE
        sta snd_music_req
        jsr title_menu
        lda #$1B
        sta $D011
        rts

title_tick:
        jsr title_code_tick
        bcs @timer
        lda joy
        eor #$FF
        and joyprev
        and #3
        beq @timer
        lsr
        lda #0
        bcs :+
        lda #1
:       sta game_mode
        jsr title_menu
        lda #0
        sta attrlo
        sta attrhi
@timer: inc attrlo
        bne @start
        inc attrhi
@start: lda input_fire
        ora input_fire+1
        bne @go
        lda attrhi
        cmp #>1173
        bcc @done
        lda attrlo
        cmp #<1173
        bcc @done
        jmp demo_start
@go:    jmp start_game
@done:  rts

start_game:
        lda #$00
        sta $D011
        lda #$18                ; mixed hires clouds and multicolour terrain
        sta $D016
        lda #$03
        sta lives
        lda selected_mountain
        sta mountain
        lda #1
        sta new_game
        lda #$00
        sta score_lo
        sta score_hi
        sta score_top
        sta score_mil
        sta extra_life_given
        sta extra_life_given+1
        sta phase_counter
        sta completed_mountains
        lda #$01
        sta state
        jsr setup_level
        jsr preview_init
        jsr preview_cache_init
        lda #MUSIC_PREVIEW      ; original $C4A9
        sta snd_music_req
        rts

setup_level:
        sei
        jsr normal_player_art
        lda #0
        sta $D011
        sta $D01A
        sta $D015
        lda game_mode
        clc
        adc #1
        sta player_count
        jsr view_init
        jsr score_counts_reset  ; new mountain; deaths keep its event counters
        ; Ice colour cycles through four themes
        lda mountain
        sec
        sbc #$01
        and #$03
        tax
        lda ice_cols,X
        sta icecol
        lda #$00
        sta cam                 ; Camera starts at the bottom of the mountain (0..5)
        sta normal_pan_t
        sta normal_pan_request
        sta normal_camera
        sta normal_camera+1
        sta normal_pan_high
        sta normal_pan_high+1
        sta normal_pan_dead
        sta normal_pan_dead+1
        jsr init_floors         ; Decode the selected NES mountain
        jsr draw_level
        ; Start the player on the ground within the NES playfield
        lda #100
        sta pxlo
        lda #$00
        sta pxhi
        sta face
        sta maxfloor
        sta hammer_t
        sta attack_t
        sta e_stun
        sta b_stun
        sta air_init
        sta move_dir
        sta walk_time
        sta walk_frac
        sta air_xfrac
        sta skid_t
        sta flow_frac
        sta invul_t
        lda #216                ; land_py[0]
        sta py
        lda #$00
        sta curfloor
        lda #$01
        sta onground
        lda #$00
        sta vy
        jsr players_setup
        jsr environment_init    ; also the original NES objects
        jsr actors_reset
        rts

.segment "STACKCODE"
enter_win:
        lda #1
        sta bonus_requested
        rts
.segment "CODE"
.segment "EXTRA"
win_tick:
        jmp results_tick
.segment "CODE"

; The displayed32-mountain cycle follows the original99-stage counter.
next_mountain:
        jsr original_advance_mountain
@valid:
        lda #$00
        sta $D020
        lda #1
        sta state
        jsr setup_level
        lda #$01
        sta state
        lda #MUSIC_BACKGROUND   ; original $C2A0
        sta snd_music_req
        rts

; A climber below the screen ($D463: no sound) loses a life.
player_died:
        dec lives               ; original lives are spare climbers: 0 is the
        bpl @respawn            ; last one; negative is out ($EB8E: BMI)
        lda #SFX1_GAME_OVER     ; $ED10: this climber is out
        sta snd_sfx1_req
        lda player_count
        cmp #2
        beq @done
        jmp @over
@respawn:
        jsr respawn_player      ; keep broken ice and the reached floor
        rts
@over:  jsr enter_game_over
@done:  rts

respawn_player:
        lda #0
        ldx player_index
        sta GROUND_SWING,X
        sta PLAYER_LAND_AGE,X
        lda #1                  ; original EB8A retains the current viewport
        sta respawn_keep_camera
        lda cam
        clc
        adc #2                  ; EB8A visible clamp of D1F9 physical death floor
        sta wrld
        lda normal_pan_high,X
        bne @bottom             ; wrapped logical Y still means bottom-band death
        lda py
        cmp #122
        bcc @clouds
        dec wrld
        cmp #170
        bcc @clouds
@bottom:
        lda cam
        sta wrld
@clouds:
        jsr respawn_visible_cloud_mask
        sta work_hi
@floor: lda wrld
        sec
        sbc cam
        tax
        lda respawn_floor_bits,X
        and work_hi
        beq @scan               ; EBD3 skips only the two active cloud slots
        lda wrld
        cmp cam
        bne @down
        clc
        adc #3                  ; cycle through the three visible floor choices
        sta wrld
@down:  dec wrld
        jmp @floor
@scan:  lda pxlo
        sec
        sbc #44                 ; source body X+8, modulo the 256-pixel world
        sta respawn_col
@cell:  jsr respawn_upper_probe  ; DEB9 accepts raw0/1/2/4, rejects FF and raw3
        bne @found
        lda respawn_col
        clc
        adc #8                  ; EBFE scans right without changing floors
        sta respawn_col
        cmp #224
        bcc @cell
@found: lda #0
        sta support_offset
@position:
        lda wrld
        sta curfloor
@keep_camera:
        lda wrld
        cmp maxfloor
        bcc @slot
        sta maxfloor
@slot:  jsr compute_slot
        ldx slot
        lda land_py,X
        clc
        adc support_offset
        sta py
        lda #0
        sta pxhi
        sta vy
        sta air_init
        sta move_dir
        sta walk_time
        sta skid_t
        sta hammer_t
        sta attack_t
        ldx player_index
        sta normal_pan_high,X   ; this ninth bit belonged to the pre-respawn body
        lda respawn_col
        sec
        sbc #8                  ; retain the original body's X modulo8
        clc
        adc #52
        sta pxlo
        bcc @ready
        inc pxhi
@ready: lda #1
        sta onground
        lda #120
        sta invul_t
        ; Full world cache remains valid when the camera moves.
        rts

        .include "respawn.asm"

; --- NES terrain: two independent block planes -------------------------------
land_py:
        .byte 216, 168, 120, 72
ice_cols:
        .byte $0E, $03, $0D, $07
.segment "DATA"
floor_offsets:
        .byte 0,24,48,72,96,120,144,168,192
.segment "DATA"
.include "../build/nes_level_offsets.inc"

init_floors:
        lda mountain
        sec
        sbc #1
        and #31
        sta levelidx
        tax
        lda level_ptr_lo,X
        sta src
        lda level_ptr_hi,X
        sta src+1
        ; The view cache is disposable while setup_level masks the screen.
        lda #<WORLD_CACHE
        sta dst
        lda #>WORLD_CACHE
        sta dst+1
        lda #>(WORLD_CACHE+$100)
        sta work2
        jsr unpack_asset_data
        lda #<WORLD_CACHE
        sta src
        lda #>WORLD_CACHE
        sta src+1
        ldx #0
        ldy #0
@upper:
        lda (src),Y
        sta packed
        .repeat 4
        lda packed
        and #3
        sta floor_upper,X
        lsr packed
        lsr packed
        inx
        .endrep
        iny
        cpy #54
        bne @upper
        ldx #0
@lower:
        lda (src),Y
        sta packed
        .repeat 4
        lda packed
        and #3
        sta floor_lower,X
        lsr packed
        lsr packed
        inx
        .endrep
        iny
        cpy #108
        bne @lower
        ; Seven per-floor descriptors, in the same order as NES $E382.
        lda levelidx
        asl
        asl
        asl
        sec
        sbc levelidx
        tax
        ldy #1
@types:
        lda level_types_src,X
        sta floor_types,Y
        inx
        iny
        cpy #8
        bne @types
        lda #0
        sta floor_types
        sta floor_types+8
        jmp normal_cloud_init

.segment "CODE"
; (wrld, colw) -> X=cell index, carry clear if inside the original 24x9 map.
cell_index:
        lda wrld
        cmp #9
        bcs @invalid
        tax
        lda colw
        cmp #8
        bcc @invalid
        cmp #32
        bcs @invalid
        sec
        sbc #8
        clc
        adc floor_offsets,X
        tax
        clc
        rts
@invalid:
        sec
        rts

upper_tiles:
        .byte BLANK,ICE,STONE,STONE ; tag2 retains original raw4 stone-post rule
lower_tiles:
        .byte BLANK,ICE_LOW,ICE_LOW_CHIP,STONE
terrain_color:
        cmp #BLANK
        beq @black
        ; NES floors 1-5 use yellow highlights; the snowy upper third is
        ; white. The two shared shades change at matching raster lines.
        lda #15
        ldx wrld
        cpx #5
        bcc @done
        bne @snow
        ldx cache_layer         ; floor5 lower row31 is still brown
        bne @done
@snow:
        lda #9
@done:
        rts
@black: lda blank_colour
        rts

draw_level:
        jmp cache_normal
get_char:
        jmp world_get_char
set_char:
        rts

solid_char:
        cmp #ICE
        beq @yes
        cmp #ICE_LOW
        bcc @no
        cmp #ICE_LOW_CHIP+1
        bcs @no
@yes:   sec
        rts
@no:    clc
        rts

; A=screen floor -> supflag 0/1/2 (none/terrain/cloud), support_offset=0.
; Original CD62 tests only the upper plane. The lower plane is a breakable
; underside, never an additional standing surface eight pixels below it.
support_at:
        cmp #VISIBLE_FLOORS
        jcs @no
        sta rowidx
        jsr compute_feet_columns ; NES $CD62 probes X+6 and X+9 only
        lda #0
        sta break_layer
        sta support_offset
        lda rowidx
        clc
        adc cam
        sta wrld
        cmp #9
        bcs @no                 ; outside the map: blank, no cloud
        tax
        lda floor_offsets,X
        sec
        sbc #8
        sta support_base        ; cell = base + column, columns 8..31
        lda pleft
        jsr support_wall_column
        bcs @terrain            ; DBB4 rejects walls before looking for a cloud
        ldx wrld
        lda floor_types,X
        and #$E0
        cmp #$60
        bcc @left_cell
        jsr normal_cloud_contact ; original first-foot query records cloud carry
        bcs @cloud
@left_cell:
        lda pleft
        clc
        adc support_base
        tay
        jsr support_upper_y
        bne @terrain
        lda pright
        jsr support_wall_column
        bcs @terrain
        lda pright
        clc
        adc support_base
        tax
        jsr support_upper_x
        bne @terrain
        jmp @no
@cloud: lda #2
        bne @found
@terrain:
        lda #1
@found: sta supflag
        rts
@no:    lda #0
        sta supflag
        rts

; Original raised mallet: $D17C positions it at NES X+0/+8; $DA99
; samples its centre and adjacent block at NES X+4 and X+12. A hit can
; affect at most two blocks, even when Popo straddles a character boundary.
; Foot probes are separate ($CD62), so sprite width never decides support.
compute_pcols:
        lda pxlo
        sec
        sbc #16                 ; NES X+4, plus four C64 margin columns
        sta tmplo
        lda pxhi
        sbc #$00
        sta tmphi
        lda tmplo
        lsr tmphi
        ror
        lsr tmphi
        ror
        lsr tmphi
        ror
        sta pleft
        lda pleft
        clc
        adc #1
        sta pright
        sta tmplo
        rts

; Foot contact uses the original narrow support probes rather than the
; complete sprite width. C64 X52 corresponds to NES X0; column4 is NES0.
compute_feet_columns:
        lda pxlo
        sec
        sbc #14                 ; NES X+6, plus the C64 character margin
        sta tmplo
        lda pxhi
        sbc #0
        sta tmphi
        lda tmplo
        lsr tmphi
        ror
        lsr tmphi
        ror
        lsr tmphi
        ror
        sta pleft
        lda tmplo
        and #7
        cmp #5                  ; second probe is three pixels to the right
        lda pleft
        adc #0
        sta pright
        rts

; Player screen floor (slot) = world floor - camera
compute_slot:
        lda curfloor
        sec
        sbc cam
        sta slot
        rts

; --- Main game loop ---------------------------------------------------------
normal_player_tick:
        ldx player_index
        lda #0
        sta PLAYER_LAND_AGE,X
        lda invul_t
        beq @attack_timer
        dec invul_t
@attack_timer:
        jsr ground_swing_tick
        bcc @moving_attack
        rts
@moving_attack:
        lda attack_t
        beq @attack_input
        dec attack_t
@attack_input:
        lda firehit
        beq @stun_topi
        lda #20                 ; original $D05D ground swing duration
        sta attack_t
@stun_topi:
        jsr move_horizontal
        tay                     ; source input phase: new/old/finished stop
        lda onground
        beq @air
        cpy #3                  ; $CFEB finishes a stop without reading A
        beq @probe
        lda firehit             ; original A is an edge, not auto-repeat
        and #1
        beq @probe
        cpy #2
        bne @jump               ; newly-entered stop preserves old velocity
        lda #0
        sta skid_t
        sta move_dir
        sta walk_time
        sta hammer_t
@jump:
        jsr begin_jump
        lda #SFX3_JUMP          ; $CE58
        sta snd_sfx3_req
@probe: jsr compute_slot        ; CD3B probes after CE43 changes the handler
        lda slot
        jsr support_at
        lda supflag
        beq @fall
        ldx slot
        lda land_py,X
        clc
        adc support_offset
        cmp py
        beq @done_all
@fall:  jsr begin_fall          ; gravity starts on the next tick
        jmp @done_all
@air:   jsr air_move
        lda state
        cmp #1
        bne @ret
@done_all:
        jmp surface_motion      ; NES E29A carries only after the final foot probe
@ret:   rts

; NES ground walk: 1 + $20/256 px/tick, 24-tick run-up, release/reversal skid.
; In flight the original direction is latched, at $45/$90 fractional speed.
.segment "HELPERS"
input_direction:
        lda joy
        and #4
        beq @left
        lda joy
        and #8
        beq @right
        lda #0
        rts
@left:  lda #2
        rts
@right: lda #1
        rts

.segment "CODE"
move_horizontal:
        lda skid_t
        beq @timer_done
        dec skid_t              ; original $32 counts down in every handler
@timer_done:
        lda onground
        jeq @air
        cmp #2                  ; original handler3, including a zero timer
        bne @input
@skid_step:
        ldx player_index
        lda py
        sta PLAYER_LAND_Y,X
        lda #$80                ; source CFC6 draws stop pose5, even on A/exit
        sta PLAYER_LAND_AGE,X
        ldx #1
        jsr horizontal_steps
        lda skid_t
        beq @finish_stop
        lda state
        cmp #3
        beq @old_stop           ; bonus retains the upper-floor friction
        lda curfloor
        cmp #5                  ; $CFE0: friction only on source floors6..9
        bcs @old_stop
@finish_stop:
        lda #0
        sta skid_t
        sta move_dir
        sta walk_time
        sta hammer_t
        lda #1
        sta onground
        lda #3                  ; input is ignored on this finishing tick
        rts
@old_stop:
        lda #2                  ; A from an existing upper stop is vertical
        rts
@input: jsr input_direction
        sta tmp
        cmp move_dir
        beq @walking
        lda move_dir
        beq @newdir
        lda walk_time
        lsr
        sta skid_t
        lda #2
        sta onground
        lda #1                  ; $CDD0 starts handler3 WITHOUT a walk step
        rts
@newdir:
        lda tmp                 ; $CDF1 keeps $6E: only $CFEF clears it, so
        sta move_dir            ; a fall (5) or a $D212 bump ($18) carries on
@walking:
        lda move_dir
        beq @done
        inc hammer_t            ; original CD95 advances once per walk tick
        lda hammer_t
        and #7
        sta hammer_t
        jsr face_motion
        lda walk_time
        cmp #24
        bcs @walk
        inc walk_time
@walk:  ldx #1
        lda walk_frac
        clc
        adc #$20
        sta walk_frac
        bcc @step
        inx
@step:  jsr horizontal_steps
        lda #0
        rts
@air:   jsr air_grace           ; A = move_dir; a late takeoff direction
        bne @air_move
        lda fall_int
        cmp #3
        bcc @done
        jsr input_direction
        beq @done
        sta move_dir
        lda #15
        sta walk_time
        jsr face_motion
@air_move:
        lda #$90
        ldx walk_time
        cpx #12
        bcs @air_speed
        lda #$45
@air_speed:
        clc
        adc air_xfrac
        sta air_xfrac
        bcc @done
        jsr air_horizontal_step ; original D160/D171 uses facing, also at bonus walls
@done:  jsr clamp_x
        lda #0
        rts

face_motion:
        lda move_dir
        sec
        sbc #1
        sta face
        rts

horizontal_steps:
        lda move_dir
        beq clamp_x
        cmp #1
        bne @left
@right: inc pxlo
        bne @rnext
        inc pxhi
@rnext: dex
        bne @right
        jmp clamp_x
@left:  lda pxlo
        bne @dec
        dec pxhi
@dec:   dec pxlo
        dex
        bne @left
clamp_x:
        ; NES $D171 stores an eight-bit X: both edges are connected.
        ; C64 sprite origin52 represents NES X0, so wrap52..307.
        lda pxlo
        sec
        sbc #52
        clc
        adc #52
        sta pxlo
        lda #0
        adc #0
        sta pxhi
        rts

begin_fall:
        jmp original_begin_fall

; Direct adaptation of NES $C83D. Keeping both fractional accumulators
; preserves its rounding: 51-pixel rise, apex at ticks 26-30, gravity $22.
vertical_step:
        lda air_init
        bne @gravity
        sta fall_int
        lda #8
        sta fall_frac
        lda #$F0
        sta y_frac
        lda hammer_t            ; CDB0 leaves its r60 walking count for D04F
        and #1
        clc
        adc #1
        sta air_init
        jmp @apply
@gravity:
        lda air_init            ; render-only age: original $D04F changes
        and #$0F                ; high bits retain original collision flags
        cmp #12                 ; from pose6 to pose7 after eleven air ticks
        bcs @aged
        inc air_init
@aged:
        lda fall_int
        cmp #8
        bcs @apply
        lda fall_frac
        adc nes_gravity        ; $C839[$2F]: $22, $17 while dying; C clear
        sta fall_frac
        lda fall_int
        adc #0
        sta fall_int
@apply: lda y_frac
        sec
        sbc rise_frac
        sta y_frac
        lda py
        sbc rise_int
        pha
        clc
        lda y_frac
        adc fall_frac
        sta y_frac
        pla
        adc fall_int
        sta py
        sec
        sbc prevpy
        sta vy
        rts

air_move:
        lda air_init
        and #$0F
        sta loopidx             ; previous rendered mallet pose for $D021
        ldx player_index
        sta PLAYER_LAND_AGE,X    ; only used if this tick lands without drawing
        lda py
        sta PLAYER_LAND_Y,X
        sta prevpy
        jsr vertical_step
@contacts:
        jsr head_check
        jsr land_check
        lda onground
        bne @done
        lda py
        cmp #240                ; source D463: bodyY+25 in $F1..$FA band
        bcc @done
@dead:  jmp player_fell
@done:  rts

; $CEEF/$CF5B test the real head clearance, independently of the mallet.
; A hit changes the NEXT tick's rise vector. $D021/$DDC9 later removes
; the brick only when the previously drawn raised mallet reaches its band.
.segment "HELPERS"
head_check:
        lda air_init
        jmi @done               ; original $86 head-inhibit latch
        lda curfloor
        sec
        sbc cam
        clc
        adc #1
        sta rowidx
        cmp #VISIBLE_FLOORS
        jcs @done
        tax
        lda land_py,X
        clc
        adc #31                 ; bodyY-6 in the original seven-pixel band
        sta ceilpy
        lda py
        sec
        sbc ceilpy
        cmp #7
        bcs @mallet_gate
        jsr normal_head_mask
        sta blocked
        lda #1
        sta break_layer
        lda #8
        jsr normal_head_probe
        cmp #BLANK
        bne @lower_hit
        lda blocked
        beq @mallet_gate
        lda #$F0
        bne @hit
@lower_hit:
        lda #$B0
@hit:   sta rise_frac            ; original preserves the actual overshoot Y
        lda #0
        sta rise_int
@mallet_gate:
        lda rise_int
        bne @done
        lda fall_int
        cmp #3
        bcs @done
        lda loopidx             ; previous rendered air pose, not this tick's
        beq @done
        cmp #12
        lda #7                  ; pose6 malletY+8, then source subtracts1
        bcc @point
        lda #$F7                ; pose7 malletY-8, then source subtracts1
@point: clc
        adc prevpy
        sta tmp
        ldx rowidx
        lda land_py,X
        clc
        adc #25
        sta ceilpy
        lda tmp
        sec
        sbc ceilpy
        cmp #7
        bcs @done
        lda air_init
        ora #$80
        sta air_init
        jsr normal_break_head
@done:  rts

; A=head offset in NES pixels. Return the source upper/lower cell, with
; the original cloud interval replacing air by solid0 ($DBB4/$DC62).
normal_head_probe:
        clc
        adc pxlo
        sec
        sbc #52
        lsr
        lsr
        lsr
        clc
        adc #4
        sta coltmp
        jsr get_char
        cmp #BLANK
        bne @done
        lda wrld
        cmp #9
        bcs @air
        tax
        lda floor_types,X
        and #$E0
        cmp #$60
        bcc @air
        jsr normal_cloud_contact
        bcc @air
        lda #STONE
        rts
@air:   lda #BLANK
@done:  rts

normal_head_mask:
        lda #0
        sta break_layer
        sta blocked
        lda #8
        jsr normal_head_probe
        cmp #BLANK
        beq @sides
        lda #1
        rts
@sides: lda move_dir
        bne @moving
        lda #6
        jsr normal_head_probe
        cmp #BLANK
        beq @right
        lda #$E0
        sta blocked
@right: lda #10
        jsr normal_head_probe
        cmp #BLANK
        beq @test
        lda blocked
        ora #7
        sta blocked
        bne @test
@moving:
        lda #13
        ldx face
        beq @front
        lda #3
@front: jsr normal_head_probe
        cmp #BLANK
        beq @test
        lda #1
        ldx move_dir
        dex
        beq @mask
        lda #$80
@mask:  sta blocked
@test:  lda pxlo
        sec
        sbc #4                  ; (original bodyX+8)&7
        and #7
        tax
        lda #$80
@shift: cpx #0
        beq @bit
        lsr
        dex
        bne @shift
@bit:   and blocked
        beq @clear
        lda #1
@clear: rts

.segment "CODE"
normal_break_head:
        jsr compute_pcols       ; raised mallet: right4/12, left12/4
        lda #1
        sta break_layer
@layer: lda face
        beq @right_first
        lda pright
        bne @column
@right_first:
        lda pleft
@column:
        sta coltmp
        lda rowidx
        clc
        adc cam
        sta wrld
        lda #8
        ldx wrld
        cpx #2
        bcc @bounds
        lda #9
        cpx #5
        bcc @bounds
        lda #10
@bounds:sta tmp
        lda coltmp
        cmp tmp
        bcc @bump
        lda #40
        sec
        sbc tmp
        cmp coltmp
        beq @bump
        bcc @bump
        jsr get_char
        cmp #STONE
        beq @next
        jsr solid_char
        bcc @next
        jmp break_block         ; exactly one brick, lower before upper
@next:  lda face
        beq @right_next
        lda coltmp
        cmp pleft
        beq @next_layer
        lda pleft
        jmp @column
@right_next:
        lda coltmp
        cmp pright
        beq @next_layer
        lda pright
        jmp @column
@next_layer:
        lda break_layer
        beq @done
        dec break_layer
        jmp @layer
@bump:  lda #SFX1_BUMP          ; $DDE6: outside the floor ($DAD5)
        sta snd_sfx1_req
@done:  rts

.segment "HELPERS"
break_block:
        lda #BLANK
        sta chartmp
        jsr set_char            ; Caller supplies rowidx and coltmp
        lda rowidx
        clc
        adc cam
        sta wrld
        lda coltmp
        sta colw
        jsr cell_index
        bcs @invalid
        jsr debris_note         ; $D91C starts a piece of debris
        lda #0
        ldy break_layer
        beq @upper
        sta floor_lower,X
        jmp @refresh
@upper: sta floor_upper,X
@refresh:
        jsr cache_cell          ; wrld/colw: just this cell
@invalid:
        lda #SFX1_BLOCK         ; $DDA9
        sta snd_sfx1_req
        lda #$01
        sta broke
        lda #4                  ; original block counter, paid at results
        jmp score_event

.segment "CODE"
; Falling: land when crossing a supported floor; check for completion
land_check:
        lda #0
        sta loopidx
@check:
        ldx loopidx
        lda land_py,X
        clc
        adc #1
        sta land_target
        lda py
        sec
        sbc land_target
        ldy #7                  ; $CBDC: upper bands are seven pixels high
        cpx #0
        bne @height
        ldy #9                  ; bottom visible band is nine pixels high
@height:sty tmp
        cmp tmp
        jcs @next
        txa
        clc
        adc #1
        asl
        asl
        asl
        asl
        sta tmp
        lda air_init
        and #$70
        cmp tmp
        jeq @done               ; original $88 probes a band only once
        lda fall_int            ; CF1A checks/clears its band before eligibility
        cmp #3
        bcs @eligible
        cmp #2
        jcc @done
        lda rise_int
        bne @fraction
        lda rise_frac
        cmp #$B0                ; source lower-block handler8 is special
        beq @eligible
@fraction:
        lda fall_frac
        cmp #$C0
        jcc @done
@eligible:
        lda air_init
        and #$8F
        ora tmp
        sta air_init
        lda loopidx
        jsr support_at
        lda supflag
        bne @supported
        jmp @done
@supported:
        ldx loopidx
        lda land_py,X
        sta py
        lda loopidx
        clc
        adc cam
        sta curfloor
        lda #1
        sta onground
        lda move_dir
        beq @landed
        lda #2                  ; source CEBC enters the stop handler
        sta onground
        ldx player_index
        lda py                  ; moving landing falls through CED0/D17C pose7
        sta PLAYER_LAND_Y,X
        lda #12
        sta PLAYER_LAND_AGE,X
@landed:
        lda hammer_t            ; source CEAC clears r60, retains walk pose r6C
        and #6
        sta hammer_t
        lda #0
        sta vy
        sta air_init
        lda walk_time
        lsr
        ldx curfloor
        cpx #7
        bcs @skid
        lsr
@skid:  sta skid_t
        lda curfloor
        cmp maxfloor
        beq @scroll
        bcc @scroll
        sta maxfloor
@scroll:
        lda curfloor
        cmp #WORLD_TOP
        bne @done
        jmp enter_win
@done:  rts
@next:  inc loopidx
        lda loopidx
        cmp #VISIBLE_FLOORS
        bne @more
        lda air_init
        and #$8F                ; $CF51 clears the last foot band outside it
        sta air_init
        rts
@more:
        jmp @check

.segment "CODE"

; --- sprites / UI ----------------------------------------------------------------
popo_frames:
        .byte POPO_R_WALK0, POPO_L_WALK0, POPO_R_WALK1, POPO_L_WALK1
        .byte POPO_R_JUMP, POPO_L_JUMP, POPO_R_HAMMER, POPO_L_HAMMER
        .byte POPO_R_ATTACK, POPO_L_ATTACK
        .byte POPO_R_STRIKE, POPO_L_STRIKE
        .byte POPO_R_WALK2, POPO_L_WALK2
        .byte POPO_R_WALK0, POPO_L_WALK0 ; reserved direct idle pose
        .byte POPO_R_IDLE, POPO_L_IDLE
        .byte POPO_R_STOP, POPO_L_STOP
popo_y:
        .byte POPO_R_WALK0_Y, POPO_L_WALK0_Y, POPO_R_WALK1_Y, POPO_L_WALK1_Y
        .byte POPO_R_JUMP_Y, POPO_L_JUMP_Y, POPO_R_HAMMER_Y, POPO_L_HAMMER_Y
        .byte POPO_R_ATTACK_Y, POPO_L_ATTACK_Y
        .byte POPO_R_STRIKE_Y, POPO_L_STRIKE_Y
        .byte POPO_R_WALK2_Y, POPO_L_WALK2_Y
        .byte POPO_R_WALK0_Y, POPO_L_WALK0_Y
        .byte POPO_R_IDLE_Y, POPO_L_IDLE_Y
        .byte POPO_R_STOP_Y, POPO_L_STOP_Y
mallet_frames:
        .byte MALLET_R_CARRY, MALLET_L_CARRY, MALLET_R_CARRY, MALLET_L_CARRY
        .byte MALLET_R_WINDUP, MALLET_L_WINDUP, MALLET_R_RAISED, MALLET_L_RAISED
        .byte MALLET_R_STRIKE, MALLET_L_STRIKE
        .byte MALLET_R_FOLLOWTHROUGH, MALLET_L_FOLLOWTHROUGH
mallet_xlo:
        .byte 12, $FC, 12, $FC, $F8, 16, 0, 8, 16, $F8, 16, $F8
mallet_xhi:
        .byte 0, $FF, 0, $FF, $FF, 0, 0, 0, 0, $FF, 0, $FF
mallet_y:
        .byte 4, 4, 4, 4, 2, 2, $F2, $F2, $FA, $FA, 10, 10
topi_frames:
        .byte TOPI_R_WALK0, TOPI_L_WALK0, TOPI_R_WALK1, TOPI_L_WALK1
        .byte TOPI_R_WALK2, TOPI_L_WALK2, TOPI_R_WALK1, TOPI_L_WALK1
bird_frames:
        .byte BIRD_R_FLAP0, BIRD_L_FLAP0, BIRD_R_FLAP1, BIRD_L_FLAP1
        .byte BIRD_R_DEAD, BIRD_L_DEAD

.include "ui.asm"

; ---------------------------------------------------------------------------
; Each update commits at line 250. One that ends late but while the lower
; border, or the top border up to the frame IRQ, still leaves commit_actors
; time to re-arm that IRQ, commits at once instead of a whole frame later:
; a few lines of overrun no longer repeat a frame.
wait_frame:
        jsr sound_idle          ; the sound uses the time this would wait
        lda frame_ticks         ; frame IRQs since the last commit
        sec
        sbc commit_ticks
        cmp #1
        beq @late_window
        cmp #0
        bne @wait
        ; A short update can end in the SAME lower border as its commit.
        ; Do not replace that packet before the frame IRQ has displayed it.
        ; The physical border transition also paces the IRQ-free title.
@next_border:
        bit $D011
        bmi @next_border
        lda RASTER
        cmp #250
        bcs @next_border
        bit $D011               ;low-byte wrap255->256 must not look like line0
        bmi @next_border
        jmp @wait
@late_window:
@sample:
        ldx RASTER
        lda $D011
        cpx RASTER
        bne @sample             ; a consistent line number
        asl
        bcs @now                ; PAL lower border (256..311), before IRQ12
        cpx #250
        bcs @now                ; lines 250..255
        cpx #FRAME_IRQ_LINE-5
        bcc @now                ; 6+ lines: fits any view commit
        bne @wait               ; too late or on time for the next lower border
        lda state
        cmp #3
        beq @now                ; 5 lines: constant-colour bonus commit only
@wait:  lda #$FA
@w1:    bit $D011               ; an IRQ may occupy the entire line250
        bmi @now                ; PAL lower border, lines256..311
        cmp RASTER
        bcs @w1                 ; accept any line251..255 as well
        lda #0                  ; on time: extra_tick may judge by the raster
        beq @commit
@now:   lda #1
@commit:
        sta late_commit
        lda frame_ticks
        sta commit_ticks
        rts


; ---------------------------------------------------------------------------
.segment "EXTRA"
extra_begin:
.segment "HIGH"
high_begin:
.segment "CODE"
.include "world.asm"
.include "environment.asm"
.include "actors.asm"
.include "bonus.asm"
.include "preview.asm"
.include "preview_world.asm"
.include "terrain.asm"
.include "terrain_palette.asm"
.include "terrain_unpack.asm"
.include "original_physics.inc"
.include "relocate.asm"
.include "jump_grace.asm"
.include "nes_objects.asm"
.include "boot.inc"
.include "sound.asm"            ; last: the routines above keep their places
.segment "EXTRA"
extra_end:
.segment "HIGH"
high_end:
; Sound RAM (sound.asm): zero in the file, after the high code.
snd_vars:
snd_apu:        .res 16         ; $4000-$400F; +2/+3, +6/+7: the live periods
snd_apu_w:      .res 16         ; nonzero: the engine wrote that register
snd_ram:        .res 19         ; the engine's $0700-$0712
snd_start:      .res 4          ; envelope start flags (triangle: linear reload)
snd_sw_div:     .res 2          ; sweep dividers
snd_sw_reload:  .res 4          ; sweep reload flags
snd_mute_lo:    .res 2          ; pulse_muted: the last muted period
snd_mute_hi:    .res 2
snd_mute_r1:    .res 2          ; and sweep register
snd_linear:     .res 1          ; the triangle's linear counter
snd_phase:      .res 1          ; sound_frame: 6 ticks in 5 frames
snd_debt:       .res 1          ; engine ticks the APU has not followed yet
snd_q:          .res 1          ; apu_clocks: quarter frames before the update
snd_hurry:      .res 1          ; apu_batch: $40 spare time, $80 forced, 0 always
snd_quiet:      .res 1          ; frames since the SID was last updated
snd_noise_voice: .res 1         ; SID voice offset the noise plays on (0: none)
snd_sid:        .res 21         ; the SID voice registers as last written; +2
                                ; and +5: the voice's pitch signature
snd_pw:         .res 1
snd_f:          .res 2
snd_x:          .res 2
snd_t:          .res 2          ; sweep_target
snd_c:          .res 2
snd_u:          .res 1          ; freq_of
snd_frac:       .res 1
snd_shl:        .res 1
snd_shr:        .res 1
snd_vars_end:
        .assert snd_vars_end <= $8000, error, "Sound RAM overlaps the assets"
.segment "CODE"
code_end:
.segment "DATA"
charset_src:
        .incbin "../../converted/charset/charset_hires.bin",0,80
terrain_packed_src:
        .incbin "../build/terrain_charset.rle"
colram_src:
        .incbin "../build/title_colours.rle"
screen_src:
        .incbin "../build/title_screen.rle"
condor_rle:                     ; the condor blocks' art (debris_condor)
        .incbin "../build/condor_sprites.rle"
.segment "SPRITESHI"            ; boot only: unpacked first, from below $6000
sprites_hi_src:
        .incbin "../build/game_sprites_hi.rle"
.segment "SPRITESLO"            ; boot only: unpacked second, from below $5000
sprites_lo_src:
        .incbin "../build/game_sprites_lo.rle"
.segment "DATA"
        ; RLE is checked against game_sprites.bin by the build/test tools.
        .assert SPRITES+SPRITE_PAGES*256 <= $7000, error, "Sprites overlap high code"
title_charset_src:
        .incbin "../build/title_charset.rle"
levels_src:
        .incbin "../build/nes_levels.rle"
level_types_src:
        .incbin "../build/nes_floor_types.bin"
ui_font_src:
        .incbin "../build/ui_font.bin"
assets_end:
        .assert assets_end <= $C000, error, "Asset data overlaps extra code"
