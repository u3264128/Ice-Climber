#!/usr/bin/env python3
"""Reconstruct NES screens from the PPU update scripts found in the ROM.

Ice Climber draws its static screens through compact buffer scripts:

    <addr-hi> <addr-lo>          PPU destination ($2000-$2FFF / $3F00-$3F1F)
    <mode | count>               mode bits: 00=bytes-h, 40=fill-h,
                                                80=bytes-v, C0=fill-v
    <data ...>                   count bytes, or 1 byte for fill modes
    ...                          more entries
    $00                          end token

Sources used here (all verified in the disassembly):
    PPU $10A0 (stored inside CHR)   title/logo screen nametable script
    PPU $1204                       score screen script
    PPU $12E3                       score screen palette
    PPU $11EC                       title screen palette
    PRG $C694                       full 32-byte palette set (logo screen)
    PRG $C6B8                       mountain preview attribute/tile script

Outputs (extracted/screens/):
    title_screen.nam/.pal/.png      reconstructed title screen
    score_screen.nam/.pal/.png      score screen (delta applied)
    mountain_attr.nam (attrs only), mountain_preview.png
    ppu_scripts.json                decoded script entries
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nesgfx import NES_PALETTE, chr_tiles  # noqa: E402
from png import Canvas  # noqa: E402


class PPU:
    """2 nametables + attributes + palette, targeted by PPU addresses."""

    def __init__(self):
        # Reset clears nametables to the blank CHR tile, not digit zero.
        self.nt = [bytearray([0x38] * (32 * 30)) for _ in range(2)]
        self.attr = [bytearray(64), bytearray(64)]
        self.pal = bytearray(32)

    def write(self, addr: int, val: int) -> None:
        addr &= 0x3FFF
        if 0x3F00 <= addr <= 0x3F1F:
            self.pal[addr - 0x3F00] = val
            return
        base = addr & 0x0C00
        nt_i = 0 if base in (0x0000, 0x0400) else 1
        if base == 0x0400:            # vertical mirroring maps 2400->2000
            nt_i = 0
        if base == 0x0C00:            # 2C00 mirrors 2800
            nt_i = 1
        off = addr & 0x03FF
        if off < 0x3C0:
            self.nt[nt_i][off] = val
        else:
            self.attr[nt_i][off - 0x3C0] = val

    def attr_read(self, nt_i: int, tx: int, ty: int) -> int:
        a = self.attr[nt_i][(ty // 4) * 8 + (tx // 4)]
        shift = ((ty % 4) // 2) * 4 + ((tx % 4) // 2) * 2
        return (a >> shift) & 3

    def run_script(self, blob: bytes, start: int) -> list:
        entries = []
        p = start
        while True:
            hi = blob[p]
            if hi == 0:
                p += 1
                break
            addr = (hi << 8) | blob[p + 1]
            if not (0x2000 <= addr < 0x3000 or 0x3F00 <= addr <= 0x3F1F):
                raise ValueError(f"Invalid PPU destination ${addr:04X} at ${p:04X}")
            mode = blob[p + 2]
            count = mode & 0x3F
            kind = mode & 0xC0
            p += 3
            if kind in (0x00, 0x80):          # run of distinct tiles
                data = blob[p:p + count]
                p += count
            else:                              # fill with one tile
                data = bytes([blob[p]])
                p += 1
            for i, t in enumerate(data * count if kind in (0x40, 0xC0) else data):
                if kind in (0x00, 0x40):       # horizontal
                    self.write(addr + i, t)
                else:                          # vertical
                    self.write(addr + i * 32, t)
            entries.append({"ppu": f"${addr:04X}", "mode": f"${mode:02X}",
                            "count": count, "data": data.hex(" ")})
        return entries, p


def tile_pix(chr_bytes: bytes, idx: int) -> list[list[int]]:
    """8x8 pixels for background tile index (bg pattern table at $1000).

    The CHR image is linear: idx<10 -> $1000, idx>=48 -> $1300 (both are
    simply $1000+idx*16).  Indices 10-47 fall inside the embedded PPU-script
    data hole and are never referenced as tiles.
    """
    off = 0x1000 + idx * 16
    data = chr_bytes[off:off + 16]
    if len(data) < 16:
        data = data + b"\x00" * (16 - len(data))
    return chr_tiles(data)[0]


def render_screen(ppu: PPU, chr_bytes: bytes, nt_i: int, path: str,
                  scale: int = 2) -> None:
    c = Canvas(256 * scale, 240 * scale, fill=NES_PALETTE[0x0F])
    for ty in range(30):
        for tx in range(32):
            pal_i = ppu.attr_read(nt_i, tx, ty)
            colors = [NES_PALETTE[ppu.pal[pal_i * 4 + k] & 0x3F] for k in range(4)]
            pix = tile_pix(chr_bytes, ppu.nt[nt_i][ty * 32 + tx])
            for y in range(8):
                for x in range(8):
                    col = colors[pix[y][x]]
                    for sy in range(scale):
                        for sx in range(scale):
                            c.px(tx * 8 * scale + x * scale + sx,
                                 ty * 8 * scale + y * scale + sy, col)
    c.save(path)


def ascii_screen(ppu: PPU, chr_bytes: bytes, nt_i: int) -> str:
    """Full-resolution ASCII render: 240 lines x 256 chars, 4 grey levels."""
    out = []
    for ty in range(30):
        rows = [""] * 8
        for tx in range(32):
            pix = tile_pix(chr_bytes, ppu.nt[nt_i][ty * 32 + tx])
            for y in range(8):
                rows[y] += "".join(
                    "@" if v == 3 else "#" if v == 2 else
                    "." if v == 1 else " " for v in pix[y])
        out.extend(rows)
    return "\n".join(out)


def main(nes_dir: str, out_dir: str) -> None:
    rom_dir = Path(__file__).parent.parent / "extracted" / "rom"
    prg = (rom_dir / "prg_c000-ffff.bin").read_bytes()
    chr_bytes = (rom_dir / "chr_0000-1fff.bin").read_bytes()

    def prg_at(addr: int) -> bytes:
        return prg[addr - 0xC000:]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    scripts = {}

    # --- title screen -------------------------------------------------------
    ppu = PPU()
    # logo screen script: PPU $10A0 (inside CHR), palette from PRG $C694
    ents, _ = ppu.run_script(chr_bytes, 0x10A0)
    scripts["title_screen_script_ppu_10A0"] = ents
    ppu.run_script(prg_at(0xC694), 0)                       # full 32-colour palette
    ents, _ = ppu.run_script(chr_bytes, 0x11EC)             # actual title palette
    scripts["title_screen_palette_ppu_11EC"] = ents
    title_pal = bytes(ppu.pal)

    (out / "title_screen.nam").write_bytes(bytes(ppu.nt[0]) + bytes(ppu.attr[0]))
    (out / "title_screen.pal").write_bytes(title_pal)
    render_screen(ppu, chr_bytes, 0, out / "title_screen.png")

    # ASCII preview (top half) for terminal inspection
    (out / "title_screen.txt").write_text(ascii_screen(ppu, chr_bytes, 0))

    # --- score screen has its own script, starting at $1204 -----------------
    ppu2 = PPU()
    ents2, _ = ppu2.run_script(chr_bytes, 0x1204)
    scripts["score_screen_script_ppu_1204"] = ents2
    ppu2.run_script(prg_at(0xC694), 0)
    ents3, _ = ppu2.run_script(chr_bytes, 0x12E3)
    scripts["score_screen_palette_ppu_12E3"] = ents3
    (out / "score_screen.nam").write_bytes(bytes(ppu2.nt[0]) + bytes(ppu2.attr[0]))
    (out / "score_screen.pal").write_bytes(bytes(ppu2.pal))
    render_screen(ppu2, chr_bytes, 0, out / "score_screen.png")

    # --- mountain preview (attribute script in PRG $C6B8) -------------------
    ppu3 = PPU()
    ents4, _ = ppu3.run_script(prg_at(0xC6B8), 0)
    scripts["mountain_preview_script_prg_C6B8"] = ents4
    (out / "mountain_attr.nt2").write_bytes(bytes(ppu3.nt[1]) + bytes(ppu3.attr[1]))
    render_screen(ppu3, chr_bytes, 1, out / "mountain_preview.png")

    (out / "ppu_scripts.json").write_text(json.dumps(scripts, indent=1))
    print("screens reconstructed:", ", ".join(sorted(p.name for p in out.iterdir())))
    print("title palette:", title_pal.hex(" "))


if __name__ == "__main__":
    nes = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2])
    dst = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parents[1] / "extracted/screens")
    main(nes, dst)
