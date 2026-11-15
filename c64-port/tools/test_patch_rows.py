"""Execute every patch interval against an independent complete-RAM oracle."""
import hashlib
import json

from plan_mountains import PlanningMachine
from test_game import BASE


def main():
    machine = PlanningMachine()
    ram, labels = machine.ram, machine.labels
    original = bytes(ram)
    cases = 0
    wrapped = 0
    full_rows = 0
    # Real screen rows include both sides of a 256-byte boundary. Source
    # pointers independently straddle pages, including a start at byte255.
    layouts = ((0, 0xE000, 0xF000), (6, 0xE0EF, 0xF0E9),
               (12, 0xE0F8, 0xF0F0), (24, 0xE1FF, 0xF1FF))
    for screen_row, source, colour_source in layouts:
        for bank in (0, 1):
            destination = 0x4000+bank*1024+screen_row*40+4
            colour_destination = 0xD800+screen_row*40+4
            for kind in (1, 3, 5):  # chars, chars+colours, two wrapped chars intervals
                for low in range(32):
                    for high in range(32):
                        if (low > high) != bool(kind & 4):
                            continue
                        ram[:] = original
                        ram[source:source+32] = bytes((i*43+cases)&255 for i in range(32))
                        ram[colour_source:colour_source+32] = bytes((i*7+cases)&15 for i in range(32))
                        ram[destination-16:destination+48] = b'\xA5'*64
                        ram[colour_destination-16:colour_destination+48] = b'\xB6'*64
                        for name, address in (('src', source), ('dst', destination),
                                              ('work_lo', colour_source), ('colptr', colour_destination)):
                            pointer = labels[name]
                            ram[pointer:pointer+2] = address.to_bytes(2, 'little')
                        ram[labels['patch_lo']] = low
                        ram[labels['patch_hi']] = high
                        ram[labels['patch_kind']] = kind
                        expected = bytearray(ram)
                        intervals = ((0, high), (low, 31)) if kind & 4 else ((low, high),)
                        for first, last in intervals:
                            expected[destination+first:destination+last+1] = ram[source+first:source+last+1]
                            if kind & 2:
                                expected[colour_destination+first:colour_destination+last+1] = \
                                    ram[colour_source+first:colour_source+last+1]
                        saved_x = cases & 255
                        machine.x = saved_x
                        machine.call('patch_row', cases & 255)
                        context = (screen_row, bank, kind, low, high)
                        # The call's return address is the only RAM change
                        # permitted outside the requested destination cells.
                        assert ram[:0x100] == expected[:0x100], ('zero page', context)
                        assert ram[0x200:] == expected[0x200:], ('RAM result', context)
                        assert machine.x == saved_x, ('X register', context)
                        if not kind & 4:
                            last_source = colour_source if kind & 2 else source
                            assert machine.a == ram[last_source+low], ('A result', context)
                        cases += 1
                        wrapped += bool(kind & 4)
                        full_rows += low == 0 and high == 31
    promotions = 0
    promoted_cells = 0
    for name in ('patch_full_chars', 'patch_full_row'):
        for previous in (5, 7):
            for bank in (0, 1):
                for screen_row in range(25):
                    ram[:] = original
                    row = 17
                    ram[labels['PATCH_FLAG']+row] = previous
                    ram[labels['PATCH_LO']+row] = 29
                    ram[labels['PATCH_HI']+row] = 3
                    machine.x = row
                    machine.call(name)
                    expected_kind = 3 if name == 'patch_full_row' or previous & 2 else 1
                    assert ram[labels['PATCH_FLAG']+row] == expected_kind, ('wrapped promotion flag', name, previous)
                    assert ram[labels['PATCH_LO']+row] == 0
                    assert ram[labels['PATCH_HI']+row] == 31
                    assert ram[labels['patch_any']] == expected_kind
                    for field, array in (('patch_kind', 'PATCH_FLAG'), ('patch_lo', 'PATCH_LO'),
                                         ('patch_hi', 'PATCH_HI')):
                        ram[labels[field]] = ram[labels[array]+row]
                    destination = 0x4000+bank*1024+screen_row*40+4
                    colour_destination = 0xD800+screen_row*40+4
                    ram[0xE000:0xE020] = bytes((i*13+screen_row)&255 for i in range(32))
                    ram[0xF000:0xF020] = bytes((i+screen_row)&15 for i in range(32))
                    ram[destination:destination+32] = b'\xA5'*32
                    ram[colour_destination:colour_destination+32] = b'\xB6'*32
                    for field, address in (('src',0xE000), ('dst',destination),
                                            ('work_lo',0xF000), ('colptr',colour_destination)):
                        pointer = labels[field]
                        ram[pointer:pointer+2] = address.to_bytes(2,'little')
                    expected = bytearray(ram)
                    expected[destination:destination+32] = ram[0xE000:0xE020]
                    if expected_kind & 2:
                        expected[colour_destination:colour_destination+32] = ram[0xF000:0xF020]
                    machine.call('patch_row')
                    assert ram[:0x100] == expected[:0x100] and ram[0x200:] == expected[0x200:], \
                        ('promoted full row', name, previous, bank, screen_row)
                    promotions += 1
                    promoted_cells += 32
    report = dict(status='passed', interval_cases=cases, wrapped_cases=wrapped,
                  wrapped_promotions=promotions, promoted_cells=promoted_cells, complete_rows=full_rows,
                  screen_buffers=2, source_page_crossings=True,
                  exact_memory_except_call_stack=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/patch_rows.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS every patch interval and full-row fast path:', report)


if __name__ == '__main__':
    main()
