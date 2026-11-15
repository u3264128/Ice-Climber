#!/usr/bin/env python3
"""Replay current-build joystick candidates and publish the verified aggregate."""
import hashlib
import json
import os
import time

import plan_mountains as p


def main():
    digest = hashlib.sha256((p.BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    sources = [p.BASE/'tools/fixtures/mountain_routes.json']
    sources += list((p.BASE/'build_dbg').glob('mountain_routes_clock_*.json'))
    sources += list((p.BASE/'build_dbg').glob('mountain_routes_final_clock*.json'))
    sources += list((p.BASE/'build_dbg').glob('trueair_physics*_final*.json'))
    sources += list((p.BASE/'build_dbg').glob('trueair_physics*_fine.json'))
    sources += list((p.BASE/'build_dbg').glob('trueair_physics*_smart.json'))
    candidates = {}
    for source in sources:
        try:
            data = json.loads(source.read_text())
        except (OSError, ValueError):
            continue
        prior_build = data.get('prg_sha256') != digest
        for route in data.get('routes', []):
            # A display/bonus rebuild can retain a normal input route, but
            # its former proof must never substitute for executing this PRG.
            if prior_build:
                route = dict(route, full_replay=False)
            candidates.setdefault(route['mountain'], []).append(route)
    routes = []
    for mountain, options in sorted(candidates.items()):
        seen = set()
        for route in sorted(options, key=lambda r: (-r['lives'], r['frames'])):
            sequence = bytes(route['inputs'])
            if sequence in seen:
                continue
            seen.add(sequence)
            if not (route.get('full_replay') and route.get('no_skipped_helpers')):
                try:
                    machine = p.replay(mountain, sequence, native=True)
                except AssertionError as error:
                    print('REJECT', mountain, str(error), flush=True)
                    continue
                route.update(lives=machine.ram[0x19], score=0, normal_score=0)
            route.update(full_replay=True, no_skipped_helpers=True,
                         replay_backend='compiled6502_full_mainloop')
            routes.append(route)
            break
    missing = [n for n in range(1, 33) if n not in {r['mountain'] for r in routes}]
    result = dict(status='incomplete' if missing else 'passed', prg_sha256=digest,
                  routes=routes, missing=missing,
                  backend='compiled6502_full_mainloop', no_skipped_helpers=True)
    destination = p.BASE/'tools/fixtures/mountain_routes.json'
    temporary = destination.with_suffix('.%s.tmp' % os.getpid())
    temporary.write_text(json.dumps(result)+'\n')
    for attempt in range(100):
        try:
            temporary.replace(destination)
            break
        except PermissionError:
            if attempt == 99:
                raise
            time.sleep(0.05)
    (p.BASE/'docs/verification/mountain_routes_regression.json').write_text(json.dumps(result)+'\n')
    print('PUBLISHED', len(routes), 'MISSING', missing, flush=True)


if __name__ == '__main__':
    main()
