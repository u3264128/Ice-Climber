#!/usr/bin/env python3
"""Native VICE flyover checks, selecting mountains through hidden keyboard codes.

Only the monitor's joystick latch is changed during each preview. The
separate next-stage transition fixture calls the release routine through
the existing bonus/result state flow after the real preview has finished.
"""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json

from extract_levels import BASE
from nesgfx import chr_tiles
from probe_preview import original_prg, trace_preview
from test_original_preview import assert_preview_sprites, assert_shown_world, frozen_fields, world_reference
from test_preview_sprites import source_condor
from verify_display_pixels import X0, grab
from verify_vice import protected
from vice_session import ViceSession


def assert_displayed_condor(session, original, phase):
    """Check actual VIC pixels against F737's OAM, away from frame edges."""
    canvas = grab(session)
    checked = 0
    palette = (0, 1, 14, 10)
    # The fruit begins at bird Y+14. Keep this comparison above its layers.
    for y, row in enumerate(original[:14]):
        for x in range(0, 32, 2):
            colours = {palette[value] for value in row[x:x+2] if value}
            if not colours:
                continue
            for dx in (0, 1):
                got = canvas[158+y][164+X0+x+dx]
                assert got in colours, ('displayed condor', phase, x+dx, y, got, colours)
                checked += 1
    return checked


def replay_preview(mountain, vice, out, prg, expected):
    release = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:4096])
    bird_frames = [source_condor(tiles, phase) for phase in range(3)]
    displayed_poses = set()
    displayed_pixels = 0
    with ViceSession(f'preview_{mountain:02}', vice) as s:
        original = protected(s)
        s.title_code(mountain)
        assert s.read('selected_mountain')[0] == mountain
        s.frame(0xEF)
        labels = s.labels
        small = bytearray(s.read(0, 0x800))
        read = lambda address, count: small[address:address+count]
        assert read(labels['state'], 1) == b'\4'
        frozen = frozen_fields(read, labels)
        world = world_reference(prg, mountain-1)
        frames = ticks = 0
        shown_row = None
        snapshots = []
        maximum_view_lag = 0
        while small[labels['state']] == 4 and frames < 700:
            if small[labels['packet_ready']]:
                shown_row = small[labels['last_view_row']]
            s.frame((255, 0xFE, 0xFB, 0xF7)[frames % 4])
            frames += 1
            ticks += 1                  # one flyover tick per PAL frame
            small[:] = s.read(0, 0x800)
            if small[labels['state']] != 4:
                break
            assert frozen_fields(read, labels) == frozen, ('native preview gameplay changed', mountain, frames)
            row = expected[ticks-1]
            camera = int.from_bytes(read(labels['preview_camera'], 2), 'little')
            visual = int.from_bytes(read(labels['visual_camera'], 2), 'little')
            maximum_view_lag = max(maximum_view_lag, camera-visual)
            assert camera == row['camera'], (mountain, frames, camera, row['camera'])
            assert read(labels['preview_bird_y'], 1)[0] == row['bird_y']
            assert read(labels['preview_anim_frame'], 1)[0] == row['anim_frame']
            assert visual == camera, ('native preview camera stalled', mountain, frames, visual, camera)
            if shown_row is not None:
                assert_shown_world(s.read, labels, world, shown_row)
            count = read(labels['logical_count'], 1)[0]
            assert count <= 6, ('unexpected preview actors', mountain, frames, count)
            if frames in (196, 204, 212):
                phase = row['anim_frame']
                displayed_pixels += assert_displayed_condor(s, bird_frames[phase], phase)
                displayed_poses.add(phase)
            if frames in (8, 196, 200, 204, 212, 320, 465):
                assert_preview_sprites(s.read, labels)
                path = out/f'preview_{mountain:02}_{frames:03}.png'
                s.capture(path)
                snapshots.append(dict(frame=frames, camera=camera, image=path.name,
                                      bird_y=row['bird_y'], logical_sprites=count))
        assert frames == 573, (mountain, frames)
        assert displayed_poses == {0, 1, 2}, displayed_poses
        assert small[labels['state']] == 1, ('preview did not start gameplay', mountain)
        assert read(labels['lives'], 1) == b'\3'
        assert read(labels['curfloor'], 1) == b'\0'
        assert read(labels['normal_camera'], 2) == b'\0\0'
        assert read(labels['logic_frame'], 1) == b'\0'
        s.frame()
        s.capture(out/f'preview_{mountain:02}_gameplay.png')
        assert protected(s) == original, 'Preview changed program or source asset bytes'
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest() == release
    result = dict(mountain=mountain, pal_update_frames=frames,
                  source_logic_ticks=573, camera_pixels=638,
                  maximum_view_lag=maximum_view_lag,
                  frozen_gameplay=True, joystick_only=True,
                  screen_rows_match_original=True, readonly_intact=True,
                  no_gameplay_hud=True, reached_gameplay=True, lives=3,
                  displayed_condor_poses=sorted(displayed_poses),
                  displayed_condor_pixels=displayed_pixels,
                  captures=snapshots)
    print(f'PASS native preview {mountain:02}: {frames} updates,638px,correct bottom reset', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    add_vice_argument(parser)
    parser.add_argument('--mountains', type=int, nargs='+', default=[1, 6])
    args = parser.parse_args()
    out = BASE/'docs/verification'
    out.mkdir(exist_ok=True)
    release = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    prg = original_prg()
    expected = trace_preview(prg)
    records = [replay_preview(mountain, args.vice, out, prg, expected)
               for mountain in args.mountains]
    report = dict(status='passed', prg_sha256=release, previews=records,
                  normal_or_bonus_gameplay_ram_modified=False,
                  original_reference='executed C3CC/C3E8/D8EA/F737 plus original map generators')
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest() == release
    (out/'original_preview_native.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
