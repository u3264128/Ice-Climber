#!/usr/bin/env python3
"""Convert the original mountain CHR into a mixed VIC-II gameplay charset.

Terrain uses three shades, with the two shared colours changed at the
original mountain's green/orange/blue boundaries. HUD text, water and clouds
stay hires. No terrain is redrawn by hand: even the sloping mountain edges,
stone texture and the short lower ice brick come from the NES pattern table.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_c64_gfx import C64_COLORS
from nesgfx import NES_PALETTE, chr_tiles
from png import Canvas

BASE = Path(__file__).resolve().parents[1]
NES_TO_VIC_BITS = (0, 3, 1, 2)
PALETTES = {
    "ground": {"nes": [0x0F, 0x38, 0x29, 0x0A], "c64": [0, 7, 13, 5]},
    "mountain": {"nes": [0x0F, 0x27, 0x17, 0x07], "c64": [0, 7, 8, 9]},
    "summit": {"nes": [0x0F, 0x30, 0x21, 0x01], "c64": [0, 1, 14, 6]},
}


def pair_shade(left, right):
    """Keep thin highlight rims and dark seams when reducing two pixels.

Identical pairs are lossless. Mixed pairs always retain an actual source
shade: rim (1), then shadow (3), then face (2). Background wins only when
both source pixels are empty. This retains the exact occupied 2-pixel
silhouette and avoids a numeric max() erasing the light ice rims.
"""
    for shade in (1, 3, 2, 0):
        if shade == left or shade == right:
            return shade
    raise ValueError((left, right))


def multicolour(rows):
    result = bytearray()
    for row in rows:
        value = 0
        for x in range(0, 8, 2):
            value = (value << 2) | NES_TO_VIC_BITS[pair_shade(*row[x:x+2])]
        result.append(value)
    return bytes(result)


def hires(rows, shade=1):
    return bytes(sum((pixel == shade) << (7-x) for x, pixel in enumerate(row))
                 for row in rows)


def packbits(data):
    """Same literal/repeat packets as video.inc's sprite loader."""
    result = bytearray()
    i = 0
    while i < len(data):
        count = 1
        while count < 128 and i+count < len(data) and data[i+count] == data[i]:
            count += 1
        if count >= 3:
            result += bytes([128 | (count-1), data[i]])
            i += count
        else:
            start = i
            while i < len(data) and i-start < 128:
                if i+2 < len(data) and data[i] == data[i+1] == data[i+2]:
                    break
                i += 1
            result.append(i-start-1)
            result += data[start:i]
    return bytes(result)


def main():
    source = (BASE / "extracted/rom/chr_0000-1fff.bin").read_bytes()[0x1000:]
    tiles = chr_tiles(source)
    target = BASE / "c64/build"
    target.mkdir(parents=True, exist_ok=True)
    charset = bytearray(2048)
    digits = (BASE / "converted/charset/charset_hires.bin").read_bytes()[:80]
    charset[:80] = digits
    charset[190*8:200*8] = digits
    records = []
    source_to_char = {0x38: 255, 0x90: 218, 0x92: 227, 0xEB: 224}

    def put(char, tile=None, mode="mc", role="source", data=None, policy=None):
        data = data if data is not None else (
            multicolour(tiles[tile]) if mode == "mc" else hires(tiles[tile]))
        assert len(data) == 8 and 0 <= char < 256
        charset[char*8:char*8+8] = data
        record = dict(char=char, nes_tile=tile, mode=mode, role=role)
        if policy:
            record["policy"] = policy
        records.append(record)

    # Keep the collision-facing semantic IDs stable. Upper map value 2 is
    # unused by the original generator: its unused $91 table entry is the
    # letter S, so use the original full brick as the safe upper fallback.
    for char, tile in ((218, 0x90), (223, 0x90), (226, 0x90), (227, 0x92),
                       (224, 0xEB), (219, 0xB0), (220, 0xC8), (222, 0x90)):
        put(char, tile, role="terrain")
    put(221, 0x31, mode="hires", role="water", policy="mask_nes_1")
    source_to_char[0x31] = 221
    put(216, 0x32, mode="hires", role="water", policy="mask_nes_1")
    source_to_char[0x32] = 216
    # Moving clouds have a separate runtime phase generator. Their hires
    # seed must retain its six-line height and white per-character colour.
    put(225, mode="hires", role="cloud", data=bytes.fromhex("187efffffe7c0000"))
    put(249, 0xCD, role="conveyor")
    put(250, 0xD3, role="conveyor")

    available = list(range(21, 190)) + list(range(200, 216))
    original_tiles = [tile for tile in range(0x40, 0xFC)
                      if tile not in (0x90, 0x92, 0xEB)]
    assert len(available) == len(original_tiles)
    for tile, char in zip(original_tiles, available):
        if 0xEC <= tile <= 0xFB:
            # The two-tile floor numerals have a one-pixel black frame.
            # Pair reduction would turn x=1/6 into edge pixels and erase
            # that frame. Keep their original six-pixel strokes in hires;
            # runtime colour RAM selects yellow or white on black.
            put(char, tile, mode="hires", role="floor_number",
                data=hires(tiles[tile], shade=2), policy="mask_nes_2_black_frame")
        else:
            put(char, tile)
        source_to_char[tile] = char

    (target / "terrain_charset.bin").write_bytes(charset)
    packed = packbits(charset)
    (target / "terrain_charset.rle").write_bytes(packed)
    definitions = ["; Generated by tools/convert_terrain.py from original NES CHR."]
    definitions.extend(f"NES_TILE_{tile:02X} = {char}"
                       for tile, char in sorted(source_to_char.items()))
    (target / "terrain_tiles.inc").write_text("\n".join(definitions)+"\n", encoding="utf-8")
    metadata = dict(chr_sha256=hashlib.sha256(source).hexdigest(),
                    charset_bytes=len(charset), packed_charset_bytes=len(packed),
                    nes_to_vic_bits=NES_TO_VIC_BITS,
                    pair_policy="source highlight 1, shadow 3, face 2; preserve occupied pair",
                    palettes=PALETTES,
                    source_to_char={f"{k:02X}": v for k, v in sorted(source_to_char.items())},
                    tiles=records)
    (target / "terrain.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")

    # Each atlas cell shows NES pixels on the left and C64 pixels on the
    # right. The three sheets share tile order so band palettes can be
    # compared without changing artwork or conversion policy.
    for name, palette in PALETTES.items():
        atlas = Canvas(16*52, ((len(original_tiles)+15)//16)*28, (24, 24, 24))
        for i, tile in enumerate(original_tiles):
            x0, y0 = (i % 16)*52, (i//16)*28
            converted = charset[source_to_char[tile]*8:source_to_char[tile]*8+8]
            for y, row in enumerate(tiles[tile]):
                for x, value in enumerate(row):
                    if 0xEC <= tile <= 0xFB:
                        c64_value = 1 if converted[y] & (0x80 >> x) else 0
                    else:
                        bits = (converted[y] >> (6-2*(x//2))) & 3
                        c64_value = NES_TO_VIC_BITS.index(bits)
                    for dy in range(3):
                        for dx in range(3):
                            atlas.px(x0+x*3+dx, y0+y*3+dy,
                                     NES_PALETTE[palette["nes"][value]])
                            atlas.px(x0+28+x*3+dx, y0+y*3+dy,
                                     C64_COLORS[palette["c64"][c64_value]])
        atlas.save(target / f"terrain_{name}.png")
    print(f"Terrain: {len(original_tiles)} original tiles, 2048-byte charset ({len(packed)} packed)")


if __name__ == "__main__":
    main()
