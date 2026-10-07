# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A display bar shows exactly what the channel's LEDs show (2026-10-07).

The maintainer: *"the display vu must show exactly the same as the channel
input vu. yellow red marker must fit the dotted line in the displays."*

The LEDs move in eight steps, so the bar does too: a level that lights n
of the 8 LEDs fills exactly n/8 of the bar -- nothing between two steps,
and nothing at all below the first LED (the sliver below -36 dBFS is gone).
The held peak stands at the top of the segment of the LED the firmware
keeps lit as hold. The displays are monochrome, so two marks beside every
bar show where the LEDs turn yellow and red: at the bottom row of the first
yellow segment and of the first red one -- the bar covers a mark exactly
when an LED of that colour is lit."""

import re
import sys
import unittest
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
FIRMWARE = SOFTWARE.parent / "hardware/mainboard/firmware/src/main.cpp"
sys.path.insert(0, str(SOFTWARE / "scripts"))
sys.path.insert(0, str(SOFTWARE / "scripts" / "a3-mixer-set-display"))

import a3_mixer_meters  # noqa: E402
from a3_mixer_meters import (CHANNEL_LED_COLOURS, CHANNEL_LED_THRESHOLDS_DB,  # noqa: E402
                             bar_fraction, channel_leds, channel_vu_line)

W, H = 128, 64
LEDS = len(CHANNEL_LED_THRESHOLDS_DB)
JUST = 0.01
#: Every threshold and a hair below each: where the LEDs change.
EDGES_DB = tuple(db for t in CHANNEL_LED_THRESHOLDS_DB for db in (t - JUST, float(t)))


def peak(db):
    """The linear peak the analyzer sends for `db` dBFS."""
    return 10 ** (db / 20)


def colour_lit(db, colour):
    """Whether a peak of `db` dBFS lights an LED of `colour`."""
    return colour in CHANNEL_LED_COLOURS[:channel_leds(db)]


class TheBarIsTheLeds(unittest.TestCase):
    def test_every_threshold_fills_exactly_its_eighths(self):
        for count, threshold in enumerate(CHANNEL_LED_THRESHOLDS_DB, start=1):
            with self.subTest(threshold=threshold):
                self.assertEqual(bar_fraction(threshold), count / LEDS)

    def test_just_below_a_threshold_is_the_step_below(self):
        for count, threshold in enumerate(CHANNEL_LED_THRESHOLDS_DB, start=1):
            with self.subTest(threshold=threshold):
                self.assertEqual(bar_fraction(threshold - JUST), (count - 1) / LEDS)

    def test_nothing_between_two_steps(self):
        for db in [x / 8 for x in range(-60 * 8, 6 * 8)]:
            with self.subTest(db=db):
                self.assertEqual(bar_fraction(db), channel_leds(db) / LEDS)

    def test_the_photo_minus_ten_is_half_a_bar(self):
        """-10 dBFS lights four green LEDs: the bar is half, not over it."""
        self.assertEqual(channel_leds(-10.0), 4)
        self.assertEqual(bar_fraction(-10.0), 0.5)

    def test_below_the_first_led_the_bar_is_empty(self):
        """No sliver below -36 dBFS any more: no LED, no bar (2026-10-07)."""
        for db in (-36 - JUST, -40.0, -47.0, -60.0, -120.0):
            with self.subTest(db=db):
                self.assertEqual(bar_fraction(db), 0.0)

    def test_the_display_level_of_a_linear_peak(self):
        from display_panel import meter_level
        self.assertEqual(meter_level(peak(-10.0)), 0.5)
        self.assertEqual(meter_level(peak(-40.0)), 0.0)
        self.assertEqual(meter_level(1.0), 1.0)
        self.assertEqual(meter_level(2.0), 1.0)

    def test_silence_is_an_empty_bar(self):
        from display_panel import meter_level
        for silence in (0.0, -1.0, None, "loud", True):
            with self.subTest(silence=silence):
                self.assertEqual(meter_level(silence), 0.0)

    def test_the_hold_is_the_firmwares_hold_led(self):
        """VU:slot:bar:hold lights LED `hold` (index = count - 1): the
        display's hold line tops that LED's segment."""
        for db in EDGES_DB + (-120.0, 6.0):
            with self.subTest(db=db):
                hold_index = int(channel_vu_line(0, -120.0, db).split(":")[3])
                self.assertEqual(bar_fraction(db), (hold_index + 1) / LEDS)


class TheScaleIsOneTable(unittest.TestCase):
    def test_the_display_reads_the_leds_table(self):
        import display_panel
        self.assertIs(display_panel.CHANNEL_LED_THRESHOLDS_DB,
                      a3_mixer_meters.CHANNEL_LED_THRESHOLDS_DB)

    def test_the_marks_are_where_the_colours_start(self):
        from a3_mixer_meters import RED_FROM_FRACTION, YELLOW_FROM_FRACTION
        self.assertEqual(YELLOW_FROM_FRACTION, CHANNEL_LED_COLOURS.index("yellow") / LEDS)
        self.assertEqual(RED_FROM_FRACTION, CHANNEL_LED_COLOURS.index("red") / LEDS)
        self.assertEqual((YELLOW_FROM_FRACTION, RED_FROM_FRACTION), (4 / 8, 6 / 8))

    def test_the_colours_are_the_firmwares(self):
        source = FIRMWARE.read_text()
        table = source[source.index("channelLedColour[8]"):]
        names = re.findall(r"\b(GREEN|YELLOW|RED)\b", table[:table.index("};")])
        self.assertEqual([n.lower() for n in names], list(CHANNEL_LED_COLOURS))
        self.assertEqual(CHANNEL_LED_THRESHOLDS_DB[names.index("YELLOW")], -9)
        self.assertEqual(CHANNEL_LED_THRESHOLDS_DB[names.index("RED")], -3)

    def test_above_a_mark_exactly_when_its_colour_is_lit(self):
        from a3_mixer_meters import RED_FROM_FRACTION, YELLOW_FROM_FRACTION
        for db in EDGES_DB:
            with self.subTest(db=db):
                self.assertEqual(bar_fraction(db) > YELLOW_FROM_FRACTION,
                                 colour_lit(db, "yellow"))
                self.assertEqual(bar_fraction(db) > RED_FROM_FRACTION,
                                 colour_lit(db, "red"))


def pictures(level, hold=0.0):
    """Every display drawn with all meters at `level` and `hold`."""
    from display_panel import STEM_MODE, channel_picture, return_picture
    return {
        "channel": channel_picture(0, (level,) * 9, 0, W, H, holds=(hold,) * 9),
        "return": return_picture(STEM_MODE, STEM_MODE, False, (level,) * 2, W, H,
                                 holds=(hold,) * 2),
    }


def covered(meter, row):
    """Whether `meter`'s bar covers panel row `row`."""
    return meter.box[3] - meter.pixels() < row <= meter.box[3]


class TheBarInPixels(unittest.TestCase):
    """45 rows a bar on the 64-row panel, 5.625 an eighth: the segments are
    lit_rows(n/8, rows) rows -- half up --, and the marks use the same
    rounding, so a mark is always a segment's bottom row."""

    def test_the_segments_on_the_real_panel(self):
        from display_panel import lit_rows
        meter = pictures(0.0)["channel"].meters[0]
        rows = meter.box[3] - meter.box[1] + 1
        self.assertEqual(rows, 45)
        self.assertEqual([lit_rows(n / LEDS, rows) for n in range(LEDS + 1)],
                         [0, 6, 11, 17, 23, 28, 34, 39, 45])

    def test_n_leds_light_the_rows_of_n_segments(self):
        from display_panel import lit_rows
        for n in range(LEDS + 1):
            for name, picture in pictures(n / LEDS).items():
                for meter in picture.meters:
                    with self.subTest(name, n=n, meter=meter.box):
                        rows = meter.box[3] - meter.box[1] + 1
                        self.assertEqual(meter.pixels(), lit_rows(n / LEDS, rows))

    def test_the_marks_are_the_bottom_rows_of_the_first_yellow_and_red_segment(self):
        from display_panel import lit_rows, meter_marks
        yellow = CHANNEL_LED_COLOURS.index("yellow")
        red = CHANNEL_LED_COLOURS.index("red")
        for name, picture in pictures(0.0).items():
            for meter in picture.meters:
                with self.subTest(name, meter=meter.box):
                    y1 = meter.box[3]
                    rows = y1 - meter.box[1] + 1
                    marks = [box[1] for box in meter_marks(meter.box)]
                    self.assertEqual(marks, [y1 - lit_rows(yellow / LEDS, rows),
                                             y1 - lit_rows(red / LEDS, rows)])

    def test_the_bar_covers_a_mark_exactly_when_its_colour_is_lit(self):
        from display_panel import meter_marks, meter_level
        for db in EDGES_DB:
            for name, picture in pictures(meter_level(peak(db) * (1 + 1e-9))).items():
                for meter in picture.meters:
                    yellow_row, red_row = (box[1] for box in meter_marks(meter.box))
                    with self.subTest(name, db=db, meter=meter.box):
                        self.assertEqual(covered(meter, yellow_row), colour_lit(db, "yellow"))
                        self.assertEqual(covered(meter, red_row), colour_lit(db, "red"))

    def test_the_hold_line_tops_the_held_leds_segment(self):
        from display_panel import lit_rows
        for n in range(1, LEDS + 1):
            for name, picture in pictures(0.0, n / LEDS).items():
                for meter in picture.meters:
                    with self.subTest(name, n=n, meter=meter.box):
                        rows = meter.box[3] - meter.box[1] + 1
                        self.assertEqual(meter.hold_row(),
                                         meter.box[3] - lit_rows(n / LEDS, rows) + 1)


class MarksBesideTheBar(unittest.TestCase):
    def test_every_meter_has_a_yellow_and_a_red_mark(self):
        from display_panel import meter_marks
        for name, picture in pictures(0.0).items():
            for meter in picture.meters:
                with self.subTest(name, meter=meter.box):
                    marks = [m for m in picture.marks if m in meter_marks(meter.box)]
                    self.assertEqual(len(marks), len(meter_marks(meter.box)))
                    self.assertEqual(len({m[1] for m in marks}), 2)

    def test_a_mark_stands_beside_the_bar_never_on_it(self):
        from display_panel import meter_marks
        for name, picture in pictures(0.0).items():
            for meter in picture.meters:
                x0, y0, x1, y1 = meter.box
                for mx0, my0, mx1, my1 in meter_marks(meter.box):
                    with self.subTest(name, meter=meter.box):
                        self.assertEqual(my0, my1)
                        self.assertTrue(y0 <= my0 <= y1)
                        self.assertTrue(mx1 < x0 or mx0 > x1)

    def test_the_marks_stay_on_the_panel_and_clear_of_the_bracket(self):
        for name, picture in pictures(0.0).items():
            bracket_bottom = picture.active[3]
            for x0, y0, x1, y1 in picture.marks:
                with self.subTest(name, mark=(x0, y0, x1, y1)):
                    self.assertTrue(0 <= x0 <= x1 < W and 0 <= y0 <= y1 < H)
                    self.assertGreater(y0, bracket_bottom + 1)

    def test_the_marks_cover_no_bar_and_no_divider(self):
        """In a 2-column gap the marks of two neighbours meet; they must
        not touch either neighbour's bar or a divider."""
        for name, picture in pictures(0.0).items():
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
