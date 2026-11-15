"""Trial only: change bonus copy scheduling in VICE RAM, preserving the PRG."""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json
import re

from measure_display_scroll import bonus
from vice_session import ViceSession,BASE


def wait_patch(session,margin):
    if margin is None:
        return None
    wait=session.labels['wait_frame']
    code=session.read(wait,180)
    if 'wait_need' in session.labels:
        address=session.labels['wait_need']
        needle=bytes((0xA9,6,0x8D,address&255,address>>8))
        if code.count(needle)==1:
            return wait+code.index(needle)+1,margin
    # The direct guard accepts lines 0..6 in all modes and line 7 only in
    # bonus. Zeroing the final BEQ displacement redirects line 7 to @wait.
    state=session.labels['state']
    pattern=rb'\xe0\x07\x90.\xd0.\xa5'+re.escape(bytes([state]))+rb'\xc9\x03\xf0.'
    matches=list(re.finditer(pattern,code,re.DOTALL))
    assert len(matches)==1,'Unrecognized wait_frame guard'
    return (wait+matches[0].end()-1,0) if margin==6 else None


def main():
    p=argparse.ArgumentParser();add_vice_argument(p);p.add_argument('--first-columns',type=int,default=14)
    p.add_argument('--all-variants',action='store_true')
    p.add_argument('--mountain',type=int,default=1)
    p.add_argument('--setup-first-rows',type=int,default=12)
    p.add_argument('--wait-margin',type=int,choices=(5,6),
                   help='override the compiled guard during bonus mode')
    p.add_argument('--start-camera',type=int,default=220)
    p.add_argument('--max-camera',type=int,default=256)
    a=p.parse_args();stop=31-a.first_columns
    prg=BASE/'c64/build/iceclimber_game.prg';release=hashlib.sha256(prg.read_bytes()).hexdigest()
    enter=ViceSession.__enter__
    def install_trial(self):
        write=self.write
        starts=self.labels.get('copy_bonus_starts',self.labels['copy_starts'])
        stops=self.labels.get('copy_bonus_stops',self.labels['copy_stops'])
        first=self.labels['bonus_copy_setup_first']
        second=self.labels['bonus_copy_setup_second']
        assert self.read(first,2)==bytes((0xA9,12))
        assert self.read(second+5,2)==bytes((0xA9,12))
        margin_patch=wait_patch(self,a.wait_margin)
        applied=False
        def trial_write(name,value):
            nonlocal applied
            write(name,value)
            if not applied and name=='paused' and value==1 and self.read('state')==bytes([3]):
                write(starts,[31,stop]);write(stops,[stop,255])
                write(first+1,a.setup_first_rows);write(second+6,a.setup_first_rows)
                if margin_patch is not None:
                    write(*margin_patch)
                applied=True
        self.write=trial_write

    def trial_enter(self):
        result=enter(self)
        try:
            install_trial(self)
        except BaseException:
            self.close()
            raise
        return result
    ViceSession.__enter__=trial_enter
    cases={}
    try:
        for mountain in (range(1,9) if a.all_variants else (a.mountain,)):
            samples=bonus(a.vice,2,mountain=mountain,
                          start=a.start_camera,maximum=a.max_camera)
            holds=[(s['frame'],s['displayed_camera'],s['copy_stage']) for previous,s in zip(samples,samples[1:])
                   if s['displayed_camera']==previous['displayed_camera'] and s['target']>s['displayed_camera']]
            assert samples[-1]['buffer_checks']>=55
            cases[str(mountain)]=dict(holds=holds,samples=samples)
            print('TRIAL M',mountain,'TABLES',a.first_columns,32-a.first_columns,'HOLDS',holds,
                  'SETUP_ROWS',a.setup_first_rows,25-a.setup_first_rows,
                  'WAIT_MARGIN',a.wait_margin if a.wait_margin is not None else 'compiled',
                  'BUFFER_CHECKS',samples[-1]['buffer_checks'],flush=True)
    finally:ViceSession.__enter__=enter
    assert hashlib.sha256(prg.read_bytes()).hexdigest()==release
    report=dict(prg_sha256=release,trial_only=True,ram_patch=dict(
        copy_bonus_starts=[31,stop],copy_bonus_stops=[stop,255],
        first_setup_rows=a.setup_first_rows,second_setup_row=a.setup_first_rows,
        wait_margin_bonus_only=a.wait_margin),start_camera=a.start_camera,
        maximum_camera=a.max_camera,cases=cases)
    suffix='_all8' if a.all_variants else f'_m{a.mountain}'
    if a.setup_first_rows!=12:suffix+=f'_rows{a.setup_first_rows}'
    if a.wait_margin is not None:suffix+=f'_wait{a.wait_margin}'
    if a.start_camera!=220:suffix+=f'_cam{a.start_camera}_{a.max_camera}'
    (BASE/f'build_dbg/scroll_copy_trial_{a.first_columns}_{release[:8]}{suffix}.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.all_variants:assert all(not case['holds'] for case in cases.values()),'Repeated PAL motion frames'


if __name__=='__main__':main()
