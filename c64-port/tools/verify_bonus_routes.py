#!/usr/bin/env python3
"""Replay published normal+bonus joystick routes in native VICE.

Mountain selection uses hidden keyboard codes. No player, map, platform, enemy or
timer state is changed during gameplay. Startup uses the CIA code fixture;
gameplay uses the existing VICE controller latches.
"""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json
import time

from test_game import BASE
from test_original_scores import original_total
from verify_vice import protected, score
from vice_session import ViceSession


def wait_route(mountain, wait_seconds, checksum=None):
    deadline=time.monotonic()+wait_seconds
    while True:
        route=None
        for filename in ('bonus_routes_verified.json','bonus_routes.json','bonus_routes_extra.json'):
            try:
                fixture=json.loads((BASE/'tools/fixtures'/filename).read_text())
            except (FileNotFoundError,json.JSONDecodeError):
                continue
            if checksum is not None and fixture.get('prg_sha256')!=checksum:
                continue
            route=next((entry for entry in fixture['routes'] if entry['mountain']==mountain),None)
            if route is not None:
                break
        if route is None and mountain==1:
            route=json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())
            route.update(mountain=1,variant=0,normal_frames=len(route['normal']),full_replay=True)
        if route is not None:
            return route
        if time.monotonic()>=deadline:
            raise AssertionError(('No published bonus route',mountain))
        time.sleep(10)


def replay(route,vice,out):
    mountain=route['mountain']
    with ViceSession(f'native_bonus_route_{mountain:02}',vice) as session:
        before=protected(session)
        session.title_code(mountain)
        assert session.read('selected_mountain')[0]==mountain
        session.frame(0xEF)
        session.frame()
        for joy in route['normal']:
            session.frame(joy)
        assert session.read('state')==bytes([3]), ('normal route',mountain)
        lives=session.read('lives')[0]
        assert lives==route['lives']
        normal_score=score(session)
        counts=session.read('SCORE_COUNTS',5)
        for index,joy in enumerate(route['bonus']):
            session.frame(joy)
            if index==9:
                session.capture(out/f'vice_bonus_route_{mountain:02}_entry.png')
            if index==len(route['bonus'])-2:
                session.capture(out/f'vice_bonus_route_{mountain:02}_condor.png')
        assert session.read('state')==bytes([2]) and session.read('bonus_winner')==bytes([1]), \
            ('bonus route did not catch condor',mountain)
        fruit=session.read('fruit_counts')[0]
        assert fruit==route['fruit'] and session.read('lives')[0]==lives
        session.frame()
        session.frame(0xEF)
        expected=normal_score+original_total(mountain,0,fruit,counts[2],counts[3],counts[4],condor=True)
        assert score(session)==expected, ('source score',mountain,score(session),expected)
        session.frame()
        session.capture(out/f'vice_bonus_route_{mountain:02}_results.png')
        session.frame(0xEF)
        session.frame()
        assert session.read('state')==bytes([1]) and session.read('mountain')[0]==mountain+1
        from test_topi_sprites import normal_gameplay_sprites
        assert session.read(0x5000,8192)==normal_gameplay_sprites()
        assert protected(session)==before
        return dict(mountain=mountain,variant=route['variant'],
                    normal_frames=len(route['normal']),bonus_frames=len(route['bonus']),
                    fruit=fruit,lives=lives,condor_caught=True,score=expected,
                    readonly_intact=True,normal_sprites_restored=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mountains',nargs='+',type=int,default=list(range(1,9)))
    parser.add_argument('--wait-for-routes',type=int,default=0)
    add_vice_argument(parser)
    args=parser.parse_args()
    out=BASE/'docs/verification'
    checksum=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    path=out/'bonus_routes_vice.json'
    previous=json.loads(path.read_text()) if path.exists() else {}
    records=previous.get('routes',[]) if previous.get('prg_sha256')==checksum else []
    for mountain in sorted(set(args.mountains)):
        route=wait_route(mountain,args.wait_for_routes,checksum)
        assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()==checksum, \
            'Release changed during native route verification'
        record=replay(route,args.vice,out)
        records=[entry for entry in records if entry['mountain']!=mountain]+[record]
        records.sort(key=lambda entry:entry['mountain'])
        path.write_text(json.dumps(dict(status='passed' if len(records)==8 else 'incomplete',
            prg_sha256=checksum,target_variants=8,routes=records),indent=2)+'\n')
        archive_path=BASE/'tools/fixtures/bonus_routes_verified.json'
        previous=json.loads(archive_path.read_text()) if archive_path.exists() else {}
        archive=previous.get('routes',[]) if previous.get('prg_sha256')==checksum else []
        archive=[entry for entry in archive if entry['mountain']!=mountain]
        archive.append({**route,**record,'full_replay':True,'final_replay':'native_vice'})
        archive.sort(key=lambda entry:entry['mountain'])
        archive_path.write_text(json.dumps(dict(status='passed' if len(archive)==8 else 'incomplete',
            prg_sha256=checksum,target_variants=8,routes=archive))+'\n')
        print('PASS native bonus variant',mountain,record,flush=True)


if __name__=='__main__':
    main()
