# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Send an SSD1306 only the part of the picture that changed.

luma's ssd1306.display() sends the whole frame on every draw -- 1 KB, about
0.1 s on the desk's 100 kHz bus -- and packs it pixel by pixel in Python. The
controller takes a column and page window (COLUMNADDR, PAGEADDR) and then only
that window's bytes, so one stem square costs a tenth of the frame.

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


def changed_window(before, after):
    """(x0, x1, page0, page1) around everything that differs, or None."""
    box = ImageChops.logical_xor(before, after).getbbox()
    if box is None:
        return None
    left, upper, right, lower = box
    return left, right - 1, upper // PAGE, (lower - 1) // PAGE


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
            window = (0, picture.width - 1, 0, picture.height // PAGE - 1)
        else:
            window = changed_window(before, picture)
            if window is None:
                return
        x0, x1, page0, page1 = window
        const = device._const
        device.command(const.COLUMNADDR, x0, x1, const.PAGEADDR, page0, page1)
        device.data(page_bytes(picture, x0, x1, page0, page1))
        self._shown[device] = picture

    def forget(self, device):
        self._shown.pop(device, None)
