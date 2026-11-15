#!/usr/bin/env python3
"""Run the NES mountain generator, then pack its two 24x9 block planes.

C5A7 generates the random lower ice, E4C2 decodes floor properties,
C542/C4D7 build the upper plane/rock walls, DFAB adds stone ledges.
The ROM routines execute unchanged, with a fixed five-byte LFSR seed.
The upper plane retains the original conditional stone post (raw4) as2;
its unused raw2 ice entry never occurs. The lower plane uses2 for short ice.
FF=air, 1=ice, 0/3=rock. Lower4 shares its upper post's conditional support.
Cloud, wind and conveyor descriptors remain separate from terrain.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bzk_parse import parse_project, build_images
from emulate_prg import CPU
from convert_terrain import packbits
from png import Canvas

BASE = Path(__file__).resolve().parents[1]
SEED = bytes.fromhex('a5 37 c9 51 82')
ROUTINES = (0xC5A7, 0xE4C2, 0xC542, 0xC4D7, 0xDFAB)


class Generator(CPU):
    def write(self, addr, value):
        assert addr < 0x0800, f'NES map generator wrote outside RAM: ${addr:04X}'
        super().write(addr, value)

    def call(self, addr):
        self.push(0xBF)
        self.push(0xFF)  # RTS to $C000, before executing its first instruction
        self.pc = addr
        for _ in range(100000):
            if self.pc == 0xC000:
                assert self.sp == 0xFD
                return
            self.step()
        raise RuntimeError(f'NES generator did not return: ${self.pc:04X}')


def generate(prg, mountain):
    ram = bytearray(65536)
    ram[0xC000:] = prg
    ram[0x59] = mountain
    ram[0x18:0x1D] = SEED
    cpu = Generator(ram, {})
    for routine in ROUTINES:
        cpu.call(routine)
    raw = bytes(ram[0x400:0x4D8] + ram[0x500:0x5D8])
    assert set(raw) <= {0, 1, 2, 3, 4, 255}
    assert 2 not in raw[:216], 'Upper plane value2 is reserved for conditional stone posts'
    cells = bytes(0 if c == 255 else 1 if c == 1 else 2 if c == 4 else 3
                  for c in raw[:216])
    cells += bytes(0 if c == 255 else c if c in (1, 2) else 3 for c in raw[216:])
    packed = bytes(sum(cells[i+j] << (j*2) for j in range(4))
                   for i in range(0, len(cells), 4))
    types = prg[0x2382+mountain*7:0x2389+mountain*7]
    return raw, cells, packed, types


def generate_bonus(prg, mountain):
    """Original $F2EC ledges, retaining unwrapped height across nametables."""
    ram = bytearray(65536)
    ram[0xC000:] = prg
    ram[0x59] = mountain
    ram[0x18:0x1D] = SEED
    ram[0x8D] = 1
    cpu = Generator(ram, {})
    platforms = []
    for row in range(62):
        ram[0x52] = ram[0x300] = 0  # consume the PPU buffer after each row
        before = ram[0x347]
        cpu.call(0xF2EC)
        for i in range(before, ram[0x347]):
            platforms.append(dict(left=ram[0x668+i], right=ram[0x686+i] or 256,
                                  height=row*8))
    start = prg[0x255A+(mountain & 7)]
    clouds = []
    while prg[0x2539+start] != 255:
        d = prg[0x2539+start]
        clouds.append(dict(descriptor=d, height=((d & 63)-1)*8,
                           speed=192 if d & 128 else 128,
                           direction=1 if d & 64 else -1,
                           width=32 if mountain & 4 else 48))
        start += 1
    assert len(platforms) <= 24 and len(clouds) <= 6
    return dict(platforms=platforms, clouds=clouds)


def main():
    # Rebuild from current disassembly rather than trusting stale extracted files.
    image = build_images(parse_project(BASE.parent))
    prg = bytes(image[0x10:0x4010])
    records = [generate(prg, m) for m in range(32)]
    target = BASE/'c64/build'
    target.mkdir(exist_ok=True, parents=True)
    (target/'nes_levels.bin').write_bytes(b''.join(v[2] for v in records))
    packed_levels, packed_offsets = bytearray(), []
    for record in records:
        packed_offsets.append(len(packed_levels))
        packed_levels.extend(packbits(record[2]+bytes(256-len(record[2]))))
    (target/'nes_levels.rle').write_bytes(packed_levels)
    (target/'nes_level_offsets.inc').write_text(''.join(
        ('.segment "CODE"\n' if operator == '<' else '.segment "DATA"\n')+
        label+':\n        .byte '+','.join(f'{operator}(levels_src+{offset})' for offset in packed_offsets)+'\n'
        for label, operator in (('level_ptr_lo', '<'), ('level_ptr_hi', '>'))))
    (target/'nes_floor_types.bin').write_bytes(b''.join(v[3] for v in records))
    # Respawn DEB9 distinguishes immutable raw3 ledges from raw0 rock.
    # Both render as packed3, so retain only their compact immutable spans.
    offsets, starts, lengths = bytearray([0]), bytearray(), bytearray()
    for raw, _, _, _ in records:
        for floor in range(9):
            row = raw[floor*24:(floor+1)*24]
            col = 0
            while col < 24:
                if row[col] != 3:
                    col += 1
                    continue
                end = col+1
                while end < 24 and row[end] == 3:
                    end += 1
                assert floor < 8 and len(starts) < 256
                starts.append(floor*32+col)
                lengths.append(end-col)
                col = end
        offsets.append(len(starts))
    assert len(starts) == 139 and max(lengths) <= 4
    packed_lengths = bytes(sum((lengths[i+j]-1) << (j*2)
                               for j in range(min(4, len(lengths)-i)))
                           for i in range(0, len(lengths), 4))
    (target/'nes_respawn_ledges.bin').write_bytes(offsets+starts+packed_lengths)
    bonus = [generate_bonus(prg, m) for m in range(8)]
    platform_blob, cloud_blob = bytearray(), bytearray()
    for variant in bonus:
        entry = bytearray([len(variant['platforms'])])
        for p in variant['platforms']:
            entry += bytes([p['left']//8+4, p['right']//8+4]) + p['height'].to_bytes(2, 'little')
        entry.extend(bytes(97-len(entry)))
        platform_blob += entry
        entry = bytearray([len(variant['clouds'])])
        for c in variant['clouds']:
            entry += c['height'].to_bytes(2, 'little') + bytes([c['speed'], c['direction'] & 255, c['width']])
        entry.extend(bytes(31-len(entry)))
        cloud_blob += entry
    (target/'nes_bonus_platforms.bin').write_bytes(platform_blob)
    (target/'nes_bonus_clouds.bin').write_bytes(cloud_blob)
    (target/'nes_bonus.json').write_text(json.dumps(bonus, indent=2)+'\n')
    manifest = dict(seed=SEED.hex(), routines=[f'${a:04X}' for a in ROUTINES],
                    upper_values={'0': 'air', '1': 'ice', '2': 'conditional stone post (NES4)', '3': 'stone'},
                    lower_values={'0': 'air', '1': 'ice', '2': 'short ice', '3': 'stone'},
                    prg_sha256=hashlib.sha256(prg).hexdigest(),
                    levels=[dict(mountain=m+1, floor_types=list(v[3]),
                                 raw_planes=v[0].hex(), cells=v[1].hex())
                            for m, v in enumerate(records)])
    (target/'nes_levels.json').write_text(json.dumps(manifest, indent=2)+'\n')
    # Overview: eight mountains per row; two pixel-high rows per floor.
    canvas = Canvas(8*104, 4*92, (10, 15, 25))
    colors = ((10, 15, 25), (120, 195, 255), (70, 135, 220), (160, 120, 75))
    for m, (_, cells, _, types) in enumerate(records):
        ox, oy = (m % 8)*104+4, (m//8)*92+4
        for floor in range(9):
            for layer in range(2):
                for col in range(24):
                    kind = cells[layer*216+floor*24+col]
                    for yy in range(2):
                        for xx in range(4):
                            canvas.px(ox+col*4+xx, oy+(8-floor)*10+layer*2+yy, colors[kind])
            if 1 <= floor <= 7 and types[floor-1] & 0xE0 >= 0xA0:
                for x in range(12, 32):
                    canvas.px(ox+x, oy+(8-floor)*10, (255, 255, 255))
    canvas.save(target/'nes_levels.png')
    print('NES mountains: 32 x 9 floors, 24 columns, two block planes; 3456 bytes + 224 floor descriptors')


if __name__ == '__main__':
    main()
