"""Compare the bounded bonus-fruit emitter with the preceding assembled code."""
import argparse
import hashlib
import json
import random

from test_game import Machine,BASE


FIELDS=('frame','visual_camera','visual_camera_hi','actor_mask','fruit_mask',
        'completed_mountains','logical_count')
ARRAYS=('LOG_X','LOG_XHI','LOG_Y','LOG_PTR','LOG_COL','LOG_MC','LOG_GROUP')


def main():
    p=argparse.ArgumentParser();p.add_argument('--record',action='store_true');a=p.parse_args()
    file=BASE/'tools/fixtures/fruit_append_reference.json'
    m=Machine();r,L=m.ram,m.labels
    rng=random.Random(46611)
    if a.record:
        cases=[]
        explicit=[(n,c,mask) for n in (0,1,14,30,31,32)
                  for c in (0,31,32,220,240,256,296,405,511,65535)
                  for mask in (0,1,7,15)]
        for n,c,mask in explicit:
            fields=[rng.randrange(256),c&255,c>>8,rng.choice((0,4,15)),mask,
                    rng.randrange(256),n]
            cases.append(dict(fields=fields,initial=rng.randbytes(32*7).hex()))
        cases.extend(dict(fields=[rng.randrange(256),rng.randrange(256),rng.randrange(3),
                                  rng.choice((0,4,15)),rng.randrange(16),rng.randrange(256),
                                  rng.randrange(33)],initial=rng.randbytes(32*7).hex())
                     for _ in range(300))
    else:cases=json.loads(file.read_text())['cases']
    for i,case in enumerate(cases):
        initial=bytes.fromhex(case['initial'])
        for n,name in enumerate(ARRAYS):r[L[name]:L[name]+32]=initial[n*32:(n+1)*32]
        for name,value in zip(FIELDS,case['fields']):
            address=L['visual_camera']+1 if name=='visual_camera_hi' else L[name]
            r[address]=value
        r[L['actor_kind']],r[L['actor_mc']]=1,0
        m.call('actor_fruits')
        result=dict(count=r[L['logical_count']],arrays=b''.join(
            r[L[name]:L[name]+32] for name in ARRAYS).hex())
        if a.record:case['result']=result
        else:assert result==case['result'],(i,case['fields'],result,case['result'])
    if a.record:
        file.write_text(json.dumps(dict(source_prg_sha256=hashlib.sha256(
            (BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),cases=cases))+'\n')
    print('PASS fruit emitter equivalence:',len(cases),'clipping/mask/capacity/type/camera cases',flush=True)


if __name__=='__main__':main()
