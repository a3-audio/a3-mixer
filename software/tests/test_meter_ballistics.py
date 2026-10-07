# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""One meter behaviour everywhere (decided 2026-10-07): the sources send raw
peaks, every display applies the same ballistics -- an instant rise, a fall
of 20 dB/s, the highest recent peak held 1.5 s and then falling at the same
rate. The numbers are Core's, in the truth's "meters" block; without it the
desk uses the same three as defaults."""

import sys
import unittest
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE / "scripts"))

from a3_mixer_meters import (DEFAULT_METER_TIMING, METER_FLOOR_DB,  # noqa: E402
                             MeterBallistics, MeterTiming, peak_db)
from a3_mixer_osc import MetersRefused  # noqa: E402
from test_osc_truth import made_up  # noqa: E402

#: The desk's clock counts from the Pi's boot: a meter must not care where
#: its clock starts (feedback desk-library-and-clock-traps).
BOOT = 86_400.0


class Clock:
    def __init__(self, at=BOOT):
        self.now = at

    def __call__(self):
        return self.now


def ballistics(timing=DEFAULT_METER_TIMING):
    clock = Clock()
    return MeterBallistics(timing, clock), clock


class TheNumbers(unittest.TestCase):
    def test_the_defaults_are_the_agreed_ones(self):
        self.assertEqual(DEFAULT_METER_TIMING, MeterTiming(attack_ms=0.0,
                                                           release_db_per_second=20.0,
                                                           peak_hold_seconds=1.5))


class TheBar(unittest.TestCase):
    def test_a_rise_is_immediate(self):
        meter, _ = ballistics()
        self.assertEqual(meter.feed(-6.0).level_db, -6.0)

    def test_the_first_feed_shows_its_peak_whatever_the_clock_says(self):
        meter, clock = ballistics()
        clock.now = 12_345_678.9
        self.assertEqual(meter.feed(-12.0).level_db, -12.0)

    def test_it_falls_twenty_db_a_second(self):
        meter, clock = ballistics()
        meter.feed(0.0)
        clock.now += 0.5
        self.assertAlmostEqual(meter.feed(METER_FLOOR_DB).level_db, -10.0)
        clock.now += 0.5
        self.assertAlmostEqual(meter.feed(METER_FLOOR_DB).level_db, -20.0)

    def test_the_fall_does_not_depend_on_how_often_it_is_fed(self):
        coarse, coarse_clock = ballistics()
        fine, fine_clock = ballistics()
        coarse.feed(0.0)
        fine.feed(0.0)
        coarse_clock.now += 1.0
        for _ in range(25):
            fine_clock.now += 0.04
            shown = fine.feed(METER_FLOOR_DB).level_db
        self.assertAlmostEqual(coarse.feed(METER_FLOOR_DB).level_db, shown)

    def test_it_stops_at_the_level_it_is_fed(self):
        meter, clock = ballistics()
        meter.feed(0.0)
        clock.now += 3.0
        self.assertEqual(meter.feed(-24.0).level_db, -24.0)

    def test_it_never_falls_below_the_floor(self):
        meter, clock = ballistics()
        meter.feed(0.0)
        clock.now += 60.0
        self.assertEqual(meter.feed(METER_FLOOR_DB).level_db, METER_FLOOR_DB)

    def test_a_clock_that_steps_back_is_no_time(self):
        meter, clock = ballistics()
        meter.feed(-3.0)
        clock.now -= 5.0
        self.assertEqual(meter.feed(METER_FLOOR_DB).level_db, -3.0)

    def test_an_attack_time_spreads_the_rise(self):
        meter, clock = ballistics(MeterTiming(attack_ms=100.0))
        meter.feed(-40.0)
        clock.now += 0.2
        self.assertEqual(meter.feed(-40.0).level_db, -40.0)
        clock.now += 0.05
        self.assertAlmostEqual(meter.feed(0.0).level_db, -20.0 - 0.5 * 1.0, places=6)
        clock.now += 0.2
        self.assertEqual(meter.feed(0.0).level_db, 0.0)

    def test_the_release_is_the_timings(self):
        meter, clock = ballistics(MeterTiming(release_db_per_second=10.0))
        meter.feed(0.0)
        clock.now += 1.0
        self.assertAlmostEqual(meter.feed(METER_FLOOR_DB).level_db, -10.0)


class TheHold(unittest.TestCase):
    def test_the_peak_is_held_one_and_a_half_seconds(self):
        meter, clock = ballistics()
        meter.feed(-6.0)
        clock.now += 1.5
        reading = meter.feed(METER_FLOOR_DB)
        self.assertEqual(reading.hold_db, -6.0)
        self.assertAlmostEqual(reading.level_db, -36.0)

    def test_then_it_falls_twenty_db_a_second(self):
        meter, clock = ballistics()
        meter.feed(-6.0)
        clock.now += 2.0
        self.assertAlmostEqual(meter.feed(METER_FLOOR_DB).hold_db, -16.0)

    def test_a_new_peak_above_it_restarts_the_hold(self):
        meter, clock = ballistics()
        meter.feed(-12.0)
        clock.now += 1.0
        meter.feed(-6.0)
        clock.now += 1.4
        self.assertEqual(meter.feed(METER_FLOOR_DB).hold_db, -6.0)

    def test_a_peak_below_it_does_not(self):
        meter, clock = ballistics()
        meter.feed(-6.0)
        clock.now += 1.0
        meter.feed(-12.0)
        clock.now += 0.7
        self.assertAlmostEqual(meter.feed(METER_FLOOR_DB).hold_db, -10.0)

    def test_a_peak_above_the_falling_hold_restarts_it(self):
        meter, clock = ballistics()
        meter.feed(-6.0)
        clock.now += 2.5                 # held -6, fallen to -26
        meter.feed(-20.0)
        clock.now += 1.0
        self.assertEqual(meter.feed(METER_FLOOR_DB).hold_db, -20.0)

    def test_the_hold_is_never_below_the_bar(self):
        meter, clock = ballistics(MeterTiming(attack_ms=100.0))
        reading = meter.feed(-3.0)
        self.assertGreaterEqual(reading.hold_db, reading.level_db)

    def test_the_hold_time_is_the_timings(self):
        meter, clock = ballistics(MeterTiming(peak_hold_seconds=0.5))
        meter.feed(-6.0)
        clock.now += 1.0
        self.assertAlmostEqual(meter.feed(METER_FLOOR_DB).hold_db, -16.0)


class PeakInDb(unittest.TestCase):
    def test_full_scale_is_zero(self):
        self.assertEqual(peak_db(1.0), 0.0)

    def test_silence_and_nonsense_are_the_floor(self):
        for odd in (0.0, -1.0, None, "x", True, float("nan")):
            with self.subTest(odd=odd):
                self.assertEqual(peak_db(odd), METER_FLOOR_DB)


class TheTimingIsCores(unittest.TestCase):
    """Core owns the numbers (maintainer, 2026-10-07): a "meters" block in
    the truth, read by a3-core's rules (a3_osc.Truth.meters). A truth
    without one -- every truth before it -- gets the agreed numbers, so the
    desk works with either Core."""

    def test_without_a_block_the_defaults(self):
        self.assertEqual(made_up().meters(), DEFAULT_METER_TIMING)

    def test_the_block_is_read(self):
        osc = made_up(meters={"attack_ms": 5, "release_db_per_second": 12,
                              "peak_hold_seconds": 2.0})
        self.assertEqual(osc.meters(), MeterTiming(5.0, 12.0, 2.0))

    def test_a_missing_key_is_its_default(self):
        osc = made_up(meters={"release_db_per_second": 30})
        self.assertEqual(osc.meters(), MeterTiming(0.0, 30.0, 1.5))

    def test_underscore_keys_are_comments(self):
        osc = made_up(meters={"_why": "decided 2026-10-07", "peak_hold_seconds": 1})
        self.assertEqual(osc.meters(), MeterTiming(0.0, 20.0, 1.0))

    def test_the_edges_that_are_allowed(self):
        osc = made_up(meters={"attack_ms": 0, "peak_hold_seconds": 0,
                              "release_db_per_second": 0.1})
        self.assertEqual(osc.meters(), MeterTiming(0.0, 0.1, 0.0))

    def test_what_is_refused(self):
        for block in ({"attack_ms": "fast"}, {"peak_hold_seconds": True},
                      {"release_db_per_second": 0}, {"release_db_per_second": -3},
                      {"peak_hold_seconds": -0.1}, {"attack_ms": -1},
                      {"decay": 20}, [1, 2], None):
            with self.subTest(block=block):
                with self.assertRaises(MetersRefused):
                    made_up(meters=block).meters()

    def test_a_refused_block_is_a_lacking_truth(self):
        """The desk then waits for Core's truth instead of crashing into a
        restart loop at its first meter."""
        lacking = made_up(meters={"decay": 20}).missing()
        self.assertEqual(len(lacking), 1)
        self.assertIn("decay", lacking[0])

    def test_the_real_truth_meters(self):
        from test_osc_truth import real_truth_path
        import a3_mixer_osc
        self.assertIsInstance(a3_mixer_osc.load(real_truth_path()).meters(), MeterTiming)


if __name__ == "__main__":
    unittest.main()
