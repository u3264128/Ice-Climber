#!/usr/bin/env python3
"""Executed NES result-screen oracle and C64 event/score regressions."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

from test_original_physics import PRG, Reference
from test_game import start, bcd

BASE = Path(__file__).resolve().parents[1]


def source_score(ram):
    # NES stores six BCD digits with the displayed trailing zero implicit.
    value = 0
    for byte in ram[0x7F1:0x7F4]:
        assert byte >> 4 < 10 and byte & 15 < 10
        value = value*100+(byte >> 4)*10+(byte & 15)
    return value*10


def original_category_points(category, mountain=1, completed=0, count=1):
    reference = Reference()
    ram = reference.ram
    ram[0x59], ram[0x56] = mountain-1, completed
    ram[0x3A3], ram[0x360+category] = category, count
    while ram[0x360+category]:
        ram[0x3A3] = category
        reference.call(0xE9CE, y=category)
    return source_score(ram)


def original_total(mountain, completed, fruit, ice, birds, blocks, condor=False):
    reference = Reference()
    ram = reference.ram
    ram[0x59], ram[0x56] = mountain-1, completed
    units = reference.call(0xEA55) if condor else 0
    ram[0x360:0x365] = bytes((units, fruit, ice, birds, blocks))
    for category in range(5):
        while ram[0x360+category]:
            ram[0x3A3] = category
            reference.call(0xE9CE, y=category)
    return source_score(ram)


def check_oracle():
    cases = 0
    fruit_units = (300, 500, 600, 700, 800, 1000, 2000, 3000, 4000, 5000)
    for mountain in range(1, 33):
        for completed in range(10):
            expected = (1000, fruit_units[completed], 400, 800, mountain*10)
            for category in range(5):
                actual = original_category_points(category, mountain, completed)
                assert actual == expected[category], (mountain, completed, category, actual)
                cases += 1
    # Changing floors neither touches the source score nor result counters.
    reference = Reference()
    ram = reference.ram
    ram[0x5A], ram[0x66], ram[0x90] = 1, 49, 9
    ram[0x7F0:0x7F8] = bytes.fromhex('0000123400005678')
    before = bytes(ram[0x7F0:0x7F8])
    reference.call(0xD1E5)
    assert bytes(ram[0x7F0:0x7F8]) == before and ram[0x5A] != 1
    # F6A4 is the countdown, not a remaining-time points award.
    ram[0x7FA] = ram[0x7FE] = 0x40
    reference.call(0xF6A4)
    assert bytes(ram[0x7F0:0x7F8]) == before
    assert ram[0x7FA:0x7FC] == bytes.fromhex('3999')
    return cases


def event_fixture(object_slot, player=0):
    """The C64 runs the original $D421 itself (nes_objects.asm)."""
    machine = start(mode=2 if player else 1)
    ram, labels = machine.ram, machine.labels
    ram[1] = 0x34               # the transplanted code runs from RAM under I/O
    machine.x, machine.y = player, object_slot
    machine.call('N_D421')
    ram[1] = 0x35
    return machine


def check_event_counters():
    cases = 0
    # Original $D421: object0 is Nitpicker;2..4 seals;5..7 carried ice.
    for kind, object_slot, category in (('seal', 2, None), ('carried_ice', 5, 2),
                                        ('bird', 0, 3), ('icicle', 8, None)):
        machine = event_fixture(object_slot)
        ram, labels = machine.ram, machine.labels
        expected = bytearray(5)
        if category is not None:
            expected[category] = 1
        assert ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+5] == expected, (kind, ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+5])
        assert bcd(ram[0x25:0x27]+ram[0x51:0x52]) == 0, ('events must wait for results', kind)
        reference = Reference()
        reference.call(0xD421, y=object_slot)
        assert reference.ram[0x360:0x365] == expected
        cases += 1
    machine = start(mode=2)
    ram, labels = machine.ram, machine.labels
    for player in (0, 1):
        ram[labels['player_index']] = player
        for _ in range(120):
            machine.call('score_event', 4)
        assert ram[labels['SCORE_COUNTS']+player*5+4] == 99
    snapshot = bytes(ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+10])
    machine.call('player_died')
    assert ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+10] == snapshot
    machine.call('enter_bonus')
    assert ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+10] == snapshot
    machine.call('setup_level')
    assert not any(ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+10])
    return cases+4


def check_result_totals():
    cases = 0
    for mountain in (1, 7, 16, 32):
        for completed in (0, 4, 9, 12):
            for condor in (False, True):
                machine = start(mountain=mountain)
                ram, labels = machine.ram, machine.labels
                ram[labels['completed_mountains']] = completed
                ram[labels['fruit_counts']] = 2
                ram[labels['bonus_winner']] = int(condor)
                ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+5] = bytes((0, 0, 3, 2, 17))
                expected = original_total(mountain, completed, fruit=2, ice=3, birds=2, blocks=17, condor=condor)
                machine.call('enter_results')
                ram[labels['firehit']] = 0x10
                machine.call('results_tick')
                actual = bcd(ram[0x25:0x27]+ram[0x51:0x52])
                assert actual == expected, ('result total', mountain, completed, condor, actual, expected)
                cases += 1
    return cases


def check_gradual_totals():
    """The result screen's own count (no fire button) and two players: every
    climber's total equals the original's for its own counters, the count
    ends, and the high score is the best of them. Ice blocks leave tens:
    the count must not borrow a hundred from an empty total."""
    cases = 0
    counts = [(0, 0, 3, 2, 17), (0, 0, 1, 4, 40)]
    fruits = (2, 5)
    for mode, mountain, completed, winner in itertools.product((1, 2), (1, 17, 32), (0, 9, 11), (0, 1, 2)):
        if mode == 1 and winner == 2:
            continue
        for fast in (False, True):
            machine = start(mode=mode, mountain=mountain)
            ram, labels = machine.ram, machine.labels
            ram[labels['completed_mountains']] = completed
            ram[labels['fruit_counts']], ram[labels['fruit_counts']+1] = fruits
            ram[labels['bonus_winner']] = winner
            ram[labels['SCORE_COUNTS']:labels['SCORE_COUNTS']+10] = bytes(counts[0]+counts[1])
            machine.call('enter_results')
            ticks = 0
            while ram[labels['result_phase']] == 0:
                ram[labels['firehit']] = 0x10 if fast else 0
                machine.call('results_tick')
                ticks += 1
                assert ticks < 2000, ('the result count does not end', mode, mountain, completed, winner)
            scores = [bcd(ram[0x25:0x27]+ram[0x51:0x52])]
            if mode == 2:           # player 1 is loaded at the end; player 2 is in PLAYER_STATES
                states = labels['PLAYER_STATES']+32
                scores.append(bcd(bytes((ram[states+1], ram[states+2], ram[states+31]))))
            for player, actual in enumerate(scores):
                c = counts[player]
                expected = original_total(mountain, completed, fruit=fruits[player], ice=c[2],
                                          birds=c[3], blocks=c[4], condor=winner == player+1)
                assert actual == expected, ('result total', mode, fast, mountain, completed, winner, player, actual, expected)
                cases += 1
            best = bcd(bytes(ram[labels[name]] for name in ('high_score_lo', 'high_score_hi', 'high_score_top')))
            assert best == max(scores), ('high score', best, scores)
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--oracle-only', action='store_true')
    args = parser.parse_args()
    oracle_cases = check_oracle()
    if args.oracle_only:
        print(f'PASS {oracle_cases} executed NES category values, no floor/time points')
        return
    report = dict(status='passed', source_category_cases=oracle_cases,
                  event_cases=check_event_counters(), result_total_cases=check_result_totals(),
                  gradual_and_two_player_cases=check_gradual_totals(),
                  no_floor_points=True, no_remaining_timer_points=True, deferred_result_awards=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/original_scores.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS original NES category values, deferred counters, and complete result totals '
          '(fire or counted, one and two players, high score)')


if __name__ == '__main__':
    main()
