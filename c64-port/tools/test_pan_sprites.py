"""Compare frozen normal-pan OAM with the executed original pan handler."""
import hashlib
import json

from original_player_reference import PlayerReference
from test_game import BASE,start


def logical(r,L):
    n=r[L['logical_count']]
    return [dict(x=r[0xE800+i],hi=r[0xE820+i],y=r[0xE840+i],
                 ptr=r[0xE860+i],col=r[0xE880+i],mc=r[0xE8A0+i],
                 group=r[0xE8E0+i]) for i in range(n)]


def main():
    original=PlayerReference();o=original.ram
    o[0x400:0x4D8]=bytes([1])*216;o[0x500:0x5D8]=bytes([255])*216
    for address,value in ((0x55,1),(0x58,1),(0x90,4),(0x5A,4),(0x6A,1),
                          (0x64,96),(0x66,48),(0x68,1),(0x8D,255),(0x7A,2),
                          (0x3D,128),(0x2C,1),
                          (0x20,3),(0x5B,1),(0x6B,1),(0x65,152),(0x67,192),(0x21,3)):
        o[address]=value
    o[0x5F]=1;original.call(0xD17C,y=0)
    o[0x5F]=0;original.call(0xD17C,y=0)
    source_body={base:bytes(o[base:base+24]) for base in (0x200,0x224)}
    original.call(0xD7DE)
    assert o[0x8B]==o[0x8C]==12,'Source pan fixture did not arm'
    m=start(2);r,L=m.ram,m.labels
    for name,value in (('cam',0),('normal_pan_t',0),('pxlo',148),('pxhi',0),
                       ('py',72),('prevpy',72),('curfloor',3),('maxfloor',3),
                       ('onground',1),('move_dir',1),('hammer_t',0),('invul_t',0)):
        r[L[name]]=value
    r[L['visual_camera']:L['visual_camera']+2]=bytes(2)
    r[L['normal_camera']:L['normal_camera']+2]=bytes(2)
    m.call('context_store')
    r[0x225]=r[0x226]=216;r[0x227]=0;r[0x228]=1;r[0x239]=0
    m.call('normal_pan_try');m.call('actors_prepare')
    baseline=logical(r,L)
    samples=0
    for tick in range(1,12):
        original.pad=129
        original.call(0xCAED);original.call(0xCB9D);original.call(0xCBFB)
        for base,initial in source_body.items():
            for i in range(6):
                expected_y=initial[4*i]
                for _ in range(tick):
                    expected_y=248 if expected_y>=242 else expected_y+4
                assert o[base+4*i]==expected_y, \
                    ('Source OAM Y',tick,hex(base),i,o[base+4*i],initial[4*i])
                assert bytes(o[base+4*i+1:base+4*i+4])==initial[4*i+1:4*i+4], \
                    ('Source changed pose during frozen pan',tick,base,i)
        m.call('normal_pan_step')
        r[L['visual_camera']]=4*tick
        r[L['logic_frame']]=(r[L['logic_frame']]+1)&255
        r[L['frame']]=(r[L['frame']]+1)&255
        m.call('actors_prepare')
        expected=[dict(sprite,y=sprite['y']+4*tick) for sprite in baseline
                  if sprite['y']+4*tick<247]
        assert logical(r,L)==expected,('C64 changed frozen OAM',tick,logical(r,L),expected)
        samples+=len(expected)
    r[L['normal_pan_t']]=0;m.call('actors_prepare')
    assert r[L['actors_pan_active']]==0,'Pan rendercache survived resumed handlers'
    report=dict(status='passed',prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                frozen_logic_ticks=11,original_player_oam_samples=11*12,
                c64_sprite_samples=samples,poses_frozen=True,bottom_clipped=True)
    (BASE/'docs/verification/pan_sprites.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS executed original frozen pan OAM, C64 shift/clip and cache exit')


if __name__=='__main__':main()
