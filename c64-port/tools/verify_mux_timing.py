#!/usr/bin/env python3
"""Measure actual VIC sprite register deadlines through VICE checkpoints.

No timing instrumentation is inserted in the 6510 program. The monitor stops
before each IRQ sprite-enable write; stopping VICE also stops the emulated beam.
Binary checkpoint/register protocol: https://vice-emu.sourceforge.io/vice_13.html
"""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json
import struct
from pathlib import Path

from vice_session import ViceSession, BASE


def registers(m):
    available = m.command(0x83, b'\0')
    names, pos = {}, 2
    for _ in range(int.from_bytes(available[:2], 'little')):
        size = available[pos]
        item = available[pos+1:pos+1+size]
        names[item[0]] = item[3:3+item[2]].decode('ascii')
        pos += size+1
    data = m.command(0x31, b'\0')
    result, pos = {}, 2
    for _ in range(int.from_bytes(data[:2], 'little')):
        size = data[pos]
        item = data[pos+1:pos+1+size]
        result[names[item[0]]] = int.from_bytes(item[1:], 'little')
        pos += size+1
    return result


def sprite_write_hooks(s):
    """The $D015 stores of the raster IRQ: one per later event (Y = the
    event), and one after the frame IRQ's batch of line-0 events (Y = the
    event after the batch, which started at irq_start)."""
    start = s.labels['raster_irq']
    code = s.read(start, 700)
    marker = b'\xB9\x00\x07\x8D\x15\xD0'      # lda EVENT_ENA,Y / sta $D015
    assert code.count(marker) == 1
    batch = s.labels['irq_initial_batch']
    batch_code = s.read(batch, 400)
    batch_marker = b'\xB9\xFF\x06\x8D\x15\xD0'  # lda EVENT_ENA-1,Y / sta $D015
    assert batch_code.count(batch_marker) == 1
    return start+code.index(marker)+3, batch+batch_code.index(batch_marker)+3


def written_events(s, r, batch_pc):
    """(event, VIC sprite, start line) of each event whose registers the
    hooked $D015 store completes. The frame IRQ's batch implies VIC sprite k
    and line 0 (they are not stored)."""
    if r['PC'] == batch_pc:
        start = s.read('irq_start')[0]
        return [(start+k, k, 0) for k in range(r['Y']-start)]
    index = r['Y']
    return [(index, s.read(0xF840+index)[0], s.read(0xF800+index)[0])]


class Timing:
    def __init__(self, s):
        self.s, self.samples, self.frames, self.commits = s, [], [], []
        self.write_pc, self.batch_pc = sprite_write_hooks(s)
        for pc in (self.write_pc, self.batch_pc):
            response = s.m.command(0x12, struct.pack('<HHBBBB', pc, pc, 1, 1, 4, 0))
        self.checkpoint = int.from_bytes(response[:4], 'little')
        self.commit_pc=s.labels['commit_actors']
        s.m.command(0x12,struct.pack('<HHBBBB',self.commit_pc,self.commit_pc,1,1,4,0))
        self.last_commit_tick=s.read('commit_ticks')[0]
        self.prev_commit_timer=None
        self.prev_commit_beam=None
        s.write(0xDD0E,0);s.write(0xDD04,[255,255]);s.write(0xDD0E,17)
        self.prev_timer=int.from_bytes(s.read(0xDD04,2),'little')

    def frame(self, joy=255, joy2=255):
        s = self.s
        s.write(0x4F, joy)
        s.write(0x4E, joy2)
        before = s.read('frame_ticks')[0]
        while True:
            s.m.resume()
            r = registers(s.m)
            if r['PC'] == s.labels['main_loop']:
                break
            if r['PC']==self.commit_pc:
                tick=s.read('frame_ticks')[0]
                timer=int.from_bytes(s.read(0xDD04,2),'little')
                beam=r['LIN']*63+r['CYC']
                physical_delta=None
                display_delta=None
                elapsed=None
                if self.prev_commit_timer is not None:
                    elapsed=(self.prev_commit_timer-timer)&65535
                    physical_delta=round((elapsed-(beam-self.prev_commit_beam))/19656)
                    # A commit before IRQ12 supplies THIS PAL display;
                    # after IRQ12 it supplies the NEXT PAL display.
                    display_delta=physical_delta+int(r['LIN']>=12)-int(self.prev_commit_beam//63>=12)
                self.commits.append(dict(update=len(self.frames),tick=tick,
                    frame_delta=(tick-self.last_commit_tick)&255,
                    physical_frame_delta=physical_delta,
                    display_frame_delta=display_delta,timer=timer,elapsed_cycles=elapsed,
                    line=r['LIN'],cycle=r['CYC']))
                self.last_commit_tick=tick
                self.prev_commit_timer=timer;self.prev_commit_beam=beam
                continue
            assert r['PC'] in (self.write_pc, self.batch_pc), r
            d011, line = s.read(0xD011, 2)
            line |= (d011 & 128)*2
            for index, slot, _ in written_events(s, r, self.batch_pc):
                event_y = s.read(0xF880+index)[0]
                self.samples.append(dict(frame=len(self.frames), line=line,
                    cycle=r.get('CY', r.get('CYC', None)), event=index,
                    slot=slot, y=event_y,
                    lead=event_y-line,
                    slack_cycles=(event_y-line)*63+54-r['CYC']-4,
                    ptr=s.read(0xF940+index)[0]))
        timer=int.from_bytes(s.read(0xDD04,2),'little')
        delta=(self.prev_timer-timer)&65535
        self.prev_timer=timer
        self.frames.append(dict(frame=len(self.frames), logical=s.read('logical_count')[0],
            scheduled=s.read('pending_count')[0], late=s.read('late_commit')[0],
            irq_frames=(s.read('frame_ticks')[0]-before)&255,
            camera=int.from_bytes(s.read('visual_camera', 2), 'little'),
            normal_pan=s.read('normal_pan_t')[0],cycles=delta,
            chunk=s.read('chunk_frame')[0],colour=s.read('colour_frame')[0],
            player_y=[s.read(0x205)[0],s.read(0x225)[0]],
            lives=[s.read(0x200)[0],s.read(0x220)[0]],
            logical_x=list(s.read(0xE800,s.read('logical_count')[0])),
            logical_y=list(s.read(0xE840,s.read('logical_count')[0])),
            raster=registers(s.m).get('LIN')))

    def summary(self):
        leads = [p['lead'] for p in self.samples]
        return dict(frames=len(self.frames), sprite_writes=len(leads),
            late_sprite_writes=sum(p['slack_cycles']<0 for p in self.samples),
            min_lead=min(leads, default=None),
            min_slack_cycles=min((p['slack_cycles'] for p in self.samples),default=None),
            max_logical=max((p['logical'] for p in self.frames), default=0),
            dropped_frames=sum(p['scheduled'] < p['logical'] for p in self.frames),
            variable_mainloop_intervals=sum(p['irq_frames'] != 1 for p in self.frames),
            missed_render_frames=sum(max(p['display_frame_delta']-1,0) for p in self.commits
                                     if p['display_frame_delta'] is not None),
            duplicate_commits=sum(p['display_frame_delta']==0 for p in self.commits),
            samples=[dict(p) for p in self.samples],
            updates=[dict(p) for p in self.frames],commits=[dict(p) for p in self.commits])


def measure_pan(args):
    with ViceSession('mux_pan_timing', args.vice) as s:
        s.frame(0xFD);s.frame();s.frame(0xEF);s.finish_preview()
        for _ in range(8):s.frame()
        for base,x,y,floor in ((0x200,70,72,3),(0x220,220,216,0)):
            for offset,value in ((3,x),(4,0),(5,y),(6,y),(7,floor),
                                 (8,1),(11,floor),(12,0),(13,0),(14,0),
                                 (20,0),(24,0),(25,0),(30,0)):
                s.write(base+offset,value)
        s.sync_player_zero()
        t=Timing(s)
        for n in range(25):
            t.frame()
            if n in (1,4,8):
                s.capture(BASE/f'docs/verification/mux_pan_{n:02d}.png')
        return t.summary()


REUSE_SCENES = {
    # Eight sprites per band, bands exactly one reuse distance (46) apart:
    # every VIC sprite is reused, eight register sets at the same line.
    'two_bands': [60]*8 + [106]*8,
    'four_bands': [50]*8 + [96]*8 + [142]*8 + [188]*8,
    # The reuse batch starts at the lower palette split (line 140, camera 0).
    'split_at_reuse': [118]*8 + [164]*8,
    'split_after': [120]*8 + [166]*8,
    'bottom': [200]*8 + [246]*8,
}


def measure_reuse(args):
    """Inject dense logical sprite lists just before schedule_actors and
    check every IRQ sprite write against the VIC's Y compare (cycle ~55)."""
    result = {}
    with ViceSession('mux_reuse_timing', args.vice) as s:
        s.frame(0xFD);s.frame();s.frame(0xEF);s.finish_preview()
        for _ in range(4):s.frame()
        L = s.labels
        sched = L['schedule_actors']
        write_pc, batch_pc = sprite_write_hooks(s)
        for pc in (sched, write_pc, batch_pc):
            s.m.command(0x12, struct.pack('<HHBBBB', pc, pc, 1, 1, 4, 0))
        for name, ys in REUSE_SCENES.items():
            slack, left_out = [], 0
            for frame in range(6):
                s.write(0x4F, 255)
                while True:
                    s.m.resume()
                    r = registers(s.m)
                    if r['PC'] == L['main_loop']:
                        break
                    if r['PC'] == sched:
                        n = len(ys)
                        s.write(L['logical_count'], bytes([n]))
                        for table, values in (('LOG_Y', ys), ('LOG_X', [(30+13*i) & 255 for i in range(n)]),
                                              ('LOG_XHI', [0]*n), ('LOG_PTR', [0x40]*n),
                                              ('LOG_COL', [1]*n), ('LOG_MC', [0]*n), ('LOG_GROUP', [1]*n)):
                            s.write(L[table], bytes(values))
                        continue
                    assert r['PC'] in (write_pc, batch_pc), r
                    d011, line = s.read(0xD011, 2)
                    line |= (d011 & 128)*2
                    for index, _, _ in written_events(s, r, batch_pc):
                        y = s.read(0xF880+index)[0]
                        if frame >= 2:      # the injected scene is on screen
                            slack.append((y-line)*63+54-r['CYC']-4)
                if frame >= 2:
                    left_out += len(ys)-s.read('pending_count')[0]
            result[name] = dict(sprites=len(ys), writes=len(slack), left_out=left_out,
                                min_slack_cycles=min(slack), late_sprite_writes=sum(v < 0 for v in slack))
            print('reuse', name, result[name], flush=True)
    return dict(late_sprite_writes=sum(v['late_sprite_writes'] for v in result.values()),
                left_out=sum(v['left_out'] for v in result.values()),
                min_slack_cycles=min(v['min_slack_cycles'] for v in result.values()),
                missed_render_frames=0, duplicate_commits=0, scenes=result)


def publish(args,report):
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()==report['prg_sha256'], \
        'PRG changed during native timing check'
    report['commit_clock']='CIA2 elapsed cycles and9bit PAL raster position; frameIRQ counter also recorded'
    report['status']=('passed' if all(not any(case[key] for key in
        ('late_sprite_writes','missed_render_frames','duplicate_commits'))
        for case in report['cases'].values()) else 'failed')
    out=BASE/args.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:{a:b for a,b in v.items() if a not in ('samples','updates','commits')}
                      for k,v in report['cases'].items()},indent=2),flush=True)
    assert report['status']=='passed','Native sprite/commit deadline failure; see report'


def run(args):
    route = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())
    report = dict(prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(), cases={})
    if args.pan_only:
        report['cases']['normal_pan']=measure_pan(args)
        publish(args,report)
        return
    with ViceSession('mux_native_timing', args.vice) as s:
        s.frame(0xEF);s.finish_preview()
        t = Timing(s)
        for joy in route['normal'][:args.frames]:
            t.frame(joy)
        report['cases']['real_climb'] = t.summary()
        report['cases']['real_climb']['end_state']=s.read('state')[0]
        report['cases']['real_climb']['lives']=s.read('lives')[0]
        report['cases']['real_climb']['maxfloor']=s.read('maxfloor')[0]
        if args.frames is None or args.frames >= len(route['normal']):
            assert s.read('state') == bytes([3]) and s.read('lives') == bytes([3]), \
                'The complete joystick route did not reach bonus with three lives'
    with ViceSession('mux_two_player_timing', args.vice) as s:
        s.frame(0xFD);s.frame();s.frame(0xEF);s.finish_preview()
        t = Timing(s)
        for n in range(120):
            t.frame(0xF6 if n % 38 == 0 else 0xF7,
                    0xFA if n % 41 == 0 else 0xFB)
        report['cases']['two_players'] = t.summary()
        # Real actor preparation/IRQ, controlled dense position fixture.
        # Both original player bodies + mallets, and two active icicles.
        s.write('paused', 1)
        for base in (0x200, 0x220):
            s.write(base+5, 72); s.write(base+8, 0)
            s.write(base+13, 0); s.write(base+14, 12)
            s.write(base+25, 0)
        s.write('py', 72); s.write('onground', 0); s.write('air_init', 12)
        s.write('invul_t', 0)
        s.write('actor_mask', 9)
        from transplant_objects import map_ram
        def icicles(y):
            # Original icicles 8 and 9 (object slot $18|$40, tile $10).
            for i, x in ((0, 90), (1, 250)):
                for nes, value in ((0x99+i, 0xFF), (0xA4+i, x-56), (0xAF+i, y-18),
                                   (0x03E5+i, 0x10), (0x03F0+i, 0x58+i)):
                    s.write(map_ram(nes), value)
        icicles(54)
        t.samples.clear(); t.frames.clear();t.commits.clear()
        for _ in range(12): t.frame()
        report['cases']['dense_eight'] = t.summary()
        for base in (0x200,0x220):s.write(base+5,53)
        s.write('py',53);icicles(39)
        t.frame();t.frame()
        t.samples.clear();t.frames.clear();t.commits.clear()
        for _ in range(12):t.frame()
        report['cases']['earliest_eight'] = t.summary()
        s.write('actor_mask',15)
        # A seal on floor 2, Nitpicker and a walking bear on floor 3.
        for nes, value in ((0x93, 0xFF), (0x9E, 100), (0xA9, 0x98), (0xBF, 1), (0x03DF, 0xA0), (0x03EA, 5),
                           (0x91, 0xFF), (0x9C, 120), (0xA7, 94), (0xBD, 0x80), (0x03DD, 0xE0), (0x03E8, 0x43),
                           (0x92, 0xFF), (0x9D, 94), (0xA8, 0x58), (0xBE, 1), (0x03DE, 0x18), (0x03E9, 4)):
            s.write(map_ram(nes), value)
        t.frame();t.frame()
        t.samples.clear();t.frames.clear();t.commits.clear()
        for _ in range(20):t.frame()
        report['cases']['reused_slots'] = t.summary()
    report['cases']['normal_pan']=measure_pan(args)
    report['cases']['reuse_bands']=measure_reuse(args)
    assert report['cases']['reuse_bands']['left_out']==0, 'A fitting reuse scene lost sprites'
    publish(args,report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    add_vice_argument(parser)
    parser.add_argument('--frames', type=int, default=None,
                        help='Limit the climb; the default runs the complete verified route')
    parser.add_argument('--pan-only',action='store_true')
    parser.add_argument('--output', default='docs/verification/mux_timing.json')
    run(parser.parse_args())
