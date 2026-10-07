# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A channel's eight input LEDs show the louder side of its stereo meter
(spec stereo-channel-meters, 2026-10-06), the way DJ mixers do. The mono
in<N>_pre read 3 dB low: REAPER's send downmix divides by the channel count.
Core meters each channel as in<N>_pre_L and in<N>_pre_R (/vu 51-58 in its
truth); the desk takes peak and RMS each as the max of the two sides. Since
2026-10-07 the mono meters are gone from the truth (/vu 1-8 are the analog
inputs, test_analog_input_meters), and so is the desk's fallback to them."""

import sys
import unittest
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE / "scripts"))

import a3_mixer_osc  # noqa: E402
from a3_mixer_meters import StereoInputs, louder  # noqa: E402
from test_osc_truth import made_up  # noqa: E402

STEREO = ["in1_pre", "in2_pre", "in3_pre", "in4_pre", "main_sub",
          "in1_pre_L", "in1_pre_R", "in2_pre_L", "in2_pre_R",
          "in3_pre_L", "in3_pre_R", "in4_pre_L", "in4_pre_R"]


class TheLouderSide(unittest.TestCase):
    def test_peak_and_rms_are_each_the_louder_side(self):
        self.assertEqual(louder((0.5, 0.1), (0.25, 0.2)), (0.5, 0.2))

    def test_equal_sides_are_that_level(self):
        self.assertEqual(louder((0.3, 0.1), (0.3, 0.1)), (0.3, 0.1))


class ALevelIsHeldPerSide(unittest.TestCase):
    """L and R arrive as two messages; each side's last level is kept, so
    the LED level of channel 1 is the louder of in1_pre_L and in1_pre_R."""

    def test_the_led_level_is_the_louder_of_left_and_right(self):
        inputs = StereoInputs()
        inputs.note(0, 0, 0.5, 0.1)
        self.assertEqual(inputs.note(0, 1, 0.25, 0.2), (0.5, 0.2))

    def test_a_side_not_heard_yet_is_silence(self):
        self.assertEqual(StereoInputs().note(2, 1, 0.25, 0.2), (0.25, 0.2))

    def test_the_newest_level_of_a_side_replaces_its_last(self):
        inputs = StereoInputs()
        inputs.note(0, 0, 0.9, 0.9)
        inputs.note(0, 1, 0.1, 0.1)
        self.assertEqual(inputs.note(0, 0, 0.2, 0.05), (0.2, 0.1))

    def test_channels_do_not_mix(self):
        inputs = StereoInputs()
        inputs.note(0, 0, 0.9, 0.9)
        self.assertEqual(inputs.note(1, 0, 0.1, 0.1), (0.1, 0.1))


class TheStereoMetersByName(unittest.TestCase):
    def test_each_side_is_its_channels_slot_and_side(self):
        osc = made_up(vu_meters=STEREO)
        self.assertEqual(osc.input_side(6), (0, 0))   # in1_pre_L
        self.assertEqual(osc.input_side(7), (0, 1))   # in1_pre_R
        self.assertEqual(osc.input_side(13), (3, 1))  # in4_pre_R

    def test_other_meters_are_no_input_side(self):
        osc = made_up(vu_meters=STEREO)
        self.assertIsNone(osc.input_side(1))   # in1_pre, mono
        self.assertIsNone(osc.input_side(5))   # main_sub
        self.assertIsNone(osc.input_side(0))
        self.assertIsNone(osc.input_side(14))

    def test_with_stereo_meters_the_mono_ones_light_nothing(self):
        """Both stay in the truth until every consumer has switched; two
        meters on one strip would flicker between them."""
        osc = made_up(vu_meters=STEREO)
        self.assertTrue(all(osc.vu_slot(n) is None for n in range(1, 5)))
        self.assertEqual(osc.vu_slot(5), 4)   # main_sub still lights

    def test_a_mono_input_meter_lights_nothing(self):
        """Since 2026-10-07 no truth has the mono in<N>_pre: /vu 1-8 are the
        analog inputs, and the desk has no fallback to them."""
        osc = made_up(vu_meters=["in1_pre", "in2_pre", "main_sub"])
        self.assertIsNone(osc.vu_slot(1))
        self.assertIsNone(osc.vu_slot(2))
        self.assertFalse(osc.shows_meter(1))


class TheDeskLightsTheLouderSide(unittest.TestCase):
    """a3-mixer.py needs the Pi to import, so its wiring is read."""

    def setUp(self):
        source = (SOFTWARE / "scripts/a3-mixer.py").read_text()
        self.handler = source.split("def vu_handler(", 1)[1].split("\ndef ", 1)[0]

    def test_a_stereo_side_is_combined_before_it_is_sent(self):
        self.assertIn("osc.input_side(number)", self.handler)
        self.assertIn("stereo_inputs.note(", self.handler)

    def test_a_side_lights_the_leds_only(self):
        """The stereo input meter carries whatever plays on the channel; A
        is the analog input's own meter since 2026-10-07."""
        stereo = self.handler.split("osc.input_side(number)", 1)[1].split("return", 1)[0]
        self.assertNotIn("displays.", stereo)

    def test_the_stereo_side_is_asked_before_the_slot(self):
        self.assertLess(self.handler.index("osc.input_side(number)"),
                        self.handler.index("osc.vu_slot(number)"))


class TheRealTruthHasTheStereoMeters(unittest.TestCase):
    """Needs a3-core's truth with /vu 51-58 (branch feat/stereo-channel-meters)."""

    def test_every_channel_has_its_left_and_right(self):
        from test_osc_truth import real_truth_path
        osc = a3_mixer_osc.load(real_truth_path())
        sides = [osc.input_side(n) for n in range(51, 59)]
        self.assertEqual(sides, [(ch, side) for ch in range(4) for side in (0, 1)])


if __name__ == "__main__":
    unittest.main()
