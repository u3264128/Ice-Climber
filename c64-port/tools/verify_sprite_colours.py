"""Check ice sprite shades in VICE's displayed pixels, in both directions."""
import argparse
import hashlib
import json

from tool_paths import add_vice_argument
from transplant_objects import map_ram
from verify_display_pixels import X0, grab
from vice_session import BASE, ViceSession


def check(vice):
    output = BASE/'docs/verification'
    checked = 0
    shades = set()
    with ViceSession('ice_colours', vice) as session:
        session.frame(0xEF)
        session.finish_preview()
        session.write('paused', 1)
        for obj in range(11):
            session.write(map_ram(0x03E8+obj), 0)
        # Keep palette samples in open air; wall occlusion has its own check.
        for direction in (0xFF, 1):
            for obj, tile in enumerate((0xAC, 0x10, 0x0E, 0x0C, 0x12, 0x14), 5):
                for nes, value in ((0x91+obj, 255), (0x9C+obj, 64+(obj-5)*24),
                                   (0xA7+obj, 100), (0xBD+obj, direction),
                                   (0x03DD+obj, tile), (0x03E8+obj, 0x48 if obj < 8 else 0x58)):
                    session.write(map_ram(nes), value)
            for _ in range(4):
                session.frame()
            canvas = grab(session)
            count = session.read('logical_count')[0]
            pointers = session.read('LOG_PTR', count)
            colours = session.read('LOG_COL', count)
            xs = session.read('LOG_X', count)
            xhigh = session.read('LOG_XHI', count)
            ys = session.read('LOG_Y', count)
            ice = [i for i, pointer in enumerate(pointers) if 0xB0 <= pointer < 0xBC]
            assert len(ice) == 6, ('missing ice sprites', pointers)
            assert session.read(0xD025)[0] & 15 == 1 and session.read(0xD026)[0] & 15 == 14
            for index in ice:
                assert colours[index] & 15 == 6, 'Ice shadows lost their separate colour'
                data = session.read(0x4000+pointers[index]*64, 63)
                for y in range(16):
                    for x in range(8):
                        bits = data[y*3+x//8] >> (6-(x & 6)) & 3
                        if not bits:
                            continue
                        want = (0, 1, 6, 14)[bits]
                        got = canvas[ys[index]+y][xs[index]+256*xhigh[index]+X0+x]
                        assert got == want, (direction, index, x, y, want, got)
                        shades.add(got)
                        checked += 1
            session.capture(output/f'ice_colours_{direction:02x}.png')
    assert shades == {1, 6, 14}, shades
    return dict(status='passed', displayed_pixels=checked, directions=2,
                sprite_colours=sorted(shades), sprites_per_direction=6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_vice_argument(parser)
    args = parser.parse_args()
    report = check(args.vice)
    report['prg_sha256'] = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    (BASE/'docs/verification/sprite_colours.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS displayed ice sprite colours', report['displayed_pixels'])


if __name__ == '__main__':
    main()
