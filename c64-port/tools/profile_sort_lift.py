"""Read-only native capture and NMOS-cycle trial of a12-to14 sort cache lift."""
import copy
import hashlib
import json
import struct

from plan_mountains import PlanningMachine
from profile_bonus_scroll import configure
from test_game import BASE
from test_commit_margin import CYCLES,BRANCHES,PAGE_X,PAGE_Y,PAGE_INDIRECT
from vice_session import ViceSession
from verify_mux_timing import registers


def capture(path,release):
    records=[]
    with ViceSession('sort_lift_capture') as s:
        s.write('selected_mountain',4)
        s.frame(0xFD);s.frame();s.frame(0xEF);s.finish_preview()
        s.write('bonus_requested',1);s.frame();s.write('paused',1)
        s.write('bonus_camera',(220).to_bytes(2,'little'))
        for _ in range(130):s.frame()
        s.write('paused',0);configure(s,0,256,220)
        entry=s.labels['bonus_sort_try']
        s.m.command(0x12,struct.pack('<HHBBBB',entry,entry,1,1,4,0))
        finished=False
        for frame in range(24):
            while True:
                s.m.resume();reg=registers(s.m)
                if reg['PC']==s.labels['main_loop']:
                    configure(s,frame,256,220)
                    break
                assert reg['PC']==entry
                camera=int.from_bytes(s.read('visual_camera',2),'little')
                count=s.read('logical_count')[0]
                phase=s.read('frame')[0]&3
                old=s.read(s.labels['BONUS_SORT_COUNT']+phase)[0]
                if count==14 and camera in (233,235,237,239):
                    records.append(dict(camera=camera,phase=phase,old_count=old,
                        low=s.read(0,0x800).hex(),logs=s.read(0xE800,0x200).hex()))
                    if camera==239:finished=True;break
            if finished:break
    assert records and records[-1]['camera']==239
    path.write_text(json.dumps(dict(prg_sha256=release,cases=records))+'\n')
    return records


def raw_call(cpu,address):
    cpu.sp=0xFD;cpu.d=0;cpu.pc=address
    cpu.push(0xFF);cpu.push(0xEF)
    elapsed=6  # actual caller's JSR, in addition to executed callee RTS
    for _ in range(10000):
        if cpu.pc==0xFFF0:return elapsed
        pc=cpu.pc;op=cpu.ram[pc]
        cycles=2 if op in BRANCHES else CYCLES.get(op)
        assert cycles is not None,(hex(pc),hex(op))
        if op in PAGE_X|PAGE_Y:
            operand=cpu.ram[pc+1]|cpu.ram[pc+2]<<8
            index=cpu.x if op in PAGE_X else cpu.y
            cycles+=(operand&255)+index>255
        if op in PAGE_INDIRECT:
            pointer=cpu.ram[pc+1]
            operand=cpu.ram[pointer]|cpu.ram[(pointer+1)&255]<<8
            cycles+=(operand&255)+cpu.y>255
        cpu.step()
        if op in BRANCHES and cpu.pc!=(pc+2)&65535:
            cycles+=1+(((pc+2)&0xFF00)!=(cpu.pc&0xFF00))
        elapsed+=cycles
    raise AssertionError('raw call did not return')


def prototype(machine):
    r,L=machine.ram,machine.labels
    base=0xE984
    original=bytes(r[L['bonus_sort_try']:L['bonus_sort_try']+90])
    end=original.index(bytes((0x18,0x60)))+2
    code=bytearray(original[:end]);miss=end-2
    count=L['logical_count'];counts=L['BONUS_SORT_COUNT'];ptr=L['world_ptr']
    needle=bytes((0xCD,count&255,count>>8,0xD0))
    position=code.index(needle)+4
    code[position]=end-(position+1)
    def branch(op,target):
        code.append(op);code.append((target-(len(code)+1))&255)
    code.extend((0xC9,12));branch(0xD0,miss)
    code.extend((0xAD,count&255,count>>8,0xC9,14));branch(0xD0,miss)
    code.extend((0x9D,counts&255,counts>>8,0xA0,13,0xA9,4,0x91,ptr,0x88,
                 0xA9,5,0x91,ptr,0x88))
    loop=len(code)
    code.extend((0xB1,ptr,0xC9,4,0x90,2,0x69,1,0x91,ptr,0x88))
    branch(0x10,loop)
    validate=L['bonus_sort_validate'];code.extend((0x4C,validate&255,validate>>8))
    assert len(code)<=124
    return base,code,end


def main():
    release=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    file=BASE/f'build_dbg/sort_lift_capture_{release[:8]}.json'
    cases=json.loads(file.read_text())['cases'] if file.exists() else capture(file,release)
    machine=PlanningMachine();base,code,prefix=prototype(machine);L=machine.labels
    results=[]
    for case in cases:
        original=machine.ram.copy()
        original[:0x800]=bytes.fromhex(case['low'])
        original[0xE800:0xEA00]=bytes.fromhex(case['logs'])
        old=copy.copy(machine);old.ram=original.copy()
        elapsed_old=raw_call(old,L['bonus_sort_try'])
        assert not old.c
        elapsed_old+=raw_call(old,L['bonus_pair_sort'])
        assert old.c
        elapsed_old+=raw_call(old,L['bonus_sort_save'])
        trial=copy.copy(machine);trial.ram=original.copy();trial.ram[base:base+len(code)]=code
        elapsed_new=raw_call(trial,base);hit=bool(trial.c)
        if not hit:
            elapsed_new+=raw_call(trial,L['bonus_pair_sort'])
            elapsed_new+=raw_call(trial,L['bonus_sort_save'])
        n=original[L['logical_count']]
        assert old.ram[L['LOG_ORDER']:L['LOG_ORDER']+n]==trial.ram[L['LOG_ORDER']:L['LOG_ORDER']+n]
        phase=case['phase'];p=L['BONUS_SORT_ORDER']+phase*16
        assert old.ram[p:p+n]==trial.ram[p:p+n]
        steady_old=raw_call(old,L['bonus_sort_try']);steady_new=raw_call(trial,base)
        assert steady_old==steady_new
        results.append(dict(camera=case['camera'],phase=phase,old_count=case['old_count'],
            original_cycles=elapsed_old,lift_cycles=elapsed_new,saved=elapsed_old-elapsed_new,
            promoted_validated=hit,steady_cycles=steady_old))
    report=dict(prg_sha256=release,prototype_ram_address=base,
                prototype_added_bytes=len(code)-prefix,raw_nmos_cycles=True,
                original_includes_try_pair_sort_save=True,cases=results)
    (BASE/'build_dbg/sort_lift_cycles.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
