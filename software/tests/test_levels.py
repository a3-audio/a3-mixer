# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A stem's level as one of 6 steps, and a gate that lets the displays redraw
at most 10 times a second and only when a step changed (issue a3-system#71)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_levels import STEPS, LevelGate, level_step  # noqa: E402


class Steps(unittest.TestCase):
    def test_silence_is_no_bar(self):
        self.assertEqual(level_step(0.0), 0)

    def test_full_scale_is_the_last_step(self):
        self.assertEqual(level_step(1.0), STEPS)

    def test_minus_forty_eight_db_is_the_edge(self):
        self.assertEqual(level_step(10 ** (-49 / 20)), 0)
        self.assertEqual(level_step(10 ** (-47 / 20)), 1)

    def test_steps_rise_with_the_level(self):
        steps = [level_step(10 ** (db / 20)) for db in range(-60, 1, 6)]
        self.assertEqual(steps, sorted(steps))

    def test_odd_levels_are_clamped(self):
        self.assertEqual(level_step(4.0), STEPS)
        self.assertEqual(level_step(-1.0), 0)
        self.assertEqual(level_step(float("nan")), 0)
        self.assertEqual(level_step(1e-45), 0)


class Gate(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.gate = LevelGate(interval=0.1, clock=lambda: self.now)

    def test_nothing_changed_nothing_due(self):
        self.assertIsNone(self.gate.due())
        self.assertFalse(self.gate.pending)

    def test_a_change_is_due_at_once_the_first_time(self):
        self.gate.update(3, 2)
        self.assertTrue(self.gate.pending)
        self.assertEqual(self.gate.due()[3], 2)
        self.assertFalse(self.gate.pending)

    def test_a_second_change_waits_for_the_interval(self):
        self.gate.update(3, 2)
        self.gate.due()
        self.now = 0.05
        self.gate.update(3, 4)
        self.assertIsNone(self.gate.due())
        self.now = 0.11
        self.assertEqual(self.gate.due()[3], 4)

    def test_the_same_step_again_is_no_change(self):
        self.gate.update(3, 2)
        self.gate.due()
        self.now = 1.0
        self.gate.update(3, 2)
        self.assertIsNone(self.gate.due())

    def test_all_eight_pairs_are_handed_out(self):
        self.gate.update(1, 1)
        self.assertEqual(sorted(self.gate.due()), list(range(1, 9)))


class OneCountOfSteps(unittest.TestCase):
    def test_the_bar_knows_the_same_steps(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"
                               / "a3-mixer-set-display"))
        from display_panel import LEVEL_STEPS
        self.assertEqual(LEVEL_STEPS, STEPS)


if __name__ == "__main__":
    unittest.main()
