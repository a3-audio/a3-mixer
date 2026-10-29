# SPDX-FileCopyrightText: 2026 Raphael Eismann
# SPDX-License-Identifier: GPL-3.0-or-later
"""The AUX-RTN encoder's delay list: five rows, a push toggles select and edit,
a turn moves the cursor (select) or changes the row (edit), four quiet seconds
leave edit (rulings R22-R25)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "a3-mixer-set-display"))

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


class ListFixture(unittest.TestCase):
    def setUp(self):
        self.time = FakeTime()
        self.sent = []
        self.views = []
        self.cue = [False]
        self.answers = [0]    # lamp announcements seen so far
        self.list = delay.DelayList(
            made_up(), lambda *message: self.sent.append(message),
            lambda mode, cursor: self.views.append((mode, cursor)),
            lambda: self.cue[0], clock=self.time.clock, later=self.time.later,
            cue_answers=lambda: self.answers[0])

    def edit(self, row):
        """Select `row` and press into edit mode, sending nothing."""
        self.list.turn(delay.ROWS.index(row))
        self.list.press()
        self.sent.clear()
        self.views.clear()


class Select(ListFixture):
    def test_it_starts_in_select_on_beat(self):
        self.assertEqual((self.list.mode, self.list.cursor), (delay.SELECT, 0))
        self.assertEqual(delay.ROWS[0], "beat")

    def test_the_rows_are_the_four_parameters_and_cue(self):
        self.assertEqual(delay.ROWS, ("beat", "feedback", "color", "spread", "cue"))
        self.assertEqual(delay.DELAY_ROWS, delay.ROWS[:4])

    def test_a_turn_moves_the_cursor_and_sends_nothing(self):
        self.list.turn(1)
        self.assertEqual(self.list.cursor, 1)
        self.list.turn(1)
        self.assertEqual(self.list.cursor, 2)
        self.list.turn(-1)
        self.assertEqual(self.list.cursor, 1)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.views, [(delay.SELECT, 1), (delay.SELECT, 2), (delay.SELECT, 1)])

    def test_the_cursor_stops_at_beat_and_at_cue_it_does_not_wrap(self):
        self.list.turn(-1)
        self.assertEqual(self.list.cursor, 0)
        self.list.turn(9)
        self.assertEqual(self.list.cursor, 4)
        self.list.turn(1)
        self.assertEqual(self.list.cursor, 4)

    def test_a_turn_that_moves_nothing_shows_nothing(self):
        self.list.turn(-1)
        self.assertEqual(self.views, [])

    def test_no_clicks_no_change(self):
        self.list.turn(0)
        self.assertEqual((self.views, self.sent), ([], []))

    def test_select_never_falls_back_or_cues(self):
        self.list.turn(2)
        self.views.clear()
        self.time.advance(60)
        self.assertEqual((self.views, self.sent), ([], []))


class Toggle(ListFixture):
    def test_a_press_goes_into_edit_and_the_next_back(self):
        self.list.turn(2)
        self.list.press()
        self.assertEqual((self.list.mode, self.list.cursor), (delay.EDIT, 2))
        self.list.press()
        self.assertEqual((self.list.mode, self.list.cursor), (delay.SELECT, 2))
        self.assertEqual(self.views[-2:], [(delay.EDIT, 2), (delay.SELECT, 2)])

    def test_a_press_is_the_edge_there_is_no_hold(self):
        self.list.press()
        self.time.advance(2)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.list.mode, delay.EDIT)

    def test_edit_falls_back_to_select_after_four_seconds_cursor_stays(self):
        self.list.turn(3)
        self.list.press()
        self.time.advance(3.9)
        self.assertEqual(self.list.mode, delay.EDIT)
        self.time.advance(0.2)
        self.assertEqual((self.list.mode, self.list.cursor), (delay.SELECT, 3))
        self.assertEqual(self.views[-1], (delay.SELECT, 3))

    def test_a_turn_in_edit_restarts_the_four_seconds(self):
        self.edit("beat")
        self.time.advance(3)
        self.list.turn(1)
        self.time.advance(3)
        self.assertEqual(self.list.mode, delay.EDIT)
        self.time.advance(1.1)
        self.assertEqual(self.list.mode, delay.SELECT)

    def test_a_fallback_after_the_user_left_edit_does_nothing(self):
        self.edit("beat")
        self.list.press()
        self.views.clear()
        self.time.advance(10)
        self.assertEqual(self.views, [])

    def test_a_second_visit_to_edit_gets_its_own_four_seconds(self):
        self.edit("beat")
        self.time.advance(2)
        self.list.press()
        self.list.press()
        self.time.advance(3)
        self.assertEqual(self.list.mode, delay.EDIT)
        self.time.advance(1.5)
        self.assertEqual(self.list.mode, delay.SELECT)


class Edit(ListFixture):
    def test_a_turn_sends_the_rows_turn_word_with_the_clicks(self):
        for row in delay.DELAY_ROWS:
            self.list = delay.DelayList(
                made_up(), lambda *m: self.sent.append(m), lambda *v: None,
                lambda: False, clock=self.time.clock, later=self.time.later)
            self.edit(row)
            self.list.turn(2)
            self.list.turn(-1)
            self.assertEqual(self.sent, [("/t/aux-return.delay.%s.turn" % row, 2),
                                         ("/t/aux-return.delay.%s.turn" % row, -1)], row)

    def test_a_turn_in_edit_does_not_move_the_cursor(self):
        self.edit("feedback")
        self.list.turn(3)
        self.assertEqual(self.list.cursor, 1)
        self.assertEqual(self.views, [])

    def test_no_clicks_send_nothing(self):
        self.edit("beat")
        self.list.turn(0)
        self.assertEqual(self.sent, [])


class CueRow(ListFixture):
    PUSH = ("/t/aux-return.stem.push", 1)

    def test_a_right_turn_cues_a_cue_that_is_off(self):
        self.edit("cue")
        self.list.turn(1)
        self.assertEqual(self.sent, [self.PUSH])

    def test_a_right_turn_on_a_cue_that_is_on_sends_nothing(self):
        self.edit("cue")
        self.cue[0] = True
        self.list.turn(1)
        self.assertEqual(self.sent, [])

    def test_a_left_turn_uncues_a_cue_that_is_on(self):
        self.edit("cue")
        self.cue[0] = True
        self.list.turn(-1)
        self.assertEqual(self.sent, [self.PUSH])

    def test_a_left_turn_on_a_cue_that_is_off_sends_nothing(self):
        self.edit("cue")
        self.list.turn(-2)
        self.assertEqual(self.sent, [])

    def test_a_fast_turn_before_the_lamp_answers_sends_one_push(self):
        self.edit("cue")
        self.list.turn(1)
        self.time.advance(0.05)
        self.list.turn(1)
        self.list.turn(2)
        self.assertEqual(self.sent, [self.PUSH])

    def test_once_the_lamp_answered_the_other_way_works(self):
        self.edit("cue")
        self.list.turn(1)
        self.cue[0] = True
        self.time.advance(0.2)
        self.list.turn(-1)
        self.assertEqual(self.sent, [self.PUSH, self.PUSH])

    def test_a_toggle_is_never_resent_blind(self):
        self.edit("cue")
        self.list.turn(1)
        self.time.advance(60)
        self.list.turn(1)
        self.assertEqual(self.sent, [self.PUSH])

    def test_a_lost_push_is_recovered_by_turning_back_and_forth(self):
        self.edit("cue")
        self.list.turn(1)            # the push is lost, the lamp stays off
        self.list.turn(-1)           # the other way: lamp says off already
        self.list.turn(1)
        self.assertEqual(self.sent, [self.PUSH, self.PUSH])

    def test_a_cue_changed_elsewhere_after_an_answered_push_does_not_swallow_a_turn(self):
        self.edit("cue")
        self.list.turn(1)
        self.cue[0] = True           # the lamp answers
        self.answers[0] += 1
        self.cue[0] = False          # the virtual desk uncues
        self.answers[0] += 1
        self.list.turn(1)
        self.assertEqual(self.sent, [self.PUSH, self.PUSH])

    def test_an_unanswered_push_is_still_not_resent_across_a_new_edit_visit(self):
        self.edit("cue")
        self.list.turn(1)
        self.list.press()
        self.list.press()
        self.list.turn(1)
        self.assertEqual(self.sent, [self.PUSH])

    def test_a_press_in_edit_on_cue_sends_nothing(self):
        self.edit("cue")
        self.list.press()
        self.assertEqual(self.sent, [])


class DisplayModuleStandsAlone(unittest.TestCase):
    def test_the_display_module_does_not_import_the_desk_logic(self):
        source = (Path(__file__).resolve().parents[1] / "scripts" / "a3-mixer-set-display"
                  / "display_panel.py").read_text()
        self.assertNotIn("a3_mixer_delay", source)

    def test_its_mode_name_is_the_lists(self):
        import display_panel
        self.assertEqual(display_panel.SELECT_MODE, delay.SELECT)


class Values(unittest.TestCase):
    ALL_NONE = {"beat": None, "feedback": None, "color": None, "spread": None}

    def setUp(self):
        self.shown = []
        self.state = delay.DelayState(
            lambda mode, cursor, values: self.shown.append((mode, cursor, dict(values))))

    def test_no_value_until_core_speaks(self):
        self.state.show_view(delay.SELECT, 0)
        self.assertEqual(self.shown[-1], (delay.SELECT, 0, self.ALL_NONE))

    def test_a_value_is_kept_and_shown_with_the_view(self):
        self.state.set_value("feedback", 0.7)
        self.state.show_view(delay.EDIT, 1)
        self.assertEqual(self.shown[-1][:2], (delay.EDIT, 1))
        self.assertEqual(self.shown[-1][2]["feedback"], 0.7)
        self.assertIsNone(self.shown[-1][2]["beat"])

    def test_a_value_alone_redraws_the_current_view(self):
        self.state.show_view(delay.EDIT, 2)
        self.state.set_value("color", -0.3)
        self.assertEqual(self.shown[-1], (delay.EDIT, 2, dict(self.ALL_NONE, color=-0.3)))

    def test_the_four_values_are_the_delay_rows(self):
        self.assertEqual(delay.VALUE_KEYS, tuple("aux-return.delay." + r for r in delay.DELAY_ROWS))


class TheDisplaysStartLikeTheState(unittest.TestCase):
    def test_the_first_delay_view_is_select_on_beat_with_no_values(self):
        from test_displays import Rig
        displays = Rig().displays()
        self.assertEqual(displays.delay_view,
                         (delay.SELECT, 0, {row: None for row in delay.DELAY_ROWS}))


class ValueAnnouncement(unittest.TestCase):
    def test_a_float_is_a_value(self):
        self.assertEqual(delay.value_announcement((0.25,)), 0.25)
        self.assertEqual(delay.value_announcement((60,)), 60.0)

    def test_damage_is_none(self):
        for args in ((), ("x",), (None,), (float("nan"),), (1, 2), (True,)):
            self.assertIsNone(delay.value_announcement(args), args)


class ReturnEncoderMessages(unittest.TestCase):
    def test_the_return_push_is_the_lists_not_an_immediate_cue(self):
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
        self.assertLess(branch.index("calibration.turned("), branch.index("delay_list.turn("))
        self.assertLess(branch.index("calibration.pushed()"), branch.index("delay_list.press("))

    def test_the_shown_cue_reaches_the_serial_reader(self):
        handler = self.source.split("def cue_handler_return(", 1)[1].split("\n\n", 1)[0]
        self.assertIn("cue_shown.value", handler)
        self.assertIn("cue_shown", self.source.split("def serial_handler(", 1)[1].split(")", 1)[0])

    def test_a_press_edge_toggles_and_a_release_does_nothing(self):
        branch = self.source.split('if mode == "EB"', 1)[1].split("# Buttons", 1)[0]
        self.assertNotIn(".release(", branch)

    def test_a_value_handler_sends_nothing(self):
        handler = self.source.split("def delay_handler(", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("send", handler)
        self.assertNotIn("to_core", handler)


if __name__ == "__main__":
    unittest.main()
