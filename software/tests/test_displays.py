# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live displays, with the hardware faked: one device per panel for the
life of the process, rebuilt only after a failure, and nothing raised."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_displays import Displays


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

    def displays(self):
        return Displays(self.select, self.make_device, self.draw, self.reports.append)


class OneDevicePerPanel(unittest.TestCase):
    def test_two_draws_build_the_device_once(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.show_channel(0, 2)
        self.assertEqual(1, len(rig.built))
        self.assertEqual(2, len(rig.drawn))

    def test_the_device_persists_past_exit(self):
        rig = Rig()
        rig.displays().show_channel(0, 1)
        self.assertTrue(rig.built[0][1].persist)

    def test_the_multiplexer_is_selected_before_every_draw(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        displays.show_channel(0, 2)
        displays.show_return(1, (True,) * 8)
        self.assertEqual([2, 2, 6], rig.selected)

    def test_each_panel_has_its_own_device(self):
        rig = Rig()
        rig.displays().blank_all()
        self.assertEqual(5, len(rig.built))


class WhatIsDrawn(unittest.TestCase):
    def test_the_squares_are_sized_to_the_device(self):
        rig = Rig()
        rig.make_device = lambda panel: type(
            "Device", (), {"persist": False, "width": 128, "height": 32})()
        rig.displays().show_channel(0, 1)
        device, squares = rig.drawn[-1]
        self.assertTrue(all(s.box[3] < 32 for s in squares))
        self.assertTrue(squares[0].filled)

    def test_the_return_shows_its_cursor(self):
        rig = Rig()
        rig.displays().show_return(3, (True,) * 8)
        device, squares = rig.drawn[-1]
        self.assertEqual([bool(s.frame) for s in squares].index(True), 2)


class AfterAFailure(unittest.TestCase):
    def test_a_failed_draw_drops_the_device_and_the_next_rebuilds(self):
        rig = Rig()
        displays = rig.displays()
        displays.show_channel(0, 1)
        rig.fail_draw = True
        displays.show_channel(0, 2)
        rig.fail_draw = False
        displays.show_channel(0, 3)
        self.assertEqual(2, len(rig.built))
        filled = [s.filled for s in rig.drawn[-1][1]]
        self.assertEqual(filled.index(True), 2)   # pair 3 drawn after the rebuild

    def test_a_failure_never_raises_and_is_reported_once(self):
        rig = Rig()
        displays = rig.displays()
        rig.fail_draw = True
        displays.show_channel(1, 1)
        displays.show_channel(1, 2)
        self.assertEqual(1, len(rig.reports))


if __name__ == "__main__":
    unittest.main()
