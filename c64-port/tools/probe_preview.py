"""Small executed-ROM trace used by the preview controller regression."""
import json

from bzk_parse import build_images, parse_project
from extract_levels import BASE, Generator, SEED


def original_prg():
    return bytes(build_images(parse_project(BASE.parent))[0x10:0x4010])


def trace_preview(prg, timer_phase=0, mountain=0):
    r = bytearray(65536)
    r[0xC000:] = prg
    r[0x18:0x1D] = SEED
    r[0x55], r[0x57], r[0x13], r[0x59] = 5, 6, 159, mountain
    r[0x31] = timer_phase
    c = Generator(r, {})
    c.call(0xC3CC)
    rows = []
    camera = 0
    for tick in range(1, 1000):
        before_y, before_scroll = r[0xD7], r[0x13]
        r[0x52] = r[0x300] = r[0x301] = 0
        c.call(0xCB9D)
        r[0x50] = (r[0x50]+1) & 255
        c.call(0xC44A)
        if before_scroll != r[0x13]:
            camera += 2
        rows.append(dict(tick=tick, camera=camera, bird_y=r[0xD7],
                         scroll=r[0x13], wraps=r[0x7A],
                         anim_tick=r[0xD3], anim_frame=r[0xD4],
                         hold=r[0x46], timer_phase=r[0x31], state=r[0x55],
                         generated_row=r[0x8D],
                         phase='approach' if before_y > 128 else
                               'scroll' if before_y == 128 else
                               'depart' if before_y >= 29 else 'hold'))
        if r[0x55] == 1:
            return rows
    raise AssertionError('Preview did not finish')


if __name__ == '__main__':
    prg = original_prg()
    rows = trace_preview(prg)
    print(json.dumps(dict(ticks=len(rows), final=rows[-1],
                          phase_counts={p: sum(v['phase'] == p for v in rows)
                                        for p in ('approach', 'scroll', 'depart', 'hold')},
                          transitions=[v for i, v in enumerate(rows)
                                       if not i or v['phase'] != rows[i-1]['phase']]), indent=2))
    (BASE/'build_dbg/preview_original_trace.json').write_text(json.dumps(rows, indent=2)+'\n')
