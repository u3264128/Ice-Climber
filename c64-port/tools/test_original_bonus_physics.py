#!/usr/bin/env python3
"""Bonus jump/contact fixtures against executed CE43/D552/D59C/D6E0."""
import argparse
import hashlib
import json

from test_game import BASE, start
from test_original_physics import Reference, PRG


def source_record(left, right, cloud=False):
    c = Reference()
    r = c.ram
    slot = 26 if cloud else 0
    r[0x6E0:0x6FE] = bytes([128])*30
    r[0x6E0+slot], r[0x668+slot], r[0x686+slot] = 0, left, right & 255
    r[0x6A4+slot], r[0x6C2+slot] = 120, 125 if cloud else 123
    return c, slot


def source_contact(c, slot, x, delta=0, head=False):
    r = c.ram
    r[0x64], r[0x66], r[0x6A], r[0x783], r[0x352] = x, 95+delta, 2, 255, 0
    r[0xE6], r[0xE8] = (2, 99) if head else (3, 99)
    if head:
        r[0x0B] = (123 if slot == 26 else 121)+delta
        r[0x2A] = 0
        c.call(0xD6E0)
        return (r[0xE6], r[0xE8]) == (4, 32)
    c.call(0xD59C)
    return r[0x783] == slot


def target_record(m, left, right, cloud=False):
    r, L = m.ram, m.labels
    r[L['bonus_camera']:L['bonus_camera']+2] = bytes(2)
    r[L['bonus_platform_count']], r[L['bonus_cloud_count']] = (0, 1) if cloud else (1, 0)
    if cloud:
        r[L['bonus_cloud_hlo']], r[L['bonus_cloud_hhi']] = 96, 0
        r[L['bonus_cloud_x']], r[L['bonus_cloud_width']] = left, (right-left) & 255
        r[L['bonus_cloud_motion']] = 0
    else:
        r[L['BONUS_LEDGE_L']], r[L['BONUS_LEDGE_R']] = left//8+4, right//8+4
        r[L['BONUS_LEDGE_HLO']], r[L['BONUS_LEDGE_HHI']] = 96, 0
    m.call('bonus_height_index')  # rebuild immutable fixtures, exercising the indexed query
    m.call('bonus_cloud_height_index')


def target_contact(m, x, delta=0, head=False, cloud=False):
    r, L = m.ram, m.labels
    r[L['pxlo']:L['pxhi']+1] = (x+52).to_bytes(2, 'little')
    r[L['py']] = (120+delta) if not head else (148 if cloud else 146)+delta
    r[L['prevpy']] = (r[L['py']]-1) & 255
    r[L['bonus_support_mode']] = 2 if head else 1
    r[L['fall_int']], r[L['fall_frac']] = (2, 99) if head else (3, 99)
    m.call('bonus_find_support')
    if head:
        assert bool(r[L['bonus_support']]) == ((r[L['fall_int']], r[L['fall_frac']]) == (4, 32))
    return bool(r[L['bonus_support']])


def check_contacts(source_only=False):
    m = None if source_only else start()
    if m:
        m.call('enter_bonus')
    cases = 0
    records = [(left, right, False) for left, right in ((8, 56), (48, 80), (80, 128), (200, 256))]
    records += [(left, left+width, True) for left in (0, 1, 7, 8, 80, 224, 232, 240, 248) for width in (32, 48)]
    for left, right, cloud in records:
        ref, slot = source_record(left, right, cloud)
        if m:
            target_record(m, left, right, cloud)
        for head in (False, True):
            for x in range(256):
                expected = source_contact(ref, slot, x, head=head)
                if m:
                    actual = target_contact(m, x, head=head, cloud=cloud)
                    assert actual == expected, ('bonus X interval', left, right, cloud, head, x, actual, expected)
                cases += 1
    for cloud in (False, True):
        ref, slot = source_record(80, 128, cloud)
        if m:
            target_record(m, 80, 128, cloud)
        for head in (False, True):
            for delta in range(-3, 8):
                expected = source_contact(ref, slot, 88, delta, head)
                assert expected == (0 <= delta <= (3 if head else 4)), ('source Y window', cloud, head, delta)
                if m:
                    assert target_contact(m, 88, delta, head, cloud) == expected, ('bonus Y window', cloud, head, delta)
                cases += 1
    return cases


def check_jump(source_only=False):
    # Normal A has no entry lift; bonus A has the source's extra one pixel.
    for state in (1, 2):
        c = Reference()
        c.ram[0x55], c.ram[0x70], c.ram[0x66] = state, 128, 180
        c.call(0xCE43)
        assert c.ram[0x66] == 180-(state == 2)
    landings = []
    for direction in (1, 2):
        c = Reference()
        r = c.ram
        r[0x6E0:0x6FE] = bytes([128])*30
        current = (56, 96) if direction == 1 else (160, 200)
        target = (80, 128) if direction == 1 else (128, 176)
        for slot, (left, right), top, page in ((0, current, 16, 1), (1, target, 216, 0)):
            r[0x668+slot], r[0x686+slot], r[0x6A4+slot], r[0x6C2+slot], r[0x6E0+slot] = left, right, top, top+3, page
        x = 64 if direction == 1 else 177
        r[0x55], r[0x13], r[0x66], r[0x64], r[0x6A] = 2, 100, 147, x, 1
        r[0x68], r[0x6E], r[0x62], r[0x70], r[0x14] = direction, 24, 2-direction, 128 | direction, direction
        m = None if source_only else start()
        if m:
            m.call('enter_bonus')
            a, L = m.ram, m.labels
            a[L['bonus_platform_count']], a[L['bonus_cloud_count']] = 2, 0
            for slot, edges, height in ((0, current, 200), (1, target, 256)):
                a[L['BONUS_LEDGE_L']+slot], a[L['BONUS_LEDGE_R']+slot] = edges[0]//8+4, edges[1]//8+4
                a[L['BONUS_LEDGE_HLO']+slot], a[L['BONUS_LEDGE_HHI']+slot] = height & 255, height >> 8
            m.call('bonus_height_index')
            a[L['bonus_camera']:L['bonus_camera']+2] = (156).to_bytes(2, 'little')
            a[L['py']], a[L['prevpy']], a[L['onground']], a[L['move_dir']] = 172, 172, 1, direction
            a[L['pxlo']:L['pxhi']+1] = (x+52).to_bytes(2, 'little')
            a[L['walk_time']], a[L['skid_t']], a[L['walk_frac']], a[L['air_xfrac']] = 24, 0, 0, 0
            a[L['face']], a[L['joy']], a[L['firehit']] = direction-1, 0xF6 if direction == 1 else 0xFA, 1
            m.call('bonus_player_tick')
        c.call(0xCDB0)
        c.call(0xD59C)
        assert r[0x66] == 146
        for tick in range(1, 61):
            r[0x70] = 0
            c.call(0xD552)
            c.call(0xD59C)
            if m:
                a[L['firehit']], a[L['joy']] = 0, 0xF7 if direction == 1 else 0xFB
                m.call('bonus_player_tick')
                assert a[L['py']] == r[0x66]+25, ('56px jump Y', direction, tick, a[L['py']], r[0x66])
                assert int.from_bytes(a[L['pxlo']:L['pxhi']+1], 'little') == r[0x64]+52, ('56px jump X', direction, tick)
                assert bool(a[L['onground']]) == (r[0x6A] in (1, 3)), ('56px landing', direction, tick)
            if r[0x6A] in (1, 3):
                assert r[0x66] == 91
                landings.append(tick)
                break
        else:
            raise AssertionError(('could not land56px jump', direction))
    return dict(source_entry='$CE43', source_movement='$D552', source_contact='$D59C',
                normal_jump_peak=51, bonus_jump_peak=52, climbed_height=56,
                landing_ticks_both_directions=landings)


def check_actual_entries(source_only=False):
    """A straight first jump really does hit the original32px ledge."""
    from extract_levels import Generator, SEED
    checked = 0
    for mountain in range(8):
        data = bytearray(65536)
        data[0xC000:] = PRG
        data[0x59], data[0x8D] = mountain, 1
        data[0x18:0x1D] = SEED
        generator = Generator(data, {})
        for _ in range(62):
            data[0x52] = data[0x300] = 0
            generator.call(0xF2EC)
        reference = Reference()
        r = reference.ram
        r[0x668:0x6FE] = data[0x668:0x6FE]
        r[0x55], r[0x27], r[0x66], r[0x64], r[0x6A], r[0x70] = 2, 1, 207, 48, 1, 128
        m = None if source_only else start(mountain=mountain+1)
        if m:
            m.call('enter_bonus')
            a, L = m.ram, m.labels
            a[L['joy']], a[L['firehit']] = 0xFE, 1
            m.call('bonus_player_tick')
        reference.call(0xCDB0)
        reference.call(0xD59C)
        heights = [207-r[0x66]]
        if m:
            assert 216-a[L['py']] == heights[-1]
        for tick in range(8):
            r[0x70] = 0
            reference.call(0xD552)
            reference.call(0xD59C)
            heights.append(207-r[0x66])
            if m:
                a[L['joy']], a[L['firehit']] = 255, 0
                m.call('bonus_player_tick')
                assert 216-a[L['py']] == heights[-1], ('actual bonus entry', mountain, tick, a[L['py']], heights)
                assert (a[L['fall_int']], a[L['fall_frac']]) == (r[0xE6], r[0xE8])
            checked += 1
        assert heights == [1, 4, 4, 3, 2, 1, 0, 0, 0], ('original entry trajectory', mountain, heights)
    return dict(variants=8, compared_air_ticks=checked,
                pure_up_heights=[1, 4, 4, 3, 2, 1, 0, 0, 0],
                first_ledge_requires_side_launch=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-only', action='store_true')
    args = parser.parse_args()
    report = dict(status='source-passed' if args.source_only else 'passed',
                  contacts=check_contacts(args.source_only), jump=check_jump(args.source_only),
                  actual_entries=check_actual_entries(args.source_only),
                  nes_prg_sha256=hashlib.sha256(PRG).hexdigest())
    if not args.source_only:
        report['prg_sha256'] = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
        (BASE/'docs/verification/original_bonus_physics.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
