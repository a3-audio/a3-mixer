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


class AfterARestart(unittest.TestCase):
    """The desk reads time.monotonic(), seconds since the Pi booted. Started
    at 0, a service restarted more than give_up_after into the boot had given
    up before it asked once (2026-10-04): the return display stayed on its
    blank state until an encoder turn."""

    def test_without_a_start_it_starts_at_the_first_look(self):
        request = RecallRequest(every=5.0, give_up_after=120.0)
        self.assertTrue(request.due(6553.0))

    def test_without_a_start_it_still_gives_up(self):
        request = RecallRequest(every=5.0, give_up_after=120.0)
        request.due(6553.0)
        request.asked(6670.0)
        self.assertFalse(request.due(6675.0))


class TheDeskActuallyAsks(unittest.TestCase):
    def test_a3_mixer_uses_it(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/a3-mixer.py").read_text()
        self.assertIn("RecallRequest", source)
        self.assertIn("answered()", source)

    def test_it_asks_in_the_truths_words(self):
        """The address is the one truth's, like every other the desk speaks
        (2026-09-30) -- it used to be a constant on RecallRequest."""
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/a3-mixer.py").read_text()
        self.assertIn('osc.address("state.recall")', source)
        self.assertIn("osc.hello()", source)
        self.assertFalse(hasattr(RecallRequest, "ADDRESS"))



class AskingSurvivesTheNetwork(unittest.TestCase):
    """2026-10-02, after a reboot: the desk started before its network, the
    first hello raised 'Network is unreachable' and ended the thread -- no
    state from Core, no hello to it, until the next restart. A failed send
    is said once and tried again a second later."""

    def setUp(self):
        from a3_mixer_recall import HelloEvery, RecallRequest, StateAsker
        self.sent, self.reports, self.send = [], [], None
        self.asker = StateAsker(HelloEvery(), RecallRequest(),
                                lambda kind: self.send(kind), self.reports.append)

    def ask(self, now, send):
        self.send = send
        self.asker.ask(now)

    def failing(self, kind):
        raise OSError(101, "Network is unreachable")

    def test_a_failed_send_does_not_raise(self):
        self.ask(0.0, self.failing)
        self.assertEqual(len(self.reports), 1)

    def test_it_is_tried_again(self):
        self.ask(0.0, self.failing)
        self.ask(1.0, lambda kind: self.sent.append(kind))
        self.assertEqual(self.sent, ["hello", "recall"])

    def test_an_outage_is_said_once(self):
        for second in range(5):
            self.ask(float(second), self.failing)
        self.assertEqual(len(self.reports), 1)

    def test_the_loop_uses_it(self):
        from pathlib import Path
        script = (Path(__file__).resolve().parents[1] / "scripts/a3-mixer.py").read_text()
        loop = script[script.index("def ask_for_the_state"):]
        loop = loop[:loop.index("threading.Thread")]
        self.assertIn("asker.ask(", loop)

if __name__ == "__main__":
    unittest.main()
