#!/usr/bin/env python3
"""Transplant the original NES enemy object code into the C64 build.

The NES and the C64 share the 6502. Instead of re-writing Topi, the ice
blocks, the polar bear, the icicles, Nitpicker and the hammer/touch hit boxes
by hand, this tool takes every instruction reachable from the original
per-frame object entries in bank_FF.asm and emits it as ca65 source:

* RAM operands are moved to the C64 addresses in RAM_MAP. Zero-page NES
  variables stay in zero page where the addressing mode needs it.
* Branches, jumps and calls inside the closure become local labels. Calls
  and jumps to the routines in GLUE (player handler, death, random, PPU and
  OAM writes) become calls to C64 glue routines.
* ROM tables read by the code are copied byte for byte.
* The instruction bytes are checked against the original PRG.

The output is c64/build/nes_objects.inc. tools/test_nes_objects.py runs the
same entries in the original ROM and in the C64 build side by side.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nes6502 import ENCODE, MODES_SIZE, OPCODES, widen
from transplant_sound import ZERO_PAGE as SOUND_ZERO_PAGE

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE.parent/'bank_FF.asm'
PRG = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()

# The original per-frame order ($CBFB) for objects, after the players.
ENTRIES = {
    0xEFEC: 'nes_topi_spawn',       # two seals and their ice
    0xE189: 'nes_bear_tick',        # polar bear states
    0xEE0D: 'nes_objects_tick',     # objects 1..7: walk, carry, fall
    0xEF9A: 'nes_bear_drop',        # bear landing after a pan
    0xF10B: 'nes_icicles_tick',     # three icicles
    0xD3AC: 'nes_hammer_hits',      # hammer against objects
    0xD301: 'nes_touch_hits',       # objects against players
    0xF838: 'nes_bird_tick',        # Nitpicker
    0xDE22: 'nes_ice_blocks',       # pushed ice fills a hole
    0xEC51: 'nes_pan_objects',      # each pan tick moves objects 4 lines
    0xD861: 'nes_pan_end',          # objects four floors below are hidden
    0xF19E: 'nes_icicle_reset',     # X = icicle: new random delay
    0xF80C: 'nes_bird_init',        # Nitpicker waits at its start
    0xE002: 'nes_stones_init',      # stage start and pan ticks: stone posts
    0xE0B9: 'nes_stone_push',       # stone posts push the climbers aside
    0xD212: 'nes_body_bump',        # two climbers that touch push each other
}
# Code that does not fit the RAM under I/O goes to other RAM that is not
# ROM with $01 = $34 either: (first, end) -> segment. Default IOCODE.
CODE_SEGMENTS = {
    (0xE0B9, 0xE185): 'HELPERS',
    (0xD211, 0xD2D9): 'CODE',       # $D212 and its $D2BC; $D2D9 stays under I/O
}
# ROM tables in other segments than IODATA ($D400, one page).
TABLE_SEGMENTS = {
    0xDEF6: 'DATA', 0xDEFA: 'DATA', 0xDF1B: 'DATA',     # stone posts per mountain
}
# Original instructions replaced by C64 code: start -> (end, lines, falls
# through). Everything else is the original instruction stream.
PATCHES = {
    # $DE22 waits for an empty PPU buffer; the C64 patches its screen itself.
    0xDE22: (0xDE2A, [], True),
    # The filled cell's nametable/attribute writes become a C64 cell patch.
    0xDE4D: (0xDE83, ['jsr glue_ice_filled'], True),
    # $DEB9 reads both block planes. The C64 planes use 0 for air and 3 for
    # the lower post; the glue returns the original values ($FF air, 4 post).
    0xDEDB: (0xDEDD, ['jsr glue_lower_cell'], True),
    0xDEE1: (0xDEE3, ['jsr glue_upper_cell'], True),
    # Players move with the C64 pan; only the objects move here.
    0xEC74: (0xEC82, [], True),
    # The OAM copy is redrawn from the objects by the C64.
    0xEC95: (0xECB7, ['rts'], False),
}
# Original routines that the C64 provides itself.
GLUE = {
    0xD07C: 'glue_end_attack',      # hammer hit: the player's attack ends
    0xD446: 'glue_kill_player',     # an object touched the player
}

# NES RAM -> C64 address. Blocks keep their internal layout.
ZP_BLOCKS = [
    (0x00, 0x0F, 0xD8),             # routine temporaries
    (0x16, 0x1F, 0xE8),             # ram_random (two bytes before for $16,X)
    (0x8E, 0xC7, 0x9D),             # object state, X, Y, floor, direction
    (0x68, 0x69, 0xF2),             # player push direction (STY zp,X)
    (0x7C, 0x7C, 0xF4),             # bear phase, also read by the C64 $D7DE
    (0x3A, 0x3B, 0xFE),             # per-player push timers ($CB9D, every tick)
]
# The sound requests ($FC noise, $FE pulse 2, $FF pulse 1) are the
# transplanted sound engine's own bytes (tools/transplant_sound.py).
ZP_BLOCKS += [(nes, nes, SOUND_ZERO_PAGE[nes]) for nes in (0xFC, 0xFE, 0xFF)]
ABS_BLOCKS = [
    (0x0376, 0x03F2, 0x026C),       # object counters, animation, attributes
    (0x0360, 0x0369, 0x0240),       # result counters: same layout as SCORE_COUNTS
    (0x48, 0x4F, 0x02F2),           # slow timers ($CB9D, every eleventh tick)
    (0x0600, 0x062F, 0xD070),       # stone posts: X, Y and right edge ($E002)
    (0x6E, 0x6F, 0xD0A0),           # walk speed ($D212 sets $18)
    (0xE8, 0xE9, 0xD0A2),           # fall speed fractions ($D212 swaps them)
    (0x86, 0x89, 0xD0A4),           # head and landing latches ($D212 clears them)
    (0x02D0, 0x02E7, 0x01A8),       # debris OAM: also drawn and panned by the C64
    (0x0640, 0x0667, 0xD0A8),       # debris motion: Y fraction, speed, X step, age
]
# NES variables that are C64 variables with the same meaning.
SHARED = {
    0x3D: 'bear_timer',             # $D7DE's spawn timer, already original
    0x56: 'completed_mountains',
}
MIRRORS = {}                        # filled from MIRROR_ORDER below
MIRROR_BASE = 0xD040                # RAM under I/O: only this code uses it
MIRROR_ORDER = [
    0x2D, 0x2E,                     # per-player object immunity
    0x50,                           # frame counter
    0x55,                           # game phase
    0x59,                           # raw mountain counter
    0x5A, 0x5B,                     # player floors
    0x5F,                           # player index
    0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x6A, 0x6B,
    0x90,                           # upper visible floor
    0xDC, 0xDD, 0xDF,               # bear landing / jump counters
    0xFC, 0xFD, 0xFE, 0xFF,         # sound requests
    0xD9,                           # ice block floor
    0x021C, 0x021D, 0x021E, 0x021F, 0x0220, 0x0221, 0x0222, 0x0223,  # mallet OAM
    0x0786, 0x0787, 0x0788, 0x0789, 0x078A, 0x078B, 0x078C, 0x078D,
    0x078E, 0x078F,                 # two cloud objects: floor, X, ..
    0xE6, 0xE7,                     # player fall accumulators
]
for index, address in enumerate(MIRROR_ORDER):
    MIRRORS[address] = MIRROR_BASE+index

JUMP_WORDS = {}
# Symbols for the C64 glue: name -> NES address.
SYMBOLS = {
    'NES_OBJ_STATE': 0x91, 'NES_OBJ_X': 0x9C, 'NES_OBJ_Y': 0xA7, 'NES_OBJ_FLOOR': 0xB2,
    'NES_OBJ_DIR': 0xBD, 'NES_UPPER_FLOOR': 0x90, 'NES_TEMP': 0x00, 'NES_RANDOM': 0x18,
    'NES_PUSH_DIR': 0x68, 'NES_BEAR_PHASE': 0x7C,
    'NES_PAN_FLAG': 0x0376, 'NES_OBJ_0382': 0x0382, 'NES_OBJ_SPEED': 0x03A6,
    'NES_OBJ_ANIM': 0x03DD, 'NES_OBJ_ATTR': 0x03E8, 'NES_OBJ_03D2': 0x03D2,
    'NES_IMMUNE': 0x2D, 'NES_TIMERS': 0x48, 'NES_FRAME': 0x50, 'NES_PHASE': 0x55,
    'NES_RAW_MOUNTAIN': 0x59, 'NES_PLAYER_FLOOR': 0x5A, 'NES_PLAYER_INDEX': 0x5F,
    'NES_PLAYER_POSE': 0x60, 'NES_FACING': 0x62, 'NES_PLAYER_X': 0x64, 'NES_PLAYER_Y': 0x66,
    'NES_HANDLER': 0x6A, 'NES_ICE_FLOOR': 0xD9, 'NES_BEAR_DROP': 0xDC, 'NES_BEAR_DROP_T': 0xDD,
    'NES_BEAR_COUNT': 0xDF, 'NES_SFX_1': 0xFC, 'NES_SFX_2': 0xFE, 'NES_SFX_3': 0xFF,
    'NES_MALLET_OAM': 0x021C, 'NES_CLOUD_OBJ': 0x0786,
    'NES_PUSH_T': 0x3A, 'NES_FALL': 0xE6, 'NES_STONES': 0x0600,
    'NES_WALK': 0x6E, 'NES_FALL_FRAC': 0xE8, 'NES_LATCH': 0x86,
    'NES_DEBRIS_OAM': 0x02D0, 'NES_DEBRIS': 0x0640,
}

LINE = re.compile(r'^([C-]) ([D-]) ([-0-9]) ([-J]) ([-I]) - 0x([0-9A-F]{6}) '
                  r'00:([0-9A-F]{4}): ((?:[0-9A-F]{2} ){1,3})\s*(.*)$')


def parse():
    ins, labels, pending = {}, {}, []
    for raw in SOURCE.read_text(encoding='latin-1').splitlines():
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):', raw)
        if m:
            pending.append(m.group(1))
            continue
        m = LINE.match(raw)
        if not m:
            continue
        address = int(m.group(7), 16)
        data = bytes(int(x, 16) for x in m.group(8).split())
        if not m.group(9).startswith('.') and m.group(1) == 'C':
            # The listing shows some BIT-skipped instructions with the $2C
            # in front. The PRG bytes at the address are authoritative.
            opcode = PRG[address-0xC000]
            data = PRG[address-0xC000:address-0xC000+MODES_SIZE[OPCODES[opcode][1]]]
        assert PRG[address-0xC000:address-0xC000+len(data)] == data, hex(address)
        ins[address] = (m.group(1), data, m.group(9))
        if pending:
            labels[address] = pending
            pending = []
    return ins, labels


def map_ram(address):
    for lo, hi, base in ZP_BLOCKS:
        if lo <= address <= hi:
            return base+address-lo
    for lo, hi, base in ABS_BLOCKS:
        if lo <= address <= hi:
            return base+address-lo
    if address in MIRRORS:
        return MIRRORS[address]
    if address in SHARED:
        return SHARED[address]
    raise KeyError(f'NES RAM ${address:04X} has no C64 address')


def instruction(ins, address):
    kind, data, text = ins[address]
    if text.startswith('.byte') and data[0] == 0x2C:
        return 'bit3', data
    if text.startswith('.'):
        return 'data', data
    mnemonic, mode = OPCODES[data[0]]
    return (mnemonic, mode), data


def successors(ins, address):
    if address in PATCHES:
        end, lines, falls = PATCHES[address]
        return ([end] if falls else []), []
    form, data = instruction(ins, address)
    if form == 'bit3':
        # The skipped instruction must be emitted even when nothing jumps
        # to it: its two bytes are the BIT operand.
        return [address+3, address+1], []
    if form == 'data':
        return [], []
    mnemonic, mode = form
    if mnemonic in ('RTS', 'RTI'):
        return [], []
    if mnemonic == 'JMP':
        if mode == 'ind':
            if address != 0xC73A:   # only the C728 dispatcher jumps through RAM
                raise ValueError(f'indirect jump at ${address:04X}')
            return [], []
        target = data[1] | data[2] << 8
        return ([], [target]) if target in GLUE else ([target], [])
    if mnemonic == 'JSR':
        target = data[1] | data[2] << 8
        if target == 0xC728:
            # sub_C728_jump_to_pointers_after_jsr: the words after the JSR
            entries, k = [], address+3
            while k in ins and ins[k][2].startswith('.word'):
                word = ins[k][1]
                entries.append(word[0] | word[1] << 8)
                JUMP_WORDS[k] = word[0] | word[1] << 8
                k += 2
            return entries, [target]
        return [address+3], [target]
    if mode == 'rel':
        offset = data[1]-256 if data[1] > 127 else data[1]
        return [address+2, address+2+offset], []
    return [address+len(data)], []


def closure(ins):
    seen, work = set(), list(ENTRIES)
    while work:
        address = work.pop()
        if address in seen or address in GLUE:
            continue
        assert address in ins, hex(address)
        seen.add(address)
        follow, calls = successors(ins, address)
        work.extend(follow)
        work.extend(t for t in calls if t not in GLUE)
    return seen


def table_extent(ins, labels, start):
    """Bytes of the ROM data table that holds start, up to the next label."""
    end = start+1
    while end < 0x10000 and end not in labels and (end not in ins or ins[end][0] != 'C'):
        end += 1
    return end


# $D2F9 in the loops that run every tick: $DB1D's hostile hit boxes (touch
# and hammer) and $E0C0's stone posts.
INLINE_ABS = {0xDB71, 0xDB90, 0xE0EF, 0xE0FF}


def generate():
    ins, labels = parse()
    code = closure(ins)
    targets = set(ENTRIES) | set(JUMP_WORDS.values())
    tables = {}
    zp_needed = {}
    for address in code:
        if address in PATCHES:
            continue
        form, data = instruction(ins, address)
        if form in ('bit3', 'data'):
            continue
        mnemonic, mode = form
        if mode == 'rel':
            follow, _ = successors(ins, address)
            targets.add(follow[1])
        elif mnemonic in ('JMP', 'JSR'):
            target = data[1] | data[2] << 8
            if target not in GLUE:
                targets.add(target)
        elif MODES_SIZE[mode] == 3:
            operand = data[1] | data[2] << 8
            if operand >= 0x8000:
                tables[operand] = None
    # "BIT abs" ($2C) skips a two-byte instruction. When the skipped
    # instruction's RAM operand leaves zero page it grows to three bytes;
    # a JMP past it does the skip then (it keeps every flag; the original
    # code after such skips does not test BIT's flags).
    bit_jumps = set()
    for address in code:
        if address in PATCHES or instruction(ins, address)[0] != 'bit3':
            continue
        (mnemonic, mode), data = instruction(ins, address+1)
        assert MODES_SIZE[mode] == 2, hex(address)
        if mode in ('zp', 'zpx', 'zpy'):
            c64 = map_ram(data[1])
            if isinstance(c64, str) or c64 > 0xFF:
                bit_jumps.add(address)
                targets.add(address+3)
    # Data tables: emit each labelled ROM block that an operand points into.
    blocks = {}
    data_labels = sorted(a for a in labels if a in ins and ins[a][0] != 'C')
    for operand in tables:
        below = [a for a in data_labels if a <= operand]
        start = below[-1] if below else None
        if start is None or table_extent(ins, labels, start) <= operand:
            # "tbl - $02,X": the operand lies just before its table
            start = min(a for a in data_labels if a > operand)
            assert start-operand <= 4, hex(operand)
        blocks[start] = table_extent(ins, labels, start)
        tables[operand] = start
    out = ['; Generated by tools/transplant_objects.py from bank_FF.asm. Do not edit.',
           '; Every instruction below is an original NES instruction; only RAM',
           '; operands, labels and the glue calls differ.']
    for address, name in sorted(ENTRIES.items()):
        out.append(f'{name} = N_{address:04X}')
    previous_end = None
    for start, (end, lines, falls) in PATCHES.items():
        inside = [a for a in targets if start < a < end]
        assert not inside, (hex(start), [hex(a) for a in inside])
    segment = 'IOCODE'
    for address in sorted(code):
        wanted = next((name for (lo, hi), name in CODE_SEGMENTS.items() if lo <= address < hi), 'IOCODE')
        if wanted != segment:
            out.append('')
            out.append(f'.segment "{wanted}"')
            segment = wanted
            previous_end = None
        if address in PATCHES:
            end, lines, falls = PATCHES[address]
            if previous_end is not None and address != previous_end:
                out.append('')
            if address in targets or address in ENTRIES:
                out.append(f'N_{address:04X}:')
            out.append(f'        ; ${address:04X}-${end-1:04X} replaced by C64 code')
            out.extend(f'        {line}' for line in lines)
            previous_end = end
            continue
        form, data = instruction(ins, address)
        if previous_end is not None and address != previous_end:
            out.append('')
        if address in targets or address in ENTRIES:
            out.append(f'N_{address:04X}:')
        previous_end = address+len(data)
        if form == 'bit3':
            nxt = address+1
            assert nxt in code
            if address in bit_jumps:
                out.append(f'        jmp N_{address+3:04X}            ; ${address:04X}: BIT skip of a widened instruction')
                previous_end = None
            else:
                out.append(f'        .byte $2C               ; ${address:04X} skips the next two bytes')
            continue
        mnemonic, mode = form
        operand = None
        if mode in ('zp', 'zpx', 'zpy', 'indx', 'indy'):
            nes = data[1]
            c64 = map_ram(nes)
            if isinstance(c64, str) or c64 > 0xFF:
                wide = widen(mnemonic, mode)
                if wide is None:
                    zp_needed.setdefault(nes, []).append(f'{mnemonic} ${address:04X}')
                    c64 = 'ZP_NEEDED'
                else:
                    mode = wide
            operand = c64
        elif mode == 'ind':
            operand = map_ram(data[1] | data[2] << 8)
        elif mode in ('abs', 'absx', 'absy'):
            nes = data[1] | data[2] << 8
            if mnemonic in ('JMP', 'JSR'):
                operand = GLUE.get(nes, f'N_{nes:04X}')
            elif nes >= 0x8000:
                start = tables[nes]
                operand = f'T_{start:04X}' + (f'{nes-start:+d}' if nes != start else '')
            else:
                c64 = map_ram(nes)
                if not isinstance(c64, str) and c64 < 0x100:
                    mode = {'abs': 'zp', 'absx': 'zpx', 'absy': 'zpy'}[mode] \
                        if (mnemonic, {'abs': 'zp', 'absx': 'zpx', 'absy': 'zpy'}[mode]) in ENCODE else mode
                operand = c64
        elif mode == 'rel':
            follow, _ = successors(ins, address)
            operand = f'N_{follow[1]:04X}'
        if mnemonic == 'JSR' and address in INLINE_ABS:
            # $D2F9 (A = |A| of a signed difference): the same four
            # instructions in place of the call (no stack use, same flags).
            assert data[1] | data[2] << 8 == 0xD2F9
            out.append(f'        bpl :+                        ; ${address:04X}: JSR $D2F9 inlined')
            out.append('        eor #$FF')
            out.append('        clc')
            out.append('        adc #$01')
            out.append(':')
            continue
        text = format_instruction(mnemonic, mode, operand, data)
        out.append(f'        {text:30s}; ${address:04X}')
        k = address+len(data)
        while k in JUMP_WORDS:
            out.append(f'        .word N_{JUMP_WORDS[k]:04X}          ; ${k:04X}')
            k += 2
            previous_end = k
    segment = None
    for start, end in sorted(blocks.items(), key=lambda b: (TABLE_SEGMENTS.get(b[0], 'IODATA'), b[0])):
        if TABLE_SEGMENTS.get(start, 'IODATA') != segment:
            segment = TABLE_SEGMENTS.get(start, 'IODATA')
            out.append('')
            out.append(f'.segment "{segment}"')
            out.append('; Original ROM tables read by the code above.')
        data = PRG[start-0xC000:end-0xC000]
        out.append(f'T_{start:04X}:')
        for i in range(0, len(data), 8):
            out.append('        .byte ' + ','.join(f'${b:02X}' for b in data[i:i+8]))
    if zp_needed:
        raise SystemExit('Zero page needed for: ' + ', '.join(
            f'${k:02X} ({", ".join(v)})' for k, v in sorted(zp_needed.items())))
    size = sum(len(instruction(ins, a)[1]) for a in code if a not in PATCHES)
    return '\n'.join(out)+'\n', size, sum(e-s for s, e in blocks.items())


def format_instruction(mnemonic, mode, operand, data):
    m = mnemonic.lower()
    def addr(value, width):
        if isinstance(value, str):
            return value
        return f'${value:0{width}X}'
    if mode in ('imp',):
        return m
    if mode == 'acc':
        return f'{m} a'
    if mode == 'imm':
        return f'{m} #${data[1]:02X}'
    if mode == 'zp':
        return f'{m} z:{addr(operand, 2)}'
    if mode == 'zpx':
        return f'{m} z:{addr(operand, 2)},x'
    if mode == 'zpy':
        return f'{m} z:{addr(operand, 2)},y'
    if mode == 'indx':
        return f'{m} ({addr(operand, 2)},x)'
    if mode == 'indy':
        return f'{m} ({addr(operand, 2)}),y'
    if mode == 'abs':
        return f'{m} a:{addr(operand, 4)}'
    if mode == 'absx':
        return f'{m} a:{addr(operand, 4)},x'
    if mode == 'absy':
        return f'{m} a:{addr(operand, 4)},y'
    if mode == 'rel':
        return f'{m} {operand}'
    if mode == 'ind':
        return f'{m} (${operand:04X})'
    raise ValueError(mode)


def main():
    text, size, table_bytes = generate()
    target = BASE/'c64/build/nes_objects.inc'
    target.write_text(text, encoding='ascii')
    symbols = ['; Generated by tools/transplant_objects.py: NES RAM in the C64 build.']
    for name, address in SYMBOLS.items():
        c64 = map_ram(address)
        text = c64 if isinstance(c64, str) else f'${c64:02X}' if c64 < 0x100 else f'${c64:04X}'
        symbols.append(f'{name:18s} = {text:8s} ; NES ${address:04X}')
    symbols.append(f'NES_MIRROR_FIRST   = ${MIRROR_BASE:04X}')
    symbols.append(f'NES_MIRROR_END     = ${MIRROR_BASE+len(MIRROR_ORDER):04X}')
    (BASE/'c64/build/nes_symbols.inc').write_text(chr(10).join(symbols)+chr(10), encoding='ascii')
    print(f'nes objects: {size} code bytes from {len(ENTRIES)} original entries, '
          f'{table_bytes} table bytes -> {target.relative_to(BASE)}')


if __name__ == '__main__':
    main()
