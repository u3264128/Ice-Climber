#!/usr/bin/env python3
"""Compare the flyover controller with executed NES C3CC/C3E8/D8EA/F737.

The reference runs original machine code, including its 240px nametable wrap
and slow timer bank. It does not derive expected coordinates from C64 code.
"""
import argparse
import hashlib
import json
import re

from extract_levels import BASE, Generator, generate_bonus
from probe_preview import original_prg, trace_preview
from test_original_levels import reference_planes
from original_stones import stone_cells


def normal_reference(prg, mountain):
    """Original wall PPU commands plus independently decoded block planes."""
    tiles = {int(n, 16): int(v) for n, v in re.findall(
        r'NES_TILE_([0-9A-F]+) = (\d+)', (BASE/'c64/build/terrain_tiles.inc').read_text())}
    font = (BASE/'c64/build/terrain_charset.bin').read_bytes()
    assert font[tiles[0xA2]*8:tiles[0xA2]*8+8] == font[224*8:225*8]
    tiles[0xA2] = 224  # Last cloud-wall bottom and EB have identical pixels.
    world = [bytearray([255])*32 for _ in range(112)]

    class Walls(Generator):
        def step(self):
            # E79D submits each section's actual PPU command buffer through
            # C150 with X9. Capture its12 vertical six-tile commands before
            # the PPU writer. No terrain is synthesized by the C64 renderer.
            if self.pc == 0xC150 and self.x == 9:
                section = self.ram[0x0F]
                for cmd in range(12):
                    offset = 0x600+cmd*9
                    column = self.ram[offset+1] & 31
                    assert self.ram[offset+2] == 0x86
                    for y, tile in enumerate(self.ram[offset+3:offset+9]):
                        world[section*6+1-y][column] = tiles[tile]
                self.pc = (self.pop() | self.pop() << 8)+1
            elif self.ram[self.pc] in (0x3E, 0x7E):
                # Wall narrowing shifts six tile IDs across the whole side;
                # these two legal opcodes are absent from the small ROM CPU.
                op = self.ram[self.pc]
                address = (int.from_bytes(self.ram[self.pc+1:self.pc+3], 'little')+self.x) & 65535
                value = self.ram[address]
                if op == 0x3E:
                    result, carry = (value << 1 | self.c) & 255, value >> 7
                else:
                    result, carry = value >> 1 | self.c << 7, value & 1
                self.write(address, result)
                self.c = carry
                self.setzn(result)
                self.pc += 3
            else:
                super().step()

    ram = bytearray(65536)
    ram[0xC000:] = prg
    ram[0x59] = mountain
    walls = Walls(ram, {})
    walls.call(0xE79D)
    raw, descriptors, _ = reference_planes(prg, mountain)
    upper_widths = (4, 4, 5, 5, 5, 6, 6, 6, 4)
    lower_widths = (4, 4, 4, 5, 5, 5, 6, 6, 6)
    for floor in range(9):
        descriptor = descriptors[floor-1] if 1 <= floor <= 7 else 0
        for layer, widths in enumerate((upper_widths, lower_widths)):
            for column in range(widths[floor], 32-widths[floor]):
                value = raw[layer*216+floor*24+column-4]
                tile = 255 if value == 255 else 224 if value in (0, 3, 4) else (
                    223 if value == 1 else 227) if layer else 218
                if not layer and value == 1 and 0 < descriptor & 0xE0 < 0x80:
                    tile = 250 if descriptor & 0x10 else 249
                world[floor*6+2-layer][column] = tile
    for row, column in stone_cells(mountain+1):
        world[row][column] = 224
    world[0][:] = bytes([221])*32
    return world


def world_reference(prg, mountain):
    world = normal_reference(prg, mountain)
    world[50][:] = bytes([255])*32
    for ledge in generate_bonus(prg, mountain)['platforms']:
        row = 50+ledge['height']//8
        world[row][ledge['left']//8:ledge['right']//8] = bytes([224])*((ledge['right']-ledge['left'])//8)
    return world


def frozen_fields(read, labels):
    """Only gameplay values; renderer buffers, input and private clocks vary."""
    names = ('lives', 'score_top', 'cam', 'curfloor', 'maxfloor', 'pxlo', 'pxhi',
             'py', 'vy', 'onground', 'logic_frame', 't_floor', 't_state', 't_wait',
             'epxlo', 'edir', 'bird_state', 'bird_wait', 'bird_fraction',
             'bear_state', 'bear_timer', 'last_climb', 'topi_spawn_wait')
    values = [(name, bytes(read(labels[name], 1))) for name in names if name in labels]
    values += [('score', bytes(read(labels['score_lo'], 2))),
               ('contexts_and_counters', bytes(read(0x200, 0x4A))),
               ('normal_map_clouds', bytes(read(0x400, 0x240)))]
    return values


def assert_shown_world(read, labels, world, shown_row=None):
    if shown_row is None:
        shown_row = read(labels['last_view_row'], 1)[0]
    if shown_row == 255:
        return
    screen = 0x4000+0x400*read(labels['screen_buffer'], 1)[0]
    for y in range(25):
        row = shown_row+24-y
        actual = read(screen+y*40+4, 32)
        assert actual == world[row], ('committed preview row', row, y,
                                      [(i, a, b) for i, (a, b) in enumerate(zip(actual, world[row])) if a != b][:5])


def assert_preview_sprites(read, labels):
    """Only the original condor and its one carried fruit enter the IRQ list."""
    frames = {v['name']: v['pointer'] for v in json.loads((BASE/'c64/build/sprite_frames.json').read_text())}
    bird_y = read(labels['preview_bird_y'], 1)[0]
    pose = read(labels['preview_anim_frame'], 1)[0]
    # NES has240 visible lines; the C64 preview centres that into its smaller
    # viewport. This screen-only offset keeps the original final hold visible.
    bird_screen_y, fruit_screen_y = bird_y+30, bird_y+44
    flap = 1 if pose == 1 else 0
    expected = []
    if 35 <= bird_screen_y < 247:
        expected += [(164, bird_screen_y, frames[f'CONDOR_L_FLAP{flap}_0_0']),
                     (188, bird_screen_y, frames[f'CONDOR_L_FLAP{flap}_24_0'])]
    if 35 <= fruit_screen_y < 247:
        ptr = frames['FRUIT_L_0_0_0']
        expected += [(174, fruit_screen_y, ptr), (174, fruit_screen_y, ptr+1)]
    count = read(labels['logical_count'], 1)[0]
    data = read(0xE800, 0x100)
    actual = [(data[i], data[0x40+i], data[0x60+i]) for i in range(count)]
    assert actual == expected, ('preview actor list', bird_y, pose, actual, expected)


def world_tests(prg):
    from plan_mountains import PlanningMachine
    m = PlanningMachine()
    r, labels = m.ram, m.labels
    rows_checked = 0
    for mountain in range(32):
        world = world_reference(prg, mountain)
        r[labels['mountain']] = mountain+1
        r[labels['state']] = 1
        m.call('setup_level')
        m.call('preview_init')
        m.call('preview_cache_init')
        for row in range(50):
            actual = r[0xE000+row*32:0xE020+row*32]
            assert actual == world[row], ('normal preview map', mountain+1, row,
                                         [(i, a, b) for i, (a, b) in enumerate(zip(actual, world[row])) if a != b][:5])
            rows_checked += 1
        # Cross both64-row ring wraps and include the prefetch row at105.
        for view_row in range(81):
            r[labels['view_row']] = view_row
            m.call('preview_cache_stream')
            for row in range(view_row, view_row+26):
                actual = r[0xE000+(row & 63)*32:0xE020+(row & 63)*32]
                assert actual == world[row], ('streamed preview map', mountain+1, view_row, row)
                rows_checked += 1
    return dict(static_mountains=32, static_rows_checked=rows_checked,
                original_wall_ppu_commands=True, original_bonus_generator=True)


def integration_tests(prg, trace):
    from plan_mountains import PlanningMachine
    results = []
    for mountain in (1, 6):
        m = PlanningMachine()
        r, labels = m.ram, m.labels
        read = lambda address, count: r[address:address+count]
        r[labels['selected_mountain']] = mountain
        m.frame(0xEF)
        assert r[labels['state']] == 4
        frozen = frozen_fields(read, labels)
        world = world_reference(prg, mountain-1)
        frames = ticks = 0
        shown_row = None
        while r[labels['state']] == 4 and frames < 700:
            if r[labels['packet_ready']]:
                shown_row = r[labels['last_view_row']]
            m.frame((255, 0xFE, 0xFB, 0xF7)[frames % 4])
            frames += 1
            ticks += 1                  # one flyover tick per PAL frame
            if r[labels['state']] != 4:
                break
            expected = trace[ticks-1]
            assert frozen_fields(read, labels) == frozen, ('preview gameplay changed', mountain, frames)
            camera = int.from_bytes(read(labels['preview_camera'], 2), 'little')
            assert camera == expected['camera'] and r[labels['preview_bird_y']] == expected['bird_y']
            visual = int.from_bytes(read(labels['visual_camera'], 2), 'little')
            assert visual == camera, ('preview camera stalled', mountain, frames, visual, camera)
            if shown_row is not None:
                assert_shown_world(read, labels, world, shown_row)
            assert_preview_sprites(read, labels)
        assert frames == 573 and r[labels['state']] == 1, (mountain, frames, r[labels['state']])
        assert r[labels['lives']] == 3 and r[labels['curfloor']] == 0
        assert r[labels['normal_camera']:labels['normal_camera']+2] == b'\0\0'
        assert r[labels['logic_frame']] == 0, 'Gameplay tick ran before preview handoff'
        # A stage transition follows original CC7E directly, without a preview.
        m.call('next_mountain')
        assert r[labels['state']] == 1 and r[labels['mountain']] == mountain+1
        results.append(dict(mountain=mountain, pal_frames=frames, reached_gameplay=True,
                            exact_camera=True, frozen_gameplay=True,
                            next_mountain_without_preview=True))
    return results


def source_tests(prg):
    traces = [trace_preview(prg, phase) for phase in range(11)]
    for phase, rows in enumerate(traces):
        assert all(v['camera'] == 0 for v in rows[:48])
        assert rows[47]['bird_y'] == 128
        assert rows[48]['camera'] == 2 and rows[48]['bird_y'] == 128
        assert rows[366]['camera'] == 638 and rows[366]['bird_y'] == 126
        assert rows[415]['bird_y'] == 28 and rows[415]['anim_frame'] == 1
        assert all(v['camera'] == 638 and v['bird_y'] == 28 for v in rows[415:])
        assert rows[-1]['state'] == 1 and rows[-1]['hold'] == 1
        assert sum(v['phase'] == 'scroll' for v in rows) == 319
        # The last scroll tick also starts the final ascent of the bird.
        assert sum(v['phase'] == 'depart' for v in rows) == 49
        assert all(v['state'] == 5 for v in rows[:-1])
        assert rows[-1]['anim_tick'] == 0 and rows[-1]['anim_frame'] == 1
    # The last normal floor and the first generated bonus row use the SAME
    # PPU row ($2BA0). Eight48px floor steps give a384px logical join.
    assert prg[0x1775] == 0x2B and prg[0x177E] == 0xA0
    assert prg[0x345B:0x3465] == bytes.fromhex('a9 2b 8d 49 03 a9 a0 8d 48 03')
    return traces


def paired_tests(traces):
    from plan_mountains import PlanningMachine
    m = PlanningMachine()
    r, labels = m.ram, m.labels
    assert 'preview_tick' in labels, 'Build the coordinated preview patch first'
    key_labels = dict(camera='preview_camera', bird_y='preview_bird_y',
                      anim_tick='preview_anim_tick', anim_frame='preview_anim_frame',
                      hold='preview_hold', timer_phase='preview_timer_phase',
                      scroll='preview_scroll', wraps='preview_wraps')
    cases = 0
    for phase, rows in enumerate(traces):
        r[labels['mountain']] = 1
        m.call('preview_init')
        assert r[labels['state']] == 4
        r[labels['preview_timer_phase']] = phase
        assert r[labels['preview_bird_y']] == 224
        assert r[labels['preview_camera']:labels['preview_camera']+2] == b'\x00\x00'
        protected = bytes(r[:0x100] + r[0x200:0x252] + r[0x25C:])
        for expected in rows:
            m.call('preview_tick')
            for key, label in key_labels.items():
                addr = labels[label]
                got = r[addr] + (r[addr+1]*256 if key == 'camera' else 0)
                assert got == expected[key], (phase, expected['tick'], key, got, expected[key])
            assert r[labels['preview_done']] == (expected['state'] == 1)
            assert r[labels['state']] == 4, 'The main loop owns the masked bottom reset'
            assert bytes(r[:0x100] + r[0x200:0x252] + r[0x25C:]) == protected, 'Preview advanced gameplay state'
            cases += 1
        m.call('preview_tick')
        assert r[labels['preview_done']] == 1
    # Geometry selection stays shared with actual bonus entry for all32 menus.
    for mountain in range(1, 33):
        r[labels['mountain']] = mountain
        m.call('preview_init')
        variant = (mountain-1) & 7
        expected_ptr = labels['bonus_platform_src']+variant*97
        got = r[labels['bonus_platform_ptr']]+256*r[labels['bonus_platform_ptr']+1]
        assert got == expected_ptr, (mountain, got, expected_ptr)
        assert r[labels['bonus_platform_count']] == r[expected_ptr]
    return dict(paired_ticks=cases, geometry_selections=32, gameplay_state_frozen=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--world-only', action='store_true')
    parser.add_argument('--integration-only', action='store_true')
    args = parser.parse_args()
    prg = original_prg()
    if args.world_only:
        print('PASS preview static geometry:', world_tests(prg), flush=True)
        return
    if args.integration_only:
        print('PASS preview main loop:', integration_tests(prg, trace_preview(prg)), flush=True)
        return
    traces = source_tests(prg)
    counts = [len(v) for v in traces]
    report = dict(status='passed', original_prg_sha256=hashlib.sha256(prg).hexdigest(),
                  original_routines=['C3CC', 'C3E8', 'CB9D', 'D8EA', 'F737', 'F67E'],
                  source_ticks=sum(counts), timer_phase_lengths=counts,
                  camera_pixels=638, stationary_camera_ticks=48,
                  camera_scroll_ticks=319, bird_departure_ticks=49,
                  bonus_join_height=384, source_music_id=1,
                  carried_fruit_offset=[10, 14], clouds_visible=False,
                  preview_on_title_start=True, preview_on_next_mountain=False,
                  return_to_bottom='masked reload, without downward flyover')
    if not args.source_only:
        report.update(paired_tests(traces))
        report.update(world_tests(prg))
        report['full_prg_previews'] = integration_tests(prg, traces[0])
        report['prg_sha256'] = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    (BASE/'docs/verification/original_preview.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS original preview:', sum(counts), 'source ticks;', counts, flush=True)
    if not args.source_only:
        print('PASS C64 preview coordinates, three poses, hold timer and paused gameplay', flush=True)


if __name__ == '__main__':
    main()
