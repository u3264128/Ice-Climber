#!/usr/bin/env python3
"""Extract CHR pattern tables from the rebuilt CHR-ROM.

Ice Climber memory layout (sprite pattern table = PPU $0000, background
pattern table = PPU $1000, per $2000 = #$10 in the RESET routine):

    $0000-$0FFF  sprite tiles (256 x 8x8, 2bpp)   -> CHR_ROM_1.chr
    $1000-$109F  background tiles (10)
    $10A0-$12FF  screen/palette update scripts stored inside CHR space
    $1300-$1FFF  background tiles (208)

Outputs (extracted/chr + extracted/graphics):
    sprites_pattern0.bin        raw 4 KiB sprite pattern table (NES 2bpp)
    bg_pattern1_1000.bin        bg tiles at PPU $1000 (NES 2bpp)
    bg_pattern1_1300.bin        bg tiles at PPU $1300 (NES 2bpp)
    ppu_10a0-1300_data.bin      embedded PPU update scripts
    *.png                       tile sheets for visual reference
    chr_map.json                tile index -> file/sheet position map
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nesgfx import chr_tiles, NES_PALETTE  # noqa: E402
from png import Canvas  # noqa: E402

# neutral 4-step ramp for structure previews (value 0 = transparent for sprites)
RAMP = [NES_PALETTE[0x0F], (0x60, 0x60, 0x60), (0xB0, 0xB0, 0xB0), NES_PALETTE[0x30]]


def sheet(tiles, per_row: int, tile_px: int = 8, gap: int = 1) -> Canvas:
    rows = (len(tiles) + per_row - 1) // per_row
    c = Canvas(per_row * (tile_px + gap) - gap, rows * (tile_px + gap) - gap,
               fill=(20, 20, 20))
    for i, t in enumerate(tiles):
        x0 = (i % per_row) * (tile_px + gap)
        y0 = (i // per_row) * (tile_px + gap)
        c.blit(x0, y0, t, RAMP)
    return c


def main(chr_path: str, out_dir: str) -> None:
    chr_bytes = Path(chr_path).read_bytes()
    assert len(chr_bytes) == 0x2000
    out = Path(out_dir)
    (out / "chr").mkdir(parents=True, exist_ok=True)
    (out / "graphics" / "tiles").mkdir(parents=True, exist_ok=True)

    spr_tbl = chr_bytes[0x0000:0x1000]
    bg_lo = chr_bytes[0x1000:0x10A0]
    mid = chr_bytes[0x10A0:0x1300]
    bg_hi = chr_bytes[0x1300:0x2000]

    (out / "chr" / "sprites_pattern0.bin").write_bytes(spr_tbl)
    (out / "chr" / "bg_pattern1_1000.bin").write_bytes(bg_lo)
    (out / "chr" / "bg_pattern1_1300.bin").write_bytes(bg_hi)
    (out / "chr" / "ppu_10a0-1300_data.bin").write_bytes(mid)

    # ---- tile sheets ------------------------------------------------------
    spr_tiles = chr_tiles(spr_tbl)
    bg_tiles = chr_tiles(bg_lo) + chr_tiles(bg_hi)

    sheet(spr_tiles, 16).save(out / "graphics" / "tiles" / "sprites_pattern0.png")
    sheet(bg_tiles, 16).save(out / "graphics" / "tiles" / "bg_pattern1.png")

    # ---- stats + map ------------------------------------------------------
    def used(tiles):
        return sum(1 for t in tiles if any(v for row in t for v in row))

    uniq = {}
    for i, t in enumerate(spr_tiles):
        key = bytes(v for row in t for v in row)
        uniq.setdefault(key, []).append(i)
    dup_groups = [v for v in uniq.values() if len(v) > 1]

    info = {
        "sprites": {
            "file": "chr/sprites_pattern0.bin",
            "ppu_base": "0x0000",
            "tiles": 256,
            "nonempty": used(spr_tiles),
            "sheet": "graphics/tiles/sprites_pattern0.png",
            "sheet_layout": "16 tiles per row, index = row*16 + col",
            "duplicate_groups": dup_groups,
        },
        "background": {
            "files": {"0x1000": "chr/bg_pattern1_1000.bin",
                      "0x1300": "chr/bg_pattern1_1300.bin"},
            "tiles_0x1000": 10,
            "tiles_0x1300": 208,
            "nonempty": used(bg_tiles),
            "sheet": "graphics/tiles/bg_pattern1.png",
            "sheet_layout": "16 per row; indices 0-9 = PPU $1000-... (file bg_pattern1_1000.bin), 10-217 = PPU $1300-...",
        },
        "ppu_data_hole": {
            "file": "chr/ppu_10a0-1300_data.bin",
            "note": "PPU update scripts (nametable/palette/attribute writes) stored inside pattern table 1",
        },
    }
    (out / "chr" / "chr_map.json").write_text(json.dumps(info, indent=2))

    print(f"sprites: {used(spr_tiles)}/256 tiles non-empty, "
          f"{len(dup_groups)} duplicate groups")
    print(f"bg     : {used(bg_tiles)}/218 tiles non-empty")


if __name__ == "__main__":
    chr_p = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "extracted/rom/chr_0000-1fff.bin")
    dst = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parents[1] / "extracted")
    main(chr_p, dst)
