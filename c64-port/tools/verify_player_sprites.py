"""Check every live player pose in VICE's actual displayed pixels."""
import argparse
import hashlib
import json

from nesgfx import chr_tiles
from test_player_sprites import player_fixture
from test_sprite_conversion import PLAYER_POSES, source_frame, decode, check_pixels, player_eyes, check_jump_face
from tool_paths import add_vice_argument
from transplant_objects import map_ram
from measure_display_scroll import DisplayTrace
from verify_display_pixels import X0, grab
from vice_session import BASE, ViceSession


def jump_animation(vice, players, others, face):
    """Follow real UP input across the two airborne poses in VICE's canvas."""
    entries = {e['name']:e for e in json.loads((BASE/'c64/build/sprite_frames.json').read_text())}
    facing = 'L' if face else 'R'
    poses = [entries[f'POPO_{facing}_{p}'] for p in ('IDLE','JUMP','HAMMER')]
    compact = players == 2 or others >= 5
    with ViceSession(f'jump_face_{players}_{others}_{face}',vice) as s:
        if players == 2: s.frame(0xFD); s.frame()
        s.frame(0xEF); s.finish_preview()
        for obj in range(11):
            s.write(map_ram(0x3E8+obj),0)
            s.write(map_ram(0x91+obj),0)
        s.write(map_ram(0x48),bytes([255])*8)
        for player in range(players):
            address=s.labels['PLAYER_STATES']+player*32
            block=bytearray(s.read(address,32))
            block[3:9]=bytes((120+100*player,0,216,216,0,1))
            block[10]=face
            block[11:31]=bytes(20)
            s.write(address,block)
        s.sync_player_zero()
        def budget(session,_): session.write('mux_others',others)
        trace=DisplayTrace(s,budget,record_sprites=True)
        previous=None; sequence=[]; checked=0
        for frame in range(50):
            current=trace.next(0xFE if frame in (1,2) else 255)
            if previous is not None:
                events=[v for v in previous['sprites'] if 120 <= v[0] <= 121]
                if events:
                    pointer=events[0][2]
                    entry=next((e for e in poses if pointer == e['pointer']+int(compact and not e['compact'])),None)
                    if entry and entry['name'].endswith(('JUMP','HAMMER')):
                        pose=entry['name'].split('_')[2]
                        if not sequence or sequence[-1] != pose: sequence.append(pose)
                        if compact and pose == 'JUMP':
                            canvas=grab(s); x,y=events[0][:2]
                            for dx in (13,14):
                                dx=dx if face else 23-dx
                                assert canvas[y+5][x+X0+dx] == 10, ('jump cheek disappeared',players,others,face,frame)
                                checked += 1
            previous=current
        assert sequence[:2] == ['JUMP','HAMMER'], ('jump transition not exercised',sequence)
        assert checked > 0 or not compact
        return dict(players=players,other_sprite_budget=others,face=face,frames=50,
                    poses=sequence,cheek_pixels=checked)


def check(vice):
    tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:4096])
    entries = {e['name']: e for e in json.loads((BASE/'c64/build/sprite_frames.json').read_text())}
    contexts = dict(lives=0, pxlo=3, pxhi=4, py=5, onground=8, face=10,
                    hammer_t=12, attack_t=13, air_init=14, move_dir=20, invul_t=25)
    cases = pixels = exact = compact = 0
    for bonus in (False, True):
        for players, others in ((1, 0), (1, 5), (2, 0)):
            name = f'player_quality_{int(bonus)}_{players}_{others}'
            with ViceSession(name, vice) as s:
                if players == 2:
                    s.frame(0xFD)
                    s.frame()
                s.frame(0xEF)
                s.finish_preview()
                if bonus:
                    s.write('bonus_requested', 1)
                    for _ in range(3):
                        s.frame()
                    assert s.read('state') == b'\3'
                    s.write('fruit_mask', 0)
                s.write('paused', 1)
                for obj in range(11):
                    s.write(map_ram(0x03E8+obj), 0)
                s.write('debris_any', 0)
                bank = s.read(0x5000, 0x2000)
                for pose in PLAYER_POSES:
                    if bonus and pose == 'JUMP':
                        continue
                    for face in (0, 1):
                        for player in range(players):
                            x = 255 if player == players-1 else 160
                            fixture = player_fixture(s.labels, pose, players, player, others, x, face)
                            for address, value in fixture.items():
                                s.write(address, value)
                            for field, offset in contexts.items():
                                s.write(s.labels['PLAYER_STATES']+player*32+offset, fixture[s.labels[field]])
                        s.sync_player_zero()
                        for _ in range(4):
                            s.write('mux_others', others)
                            s.frame()
                        canvas, logs = grab(s), s.read(0xE800, 0x100)
                        index = 0
                        for player in range(players):
                            entry = entries[f'POPO_{"L" if face else "R"}_{pose}']
                            layers = 2 if entry['compact'] or players == 2 or others >= 5 else 3
                            x = 255 if player == players-1 else 160
                            blocks, modes, offsets = [], [], []
                            for i in range(index, index+layers):
                                pointer, colour, mc = logs[0x60+i], logs[0x80+i] & 15, logs[0xA0+i]
                                start = (pointer-0x40)*64
                                blocks.append(bank[start:start+64])
                                modes.append((0, 1, 3, 2) if mc else {1: 1, 14 if player == 0 else 4: 2, 10: 3}[colour])
                                offsets.append(logs[i]+256*logs[0x20+i]-x)
                            drawn = decode(b''.join(blocks), modes, offsets)
                            original = source_frame(tiles, entry, bonus)
                            shift = offsets[1] if layers == 2 else 0
                            context = (bonus, players, others, player, pose, face)
                            check_pixels(original, drawn, modes, context, shift, player_eyes(entry, layers==2))
                            check_jump_face(entry, drawn, layers==2)
                            palette = (0, 1, 14 if player == 0 else 4, 10)
                            y0 = logs[0x40+index]
                            for dx,dy in player_eyes(entry, layers==2):
                                assert canvas[y0+dy][x+X0+dx] == 0, ('displayed eye filled',context,dx,dy)
                            for y, row in enumerate(drawn):
                                for dx, role in enumerate(row):
                                    if role:
                                        got = canvas[y0+y][x+X0+dx]
                                        assert got == palette[role], ('displayed player pixel', context, dx, y, role, got)
                                        pixels += 1
                            exact += layers == 3
                            compact += layers == 2
                            cases += 1
                            index += layers+int(not bonus and pose in ('JUMP', 'HAMMER', 'ATTACK', 'STRIKE'))
                        assert s.read('logical_count')[0] == index, ('unexpected player/NPC layers', name, pose)
                        if players == 2 and pose in ('IDLE', 'HAMMER') and face == 0:
                            s.capture(BASE/f'docs/verification/{name}_{pose.lower()}.png')
            print(f'PASS displayed player poses: bonus={bonus}, players={players}, other-sprite budget={others}', flush=True)
    animation=[jump_animation(vice,p,o,f) for p,o in ((1,0),(1,5),(2,0)) for f in (0,1)]
    return dict(status='passed', cases=cases, displayed_pixels=pixels, jump_animation=animation,
                exact_hires_cases=exact, compact_cases=compact,
                both_players=True, both_directions=True, normal_and_bonus=True,
                source='executed NES D17C and CE06 OAM')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_vice_argument(parser)
    args = parser.parse_args()
    report = check(args.vice)
    report['prg_sha256'] = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    (BASE/'docs/verification/player_display_quality.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS VICE player quality', report, flush=True)


if __name__ == '__main__':
    main()
