#!/usr/bin/env python3
"""Cycle-exact VICE regression using its documented binary monitor API.

The two initial joystick reads are redirected to input latches at $4F/$4E
in emulator RAM. The release PRG is unchanged. The first mountain and its
bonus use real joystick sequences; later state/score checks use RAM fixtures.
https://vice-emu.sourceforge.io/vice_13.html
"""
from tool_paths import add_vice_argument
import argparse
import json
import hashlib
import re
import socket
import struct
import subprocess
import time
import wave
from pathlib import Path

from png import write_png
from convert_c64_gfx import C64_COLORS

BASE = Path(__file__).resolve().parents[1]


class Monitor:
    def __init__(self, sock):
        self.sock, self.serial = sock, 0
        self.events = []

    def exact(self, n):
        result = bytearray()
        while len(result) < n:
            chunk = self.sock.recv(n-len(result))
            if not chunk:
                raise RuntimeError("VICE closed the monitor connection")
            result += chunk
        return result

    def receive(self):
        h = self.exact(12)
        assert h[:2] == b'\x02\x02', h.hex()
        length, kind, error, serial = struct.unpack('<IBBI', h[2:])
        body = self.exact(length)
        if error:
            raise RuntimeError(f"VICE command ${kind:02X} failed: ${error:02X}")
        return kind, serial, body

    def command(self, kind, body=b''):
        self.serial += 1
        self.sock.sendall(b'\x02\x02' + struct.pack('<IIB', len(body), self.serial, kind) + body)
        while True:
            response, serial, data = self.receive()
            if serial == self.serial:
                return data
            if response in (0x62,0x63):
                self.events.append((response,serial,data))

    def read(self, start, length):
        return self.command(1, struct.pack('<BHHBH', 0, start, start+length-1, 0, 0))[2:]

    def write(self, start, data):
        self.command(2, struct.pack('<BHHBH', 0, start, start+len(data)-1, 0, 0) + data)

    def frame(self, joy=255):
        self.write(0x4F, bytes([joy]))
        self.resume()

    def resume(self):
        self.events.clear()
        self.command(0xAA)
        resumed = False
        while True:
            kind, _, _ = self.events.pop(0) if self.events else self.receive()
            if kind == 0x63:
                resumed = True
            if kind == 0x62 and resumed:
                return

    def display(self, path):
        data = self.command(0x84, b'\x01\x00')
        fields = struct.unpack_from('<I', data)[0]
        width, height = struct.unpack_from('<HH', data, 4)
        length = struct.unpack_from('<I', data, fields)[0]
        pixels = data[fields+4:fields+4+length]
        assert len(pixels) == width*height
        rows = [b''.join(bytes(C64_COLORS[v & 15]) for v in pixels[y*width:(y+1)*width])
                for y in range(height)]
        write_png(path, width, height, rows)
        return pixels


def protected(s):
    regions = {lo:s.read(s.labels[lo],s.labels[hi]-s.labels[lo]) for lo,hi in
            (('code_begin','code_end'),('assets_begin','assets_end'),('extra_begin','extra_end'),('high_begin','high_end'))}
    for region in ('HELPERS', 'PRIOCODE'):
        size=s.labels.get(f'__{region}_SIZE__',0)
        if size:
            regions[region.lower()]=s.read(s.labels[f'__{region}_RUN__'],size)
    return regions


def score(s,player=None):
    from test_game import bcd
    if player is None:
        return bcd(s.read(0x25,2)+s.read(0x51)+s.read('score_mil'))
    data=s.read(0x200+player*32,32)
    return bcd(data[1:3]+data[31:32]+data[30:31])


def measure(s,n=30):
    s.write(0xDD0E,0);s.write(0xDD04,[255,255]);s.write(0xDD0E,17)
    prev=int.from_bytes(s.read(0xDD04,2),'little')
    cycles=[]
    for _ in range(n):
        s.frame()
        now=int.from_bytes(s.read(0xDD04,2),'little')
        cycles.append((prev-now)&65535);prev=now
    return dict(updates=n,pal_frames=round(sum(cycles)/19656,2),
                cycles=sum(cycles),peak_checkpoint_delta=max(cycles))


def real_playthrough(ViceSession,out,vice,normal_only=False):
    from test_original_scores import original_total
    from test_topi_sprites import normal_gameplay_sprites
    route=json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())
    with ViceSession('native_playthrough',vice) as s:
        original=protected(s)
        title=(BASE/'converted/screens/title_c64.bin').read_bytes()
        assert s.read(0x4000,13*40)==title[:13*40]
        for _ in range(2):s.frame()
        s.capture(out/'vice_title.png')
        s.frame(0xEF)
        s.finish_preview()     # actual opening sequence, then normal fixture phase
        for n,joy in enumerate(route['normal']):
            s.frame(joy)
            if n==30:s.capture(out/'vice_game.png')
            if n==350:s.capture(out/'vice_climb.png')
        assert s.read('state')==b'\3' and s.read('lives')==b'\3'
        normal_score=score(s)
        normal_counts=s.read('SCORE_COUNTS',5)
        if normal_only:
            assert protected(s)==original
            return dict(normal_input_frames=len(route['normal']),lives=3,
                        entered_bonus=True,readonly_intact=True)
        assert route.get('bonus'), 'No current bonus replay; use --normal-only or regenerate the bonus route'
        for n,joy in enumerate(route['bonus']):
            s.frame(joy)
            if n==120:s.capture(out/'vice_bonus_clouds.png')
            if n==310:s.capture(out/'vice_condor.png')
        assert s.read('state')==b'\2' and s.read('bonus_winner')==b'\1'
        fruit=s.read('fruit_counts')[0]
        assert fruit==route['fruit']
        s.frame();s.frame(0xEF)
        expected=normal_score+original_total(1,0,fruit,normal_counts[2],
                                             normal_counts[3],normal_counts[4],condor=True)
        assert score(s)==expected,(score(s),expected)
        s.frame();s.capture(out/'vice_results.png')
        s.frame(0xEF);s.frame()
        assert s.read('state')==b'\1' and s.read('mountain')==b'\2'
        assert score(s)==expected and s.read('lives')==b'\3'
        # Every camera fine phase must leave the entire score panel unchanged.
        s.write('paused',1)
        for _ in range(3):s.frame()
        s.write('cam',1)
        headers=[]
        for n in range(28):
            s.frame();pixels=s.capture(out/'vice_smooth_camera.png')
            header=bytes(v for y in range(52,64) for v in pixels[y*504+140:y*504+460])
            headers.append(header)
        assert len(set(headers))==1 and headers[0].count(1)>80,'Moving or missing score panel'
        assert protected(s)==original
        sprites=normal_gameplay_sprites()
        assert s.read(0x5000,len(sprites))==sprites
        return dict(normal_input_frames=len(route['normal']),bonus_input_frames=len(route['bonus']),
                    lives=3,fruit=fruit,condor_caught=True,normal_score=normal_score,
                    score_after_bonus=expected,hud_identical_frames=len(headers),readonly_intact=True)


def cooperative(ViceSession,out,vice):
    with ViceSession('native_cooperative',vice) as s:
        original=protected(s)
        s.frame(0xFD);s.frame();s.capture(out/'vice_two_player_menu.png');s.frame(0xEF);s.finish_preview()
        for _ in range(20):s.frame(0xF7,0xFB)
        a,b=s.read(0x200,32),s.read(0x220,32)
        assert a[3]>100 and b[3]<220 and (a[10],b[10])==(0,1)
        s.capture(out/'vice_two_players.png')
        idle=measure(s)
        # The original has no friendly hammer hit ($D3AC tests only the
        # objects): a swing at the partner costs no life, points or control.
        def side_by_side(x0,x1):
            s.write(0x203,x0);s.write(0x223,x1)
            for base in (0x200,0x220):
                s.write(base+5,216);s.write(base+6,216);s.write(base+7,0);s.write(base+8,1)
                for field in (12,13,20,21,24,25):s.write(base+field,0)
            s.write(0x20A,0);s.write(0x22A,1);s.sync_player_zero()
        side_by_side(150,170);s.frame();s.frame(0xEF)
        assert s.read(0x220)==b'\3' and score(s,0)==score(s,1)==0
        for _ in range(4):s.frame(0xFF,0xF7)
        assert s.read(0x223)[0]>170,'The partner lost control after a swing'
        # Climbers that touch push each other two pixels apart ($D212).
        side_by_side(150,158);s.frame()
        assert (s.read(0x203)[0],s.read(0x223)[0])==(148,160),(s.read(0x203)[0],s.read(0x223)[0])
        # The bear raises the shared camera; the lower player respawns safely.
        s.write(0x207,2);s.write(0x20B,2);s.write(0x205,120);s.write(0x206,120)
        from transplant_objects import map_ram
        s.write('last_climb',2)   # no climbing progress resets the bear clock
        s.write('bear_timer',[0,0]);s.write(map_ram(0x7C),0x80)   # $D816: the bear jumped
        s.sync_player_zero()
        for _ in range(16):
            s.frame()
            if s.read('cam') == b'\1' and s.read('normal_pan_t') == b'\0':
                break
        else:
            raise AssertionError('Bear pan did not finish')
        s.frame()  # Normal handlers resume after the last displayed scroll step.
        assert s.read('cam')==b'\1' and s.read(0x220)==b'\2'
        assert s.read(0x227)[0]>=1 and s.read(0x200)==b'\3'
        s.capture(out/'vice_shared_camera.png')
        s.write('last_climb',s.read('maxfloor')[0])
        s.write('bear_timer',[0,0]);s.write(map_ram(0x7C),0x80)   # another bear pan
        scrolling=measure(s)
        assert protected(s)==original
        return dict(two_inputs=True,no_friendly_hammer=True,body_bump=True,shared_camera=True,
                    independent_lives=True,idle_timing=idle,scroll_timing=scrolling)


def all_stages(ViceSession,out,vice):
    from test_game import bcd
    from test_topi_sprites import normal_gameplay_sprites
    levels=json.loads((BASE/'c64/build/nes_levels.json').read_text())['levels']
    bonus=json.loads((BASE/'c64/build/nes_bonus.json').read_text())
    fruit_points=(300,500,600,700,800,1000,2000,3000,4000,5000)
    condor_points=(3000,5000,6000,7000,8000,10000,20000,30000,40000,50000)
    checked=[]
    with ViceSession('native_all_stages',vice) as s:
        original=protected(s)
        s.frame(0xFD);s.frame();s.frame(0xEF);s.finish_preview()
        expected=[0,0]
        for mountain in range(1,33):
            assert s.read('mountain')[0]==mountain
            cells=bytes.fromhex(levels[mountain-1]['cells'])
            assert s.read(0x400,216)==cells[:216] and s.read(0x500,216)==cells[216:]
            assert s.read(0x601,7)==bytes(levels[mountain-1]['floor_types'])
            for _ in range(3):s.frame()
            if mountain in (10,24,32):s.capture(out/f'vice_mountain_{mountain:02}.png')
            lives=[s.read(0x200)[0],s.read(0x220)[0]]
            s.write('bonus_requested',1);s.frame()
            assert s.read('state')==b'\3'
            variant=bonus[(mountain-1)&7]
            assert s.read('bonus_platform_count')[0]==len(variant['platforms'])
            assert s.read('bonus_cloud_count')[0]==len(variant['clouds'])
            for _ in range(6):s.frame()
            # State/score fixtures exercise all 32 transitions and both tallies.
            winner=mountain%2+1
            s.write('fruit_counts',[1,2]);s.write('bonus_winner',winner)
            s.write('bonus_ticks',1);s.write('bonus_left',1)
            for _ in range(200):        # $F6DB: the timeout holds 110 frames
                s.frame()
                if s.read('state')==b'\2':break
            assert s.read('state')==b'\2'
            i=min(mountain-1,9)
            for player in (0,1):
                expected[player]=min(9999999,expected[player]+fruit_points[i]*(player+1)+
                                     (condor_points[i] if winner==player+1 else 0))
            s.frame();s.frame(0xEF)
            assert [score(s,0),score(s,1)]==expected,(mountain,expected,score(s,0),score(s,1))
            s.frame();s.frame(0xEF);s.frame()
            after=[s.read(0x200)[0],s.read(0x220)[0]]
            assert after==([v+1 for v in lives] if mountain==5 else lives)
            checked.append(dict(mountain=mountain,variant=(mountain-1)&7,
                                platforms=len(variant['platforms']),clouds=len(variant['clouds']),
                                scores=expected.copy(),lives=after))
        assert s.read('mountain')==b'\1' and s.read('phase_counter')==b'\1'
        assert protected(s)==original
        raw=normal_gameplay_sprites()
        assert s.read(0x5000,len(raw))==raw
    return checked


def audio_run(vice,out):
    startup=None
    if hasattr(subprocess, 'STARTUPINFO'):
        startup=subprocess.STARTUPINFO()
        startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    with (BASE/'build_dbg/native_audio_console.log').open('wb') as log:
        result=subprocess.run([vice,'-default','-autostartprgmode','1','-autostart',
            str(BASE/'c64/build/iceclimber_game.prg'),'-limitcycles','12000000',
            '-sounddev','wav','-soundarg',str(out/'game_fixed.wav'),'-soundwarpmode','1',
            '-exitscreenshot',str(out/'vice_game_idle.png'),
            '-logfile',str(BASE/'build_dbg/native_audio.log')],startupinfo=startup,
            stdout=log,stderr=subprocess.STDOUT,timeout=40)
    # VICE reports its intentional cycle-limit exit as status 1.
    assert result.returncode in (0,1)
    assert "cycle limit reached" in (BASE/"build_dbg/native_audio.log").read_text()
    with wave.open(str(out/'game_fixed.wav')) as wav:
        data=wav.readframes(wav.getnframes())
        peak=max(abs(v[0]) for v in struct.iter_unpack('<h',data))
        assert peak>1000,'Silent SID recording'
        return dict(peak=peak,frames=wav.getnframes(),sample_rate=wav.getframerate())


def main():
    from vice_session import ViceSession
    parser=argparse.ArgumentParser()
    add_vice_argument(parser)
    parser.add_argument('--normal-only',action='store_true',help='Use the current normal climb; bonus rules are covered by source and stage fixtures')
    args=parser.parse_args()
    out=BASE/'docs/verification';out.mkdir(parents=True,exist_ok=True)
    report=dict(status='passed',prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    report['real_playthrough']=real_playthrough(ViceSession,out,args.vice,args.normal_only)
    print('PASS native joystick climb to bonus and protected RAM' if args.normal_only else
          'PASS native joystick climb, real bonus/condor, tally, fixed score panel and RAM',flush=True)
    report['cooperative']=cooperative(ViceSession,out,args.vice)
    print('PASS native two players, no friendly hammer, body bump, bear and shared-camera respawn',flush=True)
    report['stage_fixtures']=all_stages(ViceSession,out,args.vice)
    print('PASS native all 32 maps, eight bonus variants, BCD scores, extra lives and wraparound',flush=True)
    report['audio']=audio_run(args.vice,out)
    (out/'vice_regression.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS uninterrupted release PRG, reSID audio and autostart',report['audio'],flush=True)


if __name__=='__main__':main()


