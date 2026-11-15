#!/usr/bin/env python3
"""Replay all mountain routes in native VICE using joystick input only.

Mountains are selected through hidden keyboard codes. Position, terrain, enemies
and camera are never changed during a route. Separate controlled fixtures
check seal combat and both horizontal screen boundaries.
"""
from tool_paths import add_vice_argument
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
from pathlib import Path

from test_game import bcd
from vice_session import ViceSession

BASE = Path(__file__).resolve().parents[1]


def read_score(s):
    return bcd(s.read('score_lo', 2)+s.read('score_top'))


def mountain_routes(vice, out, workers=3, follow=False, resume=False):
    fixture_path = BASE/'tools/fixtures/mountain_routes.json'
    prg_path = BASE/'c64/build/iceclimber_game.prg'
    release_hash = hashlib.sha256(prg_path.read_bytes()).hexdigest()
    cache = out/'native_mountain_routes'
    cache.mkdir(exist_ok=True)
    records = {}
    def replay(route):
        mountain = route['mountain']
        assert hashlib.sha256(prg_path.read_bytes()).hexdigest() == release_hash, 'PRG changed during verification'
        with ViceSession(f'original_route_{mountain:02}', vice) as s:
            # Use the hidden keyboard code, then start normally.
            s.title_code(mountain)
            assert s.read('selected_mountain')[0] == mountain
            s.frame(0xEF)
            for _ in range(route.get('start_idle_frames', 1)):
                s.frame()
            # The routes start after the mountain flyover, as the planner's
            # start (test_game.finish_opening) does.
            if s.read('state') == b'\x04':
                s.finish_preview()
            initial_lives = s.read('lives')[0]
            for n, joy in enumerate(route['inputs']):
                assert joy & 0x10, ('route requires a separate fire button', mountain, n)
                s.frame(joy)
                if n == 30 and mountain in (1, 10, 24, 32):
                    s.capture(out/f'original_mountain_{mountain:02}.png')
            assert s.read('state') == b'\x03', ('did not reach bonus', mountain)
            assert s.read('maxfloor') == b'\x08', ('did not reach summit', mountain)
            assert s.read('lives')[0] == route['lives'], ('lives', mountain)
            expected_score=route.get('score',route.get('normal_score'))
            if expected_score is not None:
                assert read_score(s) == expected_score, ('score', mountain, read_score(s), expected_score)
            result = dict(mountain=mountain, frames=len(route['inputs']),
                                lives=s.read('lives')[0], initial_lives=initial_lives,
                                score=read_score(s), up_only_action=True,
                                entered_bonus=True, gameplay_ram_unmodified=True,
                                inputs_sha256=hashlib.sha256(bytes(route['inputs'])).hexdigest())
            if mountain in (1, 10, 24, 32):
                s.capture(out/f'original_summit_{mountain:02}.png')
        assert hashlib.sha256(prg_path.read_bytes()).hexdigest() == release_hash, 'PRG changed during verification'
        (cache/f'{mountain:02}.json').write_text(json.dumps(dict(prg_sha256=release_hash, **result), indent=2)+'\n')
        print(f'PASS native mountain {mountain:02}: {len(route["inputs"])} frames, UP action', flush=True)
        return result
    def retry_replay(route):
        for attempt in range(2):
            try:
                return replay(route)
            except (TimeoutError, ConnectionError):
                if attempt:
                    raise
                print(f'RETRY native mountain {route["mountain"]:02}: monitor connection', flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        submitted, pending = set(), {}
        while True:
            try:
                fixture = json.loads(fixture_path.read_text())
            except (OSError, json.JSONDecodeError):
                if not follow:
                    raise
                time.sleep(1)
                continue
            desired = {}
            for route in fixture['routes']:
                key = (route['mountain'], hashlib.sha256(bytes(route['inputs'])).hexdigest())
                desired[key[0]] = key[1]
                if key not in submitted:
                    submitted.add(key)
                    saved_path = cache/f'{key[0]:02}.json'
                    saved = json.loads(saved_path.read_text()) if resume and saved_path.exists() else {}
                    if saved.get('prg_sha256') == release_hash and saved.get('inputs_sha256') == key[1]:
                        records[key[0]] = {k:v for k,v in saved.items() if k != 'prg_sha256'}
                    else:
                        pending[pool.submit(retry_replay, route)] = key
            for future in list(pending):
                if future.done():
                    result = future.result()
                    records[result['mountain']] = result
                    del pending[future]
                    progress = dict(status='incomplete', prg_sha256=hashlib.sha256(
                        (BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                        mountains=sorted(records.values(), key=lambda r:r['mountain']))
                    (out/'original_rules_native_progress.json').write_text(json.dumps(progress, indent=2)+'\n')
            complete = len(desired) == 32 and all(
                m in records and records[m]['inputs_sha256'] == h for m,h in desired.items())
            if complete or (not follow and not pending):
                break
            time.sleep(1)
    result = sorted(records.values(), key=lambda r:r['mountain'])
    assert [r['mountain'] for r in result] == list(range(1, 33))
    return result


def combat_and_wrap(vice, out):
    with ViceSession('original_controls', vice) as s:
        s.frame(0xEF)
        s.frame()
        # An isolated close original seal (object 2) is knocked down by the
        # ground swing, also while the climber has spawn protection. The
        # jumping hammer passes it ($D3D9 checks only Nitpicker and icicles).
        from transplant_objects import map_ram
        s.finish_preview()
        for name, value in (('pxlo', 120), ('pxhi', 0), ('py', 216), ('curfloor', 0), ('face', 0),
                            ('onground', 1), ('move_dir', 0), ('walk_time', 0), ('skid_t', 0),
                            ('invul_t', 100)):
            s.write(name, value)
        for nes, value in ((0x93, 0xFF), (0x9E, 120-52+16), (0xA9, 0xC8), (0xB4, 1), (0xBF, 0xFF),
                           (0x03EA, 5), (0x03A8, 0x40), (0x03DF, 0xA0)):
            s.write(map_ram(nes), value)
        before = read_score(s)
        s.frame(0xEF)
        for _ in range(24):
            if s.read(map_ram(0x93))[0] != 0xFF:
                break
            s.frame()
        assert s.read(map_ram(0x93))[0] == 1, 'The ground swing did not knock the seal down'
        assert read_score(s) == before, 'The original does not award points for a seal'
        assert s.read('lives')[0] == 3
        s.capture(out/'original_up_hammer.png')
    crossings = []
    for direction, position in ((0xF7, 304), (0xFB, 54)):
        with ViceSession(f'original_wrap_{direction:02x}', vice) as s:
            s.frame(0xEF)
            s.finish_preview()
            s.write('pxlo', position & 255)
            s.write('pxhi', position >> 8)
            s.write('move_dir', 0)
            s.write('walk_time', 0)
            s.write('skid_t', 0)
            from transplant_objects import map_ram
            for obj in range(11):  # keep this boundary fixture free of enemies
                s.write(map_ram(0x91+obj), 0)
                s.write(map_ram(0x03E8+obj), 0)
            s.write(map_ram(0x4A), 255)     # no new seals during the walk
            s.write(map_ram(0x4B), 255)
            s.write(map_ram(0x4E), 255)     # nor Nitpicker
            values = [position]
            for _ in range(16):
                s.frame(direction)
                values.append(int.from_bytes(s.read('pxlo', 2), 'little'))
            differences = [b-a for a, b in zip(values, values[1:])]
            assert any(d < -240 if direction == 0xF7 else d > 240 for d in differences), values
            assert s.read('lives') == b'\x03', 'Walking through the side wall lost a life'
            assert s.read('onground') == b'\x01', 'Side stone did not support the climber'
            crossings.append(dict(direction='right' if direction == 0xF7 else 'left', positions=values))
            s.capture(out/f'original_wrap_{direction:02x}.png')
    return dict(ground_swing_hits_seal=True, protected_player_can_attack=True, horizontal_wrap=crossings)


def main():
    parser = argparse.ArgumentParser()
    add_vice_argument(parser)
    parser.add_argument('--controls-only', action='store_true')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--follow', action='store_true', help='Verify new routes as the planner publishes them')
    parser.add_argument('--resume', action='store_true', help='Reuse matching completed VICE cases from this exact PRG')
    args = parser.parse_args()
    out = BASE/'docs/verification'
    out.mkdir(parents=True, exist_ok=True)
    report = dict(status='passed', prg_sha256=hashlib.sha256(
        (BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    report['controls'] = combat_and_wrap(args.vice, out)
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest() == report['prg_sha256'], 'PRG changed during verification'
    (out/'original_controls_native.json').write_text(json.dumps(report, indent=2)+'\n')
    if not args.controls_only:
        report['mountains'] = mountain_routes(args.vice, out, args.workers, args.follow, args.resume)
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest() == report['prg_sha256'], 'PRG changed during verification'
    destination = 'original_controls_native.json' if args.controls_only else 'original_rules_native.json'
    (out/destination).write_text(json.dumps(report, indent=2)+'\n')
    print('PASS native original rules and joystick input', flush=True)


if __name__ == '__main__':
    main()
