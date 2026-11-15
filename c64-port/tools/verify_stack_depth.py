#!/usr/bin/env python3
"""The stack stays above $01C0 in native VICE, IRQs included.

$0100-$01A7 holds the debris code (STACKCODE) and $01A8-$01BF the debris
OAM entries. A canary pattern below the stack ($01C0-$01EF) is written after
the boot, then a whole climb with debris, the bonus stage and two-player
play run. The lowest overwritten canary byte gives the deepest stack.
"""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json
from pathlib import Path

from vice_session import ViceSession

BASE = Path(__file__).resolve().parents[1]
CANARY = 0x5A
LOW, HIGH = 0x01C0, 0x01F0


def deepest(s):
    data = s.read(LOW, HIGH-LOW)
    touched = [LOW+i for i, b in enumerate(data) if b != CANARY]
    return min(touched) if touched else HIGH


def main():
    parser = argparse.ArgumentParser()
    add_vice_argument(parser)
    args = parser.parse_args()
    routes = json.loads((BASE/'tools/fixtures/mountain_routes.json').read_text())['routes']
    route = next(r for r in routes if r['mountain'] == 1)
    lows = {}
    with ViceSession('stack_depth', args.vice) as s:
        s.frame(0xEF)
        s.frame()
        s.write(LOW, bytes([CANARY])*(HIGH-LOW))
        s.finish_preview()
        for joy in route['inputs']:
            s.frame(joy)
        assert s.read('state') == b'\x03', 'the climb did not reach the bonus'
        lows['climb'] = deepest(s)
        for n in range(400):
            s.frame(0xFE if n % 30 < 2 else 0xF7)
        lows['bonus'] = deepest(s)
    with ViceSession('stack_depth_2p', args.vice) as s:
        s.frame(0xFD)
        s.frame()
        s.frame(0xEF)
        s.write(LOW, bytes([CANARY])*(HIGH-LOW))
        s.finish_preview()
        for n in range(900):
            s.frame(0xFE if n % 40 < 2 else 0xF7 if n % 200 < 100 else 0xFB,
                    0xFE if n % 50 < 2 else 0xFB if n % 160 < 80 else 0xF7)
        lows['two_players'] = deepest(s)
    deepest_byte = min(lows.values())
    assert deepest_byte > LOW, ('the stack reached the debris OAM', lows)
    report = dict(status='passed', canary=[f'${LOW:04X}', f'${HIGH-1:04X}'],
                  deepest={k: f'${v:04X}' for k, v in lows.items()},
                  bytes_used=0x200-deepest_byte, free_above_debris=deepest_byte-LOW,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/stack_depth.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'PASS native stack depth: deepest ${deepest_byte:04X} ({0x200-deepest_byte} bytes), '
          f'{deepest_byte-LOW} bytes above the debris OAM')


if __name__ == '__main__':
    main()
