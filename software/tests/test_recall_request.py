# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Das Pult fragt nach, was gerade gilt.

Gemeldet am 2026-09-18: *„a3-mixer: wenn schon fx an ist sollte auch die
zugehörige led an sein."* Die Lampen kommen von A3 Core -- aber nur, wenn sich
etwas *ändert*. Core beantwortet `/state/recall` mit allen Lampen und Flags,
und das Pult hat diese Adresse nie benutzt: nach jedem Start einer der beiden
Seiten blieben die LEDs dunkel, bis jemand einen Knopf drückte.

Die Regel steht hier, weil a3-mixer.py sich ohne die Pi-Hardware nicht einmal
importieren lässt (board, neopixel).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_recall import RecallRequest   # noqa: E402


class WhenTheDeskAsks(unittest.TestCase):
    def test_it_asks_as_soon_as_it_comes_up(self):
        request = RecallRequest(every=5.0, now=0.0)
        self.assertTrue(request.due(0.0))

    def test_it_waits_between_tries(self):
        request = RecallRequest(every=5.0, now=0.0)
        request.asked(0.0)
        self.assertFalse(request.due(4.9))
        self.assertTrue(request.due(5.0))

    def test_an_answer_ends_it(self):
        # Core may not be up yet -- it is the machine the desk plugs into --
        # so asking once is not enough, and asking forever is a message every
        # five seconds for the whole evening.
        request = RecallRequest(every=5.0, now=0.0)
        request.asked(0.0)
        request.answered()
        self.assertFalse(request.due(100.0))

    def test_it_gives_up_eventually(self):
        request = RecallRequest(every=5.0, give_up_after=60.0, now=0.0)
        request.asked(55.0)
        self.assertTrue(request.due(60.0))
        request.asked(60.0)
        self.assertFalse(request.due(65.0), "nobody is answering; stop asking")

    def test_the_address_is_cores_own(self):
        self.assertEqual(RecallRequest.ADDRESS, "/state/recall")


class TheDeskActuallyAsks(unittest.TestCase):
    def test_a3_mixer_uses_it(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/a3-mixer.py").read_text()
        self.assertIn("RecallRequest", source)
        self.assertIn("answered()", source)


if __name__ == "__main__":
    unittest.main()
