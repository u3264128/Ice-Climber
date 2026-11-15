"""Compare the bonus-only play context contract with the complete API.

The public context API remains complete during scene setup/results. A bonus
tick writes only the 22 listed fields; its other per-player values may be
arbitrary and different. Omitted zero-page fields retain player zero's
values until the tick restores that player's mutable fields and lives.
"""
import hashlib
import json
import random

from plan_mountains import BASE, PlanningMachine, clone


NAMES = ('lives score_lo score_hi pxlo pxhi py prevpy curfloor onground vy '
         'face maxfloor hammer_t attack_t air_init fall_int fall_frac y_frac '
         'rise_int rise_frac move_dir walk_time walk_frac air_xfrac skid_t '
         'invul_t pleft pright flow_frac bonus_plat score_mil score_top').split()
# PLAYER_STATES offset of each name (offset 30, unused before, holds the
# score's millions digit).
OFFSETS = tuple(range(32))
NAME_AT = dict(zip(OFFSETS, NAMES))
WRITTEN = (3, 4, 5, 6, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19,
           20, 21, 22, 23, 24, 29)
LOADED = (0, *WRITTEN)


def values(machine):
    return bytes(machine.ram[machine.labels[name]] for name in NAMES)


def pick(data):
    return bytes(data[offset] for offset in OFFSETS)


def set_values(machine, data):
    for name, offset in zip(NAMES, OFFSETS):
        machine.ram[machine.labels[name]] = data[offset]


def general_dispatch(machine):
    # Reference executes the unchanged complete routines from this same PRG.
    # Patching only the two test clone entries avoids a second game build.
    for play, general in (('play_context_store', 'context_store'),
                          ('play_context_load', 'context_load')):
        start, target = machine.labels[play], machine.labels[general]
        machine.ram[start:start+3] = bytes((0x4C, target & 255, target >> 8))


def check_contract(base):
    rng = random.Random(0xC064)
    cases = 0
    for trial in range(256):
        contexts = rng.randbytes(64)
        for player in (0, 1):
            for scene in (1, 3):
                new, old = clone(base), clone(base)
                for m in (new, old):
                    m.ram[0x200:0x240] = contexts
                    m.ram[m.labels['player_index']] = player
                    m.ram[m.labels['state']] = scene
                selected = bytearray(contexts[player*32:(player+1)*32])
                for index in WRITTEN:
                    selected[index] = rng.randrange(256)
                for m in (new, old):
                    set_values(m, selected)
                original_y = old.y
                new.call('play_context_store')
                old.call('context_store')
                assert (old.a, old.x, old.y, old.c, old.z, old.n) == \
                    (selected[31], player*32, original_y, 0,
                     int(selected[31] == 0), int(bool(selected[31] & 128))), \
                    ('complete store register contract', trial, player, scene)
                assert new.ram[0x200:0x240] == old.ram[0x200:0x240], \
                    ('store', trial, player, scene)
                # A full normal load restores all 32 arbitrary bytes.
                # A bonus load restores only its documented live subset.
                before = rng.randbytes(32)
                set_values(new, before)
                set_values(old, before)
                original_y = old.y
                old.call('context_load')
                assert values(old) == pick(selected), ('complete load RAM', trial, player, scene)
                assert (old.a, old.x, old.y, old.c, old.z, old.n) == \
                    (selected[31], player*32, original_y, 0,
                     int(selected[31] == 0), int(bool(selected[31] & 128))), \
                    ('complete load register contract', trial, player, scene)
                new.call('play_context_load')
                expected = bytearray(before)
                for index in LOADED if scene == 3 else range(32):
                    expected[index] = selected[index]
                assert values(new) == pick(expected), ('load', trial, player, scene)
                cases += 1
        # Complete two-player save/load round trip, with different arbitrary
        # immutable values in both contexts and all mutable fields changed.
        new, old = clone(base), clone(base)
        for m in (new, old):
            m.ram[0x200:0x240] = contexts
            m.ram[m.labels['state']] = 3
            set_values(m, contexts[:32])
        for player in (0, 1):
            for m in (new, old):
                m.ram[m.labels['player_index']] = player
                if player:
                    m.call('play_context_load' if m is new else 'context_load')
            changes = {index: rng.randrange(256) for index in WRITTEN}
            for m in (new, old):
                for index, value in changes.items():
                    m.ram[m.labels[NAME_AT[index]]] = value
                m.call('play_context_store' if m is new else 'context_store')
        for m in (new, old):
            m.ram[m.labels['player_index']] = 0
            m.call('play_context_load' if m is new else 'context_load')
        assert new.ram[0x200:0x240] == old.ram[0x200:0x240], ('roundtrip RAM', trial)
        assert values(new) == values(old), ('roundtrip ZP', trial)
        cases += 1
    return cases


def check_ticks(base):
    rng = random.Random(0xB064)
    cases = 0
    labels = base.labels
    # All logical state below $0800 except the hardware stack; plus bonus
    # ledge/cache metadata and the actual video cache. Dispatch patches are
    # outside these ranges. This includes every player's immutable bytes.
    ranges = ((0, 0x100), (0x200, 0x800), (0xA000, 0xF000))
    for players in (1, 2):
        for mountain in range(1, 9):
            for camera in (0, 128, 220, 255, 256):
                new = clone(base)
                new.ram[labels['player_count']] = players
                new.ram[labels['mountain']] = mountain
                new.ram[0x200:0x240] = rng.randbytes(64)
                # Arbitrary score/invulnerability values are deliberately
                # retained, while controls/physics receive legal fixtures.
                new.ram[0x200] = 3
                new.ram[0x220] = 0 if camera == 128 else 2
                new.call('enter_bonus')
                new.ram[labels['bonus_camera']:labels['bonus_camera']+2] = camera.to_bytes(2, 'little')
                for player in range(players):
                    offset = 0x200+player*32
                    for field, value in ((3, 120+100*player), (4, 0), (5, 140+10*player),
                                         (6, 140+10*player), (8, 0), (12, 0), (13, 0),
                                         (14, 12), (15, 3), (16, 8), (17, 240),
                                         (18, 3), (19, 168), (20, 0), (21, 0),
                                         (24, 0)):
                        new.ram[offset+field] = value
                new.ram[labels['player_index']] = 0
                new.call('context_load')
                old = clone(new)
                general_dispatch(old)
                dispatch_bytes = {labels[name]+i for name in
                                  ('play_context_load', 'play_context_store') for i in range(3)}
                for tick in range(12):
                    for m in (new, old):
                        m.ram[labels['input_joy']:labels['input_joy']+2] = \
                            bytes((0xF6 if tick & 1 else 0xFB, 0xFA if tick & 1 else 0xF7))
                        m.ram[labels['input_fire']:labels['input_fire']+2] = \
                            bytes((int(tick % 5 == 0), int(tick % 7 == 0)))
                        m.call('game_tick')
                    for start, end in ranges:
                        differences = [(i, a, b) for i, (a, b) in
                                       enumerate(zip(new.ram[start:end], old.ram[start:end]), start)
                                       if a != b and i not in dispatch_bytes]
                        assert not differences, ('whole tick', players, mountain, camera,
                                                 tick, differences[:12])
                    cases += 1
                    if new.ram[labels['state']] != 3:
                        break
    return cases


def check_camera_shares(base):
    cases = 0
    for camera in (0, 120, 228):
        new = clone(base)
        r, labels = new.ram, new.labels
        r[labels['player_count']] = 2
        r[0x200], r[0x220] = 3, 2
        new.call('enter_bonus')
        r[labels['bonus_camera']:labels['bonus_camera']+2] = camera.to_bytes(2, 'little')
        r[labels['bonus_pan']] = 12     # an original $D8AF pan moves both climbers
        for player in (0, 1):
            for field, value in ((3, 120+100*player), (4, 0), (5, 100+10*player),
                                 (6, 100+10*player), (8, 0), (14, 12), (15, 0),
                                 (16, 8), (17, 240), (18, 3), (19, 168),
                                 (20, 0), (21, 0), (24, 0),
                                 (1, 17+14*player), (2, 34+14*player), (7, 0),
                                 (11, 3+4*player), (25, 5+8*player),
                                 (26, 12+30*player), (27, 19+31*player),
                                 (28, 33+35*player), (31, player)):
                r[0x200+player*32+field] = value
        r[labels['player_index']] = 0
        new.call('context_load')
        old = clone(new)
        general_dispatch(old)
        for tick in range(30):
            for m in (new, old):
                m.call('game_tick')
            assert new.ram[:0x100] == old.ram[:0x100], ('camera share ZP', camera, tick)
            assert new.ram[0x200:0x800] == old.ram[0x200:0x800], ('camera share RAM', camera, tick)
            cases += 1
            if r[labels['state']] != 3:
                break
        assert int.from_bytes(r[labels['bonus_camera']:labels['bonus_camera']+2], 'little') > camera
    return cases


def main():
    digest = hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest()
    base = PlanningMachine()
    contracts = check_contract(base)
    ticks = check_ticks(base)
    camera_shares = check_camera_shares(base)
    assert hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest() == digest
    report = dict(status='passed', prg_sha256=digest, arbitrary_context_cases=contracts,
                  whole_bonus_ticks=ticks+camera_shares, camera_share_ticks=camera_shares,
                  mutable_store_fields=21, live_load_fields=22,
                  players=[1, 2], original_bonus_variants=8)
    (BASE/'docs/verification/play_context.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS play context:', contracts, 'arbitrary-context cases;', ticks+camera_shares,
          'whole bonus ticks against unchanged complete context API', flush=True)


if __name__ == '__main__':
    main()
