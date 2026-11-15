#!/usr/bin/env python3
"""The sprite scheduler in real play against test_game's scheduler model.

Every time schedule_actors runs (normal play, pans, both climbers and the
bonus round), the logical sprites it is given go through schedule_model
(test_game.py: stable height order, the initial batch, VIC deadlines and
the overload priority). The back half must then hold exactly those raster
events, with each logical sprite's Y, X, pointer and colour, and the
$D010/$D01C/$D015 values after each event; the counts and the frame IRQ's
batch (pending_batch: line 0 and VIC sprite k implied, only its last event
stores $D010/$D01C/$D015) must agree too.
"""
import json
import random
import sys

from test_game import BASE, Machine, finish_opening, schedule_model


class Checked(Machine):
    def __init__(self):
        self.pending = None
        self.calls = self.multiplexed = self.dropped = self.converted = 0
        self.bad = []
        self.checking = False
        super().__init__()

    def logical(self):
        r, L = self.ram, self.labels
        names = ('LOG_X', 'LOG_XHI', 'LOG_Y', 'LOG_PTR', 'LOG_COL', 'LOG_MC', 'LOG_GROUP')
        return [dict(zip(('x', 'xhi', 'y', 'ptr', 'col', 'mc', 'g'), (r[L[n]+i] for n in names)))
                for i in range(r[L['logical_count']])]

    def expected(self, logs):
        events, msb, mc, ena = [], 0, 0, 0
        r, L = self.ram, self.labels
        plan = schedule_model(logs, players=r[L['player_sprites']], odd=r[L['frame']] & 1,
                              details=r[L['popo_details']+r[L['animidx']]])
        for line, slot, i in plan:
            l, bit = logs[i], 1 << slot
            msb = msb | bit if l['xhi'] else msb & ~bit
            mc = mc | bit if l['mc'] else mc & ~bit
            ena |= bit
            events.append((line, slot, l['y'], l['x'], msb, l['ptr'], l['col'], mc, ena))
        batch = 0
        while batch < len(events) and events[batch][:2] == (0, batch):
            batch += 1
        return len(events), batch, self.masked(events, batch)

    @staticmethod
    def masked(events, batch):
        # The batch's own line and slot are implied; only its last event
        # stores $D010/$D01C/$D015.
        out = list(events)
        for k in range(batch):
            line, slot, y, x, msb, ptr, col, mc, ena = out[k]
            out[k] = (0, k, y, x) + ((msb, ptr, col, mc, ena) if k == batch-1 else (None, ptr, col, None, None))
        return out

    def written(self, base):
        r, L = self.ram, self.labels
        count = r[L['pending_count']]
        arrays = ('EVENT_LINE', 'EVENT_SLOT', 'EVENT_Y', 'EVENT_X', 'EVENT_MSB',
                  'EVENT_PTR', 'EVENT_COL', 'EVENT_MC', 'EVENT_ENA')
        events = [tuple(r[L[a]+base+k] for a in arrays) for k in range(count)]
        batch = r[L['pending_batch']]
        assert r[L['scheduled_count']] == count, (r[L['scheduled_count']], count)
        return count, batch, self.masked(events, batch)

    def step(self):
        L = self.labels
        if self.pending is None and self.checking and self.pc == L['schedule_actors']:
            sp = self.sp
            ret = (self.ram[0x100+((sp+1) & 255)] | self.ram[0x100+((sp+2) & 255)] << 8)+1
            logs = self.logical()
            self.pending = (ret, self.ram[L['back_base']], logs, self.expected(logs))
        elif self.pending is not None and self.pc == self.pending[0]:
            ret, base, logs, want = self.pending
            got = self.written(base)
            self.calls += 1
            self.multiplexed += len(logs) >= 9
            converted = bool(logs) and logs[0]['col'] == logs[0]['y'] == 0xFF   # Popo in two layers
            self.converted += converted
            self.dropped += want[0] < len(logs) - converted
            if got != want and len(self.bad) < 3:
                self.bad.append((len(logs), [(l['y'], l['g']) for l in logs], got, want))
            self.pending = None
        super().step()


def route_case(mountain, extra):
    routes = {r['mountain']: r for r in json.loads((BASE/'tools/fixtures/mountain_routes.json').read_text())['routes']}
    m = Checked()
    L = m.labels
    m.ram[L['selected_mountain']] = mountain
    m.frame(0xEF)
    finish_opening(m)
    m.checking = True
    rnd = random.Random(mountain)
    for joy in routes[mountain]['inputs']:
        m.frame(joy)
    for _ in range(extra):                 # the bonus round after the summit
        m.frame(rnd.choice((0xFF, 0xEF, 0xFB, 0xF7, 0xEB, 0xE7)))
    return m


def two_player_case(mountain, frames):
    m = Checked()
    L = m.labels
    m.frame(0xFD)
    m.frame()
    m.ram[L['selected_mountain']] = mountain
    m.frame(0xEF)
    finish_opening(m)
    m.checking = True
    rnd = random.Random(mountain)
    keys = (0xFF, 0xEF, 0xFB, 0xF7, 0xEB, 0xE7, 0xFE)
    for _ in range(frames):
        m.frame(rnd.choice(keys), rnd.choice(keys))
    return m


def main():
    cases = [('route', 31, 500), ('route', 22, 0), ('route', 1, 700)]
    cases += [('2p', 3, 1500), ('2p', 14, 1500)]
    if len(sys.argv) > 1:
        cases = [tuple(int(v) if v.isdigit() else v for v in a.split(':')) for a in sys.argv[1:]]
    total = multiplexed = dropped = converted = 0
    for kind, mountain, frames in cases:
        m = route_case(mountain, frames) if kind == 'route' else two_player_case(mountain, frames)
        assert not m.bad, (kind, mountain, m.bad)
        assert m.calls > 100, (kind, mountain, m.calls)
        total += m.calls
        multiplexed += m.multiplexed
        dropped += m.dropped
        converted += m.converted
        print(f'{kind} {mountain}: {m.calls} schedules ({m.multiplexed} multiplexed, {m.dropped} overloaded, '
              f'{m.converted} with Popo turned into two layers) equal the model', flush=True)
    assert multiplexed > 1000 and dropped + converted > 0, (multiplexed, dropped, converted)
    print(f'PASS scheduler: {total} schedules of real play, {multiplexed} with nine or more sprites '
          f'({dropped} overloaded, {converted} with Popo turned into two layers), '
          f'equal test_game\'s scheduler model')


if __name__ == '__main__':
    main()
