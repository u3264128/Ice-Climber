"""Official 6502 opcodes: opcode -> (mnemonic, addressing mode)."""

MODES_SIZE = {'imp': 1, 'acc': 1, 'imm': 2, 'zp': 2, 'zpx': 2, 'zpy': 2, 'rel': 2,
              'indx': 2, 'indy': 2, 'abs': 3, 'absx': 3, 'absy': 3, 'ind': 3}

_TABLE = """
ADC 69imm 65zp 75zpx 6Dabs 7Dabsx 79absy 61indx 71indy
AND 29imm 25zp 35zpx 2Dabs 3Dabsx 39absy 21indx 31indy
ASL 0Aacc 06zp 16zpx 0Eabs 1Eabsx
BCC 90rel
BCS B0rel
BEQ F0rel
BIT 24zp 2Cabs
BMI 30rel
BNE D0rel
BPL 10rel
BRK 00imp
BVC 50rel
BVS 70rel
CLC 18imp
CLD D8imp
CLI 58imp
CLV B8imp
CMP C9imm C5zp D5zpx CDabs DDabsx D9absy C1indx D1indy
CPX E0imm E4zp ECabs
CPY C0imm C4zp CCabs
DEC C6zp D6zpx CEabs DEabsx
DEX CAimp
DEY 88imp
EOR 49imm 45zp 55zpx 4Dabs 5Dabsx 59absy 41indx 51indy
INC E6zp F6zpx EEabs FEabsx
INX E8imp
INY C8imp
JMP 4Cabs 6Cind
JSR 20abs
LDA A9imm A5zp B5zpx ADabs BDabsx B9absy A1indx B1indy
LDX A2imm A6zp B6zpy AEabs BEabsy
LDY A0imm A4zp B4zpx ACabs BCabsx
LSR 4Aacc 46zp 56zpx 4Eabs 5Eabsx
NOP EAimp
ORA 09imm 05zp 15zpx 0Dabs 1Dabsx 19absy 01indx 11indy
PHA 48imp
PHP 08imp
PLA 68imp
PLP 28imp
ROL 2Aacc 26zp 36zpx 2Eabs 3Eabsx
ROR 6Aacc 66zp 76zpx 6Eabs 7Eabsx
RTI 40imp
RTS 60imp
SBC E9imm E5zp F5zpx EDabs FDabsx F9absy E1indx F1indy
SEC 38imp
SED F8imp
SEI 78imp
STA 85zp 95zpx 8Dabs 9Dabsx 99absy 81indx 91indy
STX 86zp 96zpy 8Eabs
STY 84zp 94zpx 8Cabs
TAX AAimp
TAY A8imp
TSX BAimp
TXA 8Aimp
TXS 9Aimp
TYA 98imp
"""

OPCODES = {}
ENCODE = {}
for line in _TABLE.strip().splitlines():
    mnemonic, *forms = line.split()
    for form in forms:
        opcode, mode = int(form[:2], 16), form[2:]
        OPCODES[opcode] = (mnemonic, mode)
        ENCODE[(mnemonic, mode)] = opcode
assert len(OPCODES) == 151


def widen(mnemonic, mode):
    """The absolute form of a zero-page mode, or None if the 6502 has none."""
    wide = {'zp': 'abs', 'zpx': 'absx', 'zpy': 'absy'}.get(mode)
    return wide if wide and (mnemonic, wide) in ENCODE else None
