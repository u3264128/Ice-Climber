"""VICE: columns survive hammering and Topis cross behind stone faces."""
import argparse
import hashlib
import json

from tool_paths import add_vice_argument
from measure_display_scroll import DisplayTrace
from transplant_objects import map_ram
from verify_display_pixels import X0, grab, own_pixels
from verify_vice import protected
from vice_session import BASE, ViceSession


def clear_objects(s):
    for obj in range(11):
        s.write(map_ram(0x91+obj), 0)
        s.write(map_ram(0x3E8+obj), 0)
    s.write(map_ram(0x48), bytes([255])*8)


def place_players(s, players, first_x):
    for player in range(players):
        block = bytearray(s.read(0x200+32*player, 32))
        x = (first_x if player == 0 else 220)+52
        block[3:5] = x.to_bytes(2, 'little')
        block[5:9] = bytes((216, 216, 0, 1))
        block[10:26] = bytes(16)
        s.write(0x200+32*player, block)
    s.write('GROUND_SWING', [0, 0])
    s.sync_player_zero()


def run(vice, players, direction):
    with ViceSession(f'stone_rules_{players}p_{direction}', vice) as s:
        guard = protected(s)
        if players == 2:
            s.frame(0xFD)
            s.frame()
        s.title_code(31)
        s.frame(0xEF)
        s.finish_preview()
        clear_objects(s)
        place_players(s, players, 80)
        initial_map = s.read(0x400, 0x1D8)
        column = [(0xE000+row*32+15) for row in range(4, 9)]
        assert all(s.read(address) == b'\xE0' for address in column)
        for joy in [0xF7]*30+[0xE7]*40+[0xF7]*10:
            s.frame(joy)
            x = int.from_bytes(s.read('pxlo', 2), 'little')-52
            assert x <= 104, ('hammer walked through column', players, x)
            assert s.read(0x400, 0x1D8) == initial_map
            assert all(s.read(address) == b'\xE0' for address in column)
        assert x == 104
        place_players(s, players, 48)
        clear_objects(s)
        start = 100 if direction == 1 else 140
        for address, value in ((0x93, 255), (0x9E, start), (0xA9, 200),
                               (0xB4, 1), (0xBF, direction & 255), (0x3A8, 128),
                               (0x3BE, 16), (0x3DF, 0xA0), (0x3EA, 0x40)):
            s.write(map_ram(address), value)
        positions, hidden, visible = [], 0, 0
        captured = False
        previous = None
        trace = DisplayTrace(s, record_sprites=True)
        for frame in range(80):
            current = trace.next()
            x = s.read(map_ram(0x9E))[0]
            positions.append(x)
            shown, previous = previous, current
            if shown is None:
                continue
            events = shown['sprites']
            expected_priority = sum((1 << i) for i, event in enumerate(events) if event[3] & 128)
            assert s.read(0xD01B)[0] == expected_priority, ('VIC priority', players, frame)
            if not 108 <= x <= 128:
                continue
            background = trace.previous_background
            canvas = grab(s)
            for event in events:
                _, _, pointer, colour, mode = event
                if not (0x6C <= pointer < 0x78):
                    continue
                assert colour & 128
                raw = (event[0], event[1], pointer, colour & 15, mode)
                whole = {(y, x): c for y, x, c in own_pixels(s, raw)}
                shown = {(y, x): c for y, x, c in own_pixels(s, event, background=background)}
                for (y, px), colour in whole.items():
                    # Only the real ground column, away from the players.
                    if not X0+24+19*8 <= px < X0+24+20*8:
                        continue
                    if (y, px) in shown:
                        assert canvas[y][px] == colour, ('visible Topi pixel', players, direction, frame, y, px,
                                                         canvas[y][px], colour, event)
                        visible += 1
                    else:
                        assert canvas[y][px] in (5, 7), ('stone did not hide Topi', players, direction, frame, y, px, canvas[y][px])
                        hidden += 1
            if hidden and not captured:
                s.capture(BASE/f'docs/verification/topi_behind_stone_{players}p_{direction}.png')
                captured = True
        assert min(positions) < 120 and max(positions) > 128, positions
        assert hidden and visible, ('column overlap not exercised', hidden, visible)
        assert all(s.read(address) == b'\xE0' for address in column)
        assert protected(s) == guard
        return dict(players=players, direction=direction, mountain=31, hammer_frames=80,
                    topi_frames=80, hidden_pixels=hidden, visible_pixels=visible,
                    column_intact=True, player_stopped_at_x=104)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_vice_argument(parser)
    args = parser.parse_args()
    report = dict(status='passed', cases=[run(args.vice, players, direction)
                  for players in (1, 2) for direction in (1, -1)],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/stone_rules_native.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS native permanent columns, hammer strikes, and Topi occlusion', report)


if __name__ == '__main__':
    main()
