#!/usr/bin/env python3
"""Check the pixels VICE actually displayed, one PAL frame at a time.

The register checks (verify_scroll, verify_mux_timing) prove the values the
VIC is given. This check reads VICE's rendered canvas instead. At each frame
IRQ the canvas below that line still holds the previous frame, whose camera
and raster sprite events are known. For every frame:

* background: with all sprite boxes masked, each 8-line band must equal the
  previous frame shifted by the camera change. A band that differs must not
  fit any other shift better (no tearing, late buffer swap or colour lag);
  local changes such as moving clouds fit the camera shift.
* sprites: every scheduled raster event's own-colour pixels must be shown.
* camera: normal pans move 4 pixels in each of 12 frames; the bonus camera
  moves 0-2 pixels and changes speed by at most 1 pixel per frame.
Deliberate multiplexer drops (logical > scheduled) are counted.
"""
from tool_paths import add_vice_argument
import argparse
import json
import random
import struct
from collections import Counter

from pixel_checks import band_comparison, sprite_mask

import measure_display_scroll
from measure_display_scroll import DisplayTrace
from vice_session import ViceSession, BASE

X0 = 116                # canvas column = sprite X + X0; canvas row = sprite Y + line
TOP, BOTTOM, LEFT, RIGHT = 56, 246, 136, 456   # inner playfield on the canvas


def grab(s):
    data = s.m.command(0x84, b'\x01\x00')
    fields = struct.unpack_from('<I', data)[0]
    width, height = struct.unpack_from('<HH', data, 4)
    length = struct.unpack_from('<I', data, fields)[0]
    raw = bytes(value & 15 for value in data[fields+4:fields+4+length])
    assert len(raw) == width * height, 'Unexpected VICE canvas size'
    return tuple(raw[row*width:(row+1)*width] for row in range(height))


def own_pixels(s, event, opaque=False, background=None):
    """(row, column, colour) of the pixels drawn in the sprite's own colour;
    with opaque, every pixel the sprite covers (also the shared multicolours)."""
    x, y, pointer, colour, multicolour = event
    data = s.read(0x4000+pointer*64, 63)
    out = []
    for line in range(21):
        bits = int.from_bytes(data[line*3:line*3+3], 'big')
        if multicolour:
            out += [(y+line, x+X0+2*p+h, colour & 15) for p in range(12)
                    if ((bits >> (22-2*p)) & 3 == 2 or (opaque and (bits >> (22-2*p)) & 3))
                    for h in (0, 1)]
        else:
            out += [(y+line, x+X0+p, colour & 15) for p in range(24) if bits >> (23-p) & 1]
    # Rows from BOTTOM on lie in the lower border (24-row mode).
    out = [(r, c, v) for r, c, v in out if TOP <= r < BOTTOM and LEFT <= c < RIGHT]
    # VIC sprite-to-sprite priority is resolved before background priority:
    # even a terrain-hidden sprite can cover another sprite's pixels.
    if colour & 128 and not opaque:
        assert background is not None, 'Behind-terrain pixels need the displayed frame snapshot'
        chars, colours, font, top = background
        def foreground(row, column):
            sy, py = divmod(row-top, 8)
            sx, px = divmod(column-X0-24, 8)
            if not (0 <= sy < 25 and 0 <= sx < 40):
                return False
            index = sy*40+sx
            bits = font[chars[index]*8+py]
            return bool(bits & (0x80 >> (px & 6))) if colours[index] & 8 else bool(bits & (0x80 >> px))
        out = [(r, c, v) for r, c, v in out if not foreground(r, c)]
    return out


def scenario(case):
    route = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())['normal']
    if case == 'route1':
        return dict(players=1, state=1, inputs=route)
    if case == 'route2':
        return dict(players=2, state=1, inputs=route)
    if case == 'random':
        rng, joy, inputs = random.Random(1), 0xFF, []
        for _ in range(1200):
            if rng.random() < 0.12:
                joy = rng.choice((0xFF, 0xF7, 0xFB, 0xF6, 0xFA, 0xFE))
            inputs.append(joy)
        return dict(players=2, state=1, inputs=inputs, mountain=3)
    if case == 'bonus':
        return dict(players=1, state=3, bonus=True,
                    inputs=[0xFE if i % 70 in range(10, 14) else 0xFF for i in range(280)])
    raise ValueError(case)


def run(case, vice):
    sc = scenario(case)
    inputs, players = sc['inputs'], sc['players']
    res = dict(case=case, frames=0, deltas=[], tearing=[], lost=[], drop_frames=0, local_bands=0)
    with ViceSession(f'display_pixels_{case}', vice) as s:
        if players == 2:
            s.frame(0xFD)
            s.frame()
        s.write('selected_mountain', sc.get('mountain', 1))
        s.frame(0xEF)
        s.finish_preview()
        if sc.get('bonus'):
            s.write('bonus_requested', 1)
            for _ in range(5):
                s.frame()
            # Controlled ledge fixture: a real eased camera climb.
            for name, value in (('pxlo', 92), ('pxhi', 0), ('py', 88), ('prevpy', 88)):
                s.write(name, value)
            for offset, value in ((3, 92), (4, 0), (5, 88), (6, 88)):
                s.write(s.labels['PLAYER_STATES']+offset, value)
        played = 0

        def joy():
            return inputs[played] if played < len(inputs) else 0xFF

        def advance(session, _):
            nonlocal played
            if session.left_out()[0] > 0:
                res['drop_frames'] += 1
            played += 1
            session.write(0x4F, joy())
            session.write(0x4E, joy() if players == 2 else 0xFF)

        trace = DisplayTrace(s, advance, record_sprites=True)
        previous = shown = None
        while played < len(inputs):
            sample = trace.next(joy(), joy() if players == 2 else 0xFF)
            pixels = grab(s)
            if sample['state'] != sc['state']:
                break
            if shown is not None and shown['displayed_camera'] is not None:
                res['frames'] += 1
                mask = sprite_mask(pixels, shown['sprites'], X0)
                drawn = [own_pixels(s, event, background=trace.previous_background) for event in shown['sprites']]
                covers = [own_pixels(s, event, opaque=True, background=trace.previous_background) for event in shown['sprites']]
                for index, event in enumerate(shown['sprites']):
                    # Another figure may lie on top (the climbers come first,
                    # as in the original OAM): only uncovered pixels count.
                    others = {(r, c) for k, other in enumerate(covers) if k != index
                              for r, c, _ in other}
                    own = [(r, c, v) for r, c, v in drawn[index] if (r, c) not in others]
                    if len(own) >= 6 and sum(pixels[r][c] == v for r, c, v in own) < len(own)//2:
                        res['lost'].append((res['frames'], event))
                if previous is not None:
                    old_pixels, old_shown, old_mask = previous
                    d = shown['displayed_camera']-old_shown['displayed_camera']
                    res['deltas'].append(d)
                    for band in range(TOP, BOTTOM-8, 8):
                        mismatch = band_comparison(pixels, old_pixels, mask, old_mask, band, d, LEFT, RIGHT)
                        here = mismatch(d)
                        if here <= 40:
                            continue
                        if d and band == TOP:
                            continue        # rows entering below the blank top lines
                        best = min(range(-12, 13), key=mismatch)
                        if mismatch(best) < here:
                            res['tearing'].append((res['frames'], band, d, here, best, mismatch(best)))
                        else:
                            res['local_bands'] += 1
                previous = (pixels, shown, mask)
            shown = sample
    return res


def check(res):
    case, deltas = res['case'], res['deltas']
    assert res['frames'] > 100, res
    assert not res['lost'], (case, 'scheduled sprites missing on screen', res['lost'][:5])
    assert not res['tearing'], (case, 'background shifted unlike the camera', res['tearing'][:5])
    if case.startswith('route') or case == 'random':
        assert set(deltas) <= {0, 4}, (case, Counter(deltas))
        runs = ''.join('4' if d else '0' for d in deltas).split('0')
        assert all(len(run) in (0, 12) for run in runs), (case, 'pan not 12 x 4 pixels')
    else:
        assert set(deltas) <= {0, 1, 2} and 2 in deltas, (case, Counter(deltas))
        assert all(abs(b-a) <= 1 for a, b in zip(deltas, deltas[1:])), (case, deltas)
    return dict(frames=res['frames'], camera_deltas=dict(Counter(deltas)),
                pans=''.join('4' if d == 4 else '0' for d in deltas).count('4'*12),
                local_changes=res['local_bands'], deliberate_drop_frames=res['drop_frames'],
                missing_sprites=0, tearing_bands=0)


def main():
    p = argparse.ArgumentParser()
    add_vice_argument(p)
    p.add_argument('--case', action='append', choices=('route1', 'route2', 'random', 'bonus'))
    args = p.parse_args()
    report = {}
    for case in args.case or ('route1', 'route2', 'random', 'bonus'):
        report[case] = check(run(case, args.vice))
        print('PASS', case, report[case], flush=True)
    out = BASE/'docs/verification/display_pixels.json'
    if not args.case:
        out.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('PASS displayed VICE pixels: background follows the camera, every scheduled sprite shown')


if __name__ == '__main__':
    measure_display_scroll.IRQ_STOPS = max(measure_display_scroll.IRQ_STOPS, 400)
    main()
