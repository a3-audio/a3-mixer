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
                             channel_vu_line, main_led_index, main_vu_line)

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


class TheLineCarriesTheBarAndTheHold(unittest.TestCase):
    """"VU:slot:a:b" keeps its shape. For a channel a is the top LED of the
    bar and b the LED of the held peak (index = count − 1, −1 = dark,
    2026-10-07): the firmware draws 0..a in fixed colours and lights b in
    its own. A desk still on the old firmware reads only a and draws the
    same bar, without the hold."""

    def test_a_dark_channel_sends_minus_one(self):
        self.assertEqual(channel_vu_line(2, float("-inf"), float("-inf")), "VU:2:-1:-1")

    def test_a_full_channel_sends_its_top_led(self):
        self.assertEqual(channel_vu_line(0, 0.0, 0.0), "VU:0:7:7")

    def test_the_hold_rides_above_the_bar(self):
        self.assertEqual(channel_vu_line(3, -18.0, -6.0), "VU:3:2:5")

    def test_a_hold_below_the_first_led_is_dark(self):
        self.assertEqual(channel_vu_line(1, -50.0, -40.0), "VU:1:-1:-1")


class TheMainLineCarriesTheHoldDot(unittest.TestCase):
    """The main meter's 32 rows keep their −60…0 dBFS scale and the old
    firmware's field order -- a the single dot, b the bar --, so a desk on
    the old firmware draws it right as it is: bar = the ballistic peak,
    dot = the held peak. RMS is no longer drawn (spec meter-ballistics)."""

    def test_the_bar_and_the_dot(self):
        self.assertEqual(main_vu_line(5, -30.0, -15.0), "VU:5:24:16")

    def test_full_scale_is_the_top_row(self):
        self.assertEqual(main_vu_line(4, 0.0, 0.0), "VU:4:31:31")

    def test_silence_is_the_bottom_row_as_before(self):
        self.assertEqual(main_vu_line(11, -120.0, -120.0), "VU:11:0:0")

    def test_the_index_is_the_old_one(self):
        for db in (-60.0, -45.5, -12.0, -1.0):
            with self.subTest(db=db):
                self.assertEqual(main_led_index(db), min(int((db + 60) / 60 * 32), 31))


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

    def test_the_hold_led_is_lit_in_its_own_colour(self):
        """The second field is the hold LED: lit at its place, in its
        position's colour, whether or not the bar reaches it."""
        section = channel_section()
        self.assertIn("int hold_index = rms_index;", section)
        self.assertRegex(section, r"j <= top_index \|\| j == hold_index")

    def test_the_main_meter_draws_its_bar_and_one_dot(self):
        source = FIRMWARE.read_text()
        section = source[source.index("// output VU meters"):]
        self.assertIn("j <= rms_index || j == peak_index", section)


class TheDeskSendsTheBallisticLevels(unittest.TestCase):
    def test_every_led_meter_goes_through_its_ballistics(self):
        script = (SOFTWARE / "scripts/a3-mixer.py").read_text()
        sender = script[script.index("def send_vu_data"):]
        sender = sender[:sender.index("\ndef ")]
        self.assertIn("led_ballistics[", sender)
        self.assertIn("main_vu_line(", sender)


if __name__ == "__main__":
    unittest.main()
