#!/usr/bin/env python3
"""Play every mountain in native VICE and check every displayed frame.

For each of the 32 mountains the planned joystick route
(tools/fixtures/mountain_routes.json) climbs to the summit with one player
and the bonus stage is played on with simple inputs; a second session plays
the mountain with two players and random inputs. Every PAL frame VICE
actually displayed is checked as in verify_display_pixels:

* every scheduled sprite's own-colour pixels are on screen (no sprite lost);
* the background follows the camera (no tearing, late buffer or colour lag);
* normal pans move 12 x 4 pixels, the bonus camera 0-2 pixels per frame,
  changing by at most one;
* multiplexer drops (logical > scheduled sprites: flicker) are counted;
* the eight condor blocks hold the debris art in normal play and the
  original condor in the bonus stage.
"""
from tool_paths import add_vice_argument
import argparse
import json
import random
from collections import Counter

from pixel_checks import band_comparison, sprite_mask

import measure_display_scroll
from measure_display_scroll import DisplayTrace
from verify_display_pixels import BOTTOM, LEFT, RIGHT, TOP, X0, grab, own_pixels
from vice_session import BASE, ViceSession

SPRITES = (BASE/'c64/build/game_sprites.bin').read_bytes()
META = {e['name']: e['pointer'] for e in json.loads((BASE/'c64/build/sprite_frames.json').read_text())}
CONDOR = (META['CONDOR_R_FLAP0_0_0']-0x40)*64
DEBRIS_ART = (BASE/'c64/build/debris_art.bin').read_bytes()
DEBRIS_BLOCKS = bytearray(512)
for piece in range(8):
    for row in range(8):
        DEBRIS_BLOCKS[piece*64+row*3] = DEBRIS_ART[piece*8+row]
DEBRIS_BLOCKS = bytes(DEBRIS_BLOCKS)
CONDOR_BLOCKS = SPRITES[CONDOR:CONDOR+512]


def start(s, mountain, players):
    if players == 2:
        s.frame(0xFD)
        s.frame()
    s.title_code(mountain)
    assert s.read('selected_mountain')[0] == mountain
    s.frame(0xEF)
    s.frame()
    if s.read('state') == b'\x04':
        s.finish_preview()


def play(s, inputs, players, res):
    """Check every displayed frame while the inputs run (normal play and bonus)."""
    played = 0

    def joy():
        return inputs[played] if played < len(inputs) else 0xFF

    def advance(session, _):
        nonlocal played
        if session.read('state') in (b'\x01', b'\x03'):
            dropped, two = session.left_out()
            res['drop_frames'] += dropped > 0
            res['two_layer_frames'] += two
        played += 1
        session.write(0x4F, joy())
        session.write(0x4E, joy() if players == 2 else 0xFF)

    trace = DisplayTrace(s, advance, record_sprites=True)
    previous = shown = None
    while played < len(inputs):
        try:
            sample = trace.next(joy(), joy() if players == 2 else 0xFF)
        except AssertionError as error:
            if 'No frame IRQ' not in str(error):
                raise
            # A scene change with the display off (results, game over):
            # no frame IRQ to sample. The mountain is done.
            res['stopped'] = (played, s.read('state')[0])
            break
        pixels = grab(s)
        state = sample['state']
        if state not in (1, 3):
            res['other_frames'] += 1
            previous = shown = None
            if state == 2 or state == 0:
                break               # results, game over: the mountain is done
            continue
        if res['frames'] % 25 == 0:
            blocks = s.read(0x4000+META['CONDOR_R_FLAP0_0_0']*64, 512)
            want = DEBRIS_BLOCKS if state == 1 else CONDOR_BLOCKS
            if blocks != want:
                res['art'].append((res['frames'], state))
        if shown is not None and shown['displayed_camera'] is not None and shown['state'] == state:
            res['frames'] += 1
            res['states'][state] += 1
            mask = sprite_mask(pixels, shown['sprites'], X0)
            drawn = [own_pixels(s, event, background=trace.previous_background) for event in shown['sprites']]
            covers = [own_pixels(s, event, opaque=True, background=trace.previous_background) for event in shown['sprites']]
            for index, event in enumerate(shown['sprites']):
                others = {(r, c) for k, other in enumerate(covers) if k != index for r, c, _ in other}
                own = [(r, c, v) for r, c, v in drawn[index] if (r, c) not in others]
                if len(own) >= 6 and sum(pixels[r][c] == v for r, c, v in own) < len(own)//2:
                    res['lost'].append((res['frames'], state, event))
            if previous is not None and previous[1]['state'] == state:
                old_pixels, old_shown, old_mask = previous
                d = shown['displayed_camera']-old_shown['displayed_camera']
                res['deltas'][state].append(d)
                for band in range(TOP, BOTTOM-8, 8):
                    mismatch = band_comparison(pixels, old_pixels, mask, old_mask, band, d, LEFT, RIGHT)
                    here = mismatch(d)
                    if here <= 40 or (d and band == TOP):
                        continue
                    best = min(range(-12, 13), key=mismatch)
                    if mismatch(best) < here:
                        res['tearing'].append((res['frames'], state, band, d, here, best, mismatch(best)))
            previous = (pixels, shown, mask)
        shown = sample
    return played


def check_camera(res):
    problems = []
    normal = res['deltas'][1]
    if not set(normal) <= {0, 4}:
        problems.append(('normal camera steps', dict(Counter(normal))))
    runs = ''.join('4' if d else '0' for d in normal).split('0')
    if not all(len(run) in (0, 12) for run in runs):
        problems.append(('pan not 12 x 4', [len(r) for r in runs if len(r) not in (0, 12)]))
    bonus = res['deltas'][3]
    if not set(bonus) <= {0, 1, 2}:
        problems.append(('bonus camera steps', dict(Counter(bonus))))
    if not all(abs(b-a) <= 1 for a, b in zip(bonus, bonus[1:])):
        problems.append(('bonus camera jerk', None))
    return problems


def new_result(case):
    return dict(case=case, frames=0, other_frames=0, states=Counter(), deltas={1: [], 3: []},
                lost=[], tearing=[], drop_frames=0, two_layer_frames=0, art=[])


def run_route(vice, mountain, route, bonus_frames):
    res = new_result(f'route_{mountain:02}')
    with ViceSession(f'playthrough_{mountain:02}', vice) as s:
        start(s, mountain, 1)
        inputs = list(route['inputs'])
        # The bonus stage after the summit: the climber stays on its start
        # ledge while the clouds, condor and timer run.
        inputs += [0xFF]*bonus_frames
        play(s, inputs, 1, res)
        res['summit'] = res['states'][3] > 0
    return res


def run_bonus_route(vice, mountain, route):
    """A planned climb and bonus route: summit, bonus climb, condor."""
    res = new_result(f'bonus_{mountain:02}')
    with ViceSession(f'playthrough_bonus_{mountain:02}', vice) as s:
        start(s, mountain, 1)
        played = play(s, list(route['normal'])+list(route['bonus'])+[0xFF]*60, 1, res)
        res['summit'] = res['states'][3] > 0
        res['condor'] = s.read('bonus_winner')[0] == 1
        res['played'] = played
    return res


def run_route_2p(vice, mountain, route, bonus_frames):
    """Two climbers both given the route's inputs from their own starts: two
    active climbers, bumps, shared camera, deaths and respawns all the way."""
    res = new_result(f'route2p_{mountain:02}')
    with ViceSession(f'playthrough_r2p_{mountain:02}', vice) as s:
        start(s, mountain, 2)
        play(s, list(route['inputs'])+[0xFF]*bonus_frames, 2, res)
        res['summit'] = res['states'][3] > 0
        res['max_floor'] = max(s.read('PLAYER_STATES', 64)[11], s.read('PLAYER_STATES', 64)[43])
    return res


def run_random(vice, mountain, frames, seed):
    res = new_result(f'random2p_{mountain:02}')
    rng = random.Random(seed)
    joy, inputs = 0xFF, []
    for _ in range(frames):
        if rng.random() < 0.12:
            joy = rng.choice((0xFF, 0xF7, 0xFB, 0xF6, 0xFA, 0xFE, 0xEF))
        inputs.append(joy)
    with ViceSession(f'playthrough_2p_{mountain:02}', vice) as s:
        start(s, mountain, 2)
        play(s, inputs, 2, res)
    return res


def summary(res):
    problems = check_camera(res)
    if res['lost']:
        problems.append(('lost sprites', res['lost'][:4]))
    if res['tearing']:
        problems.append(('tearing', res['tearing'][:4]))
    if res['art']:
        problems.append(('wrong condor/debris art', res['art'][:4]))
    return dict(case=res['case'], frames=res['frames'], normal_frames=res['states'][1],
                bonus_frames=res['states'][3], drops=res['drop_frames'],
                popo_two_layers=res['two_layer_frames'],
                pans=''.join('4' if d == 4 else '0' for d in res['deltas'][1]).count('4'*12),
                summit=res.get('summit'), stopped=res.get('stopped'), problems=problems)


def main():
    p = argparse.ArgumentParser()
    add_vice_argument(p)
    p.add_argument('--mountains', nargs='*', type=int, default=list(range(1, 33)))
    p.add_argument('--bonus-frames', type=int, default=700)
    p.add_argument('--random-frames', type=int, default=700)
    p.add_argument('--two-player-routes', action='store_true',
                   help='both climbers follow the route (two active climbers on every mountain)')
    p.add_argument('--bonus-routes', action='store_true',
                   help='play the planned bonus routes (build_dbg/bonus_routes_input_cache) to the condor')
    args = p.parse_args()
    if args.bonus_routes:
        import hashlib
        release = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
        report = []
        for mountain in args.mountains:
            path = BASE/f'build_dbg/bonus_routes_input_cache/{mountain:02}.json'
            route = json.loads(path.read_text()) if path.exists() else {}
            if route.get('replay_prg_sha256') != release:
                print('SKIP', mountain, 'no bonus route for this PRG', flush=True)
                continue
            res = run_bonus_route(args.vice, mountain, route)
            line = summary(res)
            line['condor'] = res['condor']
            if not res['condor']:
                line['problems'].append(('condor not caught', res['played']))
            report.append(line)
            print('FAIL' if line['problems'] else 'PASS', json.dumps(line), flush=True)
        (BASE/'docs/verification/playthrough_bonus.json').write_text(json.dumps(report, indent=2)+chr(10))
        failed = [r['case'] for r in report if r['problems']]
        print(f"{'FAIL' if failed else 'PASS'} bonus playthrough: {len(report)} variants", flush=True)
        assert not failed, failed
        return
    routes = {r['mountain']: r for r in json.loads((BASE/'tools/fixtures/mountain_routes.json').read_text())['routes']}
    if args.two_player_routes:
        report = []
        for mountain in args.mountains:
            res = run_route_2p(args.vice, mountain, routes[mountain], args.bonus_frames)
            line = summary(res)
            line['max_floor'] = res['max_floor']
            line['summit'] = None   # the route is planned for one climber
            report.append(line)
            print('FAIL' if line['problems'] else 'PASS', json.dumps(line), flush=True)
        (BASE/'docs/verification/playthrough_2p.json').write_text(json.dumps(report, indent=2)+chr(10))
        failed = [r['case'] for r in report if r['problems']]
        print(f"{'FAIL' if failed else 'PASS'} two-player playthrough: {len(report)} mountains, "
              f"{sum(r['frames'] for r in report)} checked frames, "
              f"{sum(r['drops'] for r in report)} multiplexer drop frames", flush=True)
        assert not failed, failed
        return
    report = []
    for mountain in args.mountains:
        for res in (run_route(args.vice, mountain, routes[mountain], args.bonus_frames),
                    run_random(args.vice, mountain, args.random_frames, mountain)):
            line = summary(res)
            report.append(line)
            print('FAIL' if line['problems'] else 'PASS', json.dumps(line), flush=True)
    (BASE/'docs/verification/playthrough.json').write_text(json.dumps(report, indent=2)+'\n')
    failed = [r for r in report if r['problems'] or r['summit'] is False]
    print(f"{'FAIL' if failed else 'PASS'} playthrough: {len(report)} sessions, "
          f"{sum(r['frames'] for r in report)} checked frames, "
          f"{sum(r['drops'] for r in report)} multiplexer drop frames", flush=True)
    assert not failed, [r['case'] for r in failed]


if __name__ == '__main__':
    measure_display_scroll.IRQ_STOPS = max(measure_display_scroll.IRQ_STOPS, 400)
    main()
