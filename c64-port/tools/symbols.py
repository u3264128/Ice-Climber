"""Linker labels plus fixed hardware/runtime addresses from the sources."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def read_symbols():
    labels = {n: int(a, 16) for a, n in re.findall(
        r'al ([0-9A-Fa-f]+) \.([A-Za-z_]\w*)', (BASE/'c64/build/game.lbl').read_text())}
    for name in ('game.asm', 'runtime.inc', 'video.inc', 'preview.asm'):
        source = (BASE/'c64/src'/name).read_text(encoding='utf-8-sig')
        for n, a in re.findall(r'^\s*([A-Za-z_]\w*)\s*=\s*\$([0-9A-Fa-f]+)', source, re.M):
            labels[n] = int(a, 16)
    return labels
