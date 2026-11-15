#!/usr/bin/env python3
"""Convert the original24-pixel cloud sprite into hires character phases.

The original $E6D7/$E4BB sequence is $DC,$FF,$FE for a capped cloud.
Other floor types replace the two inner caps by $FF, giving two joined
halves $DC/$FF/$FF and $FF/$FF/$FE. All three profiles are retained.
Both white face pixels and blue shadow pixels contribute to its silhouette;
transparent NES pixels remain transparent. The VIC character version is
white so it can share colour RAM with the sky on moving cloud rows.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nesgfx import chr_tiles
from png import Canvas

BASE = Path(__file__).resolve().parents[1]


def shifted_glyphs(rows):
    result = bytearray()
    for phase in range(8):
        for glyph in range(4):
            for y in range(8):
                byte = 0
                for bit in range(8):
                    source_x = glyph*8+bit-phase
                    if 0 <= source_x < 24 and rows[y][source_x]:
                        byte |= 0x80 >> bit
                result.append(byte)
    return bytes(result)


def main():
    source = (BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000]
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    tiles = chr_tiles(source)
    order = [prg[0x24BB+i] for i in (6, 5, 4)]
    assert order == [0xDC, 0xFF, 0xFE], 'Original cloud table changed'
    profiles = [[order[0], order[1], order[1]],
                [order[1], order[1], order[2]], order]
    masks, phases = bytearray(), bytearray()
    profile_rows = []
    for profile in profiles:
        rows = [[pixel for tile in profile for pixel in tiles[tile][y]] for y in range(8)]
        profile_rows.append(rows)
        for tile in profile:
            masks.extend(sum(bool(value) << (7-x) for x, value in enumerate(row))
                         for row in tiles[tile])
        phases.extend(shifted_glyphs(rows))
    assert len(masks) == 72 and len(phases) == 768
    target = BASE/'c64/build'
    target.mkdir(parents=True, exist_ok=True)
    (target/'original_cloud_phases.bin').write_bytes(phases)
    (target/'original_cloud_masks.bin').write_bytes(masks)
    # Gameplay does not use these characters as screen codes. The static
    # atlas keeps one copy of every distinct source glyph, including the
    # silhouette shared by the three cloud profiles.
    free = iter((*range(10, 21), *range(40, 52), *range(228, 249)))
    codes = {bytes(8): 255}
    layout = bytearray()
    for offset in range(0, len(phases), 8):
        glyph = bytes(phases[offset:offset+8])
        if glyph not in codes:
            codes[glyph] = next(free)
        layout.append(codes[glyph])
    assert len(codes) == 45
    (target/'normal_cloud_phase_codes.bin').write_bytes(layout)
    # The same entries as charset addresses (CHARSET $4800): 96 low bytes,
    # then 96 high bytes, for the unrolled glyph copy.
    addresses = [0x4800+code*8 for code in layout]
    (target/'normal_cloud_phase_addr.bin').write_bytes(
        bytes(a & 255 for a in addresses)+bytes(a >> 8 for a in addresses))
    (target/'original_cloud_art.json').write_text(json.dumps(dict(
        source_chr_sha256=hashlib.sha256(source).hexdigest(),
        source_routine='$E6D7', source_tile_table='$E4BB', tile_order=order,
        profiles=profiles, profile_order=['joined_left', 'joined_right', 'capped'],
        source_width=24, source_height=8, phases=8, glyphs_per_phase=4,
        masks_format='profile-major, three source glyphs, eight rows per glyph, MSB-first hires',
        phases_format='profile-major, phase-major, four glyphs, eight rows per glyph, MSB-first hires',
        mask_policy='NES0 transparent; every nonzero source pixel becomes white'),
        indent=2)+'\n', encoding='utf-8')
    # First row: original white/blue artwork. Following rows: the eight
    # white hires phases, with an exact one-source-pixel shift each row.
    scale = 6
    canvas = Canvas(3*32*scale, 9*10*scale, (0, 0, 0))
    palette = [(0, 0, 0), (255, 255, 255), (112, 109, 235), (46, 44, 155)]
    for profile, rows in enumerate(profile_rows):
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                for dy in range(scale):
                    for dx in range(scale):
                        canvas.px((profile*32+x)*scale+dx, y*scale+dy, palette[value])
        for phase in range(8):
            for y in range(8):
                for x in range(32):
                    if phases[profile*256+phase*32+(x//8)*8+y] & (0x80 >> (x%8)):
                        for dy in range(scale):
                            for dx in range(scale):
                                canvas.px((profile*32+x)*scale+dx, ((phase+1)*10+y)*scale+dy,
                                          (255, 255, 255))
    canvas.save(target/'original_cloud_art.png')
    print('Original clouds: three24-pixel profiles,72-byte masks,768-byte reference phases')


if __name__ == '__main__':
    main()
