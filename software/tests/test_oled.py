# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Only what changed goes over I2C.

luma's ssd1306 sends the whole 1 KB frame on every draw, about 0.1 s at the
desk's 100 kHz, and builds it pixel by pixel in Python. The SSD1306 takes a
column and page window instead, so a square that changed costs its own bytes
(2026-10-01: the stem displays lagged behind the encoders)."""

import random
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_oled import PartialSender, changed_windows, page_bytes  # noqa: E402

WIDTH, HEIGHT = 128, 64


def luma_bytes(image, x0, x1, page0, page1):
    """What luma's ssd1306.display() would send for that window: one byte per
    column and page, bit 0 the page's top row."""
    out = []
    for page in range(page0, page1 + 1):
        for x in range(x0, x1 + 1):
            byte = 0
            for bit in range(8):
                if image.getpixel((x, page * 8 + bit)):
                    byte |= 1 << bit
            out.append(byte)
    return out


def noise(seed):
    rng = random.Random(seed)
    image = Image.new("1", (WIDTH, HEIGHT))
    for _ in range(900):
        image.putpixel((rng.randrange(WIDTH), rng.randrange(HEIGHT)), 1)
    return image


class FakeDevice:
    class _const:
        COLUMNADDR = 0x21
        PAGEADDR = 0x22

    mode = "1"
    size = (WIDTH, HEIGHT)

    def __init__(self, rotate180=False):
        self.rotate180 = rotate180
        self.sent = []

    def preprocess(self, image):
        return image.rotate(180) if self.rotate180 else image

    def command(self, *codes):
        self.sent.append(("command", codes))

    def data(self, values):
        self.sent.append(("data", list(values)))


class PageBytes(unittest.TestCase):
    def test_the_whole_frame_is_what_luma_sends(self):
        image = noise(1)
        self.assertEqual(page_bytes(image, 0, WIDTH - 1, 0, 7),
                         luma_bytes(image, 0, WIDTH - 1, 0, 7))

    def test_a_window_is_what_luma_sends_for_it(self):
        image = noise(2)
        self.assertEqual(page_bytes(image, 37, 70, 2, 5),
                         luma_bytes(image, 37, 70, 2, 5))


def flip(image, *points):
    after = image.copy()
    for x, y in points:
        after.putpixel((x, y), 1 - after.getpixel((x, y)))
    return after


class ChangedWindows(unittest.TestCase):
    """One window per changed area, not one rectangle around all of them: a
    channel turn empties one square and fills another, and a rectangle around
    both was most of the display again (2026-10-01: 47-73 ms per draw)."""

    def test_the_same_picture_changes_nothing(self):
        self.assertEqual(changed_windows(noise(3), noise(3)), [])

    def test_one_pixel_is_its_column_and_page(self):
        self.assertEqual(changed_windows(noise(3), flip(noise(3), (40, 20))),
                         [(40, 40, 2, 2)])

    def test_two_far_apart_changes_are_two_windows(self):
        self.assertEqual(changed_windows(noise(3), flip(noise(3), (10, 3), (90, 50))),
                         [(10, 10, 0, 0), (90, 90, 6, 6)])

    def test_close_changes_in_one_band_share_a_window(self):
        self.assertEqual(changed_windows(noise(3), flip(noise(3), (10, 3), (14, 5))),
                         [(10, 14, 0, 0)])

    def test_a_square_over_several_bands_is_one_window(self):
        before = Image.new("1", (WIDTH, HEIGHT))
        after = before.copy()
        after.paste(1, (38, 6, 58, 26))
        self.assertEqual(changed_windows(before, after), [(38, 57, 0, 3)])


class Sending(unittest.TestCase):
    def test_the_first_picture_goes_out_whole(self):
        device = FakeDevice()
        PartialSender().send(device, noise(4))
        self.assertEqual(device.sent[0], ("command", (0x21, 0, WIDTH - 1, 0x22, 0, 7)))
        self.assertEqual(len(device.sent[1][1]), 1024)

    def test_an_unchanged_picture_sends_nothing(self):
        device, sender = FakeDevice(), PartialSender()
        sender.send(device, noise(4))
        device.sent.clear()
        sender.send(device, noise(4))
        self.assertEqual(device.sent, [])

    def test_a_changed_square_sends_only_its_window(self):
        device, sender = FakeDevice(), PartialSender()
        before = Image.new("1", (WIDTH, HEIGHT))
        sender.send(device, before)
        device.sent.clear()
        after = before.copy()
        after.paste(1, (38, 6, 58, 26))           # a 20x20 square, x 38-57, y 6-25
        sender.send(device, after)
        self.assertEqual(device.sent[0], ("command", (0x21, 38, 57, 0x22, 0, 3)))
        self.assertEqual(device.sent[1][1], luma_bytes(after, 38, 57, 0, 3))
        self.assertLess(len(device.sent[1][1]), 1024 // 10)

    def test_a_turn_sends_two_small_windows(self):
        device, sender = FakeDevice(), PartialSender()
        before = Image.new("1", (WIDTH, HEIGHT))
        before.paste(1, (80, 6, 100, 26))          # the old stem, top right
        sender.send(device, before)
        device.sent.clear()
        after = Image.new("1", (WIDTH, HEIGHT))
        after.paste(1, (6, 38, 26, 58))            # the new one, bottom left
        sender.send(device, after)
        commands = [codes for kind, codes in device.sent if kind == "command"]
        sent = sum(len(values) for kind, values in device.sent if kind == "data")
        self.assertEqual(commands, [(0x21, 80, 99, 0x22, 0, 3), (0x21, 6, 25, 0x22, 4, 7)])
        self.assertEqual(sent, 2 * 20 * 4)

    def test_the_device_rotation_is_applied_before_comparing(self):
        device, sender = FakeDevice(rotate180=True), PartialSender()
        image = noise(5)
        sender.send(device, image)
        self.assertEqual(device.sent[1][1], luma_bytes(image.rotate(180), 0, WIDTH - 1, 0, 7))

    def test_a_forgotten_device_gets_the_whole_picture_again(self):
        device, sender = FakeDevice(), PartialSender()
        sender.send(device, noise(6))
        sender.forget(device)
        device.sent.clear()
        sender.send(device, noise(6))
        self.assertEqual(len(device.sent[1][1]), 1024)


if __name__ == "__main__":
    unittest.main()
