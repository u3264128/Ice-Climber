#!/usr/bin/env python3
"""Row patch marks against the cells they were asked to cover.

Random sequences of the PRG's own marking routines on one cache row:
single columns (characters, or characters and colours: patch_mark), the
changed cells of a moving cloud (patch_cloud_span, columns work_lo-4 to
work_hi-1, wrapping at 32) and whole rows. The resulting PATCH_LO/HI/FLAG
must cover every requested character and colour cell; a wrapped span
(PATCH_WRAP: LO..31 and 0..HI) carries characters only. The row is listed
for the commit, and a lone cloud span round column 31 is marked as exactly
that span rather than the whole row.
"""
import json
import random

from test_game import BASE, Machine, finish_opening

CHARS, COLOURS, WRAP = 1, 2, 4


def covered(lo, hi, flag):
    columns = set(range(lo, 32)) | set(range(0, hi+1)) if flag & WRAP else set(range(lo, hi+1))
    return (columns if flag & CHARS else set()), (columns if flag & COLOURS else set())


def main():
    m = Machine()
    r, L = m.ram, m.labels
    rng = random.Random(31)
    row = 14
    cases = wrapped_kept = 0
    for case in range(6000):
        r[L['PATCH_FLAG']+row] = 0
        r[L['patch_count']] = 0
        r[L['patch_any']] = 0
        want_chars, want_colours = set(), set()
        steps = []
        for _ in range(rng.randrange(1, 5)):
            op = rng.choice(('cloud', 'cloud', 'cloud', 'chars', 'colours', 'full'))
            if op == 'cloud':
                # cloud_x values; clouds across column 31 count the columns
                # left of it one row on (up to 51)
                lo = rng.randrange(4, 36)
                hi = lo+rng.randrange(0, 8)
                if hi > 35 and lo < 20:
                    hi = 35
                r[L['work_lo']], r[L['work_hi']] = lo, hi
                m.x = row
                m.call('patch_cloud_span')
                want_chars |= {c % 32 for c in range(lo-4, hi)}
                steps.append((op, lo, hi))
            elif op in ('chars', 'colours'):
                column = rng.randrange(32)
                m.x, m.y = row, column
                m.call('patch_mark', CHARS if op == 'chars' else CHARS | COLOURS)
                want_chars.add(column)
                if op == 'colours':
                    want_colours.add(column)
                steps.append((op, column))
            else:
                m.x = row
                m.call('patch_full_row')
                want_chars |= set(range(32))
                want_colours |= set(range(32))
                steps.append((op,))
            assert m.x == row, steps
        lo, hi, flag = r[L['PATCH_LO']+row], r[L['PATCH_HI']+row], r[L['PATCH_FLAG']+row]
        assert flag and r[L['patch_any']], steps
        assert not (flag & WRAP and flag & COLOURS), ('a wrapped span carries characters only', steps, flag)
        assert flag & WRAP or lo <= hi, (steps, lo, hi, flag)
        assert not flag & WRAP or hi+1 < lo, (steps, lo, hi, flag)
        chars, colours = covered(lo, hi, flag)
        assert want_chars <= chars, ('characters left out', steps, lo, hi, flag)
        assert want_colours <= colours, ('colours left out', steps, lo, hi, flag)
        listed = list(r[L['PATCH_LIST']:L['PATCH_LIST']+r[L['patch_count']]])
        assert listed == [row], (steps, listed)
        if len(steps) == 1 and steps[0][0] == 'cloud' and steps[0][2]-steps[0][1] < 28:
            # one cloud span: exactly its cells, wrapped round column 31 if need be
            assert chars == want_chars, (steps, lo, hi, flag)
            wrapped_kept += steps[0][2] >= 33
        cases += 1
    assert wrapped_kept > 100, wrapped_kept
    frames, checks, spans = route_screens()
    print(f'PASS patch marks: {cases} random mark sequences cover their cells; '
          f'{wrapped_kept} lone cloud spans round column 31 stay exact; route 31: '
          f'{checks} committed screens over {frames} frames equal the world cache '
          f'({spans} wrapped cloud spans)')


def route_screens(mountain=31):
    """Replay a route whose clouds cross column 31; after every commit the
    shown screen buffer must equal the world cache on every visible row."""
    m = Machine()
    r, L = m.ram, m.labels
    routes = {x['mountain']: x for x in json.loads((BASE/'tools/fixtures/mountain_routes.json').read_text())['routes']}
    r[L['selected_mountain']] = mountain
    m.frame(0xEF)
    finish_opening(m)
    check_pc, span_pc = L['read_joy'], L['patch_cloud_span']
    stats = {'checks': 0, 'spans': 0}
    plain = m.step

    def step():
        if m.pc == check_pc:
            view = r[L['last_view_row']]
            if r[L['state']] == 1 and view != 255:
                front = 0x4000+r[L['screen_buffer']]*1024
                for sy in range(25):
                    row = (view+24-sy) & 63
                    shown = bytes(r[front+sy*40+4:front+sy*40+36])
                    cache = bytes(r[0xE000+row*32:0xE000+row*32+32])
                    assert shown == cache, ('committed screen differs from the cache', stats['checks'], view, sy)
                stats['checks'] += 1
        elif m.pc == span_pc and r[L['work_hi']] >= 33:
            stats['spans'] += 1
        plain()
    m.step = step
    inputs = routes[mountain]['inputs']
    for joy in inputs:
        m.frame(joy)
    assert stats['spans'] > 50, stats
    return len(inputs), stats['checks'], stats['spans']


if __name__ == '__main__':
    main()
