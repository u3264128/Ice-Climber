"""Scene setup restores terrain and keeps the source cloud atlas off screen."""
import hashlib
import json

from plan_mountains import PlanningMachine
from test_bonus_glyph_cache import FONT_START, FONT_SIZE, source_font
from test_game import BASE


def check_font(ram, expected, private, context):
    actual = bytes(ram[0x4800:0x5000])
    assert actual == expected, ('restored scene font', context)
    reachable = set(ram[0xE000:0xE800])
    assert not reachable & private, ('private glyph reached world', context, reachable & private)
    return len(reachable)


def main():
    machine = PlanningMachine()
    ram, labels = machine.ram, machine.labels
    terrain = (BASE/'c64/build/terrain_charset.bin').read_bytes()
    phases = (BASE/'c64/build/original_cloud_phases.bin').read_bytes()
    atlas = (BASE/'c64/build/normal_cloud_phase_codes.bin').read_bytes()
    expected_normal = bytearray(terrain)
    for i, code in enumerate(atlas):
        expected_normal[code*8:(code+1)*8] = phases[i*8:(i+1)*8]
    expected_normal[52*8:56*8] = phases[-32:]
    normal_private = (set(atlas) - {255}) | set(range(52,56))
    expected_bonus = bytearray(terrain)
    offset = FONT_START-0x4800
    expected_bonus[offset:offset+FONT_SIZE] = source_font()
    compared = 0
    for mountain in range(1,33):
        ram[labels['mountain']] = mountain
        machine.call('setup_level')
        ram[labels['state']] = 1
        ram[0x4800:0x5000] = b'\xA5'*2048
        machine.call('view_init')
        machine.call('cache_normal')
        compared += check_font(ram, expected_normal, normal_private, ('normal', mountain))
    for mountain in range(1,9):
        ram[labels['mountain']] = mountain
        ram[0x4800:0x5000] = b'\x5A'*2048
        machine.call('enter_bonus')
        compared += check_font(ram, expected_bonus, set(range(228,249)), ('bonus', mountain))
    report = dict(status='passed', normal_mountains=32, bonus_variants=8,
                  restored_source_bytes=40*2048, reachable_glyph_comparisons=compared,
                  private_normal_atlas_unreachable=True, source_phase_pixels=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/unused_cloud_font.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS cloud atlas and scene font lifecycle:',report)


if __name__ == '__main__':
    main()
