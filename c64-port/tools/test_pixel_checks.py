"""Check camera-shift comparisons with overlapping and clipped sprites."""
from pixel_checks import band_comparison, sprite_mask


def main():
    width, height = 80, 100
    background = [bytes((row * 7 + column * 3) % 16 for column in range(width))
                  for row in range(height)]
    cases = 0
    for delta in (-4, 0, 1, 2, 4):
        previous = [bytearray(row) for row in background]
        current = [bytearray(background[(row - delta) % height]) for row in range(height)]
        old_events = [(8, 28), (70, 90)]
        events = [(18, 37), (72, 93)]
        old_mask = sprite_mask(previous, old_events, 0)
        mask = sprite_mask(current, events, 0)
        # Different sprite colours and positions must not resemble tearing.
        for pixels, covered, colour in ((previous, old_mask, 2), (current, mask, 5)):
            for row in range(height):
                for column in range(width):
                    if covered[row][column]:
                        pixels[row][column] = colour
        for band in (24, 40, 56, 72):
            mismatch = band_comparison(current, previous, mask, old_mask, band, delta, 0, width)
            assert mismatch(delta) == 0, (delta, band)
            assert mismatch(delta + 1) > 0, (delta, band, 'wrong shift accepted')
            cases += 1
        # One unmasked terrain pixel must still be counted.
        current[64][60] ^= 1
        mismatch = band_comparison(current, previous, mask, old_mask, 64, delta, 0, width)
        assert mismatch(delta) == 1, delta
    clipped = sprite_mask(background, [(78, 94)], 0)
    assert sum(map(sum, clipped)) == 21  # Three columns, seven visible rows.
    outside = sprite_mask(background, [(100, 120), (-30, -40)], 0)
    assert not any(map(any, outside))
    print(f'PASS pixel comparisons: {cases} shifted bands, sprite masks, terrain edits, and clipping')


if __name__ == '__main__':
    main()
