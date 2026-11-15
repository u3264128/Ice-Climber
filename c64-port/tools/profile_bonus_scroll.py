"""Non-invasive inclusive native profile of the dense two-player bonus view."""
import argparse
import hashlib
import json
import struct
from collections import defaultdict

from vice_session import ViceSession,BASE
from verify_mux_timing import registers


def configure(s,n,maximum=256,start=240):
    s.write('bonus_camera',min(start+2*n,maximum).to_bytes(2,'little'))
    s.write('fruit_mask',15);s.write('bonus_out',[0,0])
    for base,x,y in ((0x200,120,140),(0x220,240,150)):
        for offset,value in ((3,x&255),(4,x>>8),(5,y),(6,y),(8,0),
                             (12,0),(13,0),(14,12),(15,3),(16,8),
                             (17,240),(18,3),(19,168),(20,0),(21,0),
                             (24,0),(25,0),(30,0)):
            s.write(base+offset,value)
    for name,value in (('pxlo',120),('pxhi',0),('py',140),('prevpy',140),
                       ('onground',0),('hammer_t',0),('attack_t',0),
                       ('air_init',12),('fall_int',3),('fall_frac',8),
                       ('y_frac',240),('rise_int',3),('rise_frac',168),
                       ('move_dir',0),('walk_time',0),('skid_t',0),
                       ('invul_t',0)):
        s.write(name,value)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tag',default='baseline')
    parser.add_argument('--players',type=int,choices=(1,2),default=2)
    parser.add_argument('--max-camera',type=int,default=256)
    parser.add_argument('--start-camera',type=int,default=240)
    parser.add_argument('--mountain',type=int,default=1)
    args=parser.parse_args()
    image=BASE/'c64/build/iceclimber_game.prg'
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    output=[]
    with ViceSession('bonus_scroll_routine_profile') as s:
        s.write('selected_mountain',args.mountain)
        if args.players==2:s.frame(0xFD);s.frame()
        s.frame(0xEF);s.finish_preview()
        s.write('bonus_requested',1);s.frame()
        s.write('paused',1);s.write('bonus_camera',args.start_camera.to_bytes(2,'little'))
        for _ in range(130):s.frame()
        s.write('paused',0)
        names=('wait_frame','commit_view','commit_actors','commit_colours','commit_patches',
               'game_tick','bonus_player_tick','bonus_world_tick','bonus_find_support',
               'bonus_cloud_paint','bonus_cloud_paint_ready','sound_frame','view_tick','extra_tick',
               'actors_prepare','copy_setup','bonus_copy_setup_first','bonus_copy_setup_second',
               'CACHE_COPY_RUN','schedule_actors','bonus_sort_try','bonus_sort_validate','bonus_sort_save',
               'commit_clouds','context_load','context_store','bonus_collect','bonus_side_bounds')
        entries={s.labels[name]:name for name in names if name in s.labels}
        checkpoints={s.labels['main_loop']}
        def checkpoint(pc):
            if pc in checkpoints:return
            checkpoints.add(pc)
            s.m.command(0x12,struct.pack('<HHBBBB',pc,pc,1,1,4,0))
        for pc in entries:checkpoint(pc)
        s.write(0xDD0E,0);s.write(0xDD04,[255,255]);s.write(0xDD0E,17)
        active=defaultdict(list)
        for frame in range(24):
            # DisplayTrace first configures camera0 before sampling, then
            # repeats callback0 at the first completed main loop. Mirror
            # that exact input timing, including its one initial repeat.
            configure(s,max(frame-1,0),args.max_camera,args.start_camera)
            samples=[]
            while True:
                s.m.resume();reg=registers(s.m);pc=reg['PC']
                timer=int.from_bytes(s.read(0xDD04,2),'little')
                matches=[value for value in active[pc] if value['sp']==reg['SP']]
                for value in matches:
                    active[pc].remove(value)
                    samples.append(dict(name=value['name'],cycles=(value['timer']-timer)&65535,
                                        start_line=value['line'],start_cycle=value['cycle'],
                                        end_line=reg['LIN'],end_cycle=reg['CYC']))
                if pc==s.labels['main_loop']:break
                if pc in entries:
                    sp=reg['SP'];stack=s.read(0x100+sp+1,2)
                    ret=(int.from_bytes(stack,'little')+1)&65535
                    checkpoint(ret)
                    active[ret].append(dict(name=entries[pc],timer=timer,
                                           line=reg['LIN'],cycle=reg['CYC'],sp=(sp+2)&255))
            output.append(dict(frame=frame,camera=int.from_bytes(s.read('visual_camera',2),'little'),
                               logical=s.read('logical_count')[0],calls=samples))
    totals=defaultdict(list)
    for frame in output:
        for sample in frame['calls']:totals[sample['name']].append(sample['cycles'])
    summary={name:dict(count=len(values),mean=round(sum(values)/len(values)),
                       max=max(values),min=min(values)) for name,values in totals.items()}
    assert hashlib.sha256(image.read_bytes()).hexdigest()==digest
    report=dict(prg_sha256=digest,players=args.players,mountain=args.mountain,controlled_camera_max=args.max_camera,
                inclusive_cycles=True,routines=summary,frames=output)
    report['input_schedule']='matches DisplayTrace main-loop callback (initial camera repeated)'
    (BASE/f'build_dbg/bonus_scroll_profile_{args.tag}.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
