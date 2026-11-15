"""Takeoff grace: a stick direction one or two PAL frames after UP.

A diagonal push often reports UP a frame before LEFT/RIGHT. Such a jump
must continue exactly like one that had the direction at takeoff (X, Y,
ground flag and latched direction in every later frame), in normal stages,
in the bonus and for player 2. Outside the window, for falls and for a
held direction without motion (a jump from a stop), the original rules stay.
"""
from test_game import start

UP, NONE, RIGHT, LEFT = 0xFE, 0xFF, 0xF7, 0xFB


def trajectory(m, base, seq, player=0, frames=60, grace=True):
    r, L = m.ram, m.labels
    r[:] = base
    out = []
    for i in range(frames):
        joy = seq[i] if i < len(seq) else seq[-1]
        m.frame(joy if player == 0 else NONE, joy if player == 1 else NONE)
        if not grace:                      # the original rules: no window
            r[L['jump_grace']] = r[L['jump_grace']+1] = 0
        if player == 0:
            fields = (r[L['pxlo']] | r[L['pxhi']] << 8, r[L['py']], r[L['onground']], r[L['move_dir']])
        else:
            p = r[L['PLAYER_STATES']+32:L['PLAYER_STATES']+64]
            fields = (p[3] | p[4] << 8, p[5], p[8], p[20])
        out.append(fields)
    return out


def check_late(m, label, player=0, positions=(80, 104, 136, 168, 200)):
    r, L = m.ram, m.labels
    origin = bytes(r)
    cases = 0
    for x in positions:
        for wait in range(5):              # every phase of the 6:5 tick cadence
            for direction in (RIGHT, LEFT):
                r[:] = origin
                if player == 0:
                    r[L['pxlo']], r[L['pxhi']] = x, 0
                else:
                    r[L['PLAYER_STATES']+35], r[L['PLAYER_STATES']+36] = x, 0
                for _ in range(wait):
                    m.frame()
                base = bytes(r)
                both = direction & UP
                takeoff = trajectory(m, base, [both]*4 + [direction], player)
                assert takeoff[-1][0] != takeoff[0][0], (label, 'jump did not move sideways')
                for late in (1, 2):
                    shown = trajectory(m, base, [UP]*late + [both]*4 + [direction], player)
                    assert shown[late:] == takeoff[late:], (label, x, wait, direction, late)
                    cases += 1
                # Four frames late is outside the window: the original jump.
                outside = [UP]*4 + [both]*4 + [direction]
                assert trajectory(m, base, outside, player) ==                     trajectory(m, base, outside, player, grace=False), (label, x, wait, 'late steer')
    r[:] = origin
    return cases


def check_rules(m):
    r, L = m.ram, m.labels
    origin = bytes(r)
    grace = L['jump_grace']
    for move_dir, joy, armed in ((0, NONE, 3), (0, RIGHT, 0), (1, RIGHT, 0), (2, NONE, 0)):
        r[:] = origin
        r[L['player_index']] = 0
        r[L['move_dir']] = move_dir
        r[L['joy']] = joy
        m.call('begin_jump')
        assert r[grace] == armed, ('grace arming', move_dir, joy, r[grace])
        assert r[L['onground']] == 0 and r[L['rise_int']] == 3 and r[L['rise_frac']] == 0xA8
    # A fall (air_init bit 7, $CD3B) never takes the takeoff step.
    r[:] = origin
    r[L['player_index']] = 0
    r[L['move_dir']], r[L['joy']], r[grace] = 0, RIGHT, 3
    r[L['air_init']], r[L['onground']] = 0x8C, 0
    x = r[L['pxlo']]
    m.call('air_grace')
    assert r[L['move_dir']] == 0 and r[L['pxlo']] == x, 'a fall used the takeoff grace'
    r[:] = origin


def main():
    m = start(1)
    for _ in range(40):
        m.frame()
    assert m.ram[m.labels['state']] == 1 and m.ram[m.labels['onground']] == 1
    check_rules(m)
    normal = check_late(m, 'normal')
    two = start(2)
    for _ in range(40):
        two.frame()
    # Away from player 1 (X 100): climbers that touch bump each other ($D212).
    second = check_late(two, 'player 2', player=1, positions=(136, 168))
    bonus = start(1)
    bonus.ram[bonus.labels['bonus_requested']] = 1
    for _ in range(80):
        bonus.frame()
    assert bonus.ram[bonus.labels['state']] == 3 and bonus.ram[bonus.labels['onground']] == 1
    bonus_cases = check_late(bonus, 'bonus', positions=(96, 120, 150))
    print(f'PASS takeoff grace: {normal} normal, {second} player-2 and {bonus_cases} bonus late '
          'directions equal a takeoff direction; late, stop and fall rules unchanged')


if __name__ == '__main__':
    main()
