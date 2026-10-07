# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A on a channel's display is the channel's analog input, always
(2026-10-07): also while a stem plays there, so the DJ sees there is
something on analog before switching. Core meters the four analog inputs
before any channel processing as analog1_L ... analog4_R (/vu 1-8, which
retired the mono in<N>_pre/post). The stereo input meters in<N>_pre_L/R
carry whatever plays and keep the channel LEDs, but no longer A."""

import json
import sys
import unittest
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE / "scripts"))

import a3_mixer_osc  # noqa: E402
from test_displays import Rig, stem  # noqa: E402
from test_osc_truth import made_up, real_truth_path  # noqa: E402

ANALOG = ["analog1_L", "analog1_R", "analog2_L", "analog2_R",
          "analog3_L", "analog3_R", "analog4_L", "analog4_R"]


def renamed_truth():
    """The installed truth with /vu 1-8 renamed as a3-core renames them, so
    the desk is held against the new truth before a3-core is merged."""
    data = json.loads(real_truth_path().read_text())
    data["vu_meters"][0:8] = ANALOG
    return a3_mixer_osc.MixerOsc(data)


class TheAnalogMetersByName(unittest.TestCase):
    def setUp(self):
        self.osc = made_up(vu_meters=["main_sub", "analog2_R", "in2_pre_L",
                                      "analog1_L", "analog4_R", "free"])

    def test_each_is_its_channel_and_side(self):
        self.assertEqual(self.osc.analog_side(2), (1, 1))
        self.assertEqual(self.osc.analog_side(4), (0, 0))
        self.assertEqual(self.osc.analog_side(5), (3, 1))

    def test_an_input_meter_is_no_analog_meter(self):
        self.assertIsNone(self.osc.analog_side(3))     # in2_pre_L
        self.assertIsNone(self.osc.analog_side(1))     # main_sub
        self.assertIsNone(self.osc.analog_side(0))
        self.assertIsNone(self.osc.analog_side(7))

    def test_an_analog_meter_is_no_input_meter(self):
        self.assertIsNone(self.osc.input_side(2))
        self.assertIsNone(self.osc.vu_slot(2))

    def test_the_desk_shows_them(self):
        """The coalescer drops a meter the desk does not show (#6)."""
        self.assertEqual([self.osc.shows_meter(n) for n in range(1, 7)],
                         [True, True, True, True, True, False])


class TheRenamedTruth(unittest.TestCase):
    """The installed truth with 1-8 renamed: what the desk meets once
    a3-core has the analog meters."""

    def setUp(self):
        self.osc = renamed_truth()

    def test_one_to_eight_are_the_four_analog_inputs(self):
        self.assertEqual([self.osc.analog_side(n) for n in range(1, 9)],
                         [(ch, side) for ch in range(4) for side in (0, 1)])

    def test_one_to_eight_are_shown(self):
        self.assertTrue(all(self.osc.shows_meter(n) for n in range(1, 9)))

    def test_one_to_eight_light_no_led(self):
        self.assertTrue(all(self.osc.vu_slot(n) is None for n in range(1, 9)))
        self.assertTrue(all(self.osc.input_side(n) is None for n in range(1, 9)))

    def test_the_stereo_input_meters_still_light_the_channel_leds(self):
        self.assertEqual([self.osc.input_side(n) for n in range(51, 59)],
                         [(ch, side) for ch in range(4) for side in (0, 1)])


class TheRealTruthHasTheAnalogMeters(unittest.TestCase):
    """Needs a3-core's truth with analog1_L ... analog4_R at /vu 1-8."""

    def test_one_to_eight_are_the_four_analog_inputs(self):
        osc = a3_mixer_osc.load(real_truth_path())
        self.assertEqual([osc.analog_side(n) for n in range(1, 9)],
                         [(ch, side) for ch in range(4) for side in (0, 1)])


class TheDeskFeedsAFromTheAnalogMeters(unittest.TestCase):
    """a3-mixer.py needs the Pi to import, so its wiring is read."""

    def setUp(self):
        source = (SOFTWARE / "scripts/a3-mixer.py").read_text()
        self.handler = source.split("def vu_handler(", 1)[1].split("\ndef ", 1)[0]

    def branch(self, asked):
        return self.handler.split(asked, 1)[1].split("return", 1)[0]

    def test_an_analog_meter_is_a(self):
        self.assertIn("displays.note_analog(channel, side, osc_arguments[0])",
                      self.branch("osc.analog_side(number)"))

    def test_an_analog_meter_lights_no_led(self):
        self.assertNotIn("send_vu_level", self.branch("osc.analog_side(number)"))

    def test_an_input_meter_no_longer_feeds_a(self):
        self.assertNotIn("displays.", self.branch("osc.input_side(number)"))

    def test_nothing_else_feeds_a(self):
        self.assertEqual(self.handler.count("displays.note_analog("), 1)
        self.assertNotIn("note_input", self.handler)


class AIsTheAnalogInputWhateverPlays(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.rig = Rig()
        self.displays = self.rig.displays(clock=lambda: self.now)
        self.displays.blank_all()
        self.displays.drain()

    def a_level(self, label):
        from display_panel import PANELS
        panel = next(p for p in PANELS if p.label == label)
        return self.displays._picture_for(panel)(128, 64).meters[8].level

    def step(self):
        from display_panel import METER_STEPS_PER_SECOND
        self.now += 1.0 / METER_STEPS_PER_SECOND
        self.displays.step_meters()
        self.displays.drain()

    def test_a_lights_from_analog2_l_while_channel_2_plays_a_stem(self):
        self.displays.show_channel(1, stem(3))
        self.displays.note_analog(1, 0, 1.0)
        self.step()
        self.assertEqual(self.a_level("Deck 2"), 1.0)

    def test_a_lights_while_a_plays_too(self):
        self.displays.show_channel(1, 0)
        self.displays.note_analog(1, 1, 1.0)
        self.step()
        self.assertEqual(self.a_level("Deck 2"), 1.0)


if __name__ == "__main__":
    unittest.main()
