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
    def test_four_counts_are_one_click(self):
        c = enc.Clicks()
        c.feed(0, 0)
        self.assertEqual(c.feed(0, 4), 1)

    def test_counts_carry_over(self):
        c = enc.Clicks()
        c.feed(0, 0)
        self.assertEqual(c.feed(0, 3), 0)
        self.assertEqual(c.feed(0, 5), 1)
        self.assertEqual(c.feed(0, 1), -1)

    def test_encoders_count_on_their_own(self):
        c = enc.Clicks()
        c.feed(0, 0)
        c.feed(1, 0)
        self.assertEqual(c.feed(1, 8), 2)
        self.assertEqual(c.feed(0, 4), 1)


class Messages(unittest.TestCase):
    def test_a_channel_encoder_turns_its_channel(self):
        self.assertEqual(enc.encoder_message(made_up(), 1, -2), ("/t/channel.stem.turn/2", -2))

    def test_the_fifth_turns_the_return(self):
        self.assertEqual(enc.encoder_message(made_up(), 4, 1), ("/t/fx-return.stem.turn", 1))

    def test_no_click_no_message(self):
        self.assertIsNone(enc.encoder_message(made_up(), 0, 0))

    def test_the_return_push_on_press_only(self):
        self.assertEqual(enc.push_message(made_up(), 4, True), ("/t/fx-return.stem.push", 1))
        self.assertIsNone(enc.push_message(made_up(), 4, False))

    def test_a_channel_push_does_nothing_yet(self):
        self.assertIsNone(enc.push_message(made_up(), 0, True))


if __name__ == "__main__":
    unittest.main()
