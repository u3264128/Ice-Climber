#!/usr/bin/env python3
"""The original death after an object touches a climber, tick by tick.

The executed original runs $D446 (an object touched player 0), then every
frame its timers ($CB9D), the player handler (7: $D0AA, $D127/$D133 and
$CD95), $D463 (below the screen) and $EB7F/$EB8A (back on a floor). The C64
climber enters the same death through nes_objects.asm. In every tick the
frozen timer $32, the falling body Y, the spin frame $6C, the lost life,
the slow wait $3F and the place where the climber reappears must equal the
original.
"""
import hashlib
import json

from original_player_reference import PlayerReference
from test_game import BASE, start
from transplant_objects import map_ram


def run(timer_phase, protected=False, lives=None):
    reference = PlayerReference()
    ref = reference.ram
    machine = start()
    r, L = machine.ram, machine.labels
    if lives is not None:
        r[L['lives']] = lives
    ref[0x64] = (r[L['pxlo']]-52) & 255
    ref[0x66] = r[L['py']]-24
    ref[0x20] = r[L['lives']]
    ref[0x31] = timer_phase
    r[L['timer_divider']] = 10-timer_phase
    ref[0x2D] = r[L['invul_t']] = 1 if protected else 0
    machine.call('play_context_store')
    # $D446 with X = 0: the C64 side as nes_apply leaves it.
    reference.call(0xD446)
    r[map_ram(0x0382)] = ref[0x0382]
    r[L['nes_dying']], r[L['nes_death_t']] = 1, 0x40
    r[L['nes_spin']] = r[L['nes_spin_t']] = 0
    trace = []
    for tick in range(1, 400):
        reference.tick(0)
        reference.call(0xD463)
        reference.call(0xEB7F)
        machine.call('environment_timers')
        machine.call('player_dying_tick')
        dying = r[L['nes_dying']]
        context = (timer_phase, protected, tick)
        if ref[0x6A] == 7 and ref[0x5A]:
            assert dying in (1, 2), ('still dying', context, dying)
            if ref[0x32]:
                assert dying == 1 and r[L['nes_death_t']] == ref[0x32], ('frozen timer', context)
                assert r[L['py']] == ref[0x66]+24, ('frozen body', context)
            else:
                assert dying == 2, ('falling', context, dying)
                assert r[L['py']] == ref[0x66]+24, ('falling body Y', context, r[L['py']], ref[0x66]+24)
                assert r[L['nes_spin']] == ref[0x6C], ('spin frame', context, r[L['nes_spin']], ref[0x6C])
        elif ref[0x5A] == 0:
            assert dying == 3, ('below the screen', context, dying)
            assert r[L['lives']] == ref[0x20], ('lives', context, r[L['lives']], ref[0x20])
            assert r[L['nes_death_t']] == ref[0x3F], ('slow wait $3F', context, r[L['nes_death_t']], ref[0x3F])
        else:
            assert dying == 0, ('back on a floor', context, dying)
            assert (r[L['curfloor']]+1, r[L['py']]-24, (r[L['pxlo']]-52) & 255) == (ref[0x5A], ref[0x66], ref[0x64]), \
                ('respawn place', context, (r[L['curfloor']]+1, r[L['py']]-24, (r[L['pxlo']]-52) & 255),
                 (ref[0x5A], ref[0x66], ref[0x64]))
            assert r[L['lives']] == ref[0x20]
            trace.append(tick)
            return dict(phase=timer_phase, protected=protected, respawn_tick=tick, lives=ref[0x20])
    raise AssertionError(('the climber did not come back', timer_phase, protected))


def last_climber(timer_phase):
    """No spare climber left (lives 0): the original never brings it back
    ($EB8E: BMI on the negative lives), and the C64 shows GAME OVER when the
    same slow $3F wait ends."""
    reference = PlayerReference()
    ref = reference.ram
    machine = start()
    r, L = machine.ram, machine.labels
    r[L['lives']] = 0
    ref[0x64] = (r[L['pxlo']]-52) & 255
    ref[0x66] = r[L['py']]-24
    ref[0x20], ref[0x21] = 0, 0xFC          # one player: no second climber
    ref[0x31] = timer_phase
    r[L['timer_divider']] = 10-timer_phase
    ref[0x2D] = r[L['invul_t']] = 0
    machine.call('play_context_store')
    reference.call(0xD446)
    r[map_ram(0x0382)] = ref[0x0382]
    r[L['nes_dying']], r[L['nes_death_t']] = 1, 0x40
    r[L['nes_spin']] = r[L['nes_spin_t']] = 0
    waited = None
    for tick in range(1, 400):
        reference.tick(0)
        reference.call(0xD463)
        reference.call(0xEB7F)
        machine.call('environment_timers')
        machine.call('player_dying_tick')
        assert ref[0x5A] == 0 or ref[0x6A] == 7, ('the original brought the last climber back', timer_phase, tick)
        if ref[0x5A] == 0 and ref[0x3F] == 0 and waited is None:
            waited = tick
        if r[L['state']] == 2:
            assert r[L['result_game_over']] and ref[0x20] == 0xFF == r[L['lives']], (timer_phase, tick)
            assert waited == tick, ('GAME OVER after the original wait', timer_phase, tick, waited)
            return tick
    raise AssertionError(('no GAME OVER for the last climber', timer_phase))


def main():
    cases = [run(phase, protected) for phase in range(11) for protected in (False, True)]
    # The last spare climber (lives 1) comes back with lives 0, as in the
    # original; with lives 0 the next loss ends the game.
    last = [run(phase, False, lives=1) for phase in (0, 5, 10)]
    assert all(case['lives'] == 0 for case in last), last
    game_over = [last_climber(phase) for phase in (0, 5, 10)]
    report = dict(status='passed', cases=cases,
                  source_routines=['$D446', '$CB9D', '$D0AA', '$D127', '$D133', '$CD95', '$D463', '$EB7F'],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/nes_death.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    ticks = sorted({case['respawn_tick'] for case in cases})
    print(f'PASS original death: {len(cases)} timer phases and protections; frozen timer, fall, spin, '
          f'lost life, $3F wait and respawn equal the original (back after {ticks[0]}-{ticks[-1]} ticks); '
          f'the last spare climber comes back, the one after it ends the game (GAME OVER after {game_over} ticks)')


if __name__ == '__main__':
    main()
