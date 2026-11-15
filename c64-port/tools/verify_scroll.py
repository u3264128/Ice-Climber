#!/usr/bin/env python3
"""Check displayed VIC scrolling once per PAL frame in the release PRG.

Geometry is recovered from the D018-selected screen and the D011 fine scroll
after the actual frame IRQ. Controlled bonus positions keep both players,
four fruit and the condor visible, within the real camera limit of 256.
Every committed screen is also compared with all 25 world-cache rows.
"""
from tool_paths import add_vice_argument
import argparse
from collections import Counter
import hashlib
import json

from measure_display_scroll import bonus, normal, normal_coop_pan, normal_route
from vice_session import BASE


def check_normal(samples):
    cameras = [r['displayed_camera'] for r in samples]
    assert None not in cameras, ('Unrecognized displayed terrain', cameras)
    first = cameras.index(4)
    assert cameras[first:first+12] == list(range(4, 49, 4)), cameras
    assert all(c == 48 for c in cameras[first+12:]), cameras
    assert samples[-1]['buffer_checks'] >= 20
    return dict(pal_frames=len(samples), pan_pixels=48, pan_frames=12,
                pixels_per_frame=4, repeated_motion_frames=0,
                full_screen_checks=samples[-1]['buffer_checks'])


def normal_pan_pairs(samples):
    for previous, current in zip(samples, samples[1:]):
        before, after = previous['displayed_camera'], current['displayed_camera']
        if (previous['state'] == current['state'] == 1 and before is not None
                and after is not None and (before != after or before%48)):
            yield previous, current


def check_normal_pan_sprites(pairs, pans):
    cameras = [current['displayed_camera'] for _, current in pairs]
    assert cameras == list(range(4, pans*48+1, 4)), ('Normal pan cadence', cameras)
    sprite_checks = 0
    for previous, current in pairs:
        step = current['displayed_camera']-previous['displayed_camera']
        assert step == 4
        expected = Counter((x,y+step,graphic,colour,mc)
                           for x,y,graphic,colour,mc in previous['sprites'] if y+step < 247)
        observed = Counter(map(tuple, current['sprites']))
        assert observed == expected, ('Sprite did not move with the camera',
                                      current['frame'], current['displayed_camera'],
                                      expected-observed, observed-expected)
        sprite_checks += sum(observed.values())
    assert sprite_checks >= pans*12*2
    return dict(pans=pans, motion_frames=len(cameras), pixels_per_frame=4,
                repeated_motion_frames=0, matching_sprite_layers=sprite_checks)


def check_bonus(samples, players, start=0, end=64, minimum_sprites=None):
    cameras = [r['displayed_camera'] for r in samples]
    assert None not in cameras, ('Unrecognized displayed terrain', cameras)
    first = next(i for i, c in enumerate(cameras) if c > start)
    last = cameras.index(end)
    moving = [start]+cameras[first:last+1]
    steps = [b-a for a, b in zip(moving, moving[1:])]
    assert all(d in (1, 2) for d in steps), ('Repeated or skipped display', cameras)
    assert all(abs(a-b) <= 1 for a, b in zip(steps, steps[1:])), steps
    assert all(c == end for c in cameras[last:]), cameras
    # The four fruit on their original ledges (two layers each) and the
    # climbers (two layers each): 10 sprites for one, 12 for two.
    minimum_sprites = minimum_sprites if minimum_sprites is not None else (12 if players == 2 else 10)
    assert max(r['logical'] for r in samples) >= minimum_sprites
    assert samples[-1]['buffer_checks'] >= 55
    return dict(pal_frames=len(samples), camera_start=start, camera_end=end,
                camera_limit=240, motion_frames=len(steps), steps=steps,
                maximum_logical_sprites=max(r['logical'] for r in samples),
                repeated_motion_frames=0,
                full_screen_checks=samples[-1]['buffer_checks'])


def main():
    parser = argparse.ArgumentParser()
    add_vice_argument(parser)
    args = parser.parse_args()
    prg = BASE/'c64/build/iceclimber_game.prg'
    release = hashlib.sha256(prg.read_bytes()).hexdigest()
    report = dict(status='passed', prg_sha256=release,
                  measurement='actual D011/D018 at PAL frame IRQ and full committed screen/cache equality',
                  controlled_gameplay_positions=True, cases={})
    out = BASE/'docs/verification/scroll_timing.json'
    def record(name, samples, check):
        report['cases'][name] = dict(samples=samples)
        try:
            report['cases'][name].update(check())
        except AssertionError as error:
            report.update(status='failed', failed_case=name, error=str(error))
            out.write_text(json.dumps(report, indent=2)+'\n')
            raise

    def record_pan(name, samples, pans, check_route=None):
        pairs = list(normal_pan_pairs(samples))
        frames = {frame['frame']:frame for pair in pairs for frame in pair}

        def verify():
            result = check_normal_pan_sprites(pairs, pans)
            if check_route is not None:
                result.update(check_route())
            return result

        record(name, list(frames.values()), verify)
        print('PASS', name, 'sprite layers follow every 4px step', flush=True)

    route = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())['normal']
    samples, played, lives = normal_route(args.vice, route)

    def verify_route():
        assert played == len(route) and samples[-1]['state'] == 3 and lives == 3
        return dict(joystick_updates=played, lives=lives, entered_bonus=True)

    record_pan('normal_joystick_pan_sprites', samples, 5, verify_route)
    record_pan('normal_two_player_pan_sprites', normal_coop_pan(args.vice), 1)
    for players in (1, 2):
        for mountain in (1, 5):
            name = f'normal_m{mountain:02}_{players}p'
            samples = normal(args.vice, mountain, players)
            record(name, samples, lambda: check_normal(samples))
            print('PASS', name, '12 consecutive displayed 4px steps', flush=True)
        for mountain in ((1,) if players == 1 else range(1, 9)):
            name = f'bonus_dense_m{mountain:02}_{players}p'
            samples = bonus(args.vice, players, mountain=mountain, start=0, maximum=64)
            record(name, samples, lambda: check_bonus(samples, players))
            print('PASS', name, 'no repeated PAL frames while moving', flush=True)
    # The top: the condor is drawn there only (camera 240, source scroll 0).
    name = 'bonus_top_m01_2p_200_240'
    samples = bonus(args.vice, 2, maximum=240, mountain=1, start=200)
    record(name, samples, lambda: check_bonus(samples, 2, 200, 240, minimum_sprites=6))
    print('PASS', name, 'no repeated PAL frames while moving', flush=True)
    for mountain, start, end in ((3, 16, 80), (8, 128, 192), (1, 128, 192)):
        name = f'bonus_lower_m{mountain:02}_2p_{start}_{end}'
        samples = bonus(args.vice, 2, maximum=end, mountain=mountain, start=start)
        record(name, samples, lambda: check_bonus(samples, 2, start, end, minimum_sprites=4))
        print('PASS', name, 'no repeated PAL frames while moving', flush=True)
    assert hashlib.sha256(prg.read_bytes()).hexdigest() == release, 'PRG changed during measurement'
    out.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
