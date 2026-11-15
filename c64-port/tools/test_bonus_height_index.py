"""Check indexed immutable bonus ledges against the NES-validated generic query.

All eight original record lists are immutable after their source decoder runs.
Controlled arbitrary-height fixtures deliberately retain the generic path.
"""
import hashlib
import json

from plan_mountains import BASE, PlanningMachine


def query(m, camera, y, x, mode, indexed, cloud_index_count=None):
    r, labels = m.ram, m.labels
    r[labels['bonus_camera']:labels['bonus_camera']+2] = camera.to_bytes(2, 'little')
    r[labels['py']] = y
    r[labels['pxlo']:labels['pxlo']+2] = (x+52).to_bytes(2, 'little')
    r[labels['bonus_support_mode']] = mode
    r[labels['bonus_plat']] = 255
    r[labels['fall_int']], r[labels['fall_frac']] = 2, 99
    r[labels['bonus_index_count']] = r[labels['bonus_platform_count']] if indexed else 255
    count = r[labels['bonus_cloud_count']] if cloud_index_count is None else cloud_index_count
    disabled = 254 if r[labels['bonus_cloud_count']] == 255 else 255
    r[labels['BONUS_CLOUD_INDEX_COUNT']] = count if indexed else disabled
    m.call('bonus_find_support')
    support = r[labels['bonus_support']]
    return (support, r[labels['bonus_plat']], r[labels['bonus_check_y']] if support else None,
            int.from_bytes(r[labels['pxlo']:labels['pxlo']+2], 'little'),
            r[labels['fall_int']], r[labels['fall_frac']])


def main():
    m = PlanningMachine()
    r, labels = m.ram, m.labels
    count = 0
    counts = []
    for mountain in range(1, 9):
        r[labels['mountain']] = mountain
        m.call('enter_bonus')
        platforms = r[labels['bonus_platform_count']]
        counts.append(platforms)
        assert r[labels['bonus_index_count']] == platforms
        assert r[labels['BONUS_CLOUD_INDEX_COUNT']] == r[labels['bonus_cloud_count']]
        for cloud in range(r[labels['bonus_cloud_count']]):
            r[labels['bonus_cloud_motion']+cloud] = 1 if cloud & 1 else 255
        for camera in (0, 128, 255, 256):
            for y in (*range(0, 32, 3), *range(32, 256, 16), 254, 255):
                for mode in range(3):
                    for x in (0, 7, 8, 40, 64, 120, 216, 248, 255):
                        expected = query(m, camera, y, x, mode, False)
                        actual = query(m, camera, y, x, mode, True)
                        assert actual == expected, (mountain, camera, y, x, mode, actual, expected)
                        count += 1
    # Same low height on different pages, plus two overlapping records:
    # retain original priority and the full high-byte/window validation.
    r[labels['bonus_platform_count']], r[labels['bonus_cloud_count']] = 3, 0
    for i, (height, left, right) in enumerate(((96, 5, 12), (352, 6, 16), (96, 10, 20))):
        r[labels['BONUS_LEDGE_HLO']+i] = height & 255
        r[labels['BONUS_LEDGE_HHI']+i] = height >> 8
        r[labels['BONUS_LEDGE_L']+i], r[labels['BONUS_LEDGE_R']+i] = left, right
    m.call('bonus_height_index')
    assert r[labels['bonus_index_count']] == 3
    for camera, x, expected_slot in ((0, 56, 0), (0, 100, 2), (256, 40, 1)):
        actual = query(m, camera, 120, x, 0, True)
        assert actual[0:3] == (1, expected_slot, 120), (camera, x, actual)
    # A negative height delta can still be the source's valid8-bit Y wrap.
    r[labels['bonus_platform_count']] = 1
    r[labels['BONUS_LEDGE_HLO']], r[labels['BONUS_LEDGE_HHI']] = 216, 0
    r[labels['BONUS_LEDGE_L']], r[labels['BONUS_LEDGE_R']] = 5, 20
    m.call('bonus_height_index')
    assert r[labels['bonus_index_count']] == 1
    assert query(m, 255, 0, 12, 1, True)[0:3] == (1, 0, 255)
    # The public generic helper also accepts unaligned fixture heights.
    r[labels['BONUS_LEDGE_HLO']], r[labels['BONUS_LEDGE_HHI']] = 217, 0
    r[labels['BONUS_LEDGE_L']], r[labels['BONUS_LEDGE_R']] = 5, 20
    m.call('bonus_height_index')
    assert r[labels['bonus_index_count']] == 255
    r[labels['bonus_camera']:labels['bonus_camera']+2] = (256).to_bytes(2, 'little')
    r[labels['py']], r[labels['bonus_support_mode']] = 0, 1
    r[labels['pxlo']:labels['pxlo']+2] = (64).to_bytes(2, 'little')
    m.call('bonus_find_support')
    assert (r[labels['bonus_support']], r[labels['bonus_check_y']]) == (1, 255)

    # Cloud buckets must retain both height bytes and the source's wrapped
    # screen-Y window. Duplicate low-byte buckets (even on different pages)
    # and unaligned heights deliberately fall back to original record order.
    cloud_cases = 0
    fixtures = (
        ([(96, 80, 48, 1), (200, 120, 32, 255)], 2),
        ([(352, 80, 48, 255)], 1),
        ([(216, 80, 48, 1)], 1),
        ([(217, 80, 48, 1)], 255),
        ([(96, 80, 48, 1), (352, 88, 48, 255), (96, 96, 32, 0)], 255),
        ([], 0),
    )
    r[labels['bonus_platform_count']] = 0
    for records, expected_flag in fixtures:
        r[labels['bonus_cloud_count']] = len(records)
        for slot, (height, x, width, motion) in enumerate(records):
            for name, value in (('bonus_cloud_hlo', height & 255),
                                ('bonus_cloud_hhi', height >> 8), ('bonus_cloud_x', x),
                                ('bonus_cloud_width', width), ('bonus_cloud_motion', motion)):
                r[labels[name]+slot] = value
        m.call('bonus_cloud_height_index')
        built = r[labels['BONUS_CLOUD_INDEX_COUNT']]
        assert built == expected_flag, ('cloud index builder', records, built, expected_flag)
        for camera in (0, 255, 256):
            for y in (0, 120, 148, 255):
                for x in (0, 7, 80, 88, 120, 255):
                    for mode in range(3):
                        expected = query(m, camera, y, x, mode, False)
                        actual = query(m, camera, y, x, mode, True, built)
                        assert actual == expected, ('cloud fallback/page/wrap', records,
                                                    camera, y, x, mode, actual, expected)
                        cloud_cases += 1
        if records and records[0][0] in (216, 217):
            camera = 255 if records[0][0] == 216 else 256
            assert query(m, camera, 0, 88, 1, True, built)[0:3] == (1, 24, 255)
    # Rejected nonempty counts, including the $FF sentinel itself, remain
    # linear. The second record must be tried after the first fails X.
    for slot, x in enumerate((0, 80)):
        for name, value in (('bonus_cloud_hlo', 96), ('bonus_cloud_hhi', 0),
                            ('bonus_cloud_x', x), ('bonus_cloud_width', 32 if not slot else 48),
                            ('bonus_cloud_motion', 0)):
            r[labels[name]+slot] = value
    for oversized in (9, 255):
        r[labels['bonus_cloud_count']] = oversized
        m.call('bonus_cloud_height_index')
        assert r[labels['BONUS_CLOUD_INDEX_COUNT']] == 255
        expected = query(m, 0, 120, 88, 1, False)
        actual = query(m, 0, 120, 88, 1, True, 255)
        assert actual == expected and actual[0:2] == (1, 25), ('rejected cloud count', oversized)
        cloud_cases += 1
    report = dict(status='passed', comparisons=count, variant_platform_counts=counts,
                  duplicate_and_page_priority=True, arbitrary_height_fallback=True,
                  wrapped_surface_y_255=True,
                  cloud_page_wrap_fallback_cases=cloud_cases,
                  cloud_oversized_count_fallback=True,
                  prg_sha256=hashlib.sha256((BASE/'c64/build/iceclimber_game.prg').read_bytes()).hexdigest())
    (BASE/'docs/verification/bonus_height_index.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS indexed/generic bonus queries:', count, 'original-list cases; page/priority/wrap/fallback', flush=True)


if __name__ == '__main__':
    main()
