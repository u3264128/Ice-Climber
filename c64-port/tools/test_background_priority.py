"""NES C777 foreground flags survive C64 sprite pairing and channel reuse."""
import hashlib
import json
import random

from plan_mountains import PlanningMachine
from test_game import BASE
from test_topi_sprites import source_oam
from transplant_objects import map_ram


def object_flags(machine):
    a, labels = machine.ram, machine.labels
    a[labels['state']], a[labels['mountain']] = 1, 31
    machine.call('setup_level')
    machine.call('actors_prepare')
    assert not any(v & 128 for v in a[labels['LOG_COL']:labels['LOG_COL']+a[labels['player_sprites']]])
    cases = 0
    for obj, slot, tile in ((0, 3, 0xE0), (1, 4, 0x18), (2, 5, 0xA0),
                            (3, 6, 0x06), (4, 7, 0xA8), (5, 8, 0xAC),
                            (6, 9, 0x12), (7, 10, 0x14),
                            (8, 24, 0x10), (9, 25, 0x0E), (10, 26, 0x0C)):
        for direction in (1, 255):
            for address, value in ((0x91+obj, 255), (0x9C+obj, 120),
                                   (0xA7+obj, 130), (0xBD+obj, direction),
                                   (0x3DD+obj, tile), (0x3E8+obj, 0x40)):
                a[map_ram(address)] = value
            a[labels['logical_count']] = 0
            a[labels['actor_mask']] = 255
            machine.x = obj
            machine.call('actor_nes_object')
            entries = source_oam(slot, tile, 120, 130, int(direction < 128), 0x40)
            flags = {bool(attribute & 32) for _, _, attribute, _ in entries}
            assert len(flags) == 1
            want = flags.pop()
            count = a[labels['logical_count']]
            assert count > 0
            assert all(bool(a[labels['LOG_COL']+i] & 128) == want for i in range(count)), (
                'NES background priority', obj, slot, direction, want)
            cases += 1
    machine.call('enter_bonus')
    machine.call('actors_prepare')
    assert not any(v & 128 for v in a[labels['LOG_COL']:labels['LOG_COL']+a[labels['logical_count']]])
    return cases


def packets(machine):
    a, labels = machine.ram, machine.labels
    rng = random.Random(0xD01B)
    total = reused = 0
    a[labels['state']] = 1
    a[labels['player_sprites']] = 0
    for count in range(33):
        for base in (0, 32):
            for repeat in range(8):
                a[labels['back_base']] = base
                a[labels['logical_count']] = count
                a[labels['frame']] = repeat & 1
                for i in range(count):
                    for name, value in (('Y', rng.randrange(35, 247)), ('X', rng.randrange(256)),
                                        ('XHI', rng.randrange(2)), ('PTR', 0x40+i),
                                        ('COL', rng.randrange(16) | (rng.randrange(2) << 7)),
                                        ('MC', rng.randrange(2)), ('GROUP', 1)):
                        a[labels['LOG_'+name]+i] = value
                machine.call('schedule_actors')
                mask = 0
                batch = a[labels['pending_batch']]
                for i in range(a[labels['pending_count']]):
                    event = base+i
                    slot = i if i < batch else a[labels['EVENT_SLOT']+event]
                    bit = 1 << slot
                    mask = mask | bit if a[labels['EVENT_COL']+event] & 128 else mask & ~bit
                    assert a[labels['EVENT_BG']+event] == mask, ('reused priority', count, base, i)
                    total += 1
                    reused += i >= batch
    foreground_cases = 0
    for state in (3, 4):
        a[labels['state']] = state
        for base in (0, 32):
            for count in range(33):
                a[labels['EVENT_BG']:labels['EVENT_BG']+64] = bytes([165])*64
                machine.call('priority_reset')
                assert a[labels['EVENT_BG']:labels['EVENT_BG']+64] == bytes(64)
                a[labels['pending_count']] = count
                a[labels['back_base']] = base
                machine.call('packet_priority')
                assert a[labels['EVENT_BG']+base:labels['EVENT_BG']+base+count] == bytes(count)
                foreground_cases += 1
    return dict(cases=33*2*8, events=total, reused_events=reused,
                foreground_scene_cases=foreground_cases)


def pan_packets(machine):
    a, labels = machine.ram, machine.labels
    cases = 0
    for base in (0, 32):
        for count in range(1, 33):
            a[labels['irq_start']] = base
            a[labels['irq_count']] = base+count
            a[labels['back_base']] = base ^ 32
            a[labels['work_lo']] = 4
            a[labels['EVENT_BATCH']+base] = min(count, 8)
            expected = bytes((37*i+count) & 255 for i in range(count))
            a[labels['EVENT_BG']+base:labels['EVENT_BG']+base+count] = expected
            a[labels['EVENT_BG']+(base ^ 32):labels['EVENT_BG']+(base ^ 32)+count] = bytes(count)
            machine.call('pan_shift_events')
            assert a[labels['EVENT_BG']+(base ^ 32):labels['EVENT_BG']+(base ^ 32)+count] == expected
            cases += 1
    return cases


def main():
    machine = PlanningMachine()
    a, labels = machine.ram, machine.labels
    run, load, size = (labels[f'__PRIOCODE_{suffix}__'] for suffix in ('RUN', 'LOAD', 'SIZE'))
    image = (BASE/'c64/build/iceclimber_game.prg').read_bytes()
    expected = image[2+load-machine.load:2+load-machine.load+size]
    assert bytes(a[run:run+size]) == expected
    report = dict(status='passed', object_cases=object_flags(machine), packets=packets(machine),
                  normal_pan_packets=pan_packets(machine),
                  source_entry='EAFC/C777 with normal phase1',
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    assert bytes(a[run:run+size]) == expected
    (BASE/'docs/verification/background_priority.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS original object priority and reused VIC channels', report)


if __name__ == '__main__':
    main()
