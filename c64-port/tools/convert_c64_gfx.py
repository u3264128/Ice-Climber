#!/usr/bin/env python3
"""Convert extracted NES graphics to C64 (VIC-II) formats.

Outputs under converted/:

  palettes/nes2c64.bin        64 bytes: NES palette index -> VIC-II colour
  palettes/nes2c64.json       human-readable mapping incl. RGB deltas
  palettes/title_palette.txt  the game's palettes translated to C64 colours
  charset/charset_hires.bin   218 bg tiles -> 1bpp C64 charset (8 B/char)
  charset/charset_hires.col   per-char colour RAM bytes
  charset/charset_mc.bin      same tiles as multicolour charset (8 B/char)
  charset/charset_mc.json     per-char colour + shared MC colour assignment
  charset/*.png               previews rendered with VIC-II colours
  sprites/sprites_mc_all.bin  128 metatiles -> 63-byte MC sprites
  sprites/sprites_meta.json   metatile index -> tile ids, colours
  sprites/sprites_mc.png      preview sheet
  screens/title_c64.bin       C64 screen (40x25 chars) + colours for demo

Conversion rules
  colours : nearest VIC-II colour by RGB distance (preview-palette based)
  charset : hires = any non-zero pixel -> set bit, colour byte = dominant
            colour; multicolor = 4 levels kept (00 bg, 01 mc1, 10 mc2,
            11 per-char), half horizontal resolution
  sprites : 16x16 NES metatile -> 24x21 C64 multicolour sprite,
            NES values map 0->transp, 1->01, 2->11 (sprite colour),
            3->10; half horizontal resolution
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nesgfx import NES_PALETTE, chr_tiles, decode_tile  # noqa: E402
from png import Canvas  # noqa: E402

# VIC-II colour indices -> RGB (common VICE palette)
C64_COLORS = [
    (0x00, 0x00, 0x00),   # 0 black
    (0xFF, 0xFF, 0xFF),   # 1 white
    (0x81, 0x33, 0x38),   # 2 red
    (0x75, 0xCE, 0xC8),   # 3 cyan
    (0x8E, 0x3C, 0x97),   # 4 purple
    (0x56, 0xAC, 0x4D),   # 5 green
    (0x2E, 0x2C, 0x9B),   # 6 blue
    (0xED, 0xF1, 0x71),   # 7 yellow
    (0x8E, 0x50, 0x29),   # 8 orange
    (0x55, 0x38, 0x00),   # 9 brown
    (0xC4, 0x6C, 0x71),   # 10 light red
    (0x4A, 0x4A, 0x4A),   # 11 dark grey
    (0x7B, 0x7B, 0x7B),   # 12 grey
    (0xA9, 0xFF, 0x9F),   # 13 light green
    (0x70, 0x6D, 0xEB),   # 14 light blue
    (0xB2, 0xB2, 0xB2),   # 15 light grey
]
C64_NAMES = ["black", "white", "red", "cyan", "purple", "green", "blue",
             "yellow", "orange", "brown", "light red", "dark grey", "grey",
             "light green", "light blue", "light grey"]

NES_NAMES = {0x0F: "black", 0x30: "white", 0x21: "blue", 0x01: "dark blue",
             0x26: "salmon", 0x2A: "green", 0x38: "pale yellow",
             0x29: "orange", 0x0A: "green", 0x27: "orange-red",
             0x17: "peach", 0x07: "brown", 0x11: "pale blue",
             0x15: "violet", 0x12: "blue"}


def dist(a, b) -> int:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def nes_to_c64(nes_idx: int) -> int:
    """Nearest VIC-II colour for a NES palette index."""
    rgb = NES_PALETTE[nes_idx & 0x3F]
    return min(range(16), key=lambda c: dist(rgb, C64_COLORS[c]))


# ---------------------------------------------------------------------------
def convert_palette(out: Path) -> dict:
    table = [nes_to_c64(i) for i in range(64)]
    (out / "palettes").mkdir(parents=True, exist_ok=True)
    (out / "palettes" / "nes2c64.bin").write_bytes(bytes(table))
    used = [0x0F, 0x30, 0x21, 0x01, 0x26, 0x2A, 0x38, 0x29, 0x0A, 0x27,
            0x17, 0x07, 0x11, 0x15, 0x12]
    info = {"_comment": "NES index -> VIC-II colour (nearest RGB)",
            "used_by_game": {f"${i:02X}": {"name": NES_NAMES.get(i, "?"),
                                            "c64": f"${table[i]:02X}",
                                            "c64_name": C64_NAMES[table[i]]}
                             for i in used},
            "table_0x00_0x3f": [f"${t:02X}" for t in table]}
    (out / "palettes" / "nes2c64.json").write_text(json.dumps(info, indent=1))

    # title palette translation (from PRG $C694)
    bg_pal = [[0x0F, 0x30, 0x21, 0x01], [0x0F, 0x26, 0x2A, 0x30],
              [0x0F, 0x38, 0x29, 0x0A], [0x0F, 0x27, 0x17, 0x07]]
    spr_pal = [[0x0F, 0x30, 0x11, 0x26], [0x0F, 0x30, 0x15, 0x26],
               [0x0F, 0x30, 0x21, 0x12], [0x0F, 0x38, 0x29, 0x0A]]
    lines = ["Ice Climber palettes (PRG $C694) -> C64 VIC-II",
             "", "background:"]
    for i, p in enumerate(bg_pal):
        c64 = [nes_to_c64(c) for c in p]
        lines.append(f"  pal{i}: NES {' '.join(f'{c:02X}' for c in p)}"
                     f"  ->  C64 {' '.join(f'{c:02X}' for c in c64)}"
                     f"   ({', '.join(C64_NAMES[c] for c in c64)})")
    lines.append("sprites:")
    for i, p in enumerate(spr_pal):
        c64 = [nes_to_c64(c) for c in p]
        lines.append(f"  pal{i}: NES {' '.join(f'{c:02X}' for c in p)}"
                     f"  ->  C64 {' '.join(f'{c:02X}' for c in c64)}"
                     f"   ({', '.join(C64_NAMES[c] for c in c64)})")
    (out / "palettes" / "title_palette.txt").write_text("\n".join(lines))
    return table


# ---------------------------------------------------------------------------
def load_bg_tiles(rom_dir: Path) -> list:
    """Background tiles in C64 charset order.

    NES tile indices 10-47 fall inside the PPU-script data hole stored in
    the pattern table and are never used as graphics.  The C64 charset
    therefore renumbers: charset char 0-9 = NES tiles 0-9,
    charset char 10-217 = NES tiles 48-255.  The screen converter uses
    the same remap, so char indices line up 1:1.
    """
    chr_bytes = (rom_dir / "chr_0000-1fff.bin").read_bytes()

    def tile(idx):
        return decode_tile(chr_bytes[0x1000 + idx * 16:0x1000 + idx * 16 + 16])

    return [tile(i) for i in range(0, 10)] + [tile(i) for i in range(48, 256)]


def convert_charset(rom_dir: Path, out: Path, n2c: dict) -> None:
    tiles = load_bg_tiles(rom_dir)
    (out / "charset").mkdir(parents=True, exist_ok=True)

    hires = bytearray()
    colors = bytearray()
    mc = bytearray()
    mc_meta = []
    # title screen palette 0 (menu/box) for dominant-colour decisions
    pal0 = [0x0F, 0x30, 0x21, 0x01]
    for t in tiles:
        # --- hires: bit set for any non-zero pixel ------------------------
        for y in range(8):
            byte = 0
            for x in range(8):
                byte = (byte << 1) | (1 if t[y][x] else 0)
            hires.append(byte)
        counts = [0, 0, 0, 0]
        for row in t:
            for v in row:
                counts[v] += 1
        dom = max(range(1, 4), key=lambda v: counts[v])
        colors.append(n2c[pal0[dom]])

        # --- multicolor: keep 4 levels, half horizontal resolution --------
        # C64 MC char: still 8 bytes/char; each byte = 4 MC pixels,
        # bitpairs MSB-first: 00 = d021 bg, 01 = d022 mc1, 10 = d023 mc2,
        # 11 = colour RAM (low 3 bits; bit 3 of colour RAM enables MC)
        for y in range(8):
            byte = 0
            for x in range(0, 8, 2):
                v = max(t[y][x], t[y][x + 1])
                byte = (byte << 2) | v
            mc.append(byte)
        nonzero = [v for v in (1, 2, 3) if counts[v] > 0]
        mc_meta.append({"char": len(mc_meta),
                        "levels_used": nonzero,
                        "colour_ram": f"${n2c[pal0[dom]]:02X}"})

    (out / "charset" / "charset_hires.bin").write_bytes(hires)
    (out / "charset" / "charset_hires.col").write_bytes(colors)
    (out / "charset" / "charset_mc.bin").write_bytes(mc)
    meta = {"chars": len(tiles),
            "layout_hires": "8 bytes/char, bit set = pixel on, colour from "
                            "charset_hires.col (colour RAM)",
            "layout_mc": "8 bytes/char, 4 MC pixels per byte (2 bits, "
                         "MSB first): 00=d021 bg, 01=d022 mc1, 10=d023 mc2, "
                         "11=colour RAM & 7 (set colour RAM bit 3 for MC)",
            "mc_shared": {"d022_mc1": "$01 white", "d023_mc2": "$06 blue"},
            "chars_meta": mc_meta}
    (out / "charset" / "charset_mc.json").write_text(json.dumps(meta, indent=1))

    # ---- previews with VIC-II colours ------------------------------------
    def sheet_hires(path):
        c = Canvas(8 * 16, 8 * ((len(tiles) + 15) // 16), fill=C64_COLORS[6])
        for i in range(len(tiles)):
            x0, y0 = (i % 16) * 8, (i // 16) * 8
            col = C64_COLORS[colors[i]]
            for y in range(8):
                byte = hires[i * 8 + y]
                for x in range(8):
                    if byte & (0x80 >> x):
                        c.px(x0 + x, y0 + y, col)
        c.save(path)

    def sheet_mc(path):
        c = Canvas(8 * 16 * 2, 8 * ((len(tiles) + 15) // 16), fill=C64_COLORS[0])
        for i in range(len(tiles)):
            x0, y0 = (i % 16) * 16, (i // 16) * 8
            cmap = {0: C64_COLORS[0], 1: C64_COLORS[1],
                    2: C64_COLORS[6], 3: C64_COLORS[colors[i] & 0x0F]}
            for y in range(8):
                byte = mc[i * 8 + y]
                for x in range(4):
                    v = (byte >> (6 - x * 2)) & 3
                    c.px(x0 + x * 2, y0 + y, cmap[v])
                    c.px(x0 + x * 2 + 1, y0 + y, cmap[v])
        c.save(path)

    sheet_hires(out / "charset" / "charset_hires.png")
    sheet_mc(out / "charset" / "charset_mc.png")
    print(f"charset: {len(tiles)} chars -> hires {len(hires)} B, "
          f"mc {len(mc)} B")


# ---------------------------------------------------------------------------
def metatile(tiles, base: int):
    """16x16 pixel matrix from 4 sprite tiles (n, n+1, n+16, n+17).

    The bottom tile row of the pattern table ($F0-$FF) has no row below;
    metatiles there get an empty lower half.
    """
    empty = [[0] * 8 for _ in range(8)]
    rows = []
    for y in range(16):
        top = y < 8
        t0 = tiles[base] if top else (tiles[base + 16] if base + 16 < 256 else empty)
        t1 = (tiles[base + 1] if top else
              (tiles[base + 17] if base + 17 < 256 else empty))
        rows.append(t0[y % 8] + t1[y % 8])
    return rows


def sprite_63(rows16) -> bytes:
    """Pack a 24x21 C64 multicolour sprite from a 16x16 NES matrix.

    NES value -> MC bitpair: 0 -> 00 (transparent), 1 -> 01 (mc1),
    2 -> 11 (sprite colour), 3 -> 10 (mc2).  16 NES px -> 8 MC px wide,
    drawn at x=4..19 (8..15 unused), y=2..17.
    """
    grid = [[0] * 12 for _ in range(21)]
    for y in range(16):
        for mx in range(8):
            v = max(rows16[y][mx * 2], rows16[y][mx * 2 + 1])
            pair = {0: 0, 1: 1, 2: 3, 3: 2}[v]
            grid[y + 2][2 + mx] = pair
    out = bytearray(63)
    for y in range(21):
        for mx in range(12):
            pair = grid[y][mx]
            bit1 = pair & 1
            bit2 = (pair >> 1) & 1
            byte_i = y * 3 + mx // 4
            bit_pos = 7 - ((mx % 4) * 2)
            out[byte_i] |= bit2 << bit_pos
            out[byte_i] |= bit1 << (bit_pos - 1)
    return bytes(out)


def sprite_63_hires(rows16, value: int) -> bytes:
    """24x21 C64 hires sprite (1bpp) with a bit set for every NES pixel
    equal to `value` - full horizontal resolution, one colour."""
    out = bytearray(63)
    for y in range(16):
        for x in range(16):
            if rows16[y][x] == value:
                px = 4 + x                     # centrer i 24 px
                byte_i = (y + 2) * 3 + px // 8
                out[byte_i] |= 0x80 >> (px % 8)
    return bytes(out)


def sprite_63_mc_values(rows16, mapping: dict) -> bytes:
    """24x21 C64 MC sprite from a value->bitpair mapping (half h-res).
    mapping values: 0 = transparent, 1 = mc1 ($D025), 2 = mc2 ($D026),
    3 = individual colour."""
    grid = [[0] * 12 for _ in range(21)]
    for y in range(16):
        for mx in range(8):
            raw = max(rows16[y][mx * 2], rows16[y][mx * 2 + 1])
            grid[y + 2][2 + mx] = mapping.get(raw, 0)
    out = bytearray(63)
    for y in range(21):
        for mx in range(12):
            pair = grid[y][mx]
            byte_i = y * 3 + mx // 4
            bit_pos = 7 - ((mx % 4) * 2)
            out[byte_i] |= ((pair >> 1) & 1) << bit_pos
            out[byte_i] |= (pair & 1) << (bit_pos - 1)
    return bytes(out)


def convert_sprites(rom_dir: Path, out: Path) -> None:
    chr_bytes = (rom_dir / "chr_0000-1fff.bin").read_bytes()
    tiles = chr_tiles(chr_bytes[:0x1000])
    (out / "sprites").mkdir(parents=True, exist_ok=True)

    all_sprites = bytearray()
    all_hires = bytearray()
    all_mc2 = bytearray()
    meta = {"_comment": "metatile i uses sprite tiles (2i, 2i+1, 2i+16, "
                        "2i+17).  Two variants per metatile: "
                        "sprites_mc_all.bin = single multicolour sprite; "
                        "2-layer = sprites_hires_all.bin (full-resolution "
                        "layer, one colour = dominant NES value) overlaid "
                        "with sprites_mc2_all.bin (MC layer with the two "
                        "remaining colours).",
            "colours": {"d025_mc1": "$01 white",
                        "d026_mc2": "$0A light red (skin)",
                        "sprite_colour_player": "$0E light blue"},
            "mapping_single_mc": "NES 0->transparent, 1->mc1(white), "
                                 "2->sprite colour, 3->mc2(skin)",
            "mapping_2layer": "dominant NES value -> hires bit (full res); "
                              "other two -> MC pairs 01/10",
            "sprites": []}

    # player palette value -> C64 colour (sprite palette 0 from PRG $C694:
    # 0F 30 11 26 -> transparent, white, pale blue, salmon)
    val_col = {1: 1, 2: 14, 3: 10}

    for i in range(128):
        rows = metatile(tiles, i * 2)
        all_sprites += sprite_63(rows)

        counts = [0, 0, 0, 0]
        for r in rows:
            for v in r:
                counts[v] += 1
        used = [v for v in (1, 2, 3) if counts[v]]
        dom = max(used, key=lambda v: counts[v]) if used else 1
        others = [v for v in (1, 2, 3) if v != dom]
        o_mc1, o_mc2 = (others + [None, None])[:2]
        all_hires += sprite_63_hires(rows, dom)
        mapping = {}
        if o_mc1 is not None:
            mapping[o_mc1] = 1        # 01 -> mc1
        if o_mc2 is not None:
            mapping[o_mc2] = 2        # 10 -> mc2
        all_mc2 += sprite_63_mc_values(rows, mapping)

        meta["sprites"].append({
            "metatile": i,
            "nes_tiles": [f"${i*2:02X}", f"${i*2+1:02X}",
                          f"${i*2+16:02X}", f"${i*2+17:02X}"],
            "dominant_value": dom,
            "hires_colour": f"${val_col.get(dom, 1):02X}",
            "mc1_value": o_mc1, "mc2_value": o_mc2})

    (out / "sprites" / "sprites_mc_all.bin").write_bytes(all_sprites)
    (out / "sprites" / "sprites_hires_all.bin").write_bytes(all_hires)
    (out / "sprites" / "sprites_mc2_all.bin").write_bytes(all_mc2)
    (out / "sprites" / "sprites_meta.json").write_text(json.dumps(meta, indent=1))

    # preview sheet of the 2-layer variant: hires colour at full resolution
    # + MC accents (drawn 2 px wide), 16 per row
    c = Canvas(16 * 25 - 1, 8 * 22 - 1, fill=(30, 30, 30))
    for i in range(128):
        x0, y0 = (i % 16) * 25, (i // 16) * 22
        entry = meta["sprites"][i]
        hcol = C64_COLORS[int(entry["hires_colour"][1:], 16)]
        mc1c = C64_COLORS[1]
        mc2c = C64_COLORS[10]
        for y in range(21):
            hbits = "".join(f"{all_hires[i*63+y*3+b]:08b}" for b in range(3))
            mbits = "".join(f"{all_mc2[i*63+y*3+b]:08b}" for b in range(3))
            for px in range(24):
                if hbits[px] == "1":
                    c.px(x0 + px, y0 + y, hcol)
                else:
                    pair = mbits[(px // 2) * 2:(px // 2) * 2 + 2]
                    col = {"01": mc1c, "10": mc2c}.get(pair)
                    if col:
                        c.px(x0 + px, y0 + y, col)
    c.save(out / "sprites" / "sprites_2layer.png")
    print(f"sprites: 128 metatiles -> MC {len(all_sprites)} B, "
          f"2-layer {len(all_hires)}+{len(all_mc2)} B")


# ---------------------------------------------------------------------------
def convert_screen(rom_dir: Path, out: Path, n2c: dict) -> None:
    """Mixed hires/MC title font: coloured logo, full-resolution menu text.

    The title has its own compact font.  A single hires mask cannot show
    the white logo panel AND its blue lettering.  MC cells use shared white
    and light blue, with dark blue as the cell colour.  Single-colour text
    stays hires even with VIC multicolour text mode enabled.
    """
    nam = (Path(__file__).parent.parent / "extracted" / "screens"
           / "title_screen.nam").read_bytes()
    pal = (Path(__file__).parent.parent / "extracted" / "screens"
           / "title_screen.pal").read_bytes()
    assert len(nam) == 960 + 64
    chr_bytes = (rom_dir / "chr_0000-1fff.bin").read_bytes()
    tiles = chr_tiles(chr_bytes[0x1000:])
    font = [bytes(8)]                       # char zero really is blank
    screen = bytearray(40 * 25)
    colors = bytearray(40 * 25)
    preview = Canvas(320, 200)
    source_rows = list(range(2, 27))
    source_rows[-1] = 27                    # retain copyright below scores
    for ty, sy in enumerate(source_rows):
        for tx in range(32):
            nes_tile = nam[sy * 32 + tx]
            if sy == 18:                   # this port currently supports 1P
                nes_tile = 0x38
            assert nes_tile < 10 or nes_tile >= 48, "PPU script used as graphics"
            attr = nam[960 + (sy // 4) * 8 + tx // 4]
            shift = ((sy % 4) // 2) * 4 + ((tx % 4) // 2) * 2
            pal_i = (attr >> shift) & 3
            tile = tiles[nes_tile]
            counts = [0, 0, 0, 0]
            for row in tile:
                for v in row:
                    counts[v] += 1
            used = [v for v in range(1, 4) if counts[v]]
            cmap = [n2c[pal[pal_i * 4 + v]] for v in range(4)]
            if sy <= 13:
                # White panel, light blue letters, dark blue edge.
                pairs = {0: 0, 1: 1, 2: 2, 3: 3}
                glyph = bytes(sum(pairs[tile[y][x]] << (6 - x)
                                  for x in range(0, 8, 2)) for y in range(8))
                color = 8 | 6
                rendered = [[(0, 1, 14, 6)[(glyph[y] >> (6 - (x//2)*2)) & 3]
                             for x in range(8)] for y in range(8)]
            else:
                dom = max(used, key=lambda v: counts[v]) if used else 0
                # In mixed mode bit 3 selects MC, so hires colours are 0..7.
                color = min(range(8), key=lambda c: dist(C64_COLORS[c], C64_COLORS[cmap[dom]]))
                glyph = bytes(sum((1 if tile[y][x] else 0) << (7-x)
                                  for x in range(8)) for y in range(8))
                rendered = [[color if v else 0 for v in row] for row in tile]
            if glyph not in font:
                font.append(glyph)
            cell = ty * 40 + tx + 4
            screen[cell] = font.index(glyph)
            colors[cell] = color
            for y in range(8):
                for x in range(8):
                    preview.px((tx+4)*8+x, ty*8+y, C64_COLORS[rendered[y][x]])
    assert len(font) <= 128, "Title font exceeds four pages"
    (out / "screens").mkdir(parents=True, exist_ok=True)
    (out / "charset" / "title_charset.bin").write_bytes(b"".join(font).ljust(1024, b"\0"))
    (out / "screens" / "title_c64.bin").write_bytes(screen)
    (out / "screens" / "title_c64.col").write_bytes(colors)
    preview.save(out / "screens" / "title_c64.png")
    print(f"screen: 40x25, {len(font)} title glyphs (hires + multicolour)")


if __name__ == "__main__":
    base = Path(__file__).parent.parent
    rom_dir = base / "extracted" / "rom"
    out = base / "converted"
    n2c = convert_palette(out)
    convert_charset(rom_dir, out, n2c)
    convert_sprites(rom_dir, out)
    convert_screen(rom_dir, out, n2c)
