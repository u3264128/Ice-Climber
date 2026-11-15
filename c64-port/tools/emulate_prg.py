#!/usr/bin/env python3
"""Tiny 6510 test harness: runs the demo .prg without a C64.

Emulates plain RAM plus fake VIC/SID/CIA registers, executes from the SYS
entry point and reports:
  * screen RAM / colour RAM / charset / sprite uploads
  * every SID frequency+control write, translated back to note names
so we can prove the demo actually draws the screen, animates the sprite
and plays the converted music.
"""
import sys
from pathlib import Path

FLAGS_C, FLAGS_Z, FLAGS_I, FLAGS_D, FLAGS_B, FLAGS_U, FLAGS_V, FLAGS_N = (
    1, 2, 4, 8, 16, 32, 64, 128)


class CPU:
    def __init__(self, ram, hooks, decimal_supported=False):
        self.ram = ram
        self.decimal_supported = decimal_supported
        self.hooks = hooks        # dict addr->callable(mem, addr, value|None)
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.pc = 0
        self.c = self.z = self.i = self.d = self.v = self.n = 0

    # --- memory with I/O hooks ----------------------------------------------
    def read(self, a):
        if a in self.hooks:
            r = self.hooks[a](self.ram, a, None)
            if r is not None:
                return r
        return self.ram[a]

    def write(self, a, v):
        self.ram[a] = v & 0xFF
        if a in self.hooks:
            self.hooks[a](self.ram, a, v & 0xFF)

    # --- helpers --------------------------------------------------------------
    def setzn(self, v):
        v &= 0xFF
        self.z = 1 if v == 0 else 0
        self.n = 1 if v & 0x80 else 0

    def push(self, v):
        self.ram[0x100 + self.sp] = v & 0xFF
        self.sp = (self.sp - 1) & 0xFF

    def pop(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.ram[0x100 + self.sp]

    def branch(self, cond):
        off = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        if cond:
            if off & 0x80:
                off -= 0x100
            self.pc = (self.pc + off) & 0xFFFF

    def adc(self, w):
        a, carry = self.a, self.c
        binary = a+w+carry
        self.v = int(bool(~(a^w) & (a^binary) & 0x80))
        self.setzn(binary)
        if self.d and self.decimal_supported:
            lo = (a & 15)+(w & 15)+carry
            if lo > 9: lo += 6
            hi = (a >> 4)+(w >> 4)+(lo > 15)
            if hi > 9: hi += 6
            self.c = int(hi > 15)
            self.a = ((hi << 4) | (lo & 15)) & 255
        else:
            self.c, self.a = int(binary > 255), binary & 255

    def sbc(self, w):
        a, borrow = self.a, 1-self.c
        binary = a-w-borrow
        self.v = int(bool((a^w) & (a^binary) & 0x80))
        self.c = int(binary >= 0)
        self.setzn(binary)
        if self.d and self.decimal_supported:
            lo = (a & 15)-(w & 15)-borrow
            hi = (a >> 4)-(w >> 4)-(lo < 0)
            if lo < 0: lo -= 6
            if hi < 0: hi -= 6
            self.a = ((hi << 4) | (lo & 15)) & 255
        else:
            self.a = binary & 255

    def step(self):
        op = self.read(self.pc)
        pc0 = self.pc
        self.pc = (self.pc + 1) & 0xFFFF
        a = self.a
        # addressing helpers
        def imm():
            v = self.pc
            self.pc = (self.pc + 1) & 0xFFFF
            return v

        def zp():
            v = self.read(imm())
            return v

        def zpx():
            v = (self.read(imm()) + self.x) & 0xFF
            return v

        def zpy():
            v = (self.read(imm()) + self.y) & 0xFF
            return v

        def ab():
            lo = self.read(imm())
            hi = self.read(imm())
            return lo | (hi << 8)

        def abx(w=True):
            b = ab()
            if w:
                return (b + self.x) & 0xFFFF
            return b + self.x, b

        def aby(w=True):
            b = ab()
            if w:
                return (b + self.y) & 0xFFFF
            return b + self.y, b

        def izx():
            z = (self.read(imm()) + self.x) & 0xFF
            return self.ram[z] | (self.ram[(z + 1) & 0xFF] << 8)

        def izy(w=True):
            z = self.read(imm())
            b = self.ram[z] | (self.ram[(z + 1) & 0xFF] << 8)
            if w:
                return (b + self.y) & 0xFFFF
            return b + self.y, b

        def fetch():
            v = self.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return v

        # --- the big opcode switch -------------------------------------------
        if op == 0xA9: self.a = fetch(); self.setzn(self.a)
        elif op == 0xA5: self.a = self.read(zp()); self.setzn(self.a)
        elif op == 0xB5: self.a = self.read(zpx()); self.setzn(self.a)
        elif op == 0xAD: self.a = self.read(ab()); self.setzn(self.a)
        elif op == 0xBD: self.a = self.read(abx()); self.setzn(self.a)
        elif op == 0xB9: self.a = self.read(aby()); self.setzn(self.a)
        elif op == 0xA1: self.a = self.read(izx()); self.setzn(self.a)
        elif op == 0xB1: self.a = self.read(izy()); self.setzn(self.a)
        elif op == 0xA2: self.x = fetch(); self.setzn(self.x)
        elif op == 0xA6: self.x = self.read(zp()); self.setzn(self.x)
        elif op == 0xAE: self.x = self.read(ab()); self.setzn(self.x)
        elif op == 0xB6: self.x = self.read(zpy()); self.setzn(self.x)
        elif op == 0xBE: self.x = self.read(aby()); self.setzn(self.x)
        elif op == 0xA0: self.y = fetch(); self.setzn(self.y)
        elif op == 0xA4: self.y = self.read(zp()); self.setzn(self.y)
        elif op == 0xB4: self.y = self.read(zpx()); self.setzn(self.y)
        elif op == 0xAC: self.y = self.read(ab()); self.setzn(self.y)
        elif op == 0xBC: self.y = self.read(abx()); self.setzn(self.y)
        elif op == 0x85: self.write(zp(), self.a)
        elif op == 0x95: self.write(zpx(), self.a)
        elif op == 0x8D: self.write(ab(), self.a)
        elif op == 0x9D: self.write(abx(), self.a)
        elif op == 0x99: self.write(aby(), self.a)
        elif op == 0x81: self.write(izx(), self.a)
        elif op == 0x91: self.write(izy(), self.a)
        elif op == 0x86: self.write(zp(), self.x)
        elif op == 0x8E: self.write(ab(), self.x)
        elif op == 0x96: self.write(zpy(), self.x)
        elif op == 0x84: self.write(zp(), self.y)
        elif op == 0x8C: self.write(ab(), self.y)
        elif op == 0xAA: self.x = self.a; self.setzn(self.x)
        elif op == 0xA8: self.y = self.a; self.setzn(self.y)
        elif op == 0x8A: self.a = self.x; self.setzn(self.a)
        elif op == 0x98: self.a = self.y; self.setzn(self.a)
        elif op == 0xBA: self.x = self.sp; self.setzn(self.x)
        elif op == 0x9A: self.sp = self.x
        elif op == 0x48: self.push(self.a)
        elif op == 0x68: self.a = self.pop(); self.setzn(self.a)
        elif op == 0x08:
            self.push((self.n << 7) | (self.v << 6) | 0x30 | (self.d << 3)
                      | (self.i << 2) | (self.z << 1) | self.c)
        elif op == 0x28:
            p = self.pop()
            self.n, self.v, self.d = (p >> 7) & 1, (p >> 6) & 1, (p >> 3) & 1
            self.i, self.z, self.c = (p >> 2) & 1, (p >> 1) & 1, p & 1
        elif op == 0x09: self.a |= fetch(); self.setzn(self.a)
        elif op == 0x05: self.a |= self.read(zp()); self.setzn(self.a)
        elif op == 0x0D: self.a |= self.read(ab()); self.setzn(self.a)
        elif op == 0x15: self.a |= self.read(zpx()); self.setzn(self.a)
        elif op == 0x1D: self.a |= self.read(abx()); self.setzn(self.a)
        elif op == 0x19: self.a |= self.read(aby()); self.setzn(self.a)
        elif op == 0x29: self.a &= fetch(); self.setzn(self.a)
        elif op == 0x25: self.a &= self.read(zp()); self.setzn(self.a)
        elif op == 0x2D: self.a &= self.read(ab()); self.setzn(self.a)
        elif op == 0x35: self.a &= self.read(zpx()); self.setzn(self.a)
        elif op == 0x3D: self.a &= self.read(abx()); self.setzn(self.a)
        elif op == 0x39: self.a &= self.read(aby()); self.setzn(self.a)
        elif op == 0x49: self.a ^= fetch(); self.setzn(self.a)
        elif op == 0x45: self.a ^= self.read(zp()); self.setzn(self.a)
        elif op == 0x4D: self.a ^= self.read(ab()); self.setzn(self.a)
        elif op == 0x55: self.a ^= self.read(zpx()); self.setzn(self.a)
        elif op == 0x5D: self.a ^= self.read(abx()); self.setzn(self.a)
        elif op == 0x59: self.a ^= self.read(aby()); self.setzn(self.a)
        elif op == 0x51: self.a ^= self.read(izy()); self.setzn(self.a)
        elif op in (0x24, 0x2C):
            v = self.read(zp() if op == 0x24 else ab())
            self.z = int((self.a & v) == 0)
            self.n, self.v = v >> 7, (v >> 6) & 1
        elif op == 0x06: m = zp(); v = self.read(m) << 1; self.write(m, v); self.setzn(v); self.c = 1 if v & 0x100 else 0
        elif op == 0x0E: m = ab(); v = self.read(m) << 1; self.write(m, v); self.setzn(v); self.c = 1 if v & 0x100 else 0
        elif op == 0x16: m = zpx(); v = self.read(m) << 1; self.write(m, v); self.setzn(v); self.c = 1 if v & 0x100 else 0
        elif op == 0x1E: m = abx(); v = self.read(m) << 1; self.write(m, v); self.setzn(v); self.c = 1 if v & 0x100 else 0
        elif op == 0x46: m = zp(); v = self.read(m); self.c = v & 1; v >>= 1; self.write(m, v); self.setzn(v)
        elif op == 0x26: m = zp(); v = self.read(m); c = v >> 7; v = ((v << 1) | self.c) & 0xFF; self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x66: m = zp(); v = self.read(m); c = v & 1; v = (v >> 1) | (self.c << 7); self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x36: m = zpx(); v = self.read(m); c = v >> 7; v = ((v << 1) | self.c) & 0xFF; self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x76: m = zpx(); v = self.read(m); c = v & 1; v = (v >> 1) | (self.c << 7); self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x2E: m = ab(); v = self.read(m); c = v >> 7; v = ((v << 1) | self.c) & 0xFF; self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x6E: m = ab(); v = self.read(m); c = v & 1; v = (v >> 1) | (self.c << 7); self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x3E: m = abx(); v = self.read(m); c = v >> 7; v = ((v << 1) | self.c) & 0xFF; self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x7E: m = abx(); v = self.read(m); c = v & 1; v = (v >> 1) | (self.c << 7); self.c = c; self.write(m, v); self.setzn(v)
        elif op == 0x4E: m = ab(); v = self.read(m); self.c = v & 1; v >>= 1; self.write(m, v); self.setzn(v)
        elif op == 0x56: m = zpx(); v = self.read(m); self.c = v & 1; v >>= 1; self.write(m, v); self.setzn(v)
        elif op == 0x5E: m = abx(); v = self.read(m); self.c = v & 1; v >>= 1; self.write(m, v); self.setzn(v)
        elif op == 0x0A: self.c = self.a >> 7; self.a = (self.a << 1) & 0xFF; self.setzn(self.a)
        elif op == 0x4A: self.c = self.a & 1; self.a >>= 1; self.setzn(self.a)
        elif op == 0x2A:
            c = self.a >> 7
            self.a = ((self.a << 1) | self.c) & 0xFF
            self.c = c; self.setzn(self.a)
        elif op == 0x6A:
            c = self.a & 1
            self.a = (self.a >> 1) | (self.c << 7)
            self.c = c; self.setzn(self.a)
        elif op in (0xE9, 0xEB): self.sbc(fetch())
        elif op == 0xE5: self.sbc(self.read(zp()))
        elif op == 0xED: self.sbc(self.read(ab()))
        elif op == 0xF5: self.sbc(self.read(zpx()))
        elif op == 0xFD: self.sbc(self.read(abx()))
        elif op == 0xF9: self.sbc(self.read(aby()))
        elif op == 0xF1: self.sbc(self.read(izy()))
        elif op == 0xE1: self.sbc(self.read(izx()))
        elif op == 0xC9:
            w = fetch(); r = self.a - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xC5:
            w = self.read(zp()); r = self.a - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xCD:
            w = self.read(ab()); r = self.a - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xDD:
            w = self.read(abx()); r = self.a - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xD9:
            w = self.read(aby()); r = self.a - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xD5:
            w = self.read(zpx()); r = self.a - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xE0:
            w = fetch(); r = self.x - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xE4:
            w = self.read(zp()); r = self.x - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xEC:
            w = self.read(ab()); r = self.x - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xC0:
            w = fetch(); r = self.y - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xC4:
            w = self.read(zp()); r = self.y - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0xCC:
            w = self.read(ab()); r = self.y - w
            self.c = 1 if r >= 0 else 0; self.setzn(r & 0xFF)
        elif op == 0x69: self.adc(fetch())
        elif op == 0x65: self.adc(self.read(zp()))
        elif op == 0x6D: self.adc(self.read(ab()))
        elif op == 0x75: self.adc(self.read(zpx()))
        elif op == 0x7D: self.adc(self.read(abx()))
        elif op == 0x79: self.adc(self.read(aby()))
        elif op == 0x71: self.adc(self.read(izy()))
        elif op == 0x61: self.adc(self.read(izx()))
        elif op == 0xE6: m = zp(); v = (self.read(m) + 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xEE: m = ab(); v = (self.read(m) + 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xF6: m = zpx(); v = (self.read(m) + 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xFE: m = abx(); v = (self.read(m) + 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xC6: m = zp(); v = (self.read(m) - 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xCE: m = ab(); v = (self.read(m) - 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xD6: m = zpx(); v = (self.read(m) - 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xDE: m = abx(); v = (self.read(m) - 1) & 0xFF; self.write(m, v); self.setzn(v)
        elif op == 0xCA: self.x = (self.x - 1) & 0xFF; self.setzn(self.x)
        elif op == 0x88: self.y = (self.y - 1) & 0xFF; self.setzn(self.y)
        elif op == 0xE8: self.x = (self.x + 1) & 0xFF; self.setzn(self.x)
        elif op == 0xC8: self.y = (self.y + 1) & 0xFF; self.setzn(self.y)
        elif op == 0x4C: self.pc = ab()
        elif op == 0x6C:
            p = ab()
            lo = self.ram[p]
            hi = self.ram[(p & 0xFF00) | ((p + 1) & 0xFF)]
            self.pc = lo | (hi << 8)
        elif op == 0x20:
            lo = fetch(); hi = fetch()
            ret = (self.pc - 1) & 0xFFFF
            self.push((ret >> 8) & 0xFF); self.push(ret & 0xFF)
            self.pc = lo | (hi << 8)
        elif op == 0x60:
            lo = self.pop(); hi = self.pop()
            self.pc = ((lo | (hi << 8)) + 1) & 0xFFFF
        elif op == 0x40:
            p = self.pop(); lo = self.pop(); hi = self.pop()
            self.n, self.v, self.d = (p >> 7) & 1, (p >> 6) & 1, (p >> 3) & 1
            self.i, self.z, self.c = (p >> 2) & 1, (p >> 1) & 1, p & 1
            self.pc = lo | (hi << 8)
        elif op == 0x00:
            raise RuntimeError(f"BRK at ${pc0:04X}")
        # branches
        elif op == 0x10: self.branch(not self.n)
        elif op == 0x30: self.branch(self.n)
        elif op == 0x50: self.branch(not self.v)
        elif op == 0x70: self.branch(self.v)
        elif op == 0x90: self.branch(not self.c)
        elif op == 0xB0: self.branch(self.c)
        elif op == 0xD0: self.branch(not self.z)
        elif op == 0xF0: self.branch(self.z)
        # flags
        elif op == 0x18: self.c = 0
        elif op == 0x38: self.c = 1
        elif op == 0x58: self.i = 0
        elif op == 0x78: self.i = 1
        elif op == 0xB8: self.v = 0
        elif op == 0xD8: self.d = 0
        elif op == 0xF8: self.d = 1
        elif op == 0xEA: pass
        else:
            raise RuntimeError(f"unimplemented opcode ${op:02X} at ${pc0:04X}")


# ----------------------------------------------------------------------------
def sid_note(freq_word: int) -> str:
    if freq_word == 0:
        return "rest"
    f = freq_word * 985248.0 / (1 << 24)
    import math
    midi = round(69 + 12 * math.log2(f / 440.0))
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"


def screenshot(ram, path):
    """Render VIC banked hires/MC text and all eight hardware sprites."""
    from png import Canvas
    from convert_c64_gfx import C64_COLORS
    bg = ram[0xD021] & 15
    c = Canvas(320, 200, fill=C64_COLORS[bg])
    bank = ((~ram[0xDD00]) & 3) * 0x4000
    scr_base = bank + ((ram[0xD018] >> 4) & 15) * 0x400
    chr_base = bank + ((ram[0xD018] >> 1) & 7) * 0x800
    for cy in range(25):
        for cx in range(40):
            char = ram[scr_base+cy*40+cx]
            col = ram[0xD800+cy*40+cx] & 15
            mc = bool(ram[0xD016] & 16 and col & 8)
            colors = [bg, ram[0xD022] & 15, ram[0xD023] & 15, col & 7]
            for y in range(8):
                byte = ram[chr_base+char*8+y]
                for x in range(8):
                    color = (colors[(byte >> (6-(x//2)*2)) & 3] if mc
                             else col if byte & (0x80 >> x) else bg)
                    c.px(cx*8+x, cy*8+y, C64_COLORS[color])
    # Lower-numbered sprites have priority. VIC sprite coordinates include
    # the border; the image above is the 320x200 character display only.
    for number in range(7, -1, -1):
        if not ram[0xD015] & (1 << number):
            continue
        sx = ram[0xD000+number*2] + ((ram[0xD010] >> number) & 1)*256 - 24
        sy = ram[0xD001+number*2] - 50
        pointer = bank + ram[scr_base+0x3F8+number]*64
        colors = [None, ram[0xD025] & 15, ram[0xD026] & 15, ram[0xD027+number] & 15]
        for y in range(21):
            bits = int.from_bytes(ram[pointer+y*3:pointer+y*3+3], 'big')
            for x in range(24):
                color = (colors[(bits >> (22-(x//2)*2)) & 3] if ram[0xD01C] & (1 << number)
                         else colors[3] if bits & (1 << (23-x)) else None)
                if color is not None:
                    c.px(sx+x, sy+y, C64_COLORS[color])
    c.save(path)


def main(prg_path: str, frames: int = 200, shot=None) -> int:
    data = Path(prg_path).read_bytes()
    load = data[0] | (data[1] << 8)
    ram = bytearray(0x10000)
    ram[load:load + len(data) - 2] = data[2:]

    sid_writes = []          # (frame, voice, freq, ctrl)
    raster_state = {"v": 0xF0}
    frame_no = [0]

    def raster_read(mem, a, v):
        # flip $D012 between $FA and $F0 on each read so wait_frame advances;
        # the $FA -> $F0 transition marks one emulated frame
        was = raster_state["v"]
        raster_state["v"] = 0xF0 if was == 0xFA else 0xFA
        if was == 0xFA:
            frame_no[0] += 1
        return raster_state["v"]

    hooks = {}
    sid_shadow = {}

    def sid_write(mem, a, v):
        reg = a - 0xD400
        sid_shadow[reg] = v
        if reg in (0x04, 0x0B, 0x12) and v & 1:      # ctrl gate on
            voice = {0x04: 1, 0x0B: 2, 0x12: 3}[reg]
            if voice == 1:
                freq = sid_shadow.get(0x00, 0) | (sid_shadow.get(0x01, 0) << 8)
            elif voice == 2:
                freq = sid_shadow.get(0x07, 0) | (sid_shadow.get(0x08, 0) << 8)
            else:
                freq = sid_shadow.get(0x0E, 0) | (sid_shadow.get(0x0F, 0) << 8)
            sid_writes.append((frame_no[0], voice, freq, v))

    for a in range(0xD400, 0xD420):
        hooks[a] = sid_write
    hooks[0xD012] = raster_read
    hooks[0xDC01] = lambda mem, addr, value: 255 if value is None else None

    cpu = CPU(ram, hooks)
    cpu.pc = 0x080E
    cpu.sp = 0xFF

    # run: init + main loop; each "wait_frame" pass = one emulated frame
    steps = 0
    last_pc_count = 0
    max_steps = 8_000_000
    while frame_no[0] < frames and steps < max_steps:
        # detect wait_frame exit: count raster reads instead - simpler:
        cpu.step()
        steps += 1
        # a frame about whenever PC returns to the top of main_loop (0x0810-ish);
        # find main_loop by tracking PC hitting the loop head after music_tick
        if cpu.pc == 0x080E or cpu.pc == 0x0000:
            raise RuntimeError(f"PC lost at ${cpu.pc:04X}")
    print(f"executed {steps} steps")
    print(f"SID note events: {len(sid_writes)}")
    for f, v, freq, ctrl in sid_writes[:24]:
        print(f"  frame {f:3d}  voice {v}  freq ${freq:04X}  {sid_note(freq)}")
    if len(sid_writes) > 24:
        print("  ...")
        for f, v, freq, ctrl in sid_writes[-6:]:
            print(f"  frame {f:3d}  voice {v}  freq ${freq:04X}  {sid_note(freq)}")
    # VIC state
    print(f"$D018={ram[0xD018]:02X} $D015={ram[0xD015]:02X} "
          f"$D01C={ram[0xD01C]:02X} $D025={ram[0xD025]:02X} "
          f"$D026={ram[0xD026]:02X} $D027={ram[0xD027]:02X}")
    bank = ((~ram[0xDD00]) & 3) * 0x4000
    scr_base = bank + ((ram[0xD018] >> 4) & 0x0F) * 0x400
    chr_base = bank + ((ram[0xD018] >> 1) & 0x07) * 0x800
    scr = ram[scr_base:scr_base + 1000]
    print(f"screen (${scr_base:04X}): {sum(1 for c in scr if c != 0x20)} "
          f"max index {max(scr)}")
    col = ram[0xD800:0xD800 + 1000]
    print(f"colram: used colours {sorted(set(col))[:12]}")
    print(f"charset non-zero bytes at ${chr_base:04X}: "
          f"{sum(1 for b in ram[chr_base:chr_base + 1744] if b)}")
    print(f"sprites at $5000 non-zero: "
          f"{sum(1 for b in ram[0x5000:0x5A00] if b)}")
    print(f"sprite pointers: ${ram[scr_base + 0x3F8]:02X} "
          f"${ram[scr_base + 0x3F9]:02X}")
    if shot:
        screenshot(ram, shot)
        print(f"screenshot -> {shot}")
    return 0 if sid_writes else 1


if __name__ == "__main__":
    prg = sys.argv[1] if len(sys.argv) > 1 else "../c64/build/iceclimber_demo.prg"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    shot = sys.argv[3] if len(sys.argv) > 3 else None
    raise SystemExit(main(prg, n, shot))
