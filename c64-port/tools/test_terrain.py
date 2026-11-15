#!/usr/bin/env python3
"""Check actual VIC character pixels against the original NES artwork.

This deliberately does not import the terrain converter or repeat its
quantizer. Each double-width VIC pixel must select one of the corresponding
two NES pixels. Equal source pixels must survive unchanged. Mountain side
placement is checked against the original $E79D six-row/column-major layout.
The broader map, collision and camera checks remain in test_game.py.
"""
import hashlib
import json
from pathlib import Path

from nesgfx import chr_tiles
from test_game import start


BASE = Path(__file__).resolve().parents[1]
CHARSET = 0x4800
WORLD = 0xE000
COLOURS = 0xF000
# $D022 = main rock; colour RAM = highlight; $D023 = shadow.
VIC_TO_NES = (0, 2, 3, 1)
# The unused upper-plane map value 2 falls back to normal ice. NES $91 is
# the letter S (the corresponding original D785 table entry is unused).
SEMANTIC_TILES = {218: 0x90, 223: 0x90, 226: 0x90, 227: 0x92, 224: 0xEB}


def check_tile(ram, code, source, context):
    """Accept either member of a source pair without prescribing a filter."""
    for y in range(8):
        bits = ram[CHARSET + code * 8 + y]
        for x in range(4):
            value = VIC_TO_NES[(bits >> (6 - 2 * x)) & 3]
            allowed = source[y][2*x:2*x+2]
            assert value in allowed, (context, code, x, y, value, allowed)


def check_number(ram, code, source, context):
    """Original six-pixel strokes retain both one-pixel black side borders."""
    for y in range(8):
        bits = ram[CHARSET + code*8 + y]
        for x in range(8):
            assert bool(bits & (0x80 >> x)) == (source[y][x] == 2), \
                (context, code, x, y, bits, source[y])
        assert bits & 0x81 == 0, ('missing black number border', context, y)


def expected_walls(floor_types=bytes(9)):
    """Source tile IDs from $E79D/$E85D, without converter metadata."""
    cells = {}
    # The alternative fluted cloud walls are column starts from NES $E791.
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    cloud_columns = prg[0x2791:0x279D]
    for floor in range(1, 9):
        width = 4 if floor <= 2 else 5 if floor <= 5 else 6
        for row in range(6):
            world_row = 6 * floor + 1 - row
            for col in range(width):
                left = 0xA4 + (6-width+col) * 6 + row
                right = 0xC8 + col * 6 + row
                if floor >= 2 and floor_types[floor-1] & 0xE0 >= 0xA0:
                    left = cloud_columns[6-width+col] + row
                    right = cloud_columns[6+col] + row
                if row == 5:
                    left = right = 0xEB
                cells[world_row, col] = left
                cells[world_row, 32-width+col] = right
        for row in (2, 3):
            number = 0xEA + 2*floor + row-2
            cells[6*floor+1-row, width-3] = number
            cells[6*floor+1-row, 32-width+2] = number
    return cells


def check_world(ram, tiles):
    for (row, col), nes in expected_walls(ram[0x600:0x609]).items():
        code = ram[WORLD + row*32 + col]
        if 0xEC <= nes <= 0xFB:
            check_number(ram, code, tiles[nes], ('number', row, col, hex(nes)))
            assert ram[COLOURS + row*32 + col] == (1 if row >= 32 else 7), \
                ('number contrast', row, col)
        else:
            check_tile(ram, code, tiles[nes], ('wall', row, col, hex(nes)))
            assert ram[COLOURS + row*32 + col] & 8, ('hires wall', row, col)
    # The empty gap above each sloping side is part of the mountain's shape.
    # Check complete black source pairs as well as the filled rock pixels;
    # a solid rectangle fails even when it uses the correct colours.
    widths = set()
    for floor in (1, 3, 6):
        row = 6*floor-1
        visible = []
        for col in range(8):
            code = ram[WORLD + row*32 + col]
            if any(ram[CHARSET+code*8:CHARSET+(code+1)*8]):
                visible.append(col)
        widths.add(len(visible))
    assert len(widths) == 3, ('mountain sides do not widen', widths)


def check_display(machine):
    """Check visible colour RAM for the wider sides, including column 5."""
    ram, labels = machine.ram, machine.labels
    for camera in range(6):
        ram[labels['cam']] = camera
        for _ in range(29):
            machine.call('commit_view')
            machine.call('commit_colours')
            machine.call('view_tick')
        machine.call('commit_view')
        machine.call('commit_colours')
        screen = 0x4000 + 1024*ram[labels['screen_buffer']]
        view = ram[labels['last_view_row']]
        for sy in range(2, 24):
            row = view + 24 - sy
            for col in range(32):
                code = ram[WORLD + row*32 + col]
                if not any(ram[CHARSET+code*8:CHARSET+(code+1)*8]):
                    continue
                actual = ram[0xD800 + sy*40 + 4+col] & 15
                expected = ram[COLOURS + row*32 + col]
                assert actual == expected, ('display colour', camera, sy, col, actual, expected)
                assert ram[screen + sy*40 + 4+col] == code


def check_attack_animation(machine):
    """Compare pose geometry with the unchanged NES $D17C OAM routine."""
    from emulate_prg import CPU
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    source_tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000])
    sprites = json.loads((BASE/'c64/build/sprite_frames.json').read_text())
    frames = {entry['pointer']+layer: entry for entry in sprites
              for layer in range(entry['layers'])}
    ram, labels = machine.ram, machine.labels
    comparisons = 0
    for players in (1, 2):
        for face in (0, 1):
            # GROUND_SWING1 is active D05D; input entry uses flag2 separately.
            for countdown in range(20, 0, -1):
                # Execute the actual attack pose selector, not a copied
                # countdown-to-pose table. It increments its elapsed tick.
                reference = bytearray(65536)
                reference[0xC000:] = prg
                reference[0x5F] = 0
                reference[0x60] = 20-countdown
                reference[0x62] = 1-face
                reference[0x64] = 120
                reference[0x66] = 162
                cpu = CPU(reference, {})
                cpu.push(0xBF)
                cpu.push(0xFF)
                cpu.pc = 0xD05D
                for _ in range(20000):
                    if cpu.pc == 0xC000:
                        break
                    cpu.step()
                else:
                    raise AssertionError(('NES attack did not return', hex(cpu.pc)))
                body_tile = min(reference[0x201+i*4] for i in range(6))
                body_pixels = [[source_tiles[body_tile+(x//8)*3+y//8][y%8][x%8]
                                for x in range(16)] for y in range(24)]
                last_row = max(y for y, row in enumerate(body_pixels) if any(row))
                crop = max(0, last_row-20)
                ram[labels['player_count']] = players
                ram[labels['player_index']] = players-1
                ram[labels['logical_count']] = 0
                ram[labels['actor_mask']] = 255
                ram[labels['attack_t']] = countdown
                ram[labels['GROUND_SWING']+players-1] = 1
                ram[labels['hammer_t']] = 0
                ram[labels['onground']] = 1
                ram[labels['move_dir']] = 0
                ram[labels['face']] = face
                ram[labels['pxlo']] = 120
                ram[labels['pxhi']] = 0
                ram[labels['py']] = 168
                ram[labels['view_delta']:labels['view_delta']+2] = bytes(2)
                machine.call('actor_player')
                count = ram[labels['logical_count']]
                body = frames[ram[labels['LOG_PTR']]]
                mallet = frames[ram[labels['LOG_PTR']+count-1]]
                assert body['nes_base'] == body_tile, ('body pose', players, face, countdown)
                assert ram[labels['LOG_Y']] == reference[0x200]+crop, \
                    ('visual attack hop', players, face, countdown)
                if reference[0x21C] != 0xF8:  # separate hammer is visible in action poses
                    assert mallet['nes_base'] == reference[0x21D], ('mallet tile', countdown)
                    assert ram[labels['LOG_X']+count-1] == reference[0x21F], ('mallet X', face, countdown)
                    assert ram[labels['LOG_Y']+count-1] == reference[0x21C], ('mallet Y', face, countdown)
                else:
                    assert count == (3 if players == 1 and not body.get('compact') else 2), \
                        'Duplicate idle club sprite'
                assert ram[labels['py']] == 168, 'Visual hammer hop changed physical position'
                if body_tile == 0x86:
                    assert count == 3
                    assert ram[labels['LOG_COL']] == (4 if players == 2 else 14)
                comparisons += 1
            # Ground-B's final tick forces original pose0 even when a
            # walking direction/animation phase was latched before the swing.
            ram[labels['logical_count']] = 0
            ram[labels['attack_t']] = 1
            ram[labels['move_dir']] = 1
            ram[labels['walk_frac']] = 64
            ram[labels['GROUND_SWING']+players-1] = 1
            machine.call('actor_player')
            body = frames[ram[labels['LOG_PTR']]]
            assert body['nes_base'] == min(reference[0x201+i*4] for i in range(6)), \
                ('ground attack exit pose', players, face)
            assert ram[labels['py']] == 168
            ram[labels['GROUND_SWING']+players-1] = 0
            comparisons += 1
    return comparisons


def check_walk_animation(machine):
    """The original $CD95 advances its four-pose cycle every two ticks."""
    from emulate_prg import CPU
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    sprites = json.loads((BASE/'c64/build/sprite_frames.json').read_text())
    frames = {entry['pointer']+layer: entry for entry in sprites
              for layer in range(entry['layers'])}
    ram, labels = machine.ram, machine.labels
    comparisons = 0
    for players in (1, 2):
        for face in (0, 1):
            reference = bytearray(65536)
            reference[0xC000:] = prg
            reference[0x62] = 1-face
            reference[0x64] = 120
            reference[0x66] = 162
            cpu = CPU(reference, {})
            for tick in range(1, 33):
                for routine in (0xCD95, 0xD17C):
                    cpu.x = 0
                    cpu.y = 0 if routine == 0xCD95 else reference[0x6C]
                    cpu.push(0xBF)
                    cpu.push(0xFF)
                    cpu.pc = routine
                    for _ in range(20000):
                        if cpu.pc == 0xC000:
                            break
                        cpu.step()
                    else:
                        raise AssertionError(('NES walking pose did not return', hex(cpu.pc)))
                body_tile = min(reference[0x201+i*4] for i in range(6))
                ram[labels['player_count']] = players
                ram[labels['player_index']] = players-1
                ram[labels['logical_count']] = 0
                ram[labels['actor_mask']] = 255
                ram[labels['attack_t']] = 0
                ram[labels['hammer_t']] = 0
                ram[labels['onground']] = 1
                ram[labels['move_dir']] = 1
                ram[labels['walk_frac']] = tick*0x20 & 255
                ram[labels['hammer_t']] = tick&7
                ram[labels['face']] = face
                ram[labels['pxlo']] = 120
                ram[labels['pxhi']] = 0
                ram[labels['py']] = 168
                ram[labels['view_delta']:labels['view_delta']+2] = bytes(2)
                machine.call('actor_player')
                count = ram[labels['logical_count']]
                assert frames[ram[labels['LOG_PTR']]]['nes_base'] == body_tile, \
                    ('walk pose', players, face, tick, hex(body_tile))
                assert count == (3 if players == 1 and body_tile == 0x62 else 2), \
                    ('duplicate carried club', players, face, tick, count)
                comparisons += 1
    return comparisons


def check_idle_foot(machine):
    """Execute normal-ground $CDB0, including its $CE29 foot-tile patch."""
    from emulate_prg import CPU
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    source_tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000])
    ram, labels = machine.ram, machine.labels
    checks = 0
    for players in (1, 2):
        for face in (0, 1):
            source = bytearray(65536)
            source[0xC000:] = prg
            source[0x55] = 1  # original normal mountain mode
            source[0x62] = 1-face
            source[0x64] = 120
            source[0x66] = 162
            source[0x6A] = 1
            cpu = CPU(source, {})
            cpu.push(0xBF)
            cpu.push(0xFF)
            cpu.pc = 0xCDB0
            for _ in range(20000):
                if cpu.pc == 0xC000:
                    break
                cpu.step()
            else:
                raise AssertionError(('NES idle did not return', hex(cpu.pc)))
            original = [[0]*16 for _ in range(24)]
            for i in range(6):
                y, tile, attrs, x = source[0x200+i*4:0x204+i*4]
                for ty in range(8):
                    for tx in range(8):
                        original[y-162+ty][x-120+tx] = source_tiles[tile][ty][7-tx if attrs & 0x40 else tx]
            last = max(y for y, row in enumerate(original) if any(row))
            crop = max(0, last-20)
            ram[labels['player_count']] = players
            ram[labels['player_index']] = players-1
            ram[labels['logical_count']] = 0
            ram[labels['actor_mask']] = 255
            ram[labels['attack_t']] = 0
            ram[labels['hammer_t']] = 0
            ram[labels['onground']] = 1
            ram[labels['move_dir']] = 0
            ram[labels['face']] = face
            ram[labels['pxlo']] = 120
            ram[labels['pxhi']] = 0
            ram[labels['py']] = 168
            ram[labels['view_delta']:labels['view_delta']+2] = bytes(2)
            machine.call('actor_player')
            assert ram[labels['logical_count']] == 2, 'Idle body has a duplicate club'
            pointer = ram[labels['LOG_PTR']]
            assert ram[labels['LOG_Y']] == 162+crop
            sprite = 0x4000+pointer*64
            # The parka remains exact hires, including the independently
            # executed original idle-foot replacement and facing.
            for y in range(21):
                bits = int.from_bytes(ram[sprite+y*3:sprite+y*3+3], 'big')
                for x in range(16):
                    assert bool(bits & (1 << (23-(x+4)))) == (original[y+crop][x] == 2), \
                        ('idle foot pixels', players, face, x, y)
            checks += 1
    return checks


def check_bonus_player_art(machine):
    """Check reversible RAM patches and bonus feet against executed NES OAM."""
    from emulate_prg import CPU
    from test_topi_sprites import normal_gameplay_sprites
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000])
    # This unit calls the player patch alone, without a scene transition.
    normal = normal_gameplay_sprites()
    bonus = normal_gameplay_sprites((BASE/'c64/build/game_sprites_bonus.bin').read_bytes())
    ram, labels = machine.ram, machine.labels
    machine.call('normal_player_art')
    assert ram[0x5000:0x7000] == normal
    machine.call('bonus_player_art')
    assert ram[0x5000:0x7000] == bonus
    machine.call('bonus_player_art')
    assert ram[0x5000:0x7000] == bonus, 'Repeated bonus setup applied XOR twice'
    checks = 0
    for players in (1, 2):
        for face in (0, 1):
            for pose, phase, idle in (('WALK0', 0, False), ('WALK1', 1, False),
                                       ('WALK2', 3, False), ('IDLE', 0, True)):
                source = bytearray(65536)
                source[0xC000:] = prg
                source[0x55] = 2
                source[0x62] = 1-face
                source[0x64] = 120
                source[0x66] = 162
                source[0x6A] = 1
                source[0x6C] = phase
                if not idle:
                    source[0x68] = source[0x70] = 2 if face else 1
                cpu = CPU(source, {})
                cpu.push(0xBF)
                cpu.push(0xFF)
                cpu.pc = 0xCDB0
                for _ in range(20000):
                    if cpu.pc == 0xC000:
                        break
                    cpu.step()
                else:
                    raise AssertionError(('NES bonus pose did not return', hex(cpu.pc)))
                origin_x = min(source[0x203+i*4] for i in range(6))
                origin_y = min(source[0x200+i*4] for i in range(6))
                original = [[0]*16 for _ in range(24)]
                for i in range(6):
                    y, tile, attrs, x = source[0x200+i*4:0x204+i*4]
                    for ty in range(8):
                        for tx in range(8):
                            original[y-origin_y+ty][x-origin_x+tx] = tiles[tile][ty][7-tx if attrs & 0x40 else tx]
                ram[labels['state']] = 3
                ram[labels['player_count']] = players
                ram[labels['player_index']] = players-1
                ram[labels['logical_count']] = 0
                ram[labels['actor_mask']] = 255
                ram[labels['attack_t']] = ram[labels['hammer_t']] = 0
                ram[labels['onground']] = 1
                ram[labels['move_dir']] = 0 if idle else 1
                ram[labels['walk_frac']] = phase*64
                ram[labels['hammer_t']] = phase*2
                ram[labels['face']] = face
                ram[labels['pxlo']] = 120
                ram[labels['pxhi']] = 0
                ram[labels['py']] = 168
                ram[labels['view_delta']:labels['view_delta']+2] = bytes(2)
                machine.call('actor_player')
                count = ram[labels['logical_count']]
                assert count == (3 if players == 1 and pose == 'WALK1' else 2), \
                    ('bonus has separate mallet', players, face, pose, count)
                parka = next(i for i in range(count) if not ram[labels['LOG_MC']+i]
                             and ram[labels['LOG_COL']+i] == (4 if players == 2 else 14))
                crop = ram[labels['LOG_Y']+parka]-origin_y
                sprite = 0x4000+ram[labels['LOG_PTR']+parka]*64
                assert not any(any(row) for row in original[:crop])
                for y in range(21):
                    bits = int.from_bytes(ram[sprite+y*3:sprite+y*3+3], 'big')
                    for x in range(16):
                        assert bool(bits & (1 << (23-(x+4)))) == (original[y+crop][x] == 2), \
                            ('bonus foot pixels', players, face, pose, x, y)
                checks += 1
    # Bonus air uses original pose7 and no separate mallet, unlike the
    # normal mountain's initial raised-arm jump pose.
    ram[labels['onground']] = 0
    ram[labels['logical_count']] = 0
    machine.call('actor_player')
    assert ram[labels['animidx']] in (6, 7)
    assert ram[labels['logical_count']] == 2
    machine.call('normal_player_art')
    assert ram[0x5000:0x7000] == normal, 'Normal mountain did not restore all sprite bytes'
    machine.call('normal_player_art')
    assert ram[0x5000:0x7000] == normal
    ram[labels['state']] = 1
    return checks


def check_normal_air_animation(machine):
    """Execute NES $D04F: eleven pose6 ticks followed by pose7."""
    from emulate_prg import CPU
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    sprites = json.loads((BASE/'c64/build/sprite_frames.json').read_text())
    frames = {entry['pointer']+layer: entry for entry in sprites
              for layer in range(entry['layers'])}
    ram, labels = machine.ram, machine.labels
    comparisons = 0
    for players in (1, 2):
        for face in (0, 1):
            reference = bytearray(65536)
            reference[0xC000:] = prg
            reference[0x62] = 1-face
            reference[0x64] = 120
            reference[0x66] = 162
            cpu = CPU(reference, {})
            for tick in range(1, 21):
                cpu.push(0xBF)
                cpu.push(0xFF)
                cpu.pc = 0xD04F
                for _ in range(20000):
                    if cpu.pc == 0xC000:
                        break
                    cpu.step()
                else:
                    raise AssertionError(('NES air pose did not return', hex(cpu.pc)))
                ram[labels['state']] = 1
                ram[labels['player_count']] = players
                ram[labels['player_index']] = players-1
                ram[labels['logical_count']] = 0
                ram[labels['actor_mask']] = 255
                ram[labels['attack_t']] = ram[labels['hammer_t']] = 0
                ram[labels['onground']] = 0
                ram[labels['air_init']] = min(tick, 12)|(0x80 if tick&1 else 0xC0)
                ram[labels['move_dir']] = 0
                ram[labels['face']] = face
                ram[labels['pxlo']] = 120
                ram[labels['pxhi']] = 0
                ram[labels['py']] = 168
                ram[labels['view_delta']:labels['view_delta']+2] = bytes(2)
                machine.call('actor_player')
                count = ram[labels['logical_count']]
                body = frames[ram[labels['LOG_PTR']]]
                mallet = frames[ram[labels['LOG_PTR']+count-1]]
                assert body['nes_base'] == min(reference[0x201+i*4] for i in range(6)), \
                    ('air body pose', players, face, tick)
                assert ram[labels['LOG_Y']] == reference[0x200], ('air body origin', tick)
                assert mallet['nes_base'] == reference[0x21D], ('air mallet tile', tick)
                assert ram[labels['LOG_X']+count-1] == reference[0x21F], ('air mallet X', tick)
                assert ram[labels['LOG_Y']+count-1] == reference[0x21C], ('air mallet Y', tick)
                assert ram[labels['py']] == 168
                comparisons += 1
    return comparisons


def check_original_cloud_art(machine=None):
    """Execute original cloud OAM setup, then compare every shifted pixel."""
    from emulate_prg import CPU
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000])
    masks = (BASE/'c64/build/original_cloud_masks.bin').read_bytes()
    phases = (BASE/'c64/build/original_cloud_phases.bin').read_bytes()
    assert len(masks) == 72 and len(phases) == 768
    profiles = []
    for kind in (0xA0, 0xE0):
        source = bytearray(65536)
        source[0xC000:] = prg
        source[0x0E] = kind
        source[0x01] = 48
        source[0x03] = 128
        source[0x90] = 4
        source[0] = 2
        cpu = CPU(source, {})
        cpu.push(0xBF)
        cpu.push(0xFF)
        cpu.pc = 0xE6D3
        for _ in range(10000):
            if cpu.pc == 0xC000:
                break
            cpu.step()
        else:
            raise AssertionError(('Original cloud setup did not return', hex(cpu.pc)))
        source_profiles = []
        for start in (0, 3):
            order = [source[0x2A1+(start+i)*4] for i in range(3)]
            assert all(not source[0x2A2+(start+i)*4] & 0xC0 for i in range(3))
            source_profiles.append([[value for tile in order for value in tiles[tile][y]]
                                    for y in range(8)])
        if kind == 0xA0:
            profiles += source_profiles
        else:
            assert source_profiles[0] == source_profiles[1]
            profiles.append(source_profiles[0])
    pixels = 0
    for profile, original in enumerate(profiles):
        for y in range(8):
            for x in range(24):
                bit = masks[profile*24+(x//8)*8+y] & (0x80 >> (x%8))
                assert bool(bit) == bool(original[y][x]), ('cloud source mask', profile, x, y)
        for phase in range(8):
            for y in range(8):
                for x in range(32):
                    bit = phases[profile*256+phase*32+(x//8)*8+y] & (0x80 >> (x%8))
                    source_x = x-phase
                    expected = 0 <= source_x < 24 and bool(original[y][source_x])
                    assert bool(bit) == expected, ('shifted cloud pixel', profile, phase, x, y)
                    pixels += 1
            if machine is not None:
                machine.ram[machine.labels['state']] = 1
                machine.x = profile
                machine.y = 56
                machine.call('cloud_generate_normal', phase)
                assert machine.ram[CHARSET+56*8:CHARSET+60*8] == \
                    phases[profile*256+phase*32:profile*256+(phase+1)*32], \
                    ('runtime cloud source pixels', profile, phase)
    if machine is not None:
        for width in (4, 6):
            source = bytearray(65536)
            source[0xC000:] = prg
            source[1] = 48
            source[3] = width
            source[5] = 168
            source[7] = 0xDC
            cpu = CPU(source, {})
            cpu.pc = 0xE614
            for _ in range(10000):
                if cpu.pc == 0xE63A:  # original cloud writer has finished this cloud
                    break
                cpu.step()
            else:
                raise AssertionError(('Original bonus cloud writer did not finish', hex(cpu.pc)))
            order = [source[0x2A1+i*4] for i in range(width)]
            original = [[value for tile in order for value in tiles[tile][y]] for y in range(8)]
            for phase in range(8):
                machine.ram[machine.labels['state']] = 3
                machine.x = 2
                machine.y = 228
                machine.call('cloud_generate_normal', phase)
                runtime = machine.ram[CHARSET+228*8:CHARSET+233*8]
                for y in range(8):
                    for x in range((width+1)*8):
                        glyph = x//8
                        role = (0 if glyph == 0 else 1 if glyph == 1 else
                                3 if glyph == width-1 else 4 if glyph == width else 2)
                        bit = runtime[role*8+y] & (0x80 >> (x%8))
                        source_x = x-phase
                        expected = 0 <= source_x < width*8 and bool(original[y][source_x])
                        assert bool(bit) == expected, ('runtime bonus cloud pixel', width, phase, x, y)
                        pixels += 1
        machine.ram[machine.labels['state']] = 1
    return pixels


def check_bonus_ledge_art(machine, tiles):
    """The original F3F6 writer fills every fixed bonus ledge with CHR EB."""
    from emulate_prg import CPU
    reference = bytearray(65536)
    reference[0xC000:] = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    cpu = CPU(reference, {})
    cpu.x, cpu.y, cpu.pc = 5, 0, 0xF3F6
    for _ in range(100):
        if cpu.pc == 0xF3FF:
            break
        cpu.step()
    else:
        raise AssertionError('Original fixed bonus ledge writer did not finish')
    original = reference[0x304:0x30A]
    assert original == bytes([0xEB])*6
    cells = 0
    ram, labels = machine.ram, machine.labels
    for mountain in range(1, 9):
        ram[labels['state']] = 1
        ram[labels['mountain']] = mountain
        machine.call('setup_level')
        machine.call('enter_bonus')
        for index in range(ram[labels['bonus_platform_count']]):
            left = ram[labels['BONUS_LEDGE_L']+index]-4
            right = ram[labels['BONUS_LEDGE_R']+index]-4
            height = ram[labels['BONUS_LEDGE_HLO']+index] + 256*ram[labels['BONUS_LEDGE_HHI']+index]
            row = height//8+2
            assert 0 <= left < right <= 32
            for column in range(left, right):
                address = row*32+column
                code = ram[WORLD+address]
                assert code == 224, ('bonus ledge source character', mountain, index, column, code)
                assert ram[COLOURS+address] == 9, ('bonus ledge source palette', mountain, index, column)
                check_tile(ram, code, tiles[original[0]], ('bonus ledge', mountain, index, column))
                cells += 1
    assert cells > 200, ('missing bonus ledge fixtures', cells)
    return cells


def main():
    source = (BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()
    tiles = chr_tiles(source[0x1000:])
    machine = start()
    ram, labels = machine.ram, machine.labels
    metadata = json.loads((BASE/'c64/build/terrain.json').read_text())
    # Normal play uses live cloud characters and a private source atlas.
    # The font lifecycle check verifies that the atlas is absent from maps.
    dynamic_cloud_chars = set(range(52, 112))
    dynamic_cloud_chars |= set((BASE/'c64/build/normal_cloud_phase_codes.bin').read_bytes()) - {255}
    glyphs = [entry for entry in metadata['tiles']
              if entry['mode'] == 'mc' and entry['role'] == 'source'
              and entry['char'] not in dynamic_cloud_chars]
    numbers = [entry for entry in metadata['tiles'] if entry['role'] == 'floor_number']
    assert len(numbers) == 16
    sprites = bytes(ram[0x5000:0x7000])
    checks = 0
    for mountain in (1, 10, 24, 32):
        ram[labels['mountain']] = mountain
        machine.call('setup_level')
        assert ram[0xD016] & 0x10, 'Multicolour character mode is disabled'
        for code, nes in SEMANTIC_TILES.items():
            check_tile(ram, code, tiles[nes], ('terrain', code, hex(nes)))
        for entry in glyphs:
            check_tile(ram, entry['char'], tiles[entry['nes_tile']], ('source', entry))
        for entry in numbers:
            check_number(ram, entry['char'], tiles[entry['nes_tile']], ('number', entry))
        for floor in range(1, 9):
            upper = metadata['source_to_char'][f'{0xEA+floor*2:02X}']
            lower = metadata['source_to_char'][f'{0xEB+floor*2:02X}']
            assert ram[CHARSET+upper*8:CHARSET+upper*8+2] == bytes(2)
            assert ram[CHARSET+lower*8+6:CHARSET+lower*8+8] == bytes(2)
        check_world(ram, tiles)
        check_display(machine)
        # Bonus and results load fonts, then the next mountain must restore
        # the complete terrain charset, including low-numbered rock tiles.
        machine.call('enter_bonus')
        for code, nes in SEMANTIC_TILES.items():
            check_tile(ram, code, tiles[nes], ('bonus terrain', code, hex(nes)))
        machine.call('enter_results')
        ram[labels['state']] = 1
        machine.call('setup_level')
        for entry in glyphs:
            check_tile(ram, entry['char'], tiles[entry['nes_tile']], ('restored source', entry))
        for entry in numbers:
            check_number(ram, entry['char'], tiles[entry['nes_tile']], ('restored number', entry))
        check_world(ram, tiles)
        assert bytes(ram[0x5000:0x7000]) == sprites, 'Terrain overwrote sprite RAM'
        checks += 1
    attack_comparisons = check_attack_animation(machine)
    walk_comparisons = check_walk_animation(machine)
    idle_comparisons = check_idle_foot(machine)
    air_comparisons = check_normal_air_animation(machine)
    bonus_comparisons = check_bonus_player_art(machine)
    cloud_pixels = check_original_cloud_art(machine)
    bonus_ledge_cells = check_bonus_ledge_art(machine, tiles)
    from test_topi_sprites import check_topi_source_art
    topi_pixels = check_topi_source_art(machine)
    from test_player_sprites import check_actual_input_art, check_actual_b_entry_art
    actual_input_samples = check_actual_input_art()
    actual_b_entries = check_actual_b_entry_art()
    report = dict(status='passed', source_chr_sha256=hashlib.sha256(source).hexdigest(),
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                  mountain_fixtures=checks, wall_cells=len(expected_walls()), source_glyphs=len(glyphs),
                  framed_number_glyphs=len(numbers),
                  original_attack_pose_comparisons=attack_comparisons,
                  original_walk_pose_comparisons=walk_comparisons,
                  original_idle_pose_comparisons=idle_comparisons,
                  original_air_pose_comparisons=air_comparisons,
                  original_bonus_pose_comparisons=bonus_comparisons,
                  original_cloud_pixel_comparisons=cloud_pixels,
                  original_bonus_ledge_cells=bonus_ledge_cells,
                  original_topi_pixel_comparisons=topi_pixels,
                  actual_input_source_oam_samples=actual_input_samples,
                  actual_b_entry_source_oam_samples=actual_b_entries,
                  original_pixel_pairs=True, font_lifecycle=True, sprite_ram_unchanged=True)
    out = BASE/'docs/verification'
    out.mkdir(parents=True, exist_ok=True)
    (out/'terrain_regression.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS original NES terrain pixels, mountain sides, framed numbers, font restoration and player animation')


if __name__ == '__main__':
    main()
