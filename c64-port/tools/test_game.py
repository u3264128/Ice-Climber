#!/usr/bin/env python3
"""Behaviour regressions for the assembled PRG (run after build_game).

Uses the small instruction interpreter for repeatable input and RAM guards.
It models 6510 decimal arithmetic and guards readonly program/assets.
VICE remains the authority for video, timing and SID audio.
"""
import re
import json
import hashlib
from pathlib import Path

from emulate_prg import CPU
from symbols import read_symbols

BASE = Path(__file__).resolve().parents[1]


class Machine(CPU):
    def __init__(self):
        self.relocated_ready = False
        self.labels = read_symbols()
        data = (BASE / "c64/build/iceclimber_game.prg").read_bytes()
        self.load = int.from_bytes(data[:2], "little")
        self.end = self.load + len(data) - 2
        ram = bytearray(65536)
        ram[self.load:self.end] = data[2:]
        # This instruction-only fixture normally alternates250/251. The
        # real pacing loop now also waits for a physical border wrap;
        # offer that wrap only at its own D012 read, preserving the
        # established extra_tick raster policy elsewhere.
        wait_start=self.labels['wait_frame']
        wait_code=bytes(ram[wait_start:wait_start+160])
        wrap_read=b'\xAD\x12\xD0\xC9\xFA'
        assert wait_code.count(wrap_read)==1
        self.wait_wrap_pc=wait_start+wait_code.index(wrap_read)+3
        self.joystick, self.joystick2, self.keys, self.raster = 255, 255, {}, 251
        self.sid_events = []
        # RAM under the I/O area: visible when $01 hides I/O (the NES
        # objects run there with $01=$34); otherwise ram[] is the I/O side.
        self.under_io = bytearray(0x1000)
        super().__init__(ram, {0xDC00: self.port_a, 0xDC01: self.port_b,
                              0xD012: self.raster_read}, decimal_supported=True)
        self.pc = 0x080E
        self.run_to(self.labels["main_loop"])
        # Fixed tick timing: the 1p sixth tick runs in its own frame, as the
        # planned routes assume (the shipped game defers it when the frame
        # has no time left, see extra_tick).
        self.ram[self.labels['fixed_ticks']] = 1
        self.relocated_ready = True

    def port_a(self, mem, addr, value):
        if value is None:
            return self.joystick if mem[0xDC02] == 0 else mem[addr]

    def port_b(self, mem, addr, value):
        if value is None:
            select = mem[0xDC00]
            if select == 255:
                return self.joystick2
            # The keyboard matrix: every selected row (a low bit) pulls its
            # pressed columns low, so several rows read as their AND.
            columns = 255
            for row, pressed in self.keys.items():
                if ~row & ~select & 255:
                    columns &= pressed
            return columns

    def raster_read(self, mem, addr, value):
        if value is None:
            if self.pc==self.wait_wrap_pc:
                return 0
            self.raster = 251 if self.raster == 250 else 250
            return self.raster

    def io_hidden(self):
        bank = self.ram[1]
        return not (bank & 3 and bank & 4)

    def read(self, addr):
        if 0xD000 <= addr < 0xE000 and self.io_hidden():
            return self.under_io[addr-0xD000]
        return super().read(addr)

    def write(self, addr, value):
        if 0xD000 <= addr < 0xE000 and self.io_hidden():
            self.under_io[addr-0xD000] = value & 0xFF
            return
        if self.relocated_ready:
            for region in ('HELPERS', 'PRIOCODE'):
                start = self.labels.get(f'__{region}_RUN__', 0)
                assert not start <= addr < start+self.labels.get(f'__{region}_SIZE__', 0), \
                    f"Relocated program corruption at ${addr:04X}, PC=${self.pc:04X}"
        assert not any(self.labels[lo] <= addr < self.labels[hi] for lo, hi in
                       (("code_begin", "code_end"), ("assets_begin", "assets_end"),
                        ("extra_begin", "extra_end"), ("high_begin", "high_end"))), \
            f"Program/asset corruption at ${addr:04X}, PC=${self.pc:04X}"
        if 0xD400 <= addr < 0xD420:
            self.sid_events.append((addr, value))
        super().write(addr, value)

    def run_to(self, addr):
        for _ in range(500000):
            if self.pc == addr:
                return
            self.step()
        raise AssertionError(f"Did not reach ${addr:04X}, PC=${self.pc:04X}")

    def call(self, name, a=0):
        self.push(0xFF)
        self.push(0xEF)          # RTS target $FFF0
        self.a = a
        self.pc = self.labels[name]
        self.run_to(0xFFF0)

    def frame(self, joy=255, joy2=255):
        self.joystick, self.joystick2 = joy, joy2
        self.pc = self.labels["main_loop"]
        self.step()
        self.run_to(self.labels["main_loop"])


def climb_first_mountain(m):
    """Replay the verified UP/left/right route; never change gameplay RAM."""
    fixture = json.loads((BASE/'tools/fixtures/first_mountain_route.json').read_text())
    sequence = fixture['normal']
    assert all(joy & 0x10 for joy in sequence), 'Climb must use UP without a separate hammer button'
    for n, joy in enumerate(sequence):
        m.frame(joy)
        if n % 5 == 2 and m.ram[0x18] == 1:
            assert_cloud_glyphs(m, ('climb', n))   # normal clouds shift too
    r = m.ram
    assert r[0x18] == 3 and r[0x2C] == 8 and r[0x3A] == 5, 'Did not climb original mountain 1'
    return sequence


def start(mode=1, mountain=1):
    m = Machine()
    m.ram[m.labels['selected_mountain']] = mountain
    if mode == 2:
        m.frame(0xFD)
        m.frame()
    m.frame(0xEF)
    finish_opening(m)
    return m


def finish_opening(m):
    # These are gameplay unit fixtures. Execute the actual preview controller
    # without rendering its hundreds of frames; verify_preview exercises the
    # full frame loop and native video independently.
    ticks = 0
    while m.ram[m.labels['state']] == 4:
        m.call('scene_tick')
        ticks += 1
        assert ticks < 700
    frames = ticks              # the flyover runs one tick per PAL frame
    m.ram[m.labels['logic_phase']] = frames % 5
    m.ram[m.labels['frame']] = (m.ram[m.labels['frame']]+frames) & 255
    m.frame()


def bcd(data):
    assert all((v & 15) < 10 and v >> 4 < 10 for v in data), list(data)
    return sum(((v >> 4)*10+(v & 15))*100**i for i,v in enumerate(data))


def check_maps_and_camera():
    from extract_levels import generate, generate_bonus
    m = start()
    r, L = m.ram, m.labels
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    # No score panel in the original gameplay: one fine scroll spans the
    # full playfield, and terrain occupies the former HUD rows as well.
    for fine in range(8):
        r[L['view_fine']] = fine
        m.call('split_latch')
        assert r[L['split_open']] == 0x10 | fine
    records = []
    for mountain in range(32):
        _, cells, _, types = generate(prg, mountain)
        r[L['mountain']] = mountain+1
        m.call('setup_level')
        assert r[0x400:0x4D8] == cells[:216]
        assert r[0x500:0x5D8] == cells[216:]
        assert r[0x601:0x608] == types
        # All six camera positions must display the same immutable world.
        for cam in range(6):
            r[L['cam']] = cam
            r[L['normal_camera']:L['normal_camera']+2] = (48*cam).to_bytes(2, 'little')
            for _ in range(29):         # main_loop order: the colour swap is
                m.call('commit_view')   # committed before the next view_tick
                m.call('commit_colours')
                m.call('view_tick')
            m.call('commit_view')
            screen = 0x4000+1024*r[L['screen_buffer']]
            row = r[L['last_view_row']]
            for sy in range(25):
                expected = r[0xE000+(row+24-sy)*32:0xE000+(row+25-sy)*32]
                assert r[screen+sy*40+4:screen+sy*40+36] == expected, (mountain,cam,sy)
            # Visible colours: ice rows completely, rows between floors only
            # their rock walls (blank cells show no colour).
            m.call('commit_colours')
            assert r[L['colour_ready']] == 0
            for sy in range(25):
                c = row+24-sy
                colours = r[0xF000+c*32:0xF000+(c+1)*32]
                shown = r[0xD800+sy*40+4:0xD800+sy*40+36]
                kind = r[L['ROW_KIND']+c]
                cells = range(32) if kind == 2 else [x for x in range(32) if r[0xE000+c*32+x] != 255] if kind else ()
                assert all(shown[x] & 15 == colours[x] for x in cells), (mountain,cam,sy)
        m.call('enter_bonus')
        bonus = generate_bonus(prg, mountain)
        assert r[L['bonus_platform_count']] == len(bonus['platforms'])
        assert r[L['bonus_cloud_count']] == len(bonus['clouds'])
        # Every extracted ledge supports the original centre-foot probe.
        for p in bonus['platforms']:
            camera = max(0, p['height']-116)
            r[L['bonus_camera']:L['bonus_camera']+2] = camera.to_bytes(2,'little')
            x = 52+(p['left']+p['right'])//2-8
            r[0x1E:0x20] = x.to_bytes(2,'little')
            r[0x22] = 216+camera-p['height']
            r[L['bonus_support_mode']] = 0
            m.call('bonus_find_support')
            assert r[L['bonus_support']], (mountain,p)
        records.append(dict(mountain=mountain+1, platforms=len(bonus['platforms']), clouds=len(bonus['clouds'])))
        r[0x18] = 1
    print('PASS 32 NES maps, 192 camera positions, 32 bonus layouts and every static ledge')
    return records


def check_camera_pipeline(mode=1):
    """Back-buffer streaming keeps up with the camera and never deadlocks."""
    def run(reverse_at=None, frames=140):
        m = start(mode)
        r, L = m.ram, m.labels
        r[L['state']] = 3        # renderer pipeline; source normal-pan test is separate
        def step():
            m.call('commit_view')
            view = r[L['last_view_row']]
            if view != 0xFF:            # the shown buffer equals the cache
                base = 0x4000 + 0x400*r[L['screen_buffer']]
                for i in range(25):
                    row = (view+24-i) & 63
                    shown = r[base+i*40+4:base+i*40+36]
                    assert shown == r[0xE000+row*32:0xE000+row*32+32], (view, i)
            m.call('view_tick')
        for _ in range(10):
            step()
        r[L['bonus_camera']:L['bonus_camera']+2] = (240).to_bytes(2, 'little')
        seen = []
        for n in range(frames):
            step()
            seen.append(r[L['visual_camera']] | r[L['visual_camera']+1] << 8)
            if n == reverse_at:
                r[L['bonus_camera']:L['bonus_camera']+2] = bytes(2)
        return seen
    seen = run()
    moves = [b-a for a, b in zip(seen, seen[1:])]
    start_move = next(i for i, d in enumerate(moves) if d)
    # The row above is built while the camera rests: a climb starts at once.
    assert start_move == 0 and seen[-1] == 240, (start_move, seen[-1])
    # The eased camera moves every frame until it arrives (no stall), cruises
    # at 2 pixels and changes its speed by at most one pixel per frame.
    arrive = seen.index(240)
    travel = moves[:arrive]
    assert all(d in (1, 2) for d in travel), moves
    assert all(abs(b-a) <= 1 for a, b in zip(travel, travel[1:])), moves
    assert travel.count(2) >= 110 and not any(moves[arrive:]), moves
    # A reversal while a predicted row is pending or finished must not
    # freeze the camera (it used to stop up to 10 pixels from the target).
    for at in range(2, 24):
        assert run(at, 80)[-1] == 0, at
    # Down again from the top, then up: the back buffer view is tracked
    # across both directions.
    m = start(mode); r, L = m.ram, m.labels
    r[L['state']] = 3
    for cam, frames in ((5, 140), (0, 140), (3, 90), (1, 60), (5, 120)):
        r[L['bonus_camera']:L['bonus_camera']+2] = (cam*48).to_bytes(2, 'little')
        for _ in range(frames):
            m.call('commit_view')
            view = r[L['last_view_row']]
            base = 0x4000 + 0x400*r[L['screen_buffer']]
            for i in range(25):
                row = (view+24-i) & 63
                assert r[base+i*40+4:base+i*40+36] == r[0xE000+row*32:0xE000+row*32+32], (cam, view, i)
            m.call('view_tick')
    # The bonus stage streams too (its sky rows are skipped when unchanged).
    for variant in (0, 5):
        m = start(mode); r, L = m.ram, m.labels
        r[L['mountain']] = variant + 1
        m.call('enter_bonus')
        cam = 0
        for n in range(330):
            m.call('commit_view')
            view = r[L['last_view_row']]
            if view != 0xFF:
                base = 0x4000 + 0x400*r[L['screen_buffer']]
                for i in range(25):
                    row = (view+24-i) & 63
                    assert r[base+i*40+4:base+i*40+36] == r[0xE000+row*32:0xE000+row*32+32], (variant, n, i)
            cam = 150 if n == 300 else min(cam + (n > 10 and n % 2 == 0), 300)
            r[L['bonus_camera']:L['bonus_camera']+2] = cam.to_bytes(2, 'little')
            m.call('view_tick')
    print(f'PASS {mode}P pixel camera pipeline, reversals and shown buffers equal the map')


def assert_cloud_glyphs(m, where):
    """The visible cloud glyphs equal a fresh generation at the phases
    they claim to show. Machine state is left as it was."""
    r, L = m.ram, m.labels
    if r[L['state']] == 3:
        from test_bonus_glyph_cache import FONT_START, FONT_SIZE, source_font
        assert bytes(r[FONT_START:FONT_START+FONT_SIZE]) == source_font(), \
            ('incorrect shared source cloud font', where)
        return
    regs = {k: getattr(m, k) for k in ('pc', 'a', 'x', 'y', 'sp', 'c', 'z', 'i', 'd', 'v', 'n')}
    phase, shown = L['GLYPH_PHASE'], L['GLYPH_SHOWN']
    phase2, shown2 = 0x0640, 0x0648        # normal_clouds.asm GLYPH_PHASE2/SHOWN2
    saved = {k: bytes(r[k:k+8]) for k in (phase, shown, phase2, shown2)}
    glyphs = bytes(r[0x4800:0x5000])
    r[phase:phase+8], r[phase2:phase2+8] = r[shown:shown+8], r[shown2:shown2+8]
    r[shown:shown+8] = r[shown2:shown2+8] = b'\xff'*8
    zero = bytes(r[0x80:0x8A])
    m.call('commit_clouds')
    assert bytes(r[0x4800:0x5000]) == glyphs, (where, [hex(0x4800+i) for i in range(0x800)
                                                         if r[0x4800+i] != glyphs[i]][:8])
    for k, v in saved.items():
        r[k:k+8] = v
    r[0x80:0x8A] = zero
    for k, v in regs.items():
        setattr(m, k, v)


def check_bonus_clouds_shown():
    """Moving bonus clouds reach the screen: once everything is committed
    (at read_joy), the shown buffer equals the map in every frame."""
    checked = 0
    for variant in range(8):
        m = start(mountain=variant+1)
        r, L = m.ram, m.labels
        r[L['bonus_requested']] = 1
        m.frame()
        assert r[0x18] == 3
        count = r[L['bonus_cloud_count']]
        moved = set()
        start_x = bytes(r[L['bonus_cloud_x']:L['bonus_cloud_x']+count])
        for n in range(240):
            m.pc = L['main_loop']
            m.step()
            m.run_to(L['read_joy'])
            view = r[L['last_view_row']]
            base = 0x4000 + 0x400*r[L['screen_buffer']]
            for i in range(25):
                row = (view+24-i) & 63
                assert r[base+i*40+4:base+i*40+36] == r[0xE000+row*32:0xE000+row*32+32], (variant, n, i)
            # Shared phase codes cannot identify the owning cloud. Resolve
            # each immutable world height to the actual prepared screen row
            # and check its phase, complete role sequence and original mask.
            from test_bonus_glyph_cache import source_phase
            for c in range(count):
                height = r[L['bonus_cloud_hlo']+c]+256*r[L['bonus_cloud_hhi']+c]
                cloud_row = height//8+2
                difference = cloud_row-view
                if 0 <= difference < 25:
                    phase = r[L['bonus_cloud_x']+c] & 7
                    assert r[L['GLYPH_SHOWN']+c+1] == phase, \
                        ('stale displayed bonus cloud', variant, n, c)
                    roles = (0, 1)+(2,)*(r[L['bonus_cloud_width']+c]//8-3)+(3, 4)
                    column = r[L['bonus_cloud_x']+c]//8
                    screen_row = base+(24-difference)*40+4
                    mask = source_phase(phase)
                    for offset, role in enumerate(roles):
                        code = r[screen_row+((column+offset)&31)]
                        assert code == 128+5*phase+role, \
                            ('stale displayed bonus phase ID', variant, n, c, offset, code)
                        assert bytes(r[0x4800+code*8:0x4800+(code+1)*8]) == mask[role*8:role*8+8], \
                            ('wrong displayed source cloud pixels', variant, n, c, offset)
            if n % 6 == 3:
                assert_cloud_glyphs(m, (variant, n))
            checked += 1
            m.run_to(L['main_loop'])
        moved = [a != b for a, b in zip(start_x, r[L['bonus_cloud_x']:L['bonus_cloud_x']+count])]
        assert all(moved), (variant, 'clouds did not move')
    print(f'PASS moving bonus clouds on screen in all 8 variants ({checked} frames, glyph phases)')


def check_cloud_cells():
    """Four-cell cloud steps must leave exactly what a full floor redraw draws."""
    m = start()
    r, L = m.ram, m.labels
    floors_checked = 0
    for mountain in range(1, 33):
        r[0x46] = mountain
        m.call('setup_level')
        # Rows below the view are never shown again, so cloud_update leaves
        # them stale; here every floor counts as visible.
        r[L['last_view_row']] = 0
        clouds = [f for f in range(1, 8) if r[0x600+f] & 0xE0 >= 0x60]
        for tick in range(400):
            m.call('cloud_update')
            if tick % 50 != 49:
                continue
            for f in clouds:
                row = 0xE000 + (6*f+2)*32
                stepped = bytes(r[row:row+32])
                m.call('cache_normal_floor', f)
                assert bytes(r[row:row+32]) == stepped, (mountain, f, tick)
                floors_checked += 1
    assert floors_checked > 100
    print(f'PASS incremental cloud cells equal full redraws ({floors_checked} floor rows)')
    # Broken and repaired cells update two cache cells, on screen or not.
    import random
    rng = random.Random(7)
    cells = 0
    for mountain in range(1, 33):
        r[0x46] = mountain
        m.call('setup_level')
        for _ in range(12):
            f, col = rng.randrange(1, 8), rng.randrange(24)
            index = f*24+col
            r[0x400+index], r[0x500+index] = rng.choice(((0, 0), (1, 1), (0, 1), (1, 0), (2, 1)))
            r[L['wrld']], r[L['colw']] = f, col+8
            m.call('cache_cell')
            rows = [0xE000+(6*f+k)*32 for k in (1, 2)]
            cached = [bytes(r[a:a+32])+bytes(r[a+0x1000:a+0x1020]) for a in rows]
            m.call('cache_normal_floor', f)
            assert cached == [bytes(r[a:a+32])+bytes(r[a+0x1000:a+0x1020]) for a in rows], (mountain, f, col)
            cells += 1
    print(f'PASS single-cell breaks and repairs equal full floor redraws ({cells} cells)')


def schedule_model(logs, rotated=None, split_ties=None, players=0, odd=False, details=None):
    """The raster events schedule_actors writes for the logical sprites
    logs (dicts with y, x and group g): (line, VIC sprite, logical index)
    in event order. Stable height order, the initial batch, VIC deadlines
    and the overload priority (players: the climbers' sprites, logical
    0..players-1; odd: the frame counter's parity); test_scheduler.py
    checks every schedule of real play against it. Popo's three layers
    (logical 0..2, colour $11 first) become the two of a crowded frame
    before anything drops: logs then changes as the RAM does (details:
    the multicolour layer's pointer, popo_details[animidx])."""
    if len(logs) <= 8:
        return [(0, i, i) for i in range(len(logs))]
    order = sorted(range(len(logs)), key=lambda i: (logs[i]['y'], i), reverse=True)
    heights = [logs[i]['y'] for i in reversed(order)]

    def same(a, b):
        # layers of one figure: equal y and x (the low byte)
        return (logs[a]['y'], logs[a]['x'] & 255) == (logs[b]['y'], logs[b]['x'] & 255)
    # Short reuse: the initial batch (VIC sprites 0-7 from line 0), then at
    # most four later events, each adding a line to the 36-line reuse.
    short = 28 + len(logs)
    initial_batch = len(logs) <= 12 and all(b-a >= short for a, b in zip(heights, heights[8:]))
    p = len(logs)-8                     # event 7 in order (descending)
    if initial_batch and same(order[p], order[p-1]):
        # A figure on the batch boundary: its back layers end the batch, its
        # front layers reuse lower VIC sprites (sched_rotate).
        lo, hi = p-1, p
        while lo > 0 and same(order[lo-1], order[p]):
            lo -= 1
        while hi+1 < len(order) and same(order[hi+1], order[p]):
            hi += 1
        m = hi-p+1
        order[lo:hi+1] = order[lo+m:hi+1]+order[lo:lo+m]
        if rotated is not None:
            rotated.append((m, p-lo))
    elif split_ties is not None and initial_batch and logs[order[p]]['y'] == logs[order[p-1]]['y']:
        split_ties.append(p)
    reuse = short if initial_batch else 46
    while True:
        crowded = next((k for k in range(len(order)-8)
                        if logs[order[k]]['y'] - logs[order[k+8]]['y'] < reuse), None)
        if crowded is None:
            break
        if logs[0].get('col') == 0x11:
            logs[2].update(ptr=details, mc=1)
            logs[0].update(col=0xFF, y=0xFF)
            order.remove(0)
            continue
        # Never a climber: the lowest other sprite in the window on even
        # frames, the highest on odd ones (two crowded figures take turns),
        # with the other layer of its pair when that is its neighbour.
        others = [k for k in range(crowded, crowded+9) if order[k] >= players]
        k = others[-1] if odd else others[0]
        victim = order[k]
        drop = {victim}
        if logs[victim]['g'] == 0 and k+1 < len(order) and order[k+1] == victim-1:
            drop.add(victim-1)
        elif logs[victim]['g'] == 2 and k > 0 and order[k-1] == victim+1:
            drop.add(victim+1)
        order = [i for i in order if i not in drop]
    previous, events = [None]*8, []
    for n,i in enumerate(reversed(order)):
        y = logs[i]['y']
        if initial_batch and n < 8:
            slot, line = n, 0
        else:
            slot = next(s for s in range(8) if previous[s] is None or previous[s]+reuse <= y)
            # A VIC sprite's first use starts at line 0 (as early as the
            # event order allows); a reuse 28 lines early or after the
            # previous sprite on it ended.
            line = 0 if previous[slot] is None else max(y-28, previous[slot]+22)
        previous[slot] = y
        events.append((line, slot, i))
    return events


def check_multiplexer():
    """Check stable height order, VIC deadlines and overload priority."""
    import random
    m = Machine(); r, L = m.ram, m.labels
    rotated, split_ties = [], []
    fallback = adaptive = 0
    rng = random.Random(3)
    for _ in range(1500):
        # The climbers come first: up to three layers and a mallet each
        # (actor_append), at most six sprites with two climbers.
        logs = []
        climbers = rng.choice((0, 1, 1, 2))
        for _ in range(climbers):
            y, x = rng.randrange(43, 247), rng.randrange(256)
            layers = rng.choice((1, 2, 3)) if climbers == 1 else rng.choice((1, 2))
            logs += [dict(y=y, x=x, g=1) for _ in range(layers)]
            if rng.random() < 0.5:
                logs.append(dict(y=y-8, x=(x+8) & 255, g=1))
        players = len(logs)
        odd = rng.random() < 0.5
        while len(logs) < rng.randrange(6, 21):
            # Often at an earlier sprite's height: layers of one figure
            # (its x too) or another figure beside it.
            y = rng.choice([l['y'] for l in logs]) if logs and rng.random() < 0.3 else rng.randrange(35, 247)
            x = rng.randrange(256)
            if rng.random() < 0.5:      # actor_pair: both layers at one x, y
                logs += [dict(y=y, x=x, g=2), dict(y=y, x=x, g=0)]
            else:                       # actor_append: a climber's layers
                logs += [dict(y=y, x=x, g=1) for _ in range(rng.choice((1, 1, 2, 3)))]
        for i, l in enumerate(logs):
            l['xhi'], l['mc'] = rng.random() < 0.3, rng.random() < 0.5
            r[0xE800+i], r[0xE820+i], r[0xE840+i], r[0xE8E0+i] = l['x'], l['xhi'], l['y'], l['g']
            r[0xE860+i], r[0xE880+i], r[0xE8A0+i] = i, i & 15, l['mc']
        r[L['logical_count']] = len(logs)
        r[L['player_sprites']] = players
        r[L['frame']] = rng.randrange(128)*2 + odd
        r[L['back_base']] = 32 * (len(logs) & 1)
        # twice (the second pass reuses its choice) and once nudged by 0..2 lines
        for nudge in (False, False, True):
            if nudge:           # both layers of a pair share their y (actor_pair)
                for i, l in enumerate(logs):
                    if l['g'] != 0:
                        dy = rng.randrange(0, 3)
                    l['y'] = min(l['y'] + dy, 246)
                    r[0xE840+i] = l['y']
            m.call('schedule_actors')
            b = r[L['back_base']]   # events go to the half the IRQ is not reading
            # The frame IRQ's batch (pending_batch leading events) implies
            # line 0 and VIC sprite k; their own line and slot are not stored.
            batch = r[L['pending_batch']]
            got = [(0, k) if k < batch else (r[0xF800+b+k], r[0xF840+b+k]) for k in range(r[L['pending_count']])]
            got = [event+(r[0xF880+b+k], r[0xF8C0+b+k]) for k, event in enumerate(got)]
            want = [(line, slot, logs[i]['y'], logs[i]['x'])
                    for line, slot, i in schedule_model(logs, rotated, split_ties, players, odd)]
            assert got == want, (nudge, logs)
            # The layers of one figure (consecutive, equal y and x) keep
            # their priority: the front one on the lower VIC sprite.
            slots = {r[0xF940+b+k]: got[k][1] for k in range(len(got))}
            for i in range(len(logs)-1):
                if i in slots and i+1 in slots and (
                        (logs[i]['y'], logs[i]['x'] & 255) == (logs[i+1]['y'], logs[i+1]['x'] & 255)):
                    assert slots[i] < slots[i+1], (i, slots, logs)
            assert set(range(players)) <= {i for _, _, i in schedule_model(logs, None, None, players, odd)}
            run = 0
            while run < len(want) and want[run][:2] == (0, run):
                run += 1
            assert batch == run, (nudge, batch, run, logs)
        # $D010/$D01C/$D015 after each event from the batch's last one on
        msb = mc = ena = 0
        for k in range(len(got)):
            slot, ptr = got[k][1], r[0xF940+b+k]
            l, bit = logs[ptr], 1 << slot
            msb = msb | bit if l['xhi'] else msb & ~bit
            mc = mc | bit if l['mc'] else mc & ~bit
            ena |= bit
            if k >= batch-1:
                assert (r[0xF900+b+k], r[0xF9C0+b+k], r[0x0700+b+k]) == (msb, mc, ena), (k, logs)
            assert r[0xF980+b+k] == ptr & 15
        fallback += len(logs) > 8 and len(got) < len(logs)
        adaptive += len(logs) > 8 and [event[:2] for event in got[:8]] == [(0,i) for i in range(8)]
    assert fallback > 50 and adaptive > 0 and rotated and split_ties, (len(rotated), len(split_ties))
    assert {m for m, _ in rotated} >= {1, 2} and {n for _, n in rotated} >= {1, 2}, set(rotated)
    # Six player layers/mallets are appended first in2P. Every crowded
    # nine-sprite window therefore contains a lower-priority enemy.
    for _ in range(1000):
        for i in range(32):
            r[0xE840+i]=rng.randrange(35,247)
            r[0xE860+i]=i
            r[0xE8E0+i]=1
        r[L['logical_count']]=32
        r[L['player_sprites']]=6
        r[L['frame']]=rng.randrange(256)
        m.call('schedule_actors')
        b=r[L['back_base']]
        kept=set(r[0xF940+b:0xF940+b+r[L['pending_count']]])
        assert set(range(6)) <= kept, ('Player or hammer lost to priority',kept)
    # The two-climber scene of random2p_16 (frames 576-580): both climbers
    # hammering 39 lines below Topi and the ice block it pushes. Eleven
    # sprites, three later events: a 39-line reuse, all shown, with the
    # second climber turned on the batch boundary. Four lines closer, nine
    # sprites within 35 lines: Topi and the block take turns, the climbers
    # stay.
    for closer, missing in ((0, (set(), set())), (4, ({10}, {8, 9}))):
        scene = [(155,106,1)]*2+[(147,106,1)]+[(155,230,1)]*2+[(147,230,1)]+[(212,55,2),(212,55,0),
                 (116+closer,66,2),(116+closer,66,0),(118+closer,84,1)]
        logs = [dict(y=y, x=x, g=g) for y, x, g in scene]
        for frame in (10, 11):
            for i, l in enumerate(logs):
                r[0xE800+i], r[0xE820+i], r[0xE840+i], r[0xE8E0+i] = l['x'], 0, l['y'], l['g']
                r[0xE860+i], r[0xE880+i], r[0xE8A0+i] = i, i & 15, 0
            r[L['logical_count']], r[L['player_sprites']], r[L['frame']] = len(logs), 6, frame
            m.call('schedule_actors')
            b, count = r[L['back_base']], r[L['pending_count']]
            want = schedule_model(logs, None, None, 6, frame & 1)
            assert [(line, slot) for line, slot, _ in want] ==                 [(0, k) if k < r[L['pending_batch']] else (r[0xF800+b+k], r[0xF840+b+k]) for k in range(count)]
            assert set(range(11))-set(r[0xF940+b:0xF940+b+count]) == missing[frame & 1], (closer, frame)
            if not closer:
                slots = {r[0xF940+b+k]: (r[0xF840+b+k] if k >= r[L['pending_batch']] else k) for k in range(count)}
                assert r[L['sched_gap']] == 39 and slots[4] == 7 and slots[3] < 7, slots
                assert slots[0] < slots[1] and slots[3] < slots[4], slots
    # Popo in three layers (route 31, frame 2196: nine sprites, eight on
    # lines 172-175) becomes the two of a crowded frame instead: the white
    # layer leaves, the third layer takes the multicolour details. Nothing
    # else is left out, in either frame parity.
    scene = [(155,245,1,0x53,0x11,0),(155,245,1,0x54,14,0),(155,245,1,0x55,10,0),(147,253,1,0x85,10,0),
             (172,106,2,0x7A,3,1),(172,106,0,0x7B,10,0),(164,53,2,0x70,3,1),(164,53,0,0x71,10,0),
             (166,71,1,0xB1,1,1)]
    for frame in (6, 7):
        logs = [dict(y=y, x=x, g=g, ptr=p, col=c, mc=mc) for y, x, g, p, c, mc in scene]
        for i, l in enumerate(logs):
            r[0xE800+i], r[0xE820+i], r[0xE840+i], r[0xE8E0+i] = l['x'], 0, l['y'], l['g']
            r[0xE860+i], r[0xE880+i], r[0xE8A0+i] = l['ptr'], l['col'], l['mc']
        r[L['animidx']] = 4                     # jumping, facing right
        details = r[L['popo_details']+4]
        r[L['logical_count']], r[L['player_sprites']], r[L['frame']] = len(logs), 4, frame
        m.call('schedule_actors')
        b, count = r[L['back_base']], r[L['pending_count']]
        want = schedule_model(logs, None, None, 4, frame & 1, details)
        assert [(line, slot) for line, slot, _ in want] == \
            [(0, k) if k < r[L['pending_batch']] else (r[0xF800+b+k], r[0xF840+b+k]) for k in range(count)]
        ptrs = [r[0xF940+b+k] for k in range(count)]
        assert ptrs == [logs[i]['ptr'] for _, _, i in want]
        assert sorted(ptrs) == sorted([0x54, details, 0x85, 0x7A, 0x7B, 0x70, 0x71, 0xB1]), [hex(p) for p in ptrs]
        assert (r[L['LOG_PTR']+2], r[L['LOG_MC']+2], r[L['LOG_COL']], r[L['LOG_Y']]) == (details, 1, 0xFF, 0xFF)
    for y,hi,visible in ((34,0,False),(35,0,True),(246,0,True),
                         (247,0,False),(255,255,False),(0,1,False)):
        r[L['logical_count']]=0
        r[L['actor_mask']]=r[L['actor_category']]=1
        r[L['actor_y']],r[L['actor_yhi']]=y,hi
        m.call('actor_append')
        assert bool(r[L['logical_count']])==visible,(y,hi,visible)
    print(f'PASS sprite multiplexer schedules 1500 random scenes like the reference ({fallback} with priority drops, {adaptive} with eight initial channels, {len(rotated)} figures turned on the batch boundary, {len(split_ties)} split equal-height figures)')


def check_physics_and_enemies():
    m = start()
    r,L = m.ram,m.labels
    prg = (BASE/'extracted/rom/prg_c000-ffff.bin').read_bytes()
    for falling in (False, True):
        ref = bytearray(65536)
        ref[0xC000:] = prg
        ref[1] = r[0x22] = 180
        ref[0xE2],ref[0xE4] = r[0x57],r[0x56] = 0xA8,3
        ref[0xE0] = r[0x52] = int(falling)
        ref[0xE6] = r[0x53] = 4 if falling else 0
        ref[0xE8] = r[0x54] = 5 if falling else 0
        ref[0xEA] = r[0x55] = 0
        cpu,profile = CPU(ref,{}),[]
        for _ in range(60):
            cpu.a=0
            cpu.push(0xBF);cpu.push(0xFF);cpu.pc=0xC83D
            while cpu.pc != 0xC000: cpu.step()
            r[0x1D]=r[0x22]
            m.call('vertical_step')
            assert r[0x22] == ref[1]
            assert r[0x53:0x56] == bytes([ref[0xE6],ref[0xE8],ref[0xEA]])
            profile.append(r[0x22])
        if not falling: assert 180-min(profile)==51
    m.call('setup_level')
    r[0x1E]=160;r[0x17]=0xF7
    for _ in range(64):m.call('move_horizontal')
    assert r[0x1E]==232 and r[0x59]==24 and r[0x2B]==0
    r[0x17]=0xFB;m.call('move_horizontal')
    assert r[0x2B]==0 and r[L['onground']]==2
    for _ in range(15):m.call('move_horizontal')
    assert r[0x2B]==1
    m.call('begin_jump');old=r[0x1E];r[0x17]=0xF7
    for _ in range(8):m.call('move_horizontal')
    assert r[0x2B]==1 and r[0x1E]<old
    # Full input/helmet/brick trajectories are checked against the executed
    # original player handler, rather than invented impact coordinates.
    # The enemies are the original NES objects (tools/test_nes_objects.py
    # compares every tick with the ROM). Here: their effects in the game.
    from transplant_objects import map_ram
    seal_state=map_ram(0x93)
    m.call('setup_level');r[0x46]=2;r[L['completed_mountains']]=1;m.call('setup_level')
    hole=2*24+12                       # NES floor 3: $F02F puts a seal there
    r[0x400+hole]=0
    filled=False
    for _ in range(3000):
        m.frame()
        if r[0x400+hole]:
            filled=True;break
    assert filled,'No seal brought ice to the hole'
    m.call('setup_level');r[L['bear_timer']:L['bear_timer']+2]=bytes((1,0))
    bear=False
    for _ in range(4000):
        m.frame()
        bear|=r[map_ram(0x92)]==0xFF
        if r[0x3A]:
            break
    assert bear and r[0x3A]==1,'The bear did not raise the view'
    m.call('setup_level');r[0x46]=2;r[L['completed_mountains']]=1;m.call('setup_level')
    icicles=set()
    for _ in range(600):
        m.frame();icicles|={r[map_ram(0x99+i)] for i in range(3)}
    assert icicles&{2,0xFF},('No icicle hung or fell',icicles)
    # Clouds carry a rider without altering the persistent terrain maps.
    m.call('setup_level');r[0x46]=2;m.call('setup_level')
    r[0x1A],r[0x22],r[0x1D]=3,72,72
    r[0x613]=12;r[L['cloud_subpixel']+3]=0
    r[0x448:0x460]=bytes(24);r[0x548:0x560]=bytes(24)
    cloud_player_x=r[0x613]*8+20
    r[0x1E],r[0x1F]=cloud_player_x&255,cloud_player_x>>8
    r[L['joy']]=255
    r[L['firehit']]=0
    before=r[0x1E];terrain=bytes(r[0x400:0x600])
    for _ in range(20):
        m.call('cloud_update')
        m.call('normal_player_tick')  # probe support, then carry the rider
    assert r[0x1E]!=before and r[0x400:0x600]==terrain
    lives=r[0x19];r[0x2C]=3;m.call('player_died')
    assert r[0x19]==lives-1 and r[0x1A]<=3 and r[0x2C]==3 and r[0x69]==120 and r[0x400:0x600]==terrain
    print('PASS NES jump/skid, two ice layers, stone, repair, enemy deaths, bear, ice and cloud riders')


def sprite_feet():
    """Pointer -> last sprite row with pixels, from the built sprite data."""
    inc=(BASE/'c64/build/sprite_frames.inc').read_text()
    blob=(BASE/'c64/build/game_sprites.bin').read_bytes()
    names={int(v,16):n for n,v in re.findall(r'(\w+) = \$([0-9A-F]+)',inc) if n!='SPRITE_PAGES'}
    feet={}
    for p in range(0x40,0x40+len(blob)//64):
        n=names[max(q for q in names if q<=p)]    # extra layers follow their frame
        d=blob[(p-0x40)*64:(p-0x40)*64+63]
        used=[y for y in range(21) if any(d[y*3:y*3+3])]
        feet[p]=(n,used[-1] if used else None)
    return feet


def check_support_probe():
    """Compare random packed maps with the executed original CD62 oracle."""
    import random
    from test_original_physics import Reference
    m=start();r,L=m.ram,m.labels
    original=Reference();ref=original.ram
    rng=random.Random(7)
    for _ in range(3000):
        for i in range(9*24):
            value=rng.choice((0,0,0,1,2,3))
            r[0x400+i]=3 if value==2 and i%24 in (0,23) else value
            r[0x500+i]=rng.choice((0,0,0,1,2,3))
        r[L['cam']]=rng.randrange(0,7)
        px=rng.randrange(52,308)
        r[L['pxlo']],r[L['pxhi']]=px&255,px>>8
        row=rng.randrange(0,5)
        r[L['supflag']]=r[L['support_offset']]=r[L['break_layer']]=0x55
        m.call('support_at',row)
        got=(r[L['supflag']],r[L['support_offset']],r[L['break_layer']])
        if row>=4:
            assert r[L['supflag']]==0,(row,got);continue
        w=row+r[L['cam']]
        ref[0x400:0x4D8]=bytes(255 if value==0 else 4 if value==2 else 0 if value==3 else 1
                                    for value in r[0x400:0x4D8])
        ref[0x500:0x5D8]=bytes(255 if value==0 else value for value in r[0x500:0x5D8])
        ref[0x5A],ref[0x64],ref[0x6A],ref[0x68]=w+1,(px-52)&255,1,r[L['move_dir']]
        ref[0x786]=ref[0x787]=0
        if w<9 and (r[L['floor_types']+w]&0xE0)>=0x60:
            ref[0x786]=w+1
            lefts=[((r[L['cloud_x']+slot]-4)*8+r[L['cloud_subpixel']+slot])&255
                   for slot in (w,w+8)]
            width2=28 if (r[L['floor_types']+w]&0xE0)<0xC0 else 27
            ref[0x788],ref[0x78A]=lefts[0],(lefts[0]+26)&255
            ref[0x78C],ref[0x78E]=lefts[1],(lefts[1]+width2)&255
            ref[0x7D7]=r[L['cloud_dir']+w]
        original.call(0xCD62)
        support=2 if original.c and ref[0x783]<128 else 1 if original.c else 0
        want=(support,0,0)
        assert got==want,(row,w,px,got,want,ref[0x783])
    print('PASS3000 original CD62 map/side-wall/post/cloud support cases')


def check_actor_feet():
    """Popo, a seal and the walking bear stand on the same raster line."""
    from transplant_objects import map_ram
    feet=sprite_feet()
    m=start();r,L=m.ram,m.labels
    def standing(kind):
        lines=set()
        for i in range(r[L['logical_count']]):
            name,last=feet[r[0xE860+i]]
            if last is not None and name.startswith(kind) and (kind!='BEAR_' or name.endswith('_16')):
                lines.add(r[0xE840+i]+last)    # LOG_Y + lowest pixel row
        return lines
    m.frame()
    # The original bottom floor: seal Y $C8 ($EDD5), walking bear Y $B8 ($E185).
    for nes,value in ((0x92,0xFF),(0x9D,100),(0xA8,0xB8),(0xBE,1),(0x03DE,0x18),(0x03E9,4),
                      (0x93,0xFF),(0x9E,160),(0xA9,0xC8),(0xBF,1),(0x03DF,0xA0),(0x03EA,5)):
        r[map_ram(nes)]=value
    for frame in range(4):
        r[L['frame']]=frame
        m.call('actors_prepare')
        popo,bear,topi=(max(standing(k),default=None) for k in ('POPO_','BEAR_','TOPI_'))
        # land_py 216/168/120/72 floor lines; sprites sit 4 lines higher
        assert popo==216+17-4 and bear==popo and topi==popo,(popo,bear,topi)
    print('PASS Popo, a seal and the walking bear stand on the same floor line')


def check_two_players():
    m=start(2);r,L=m.ram,m.labels
    assert r[L['player_count']]==2
    for _ in range(20):m.frame(0xF7,0xFB)
    assert r[0x203]>100 and r[0x223]<220
    assert r[0x20A]==0 and r[0x22A]==1
    # Keyboard inputs and pause are decoded independently.
    m.keys={0xFD:0xFD,0xEF:0xFD}
    m.call('read_joy');assert r[L['input_joy']]&1==0 and r[L['input_joy']+1]&1==0
    m.keys={0xDF:0xFD};m.call('read_joy');assert r[L['paused']]==1
    old=r[L['logic_frame']];m.call('play_tick');assert r[L['logic_frame']]==old
    m.keys={};m.call('read_joy');m.keys={0xDF:0xFD};m.call('read_joy')
    assert not r[L['paused']]
    m.keys={};m.call('setup_level')
    # The original has no partner hammer hit: climbers bump ($D212,
    # tools/test_nes_bump.py) instead.
    assert 'players_hit' not in L
    m.call('setup_level')
    r[0x207],r[0x20B],r[0x205],r[0x206]=2,2,168,168
    r[0x3A]=1;r[L['camera_before']]=0;r[L['player_index']]=0
    m.call('share_camera');assert r[L['player_hidden']+1]
    m.call('context_load')  # complete the controlled P0-context fixture
    m.call('play_tick')
    assert r[0x220]==2 and r[0x227]>=1 and r[0x3A]==1
    # One player can continue after the other runs out of lives (original
    # lives are spare climbers: 0 is the last one, negative is out).
    r[0x200]=0xFF;m.call('context_load');m.call('play_tick');assert r[0x18]==1 and r[0x220]==2
    r[0x220]=0xFF;m.call('play_tick');assert r[0x18]==2 and r[L['result_game_over']]
    def screen_text(row):
        return bytes(r[0x4000+row*40:0x4000+row*40+40])
    font_g = screen_text(7)[15]
    r[L['firehit']]=1;m.call('results_tick');assert r[0x18]==0 and not r[L['result_game_over']]
    # One climber: with no spare life left (0) it still comes back; losing
    # that one shows GAME OVER and returns to the title.
    m=start();r,L=m.ram,m.labels
    r[0x19]=1;m.call('player_died')
    assert r[0x18]==1 and r[0x19]==0 and not r[L['result_game_over']]
    m=start();r,L=m.ram,m.labels
    r[0x19]=0;m.call('player_died')
    assert r[0x18]==2 and r[L['result_game_over']] and screen_text(7)[15]==font_g
    r[L['firehit']]=0
    for _ in range(249):m.call('results_tick')
    assert r[0x18]==2
    m.call('results_tick');assert r[0x18]==0
    print('PASS two joysticks, keyboard/pause, friendly hammer stun, shared camera, independent lives, game over')


def check_bonus_and_scores():
    m=start(2);r,L=m.ram,m.labels
    m.call('enter_bonus')
    # Fruit on the original ledges ($F6F2: the first view), touched in the
    # middle of their $DB1D boxes (tools/test_bonus_rom.py has the edges).
    ps=L['PLAYER_STATES']
    for i in range(4):
        camera=0
        height=(191,143,55,55)[i]
        r[L['bonus_camera']:L['bonus_camera']+2]=camera.to_bytes(2,'little')
        r[ps+3],r[ps+4],r[ps+5]=(152,216,100,244)[i],0,216+camera-height
        m.call('bonus_fruits')
    assert r[L['fruit_counts']]==4 and r[L['fruit_mask']]==0
    # The condor at the top: its legs pass just right of its X ($D507).
    r[L['bonus_camera']:L['bonus_camera']+2]=(240).to_bytes(2,'little')
    r[0x1E],r[0x22]=r[L['condor_xlo']]+7,30
    m.call('bonus_catch');assert r[L['bonus_winner']]==1
    m.call('enter_results')
    assert bcd(r[L['result_pending']:L['result_pending']+3])==4200
    r[0x2A]=1;m.call('results_tick')
    assert bcd(bytes([r[0x25],r[0x26],r[0x51]]))==4200
    r[0x2A]=1;m.call('results_tick')
    assert r[0x18]==1 and r[0x46]==2 and r[L['player_count']]==2
    assert bcd(bytes([r[0x25],r[0x26],r[0x51]]))==4200
    # Decimal carry into the millions digit (the original keeps six BCD
    # digits of tens: up to 9,999,990) and the 9,999,999 cap, checked again
    # in native VICE.
    mil=L['score_mil']
    r[0x25],r[0x26],r[0x51],r[mil]=0x90,0x99,0x99,0
    m.x=0;m.y=0;m.call('score_add',0x50)
    assert (r[0x25],r[0x26],r[0x51],r[mil])==(0x40,0x00,0x00,1)
    hs=[r[L[k]] for k in ('high_score_lo','high_score_hi','high_score_top','high_score_mil')]
    assert bcd(bytes(hs))==1000040
    r[0x25],r[0x26],r[0x51],r[mil]=0x90,0x99,0x99,9
    m.x=0;m.y=0;m.call('score_add',0x50)
    assert (r[0x25],r[0x26],r[0x51],r[mil])==(0x99,0x99,0x99,9)
    m=start();r,L=m.ram,m.labels;m.call('enter_bonus')
    lives=r[0x19];r[0x22]=240;m.call('begin_fall');m.call('bonus_player_tick')
    m.call('play_context_store');m.call('bonus_falls')
    assert r[L['bonus_out']]==1 and r[0x19]==lives
    m.call('play_tick');assert r[0x18]==2
    m=start();r,L=m.ram,m.labels;m.call('enter_bonus')
    r[L['bonus_ticks']]=1;r[L['bonus_left']]=1;m.call('play_tick')
    # $F6DB: music off and a $4D wait of $0A slow ticks (110 frames) first
    from transplant_sound import ZERO_PAGE
    assert r[0x18]==3 and r[L['bonus_reason']]==2 and r[ZERO_PAGE[0xFB]]==0x80
    for tick in range(200):
        if r[0x18]!=3:break
        m.call('play_tick')
    assert r[0x18]==2 and 108<=tick<=112, tick
    # Every stage can pass through bonus/tally and continue; 32 wraps to 1.
    m=start(2);r,L=m.ram,m.labels
    for mountain in range(1,33):
        assert r[0x46]==mountain
        m.call('enter_bonus')
        r[L['fruit_counts']],r[L['fruit_counts']+1]=1,2
        m.call('enter_results');r[0x2A]=1;m.call('results_tick')
        r[0x2A]=1;m.call('results_tick')
    assert r[0x46]==1 and r[L['phase_counter']]==1
    assert r[0x19]==4 and r[0x220]==4
    print('PASS fruit, condor, bonus fall/timeout, seven-digit BCD, extra lives and all 32 stage transitions')


def main():
    m=Machine();r=m.ram
    sprites=(BASE/'c64/build/game_sprites.bin').read_bytes()
    assert r[0x5000:0x5000+len(sprites)]==sprites and len(sprites)<=8192
    original=(BASE/'converted/screens/title_c64.bin').read_bytes()
    assert r[0x4000:0x4000+13*40]==original[:13*40]
    assert r[0xD015]==0 and r[0xD016]==0x18
    assert r[0x7000:0x7000+0x1000] == (BASE/'c64/build/iceclimber_game.prg').read_bytes()[2+0x7000-0x801:2+0x8000-0x801]
    helper_load=m.labels['__HELPERS_LOAD__']
    helper_run=m.labels['__HELPERS_RUN__']
    helper_size=m.labels['__HELPERS_SIZE__']
    image=(BASE/'c64/build/iceclimber_game.prg').read_bytes()
    source=helper_load-m.load+2
    assert 0xFC00 <= helper_run < helper_run+helper_size <= 0xFFE0
    assert r[helper_run:helper_run+helper_size] == image[source:source+helper_size]
    assert m.labels['code_begin'] <= int.from_bytes(r[0xFFFA:0xFFFC], 'little') < m.labels['code_end']
    assert m.labels['code_begin'] <= int.from_bytes(r[0xFFFE:0x10000], 'little') < m.labels['code_end']
    m.frame(0xEF)  # the title has a safe RTI vector; gameplay enables raster IRQs
    assert int.from_bytes(r[0xFFFE:0x10000], 'little') == m.labels['raster_irq']
    print('PASS relocated helpers survive video initialization and preserve interrupt vectors')
    records=check_maps_and_camera()
    check_camera_pipeline()
    check_camera_pipeline(2)
    check_bonus_clouds_shown()
    check_cloud_cells()
    check_multiplexer()
    check_physics_and_enemies()
    check_actor_feet()
    check_support_probe()
    check_two_players()
    check_bonus_and_scores()
    m=start();sequence=climb_first_mountain(m)
    (BASE/'build_dbg/climb_sequence.json').write_text(json.dumps(sequence)+'\n')
    assert m.ram[0x19]==3
    print(f'PASS full joystick climb to bonus ({len(sequence)} PAL input frames, three lives)')
    # the logo music (original request $04) plays on all three SID voices
    # (tools/test_sound.py checks the engine and the APU emulation)
    from transplant_sound import ZERO_PAGE
    m.ram[ZERO_PAGE[0xFB]]=0x04
    for _ in range(240):
        m.call('sound_engine');m.ram[m.labels['snd_debt']]=1;m.ram[m.labels['snd_hurry']]=0;m.call('apu_batch')
    assert all(any(a==0xD400+o and v&1 for a,v in m.sid_events) for o in (4,11,18))
    report=dict(prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest(),
                mountains=records,climb_frames=len(sequence),lives=3,
                readonly_guards=True,decimal_arithmetic=True,status='passed')
    out=BASE/'docs/verification'
    out.mkdir(parents=True,exist_ok=True)
    (out/'prg_regression.json').write_text(json.dumps(report,indent=2)+'\n')
    print('All PRG checks passed; code, source assets and extra code remained intact.')


if __name__=='__main__':
    main()


