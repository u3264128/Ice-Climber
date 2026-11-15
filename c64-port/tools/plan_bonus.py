"""Find real joystick routes through the eight original bonus variants.

Search skips video/SID work, then replays the selected input on the complete
PRG. It never changes a position, platform, timer, fruit or enemy state.
"""
import copy
import argparse
import concurrent.futures
import hashlib
import json
import time
from test_game import BASE, Machine, finish_opening


def clone(m):
    n=copy.copy(m)
    n.ram=m.ram.copy()
    n.under_io=m.under_io.copy()
    n.sid_events=[]
    n.hooks={0xDC00:n.port_a,0xDC01:n.port_b,0xD012:n.raster_read}
    return n


def fast_frame(m,joy):
    from plan_mountains import fast_frame as original_frame
    original_frame(m,joy)


def height(m):
    L=m.labels
    return 216+int.from_bytes(m.ram[L['bonus_camera']:L['bonus_camera']+2],'little')-m.ram[0x22]


def ground_frames(machine, joystick, count):
    """Advance one shared walking prefix, rejecting departure from support."""
    r,L=machine.ram,machine.labels
    for _ in range(count):
        fast_frame(machine,joystick)
        if r[0x18]!=3 or r[L['bonus_out']] or not r[0x1B]:return False
    return True


def flight(m,direction,air_direction=None,air_delay=0):
    n=clone(m);r,L=n.ram,n.labels;inputs=[]
    if air_direction is None:air_direction=direction
    airborne=False
    for _ in range(90):
        if not airborne:joy=direction & 0xFE
        elif air_delay:
            joy=255
            air_delay-=1
        else:joy=air_direction
        fast_frame(n,joy);inputs.append(joy)
        if r[0x18]==2:
            return (n,inputs) if r[L['bonus_winner']] else None
        if r[L['bonus_out']]:return None
        if not r[0x1B]:airborne=True
        if airborne and r[0x1B]:return n,inputs
    return None


def attempt(m,wait,direction,run,preparation=255,air_direction=None,brake=0,air_delay=0):
    n=clone(m);prefix=[]
    for count,joy in ((wait,preparation),(run,direction),(brake,255)):
        if not ground_frames(n,joy,count):return None
        prefix += [joy]*count
    result=flight(n,direction,air_direction,air_delay)
    if result is None:return None
    after,inputs=result
    return after,prefix+inputs


def jump_options(machine):
    """Try all coarse cloud phases before refining approach/brake timing.

    Waiting, running and braking prefixes execute once. Every airborne
    control choice clones that completed prefix instead of replaying it.
    """
    current=height(machine)
    tested=set()
    merged=[]
    for positioned in (False, True, 'fine'):
        fine=positioned=='fine'
        waits=range(0,513,4) if fine else (0,16,32,48,64,96,128,192,256,320,384,448,512)
        diverse=[];seen_landings=set()
        for wait in waits:
            options=[]
            preparations=(255,0xF7,0xFB) if positioned and wait else (255,)
            for preparation in preparations:
                prepared=clone(machine)
                if not ground_frames(prepared,preparation,wait):continue
                for direction in (255,0xF7,0xFB):
                    runs=(0,) if direction==255 else ((0,4,8,12,16,24,32,48) if fine else (0,6,12,24,36,48,64,96))
                    moving=clone(prepared);last_run=0
                    for run in runs:
                        if not ground_frames(moving,direction,run-last_run):break
                        last_run=run
                        braked=clone(moving);last_brake=0
                        for brake in ((0,2,4) if fine else (0,)):
                            if not ground_frames(braked,255,brake-last_brake):break
                            last_brake=brake
                            prefix=[preparation]*wait+[direction]*run+[255]*brake
                            airborne=(direction,255,0xF7,0xFB) if positioned else (direction,)
                            for air_direction in dict.fromkeys(airborne):
                                delays=(0,4,8) if fine and air_direction!=255 else (0,)
                                for delay in delays:
                                    key=(bytes(prefix),direction,air_direction,delay)
                                    if key in tested:continue
                                    tested.add(key)
                                    result=flight(braked,direction,air_direction,delay)
                                    if result is None:continue
                                    n,tail=result
                                    caught=n.ram[n.labels['bonus_winner']]
                                    if caught or height(n)>current:
                                        inputs=prefix+tail
                                        rank=(bool(caught),height(n),n.ram[n.labels['fruit_counts']],-len(inputs),-abs(n.ram[0x1E]-164))
                                        options.append((rank,n,inputs))
            for option in sorted(options,key=lambda value:value[0],reverse=True):
                rank,candidate,inputs=option
                r,L=candidate.ram,candidate.labels
                if r[L['bonus_winner']]:return [option]
                landing=(height(candidate),r[0x1E]//6,r[L['bonus_plat']])
                if landing in seen_landings:continue
                seen_landings.add(landing);diverse.append(option)
                if len(diverse)>=12:
                    if not THOROUGH:return diverse
                    break
        if diverse and not THOROUGH:return diverse
        merged+=diverse
    # --thorough: the landings of all three passes, coarse ones first.
    return merged


def normal_route(mountain, wait_seconds):
    deadline = time.monotonic()+wait_seconds
    while True:
        if mountain == 1:
            first = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())
            checksum = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
            if first.get('prg_sha256') == checksum and first.get('normal_verified'):
                return first['normal']
        try:
            fixture = json.loads((BASE/'tools/fixtures/mountain_routes.json').read_text())
        except json.JSONDecodeError:
            # Another planner may be publishing the next normal route.
            fixture = {'routes': []}
        route = next((entry for entry in fixture['routes'] if entry['mountain'] == mountain), None)
        if route is not None:
            return route['inputs']
        if time.monotonic() >= deadline:
            raise AssertionError(('No published legal normal route', mountain))
        time.sleep(10)


def require_prg(checksum):
    if checksum is not None:
        actual=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
        assert actual==checksum, 'Release changed during bonus route validation'


def replay_existing(route, checksum=None):
    """Revalidate an established input tuple after an unrelated PRG change."""
    require_prg(checksum)
    machine=Machine()
    machine.ram[machine.labels['selected_mountain']]=route['mountain']
    machine.frame(0xEF)
    finish_opening(machine)     # the routes start after the mountain flyover
    for joystick in route['normal']:
        machine.frame(joystick)
    assert machine.ram[0x18]==3, ('Existing normal replay failed',route['mountain'])
    for joystick in route['bonus']:
        machine.frame(joystick)
    assert machine.ram[0x18]==2 and machine.ram[machine.labels['bonus_winner']]==1, \
        ('Existing bonus replay failed',route['mountain'])
    require_prg(checksum)
    return {**route,'normal_frames':len(route['normal']),'bonus_frames':len(route['bonus']),
            'fruit':machine.ram[machine.labels['fruit_counts']],
            'lives':machine.ram[0x19],'full_replay':True,'reused':True}


def search(mountain, max_steps=120, wait_seconds=0, checksum=None, resume=False):
    normal = normal_route(mountain, wait_seconds)
    require_prg(checksum)
    from plan_mountains import PlanningMachine
    m=PlanningMachine()
    m.ram[m.labels['selected_mountain']]=mountain  # menu selection before gameplay
    m.frame(0xEF);finish_opening(m)   # the routes start after the flyover
    for joy in normal:
        m.frame(joy)
    assert m.ram[0x18] == 3, ('Published normal route did not reach bonus', mountain)
    initial=clone(m)
    # Keep the established first-mountain route whenever its unchanged
    # input still succeeds, rather than perturbing the main regression.
    if mountain == 1:
        established = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())
        if normal == established['normal'] and established.get('bonus'):
            replay=clone(initial)
            for joy in established['bonus']:
                replay.frame(joy)
            if replay.ram[0x18] == 2 and replay.ram[replay.labels['bonus_winner']] == 1:
                require_prg(checksum)
                return dict(mountain=mountain, variant=(mountain-1)&7,
                            normal=normal, bonus=established['bonus'],
                            normal_frames=len(normal), bonus_frames=len(established['bonus']),
                            fruit=replay.ram[replay.labels['fruit_counts']],
                            lives=replay.ram[0x19], full_replay=True, reused=True)
    m.planning=True             # candidate search only; initial replay stays full PRG
    route=[]
    alternatives=[]
    checkpoint_dir=BASE/'build_dbg/bonus_search_checkpoints'
    checkpoint_dir.mkdir(parents=True,exist_ok=True)
    checkpoint_path=checkpoint_dir/f'{mountain:02}.json'
    release=checksum or hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    if resume and checkpoint_path.exists():
        checkpoint=json.loads(checkpoint_path.read_text())
        if checkpoint.get('prg_sha256')==release and checkpoint.get('normal')==normal:
            candidate=clone(m)
            for joy in checkpoint['bonus']:fast_frame(candidate,joy)
            if candidate.ram[0x18]==3 and candidate.ram[0x1B] and not candidate.ram[candidate.labels['bonus_out']]:
                m=candidate;route=checkpoint['bonus']
                print('mountain',mountain,'resume',height(m),len(route),flush=True)

    def save_checkpoint():
        checkpoint_path.write_text(json.dumps(dict(mountain=mountain,variant=(mountain-1)&7,
            prg_sha256=release,normal=normal,bonus=route,height=height(m),
            x=m.ram[0x1E],lives=m.ram[0x19],full_replay=False))+'\n')

    for step in range(max_steps):
        current=height(m)
        options=jump_options(m)
        if not options:
            if not alternatives:raise AssertionError(('No bonus route',step,current,len(route)))
            _,m,inputs,base=alternatives.pop()
            route=base+inputs
            save_checkpoint()
            print('mountain',mountain,'backtrack',height(m),len(route),flush=True)
            continue
        options.sort(key=lambda o:o[0],reverse=True)
        diverse=[];seen=set()
        for rank,n,inputs in options:
            r,L=n.ram,n.labels
            signature=(height(n),r[0x1E]//4,r[0x58],r[0x59]//8,bool(r[0x5C]),r[0x14]//4,
                       bytes(r[L['bonus_cloud_x']:L['bonus_cloud_x']+r[L['bonus_cloud_count']]]))
            if signature in seen:continue
            seen.add(signature);diverse.append((rank,n,inputs))
            if len(diverse)==12:break
        for rank,n,inputs in reversed(diverse[1:]):alternatives.append((rank,n,inputs,route.copy()))
        rank,m,inputs=options[0];route+=inputs
        save_checkpoint()
        print('mountain',mountain,'jump',step,'height',height(m),'x',m.ram[0x1E],'frames',len(route),
              'fruit',m.ram[m.labels['fruit_counts']],'caught',m.ram[m.labels['bonus_winner']],flush=True)
        if m.ram[m.labels['bonus_winner']]:break
    else:raise AssertionError('Bonus search exhausted')
    # Full rendering/IRQ-free CPU replay must agree with the planning model.
    require_prg(checksum)
    replay=initial
    for joy in route:replay.frame(joy)
    assert replay.ram[0x18]==2 and replay.ram[replay.labels['bonus_winner']]==1
    require_prg(checksum)
    return dict(mountain=mountain,variant=(mountain-1)&7,normal=normal,bonus=route,
                normal_frames=len(normal),bonus_frames=len(route),
                fruit=replay.ram[replay.labels['fruit_counts']],
                lives=replay.ram[0x19],full_replay=True,reused=False)


import os
# The search runs in worker processes: they read the option from the environment.
THOROUGH=os.environ.get('PLAN_BONUS_THOROUGH')=='1'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mountains',nargs='+',type=int,default=[1])
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--steps',type=int,default=120)
    parser.add_argument('--wait-for-normal',type=int,default=0)
    parser.add_argument('--output',default='bonus_routes.json')
    parser.add_argument('--replay-existing',action='store_true',
                        help='Replay saved normal/bonus tuples instead of searching again')
    parser.add_argument('--resume',action='store_true',
                        help='Continue a matching saved accepted-landing checkpoint')
    parser.add_argument('--thorough',action='store_true',
                        help='keep the coarse, positioned and fine landings of every jump')
    args=parser.parse_args()
    if args.thorough:
        os.environ['PLAN_BONUS_THOROUGH']='1'
    assert all(1 <= mountain <= 8 for mountain in args.mountains)
    assert 1 <= args.workers <= 2
    requested=sorted(set(args.mountains))
    checksum=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    output=BASE/'tools/fixtures'/args.output
    previous=json.loads(output.read_text()) if output.exists() else {}
    routes=previous.get('routes',[]) if previous.get('prg_sha256')==checksum else []
    failed=[entry for entry in previous.get('failed',[]) if entry['mountain'] not in requested] \
        if previous.get('prg_sha256')==checksum else []

    def save():
        result=dict(status='passed' if len(routes)==8 and not failed else 'incomplete',
                    prg_sha256=checksum,target_variants=8,requested_mountains=requested,
                    routes=sorted(routes,key=lambda route:route['mountain']),failed=failed)
        output.write_text(json.dumps(result)+'\n')
        summary={**result,'routes':[{key:value for key,value in route.items()
                                    if key not in ('normal','bonus')} for route in result['routes']]}
        proof_name=output.stem+'_prg.json'
        (BASE/'docs/verification'/proof_name).write_text(json.dumps(summary,indent=2)+'\n')

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        cached={route['mountain']:route for route in previous.get('routes',[])}
        futures={
            (pool.submit(replay_existing,cached[mountain],checksum)
             if args.replay_existing and mountain in cached else
             pool.submit(search,mountain,args.steps,args.wait_for_normal,checksum,args.resume)):mountain
            for mountain in requested}
        for future in concurrent.futures.as_completed(futures):
            mountain=futures[future]
            try:
                data=future.result()
                cache=BASE/'build_dbg/bonus_routes_input_cache'
                cache.mkdir(parents=True,exist_ok=True)
                (cache/f'{mountain:02}.json').write_text(json.dumps(
                    {**data,'replay_prg_sha256':checksum})+'\n')
                routes=[entry for entry in routes if entry['mountain']!=mountain]
                routes.append(data)
                if mountain==1:
                    first=BASE/'tools/fixtures/first_mountain_route.json'
                    previous=json.loads(first.read_text())
                    assert previous['normal']==data['normal'],'Never replace the established normal route here'
                    first_data={key:data[key] for key in ('normal','bonus','fruit','bonus_frames','lives')}
                    first_data.update(prg_sha256=checksum,normal_verified=True,
                                      bonus_replay_available=True,normal_frames=len(data['normal']))
                    first.write_text(json.dumps(first_data)+'\n')
                    (BASE/'build_dbg/bonus_route.json').write_text(json.dumps(first_data)+'\n')
                print('PASS bonus mountain',mountain,'normal',data['normal_frames'],
                      'bonus',data['bonus_frames'],'fruit',data['fruit'],'lives',data['lives'],flush=True)
            except Exception as error:
                failed.append(dict(mountain=mountain,error=str(error)))
                print('FAIL bonus mountain',mountain,repr(error),flush=True)
            save()
    if failed:
        raise SystemExit(1)


if __name__=='__main__':main()
