# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The channel LEDs read like a DJ mixer's (gain-structure spec, F10/O9):
the bar follows the peak on a fixed dBFS scale, and every LED has its own
colour -- 1-4 green, 5-6 yellow, 7-8 red -- so red means near clip and
nothing else. Before, the scale was −60..0 dBFS linear and the peak was a
red dot that wandered down the strip with the level."""

import re
import sys
import unittest
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
FIRMWARE = SOFTWARE.parent / "hardware/mainboard/firmware/src/main.cpp"
sys.path.insert(0, str(SOFTWARE / "scripts"))

from a3_mixer_meters import (CHANNEL_LED_THRESHOLDS_DB, channel_leds,
                             channel_vu_line)

THRESHOLDS = [-36, -24, -18, -12, -9, -6, -3, 0]
JUST = 0.01


class TheChannelScaleIsFixed(unittest.TestCase):
    def test_the_table_is_the_agreed_scale(self):
        self.assertEqual(list(CHANNEL_LED_THRESHOLDS_DB), THRESHOLDS)

    def test_each_led_lights_at_its_threshold(self):
        for count, threshold in enumerate(THRESHOLDS, start=1):
            with self.subTest(threshold=threshold):
                self.assertEqual(channel_leds(threshold), count)

    def test_each_led_stays_dark_just_below_its_threshold(self):
        for count, threshold in enumerate(THRESHOLDS, start=1):
            with self.subTest(threshold=threshold):
                self.assertEqual(channel_leds(threshold - JUST), count - 1)

    def test_silence_lights_nothing(self):
        self.assertEqual(channel_leds(float("-inf")), 0)
        self.assertEqual(channel_leds(-60.0), 0)

    def test_over_full_scale_lights_all_eight(self):
        self.assertEqual(channel_leds(6.0), 8)


class TheLineCarriesTheTopLed(unittest.TestCase):
    """"VU:slot:a:b" keeps its shape. For a channel both fields carry the
    index of the top lit LED (count − 1, −1 = dark): the new firmware draws
    0..a in fixed colours, and a desk still on the old firmware draws the
    same bar, green with its top red, instead of a stray dot."""

    def test_a_dark_channel_sends_minus_one(self):
        self.assertEqual(channel_vu_line(2, float("-inf")), "VU:2:-1:-1")

    def test_a_full_channel_sends_its_top_led(self):
        self.assertEqual(channel_vu_line(0, 0.0), "VU:0:7:7")

    def test_the_reference_lights_three(self):
        self.assertEqual(channel_vu_line(3, -18.0), "VU:3:2:2")


class TheDeskUsesTheScaleForChannels(unittest.TestCase):
    def test_the_channel_slots_go_through_channel_vu_line(self):
        script = (SOFTWARE / "scripts/a3-mixer.py").read_text()
        sender = script[script.index("def send_vu_data"):]
        sender = sender[:sender.index("\ndef ")]
        self.assertIn("channel_vu_line(", sender)


def channel_section():
    source = FIRMWARE.read_text()
    section = source[source.index("// per-channel VU meters"):]
    return section[:section.index("// output VU meters")]


class TheFirmwareColoursByPosition(unittest.TestCase):
    def test_the_colours_are_four_green_two_yellow_two_red(self):
        source = FIRMWARE.read_text()
        table = source[source.index("channelLedColour[8]"):]
        table = table[:table.index("};")]
        names = re.findall(r"\b(GREEN|YELLOW|RED)\b", table)
        self.assertEqual(names, ["GREEN"] * 4 + ["YELLOW"] * 2 + ["RED"] * 2)

    def test_a_led_is_lit_up_to_the_top_index_in_its_own_colour(self):
        section = channel_section()
        self.assertIn("j <= top_index", section)
        self.assertIn("channelLedColour[j]", section)

    def test_there_is_no_wandering_peak_dot(self):
        self.assertNotIn("j == peak_index", channel_section())


if __name__ == "__main__":
    unittest.main()
