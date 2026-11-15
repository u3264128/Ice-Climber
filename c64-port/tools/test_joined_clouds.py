#!/usr/bin/env python3
"""Moving clouds keep the original silhouette in every position.

On the NES a cloud floor is two 24-pixel sprite clouds. Joined floors put
them 24 pixels apart ($E8/$00), or 8 pixels apart on type C0 ($E8/$F0),
so their sprites overlap one character cell, and the NES shows both there.
The port draws clouds with character codes, so the cell needs a glyph that
shows both. Without it, the second cloud cut 1-7 pixels from the first one
and a gap opened and closed in the middle of the cloud.

This test moves the real routines through a full 256-pixel cycle for each
floor type and direction. After every tick it renders the cached cloud row
from its codes and the phase glyphs, and compares it with the union of the
original sprite masks. Cells with terrain (walls) are skipped, because the
original sprites lie behind the background there.
"""
from test_game import BASE, start
from test_scroll_cloud_edges import GLYPH_PHASE2, original_cloud_mask, paint_floor_clouds

FLOOR = 4
CLOUD_FIRST, CLOUD_SECOND, BLANK = 56, 84, 255
WORLD_CACHE = 0xE000
# One descriptor per cloud class (24 px joined, 8 px joined, capped), both
# directions (bit 4) and several speeds, including mountain 2's $A1.
TYPES = (0x60, 0x75, 0x86, 0x94, 0xA1, 0xB3, 0xC5, 0xD4, 0xC0, 0xE6, 0xF0)


def silhouette(profile):
    """Eight 24-bit rows of an original cloud profile."""
    mask = original_cloud_mask(profile, 0)
    return [int.from_bytes(bytes(mask[g*8+y] for g in range(3)), 'big') for y in range(8)]


def expected_row(clouds):
    """Union of the clouds' sprite pixels: 8 rows of 256 booleans."""
    rows = [[False]*256 for _ in range(8)]
    for x, profile in clouds:
        for y, bits in enumerate(silhouette(profile)):
            for i in range(24):
                if bits >> (23-i) & 1:
                    rows[y][(x+i) & 255] = True
    return rows


def glyph(code, profiles, phases):
    if code == BLANK:
        return bytes(8)
    first = CLOUD_FIRST+4*(FLOOR-1)
    second = CLOUD_SECOND+4*(FLOOR-1)
    for base, profile, phase in ((first, profiles[0], phases[0]),
                                 (second, profiles[1], phases[1])):
        if base <= code < base+4:
            role = code-base
            return original_cloud_mask(profile, phase)[role*8:role*8+8]
    raise AssertionError(('foreign cloud code in the cloud row', code))


def check_type(machine, descriptor):
    ram, labels = machine.ram, machine.labels
    machine.ram[labels['mountain']] = 2
    machine.call('setup_level')
    ram[labels['state']] = 1
    ram[labels['paused']] = 1
    floors = labels['floor_types']
    ram[floors:floors+9] = bytes(9)
    ram[floors+FLOOR] = descriptor
    machine.call('normal_cloud_init')
    paint_floor_clouds(machine, FLOOR)
    profiles = (2, 2) if descriptor & 0xE0 == 0xE0 else (0, 1)
    row = WORLD_CACHE+(FLOOR*6+2)*32
    ram[labels['last_view_row']] = 0     # the floor is on (or above) the screen
    cloud_x, subpixel = labels['cloud_x'], labels['cloud_subpixel']
    start_x = [((ram[cloud_x+FLOOR+k]-4)*8+ram[subpixel+FLOOR+k]) & 255 for k in (0, 8)]
    distance = (start_x[1]-start_x[0]) & 255
    travelled = ticks = cells = 0
    shared = 0
    previous = start_x[0]
    while travelled < 264:
        xs = [((ram[cloud_x+FLOOR+k]-4)*8+ram[subpixel+FLOOR+k]) & 255 for k in (0, 8)]
        assert (xs[1]-xs[0]) & 255 == distance, ('clouds drifted apart', descriptor, xs)
        phases = (ram[labels['GLYPH_PHASE']+FLOOR], ram[GLYPH_PHASE2+FLOOR])
        assert phases == (xs[0] & 7, xs[1] & 7), ('stale glyph phase', descriptor, xs, phases)
        want = expected_row(list(zip(xs, profiles)))
        alone = [expected_row([(x, profile)]) for x, profile in zip(xs, profiles)]
        codes = ram[row:row+32]
        for cell, code in enumerate(codes):
            if code != BLANK and not CLOUD_FIRST <= code < CLOUD_SECOND+28:
                continue            # terrain in front of the original sprites
            shown = glyph(code, profiles, phases)
            for y in range(8):
                bits = ''.join('1' if want[y][cell*8+i] else '0' for i in range(8))
                assert shown[y] == int(bits, 2), (
                    'cloud pixels differ from the original sprites', hex(descriptor),
                    dict(tick=ticks, cell=cell, row=y, x=xs, code=code,
                         shown=f'{shown[y]:08b}', original=bits))
            cells += 1
            if all(any(own[y][cell*8+i] for y in range(8) for i in range(8)) for own in alone):
                shared += 1     # both original clouds have pixels in this cell
        machine.call('cloud_update')
        ticks += 1
        now = ((ram[cloud_x+FLOOR]-4)*8+ram[subpixel+FLOOR]) & 255
        step = (now-previous) & 255
        travelled += min(step, 256-step)
        previous = now
        assert ticks < 2000, ('cloud did not move', hex(descriptor))
    return dict(descriptor=f'${descriptor:02X}', distance=distance, ticks=ticks,
                cells=cells, shared_cells=shared)


def main():
    machine = start(mountain=2)
    results = [check_type(machine, descriptor) for descriptor in TYPES]
    for result in results:
        assert result['distance'] in (8, 24) or result['descriptor'] in ('$E6', '$F0'), result
    joined = [r for r in results if r['distance'] in (8, 24)]
    assert all(r['shared_cells'] > r['ticks']//4 for r in joined), joined
    for result in results:
        print(result)
    print(f'PASS joined clouds: {len(results)} floor types, '
          f'{sum(r["ticks"] for r in results)} ticks and '
          f'{sum(r["cells"] for r in results)} cloud-row cells equal the original sprite union')


if __name__ == '__main__':
    main()
