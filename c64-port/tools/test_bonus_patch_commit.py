"""Mixed cloud patches update both complete buffers from an independent map."""
import hashlib
import itertools
import json

from plan_mountains import PlanningMachine
from test_game import BASE


def screen(world, view):
    result = bytearray([0xA5])*1024
    for y in range(25):
        row = (view+24-y)&63
        result[y*40+4:y*40+36] = world[row*32:row*32+32]
    return result


def check_staged_copy(machine, initial, world, cloud_row):
    """Patch during each stage, then execute the remaining generated columns."""
    ram, labels = machine.ram, machine.labels
    first, split = ram[labels['copy_bonus_starts']:labels['copy_bonus_starts']+2]
    assert first == 31 and 0 <= split < first
    view, target, previous_back = 29, 30, 28
    assert target <= cloud_row <= view+24
    assert not ram[labels['SAME2']+cloud_row]
    cases = 0
    for bank, stage, (kind, low, high) in itertools.product(
            (0,1), (2,3,4,5), ((1,17,25), (5,29,4))):
        ram[:] = initial
        ram[labels['player_count']] = 2
        front = 0x4000+bank*1024
        back = 0x4000+(bank^1)*1024
        ram[front:front+1024] = screen(world,view)
        ram[back:back+1024] = screen(world,previous_back)
        for name, value in (('screen_buffer',bank), ('last_view_row',view),
                            ('copy_target_row',target), ('copy_stage',stage),
                            ('back_view',previous_back)):
            ram[labels[name]] = value
        machine.call('bonus_copy_setup_first')
        if stage >= 3:
            machine.call('bonus_copy_setup_second')
        if stage >= 4:
            machine.x = split
            machine.call('CACHE_COPY_RUN',first)
        if stage == 5:
            machine.x = 255
            machine.call('CACHE_COPY_RUN',split)

        columns = list(range(low,32))+list(range(high+1)) if kind & 4 else range(low,high+1)
        expected_back = bytearray(ram[back:back+1024])
        for col in columns:
            addr = 0xE000+cloud_row*32+col
            ram[addr] ^= 0xFF
            if stage >= 4:
                expected_back[(target+24-cloud_row)*40+4+col] = ram[addr]
        ram[labels['PATCH_FLAG']:labels['PATCH_FLAG']+64] = bytes(64)
        for name, value in (('PATCH_FLAG',kind), ('PATCH_LO',low), ('PATCH_HI',high)):
            ram[labels[name]+cloud_row] = value
        ram[labels['patch_any']] = kind
        updated = bytes(ram[0xE000:0xE800])
        machine.call('commit_patches')
        context = (bank,stage,kind)
        assert ram[front:front+1024] == screen(updated,view), ('staged front',context)
        assert ram[back:back+1024] == expected_back, ('staged back',context)
        assert not ram[labels['PATCH_FLAG']+cloud_row] and not ram[labels['patch_any']]

        if stage == 2:
            machine.call('bonus_copy_setup_second')
        if stage <= 3:
            machine.x = split
            machine.call('CACHE_COPY_RUN',first)
        if stage <= 4:
            machine.x = 255
            machine.call('CACHE_COPY_RUN',split)
        assert ram[back:back+1024] == screen(updated,target), ('completed back',context)
        cases += 1
    return cases


def main():
    machine = PlanningMachine()
    ram, labels = machine.ram, machine.labels
    ram[labels['mountain']] = 3
    machine.call('enter_bonus')
    assert ram[labels['bonus_cloud_count']] == 5
    rows = [ram[labels['bonus_cloud_hlo']+i]//8+
            32*ram[labels['bonus_cloud_hhi']+i]+2 for i in range(5)]
    assert len(set(rows)) == 5
    assert list(ram[labels['BONUS_CLOUD_CACHE_ROW']:labels['BONUS_CLOUD_CACHE_ROW']+5]) == rows
    initial = bytes(ram)
    original_world = bytes(ram[0xE000:0xE800])
    spans = ((1,2,8), (5,29,3), (1,7,13), (5,30,4), (1,0,31))
    cases = dirty_rows = 0
    for mask, bank, view, delta, stage in itertools.product(
            range(32), (0,1), (2,12,20,28,34), (-2,0,2), (0,4)):
        ram[:] = initial
        target = view+delta
        front = 0x4000+bank*1024
        back = 0x4000+(bank^1)*1024
        ram[front:front+1024] = screen(original_world,view)
        ram[back:back+1024] = screen(original_world,target)
        ram[0xD800:0xDBE8] = b'\xB6'*1000
        ram[labels['screen_buffer']] = bank
        ram[labels['last_view_row']] = view
        ram[labels['copy_target_row']] = target
        ram[labels['copy_stage']] = stage
        ram[labels['PATCH_FLAG']:labels['PATCH_FLAG']+64] = bytes(64)
        ram[labels['patch_any']] = bool(mask)
        for i, row in enumerate(rows):
            if mask & (1<<i):
                kind, low, high = spans[i]
                ram[labels['PATCH_FLAG']+row] = kind
                ram[labels['PATCH_LO']+row] = low
                ram[labels['PATCH_HI']+row] = high
                columns = list(range(low,32))+list(range(high+1)) if kind & 4 else range(low,high+1)
                for column in columns:
                    ram[0xE000+row*32+column] = (row*7+column*13+cases)&255
                dirty_rows += 1
        world = bytes(ram[0xE000:0xE800])
        expected_front = screen(world,view)
        expected_back = screen(world if stage else original_world,target)
        colour_back = bytes(ram[0xEC00:0xEFE8])
        source_colours = bytes(ram[0xF000:0xF800])
        machine.call('commit_patches')
        context = (mask,bank,view,delta,stage)
        assert ram[front:front+1024] == expected_front, ('front buffer',context)
        assert ram[back:back+1024] == expected_back, ('back buffer',context)
        assert ram[0xD800:0xDBE8] == b'\xB6'*1000, ('immutable bonus colours',context)
        assert ram[0xEC00:0xEFE8] == colour_back, ('bonus metadata/colour back',context)
        assert ram[0xE000:0xE800] == world and ram[0xF000:0xF800] == source_colours
        assert not any(ram[labels['PATCH_FLAG']:labels['PATCH_FLAG']+64]), ('uncleared flags',context)
        assert ram[labels['patch_any']] == 0, ('uncleared patch_any',context)
        cases += 1
    # The new loop itself also handles zero safely. Actual source variants
    # all have1..5clouds; commit_clouds has that separate source contract.
    ram[:] = initial
    ram[labels['bonus_cloud_count']] = 0
    ram[labels['patch_any']] = 0
    ram[labels['PATCH_FLAG']:labels['PATCH_FLAG']+64] = bytes(64)
    machine.call('bonus_commit_patches')
    assert ram[labels['patch_any']] == 0 and ram[labels['ui_index']] == 255
    staged_cases = check_staged_copy(machine, initial, original_world, rows[-1])
    report = dict(status='passed', cases=cases, dirty_rows=dirty_rows,
                  staged_two_player_cases=staged_cases,
                  uncopied_back_untouched=True, completed_staged_copy_matches_cache=True,
                  dirty_subsets=32, cloud_rows=5, screen_buffers=2,
                  mixed_linear_wrapped_full_rows=True, zero_clouds_safe=True,
                  all_flags_cleared=True, complete_buffers_match_cache=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/bonus_patch_commit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS five-cloud commit patches:',report)


if __name__ == '__main__':
    main()
