"""Compare the bonus permutation cache with the unchanged general scheduler."""
import hashlib
import json
import random

from plan_mountains import PlanningMachine, clone
from test_game import BASE, check_multiplexer
import test_game


ARRAYS = ('LOG_X', 'LOG_XHI', 'LOG_Y', 'LOG_PTR', 'LOG_COL', 'LOG_MC', 'LOG_GROUP')
EVENTS = ('EVENT_LINE', 'EVENT_SLOT', 'EVENT_Y', 'EVENT_X', 'EVENT_MSB',
          'EVENT_PTR', 'EVENT_COL', 'EVENT_MC', 'EVENT_ENA')


def main():
    m = PlanningMachine()
    r, L = m.ram, m.labels
    r[L['BONUS_SORT_COUNT']:L['BONUS_SORT_COUNT']+4] = bytes([255])*4
    m.call('actors_reset')
    assert r[L['BONUS_SORT_COUNT']:L['BONUS_SORT_COUNT']+4] == bytes(4)
    r[L['player_count']] = 2
    reference = clone(m)
    rng = random.Random(940983)
    calls = 0

    def compare(ys, groups, phase):
        nonlocal calls
        n = len(ys)
        for name in ARRAYS:
            values = [rng.randrange(256) for _ in range(n)]
            if name == 'LOG_Y': values = ys
            if name == 'LOG_GROUP': values = groups
            if name == 'LOG_PTR': values = list(range(n))
            if name in ('LOG_XHI', 'LOG_MC'): values = [v & 1 for v in values]
            for machine in (m, reference):
                machine.ram[L[name]:L[name]+n] = bytes(values)
        for machine, state in ((m, 3), (reference, 1)):
            machine.ram[L['state']] = state
            machine.ram[L['frame']] = phase
            machine.ram[L['logical_count']] = n
            machine.ram[L['back_base']] = 32*(phase & 1)
            machine.call('schedule_actors')
        count = r[L['pending_count']]
        assert count == reference.ram[L['pending_count']], (calls, n, phase, ys)
        b = r[L['back_base']]
        for name in EVENTS:
            address = L[name]+b
            assert r[address:address+count] == reference.ram[address:address+count], \
                (calls, name, n, phase, ys, groups)
        if 9 <= n <= 16:
            base = L['BONUS_SORT_ORDER']+16*(phase & 3)
            expected = sorted(range(n), key=lambda i: (ys[i], i), reverse=True)
            assert list(r[base:base+n]) == expected, (calls, 'full pre-drop order')
            assert r[L['BONUS_SORT_COUNT']+(phase & 3)] == n
        calls += 1

    # Each source phase repeats, warms, crosses, then returns. Equal heights
    # exercise strict source-order ties; changing N invalidates old phases.
    for n in range(9, 17):
        for scene in range(20):
            heights = [rng.randrange(35, 247) for _ in range(n)]
            if scene % 3 == 0: heights = [120]*n
            for tick in range(24):
                phase = tick & 3
                dy = min(tick//4, 3)
                ys = [min(246, h+dy) for h in heights]
                if tick >= 16:
                    ys[0], ys[-1] = ys[-1], ys[0]
                compare(ys, [1]*n, phase)
    # Exact paired layer layout of dense bonus scenes: stable caches must
    # retain the complete fourteen entries even when the overload drops pairs.
    for scene in range(100):
        heights = [rng.randrange(35, 247) for _ in range(7)]
        for tick in range(12):
            rotated = heights[:3]+heights[3+(tick & 3):]+heights[3:3+(tick & 3)]
            ys = [v for y in rotated for v in (y, y)]
            compare(ys, [2, 0]*7, tick & 3)
    # General/direct paths and same-count geometry changes remain identical.
    for _ in range(1000):
        n = rng.randrange(1, 33)
        compare([rng.randrange(35, 247) for _ in range(n)], [1]*n, rng.randrange(256))
    cold_pairs = broken_pairs = 0
    for n in (10, 12, 14, 16):
        for scene in range(40):
            for phase in range(4):
                heights = [rng.randrange(35, 246) for _ in range(n//2)]
                if scene % 3 == 0: heights = [120]*(n//2)
                ys = [value for height in heights for value in (height, height)]
                r[L['BONUS_SORT_COUNT']+phase] = 0
                compare(ys, [2, 0]*(n//2), phase)
                cold_pairs += 1
                if scene % 4 == 0:
                    ys[rng.randrange(n)] += 1
                    r[L['BONUS_SORT_COUNT']+phase] = 0
                    compare(ys, [2, 0]*(n//2), phase)
                    broken_pairs += 1
    lift_hits = lift_fallbacks = 0
    for scene in range(128):
        phase=scene&3
        heights=[40,80]+[rng.randrange(110,247) for _ in range(4)]
        old_ys=[y for h in heights for y in (h,h)]
        compare(old_ys,[2,0]*6,phase)
        compare(old_ys[:4]+[35,35]+old_ys[4:],[2,0]*7,phase)
        assert r[L['sched_i']]==0,('Valid12-to14 lift did not bypass sorting',scene)
        lift_hits+=1
        compare(old_ys,[2,0]*6,phase)
        # Equal Y at the last old player violates the new source tie, or
        # a larger Y violates the lifted order even without an equal tie.
        y=40 if scene&1 else 80
        compare(old_ys[:4]+[y,y]+old_ys[4:],[2,0]*7,phase)
        assert r[L['sched_i']]!=0,('Invalid12-to14 lift bypassed fallback',scene)
        lift_fallbacks+=1
    # Retain the independent Python scheduling oracle and every existing
    # random/priority assertion, using the validated compiled CPU for these
    # direct routine calls as well as the cache comparisons above.
    original_machine = test_game.Machine
    try:
        test_game.Machine = PlanningMachine
        check_multiplexer()
    finally:
        test_game.Machine = original_machine
    report = dict(status='passed', cached_scheduler_comparisons=calls,
                  full_pre_drop_order=True, explicit_reset=True,
                  reference_random_scenes=1500, player_priority_scenes=1000,
                  forced_cold_pair_scenes=cold_pairs, broken_pair_fallback_scenes=broken_pairs,
                  validated_lifts=lift_hits, rejected_lifts=lift_fallbacks,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'build_dbg/bonus_sort_cache_equivalence.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS bonus sort cache:', calls, 'phase/tie/cross/count/full-pair packet comparisons')


if __name__ == '__main__':
    main()
