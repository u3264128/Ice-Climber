#!/usr/bin/env python3
"""The NES view of the climbers that the original objects see.

nes_objects.asm gives the transplanted object code the original player
variables: handler $6A (and pose $60 while attacking), X $64, Y $66, floor
$5A, facing $62, direction $68 and the mallet OAM entry $021C/$021F. Here
the executed original controller and player handlers (PlayerReference) and
the C64 climber get the same pads tick by tick. After each tick the values
the C64 exports must equal the original RAM.
"""
import hashlib
import json

from original_player_reference import PlayerReference
from test_game import BASE, start
from transplant_objects import map_ram


def joystick(pad):
    value = 255
    if pad & 0x80:
        value &= 0xFE           # UP: the jump (and its raised hammer)
    if pad & 0x40:
        value &= 0xEF           # FIRE: the ground swing
    if pad & 1:
        value &= 0xF7
    if pad & 2:
        value &= 0xFB
    return value


def exported(machine, nes):
    address = map_ram(nes)
    if isinstance(address, str):
        address = machine.labels[address]
    if 0xD000 <= address < 0xE000:
        return machine.under_io[address-0xD000]
    return machine.ram[address]


def handler_class(handler):
    """What the object code distinguishes: $D308 skips 0/7/9, $D3D9 hits
    with 4, $D3DF with 5 (pose 9), $D383 turns odd handlers. Falls from a
    ledge (2) and after a head hit (6, 8) are equal for the objects."""
    if handler in (0, 7, 9):
        return 'none'
    if handler in (4, 5):
        return handler
    return 'odd' if handler & 1 else 'even'


SEQUENCES = {
    'idle_jump': [0]*6+[0x80]+[0]*40,
    'run_jump_right': [1]*24+[0x81]+[1]*40,
    'run_jump_left': [2]*12+[0x82]+[2]*40,
    'ground_swing': [0]*4+[0x40]+[0]*26,
    'walk_swing': [1]*9+[0x41]+[1]*24,
    'swing_left': [2]*3+[0x42]+[0]*26,
    'held_jump': [0x80]*60,
    'held_swing': [0x40]*70,
    'walk_held_swing': [1]*9+[0x41]*50,
    'swing_again_at_once': [0x40]+[0]*20+[0x40]+[0]*30,
    'walk_off': [1]*90+[2]*90,
}


def check():
    ticks = compared = mallets = 0
    handlers = set()
    for name, pads in SEQUENCES.items():
        reference = PlayerReference()
        machine = start()
        r, L = machine.ram, machine.labels
        ref = reference.ram
        r[map_ram(0x91)] = 0xFF     # a flying Nitpicker: jumps test the mallet
        for tick, pad in enumerate(pads):
            reference.tick(pad)
            machine.joystick = joystick(pad)
            machine.call('read_joy')
            machine.call('normal_player_tick')
            machine.call('play_context_store')
            r[1] = 0x34         # the export runs with RAM under I/O
            machine.call('nes_export')
            machine.call('nes_mallets')
            r[1] = 0x35
            context = (name, tick, pad)
            handler = exported(machine, 0x6A)
            want = ref[0x6A]
            handlers.add(want)
            assert handler_class(handler) == handler_class(want), ('handler', context, handler, want)
            if want == 5:
                assert exported(machine, 0x60) == ref[0x60], ('attack pose', context)
            for nes in (0x5A, 0x64, 0x66, 0x62, 0x68):
                assert exported(machine, nes) == ref[nes], (f'${nes:02X}', context,
                                                             exported(machine, nes), ref[nes])
                compared += 1
            # $D3B3 reads the mallet entry only while jumping (4) or at
            # swing pose 9 (5); the C64 builds it for exactly those ticks.
            if ref[0x21C] != 0xF8 and (want == 4 or (want == 5 and ref[0x60] == 9)):
                assert (exported(machine, 0x21C), exported(machine, 0x21F)) == (ref[0x21C], ref[0x21F]), \
                    ('mallet OAM', context, exported(machine, 0x21C), exported(machine, 0x21F),
                     ref[0x21C], ref[0x21F])
                mallets += 1
            ticks += 1
    return dict(sequences=len(SEQUENCES), ticks=ticks, compared_values=compared,
                mallet_oam=mallets, handlers=sorted(handlers))


def main():
    report = check()
    report.update(status='passed', source_routines=['$CAED', '$CB9D', '$CD13', '$DA99', '$D1E5'],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/nes_export.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(f"PASS NES view of the climbers: {report['ticks']} ticks, handlers {report['handlers']}, "
          f"{report['mallet_oam']} mallet OAM entries equal the original")


if __name__ == '__main__':
    main()
