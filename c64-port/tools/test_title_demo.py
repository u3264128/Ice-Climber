"""Hidden title input and attract mode, checked against executed NES code."""
import hashlib
import json

from level_codes import CODES, KEYS
from test_game import BASE, Machine, finish_opening
from test_nes_export import joystick
from test_original_physics import Reference


def key(machine, char, frames=1):
    position = KEYS[char]
    machine.keys = {255 ^ (1 << (position//8)): 255 ^ (1 << (position % 8))}
    for _ in range(frames):
        machine.frame()


def type_code(machine, text):
    for char in text:
        key(machine, char)
        machine.keys = {}
        machine.frame()


def display(machine):
    return bytes(machine.ram[0x4000:0x4400])+bytes(machine.ram[0xD800:0xDBE8])


def original_idle():
    reference = Reference()
    r = reference.ram
    r[0x31], r[0x4E], r[0x51], r[0x59] = 9, 128, 1, 30
    for ticks in range(1, 1600):
        reference.call(0xCB9D)
        reference.call(0xC460)
        if r[0x53]:
            assert (r[0x55], r[0x59], r[0x03FE], r[0x4015]) == (5, 0, 30, 0)
            return ticks
    raise AssertionError('original did not enter demo')


def check_codes():
    m = Machine()
    r, L = m.ram, m.labels
    for row in (19, 20, 23):
        assert r[0x4000+row*40:0x4000+(row+1)*40] == bytes(40), ('old title text remains', row)
    before = display(m)
    for mountain, code in enumerate(CODES, 1):
        type_code(m, code)
        assert r[L['selected_mountain']] == mountain, (mountain, code)
        assert r[L['state']] == 0 and display(m) == before, ('visible code input', code)
    m.frame(0xF7)
    m.frame()
    assert r[L['selected_mountain']] == 32, 'right must not select a mountain'
    type_code(m, 'jd3q')
    m.frame(0xFD)
    m.frame()
    m.frame(0xEF)
    assert (r[L['mountain']], r[L['player_count']], r[L['state']]) == (31, 2, 4)
    finish_opening(m)
    r[L['paused']] = 1
    m.keys = {0x7F: 0x7F}  # RUN/STOP
    m.frame()
    assert r[L['state']] == 0 and r[L['selected_mountain']] == 1 and not r[L['paused']]
    m.keys = {}
    m.frame()
    type_code(m, 'jd3q')
    type_code(m, 'xxxx')
    assert r[L['selected_mountain']] == 1
    key(m, 'j', 250)
    assert r[L['title_count']] == 1
    m.frame()
    assert r[L['title_count']] == 0 and r[L['selected_mountain']] == 1
    # A held key cannot restart the expired partial code.
    m.frame()
    assert r[L['title_count']] == 0
    m.keys = {}
    m.frame()
    type_code(m, 'd3q')
    assert r[L['selected_mountain']] == 1
    m.call('enter_title')
    type_code(m, 'jd3q')
    m.frame(0xEF)
    assert r[L['mountain']] == 31 and r[L['player_count']] == 2
    return dict(codes=32, invisible=True, timeout_frames=250, two_player_mountain=31)


def check_demo():
    ticks = original_idle()
    assert ticks == 1407
    pal = (ticks*5+5)//6
    m = Machine()
    r, L = m.ram, m.labels
    # Exercise the release title timer without rendering 1173 static frames.
    m.call('read_joy')
    for frame in range(pal):
        m.call('title_tick')
        assert r[L['state']] == (4 if frame == pal-1 else 0), frame
    assert r[L['demo_active']] == 1 and r[0xD418] == 0
    finish_opening(m)
    assert not r[L['paused']]
    source = Reference()
    q = source.ram
    q[0x55], q[0x51], q[0x66] = 1, 1, 128
    # The input emitter is independent of actual motion. Compare three full
    # loops with C620, including counter boundaries and both frame parities.
    r[L['demo_index']] = r[L['demo_remaining']] = 0
    for tick in range(1800):
        r[L['logic_frame']] = q[0x50] = tick & 255
        r[L['py']] = 128+24
        source.call(0xC620)
        m.call('demo_input')
        assert r[L['input_joy']] == joystick(q[0x14]), (tick, q[0x14], r[L['input_joy']])
        assert r[L['input_fire']] == (~joystick(q[0x15]) & 0x11)
        assert (r[L['demo_index']], r[L['demo_remaining']]) == (q[0x3FA] & 15, q[0x3FB])
    # Physical fire returns to the title and is consumed; a fresh press starts.
    m.frame(0xEF)
    assert r[L['state']] == 0 and not r[L['demo_active']] and r[0xD418] == 15
    m.frame(0xEF)
    assert r[L['state']] == 0
    m.frame()
    m.frame(0xEF)
    assert r[L['state']] == 4 and not r[L['demo_active']]
    m.call('enter_title')
    type_code(m, 'jd3q')
    for expected in (2, 3, 4, 1):
        m.call('demo_start')
        assert r[L['mountain']] == expected
        finish_opening(m)
        r[L['py']] = 236
        m.call('game_tick')
        assert r[L['state']] == 0 and r[L['selected_mountain']] == 31
    m.call('demo_start')
    finish_opening(m)
    m.keys = {0xDF: 0xFD}       # P is the C64 Select/exit equivalent
    m.frame()
    assert r[L['state']] == 0 and not r[L['paused']]
    m.keys = {}
    m.frame()
    m.frame(0xEF)
    finish_opening(m)
    assert not r[L['paused']]
    key(m, 'l')
    assert not r[L['paused']], 'player2 movement must not pause the game'
    return dict(original_idle_ticks=ticks, pal_idle_frames=pal, scripted_ticks=1800,
                demo_mountains=[1, 2, 3, 4], input_exit=True, fall_exit=True)


def main():
    report = dict(status='passed', codes=check_codes(), demo=check_demo(),
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/title_demo.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS hidden title codes and original attract demo', report)


if __name__ == '__main__':
    main()
