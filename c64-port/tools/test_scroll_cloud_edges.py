"""Cloud CHR must be current wherever vertical fine scrolling can expose it.

The VIC's 24-row window opens at raster55 and closes at247. Its character
fetches begin at48+YSCROLL, so the union of visible rows over all eight fine
positions includes both top rows and the partly visible last cached row.
Expected masks come directly from the original NES sprite bitplanes.
"""
import hashlib
import json
from functools import cache

from test_game import BASE, start


def paint_floor_clouds(machine, floor):
    """Paint a floor's two clouds from scratch. The game's cloud_step only
    clears the cells of the two clouds' previous columns (old_cloud_col,
    old_cloud_col2): clear the row's cloud glyphs first."""
    ram, labels = machine.ram, machine.labels
    row = 0xE000+(floor*6+2)*32
    for cell in range(row, row+32):
        if 56 <= ram[cell] < 84+28:     # CLOUD_FIRST .. CLOUD_SECOND+27
            ram[cell] = 255             # BLANK
    ram[labels['cloud_slot']] = floor
    ram[labels['old_cloud_col']] = ram[labels['cloud_x']+floor]
    ram[labels['old_cloud_col2']] = ram[labels['cloud_x']+floor+8]
    machine.call('cloud_step', floor)

GLYPH_PHASE2, GLYPH_SHOWN2 = 0x0640, 0x0648


def visible_during_fine_scroll(screen_row):
    return any(max(55, 48+fine+8*screen_row) <
               min(247, 48+fine+8*(screen_row+1)) for fine in range(8))


@cache
def original_cloud_mask(profile, phase):
    chr_data = (BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    left, middle, right = (prg[0x24BB+i] for i in (6, 5, 4))
    tiles = ((left, middle, middle), (middle, middle, right),
             (left, middle, right))[profile]
    result = bytearray()
    for glyph in range(4):
        for y in range(8):
            byte = 0
            for x in range(8):
                source_x = glyph*8+x-phase
                if 0 <= source_x < 24:
                    tile, pixel = tiles[source_x//8], source_x%8
                    planes = chr_data[tile*16+y] | chr_data[tile*16+8+y]
                    if planes & (0x80 >> pixel):
                        byte |= 0x80 >> x
            result.append(byte)
    return bytes(result)


def check_cloud_edges():
    machine = start(mountain=5)
    ram, labels = machine.ram, machine.labels
    atlas = (BASE/'c64/build/normal_cloud_phase_codes.bin').read_bytes()
    for profile in range(3):
        for phase in range(8):
            expected = original_cloud_mask(profile, phase)
            offset = profile*32+phase*4
            for role, code in enumerate(atlas[offset:offset+4]):
                assert bytes(ram[0x4800+code*8:0x4800+(code+1)*8]) == expected[role*8:(role+1)*8]
    floor = 4
    cache_row = floor*6+2
    first = 56+(floor-1)*4
    second = 84+(floor-1)*4
    dirty = bytes([0xA5])*32
    cases = updates = source_bytes = 0
    tested_rows = (-1, 0, 1, 2, 23, 24, 25)
    for screen_row in tested_rows:
        # A normal cached world contains the test floor at this screen row.
        view_row = cache_row-(24-screen_row)
        camera = view_row*8
        for descriptor, profiles in ((0x60, (0, 1)), (0xE0, (2, 2))):
            for phase in range(8):
                ram[labels['mountain']] = 5
                machine.call('setup_level')
                ram[labels['state']] = 1
                ram[labels['paused']] = 1
                ram[labels['floor_types']:labels['floor_types']+9] = bytes(9)
                ram[labels['floor_types']+floor] = descriptor
                for slot, column, value in ((floor, 20, phase),
                                            (floor+8, 24, (phase+3)&7)):
                    ram[labels['cloud_x']+slot] = column
                    ram[labels['cloud_subpixel']+slot] = value
                paint_floor_clouds(machine, floor)
                machine.call('view_init')
                for address in (labels['normal_camera'], labels['visual_camera']):
                    ram[address:address+2] = camera.to_bytes(2, 'little')
                for glyph, shown in ((first, labels['GLYPH_SHOWN']+floor),
                                     (second, GLYPH_SHOWN2+floor)):
                    ram[0x4800+glyph*8:0x4800+(glyph+4)*8] = dirty
                    ram[shown] = 255
                machine.call('view_tick')
                machine.call('commit_view')
                machine.call('commit_colours')
                machine.call('commit_patches')
                visible = visible_during_fine_scroll(screen_row)
                assert ram[labels['last_view_row']] == view_row
                for turn in range(2):
                    for glyph, wanted, shown, profile in (
                        (first, labels['GLYPH_PHASE']+floor,
                         labels['GLYPH_SHOWN']+floor, profiles[0]),
                        (second, GLYPH_PHASE2+floor,
                         GLYPH_SHOWN2+floor, profiles[1])):
                        actual = bytes(ram[0x4800+glyph*8:0x4800+(glyph+4)*8])
                        context = (screen_row, descriptor, phase, turn, glyph)
                        if visible:
                            assert ram[shown] == ram[wanted], ('stale visible cloud phase', context,
                                                              ram[shown], ram[wanted])
                            expected = original_cloud_mask(profile, ram[wanted])
                            assert actual == expected, ('stale visible source mask', context)
                            source_bytes += len(expected)
                        else:
                            assert ram[shown] == 255 and actual == dirty, \
                                ('offscreen cloud unnecessarily committed', context)
                    if turn == 0:
                        ram[labels['GLYPH_PHASE']+floor] = (phase+1)&7
                        ram[GLYPH_PHASE2+floor] = (phase+4)&7
                        machine.call('commit_clouds')
                        updates += 1
                cases += 1
    return dict(cases=cases, phase_updates=updates, source_mask_bytes=source_bytes,
                screen_rows=list(tested_rows),
                potentially_visible_rows=[r for r in tested_rows if visible_during_fine_scroll(r)],
                both_clouds=True, original_profiles=3, phases=8)


def check_bonus_cloud_edges():
    """Hidden bonus clouds may keep an old phase; exposed ones may not."""
    from test_bonus_glyph_cache import FONT_START, FONT_SIZE, source_font, source_phase

    machine = start()
    ram, labels = machine.ram, machine.labels
    expected_font = source_font()
    original_write = machine.write
    watch_font = False
    def write(address, value):
        assert not (watch_font and FONT_START <= address < FONT_START+FONT_SIZE), \
            ('shared bonus font rewritten during a frame', hex(address))
        original_write(address, value)
    machine.write = write
    cases = source_bytes = 0
    for screen_row in (-1, 0, 1, 2, 23, 24, 25):
        view_row = 26-(24-screen_row)
        for width in (32, 48):
            for phase in range(8):
                watch_font = False
                machine.call('enter_bonus')
                ram[labels['paused']] = 1
                ram[labels['bonus_cloud_count']] = 1
                ram[labels['bonus_cloud_hlo']] = 192
                ram[labels['bonus_cloud_hhi']] = 0
                ram[labels['bonus_cloud_width']] = width
                ram[labels['bonus_cloud_x']] = 128+phase
                # Heights are immutable in play; rebuild the cache and its
                # footprint metadata after moving this controlled fixture.
                machine.call('cache_bonus')
                machine.call('view_init')
                for address in (labels['bonus_camera'], labels['visual_camera']):
                    ram[address:address+2] = (view_row*8).to_bytes(2, 'little')
                ram[labels['GLYPH_SHOWN']+1] = 255
                assert bytes(ram[FONT_START:FONT_START+FONT_SIZE]) == expected_font
                watch_font = True
                machine.call('view_tick')
                machine.call('commit_view')
                machine.call('commit_colours')
                machine.call('commit_patches')
                visible = visible_during_fine_scroll(screen_row)
                for turn in range(2):
                    wanted = ram[labels['GLYPH_PHASE']+1]
                    context = (screen_row, width, phase, turn)
                    assert wanted == ram[labels['bonus_cloud_x']] & 7
                    glyph = 128+5*wanted
                    actual = bytes(ram[0x4800+glyph*8:0x4800+(glyph+5)*8])
                    roles = (0, 1)+(2,)*(width//8-3)+(3, 4)
                    column = ram[labels['bonus_cloud_x']]//8
                    expected_codes = bytes(glyph+role for role in roles)
                    cache = 0xE000+26*32
                    assert bytes(ram[cache+column:cache+column+len(roles)]) == expected_codes, \
                        ('incorrect phase IDs in cloud row', context)
                    assert bytes(ram[FONT_START:FONT_START+FONT_SIZE]) == expected_font, \
                        ('shared source font changed', context)
                    if visible:
                        assert ram[labels['GLYPH_SHOWN']+1] == wanted, \
                            ('stale displayed bonus phase', context)
                        expected = source_phase(wanted)
                        assert actual == expected, ('stale displayed bonus mask', context)
                        screen = 0x4000+1024*ram[labels['screen_buffer']]
                        shown = screen+screen_row*40+4+column
                        assert bytes(ram[shown:shown+len(roles)]) == expected_codes, \
                            ('stale displayed shared glyph IDs', context)
                        source_bytes += len(expected)
                    else:
                        assert ram[labels['GLYPH_SHOWN']+1] == 255, \
                            ('hidden bonus cloud phase needlessly committed', context)
                    if turn == 0:
                        ram[labels['bonus_cloud_x']] += 1
                        machine.x = 0
                        machine.call('bonus_cloud_paint')
                        machine.call('commit_patches')
                cases += 1
    return dict(bonus_cases=cases, bonus_source_mask_bytes=source_bytes,
                offscreen_bonus_phases_may_remain_stale=True,
                exposed_bonus_phases_always_current=True,
                bonus_shared_font_unchanged_during_frames=True)


def main():
    result = check_cloud_edges()
    result.update(check_bonus_cloud_edges())
    result.update(status='passed', prg_sha256=hashlib.sha256(
        (BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/scroll_cloud_edges.json').write_text(
        json.dumps(result, indent=2)+'\n')
    print('PASS cloud masks at every exposed top/bottom scroll edge:', result)


if __name__ == '__main__':
    main()
