"""Both setup halves reproduce the full self-modifying copy template."""
from plan_mountains import PlanningMachine,clone


def dirty_copy_init(m, case):
    """Unused command bytes are arbitrary; only the header/STAs are static."""
    r,L=m.ram,m.labels
    base=L['CACHE_COPY']
    size=8+2*25*6+3
    priority=L['__PRIOCODE_RUN__']
    preserved=bytes(r[priority:priority+L['__PRIOCODE_SIZE__']])
    r[base:base+size]=bytes((i*37+case)&255 for i in range(size))
    m.call('view_init')
    assert bytes(r[base:base+8])==bytes.fromhex('a2 20 ca e0 ff d0 01 60')
    for slot in range(25):
        assert r[base+8+slot*6+3]==0x9D,('missing body STA',case,slot)
        assert r[base+8+25*6+slot*6+3]==0x9D,('missing colour STA',case,slot)
    assert bytes(r[priority:priority+L['__PRIOCODE_SIZE__']])==preserved


def check_copy(m,row,bank,back,context):
    r,L=m.ram,m.labels
    destination=0x4000+(bank^1)*1024
    colour=L['COLOUR_BACK']
    r[destination:destination+1000]=bytes([0xA5])*1000
    r[colour:colour+1000]=bytes([0xB6])*1000
    if back!=255:
        for sy in range(25):
            crow=(back+24-sy)&63
            r[destination+sy*40+4:destination+sy*40+36]=r[0xE000+crow*32:0xE000+crow*32+32]
    expected=[]
    expected_colours=[]
    for sy in range(25):
        crow=(row+24-sy)&63
        expected.append(bytes(r[0xE000+crow*32:0xE000+crow*32+32]))
        if r[L['ROW_KIND']+crow]==2:  # ROW_FULL
            expected_colours.append((sy,bytes(r[0xF000+crow*32:0xF000+crow*32+32])))
    # Execute the generated code, checking every copied byte independently
    # of the setup implementation and preserving all40-byte row strides.
    m.x=255
    m.call('CACHE_COPY_RUN',31)
    for sy,data in enumerate(expected):
        assert r[destination+sy*40+4:destination+sy*40+36]==data,(context,'characters',sy)
        assert r[destination+sy*40:destination+sy*40+4]==bytes([0xA5])*4,(context,'left margin',sy)
        assert r[destination+sy*40+36:destination+sy*40+40]==bytes([0xA5])*4,(context,'right margin',sy)
    for sy,data in expected_colours:
        assert r[colour+sy*40+4:colour+sy*40+36]==data,(context,'colours',sy)


def main():
    m=PlanningMachine();r,L=m.ram,m.labels
    cases=0
    for mountain in range(1,9):
        r[L['mountain']]=mountain
        m.call('enter_bonus')
        assert 2 not in r[L['ROW_KIND']:L['ROW_KIND']+64], 'Split setup requires constant bonus colours'
        for row in (0,1,3,5,11,20,30,40):
            for bank in (0,1):
                for back in (255,(row-2)&255):
                    dirty_copy_init(m,cases)
                    r[L['copy_target_row']]=row
                    r[L['screen_buffer']]=bank
                    r[L['back_view']]=back
                    original=bytes(r)
                    m.call('copy_setup')
                    expected=bytes(r[L['CACHE_COPY']:L['CACHE_COPY']+512])
                    r[:]=original
                    m.call('bonus_copy_setup_first')
                    assert r[L['copy_row']]==12 and r[L['copy_setup_stop']]==12
                    # Actual logic, patches and sprites use these work bytes
                    # between the two PAL frames. None may be assumed saved.
                    for name in ('copy_row','copy_crow','byteidx','tmp','skip_rows',
                                 'work_lo','work_hi','work2'):
                        r[L[name]]=0xA5
                    m.call('bonus_copy_setup_second')
                    actual=bytes(r[L['CACHE_COPY']:L['CACHE_COPY']+512])
                    assert actual==expected,(mountain,row,bank,back)
                    assert r[L['copy_row']]==25 and r[L['copy_setup_stop']]==25
                    check_copy(m,row,bank,back,('bonus',mountain,row,bank,back))
                    cases+=1
    normal=0
    for mountain in range(1,33):
        r[L['mountain']]=mountain
        m.call('setup_level')
        m.call('cache_normal')
        for row in (0,4,11,20,30):
            for bank in (0,1):
                for back in (255,(row-2)&255):
                    dirty_copy_init(m,cases+normal)
                    r[L['copy_target_row']]=row
                    r[L['screen_buffer']]=bank
                    r[L['back_view']]=back
                    m.call('copy_setup')
                    check_copy(m,row,bank,back,('normal',mountain,row,bank,back))
                    normal+=1
    print('PASS packed/split copy template:',cases,'bonus half/full cases;',normal,
          'normal character/colour execution oracles, dirty311-byte commands and preserved priority code',flush=True)


if __name__=='__main__':main()
