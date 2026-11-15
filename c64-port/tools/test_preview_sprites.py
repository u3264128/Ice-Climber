#!/usr/bin/env python3
"""Execute preview renderer and compare its three poses with original CHR."""
import hashlib
import json

from nesgfx import chr_tiles
from test_game import Machine, BASE
from test_original_physics import Reference, PRG
from test_topi_sprites import source_pixels


def source_condor(tiles, phase):
    """Execute F737, including its third-frame wing tile replacements."""
    reference = Reference()
    ram = reference.ram
    ram[0xD3:0xD8] = bytes((0, phase, 0, 112, 128))
    reference.call(0xF737)
    descriptor = PRG[0x2ADE+13]
    assert descriptor == 0x24, 'Source condor must be 2 rows by 4 columns'
    start = 0x200+PRG[0x2AA2+13]
    oam = [tuple(ram[start+i:start+i+4]) for i in range(0, 32, 4)]
    pixels = source_pixels(tiles, oam)
    return [[pixels.get((112+x, 128+y), 0) for x in range(32)] for y in range(16)]


def main():
    m=Machine();r,L=m.ram,m.labels
    tiles=chr_tiles((BASE/'extracted/rom/chr_0000-1fff.bin').read_bytes()[:4096])
    bank=bytes(r[0x5000:0x7000])
    pixels=0
    r[L['state']]=4;r[L['actor_mask']]=15
    r[L['preview_bird_y']]=128;r[L['completed_mountains']]=0
    for phase in range(3):
        original = source_condor(tiles, phase)
        r[L['preview_anim_frame']]=phase
        m.call('actors_prepare')
        assert r[L['logical_count']]==4,'Preview includes player/NPC or misses fruit'
        assert r[0xE800:0xE804]==bytes((164,188,174,174))
        assert r[0xE840:0xE844]==bytes((158,158,172,172))
        for part in range(2):
            pointer=r[0xE860+part]
            for y in range(16):
                for pair in range(12):
                    bits=r[0x4000+pointer*64+y*3+pair//4]
                    value=(0,1,3,2)[(bits>>(6-2*(pair%4)))&3]
                    x=part*24+pair*2
                    source=([original[y][xx] for xx in (x,x+1)]
                            if x<32 else [0,0])
                    assert value in source,(phase,part,pair,y,value,source)
                    assert bool(value) == bool(any(source)), (phase,part,pair,y,'missing silhouette')
                    pixels+=1
        # The screen-space OAM is independent of the mountain camera.
        expected=bytes(r[0xE800:0xE880])
        r[L['visual_camera']]=177;r[L['visual_camera']+1]=2
        m.call('actors_prepare')
        assert bytes(r[0xE800:0xE880])==expected
    m.call('normal_condor_art')
    assert bytes(r[0x5000:0x7000])==bank,'Condor XOR failed to restore bank'
    m.call('normal_condor_art')
    assert bytes(r[0x5000:0x7000])==bank,'Condor restore is not idempotent'
    report=dict(status='passed',prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                poses=3,source_pixel_pairs=pixels,screen_space_positions=True,
                source_width_pixels=32,preview_viewport_y_translation=30,
                player_npcs_absent=True,bank_restored=True)
    (BASE/'docs/verification/preview_sprites.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS three original condor poses, carriedfruit, screen coordinates and bank restoration')


if __name__=='__main__':main()
