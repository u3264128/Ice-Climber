"""Native VICE checks for standing jumps and the original Topi hit reaction."""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json

from test_game import BASE, start
from vice_session import ViceSession


def helper_guard(session):
    image = (BASE/'c64/build/iceclimber_game.prg').read_bytes()
    load = int.from_bytes(image[:2], 'little')
    address = session.labels['__HELPERS_RUN__']
    size = session.labels['__HELPERS_SIZE__']
    source = session.labels['__HELPERS_LOAD__']-load+2
    assert session.read(address, size) == image[source:source+size], 'Relocated helper corruption'


def standing_jump(vice, output, direction, column):
    with ViceSession(f'jump_rest_{direction:02x}', vice) as session:
        session.frame(0xEF)
        session.finish_preview()
        model = start()
        index = 24+column
        for name in ('floor_upper', 'floor_lower'):
            session.write(session.labels[name]+index, 0)
            model.ram[model.labels[name]+index] = 0
        before = bytes(model.ram)
        model.ram[model.labels['wrld']] = 1
        model.ram[model.labels['colw']] = column+8
        model.call('cache_cell')
        # Bring only the controlled hole's display-cache patches across;
        # the native game commits them normally on the following frame.
        for address in range(0xE000, 0xFC00):
            if before[address] != model.ram[address]:
                session.write(address, model.ram[address])
        session.write('patch_any', model.ram[model.labels['patch_any']])
        airborne = False
        positions = []
        for frame in range(45):
            joy = direction & 0xFE if frame == 0 else direction
            session.frame(joy)
            model.frame(joy)
            actual = session.read('curfloor', 9)
            expected = model.ram[0x1A:0x23]
            assert all(actual[i] == expected[i] for i in (0, 1, 4, 5, 8)), \
                ('Native standing jump', direction, frame, list(actual), list(expected))
            positions.append(dict(x=int.from_bytes(actual[4:6], 'little'), y=actual[8]))
            airborne |= not actual[1]
            if frame == 15:
                side = 'right' if direction == 0xF7 else 'left'
                session.capture(output/f'jump_from_rest_{side}.png')
            if airborne and actual[1] and actual[0] == 1:
                break
        assert airborne and actual[0] == 1 and actual[1], 'Did not climb48px from rest'
        assert positions[-1]['y'] == 168
        helper_guard(session)
        return dict(direction='right' if direction == 0xF7 else 'left',
                    prior_runup_frames=0, climbed_pixels=48,
                    frames=len(positions), positions=positions,
                    matches_full_prg_model=True)


def stunned_topi(vice, output):
    """An original seal (object 2) stunned by the ground swing ($D3DF)."""
    from test_topi_sprites import normal_gameplay_sprites, TOPI_OVERLAY_PTR
    from transplant_objects import map_ram
    with ViceSession('topi_original_stars', vice) as session:
        session.frame(0xEF)
        session.finish_preview()
        sprite_bank = normal_gameplay_sprites()
        assert session.read(0x5000, len(sprite_bank)) == sprite_bank
        port = session.read(1)
        # Controlled same-floor contact, with an intact original ground.
        # Only setup changes RAM; subsequent movement is actual FIRE/idle.
        for name, value in (('pxlo', 120), ('pxhi', 0), ('py', 216),
                            ('curfloor', 0), ('face', 0), ('onground', 1),
                            ('move_dir', 0), ('walk_time', 0), ('skid_t', 0),
                            ('invul_t', 100)):
            session.write(name, value)
        for nes, value in ((0x93, 0xFF), (0x9E, 120-52+16), (0xA9, 0xC8), (0xB4, 1), (0xBF, 0xFF),
                           (0x03EA, 5), (0x03A8, 0x40), (0x03DF, 0xA0)):
            session.write(map_ram(nes), value)
        state = map_ram(0x93)
        session.frame(0xEF)
        for _ in range(24):
            if session.read(state) != b'\xff':
                break
            session.frame()
        assert session.read(state) == b'\x01', 'The ground swing did not stun the seal'
        positions = []
        for frame in range(24):
            session.frame()
            assert session.read(state) == b'\x01', 'Seal did not remain stunned on intact ground'
            assert session.read(map_ram(0xA9)) == b'\xc8', 'Seal fell through the platform'
            positions.append(session.read(map_ram(0x9E))[0])
            if frame == 7:
                session.capture(output/'topi_stunned_original.png')
        assert len(set(positions)) > 1, 'Stunned seal did not move sideways'
        pointers = range(TOPI_OVERLAY_PTR, TOPI_OVERLAY_PTR+4)
        count = session.read('logical_count')[0]
        shown = session.read('LOG_PTR', count)
        modes = session.read('LOG_MC', count)
        seal = [i for i, pointer in enumerate(shown) if pointer in pointers]
        assert len(seal) == 2 and all(modes[i] == 0 for i in seal), 'Stars lost hires pixels'
        assert session.read('lives') == bytes([3])
        assert session.read(0x5000, len(sprite_bank)) == sprite_bank
        session.write('bonus_requested', 1)
        session.frame()
        bonus = (BASE/'c64/build/game_sprites_bonus.bin').read_bytes()
        assert session.read('state') == b'\x03' and session.read(0x5000, len(bonus)) == bonus
        assert session.read(1) == port, '6510 I/O mapping changed during the scene swap'
        helper_guard(session)
        return dict(ground_swing_stuns_seal=True, stays_on_platform=True, moves_sideways=True,
                    original_stars_selected=True, both_layers_hires=True,
                    immutable_normal_sprites=True, original_fruit_restored=True,
                    positions=positions, lives=3)


def main():
    parser = argparse.ArgumentParser()
    add_vice_argument(parser)
    arguments = parser.parse_args()
    output = BASE/'docs/verification'
    checksum = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    report = dict(status='passed', prg_sha256=checksum)
    report['standing_jumps'] = [standing_jump(arguments.vice, output, direction, column)
                                for direction, column in ((0xF7, 3), (0xFB, 2))]
    report['seal'] = stunned_topi(arguments.vice, output)
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest() == checksum, \
        'Release changed during native validation'
    (output/'jump_topi_native.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS native standing left/right jumps, original ground-swing seal stars/sideways stun and helper memory')


if __name__ == '__main__':
    main()
