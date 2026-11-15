"""Adjacent cloud footprints use their exact six/eight-cell wrapped union."""
import hashlib
import itertools
import json

from plan_mountains import PlanningMachine
from test_bonus_glyph_cache import FONT_START, FONT_SIZE, source_font, source_phase
from test_game import BASE


def cloud_row(x, width):
    phase = x&7
    roles = (0,1)+(2,)*(width//8-3)+(3,4)
    result = bytearray([255])*32
    for offset,role in enumerate(roles):
        result[(x//8+offset)&31] = 128+5*phase+role
    return bytes(result)


def covered(kind, low, high):
    assert kind in (1,5), ('unexpected cloud patch kind',kind)
    if kind&4:
        assert low>high, ('invalid wrapped interval',low,high)
        return set(range(low,32))|set(range(high+1))
    assert low<=high, ('invalid linear interval',low,high)
    return set(range(low,high+1))


def main():
    machine = PlanningMachine()
    ram, labels = machine.ram, machine.labels
    fixture = BASE/'tools/fixtures/bonus_cloud_tiles_reference.json'
    golden = fixture.read_bytes()
    expected_font = source_font()
    cases = fresh = pending = wrap_crossings = 0
    heights = set()
    for mountain in (1,4):
        ram[labels['mountain']] = mountain
        machine.call('enter_bonus')
        initial = bytes(ram)
        count = ram[labels['bonus_cloud_count']]
        for slot in range(count):
            height = initial[labels['bonus_cloud_hlo']+slot]+256*initial[labels['bonus_cloud_hhi']+slot]
            row = height//8+2
            heights.add(height)
            address = 0xE000+row*32
            for column,width,direction,prior in itertools.product(range(32),(32,48),(-1,1),(0,1,5)):
                ram[:] = initial
                old_x = column*8+(7 if direction>0 else 0)
                new_x = (old_x+direction)&255
                ram[labels['bonus_cloud_width']+slot] = width
                ram[labels['bonus_cloud_x']+slot] = old_x
                machine.x = slot
                machine.call('bonus_cloud_paint')
                assert bytes(ram[address:address+32]) == cloud_row(old_x,width)
                assert ram[labels['BONUS_CLOUD_CACHE_ROW']+slot] == row
                ram[labels['PATCH_FLAG']:labels['PATCH_FLAG']+64] = bytes(64)
                ram[labels['patch_any']] = 0
                prior_cells = set()
                if prior:
                    low,high = (14,16) if prior==1 else (29,3)
                    ram[labels['PATCH_FLAG']+row] = prior
                    ram[labels['PATCH_LO']+row] = low
                    ram[labels['PATCH_HI']+row] = high
                    ram[labels['patch_any']] = prior
                    prior_cells = covered(prior,low,high)
                before = bytes(ram[0xE000:0xE800])
                colours = bytes(ram[0xF000:0xF800])
                ram[labels['bonus_cloud_x']+slot] = new_x
                machine.x = slot
                machine.call('bonus_cloud_paint')
                context = (mountain,slot,height,column,width,direction,prior)
                expected_row = cloud_row(new_x,width)
                expected_world = bytearray(before)
                expected_world[row*32:row*32+32] = expected_row
                assert ram[0xE000:0xE800] == expected_world, ('independent complete row/world',context)
                assert ram[0xF000:0xF800] == colours, ('immutable cloud colours',context)
                assert ram[FONT_START:FONT_START+FONT_SIZE] == expected_font, ('source phase font',context)
                phase_mask = source_phase(new_x&7)
                for code in expected_row:
                    if code != 255:
                        phase,role = divmod(code-128,5)
                        assert phase == new_x&7
                        assert bytes(ram[0x4800+code*8:0x4800+(code+1)*8]) == phase_mask[role*8:role*8+8]
                flags = bytes(ram[labels['PATCH_FLAG']:labels['PATCH_FLAG']+64])
                assert flags[row] in (1,5) and not any(flags[:row]+flags[row+1:]), ('dirty rows',context,flags)
                actual = covered(flags[row],ram[labels['PATCH_LO']+row],ram[labels['PATCH_HI']+row])
                changed = {x for x in range(32) if before[row*32+x] != expected_row[x]}
                assert changed|prior_cells <= actual, ('patch missed current/prior changes',context,changed|prior_cells,actual)
                if not prior:
                    assert len(changed) == width//8+2
                    assert actual == changed and len(actual) in (6,8), \
                        ('fresh adjacent union widened',context,changed,actual)
                    fresh += 1
                else:
                    pending += 1
                wrap_crossings += abs(old_x//8-new_x//8)==31
                cases += 1
    assert fixture.read_bytes() == golden, 'Canonical cloud golden changed'
    report = dict(status='passed',cases=cases,fresh_exact_unions=fresh,prior_flag_cases=pending,
                  old_columns=32,widths=[32,48],directions=['left','right'],
                  heights=sorted(heights),height_banks=sorted({height>>8 for height in heights}),
                  boundary_0_31_crossings=wrap_crossings,source_phase_masks_exact=True,
                  canonical_golden_unchanged=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/bonus_cloud_union.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS exact adjacent bonus cloud patch unions:',report)


if __name__ == '__main__':
    main()
