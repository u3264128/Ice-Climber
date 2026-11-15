#!/usr/bin/env python3
"""Execute the original death/respawn code, then compare C64 floor/Y/X.

Includes solid and blank fixtures, all32 actual maps, stone-ledge provenance,
the original two active cloud slots, and all256 old horizontal positions.
"""
import hashlib
import json

from extract_levels import BASE, Generator
from test_original_levels import reference_planes


class Reference(Generator):
    def __init__(self, ram):
        super().__init__(ram, {})
        self.camera_writes = []

    def write(self, address, value):
        if address in (0x13, 0x90):
            self.camera_writes.append((self.pc, address, value))
        super().write(address, value)


def source_case(prg, player, upper, scroll, floor=None, physical_py=None, solid=True,
                old_x=64, raw_planes=None, cloud_slots=(0, 0)):
    r = bytearray(65536)
    r[0xC000:] = prg
    r[0x400:0x600] = bytes([1 if solid else 255])*512
    if raw_planes is not None:
        r[0x400:0x4D8] = raw_planes[:216]
        r[0x500:0x5D8] = raw_planes[216:]
    r[0x55], r[0x90], r[0x13] = 1, upper, scroll
    r[0x20+player], r[0x5A+player], r[0x64+player] = 3, floor or 1, old_x
    r[0x786:0x788] = bytes(cloud_slots)
    c = Reference(r)
    if physical_py is not None:
        r[0x66+player] = (physical_py-24) & 255
        c.call(0xD1E5)
    death_floor = r[0x5A+player]
    c.x = player
    c.call(0xD446)
    assert r[0x382+player] == death_floor
    assert r[0x6A+player] == 7
    r[0x66+player] = 220  # Source bottom-band death collection.
    c.call(0xD463)
    assert r[0x5A+player] == 0 and r[0x20+player] == 2
    r[0x3F+player] = 0  # Expired respawn timer; no change to its policy.
    c.x = player
    c.call(0xEB8A)
    expected_floor = min(max(death_floor, upper-3), upper-1)
    while expected_floor in cloud_slots:
        expected_floor -= 1
        if expected_floor < upper-3:
            expected_floor += 3
    assert r[0x5A+player] == expected_floor
    assert r[0x66+player] == 48*(upper-expected_floor+1)
    assert (r[0x90], r[0x13]) == (upper, scroll)
    assert not c.camera_writes
    return dict(death_floor=death_floor, floor=r[0x5A+player],
                body_y=r[0x66+player], x=r[0x64+player], lives=r[0x20+player])


def source_tests(prg):
    count = 0
    for player in (0, 1):
        for upper in range(4, 10):
            for floor in range(1, 10):
                for scroll in (0, 15, 63, 111, 159, 207, 239):
                    source_case(prg, player, upper, scroll, floor=floor)
                    count += 1
    return count


def paired_tests(prg):
    from plan_mountains import PlanningMachine, clone
    template = PlanningMachine()
    labels = template.labels
    count = empty = overflow = 0
    examples = []
    physical_values = (0, 8, 23, 24, 73, 74, 121, 122, 169, 170, 217, 218, 240, 245, 255)

    def prepare(mode, player, cam, py, maximum, solid, old_x=64):
        m = clone(template)
        r = m.ram
        r[0x400:0x600] = bytes([1 if solid else 0])*512
        r[0x600:0x609] = bytes(9)
        for name, value in dict(state=1, mountain=1, player_count=mode,
                                player_index=player, lives=3, cam=cam,
                                curfloor=cam, maxfloor=maximum, py=py,
                                normal_pan_t=0, normal_pan_request=0,
                                score_lo=0, score_hi=0, score_top=0).items():
            r[labels[name]] = value
        for name in ('normal_camera', 'visual_camera', 'target_camera'):
            r[labels[name]:labels[name]+2] = (cam*48).to_bytes(2, 'little')
        r[labels['normal_pan_high']:labels['normal_pan_high']+2] = bytes(2)
        r[labels['pxlo']:labels['pxlo']+2] = (old_x+52).to_bytes(2, 'little')
        return m

    def verify_camera(m, cam, terrain):
        r = m.ram
        assert r[labels['cam']] == cam, ('logical camera moved', cam, r[labels['cam']])
        for name in ('normal_camera', 'visual_camera', 'target_camera'):
            assert int.from_bytes(r[labels[name]:labels[name]+2], 'little') == cam*48, name
        assert r[labels['normal_pan_t']] == 0
        assert r[0x400:0x600] == terrain, 'Respawn changed the map'
        assert r[labels['lives']] == 2 and r[labels['state']] == 1
        assert r[labels['score_lo']] == r[labels['score_hi']] == r[labels['score_top']] == 0

    for mode, player in ((1, 0), (2, 0), (2, 1)):
        for cam in range(6):
            for py in physical_values:
                expected = source_case(prg, player, cam+4, (159-cam*48) % 240,
                                       physical_py=py)
                for maximum in (0, 3, 8):
                    m = prepare(mode, player, cam, py, maximum, True)
                    r = m.ram
                    terrain = bytes(r[0x400:0x600])
                    m.call('player_died')
                    verify_camera(m, cam, terrain)
                    assert r[labels['curfloor']] == expected['floor']-1, (mode, player, cam, py, maximum, expected)
                    assert r[labels['py']] == expected['body_y']+24, (mode, player, cam, py, maximum, expected)
                    assert int.from_bytes(r[labels['pxlo']:labels['pxlo']+2], 'little') == expected['x']+52
                    assert r[labels['normal_pan_high']+player] == 0
                    count += 1
                    if mode == 1 and cam == 0 and maximum == 3 and py in (72, 168, 216):
                        examples.append(dict(maxfloor=maximum, physical_py=py,
                                             source_death_floor=expected['death_floor'],
                                             respawn_floor=r[labels['curfloor']],
                                             respawn_py=r[labels['py']], camera=cam))
            for py in (72, 168, 216):
                expected = source_case(prg, player, cam+4, (159-cam*48) % 240,
                                       physical_py=py, solid=False)
                for maximum in (0, 3, 8):
                    m = prepare(mode, player, cam, py, maximum, False)
                    r = m.ram
                    terrain = bytes(r[0x400:0x600])
                    m.call('player_died')
                    verify_camera(m, cam, terrain)
                    assert r[labels['curfloor']] == expected['floor']-1
                    assert r[labels['py']] == expected['body_y']+24
                    x = int.from_bytes(r[labels['pxlo']:labels['pxlo']+2], 'little')
                    assert x == 216+52, ('empty map right wall', mode, player, cam, x)
                    empty += 1
            for wrapped_py in (0, 8, 23):
                m = prepare(mode, player, cam, wrapped_py, 8, True)
                r = m.ram
                r[labels['normal_pan_high']+player] = 1
                terrain = bytes(r[0x400:0x600])
                m.call('player_died')
                verify_camera(m, cam, terrain)
                assert r[labels['curfloor']] == cam and r[labels['py']] == 216
                assert r[labels['normal_pan_high']+player] == 0
                overflow += 1
    real = paired_real_maps(prg, template, prepare, verify_camera)
    return dict(paired_solid_cases=count, paired_blank_cases=empty,
                wrapped_body_camera_cases=overflow, examples=examples,
                maxfloor_does_not_select_respawn=True, terrain_preserved=True,
                blank_map_search_policy='exact EBFE rightward probe, retaining its floor', **real)


def source_cloud_states(prg, mountain):
    """Independent source fixture: actual cloud init and twelve-step pan chain."""
    r = bytearray(65536)
    r[0xC000:] = prg
    r[0x55], r[0x59], r[0x90] = 1, mountain, 4
    c = Generator(r, {})
    c.call(0xC81D)
    c.call(0xE4C2)
    states = [tuple(r[0x786:0x788])]
    for cam in range(1, 6):
        r[0x90] = cam+4
        for _ in range(12):
            c.call(0xE27A)
            c.call(0xEC51)
        c.call(0xE63D)
        states.append(tuple(r[0x786:0x788]))
    return states


def paired_real_maps(prg, template, prepare, verify_camera):
    labels = template.labels
    levels = [reference_planes(prg, mountain) for mountain in range(32)]
    slots = [source_cloud_states(prg, mountain) for mountain in range(32)]
    # Every map/camera/physical-floor band plus every pixel of oldX for three
    # representative stone/cloud layouts. Source state is reused only across
    # 1P/2P comparisons; no C64 expected placement is synthesized.
    fixtures = {(mountain, cam, py, x) for mountain in range(32) for cam in range(6)
                for py in (72, 168, 216) for x in (0, 31, 32, 63, 127, 215, 216, 255)}
    fixtures.update((mountain, cam, py, x) for mountain in (0, 2, 23)
                    for cam in (0, 2, 5) for py in (72, 168, 216) for x in range(256))
    count = 0
    for mountain, cam, py, old_x in sorted(fixtures):
        raw, descriptors, _ = levels[mountain]
        expected = source_case(prg, 0, cam+4, (159-cam*48) % 240,
                               physical_py=py, old_x=old_x, raw_planes=raw,
                               cloud_slots=slots[mountain][cam])
        packed_upper = bytes(0 if v == 255 else 1 if v == 1 else 2 if v == 4 else 3
                             for v in raw[:216])
        packed_lower = bytes(0 if v == 255 else v if v in (1, 2) else 3 for v in raw[216:])
        for mode, player in ((1, 0), (2, 1)):
            m = prepare(mode, player, cam, py, 8, True, old_x)
            r = m.ram
            r[labels['mountain']] = mountain+1
            r[labels['levelidx']] = mountain  # invariant established by real init_floors
            r[0x400:0x4D8], r[0x500:0x5D8] = packed_upper, packed_lower
            r[0x601:0x608] = descriptors
            terrain = bytes(r[0x400:0x600])
            m.call('player_died')
            verify_camera(m, cam, terrain)
            got = dict(floor=r[labels['curfloor']]+1, body_y=r[labels['py']]-24,
                       x=int.from_bytes(r[labels['pxlo']:labels['pxlo']+2], 'little')-52)
            assert all(got[k] == expected[k] for k in got), (mountain+1, cam, py, old_x,
                                                           mode, slots[mountain][cam], got, expected)
            count += 1
    visible_masks = [[sum(1 << (f-1) for f in set(state) if f) >> cam & 7
                      for cam, state in enumerate(stage)] for stage in slots]
    masks = bytes(stage[cam] | stage[cam+1] << 3 for stage in visible_masks for cam in (0, 2, 4))
    assert (BASE/'c64/build/nes_respawn_cloud_masks.bin').read_bytes() == masks
    return dict(real_map_source_cases=len(fixtures), paired_real_map_cases=count,
                source_cloud_camera_states=192, all_horizontal_positions=True,
                real_mountains=32, source_ledge_provenance=True,
                mountain26_camera2_cloud_slots=list(slots[25][2]))


def main():
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    count = source_tests(prg)
    paired = paired_tests(prg)
    report = dict(status='passed', source_camera_cases=count,
                  source_camera_writes=0,
                  routines=['D1E5', 'D446', 'D463', 'EB8A', 'EDD5'],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                  original_prg_sha256=hashlib.sha256(prg).hexdigest(), **paired)
    (BASE/'docs/verification/original_respawn.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS original respawn:', count, 'source camera cases;',
          paired['paired_solid_cases'], 'paired solid cases;',
          paired['paired_blank_cases'], 'blank and',
          paired['wrapped_body_camera_cases'], 'wrapped body cases;',
          paired['paired_real_map_cases'], 'exact floor/Y/X comparisons on all32 maps', flush=True)


if __name__ == '__main__':
    main()
