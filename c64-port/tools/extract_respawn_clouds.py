#!/usr/bin/env python3
"""Execute the original two cloud-slot lifecycle for each normal camera.

E4C2 fills the two slots from floors5..1. Each real normal pan runs E27A
(retire offscreen slots), EC51 (move their OAM four pixels) twelve times,
then E63D (create the next upcoming cloud). EB8A consults these two IDs.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bzk_parse import build_images, parse_project
from extract_levels import BASE, Generator, SEED


def cloud_slot_masks(prg, mountain):
    r = bytearray(65536)
    r[0xC000:] = prg
    r[0x18:0x1D] = SEED
    r[0x55], r[0x59], r[0x90] = 1, mountain, 4
    c = Generator(r, {})
    c.call(0xC81D)
    c.call(0xE4C2)
    rows = []
    for cam in range(6):
        if cam:
            r[0x90] = cam+4
            for _ in range(12):
                c.call(0xE27A)
                c.call(0xEC51)
            c.call(0xE63D)
        slots = list(r[0x786:0x788])
        assert all(0 <= f <= 8 for f in slots)
        mask = sum(1 << (floor-1) for floor in set(slots) if floor)
        rows.append(dict(camera=cam, slots=slots, mask=mask, visible_mask=(mask >> cam) & 7))
    return rows


def main():
    prg = bytes(build_images(parse_project(BASE.parent))[0x10:0x4010])
    stages = [cloud_slot_masks(prg, mountain) for mountain in range(32)]
    target = BASE/'c64/build'
    packed = bytes(stage[cam]['visible_mask'] | stage[cam+1]['visible_mask'] << 3
                   for stage in stages for cam in (0, 2, 4))
    (target/'nes_respawn_cloud_masks.bin').write_bytes(packed)
    (target/'nes_respawn_cloud_masks.json').write_text(json.dumps(stages, indent=2)+'\n')
    print('Original respawn cloud masks:', len(stages)*6, 'executed stage/camera states;', len(packed), 'bytes')
    print('Mountain26 camera2:', stages[25][2])


if __name__ == '__main__':
    main()
