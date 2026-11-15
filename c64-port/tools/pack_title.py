"""Losslessly pack the title screen, colours and font for the C64 build."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_terrain import packbits

base = Path(__file__).resolve().parents[1]
colours = (base/'converted/screens/title_c64.col').read_bytes()
assert len(colours) <= 1024
colours += bytes(1024-len(colours))
packed = packbits(colours)
(base/'c64/build/title_colours.rle').write_bytes(packed)
print(f'Title colours: {len(colours)} bytes -> {len(packed)} packed')
screen = (base/'converted/screens/title_c64.bin').read_bytes()
assert len(screen) <= 1024
screen += bytes(1024-len(screen))
packed = packbits(screen)
(base/'c64/build/title_screen.rle').write_bytes(packed)
print(f'Title screen: {len(screen)} bytes -> {len(packed)} packed')
font = (base/'converted/charset/title_charset.bin').read_bytes()
assert len(font) == 1024
packed = packbits(font)
(base/'c64/build/title_charset.rle').write_bytes(packed)
print(f'Title font: {len(font)} bytes -> {len(packed)} packed')
