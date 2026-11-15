#!/usr/bin/env python3
"""Independent table-based audit of all original normal-stage maps.

Unlike the build extractor this never calls the NES map generator. It
decodes the original bit patterns, LFSR, descriptors, rock boundaries and
stone-ledge records directly, then checks the executed NES output and PRG.
"""
import hashlib
import json

from extract_levels import SEED, generate
from test_game import BASE, Machine


def reference_planes(prg, mountain):
    def table(address, count):
        return prg[address-0xC000:address-0xC000+count]

    descriptors = table(0xE382+mountain*7, 7)
    random = bytearray(SEED)
    lower = bytearray([255]*216)
    masks = table(0xC59F, 8)
    for floor in range(8, -1, -1):
        # $CACE: five-byte ROR with the bit1 xor feedback (zero first
        # byte is treated as $37 when deriving its feedback).
        carry = (((random[0] or 0x37) ^ random[1]) >> 1) & 1
        for i, value in enumerate(random):
            random[i], carry = (value >> 1) | (carry << 7), value & 1
        bits = bytes(masks[value & 7] for value in random[:3])
        previous = False
        for column in range(23, -1, -1):
            occupied = bool(bits[column//8] & (0x80 >> (column & 7)))
            lower[floor*24+column] = 1 if occupied and previous else 2 if occupied or previous else 255
            previous = occupied

    upper = bytearray([255]*216)
    patterns = table(0xC512, 48)
    vertical = [table(address+(mountain & 15), 1)[0]
                for address in (0xE492, 0xE482, 0xE472, 0xE462)]
    for floor in range(8):
        pattern = 1 if floor == 0 else sum(((value >> (7-floor)) & 1) << bit
                                         for bit, value in enumerate(vertical))
        descriptor = 0 if floor == 0 else descriptors[floor-1]
        if descriptor & 0xE0 >= 0xA0:
            pattern = 0
        row_bits = patterns[pattern*3:pattern*3+3]
        for column in range(24):
            if row_bits[column//8] & (0x80 >> (column & 7)):
                upper[floor*24+column] = 0 if descriptor & 8 else 1
                if descriptor & 8:
                    lower[floor*24+column] = 255
            else:
                lower[floor*24+column] = 255
    upper[192:] = bytes(24)
    lower[192:] = bytes([255]*24)
    for column in (3, 4, 11, 12, 19, 20):
        upper[192+column] = 255
    for floor in range(2, 8):
        for column in (0, 23):
            upper[floor*24+column] = 0
        if floor >= 5:
            for column in (1, 22):
                upper[floor*24+column] = 0

    ledges = []
    starts = table(0xDEFA, 33)
    for index in range(starts[mountain+1], starts[mountain], -1):
        descriptor = table(0xDF1B+index, 1)[0]
        floor = (descriptor >> 5)-1
        column = (descriptor & 31)-1
        assert 0 <= floor < 8 and 0 <= column < 22, (mountain, index, descriptor)
        for dx in range(3):
            upper[floor*24+column+dx] = 3
        upper[(floor+1)*24+column+1] = 4
        lower[(floor+1)*24+column+1] = 4
        ledges.append(dict(floor=floor, left_column=column, post_floor=floor+1,
                           post_column=column+1))
    return bytes(upper+lower), bytes(descriptors), ledges


def main():
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    machine = Machine()
    reports = []
    for mountain in range(32):
        expected, descriptors, ledges = reference_planes(prg, mountain)
        actual, cells, _, extracted_types = generate(prg, mountain)
        assert actual == expected, ('source map mismatch', mountain+1,
                                    [(i, a, b) for i, (a, b) in enumerate(zip(actual, expected)) if a != b][:8])
        assert extracted_types == descriptors
        machine.ram[machine.labels['mountain']] = mountain+1
        machine.call('setup_level')
        assert machine.ram[0x400:0x4D8] == cells[:216]
        assert machine.ram[0x500:0x5D8] == cells[216:]
        assert machine.ram[0x601:0x608] == descriptors
        posts = [i for i, value in enumerate(expected[:216]) if value == 4]
        assert all(cells[index] == 2 for index in posts), ('stone post tag lost', mountain+1)
        reports.append(dict(mountain=mountain+1, upper_sha256=hashlib.sha256(expected[:216]).hexdigest(),
                            lower_sha256=hashlib.sha256(expected[216:]).hexdigest(),
                            floor_types=list(descriptors), conditional_posts=posts, stone_ledges=ledges))
    result = dict(status='passed', independent_reference='original ROM bit tables and LFSR; no CPU generator calls',
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                  levels=reports)
    (BASE/'docs/verification/original_levels_regression.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS independent original bit tables, random lower ice, rock ledges and conditional posts for all32 mountains')


if __name__ == '__main__':
    main()
