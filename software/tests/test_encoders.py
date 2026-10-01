# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk's five encoders choose stems (spec stem-routing-on-the-desk).

The firmware sends T:<n>:ENC:0:<position> and T:<n>:EB:0:<0|1>. Which
encoder is which strip and how many counts make one click are measured on
the desk; the tables in a3_mixer_encoders say what was measured.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import a3_mixer_encoders as enc          # noqa: E402
from test_osc_truth import made_up        # noqa: E402


class Clicks(unittest.TestCase):
    """The firmware counts from 0 at boot and prints on every change, so the
    first line already says 1 or -1. Detents rest on multiples of four; a
    click is counted half-way between two of them."""

    def test_four_counts_are_one_click(self):
        c = enc.Clicks()
        c.feed(0, 1)
        self.assertEqual(c.feed(0, 4), 1)

    def test_the_first_report_sends_nothing(self):
        c = enc.Clicks()
        self.assertEqual(c.feed(0, 9), 0)
        self.assertEqual(c.feed(0, 8), 0)
        self.assertEqual(c.feed(0, 12), 1)

    def test_counts_carry_over(self):
        c = enc.Clicks()
        c.feed(0, 1)
        self.assertEqual(c.feed(0, 5), 1)
        self.assertEqual(c.feed(0, 7), 1)
        self.assertEqual(c.feed(0, 1), -2)

    def test_jitter_around_a_rest_position_sends_nothing(self):
        c = enc.Clicks()
        c.feed(0, 1)
        self.assertEqual(c.feed(0, 4), 1)
        for position in (5, 3, 4, 5, 3, 4):
            self.assertEqual(c.feed(0, position), 0, position)

    def test_jitter_around_zero_sends_nothing(self):
        c = enc.Clicks()
        for position in (-1, 0, 1, 0, -1):
            self.assertEqual(c.feed(0, position), 0, position)

    def test_encoders_count_on_their_own(self):
        c = enc.Clicks()
        c.feed(0, 1)
        c.feed(1, 1)
        self.assertEqual(c.feed(1, 8), 2)
        self.assertEqual(c.feed(0, 4), 1)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class PushHoldOff(unittest.TestCase):
    """The firmware reads the encoder switch raw, so one press can arrive as
    several EB edges -- and a release as well. Edges in quick succession are
    one press, not a mute toggled a random number of times."""

    def setUp(self):
        self.clock = FakeClock()
        self.hold = enc.PushHoldOff(clock=self.clock)

    def edges(self, *timed):
        accepted = []
        for at, pressed in timed:
            self.clock.now = at
            accepted.append(self.hold.feed(4, pressed))
        return accepted

    def test_a_clean_press_counts(self):
        self.assertEqual(self.edges((1.0, True), (1.2, False)), [True, False])

    def test_a_bouncing_press_counts_once(self):
        self.assertEqual(
            self.edges((1.0, True), (1.002, False), (1.004, True),
                       (1.010, False), (1.012, True)),
            [True, False, False, False, False])

    def test_a_bouncing_release_is_no_press(self):
        self.assertEqual(
            self.edges((1.0, True), (1.3, False), (1.302, True), (1.304, False)),
            [True, False, False, False])

    def test_two_presses_apart_both_count(self):
        self.assertEqual(
            self.edges((1.0, True), (1.15, False), (1.3, True)),
            [True, False, True])

    def test_encoders_hold_off_on_their_own(self):
        self.clock.now = 1.0
        self.assertTrue(self.hold.feed(4, True))
        self.assertTrue(self.hold.feed(3, True))


class TheDeskUsesIt(unittest.TestCase):
    def test_the_push_edge_goes_through_the_hold_off(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/a3-mixer.py").read_text()
        branch = source.split('if mode == "EB"', 1)[1].split("\n\n", 1)[0]
        self.assertIn("pushes.feed(", branch)


class ParseInt(unittest.TestCase):
    def test_numbers_come_through(self):
        self.assertEqual(enc.parse_int("12"), 12)
        self.assertEqual(enc.parse_int("-3"), -3)

    def test_a_damaged_field_is_nothing(self):
        for text in ("", "1x", "-", "--3", "\u00b2", "\u0661"):
            self.assertIsNone(enc.parse_int(text), text)


class Messages(unittest.TestCase):
    def test_a_channel_encoder_turns_its_channel(self):
        self.assertEqual(enc.encoder_message(made_up(), 1, -2), ("/t/channel.stem.turn/2", -2))

    def test_the_fifth_turns_the_return(self):
        self.assertEqual(enc.encoder_message(made_up(), 4, 1), ("/t/aux-return.stem.turn", 1))

    def test_no_click_no_message(self):
        self.assertIsNone(enc.encoder_message(made_up(), 0, 0))

    def test_the_return_push_on_press_only(self):
        self.assertEqual(enc.push_message(made_up(), 4, True), ("/t/aux-return.stem.push", 1))
        self.assertIsNone(enc.push_message(made_up(), 4, False))

    def test_a_channel_push_loads_the_selection(self):
        # Spec desk-stem-selector (2026-10-02): turn selects, push loads; the
        # cue is the strip's key alone.
        self.assertEqual(enc.push_message(made_up(), 1, True), ("/t/channel.stem.push/2", 1))
        self.assertIsNone(enc.push_message(made_up(), 1, False))


if __name__ == "__main__":
    unittest.main()
