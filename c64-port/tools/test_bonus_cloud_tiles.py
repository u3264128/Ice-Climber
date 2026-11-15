"""Compare shared-font rows with the unchanged legacy generic-writer golden."""
import hashlib
import json

from plan_mountains import PlanningMachine
from test_game import BASE
from test_bonus_glyph_cache import FONT_START, FONT_SIZE, source_font, source_phase


def digest(data):
    return hashlib.sha256(data).hexdigest()


def result(m,slot):
    r,L=m.ram,m.labels
    assert bytes(r[FONT_START:FONT_START+FONT_SIZE]) == source_font(), 'Incorrect original phase masks'
    world=bytearray(r[0xE000:0xE800])
    cloud_rows=set()
    for owner in range(r[L['bonus_cloud_count']]):
        height=r[L['bonus_cloud_hlo']+owner]+256*r[L['bonus_cloud_hhi']+owner]
        cloud_row=(height//8+2)&63
        assert cloud_row not in cloud_rows, ('Cloud rows overlap',owner,cloud_row)
        cloud_rows.add(cloud_row)
        x=r[L['bonus_cloud_x']+owner]
        phase=x&7
        roles=(0,1)+(2,)*(r[L['bonus_cloud_width']+owner]//8-3)+(3,4)
        expected=bytearray([255])*32
        for offset,role in enumerate(roles):
            expected[(x//8+offset)&31]=128+5*phase+role
        address=cloud_row*32
        actual=world[address:address+32]
        assert actual==expected, ('Wrong source phase/roles',owner,x,actual.hex(),expected.hex())
        for column,code in enumerate(actual):
            if code!=255:
                encoded_phase,role=divmod(code-128,5)
                assert encoded_phase==phase and 0<=role<5
                glyph_address=0x4800+code*8
                assert bytes(r[glyph_address:glyph_address+8])==source_phase(phase)[role*8:role*8+8]
                # The source geometry is unchanged; only each character's
                # name differs from the original per-cloud allocation.
                world[address+column]=228+5*owner+role
    assert not any(128<=code<168 for code in world), 'Shared cloud code outside its owned row'
    height=r[L['bonus_cloud_hlo']+slot]+256*r[L['bonus_cloud_hhi']+slot]
    row=(height//8+2)&63
    return dict(world=digest(world), colours=digest(r[0xF000:0xF800]),
                row=bytes(world[row*32:row*32+32]).hex(),
                kinds=bytes(r[L['ROW_KIND']:L['ROW_KIND']+64]).hex(),
                same2=bytes(r[L['SAME2']:L['SAME2']+64]).hex())


def main():
    fixture=BASE/'tools/fixtures/bonus_cloud_tiles_reference.json'
    fixture_before=fixture.read_bytes()
    m=PlanningMachine();r,L=m.ram,m.labels
    cases=json.loads(fixture_before)['cases']
    previous=None
    for i,case in enumerate(cases):
        if previous!=case['mountain']:
            r[L['mountain']]=case['mountain'];m.call('enter_bonus')
            previous=case['mountain'];original=bytes(r)
        r[:]=original
        slot=case['slot']
        r[L['PATCH_FLAG']:L['PATCH_FLAG']+64]=bytes(64)
        r[L['bonus_cloud_x']+slot]=case['x']
        r[L['bonus_cloud_width']+slot]=case['width']
        world_before=bytes(r[0xE000:0xE800])
        m.x=slot;m.call('bonus_cloud_paint')
        actual=result(m,slot)
        height=r[L['bonus_cloud_hlo']+slot]+256*r[L['bonus_cloud_hhi']+slot]
        row=(height//8+2)&63
        # Patch history predates this operation. Reset it explicitly and
        # check the one required character-row flag with an independent
        # oracle rather than retaining the old fixture's discovery history.
        flags=bytes(r[L['PATCH_FLAG']:L['PATCH_FLAG']+64])
        assert flags[row] in (1,5) and not any(flags[:row]+flags[row+1:]),(i,'patch flags',flags)
        low,high=r[L['PATCH_LO']+row],r[L['PATCH_HI']+row]
        if flags[row]&4:
            assert low>high,(i,'wrapped patch interval',low,high)
            covered=set(range(low,32))|set(range(high+1))
        else:
            assert low<=high,(i,'linear patch interval',low,high)
            covered=set(range(low,high+1))
        changed={column for column in range(32)
                 if world_before[row*32+column]!=r[0xE000+row*32+column]}
        assert changed<=covered,(i,'patch missed changed cells',changed-covered)
        expected={k:v for k,v in case['expected'].items() if k!='patches'}
        assert actual==expected,(i,case,actual)
    assert fixture.read_bytes()==fixture_before, 'Legacy golden was modified'
    print('PASS bonus cloud tiles:',len(cases),
          'unchanged legacy cache/colour/kind/SAME2 cases; shared IDs normalize with exact source masks')


if __name__=='__main__':main()
