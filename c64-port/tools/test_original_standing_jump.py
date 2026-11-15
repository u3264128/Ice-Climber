"""Standing UP+direction must reach the next floor exactly as on NES."""
import hashlib
import json

from original_player_reference import PlayerReference
from test_game import BASE, start


def main():
    cases = []
    for pad, column, expected_x in ((0x81, 3, 58), (0x82, 2, 38)):
        original = PlayerReference()
        machine = start()
        r, labels = machine.ram, machine.labels
        # A legal pre-broken hole, identical in the actual original map and
        # the packed C64 map. No movement/run-up precedes the jump button.
        index = 24+column
        original.ram[0x400+index] = original.ram[0x500+index] = 255
        r[labels['floor_upper']+index] = r[labels['floor_lower']+index] = 0
        source_map = bytes(original.ram[0x400:0x600])
        c64_map = bytes(r[0x400:0x600])
        assert r[labels['walk_time']] == r[labels['move_dir']] == 0
        trace = []
        for tick in range(36):
            buttons = pad if tick == 0 else pad & 3
            original.tick(buttons)
            joy = 255
            if buttons & 0x80:
                joy &= 0xFE
            if buttons & 1:
                joy &= 0xF7
            if buttons & 2:
                joy &= 0xFB
            machine.joystick = joy
            machine.call('read_joy')
            machine.call('normal_player_tick')
            actual = (int.from_bytes(r[labels['pxlo']:labels['pxhi']+1], 'little')-52,
                      r[labels['py']]-24)
            expected = (original.ram[0x64], original.ram[0x66])
            assert actual == expected, ('standing jump', hex(pad), tick+1, actual, expected)
            trace.append(list(actual))
        assert expected == (expected_x, 144)
        assert original.ram[0x6A] == 3 and original.ram[0x5A] == 2
        assert r[labels['onground']] and r[labels['curfloor']] == 1
        assert bytes(original.ram[0x400:0x600]) == source_map
        assert bytes(r[0x400:0x600]) == c64_map
        cases.append(dict(direction='right' if pad & 1 else 'left', ticks=36,
                          rise_to_floor=48, prior_runup_ticks=0, trajectory=trace))
    report = dict(status='passed', cases=cases, per_tick_original_xy=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/original_standing_jump.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS standing UP+left/right climbs48px without run-up, every X/Y tick matches original')


if __name__ == '__main__':
    main()
