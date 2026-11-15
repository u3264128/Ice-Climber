"""Check live moving-cloud writes against VIC fetches in native PAL VICE."""
from tool_paths import add_vice_argument
import argparse
import hashlib
import json
import struct

from test_scroll_cloud_edges import original_cloud_mask
from verify_mux_timing import registers
from vice_session import BASE, ViceSession


def return_points(session, routine, target, size):
    address = session.labels[routine]
    call = b'\x20' + session.labels[target].to_bytes(2, 'little')
    code = session.read(address, size)
    return [address+i+3 for i in range(size-2) if code[i:i+3] == call]


def local_label(session, scope, name):
    """Address of the cheap local label in a global label's scope."""
    start = session.labels[scope]
    entries = []
    for line in (BASE/'c64/build/game.lbl').read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            entries.append((int(parts[1], 16), parts[2].lstrip('.')))
    end = min(a for a, n in entries if a > start and not n.startswith('@') and not n.startswith('__'))
    found = [a for a, n in entries if n == name and start < a < end]
    assert len(found) == 1, (scope, name, found)
    return found[0]


def cloud_timing(vice):
    with ViceSession('normal_cloud_patch_deadlines', vice) as s:
        s.write('selected_mountain', 26)
        s.frame(0xFD)
        s.frame()
        s.frame(0xEF)
        s.finish_preview()
        # Camera one has three simultaneously moving cloud rows (2, 3, 4).
        s.write('paused', 1)
        s.write('cam', 1)
        s.write('normal_camera', [48, 0])
        for _ in range(20):
            s.frame()
        for base, x in ((0x200, 155), (0x220, 190)):
            for offset, value in ((3,x), (4,0), (5,168), (6,168), (7,1),
                                  (8,1), (11,1), (25,255)):
                s.write(base+offset, value)
        s.sync_player_zero()
        s.write('paused', 0)
        # Normal play commits each cloud floor in cloud_commit_normal: the
        # first cloud's glyphs are final at @second (shifted, copied or
        # unchanged), the second cloud's at @patch.
        glyph_ends = [local_label(s, 'cloud_commit_normal', '@second'),
                      local_label(s, 'cloud_commit_normal', '@patch')]
        patch_ends = return_points(s, 'patch_one_row', 'patch_row', 108)
        assert len(glyph_ends) == len(patch_ends) == 2
        # The second call patches the hidden buffer and has no VIC deadline.
        front_patch_end = patch_ends[0]
        for pc in (*glyph_ends, front_patch_end):
            s.m.command(0x12, struct.pack('<HHBBBB', pc, pc, 1, 1, 4, 0))
        minima = {'glyph': None, 'screen': None}
        counts = dict.fromkeys(minima, 0)
        misses = []
        for frame in range(300):
            while True:
                s.m.resume()
                reg = registers(s.m)
                pc, line, cycle = (reg[k] for k in ('PC', 'LIN', 'CYC'))
                if pc == s.labels['main_loop']:
                    break
                assert pc in (*glyph_ends, front_patch_end), reg
                if s.read('state') != b'\1':
                    continue
                kind = 'screen' if pc == front_patch_end else 'glyph'
                if kind == 'screen':
                    row = s.read('copy_row')[0]
                    if row not in (14, 20, 26):
                        continue
                else:
                    floor = s.read('cloud_slot')[0]
                    second = pc == glyph_ends[1]
                    row = floor*6+2
                    phase = s.read(0x0640+floor if second else s.labels['GLYPH_PHASE']+floor)[0]
                    glyph = (84 if second else 56)+4*(floor-1)
                    profile = 2 if s.read(s.labels['floor_types']+floor)[0]&0xE0 == 0xE0 else int(second)
                    assert s.read(0x4800+glyph*8, 32) == original_cloud_mask(profile, phase)
                screen_y = s.read('last_view_row')[0]+24-row
                fine = s.read('split_open')[0]&7
                fetch = 48+fine+screen_y*8
                if not 0 <= screen_y < 25 or fetch >= 247:
                    continue
                beam = (line-312 if line >= 250 else line)*63+cycle
                slack = fetch*63+14-beam
                counts[kind] += 1
                minima[kind] = slack if minima[kind] is None else min(minima[kind], slack)
                if slack <= 0:
                    misses.append(dict(frame=frame, kind=kind, row=row, line=line,
                                       cycle=cycle, fetch=fetch, slack=slack))
        assert counts['glyph'] >= 500 and counts['screen'] >= 50, counts
        return dict(frames=300, mountain=26, players=2, writes=counts,
                    minimum_cycles_before_fetch=minima, missed=misses)


def main():
    parser = argparse.ArgumentParser()
    add_vice_argument(parser)
    args = parser.parse_args()
    prg = BASE/'c64/build/iceclimber_game.prg'
    release = hashlib.sha256(prg.read_bytes()).hexdigest()
    result = cloud_timing(args.vice)
    assert hashlib.sha256(prg.read_bytes()).hexdigest() == release
    report = dict(prg_sha256=release, status='failed' if result['missed'] else 'passed', **result)
    (BASE/'docs/verification/normal_cloud_timing.json').write_text(json.dumps(report, indent=2)+'\n')
    assert not result['missed'], result['missed'][:8]
    print('PASS moving cloud glyph and screen deadlines', result)


if __name__ == '__main__':
    main()
