"""Every original enemy sprite against the original $EAFC OAM writer.

For Nitpicker, the bear, the seals, the ice blocks and the icicles, in
each animation tile and direction, the original $EAFC writes the OAM
entries of the object. The C64 renderer (actor_nes_object) draws the same
object from the same object bytes. Each opaque NES pixel at OAM (X+c, Y+r)
must be opaque at logical (X+c+56, Y+r+18); multicolour art is compared
in its double-wide pixels. The Topi pages swap in for normal play only and
the bonus, preview and title get their fruit back.
"""
import json

from nesgfx import chr_tiles
from test_game import BASE
from test_original_physics import Reference, PRG
from transplant_objects import map_ram
from extract_screens import PPU

TOPI_OVERLAY_PTR = 0xAC
SPRITE_VIEW_SHIFT = 4       # logical Y = original OAM Y + 18 - 4 (fixed display origin)
ARMED_VIEW_DELTA = -52      # climbers' delta on a pan's arming frame; objects ignore it


def source_oam(slot, tile, x, y, facing, flip, phase=1):
    """Original $EAFC: the OAM entries of one object (slot = $03E8 & $1F)."""
    reference = Reference()
    r = reference.ram
    r[0x55] = phase
    r[0], r[1], r[2], r[0x0E], r[0x0F] = x, y, tile, flip, facing
    reference.call(0xEAFC, y=slot)
    size = PRG[0x2ADE+slot-1]
    count = (size >> 4)*(size & 15)
    start = 0x200+PRG[0x2AA2+slot-1]
    return [tuple(r[start+4*i:start+4*i+4]) for i in range(count)]


def source_pixels(tiles, entries):
    pixels = {}
    for y, code, attributes, x in sorted(entries, reverse=True):
        for ty in range(8):
            for tx in range(8):
                value = tiles[code][7-ty if attributes & 0x80 else ty][7-tx if attributes & 0x40 else tx]
                if value:
                    pixels[(x+tx, y+ty)] = value
    return pixels


def c64_pixels(ram, labels, count):
    pixels = {}
    for i in range(count):
        pointer = ram[labels['LOG_PTR']+i]
        x0 = ram[labels['LOG_X']+i]+256*ram[labels['LOG_XHI']+i]
        y0 = ram[labels['LOG_Y']+i]
        multicolour = ram[labels['LOG_MC']+i]
        data = ram[0x4000+pointer*64:0x4000+pointer*64+63]
        for y in range(21):
            for x in range(24):
                if multicolour:
                    bits = (data[y*3+x//8] >> (6-(x & 6))) & 3
                else:
                    bits = data[y*3+x//8] & (0x80 >> (x % 8))
                if bits:
                    pixels[(x0+x, y0+y)] = True
    return pixels


# $C73D writes the tiles only with $03E8 bit 6 ($EF6A sets it whenever
# $03DD changes); otherwise it moves the previous tiles.
CASES = [
    # object, slot, tiles, NES $BD values (positive: right), $03E8 flag
    (0, 3, (0xE0, 0xE4, 0xB2), (0x80, 0x00), 0x40),      # Nitpicker
    (1, 4, (0x18, 0x20, 0x28, 0x98), (0x01, 0xFF), 0x40),  # polar bear
    (2, 5, (0xA0, 0xA4, 0xA8, 0x06), (0x01, 0xFF), 0x40),  # seal
    (5, 8, (0xAC, 0x12, 0x14), (0x01, 0xFF), 0x40),     # ice block, shards
    (8, 0x18, (0x10, 0x0E, 0x0C), (0x00, 0x80), 0x40),  # icicle stages
]


def normal_gameplay_sprites(original=None):
    """The VIC bank during normal play: the four Topi pages hold the stunned
    seal (WALK0 page with the original $06 art), then the ice block, the
    icicle stages and the ice shards, unmirrored and mirrored."""
    if original is None:
        original = (BASE/'c64/build/game_sprites.bin').read_bytes()
    stunned = (BASE/'c64/build/game_sprites_topi_stun.bin').read_bytes()
    metadata = json.loads((BASE/'c64/build/sprite_frames.json').read_text())
    walk0 = min(entry['pointer'] for entry in metadata if entry['name'] in ('TOPI_R_WALK0', 'TOPI_L_WALK0'))
    ice = (BASE/'c64/build/nes_ice_art.bin').read_bytes()
    result = bytearray(original)
    page = (TOPI_OVERLAY_PTR-0x40)*64
    result[page:page+256] = stunned[(walk0-0x40)*64:(walk0-0x40)*64+256]
    result[page+256:page+1024] = ice
    # The original death spin ($D086) lies over fruit 0 and 9.
    spin = (BASE/'c64/build/death_spin.bin').read_bytes()
    frames = {entry['name']: entry['pointer'] for entry in metadata}
    for pointer, data in ((frames['FRUIT_L_0_0_0'], spin[:128]), (frames['FRUIT_L_9_0_0'], spin[128:])):
        result[(pointer-0x40)*64:(pointer-0x40)*64+128] = data
    # The block debris (debris_scene_art) in the eight condor blocks: one
    # multicolour byte per row of each 8x8 piece, the rest clear.
    debris = (BASE/'c64/build/debris_art.bin').read_bytes()
    start = (frames['CONDOR_R_FLAP0_0_0']-0x40)*64
    result[start:start+512] = bytes(512)
    for piece in range(8):
        for row in range(8):
            result[start+piece*64+row*3] = debris[piece*8+row]
    return bytes(result)


def check_object_art(machine):
    tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000])
    r, L = machine.ram, machine.labels
    r[L['state']] = 1
    machine.call('normal_player_art')
    machine.call('topi_sprite_scene')
    pixels = cases = ice_pairs = ice_shadow_pairs = 0
    palette = PPU()
    palette.run_script(PRG[0x694:], 0)
    assert palette.pal[0x19:0x1C] == bytes((0x30, 0x21, 0x12))
    ice_colours = {0: 0, 1: 1, 2: 14, 3: 6}
    for obj, slot, tile_set, directions, flag in CASES:
        for tile in tile_set:
            for direction in directions:
                x, y = 120, 100
                for nes, value in ((0x91+obj, 0xFF), (0x9C+obj, x), (0xA7+obj, y),
                                   (0xBD+obj, direction), (0x03DD+obj, tile), (0x03E8+obj, slot | flag)):
                    r[map_ram(nes)] = value
                r[L['actor_mask']] = 255
                r[L['logical_count']] = 0
                r[L['view_delta']:L['view_delta']+2] = ARMED_VIEW_DELTA.to_bytes(2, 'little', signed=True)
                machine.x = obj
                machine.call('actor_nes_object')
                count = r[L['logical_count']]
                assert count, ('object not drawn', obj, hex(tile))
                facing = 1 if direction < 0x80 else 0
                source = source_pixels(tiles, source_oam(slot, tile, x, y, facing, flag))
                expected = {(sx+56, sy+18-SPRITE_VIEW_SHIFT) for sx, sy in source}
                drawn = c64_pixels(r, L, count)
                multicolour = any(r[L['LOG_MC']+i] for i in range(count))   # compare double-wide pixels
                if multicolour:
                    expected = {(px & ~1, py) for px, py in expected}
                    drawn = {(px & ~1, py) for px, py in drawn}
                else:
                    drawn = set(drawn)
                assert drawn == expected, ('object pixels', obj, hex(tile), direction,
                                           sorted(expected - drawn)[:6], sorted(drawn - expected)[:6])
                if obj >= 5:
                    # Decode the emitted VIC colours, independently of the
                    # asset converter. Equal NES pairs must keep their shade;
                    # mixed pairs may choose either occupied source pixel.
                    assert count == 1 and r[L['LOG_MC']] == 1
                    pointer = r[L['LOG_PTR']]
                    colours = (0, r[0xD025], r[L['LOG_COL']] & 15, r[0xD026])
                    for row in range(16):
                        for column in range(0, 8, 2):
                            pair = [source.get((x+column+dx, y+row), 0) for dx in (0, 1)]
                            allowed = {ice_colours[value] for value in pair if value} or {0}
                            packed = r[0x4000+pointer*64+row*3+column//8]
                            colour = colours[(packed >> (6-column%8)) & 3]
                            assert colour in allowed, ('ice shade', hex(tile), direction,
                                                       column, row, pair, colour, allowed)
                            ice_pairs += 1
                            ice_shadow_pairs += colour == 6
                pixels += len(expected)
                cases += 1
            for nes in (0x91+obj, 0x03E8+obj):
                r[map_ram(nes)] = 0
    overlay = normal_gameplay_sprites()
    assert r[0x5000:0x7000] == overlay, 'normal play shows other object pages'
    port = r[1]
    machine.call('enter_bonus')
    bonus = (BASE/'c64/build/game_sprites_bonus.bin').read_bytes()
    assert r[0x5000:0x7000] == bonus and r[1] == port, 'Bonus did not restore fruit and I/O'
    r[L['state']] = 1
    machine.call('setup_level')
    assert r[0x5000:0x7000] == overlay and r[1] == port, 'Next mountain did not load the object pages'
    machine.call('preview_init')
    normal = (BASE/'c64/build/game_sprites.bin').read_bytes()
    assert r[0x5000:0x7000] == normal and r[1] == port, 'Preview did not restore every fruit'
    machine.call('enter_title')
    assert r[0x5000:0x7000] == normal and r[1] == port, 'Title changed sprite or port contents'
    assert ice_pairs == 768 and ice_shadow_pairs > 0
    return dict(cases=cases, pixels=pixels, ice_colour_pairs=ice_pairs,
                ice_shadow_pairs=ice_shadow_pairs)


def check_topi_source_art(machine=None):
    """Kept for test_terrain: the object art in its scene lifecycle."""
    if machine is None:
        from test_game import start
        machine = start()
    return check_object_art(machine)


if __name__ == '__main__':
    from test_game import start
    print('PASS original object sprites against $EAFC', check_object_art(start()))
