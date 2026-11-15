"""Lossless asset bytes after the shared 6510 decoder and title setup."""
import hashlib
import json

from test_game import BASE, Machine


def main():
    machine = Machine()
    ram, labels = machine.ram, machine.labels
    font = (BASE/'converted/charset/title_charset.bin').read_bytes()
    screen = (BASE/'converted/screens/title_c64.bin').read_bytes().ljust(1024, b'\0')
    colours = (BASE/'converted/screens/title_c64.col').read_bytes().ljust(1024, b'\0')
    terrain = (BASE/'c64/build/terrain_charset.bin').read_bytes()
    assert ram[0x4800:0x4A00] == font[:512], 'Title logo font changed at boot'
    assert ram[0x4000:0x4000+13*40] == screen[:13*40], 'Title logo screen changed at boot'
    cases = (('unpack_title_font', 0x4800, font),
             ('unpack_title_screen', 0x4000, screen),
             ('unpack_title_colours', 0xD800, colours),
             ('unpack_terrain', 0x4800, terrain))
    total = 0
    for _ in range(3):
        for routine, address, expected in cases:
            ram[address:address+len(expected)] = bytes([0xA5])*len(expected)
            machine.call(routine)
            assert ram[address:address+len(expected)] == expected, routine
            assert int.from_bytes(ram[labels['dst']:labels['dst']+2], 'little') == address+len(expected), routine
            total += len(expected)
        # Normal title setup deliberately overlays menu glyphs64 and above;
        # the original title logo, glyphs0..63, must survive that lifecycle.
        machine.call('enter_title')
        assert ram[0x4800:0x4A00] == font[:512]
        assert ram[0x4000:0x4000+13*40] == screen[:13*40]
    report = dict(status='passed', decoded_bytes=total, passes=3,
                  assets=[name for name, _, _ in cases], title_logo_glyphs=64,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/asset_unpack.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS shared lossless decoder, complete assets and title logo lifecycle:', report)


if __name__ == '__main__':
    main()
