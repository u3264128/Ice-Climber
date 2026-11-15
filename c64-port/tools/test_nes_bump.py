#!/usr/bin/env python3
"""Two climbers that touch push each other, tick by tick ($D212).

The original has no hammer hit on the partner. Instead $D212 runs after
the hammer hits every tick: two climbers on the ground (or nine pixels
apart) are pushed two pixels apart and turned round with walk speed $18; a
climber in the air is nudged one pixel; two climbers in the air trade their
fall speeds $E6/$E8 and lose their latches $86/$88.

The executed original controller and player handlers for both climbers
($CAED $CB9D $CD13 $DA99 $D1E5) followed by $D212, and the two C64
climbers followed by the transplanted $D212 (nes_bump in nes_objects.asm),
get the same pads. After every tick X, Y, facing $62, direction $68, walk
speed $6E and fall speed $E6/$E8 of both climbers must equal the original.
"""
import hashlib
import json
import random

from original_player_reference import PlayerReference
from test_game import BASE, start
from test_nes_export import joystick

MOUNTAIN = 1
STATES = 0x200


class TwoPlayerReference(PlayerReference):
    """PlayerReference with the second controller and climber."""
    def __init__(self, mountain, x0, x1):
        super().__init__(mountain)
        self.pads, self.serials = [0, 0], [0, 0]
        self.hooks = {0x4016: self.port0, 0x4017: self.port1}
        r = self.ram
        r[0x58] = 1                         # two players
        for address, value in ((0x5B, 1), (0x6B, 1), (0x63, 0), (0x67, 192)):
            r[address] = value
        r[0x64], r[0x65] = x0, x1
        r[0x2D] = r[0x2E] = 0               # no respawn immunity

    def port(self, index, value):
        if value is not None:
            if value & 1:
                self.serials = [0, 0]
            return None
        result = (self.pads[index] >> (7-min(self.serials[index], 7))) & 1
        self.serials[index] += 1
        return result

    def port0(self, memory, address, value):
        return self.port(0, value)

    def port1(self, memory, address, value):
        return None if value is not None else self.port(1, value)

    def call_x(self, address, x):
        self.a, self.x, self.y = 0, x, 0
        self.push(0xBF)
        self.push(0xFF)
        self.pc = address
        for _ in range(20000):
            if self.pc == 0xC000:
                return
            self.step()
        raise AssertionError(('NES routine did not return', hex(address), hex(self.pc)))

    def tick2(self, pad0, pad1):
        self.pads = [pad0, pad1]
        r = self.ram
        self.call(0xCAED)
        self.call(0xCB9D)
        r[0x70] = r[0x15]
        self.call_x(0xCD13, 0)
        self.call_x(0xDA99, 0)
        r[0x71] = r[0x17]
        self.call_x(0xCD13, 1)
        self.call_x(0xDA99, 1)
        self.call(0xD1E5)
        before = bytes(r[0x60:0x70]+r[0xE6:0xEA])
        self.call(0xD212)
        return before != bytes(r[0x60:0x70]+r[0xE6:0xEA])


def original(ref, player):
    return tuple(ref[a+player] for a in (0x64, 0x66, 0x62, 0x68, 0x6E, 0xE6, 0xE8))


def ported(r, player):
    s = STATES+32*player
    return ((r[s+3]+256*r[s+4]-52) & 255, r[s+5]-24, 1-r[s+10], r[s+20], r[s+21], r[s+15], r[s+16])


def run(name, x0, x1, pads0, pads1):
    reference = TwoPlayerReference(MOUNTAIN-1, x0, x1)
    ref = reference.ram
    machine = start(mode=2, mountain=MOUNTAIN)
    r, L = machine.ram, machine.labels
    assert r[L['player_count']] == 2
    for player, x in ((0, x0), (1, x1)):
        s = STATES+32*player
        r[s+3], r[s+4] = (x+52) & 255, (x+52) >> 8
        r[s+5] = r[s+6] = 216
        r[s+10] = 1-ref[0x62+player]
        for field in (8,):
            r[s+field] = 1
        for field in (12, 13, 14, 20, 21, 24, 25):
            r[s+field] = 0
    r[L['player_index']] = 0
    machine.call('context_load')
    for player in (0, 1):
        assert ported(r, player)[:3] == original(ref, player)[:3], (name, 'start', player)
    previous = [255, 255]
    bumps = air = swaps = 0
    for tick, pads in enumerate(zip(pads0, pads1)):
        bumped = reference.tick2(*pads)
        machine.call('environment_timers')
        for player, pad in enumerate(pads):
            joy = joystick(pad)
            r[L['player_index']] = player
            if player:
                machine.call('play_context_load')
            r[L['joy']] = joy
            r[L['firehit']] = ~joy & previous[player] & 0x11
            previous[player] = joy
            machine.call('normal_player_tick')
            machine.call('play_context_store')
        r[1] = 0x34                     # the NES code runs with RAM under I/O
        machine.call('nes_export')
        machine.call('nes_bump')
        machine.call('nes_import')
        r[1] = 0x35
        machine.call('nes_apply')
        r[L['player_index']] = 0
        machine.call('play_context_load')
        if bumped:
            bumps += 1
            handlers = (ref[0x6A], ref[0x6B])
            air += any(h & 1 == 0 for h in handlers)
            swaps += all(h & 1 == 0 for h in handlers)
        for player in (0, 1):
            got, want = ported(r, player), original(ref, player)
            assert got == want, ('X, Y, $62, $68, $6E, $E6, $E8 differ', name, tick, pads, player,
                                 got, want)
    return dict(name=name, ticks=len(pads0), bumps=bumps, in_air=air, both_in_air=swaps)


def sequences():
    yield 'walk_into_each_other', 60, 120, [1]*80, [2]*80
    yield 'stand_and_walk_in', 80, 130, [0]*80, [2]*80
    yield 'jump_into_standing', 70, 90, [0x81]+[1]*50, [0]*51
    yield 'both_jump_together', 80, 92, [0x80]+[0]*50, [0x80]+[0]*50
    yield 'jump_over_walking', 60, 110, [1]*10+[0x81]+[1]*40, [2]*51
    yield 'land_on_partner', 76, 88, [0]*3+[0x81]+[1]*40, [0]*44
    yield 'held_swing_beside', 70, 84, [0x40]*70, [2]*20+[0]*50
    yield 'swing_again_at_once', 60, 160, [0x40]+[0]*20+[0x40]+[0]*30, [0]*52
    for offset in range(0, 12):
        yield f'both_jump_{offset}', 70, 70+offset, [0x81]+[1]*45, [0x82]+[2]*45
        yield f'late_jump_{offset}', 60, 100+offset, [1]*12+[0x81]+[1]*40, [2]*4+[0x82]+[2]*48
    rng = random.Random(0xD212)
    choices = [0, 1, 2, 0x80, 0x81, 0x82, 0x40, 0x41, 0x42]
    for trial in range(24):
        pads0, pads1 = [], []
        for pads in (pads0, pads1):
            while len(pads) < 240:
                pad = rng.choice(choices)
                # A direction within three air ticks of the takeoff starts
                # the C64 jump grace (jump_grace.asm, test_jump_grace.py).
                pads.extend([pad]+[pad & 3]*(3 if pad & 0x80 else 0))
                pads.extend([rng.choice((0, 1, 2))]*rng.randrange(1, 20))
        yield f'random_{trial}', rng.randrange(40, 120), rng.randrange(100, 200), pads0[:240], pads1[:240]


def handler(r, s):
    """nes_handler's original handler of a C64 climber (onground, air_init
    bit 7, rise_int), as nes_export gives it to the objects and $D212."""
    if r[s+8]:
        return 3 if r[s+8] == 2 else 1
    if r[s+14] & 0x80:
        return 2
    return 4 if r[s+18] else 6


def check_bonus():
    """The bonus stage runs $D212 too ($CCBC) with both floors 1 ($C399).
    nes_bonus_bump tests the distance before it exports the climbers: each
    case here gives the same climbers to the original $D212 and to it."""
    from test_original_physics import Reference
    machine = start(mode=2, mountain=MOUNTAIN)
    machine.call('enter_bonus')
    r, L = machine.ram, machine.labels
    assert r[L['state']] == 3 and r[L['player_count']] == 2
    rng = random.Random(0xCCBC)
    cases = bumps = 0
    grounds = ((1, 1), (2, 1), (0, 1), (1, 0), (0, 0))
    for trial in range(1500):
        x0 = rng.choice((2, 60, 128, 250, rng.randrange(256)))
        x1 = (x0+rng.randrange(-12, 13)) & 255
        y0 = rng.randrange(40, 200)
        y1 = y0+rng.choice((0, 3, -7, 20, -20, 21, -21, rng.randrange(-30, 31)))
        reference = Reference()
        ref = reference.ram
        r[L['bonus_out']] = r[L['bonus_out']+1] = 0
        for player, (x, y, ground) in enumerate(zip((x0, x1), (y0, y1), rng.choice(grounds))):
            s = STATES+32*player
            r[s] = 3
            r[s+3], r[s+4] = (x+52) & 255, (x+52) >> 8
            r[s+5] = r[s+6] = y+24
            r[s+8] = ground
            r[s+10] = rng.randrange(2)
            r[s+13] = 0
            r[s+14] = rng.choice((0x0C, 0x8C, 0x2C, 0xAC))
            r[s+15], r[s+16] = rng.randrange(9), rng.randrange(256)
            r[s+18] = rng.choice((0, 3))
            r[s+20] = rng.choice((0, 1, 2))
            r[s+21] = rng.randrange(25)
            r[s+25] = 0
            for nes, value in ((0x5A, 1), (0x2D, 0), (0x6A, handler(r, s)), (0x64, x),
                               (0x66, y), (0x62, 1-r[s+10]), (0x68, r[s+20]),
                               (0x6E, r[s+21]), (0xE6, r[s+15]), (0xE8, r[s+16]),
                               (0x86, r[s+14] >> 7), (0x88, r[s+14] >> 4 & 7)):
                ref[nes+player] = value
        before = bytes(r[STATES:STATES+64])
        r[L['player_index']] = 0
        machine.call('context_load')
        reference.call(0xD212)
        machine.call('nes_bonus_bump')
        bumped = bytes(r[STATES:STATES+64]) != before
        bumps += bumped
        for player in (0, 1):
            s = STATES+32*player
            got = ported(r, player)+(int(r[s+14] & 0xF0 != 0),)
            want = original(ref, player)+(int(bool(ref[0x86+player] or ref[0x88+player])),)
            assert got == want, ('bonus $D212', trial, x0, x1, y0, y1, player, got, want)
        cases += 1
    assert bumps, 'no bonus bump'
    return dict(cases=cases, bumps=bumps)


def main():
    bonus = check_bonus()
    cases = [run(*case) for case in sequences()]
    total = {key: sum(c[key] for c in cases) for key in ('ticks', 'bumps', 'in_air', 'both_in_air')}
    assert total['bumps'] and total['in_air'] and total['both_in_air'], total
    report = dict(status='passed', mountain=MOUNTAIN, cases=cases, **total, bonus=bonus,
                  source_routines=['$CAED', '$CB9D', '$CD13', '$DA99', '$D1E5', '$D212', '$D2BC', '$D2D9'],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/nes_bump.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(f"PASS original body bump: {total['ticks']} two-player ticks, {total['bumps']} bumps "
          f"({total['in_air']} with a climber in the air, {total['both_in_air']} fall speed trades) "
          f"equal the original; bonus stage: {bonus['bumps']} of {bonus['cases']} cases bump")


if __name__ == '__main__':
    main()
