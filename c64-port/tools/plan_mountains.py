#!/usr/bin/env python3
"""Find/replay joystick-only climbs through the 32 original normal stages.

Planning omits video and SID work, executes the assembled game logic with
real read_joy edge detection, and leaves every game-state byte to the PRG.
Selected routes are replayed through the complete main loop before saving.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from test_game import BASE, Machine, bcd, finish_opening
from emulate_prg import CPU
import native_planning


class PlanningMachine(Machine):
    """Omit display-cache subroutines while retaining all world/game logic."""
    def __init__(self):
        self.planning = False
        self.use_native = True
        super().__init__()
        self.render_entries = {self.labels[name] for name in
                               ('cloud_step', 'cloud_make_glyphs', 'cloud_make_glyphs2',
                                'cache_cell', 'bonus_cloud_paint', 'bonus_cloud_phase')}

    def step(self):
        if self.planning and self.pc in self.render_entries:
            self.pc = (self.pop() | self.pop() << 8)+1
        else:
            super().step()

    def run_to(self, target):
        if self.use_native and native_planning.library is not None:
            native_planning.run_to(self, target, self.render_entries if self.planning else ())
        else:
            super().run_to(target)

    def write(self, address, value):
        if self.planning and (address < 0x0800 or address >= 0xD000):
            if 0xD000 <= address < 0xE000 and self.io_hidden():
                self.under_io[address-0xD000] = value & 0xFF   # $01 = $34: RAM under I/O
                return
            CPU.write(self, address, value)
        else:
            super().write(address, value)


def clone(machine):
    other = copy.copy(machine)
    other.ram = machine.ram.copy()
    other.under_io = machine.under_io.copy()
    other.sid_events = []
    other.hooks = {0xDC00: other.port_a, 0xDC01: other.port_b,
                   0xD012: other.raster_read}
    return other


def fast_frame(machine, joystick):
    r, labels = machine.ram, machine.labels
    machine.joystick = joystick
    r[0x14] = (r[0x14]+1) & 255
    machine.call('read_joy')
    before = r[0x18]
    pan_before = r[labels['normal_pan_t']]
    r[labels['pan_step_frame']] = pan_before
    machine.call('play_tick')
    r[0x5D] += 1
    if r[0x5D] == 5:
        r[0x5D] = 0
        r[labels['firehit']] = 0
        r[labels['tick_debt']] = 0
        # Match the main loop at pan entry, during movement, and on the
        # final step. The reduced planner still runs six ticks per five
        # frames outside the normal pan.
        pan = before == 1 and (pan_before or r[labels['normal_pan_t']])
        if r[0x18] == before and not pan:
            machine.call('play_tick')


def start(mountain, planning=False):
    machine = PlanningMachine() if planning else Machine()
    machine.ram[machine.labels['selected_mountain']] = mountain
    machine.frame(0xEF)
    finish_opening(machine)
    if planning:
        machine.planning = True
    return machine


def x_position(r):
    return r[0x1E] + 256*r[0x1F]


def landing_holds(machine, floor, frames=30):
    """A landing above floor counts only if the climber still stands there
    after waiting: an edge landing on a cloud or ledge can slip off at once."""
    probe = clone(machine)
    r = probe.ram
    lives = r[0x19]
    for _ in range(frames):
        fast_frame(probe, 255)
        if r[0x18] == 3:
            return True
        if r[0x18] != 1 or r[0x19] != lives:
            return False
    if not (r[0x1B] and r[0x1A] > floor):
        return False
    # --cloud-footing: on a cloud floor the solid side ledge is a dead end
    # when the clouds pass without carrying the climber; demand a cloud
    # under the feet (supflag 2: the last support probe found a cloud).
    if getattr(machine, 'cloud_footing', False) and r[0x600+r[0x1A]] & 0xE0 >= 0x80:
        return r[0x30] == 2
    return True


def cloud_jump_plan(machine, dense=False, unsettled=False):
    """Choose a jump that catches a real cloud instead of guessing its phase."""
    base_floor = machine.ram[0x1A]
    base_height = 216 + 48*machine.ram[0x3A] - machine.ram[0x22]
    original_map = machine.ram[0x244]  # actual player brick count; Topi repairs are not progress
    original_upper = bytes(machine.ram[0x400:0x500])
    dense = dense or getattr(machine, 'fine_runs', False)
    unsettled = unsettled or getattr(machine, 'unsettled_first', False)
    kind = machine.ram[0x600+base_floor]
    next_kind = machine.ram[0x601+base_floor] if base_floor < 8 else 0
    waits = range(0, 257, 4) if kind & 0xE0 >= 0x60 or next_kind & 0xE0 >= 0x60 else (0, 8, 16, 32, 64, 96, 128, 192, 256)
    options = ((255, 0), (0xF7, 0), (0xFB, 0), (0xF7, 12), (0xFB, 12))
    options += ((0xF7, 24), (0xFB, 24), (0xF7, 36), (0xFB, 36))
    if dense:
        options = [(direction, run) for run in range(49) for direction in (0xF7, 0xFB)]
        if kind & 0xE0 < 0x60 and next_kind & 0xE0 < 0x60:
            waits = (0,)
    if base_floor == 7:
        options = [(direction, run) for run in range(97 if unsettled else 49)
                   for direction in (0xF7, 0xFB)]
    wait_directions = (255, 0xF7 if kind & 0x10 else 0xFB) if kind & 0xE0 in (0x20, 0x40, 0x60) else (255,)
    best, best_key = None, None
    for wait, wait_joy in ((count, joy) for count in waits for joy in wait_directions):
        # All launches from this phase share the same waiting frames. Keep
        # the resulting machine, including real cloud/enemy motion, intact.
        waiting = clone(machine)
        waiting_inputs = []
        valid = True
        for _ in range(wait):
            fast_frame(waiting, wait_joy)
            waiting_inputs.append(wait_joy)
            if waiting.ram[0x18] != 1 or waiting.ram[0x19] != machine.ram[0x19] or not waiting.ram[0x1B]:
                valid = False
                break
        if not valid:
            continue
        # Roof searches try run0, run1, ... in both directions. Advance each
        # direction's prefix only once, and clone BEFORE jump settling so
        # the next launch cannot inherit the previous launch's input/state.
        prefixes = {}
        for direction, run in options:
            if direction not in prefixes:
                prefixes[direction] = [clone(waiting), 0, True]
            prefix = prefixes[direction]
            if run < prefix[1]:  # keep alternate option orderings exact too
                prefix = prefixes[direction] = [clone(waiting), 0, True]
            while prefix[1] < run and prefix[2]:
                fast_frame(prefix[0], direction)
                prefix[1] += 1
                prefix[2] = (prefix[0].ram[0x18] == 1 and prefix[0].ram[0x19] == machine.ram[0x19] and bool(prefix[0].ram[0x1B]))
            if not prefix[2]:
                continue
            candidate = clone(prefix[0])
            r = candidate.ram
            inputs = waiting_inputs + [direction]*run
            valid = True
            desired = 0 if direction == 255 else 1 if direction == 0xF7 else 2
            for _ in range(0 if unsettled else 24):
                if not r[0x5C] and r[0x58] == desired:
                    break
                fast_frame(candidate, direction)
                inputs.append(direction)
                if not r[0x1B]:
                    valid = False
                    break
            if not valid:
                continue
            airborne = False
            for frame in range(90):
                joy = direction & 0xFE if frame == 0 else direction
                fast_frame(candidate, joy)
                inputs.append(joy)
                if r[0x18] == 3:
                    return candidate, inputs
                if r[0x18] != 1 or r[0x19] != machine.ram[0x19]:
                    break
                if not r[0x1B]:
                    airborne = True
                if airborne and r[0x1B]:
                    height = 216 + 48*r[0x3A] - r[0x22]
                    if r[0x1A] > base_floor:
                        if landing_holds(candidate, base_floor):
                            return candidate, inputs
                        break
                    if ((r[0x1A] == base_floor and height > base_height)
                            or r[0x244] != original_map):
                        key = (height, (r[0x244]-original_map) & 255, -len(inputs))
                        if dense:
                            upper_breaks = sum(old == 1 and new == 0 for old, new in
                                               zip(original_upper, r[0x400:0x500]))
                            key = (upper_breaks,) + key
                        if best_key is None or key > best_key:
                            best, best_key = (candidate, inputs), key
                    break
    return best


def greedy(mountain, limit=4000, variant=0, verbose=False, all_floor_macro=False, fine_runs=False,
           unsettled_first=False, cloud_footing=False):
    machine = start(mountain, planning=True)
    machine.fine_runs = fine_runs
    machine.unsettled_first = unsettled_first
    machine.cloud_footing = cloud_footing
    r, labels = machine.ram, machine.labels
    sequence, history = [], []
    direction, last_joy = 0xF7, 255
    clear = False
    floor_since = 0
    floor_last = 0

    def cell(floor, column, layer):
        if not (0 <= column < 24 and floor < 9):
            return 3
        value = r[0x400+layer*256+floor*24+column]
        return 3 if layer == 0 and value == 2 else value

    while len(sequence) < limit:
        frame = len(sequence)
        x = x_position(r)
        floor = r[0x1A]
        if floor != floor_last:
            floor_last, floor_since = floor, frame
            history.append(dict(frame=frame, floor=floor, x=x, lives=r[0x19]))
            if verbose:
                print('FLOOR', mountain, variant, frame, floor, x, r[0x19], flush=True)
        joy = 255
        if frame < (40 if variant & 1 else 65):
            joy = 0xFB if variant & 2 else 0xF7
        elif r[0x1B]:
            target = floor+1
            current_type = r[0x600+floor] & 0xE0
            next_type = r[0x600+target] & 0xE0 if target < 9 else 0
            if all_floor_macro or current_type >= 0x20 or next_type >= 0x60 or target == 8:
                planned = cloud_jump_plan(machine)
                if planned is None:
                    # UP can cancel a skid before the requested direction
                    # becomes the player's latched airborne direction.
                    planned = cloud_jump_plan(machine, dense=True, unsettled=True)
                if planned:
                    machine, inputs = planned
                    r, labels = machine.ram, machine.labels
                    sequence.extend(inputs)
                    last_joy = inputs[-1]
                    if r[0x18] == 3:
                        return machine, sequence, history
                    continue
                for _ in range(12):
                    fast_frame(machine, 255)
                    sequence.append(255)
                    if not r[0x1B] or r[0x18] != 1:
                        break
                last_joy = 255
                continue
            # Source NES collision probes are the two centre feet, not the
            # full sprite width. Coordinates wrap in the 256-pixel world.
            body = (x-52) & 255
            columns = [((body+delta) & 255)//8-4 for delta in (6, 9)]
            stone = any(cell(target, c, layer) == 3 for c in columns for layer in (0, 1))
            goals = [84+c*8 for c in range(23)
                     if all(cell(target, c+d, layer) != 3 for d in (0, 1) for layer in (0, 1))]
            if stone and goals:
                goal = min(goals, key=lambda v: abs(v-x))
                if abs(goal-x) > 3:
                    desired = 1 if goal > x else 2
                    distance = abs(goal-x)
                    braking = r[0x5C] or (r[0x58] == desired and distance <= r[0x59]//2+3)
                    braking |= distance < 10 and r[0x58] != 0
                    joy = 255 if braking else 0xF7 if goal > x else 0xFB
                elif r[0x58] or r[0x5C]:
                    joy = 255
                elif last_joy & 1:
                    direction = 0xFB if (variant & 4) or x > 220 else 0xF7
                    clear = all(cell(target, c, layer) == 0 for c in columns for layer in (0, 1))
                    joy = direction & 0xFE if clear else 0xFE
            elif not r[0x58] and not r[0x5C] and last_joy & 1:
                clear = all(cell(target, c, layer) == 0 for c in columns for layer in (0, 1))
                direction = 0xFB if (variant & 4) or x > 220 else 0xF7
                joy = direction & 0xFE if clear else 0xFE
            # Stuck beneath an edge: deliberately move and establish a new
            # run-up rather than repeatedly making an identical jump.
            if frame-floor_since > 500 and frame % 160 < 45:
                joy = 0xFB if variant & 1 else 0xF7
        else:
            joy = direction if clear else 255
        fast_frame(machine, joy)
        sequence.append(joy)
        last_joy = joy
        if verbose and frame % 200 == 0:
            print(mountain, variant, frame, r[0x1A], x_position(r), r[0x22], r[0x19], flush=True)
        if r[0x18] == 3:
            return machine, sequence, history
        if r[0x18] != 1 or not r[0x19]:
            break
    return None, sequence, history


def replay(mountain, sequence, native=False):
    machine = start(mountain, planning=native)
    if native:
        machine.planning = False  # complete release main loop: no skipped helpers
    # The SWAP segment after code_end trades fruit and death-spin art by scene.
    immutable = {start: bytes(machine.ram[start:end]) for start, end in
                 ((0x0801, machine.labels['code_end']), (0x7000, 0xD000))}
    helpers = machine.labels.get('__HELPERS_RUN__', 0)
    helper_size = machine.labels.get('__HELPERS_SIZE__', 0)
    if helper_size:
        immutable[helpers] = bytes(machine.ram[helpers:helpers+helper_size])
    for joy in sequence:
        machine.frame(joy)
        if machine.ram[0x18] != 1:
            break
    assert machine.ram[0x18] == 3, ('full replay did not reach bonus', mountain)
    for address, data in immutable.items():
        assert machine.ram[address:address+len(data)] == data, ('readonly corruption', mountain, address)
    return machine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mountains', nargs='*', type=int, default=list(range(1, 33)))
    parser.add_argument('--limit', type=int, default=4000)
    parser.add_argument('--variants', type=int, default=8)
    parser.add_argument('--start-variant', type=int, choices=range(8), default=0)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--no-replay', action='store_true')
    parser.add_argument('--python-replay', action='store_true')
    parser.add_argument('--all-floor-macro', action='store_true')
    parser.add_argument('--fine-runs', action='store_true')
    parser.add_argument('--unsettled-first', action='store_true')
    parser.add_argument('--cloud-footing', action='store_true')
    parser.add_argument('--output', default='mountain_routes_search.json')
    args = parser.parse_args()
    routes, failed = [], []
    for mountain in args.mountains:
        variant_order = list(range(args.start_variant, 8)) + list(range(args.start_variant))
        for variant in variant_order[:args.variants]:
            machine, inputs, history = greedy(mountain, args.limit, variant, args.verbose,
                                             args.all_floor_macro, args.fine_runs, args.unsettled_first,
                                             args.cloud_footing)
            if machine:
                if not args.no_replay:
                    machine = replay(mountain, inputs, native=not args.python_replay and native_planning.library is not None)
                r = machine.ram
                routes.append(dict(mountain=mountain, inputs=inputs, lives=r[0x19],
                                   normal_score=bcd(r[0x25:0x27]+r[0x51:0x52]),
                                   score=bcd(r[0x25:0x27]+r[0x51:0x52]), start_idle_frames=1,
                                   frames=len(inputs), history=history,
                                   full_replay=not args.no_replay, variant=variant))
                print('PASS mountain', mountain, 'frames', len(inputs), 'lives', r[0x19], flush=True)
                break
        else:
            failed.append(dict(mountain=mountain, history=history, frames=len(inputs)))
            print('FAIL mountain', mountain, history, flush=True)
        result = dict(status='incomplete' if failed else 'planned' if args.no_replay else 'passed',
                      prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                      routes=routes, failed=failed)
        (BASE/'build_dbg'/args.output).write_text(json.dumps(result)+'\n')
    if not failed and not args.no_replay and {r['mountain'] for r in routes} == set(range(1, 33)):
        (BASE/'tools/fixtures/mountain_routes.json').write_text(json.dumps(result)+'\n')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
