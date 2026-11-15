"""Check adaptive and standard sprite reuse through the native VIC IRQ."""
from tool_paths import add_vice_argument
import argparse
import hashlib
import itertools
import json
import struct
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import symbols
import vice_session
from verify_mux_timing import BASE, ViceSession, registers, sprite_write_hooks, written_events


class Scene(NamedTuple):
    name: str
    heights: list[int]
    fine: int
    reuse: int
    batch: int = 8
    xs: tuple = ()          # logical sprite x (default 35+13*i: all apart)


def scene_x(scene, i):
    return scene.xs[i] if scene.xs else 35+13*i


def apart(count, *figures):
    """x of count sprites, the index ranges in figures sharing one x (the
    layers of one figure), all others apart."""
    xs = [35+13*i for i in range(count)]
    for figure in figures:
        for i in figure:
            xs[i] = xs[figure[0]]
    return tuple(xs)


def short(count):
    """Short reuse for 9..12 sprites: 36 lines and one per later event."""
    return 28+count


def scenes():
    # The middle bands cross the palette boundary at line 140. Test its
    # different relationships to badlines and the earlier sprite DMA.
    bases = (35,36,39,40,42,114,115,116,117,118,119,120,121,122,198,200,203,204)
    for base,fine in itertools.product(bases,range(8)):
        # r reuses on one line, the other initial sprites shown meanwhile
        for count in (9,10,11,12):
            reuse,gap = count-8,short(count)
            name = 'equal' if count == 12 else f'partial{count}_'
            yield Scene(f'{name}{base}_fine{fine}',[base]*reuse+[base+22]*(8-reuse)+[base+gap]*reuse,fine,gap)
            if base <= 203:
                middle = [base+d for d in (19,21,22,24,20,23,25)][:8-reuse]
                heights = list(range(base,base+reuse))+sorted(middle)+[base+reuse-1+gap]*reuse
                name = 'unequal' if count == 12 else f'unequal{count}_'
                yield Scene(f'{name}{base}_fine{fine}',heights,fine,gap)
    for base,fine in itertools.product((35,115,118,120,200),range(8)):
        yield Scene(f'full{base}_fine{fine}',[base]*8+[base+46]*8,fine,46)
    for base,fine in itertools.product((35,116,118,120,196),range(8)):
        # events 7..10 are one figure: its back layer ends the batch, its
        # three front layers are the reuses on one line
        heights = [base]*4+[base+22]*3+[base+40]*4
        yield Scene(f'tie{base}_fine{fine}',heights,fine,short(11),8,apart(11,range(7,11)))
        # four figures at one height: eight initial ones, then three reuses
        # on one line
        yield Scene(f'split{base}_fine{fine}',heights,fine,short(11),8)
        # a figure of two layers on the boundary: the front one reuses
        yield Scene(f'tiefresh{base}_fine{fine}',[base+d for d in (0,5,10,15,20,22,25,40,40,50)],fine,
                    short(10),8,apart(10,(7,8)))
        # three layers on the boundary: two end the batch, or one does
        yield Scene(f'layers9_{base}_fine{fine}',[base+d for d in (0,5,10,15,20,22,37,37,37)],fine,
                    short(9),8,apart(9,(6,7,8)))
        yield Scene(f'layers10_{base}_fine{fine}',[base+d for d in (0,0,20,21,22,23,24,38,38,38)],fine,
                    short(10),8,apart(10,(7,8,9)))
    for base,fine in itertools.product((35,80,114,116,120,150),range(8)):
        # both climbers hammering on one floor (body and detail layers of
        # each share x and y), Topis 36-44 lines above: the batch ends
        # between the two layers of the second climber
        heights = [base+d for d in (0,0,2,36,36,44,44,44,44,96,96)]
        yield Scene(f'figures{base}_fine{fine}',heights,fine,short(11),8,apart(11,(0,1),(5,6),(7,8),(9,10)))
    for shift,fine in itertools.product((-80,-40,0,20),range(8)):
        # random2p_16, frames 576-580: Topi and its ice block 39 lines above
        # both hammering climbers, a second Topi below
        heights = [116+shift+d for d in (0,0,2,31,31,39,39,39,39,96,96)]
        yield Scene(f'climbers{116+shift}_fine{fine}',heights,fine,short(11),8,
                    apart(11,(0,1),(5,6),(7,8),(9,10)))


def measure(vice):
    trials = list(scenes())
    results = []
    with ViceSession('adaptive_mux_timing',vice) as session:
        session.frame(0xFD)
        session.frame()
        session.frame(0xEF)
        session.finish_preview()
        session.write('paused',1)
        labels = session.labels
        write_pc,batch_pc = sprite_write_hooks(session)
        for pc in (labels['schedule_actors'],labels['commit_actors'],write_pc,batch_pc):
            session.m.command(0x12,struct.pack('<HHBBBB',pc,pc,1,1,4,0))
        prepare_index = 0
        active = prepared = None
        writes = []
        enabled = 0
        while len(results) < len(trials):
            session.m.resume()
            regs = registers(session.m)
            pc = regs['PC']
            if pc == labels['commit_actors']:
                # A main-loop return can precede a later IRQ in this frame.
                # Finish the previous packet only when the next one commits.
                if active:
                    count = len(active.heights)
                    assert Counter(w['ptr'] for w in writes) == Counter(range(64,64+count)), (active,writes)
                    assert len({w['tick'] for w in writes}) == 1, (active,writes)
                    if active.reuse < 46:
                        assert [(w['event_line'],w['slot']) for w in writes[:active.batch]] == \
                            [(0,i) for i in range(active.batch)], (active,writes)
                        assert len(writes) <= active.batch or writes[active.batch]['event_line'] > 0, (active,writes)
                    # the layers of one figure: the front one on the lower VIC sprite
                    slots = {w['ptr']-64: w['slot'] for w in writes}
                    for i in range(count-1):
                        if (active.heights[i],scene_x(active,i)) == (active.heights[i+1],scene_x(active,i+1)):
                            assert slots[i] < slots[i+1], (active,slots)
                    results.append(dict(case=active.name,heights=active.heights,fine=active.fine,
                                        reuse=active.reuse,minimum_slack=min(w['slack'] for w in writes),
                                        late=sum(w['slack']<0 for w in writes),writes=writes))
                active,prepared = prepared,None
                writes = []
                enabled = 0
                previous_y = [None]*8
                if active:
                    session.write('split_open',0x10|active.fine)
                continue
            if pc == labels['schedule_actors']:
                if prepare_index < len(trials):
                    assert prepared is None
                    prepared = trials[prepare_index]
                    prepare_index += 1
                    count = len(prepared.heights)
                    session.write('logical_count',count)
                    for table,values in (
                        ('LOG_Y',prepared.heights),('LOG_X',[scene_x(prepared,i) for i in range(count)]),
                        ('LOG_XHI',[int(i%3==1) for i in range(count)]),
                        ('LOG_PTR',[64+i for i in range(count)]),
                        ('LOG_COL',[1+i%15 for i in range(count)]),
                        ('LOG_MC',[i&1 for i in range(count)]),('LOG_GROUP',[1]*count),
                    ):
                        session.write(table,values)
                continue
            if pc == labels['main_loop']:
                if prepared:
                    assert session.read('pending_count')[0] == len(prepared.heights), prepared
                    assert session.read('sched_gap')[0] == prepared.reuse, prepared
                continue
            assert pc in (write_pc,batch_pc), (hex(pc),hex(write_pc),hex(batch_pc))
            if not active:
                continue
            vic = session.read(0xD000,0x2F)
            screen = 0x4000+(vic[0x18]>>4)*1024
            assert vic[0x11]&7 == active.fine, (active,regs)
            # The $D015 store completes one event, or the frame IRQ's whole
            # line-0 batch ($D010/$D01C then already hold its last values).
            assert vic[0x15] == enabled
            for index,slot,event_line in written_events(session,regs,batch_pc):
                ptr = session.read(labels['EVENT_PTR']+index)[0]
                logical = ptr-64
                assert 0 <= logical < len(active.heights), (active,ptr)
                y = active.heights[logical]
                x = scene_x(active,logical)
                bit = 1<<slot
                assert pc == write_pc or event_line == 0, (active,index)
                assert vic[2*slot:2*slot+2] == bytes([x,y]), (active,slot,x,y)
                assert session.read(screen+0x3F8+slot) == bytes([ptr])
                assert bool(vic[0x10]&bit) == (logical%3==1)
                assert bool(vic[0x1C]&bit) == bool(logical&1)
                assert vic[0x27+slot]&15 == 1+logical%15
                enabled |= bit
                old_y = previous_y[slot]
                if old_y is not None:
                    assert y-old_y >= active.reuse and event_line >= old_y+22
                previous_y[slot] = y
                writes.append(dict(y=y,x=x,ptr=ptr,slot=slot,event_line=event_line,
                                   tick=session.read('frame_ticks')[0],line=regs['LIN'],cycle=regs['CYC'],
                                   slack=(y-regs['LIN'])*63+54-regs['CYC']-4))
            assert regs['A'] == enabled
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_vice_argument(parser)
    parser.add_argument('--build-root',type=Path,default=BASE)
    parser.add_argument('--output',type=Path,default=Path('docs/verification/adaptive_mux.json'))
    args = parser.parse_args()
    symbols.BASE = vice_session.BASE = args.build_root.resolve()
    image = args.build_root/'c64/build/iceclimber_game.prg'
    release = image.read_bytes()
    results = measure(args.vice)
    assert image.read_bytes() == release, 'PRG changed during native sprite verification'
    summary = {}
    for reuse in sorted({result['reuse'] for result in results}):
        matching = [result for result in results if result['reuse']==reuse]
        summary[reuse] = dict(scenes=len(matching),minimum_slack=min(r['minimum_slack'] for r in matching),
                              late=sum(r['late'] for r in matching))
    passed = not any(row['late'] for row in summary.values())
    report = dict(status='passed' if passed else 'failed',prg_sha256=hashlib.sha256(release).hexdigest(),
                  summary=summary,scenes=results)
    (BASE/args.output).write_text(json.dumps(report,indent=2)+'\n')
    print('Native sprite reuse:',summary)
    assert passed, 'A sprite reuse missed its VIC deadline'


if __name__ == '__main__':
    main()
