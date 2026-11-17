"""VICE: enemies must stay on their floor when a normal pan starts/ends."""
import argparse
import hashlib
import json
from tool_paths import add_vice_argument
from transplant_objects import map_ram
from measure_display_scroll import DisplayTrace
from verify_display_pixels import grab, own_pixels
from vice_session import BASE, ViceSession


def check(vice, players):
    with ViceSession(f'enemy_pan_{players}p', vice) as s:
        if players == 2:
            s.frame(0xFD); s.frame()
        s.frame(0xEF); s.finish_preview()
        s.write('paused', 1)
        for obj in range(11):
            s.write(map_ram(0x3E8+obj), 0)
            s.write(map_ram(0x91+obj), 0)
        s.write(map_ram(0x48), bytes([255])*8)
        for index,x,y,floor in ((0,223,72,3),(1,124,168,1)):
            if index >= players: continue
            address = s.labels['PLAYER_STATES']+index*32
            block = bytearray(s.read(address,32))
            block[3:9] = bytes((x,0,y,y,floor,1))
            block[11] = floor
            block[12:26] = bytes(14)
            block[30] = 0
            s.write(address,block)
        s.sync_player_zero()
        for address,value in ((0x93,255),(0x9E,120),(0xA9,104),(0xB4,3),
                              (0xBF,1),(0x3A8,0),(0x3BE,16),(0x3DF,0xA0),(0x3EA,0x45)):
            s.write(map_ram(address),value)
        for _ in range(3): s.frame()
        trace = DisplayTrace(s,record_sprites=True)
        previous = trace.next()
        s.write('paused',0)
        cameras, pixels, stationary = [],0,0
        for _ in range(22):
            current = trace.next()
            camera = previous['displayed_camera']
            assert camera is not None
            enemies = [v for v in previous['sprites'] if v[0] == 172]
            assert len(enemies) == 2, ('missing Topi',players,camera,enemies)
            assert {v[1] for v in enemies} == {116+camera}, ('enemy left its floor',players,camera,enemies)
            canvas = grab(s)
            for event in enemies:
                for y,x,colour in own_pixels(s,event,background=trace.previous_background):
                    assert canvas[y][x] == colour, ('displayed enemy pan',players,camera,y,x)
                    pixels += 1
            cameras.append(camera)
            stationary += camera == 0
            previous = current
        assert stationary >= 2, ('arming frame not captured',cameras)
        assert [c for i,c in enumerate(cameras) if i and c != cameras[i-1]] == list(range(4,49,4)), cameras
        assert cameras[-1] == 48
        return dict(players=players,frames=len(cameras),pixels=pixels,arming_frames=stationary,
                    camera_steps=12,enemy_jump_pixels=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__); add_vice_argument(parser)
    args=parser.parse_args()
    report=dict(status='passed',cases=[check(args.vice,p) for p in (1,2)],
                prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/enemy_pan.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS displayed enemy pan, including arm and resume frames',report)


if __name__=='__main__':main()
