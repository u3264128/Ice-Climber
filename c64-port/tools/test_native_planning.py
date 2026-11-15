#!/usr/bin/env python3
"""Cross-check the optional compiled search CPU against the Python CPU."""
import copy
import hashlib
import json
import random

from emulate_prg import CPU
from plan_mountains import BASE, clone, fast_frame, start
import native_planning

REGISTERS = ('pc', 'a', 'x', 'y', 'sp', 'c', 'z', 'i', 'd', 'v', 'n')


def same(reference, compiled, context):
    assert reference.ram == compiled.ram, (context, 'RAM mismatch',
           [(i, a, b) for i, (a, b) in enumerate(zip(reference.ram, compiled.ram)) if a != b][:8])
    assert all(getattr(reference, name) == getattr(compiled, name) for name in REGISTERS), \
        (context, [(name, getattr(reference, name), getattr(compiled, name)) for name in REGISTERS])


def main():
    assert native_planning.library is not None, 'Run python build.py native from the repository root'
    rng = random.Random(6502)
    arithmetic = 0
    for opcode in (0x69, 0xE9):
        for decimal in (0, 1):
            for _ in range(1500):
                ram = bytearray(65536)
                ram[0x200:0x203] = bytes((opcode, rng.randrange(256), 0x60))
                reference = CPU(ram, {}, decimal_supported=True)
                reference.pc, reference.a = 0x200, rng.randrange(256)
                reference.c, reference.d = rng.randrange(2), decimal
                for name in ('x', 'y'):
                    setattr(reference, name, rng.randrange(256))
                for name in ('n', 'z', 'i', 'v'):
                    setattr(reference, name, rng.randrange(2))
                reference.push(0xFF)
                reference.push(0xEF)
                compiled = copy.copy(reference)
                compiled.ram = reference.ram.copy()
                while reference.pc != 0xFFF0:
                    reference.step()
                native_planning.run_to(compiled, 0xFFF0)
                same(reference, compiled, ('arithmetic', opcode, decimal, arithmetic))
                arithmetic += 1

    route = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())['normal']
    cases = [(1, route)]
    for mountain in (9, 17, 25, 31):
        inputs = [rng.choice((255, 0xF7, 0xFB, 0xFE, 0xF6, 0xFA)) for _ in range(300)]
        cases.append((mountain, inputs))
    frames = 0
    for mountain, inputs in cases:
        reference = start(mountain, planning=True)
        reference.use_native = False
        compiled = clone(reference)
        compiled.use_native = True
        for index, joystick in enumerate(inputs):
            fast_frame(reference, joystick)
            fast_frame(compiled, joystick)
            same(reference, compiled, ('game', mountain, index))
            frames += 1
            if reference.ram[0x18] not in (1, 3):
                break
    rendered = 0
    for mountain, inputs in ((1, route), (25, [255]*240)):
        reference = start(mountain)
        compiled = start(mountain, planning=True)
        compiled.planning = False
        same(reference, compiled, ('full initialization', mountain))
        for index, joystick in enumerate(inputs):
            reference.frame(joystick)
            compiled.frame(joystick)
            same(reference, compiled, ('full rendered frame', mountain, index))
            rendered += 1
    report = dict(status='passed', arithmetic_cases=arithmetic, game_frames=frames,
                  fully_rendered_frames=rendered, skipped_helpers_in_full_replay=False,
                  all_ram_bytes=True, all_cpu_registers=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                  native_source_sha256=hashlib.sha256((BASE/'tools/fast6502.cpp').read_bytes()).hexdigest())
    (BASE/'docs/verification/native_planning_regression.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'PASS compiled CPU matches Python: {arithmetic} arithmetic cases, {frames} complete game frames')


if __name__ == '__main__':
    main()
