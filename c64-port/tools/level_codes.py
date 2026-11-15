"""Developer-only keyboard codes; never displayed by the game."""
CODES = (
    'r7cq', 'b2nf', 'h9vz', 't4am', 'c6qe', 'v3rb', 'n8ht', 'q5xc',
    'a9fv', 'e2zg', 'm7br', 'f4qn', 'x6ca', 'g3vh', 'z8em', 'd5rt',
    'h2qb', 't9fn', 'c4zx', 'v7ag', 'n3re', 'q8hm', 'a5vc', 'e6bt',
    'm2zf', 'f9xq', 'x4nr', 'g7ae', 'z3ch', 'b8vm', 'jd3q', 'r6gt',
)
# C64 CIA1 row/column layout, in bit order (row*8+column).
ROWS = ('\b\r\x00\x00\x00\x00\x00\x00', '3wa4zse\x00',
        '5rd6cftx', '7yg8bhuv', '9ij0mkon', '+pl-.:@,',
        '\x00*;\x00\x00=\x00\x00', '1\x00\x002 \x00q\x00')
KEYS = {char: row*8+column for row, text in enumerate(ROWS)
        for column, char in enumerate(text) if char != '\x00'}
assert len(CODES) == len(set(CODES)) == 32
assert CODES[30] == 'jd3q' and all(len(code) == 4 for code in CODES)


def assembly():
    return '\n'.join('        .byte '+','.join(str(KEYS[c]) for c in code)
                     for code in CODES)+'\n'


if __name__ == '__main__':
    from pathlib import Path
    (Path(__file__).resolve().parents[1]/'c64/build/title_codes.inc').write_text(assembly())
