"""Native hidden input, attract lifecycle, and displayed mountain31 posts."""
import argparse
import hashlib
import json

from level_codes import CODES
from original_stones import stone_cells
from measure_display_scroll import normal
from tool_paths import add_vice_argument
from verify_display_pixels import X0, grab
from verify_vice import protected
from verify_scroll import check_normal
from vice_session import BASE, ViceSession


def stop(session):
    # Feed RUN/STOP at its CIA sample; restore the read before taking guards.
    first = session.labels['read_joy']
    code = session.read(first, session.labels['game_tick']-first)
    pattern = bytes.fromhex('a97f8d00dcad01dc2980')
    assert code.count(pattern) == 1
    address = first+code.index(pattern)+5
    present = bytes.fromhex('a000ad01dcc9ff')
    assert code.count(present) == 1
    all_rows = first+code.index(present)+2
    session.write(address, bytes.fromhex('a900ea'))
    session.write(all_rows, bytes.fromhex('a900ea'))
    try:
        session.frame()
    finally:
        session.write(address, bytes.fromhex('ad01dc'))
        session.write(all_rows, bytes.fromhex('ad01dc'))
    assert session.read('state') == b'\0'
    assert session.read('paused') == b'\0'


def title(vice):
    with ViceSession('title_codes_demo', vice) as s:
        for _ in range(3):
            s.frame()
        original = protected(s)
        shown = s.read(0x4000, 1000)+bytes(v & 15 for v in s.read(0xD800, 1000))
        canvas = grab(s)
        assert any(any(row) for row in canvas), 'title display is blank'
        for mountain in range(1, 33):
            s.title_code(mountain)
            # Colour RAM contains four-bit cells; upper bus bits vary with
            # the instruction/raster phase and are not displayed colours.
            actual = s.read(0x4000, 1000)+bytes(v & 15 for v in s.read(0xD800, 1000))
            assert actual == shown, (mountain, [(i, a, b) for i, (a, b) in enumerate(zip(actual, shown)) if a != b][:12])
            assert grab(s) == canvas, ('code echoed on screen', mountain)
        s.title_code(31)
        # Count actual main-loop updates from the last character's reset.
        elapsed = int.from_bytes(s.read('attrlo', 2), 'little')
        for _ in range(1173-elapsed-1):
            s.frame()
        assert s.read('state') == b'\0'
        s.frame()
        assert s.read('state') == b'\4' and s.read('demo_active') == b'\1'
        assert s.read('mountain') == b'\1' and s.read(0xD418)[0] & 15 == 0
        s.finish_preview()
        initial = s.read('pxlo', 2)
        moved = False
        # Let the original scripted movement reach its natural fall exit.
        for frame in range(10000):
            s.frame()
            moved |= s.read('pxlo', 2) != initial
            if s.read('state') == b'\0':
                break
        else:
            raise AssertionError('demo did not return naturally')
        assert moved and s.read('selected_mountain') == b'\x1F'
        assert s.read(0xD418)[0] & 15 == 15
        s.frame(0xEF)
        assert s.read('mountain') == b'\x1F' and not s.read('demo_active')[0]
        stop(s)                 # escape during the opening flyover
        s.frame()
        s.write('attrlo', (1172).to_bytes(2, 'little'))
        s.frame()
        assert s.read('mountain') == b'\2' and s.read('demo_active') == b'\1'
        s.frame(0xEF)
        assert s.read('state') == b'\0'
        s.frame(0xEF)
        assert s.read('state') == b'\0', 'held fire restarted after leaving demo'
        for _ in range(3):
            s.frame()
        assert grab(s) == canvas, 'return did not restore the visible title'
        assert protected(s) == original
        s.capture(BASE/'docs/verification/title_hidden_codes.png')
        return dict(codes=32, no_visible_echo=True, idle_pal_frames=1173,
                    natural_demo_frames=frame+1, physical_fire_exit=True,
                    run_stop_exit=True, readonly_intact=True)


def posts(vice, players):
    mountain = 31
    checked, positions = 0, set()
    with ViceSession(f'stone_columns_{players}p', vice) as s:
        original = protected(s)
        if players == 2:
            s.frame(0xFD)
            s.frame()
        s.title_code(mountain)
        s.frame(0xEF)
        s.finish_preview()
        s.write('paused', 1)
        glyph = s.read(0x4800+224*8, 8)
        for camera in range(0, 241, 48):
            s.write('normal_camera', camera.to_bytes(2, 'little'))
            s.write('cam', camera//48)
            for _ in range(24):
                s.frame()
            assert int.from_bytes(s.read('visual_camera', 2), 'little') == camera
            view = s.read('last_view_row')[0]
            screen = 0x4000+1024*s.read('screen_buffer')[0]
            chars, colours = s.read(screen, 1000), s.read(0xD800, 1000)
            canvas = grab(s)
            fine = s.read('view_fine')[0]
            count = s.read('logical_count')[0]
            xs, xhi, ys = s.read('LOG_X', count), s.read('LOG_XHI', count), s.read('LOG_Y', count)
            for row, column in stone_cells(mountain):
                sy = view+24-row
                y0, x0 = 47+fine+8*sy, X0+24+8*(column+4)
                if not (0 <= sy < 25 and 55 <= y0 and y0+8 <= 246):
                    continue
                assert chars[sy*40+column+4] == 224, (players, camera, row, column)
                assert colours[sy*40+column+4] & 8, ('missing MC colour', row, column)
                palette = (0, 14, 6, 1) if row >= 32 else (0, 8, 9, 7) if row >= 14 else (0, 13, 5, 7)
                for y, byte in enumerate(glyph):
                    for x in range(8):
                        px, py = x0+x, y0+y
                        if any(xs[i]+256*xhi[i]+X0 <= px < xs[i]+256*xhi[i]+X0+24
                               and ys[i] <= py < ys[i]+21 for i in range(count)):
                            continue
                        bits = (byte >> (6-(x & 6))) & 3
                        expected = {palette[bits]}
                        # The palette IRQ changes shared shades at the first
                        # scanlines of rows13/31; cell colour remains local.
                        if bits in (1, 2) and row in (13, 31) and y < 2:
                            expected.add(((0, 8, 9, 7) if row == 13 else (0, 14, 6, 7))[bits])
                        assert canvas[py][px] in expected, ('post pixel', players, camera, row, column, x, y, canvas[py][px], expected)
                        checked += 1
                positions.add((row, column))
            if camera in (0, 144):
                s.capture(BASE/f'docs/verification/stone31_{players}p_cam{camera}.png')
        assert positions == set(stone_cells(mountain)), ('unseen posts', positions)
        assert protected(s) == original
        stop(s)
    return dict(players=players, mountain=mountain, displayed_cells=len(positions),
                displayed_pixels=checked, cameras=6, readonly_intact=True,
                scrolling=check_normal(normal(vice, mountain, players)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_vice_argument(parser)
    args = parser.parse_args()
    report = dict(status='passed', title=title(args.vice),
                  posts=[posts(args.vice, players) for players in (1, 2)],
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/title_stones_native.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS native title codes, attract demo, and mountain31 stone pixels', report)


if __name__ == '__main__':
    main()
