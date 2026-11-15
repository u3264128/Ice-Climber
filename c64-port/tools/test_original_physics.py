#!/usr/bin/env python3
"""Compare C64 movement with executed instructions from the original NES ROM.

The reference runs the original $C83D/$D143/$D160/$D17C/$DAD5/$CD62 bytes.
Control fixtures additionally use real joystick edges to prove UP can hit a
seal, holding UP cannot jump repeatedly, and both mountain edges connect.
"""
import hashlib
import json
import random
from pathlib import Path

from emulate_prg import CPU
from test_game import start

BASE = Path(__file__).resolve().parents[1]
PRG = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()


class Reference(CPU):
    def __init__(self):
        ram = bytearray(65536)
        ram[0xC000:] = PRG
        super().__init__(ram, {})
        self.calls = 0

    def step(self):
        # STY zp,X is used by the original collision lookup. The general
        # C64 test interpreter does not otherwise need this instruction.
        if self.ram[self.pc] == 0x94:
            address = (self.ram[self.pc+1] + self.x) & 255
            self.write(address, self.y)
            self.pc += 2
            return
        super().step()

    def call(self, address, a=0, y=0):
        self.a, self.x, self.y = a, 0, y
        self.push(0xBF)
        self.push(0xFF)
        self.pc = address
        for _ in range(20000):
            if self.pc == 0xC000:
                self.calls += 1
                return self.a
            self.step()
        raise AssertionError(('NES routine did not return', hex(address), hex(self.pc)))


def check_horizontal():
    machine = start()
    ram, labels = machine.ram, machine.labels
    reference = Reference()
    ref = reference.ram
    cases = 0
    for direction in (1, 2):
        for grounded, run_time in ((True, 0), (False, 0), (False, 11),
                                   (False, 12), (False, 24)):
            ram[labels['onground']] = int(grounded)
            ram[labels['move_dir']] = direction
            ram[labels['face']] = direction-1
            ram[labels['walk_time']] = ref[0x6E] = run_time
            ram[labels['walk_frac']] = ref[0x76] = 0
            ram[labels['air_xfrac']] = ref[0x72] = 0
            ram[labels['skid_t']] = 0
            ram[labels['fall_int']] = 0
            ram[labels['joy']] = 0xF7 if direction == 1 else 0xFB
            ref[0x6A] = 1 if grounded else 4
            ref[0x62] = 1 if direction == 1 else 0
            ref[0x64] = 248 if direction == 1 else 4
            x = ref[0x64]+52
            ram[labels['pxlo']:labels['pxhi']+1] = x.to_bytes(2, 'little')
            for tick in range(320):
                reference.call(0xD143 if grounded else 0xD160)
                machine.call('move_horizontal')
                actual = int.from_bytes(ram[labels['pxlo']:labels['pxhi']+1], 'little')
                assert actual == 52+ref[0x64], (direction, grounded, run_time, tick, actual, ref[0x64])
                assert ram[labels['walk_time']] == ref[0x6E]
                assert ram[labels['walk_frac']] == ref[0x76]
                assert ram[labels['air_xfrac']] == ref[0x72]
                cases += 1
    return cases


def check_vertical():
    machine = start()
    ram, labels = machine.ram, machine.labels
    cases = 0
    for falling in (False, True):
        reference = Reference()
        ref = reference.ram
        ram[labels['py']] = ref[1] = 180
        ram[labels['rise_int']], ram[labels['rise_frac']] = 3, 0xA8
        ref[0xE4], ref[0xE2] = 3, 0xA8
        ram[labels['air_init']] = ref[0xE0] = int(falling)
        ram[labels['fall_int']] = ref[0xE6] = 4 if falling else 0
        ram[labels['fall_frac']] = ref[0xE8] = 5 if falling else 0
        ram[labels['y_frac']] = ref[0xEA] = 0
        for tick in range(120):
            reference.call(0xC83D)
            ram[labels['prevpy']] = ram[labels['py']]
            machine.call('vertical_step')
            assert ram[labels['py']] == ref[1], (falling, tick)
            assert [ram[labels[name]] for name in ('fall_int', 'fall_frac', 'y_frac')] == \
                   [ref[0xE6], ref[0xE8], ref[0xEA]]
            cases += 1
    return cases


def check_walk_off():
    machine = start()
    ram, labels = machine.ram, machine.labels
    for direction in (0, 1, 2):
        reference = Reference()
        ref = reference.ram
        ref[0x400:0x4D8] = bytes([255])*216
        ref[0x64], ref[0x5A], ref[0x68], ref[0x6E], ref[0xEA] = 100, 1, direction, 24, 0x55
        reference.call(0xCD3B)  # original hole check and walk-off transition
        ram[labels['pxlo']], ram[labels['pxhi']] = 152, 0
        ram[labels['move_dir']], ram[labels['walk_time']], ram[labels['y_frac']] = direction, 24, 0x55
        machine.call('begin_fall')
        assert int.from_bytes(ram[labels['pxlo']:labels['pxhi']+1], 'little') == ref[0x64]+52
        assert ram[labels['walk_time']] == ref[0x6E] == 5
        assert ram[labels['y_frac']] == ref[0xEA] == 0x55
        assert bool(ram[labels['air_init']]) == bool(ref[0xE0])
        assert ram[labels['air_init']] == 0x8C  # source86 inhibit + render age12
        assert ram[labels['fall_int']] == ref[0xE6] == 4
        assert ram[labels['fall_frac']] == ref[0xE8] == 5
    return 3


def check_helmet_probes():
    machine = start()
    ram, labels = machine.ram, machine.labels
    reference = Reference()
    ref = reference.ram
    cases = 0
    for nes_x in range(48, 193):
        x = nes_x+52
        ram[labels['pxlo']:labels['pxhi']+1] = x.to_bytes(2, 'little')
        machine.call('compute_pcols')
        actual = {ram[labels['pleft']], ram[labels['pright']]}
        for facing in (0, 1):
            ref[0x64], ref[0x66], ref[0x62], ref[0x5A] = nes_x, 180, facing, 1
            reference.call(0xD17C, y=7)  # raised mallet, original OAM placement
            columns = set()
            for offset in (4, PRG[0x1A97+facing]):
                ref[0] = offset
                result = reference.call(0xDAD5)
                assert reference.c, ('probe outside source mountain', nes_x, facing)
                columns.add(4+result//8)
            assert actual == columns, (nes_x, facing, actual, columns)
            assert len(actual) == 2, ('hammer removed more than two blocks', nes_x)
            cases += 1
    return cases


def check_posts_and_feet():
    machine = start()
    ram, labels = machine.ram, machine.labels
    reference = Reference()
    ref = reference.ram
    # Both feet land within the original raw4 post at source column13.
    # The source explicitly rejects it if both neighbouring cells are air.
    ref[0x64], ref[0x5A], ref[0x82] = 100, 1, 0
    ref[0x400:0x4D8] = bytes([255])*216
    ref[0x409] = 4
    ram[labels['floor_upper']:labels['floor_upper']+24] = bytes(24)
    ram[labels['floor_lower']:labels['floor_lower']+24] = bytes(24)
    ram[labels['floor_upper']+9] = 2  # packed source raw4 tag
    ram[labels['floor_lower']+9] = 3  # original writes its post into both planes
    ram[labels['pxlo']], ram[labels['pxhi']] = 152, 0
    ram[labels['cam']] = 0
    for neighbour in (0, 1):
        ref[0x408] = 255 if neighbour == 0 else 1
        ram[labels['floor_upper']+8] = neighbour
        reference.call(0xCD62)
        expected = reference.c
        machine.call('support_at', 0)
        assert ram[labels['supflag']] == expected, ('isolated post', neighbour)
    # Foot coordinates come from the two ADC immediates in $CD62/$CD83,
    # checked over the entire world including wrapped edge positions.
    offsets = (PRG[0x0D67], PRG[0x0D84])
    assert offsets == (6, 9)
    for nes_x in range(256):
        x = nes_x+52
        ram[labels['pxlo']:labels['pxhi']+1] = x.to_bytes(2, 'little')
        machine.call('compute_feet_columns')
        actual = (ram[labels['pleft']], ram[labels['pright']])
        expected = tuple(4+(nes_x+offset)//8 for offset in offsets)
        assert actual == expected, ('feet', nes_x, actual, expected)
    return 258


def check_integrated_support():
    """Run the complete support_at call, including flags returned by helpers.

The source compares raw4 neighbours in its upper plane. Lower planes vary
independently so underside ice cannot hide an erroneous upper-air result.
Side columns remain the implicit rock specified by $DBB4 floor bounds.
"""
    machine = start()
    ram, labels = machine.ram, machine.labels
    reference = Reference()
    ref = reference.ram
    ref[0x5A] = 1
    ram[labels['cam']] = 0
    ram[labels['floor_types']:labels['floor_types']+9] = bytes(9)
    rng = random.Random(0xCD62)
    fixtures = [bytes([value])*24 for value in (255, 1, 0, 3)]
    isolated = bytearray([255])*24
    isolated[9] = 4
    fixtures.append(bytes(isolated))
    connected = isolated[:]
    connected[8] = 1
    fixtures.append(bytes(connected))
    for _ in range(24):
        row = bytearray(rng.choice((255, 255, 255, 1, 0, 3, 4)) for _ in range(24))
        row[0] = row[-1] = 3  # source generator fixes the boundary to rock
        fixtures.append(bytes(row))
    cases = 0
    for fixture, source in enumerate(fixtures):
        lower = bytes(rng.choice((255, 1, 2, 3)) for _ in range(216))
        ref[0x500:0x5D8] = lower
        ram[labels['floor_lower']:labels['floor_lower']+216] = bytes(
            0 if value == 255 else value for value in lower)
        ref[0x400:0x418] = source
        ram[labels['floor_upper']:labels['floor_upper']+24] = bytes(
            0 if value == 255 else 1 if value == 1 else 2 if value == 4 else 3
            for value in source)
        for nes_x in range(256):
            ref[0x64] = nes_x
            reference.call(0xCD62)
            expected = bool(reference.c)
            x = nes_x+52
            ram[labels['pxlo']:labels['pxhi']+1] = x.to_bytes(2, 'little')
            machine.call('support_at', 0)
            actual = bool(ram[labels['supflag']])
            assert actual == expected, ('integrated support', fixture, nes_x, actual, expected, source.hex())
            assert ram[labels['support_offset']] == 0, ('invented lower standing surface', fixture, nes_x)
            cases += 1
    return cases


def check_block_breaks():
    machine = start()
    ram, labels = machine.ram, machine.labels
    cases = 0
    for fraction in range(8):
        for face in (0, 1):
            for layer in (0, 1):
                reference = Reference()
                ref = reference.ram
                ref[0x400:0x4D8] = ref[0x500:0x5D8] = bytes([1])*216
                ref[0x200:0x300] = bytes([0xF8])*256
                ref[0x64], ref[0x66], ref[0x62] = 96+fraction, 180, 1-face
                ref[0x5A], ref[0x82], ref[0x90] = 1, 1, 4
                reference.call(0xD17C, y=7)
                ref[0] = 4  # the first hammer-centre probe in $DA99/$DDC9
                before = bytes(ref[0x400:0x600])
                reference.call(0xDAB2 if layer == 0 else 0xDDE1)
                expected = [i for i, (old, new) in enumerate(zip(before, ref[0x400:0x600])) if old != new]
                assert len(expected) == 1, ('original must remove one brick', fraction, face, layer, expected)
                machine.call('setup_level')
                ram[labels['floor_upper']:labels['floor_upper']+216] = bytes([1])*216
                ram[labels['floor_lower']:labels['floor_lower']+216] = bytes([1])*216 if layer else bytes(216)
                x = 148+fraction
                ram[labels['pxlo']:labels['pxhi']+1] = x.to_bytes(2, 'little')
                ram[labels['face']], ram[labels['cam']] = face, 0
                ram[labels['rowidx']] = 1
                machine.call('compute_pcols')
                before = bytes(ram[0x400:0x600])
                # Test the actual brick mutation kernel. Complete input/head
                # timing and the upper/lower bounce are checked separately by
                # test_original_player_input against the full NES handler.
                machine.call('normal_break_head')
                actual = [i for i, (old, new) in enumerate(zip(before, ram[0x400:0x600])) if old != new]
                assert actual == expected, ('block break', fraction, face, layer, actual, expected)
                cases += 1
    return cases


def place_seal(machine, offset):
    """An original walking seal (object 2) on the climber's floor."""
    from transplant_objects import map_ram
    ram, labels = machine.ram, machine.labels
    nes_x = (ram[labels['pxlo']]-52+offset) & 255
    for nes, value in ((0x93, 0xFF), (0x9E, nes_x), (0xA9, 0xC8), (0xB4, ram[labels['curfloor']]+1),
                       (0xBF, 0xFF), (0x03EA, 5), (0x03A8, 0x40), (0x03DF, 0xA0)):
        ram[map_ram(nes)] = value
    return map_ram(0x93)


def check_controls():
    machine = start()
    ram, labels = machine.ram, machine.labels
    seal = place_seal(machine, 20)
    ram[labels['invul_t']] = 120
    ram[labels['logic_phase']] = 0  # this assertion observes one source tick
    machine.frame(0xFE)           # UP alone: real input edge, jump and hammer
    assert not ram[labels['onground']] and ram[labels['attack_t']] == 20
    # Original $D3D9: a jumping hammer hits only Nitpicker and icicles.
    assert ram[seal] == 0xFF and ram[labels['lives']] == 3
    assert ram[labels['invul_t']], 'Fixture must retain respawn immunity'
    for _ in range(60):
        machine.frame(0xFE)
    assert ram[labels['attack_t']] == 0, 'Held UP must not restart the hammer'
    # FIRE has original ground attack timing and no physical jump.
    machine = start()
    ram, labels = machine.ram, machine.labels
    y = ram[labels['py']]
    ram[labels['logic_phase']] = 0
    machine.frame(0xEF)
    assert ram[labels['onground']] and ram[labels['py']] == y
    assert ram[labels['attack_t']] == 21
    # Original $D3DF: the ground swing hits a seal at pose 9.
    machine = start()
    ram, labels = machine.ram, machine.labels
    seal = place_seal(machine, 16)
    ram[labels['invul_t']] = 120
    machine.frame(0xEF)
    for _ in range(24):
        if ram[seal] != 0xFF:
            break
        machine.frame(0xFF)
    assert ram[seal] == 1 and ram[labels['lives']] == 3, ('ground swing must stun the seal', ram[seal])
    assert ram[labels['attack_t']] == 0, 'Original $D07C ends the attack on a hit'
    # Original $D05D exits the attack on its20th logic tick.
    reference = Reference()
    ref = reference.ram
    ref[0x6A], ref[0x66], ref[0x64] = 5, 180, 100
    for tick in range(1, 21):
        reference.call(0xD05D)
        assert (ref[0x6A] == 5) == (tick < 20)
    # UP remains navigation in the title menu.
    from test_game import Machine
    menu = Machine()
    menu.frame(0xFE)
    assert menu.ram[labels['state']] == 0
    # B is disabled in the original bonus stage ($CDB0 checks state1).
    reference = Reference()
    ref = reference.ram
    ref[0x55], ref[0x6A], ref[0x64], ref[0x66] = 2, 1, 100, 180
    ref[0x14], ref[0x70] = 0x40, 0x40
    reference.call(0xCDB0)
    assert ref[0x6A] == 1
    machine = start()
    machine.call('enter_bonus')
    machine.frame(0xEF)
    assert machine.ram[labels['attack_t']] == 0
    machine.frame(0xFE)
    assert not machine.ram[labels['onground']] and machine.ram[labels['attack_t']] == 0
    return dict(up_jump_and_hammer=True, jump_hammer_passes_seal=True, ground_swing_stuns_seal=True,
                invulnerability_does_not_block_hammer=True, held_up_does_not_repeat=True,
                fire_ground_swing=True, original_attack_ticks=20, title_up_navigation=True,
                bonus_fire_disabled=True)


def check_ground_swing():
    from test_original_player_input import check_ground_swing_full
    return check_ground_swing_full()


def check_clouds():
    """Original initial OAM/intervals, movement and directional catches."""
    machine = start()
    ram, labels = machine.ram, machine.labels
    movement, contacts = 0, 0
    descriptors = (0x60, 0x70, 0xA1, 0xB1, 0xC3, 0xD3, 0xE6, 0xF6)
    for descriptor in descriptors:
        reference = Reference()
        ref = reference.ram
        ref[0x0C], ref[0x19], ref[0x90] = descriptor, 0xD2, 3
        reference.call(0xE662, a=descriptor & 0xE0, y=2)
        ref[0x400:0x4D8] = bytes([255])*216
        machine.call('setup_level')
        ram[labels['floor_types']:labels['floor_types']+9] = bytes(9)
        ram[labels['floor_types']+1] = descriptor
        machine.call('normal_cloud_init')
        for tick in range(256):
            # Each original cloud has its own interval and phase. C64
            # slotsF/F+8 are decoded back into full NES pixel coordinates.
            for slot, source_address in ((1, 0x788), (9, 0x78C)):
                position = ((ram[labels['cloud_x']+slot]-4)*8+
                            ram[labels['cloud_subpixel']+slot]) & 255
                assert position == ref[source_address], ('cloud position', hex(descriptor), tick, slot, position, ref[source_address])
                assert ram[labels['cloud_frac']+slot] == ref[0x7C7]
                assert bool(ram[labels['cloud_dir']+slot]) == bool(ref[0x7D7])
            movement += 1
            machine.call('cloud_update')  # C64 advances the rendered world first
            if tick in (0, 1, 7, 17, 79, 255):
                for handler in (1, 2, 3, 4, 6, 8):
                    grounded = handler in (1, 3)
                    for direction in (0, 1, 2):
                        ref[0x5A], ref[0x82], ref[0x6A], ref[0x68] = 2, 0, handler, direction
                        ram[labels['wrld']], ram[labels['onground']], ram[labels['move_dir']] = 1, int(grounded), direction
                        ram[labels['rise_int']] = 0 if handler in (6, 8) else 3
                        for nes_x in range(64, 208, 7):
                            ref[0x64] = nes_x
                            reference.call(0xDBB4, a=(nes_x+6) & 255)
                            expected = ref[0x783] < 128
                            x = nes_x+52
                            ram[labels['pxlo']:labels['pxhi']+1] = x.to_bytes(2, 'little')
                            machine.call('normal_cloud_contact')
                            assert bool(machine.c) == expected, ('cloud contact', hex(descriptor), tick, handler, direction, nes_x, machine.c, expected)
                            contacts += 1
            ref[0x6A] = ref[0x6B] = 0  # do not transport fixture players
            reference.call(0xE29A)
    return dict(movement_ticks=movement, contact_cases=contacts,
                source_initialization='$E662', source_motion='$E29A', source_contact='$DBB4')


def check_surface_flow():
    """Original phase accumulator and signed conveyor displacement."""
    machine = start()
    ram, labels = machine.ram, machine.labels
    cases = 0
    for family in (0x20, 0x40, 0x60):
        for direction_bit in (0, 0x10):
            for speed in range(8):
                descriptor = family | direction_bit | speed
                reference = Reference()
                ref = reference.ram
                index = speed
                if family == 0x60:
                    index = speed-2 if speed >= 2 else 6
                ref[0x790], ref[0x7A0] = PRG[0x24A2+index*2:0x24A4+index*2]
                ref[0x7D0] = direction_bit
                ref[0x64] = 100
                ram[labels['pxlo']], ram[labels['pxhi']] = 152, 0
                ram[labels['curfloor']], ram[labels['cam']], ram[labels['onground']] = 1, 0, 1
                ram[labels['flow_frac']] = 0
                ram[labels['floor_types']:labels['floor_types']+9] = bytes(9)
                ram[labels['floor_types']+1] = descriptor
                ram[labels['floor_upper']:labels['floor_upper']+216] = bytes([1])*216
                for tick in range(64):
                    reference.x = 0
                    reference.call(0xE303)
                    reference.call(0xE2FB, a=ref[0x7B0], y=0)
                    machine.call('support_at', 1)
                    machine.call('surface_motion')
                    actual = int.from_bytes(ram[labels['pxlo']:labels['pxhi']+1], 'little')
                    assert actual == ref[0x64]+52, ('surface flow', hex(descriptor), tick, actual, ref[0x64])
                    assert ram[labels['flow_frac']] == ref[0x7C0]
                    cases += 1
    # $80 is a cloud family; it has no floor-conveyor entry in $E4C2 and
    # must not introduce a separate wind acceleration in the air.
    for grounded in (True, False):
        ram[labels['onground']] = int(grounded)
        ram[labels['curfloor']] = 1
        ram[labels['floor_types']+1] = 0x80
        ram[labels['pxlo']], ram[labels['pxhi']] = 152, 0
        for _ in range(64):
            machine.call('support_at', 1)
            machine.call('surface_motion')
        assert int.from_bytes(ram[labels['pxlo']:labels['pxhi']+1], 'little') == 152
    return cases


def check_bear_spawn_clock():
    """Run the real NMI timer bank and bear borrow until actual spawn."""
    from plan_mountains import start as planning_start
    # This runs environment_tick from the assembled PRG. The optional
    # planning accelerator has independent full-RAM/register parity proof;
    # without its DLL the same test uses the regular Python interpreter.
    from transplant_objects import map_ram
    bear_phase = map_ram(0x7C)
    machine = planning_start(1, planning=True)
    ram, labels = machine.ram, machine.labels
    ram[labels['floor_types']:labels['floor_types']+9] = bytes(9)
    cases, ticks, clocks = 0, 0, []
    for completed in range(5):
        phase_clocks = []
        for phase in range(11):
            reference = Reference()
            ref = reference.ram
            ref[0x56], ref[0x31] = completed, phase
            reference.call(0xD8FD)
            ram[labels['completed_mountains']] = completed
            ram[labels['maxfloor']] = 0
            machine.call('environment_init')
            # The original $31 counts down10..0; our shared11-frame phase
            # counts up0..10. Progress/reset must not restart that phase.
            ram[labels['timer_divider']] = 10-phase
            machine.call('reset_bear_timer')
            assert ram[labels['timer_divider']] == 10-phase
            for tick in range(1, 5001):
                reference.call(0xCB9D)
                reference.call(0xD7DE)
                machine.call('environment_tick')    # $CB9D slow timers
                machine.call('normal_pan_try')      # $D7DE borrow and bear phase
                actual = ram[labels['bear_timer']:labels['bear_timer']+2]
                assert actual == bytes((ref[0x3D], ref[0x2C])), \
                    ('bear low/high clock', completed, phase, tick, list(actual), ref[0x3D], ref[0x2C])
                assert ram[labels['timer_divider']]+ref[0x31] == 10
                assert ram[bear_phase] == ref[0x7C], ('bear spawn time', completed, phase, tick)
                ticks += 1
                if ref[0x7C]:
                    phase_clocks.append(tick)
                    cases += 1
                    break
            else:
                raise AssertionError(('bear did not spawn', completed, phase))
        clocks.append(phase_clocks)
    return dict(source_timers='$CB9D', source_borrow='$D7DE', source_reset='$D8FD',
                phase_cases=cases, compared_logic_ticks=ticks, spawn_ticks=clocks)


def main():
    report = dict(status='passed', horizontal_steps=check_horizontal(),
                  vertical_steps=check_vertical(), walk_off_cases=check_walk_off(),
                  helmet_probes=check_helmet_probes(),
                  feet_and_post_cases=check_posts_and_feet(), integrated_support_cases=check_integrated_support(),
                  block_break_cases=check_block_breaks(),
                  controls=check_controls(), ground_fire_swing=check_ground_swing(),
                  normal_clouds=check_clouds(), surface_flow_steps=check_surface_flow(),
                  bear_spawn_clock=check_bear_spawn_clock(),
                  nes_prg_sha256=hashlib.sha256(PRG).hexdigest(),
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    target = BASE/'docs/verification/original_physics.json'
    target.write_text(json.dumps(report, indent=2)+'\n')
    print('PASS executed NES horizontal/vertical physics, wrapping, hammer probes, stone posts and UP controls')


if __name__ == '__main__':
    main()
