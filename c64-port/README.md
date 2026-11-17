# C64 development

Use `python build.py` from the repository root. Python 3.10+ and cc65 are
required. The scripts use the standard library; no Python packages are
needed. VICE (`x64sc`) is required for emulator checks and running the game.

## Source layout

| Path | Purpose |
| --- | --- |
| `c64/src/game.asm` | Game entry, state machine, and source includes |
| `c64/src/title.asm` | Hidden verification codes and NES attract demonstration |
| `c64/src/players.asm`, `original_physics.inc` | Player rules and physics |
| `c64/src/nes_objects.asm`, `actors.asm` | NES object integration and rendering |
| `c64/src/world.asm`, `terrain*.asm`, `normal_clouds.asm` | Terrain and moving clouds |
| `c64/src/bonus.asm`, `preview*.asm` | Bonus stages and mountain preview |
| `c64/src/video.inc`, `normal_pan.asm` | PAL video, scrolling, and sprite scheduling |
| `c64/src/sound.asm` | NES sound engine integration with SID output |
| `tools/` | Extraction, conversion, planning, and regression tools |
| `tools/fixtures/` | Checked-in reference data and joystick routes |

Paths in this table are relative to `c64-port`. The NES disassembly,
constants, header, and CHR files at the repository root are the build inputs.

## Build and checks

The build reconstructs the NES ROM and verifies its SHA-1, extracts assets,
converts graphics and music, generates assembly data, and runs ca65/ld65.
All generated data stays in ignored directories. A clean checkout needs no
previous build, ROM download, or files from another repository.

```text
python build.py build
python build.py test
python build.py verify
python build.py build --demo
python build.py rom
```

`test` runs the Python regressions against the assembled game. `verify`
checks jumps, Topi, previews, sprite timing, scrolling, displayed pixels,
ice shades, cloud writes, stack depth, gameplay, and SID audio in VICE.
Reports go to `docs/verification`; temporary emulator files go to `build_dbg`.

The release title has no visible mountain selector. For verification, type
one of the four-character codes in `tools/level_codes.py`, then press fire.
`jd3q` selects mountain 31. Finish within five seconds of the first key;
an incomplete or invalid code resets the selection to mountain 1. Input has
no visual or audible feedback. Up/down still selects the player count.
`ViceSession.title_code()` feeds the same parser with a temporary CIA matrix
fixture and restores its instruction before gameplay and memory guards.

The original title supports mountain selection, but this port deliberately
replaces it with the requested hidden verification input. NES C460/CB9D
enters the silent attract demonstration after 1407 original ticks (1173 PAL
frames). C620 supplies its scripted controller input and returns to the title
on a fall or Start/Select. The port maps those exits to fire, P and RUN/STOP;
RUN/STOP also leaves normal gameplay or the flyover. Demonstrations rotate
through mountains 1-4 and preserve the pending verification mountain.

`test_stone_columns.py` executes the original E05E PPU commands and checks
all 32 mountains in both player modes. Posts have five visible vertical tiles,
matching E002/E0B9 collision height; all 384 stage/mode/camera collision
tables also match E002. The object regression replays mountain 31 in both
modes against the original ROM. `verify_title_stones.py` checks native
code invisibility, demo timing/return, and every mountain 31 post's displayed
pixels across six camera positions and a full pan in both modes. Level records use lossless
RLE to keep these changes within the existing memory regions.

Stone columns are permanent in the NES original. DAF2 rejects stone values
0/3/4; only ice values 1/2 can be broken. A ground hammer swing cannot open
a column. E0B9 stops or pushes the two climbers, while Topis cross columns
in their original EFEC/EE0D movement routines. `test_stone_rules.py` checks
these rules against executed NES code, including both directions and player
modes; `test_nes_stones.py` also checks held hammer swings into a column.

During normal play, C777 draws Topis, the bear and ground ice behind terrain;
players, Nitpicker and falling icicles remain in front. The C64 carries that
flag in colour bit7 and prepares a separate D01B mask for every sprite event,
including reused channels; masks follow the normal camera pan. Priority
helpers use EB80-EBFF; event masks occupy EB40-EB7F, after the generated
copy code. Startup relocates the
helper before unpacking video assets, and memory guards protect it. Scene
entry clears both mask buffers; bonus/preview frames skip the channel scan.
Fruit append flags are set once per frame to preserve the bonus timing budget.
`test_background_priority.py` checks original OAM flags and channel reuse;
`verify_stone_rules.py` checks actual wall occlusion, intact columns after
hammering, and Topi crossings in VICE. C64 multicolour priority hides sprites
behind bit pairs `%10`/`%11`; `%01` remains background, so some multicolour
edge pixels still differ from NES occlusion. Fixed VIC channel priority also
means a terrain-hidden sprite can mask another figure on a higher-numbered
channel. Display checks retain its opaque coverage when checking overlaps.
See the
[VIC-II reference, priority and collision detection](https://janklingel.de/wordpress/wp-content/uploads/2020/08/MOS-6567_6569-Video-Interface-Controller.pdf).

For a focused check, build first, then run a script from the repository root:
`python c64-port/tools/test_sound.py`. Emulator scripts accept `--vice`;
otherwise they use `VICE_ROOT` or `x64sc` on `PATH`.

The optional `python build.py native` command needs g++ with C++17. It builds
and validates a local CPU accelerator for longer regression and route
search runs. The normal build and tests work without it.

`test_sprite_conversion.py` compares 108 normal, bonus, and compact sprite
frames with NES CHR pixels. Its report and comparison atlas decode the
actual C64 bytes. Hires layers remain exact; within the current layer
allocation, multicolour pairs retain as many source pixels as possible. The
atlas uses a common palette to compare shapes. `verify_sprite_colours.py`
checks ice highlights and both blue shades in VICE's displayed pixels.

The player audit executes the original NES sprite writer, including idle
and bonus feet, in both directions. The parka stays at full horizontal
resolution. Three hires layers reproduce every source pixel; two-layer
poses combine white and skin details into multicolour pairs. Their pixel
grid is selected to reduce errors without worsening either stage type.
When a multicolour pair must choose between skin and a dark eye pixel,
the compact poses preserve the eye opening. The eye can be two pixels wide;
the total pixel error stays minimal, with no extra sprites or runtime work.
The opening stays enclosed by the face: where that pair also holds the
face's outer edge (compact WALK1, WALK2 and STRIKE), that row keeps its
skin and the eye shows on the row below.
The tilted compact jump pose keeps a one-row eye and skin immediately above
it, avoiding a square hole during takeoff. Three-layer poses retain the exact
NES pixels. The VICE player check also follows real jumps through both air
poses in both directions, with one player, a crowded budget, and two players.
The optimum applies to these modes and sprite allocation. A different
memory layout or fewer simultaneous figures can provide more detail.
The sprite bank uses all
128 blocks. `verify_player_sprites.py` checks the displayed player pixels
in VICE, including Nana, crowded scenes, and the 9-bit X carry.

Enemy and debris Y positions already move with the NES pan routines. Their
renderer applies only the fixed C64 screen offset, avoiding an extra 48-pixel
jump when a pan is armed. `test_pan_sprites.py` covers all five pan boundaries,
enemy classes and debris in both player modes. `verify_enemy_pan.py` checks
displayed enemy pixels before, during and after scrolling, including the
arming frame before the camera moves.

## Implementation notes

The game targets PAL at 50 Hz, with six NES physics ticks per five frames.
One-player rendering can defer an extra tick when the frame is busy.
Deterministic route tests use `fixed_ticks`; VICE checks remain necessary
for raster deadlines, displayed pixels, and sound.

`c64.cfg` defines the memory regions. Startup code relocates helpers,
unpacks sprites, and sets up video. The game uses VIC bank 1, double screen
buffers, raster sprite events, and RAM under BASIC/KERNAL and I/O. Preserve
the linker bounds and protected code/data guards when changing layouts.

Keep regression fixtures as references. Generate reports separately, and
replay changed routes in VICE before accepting them. See [AGENT.md](../AGENT.md)
for the shared Codex CLI and Claude Code workflow.
