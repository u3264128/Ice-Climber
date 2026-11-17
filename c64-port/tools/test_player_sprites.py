"""Compare jump/hammer input, source handlers and terrain-relative player OAM."""
import json
import hashlib
import itertools

from nesgfx import chr_tiles
from original_player_reference import PlayerReference
from test_game import BASE, start
from test_sprite_conversion import source_frame, decode, check_pixels, player_eyes, check_jump_face


def body_pixels(reference,tiles):
    sprites=[tuple(reference.ram[0x200+4*i:0x204+4*i]) for i in range(6)]
    origin_x=min(sprite[3] for sprite in sprites)
    origin_y=min(sprite[0] for sprite in sprites)
    pixels=[[0]*16 for _ in range(24)]
    for y,tile,attributes,x in reversed(sprites):
        for ty in range(8):
            for tx in range(8):
                value=tiles[tile][7-ty if attributes&0x80 else ty][7-tx if attributes&0x40 else tx]
                if value:pixels[y-origin_y+ty][x-origin_x+tx]=value
    return origin_x,origin_y,pixels


def check_actual_input_art():
    tiles=chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000])
    metadata=json.loads((BASE/'c64/build/sprite_frames.json').read_text())
    frames={entry['pointer']+layer:entry for entry in metadata for layer in range(entry['layers'])}
    sequences=((0x80,)+(0,)*23,(0x81,)+(1,)*23,(0x82,)+(2,)*23,
               (1,)*24+(0x81,)+(1,)*23,
               (0x40,)+(0,)*27,
               (1,)*6+(0x41,)+(1,)*27,
               (2,)*6+(0x42,)+(2,)*27)
    samples=0
    for sequence in sequences:
        reference=PlayerReference();machine=start()
        r,L=machine.ram,machine.labels
        for tick,pad in enumerate(sequence):
            reference.tick(pad)
            joystick=255
            if pad&128:joystick&=254
            if pad&64:joystick&=239
            if pad&1:joystick&=247
            if pad&2:joystick&=251
            machine.joystick=joystick
            machine.call('read_joy')
            machine.call('normal_player_tick')
            r[L['logical_count']]=0;r[L['actor_mask']]=255
            # NES ground216 becomes VIC raster230 in this playfield.
            # Logical player216 is source body192, with video translation14.
            r[L['view_delta']:L['view_delta']+2]=(-4).to_bytes(2,'little',signed=True)
            machine.call('actor_player')
            count=r[L['logical_count']]
            parka=next(i for i in range(count) if not r[L['LOG_MC']+i] and r[L['LOG_COL']+i]==14)
            frame=frames[r[L['LOG_PTR']+parka]]
            source_x,source_y,pixels=body_pixels(reference,tiles)
            source_base=min(reference.ram[0x201+4*i] for i in range(6))
            assert frame['nes_base']==source_base,('actual input body pose',tick,pad,frame['name'],hex(source_base),
                'NES handler/Y',reference.ram[0x6A],reference.ram[0x66],
                'source OAMY',source_y,'C64 LOGY',r[L['LOG_Y']+parka],
                'C64 ground/Y/age',r[L['onground']],r[L['py']]-24,r[L['air_init']])
            crop=frame['y_offset']+6
            assert r[L['LOG_X']+parka]==source_x+52,('actual input body X',tick,pad)
            assert r[L['LOG_Y']+parka]==source_y+crop+14,('actual input terrain-relative body Y',tick,pad,
                r[L['LOG_Y']+parka],source_y+crop+14,'NES Y',reference.ram[0x66],
                'C64Y/ground/age/latch',r[L['py']]-24,r[L['onground']],r[L['air_init']],
                r[L['PLAYER_LAND_Y']],r[L['PLAYER_LAND_AGE']])
            sprite=0x4000+r[L['LOG_PTR']+parka]*64
            for y in range(21):
                for x in range(16):
                    bit=r[sprite+y*3+(x+4)//8]&(0x80>>((x+4)%8))
                    assert bool(bit)==(pixels[y+crop][x]==2),('actual input parka/foot pixels',tick,pad,x,y)
            if reference.ram[0x21C]!=0xF8:
                mallet=count-1
                assert frames[r[L['LOG_PTR']+mallet]]['nes_base']==reference.ram[0x21D],('actual input mallet frame',tick,pad)
                assert r[L['LOG_X']+mallet]==reference.ram[0x21F]+52,('actual input mallet X',tick,pad)
                assert r[L['LOG_Y']+mallet]==reference.ram[0x21C]+14,('actual input mallet Y',tick,pad)
            else:
                assert count==frame['layers'],('actual input has duplicate club',tick,pad)
            samples+=1
    return samples


def check_actual_b_entry_art():
    """CDB0 draws the current ground pose before the D05D attack handler."""
    tiles=chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:0x1000])
    metadata=json.loads((BASE/'c64/build/sprite_frames.json').read_text())
    frames={entry['pointer']+layer:entry for entry in metadata for layer in range(entry['layers'])}
    cases=[(0,0)]+[(run,direction) for run in (*range(8),24) for direction in (1,2)]
    for run,direction in cases:
        reference=PlayerReference();machine=start()
        r,L=machine.ram,machine.labels
        for pad in [direction]*run+[0x40|direction]:
            reference.tick(pad)
            joystick=255
            if pad&0x40:joystick&=0xEF
            if pad&1:joystick&=0xF7
            if pad&2:joystick&=0xFB
            machine.joystick=joystick
            machine.call('read_joy');machine.call('normal_player_tick')
        r[L['logical_count']]=0;r[L['actor_mask']]=255
        r[L['view_delta']:L['view_delta']+2]=(-4).to_bytes(2,'little',signed=True)
        machine.call('actor_player')
        count=r[L['logical_count']]
        parka=next(i for i in range(count) if not r[L['LOG_MC']+i] and r[L['LOG_COL']+i]==14)
        frame=frames[r[L['LOG_PTR']+parka]]
        source_x,source_y,pixels=body_pixels(reference,tiles)
        source_base=min(reference.ram[0x201+4*i] for i in range(6))
        assert frame['nes_base']==source_base,('actual B entry pose',run,direction,frame['name'],hex(source_base))
        crop=frame['y_offset']+6
        assert r[L['LOG_X']+parka]==source_x+52 and r[L['LOG_Y']+parka]==source_y+crop+14
        sprite=0x4000+r[L['LOG_PTR']+parka]*64
        for y in range(21):
            for x in range(16):
                bit=r[sprite+y*3+(x+4)//8]&(0x80>>((x+4)%8))
                assert bool(bit)==(pixels[y+crop][x]==2),('actual B entry pixels',run,direction,x,y)
        assert reference.ram[0x21C]==0xF8 and count==frame['layers'],'B entry showed a premature hammer'
    return len(cases)


def player_fixture(labels, pose, players, player, others, x, face):
    """Controlled pose shared by the CPU and native displayed-pixel audits."""
    values = dict(player_count=players, player_index=player, mux_others=others,
                  py=128, pxlo=x & 255, pxhi=x >> 8, face=face, actor_mask=255,
                  logical_count=0, onground=1, move_dir=1, hammer_t=0,
                  attack_t=0, air_init=0, normal_pan_t=0, invul_t=0, lives=3)
    if pose in ('WALK1', 'WALK2'):
        values['hammer_t'] = 2 if pose == 'WALK1' else 6
    elif pose == 'IDLE':
        values['move_dir'] = 0
    elif pose in ('JUMP', 'HAMMER'):
        values.update(onground=0, air_init=1 if pose == 'JUMP' else 12)
    elif pose in ('ATTACK', 'STRIKE'):
        values['attack_t'] = 12 if pose == 'ATTACK' else 5
    result = {labels[name]: value for name, value in values.items()}
    result.update({labels['view_delta']: 0, labels['view_delta']+1: 0,
                   labels['PLAYER_LAND_AGE']+player: 128 if pose == 'STOP' else 0,
                   labels['PLAYER_LAND_Y']+player: 128,
                   labels['GROUND_SWING']+player: int(pose in ('ATTACK', 'STRIKE')),
                   labels['nes_dying']+player: 0})
    return result


def check_runtime_quality():
    """Audit every live pose, both players, stage banks and 9-bit X carry."""
    tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:4096])
    frames = {e['name']: e for e in json.loads((BASE/'c64/build/sprite_frames.json').read_text())}
    poses = ('WALK0', 'WALK1', 'WALK2', 'IDLE', 'STOP', 'JUMP', 'HAMMER', 'ATTACK', 'STRIKE')
    cases = exact = compact = 0
    for bonus in (False, True):
        machine = start(2)
        if bonus:
            machine.call('enter_bonus')
        r, L = machine.ram, machine.labels
        origin = bytes(r)
        for (players, player, others), pose, face, x in itertools.product(
                ((1, 0, 0), (1, 0, 5), (2, 0, 0), (2, 1, 0)), poses, (0, 1), (96, 255)):
            if bonus and pose == 'JUMP':
                continue  # The bonus uses the raised HAMMER pose throughout flight.
            r[:] = origin
            for address, value in player_fixture(L, pose, players, player, others, x, face).items():
                r[address] = value
            machine.call('actor_player')
            entry = frames[f'POPO_{"L" if face else "R"}_{pose}']
            layers = 2 if entry['compact'] or players == 2 or others >= 5 else 3
            expected_count = layers+int(not bonus and pose in ('JUMP', 'HAMMER', 'ATTACK', 'STRIKE'))
            context = (bonus, players, player, others, pose, face, x)
            assert r[L['logical_count']] == expected_count, ('player layer count', context)
            blocks, modes, offsets = [], [], []
            for i in range(layers):
                pointer = r[L['LOG_PTR']+i]
                blocks.append(r[0x4000+pointer*64:0x4000+pointer*64+64])
                mc = r[L['LOG_MC']+i]
                colour = r[L['LOG_COL']+i] & 15
                modes.append((0, 1, 3, 2) if mc else {1: 1, 14 if player == 0 else 4: 2, 10: 3}[colour])
                offset = r[L['LOG_X']+i]+256*r[L['LOG_XHI']+i]-x
                assert offset == (entry['detail_x_offset'] if mc else 0), ('detail alignment', context, i, offset)
                offsets.append(offset)
                expected_y = 128+entry['y_offset']-(8 if pose == 'STRIKE' else 0)
                assert r[L['LOG_Y']+i] == expected_y, ('body alignment', context, i)
            drawn = decode(b''.join(blocks), modes, offsets)
            original = source_frame(tiles, entry, bonus)
            shift = offsets[1] if layers == 2 else 0
            errors = check_pixels(original, drawn, modes, context, shift, player_eyes(entry, layers==2))
            check_jump_face(entry, drawn, layers==2)
            if layers == 3:
                assert errors == 0, context
                exact += 1
            else:
                compact += 1
            cases += 1
    report = dict(status='passed', cases=cases, exact_hires_cases=exact,
                  compact_optimal_cases=compact, parka_pixels_exact=True,
                  normal_and_bonus=True, both_players=True, x_255_carry=True,
                  source='executed NES D17C and CE06 sprite writers',
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/player_sprite_quality.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__=='__main__':
    print('PASS actual jump/hammer cycles and terrain-relative player OAM',check_actual_input_art())
    print('PASS actual B entry and original ground OAM',check_actual_b_entry_art())
    print('PASS runtime player quality',check_runtime_quality())
