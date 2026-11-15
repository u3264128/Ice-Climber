"""Collision posts must have their original five-tile visible columns."""
import hashlib
import json

from original_stones import stone_cells
from plan_mountains import PlanningMachine
from test_game import BASE
from test_original_physics import Reference


def main():
    machine = PlanningMachine()
    ram, labels = machine.ram, machine.labels
    checks = tables = 0
    for players in (1, 2):
        for mountain in range(1, 33):
            ram[labels['state']] = 1
            ram[labels['game_mode']] = players-1
            ram[labels['mountain']] = mountain
            ram[labels['new_game']] = 1
            machine.call('setup_level')
            for (row, column), _ in stone_cells(mountain).items():
                actual = ram[0xE000+row*32+column]
                assert actual == 224, ('invisible stone column', players, mountain, row, column, actual)
                assert ram[0xF000+row*32+column] & 8, ('invisible stone colour', players, mountain, row, column)
                assert not ram[labels['ROW_KIND']+row] & 128, ('post treated as side walls only', row)
                checks += 1
            reference = Reference()
            reference.ram[0x59] = mountain-1
            for camera in range(6):
                reference.ram[0x90] = camera+4
                reference.call(0xE002)
                ram[labels['cam']] = camera
                ram[1] = 0x34
                machine.call('nes_export')
                machine.call('nes_stones_seen')
                assert machine.under_io[0x70:0xA0] == reference.ram[0x600:0x630], (
                    'stone collision table', players, mountain, camera)
                ram[1] = 0x35
                tables += 1
    report = dict(status='passed', mountains=32, player_modes=2, stone_cells=checks,
                  source='executed E05E PPU commands and E002 collision tables',
                  collision_tables=tables,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/stone_columns.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS visible original stone columns', report)


if __name__ == '__main__':
    main()
