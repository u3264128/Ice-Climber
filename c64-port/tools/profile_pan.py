#!/usr/bin/env python3
"""Non-invasive, inclusive native cycle profiles for actual normal pans."""
import hashlib
import argparse
import json
import struct
from collections import defaultdict

from vice_session import ViceSession,BASE
from verify_mux_timing import registers


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mountain',type=int,default=1)
    parser.add_argument('--players',type=int,choices=(1,2),default=2)
    parser.add_argument('--tag',default='normal')
    args=parser.parse_args()
    output=[]
    image=BASE/'c64/build/iceclimber_game.prg'
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    with ViceSession('pan_routine_profile') as s:
        s.write('selected_mountain',args.mountain)
        if args.players==2:s.frame(0xFD);s.frame()
        s.frame(0xEF);s.finish_preview()
        for _ in range(8):s.frame() #finish idle next-row prefetch before climbing
        for base,x,y,floor in ((0x200,70,72,3),(0x220,220,216,0)):
            for offset,value in ((3,x),(4,0),(5,y),(6,y),(7,floor),
                                 (8,1),(11,floor),(12,0),(13,0),(14,0),
                                 (20,0),(24,0),(25,0),(30,0)):
                s.write(base+offset,value)
        s.sync_player_zero()
        if args.players==1:
            for name,value in (('py',72),('prevpy',72),('curfloor',3),('onground',1),
                               ('maxfloor',3),('move_dir',0),('walk_time',0),
                               ('skid_t',0),('invul_t',120),('pxlo',100),('pxhi',0)):
                s.write(name,value)
        if args.mountain!=1:s.write('normal_pan_request',1)
        entries={s.labels[name]:name for name in
            ('wait_frame','commit_view','commit_actors','commit_colours','commit_patches',
             'game_tick','sound_frame','view_tick','extra_tick','actors_prepare',
             'copy_setup','CACHE_COPY_RUN','schedule_actors','commit_clouds',
             'cloud_commit_slots','cloud_glyph_update','cloud_make_glyphs',
             'cloud_make_glyphs2','normal_pan_tick','play_tick','normal_condor_tick')
            if name in s.labels}
        checkpoints={s.labels['main_loop']}
        def checkpoint(pc):
            if pc in checkpoints:return
            checkpoints.add(pc)
            s.m.command(0x12,struct.pack('<HHBBBB',pc,pc,1,1,4,0))
        for pc in entries:checkpoint(pc)
        s.write(0xDD0E,0);s.write(0xDD04,[255,255]);s.write(0xDD0E,17)
        active=defaultdict(list)
        for frame in range(20):
            samples=[]
            while True:
                s.m.resume();reg=registers(s.m);pc=reg['PC']
                timer=int.from_bytes(s.read(0xDD04,2),'little')
                # Match both address and stack depth, so IRQ/nested calls
                # cannot be mistaken for the original caller's return.
                matches=[value for value in active[pc] if value['sp']==reg['SP']]
                for value in matches:
                    active[pc].remove(value)
                    samples.append(dict(name=value['name'],cycles=(value['timer']-timer)&65535,
                        start_line=value['line'],end_line=reg['LIN']))
                if pc==s.labels['main_loop']:break
                if pc in entries:
                    sp=reg['SP'];stack=s.read(0x100+sp+1,2)
                    ret=(int.from_bytes(stack,'little')+1)&65535
                    checkpoint(ret)
                    active[ret].append(dict(name=entries[pc],timer=timer,line=reg['LIN'],sp=(sp+2)&255))
            output.append(dict(frame=frame,camera=int.from_bytes(s.read('visual_camera',2),'little'),
                pan=s.read('normal_pan_t')[0],calls=samples))
    totals=defaultdict(list)
    for frame in output:
        for sample in frame['calls']:totals[sample['name']].append(sample['cycles'])
    summary={name:dict(count=len(values),mean=round(sum(values)/len(values)),max=max(values),
                       min=min(values)) for name,values in totals.items()}
    assert hashlib.sha256(image.read_bytes()).hexdigest()==digest,'PRG changed during native profile'
    report=dict(prg_sha256=digest,
                inclusive_cycles=True,routines=summary,frames=output)
    (BASE/f'build_dbg/pan_profile_{args.tag}.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
