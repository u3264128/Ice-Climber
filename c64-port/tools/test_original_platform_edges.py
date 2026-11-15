"""Compare platform edges and moving-cloud landings with the NES routines."""
import argparse
import hashlib
import itertools
import json

from original_player_reference import PlayerReference
from extract_levels import generate
from test_game import BASE, Machine, start
from test_original_player_input import compare, target_tick
from test_original_physics import PRG, Reference


def packed(value):
    return 0 if value == 255 else 2 if value == 4 else 1 if value == 1 else 3


def source_band_to_packed(band):
    return (5-band//2)*16 if band in (2,4,6,8) else 0


def check_full_edges(quick=False):
    source, target = PlayerReference(), Machine()
    r,a,L = source.ram,target.ram,target.labels
    a[L['state']],a[L['player_count']]=1,1
    source_image,target_image = bytes(r),bytes(a)
    cases,ticks,landings,misses = 0,0,0,0
    patterns = ((1,255,255),(4,255,255),(4,1,255),(4,255,1))
    floors = (1,) if quick else (1,4,5,7)
    base=itertools.product(floors,patterns,range(84,106),(0,1,2),(0,24))
    configs=((floor,pattern,x,direction,run,(0,128,255)[i%3],(0,128)[i%2],
              (4,6,8)[(i//2)%3],(0,2)[(i//3)%2])
             for i,(floor,pattern,x,direction,run) in enumerate(base))
    for floor,pattern,x,direction,run,xfrac,yfrac,handler,offset in configs:
        r[:],a[:] = source_image,target_image
        camera = min(floor-1,5)
        row = floor-camera
        py = 216-48*row-offset
        r[0x400:0x4D8] = r[0x500:0x5D8] = bytes([255])*216
        a[L['floor_upper']:L['floor_upper']+216] = bytes(216)
        a[L['floor_lower']:L['floor_lower']+216] = bytes(216)
        a[L['floor_types']:L['floor_types']+9] = bytes(9)
        r[0x400+24*(floor-1):0x400+24*floor] = bytes([1])*24
        a[L['floor_upper']+24*(floor-1):L['floor_upper']+24*floor] = bytes([1])*24
        for column,value in zip((8,7,9),pattern):
            r[0x400+24*floor+column] = value
            a[L['floor_upper']+24*floor+column] = packed(value)
        face = int(direction==2)
        r[0x90],r[0x5A],r[0x66],r[0x64] = camera+4,floor+1,py-24,x
        r[0x6A],r[0x68],r[0x6E],r[0x62],r[0x60] = handler,direction,run,1-face,11
        r[0xE0],r[0x86],r[0x88],r[0xE6],r[0xE8],r[0xEA],r[0x72] = 1,1,0,4,0,yfrac,xfrac
        a[L['pxlo']:L['pxhi']+1] = (x+52).to_bytes(2,'little')
        for name,value in (('curfloor',floor-1),('maxfloor',floor-1),('cam',camera),
                           ('py',py),('prevpy',py),('onground',0),('move_dir',direction),
                           ('walk_time',run),('face',face),('air_init',0x8C),
                           ('fall_int',4),('fall_frac',0),('y_frac',yfrac),('air_xfrac',xfrac)):
            a[L[name]] = value
        rise = (3,168) if handler==4 else (0,240 if handler==6 else 176)
        r[0xE4],r[0xE2] = rise
        a[L['rise_int']],a[L['rise_frac']] = rise
        outcome = False
        for tick in range(8):
            source.tick(direction)
            target_tick(target,direction)
            expected = (r[0x64],r[0x66],r[0x6A] in (1,3),r[0x68],r[0x6E],r[0xE6],r[0xE8],r[0xEA],r[0x72])
            actual = ((int.from_bytes(a[L['pxlo']:L['pxhi']+1],'little')-52)&255,
                      a[L['py']]-24,bool(a[L['onground']]),a[L['move_dir']],a[L['walk_time']],
                      a[L['fall_int']],a[L['fall_frac']],a[L['y_frac']],a[L['air_xfrac']])
            context = (floor,pattern,x,direction,run,xfrac,yfrac,handler,offset,tick+1)
            assert actual==expected,('full edge trajectory',context,actual,expected,
                                      'sourcefloor/band',r[0x5A],r[0x88],hex(a[L['air_init']]))
            if not a[L['onground']]:
                assert a[L['air_init']]&0x70==source_band_to_packed(r[0x88]),('edge band latch',context,r[0x88],hex(a[L['air_init']]))
            else:
                assert a[L['curfloor']]+1==r[0x5A],('landed world floor',context)
                outcome = True
            ticks += 1
        cases += 1
        landings += int(outcome)
        misses += int(not outcome)
        if cases%256==0:
            print(f'PASS edge trajectories {cases} cases / {ticks} frames',flush=True)
    return dict(cases=cases,frames=ticks,landings=landings,misses=misses)


def check_band_flags():
    source,target=Reference(),Machine()
    r,a,L=source.ram,target.ram,target.labels
    a[L['floor_types']:L['floor_types']+9]=bytes(9)
    r[0x500:0x5D8]=bytes([255])*216
    a[L['floor_lower']:L['floor_lower']+216]=bytes(216)
    cases=0
    xs=tuple(range(87,99))+(0,1,202,203,204,205,246,247,248,249,250,251,252,253,254,255)
    for raw,neighbour in ((1,255),(4,255),(4,1)):
        r[0x400:0x4D8]=bytes([255])*216
        a[L['floor_upper']:L['floor_upper']+216]=bytes(216)
        r[0x420],r[0x41F]=raw,neighbour
        a[L['floor_upper']+32],a[L['floor_upper']+31]=packed(raw),packed(neighbour)
        for x,delta,gravity,handler,oldband in itertools.product(xs,(-1,0,1,2,6,7,8),
                ((0,0),(1,255),(2,0),(2,191),(2,192),(3,0),(7,255)),(4,6,8),(0,6,8)):
            r[0x64],r[0x66],r[0x5A],r[0x6A],r[0x88]=x,144+delta,2,handler,oldband
            r[0xE6],r[0xE8]=gravity
            a[L['pxlo']:L['pxhi']+1]=(x+52).to_bytes(2,'little')
            for name,value in (('cam',0),('curfloor',0),('maxfloor',0),('py',168+delta),
                               ('prevpy',167+delta),('onground',0),('move_dir',0),
                               ('fall_int',gravity[0]),('fall_frac',gravity[1]),
                               ('rise_int',3 if handler==4 else 0),
                               ('rise_frac',168 if handler==4 else 240 if handler==6 else 176),
                               ('air_init',0x8C|source_band_to_packed(oldband))):
                a[L[name]]=value
            source.call(0xCF1A)
            expected=bool(source.c)
            target.call('land_check')
            context=(raw,neighbour,x,delta,gravity,handler,oldband)
            assert bool(a[L['onground']])==expected,('CF1A edge decision',context,a[L['onground']],expected)
            if expected:
                assert a[L['py']]==168 and a[L['air_init']]==0
            else:
                assert a[L['air_init']]&0x70==source_band_to_packed(r[0x88]),('CF1A latch',context,r[0x88],hex(a[L['air_init']]))
                assert a[L['air_init']]&0x8F==0x8C,'Band bookkeeping must preserve age and head flag'
            cases+=1
    return cases


def check_cloud_probe_order():
    source,target=Reference(),Machine()
    r,a,L=source.ram,target.ram,target.labels
    cases=0
    for floor,raw,motion,cloud_dir in itertools.product((1,5),(255,1,4),
            ((1,0),(4,1),(4,2),(8,1),(8,2)),(0,1)):
        handler,direction=motion
        r[0x400:0x4D8]=bytes([255])*216
        a[L['floor_upper']:L['floor_upper']+216]=bytes(216)
        if raw==1:
            r[0x400+24*floor:0x400+24*(floor+1)]=bytes([1])*24
            a[L['floor_upper']+24*floor:L['floor_upper']+24*(floor+1)]=bytes([1])*24
        elif raw==4:
            r[0x400+24*floor+8]=4
            a[L['floor_upper']+24*floor+8]=2
        r[0x5A],r[0x6A],r[0x68],r[0x786],r[0x787],r[0x7D7]=floor+1,handler,direction,floor+1,0,cloud_dir
        r[0x788],r[0x78A],r[0x78C],r[0x78E]=80,106,200,228
        a[L['floor_types']:L['floor_types']+9]=bytes(9)
        a[L['floor_types']+floor]=96
        a[L['cam']],a[L['onground']],a[L['move_dir']]=floor-1,int(handler==1),direction
        a[L['rise_int']]=0 if handler==8 else 3
        for slot,left in ((floor,80),(floor+8,200)):
            a[L['cloud_x']+slot],a[L['cloud_subpixel']+slot],a[L['cloud_dir']+slot]=4+left//8,left%8,cloud_dir
        for x in range(256):
            r[0x64]=x
            source.call(0xCD62)
            expected=2 if source.c and r[0x783]<128 else 1 if source.c else 0
            a[L['pxlo']:L['pxhi']+1]=(x+52).to_bytes(2,'little')
            target.call('support_at',1)
            actual=a[L['supflag']]
            assert actual==expected,('source foot/cloud probe order',floor,raw,handler,direction,cloud_dir,x,actual,expected)
            cases+=1
    return cases


def check_wall_head_contacts():
    """Test the tapered walls in the source terrain, including the underside."""
    source, target = Reference(), Machine()
    r, a, labels = source.ram, target.ram, target.labels
    blank = 255                  # gameplay BLANK character
    contacts = 0
    for mountain in range(32):
        raw, cells, _, _ = generate(PRG, mountain)
        r[0x400:0x4D8], r[0x500:0x5D8] = raw[:216], raw[216:]
        for layer, plane in enumerate(('floor_upper', 'floor_lower')):
            a[labels[plane]:labels[plane]+216] = cells[layer*216:(layer+1)*216]
            a[labels['break_layer']] = layer
            for floor in range(9):
                # The fixed map spans X32..223. The mountain walls taper
                # inward from X32 to X40 and X48 at higher floors.
                camera = min(floor, 5)
                r[0x5A] = floor+1
                a[labels['cam']], a[labels['rowidx']] = camera, floor-camera
                columns = (*range(3, 7), *range(25, 29))
                for column in columns:
                    a[labels['coltmp']] = column+4
                    source.call(0xDBB0 if layer else 0xDBB4, column*8)
                    target.call('get_char')
                    assert (target.a != blank) == (source.a < 128), (
                        'tapered wall head contact', mountain+1, floor+1,
                        layer, column*8, target.a, source.a)
                    contacts += 1
    return contacts


def check_real_wall_jumps():
    """Start a normal jump under the widened rock shelf on mountain 1."""
    cases = ((22, 1), (24, 0), (210, 2), (214, 0))
    frames = 0
    for x, direction in cases:
        source, target = PlayerReference(), Machine()
        r, a, labels = source.ram, target.ram, target.labels
        _, cells, _, _ = generate(PRG, 0)
        a[labels['floor_upper']:labels['floor_upper']+216] = cells[:216]
        a[labels['floor_lower']:labels['floor_lower']+216] = cells[216:]
        r[0x5A], r[0x64], r[0x66], r[0x62] = 2, x, 144, int(direction != 2)
        for name, value in dict(state=1, player_count=1, curfloor=1, maxfloor=1,
                                py=168, prevpy=168, onground=1,
                                face=int(direction == 2)).items():
            a[labels[name]] = value
        a[labels['pxlo']:labels['pxhi']+1] = (x+52).to_bytes(2, 'little')
        for tick in range(24):
            pad = direction | (128 if tick == 0 else 0)
            source.tick(pad)
            target_tick(target, pad)
            compare(source, target, ('real mountain wall jump', x, direction, tick+1))
            frames += 1
    return dict(cases=len(cases), frames=frames)


def check_real_ledge_edges():
    """Full first-floor jumps into the natural Mountain 02 ice ledges."""
    cases = ((83, 2, 73, True), (84, 2, 74, False),
             (157, 1, 167, True), (156, 1, 166, False))
    for x, direction, contact_x, landed in cases:
        source, target = PlayerReference(1), start(mountain=2)
        r, a, labels = source.ram, target.ram, target.labels
        r[0x64] = x
        a[labels['pxlo']:labels['pxhi']+1] = (x+52).to_bytes(2, 'little')
        a[labels['logic_phase']] = 0
        raw, cells = bytes(r[0x400:0x600]), bytes(a[0x400:0x600])
        for frame in range(30):
            pad = direction | (128 if frame == 0 else 0)
            source.tick(pad)
            if frame % 5 == 4:
                source.tick(pad)
            joy = (0xF7 if direction == 1 else 0xFB) & (0xFE if frame == 0 else 255)
            target.frame(joy)
            compare(source, target, ('real ice ledge', x, direction, frame+1))
        # The upper ice ends at X79 on the left and starts at X176 on
        # the right. At logic tick36 exactly one foot makes the catch.
        assert r[0x64] == contact_x and (r[0x6A] == 3) == landed
        assert (a[labels['curfloor']] == 1) == landed
        assert bytes(r[0x400:0x600]) == raw and bytes(a[0x400:0x600]) == cells
    return dict(cases=len(cases), pal_frames=30*len(cases),
                compared_logic_ticks=36*len(cases), one_pixel_catches=2, one_pixel_misses=2)


def check_moving_cloud_jumps():
    """Run the real PAL frame at both edges of active moving clouds."""
    cases = frames = ticks = 0
    for mountain, floor, camera, prior_ticks, motion in (
            (1, 3, 1, 244, -1), (2, 1, 0, 209, 1)):
        source, target = PlayerReference(mountain), start(mountain=mountain+1)
        r, a, labels = source.ram, target.ram, target.labels
        r[0x5A] = 0             # advance the real cloud without a rider
        source.call(0xE4C2)
        target.call('normal_cloud_init')
        for _ in range(prior_ticks):
            source.call(0xE29A)
            target.call('cloud_update')
        assert r[0x786] == floor+1
        edge_x = (r[0x78E]-1 if motion < 0 else r[0x788])-9
        outward = 1 if motion < 0 else 2
        toward_edge = -motion
        screen_y = 216-48*(floor-camera)
        source_base, target_base = bytes(r), bytes(a)
        scenarios = (
            ('land', edge_x, 0, True, 1, 1),
            ('land and ride', edge_x, 0, True, 2, 1),
            ('ride', edge_x, 0, False, 2, 1),
            ('walk to edge', edge_x-toward_edge, outward, False, 1, 1),
            ('walk off edge', edge_x, outward, False, 1, 2),
            ('jump from edge', edge_x, 128, False, 2, 4),
            ('directional jump', edge_x-14*toward_edge, 128|outward, False, 1, 4),
            ('directional jump after stepping off', edge_x-3*toward_edge,
             128|outward, False, 1, 2),
        )
        for name, x, pad, airborne, tick_count, handler in scenarios:
            r[:], a[:] = source_base, target_base
            r[0x90], r[0x5A], r[0x66], r[0x64] = camera+4, floor+1, screen_y-24, x
            r[0x6A] = 4 if airborne else 1
            a[labels['pxlo']:labels['pxhi']+1] = (x+52).to_bytes(2, 'little')
            for field, value in dict(cam=camera, py=screen_y, prevpy=screen_y,
                                     curfloor=floor-int(airborne), maxfloor=floor,
                                     onground=int(not airborne), invul_t=120,
                                     logic_phase=4 if tick_count == 2 else 0).items():
                a[labels[field]] = value
            if airborne:
                r[0xE0], r[0x86], r[0x60] = 1, 1, 11
                r[0xE6], r[0xE4], r[0xE2], r[0xEA] = 4, 3, 168, 200
                for field, value in dict(air_init=0x8C, fall_int=4, rise_int=3,
                                         rise_frac=168, y_frac=200).items():
                    a[labels[field]] = value
            for _ in range(tick_count):
                source.tick(pad)
                source.call(0xE29A)
            joy = 255
            for button, bit in ((128, 1), (1, 8), (2, 4)):
                if pad & button:
                    joy &= 255-bit
            before = a[labels['logic_frame']]
            target.frame(joy)
            context = ('moving cloud', mountain+1, name, x)
            assert r[0x6A] == handler, (context, 'source handler', r[0x6A], handler)
            assert ((a[labels['logic_frame']]-before)&255) == tick_count, context
            compare(source, target, context)
            for slot, address in ((floor, 0x788), (floor+8, 0x78C)):
                left = (a[labels['cloud_x']+slot]-4)*8+a[labels['cloud_subpixel']+slot]
                assert left == r[address], (context, 'cloud position', left, r[address])
            cases += 1
            frames += 1
            ticks += tick_count
    return dict(cases=cases, pal_frames=frames, compared_logic_ticks=ticks)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--quick',action='store_true')
    parser.add_argument('--part',choices=('all','edges','bands','clouds','walls','ledges','moving'),default='all')
    args=parser.parse_args()
    report=dict(status='passed',quick=args.quick,
                source_calls=['CAED','CB9D','CD13','DA99','D1E5','CD62','CF1A',
                              'DBB0','DBB4','E4C2','E29A'],
                prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    if args.part in ('all','edges'):report['normal']=check_full_edges(args.quick)
    if args.part in ('all','bands'):report['band_cases']=check_band_flags()
    if args.part in ('all','clouds'):report['mixed_cloud_cases']=check_cloud_probe_order()
    if args.part in ('all','walls'):
        report['wall_head_contacts'] = check_wall_head_contacts()
        report['real_wall_jumps'] = check_real_wall_jumps()
    if args.part in ('all','ledges'):
        report['real_ledge_edges'] = check_real_ledge_edges()
    if args.part in ('all','moving'):
        report['moving_cloud_jumps'] = check_moving_cloud_jumps()
    suffix='' if args.part=='all' else '_'+args.part
    (BASE/f'docs/verification/original_platform_edges{suffix}.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS original edge landing',args.part,report,flush=True)


if __name__=='__main__':
    main()
