# SPDX-FileCopyrightText: 2026 Raphael Eismann
# SPDX-License-Identifier: GPL-3.0-or-later
"""The AUX-RTN encoder's delay page: a turn changes the page's value (Core
steps it), a short push steps the page, a hold of half a second cues the
return, four quiet seconds go back to BEAT (rulings R6, R7)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import a3_mixer_delay as delay          # noqa: E402
import a3_mixer_osc                     # noqa: E402
import a3_mixer_encoders as enc         # noqa: E402
from test_osc_truth import made_up      # noqa: E402


class FakeTime:
    """A clock and a `later` that fires what is due when time is advanced."""

    def __init__(self):
        self.now = 0.0
        self._due = []

    def clock(self):
        return self.now

    def later(self, seconds, then):
        self._due.append((self.now + seconds, then))

    def advance(self, seconds):
        self.now += seconds
        due = sorted((d for d in self._due if d[0] <= self.now), key=lambda d: d[0])
        self._due = [d for d in self._due if d[0] > self.now]
        for _, then in due:
            then()


class Pager(unittest.TestCase):
    def setUp(self):
        self.time = FakeTime()
        self.sent = []
        self.pages = []
        self.pager = delay.DelayPager(
            made_up(), lambda *message: self.sent.append(message), self.pages.append,
            clock=self.time.clock, later=self.time.later)

    def test_it_starts_on_beat(self):
        self.assertEqual(self.pager.page, "beat")

    def test_a_turn_goes_to_the_pages_turn_word(self):
        self.pager.turn(-2)
        self.assertEqual(self.sent, [("/t/aux-return.delay.beat.turn", -2)])

    def test_no_clicks_no_message(self):
        self.pager.turn(0)
        self.assertEqual(self.sent, [])

    def test_a_short_push_steps_through_the_pages_and_round(self):
        for expected in ("feedback", "color", "spread", "beat"):
            self.pager.press()
            self.time.advance(0.2)
            self.pager.release()
            self.assertEqual(self.pager.page, expected)
        self.assertEqual(self.pages, ["feedback", "color", "spread", "beat"])
        self.assertEqual(self.sent, [])

    def test_a_turn_follows_the_page(self):
        self.pager.press()
        self.time.advance(0.2)
        self.pager.release()
        self.pager.turn(1)
        self.assertEqual(self.sent, [("/t/aux-return.delay.feedback.turn", 1)])

    def test_a_hold_cues_at_half_a_second_and_the_release_does_nothing(self):
        self.pager.press()
        self.time.advance(0.49)
        self.assertEqual(self.sent, [])
        self.time.advance(0.02)
        self.assertEqual(self.sent, [("/t/aux-return.stem.push", 1)])
        self.time.advance(1.0)
        self.pager.release()
        self.assertEqual(self.pager.page, "beat")
        self.assertEqual(self.pages, [])
        self.assertEqual(len(self.sent), 1)

    def test_a_short_push_never_cues(self):
        self.pager.press()
        self.time.advance(0.3)
        self.pager.release()
        self.time.advance(2.0)
        self.assertEqual(self.sent, [])

    def test_a_release_bounce_at_the_press_is_no_release(self):
        self.pager.press()
        self.time.advance(0.002)
        self.pager.release()
        self.assertEqual(self.pager.page, "beat")
        self.time.advance(0.6)
        self.assertEqual(self.sent, [("/t/aux-return.stem.push", 1)])

    def test_a_release_without_a_press_does_nothing(self):
        self.pager.release()
        self.assertEqual(self.pager.page, "beat")
        self.assertEqual(self.pages, [])

    def test_a_second_release_after_a_bounce_does_nothing(self):
        self.pager.press()
        self.time.advance(0.2)
        self.pager.release()
        self.pager.release()
        self.assertEqual(self.pager.page, "feedback")

    def test_four_quiet_seconds_go_back_to_beat(self):
        self.pager.press()
        self.time.advance(0.2)
        self.pager.release()
        self.time.advance(3.9)
        self.assertEqual(self.pager.page, "feedback")
        self.time.advance(0.2)
        self.assertEqual(self.pager.page, "beat")
        self.assertEqual(self.pages, ["feedback", "beat"])

    def test_a_turn_restarts_the_four_seconds(self):
        self.pager.press()
        self.time.advance(0.2)
        self.pager.release()
        self.time.advance(3.0)
        self.pager.turn(1)
        self.time.advance(3.0)
        self.assertEqual(self.pager.page, "feedback")
        self.time.advance(1.1)
        self.assertEqual(self.pager.page, "beat")

    def test_a_push_restarts_the_four_seconds(self):
        self.pager.press()
        self.time.advance(0.2)
        self.pager.release()
        self.time.advance(3.0)
        self.pager.press()
        self.time.advance(0.2)
        self.pager.release()
        self.time.advance(3.5)
        self.assertEqual(self.pager.page, "color")

    def test_a_hold_restarts_the_four_seconds(self):
        self.pager.press()
        self.time.advance(0.2)
        self.pager.release()
        self.time.advance(3.5)
        self.pager.press()
        self.time.advance(1.0)
        self.pager.release()
        self.time.advance(3.0)
        self.assertEqual(self.pager.page, "feedback")

    def test_on_beat_nothing_falls_back(self):
        self.pager.turn(1)
        self.time.advance(10)
        self.assertEqual(self.pages, [])


class Values(unittest.TestCase):
    def setUp(self):
        self.shown = []
        self.state = delay.DelayState(lambda page, values: self.shown.append((page, dict(values))))

    def test_no_value_until_core_speaks(self):
        self.state.show_page("beat")
        self.assertEqual(self.shown[-1], ("beat", {"beat": None, "feedback": None,
                                                     "color": None, "spread": None}))

    def test_a_value_is_kept_and_shown_with_the_page(self):
        self.state.set_value("feedback", 0.7)
        self.state.show_page("feedback")
        self.assertEqual(self.shown[-1][0], "feedback")
        self.assertEqual(self.shown[-1][1]["feedback"], 0.7)
        self.assertIsNone(self.shown[-1][1]["beat"])

    def test_a_value_alone_redraws_the_current_page(self):
        self.state.show_page("color")
        self.state.set_value("color", -0.3)
        self.assertEqual(self.shown[-1], ("color", {"beat": None, "feedback": None,
                                                      "color": -0.3, "spread": None}))

    def test_the_four_pages_are_the_four_values(self):
        self.assertEqual(delay.PAGES, ("beat", "feedback", "color", "spread"))


class TheDisplaysStartLikeTheState(unittest.TestCase):
    def test_the_first_delay_page_is_beat_with_no_values(self):
        from test_displays import Rig
        displays = Rig().displays()
        self.assertEqual(displays.delay_page,
                         ("beat", {page: None for page in delay.PAGES}))


class ValueAnnouncement(unittest.TestCase):
    def test_a_float_is_a_value(self):
        self.assertEqual(delay.value_announcement((0.25,)), 0.25)
        self.assertEqual(delay.value_announcement((60,)), 60.0)

    def test_damage_is_none(self):
        for args in ((), ("x",), (None,), (float("nan"),), (1, 2), (True,)):
            self.assertIsNone(delay.value_announcement(args), args)


class ReturnEncoderMessages(unittest.TestCase):
    def test_the_return_push_is_the_pagers_not_an_immediate_cue(self):
        self.assertIsNone(enc.push_message(made_up(), 4, True))

    def test_a_channel_push_is_as_before(self):
        self.assertEqual(enc.push_message(made_up(), 1, True), ("/t/channel.stem.push/2", 1))

    def test_the_return_turn_is_a_delay_turn_of_the_page(self):
        self.assertEqual(enc.encoder_message(made_up(), 4, 2, page="spread"),
                         ("/t/aux-return.delay.spread.turn", 2))


class TheTruthHasTheWords(unittest.TestCase):
    def test_the_real_truth_has_the_delay_page(self):
        from test_osc_truth import real_truth_path
        self.assertTrue(a3_mixer_osc.load(real_truth_path()).has_delay_page())

    def test_a_hold_is_not_lost_to_a_turn_meanwhile(self):
        time = FakeTime()
        sent = []
        pager = delay.DelayPager(made_up(), lambda *m: sent.append(m), lambda p: None,
                                 clock=time.clock, later=time.later)
        pager.press()
        time.advance(0.2)
        pager.turn(1)
        time.advance(0.4)
        self.assertEqual(sent[-1], ("/t/aux-return.stem.push", 1))

    def test_a_truth_from_before_has_none(self):
        addresses = {k: v for k, v in made_up()._data["addresses"].items()
                     if k not in a3_mixer_osc.DELAY_KEYS}
        self.assertFalse(made_up(addresses=addresses).has_delay_page())


class TheDeskUsesIt(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1] / "scripts" / "a3-mixer.py").read_text()

    def test_the_value_words_are_mapped(self):
        self.assertIn("dispatcher.map(osc.subscription(key), delay_handler)", self.source)
        self.assertIn("for key in VALUE_KEYS if osc.has_delay_page()", self.source)

    def test_a_calibration_takes_the_return_encoder_first(self):
        branch = self.source.split('if mode == "ENC"', 1)[1].split("# Buttons", 1)[0]
        self.assertLess(branch.index("calibration.turned("), branch.index("pager.turn("))
        self.assertLess(branch.index("calibration.pushed()"), branch.index("pager.press("))

    def test_a_value_handler_sends_nothing(self):
        handler = self.source.split("def delay_handler(", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("send", handler)
        self.assertNotIn("to_core", handler)


if __name__ == "__main__":
    unittest.main()
