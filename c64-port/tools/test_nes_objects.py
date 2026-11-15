#!/usr/bin/env python3
"""The transplanted enemy objects equal the original ROM, tick by tick.

The C64 runs the original object code (tools/transplant_objects.py) with
its RAM moved and a few routines replaced by C64 glue. During real C64
play on many mountains, this test stops each logic tick right after the
C64 has built the NES view of the players, clouds and camera. It copies
that view into an NES address space with the original ROM, converts the
two block planes to the original values, and runs the original entries
$EFEC $E189 $DE22 $EE0D $EF9A $F10B $D3AC $D301 $F838 $E0B9 there. When
the C64 has run the same entries, every object byte, the bear phase and
counters, the slow timers, the players' handlers, X, direction and
facing, the stone-post table and push timers and the block planes must be
equal. Pan ticks run $E002 and $EC51, the last one also $D861; the stage
start runs $E002.
"""
import hashlib
import json
import random
import struct

import transplant_objects as T
from test_game import BASE, Machine, start
from test_original_physics import PRG, Reference

ENTRY_ORDER = [0xEFEC, 0xE189, 0xDE22, 0xEE0D, 0xEF9A, 0xF10B, 0xD3AC, 0xD212, 0xD301, 0xF838, 0xE0B9]
STONES = list(range(0x0600, 0x0630))
COMPARED = ([0x2D, 0x2E, 0x3A, 0x3B] + list(range(0x48, 0x50)) + [0x5A, 0x5B, 0x62, 0x63, 0x64, 0x65,
            0x66, 0x67, 0x6A, 0x6B, 0x68, 0x69, 0x7C, 0xE6, 0xE7, 0xE8, 0xE9] + list(range(0x91, 0xC8)) + [0xDC, 0xDD, 0xDF] +
            list(range(0x0360, 0x036A)) + list(range(0x0376, 0x03F3)) + STONES)


def c64_address(machine, nes):
    target = T.map_ram(nes)
    if isinstance(target, str):
        return ('ram', machine.labels[target])
    if 0xD000 <= target < 0xE000:
        return ('io', target-0xD000)
    return ('ram', target)


def c64_read(machine, nes):
    space, address = c64_address(machine, nes)
    return machine.under_io[address] if space == 'io' else machine.ram[address]


def nes_view(machine):
    """The NES address space as the transplanted code sees it."""
    ref = Reference()
    r = ref.ram
    for nes in range(0x0800):
        try:
            r[nes] = c64_read(machine, nes)
        except KeyError:
            pass
    upper, lower = machine.labels['floor_upper'], machine.labels['floor_lower']
    for i in range(216):
        u, l = machine.ram[upper+i], machine.ram[lower+i]
        r[0x400+i] = {0: 0xFF, 1: 1, 2: 4, 3: 3}[u]
        r[0x500+i] = {0: 0xFF, 1: 1, 2: 2, 3: 4}[l]
    r[0x301] = 0                # empty PPU buffer: $DE22 runs every tick
    return ref


def call_addresses(machine, routine, targets):
    start_address = machine.labels[routine]
    code = machine.ram[start_address:start_address+200]
    found = {}
    for name in targets:
        call = b'\x20' + machine.labels[name].to_bytes(2, 'little')
        found[name] = start_address+bytes(code).index(call)
    return found


def call_with_x(ref, address, x):
    ref.a, ref.x, ref.y = 0, x, 0
    ref.push(0xBF)
    ref.push(0xFF)
    ref.pc = address
    for _ in range(20000):
        if ref.pc == 0xC000:
            return
        ref.step()
    raise AssertionError(('NES routine did not return', hex(address)))


def play(mountain, completed, players, seed, frames, route=None, bear=None):
    machine = start(mode=players, mountain=mountain)
    r, L = machine.ram, machine.labels
    r[L['completed_mountains']] = completed
    r[L['phase_counter']] = 1 if completed >= 32 else 0
    machine.call('environment_init')
    if bear is not None:
        r[L['bear_timer']:L['bear_timer']+2] = bytes(bear)
    # The stage start's stone posts ($C2A4 -> $E002) equal the original.
    start_view = nes_view(machine)
    start_view.call(0xE002)
    stones = [c64_read(machine, nes) for nes in STONES]
    assert stones == [start_view.ram[nes] for nes in STONES], ('stage start stone posts', mountain)
    assert bool(r[L['nes_stones_any']]) == any(stones[:11]), ('stone post flag', mountain)
    stops = call_addresses(machine, 'nes_objects_tick_all', ['N_EFEC', 'nes_retire'])
    pan = call_addresses(machine, 'nes_pan_tick', ['nes_stones_seen', 'N_EC51', 'N_D861'])
    # (start, end) PCs of each C64 call, and the original entries it runs.
    # The C64 skips $D301 and $E0B9 when they cannot change anything (no
    # object with state bit 7; no stone post and no push): the ROM always
    # runs them, so the comparison also proves those skips.
    hooks = {stops['N_EFEC']: (stops['nes_retire'], ENTRY_ORDER),
             pan['nes_stones_seen']: (pan['N_EC51']+3, [0xE002, 0xEC51]),
             pan['N_D861']: (pan['N_D861']+3, [0xD861])}
    ends = {end: start for start, (end, entries) in hooks.items()}
    rng = random.Random(seed)
    joy = joy2 = 0xFF
    counts = {'ticks': 0, 'pan_ticks': 0, 'pan_ends': 0, 'stone_posts': sum(1 for x in stones[:16] if x),
              'pushes': 0, 'push_ticks': 0}
    kinds = {}
    original_step = machine.step
    pending = {}

    def step():
        pc = machine.pc
        if pc in hooks:
            pending[pc] = nes_view(machine)
        elif pc in ends and ends[pc] in pending:
            ref = pending.pop(ends[pc])
            for entry in hooks[ends[pc]][1]:
                if entry == 0xF838:
                    call_with_x(ref, entry, 1)   # $EC23 leaves X = 1
                else:
                    ref.call(entry)
            compare(machine, ref, hooks[ends[pc]][1])
        original_step()

    def compare(machine, ref, entries):
        key = 'ticks' if entries is ENTRY_ORDER else 'pan_ends' if entries == [0xD861] else 'pan_ticks'
        counts[key] += 1
        any_post = any(ref.ram[0x600+i] for i in range(11))
        assert bool(r[L['nes_stones_any']]) == any_post, ('stone post flag', mountain, counts)
        if key == 'ticks':
            counts['push_ticks'] += sum(1 for p in (0x3A, 0x3B) if ref.ram[p])
            counts['pushes'] += sum(1 for p in (0x3A, 0x3B) if ref.ram[p] == 8)
        for nes in COMPARED:
            if nes in (0x66, 0x67) and key != 'ticks':
                continue        # the C64 pan moves the climbers itself ($EC74)
            got = c64_read(machine, nes)
            want = ref.ram[nes]
            assert got == want, ('object state differs', dict(mountain=mountain, kind=key, count=counts[key],
                                 nes=f'${nes:04X}', c64=got, original=want))
        for i in range(216):
            assert ({0: 0xFF, 1: 1, 2: 4, 3: 3}[r[L['floor_upper']+i]] == ref.ram[0x400+i] or
                    r[L['floor_upper']+i] == 3), ('upper plane', mountain, counts, i)
        for x in range(11):
            if ref.ram[0x91+x]:
                kinds.setdefault(x, set()).add((ref.ram[0x91+x], ref.ram[0x3DD+x]))

    machine.step = step
    for frame in range(frames):
        if route is not None:
            joy = route[frame] if frame < len(route) else 0xFF
        elif rng.random() < 0.1:
            joy = rng.choice((0xFF, 0xF7, 0xFB, 0xEF, 0xE7, 0xEB, 0xFE, 0xF6, 0xFA))
        if rng.random() < 0.1:
            joy2 = rng.choice((0xFF, 0xF7, 0xFB, 0xEF, 0xE7, 0xEB, 0xFE))
        machine.frame(joy, joy2 if players == 2 else 0xFF)
        if r[L['state']] != 1:
            break
    return counts, kinds


def main():
    report = []
    total = 0
    seen = {}
    route = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())['normal']
    cases = [dict(mountain=1, completed=0, players=1, seed=1),
             dict(mountain=2, completed=9, players=1, seed=2, bear=(3, 0)),
             dict(mountain=5, completed=20, players=2, seed=3),
             dict(mountain=13, completed=40, players=1, seed=4, bear=(20, 0)),
             dict(mountain=26, completed=61, players=2, seed=5, bear=(3, 0)),
             dict(mountain=31, completed=0, players=1, seed=31),
             dict(mountain=31, completed=0, players=2, seed=32),
             dict(mountain=32, completed=70, players=1, seed=6),
             dict(mountain=1, completed=3, players=1, seed=7, route=route),
             dict(mountain=1, completed=3, players=2, seed=8, route=route, bear=(40, 0))]
    for case in cases:
        counts, kinds = play(case['mountain'], case['completed'], case['players'], case['seed'], 2500,
                             route=case.get('route'), bear=case.get('bear'))
        total += counts['ticks']
        for x, values in kinds.items():
            seen.setdefault(x, set()).update(values)
        report.append(dict({k: v for k, v in case.items() if k != 'route'}, route='route' in case, **counts))
        print(report[-1], flush=True)
    names = {0: 'bird', 1: 'bear', 2: 'seal', 3: 'seal', 5: 'ice', 6: 'ice', 8: 'icicle', 9: 'icicle', 10: 'icicle'}
    covered = sorted({names.get(x, str(x)) for x in seen})
    out = dict(status='passed', ticks=total, objects_seen=covered, cases=report,
               entries=[f'${e:04X}' for e in ENTRY_ORDER],
               prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/nes_objects.json').write_text(json.dumps(out, indent=2)+'\n', encoding='utf-8')
    print(f'PASS original enemy objects: {total} C64 ticks equal the ROM entries; objects {covered}')


if __name__ == '__main__':
    main()
