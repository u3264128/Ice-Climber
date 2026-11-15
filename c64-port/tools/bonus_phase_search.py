"""Controller candidates with independent preparation, jump and air steering.

Every candidate executes joystick frames on a cloned release PRG state.
The coarse pass samples every waiting phase before expanding preparation.
"""
from plan_mountains import clone, fast_frame, x_position


def height(machine):
    address = machine.labels['bonus_camera']
    return 216 + int.from_bytes(machine.ram[address:address+2], 'little') - machine.ram[0x22]


def phase_landings(machine, fine=False, max_results=12, allow_same=False):
    """Yield higher grounded landings or a bird catch, using only joystick input."""
    base_height = height(machine)
    base_platform = machine.ram[machine.labels['bonus_plat']]
    seen = set()
    preparations = [(255, 0)]
    if fine:
        preparations += [(direction, count) for count in (5, 3, 8, 1, 12, 16, 14, 18, 20, 24, 32)
                         for direction in (0xFB, 0xF7)]
    r, labels = machine.ram, machine.labels
    cloud_heights = [r[labels['bonus_cloud_hlo']+index] + 256*r[labels['bonus_cloud_hhi']+index]
                     for index in range(r[labels['bonus_cloud_count']])]
    moving_phase_matters = base_height >= 350 or any(base_height <= cloud <= base_height+56
                                                   for cloud in cloud_heights)
    waits = (0, 8, 16, 24, 32, 48, 64, 96, 128, 192, 256, 320, 384, 448, 512) if moving_phase_matters else (0,)
    for wait in waits:
        waiting = clone(machine)
        waiting_inputs = [255]*wait
        valid = True
        for joystick in waiting_inputs:
            fast_frame(waiting, joystick)
            if not on_platform(waiting):
                valid = False
                break
        if not valid:
            continue
        for preparation, run in preparations:
            moving = clone(waiting)
            walking_inputs = [preparation]*run
            for joystick in walking_inputs:
                fast_frame(moving, joystick)
                if not on_platform(moving):
                    valid = False
                    break
            if not valid:
                valid = True
                continue
            for brake in ((2, 0, 4, 6, 8, 12) if fine else (0, 2)):
                ground = clone(moving)
                braking_inputs = [255]*brake
                for joystick in braking_inputs:
                    fast_frame(ground, joystick)
                    if not on_platform(ground):
                        valid = False
                        break
                if not valid:
                    valid = True
                    continue
                for launch in (255, 0xF7, 0xFB):
                    for delay in ((4, 0, 8, 12, 16, 20) if fine else (0, 4, 8)):
                        for air_direction in (0xF7, 0xFB, 255):
                            candidate = clone(ground)
                            inputs = waiting_inputs+walking_inputs+braking_inputs
                            airborne = False
                            for frame in range(90):
                                joystick = launch & 254 if frame == 0 else 255 if frame <= delay else air_direction
                                fast_frame(candidate, joystick)
                                inputs.append(joystick)
                                r, labels = candidate.ram, candidate.labels
                                if r[labels['bonus_winner']]:
                                    yield candidate, inputs
                                    return
                                if r[0x18] != 3 or r[labels['bonus_out']]:
                                    break
                                if not r[0x1B]:
                                    airborne = True
                                if airborne and r[0x1B]:
                                    candidate_height = height(candidate)
                                    if (candidate_height > base_height or
                                            (allow_same and candidate_height == base_height and
                                             r[labels['bonus_plat']] != base_platform)):
                                        key = (candidate_height, x_position(r)//6,
                                               r[labels['bonus_plat']])
                                        if key not in seen:
                                            seen.add(key)
                                            yield candidate, inputs
                                            if len(seen) >= max_results:
                                                return
                                    break


def on_platform(machine):
    r = machine.ram
    return r[0x18] == 3 and not r[machine.labels['bonus_out']] and bool(r[0x1B])
