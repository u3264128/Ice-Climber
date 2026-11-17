#!/usr/bin/env python3
"""Compose NES objects in OAM order; pack 64-byte VIC-II sprite blocks.

NES objects use consecutive tiles in COLUMN order. Popo is 16x24, with
blank rows above his hood: trim these to fit 21 lines. Three hires layers
preserve all player pixels where available; compact poses keep a hires
parka with MC details. Topi/Nitpicker use hires + MC accents. The
original Popo/Topi artwork faces LEFT; Nitpicker artwork faces RIGHT.
The hammer is a separate NES OAM tile, drawn with hardware sprite 7.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "tools"))
from nesgfx import chr_tiles
from png import Canvas
from convert_c64_gfx import C64_COLORS

PLAYER_DETAIL_SHIFT = {'WALK1', 'JUMP', 'HAMMER', 'STRIKE', 'STOP'}


def compose(tiles, base, height, width=2):
    return [[tiles[(base + (x // 8) * height + y // 8) & 255][y % 8][x % 8]
             for x in range(width * 8)] for y in range(height * 8)]


def fit_player(rows):
    nonblank = [y for y, row in enumerate(rows) if any(row)]
    crop = max(0, nonblank[-1] - 20)
    assert crop <= nonblank[0], "Player pose exceeds VIC sprite height"
    # Keep each pose's original origin. Bottom-aligning every pose made
    # raised legs/arms slide vertically relative to the separate hammer.
    body = rows[crop:crop + 21]
    return body + [[0] * 16 for _ in range(21-len(body))], crop - 6


def hires(rows, value, x_offset=4):
    block = bytearray(64)
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if v == value:
                px = x + x_offset
                block[y * 3 + px // 8] |= 0x80 >> (px % 8)
    return bytes(block)


def accents(rows, x_offset=4):
    block = bytearray(64)
    for y, row in enumerate(rows):
        for x in range(0, len(row), 2):
            pair = row[x:x+2]
            v = 3 if 3 in pair else (1 if 1 in pair else 0)
            # VIC sprite multicolour: 01 = $D025 (white), 10 = the sprite's
            # own colour (skin/detail), 11 = $D026 (shared light blue).
            bits = {0: 0, 1: 1, 3: 2}[v]
            mx = x_offset // 2 + x // 2
            block[y * 3 + mx // 4] |= bits << (6 - (mx % 4) * 2)
    return bytes(block)


def multicolour(rows):
    """White/blue/individual NES palette in one VIC multicolour layer."""
    block = bytearray(64)
    for y,row in enumerate(rows):
        for x in range(0,len(row),2):
            pair = row[x:x+2]
            value = 3 if 3 in pair else 2 if 2 in pair else 1 if 1 in pair else 0
            # NES 1 white -> 01 ($D025), 2 light blue -> 11 ($D026),
            # 3 -> 10 (the sprite's own colour), as in the previews.
            block[y*3+x//8] |= (0, 1, 3, 2)[value] << (6-(x%8))
    return bytes(block)


def player_accents(rows, shift, pose):
    """An odd detail grid preserves more pixels in selected player poses.

    The renderer moves this layer right by one pixel. A leading zero and
    the smaller margin put the original pixels back at their source X.
    """
    block = bytearray(accents([[0]+row+[0] for row in rows], 2) if shift else accents(rows))

    def opaque(y, px):
        """Composed sprite at detail pixel px: hires parka or an MC pair."""
        x = px-4+shift
        return 0 <= px < 24 and ((0 <= x < len(rows[y]) and rows[y][x] == 2)
                                 or (block[y*3+px//8] >> (6-(px & 6))) & 3)

    # Keep the original dark eyes between skin pixels. An MC pair cannot
    # show skin beside transparency: choose the dark opening on this tie,
    # losing one adjacent skin pixel instead of filling the eye.
    for y, row in enumerate(rows[:10]):
        # The tilted jump face already has a two-pixel eye on row 6.
        # Clearing the single dark source pixel above it would erase an
        # adjacent cheek pixel and turn that eye into a square hole.
        if pose == 'JUMP' and y == 5:
            continue
        for x in range(1, len(row)-1):
            if row[x] or row[x-1] != 3:
                continue
            end = x
            while end < len(row) and row[end] == 0:
                end += 1
            if end < len(row) and row[end] == 3:
                pairs = {(eye+4-shift) & ~1 for eye in range(x, end)}
                kept = block[y*3:y*3+3]
                for px in pairs:
                    block[y*3+px//8] &= ~(3 << (6-(px & 6)))
                # The face must still enclose the opening. When the lost
                # skin pixel was the face's outer edge, the eye would
                # become a notch: this row keeps skin, the other shows it.
                if not (opaque(y, min(pairs)-1) and opaque(y, max(pairs)+2)):
                    block[y*3:y*3+3] = kept
    return bytes(block)


def bonus_player_art(tiles, normal, metadata):
    """Original $CE06 bonus legs, replacing four lower OAM tiles by +$77."""
    result = bytearray(normal)
    for entry in metadata:
        name = entry["name"]
        if not name.startswith("POPO_") or not any(
                "_"+pose in name for pose in ("WALK0", "WALK1", "WALK2", "IDLE")):
            continue
        raw = compose(tiles, entry["nes_base"], 3)
        for column in range(2):
            for row in (1, 2):
                tile = entry["nes_base"]+column*3+row+0x77
                if "_IDLE" in name and column == 0 and row == 2:
                    tile = 0xDF   # $CE29 uses $DF instead of normal $D9
                for y in range(8):
                    raw[row*8+y][column*8:column*8+8] = tiles[tile & 255][y]
        # Keep the normal pose's origin: replacing its feet must not move
        # its head or the physical player position between stage types.
        _, offset = fit_player(compose(tiles, entry["nes_base"], 3))
        crop = offset+6
        rows = raw[crop:crop+21]
        rows += [[0]*16 for _ in range(21-len(rows))]
        if "_R_" in name:
            rows = [row[::-1] for row in rows]
        if name.endswith("_DETAIL"):
            layers = [player_accents(rows, entry['detail_x_offset'], name.split('_')[2])]
        elif entry["compact"]:
            layers = [hires(rows, 2), player_accents(rows, entry['detail_x_offset'], name.split('_')[2])]
        else:
            layers = [hires(rows, value) for value in (1, 2, 3)]
        start = (entry["pointer"]-0x40)*64
        result[start:start+len(layers)*64] = b"".join(layers)
    return bytes(result)


def sparse_sprite_xor(normal, bonus):
    """Pointer, five 8-bit masks with their XOR values, then pointer zero.

Only the lower forty bytes of these poses change. A bitmap avoids storing
the many unchanged bytes between their foot pixels and other sprite poses.
Applying the same patch twice restores the complete normal sprite bank.
"""
    delta = bytes(a ^ b for a, b in zip(normal, bonus))
    result, pointers = bytearray(), []
    for block in range(len(delta)//64):
        values = delta[block*64:block*64+64]
        if not any(values):
            continue
        assert not any(values[:24]), "Bonus artwork changed above the foot-patch window"
        pointers.append(0x40+block)
        result.append(0x40+block)
        for start in range(24, 64, 8):
            mask = sum(bool(values[start+i]) << (7-i) for i in range(8))
            result.append(mask)
            result.extend(values[start+i] for i in range(8) if mask & (0x80 >> i))
    result.append(0)
    return bytes(result), pointers, sum(bool(value) for value in delta)


def sprite_page_xor(normal,variant,start):
    """Thirty-two masks and sparse XOR bytes for an aligned sprite page."""
    assert start%256==0
    delta=bytes(a^b for a,b in zip(normal[start:start+256],variant[start:start+256]))
    result=bytearray()
    for start in range(0,256,8):
        mask=sum(bool(delta[start+i])<<(7-i) for i in range(8))
        result.append(mask)
        result.extend(delta[start+i] for i in range(8) if mask&(0x80>>i))
    return bytes(result),sum(bool(value) for value in delta)


def topi_carry_rows(tiles,base,direction):
    body=[[0]*16]*2+compose(tiles,base,2)
    brick=[[0]*8]*2+compose(tiles,0xAC,2,1)
    rows=[[0]*24 for _ in range(18)]
    for y in range(18):
        for x in range(8):
            if brick[y][x]:rows[y][x]=1 if brick[y][x]==1 else 2
        for x in range(16):
            if body[y][x]:rows[y][x+6]=body[y][x]
    return [row[::-1] for row in rows] if direction=='R' else rows


def main():
    tiles = chr_tiles((BASE / "extracted/rom/chr_0000-1fff.bin").read_bytes()[:0x1000])
    specs = [("POPO", p, b, 3) for p, b in
             (("WALK0", 0x5C), ("WALK1", 0x62), ("JUMP", 0x8C),
              ("HAMMER", 0x92), ("ATTACK", 0x80), ("STRIKE", 0x86),
              ("WALK2", 0x56), ("IDLE", 0x5C), ("STOP",0x74))]
    specs += [("TOPI", f"WALK{i}", b, 2) for i, b in enumerate((0xA0, 0xA4, 0xA8))]
    # sub_F838 selects $E0/$E4; object 3 is a 2x2 column-major object.
    specs += [("BIRD", f"FLAP{i}", b, 2) for i, b in enumerate((0xE0, 0xE4))]
    specs += [("BIRD", "DEAD", 0xB2, 2)]
    blob, definitions, meta = bytearray(), [], []
    source_facing = {"POPO": "L", "TOPI": "L", "BIRD": "R"}
    preview = Canvas(len(specs) * 64, 2 * 72, fill=(24, 24, 32))
    for i, (kind, pose, base, height) in enumerate(specs):
        raw = compose(tiles, base, height)
        if kind == "POPO" and pose == "IDLE":
            # Original $CE29 replaces the left bottom OAM tile with $D9
            # while standing still; horizontal flipping places it on the
            # opposite physical foot when facing right.
            for y in range(8):
                raw[16+y][:8] = tiles[0xD9][y]
        y_offset = 0
        if kind == "POPO":
            rows, y_offset = fit_player(raw)
        else:
            pad = 18 - len(raw) if kind == "TOPI" else 2
            rows = [[0] * 16 for _ in range(pad)] + raw
        for direction in ("R", "L"):
            rows2 = rows if direction == source_facing[kind] else [r[::-1] for r in rows]
            name = f"{kind}_{direction}_{pose}"
            pointer = 0x40 + len(blob) // 64  # $5000 in VIC bank $4000
            definitions.append(f"{name} = ${pointer:02X}")
            if kind == "POPO":
                definitions.append(f"{name}_Y = ${y_offset & 255:02X}")
                definitions.append(f"{name}_DETAIL_X = {int(pose in PLAYER_DETAIL_SHIFT)}")
            if kind == "POPO" and pose in ("STRIKE", "WALK2", "WALK0", "IDLE", "STOP"):
                # The last attack pose is original NES $86. Two layers
                # preserve parka colour for both climbers while fitting
                # the complete attack sequence in the VIC sprite bank.
                layers = [hires(rows2, 2), player_accents(rows2, pose in PLAYER_DETAIL_SHIFT, pose)]
            elif kind == "TOPI":
                # Original Topi uses only palette values1/2. Keep the
                # white eyes and dizzy stars one physical pixel wide.
                layers = [hires(rows2,2),hires(rows2,1)]
            elif kind == "BIRD" and pose == "DEAD":
                # Keep the source silhouette in one MC sprite. White and
                # purple remain; the minor skin accent uses shared blue.
                # This releases two blocks for the missing attack pose.
                encoded = bytearray(64)
                for y, row in enumerate(rows2):
                    for x in range(0, 16, 2):
                        pair = row[x:x+2]
                        value = 3 if 3 in pair else 2 if 2 in pair else 1 if 1 in pair else 0
                        mx = 2+x//2
                        encoded[y*3+mx//4] |= (0, 1, 2, 3)[value] << (6-(mx%4)*2)
                layers = [bytes(encoded)]
            else:
                layers = ([hires(rows2, v) for v in (1, 2, 3)] if kind == "POPO"
                          else [hires(rows2, 2), accents(rows2)])
            for layer in layers:
                assert len(layer) == 64 and layer[-1] == 0
                blob += layer
            meta.append(dict(name=name, pointer=pointer, layers=len(layers),
                             nes_base=base, nes_height=height, nes_width=2,
                             source_facing=source_facing[kind], y_offset=y_offset,
                             compact=kind == "POPO" and pose in ("STRIKE", "WALK2", "WALK0", "IDLE", "STOP"),
                             detail_x_offset=int(kind == 'POPO' and pose in PLAYER_DETAIL_SHIFT),
                             idle_foot_tile=0xD9 if kind == "POPO" and pose == "IDLE" else None,
                             multicolour=kind == "BIRD" and pose == "DEAD"))
            palette = [0, 1, {"POPO": 14, "TOPI": 3, "BIRD": 4}[kind], 10]
            for y, row in enumerate(rows2):
                for x, v in enumerate(row):
                    if v:
                        for sy in range(3):
                            for sx in range(3):
                                preview.px(i*64+x*3+sx, (direction == "L")*72+y*3+sy,
                                           C64_COLORS[palette[v]])
    # F0DC copies the seal's Y into the carried-ice object; F0F1 positions
    # its 8x16 AC/AD column at x-6 or x+14. Keep both original silhouettes
    # in the same two hires sprites. The ice's two blue shades share cyan.
    topi_push_layers={}
    carry_preview = Canvas(2*96, 72, fill=(24, 24, 32))
    for direction in ('R', 'L'):
        rows=topi_carry_rows(tiles,0xA4,direction)
        name = f'TOPI_{direction}_PUSH'
        pointer=next(entry['pointer'] for entry in meta if entry['name']==f'TOPI_{direction}_WALK1')
        definitions.append(f'{name} = TOPI_{direction}_WALK1')
        topi_push_layers[direction]=hires(rows,2,0)+hires(rows,1,0)
        meta.append(dict(name=name, pointer=pointer, layers=2, nes_base=0xA4,
                         nes_height=2, nes_width=2, source_facing='L',
                         body_dx=2 if direction == 'R' else -2, carried_ice=True,
                         ice_base=0xAC,ice_height=2,ice_width=1,white_hires=True,
                         ice_palette_quantization={'1':'white','2':'cyan','3':'cyan'},
                         carried_walk_tiles=[0xA0,0xA4,0xA8,0xA4],
                         source_ice_dx=14 if direction=='R' else -6))
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                if v:
                    for yy in range(3):
                        for xx in range(3):
                            carry_preview.px((direction == 'L')*96+x*3+xx, y*3+yy,
                                             C64_COLORS[[0, 1, 3, 10][v]])
    # tbl_CBC1 / tbl_CBC6 and sub_D17C attach a single 8x8 OAM tile
    # independently of Popo's six body tiles. All hammer pixels are NES
    # palette value3; idle/walking already carry their club in the body art.
    for pose, tile in (("WINDUP", 0xD6),
                       ("RAISED", 0x17), ("STRIKE", 0x6F), ("FOLLOWTHROUGH", 0x16)):
        raw = tiles[tile]
        for direction in ("R", "L"):
            rows = raw if direction == "L" else [r[::-1] for r in raw]
            name = f"MALLET_{direction}_{pose}"
            pointer = 0x40 + len(blob) // 64
            definitions.append(f"{name} = ${pointer:02X}")
            blob += hires(rows, 3)
            meta.append(dict(name=name, pointer=pointer, layers=1, nes_base=tile,
                             nes_height=1, nes_width=1, source_facing="L"))
    # Original $D17C hides the separate hammer in idle/walking poses; their
    # body art already contains the carried club. Keep legacy table names
    # as harmless aliases without occupying two more sprite blocks.
    definitions += ["MALLET_R_CARRY = MALLET_R_WINDUP", "MALLET_L_CARRY = MALLET_L_WINDUP"]
    # Two-player mode combines white/skin details so two players plus an
    # enemy fit on one raster line. Their blue/pink body stays hires.
    for _,pose,base,height in specs[:5]:
        rows,_ = fit_player(compose(tiles,base,height))
        for direction in ('R','L'):
            if pose == 'WALK0':
                definitions.append(f'POPO_{direction}_WALK0_DETAIL = POPO_{direction}_WALK0+1')
                continue
            pixels = [r[::-1] for r in rows] if direction == 'R' else rows
            name = f'POPO_{direction}_{pose}_DETAIL'
            pointer = 0x40+len(blob)//64
            definitions.append(f'{name} = ${pointer:02X}')
            blob += player_accents(pixels, pose in PLAYER_DETAIL_SHIFT, pose)
            meta.append(dict(name=name,pointer=pointer,layers=1,nes_base=base,
                             nes_height=height,nes_width=2,source_facing='L',multicolour=True,
                             detail_x_offset=int(pose in PLAYER_DETAIL_SHIFT)))
    # The NES descriptor at $EADE is height:width. Bear = 4:2 (16x32),
    # condor = 2:4 (32x16), fruit objects $0F..$12 = 2:2 (16x16).
    extras = []
    for pose, tile in (('WALK0', 0x18), ('WALK1', 0x20), ('WALK2', 0x28), ('JUMP', 0x98)):
        extras.append(('BEAR', pose, tile, 4, 2, 'L'))
    for pose, tile in (('FLAP0', 0x3E), ('FLAP1', 0x46)):
        extras.append(('CONDOR', pose, tile, 2, 4, 'L'))
    for i, tile in enumerate((0x52,0x70,0xAE,0xB6,0xBA,0xC2,0xC6,0xCA,0xBE,0xFA)):
        extras.append(('FRUIT', str(i), tile, 2, 2, 'L'))
    extras_preview = Canvas(10*112, 4*112, fill=(24,24,32))
    for number, (kind, pose, base, height, width, facing) in enumerate(extras):
        raw = compose(tiles, base, height, width)
        directions = ('R','L') if kind in ('BEAR','CONDOR') else ('L',)
        for direction in directions:
            pixels = raw if direction == facing else [row[::-1] for row in raw]
            for y0 in range(0,len(pixels),16):
                for x0 in range(0,len(pixels[0]),24):
                    rows = [row[x0:x0+24] for row in pixels[y0:y0+16]]
                    name = f'{kind}_{direction}_{pose}_{x0}_{y0}'
                    pointer = 0x40+len(blob)//64
                    definitions.append(f'{name} = ${pointer:02X}')
                    layers = ([hires(rows,2,0),accents(rows,0)] if kind == 'FRUIT'
                              else [multicolour(rows)])
                    blob += b''.join(layers)
                    meta.append(dict(name=name,pointer=pointer,layers=len(layers),nes_base=base,
                                     nes_height=height,nes_width=width,source_facing=facing,
                                     x_offset=x0,y_offset=y0))
        for y,row in enumerate(raw):
            for x,v in enumerate(row):
                if v:
                    for yy in range(2):
                        for xx in range(2):
                            extras_preview.px((number%10)*112+x*2+xx,(number//10)*112+y*2+yy,
                                              C64_COLORS[[0,1,14,10][v]])
    # Original death ($D0AA): pose 11 (CHR $00, one colour) while the
    # timer runs out, then $D086 spins CHR $68-$6D: normal, upside down,
    # turned and mirrored ($D0A6). Each frame is one hires layer cropped to
    # 21 rows like the climbers (y offset = crop-6).
    def death_layer(rows):
        nonblank = [y for y, row in enumerate(rows) if any(row)]
        crop = max(0, nonblank[-1]-20)
        assert crop <= nonblank[0]
        body = rows[crop:crop+21]
        body = body+[[0]*16 for _ in range(21-len(body))]
        layer = hires(body, 1)
        assert len(layer) == 64 and layer[-1] == 0
        assert set(v for row in rows for v in row) <= {0, 1}, 'death art has one colour'
        return layer, crop-6
    death = compose(tiles, 0x00, 3)
    for direction in ('R', 'L'):
        rows = death if direction == 'L' else [row[::-1] for row in death]
        layer, y_offset = death_layer(rows)
        pointer = 0x40+len(blob)//64
        definitions.append(f'DEATH_{direction} = ${pointer:02X}')
        definitions.append(f'DEATH_{direction}_Y = ${y_offset & 255:02X}')
        blob += layer
        meta.append(dict(name=f'DEATH_{direction}', pointer=pointer, layers=1, nes_base=0,
                         nes_height=3, nes_width=2, source_facing='L', y_offset=y_offset))
    spin = compose(tiles, 0x68, 3)
    spin_art = bytearray()
    for k, (vertical, horizontal) in enumerate(((False, False), (True, False), (True, True), (False, True))):
        rows = spin[::-1] if vertical else spin
        rows = [row[::-1] for row in rows] if horizontal else rows
        layer, y_offset = death_layer(rows)
        spin_art += layer
        definitions.append(f'DEATH_SPIN{k}_Y = ${y_offset & 255:02X}')
    pages = (len(blob) + 255) // 256
    assert pages <= 32, 'Sprites overlap the score panel fonts'
    blob.extend(bytes(pages * 256 - len(blob)))
    definitions.append(f"SPRITE_PAGES = {pages}")
    out = BASE / "c64/build"
    out.mkdir(parents=True, exist_ok=True)
    (out/'death_spin.bin').write_bytes(spin_art)
    (out / "game_sprites.bin").write_bytes(blob)
    # Original $EE9D draws stunned Topi from CHR$06..$09. Reuse the four
    # WALK0 blocks while stunned, so the bank remains128 sprites. Sparse
    # XOR runs restore the original walking pixels on level reset.
    topi_stunned=bytearray(blob)
    topi_entries=[entry for entry in meta if entry['name'] in ('TOPI_R_WALK0','TOPI_L_WALK0')]
    for entry in topi_entries:
        rows=[[0]*16 for _ in range(2)]+compose(tiles,0x06,2)
        if entry['name'].startswith('TOPI_R_'):rows=[row[::-1] for row in rows]
        start=(entry['pointer']-0x40)*64
        topi_stunned[start:start+128]=hires(rows,2)+hires(rows,1)
    topi_start=min((entry['pointer']-0x40)*64 for entry in topi_entries)
    assert topi_start%256==0 and len(topi_entries)==2
    topi_patch,changed=sprite_page_xor(blob,topi_stunned,topi_start)
    (out/'topi_stun_patch.bin').write_bytes(topi_patch)
    (out/'game_sprites_topi_stun.bin').write_bytes(topi_stunned)
    (out/'topi_stun_art.json').write_text(json.dumps(dict(
        source_routines=['$EE9D','$EB2E','$EAFC'],nes_base=6,nes_tiles=[6,7,8,9],
        first_pointer=topi_entries[0]['pointer'],sprite_pointers=[entry['pointer'] for entry in topi_entries],
        bytes=len(topi_patch),changed_bytes=changed,format='32 groups of mask byte and present XOR bytes',
        white_hires=True,stars_in_source_art=True),indent=2)+'\n',encoding='utf-8')
    topi_pushed=bytearray(blob)
    pushing_entries=[entry for entry in meta if entry.get('carried_ice')]
    for entry in pushing_entries:
        start=(entry['pointer']-0x40)*64
        direction=entry['name'].split('_')[1]
        topi_pushed[start:start+128]=topi_push_layers[direction]
    push_start=min((entry['pointer']-0x40)*64 for entry in pushing_entries)
    push_patch,push_changed=sprite_page_xor(blob,topi_pushed,push_start)
    (out/'topi_push_patch.bin').write_bytes(push_patch)
    (out/'game_sprites_topi_push.bin').write_bytes(topi_pushed)
    push_deltas={}
    for pose,base in ((0,0xA0),(2,0xA8)):
        variant=bytearray(topi_pushed)
        for entry in pushing_entries:
            direction=entry['name'].split('_')[1]
            rows=topi_carry_rows(tiles,base,direction)
            start=(entry['pointer']-0x40)*64
            variant[start:start+128]=hires(rows,2,0)+hires(rows,1,0)
        delta,delta_changed=sprite_page_xor(topi_pushed,variant,push_start)
        (out/f'topi_push_walk{pose}_patch.bin').write_bytes(delta)
        push_deltas[str(pose)]=dict(nes_base=base,bytes=len(delta),changed_bytes=delta_changed)
    (out/'topi_push_art.json').write_text(json.dumps(dict(
        source_routines=['$F0DC','$F0F1','$EAFC'],nes_body=0xA4,nes_ice=0xAC,
        sprite_pointers=[entry['pointer'] for entry in pushing_entries],
        bytes=len(push_patch),changed_bytes=push_changed,
        walking_deltas=push_deltas,walking_sequence=[0xA0,0xA4,0xA8,0xA4],
        format='32 groups of mask byte and present XOR bytes'),indent=2)+'\n',encoding='utf-8')
    # F737 draws the third pose from $46, then F773 replaces its right
    # wing tiles with $4E-$51. Patch the two left-facing FLAP0 blocks
    # during the preview, preserving the bank size and bonus artwork.
    preview_condor=bytearray(blob)
    condor_entries=[entry for entry in meta if entry['name'].startswith('CONDOR_L_FLAP0_')]
    condor_rows=[left+right for left,right in
                 zip(compose(tiles,0x46,2),compose(tiles,0x4E,2))]
    for entry in condor_entries:
        rows=[row[entry['x_offset']:entry['x_offset']+24] for row in condor_rows]
        start=(entry['pointer']-0x40)*64
        preview_condor[start:start+64]=multicolour(rows)
    condor_start=min((entry['pointer']-0x40)*64 for entry in condor_entries)
    assert condor_start%256==0
    condor_patch,condor_changed=sprite_page_xor(blob,preview_condor,condor_start)
    (out/'condor_preview_patch.bin').write_bytes(condor_patch)
    # The original ice block ($AC), icicle stages ($10,$0E,$0C) and ice
    # shards ($12,$14) are 8x16 objects ($EADE 2:1). $C7C1 mirrors them when
    # the object's $BD is positive. Normal play shows them from Topi pages
    # 1-3 (nes_objects.asm): one multicolour layer, no margins, unmirrored
    # then mirrored for each tile.
    ice_art = bytearray()
    for base in (0xAC, 0x10, 0x0E, 0x0C, 0x12, 0x14):
        art = compose(tiles, base, 2, 1)
        for mirrored in (False, True):
            rows = [row[::-1] if mirrored else row for row in art]
            rows = [row+[0]*16 for row in rows]+[[0]*24 for _ in range(21-len(rows))]
            layer = multicolour(rows)
            assert len(layer) == 64 and layer[-1] == 0
            ice_art += layer
    assert len(ice_art) == 768
    (out/'nes_ice_art.bin').write_bytes(ice_art)
    (out/'condor_preview_art.json').write_text(json.dumps(dict(
        source_routines=['$F737','$F773'],nes_tiles=[0x46,0x47,0x48,0x49,0x4E,0x4F,0x50,0x51],
        nes_height=2,nes_width=4,
        sprite_pointers=[entry['pointer'] for entry in condor_entries],
        bytes=len(condor_patch),changed_bytes=condor_changed,
        format='32 groups of mask byte and present XOR bytes'),indent=2)+'\n')
    bonus = bonus_player_art(tiles, blob, meta)
    foot_patch, foot_pointers, changed_bytes = sparse_sprite_xor(blob, bonus)
    (out / "game_sprites_bonus.bin").write_bytes(bonus)
    (out / "player_bonus_patch.bin").write_bytes(foot_patch)
    (out / "player_bonus_art.json").write_text(json.dumps(dict(
        bytes=len(foot_patch), sprite_pointers=foot_pointers, changed_bytes=changed_bytes,
        source_routines=["$CE06", "$CE29"],
        format="VIC pointer, five masks for offsets24..63 with XOR payload, pointer0 terminates"),
        indent=2)+"\n", encoding="utf-8")
    def rle(data):
        packed = bytearray()
        i = 0
        while i < len(data):
            count = 1
            while count < 128 and i+count < len(data) and data[i+count] == data[i]:
                count += 1
            if count >= 3:
                packed += bytes([128 | (count-1), data[i]])
                i += count
            else:
                start = i
                while i < len(data) and i-start < 128:
                    if i+2 < len(data) and data[i] == data[i+1] == data[i+2]:
                        break
                    i += 1
                packed.append(i-start-1)
                packed += data[start:i]
        return packed
    # Boot unpacks the sprites from the load buffer: the upper half first
    # (its stream lies below it, from $5000), then the lower half from below
    # $5000. Only the condor blocks' own stream stays resident (DATA).
    assert len(blob) == 0x2000
    (out / 'game_sprites.rle').write_bytes(rle(blob))
    (out / 'game_sprites_hi.rle').write_bytes(rle(blob[0x1000:]))
    (out / 'game_sprites_lo.rle').write_bytes(rle(blob[:0x1000]))
    # Block debris ($D91C/$D9CC): 8x8 tiles $0A and $0B, each unflipped,
    # H ($40), V ($80) and HV ($C0), in the condor blocks during normal
    # play. One multicolour byte per row: NES colour 1 -> 01 ($D025 white),
    # 2 and 3 -> 10 (the piece's own colour: ice, grass or earth).
    condor = [entry for entry in meta if entry['name'] == 'CONDOR_R_FLAP0_0_0'][0]['pointer']
    debris = bytearray()
    for tile in (0x0A, 0x0B):
        art = compose(tiles, tile, 1, 1)
        for flips in (0, 0x40, 0x80, 0xC0):
            rows = [row[::-1] if flips & 0x40 else row for row in art]
            rows = rows[::-1] if flips & 0x80 else rows
            for row in rows:
                byte = 0
                for x in range(0, 8, 2):
                    pair = row[x:x+2]
                    bits = 2 if (2 in pair or 3 in pair) else 1 if 1 in pair else 0
                    byte |= bits << (6-x)
                debris.append(byte)
    assert len(debris) == 64
    (out / 'debris_art.bin').write_bytes(debris)
    # Leaving normal play unpacks the eight condor blocks again from their
    # own resident stream, up to page $6B (the decoder stops on that page;
    # the bytes after the blocks get their own art back).
    first = (condor-0x40)*64
    assert 0x5000+first+512 <= 0x6B00
    (out / 'condor_sprites.rle').write_bytes(rle(blob[first:0x1B00]))
    (out / 'debris_blocks.inc').write_text('\n'.join((
        '; Generated by make_assets.py.',
        f'DEBRIS_BLOCK = ${condor:02X}         ; first of eight condor blocks',
        f'DEBRIS_RLE_DST = ${first:04X}      ; condor_sprites.rle decodes from SPRITES+this'))+'\n', encoding='utf-8')
    # Small code-native UI alphabet; reserve game characters $80..$99.
    alphabet = [
        '7e1111117e','7f49494936','3e41414122','7f4141221c','7f49494941',
        '7f09090901','3e41495172','7f0808087f','00417f4100','2040413f01',
        '7f08142241','7f40404040','7f020c027f','7f0408107f','3e4141413e',
        '7f09090906','3e4151215e','7f09192946','4649494931','01017f0101',
        '3f4040403f','1f2040201f','3f4038403f','6314081463','0708700807','6151494543']
    font = bytearray()
    for encoded in alphabet:
        cols = bytes.fromhex(encoded)
        font += bytes(sum(((cols[x] >> y) & 1) << (6-x) for x in range(5)) for y in range(8))
    (out/'ui_font.bin').write_bytes(font)
    (out / "sprite_frames.inc").write_text("; Generated by make_assets.py.\n" + "\n".join(definitions) + "\n", encoding="utf-8")
    (out / "sprite_frames.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    preview.save(out / "sprite_frames.png")
    carry_preview.save(out / 'topi_ice.png')
    extras_preview.save(out / 'bonus_enemies.png')
    # Full player/hammer preview in the same coordinates and priority as VIC.
    player_specs = specs[:8]
    mallets = ((None, 0, 0, 0), (None, 0, 0, 0),
               (0xD6, -8, 16, 2), (0x17, 0, 8, -14), (0x6F, 16, -8, -6),
               (0x16, 16, -8, 10), (None, 0, 0, 0), (None, 0, 0, 0))
    full = Canvas(8*120, 2*144, fill=(24, 24, 32))
    for i, ((_, _, base, height), (tile, right_x, left_x, hammer_y)) in enumerate(zip(player_specs, mallets)):
        body, body_y = fit_player(compose(tiles, base, height))
        if player_specs[i][1] == "IDLE":
            raw = compose(tiles, base, height)
            for y in range(8):
                raw[16+y][:8] = tiles[0xD9][y]
            body, body_y = fit_player(raw)
        if base == 0x86:
            body_y -= 8          # original $D17C visual attack hop
        for row_i, direction in enumerate(("R", "L")):
            layers = ([(tiles[tile], right_x if direction == "R" else left_x, hammer_y)]
                      if tile is not None else []) + [(body, 0, body_y)]
            for pixels, dx, dy in layers:
                pixels = [row[::-1] for row in pixels] if direction == "R" else pixels
                for y, row in enumerate(pixels):
                    for x, v in enumerate(row):
                        if v:
                            for sy in range(3):
                                for sx in range(3):
                                    full.px(i*120+(10+dx+x)*3+sx, row_i*144+(22+dy+y)*3+sy,
                                            C64_COLORS[[0, 1, 14, 10][v]])
            for x in range(8, 31):
                full.px(i*120+x*3, row_i*144+8, C64_COLORS[1])
            tip = 30 if direction == "R" else 8
            for step in range(4):
                x = tip-step if direction == "R" else tip+step
                full.px(i*120+x*3, row_i*144+8-step, C64_COLORS[1])
                full.px(i*120+x*3, row_i*144+8+step, C64_COLORS[1])
    full.save(out / "player_hammer.png")
    print(f"sprites: {len(meta)} poses, {len(blob)//64} blocks; bonus foot patch {len(foot_patch)} bytes")


if __name__ == "__main__":
    main()
