"""Prove seeded bonus fruit fields and the six-layer nonfruit prefix."""
import hashlib
import itertools
import json
import random

from plan_mountains import PlanningMachine,clone
from test_game import BASE


ARRAYS=('LOG_X','LOG_XHI','LOG_Y','LOG_PTR','LOG_COL','LOG_MC','LOG_GROUP')


def logs(m):
    return b''.join(m.ram[m.labels[name]:m.labels[name]+32] for name in ARRAYS)


def main():
    m=PlanningMachine();r,L=m.ram,m.labels
    assert r[L['fruit_seeded']]==0
    r[L['fruit_seeded']]=255;m.call('actors_reset');assert r[L['fruit_seeded']]==0
    r[L['player_count']]=1;m.call('fruit_seed_init');assert r[L['fruit_seeded']]==0
    r[L['player_count']]=2;r[L['mountain']]=1;m.call('enter_bonus')
    assert r[L['fruit_seeded']]==1
    original=bytes(r);rng=random.Random(613)
    comparisons=0
    for n in range(33):
        for _ in range(40):
            r[:]=original
            for name in ARRAYS:r[L[name]:L[name]+32]=rng.randbytes(32)
            r[L['completed_mountains']]=rng.randrange(256)
            r[L['fruit_seeded']]=0;m.call('fruit_seed_init')
            r[L['logical_count']]=n
            r[L['visual_camera']:L['visual_camera']+2]=rng.choice(
                (0,31,32,220,240,256,296,405,511,65535)).to_bytes(2,'little')
            r[L['frame']]=rng.randrange(256);r[L['fruit_mask']]=rng.randrange(16)
            r[L['actor_mask']]=rng.choice((0,4,15))
            r[L['actor_kind']],r[L['actor_mc']]=1,0
            reference=clone(m);reference.ram[L['fruit_seeded']]=0
            m.call('actor_fruits');reference.call('actor_fruits')
            assert r[L['logical_count']]==reference.ram[L['logical_count']],(n,'count')
            assert logs(m)==logs(reference),(n,'all32 logical entries')
            comparisons+=1
    # Source2P always selects compact body+detail; bonus hides the mallet.
    # Clipped bodies reduce this bound. Every physical pose path is sampled.
    body_cases=0
    r[:]=original
    for y,ground,age,attack,face,swing,player in itertools.product(
            (0,34,35,64,139,246,247,255),(0,1),(0,1,10,12,15),
            (0,1,2,10,11,14,15,20),(0,1),(0,1,2),(0,1)):
        r[:]=original
        for name,value in (('py',y),('onground',ground),('air_init',age),
                           ('attack_t',attack),('face',face),('player_index',player),
                           ('actor_mask',15),('logical_count',0)):
            r[L[name]]=value
        r[L['GROUND_SWING']+player]=swing
        r[L['view_delta']:L['view_delta']+2]=bytes(2)
        m.call('actor_player')
        assert r[L['logical_count']]<=2,(y,ground,age,attack,face,swing,player)
        for name in ARRAYS:
            assert r[L[name]+6:L[name]+14]==original[L[name]+6:L[name]+14],('body touched fruit slots',name)
        body_cases+=1
    condor_cases=0
    for camera,x,mask in itertools.product((0,128,190,220,240,256,300,405,511,65535),
                                          (0,80,168,240,255),(0,4,15)):
        r[:]=original
        r[L['visual_camera']:L['visual_camera']+2]=camera.to_bytes(2,'little')
        r[L['condor_xlo']]=x;r[L['actor_mask']]=mask;r[L['logical_count']]=4
        m.call('actor_condor')
        assert r[L['logical_count']]<=6
        for name in ARRAYS:
            assert r[L[name]+6:L[name]+14]==original[L[name]+6:L[name]+14],('condor touched fruit slots',name)
        condor_cases+=1
    report=dict(status='passed',seeded_full_log_comparisons=comparisons,
                compact_player_pose_cases=body_cases,condor_prefix_cases=condor_cases,
                seeded_range=[6,13],capacity_range=[0,32],explicit_initialization=True,
                prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'build_dbg/fruit_seed_equivalence.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS seeded fruit:',comparisons,'full LOG comparisons;',body_cases,
          'compact player poses;',condor_cases,'condor prefix cases')


if __name__=='__main__':main()
