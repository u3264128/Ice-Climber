"""Audit decoded sprite layers against CHR pixels and their encoding limits."""
import hashlib
import json

from convert_c64_gfx import C64_COLORS
from nesgfx import chr_tiles
from png import Canvas
from symbols import BASE

PLAYER_POSES = dict(WALK0=0, WALK1=1, WALK2=3, IDLE=0, STOP=5,
                    JUMP=6, HAMMER=7, ATTACK=9, STRIKE=10)


def decode(data, modes, offsets=None):
    """Decode layers in VIC priority order; values are NES colour roles."""
    result = [[0]*24 for _ in range(21)]
    offsets = offsets or (0,)*len(modes)
    for layer, mode in reversed(list(enumerate(modes))):
        block = data[layer*64:(layer+1)*64]
        assert len(block) == 64 and block[63] == 0
        for y in range(21):
            for x in range(24):
                value = ((block[y*3+x//8] >> (6-(x & 6))) & 3
                         if isinstance(mode, tuple) else
                         (block[y*3+x//8] >> (7-x%8)) & 1)
                if value:
                    target = x+offsets[layer]
                    assert 0 <= target < 24, ('opaque pixel outside sprite canvas', target)
                    result[y][target] = mode[value] if isinstance(mode, tuple) else mode
    return result


def original_player_rows(tiles, entry, bonus):
    """Render the original OAM writer and its idle/bonus foot replacements."""
    from test_original_physics import Reference, PRG
    from test_topi_sprites import source_pixels
    pose = entry['name'].split('_')[2]
    index = PLAYER_POSES[pose]
    assert entry['nes_base'] == PRG[0xBB3+index], (pose, 'wrong source pose')
    reference = Reference()
    ram = reference.ram
    ram[0x55], ram[0x62], ram[0x64], ram[0x66] = 2 if bonus else 1, int('_R_' in entry['name']), 64, 96
    ram[0x70] = 0 if pose == 'IDLE' else 1
    reference.call(0xD17C, y=index)
    if pose in ('WALK0', 'WALK1', 'WALK2', 'IDLE'):
        reference.call(0xCE06, y=0xD9)
    oam = [tuple(ram[0x200+i:0x204+i]) for i in range(0, 24, 4)]
    x0, y0 = min(v[3] for v in oam), min(v[0] for v in oam)
    pixels = source_pixels(tiles, oam)
    return [[pixels.get((x0+x, y0+y), 0) for x in range(16)] for y in range(24)]


def source_frame(tiles, entry, bonus):
    name, base = entry['name'], entry['nes_base']
    width, height = entry['nes_width'], entry['nes_height']
    if name.startswith('POPO_'):
        rows = original_player_rows(tiles, entry, bonus)
    else:
        rows = [[tiles[base+(x//8)*height+y//8][y%8][x%8]
                 for x in range(width*8)] for y in range(height*8)]
        if name.split('_')[1] != entry['source_facing']:
            rows = [row[::-1] for row in rows]
    player = name.startswith(('POPO_', 'DEATH_'))
    if player:
        crop = entry['y_offset']+6
        assert not any(any(row) for row in rows[:crop]+rows[crop+21:])
        rows = rows[crop:crop+21]
    elif name.startswith(('BEAR_', 'CONDOR_', 'FRUIT_')):
        x0, y0 = entry['x_offset'], entry['y_offset']
        rows = [row[x0:x0+24] for row in rows[y0:y0+16]]
    margin = 4 if name.startswith(('POPO_', 'TOPI_', 'BIRD_', 'MALLET_', 'DEATH_')) else 0
    top = 2 if name.startswith(('TOPI_', 'BIRD_')) else 0
    result = [[0]*24 for _ in range(21)]
    for y, row in enumerate(rows, top):
        result[y][margin:margin+len(row)] = row
    return result


def encoding(entry):
    name = entry['name']
    if name.startswith('POPO_'):
        return (2, (0, 1, 3, 2)) if entry['compact'] else (1, 2, 3)
    if name.startswith('TOPI_'):
        return (2, 1)
    if name.startswith('BIRD_'):
        return ((0, 1, 2, 3),) if name.endswith('_DEAD') else (2, (0, 1, 3, 2))
    if name.startswith('FRUIT_'):
        return (2, (0, 1, 3, 2))
    if name.startswith('MALLET_'):
        return (3,)
    if name.startswith('DEATH_'):
        return (1,)
    return ((0, 1, 3, 2),)


def pixel_pairs(source, modes, offset=0):
    """Enumerate the colours the actual hires/MC layering can represent."""
    for y, row in enumerate(source):
        for x in range(-offset, 24, 2):
            pair = [row[xx] if 0 <= xx < 24 else 0 for xx in (x, x+1)]
            candidates = [[2 if value == 2 else shade for value in pair]
                          for shade in (0, 1, 3)] if len(modes) == 2 else [[shade]*2 for shade in range(4)]
            yield x, y, pair, candidates


def minimum_errors(source, modes, offset):
    return sum(min(sum(a != b for a, b in zip(pair, candidate)) for candidate in candidates)
               for _, _, pair, candidates in pixel_pairs(source, modes, offset))


def check_pixels(source, drawn, modes, context, offset=0):
    errors = 0
    multicolour = any(isinstance(mode, tuple) for mode in modes)
    for x, y, pair, candidates in pixel_pairs(source, modes, offset):
        actual = [drawn[y][xx] if 0 <= xx < 24 else 0 for xx in (x, x+1)]
        if not multicolour:
            assert actual == pair, (context, 'hires pixels', x, y, pair, actual)
            continue
        # Enumerate all possible MC choices while keeping the hires
        # body exact. This lower bound does not repeat the quantizer.
        minimum = min(sum(a != b for a, b in zip(pair, candidate)) for candidate in candidates)
        assert actual in candidates, (context, 'incorrect layer mask', x, y, pair, actual)
        error = sum(a != b for a, b in zip(pair, actual))
        assert error == minimum, (context, 'avoidable pixel loss', x, y, pair, actual, minimum)
        assert bool(any(pair)) == bool(any(actual)), (context, 'missing silhouette', x, y)
        errors += error
    return errors


def main():
    tiles = chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:4096])
    metadata = json.loads((BASE/'c64/build/sprite_frames.json').read_text())
    normal = (BASE/'c64/build/game_sprites.bin').read_bytes()
    bonus_bank = (BASE/'c64/build/game_sprites_bonus.bin').read_bytes()
    entries = {entry['name']: entry for entry in metadata}
    records, images, player_grids = [], [], {}
    for entry in metadata:
        if entry.get('carried_ice'):
            continue  # The runtime object test checks the separate carried block.
        detail = entry['name'].endswith('_DETAIL')
        base_entry = entries[entry['name'].removesuffix('_DETAIL')] if detail else entry
        for bonus in ((False, True) if entry['name'].startswith('POPO_') else (False,)):
            bank = bonus_bank if bonus else normal
            offset = (entry['pointer']-0x40)*64
            data = bank[offset:offset+entry['layers']*64]
            modes = encoding(base_entry)
            if detail:
                body = (base_entry['pointer']+1-0x40)*64
                data = bank[body:body+64]+data
                modes = (2, (0, 1, 3, 2))
            source = source_frame(tiles, base_entry, bonus)
            shift = entry.get('detail_x_offset', 0) if len(modes) == 2 else 0
            drawn = decode(data, modes, (0, shift) if len(modes) == 2 else None)
            name = entry['name']+('_BONUS' if bonus else '')
            errors = check_pixels(source, drawn, modes, name, shift)
            if name.startswith('POPO_') and len(modes) == 2:
                player_grids.setdefault(entry['name'], []).append((shift, [minimum_errors(source, modes, p) for p in (0, 1)]))
            records.append(dict(frame=name, pixel_errors=errors, optimal_for_encoding=True, detail_x_offset=shift))
            images.append((source, drawn))
    for name, stages in player_grids.items():
        feasible = [p for p in (0, 1) if all(cost[p] <= cost[0] for _, cost in stages)]
        best = min(feasible, key=lambda p: (sum(cost[p] for _, cost in stages), p))
        assert all(shift == best for shift, _ in stages), ('suboptimal player detail grid', name, stages, best)
    # Each cell: source on the left, decoded C64 bytes on the right.
    # Use a common role palette to isolate geometry from colour choices.
    atlas = Canvas(4*160, ((len(images)+3)//4)*52, (24, 24, 32))
    for index, pair in enumerate(images):
        for panel, rows in enumerate(pair):
            for y, row in enumerate(rows):
                for x, value in enumerate(row):
                    for dy in range(2):
                        for dx in range(2):
                            atlas.px((index%4)*160+panel*72+x*2+dx,
                                     (index//4)*52+y*2+dy, C64_COLORS[(0, 1, 14, 10)[value]])
    output = BASE/'docs/verification'
    output.mkdir(parents=True, exist_ok=True)
    atlas.save(output/'sprite_conversion.png')
    report = dict(status='passed', frames=len(records), compared_pixels=len(records)*24*21,
                  exact_frames=sum(row['pixel_errors'] == 0 for row in records),
                  player_detail_errors_before=sum(cost[0] for stages in player_grids.values() for _, cost in stages),
                  player_detail_errors_after=sum(cost[shift] for stages in player_grids.values() for shift, cost in stages),
                  player_source='executed D17C and CE06 OAM, both directions and stage types',
                  scope='Minimum colour-role pixel error with the current sprite modes and layer allocation',
                  atlas='Four cells per row, source left and decoded C64 right, common role palette',
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                  cases=records)
    (output/'sprite_conversion.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS sprite conversion:', report['frames'], 'frames,', report['compared_pixels'],
          'pixels;', report['exact_frames'], 'frames exact, remaining loss minimal for current encodings')


if __name__ == '__main__':
    main()
