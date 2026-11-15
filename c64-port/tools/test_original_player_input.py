"""Full original controller/player-handler comparisons, including stops and digging.

The oracle executes CAED, CB9D, CD13, DA99 and D1E5 from the NES ROM.
It does not substitute a Python movement model for the original handlers.
"""
import hashlib
import json

from original_player_reference import PlayerReference
from test_game import BASE, start


def target_tick(machine, pad, bonus=False):
    joy = 255
    for source, target in ((128, 1), (64, 16), (1, 8), (2, 4)):
        if pad & source:
            joy &= 255-target
    machine.joystick = joy
    machine.call('read_joy')
    machine.call('bonus_player_tick' if bonus else 'normal_player_tick')


def compare(reference, machine, context, y_offset=24):
    r, a, L = reference.ram, machine.ram, machine.labels
    expected = dict(x=r[0x64], y=r[0x66], grounded=r[0x6A] in (1, 3, 5),
                    direction=r[0x68], run=r[0x6E], stop_timer=r[0x32],
                    gravity=r[0xE6], gravity_fraction=r[0xE8],
                    walk_fraction=r[0x76], air_fraction=r[0x72], y_fraction=r[0xEA])
    actual = dict(x=(int.from_bytes(a[L['pxlo']:L['pxhi']+1], 'little')-52) & 255,
                  y=a[L['py']]-y_offset, grounded=bool(a[L['onground']]),
                  **{key:a[L[name]] for key, name in
                     (('direction', 'move_dir'), ('run', 'walk_time'), ('stop_timer', 'skid_t'),
                      ('gravity', 'fall_int'), ('gravity_fraction', 'fall_frac'),
                      ('walk_fraction', 'walk_frac'), ('air_fraction', 'air_xfrac'),
                      ('y_fraction', 'y_frac'))})
    assert actual == expected, (context, actual, expected, 'handler', r[0x6A])
    return [actual['x'], actual['y']]


def flat_fixture(floor):
    reference, machine = PlayerReference(), start()
    r, a, L = reference.ram, machine.ram, machine.labels
    camera = min(max(floor-1, 0), 5)
    screen_floor = floor-camera
    r[0x400:0x4D8] = r[0x500:0x5D8] = bytes([255])*216
    r[0x400+24*floor:0x400+24*(floor+1)] = bytes([1])*24
    a[L['floor_upper']:L['floor_upper']+216] = bytes(216)
    a[L['floor_lower']:L['floor_lower']+216] = bytes(216)
    a[L['floor_upper']+24*floor:L['floor_upper']+24*(floor+1)] = bytes([1])*24
    a[L['floor_types']:L['floor_types']+9] = bytes(9)
    r[0x5A], r[0x90], r[0x66], r[0x64] = floor+1, camera+4, 192-48*screen_floor, 96
    a[L['curfloor']], a[L['cam']], a[L['py']], a[L['maxfloor']] = floor, camera, r[0x66]+24, floor
    a[L['pxlo']:L['pxhi']+1] = (148).to_bytes(2, 'little')
    return reference, machine


def check_starts():
    cases, ticks = [], 0
    for floor in (0, 4, 5, 7):
        for direction in (1, 2):
            opposite = 3-direction
            patterns = {
                'stationary': [128|direction]+[direction]*39,
                'running': [direction]*24+[128|direction]+[direction]*39,
                'new_stop_neutral_A': [direction]*8+[128]+[0]*39,
                'new_stop_reverse_A': [direction]*8+[128|opposite]+[opposite]*39,
                'old_stop_A': [direction]*8+[0]+[128|opposite]+[opposite]*39,
                'release_two_A': [direction]*8+[0]*2+[128|opposite]+[opposite]*39,
                'release_one_A': [direction]*8+[0]+[128|direction]+[direction]*39,
                'held_A': [128|direction]*70,
                'late_air_direction': [128]+[0]*25+[direction]*19,
                'air_reverse_ignored': [128|direction]+[opposite]*39,
            }
            for name, sequence in patterns.items():
                reference, machine = flat_fixture(floor)
                for tick, pad in enumerate(sequence, 1):
                    reference.tick(pad)
                    target_tick(machine, pad)
                    compare(reference, machine, (floor+1, direction, name, tick))
                    ticks += 1
                cases.append(dict(floor=floor+1, direction=direction, start=name,
                                  ticks=len(sequence)))
    return cases, ticks


def check_digging():
    cases, ticks = [], 0
    for direction in (0, 1, 2):
        reference, machine = PlayerReference(), start()
        initial = bytes(reference.ram[0x400:0x5D8])
        sequence = [128|direction]+[direction]*39+[0]*3+[128|direction]+[direction]*39
        trajectory = []
        for tick, pad in enumerate(sequence, 1):
            reference.tick(pad)
            target_tick(machine, pad)
            trajectory.append(compare(reference, machine, ('dig then jump', direction, tick)))
            for layer, base in ((0, 0x400), (1, 0x500)):
                raw = reference.ram[base:base+216]
                expected = bytes(0 if v == 255 else 2 if v == 4 and not layer else 3 if v in (0, 3, 4) else v for v in raw)
                address = machine.labels['floor_lower' if layer else 'floor_upper']
                actual = bytes(machine.ram[address:address+216])
                assert actual == expected, ('dig map', direction, tick, layer,
                                           [(i, x, y) for i, (x, y) in enumerate(zip(actual, expected)) if x != y])
            ticks += 1
        removed = sum(a != b for a, b in zip(initial, reference.ram[0x400:0x5D8]))
        assert removed, ('digging did not alter actual map', direction)
        cases.append(dict(direction=direction, ticks=len(sequence), changed_cells=removed,
                          trajectory=trajectory))
    return cases, ticks


def check_walkoffs():
    ticks = 0
    for direction in (0, 1, 2):
        reference, machine = flat_fixture(4)
        r, a, L = reference.ram, machine.ram, machine.labels
        for tick in range(4):
            reference.tick(direction)
            target_tick(machine, direction)
            compare(reference,machine,('walkoff run',direction,tick))
            ticks += 1
        r[0x400+96:0x400+120] = bytes([255])*24
        a[L['floor_upper']+96:L['floor_upper']+120] = bytes(24)
        for tick in range(16):
            pad = direction if tick == 0 else 1 if direction != 1 else 2
            reference.tick(pad)
            target_tick(machine,pad)
            compare(reference,machine,('walkoff and air control',direction,tick))
            ticks += 1
    return 3,ticks


def check_dig_then_standing_climb():
    reference, machine = PlayerReference(), start()
    sequence = [1]*7+[0]*2+([128]+[0]*39)*3+[130]+[2]*35
    trajectory = []
    for tick, pad in enumerate(sequence, 1):
        if pad & 128:
            assert reference.ram[0x68] == reference.ram[0x6E] == 0
            assert machine.ram[machine.labels['move_dir']] == machine.ram[machine.labels['walk_time']] == 0
        reference.tick(pad)
        target_tick(machine, pad)
        trajectory.append(compare(reference, machine, ('three digs then standing climb', tick)))
    r, a, L = reference.ram, machine.ram, machine.labels
    assert r[0x400+27] == r[0x500+27] == 255
    assert r[0x5A] == 2 and r[0x6A] == 3 and (r[0x64], r[0x66]) == (45, 144)
    assert a[L['curfloor']] == 1 and a[L['onground']]
    return dict(ticks=len(sequence), prior_runup_ticks=0, manual_map_changes=False,
                climbed_height=48, trajectory=trajectory)


def check_bonus_starts():
    cases, ticks = [], 0
    for direction in (1, 2):
        for name, sequence in {
            'stationary':[128|direction]+[direction]*39,
            'running':[direction]*24+[128|direction]+[direction]*39,
            'new_stop_A':[direction]*8+[128]+[0]*39,
            'old_stop_A':[direction]*8+[0]+[128|direction]+[direction]*39,
            'release_two_A':[direction]*8+[0]*2+[128|direction]+[direction]*39,
            'late_air_direction':[128]+[0]*25+[direction]*19,
            'outside_contact_skip':[direction]*8,
            'taper_rebound':[direction]*24+[128|direction]+[direction]*55,
        }.items():
            reference, machine = PlayerReference(), start()
            machine.call('enter_bonus')
            r, a, L = reference.ram, machine.ram, machine.labels
            r[0x6E0:0x6FE] = bytes([128])*30
            r[0x6E0], r[0x668], r[0x686], r[0x6A4], r[0x6C2] = 0, 40, 208, 220, 223
            r[0x55], r[0x5A], r[0x64], r[0x66], r[0x6A] = 2, 9, 120, 195, 1
            a[L['bonus_platform_count']], a[L['bonus_cloud_count']] = 1, 0
            a[L['BONUS_LEDGE_L']], a[L['BONUS_LEDGE_R']] = 9, 30
            a[L['BONUS_LEDGE_HLO']], a[L['BONUS_LEDGE_HHI']] = 252, 0
            a[L['bonus_camera']:L['bonus_camera']+2] = (256).to_bytes(2,'little')
            a[L['py']], a[L['onground']] = 220, 1
            a[L['pxlo']:L['pxhi']+1] = (172).to_bytes(2,'little')
            if name == 'outside_contact_skip':
                r[0x64] = 0 if direction == 1 else 255
                a[L['pxlo']:L['pxhi']+1] = (r[0x64]+52).to_bytes(2,'little')
            if name == 'taper_rebound':
                r[0x64] = 144 if direction == 1 else 96
                a[L['pxlo']:L['pxhi']+1] = (r[0x64]+52).to_bytes(2,'little')
            for tick, pad in enumerate(sequence,1):
                reference.pad = pad
                reference.call(0xCAED)
                reference.call(0xCB9D)
                r[0x70] = r[0x15]
                reference.call(0xD552)
                reference.call(0xD59C)
                target_tick(machine,pad,True)
                compare(reference,machine,('bonus',direction,name,tick),25)
                ticks += 1
            cases.append(dict(direction=direction,start=name,ticks=len(sequence)))
    return cases,ticks


def check_bonus_bounds():
    from test_original_physics import Reference
    reference, machine = Reference(), start()
    r, a, L = reference.ram, machine.ram, machine.labels
    cases = 0
    dense = {0,1,55,56,86,87,88,142,143,144,198,199,200,230,231,255,256,
             286,287,303,304,341,342,343,344,398,399,400,446,447}
    for world in range(448):
        if world >= 256:
            camera, py = 0, world-231
        elif world <= 230:
            camera, py = 256, world+25
        else:
            camera, py = 100, world-131
        xs = range(256) if world in dense else (0,42,43,63,64,71,72,120,168,175,176,197,198,255)
        for grounded in (False,True):
            for x in xs:
                r[0x28], r[0x2A], r[0x13], r[0x64], r[0x62] = world&255, world>>8, (-camera)&255, x, 1
                r[0x6A], r[0xE6], r[0x352] = 1 if grounded else 2, 5, 0
                reference.call(0xD648)
                a[L['py']], a[L['onground']], a[L['face']], a[L['fall_int']] = py, int(grounded), 0, 5
                a[L['bonus_camera']:L['bonus_camera']+2] = camera.to_bytes(2,'little')
                a[L['pxlo']:L['pxhi']+1] = (x+52).to_bytes(2,'little')
                machine.call('bonus_side_bounds')
                actual = (int.from_bytes(a[L['pxlo']:L['pxhi']+1],'little')-52,
                          bool(a[L['onground']]),a[L['face']],a[L['fall_int']],a[L['BONUS_WALL_SKIP']])
                expected = (r[0x64],r[0x6A] in (1,3),1-r[0x62],r[0xE6],r[0x352])
                assert actual == expected,('bonus side walls',world,camera,x,grounded,actual,expected)
                cases += 1
    return cases


def check_ground_swing_full():
    """Actual CDB0/CFC6 entry, CB9D timers and every D05D attack frame."""
    frames = {entry['pointer']+layer:entry
              for entry in json.loads((BASE/'c64/build/sprite_frames.json').read_text())
              for layer in range(entry['layers'])}
    cases, ticks, ignored = 0, 0, 0
    for floor in (0,5):
        for run in (0,1,8,24):
            for direction in ((0,) if not run else (1,2)):
                for stopping in ((False,True) if run else (False,)):
                    reference,machine = flat_fixture(floor)
                    r,a,L = reference.ram,machine.ram,machine.labels
                    prelude = [direction]*run+([0] if stopping else [])
                    for pad in prelude:
                        reference.tick(pad)
                        target_tick(machine,pad)
                    if not stopping:
                        r[0x32] = a[L['skid_t']] = 7
                    reference.tick(64|direction)
                    target_tick(machine,64|direction)
                    compare(reference,machine,('ground B entry',floor,run,direction,stopping))
                    ticks += 1
                    if r[0x6A] != 5:
                        assert not a[L['GROUND_SWING']]
                        ignored += 1
                        continue
                    assert a[L['GROUND_SWING']] == 2
                    active = 0
                    while True:
                        a[L['logical_count']],a[L['actor_mask']] = 0,255
                        machine.call('actor_player')
                        actual = frames[a[L['LOG_PTR']]]['nes_base']
                        expected = min(r[0x201+4*i] for i in range(6))
                        assert actual == expected,('full ground B pose',floor,run,direction,stopping,active,actual,expected)
                        if r[0x6A] != 5:
                            assert a[L['attack_t']] == 1
                            break
                        assert a[L['attack_t']] == 21-r[0x60]
                        pad = (128|(3-direction if direction else 1),3-direction if direction else 1,64,0)[active%4]
                        reference.tick(pad)
                        target_tick(machine,pad)
                        active += 1
                        ticks += 1
                        compare(reference,machine,('ground B active',floor,run,direction,stopping,active))
                        assert active <= 20
                    reference.tick(0)
                    target_tick(machine,0)
                    compare(reference,machine,('ground B release',floor,run,direction,stopping))
                    assert not a[L['GROUND_SWING']]
                    ticks += 1
                    cases += 1
    machine = start()
    machine.frame(0xEE)
    assert not machine.ram[machine.labels['onground']]
    assert not machine.ram[machine.labels['GROUND_SWING']]
    return dict(cases=cases,ignored_lower_or_finished_stops=ignored,executed_nes_ticks=ticks,
                source_handlers=['CAED','CB9D','CDB0','CFC6','D05D'],
                actual_entry_pose=True,walking_counter_handoff=True,timer_runs_while_frozen=True)


def main():
    starts, ticks = check_starts()
    print(f'PASS {len(starts)} full normal input/stop/air cases ({ticks} ticks)',flush=True)
    walkoffs, walkoff_ticks = check_walkoffs()
    digging, dig_ticks = check_digging()
    climb = check_dig_then_standing_climb()
    print('PASS walkoffs, exact per-tick dig maps, and actual-map standing48px climb',flush=True)
    bonus, bonus_ticks = check_bonus_starts()
    print(f'PASS {len(bonus)} full bonus input/stop/air cases',flush=True)
    bonus_bounds = check_bonus_bounds()
    print(f'PASS {bonus_bounds} executed-source bonus side-wall cases',flush=True)
    report = dict(status='passed', start_cases=starts, digging=digging,
                  dig_then_standing_climb=climb, bonus_starts=bonus,
                  walkoff_cases=walkoffs,
                  bonus_wall_cases=bonus_bounds,
                  full_handler_ticks=ticks+dig_ticks+climb['ticks']+bonus_ticks+walkoff_ticks,
                  source_entrypoints=['CAED', 'CB9D', 'CD13', 'DA99', 'D1E5', 'D552', 'D59C', 'D648'],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/original_player_input.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'PASS {len(starts)} normal and {len(bonus)} bonus input/stop/air cases, {len(digging)} dig/rejump cases and actual-map dig then48px standing climb')


if __name__ == '__main__':
    main()
