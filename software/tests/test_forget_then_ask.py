# SPDX-FileCopyrightText: 2026 Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A new Core wipes the desk's engine state -- and asks for it again.

Rig, 2026-10-28: the desk started, asked for the state (/state/recall), got
it, and the first /core/here up to 2 s later counted as a new Core: the
displays forgot every channel's source, cursor and which decks are there.
Core repeats a value only when it changes, so the deck bars stayed absent
(no meters) and the bracket stayed on ST until something else asked for a
recall. Forgetting is right for a new Core; it must be followed by asking.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_recall import CoreArrival, ForgetThenAsk  # noqa: E402


class ForgetThenAskTests(unittest.TestCase):
    def setUp(self):
        self.steps = []
        self.reports = []
        self.failing = False

    def ask(self):
        if self.failing:
            raise OSError("network unreachable")
        self.steps.append("ask")

    def reaction(self):
        return ForgetThenAsk(CoreArrival(), lambda: self.steps.append("forget"),
                             self.ask, self.reports.append)

    def test_a_new_core_is_forgotten_then_asked(self):
        self.reaction().heard(0.0, "one")
        self.assertEqual(self.steps, ["forget", "ask"])

    def test_the_steady_beat_neither_forgets_nor_asks(self):
        reaction = self.reaction()
        reaction.heard(0.0, "one")
        reaction.heard(2.0, "one")
        reaction.heard(4.0, "one")
        self.assertEqual(self.steps, ["forget", "ask"])

    def test_a_restarted_core_is_forgotten_and_asked_again(self):
        reaction = self.reaction()
        reaction.heard(0.0, "one")
        reaction.heard(2.0, "two")
        self.assertEqual(self.steps, ["forget", "ask", "forget", "ask"])

    def test_an_ask_that_cannot_be_sent_is_tried_on_the_next_beat(self):
        reaction = self.reaction()
        self.failing = True
        reaction.heard(0.0, "one")
        self.assertEqual(len(self.reports), 1)
        self.failing = False
        reaction.heard(2.0, "one")
        self.assertEqual(self.steps, ["forget", "forget", "ask"])


class TheDeskAsksAfterForgetting(unittest.TestCase):
    """a3-mixer.py needs the Pi to import, so its wiring is read."""

    def test_the_engine_mode_listener_forgets_then_asks(self):
        source = (Path(__file__).resolve().parents[1] / "scripts/a3-mixer.py").read_text()
        listener = source.split("def forget_engine_on_new_core():", 1)[1].split("forget_engine_on_new_core()", 1)[0]
        self.assertIn("ForgetThenAsk(", listener)
        self.assertIn("displays.forget_engine", listener)
        self.assertIn('osc.address("state.recall")', listener)


if __name__ == "__main__":
    unittest.main()
