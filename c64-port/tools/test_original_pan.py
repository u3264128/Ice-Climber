"""Execute the normal-stage D7DE/D82F pan and compare C64 frozen ticks."""
import argparse
import hashlib
import json

from original_player_reference import PlayerReference
from test_game import BASE,start
from transplant_objects import map_ram

NES_BIRD_TIMER=map_ram(0x4E)   # Nitpicker's slow timer, in normal RAM


def check_pan(source_only=False):
    reports=[]
    for players in (1,2):
        for timer_phase in (0,5,10):
            original=PlayerReference()
            r=original.ram
            r[0x400:0x4D8]=bytes([1])*216
            r[0x500:0x5D8]=bytes([255])*216
            for address,value in ((0x55,1),(0x58,players-1),(0x90,4),(0x5A,4),(0x6A,1),
                                  (0x64,96),(0x66,48),(0x68,1),(0x6E,24),(0x76,224),
                                  (0x72,144),(0xEA,85),(0xE6,4),(0xE8,5),
                                  (0xE4,3),(0xE2,168),(0x8D,255),(0x7A,2),
                                  (0x31,timer_phase),(0x32,7),(0x3D,128),(0x2C,1),(0x4E,88),(0x20,3)):
                r[address]=value
            if players==2:
                r[0x5B],r[0x6B],r[0x65],r[0x67],r[0x21]=1,1,152,192,3
                r[0x5F]=1
                original.call(0xD17C,y=0)
            r[0x5F]=0
            original.call(0xD17C,y=0)
            original.call(0xD7DE)
            assert (r[0x8B],r[0x8C],r[0x90],r[0x66],r[0x13])==(12,12,5,48,0)
            machine=None if source_only else start(mode=players)
            if machine:
                a,L=machine.ram,machine.labels
                a[L['floor_upper']:L['floor_upper']+216]=bytes([1])*216
                a[L['floor_lower']:L['floor_lower']+216]=bytes(216)
                a[L['floor_types']:L['floor_types']+9]=bytes(9)
                a[L['cam']]=a[L['normal_pan_t']]=0
                a[L['normal_camera']:L['normal_camera']+2]=bytes(2)
                a[L['timer_divider']],a[NES_BIRD_TIMER]=10-timer_phase,88
                a[L['bear_timer']:L['bear_timer']+2]=bytes([128,1])
                a[L['player_index']]=0
                for name,value in (('pxlo',148),('pxhi',0),('py',72),('prevpy',72),('curfloor',3),
                                   ('maxfloor',3),('onground',1),('move_dir',1),('walk_time',24),
                                   ('walk_frac',224),('air_xfrac',144),('y_frac',85),('fall_int',4),
                                   ('fall_frac',5),('rise_int',3),('rise_frac',168),('skid_t',7),('invul_t',0)):
                    a[L[name]]=value
                machine.call('context_store')
                if players==2:
                    a[L['PLAYER_STATES']+32+5]=a[L['PLAYER_STATES']+32+6]=216
                    a[L['PLAYER_STATES']+32+7]=0
                    a[L['PLAYER_STATES']+32+8]=1
                stable={name:a[L[name]] for name in ('pxlo','pxhi','move_dir','walk_time','walk_frac',
                        'air_xfrac','y_frac','fall_int','fall_frac','rise_int','rise_frac','attack_t','air_init')}
                machine.call('normal_pan_try')
                assert a[L['normal_pan_t']]==12 and a[L['cam']]==1
                assert a[L['normal_camera']]==0,'Trigger tick must not take the first pan step'
            trace=[]
            for tick in range(1,13):
                original.pad=129
                original.call(0xCAED)
                original.call(0xCB9D)
                original.call(0xCBFB)
                assert r[0x66]==48+4*tick and r[0x64]==96
                assert r[0x8B]==12-tick and bool(r[0x8C])==(tick<12)
                assert r[0x32]==max(7-tick,0)
                expected_lives=2 if players==2 and tick>=7 else 3
                if players==2:
                    assert r[0x21]==expected_lives
                    assert min(r[0x224+4*i] for i in range(6))==192+4*tick
                if machine:
                    machine.joystick=0xF6
                    machine.call('read_joy')
                    machine.call('game_tick')
                    assert {name:a[L[name]] for name in stable}==stable,('physics during pan',players,timer_phase,tick)
                    assert a[L['normal_pan_t']]==12-tick
                    camera=int.from_bytes(a[L['normal_camera']:L['normal_camera']+2],'little')
                    assert camera==4*tick
                    assert a[L['py']]-(48-camera)==r[0x66]+24
                    assert a[L['skid_t']]==r[0x32]
                    assert a[L['bear_timer']]==r[0x3D] and a[L['bear_timer']+1]==r[0x2C]
                    assert a[NES_BIRD_TIMER]==r[0x4E]   # original slow timer $4E
                    if players==2:
                        assert a[L['PLAYER_STATES']+32]==expected_lives
                        assert bool(a[L['normal_pan_dead']+1])==(tick>=7)
                        assert bool(a[L['player_hidden']+1])==(tick==12)
                trace.append(dict(tick=tick,camera=4*tick,body_y=r[0x66],skid_timer=r[0x32],
                                  second_player_lives=expected_lives if players==2 else None))
            assert r[0x15]&128==0,'Held UP must have consumed its edge during the pan'
            if machine:
                assert a[L['input_fire']]==0
                original.pad=129
                original.call(0xCAED);original.call(0xCB9D);original.call(0xCBFB)
                machine.joystick=0xF6
                machine.call('read_joy');machine.call('game_tick')
                assert a[L['onground']] and r[0x6A] in (1,3),'UP held through pan must not jump on resume'
                assert a[L['py']]-24==r[0x66]
                assert ((int.from_bytes(a[L['pxlo']:L['pxhi']+1],'little')-52)&255)==r[0x64]
                if players==2:
                    assert a[L['PLAYER_STATES']+32]==r[0x21]==2,'Pan death must not decrement a second life on resume'
            reports.append(dict(players=players,timer_phase=timer_phase,trace=trace))
    return reports


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-only',action='store_true');args=p.parse_args()
    report=dict(status='passed',cases=check_pan(args.source_only),normal_pan_logic_ticks=12,
                pixels_per_logic_tick=4,trigger_has_no_step=True,source_player_frozen=True,
                input_edges_consumed=True,second_player_death_tick=7)
    if not args.source_only:
        report['prg_sha256']=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
        (BASE/'docs/verification/original_normal_pan.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS original normal pan12x4, frozen players, generic timers and bottom death',flush=True)


if __name__=='__main__':main()
