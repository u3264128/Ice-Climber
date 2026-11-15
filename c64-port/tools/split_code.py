#!/usr/bin/env python3
"""Split the 16 KiB PRG bank into functional modules (code + raw binaries).

Each module gets:
    extracted/code/<name>.asm   - original annotated disassembly excerpt
    extracted/code/bin/<name>.bin - raw 6502 bytes as they sit at $C000+
plus extracted/code/labelmap.csv with every label and its address.
"""
import csv
import sys
from pathlib import Path

MODULES = [
    ('01_reset_interrupts', 0xC000, 0xC150,
     'RESET, NMI, PPU/RAM/audio initialization'),
    ('02_main_loop_screens', 0xC150, 0xC883,
     'Main loop, game states, title/menu/scores, level generation'),
    ('03_ppu_oam', 0xC883, 0xCACE,
     'PPU buffers, OAM DMA, sprite hiding, scrolling'),
    ('04_input_timers', 0xCACE, 0xCB9D,
     'Random number generator, controllers, countdown timers'),
    ('05_object_tables', 0xCB9D, 0xCCF6,
     'Object OAM and position tables'),
    ('06_player', 0xCCF6, 0xD4F5,
     'Player movement, jumping, hammer, blocks, death'),
    ('07_mountains_stages', 0xD4F5, 0xDBB4,
     'Mountain transitions, completion, bonus stages'),
    ('08_physics_collision', 0xDBB4, 0xE26E,
     'Collision helpers, platforms, block handling'),
    ('09_enemies', 0xE26E, 0xEAFC,
     'Bear, Topi and bird movement and interaction'),
    ('10_object_drawing', 0xEAFC, 0xEB2E,
     'Object OAM construction and tile attributes'),
    ('11_object_updates', 0xEB2E, 0xF91E,
     'Object updates, spawning, scores, fruit'),
    ('12_sound_engine', 0xF91E, 0xFD21,
     'APU sound effects and music sequencing'),
    ('13_music_data', 0xFD21, 0xFFFA,
     'Song streams, pitch and duration tables'),
    ('14_vectors', 0xFFFA, 0x10000,
     'NMI/RESET/IRQ vectors'),
]

import re

ANNO_RE = re.compile(r"0x[0-9A-Fa-f]{6} [0-9A-Fa-f]{2}:([0-9A-Fa-f]{4}):")


def anno_addr(line: str):
    """CPU/PPU address of an annotated disassembly line, else None."""
    m = ANNO_RE.search(line)
    if not m:
        return None
    # reject plain comment lines that merely quote an address
    if line.lstrip().startswith(";"):
        return None
    return int(m.group(1), 16)


def main(nes_dir: str, out_dir: str) -> None:
    src = Path(nes_dir) / "bank_FF.asm"
    prg = (Path(out_dir).parent / "rom" / "prg_c000-ffff.bin").read_bytes()
    out = Path(out_dir)
    (out / "bin").mkdir(parents=True, exist_ok=True)

    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()

    # pre-scan: map each line -> its address (data and code lines)
    line_addr = []
    for ln in lines:
        line_addr.append(anno_addr(ln))

    # ---- module .asm/.bin cuts --------------------------------------------
    index = []
    for name, lo, hi, desc in MODULES:
        sel = [ln for ln, a in zip(lines, line_addr)
               if a is not None and lo <= a < hi]
        header = [f"; === {name}  ($%04X-$%04X, %d bytes) ===" % (lo, hi, hi - lo),
                  f"; {desc}", ""]
        (out / f"{name}.asm").write_text("\n".join(header + sel) + "\n",
                                         encoding="utf-8")
        (out / "bin" / f"{name}_{lo:04X}-{hi:04X}.bin").write_bytes(
            prg[lo - 0xC000:hi - 0xC000])
        index.append({"module": name, "from": f"${lo:04X}", "to": f"${hi-1:04X}",
                      "bytes": hi - lo, "description": desc,
                      "asm": f"code/{name}.asm",
                      "bin": f"code/bin/{name}_{lo:04X}-{hi:04X}.bin"})
        print(f"{name:28s} ${lo:04X}-${hi:04X}  {hi-lo:5d} B  {len(sel):4d} lines")

    # ---- label map ----------------------------------------------------------
    sys.path.insert(0, str(Path(__file__).parent))
    from bzk_parse import parse_project
    proj = parse_project(Path(nes_dir))
    with open(out / "labelmap.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["address", "label", "segment"])
        for a, n in sorted((a, n) for n, (s, a) in proj.label_space.items()):
            w.writerow([f"${a:04X}", n, proj.label_space[n][0]])

    (out / "modules.json").write_text(
        __import__("json").dumps(index, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    nes = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2])
    dst = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parents[1] / "extracted/code")
    main(nes, dst)
