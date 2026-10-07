# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A channel's display bar and its LEDs read one scale (2026-10-07).

The maintainer's photo: channel 2's LEDs lit half -- the green part -- while
its display bar on A was almost full. The bar ran linear in dB from −48 to
0, so −12 dBFS filled 75 % of it, where the LEDs light 4 of 8. Now every
LED threshold sits at its eighth of the bar: a level that lights n LEDs
fills at least n/8 of it and less than (n+1)/8. The displays are
monochrome, so two marks beside every bar show where the LEDs turn yellow
(−9 dBFS) and red (−3 dBFS)."""

import re
import sys
import unittest
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
FIRMWARE = SOFTWARE.parent / "hardware/mainboard/firmware/src/main.cpp"
sys.path.insert(0, str(SOFTWARE / "scripts"))
sys.path.insert(0, str(SOFTWARE / "scripts" / "a3-mixer-set-display"))

import a3_mixer_meters  # noqa: E402
from a3_mixer_meters import CHANNEL_LED_THRESHOLDS_DB, channel_leds  # noqa: E402

W, H = 128, 64
LEDS = len(CHANNEL_LED_THRESHOLDS_DB)
JUST = 0.01


def peak(db):
    """The linear peak the analyzer sends for `db` dBFS."""
    return 10 ** (db / 20)


def level(db):
    from display_panel import meter_level
    return meter_level(peak(db))


class TheBarFillsTheEighthsTheLedsLight(unittest.TestCase):
    def assertInEighth(self, db):
        lit = channel_leds(db)
        fraction = level(db)
        if lit == LEDS:
            self.assertEqual(fraction, 1.0, db)
            return
        self.assertGreaterEqual(fraction, lit / LEDS, db)
        self.assertLess(fraction, (lit + 1) / LEDS, db)

    def test_every_threshold_sits_at_its_eighth(self):
        for count, threshold in enumerate(CHANNEL_LED_THRESHOLDS_DB, start=1):
            with self.subTest(threshold=threshold):
                self.assertEqual(channel_leds(threshold), count)
                self.assertAlmostEqual(level(threshold), count / LEDS)
                self.assertInEighth(threshold)

    def test_just_below_every_threshold_stays_in_the_eighth_below(self):
        for threshold in CHANNEL_LED_THRESHOLDS_DB:
            with self.subTest(threshold=threshold):
                self.assertInEighth(threshold - JUST)

    def test_between_every_two_thresholds(self):
        steps = CHANNEL_LED_THRESHOLDS_DB
        for low, high in zip(steps, steps[1:]):
            with self.subTest(between=(low, high)):
                self.assertInEighth((low + high) / 2)

    def test_the_photo_minus_twelve_is_half_a_bar_not_three_quarters(self):
        self.assertEqual(channel_leds(-12.0), 4)
        self.assertAlmostEqual(level(-12.0), 0.5)

    def test_quiet_below_the_first_led_shows_less_than_an_eighth(self):
        for db in (-36 - JUST, -40.0, -47.0, -60.0, -120.0):
            with self.subTest(db=db):
                self.assertEqual(channel_leds(db), 0)
                self.assertInEighth(db)

    def test_below_the_first_led_the_bar_still_moves(self):
        """A shows the analog input so the DJ sees something is there
        before switching to it: a quiet input is a sliver, not nothing."""
        self.assertGreater(level(-40.0), 0.0)
        self.assertGreater(level(-40.0), level(-44.0))

    def test_silence_is_an_empty_bar(self):
        from display_panel import meter_level
        for silence in (0.0, -1.0, None, "loud", True):
            with self.subTest(silence=silence):
                self.assertEqual(meter_level(silence), 0.0)

    def test_full_scale_and_over_fill_the_bar(self):
        self.assertEqual(level(0.0), 1.0)
        self.assertEqual(level(6.0), 1.0)
        self.assertEqual(channel_leds(6.0), LEDS)

    def test_it_rises_with_the_level(self):
        dbs = [x / 4 for x in range(-60 * 4, 1)]
        fractions = [level(db) for db in dbs]
        self.assertEqual(fractions, sorted(fractions))


class TheScaleIsOneTable(unittest.TestCase):
    def test_the_display_reads_the_leds_table(self):
        import display_panel
        self.assertIs(display_panel.CHANNEL_LED_THRESHOLDS_DB,
                      a3_mixer_meters.CHANNEL_LED_THRESHOLDS_DB)

    def test_the_bar_and_its_inverse_agree(self):
        from a3_mixer_meters import bar_db, bar_fraction
        for db in (-48.0, -40.0, -36.0, -30.0, -12.0, -10.5, -1.0, 0.0):
            with self.subTest(db=db):
                self.assertAlmostEqual(bar_db(bar_fraction(db)), db)


class TheBarInPixels(unittest.TestCase):
    """On the 45 rows of a channel bar an eighth is 5.6 rows: a level that
    lights n LEDs lights the rows of the n-th eighth, to the row."""

    def test_n_leds_light_the_rows_of_the_nth_eighth(self):
        from display_panel import channel_picture, lit_rows
        rows = None
        for db in [t + d for t in CHANNEL_LED_THRESHOLDS_DB[:-1] for d in (-JUST, 0.0, 1.0)]:
            with self.subTest(db=db):
                meter = channel_picture(0, (level(db),) * 9, 0, W, H).meters[0]
                rows = meter.box[3] - meter.box[1] + 1
                lit = channel_leds(db)
                self.assertGreaterEqual(meter.pixels(), lit_rows(lit / LEDS, rows))
                self.assertLessEqual(meter.pixels(), lit_rows((lit + 1) / LEDS, rows))


class MarksWhereTheLedsChangeColour(unittest.TestCase):
    def test_yellow_and_red_start_where_the_firmware_says(self):
        from a3_mixer_meters import RED_FROM_DB, YELLOW_FROM_DB
        source = FIRMWARE.read_text()
        table = source[source.index("channelLedColour[8]"):]
        names = re.findall(r"\b(GREEN|YELLOW|RED)\b", table[:table.index("};")])
        self.assertEqual(YELLOW_FROM_DB, CHANNEL_LED_THRESHOLDS_DB[names.index("YELLOW")])
        self.assertEqual(RED_FROM_DB, CHANNEL_LED_THRESHOLDS_DB[names.index("RED")])
        self.assertEqual((YELLOW_FROM_DB, RED_FROM_DB), (-9, -3))

    def pictures(self):
        from display_panel import STEM_MODE, channel_picture, return_picture
        return {
            "channel": channel_picture(0, (0.0,) * 9, 0, W, H),
            "return": return_picture(STEM_MODE, STEM_MODE, False, (0.0, 0.0), W, H),
        }

    def test_every_meter_has_a_yellow_and_a_red_mark(self):
        from display_panel import meter_marks
        for name, picture in self.pictures().items():
            for meter in picture.meters:
                with self.subTest(name, meter=meter.box):
                    marks = [m for m in picture.marks if m in meter_marks(meter.box)]
                    self.assertEqual(len(marks), len(meter_marks(meter.box)))
                    self.assertEqual(len({m[1] for m in marks}), 2)

    def test_a_mark_is_at_the_top_row_of_a_bar_at_its_level(self):
        """A bar exactly at −9 dBFS reaches the yellow mark's row, one at
        −3 the red mark's: the mark is where the bar's top stands."""
        from a3_mixer_meters import RED_FROM_DB, YELLOW_FROM_DB
        from display_panel import STEM_MODE, channel_picture, meter_marks, return_picture
        for db in (YELLOW_FROM_DB, RED_FROM_DB):
            pictures = (channel_picture(0, (level(db),) * 9, 0, W, H),
                        return_picture(STEM_MODE, STEM_MODE, False, (level(db),) * 2, W, H))
            for picture in pictures:
                for meter in picture.meters:
                    with self.subTest(db=db, meter=meter.box):
                        top = meter.box[3] - meter.pixels() + 1
                        rows = {box[1] for box in meter_marks(meter.box)}
                        self.assertIn(top, rows)

    def test_a_mark_stands_beside_the_bar_never_on_it(self):
        from display_panel import meter_marks
        for name, picture in self.pictures().items():
            for meter in picture.meters:
                x0, y0, x1, y1 = meter.box
                for mx0, my0, mx1, my1 in meter_marks(meter.box):
                    with self.subTest(name, meter=meter.box):
                        self.assertEqual(my0, my1)
                        self.assertTrue(y0 <= my0 <= y1)
                        self.assertTrue(mx1 < x0 or mx0 > x1)

    def test_the_marks_stay_on_the_panel_and_clear_of_the_bracket(self):
        for name, picture in self.pictures().items():
            bracket_bottom = picture.active[3]
            for x0, y0, x1, y1 in picture.marks:
                with self.subTest(name, mark=(x0, y0, x1, y1)):
                    self.assertTrue(0 <= x0 <= x1 < W and 0 <= y0 <= y1 < H)
                    self.assertGreater(y0, bracket_bottom + 1)

    def test_the_marks_cover_no_bar_and_no_divider(self):
        """In a 2-column gap the marks of two neighbours meet; they must
        not touch either neighbour's bar or a divider."""
        for name, picture in self.pictures().items():
            bars = {(x, y) for m in picture.meters
                    for x in range(m.box[0], m.box[2] + 1) for y in range(m.box[1], m.box[3] + 1)}
            lines = {(x, y) for x0, y0, x1, y1 in picture.dividers
                     for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
            for x0, y0, x1, y1 in picture.marks:
                pixels = {(x, y0) for x in range(x0, x1 + 1)}
                with self.subTest(name, mark=(x0, y0, x1, y1)):
                    self.assertFalse(pixels & bars)
                    self.assertFalse(pixels & lines)


if __name__ == "__main__":
    unittest.main()
