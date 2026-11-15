#!/usr/bin/env python3
"""The original stone posts stop and push the climbers, tick by tick.

Mountain 5 starts with an original stone post on the ground floor (source
X 88-96). The executed original controller and player handlers
(PlayerReference: $CAED $CB9D $CD13 $DA99 $D1E5) followed by $E0B9, and
the C64 climber followed by the transplanted $E0B9 (nes_objects.asm), get
the same pads. Walking into the post snaps the climber to its side
($E158), a jump beside it pushes the climber away for eight ticks
($E142/$E11B). After every tick X, Y, the exported floor $5A, direction
$68, facing $62 and the push timer $3A must equal the original.
"""
import hashlib
import json

from original_player_reference import PlayerReference
from test_game import BASE, start
from test_nes_export import joystick
from transplant_objects import map_ram

MOUNTAIN = 5

SEQUENCES = {
    # name: (start X in source pixels, pads)
    'walk_right_into_post': (48, [1]*80),
    'walk_left_into_post': (132, [2]*80),
    'run_jump_right_at_post': (40, [1]*14+[0x81]+[1]*60),
    'run_jump_left_at_post': (140, [2]*10+[0x82]+[2]*60),
    'jump_beside_post_left': (70, [0]*4+[0x80]+[0]*60),
    'jump_beside_post_right': (100, [0]*4+[0x80]+[0]*60),
    'jump_right_then_left': (60, [0x81]+[1]*20+[2]*40),
    'stand_next_to_post': (73, [0]*30+[2]*20+[1]*30),
    'held_hammer_into_post_right': (48, [1]*30+[0x41]*100+[1]*30),
    'held_hammer_into_post_left': (132, [2]*30+[0x42]*100+[2]*30),
}
# Running jumps that rise past the post's top beside it: the push ($E142)
# in both directions, then the eight-tick drift ($E11B INC and DEC).
for x in range(44, 80, 4):
    SEQUENCES[f'jump_right_from_{x}'] = (x, [0x81]+[1]*44)
for x in range(100, 136, 4):
    SEQUENCES[f'jump_left_from_{x}'] = (x, [0x82]+[2]*44)


def read(machine, nes):
    address = map_ram(nes)
    if isinstance(address, str):
        address = machine.labels[address]
    if 0xD000 <= address < 0xE000:
        return machine.under_io[address-0xD000]
    return machine.ram[address]


def run(name, x, pads):
    reference = PlayerReference(MOUNTAIN-1)
    ref = reference.ram
    reference.call(0xE002)              # $C2A4: the stage's stone posts
    machine = start(mountain=MOUNTAIN)
    r, L = machine.ram, machine.labels
    for nes in range(0x0600, 0x0630):
        assert read(machine, nes) == ref[nes], ('stone table', hex(nes), read(machine, nes), ref[nes])
    ref[0x64] = x
    r[L['pxlo']], r[L['pxhi']] = (x+52) & 255, (x+52) >> 8
    r[L['invul_t']] = ref[0x2D] = 0     # no respawn immunity on either side
    machine.call('play_context_store')
    original_map = bytes(ref[0x400:0x5D8])
    ported_map = bytes(r[0x400:0x5D8])
    snaps = pushes = push_ticks = 0
    drifts = set()
    for tick, pad in enumerate(pads):
        reference.tick(pad)
        machine.joystick = joystick(pad)
        machine.call('read_joy')
        machine.call('environment_timers')
        machine.call('normal_player_tick')
        machine.call('play_context_store')
        r[1] = 0x34                     # the NES code runs with RAM under I/O
        machine.call('nes_export')
        ref[0x50] = read(machine, 0x50)  # the same frame parity for $E11B
        before = ref[0x64]
        reference.call(0xE0B9)
        machine.call('N_E0B9')     # nes_stone_push
        machine.call('nes_import')
        r[1] = 0x35
        machine.call('nes_apply')
        context = (name, tick, pad)
        if ref[0x64] != before and not ref[0x3A]:
            snaps += 1
        pushes += ref[0x3A] == 8
        if ref[0x3A] and ref[0x50] & 1 and ref[0x68]:
            drifts.add(ref[0x68])
        push_ticks += bool(ref[0x3A])
        got = ((r[L['pxlo']]+256*r[L['pxhi']]-52) & 255, r[L['py']]-24, read(machine, 0x5A),
               r[L['move_dir']], 1-r[L['face']], r[map_ram(0x3A)])
        want = (ref[0x64], ref[0x66], ref[0x5A], ref[0x68], ref[0x62], ref[0x3A])
        assert got == want, ('X, Y, floor, $68, $62, $3A differ', context, got, want)
        if name.startswith('held_hammer_into_post'):
            assert bytes(ref[0x400:0x5D8]) == original_map
            assert bytes(r[0x400:0x5D8]) == ported_map
    return dict(name=name, ticks=len(pads), snaps=snaps, pushes=pushes, push_ticks=push_ticks,
                drifts=sorted(drifts))


def main():
    cases = [run(name, x, pads) for name, (x, pads) in SEQUENCES.items()]
    assert sum(c['snaps'] for c in cases) and sum(c['pushes'] for c in cases), cases
    assert {d for c in cases for d in c['drifts']} == {1, 2}, 'both $E11B drift directions'
    report = dict(status='passed', mountain=MOUNTAIN, cases=cases,
                  source_routines=['$E002', '$E0B9', '$E0C0', '$E11B', '$E12F', '$E158', '$E176'],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/nes_stones.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(f"PASS original stone posts: {sum(c['ticks'] for c in cases)} ticks, "
          f"{sum(c['snaps'] for c in cases)} side snaps, {sum(c['pushes'] for c in cases)} pushes "
          f"equal the original")


if __name__ == '__main__':
    main()
