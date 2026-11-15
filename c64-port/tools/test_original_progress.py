#!/usr/bin/env python3
"""Compare progression, bonus tiers and bear timers with the NES routines."""
import hashlib
import json

from emulate_prg import CPU
from test_game import BASE, bcd, start


def nes_call(prg, address, values):
    ram = bytearray(65536)
    ram[0xC000:] = prg
    for address_ram, value in values.items():
        ram[address_ram] = value
    cpu = CPU(ram, {})
    cpu.push(0xBF)
    cpu.push(0xFF)
    cpu.pc = address
    for _ in range(10000):
        if cpu.pc == 0xC000:
            return cpu
        cpu.step()
    raise AssertionError(('NES routine did not return', address))


def main():
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    m = start(mountain=24)
    r, labels = m.ram, m.labels
    assert r[labels['completed_mountains']] == 0
    for completed in range(32):
        r[labels['completed_mountains']] = completed
        ref = nes_call(prg, 0xD8FD, {0x56: completed})
        m.call('reset_bear_timer')
        assert r[labels['bear_timer']:labels['bear_timer']+2] == bytes((ref.ram[0x3D], ref.ram[0x2C]))
        ref = nes_call(prg, 0xEA8E, {0x56: completed})
        points = prg[0x28DE+ref.y] * 100
        r[labels['fruit_counts']] = 1
        r[labels['fruit_counts']+1] = 0
        r[labels['bonus_winner']] = 0
        m.call('enter_results')
        assert bcd(r[labels['result_pending']:labels['result_pending']+3]) == points
    # Starting a high mountain still begins with the original first prize
    # tier; its fruit/extra-life progression counts played stages.
    m = start(2, mountain=24)
    r, labels = m.ram, m.labels
    for completed in (0, 4):
        r[labels['completed_mountains']] = completed
        r[labels['fruit_counts']:labels['fruit_counts']+2] = bytes((1, 2))
        before = bytes((r[0x200], r[0x220]))
        m.call('enter_results')
        after = bytes((r[0x200], r[0x220]))
        assert after == bytes(v+(completed == 4) for v in before)
    # Execute the original increment path until its next-state dispatch.
    r[labels['mountain']] = 1
    r[labels['phase_counter']] = 0
    r[labels['completed_mountains']] = 0
    raw = 0
    for completed in range(1, 102):
        ram = bytearray(65536)
        ram[0xC000:] = prg
        ram[0x59], ram[0x56] = raw, (completed-1) & 255
        cpu = CPU(ram, {})
        cpu.pc = 0xCC84
        while cpu.pc != 0xCC92:
            cpu.step()
        raw = ram[0x59]
        m.call('original_advance_mountain')
        assert r[labels['mountain']] == raw % 32+1
        assert r[labels['phase_counter']] == raw//32
        assert r[labels['completed_mountains']] == ram[0x56]
    report = dict(status='passed', bear_timer_cases=32, bonus_tier_cases=32,
                  original_progression_steps=101, selected_mountain_progress_independent=True,
                  fifth_played_stage_extra_life=True, prg_sha256=hashlib.sha256(
                      (BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/original_progress.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS original bonus tiers, extra life, bear timers and99-stage progression')


if __name__ == '__main__':
    main()
