"""Bound sampled-raster to IRQ rearm using independent NMOS cycle counts.

The reference instruction interpreter executes the assembled code, including
its real branch addresses. Cycle accounting is separate from the interpreter
and the optional native planning accelerator. PAL top-border execution has
63 cycles per line and no sprite/badline DMA before the line12 frame IRQ.
"""
import collections
import copy
import hashlib
import itertools
import json

from test_game import BASE, Machine


CYCLES = {
    0x20:6, 0x60:6, 0x4C:3, 0x48:3, 0x68:4,
    0x18:2, 0x38:2, 0x78:2, 0x58:2, 0xAA:2, 0xA8:2, 0x8A:2, 0x98:2,
    0xE8:2, 0xC8:2, 0xCA:2, 0x88:2, 0x0A:2, 0x4A:2, 0x6A:2, 0x2A:2,
    0x46:5, 0x66:5, 0x06:5, 0x26:5,
    0xA2:2, 0xA6:3, 0xAE:4, 0xA0:2, 0xA4:3, 0xAC:4,
    0x84:3, 0x8C:4, 0x86:3, 0x8E:4,
    0xE0:2, 0xE4:3, 0xEC:4, 0xC0:2, 0xC4:3, 0xCC:4,
    0xE6:5, 0xEE:6, 0xFE:7, 0xC6:5, 0xCE:6, 0xDE:7,
    0x85:3, 0x8D:4, 0x9D:5, 0x99:5, 0x91:6, 0xBC:4, 0xBE:4,
}
for family in ((0xA9,0xA5,0xAD,0xBD,0xB9,0xB1),
               (0x69,0x65,0x6D,0x7D,0x79,0x71),
               (0xE9,0xE5,0xED,0xFD,0xF9,0xF1),
               (0xC9,0xC5,0xCD,0xDD,0xD9,0xD1),
               (0x29,0x25,0x2D,0x3D,0x39,0x31),
               (0x09,0x05,0x0D,0x1D,0x19,0x11),
               (0x49,0x45,0x4D,0x5D,0x59,0x51)):
    CYCLES.update(zip(family,(2,3,4,4,4,5)))
BRANCHES = {0x10,0x30,0x50,0x70,0x90,0xB0,0xD0,0xF0}
PAGE_X = {0xBD,0xBC,0x7D,0xFD,0xDD,0x3D,0x1D,0x5D}
PAGE_Y = {0xB9,0xBE,0x79,0xF9,0xD9,0x39,0x19,0x59}
PAGE_INDIRECT = {0xB1,0x71,0xF1,0xD1,0x31,0x11,0x51}


def run(machine, sample, raster, state, packet, camera,
        fine=7, bank=0, half=0, pending=32):
    cpu = copy.copy(machine)
    cpu.ram = machine.ram.copy()
    cpu.under_io = machine.under_io.copy()
    cpu.hooks = {0xD012:lambda mem,addr,value: raster if value is None else None,
                 0xD011:lambda mem,addr,value: 0 if value is None else None}
    ram, labels = cpu.ram, cpu.labels
    for name,value in (('state',state), ('packet_ready',packet),
                       ('pending_buffer',bank), ('view_fine',fine),
                       ('back_base',half), ('pending_count',pending),
                       ('frame_ticks',71)):
        ram[labels[name]] = value
    ram[labels['visual_camera']:labels['visual_camera']+2] = camera.to_bytes(2,'little')
    cpu.pc, cpu.sp, cpu.i, cpu.d = sample, 0xFD, 0, 0
    # Return through the actual main loop's JSR commit_view/commit_actors.
    return_address = labels['main_loop']+2
    cpu.push(return_address>>8)
    cpu.push(return_address&255)
    elapsed = 0
    trace = []
    for _ in range(200):
        pc, opcode = cpu.pc, ram[cpu.pc]
        cycles = 2 if opcode in BRANCHES else CYCLES.get(opcode)
        assert cycles is not None, ('unaccounted instruction',hex(pc),hex(opcode))
        if opcode in PAGE_X|PAGE_Y:
            address = ram[pc+1]|ram[pc+2]<<8
            index = cpu.x if opcode in PAGE_X else cpu.y
            cycles += (address&255)+index > 255
        if opcode in PAGE_INDIRECT:
            pointer = ram[pc+1]
            address = ram[pointer]|ram[(pointer+1)&255]<<8
            cycles += (address&255)+cpu.y > 255
        cpu.step()
        if opcode in BRANCHES and cpu.pc != (pc+2)&65535:
            cycles += 1+(((pc+2)&0xFF00)!=(cpu.pc&0xFF00))
        elapsed += cycles
        trace.append(dict(pc=pc,opcode=opcode,cycles=cycles,elapsed=elapsed))
        if opcode == 0x58:
            assert labels['commit_actors'] <= pc < labels['commit_actors']+100
            return elapsed, trace
    raise AssertionError(('did not rearm IRQ',state,packet,camera,hex(cpu.pc)))


def accepts_raster(machine, sample, state, raster):
    """Run the late-window path with a consistent nine-bit raster read."""
    cpu = copy.copy(machine)
    cpu.ram = machine.ram.copy()
    cpu.under_io = machine.under_io.copy()
    reads = 0

    def read_raster(mem, address, value):
        nonlocal reads
        if value is None:
            reads += 1
            return raster&255

    cpu.hooks = {0xD012:read_raster,
                 0xD011:lambda mem,addr,value: (0x80 if raster>=256 else 0) if value is None else None}
    ram, labels = cpu.ram, cpu.labels
    ram[labels['state']] = state
    ram[labels['frame_ticks']], ram[labels['commit_ticks']] = 71, 70
    cpu.pc, cpu.sp, cpu.d = labels['wait_frame'], 0xFD, 0
    return_address = labels['main_loop']+2
    cpu.push(return_address>>8)
    cpu.push(return_address&255)
    sampled = False
    for _ in range(100):
        if cpu.pc == sample:
            sampled = True
        cpu.step()
        if cpu.pc == return_address+1:
            assert sampled and reads == 2 and cpu.sp == 0xFD
            assert ram[labels['late_commit']] == 1 and ram[labels['commit_ticks']] == 71
            return True
        # Two reads establish a consistent sample. A third read means the
        # routine chose the polling loop for the next lower border.
        if reads == 3:
            assert sampled and ram[labels['commit_ticks']] == 70
            return False
    raise AssertionError(('raster probe did not return or wait',state,raster,hex(cpu.pc)))


def endpoints(machine, trace, read_done):
    result = {}
    for item in trace:
        if item['opcode'] == 0x8D:
            pc = item['pc']
            address = machine.ram[pc+1]|machine.ram[pc+2]<<8
            if address in (0xD012,0xD019,0xD01A):
                result[hex(address)] = item['elapsed']-read_done
        if item['opcode'] == 0x58:
            result['CLI'] = item['elapsed']-read_done
    return result


def main():
    image_path = BASE/'c64/build/iceclimber_game.prg'
    release = image_path.read_bytes()
    machine = Machine()
    ram, labels = machine.ram, machine.labels
    start = labels['main_loop']
    expected_calls = b''.join(b'\x20'+labels[name].to_bytes(2,'little')
                              for name in ('wait_frame','commit_view','commit_actors'))
    assert bytes(ram[start:start+9]) == expected_calls, 'Commit caller order changed'
    wait = labels['wait_frame']
    code = bytes(ram[wait:wait+180])
    consistent_read = bytes.fromhex('ae12d0ad11d0ec12d0')
    assert code.count(consistent_read) == 1
    sample = wait+code.index(consistent_read)
    actors = bytes(ram[labels['commit_actors']:labels['commit_actors']+100])
    arm = actors.index(bytes.fromhex('8d12d0'))
    assert actors[arm-2] == 0xA9
    irq_line = actors[arm-1]
    accepted = {}
    for state in range(5):
        accepted[state] = [line for line in range(312) if accepts_raster(machine,sample,state,line)]
        expected = list(range(8 if state==3 else 7))+list(range(250,312))
        assert accepted[state] == expected, ('unexpected late-window raster lines',state,accepted[state])
    latest = {state:max(line for line in accepted[state] if line<irq_line) for state in (1,3,4)}
    guards = {state:irq_line-line for state,line in latest.items()}
    distribution = collections.Counter()
    worst_by_state = {}
    for state,packet,camera in itertools.product((1,3,4),(0,1),range(768)):
        cycles, trace = run(machine,sample,latest[state],state,packet,camera)
        distribution[cycles] += 1
        if state not in worst_by_state or cycles > worst_by_state[state][0]:
            worst_by_state[state] = cycles,state,packet,camera,trace
    variants = 0
    bounds = {}
    for state,worst in worst_by_state.items():
        reserve = guards[state]
        latest_line = latest[state]
        for fine,bank,half,pending in itertools.product(range(8),(0,1),(0,32),(0,1,16,32)):
            cycles,_ = run(machine,sample,latest_line,*worst[1:4],fine,bank,half,pending)
            assert cycles == worst[0], ('unexpected operand-dependent timing',state,fine,bank,half,pending,cycles)
            variants += 1
        assert [item['opcode'] for item in worst[4][:3]] == [0xAE,0xAD,0xEC]
        read_done = sum(item['cycles'] for item in worst[4][:3])
        assert read_done == 12
        # CPX absolute reads on its last cycle. If that read still saw the
        # latest accepted line at cycle62, the following full lines remain.
        budget = (reserve-1)*63
        post_read = worst[0]-read_done
        marks = endpoints(machine,worst[4],read_done)
        assert post_read < budget, ('IRQ rearm margin exhausted',worst[:4],budget)
        assert all(cycles < budget for cycles in marks.values())
        # Keep the earlier stronger prefix bound for the normal/flyover
        # guard. The smaller bonus guard uses the exact post-read deadline.
        if state != 3:
            assert worst[0] < budget, ('normal/preview conservative margin exhausted',state,worst[0],budget)
        bounds[state] = dict(reserve_lines=reserve,latest_accepted_line=latest_line,
                             maximum_prefix_cycles=worst[0],final_consistent_read_offset=read_done,
                             maximum_post_read_cycles=post_read,minimum_post_read_budget=budget,
                             post_read_margin_cycles=budget-post_read,
                             irq_register_endpoints_post_read=marks,
                             latest_cli_line=latest_line+1+post_read//63,
                             latest_cli_cycle=post_read%63,
                             worst_packet_ready=worst[2],worst_visual_camera=worst[3],
                             worst_trace=worst[4])
    worst = max(worst_by_state.values(),key=lambda item:item[0])
    assert image_path.read_bytes() == release, 'PRG changed during timing proof'
    release_hash = hashlib.sha256(release).hexdigest()
    report = dict(status='passed',
                  prg_sha256=release_hash,
                  assembled_guards_by_state=guards,accepted_lines_by_state=accepted,
                  frame_irq_line=irq_line,
                  raster_predicate_cases=5*312,
                  control_cases=sum(distribution.values()),fine_bank_half_count_cases=variants,
                  independent_reference_interpreter=True,branch_page_penalties_included=True,
                  minimum_raw_cycles=min(distribution),maximum_raw_cycles_from_sample_through_CLI=worst[0],
                  maximum_raw_cycles_after_final_consistent_raster_read=worst[0]-12,
                  minimum_post_read_margin_cycles=min(value['post_read_margin_cycles'] for value in bounds.values()),
                  worst_state=worst[1],worst_packet_ready=worst[2],worst_visual_camera=worst[3],
                  cycle_distribution=dict(sorted(distribution.items())),state_bounds=bounds)
    (BASE/'docs/verification/commit_margin.json').write_text(json.dumps(report,indent=2)+'\n')
    bonus_report = dict(status='passed',prg_sha256=release_hash,bonus_only=True,
                        assembled_guard_lines=guards[3],
                        control_cases=1536,fine_bank_half_count_cases=128,**bounds[3])
    (BASE/'docs/verification/bonus_commit_margin.json').write_text(json.dumps(bonus_report,indent=2)+'\n')
    print('PASS exact sampled-raster to IRQ rearm margin:',
          {key:value for key,value in report.items()
           if key not in ('state_bounds','cycle_distribution','accepted_lines_by_state')})


if __name__ == '__main__':
    main()
