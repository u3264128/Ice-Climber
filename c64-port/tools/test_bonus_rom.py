#!/usr/bin/env python3
"""The bonus stage's rules against the executed original routines.

Fruit touches ($D301 with the $DB1D boxes of objects 3..6), the condor
catch ($D507), the condor's flight ($F78B), the camera pans ($D890 and
$D8AF with $EC51), falls out ($D724) and the countdown ($F6A4) run on the
original PRG and on the C64 routines from the same states.

Coordinates: C64 climber X = source X+52, object X = source X+56, screen
Y = source Y+9; camera c shows source scroll page 1 / 0 at c = 0 and page 0
/ 240-c above it (c = 240 is the top); a fruit's C64 height is 207-Y for
its $F6F2 table Y (they appear in the first, bottom view).
"""
import itertools
import random

from test_game import start
from test_original_physics import Reference
from transplant_sound import ZERO_PAGE

MUSIC_REQUEST = ZERO_PAGE[0xFB]   # the engine's $FB

FRUIT_X = (0x60, 0xA0, 0x30, 0xC0)          # $F6EE
FRUIT_Y = (0x10, 0x40, 0x98, 0x98)          # $F6EA


def source_view(camera):
    """(scroll, page) of the original for C64 camera 0..240."""
    if camera == 0:
        return 0, 1
    return 240-camera, 0


def bonus_machine(players=1):
    machine = start(mode=players)
    machine.ram[machine.labels['bonus_requested']] = 1
    machine.frame()
    assert machine.ram[machine.labels['state']] == 3
    return machine


def check_fruits(rng):
    """$D301: which fruit (if any) a climber at (X, Y) touches."""
    m = bonus_machine()
    r, L = m.ram, m.labels
    ps = L['PLAYER_STATES']
    cases = touched = 0
    for fruit in range(4):
        for camera in (0, 40, 92):
            for dx, dy in itertools.product(range(-20, 21), range(-24, 25)):
                px = (FRUIT_X[fruit]+dx) & 255
                screen = FRUIT_Y[fruit]+camera      # $EC51 moved it with each pan
                if screen >= 0xF8:
                    continue
                py = (screen+dy) & 255
                if not 20 <= py < 200:
                    continue
                ref = Reference()
                s = ref.ram
                s[0x55] = 2
                s[0x5A], s[0x6A], s[0x2D] = 1, 1, 0
                s[0x5B] = 0                           # one climber
                s[0x64], s[0x66] = px, py
                for k in range(11):
                    s[0x91+k] = 0
                s[0x91+3+fruit], s[0x9C+3+fruit], s[0xA7+3+fruit] = 0xFF, FRUIT_X[fruit], screen
                ref.call(0xD301)
                want = s[0x91+3+fruit] == 1
                assert want == bool(s[0x361]), (fruit, px, py)
                # the C64 climber
                r[L['bonus_camera']], r[L['bonus_camera']+1] = camera, 0
                r[L['fruit_mask']] = 1 << fruit
                r[L['fruit_counts']] = r[L['fruit_counts']+1] = 0
                r[L['bonus_out']] = 0
                x = px+52
                r[ps+3], r[ps+4], r[ps+5] = x & 255, x >> 8, py+9
                m.call('bonus_fruits')
                got = r[L['fruit_mask']] == 0
                assert got == want, ('fruit touch', fruit, camera, dx, dy, got, want)
                assert r[L['fruit_counts']] == int(want)
                cases += 1
                touched += want
    return cases, touched


def check_catch(rng):
    """$D507: the condor's legs, the climber's X afterwards and the winner."""
    m = bonus_machine(2)
    r, L = m.ram, m.labels
    cases = caught = 0
    for _ in range(40000):
        camera = rng.choice((0, 240, 240, 240, 236, 200))
        condor, direction = rng.randrange(256), rng.randrange(2)
        fruit = (rng.randrange(5), rng.randrange(5))
        px = (condor+rng.randrange(-4, 20)) & 255
        py = rng.randrange(0, 60)
        player = rng.randrange(2)
        scroll, page = source_view(camera)
        ref = Reference()
        s = ref.ram
        s[0x13], s[0x27] = scroll, page
        s[0x64+player], s[0x66+player] = px, py
        s[0xD6], s[0xD5] = condor, direction
        s[0x361], s[0x366] = fruit
        s[0x5F] = player
        ref.x = player
        ref.push(0xBF)
        ref.push(0xFF)
        ref.pc = 0xD507
        while ref.pc != 0xC000:
            ref.step()
        r[L['bonus_camera']], r[L['bonus_camera']+1] = camera, 0
        x = condor+56
        r[L['condor_xlo']], r[L['condor_xhi']], r[L['condor_dir']] = x & 255, x >> 8, direction
        r[L['fruit_counts']], r[L['fruit_counts']+1] = fruit
        r[L['bonus_winner']] = r[L['bonus_reason']] = 0
        r[MUSIC_REQUEST] = 0
        r[L['player_index']] = player
        x = px+52
        r[L['pxlo']], r[L['pxhi']], r[L['py']] = x & 255, x >> 8, (py+9) & 255
        m.call('bonus_catch')
        want = s[0x1E]
        got = r[L['bonus_winner']]
        assert got == want, ('condor catch', camera, condor, direction, fruit, px, py, player, got, want)
        if want:
            assert r[L['pxlo']] | r[L['pxhi']] << 8 == s[0x64+player]+52, ('caught X', s[0x64+player])
            # $D53C: mountain-complete music, $4D = $20 slow ticks held
            assert r[MUSIC_REQUEST] == 0x10 and r[L['bonus_end_wait']] == 176
        cases += 1
        caught += bool(want)
    return cases, caught


def check_condor_flight(rng):
    """$F78B: one pixel a tick, wrapping; at $60 a new direction."""
    m = bonus_machine()
    r, L = m.ram, m.labels
    cases = 0
    for condor, direction in itertools.product(range(256), (0, 1)):
        ref = Reference()
        s = ref.ram
        s[0xD6], s[0xD5], s[0x13], s[0x27] = condor, direction, 1, 0
        ref.call(0xF78B)
        x = condor+56
        r[L['condor_xlo']], r[L['condor_xhi']], r[L['condor_dir']] = x & 255, x >> 8, direction
        m.call('bonus_condor_move')
        got = (r[L['condor_xlo']] | r[L['condor_xhi']] << 8)-56
        assert got == s[0xD6], ('condor X', condor, direction, got, s[0xD6])
        if s[0xD6] != 0x60:
            assert r[L['condor_dir']] == s[0xD5] == direction
        cases += 1
    return cases


def check_pans_and_falls(rng):
    """$D890/$D8AF and $D724 over random standing climbers and cameras."""
    m = bonus_machine(2)
    r, L = m.ram, m.labels
    ps = L['PLAYER_STATES']
    cases = pans = 0
    for _ in range(3000):
        camera = rng.randrange(0, 61)*4
        scroll, page = source_view(camera)
        ys = [rng.randrange(40, 215), rng.randrange(40, 215)]
        handlers = [rng.choice((1, 1, 2, 3, 4)), rng.choice((1, 1, 3, 4))]
        ref = Reference()
        s = ref.ram
        s[0x55], s[0x13], s[0x27], s[0x8C], s[0x8B] = 2, scroll, page, 0, 0
        for p in (0, 1):
            s[0x6A+p], s[0x5A+p], s[0x66+p] = handlers[p], 1, ys[p]
        for k in range(11):
            s[0x91+k] = 0
        onground = {1: 1, 2: 0, 3: 2, 4: 0}
        r[L['bonus_camera']], r[L['bonus_camera']+1] = camera, 0
        r[L['bonus_pan']] = 0
        r[L['bonus_out']] = r[L['bonus_out']+1] = 0
        r[L['fruit_mask']] = 0
        for p in (0, 1):
            r[ps+32*p+5], r[ps+32*p+6], r[ps+32*p+8] = ys[p]+9, ys[p]+9, onground[handlers[p]]
        for tick in range(16):
            ref.call(0xD724)
            ref.call(0xD8AF)
            ref.call(0xD890)
            m.call('bonus_falls')
            m.call('bonus_pan_step')
            m.call('bonus_pan_start')
            view = (240-s[0x13] if s[0x27] == 0 else 0) if s[0x13] or s[0x27] == 0 else 0
            if s[0x27] == 0 and s[0x13] == 0:
                view = 240
            assert r[L['bonus_camera']] == view, ('camera', camera, tick, r[L['bonus_camera']], view)
            assert bool(r[L['bonus_pan']]) == bool(s[0x8C]), ('pan running', camera, tick)
            for p in (0, 1):
                out = s[0x6A+p] == 0
                assert bool(r[L['bonus_out']+p]) == out, ('fell out', p, tick, ys, handlers)
                if not out:
                    assert r[ps+32*p+5] == s[0x66+p]+9, ('screen Y', p, tick, r[ps+32*p+5], s[0x66+p])
            pans += bool(s[0x8C])
        cases += 1
    return cases, pans


def check_countdown():
    """$F6A4: 40.00 reaches zero after 2395 ticks."""
    ref = Reference()
    s = ref.ram
    s[0x7FA], s[0x7FB] = 0x40, 0
    ticks = 0
    while s[0x7FA] | s[0x7FB]:
        if s[0x3B]:
            s[0x3B] -= 1                    # $CB9D: the fast timers
        ref.call(0xF6A4)
        ticks += 1
    m = bonus_machine()
    r, L = m.ram, m.labels
    count = 0
    while not r[L['bonus_reason']]:
        m.call('bonus_timer')
        count += 1
        assert count < 4000
    assert count == ticks, (count, ticks)
    assert r[MUSIC_REQUEST] == 0x80 and r[L['bonus_end_wait']] == 55     # $F6DB
    return ticks


def main():
    rng = random.Random(31)
    fruit_cases, touched = check_fruits(rng)
    catch_cases, caught = check_catch(rng)
    flights = check_condor_flight(rng)
    pan_cases, pans = check_pans_and_falls(rng)
    countdown = check_countdown()
    print(f'PASS bonus rules = original: {fruit_cases} fruit touches ({touched} hits), {catch_cases} condor '
          f'catches ({caught} caught), {flights} condor steps, {pan_cases} pan/fall sequences ({pans} pan '
          f'ticks), countdown {countdown} ticks')


if __name__ == '__main__':
    main()
