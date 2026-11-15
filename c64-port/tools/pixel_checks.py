"""Pixel and sprite-mask comparisons using the Python standard library."""


def sprite_mask(pixels, events, x_offset):
    height, width = len(pixels), len(pixels[0])
    mask = [bytearray(width) for _ in range(height)]
    for event in events:
        x, y = event[0] + x_offset, event[1]
        left, right = max(0, x - 1), min(width, x + 25)
        if left >= right:
            continue
        for row in range(max(0, y - 1), min(height, y + 22)):
            mask[row][left:right] = b'\x01' * (right - left)
    return mask


def band_comparison(pixels, previous, mask, previous_mask, band, delta, left, right):
    """Compare shifts of one 8-line band, excluding current and moved sprites."""
    height = len(pixels)
    rows = []
    for row in range(band, band + 8):
        old_mask = previous_mask[(row - delta) % height]
        columns = [column for column in range(left, right)
                   if not (mask[row][column] or old_mask[column])]
        rows.append((row, columns, bytes(pixels[row][column] for column in columns)))

    def mismatch(shift):
        return sum(sum(a != b for a, b in zip(now, bytes(previous[row - shift][column]
                                                       for column in columns)))
                   for row, columns, now in rows)

    return mismatch
