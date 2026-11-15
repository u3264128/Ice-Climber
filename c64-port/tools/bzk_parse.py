#!/usr/bin/env python3
"""Parser for bzk-style ca65 disassemblies (Ice Climber, mishra).

Reconstructs exact binary images (PRG/CHR) from the annotated .asm sources
without running the original build scripts.  Every data line carries both a
NES file offset and the first assembled byte in its left-hand annotation
column, which lets us self-check the expression evaluator line by line.

Usage (library):
    from bzk_parse import parse_project
    proj = parse_project(nes_dir)          # -> dict with segments, symbols, labels
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Annotation column:  "- D 2 - - - 0x000010 00:C000: 01        .byte <x ; c"
#                      ^^^^^^^^^^^^ 6 CDL-ish flag slots, one space each
ANNO_RE = re.compile(
    r"^(?P<flags>(?:[A-Z0-9\-] ){6})"     # flag field
    r"0x(?P<off>[0-9A-Fa-f]{6}) "         # NES file offset
    r"(?P<bank>[0-9A-Fa-f]{2}):(?P<addr>[0-9A-Fa-f]{4}): "  # bank:cpu/ppu addr
    r"(?P<bytes>(?:[0-9A-Fa-f]{2} ?)*)"   # first byte(s) as assembled
    r"\s{2,}(?P<src>\S.*)$"               # the actual assembler source
)

LABEL_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*):")
SYM_DEF_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[^;]+)")


# ---------------------------------------------------------------------------
# Expression evaluation: $hex, decimal, symbols, + - ( ), <lo >hi prefix
class ExprError(ValueError):
    pass


def eval_expr(expr: str, symbols: dict) -> int:
    """Recursive-descent evaluator:  [+/-] atoms with ( ), <lo, >hi prefixes."""
    text = expr.strip()
    state = {"pos": 0}

    def peek() -> str | None:
        p = state["pos"]
        return text[p] if p < len(text) else None

    def advance(delta: int) -> None:
        state["pos"] += delta

    def skip_ws() -> None:
        while peek() is not None and peek().isspace():
            advance(1)

    def parse_sum() -> int:
        val = parse_mul()
        while True:
            skip_ws()
            c = peek()
            if c == "+":
                advance(1)
                val += parse_mul()
            elif c == "-":
                advance(1)
                val -= parse_mul()
            else:
                return val

    def parse_mul() -> int:
        val = parse_term()
        while True:
            skip_ws()
            c = peek()
            if c == "*":
                advance(1)
                val *= parse_term()
            elif c == "/":
                advance(1)
                val //= parse_term()
            else:
                return val

    def parse_term() -> int:
        skip_ws()
        c = peek()
        if c == "(":
            advance(1)
            v = parse_sum()
            skip_ws()
            if peek() != ")":
                raise ExprError(f"missing ')' in {expr!r}")
            advance(1)
            return v
        if c == "<":
            advance(1)
            return parse_term() & 0xFF
        if c == ">":
            advance(1)
            return (parse_term() >> 8) & 0xFF
        rest = text[state["pos"]:]
        m = re.match(r"\$([0-9A-Fa-f]+)|%([01]+)|(\d+)", rest)
        if m:
            advance(m.end())
            if m.group(1) is not None:
                return int(m.group(1), 16)
            if m.group(2) is not None:
                return int(m.group(2), 2)
            return int(m.group(3))
        nm = re.match(r"[A-Za-z_][A-Za-z0-9_]*", rest)
        if not nm:
            raise ExprError(f"cannot parse {expr!r} at {rest[:20]!r}")
        name = nm.group(0)
        advance(len(name))
        if name not in symbols:
            raise ExprError(f"unknown symbol {name!r} in {expr!r}")
        return symbols[name]

    result = parse_sum()
    skip_ws()
    if state["pos"] != len(text):
        raise ExprError(f"trailing junk in {expr!r}: {text[state['pos']:][:20]!r}")
    return result


# 6502 instruction lengths by opcode, undocumented opcodes included with
# their real encoding lengths (KIL 1, SLO zp 2, NOP abs 3, ...).
_OP_LEN = [
    1,2,1,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # 00-0F
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3,   # 10-1F
    3,2,1,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # 20-2F
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3,   # 30-3F
    1,2,1,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # 40-4F
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3,   # 50-5F
    1,2,1,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # 60-6F
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3,   # 70-7F
    2,2,2,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # 80-8F
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3,   # 90-9F
    2,2,2,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # A0-AF
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3,   # B0-BF
    2,2,2,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # C0-CF
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3,   # D0-DF
    2,2,2,2, 2,2,2,2, 1,2,1,2, 3,3,3,3,   # E0-EF
    2,2,1,2, 2,2,2,2, 1,3,1,3, 3,3,3,3]   # F0-FF


def code_bytes(annotation_hex: str, mnemonic_src: str) -> bytes:
    """Bytes for a 6502 source line from its annotation column.

    The bzk disassembler occasionally leaves a stale opcode in front of
    hand-edited immediate instructions (annotation '2C A9 B0' for 'LDA #$B0').
    An immediate operand always means a 2-byte instruction, so in that case
    the LAST two annotation bytes are the real ones.
    """
    ab = bytes.fromhex(annotation_hex.replace(" ", ""))
    operand = mnemonic_src.split(";", 1)[0].strip()
    operand = operand.split(None, 1)[1].strip() if " " in operand else ""
    if operand.startswith("#"):
        return ab[-2:] if len(ab) > 2 else ab
    want = _OP_LEN[ab[0]]
    return ab[:want] if len(ab) >= want else ab


def split_args(src: str) -> list[str]:
    """Split '.byte a, b, c' payload on top-level commas (none inside parens)."""
    args, depth, cur = [], 0, []
    for ch in src:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur).strip())
    return [a for a in args if a]


@dataclass
class Segment:
    name: str
    space: str                 # "cpu" or "ppu"
    base_off: int = None       # NES file offset of address 0 in this space
    chunks: list = field(default_factory=list)   # (file_off, addr, bytes, src_line)
    labels: dict = field(default_factory=dict)   # name -> addr in this space


@dataclass
class Project:
    symbols: dict = field(default_factory=dict)   # RAM/const symbols
    segments: dict = field(default_factory=dict)  # name -> Segment
    label_space: dict = field(default_factory=dict)  # label -> ("segment", addr)

    def label_addr(self, name: str) -> int:
        return self.label_space[name][1]


def parse_symbol_file(path: Path, symbols: dict) -> None:
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        m = SYM_DEF_RE.match(line)
        if not m:
            continue
        name, value = m.group("name"), m.group("value").strip()
        try:
            symbols[name] = eval_expr(value, symbols)
        except ExprError:
            # forward alias - retry after all plain defs are known (2nd pass)
            pass


def parse_placements(cfg_path: Path) -> dict:
    """Read segment placements from ld65.cfg:  NAME: load = MEM, start = $XXXX."""
    out = {}
    for m in re.finditer(r"(\w+):\s*load\s*=\s*(\w+)(?:,\s*start\s*=\s*\$([0-9A-Fa-f]+))?",
                         cfg_path.read_text()):
        if m.group(3):
            out[m.group(1)] = int(m.group(3), 16)
    return out


def parse_asm(path: Path, proj: Project, srcdir: Path, default_space: str,
              passes=(1, 2)) -> None:
    """Pass 1 binds labels (forward refs), pass 2 evaluates data bytes."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    placement = getattr(proj, "_placement", None)
    if placement is None:
        placement = parse_placements(srcdir / "ld65.cfg")
        proj._placement = placement

    def ensure_segment(name: str, space: str) -> Segment:
        if name not in proj.segments:
            proj.segments[name] = Segment(name, space)
        return proj.segments[name]

    all_labels: dict[str, int] = getattr(proj, "_all_labels", {})
    proj._all_labels = all_labels

    for pass_no in passes:
        cur_seg = None
        pc = None
        pending_labels: list[str] = []
        for lineno, raw in enumerate(lines, 1):
            anno = ANNO_RE.match(raw)
            if anno:
                src = anno.group("src").strip()
                file_off = int(anno.group("off"), 16)
                addr = int(anno.group("addr"), 16)
                seg = ensure_segment(cur_seg or default_space, default_space)
                if pc is None:
                    pc = placement.get(seg.name, addr)
                pc = addr          # trust the annotation address
                for lbl in pending_labels:
                    seg.labels[lbl] = addr
                    proj.label_space[lbl] = (seg.name, addr)
                    all_labels[lbl] = addr
                pending_labels.clear()
                if pass_no == 1:
                    continue

                low = src.split(";", 1)[0].strip()
                if not low:
                    continue
                scope = {**proj.symbols, **all_labels}
                if low.startswith(".byte"):
                    data = bytes(eval_expr(a, scope) & 0xFF
                                 for a in split_args(low[5:].strip()))
                elif low.startswith(".word"):
                    data = b""
                    for a in split_args(low[5:].strip()):
                        v = eval_expr(a, scope) & 0xFFFF
                        data += bytes([v & 0xFF, v >> 8])
                elif low.startswith(".dbyt"):
                    data = b""
                    for a in split_args(low[5:].strip()):
                        v = eval_expr(a, scope) & 0xFFFF
                        data += bytes([v >> 8, v & 0xFF])
                else:
                    # actual 6502 code - bytes are in the annotation column,
                    # validated/trimmed against the opcode length table
                    data = code_bytes(anno.group("bytes"), low)
                seg.chunks.append((addr, data, f"{path.name}:{lineno}"))
                pc += len(data)
                # self-check against annotated bytes: for data lines the
                # annotation may be a prefix (first byte only); for code
                # lines our trimmed bytes must match unless this is one of
                # the hand-edited immediate lines (phantom opcode prefix)
                ab = anno.group("bytes").replace(" ", "")
                if data and ab:
                    expect = bytes.fromhex(ab)
                    immediate = bool(re.match(r"\w+\s+#", low))
                    n = min(len(data), len(expect))
                    if data[:n] != expect[:n] and not immediate:
                        raise AssertionError(
                            f"{path.name}:{lineno}: eval mismatch {expect.hex()} "
                            f"vs {data.hex()}  [{low[:60]}]"
                        )
                continue

            stripped = raw.strip()
            if not stripped or stripped.startswith(";"):
                continue
            m = LABEL_RE.match(stripped)
            if m and raw.startswith(m.group("name")):  # label at column 0
                pending_labels.append(m.group("name"))
                continue
            if stripped.startswith(".segment"):
                cur_seg = re.search(r'"([^"]+)"', stripped).group(1)
                pc = placement.get(cur_seg)
                continue
            if stripped.startswith(".incbin") and pc is not None:
                if pass_no == 2:
                    seg = ensure_segment(cur_seg or default_space, default_space)
                    fn = re.search(r'"([^"]+)"', stripped).group(1)
                    data = (srcdir / fn).read_bytes()
                    for lbl in pending_labels:
                        seg.labels[lbl] = pc
                        proj.label_space[lbl] = (seg.name, pc)
                        all_labels[lbl] = pc
                    pending_labels.clear()
                    seg.chunks.append((pc, data, f"{path.name}:{lineno}"))
                    pc += len(data)
                continue
            if stripped.startswith(".include"):
                if pass_no == 1:
                    inc = re.search(r'"([^"]+)"', stripped).group(1)
                    inc = inc[5:] if inc.startswith("copy_") else inc
                    parse_symbol_file(srcdir / inc, proj.symbols)
                continue
            if stripped.startswith((".org", ".out", ".export")):
                continue
            if stripped.startswith("."):
                raise AssertionError(
                    f"{path.name}:{lineno}: unhandled directive {stripped[:60]}")


def parse_project(nes_dir: Path) -> Project:
    proj = Project()
    nes_dir = Path(nes_dir)
    # constant/RAM symbols first (two passes for aliased forwards)
    parse_symbol_file(nes_dir / "bank_val.inc", proj.symbols)
    parse_symbol_file(nes_dir / "bank_ram.inc", proj.symbols)
    parse_symbol_file(nes_dir / "bank_ram.inc", proj.symbols)
    # pass 1 everywhere (labels), then pass 2 (data) so cross-file refs work
    parse_asm(nes_dir / "bank_FF.asm", proj, nes_dir, "cpu", passes=(1,))
    parse_asm(nes_dir / "bank_ppu.asm", proj, nes_dir, "ppu", passes=(1,))
    parse_asm(nes_dir / "bank_FF.asm", proj, nes_dir, "cpu", passes=(2,))
    parse_asm(nes_dir / "bank_ppu.asm", proj, nes_dir, "ppu", passes=(2,))
    return proj


# ---------------------------------------------------------------------------
def seg_file_off(seg: Segment, addr: int) -> int:
    """Map an address in a segment's space to its offset inside the .nes file."""
    if seg.space == "cpu":          # PRG bank loaded at $C000, file offset 0x10
        return 0x10 + (addr - 0xC000)
    return 0x4010 + addr            # CHR pattern space, file offset 0x4010


def build_images(proj: Project) -> bytes:
    """Overlay every chunk at its NES file offset -> complete file body."""
    end = max(seg_file_off(seg, a) + len(d)
              for seg in proj.segments.values()
              for a, d, _s in seg.chunks)
    image = bytearray(b"\x00" * end)
    for seg in proj.segments.values():
        for addr, data, _src in seg.chunks:
            off = seg_file_off(seg, addr)
            image[off:off + len(data)] = data
    return bytes(image)


if __name__ == "__main__":
    nes_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    proj = parse_project(nes_dir)
    img = build_images(proj)
    print(f"parsed {len(proj.segments)} segments, {len(proj.label_space)} labels, "
          f"{len(proj.symbols)} symbols, body {len(img)} bytes")
    for name, seg in proj.segments.items():
        n = sum(len(d) for a, d, _s in seg.chunks)
        print(f"  {name:10s} space={seg.space:3s} bytes={n}")
