# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A pot's reading to the value on the wire: dead zones at both ends, the
calibrated span between them, an optional centre; and the file it lives in.

Measured on the rig (2026-10-29): a fader pulled down sent 0.000978 (one
count), which the engine played at about -66 dB -- signal on the phones with
every fader down."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_calibration import (CENTRE, DEAD_ZONE, FULL_SCALE, MIN_SPAN,  # noqa: E402
                                  Calibration, Range, calibrated,
                                  calibration_path, counts_of, load, save)


class Counts(unittest.TestCase):
    def test_the_panels_lowest_reading_is_one_count(self):
        self.assertEqual(counts_of("0.000978"), 1)

    def test_full_scale(self):
        self.assertEqual(counts_of("1.000000"), FULL_SCALE)

    def test_a_damaged_field_is_none(self):
        for damaged in ("", "0.5x", "nan", "-", "inf"):
            self.assertIsNone(counts_of(damaged), damaged)

    def test_out_of_range_is_held_to_the_scale(self):
        self.assertEqual(counts_of("1.2"), FULL_SCALE)
        self.assertEqual(counts_of("-0.1"), 0)


class DeadZones(unittest.TestCase):
    """Without a calibration the raw 0..1023 range, dead zones included:
    down is off from day one."""

    def test_the_lowest_reading_is_exactly_zero(self):
        self.assertEqual(calibrated(1), 0.0)

    def test_the_whole_low_zone_is_zero(self):
        zone = int(DEAD_ZONE * FULL_SCALE)
        self.assertEqual(calibrated(zone), 0.0)
        self.assertGreater(calibrated(zone + 2), 0.0)

    def test_the_low_zone_swallows_the_firmwares_deadband(self):
        # The panel sends a pot only after a 12-count move, so the last
        # value on the way down can stand 12 counts over the true bottom;
        # measured bottoms on the desk reach 8.
        self.assertEqual(calibrated(8 + 12), 0.0)

    def test_the_top_reaches_one(self):
        # Measured tops on the desk: 1014-1022, never 1023.
        self.assertEqual(calibrated(1014), 1.0)

    def test_linear_between_and_centred(self):
        self.assertAlmostEqual(calibrated(FULL_SCALE / 2), 0.5, places=6)
        self.assertLess(calibrated(400), calibrated(401))

    def test_never_outside_zero_to_one(self):
        for counts in (-50, 0, 2000):
            self.assertTrue(0.0 <= calibrated(counts) <= 1.0)


class Calibrated(unittest.TestCase):
    def test_the_calibrated_ends_are_zero_and_one(self):
        span = Range(low=40, high=900)
        self.assertEqual(calibrated(40, span), 0.0)
        self.assertEqual(calibrated(900, span), 1.0)
        self.assertEqual(calibrated(30, span), 0.0)
        self.assertEqual(calibrated(950, span), 1.0)

    def test_the_dead_zone_is_a_share_of_the_calibrated_span(self):
        span = Range(low=100, high=700)
        zone = DEAD_ZONE * 600
        self.assertEqual(calibrated(100 + zone, span), 0.0)
        self.assertGreater(calibrated(100 + zone + 1, span), 0.0)
        self.assertEqual(calibrated(700 - zone, span), 1.0)
        self.assertLess(calibrated(700 - zone - 1, span), 1.0)

    def test_the_middle_of_the_span_is_one_half(self):
        self.assertAlmostEqual(calibrated(400, Range(low=100, high=700)), 0.5, places=6)


class Centre(unittest.TestCase):
    """A pot with a centre detent: the detent is exactly CENTRE, and a
    reading that jitters around it stays there."""

    span = Range(low=0, high=1020, centre=470)

    def test_the_detent_is_exactly_the_centre(self):
        self.assertEqual(calibrated(470, self.span), CENTRE)

    def test_jitter_around_the_detent_stays_on_it(self):
        # Measured on channel 1's EQ high at rest: 509 and 527, 18 apart --
        # it sent 700 000 lines in ten days.
        span = Range(low=4, high=1014, centre=518)
        self.assertEqual(calibrated(509, span), CENTRE)
        self.assertEqual(calibrated(527, span), CENTRE)

    def test_each_side_runs_linear_to_its_end(self):
        self.assertEqual(calibrated(0, self.span), 0.0)
        self.assertEqual(calibrated(1020, self.span), 1.0)
        below, above = calibrated(300, self.span), calibrated(700, self.span)
        self.assertTrue(0.0 < below < CENTRE < above < 1.0)

    def test_monotonic(self):
        values = [calibrated(counts, self.span) for counts in range(0, 1024)]
        self.assertEqual(values, sorted(values))

    def test_a_centre_in_a_dead_zone_is_ignored(self):
        bad = Range(low=0, high=1000, centre=5)
        self.assertAlmostEqual(calibrated(500, bad), calibrated(500, Range(0, 1000)))


class Ranges(unittest.TestCase):
    def test_a_narrow_span_is_not_usable(self):
        self.assertFalse(Range(low=300, high=300 + MIN_SPAN - 1).usable())
        self.assertTrue(Range(low=0, high=MIN_SPAN).usable())

    def test_upside_down_is_not_usable(self):
        self.assertFalse(Range(low=900, high=10).usable())

    def test_an_unusable_range_maps_as_the_raw_one(self):
        self.assertEqual(Calibration({"0:5": Range(500, 510)}).value("0:5", 1), 0.0)
        self.assertEqual(Calibration({"0:5": Range(500, 510)}).value("0:5", 1014), 1.0)

    def test_an_unknown_control_maps_as_the_raw_one(self):
        self.assertEqual(Calibration().value("master:0", 1014), 1.0)


class File(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "a3-mixer" / "calibration.json"
        self.lines = []

    def tearDown(self):
        self.folder.cleanup()

    def test_save_then_load(self):
        before = Calibration({"0:5": Range(1, 1021), "0:2": Range(4, 1014, 518)})
        save(self.path, before)
        after = load(self.path, self.lines.append)
        self.assertEqual(after.range_of("0:5"), Range(1, 1021))
        self.assertEqual(after.range_of("0:2"), Range(4, 1014, 518))

    def test_the_file_is_readable_json(self):
        save(self.path, Calibration({"master:0": Range(0, 1020)}))
        data = json.loads(self.path.read_text())
        self.assertEqual(data["controls"]["master:0"], {"low": 0, "high": 1020})

    def test_a_missing_file_is_the_raw_range_and_a_line(self):
        calibration = load(self.path, self.lines.append)
        self.assertEqual(calibration.range_of("0:5"), Range())
        self.assertEqual(len(self.lines), 1)
        self.assertIn(str(self.path), self.lines[0])

    def test_a_corrupt_file_is_the_raw_range_and_a_line(self):
        self.path.parent.mkdir(parents=True)
        for corrupt in ("{not json", "[]", '{"controls": 3}',
                        '{"controls": {"0:5": {"low": "x", "high": 9}}}'):
            self.path.write_text(corrupt)
            lines = []
            calibration = load(self.path, lines.append)
            self.assertEqual(calibration.range_of("0:5"), Range(), corrupt)
            self.assertEqual(len(lines), 1, corrupt)
            self.assertIn("unreadable", lines[0])

    def test_an_unusable_entry_is_dropped_with_a_line(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"version": 1, "controls": {
            "0:5": {"low": 1, "high": 1021}, "0:4": {"low": 500, "high": 510}}}))
        calibration = load(self.path, self.lines.append)
        self.assertEqual(calibration.range_of("0:5"), Range(1, 1021))
        self.assertEqual(calibration.range_of("0:4"), Range())
        self.assertTrue(any("0:4" in line for line in self.lines))

    def test_a_save_leaves_no_temporary_file(self):
        save(self.path, Calibration({"0:5": Range(1, 1021)}))
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["calibration.json"])


class Where(unittest.TestCase):
    def test_the_desk_users_config_dir(self):
        self.assertEqual(calibration_path({"HOME": "/root"}),
                         Path("/root/.config/a3-mixer/calibration.json"))

    def test_xdg_config_home_wins_over_home(self):
        self.assertEqual(calibration_path({"HOME": "/root", "XDG_CONFIG_HOME": "/etc/x"}),
                         Path("/etc/x/a3-mixer/calibration.json"))

    def test_an_explicit_path_wins(self):
        self.assertEqual(calibration_path({"HOME": "/root",
                                           "A3_MIXER_CALIBRATION": "/tmp/c.json"}),
                         Path("/tmp/c.json"))


if __name__ == "__main__":
    unittest.main()
