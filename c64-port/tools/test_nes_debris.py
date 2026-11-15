#!/usr/bin/env python3
"""The debris of broken bricks, tick by tick ($D91C, $D9CC, $EC95).

The executed original controller and player handlers (PlayerReference:
$CAED $CB9D $CD13 $DA99 $D1E5, where $DA99/$DDC9 call $D91C for each broken
brick) followed by $D9CC, and the C64 climber followed by nes_debris_start
and the transplanted $D9CC (nes_objects.asm), get the same pads: jumps under
the bricks of several mountains. After every tick the six debris OAM
entries $02D0-$02E7 (Y, tile, attribute with flips and palette, X) and the
motion bytes $0640-$0667 must equal the original.

Two fixtures check what the climbs cannot reach: the palette of a brick on
every floor ($D957: 2 from floor 6, else 3, $D9AD's earth colours from
floor 3) and the pan step of the OAM entries ($EC95).
"""
import hashlib
import json
import random

from original_player_reference import PlayerReference
from test_game import BASE, start
from test_nes_export import joystick
from test_original_physics import Reference
from transplant_objects import map_ram

OAM = range(0x02D0, 0x02E8)
MOTION = range(0x0640, 0x0668)


def c64(machine, nes):
    address = map_ram(nes)
    if isinstance(address, str):
        address = machine.labels[address]
    if 0xD000 <= address < 0xE000:
        return machine.under_io[address-0xD000]
    return machine.ram[address]


def run(mountain, x, pads):
    reference = PlayerReference(mountain-1)
    ref = reference.ram
    for slot in range(6):
        ref[0x02D0+4*slot] = 0xF8           # the stage start's empty OAM
        ref[0x02D3+4*slot] = 0
    ref[0x063F] = 0
    machine = start(mountain=mountain)
    r, L = machine.ram, machine.labels
    for nes in OAM:
        assert c64(machine, nes) == ref[nes], ('stage start OAM', mountain, hex(nes))
    ref[0x64] = x
    r[L['pxlo']], r[L['pxhi']] = (x+52) & 255, (x+52) >> 8
    r[L['invul_t']] = ref[0x2D] = 0
    machine.call('play_context_store')
    pieces = flips = 0
    tiles = set()
    for tick, pad in enumerate(pads):
        before = [ref[a] for a in OAM[::4]]
        reference.tick(pad)
        reference.call(0xD9CC)
        machine.joystick = joystick(pad)
        machine.call('read_joy')
        machine.call('environment_timers')
        machine.call('normal_player_tick')
        machine.call('play_context_store')
        r[1] = 0x34                     # the NES code runs with RAM under I/O
        machine.call('nes_export')
        machine.call('nes_debris_start')
        machine.call('nes_debris_tick')  # the C64 skips it without debris
        machine.call('nes_import')
        r[1] = 0x35
        machine.call('nes_apply')
        pieces += sum(1 for old, a in zip(before, OAM[::4]) if old == 0xF8 and ref[a] != 0xF8)
        for a in OAM[::4]:
            if ref[a] != 0xF8:
                tiles.add(ref[a+1])
                flips |= 1 << (ref[a+2] >> 6)
        context = (mountain, x, tick, pad)
        got = [c64(machine, nes) for nes in OAM]
        want = [ref[nes] for nes in OAM]
        assert got == want, ('debris OAM differs', context, got, want)
        got = [c64(machine, nes) for nes in MOTION]
        want = [ref[nes] for nes in MOTION]
        assert got == want, ('debris motion differs', context, got, want)
        assert bool(r[L['debris_brown']]) == bool(ref[0x063F]), ('palette 3 reload', context)
    return pieces, tiles, flips


def check_palettes():
    """$D957/$D9AD for a brick on each floor, against debris_note."""
    machine = start()
    r, L = machine.ram, machine.labels
    cases = 0
    for wrld in range(9):
        for layer, value in ((0, 1), (1, 1), (1, 2), (1, 3)):
            r[L['wrld']], r[L['break_layer']] = wrld, layer
            r[L['floor_lower']+5] = value
            r[L['debris_pend']] = 0
            machine.x = 5
            machine.call('debris_note')
            pend = r[L['debris_pend']]
            d7 = wrld+1
            assert pend & 3 == (2 if d7 >= 6 else 3), ('palette', wrld)
            assert bool(pend & 0x40) == (3 <= d7 < 6), ('earth reload', wrld)
            assert bool(pend & 0x80) == (layer == 1 and value == 2), ('tile $0B', wrld, layer, value)
            cases += 1
    return cases


def check_pan():
    """$EC95 moves every OAM entry four lines down; the debris entries too."""
    machine = start()
    r = machine.ram
    rng = random.Random(0xEC95)
    cases = 0
    for trial in range(300):
        reference = Reference()
        ref = reference.ram
        ref[0x55] = 1
        values = [rng.choice((0xF8, 0xF1, 0xF2, 0xF3, 0xEE, 0, 4, rng.randrange(256))) for _ in range(6)]
        for slot, value in enumerate(values):
            ref[0x02D0+4*slot] = value
            r[map_ram(0x02D0)+4*slot] = value
        reference.call(0xEC95)
        r[1] = 0x34
        machine.call('nes_debris_pan')
        r[1] = 0x35
        assert [r[map_ram(0x02D0)+4*s] for s in range(6)] == [ref[0x02D0+4*s] for s in range(6)], \
            ('pan step', values)
        cases += 1
    return cases


def main():
    cases = []
    for mountain in (1, 2, 4, 8, 13, 20):
        for x in range(8, 216, 12):
            cases.append((mountain, x, [0x80]+[0]*60))
            cases.append((mountain, x, [1]*6+[0x81]+[1]*50))
            cases.append((mountain, x, [2]*6+[0x82]+[2]*50))
    pieces, tiles, flips = 0, set(), 0
    for case in cases:
        p, t, f = run(*case)
        pieces += p
        tiles |= t
        flips |= f
    assert pieces and tiles == {0x0A, 0x0B} and flips == 15, (pieces, tiles, flips)
    palettes, pans = check_palettes(), check_pan()
    report = dict(status='passed', sequences=len(cases), pieces=pieces, tiles=sorted(tiles),
                  palette_cases=palettes, pan_cases=pans,
                  source_routines=['$D91C', '$D957', '$D9AD', '$D9CC', '$EC95'],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/nes_debris.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(f'PASS original debris: {len(cases)} climbs, {pieces} pieces (tiles $0A and $0B, all four '
          f'flips) equal the original; {palettes} palette and {pans} pan cases')


if __name__ == '__main__':
    main()
