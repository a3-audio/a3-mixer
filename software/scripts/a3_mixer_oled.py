# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Send an SSD1306 only the part of the picture that changed.

luma's ssd1306.display() sends the whole frame on every draw -- 1 KB, about
0.1 s on the desk's 100 kHz bus -- and packs it pixel by pixel in Python. The
controller takes a column and page window (COLUMNADDR, PAGEADDR) and then only
that window's bytes, so one stem square costs a tenth of the frame. Each
changed area gets its own window (changed_windows).

The SSD1306's memory is in pages of eight rows: one byte per column and page,
bit 0 the page's top row. Pure apart from PIL, which the desk has anyway.
"""

import weakref

from PIL import Image, ImageChops

PAGE = 8

# Bit 0 must be the page's top row; PIL packs the leftmost pixel into bit 7.
_REVERSED = bytes(int("{:08b}".format(value)[::-1], 2) for value in range(256))


def page_bytes(image, x0, x1, page0, page1):
    """The controller's bytes for columns x0..x1 and pages page0..page1."""
    out = bytearray()
    for page in range(page0, page1 + 1):
        strip = image.crop((x0, page * PAGE, x1 + 1, (page + 1) * PAGE))
        # Transposed, each column becomes one 8-pixel row: one byte.
        out += strip.transpose(Image.Transpose.TRANSPOSE).tobytes().translate(_REVERSED)
    return list(out)


MERGE_GAP = 8   # columns: closer changes share a window, which costs ~7 bytes

#: More runs than this in one band go as one: a scrolling wave changes
#: scattered columns in every band, and each window is a transaction of its
#: own behind the multiplexer -- 11 of them made a draw 53 ms (2026-10-02).
MAX_RUNS_PER_BAND = 2


def changed_windows(before, after):
    """[(x0, x1, page0, page1), ...]: one window per changed area.

    Per 8-row band, the runs of changed columns -- runs closer than MERGE_GAP
    share one -- and a run directly below one with the same columns extends
    it. One rectangle around everything was most of the display again
    whenever a turn emptied one square and filled another far away."""
    diff = ImageChops.logical_xor(before, after)
    if diff.getbbox() is None:
        return []
    windows = []
    for page in range(diff.height // PAGE):
        band = diff.crop((0, page * PAGE, diff.width, (page + 1) * PAGE))
        # Transposed, each column is one byte: non-zero where it changed.
        columns = band.transpose(Image.Transpose.TRANSPOSE).tobytes()
        runs = _runs([x for x, byte in enumerate(columns) if byte])
        if len(runs) > MAX_RUNS_PER_BAND:
            runs = [(runs[0][0], runs[-1][1])]
        for x0, x1 in runs:
            _extend_or_add(windows, x0, x1, page)
    return _merge_neighbours(windows)


def _merge_neighbours(windows):
    """Windows on touching pages whose columns overlap become one: the bands
    of one moving shape go out together, not band by band."""
    merged = True
    while merged:
        merged = False
        for i, (a0, a1, ap0, ap1) in enumerate(windows):
            for j in range(i + 1, len(windows)):
                b0, b1, bp0, bp1 = windows[j]
                if a0 <= b1 and b0 <= a1 and ap0 <= bp1 + 1 and bp0 <= ap1 + 1:
                    windows[i] = (min(a0, b0), max(a1, b1), min(ap0, bp0), max(ap1, bp1))
                    del windows[j]
                    merged = True
                    break
            if merged:
                break
    return windows


def _runs(xs):
    runs = []
    for x in xs:
        if runs and x - runs[-1][1] <= MERGE_GAP:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    return [tuple(run) for run in runs]


def _extend_or_add(windows, x0, x1, page):
    for index, (w0, w1, page0, page1) in enumerate(windows):
        if (w0, w1) == (x0, x1) and page1 == page - 1:
            windows[index] = (w0, w1, page0, page)
            return
    windows.append((x0, x1, page, page))


class PartialSender:
    """Remembers what each device shows and sends it only the difference.

    A device it has not seen, or one it was told to forget -- a failed draw
    leaves the controller's memory unknown -- gets the whole picture.
    """

    def __init__(self):
        self._shown = weakref.WeakKeyDictionary()   # a dropped device takes its picture along

    def send(self, device, image):
        picture = device.preprocess(image)
        before = self._shown.get(device)
        if before is None:
            windows = [(0, picture.width - 1, 0, picture.height // PAGE - 1)]
        else:
            windows = changed_windows(before, picture)
        const = device._const
        for x0, x1, page0, page1 in windows:
            device.command(const.COLUMNADDR, x0, x1, const.PAGEADDR, page0, page1)
            device.data(page_bytes(picture, x0, x1, page0, page1))
        self._shown[device] = picture

    def forget(self, device):
        self._shown.pop(device, None)
