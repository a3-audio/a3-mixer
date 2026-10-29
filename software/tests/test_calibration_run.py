# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Calibrating the desk: the order the controls are asked for, what a push,
a turn and the FX keys do, and that nothing half-calibrated reaches Core."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_calibration import Calibration, Range  # noqa: E402
from a3_mixer_calibration_run import (CANCELLED, CENTRE_END, CONTROLS, DONE,  # noqa: E402
                                      DOWN, RUNNING, START_HOLD_SECONDS, UP,
                                      CalibrationRun, DeskCalibration, address_of,
                                      steps_of)
from a3_mixer_osc import CHANNEL_POTS, MASTER_POTS  # noqa: E402
from test_osc_truth import made_up  # noqa: E402


def control(control_id):
    return next(c for c in CONTROLS if c.id == control_id)


def every_reading(counts=500):
    return {c.id: counts for c in CONTROLS}


class Order(unittest.TestCase):
    def test_every_pot_and_fader_of_the_desk_is_asked_for(self):
        expected = {f"{track}:{index}" for track in "0123" for index in CHANNEL_POTS} \
            | {f"master:{index}" for index in MASTER_POTS}
        self.assertEqual({c.id for c in CONTROLS}, expected)
        self.assertEqual(len(CONTROLS), len(expected))

    def test_channel_by_channel_then_the_master_section(self):
        panels = [c.panel for c in CONTROLS]
        self.assertEqual(panels, sorted(panels))
        self.assertEqual(CONTROLS[0].title, "CH1 GAIN")
        self.assertEqual(CONTROLS[-1].panel, 4)

    def test_up_then_down_so_every_control_ends_at_rest(self):
        # The last step of a control leaves it where it is safe to send:
        # a fader down, an EQ at its detent.
        steps = steps_of(CONTROLS)
        self.assertEqual([s.end for s in steps[:2]], [UP, DOWN])
        fader = [s.end for s in steps if s.control.id == "0:5"]
        self.assertEqual(fader, [UP, DOWN])

    def test_only_the_eq_has_a_centre_step(self):
        centred = {c.id for c in CONTROLS if c.centre}
        self.assertEqual(centred, {f"{t}:{i}" for t in "0123" for i in ("2", "3", "4")})
        eq = [s.end for s in steps_of(CONTROLS) if s.control.id == "0:2"]
        self.assertEqual(eq, [UP, DOWN, CENTRE_END])


class Addresses(unittest.TestCase):
    """A control's id to the address its value goes to -- the same for a
    moved pot and for the values sent once after a calibration."""

    def test_a_channel_control(self):
        osc = made_up()
        self.assertEqual(address_of(osc, "0:5"), osc.channel_address("channel.volume", 0))
        self.assertEqual(address_of(osc, "3:2"), osc.channel_address("channel.eq.high", 3))

    def test_a_master_control(self):
        osc = made_up()
        self.assertEqual(address_of(osc, "master:0"), osc.address("master.volume"))

    def test_an_unmapped_pot_has_none(self):
        for unmapped in ("0:7", "master:7", "fx:0", "5:1", "nonsense"):
            self.assertIsNone(address_of(made_up(), unmapped), unmapped)


class Run(unittest.TestCase):
    def setUp(self):
        self.readings = every_reading()
        self.run = CalibrationRun(Calibration(), self.readings)

    def walk_fader(self, control_id, low, high):
        while self.run.step.control.id != control_id:
            self.run.skip()
        self.run.feed(control_id, high)
        self.run.take()
        self.run.feed(control_id, low)
        self.run.take()

    def test_starts_at_the_first_control_going_up(self):
        self.assertEqual(self.run.step.control, CONTROLS[0])
        self.assertEqual(self.run.step.end, UP)
        self.assertEqual(self.run.state, RUNNING)

    def test_up_takes_the_highest_reading_of_the_step(self):
        # The hand lets go and the reading drops back: the end is the most.
        for counts in (700, 1019, 1012):
            self.run.feed("0:1", counts)
        self.run.take()
        for counts in (300, 2, 9):
            self.run.feed("0:1", counts)
        self.run.take()
        self.assertEqual(self.run.result()[0].range_of("0:1"), Range(2, 1019))

    def test_a_control_already_at_its_end_is_taken_as_it_stands(self):
        self.readings["0:1"] = 1020
        run = CalibrationRun(Calibration(), self.readings)
        run.take()
        run.feed("0:1", 3)
        run.take()
        self.assertEqual(run.result()[0].range_of("0:1"), Range(3, 1020))

    def test_another_control_moving_does_not_count(self):
        self.run.feed("0:5", 1022)
        self.run.feed("0:1", 900)
        self.run.take()
        self.run.feed("0:1", 10)
        self.run.take()
        self.assertEqual(self.run.result()[0].range_of("0:1"), Range(10, 900))

    def test_without_any_reading_a_push_takes_nothing(self):
        run = CalibrationRun(Calibration(), {})
        self.assertFalse(run.take())
        self.assertEqual(run.step.end, UP)

    def test_the_centre_is_where_the_pot_rests(self):
        self.walk_fader("0:2", 4, 1014)
        self.assertEqual(self.run.step.end, CENTRE_END)
        for counts in (600, 530, 518):
            self.run.feed("0:2", counts)
        self.run.take()
        self.assertEqual(self.run.result()[0].range_of("0:2"), Range(4, 1014, 518))

    def test_a_skipped_centre_means_no_detent(self):
        before = Calibration({"0:2": Range(4, 1014, 518)})
        run = CalibrationRun(before, self.readings)
        while run.step.control.id != "0:2":
            run.skip()
        run.skip()
        run.skip()
        run.skip()
        self.assertEqual(run.result()[0].range_of("0:2"), Range(4, 1014))

    def test_a_skipped_end_keeps_the_stored_one(self):
        before = Calibration({"0:1": Range(5, 1000)})
        run = CalibrationRun(before, self.readings)
        run.skip()
        run.feed("0:1", 1)
        run.take()
        self.assertEqual(run.result()[0].range_of("0:1"), Range(1, 1000))

    def test_back_asks_for_the_step_before_again(self):
        self.run.feed("0:1", 1000)
        self.run.take()
        self.run.back()
        self.assertEqual((self.run.step.control.id, self.run.step.end), ("0:1", UP))
        self.run.back()
        self.assertEqual(self.run.number(), 1)

    def test_the_last_step_ends_the_run(self):
        while self.run.state == RUNNING:
            self.run.take()
        self.assertEqual(self.run.state, DONE)
        self.assertIsNone(self.run.step)

    def test_cancel(self):
        self.run.cancel()
        self.assertEqual(self.run.state, CANCELLED)

    def test_a_narrow_span_is_refused_and_the_stored_one_kept(self):
        before = Calibration({"0:1": Range(5, 1000)})
        run = CalibrationRun(before, self.readings)
        run.feed("0:1", 600)
        run.take()
        run.feed("0:1", 400)
        run.take()
        calibration, refused = run.result()
        self.assertEqual(calibration.range_of("0:1"), Range(5, 1000))
        self.assertEqual(refused, ["0:1"])

    def test_a_centre_outside_the_span_is_dropped(self):
        self.walk_fader("0:2", 100, 900)
        self.run.feed("0:2", 1010)
        self.run.take()
        self.assertEqual(self.run.result()[0].range_of("0:2"), Range(100, 900))


class View(unittest.TestCase):
    def test_the_view_names_the_control_and_the_end(self):
        run = CalibrationRun(Calibration(), every_reading())
        view = run.view()
        self.assertEqual((view.state, view.panel, view.title, view.end),
                         (RUNNING, 0, "CH1 GAIN", UP))
        self.assertEqual((view.number, view.total), (1, len(steps_of(CONTROLS))))

    def test_the_reading_of_the_asked_control_is_shown(self):
        run = CalibrationRun(Calibration(), every_reading(0))
        run.feed("0:1", 1023)
        self.assertEqual(run.view().reading, 1.0)

    def test_marks_done_current_and_todo(self):
        run = CalibrationRun(Calibration(), every_reading())
        run.take()
        run.take()
        marks = run.view().marks
        self.assertEqual(len(marks), 5)
        self.assertEqual(marks[0][0], ("GAIN", "done"))
        self.assertEqual(marks[0][1], ("HIGH", "current"))
        self.assertEqual(marks[0][2][1], "todo")
        self.assertEqual(len(marks[4]), len(MASTER_POTS))


class Rig:
    def __init__(self, calibration=None):
        self.now = 100.0
        self.saved = []
        self.shown = []
        self.resent = []
        self.lines = []
        self.desk = DeskCalibration(calibration or Calibration(), self.saved.append,
                                    self.shown.append, self.resent.append,
                                    self.lines.append, clock=lambda: self.now)

    def chord(self, held):
        self.desk.fx_key("0", True)
        self.desk.fx_key("1", True)
        self.now += held
        self.desk.fx_key("0", False)
        self.desk.fx_key("1", False)


class Desk(unittest.TestCase):
    def test_outside_a_calibration_a_pot_is_sent_calibrated(self):
        rig = Rig()
        self.assertEqual(rig.desk.pot("0:5", 1), 0.0)
        self.assertEqual(rig.desk.pot("0:5", 1021), 1.0)

    def test_both_fx_keys_held_three_seconds_start_it(self):
        rig = Rig()
        rig.chord(START_HOLD_SECONDS)
        self.assertTrue(rig.desk.active)
        self.assertEqual(rig.shown[-1].state, RUNNING)

    def test_a_short_chord_starts_nothing(self):
        rig = Rig()
        rig.chord(START_HOLD_SECONDS - 0.5)
        self.assertFalse(rig.desk.active)

    def test_one_fx_key_held_long_starts_nothing(self):
        rig = Rig()
        rig.desk.fx_key("0", True)
        rig.now += 10
        rig.desk.fx_key("0", False)
        self.assertFalse(rig.desk.active)

    def test_the_fx_keys_still_play_outside_a_calibration(self):
        rig = Rig()
        self.assertFalse(rig.desk.fx_key("0", True))

    def test_nothing_is_sent_while_calibrating(self):
        rig = Rig()
        rig.desk.start()
        self.assertIsNone(rig.desk.pot("0:1", 1020))
        self.assertIsNone(rig.desk.pot("0:5", 3))

    def test_a_push_takes_and_a_turn_skips_or_goes_back(self):
        rig = Rig()
        rig.desk.pot("0:1", 1020)
        rig.desk.start()
        rig.desk.pushed()
        self.assertEqual(rig.shown[-1].end, DOWN)
        rig.desk.turned(-1)
        self.assertEqual(rig.shown[-1].end, UP)
        rig.desk.turned(2)
        self.assertEqual(rig.shown[-1].end, DOWN)

    def test_an_fx_key_cancels_and_keeps_the_old_calibration(self):
        old = Calibration({"0:1": Range(5, 1000)})
        rig = Rig(old)
        rig.desk.pot("0:1", 600)
        rig.desk.start()
        rig.desk.pot("0:1", 1020)
        rig.desk.pushed()
        self.assertTrue(rig.desk.fx_key("1", True))
        self.assertFalse(rig.desk.active)
        self.assertEqual(rig.shown[-1].state, CANCELLED)
        self.assertEqual(rig.saved, [])
        self.assertEqual(rig.desk.calibration.range_of("0:1"), Range(5, 1000))

    def test_the_start_chords_own_release_does_not_cancel(self):
        rig = Rig()
        rig.desk.fx_key("0", True)
        rig.desk.fx_key("1", True)
        rig.now += START_HOLD_SECONDS
        rig.desk.fx_key("0", False)
        self.assertTrue(rig.desk.active)
        self.assertTrue(rig.desk.fx_key("1", False))
        self.assertTrue(rig.desk.active)

    def test_after_a_cancel_the_current_values_go_out_once(self):
        rig = Rig()
        rig.desk.pot("0:5", 600)
        rig.desk.start()
        rig.desk.pot("0:5", 2)
        rig.desk.fx_key("0", True)
        self.assertEqual(rig.resent, [{"0:5": 0.0}])

    def test_done_saves_applies_and_sends_every_value_once(self):
        rig = Rig()
        for c in CONTROLS:
            rig.desk.pot(c.id, 512)
        rig.desk.start()
        while rig.desk.active:
            step = rig.desk.step
            rig.desk.pot(step.control.id, {UP: 900, DOWN: 100, CENTRE_END: 500}[step.end])
            rig.desk.pushed()
        self.assertEqual(rig.shown[-1].state, DONE)
        self.assertEqual(len(rig.saved), 1)
        self.assertEqual(rig.saved[0].range_of("0:5"), Range(100, 900))
        self.assertEqual(rig.desk.calibration.range_of("0:2"), Range(100, 900, 500))
        self.assertEqual(len(rig.resent), 1)
        self.assertEqual(set(rig.resent[0]), {c.id for c in CONTROLS})
        self.assertEqual(rig.resent[0]["0:5"], 0.0)    # a fader ends down
        self.assertEqual(rig.resent[0]["0:2"], 0.5)    # an EQ at its detent

    def test_a_failed_save_still_applies_and_says_so(self):
        rig = Rig()

        def refuse(calibration):
            raise OSError("read-only")

        rig.desk = DeskCalibration(Calibration(), refuse, rig.shown.append,
                                   rig.resent.append, rig.lines.append,
                                   clock=lambda: rig.now)
        rig.desk.start()
        while rig.desk.active:
            rig.desk.pot(rig.desk.step.control.id,
                         {UP: 900, DOWN: 100, CENTRE_END: 500}[rig.desk.step.end])
            rig.desk.pushed()
        self.assertEqual(rig.desk.calibration.range_of("0:5"), Range(100, 900))
        self.assertTrue(any("not saved" in line for line in rig.lines))

    def test_a_turn_or_push_outside_a_calibration_is_not_taken(self):
        rig = Rig()
        self.assertFalse(rig.desk.pushed())
        self.assertFalse(rig.desk.turned(1))
        self.assertEqual(rig.shown, [])


if __name__ == "__main__":
    unittest.main()
