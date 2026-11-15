"""Sample committed VIC camera geometry at the frame IRQ, without PRG edits.

This is a diagnostic, not a game-state oracle. The displayed coarse row is
identified from the actual D018-selected screen and the world character cache;
the fine position is read from D011 after the frame IRQ latches it.
"""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json
import struct
from os import getpid

from vice_session import ViceSession, BASE
from verify_mux_timing import registers


# Checkpoint stops allowed per PAL frame (sprite and palette IRQs re-enter
# @resume; busy bonus frames need more than the default).
IRQ_STOPS = 24


class DisplayTrace:
    def __init__(self, session, at_main_loop=None, record_sprites=False):
        self.s = session
        irq = session.labels['raster_irq']
        target = session.labels['terrain_palette_top']
        code = session.read(irq, 190)
        call = bytes((0x20, target & 255, target >> 8))
        assert code.count(call) == 1
        self.pc = irq + code.index(call) + 3
        session.m.command(0x12, struct.pack('<HHBBBB', self.pc, self.pc, 1, 1, 4, 0))
        self.check_pc=session.labels['read_joy']
        session.m.command(0x12,struct.pack('<HHBBBB',self.check_pc,self.check_pc,1,1,4,0))
        self.samples = []
        self.previous_row = 0
        self.last_tick = None
        self.at_main_loop=at_main_loop
        self.record_sprites=record_sprites
        self.main_loops=0
        self.buffer_checks=0
        self.last_main_end=None
        self.background = self.previous_background = None

    def next(self, joy=255, joy2=255):
        s = self.s
        s.write(0x4F, joy)
        s.write(0x4E, joy2)
        for _ in range(IRQ_STOPS):
            s.m.resume()
            reg = registers(s.m)
            if reg['PC']==self.check_pc:
                view=s.read('last_view_row')[0]
                if s.read('state')[0] in (1,3,4) and view!=255:
                    front=0x4000+s.read('screen_buffer')[0]*1024
                    chars=s.read(front,1000);cache=s.read(0xE000,2048)
                    for sy in range(25):
                        row=(view+24-sy)&63
                        assert chars[sy*40+4:sy*40+36]==cache[row*32:row*32+32], \
                            ('Committed screen/cache mismatch',self.main_loops,view,sy)
                    self.buffer_checks+=1
                continue
            if reg['PC'] == self.pc:
                tick=s.read('frame_ticks')[0]
                # @resume is also the entry for later sprite/palette IRQs.
                if reg['LIN'] < 35 and tick != self.last_tick:
                    self.last_tick=tick
                    break
                continue
            assert reg['PC'] == s.labels['main_loop'], reg
            self.last_main_end=dict(line=reg['LIN'],cycle=reg['CYC'],
                irq_tick=s.read('frame_ticks')[0],
                visual=int.from_bytes(s.read('visual_camera',2),'little'),
                stage=s.read('copy_stage')[0])
            if self.at_main_loop:
                self.at_main_loop(s,self.main_loops)
                self.main_loops+=1
        else:
            raise AssertionError('No frame IRQ sample')
        d011 = s.read(0xD011)[0]
        d018 = s.read(0xD018)[0]
        screen_address = 0x4000 + ((d018 >> 4) & 15)*1024
        screen = s.read(screen_address, 1000)
        if self.record_sprites:
            self.previous_background = self.background
            self.background = (screen, s.read(0xD800, 1000),
                               s.read(0x4800, 2048), 47+(d011 & 7))
        world = s.read(0xE000, 2048)
        state=s.read('state')[0]
        dynamic_rows=set()
        if state==3:
            count=s.read('bonus_cloud_count')[0]
            low=s.read('bonus_cloud_hlo',count)
            high=s.read('bonus_cloud_hhi',count)
            dynamic_rows={((lo+hi*256)//8+2)&63 for lo,hi in zip(low,high)}
        elif state==1:
            kinds=s.read('floor_types',9)
            dynamic_rows={floor*6+2 for floor in range(1,8)
                          if (kinds[floor]&0xE0)>=0x60}
        possible = []
        for row in range(96):
            if all(screen[y*40+4:y*40+36] ==
                   world[((row+24-y)&63)*32:((row+24-y)&63)*32+32]
                   for y in range(25) if ((row+24-y)&63) not in dynamic_rows):
                possible.append(row)
        if possible:
            row = min(possible, key=lambda r: abs(r-self.previous_row))
            self.previous_row = row
            camera = row*8+(d011&7)-7
        else:
            row = camera = None
        start = s.read('irq_start')[0]
        count = s.read('irq_count')[0]-start
        y = list(s.read(0xF880+start, count)) if count else []
        ptr = list(s.read(0xF940+start, count)) if count else []
        record = dict(frame=len(self.samples), irq_tick=self.last_tick,line=reg['LIN'], cycle=reg['CYC'],
                      d011=d011, d018=d018, screen=hex(screen_address),
                      coarse_row=row, displayed_camera=camera,
                      live_visual=int.from_bytes(s.read('visual_camera',2),'little'),
                      normal_camera=int.from_bytes(s.read('normal_camera',2),'little'),
                      target=int.from_bytes(s.read('target_camera',2),'little'),
                      logic_phase=s.read('logic_phase')[0], pan=s.read('normal_pan_t')[0],
                      copy_stage=s.read('copy_stage')[0],
                      logical=s.read('logical_count')[0], late=s.read('late_commit')[0],
                      main_loops=self.main_loops,event_count=count,
                      buffer_checks=self.buffer_checks,
                      event_y=y,event_ptr=ptr, state=state)
        record['producer_end']=self.last_main_end
        if self.record_sprites:
            events = {name: s.read(s.labels['EVENT_'+name]+start, count)
                      for name in ('X', 'SLOT', 'COL', 'MSB', 'MC')} if count else {}
            record['sprites'] = []
            # The frame IRQ's batch (EVENT_BATCH leading events) is drawn on
            # VIC sprites 0, 1, ..; only its last event stores the bits.
            batch = s.read(s.labels['EVENT_BATCH']+start)[0] if count else 0
            for i, (sprite_y, graphic) in enumerate(zip(y, ptr)):
                slot, bits = (i, batch-1) if i < batch else (events['SLOT'][i], i)
                bit = 1<<slot
                x = events['X'][i]+256*bool(events['MSB'][bits] & bit)
                record['sprites'].append([x, sprite_y, graphic, events['COL'][i],
                                          bool(events['MC'][bits] & bit)])
        self.samples.append(record)
        return record


def normal(vice,mountain=1,players=1):
    with ViceSession(f'scroll_display_normal_{getpid()}', vice) as s:
        s.write('selected_mountain',mountain)
        if players==2:s.frame(0xFD);s.frame()
        s.frame(0xEF)
        s.finish_preview()
        for _ in range(8):
            s.frame()
        for name,value in (('py',72),('prevpy',72),('curfloor',3),('onground',1),
                           ('maxfloor',3),('move_dir',0),('walk_time',0),
                           ('skid_t',0),('invul_t',120),('pxlo',100),('pxhi',0)):
            s.write(name,value)
        # Match the live context invariant after controlled player placement.
        if players==2:
            for offset,name in enumerate(('lives','score_lo','score_hi','pxlo','pxhi',
                    'py','prevpy','curfloor','onground','vy','face','maxfloor',
                    'hammer_t','attack_t','air_init','fall_int','fall_frac','y_frac',
                    'rise_int','rise_frac','move_dir','walk_time','walk_frac',
                    'air_xfrac','skid_t','invul_t','pleft','pright','flow_frac',
                    'bonus_plat',None,'score_top')):
                if name: s.write(0x200+offset,s.read(name))
        if mountain!=1:s.write('normal_pan_request',1)
        trace=DisplayTrace(s)
        for _ in range(30):trace.next()
        return trace.samples


def normal_route(vice, inputs):
    """Use the verified real route's main-loop input boundaries, and sample PAL IRQs."""
    with ViceSession(f'scroll_normal_route_{getpid()}', vice) as s:
        s.frame(0xEF)
        s.finish_preview()
        played = 0

        def next_joy():
            return inputs[played] if played < len(inputs) else 255

        def advance(session, _):
            nonlocal played
            played += 1
            session.write(0x4F, next_joy())

        trace = DisplayTrace(s, advance, record_sprites=True)
        while played < len(inputs):
            sample = trace.next(next_joy())
            if sample['state'] != 1:
                break
            assert len(trace.samples) < len(inputs)*2, 'Joystick replay stopped advancing'
        return trace.samples, played, s.read('lives')[0]


def normal_coop_pan(vice):
    """Both climbers are visible when the leader's grounded pose arms the pan."""
    with ViceSession(f'scroll_normal_coop_{getpid()}', vice) as s:
        s.frame(0xFD)
        s.frame()
        s.frame(0xEF)
        s.finish_preview()
        assert s.read('player_count') == b'\x02'
        base = s.labels['PLAYER_STATES']
        for index, x, y, floor in ((0,223,72,3), (1,124,168,1)):
            address = base+index*32
            player = bytearray(s.read(address, 32))
            player[3:9] = bytes((x,0,y,y,floor,1))
            player[11] = floor
            player[12:26] = bytes(14)
            player[30] = 0
            s.write(address, player)
        s.sync_player_zero()
        s.write('paused', 1)
        s.frame()
        s.frame()
        s.write('paused', 0)
        s.write('logic_phase', 4)
        trace = DisplayTrace(s, record_sprites=True)
        for frame in range(26):
            # Direction/jump edges near the end still belong to the frozen pan.
            trace.next(0xFE if frame in (10,12) else 255, 0xF7 if frame >= 8 else 255)
        return trace.samples


def bonus(vice,players=2,maximum=64,mountain=1,start=0):
    with ViceSession(f'scroll_display_bonus_{getpid()}',vice) as s:
        s.write('selected_mountain',mountain)
        if players==2:s.frame(0xFD);s.frame()
        s.frame(0xEF);s.finish_preview()
        s.write('bonus_requested',1);s.frame()
        assert s.read('state')==bytes([3])
        # First settle the target camera in the region where all fourfruit
        # objects and the condor fit alongside both airborneplayers.
        s.write('paused',1);s.write('bonus_camera',start.to_bytes(2,'little'))
        for _ in range(130):s.frame()
        s.write('paused',0)
        def configure(s,n):
            camera=min(start+2*n,maximum)
            s.write('bonus_camera',camera.to_bytes(2,'little'))
            s.write('fruit_mask',15);s.write('bonus_out',[0,0])
            for base,x,y in ((0x200,120,140),(0x220,240,150)):
                for offset,value in ((3,x&255),(4,x>>8),(5,y),(6,y),(8,0),
                                     (12,0),(13,0),(14,12),(15,3),(16,8),
                                     (17,240),(18,3),(19,168),(20,0),(21,0),
                                     (24,0),(25,0),(30,0)):
                    s.write(base+offset,value)
            # Keep both public representations of player0 synchronized.
            for name,value in (('pxlo',120),('pxhi',0),('py',140),('prevpy',140),
                               ('onground',0),('hammer_t',0),('attack_t',0),
                               ('air_init',12),('fall_int',3),('fall_frac',8),
                               ('y_frac',240),('rise_int',3),('rise_frac',168),
                               ('move_dir',0),('walk_time',0),('skid_t',0),
                               ('invul_t',0)):
                s.write(name,value)
        configure(s,0)
        trace=DisplayTrace(s,configure)
        trace.previous_row=(start+7)//8
        for _ in range(70):trace.next()
        return trace.samples


def main():
    p=argparse.ArgumentParser()
    add_vice_argument(p)
    p.add_argument('--case',choices=('normal','bonus'),default='normal')
    p.add_argument('--tag',default='baseline')
    p.add_argument('--players',type=int,choices=(1,2),default=2)
    p.add_argument('--mountain',type=int,default=1)
    p.add_argument('--max-camera',type=int,default=256)
    p.add_argument('--start-camera',type=int,default=220)
    a=p.parse_args()
    release=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    samples=normal(a.vice,a.mountain,a.players) if a.case=='normal' else bonus(a.vice,a.players,a.max_camera,a.mountain,a.start_camera)
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()==release
    report=dict(prg_sha256=release,players=a.players,mountain=a.mountain,
                controlled_camera_max=a.max_camera,controlled_camera_start=a.start_camera,**{a.case:samples})
    (BASE/f'build_dbg/scroll_display_{a.case}_{a.tag}.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('frame','irq_tick','displayed_camera','live_visual','target','logic_phase','copy_stage','logical','late')} for r in samples],indent=2),flush=True)


if __name__=='__main__':main()
