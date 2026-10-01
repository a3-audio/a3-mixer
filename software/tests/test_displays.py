# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live displays, with the hardware faked: one device per panel for the
life of the process, rebuilt only after a failure, and nothing raised.

Since 2026-10-01 the OSC thread only posts what to show; drawing happens on a
thread of its own, and a panel shows the latest of what was posted -- a fast
spin used to queue one full draw per click behind the meters. Tests call
drain() to draw what is posted, the live desk runs it on start()."""

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_displays import DrawTimer, Displays, Multiplexer
from a3_mixer_levels import LevelGate


class Rig:
    def __init__(self):
        self.selected = []
        self.built = []
        self.drawn = []
        self.fail_draw = False
        self.reports = []

    def select(self, multiplexer, channel):
        self.selected.append(channel)

    def make_device(self, panel):
        device = type("Device", (), {"persist": False, "width": 128, "height": 64})()
        self.built.append((panel.label, device))
        return device

    def draw(self, device, squares):
        if self.fail_draw:
            raise OSError("nack")
        self.drawn.append((device, squares))

    def displays(self, **options):
        return Displays(self.select, self.make_device, self.draw, self.reports.append,
                        **options)


class OneDevicePerPanel(unittest.TestCase):
    def test_two_draws_build_the_device_once(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.drain()
        displays.show_channel(0, 2)
        displays.drain()
        self.assertEqual(1, len(rig.built))
        self.assertEqual(2, len(rig.drawn))

    def test_the_device_persists_past_exit(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.drain()
        self.assertTrue(rig.built[0][1].persist)

    def test_the_multiplexer_is_selected_before_every_draw(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.drain()
        displays.show_channel(0, 2)
        displays.drain()
        displays.show_return(1, (True,) * 8)
        displays.drain()
        self.assertEqual([2, 2, 6], rig.selected)

    def test_each_panel_has_its_own_device(self):
        rig = Rig()
        displays = rig.displays()
        displays.blank_all()
        displays.drain()
        self.assertEqual(5, len(rig.built))


class LatestWins(unittest.TestCase):
    def test_posting_draws_nothing_yet(self):
        rig = Rig()
        rig.displays().show_channel(0, 1)
        self.assertEqual([], rig.drawn)

    def test_a_fast_spin_is_one_draw_of_where_it_ended(self):
        rig = Rig()
        displays = rig.displays()
        for pair in (1, 2, 3, 4):
            displays.show_channel(0, pair)
        displays.drain()
        self.assertEqual(1, len(rig.drawn))
        self.assertEqual([s.filled for s in rig.drawn[0][1]].index(True), 3)

    def test_each_panel_keeps_its_own_latest(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.show_return(2, (True,) * 8)
        displays.show_channel(0, 2)
        displays.drain()
        self.assertEqual(2, len(rig.drawn))

    def test_the_thread_draws_what_is_posted(self):
        rig = Rig()
        drawn = threading.Event()
        draw = rig.draw
        rig.draw = lambda device, squares: (draw(device, squares), drawn.set())
        displays = rig.displays()
        displays.start()
        displays.show_channel(0, 1)
        self.assertTrue(drawn.wait(2.0))


class WhatIsDrawn(unittest.TestCase):
    def test_the_squares_are_sized_to_the_device(self):
        rig = Rig()
        rig.make_device = lambda panel: type(
            "Device", (), {"persist": False, "width": 128, "height": 32})()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.drain()
        device, squares = rig.drawn[-1]
        self.assertTrue(all(s.box[3] < 32 for s in squares))
        self.assertTrue(squares[0].filled)

    def test_the_return_shows_its_cursor(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_return(3, (True,) * 8)
        displays.drain()
        device, squares = rig.drawn[-1]
        self.assertEqual([bool(s.mark) for s in squares].index(True), 2)


class AfterAFailure(unittest.TestCase):
    def test_a_failed_draw_drops_the_device_and_the_next_rebuilds(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.drain()
        rig.fail_draw = True
        displays.show_channel(0, 2)
        displays.drain()
        rig.fail_draw = False
        displays.show_channel(0, 3)
        displays.drain()
        self.assertEqual(2, len(rig.built))
        filled = [s.filled for s in rig.drawn[-1][1]]
        self.assertEqual(filled.index(True), 2)   # pair 3 drawn after the rebuild

    def test_a_failure_never_raises_and_is_reported_once(self):
        rig = Rig()
        displays = rig.displays()
        rig.fail_draw = True
        displays.show_channel(1, 1)
        displays.drain()
        displays.show_channel(1, 2)
        displays.drain()
        self.assertEqual(1, len(rig.reports))


class TryingAgain(unittest.TestCase):
    """A failed draw is tried again a little later with the panel's latest
    picture -- not left until the panel next changes."""

    def test_a_failed_draw_is_tried_again_later(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        rig.fail_draw = True
        displays.show_channel(0, 3)
        displays.drain()
        self.assertEqual(1, len(scheduled))
        rig.fail_draw = False
        scheduled[0][1]()
        displays.drain()
        self.assertEqual([s.filled for s in rig.drawn[-1][1]].index(True), 2)

    def test_the_retry_draws_what_was_posted_since(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        rig.fail_draw = True
        displays.show_channel(0, 3)
        displays.drain()
        rig.fail_draw = False
        displays.show_channel(0, 5)
        displays.drain()
        scheduled[0][1]()
        displays.drain()
        self.assertEqual([s.filled for s in rig.drawn[-1][1]].index(True), 4)

    def test_a_good_draw_schedules_nothing(self):
        rig, scheduled = Rig(), []
        displays = rig.displays(later=lambda seconds, then: scheduled.append((seconds, then)))
        displays.show_channel(0, 3)
        displays.drain()
        self.assertEqual([], scheduled)


class Levels(unittest.TestCase):
    """The stem levels (issue a3-system#71): noted cheaply on the OSC thread,
    drawn through a gate -- at most every 0.1 s and only on a step change --
    while a turn of the encoder still draws at once."""

    def setUp(self):
        self.now = 0.0
        self.rig = Rig()
        self.displays = self.rig.displays(
            gate=LevelGate(interval=0.1, clock=lambda: self.now))
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def drawn_on(self, label):
        device = next(d for name, d in self.rig.built if name == label)
        return [squares for d, squares in self.rig.drawn if d is device]

    def test_a_level_redraws_every_display(self):
        self.displays.note_level(1, 3)
        self.displays.drain()
        self.assertEqual(5, len(self.rig.drawn))
        self.assertTrue(all(squares[0].bar for _, squares in self.rig.drawn))

    def test_levels_wait_for_the_gate(self):
        self.displays.note_level(1, 3)
        self.displays.drain()
        self.rig.drawn.clear()
        self.now = 0.05
        self.displays.note_level(1, 5)
        self.displays.drain()
        self.assertEqual([], self.rig.drawn)
        self.now = 0.2
        self.displays.drain()
        self.assertEqual(5, len(self.rig.drawn))

    def test_noting_a_level_draws_nothing_by_itself(self):
        self.displays.note_level(1, 3)
        self.assertEqual([], self.rig.drawn)

    def test_a_turn_is_not_held_back_by_the_gate(self):
        self.displays.note_level(1, 3)
        self.displays.drain()
        self.rig.drawn.clear()
        self.now = 0.01
        self.displays.show_channel(0, 2)
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        squares = self.rig.drawn[0][1]
        self.assertTrue(squares[1].filled)
        self.assertTrue(squares[0].bar)   # still with the level

    def test_a_turn_during_a_level_batch_goes_first(self):
        """A level batch redraws all five displays (~150 ms on the desk); a
        turn arriving meanwhile is drawn next, not after the batch."""
        order = []
        labels = {id(device): name for name, device in self.rig.built}
        draw = self.rig.draw

        def draw_and_turn(device, squares):
            draw(device, squares)
            order.append(labels[id(device)])
            if len(order) == 1:
                self.displays.show_channel(3, 5)   # Deck 4, last in the table

        self.rig.draw = draw_and_turn
        self.displays._draw_squares = draw_and_turn
        self.displays.note_level(1, 3)
        self.displays.drain()
        self.assertEqual(order, ["Deck 1", "Deck 4", "Deck 2", "Deck 3", "Aux Return"])
        last_deck_four = self.drawn_on("Deck 4")[-1]
        self.assertTrue(last_deck_four[4].filled and last_deck_four[0].bar)

    def test_the_square_state_survives_a_level_redraw(self):
        self.displays.show_channel(0, 3)
        self.displays.show_return(2, (True,) * 8)
        self.displays.drain()
        self.displays.note_level(1, 2)
        self.displays.drain()
        self.assertTrue(self.drawn_on("Deck 1")[-1][2].filled)
        self.assertTrue(self.drawn_on("Aux Return")[-1][1].mark)


class TheCueField(unittest.TestCase):
    """C on every display (2026-10-01): a channel's cue, the stem cue on the
    aux return -- drawn from what Core says, like the stems."""

    def setUp(self):
        self.rig = Rig()
        self.displays = self.rig.displays()
        self.displays.blank_all()
        self.displays.drain()
        self.rig.drawn.clear()

    def test_a_channels_cue_fills_its_c(self):
        self.displays.show_cue(1, True)
        self.displays.drain()
        self.assertEqual(1, len(self.rig.drawn))
        self.assertTrue(self.rig.drawn[0][1][9].filled)

    def test_the_stem_cue_fills_the_returns_c(self):
        self.displays.show_stem_cue(True)
        self.displays.drain()
        self.assertTrue(self.rig.drawn[0][1][8].filled)

    def test_the_cue_survives_a_stem_change(self):
        self.displays.show_cue(0, True)
        self.displays.show_channel(0, 3)
        self.displays.drain()
        self.assertTrue(self.rig.drawn[-1][1][9].filled)


class HowLongADrawTakes(unittest.TestCase):
    """One journal line per batch of draws, so the bus speed is measured on
    the desk instead of guessed."""

    def test_a_line_after_every_batch(self):
        timer = DrawTimer(every=3)
        self.assertIsNone(timer.record(0.010))
        self.assertIsNone(timer.record(0.020))
        self.assertEqual(timer.record(0.030),
                         "displays: 3 draws, mean 20.0 ms, max 30.0 ms")

    def test_each_batch_starts_afresh(self):
        timer = DrawTimer(every=2)
        timer.record(0.100)
        timer.record(0.100)
        timer.record(0.004)
        self.assertEqual(timer.record(0.006),
                         "displays: 2 draws, mean 5.0 ms, max 6.0 ms")

    def test_the_displays_report_it(self):
        rig = Rig()
        ticks = iter([0.0, 0.012, 1.0, 1.020])
        displays = rig.displays(clock=lambda: next(ticks), every=2)
        displays.show_channel(0, 1)
        displays.drain()
        displays.show_channel(1, 1)
        displays.drain()
        self.assertEqual(rig.reports, ["displays: 2 draws, mean 16.0 ms, max 20.0 ms"])


class TheMultiplexer(unittest.TestCase):
    """One open bus, one byte per select: no new SMBus, no 1 ms sleep, no
    read-back and no journal line per draw, as TCA9548A.I2C_setup does."""

    class Bus:
        def __init__(self, log, fail=False):
            self.log, self.fail = log, fail

        def write_byte(self, address, value):
            if self.fail:
                raise OSError("nack")
            self.log.append((address, value))

        def close(self):
            self.log.append("closed")

    def test_the_bus_is_opened_once(self):
        log, opened = [], []
        mux = Multiplexer(lambda: opened.append(1) or self.Bus(log))
        mux(0x70, 2)
        mux(0x70, 6)
        self.assertEqual(1, len(opened))
        self.assertEqual(log, [(0x70, 0b100), (0x70, 0b1000000)])

    def test_a_failed_select_reopens_the_bus_next_time(self):
        log, buses = [], [self.Bus([], fail=True)]
        mux = Multiplexer(lambda: buses.pop(0) if buses else self.Bus(log))
        with self.assertRaises(OSError):
            mux(0x70, 2)
        mux(0x70, 3)
        self.assertEqual(log, [(0x70, 0b1000)])


if __name__ == "__main__":
    unittest.main()
