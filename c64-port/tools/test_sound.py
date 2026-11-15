#!/usr/bin/env python3
"""The sound against the original engine and the 2A03.

1. Engine: the original $F91E runs in the NES reference and the
   transplanted sound_engine in the C64 build, tick by tick, with the same
   music and sound effect requests (every song to its end or loop, the
   pause jingles, random effects on all three channels). After every tick
   the engine RAM ($F0-$FF, $0700-$0712) must be equal, every APU register
   must hold the value the original wrote last, and the C64 must have
   marked exactly the starting writes ($4001/$4005/$4003/$4007/$400B/$400F)
   the original made.
2. APU: the original's register writes drive an independent model of the
   2A03 parts the engine uses (envelopes, sweeps with their muting, length
   and linear counters, the frame counter reset by $F91E's $4017 write).
   The C64 leaves out the length counters; with them in the model, this
   part also shows that they never cut a sound of the engine. At
   each tick's SID update the C64's SID registers must show what the model
   says: per voice gate, waveform, sustain level (= NES volume), frequency
   (K/divider within 4 cents) and pulse width; a louder or new sound must
   start the voice again.
3. Random APU writes (all registers, all sweep and envelope forms) against
   the model without length counters.
4. Pacing: the engine runs six ticks in five frames; sound_idle brings
   the APU and the SID up to date in the next frame's spare time.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_game import Machine
from test_original_physics import Reference
from transplant_sound import ZERO_PAGE

LENGTHS = [10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
           12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30]
NOISE = [4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068]
K = 1904811
DUTY_PW = (0x02, 0x04, 0x08, 0x0C)
EVENTS = (1, 3, 5, 7, 0x0B, 0x0F)


class Original(Reference):
    """The NES CPU; APU register writes are logged per tick."""
    def __init__(self):
        super().__init__()
        self.apu = []

    def write(self, a, v):
        if 0x4000 <= a <= 0x4017:
            self.apu.append((a, v & 0xFF))
        super().write(a, v)


class Envelope:
    def __init__(self):
        self.start, self.div, self.decay = False, 0, 0

    def quarter(self, reg):
        if self.start:
            self.start, self.decay, self.div = False, 15, reg & 15
        elif self.div == 0:
            self.div = reg & 15
            if self.decay:
                self.decay -= 1
            elif reg & 0x20:
                self.decay = 15
        else:
            self.div -= 1

    def volume(self, reg):
        return reg & 15 if reg & 0x10 else self.decay


class Pulse:
    def __init__(self, one):
        self.one = one
        self.r0 = self.r1 = self.period = self.length = 0
        self.env = Envelope()
        self.sw_div, self.sw_reload = 0, False

    def target(self):
        change = self.period >> (self.r1 & 7)
        if self.r1 & 8:
            return self.period - change - (1 if self.one else 0)
        return self.period + change

    def muted(self):
        return self.period < 8 or (not self.r1 & 8 and self.target() > 0x7FF)

    def half(self):
        if self.length and not self.r0 & 0x20:
            self.length -= 1
        if self.sw_div == 0 and self.r1 & 0x80 and self.r1 & 7 and not self.muted():
            self.period = self.target()
        if self.sw_div == 0 or self.sw_reload:
            self.sw_div, self.sw_reload = (self.r1 >> 4) & 7, False
        else:
            self.sw_div -= 1

    def volume(self):
        if not self.length or self.muted():
            return 0
        return self.env.volume(self.r0)


class APU:
    def __init__(self, lengths=True):
        self.p = [Pulse(True), Pulse(False)]
        self.tri_r8 = self.tri_period = self.tri_length = self.linear = 0
        self.tri_reload = False
        self.n_rc = self.n_re = self.n_length = 0
        self.n_env = Envelope()
        self.enable = 0x0F
        self.lengths = lengths
        if not lengths:                 # always running
            self.p[0].length = self.p[1].length = self.tri_length = self.n_length = 1

    def write(self, a, v):
        r = a - 0x4000
        if r < 8:
            p = self.p[r >> 2]
            k = r & 3
            if k == 0:
                p.r0 = v
            elif k == 1:
                p.r1, p.sw_reload = v, True
            elif k == 2:
                p.period = p.period & 0x700 | v
            else:
                p.period = p.period & 0xFF | (v & 7) << 8
                if self.enable >> (r >> 2) & 1:
                    p.length = LENGTHS[v >> 3]
                p.env.start = True
        elif r == 8:
            self.tri_r8 = v
        elif r == 0x0A:
            self.tri_period = self.tri_period & 0x700 | v
        elif r == 0x0B:
            self.tri_period = self.tri_period & 0xFF | (v & 7) << 8
            if self.enable & 4:
                self.tri_length = LENGTHS[v >> 3]
            self.tri_reload = True
        elif r == 0x0C:
            self.n_rc = v
        elif r == 0x0E:
            self.n_re = v
        elif r == 0x0F:
            if self.enable & 8:
                self.n_length = LENGTHS[v >> 3]
            self.n_env.start = True

    def quarter(self):
        for p in self.p:
            p.env.quarter(p.r0)
        self.n_env.quarter(self.n_rc)
        if self.tri_reload:
            self.linear = self.tri_r8 & 0x7F
        elif self.linear:
            self.linear -= 1
        if not self.tri_r8 & 0x80:
            self.tri_reload = False

    def half(self):
        for p in self.p:
            p.half()
            if not self.lengths:
                p.length = 1
        if not self.lengths:
            return
        if self.tri_length and not self.tri_r8 & 0x80:
            self.tri_length -= 1
        if self.n_length and not self.n_rc & 0x20:
            self.n_length -= 1


def sid_freq(x):
    """The C64's SND_K/x (freq_of): exact to a few cents."""
    return min(0xFFFF, round(K/x))


class Voices:
    """The C64's voice allocation and the SID state it should produce."""
    def __init__(self):
        self.noise_voice = 0
        self.state = {0: None, 7: None, 14: None}      # (wave, volume)

    def expect(self, apu):
        vols = [apu.p[0].volume(), apu.p[1].volume()]
        tri = 15 if apu.tri_length and apu.linear else 0
        noise = apu.n_env.volume(apu.n_rc) if apu.n_length else 0
        if not noise:
            self.noise_voice = 0
        elif not self.noise_voice:
            self.noise_voice = 14 if vols[0] else 7
        out = {}
        def pulse(p, v):
            return (0x40, v, sid_freq(p.period+1), DUTY_PW[p.r0 >> 6]) if v else None
        noise_sound = (0x80, noise, [0xFFFF]*3 + [round(K/n) for n in NOISE[3:]], None)
        out[0] = pulse(apu.p[1], vols[1])
        if self.noise_voice == 7:
            out[7] = (0x80, noise, noise_sound[2][apu.n_re & 15], None)
        else:
            out[7] = pulse(apu.p[0], vols[0])
        if self.noise_voice == 14:
            out[14] = (0x80, noise, noise_sound[2][apu.n_re & 15], None)
        else:
            out[14] = (0x10, 15, sid_freq(2*(apu.tri_period+1)), None) if tri else None
        restarts = {}
        for v, sound in out.items():
            before = self.state[v]
            restarts[v] = bool(sound) and (before is None or before[0] != sound[0] or sound[1] > before[1])
            self.state[v] = (sound[0], sound[1]) if sound else None
        return out, restarts


def apu_update(m, ticks=1):
    """The APU and SID update for the engine ticks since the last one."""
    r, L = m.ram, m.labels
    r[L['snd_debt']], r[L['snd_hurry']] = ticks, 0
    m.call('apu_batch')


def sound_tick(m):
    m.call('sound_engine')
    apu_update(m)


def c64_machine():
    m = Machine()
    r, L = m.ram, m.labels
    # the boot state of the sound (sound_init ran at boot): all zero
    assert not any(r[L['snd_vars']:L['snd_vars_end']]) and r[0xD418] == 0x0F
    return m


def requests(rng, tick, plan):
    """(music, sfx1, sfx2, sfx3) for this tick."""
    music = plan.get(tick, 0)
    pick = lambda bits: rng.choice(bits) if rng.random() < 0.02 else 0
    return music, pick((1, 2, 4)), pick((1, 2, 4, 8, 0x10)), pick((1, 2, 4, 8))


def run(ticks, plan, seed, check_apu=True):
    rng = random.Random(seed)
    nes = Original()
    s = nes.ram
    m = c64_machine()
    r, L = m.ram, m.labels
    zp = {nes_a: c64_a for nes_a, c64_a in ZERO_PAGE.items()}
    apu, voices = APU(), Voices()
    last = [0]*16
    stats = dict(writes=0, restarts=0, notes=set(), noise2=0, noise3=0)
    for tick in range(ticks):
        music, f1, f2, f3 = requests(rng, tick, plan)
        s[0xFB], s[0xFC], s[0xFE], s[0xFF] = music, f1, f2, f3
        r[zp[0xFB]], r[zp[0xFC]], r[zp[0xFE]], r[zp[0xFF]] = music, f1, f2, f3
        nes.apu = []
        nes.call(0xF91E)
        writes = [(a, v) for a, v in nes.apu if a not in (0x4011, 0x4017)]
        stats['writes'] += len(writes)
        # 1. the engine
        if not check_apu:
            for k in range(16):
                r[L['snd_apu']+k] = last[k]
                r[L['snd_apu_w']+k] = 0
            m.call('sound_engine')
            for a, v in writes:
                last[a-0x4000] = v
            marked = {a-0x4000 for a, v in writes if a-0x4000 in EVENTS}
            for k in range(16):
                assert r[L['snd_apu']+k] == last[k], (tick, hex(k), r[L['snd_apu']+k], last[k])
                assert bool(r[L['snd_apu_w']+k]) == (k in marked), (tick, hex(k))
        if check_apu:
            del m.sid_events[:]
            sound_tick(m)
            for a, v in writes:
                apu.write(a, v)
            apu.quarter()
            want, restarts = voices.expect(apu)
            for _ in range(3):
                apu.quarter()
            apu.half()
            apu.half()
            for voice, sound in want.items():
                sid = lambda k: r[0xD400+voice+k]
                ctrl = sid(4)
                if sound is None:
                    assert not ctrl & 1, ('voice should be off', tick, voice, hex(ctrl))
                    continue
                wave, volume, freq, pw = sound
                got = (ctrl & 0xF1, sid(6) >> 4)
                assert got == (wave | 1, volume), ('voice', tick, voice, [hex(g) for g in got], hex(wave), volume)
                f = sid(0) | sid(1) << 8
                assert abs(f-freq) <= max(1, freq*0.0025), ('frequency', tick, voice, f, freq)
                if pw is not None:
                    assert sid(3) == pw, ('pulse width', tick, voice, sid(3), pw)
                assert sid(5) == 0 and sid(6) & 15 == 0
                started = any(v & 1 for a, v in m.sid_events if a == 0xD404+voice)
                assert started == restarts[voice], ('voice start', tick, voice, started)
                stats['restarts'] += started
                if wave == 0x40 or wave == 0x10:
                    stats['notes'].add((voice, f))
                stats['noise2'] += voice == 7 and wave == 0x80
                stats['noise3'] += voice == 14 and wave == 0x80
        # engine RAM after the tick
        for nes_a, c64_a in zp.items():
            if nes_a in (0xF6, 0xF7):
                continue
            assert s[nes_a] == r[c64_a], ('engine zero page', tick, hex(nes_a), s[nes_a], r[c64_a])
        # the song data pointer, relocated with the $FD22 tables
        pointer = r[zp[0xF6]] | r[zp[0xF7]] << 8
        if pointer or s[0xF6] | s[0xF7]:
            assert pointer - L['snd_rom_FD22'] + 0xFD22 == s[0xF6] | s[0xF7] << 8, ('song pointer', tick)
        for k in range(0x13):
            if k == 0x11:
                continue                        # $0711: the DAC ramp, not emulated
            assert s[0x700+k] == r[L['snd_ram']+k], ('engine RAM', tick, hex(0x700+k), s[0x700+k], r[L['snd_ram']+k])
    return stats


def run_random_writes(ticks, seed):
    """Random APU register writes straight into the APU update: every register,
    all sweep forms, envelopes and both noise voices, beyond what the engine
    itself writes. Like the C64, the model leaves out what the engine never
    uses: length counters, the envelope loop and the triangle's control
    bit (part 2 shows with the full model that the engine's sound is the
    same)."""
    rng = random.Random(seed)
    m = c64_machine()
    r, L = m.ram, m.labels
    apu, voices = APU(lengths=False), Voices()
    swept = starts = 0
    for tick in range(ticks):
        writes = []
        for _ in range(rng.choice((0, 0, 1, 2, 4))):
            reg = rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 8, 0x0A, 0x0B, 0x0C, 0x0E, 0x0F))
            value = rng.randrange(256)
            if reg in (3, 7, 0x0B, 0x0F) and rng.random() < 0.7:
                value = value & 7 | rng.choice((0, 2, 3, 5, 7, 9)) << 3      # short lengths too
            if reg in (2, 6, 0x0A) and rng.random() < 0.8:
                value |= 0x20
            if reg in (0, 4, 0x0C):
                value &= ~0x20          # the engine uses no envelope loop
            if reg == 8:
                value &= 0x7F           # nor the triangle's control bit
            writes.append((0x4000+reg, value))
        # the C64 side: the shadow registers and their write marks, as the
        # transplanted engine's stores leave them (the period registers are
        # the live ones: $4002 replaces the low byte, $4003 the high bits)
        for a, v in writes:
            k = a-0x4000
            r[L['snd_apu']+k] = v
            if k in EVENTS:
                r[L['snd_apu_w']+k] = (r[L['snd_apu_w']+k]+1) & 255
        del m.sid_events[:]
        apu_update(m)
        for a, v in writes:
            apu.write(a, v)
        before = [apu.p[0].period, apu.p[1].period]
        apu.quarter()
        want, restarts = voices.expect(apu)
        for _ in range(3):
            apu.quarter()
        apu.half()
        apu.half()
        swept += sum(1 for k in (0, 1) if before[k] != apu.p[k].period)
        assert [r[L['snd_apu']+2] | (r[L['snd_apu']+3] & 7) << 8,
                r[L['snd_apu']+6] | (r[L['snd_apu']+7] & 7) << 8] == [apu.p[0].period, apu.p[1].period], \
            ('swept periods', tick)
        for voice, sound in want.items():
            sid = lambda k: r[0xD400+voice+k]
            ctrl = sid(4)
            if sound is None:
                assert not ctrl & 1, ('voice should be off', tick, voice, hex(ctrl))
                continue
            wave, volume, freq, pw = sound
            assert (ctrl & 0xF1, sid(6) >> 4) == (wave | 1, volume), ('voice', tick, voice)
            f = sid(0) | sid(1) << 8
            assert abs(f-freq) <= max(1, freq*0.0025), ('frequency', tick, voice, f, freq)
            if pw is not None:
                assert sid(3) == pw, ('pulse width', tick, voice)
            started = any(v & 1 for a, v in m.sid_events if a == 0xD404+voice)
            assert started == restarts[voice], ('voice start', tick, voice, started)
            starts += started
    return swept, starts


def run_batches(cases, seed):
    """An update for several ticks (spare time came late) equals one per
    tick when only the first tick wrote: the same envelopes, linear counter,
    sweeps and periods, and the same SID registers after it."""
    rng = random.Random(seed)
    m = c64_machine()
    r, L = m.ram, m.labels
    zp = {'snd_div': 0x80, 'snd_decay': 0x84, 'snd_vol': 0x98}
    for case in range(cases):
        for _ in range(rng.randrange(1, 6)):
            reg = rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 8, 0x0A, 0x0B, 0x0C, 0x0E, 0x0F))
            value = rng.randrange(256)
            if reg in (0, 4, 0x0C):
                value &= ~0x20
            if reg == 8:
                value &= 0x7F
            r[L['snd_apu']+reg] = value
            if reg in EVENTS:
                r[L['snd_apu_w']+reg] += 1
        ticks = rng.randrange(2, 7)
        saved = bytearray(r), bytearray(m.under_io)
        def state():
            regs = bytes(r[0xD400:0xD415])
            core = bytes(r[L['snd_apu']:L['snd_apu']+16]) + bytes(r[L['snd_start']:L['snd_start']+4])
            core += bytes(r[L['snd_sw_div']:L['snd_sw_div']+2]) + bytes(r[L['snd_sw_reload']:L['snd_sw_reload']+2])
            core += bytes([r[L['snd_linear']]]) + bytes(r[0x80:0x88])
            return regs, core, r[L['snd_noise_voice']]
        apu_update(m, ticks)
        batched = state()
        r[:], m.under_io[:] = saved
        for _ in range(ticks):
            apu_update(m)
        single = state()
        assert batched[1] == single[1], ('APU state', case, ticks)
        # the SID: gate and waveform; frequency, pulse width and sustain of
        # a voice that plays (an off voice's are set again when it starts)
        # (the noise keeps the voice it started on: one tick at a time it
        # may have started earlier, on the other voice)
        same_noise = batched[2] == single[2]
        for voice in ((0, 7, 14) if same_noise else (0,)):
            gate = single[0][voice+4] & 1
            assert batched[0][voice+4] & (0xF1 if gate else 1) == single[0][voice+4] & (0xF1 if gate else 1),                 ('SID control', case, voice, ticks)
            if gate:
                for k in (0, 1, 3, 6):
                    assert batched[0][voice+k] == single[0][voice+k], ('SID', case, ticks, voice, k)
    return cases


def plan_songs():
    """Every song from a clean start, the logo's $04/$08 loop, pauses."""
    plan, tick = {}, 0
    for song, length in ((0x04, 4000), (0x02, 2600), (0x01, 900), (0x10, 700),
                         (0x02, 300), (0x20, 120), (0x40, 600), (0x80, 60), (0x04, 300), (0x80, 100)):
        plan[tick] = song
        tick += length
    return plan, tick


def check_pacing():
    m = c64_machine()
    L = m.labels
    tick = L['sound_engine']
    count = [0]
    original_step = m.step
    def step():
        if m.pc == tick:
            count[0] += 1
        original_step()
    m.step = step
    for _ in range(50):
        m.frame()
    # the APU follows in the next frame's wait_frame (sound_idle)
    assert m.ram[L['snd_debt']] <= 2, m.ram[L['snd_debt']]
    return count[0]


def main():
    plan, ticks = plan_songs()
    engine = run(ticks, plan, 1, check_apu=False)
    print(f'PASS engine: {ticks} ticks, {engine["writes"]} APU writes equal the original\'s', flush=True)
    stats = run(ticks, plan, 2)
    assert stats['restarts'] > 500 and len(stats['notes']) > 60 and stats['noise2'] and stats['noise3'], stats
    print(f'PASS APU on the SID: {ticks} ticks, {stats["restarts"]} voice starts, {len(stats["notes"])} '
          f'pitches, noise on voice 2 ({stats["noise2"]} ticks) and voice 3 ({stats["noise3"]} ticks)', flush=True)
    batches = run_batches(3000, 4)
    print(f'PASS batched APU updates: {batches} updates of 2-6 ticks equal tick by tick', flush=True)
    swept, starts = run_random_writes(6000, 3)
    assert swept > 200 and starts > 500, (swept, starts)
    print(f'PASS APU, random register writes: 6000 ticks, {swept} sweep steps, '
          f'{starts} voice starts', flush=True)
    ticks50 = check_pacing()
    assert ticks50 == 60, ticks50
    print('PASS pacing: 60 engine ticks in 50 PAL frames, the APU in the spare time after')


if __name__ == '__main__':
    main()
