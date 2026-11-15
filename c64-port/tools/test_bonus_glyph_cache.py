"""Exact shared bonus-cloud phase font after dirty RAM and repeated entries."""
import hashlib
import json
from functools import cache

from test_game import BASE, start
from test_scroll_cloud_edges import original_cloud_mask

FONT_FIRST = 128
FONT_START = 0x4800+FONT_FIRST*8
FONT_SIZE = 8*40


@cache
def source_phase(phase):
    source = (BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    middle = prg[0x24BB+5]
    capped = original_cloud_mask(2, phase)
    repeated = bytes((((source[middle*16+y] | source[middle*16+8+y]) >> phase) |
                      ((source[middle*16+y] | source[middle*16+8+y]) << (8-phase))) & 255
                     for y in range(8))
    return capped[:16]+repeated+capped[16:]


@cache
def source_font():
    return b''.join(source_phase(phase) for phase in range(8))


def main():
    machine = start()
    ram, labels = machine.ram, machine.labels
    expected = source_font()
    assert len(expected) == 320
    checked = 0
    for entry, mountain in enumerate((1, 4, 8)):
        ram[labels['mountain']] = mountain
        ram[FONT_START:FONT_START+FONT_SIZE] = bytes([0xA5+entry])*FONT_SIZE
        machine.call('enter_bonus')
        assert bytes(ram[FONT_START:FONT_START+FONT_SIZE]) == expected, ('dirty bonus entry', mountain)
        checked += FONT_SIZE
        # view_init restores the shared phase font after its terrain/font
        # restore, without changing the bonus collision height index.
        ram[0xEC00:0xEC40] = bytes([0xB6+entry])*64
        neighbours = bytes(ram[0xEC00:0xEC40])
        ram[FONT_START:FONT_START+FONT_SIZE] = b'\x5a'*FONT_SIZE
        machine.call('view_init')
        assert bytes(ram[FONT_START:FONT_START+FONT_SIZE]) == expected
        assert bytes(ram[0xEC00:0xEC40]) == neighbours
        checked += FONT_SIZE
        for slot in range(1, 6):
            for phase in (7, 0, 1, 2, 3, 4, 5, 6):
                ram[labels['bonus_cloud_x']+slot-1] = 128+phase
                machine.x = slot-1
                machine.call('bonus_cloud_phase')
                glyph = FONT_FIRST+5*phase
                assert ram[labels['cloud_glyph']] == glyph, ('shared phase ID', slot, phase)
                assert ram[labels['GLYPH_PHASE']+slot] == phase
                assert bytes(ram[FONT_START:FONT_START+FONT_SIZE]) == expected, \
                    ('phase update rewrote shared font', entry, slot, phase)
                address = 0x4800+glyph*8
                assert bytes(ram[address:address+40]) == source_phase(phase)
                checked += 40
    report = dict(status='passed', entries=3, shared_font_phases=8, cloud_slots=5,
                  glyph_codes=[FONT_FIRST, FONT_FIRST+39], view_init_restores_font=True,
                  exact_source_bytes=checked, dirty_ram_reinitialized=True,
                  phase_wrap_7_to_0=True, height_index_neighbours_unchanged=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/bonus_glyph_cache.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS exact shared bonus phase font:', report)


if __name__ == '__main__':
    main()
