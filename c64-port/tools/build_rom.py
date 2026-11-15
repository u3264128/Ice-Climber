#!/usr/bin/env python3
"""Rebuild the original NES ROM from the disassembly and verify SHA-1.

Proof that our extraction pipeline is byte-perfect: the rebuilt ROM must match
the original Ice Climber (J) image checksum 1690E419BC2435739EFBE59A64D83538FF7E16B4.
Outputs under extracted/rom/:
    iceclimber.nes      full iNES image (header + PRG + CHR)
    prg_c000-ffff.bin   16 KiB program bank (machine code + data)
    chr_0000-1fff.bin   8 KiB character ROM (pattern tables)
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bzk_parse import parse_project, build_images  # noqa: E402

EXPECTED_SHA1 = "1690E419BC2435739EFBE59A64D83538FF7E16B4"
EXPECTED_SIZE = 24592


def main(nes_dir: str, out_dir: str) -> int:
    nes_dir, out_dir = Path(nes_dir), Path(out_dir)
    proj = parse_project(nes_dir)
    image = build_images(proj)

    header = (nes_dir / "header.bin").read_bytes()
    body = bytes(image[0x10:])           # PRG+CHR without the iNES header
    rom = header + body
    sha1 = hashlib.sha1(rom).hexdigest().upper()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "iceclimber.nes").write_bytes(rom)
    (out_dir / "prg_c000-ffff.bin").write_bytes(body[:0x4000])
    (out_dir / "chr_0000-1fff.bin").write_bytes(body[0x4000:0x6000])

    print(f"ROM image   : {len(rom)} bytes (expected {EXPECTED_SIZE})")
    print(f"SHA-1       : {sha1}")
    print(f"Expected    : {EXPECTED_SHA1}")
    if sha1 == EXPECTED_SHA1 and len(rom) == EXPECTED_SIZE:
        print("VERIFIED: rebuilt ROM is byte-identical to the original.")
        return 0
    print("MISMATCH - extraction is not faithful, do not trust downstream data!")
    return 1


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2])
    dst = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parents[1] / "extracted/rom")
    raise SystemExit(main(src, dst))
