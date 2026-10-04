# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fünf Displays, und eines darf die anderen vier nicht mit ins Grab nehmen.

Gefunden am 2026-09-12: `a3-mixer-set-display.service` war seit dem 2026-09-10
tot, abgebrochen in der Initialisierung des sechsten Displays. Zwei Fehler in
einer Funktion, beide durch Lesen belegbar -- `i2c(port=0, ...)` wo der
Multiplexer auf Bus 1 sitzt, und ein Zeichnen auf `device_dev_5`, das in jener
Funktion gar nicht existiert.

Der eigentliche Befund ist aber der dritte: ein Skript, das die sechs Displays
als sechs fast gleiche Funktionen hintereinander aufruft, stirbt am ersten, das
nicht antwortet, und lässt die übrigen dunkel. Ein fehlendes Display ist eine
Meldung wert, kein Grund, den Dienst zu beenden.

Die Regel steht in einem eigenen Modul, weil sich das Skript ohne die
Pi-Hardware (luma, smbus, TCA9548A) nicht einmal importieren lässt -- derselbe
Grund wie bei a3_mixer_recall.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "a3-mixer-set-display")
)

from display_panel import MULTIPLEXER_CHANNELS, PANELS, draw_panels


class PanelTable(unittest.TestCase):
    def test_every_panel_sits_on_the_bus_the_multiplexer_uses(self):
        # TCA9548A.I2C_setup() spricht den Multiplexer über SMBus(1) an. Ein
        # Display hinter diesem Multiplexer kann also nur auf Bus 1 antworten.
        # Das sechste stand auf Bus 0 -- dem Kameraanschluss des Pi, meist gar
        # nicht aktiviert -- und daran ist der Dienst gestorben.
        for panel in PANELS:
            self.assertEqual(1, panel.port, panel.label)

    def test_every_panel_has_its_own_multiplexer_channel(self):
        channels = [panel.channel for panel in PANELS]
        self.assertEqual(len(channels), len(set(channels)))

    # Fuenf, nicht sechs. Das sechste war nie da: der Kopf des alten Skripts
    # sagte "5 Oled Displays", die Adresskonstanten hiessen _2 bis _6, und
    # disp_1..disp_5 benutzten die Multiplexer-Kanaele 2 bis 6. Nur disp_6
    # griff auf Kanal 7 -- und daran ist der Dienst acht Tage lang gestorben.
    # Vom Maintainer bestaetigt: "es gibt keinen kanal 7".
    def test_there_are_five(self):
        self.assertEqual(5, len(PANELS))

    def test_the_channels_are_the_ones_the_multiplexer_has(self):
        self.assertEqual(list(MULTIPLEXER_CHANNELS),
                         [panel.channel for panel in PANELS])

    def test_no_panel_claims_a_channel_that_does_not_exist(self):
        for panel in PANELS:
            self.assertIn(panel.channel, MULTIPLEXER_CHANNELS, panel.label)

    # Vier Kanalzuege und der FX-Return, vom Maintainer aufgezaehlt:
    # "es gibt 5 (kanal 1-4 und FX-Return)". Das fuenfte trug die Aufschrift
    # "Line In" -- dieselbe Copy-Paste-Schicht, aus der auch das sechste
    # Display kam, das es nie gab.
    def test_the_fifth_is_the_aux_return(self):
        self.assertEqual("Aux Return", PANELS[-1].label)

    def test_the_first_four_are_the_channel_strips(self):
        self.assertEqual(["Deck 1", "Deck 2", "Deck 3", "Deck 4"],
                         [panel.label for panel in PANELS[:4]])

    def test_each_label_is_its_own(self):
        labels = [panel.label for panel in PANELS]
        self.assertEqual(len(labels), len(set(labels)))


class OneDeadDisplay(unittest.TestCase):
    def setUp(self):
        self.drawn = []
        self.reported = []

    def show(self, panel):
        if panel.label == "Deck 3":
            raise OSError("no answer at 0x3c")
        self.drawn.append(panel.label)

    def report(self, message):
        self.reported.append(message)

    def test_the_others_are_still_drawn(self):
        draw_panels(PANELS, self.show, self.report)
        self.assertEqual(len(PANELS) - 1, len(self.drawn))
        self.assertNotIn("Deck 3", self.drawn)

    def test_the_dead_one_is_named_in_the_report(self):
        draw_panels(PANELS, self.show, self.report)
        self.assertEqual(1, len(self.reported))
        self.assertIn("Deck 3", self.reported[0])

    def test_the_dead_ones_come_back_as_the_return_value(self):
        failed = draw_panels(PANELS, self.show, self.report)
        self.assertEqual(["Deck 3"], [panel.label for panel in failed])

    def test_all_of_them_are_attempted_even_if_the_first_one_dies(self):
        attempted = []

        def every_one_fails(panel):
            attempted.append(panel.label)
            raise OSError("nothing on this bus at all")

        failed = draw_panels(PANELS, every_one_fails, self.report)
        self.assertEqual(len(PANELS), len(attempted))
        self.assertEqual(len(PANELS), len(failed))


class NothingWrong(unittest.TestCase):
    def test_a_full_panel_reports_nothing_and_returns_nothing(self):
        reported = []
        failed = draw_panels(PANELS, lambda panel: None, reported.append)
        self.assertEqual([], failed)
        self.assertEqual([], reported)


W, H = 128, 64


def stem(pair):
    return 1 << (pair - 1)


class ChannelSelector(unittest.TestCase):
    """A channel's display is an input selector (2026-10-04): nine meters
    under D1 | D2 | A and the cursor under one of them. It shows what is
    selected on this channel -- the cursor -- and nothing else: no mark of
    which input is assigned, no peak lines, no floor lines (maintainer,
    2026-10-04: turning, you want to see the selector only)."""

    def picture(self, cursor=8, levels=(0.5,) * 9, width=W, height=H):
        from display_panel import channel_picture
        return channel_picture(cursor, levels, width, height)

    def test_three_headings_over_their_meters(self):
        p = self.picture()
        self.assertEqual([h.text for h in p.headings], ["D1", "D2", "A"])
        meters = p.meters
        for heading, (first, last) in zip(p.headings, ((0, 3), (4, 7), (8, 8))):
            self.assertEqual(heading.box[0], meters[first].box[0])
            self.assertEqual(heading.box[2], meters[last].box[2])
            self.assertLess(heading.box[3], meters[first].box[1])

    def test_nine_meters_left_to_right_inside_the_panel(self):
        boxes = [m.box for m in self.picture().meters]
        self.assertEqual(len(boxes), 9)
        for (x0, y0, x1, y1), following in zip(boxes, boxes[1:] + [None]):
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)
            if following:
                self.assertLess(x1, following[0])

    def test_the_groups_stand_apart(self):
        boxes = [m.box for m in self.picture().meters]
        inner = boxes[1][0] - boxes[0][2]
        self.assertGreater(boxes[4][0] - boxes[3][2], inner)
        self.assertGreater(boxes[8][0] - boxes[7][2], inner)

    def test_a_meter_is_only_its_level(self):
        """No assignment and no peak travel with a channel meter."""
        from display_panel import Meter
        self.assertEqual(Meter._fields, ("box", "level"))

    def test_the_levels_are_the_meters(self):
        levels = tuple(i / 8 for i in range(9))
        self.assertEqual([m.level for m in self.picture(levels=levels).meters], list(levels))

    def test_the_cursor_sits_under_its_meter(self):
        p = self.picture(cursor=4)
        meter = p.meters[4].box
        self.assertEqual((p.cursor[0], p.cursor[2]), (meter[0], meter[2]))
        self.assertGreater(p.cursor[1], meter[3])
        self.assertLess(p.cursor[3], H)

    def test_it_follows_the_panel(self):
        p = self.picture(width=128, height=32)
        for box in [m.box for m in p.meters] + [h.box for h in p.headings] + [p.cursor]:
            self.assertTrue(box[3] < 32, box)


class ReturnMeter(unittest.TestCase):
    """The return is a stereo meter like a hardware one (2026-10-04): SA (the
    StemDeck's aux bus) and A (the analog return), each a pair L|R of
    segmented bars; the mode that plays filled, the cursor under its pair."""

    def picture(self, cursor=1, mode=1, levels=(0.5,) * 4, peaks=None):
        from display_panel import return_picture
        return return_picture(cursor, mode, levels, W, H, peaks=peaks)

    def test_two_stereo_pairs_under_sa_and_a(self):
        p = self.picture(levels=(0.1, 0.2, 0.3, 0.4))
        self.assertEqual([h.text for h in p.headings], ["SA", "A"])
        self.assertEqual([m.level for m in p.meters], [0.1, 0.2, 0.3, 0.4])
        for heading, (left, right) in zip(p.headings, ((0, 1), (2, 3))):
            self.assertEqual(heading.box[0], p.meters[left].box[0])
            self.assertEqual(heading.box[2], p.meters[right].box[2])
            self.assertLess(heading.box[3], p.meters[left].box[1])

    def test_the_bars_stand_left_to_right_inside_the_panel(self):
        boxes = [m.box for m in self.picture().meters]
        for (x0, y0, x1, y1), following in zip(boxes, boxes[1:] + [None]):
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)
            if following:
                self.assertLess(x1, following[0])
        self.assertGreater(boxes[2][0] - boxes[1][2], boxes[1][0] - boxes[0][2])

    def test_the_mode_that_plays_is_filled(self):
        from display_panel import ANALOG_MODE, STEM_MODE
        self.assertEqual([m.solid for m in self.picture(mode=STEM_MODE).meters],
                         [True, True, False, False])
        self.assertEqual([m.solid for m in self.picture(mode=ANALOG_MODE).meters],
                         [False, False, True, True])

    def test_the_cursor_is_under_its_pair(self):
        from display_panel import ANALOG_MODE, STEM_MODE
        for cursor, (left, right) in ((STEM_MODE, (0, 1)), (ANALOG_MODE, (2, 3))):
            p = self.picture(cursor=cursor)
            self.assertEqual((p.cursor[0], p.cursor[2]),
                             (p.meters[left].box[0], p.meters[right].box[2]))
            self.assertGreater(p.cursor[1], p.meters[0].box[3])
            self.assertLess(p.cursor[3], H)

    def test_segments_are_a_few_rows_with_one_row_between(self):
        from display_panel import segment_rows
        bar = self.picture().meters[0]
        rows = [segment_rows(bar, index) for index in range(bar.segments)]
        self.assertGreaterEqual(bar.segments, 8)
        self.assertEqual(rows[0][1], bar.box[3])         # the first is at the bottom
        self.assertEqual(rows[-1][0], bar.box[1])        # the last at the top
        for (top, bottom), above in zip(rows, rows[1:]):
            self.assertGreaterEqual(bottom - top + 1, 2)
            self.assertEqual(top - above[1], 2)          # one dark row between

    def test_the_level_lights_its_segments(self):
        bar = self.picture(levels=(1.0, 0.5, 0.0, 0.0)).meters
        self.assertEqual(bar[0].pixels()[0], bar[0].segments)
        self.assertEqual(bar[1].pixels()[0], bar[1].segments // 2)
        self.assertEqual(bar[3].pixels()[0], 1)         # silence keeps the base segment

    def test_a_peak_above_the_level_is_its_own_segment(self):
        bars = self.picture(levels=(0.25,) * 4, peaks=(0.75, 0.25, 0.0, 0.75)).meters
        self.assertEqual(bars[0].pixels(), (bars[0].segments // 4, bars[0].segments * 3 // 4))
        self.assertEqual(bars[1].pixels()[1], 0)         # at the level: nothing extra

    def test_scale_marks_at_0_and_minus_18_between_the_pairs(self):
        from display_panel import segment_rows
        p = self.picture()
        self.assertEqual([t.text for t in p.ticks], ["0", "-18"])
        bar = p.meters[0]
        for tick, level in zip(p.ticks, (1.0, (48 - 18) / 48)):
            x0, y0, x1, y1 = tick.box
            self.assertGreater(x0, p.meters[1].box[2])
            self.assertLess(x1, p.meters[2].box[0])
            # The mark sits on the segment that lights at that level.
            top, bottom = segment_rows(bar, round(level * bar.segments) - 1)
            self.assertTrue(y0 <= (top + bottom) // 2 <= y1)
            self.assertTrue(p.meters[0].box[1] <= y0 and y1 <= p.meters[0].box[3])


class MeterBallistics(unittest.TestCase):
    """Decided 2026-10-04: instant rise, a VU-like fall of 20 dB/s, and a
    peak mark that holds the highest level for a second, then falls alike."""

    def ballistics(self):
        from display_panel import Ballistics
        return Ballistics()

    def fall(self, seconds):
        from display_panel import METER_FALL_DB_PER_SECOND, METER_FLOOR_DB
        return METER_FALL_DB_PER_SECOND / -METER_FLOOR_DB * seconds

    def test_the_constants(self):
        from display_panel import (METER_FALL_DB_PER_SECOND, METER_STEPS_PER_SECOND,
                                   PEAK_HOLD_SECONDS)
        self.assertEqual(METER_STEPS_PER_SECOND, 10)
        self.assertEqual(METER_FALL_DB_PER_SECOND, 20.0)
        self.assertEqual(PEAK_HOLD_SECONDS, 1.0)

    def test_a_rise_is_instant(self):
        self.assertEqual(self.ballistics().feed(0.8, 0.1), (0.8, 0.8))

    def test_it_falls_at_twenty_db_a_second(self):
        b = self.ballistics()
        b.feed(1.0, 0.1)
        shown, _ = b.feed(0.0, 0.1)
        self.assertAlmostEqual(shown, 1.0 - self.fall(0.1))
        for _ in range(9):
            shown, _ = b.feed(0.0, 0.1)
        self.assertAlmostEqual(shown, 1.0 - self.fall(1.0))

    def test_it_stops_at_the_level_it_is_fed(self):
        b = self.ballistics()
        b.feed(1.0, 0.1)
        for _ in range(30):
            shown, _ = b.feed(0.5, 0.1)
        self.assertEqual(shown, 0.5)

    def test_it_never_falls_below_silence(self):
        b = self.ballistics()
        b.feed(0.1, 0.1)
        self.assertEqual(b.feed(0.0, 5.0), (0.0, 0.0))

    def test_the_peak_holds_a_second_then_falls_alike(self):
        b = self.ballistics()
        b.feed(1.0, 0.1)
        for _ in range(10):
            _, peak = b.feed(0.0, 0.1)
        self.assertAlmostEqual(peak, 1.0)               # held for 1.0 s
        _, peak = b.feed(0.0, 0.1)
        self.assertAlmostEqual(peak, 1.0 - self.fall(0.1))

    def test_a_louder_level_restarts_the_hold(self):
        b = self.ballistics()
        b.feed(0.5, 0.1)
        for _ in range(8):
            b.feed(0.0, 0.1)
        b.feed(0.9, 0.1)
        for _ in range(10):
            _, peak = b.feed(0.0, 0.1)
        self.assertAlmostEqual(peak, 0.9)

    def test_the_peak_is_never_below_what_is_shown(self):
        b = self.ballistics()
        for level in (1.0, 0.0, 0.3, 0.0, 0.0):
            shown, peak = b.feed(level, 0.7)
            self.assertGreaterEqual(peak, shown)


class InPixels(unittest.TestCase):
    """A panel is redrawn when its pixels change, not its floats: the bus
    carries ~17 draws a second, and a fall of less than a row is no draw."""

    def test_a_channel_meter_is_its_bar(self):
        from display_panel import channel_picture
        p = channel_picture(8, (0.6,) * 9, W, H)
        rows = p.meters[0].box[3] - p.meters[0].box[1] + 1
        self.assertEqual(p.meters[0].pixels(), round(0.6 * rows))

    def test_less_than_a_row_is_the_same_picture(self):
        from display_panel import channel_picture, pixel_key
        one = channel_picture(8, (0.500,) * 9, W, H)
        two = channel_picture(8, (0.505,) * 9, W, H)
        three = channel_picture(8, (0.6,) * 9, W, H)
        self.assertEqual(pixel_key(one), pixel_key(two))
        self.assertNotEqual(pixel_key(one), pixel_key(three))

    def test_a_silent_input_paints_nothing(self):
        from display_panel import channel_picture
        p = channel_picture(0, (0.0,) * 9, W, H)
        self.assertEqual([m.pixels() for m in p.meters], [0] * 9)

    def test_the_cursor_is_part_of_the_picture(self):
        from display_panel import channel_picture, pixel_key
        self.assertNotEqual(pixel_key(channel_picture(0, (0.0,) * 9, W, H)),
                            pixel_key(channel_picture(1, (0.0,) * 9, W, H)))

    def test_the_return_in_segments(self):
        from display_panel import pixel_key, return_picture
        one = return_picture(1, 1, (0.50,) * 4, W, H)
        two = return_picture(1, 1, (0.52,) * 4, W, H)
        self.assertEqual(pixel_key(one), pixel_key(two))


class MeterLevels(unittest.TestCase):
    def test_levels_map_in_db(self):
        from display_panel import meter_level
        self.assertEqual(meter_level(1.0), 1.0)
        self.assertAlmostEqual(meter_level(10 ** (-24 / 20)), 0.5)
        self.assertEqual(meter_level(10 ** (-60 / 20)), 0.0)
        for odd in (0, -1, None, "x", True, float("nan")):
            self.assertEqual(meter_level(odd), 0.0, odd)


class SelectorAnnouncements(unittest.TestCase):
    def test_a_cursor_is_zero_to_eight(self):
        from display_panel import cursor_announcement
        self.assertEqual(cursor_announcement((0,)), 0)
        self.assertEqual(cursor_announcement((8,)), 8)
        for args in ((9,), (-1,), (True,), (1.0,), ("1",), (1, 2), ()):
            self.assertIsNone(cursor_announcement(args), args)

    def test_a_mode_is_zero_or_one(self):
        from display_panel import mode_announcement
        self.assertEqual(mode_announcement((1,)), 1)
        for args in ((2,), (-1,), (True,), ()):
            self.assertIsNone(mode_announcement(args), args)


class StemPanels(unittest.TestCase):
    def test_channels_zero_to_three_are_the_four_decks(self):
        from display_panel import panel_for_channel
        self.assertEqual([panel_for_channel(i).label for i in range(4)],
                         ["Deck 1", "Deck 2", "Deck 3", "Deck 4"])

    def test_the_return_is_the_aux_return_panel(self):
        from display_panel import return_panel
        self.assertEqual(return_panel().label, "Aux Return")

    def test_the_mapping_hands_out_the_table_rows_themselves(self):
        from display_panel import PANELS, panel_for_channel, return_panel
        self.assertIs(panel_for_channel(0), PANELS[0])
        self.assertIs(return_panel(), PANELS[4])

    def test_a_channel_the_desk_does_not_have_is_refused(self):
        from display_panel import panel_for_channel
        for index in (-1, 4, 5):
            with self.assertRaises(IndexError):
                panel_for_channel(index)


def return_announcement_cursor(args):
    from display_panel import return_announcement
    announced = return_announcement(args)
    return None if announced is None else announced[0]


class StemAnnouncements(unittest.TestCase):
    def test_a_channel_announcement_is_a_mask(self):
        from display_panel import channel_announcement
        self.assertEqual(channel_announcement((0b100001,)), 0b100001)
        self.assertEqual(channel_announcement((255,)), 255)
        self.assertEqual(channel_announcement((0,)), 0)

    def test_a_damaged_channel_announcement_is_none(self):
        from display_panel import channel_announcement
        for args in ((), ("x",), (256,), (-1,), (None,), (1.5,), ("3",), (True,)):
            self.assertIsNone(channel_announcement(args), args)

    def test_a_return_announcement_is_cursor_and_eight_pairs(self):
        from display_panel import return_announcement
        self.assertEqual(return_announcement((1, 1, 0, 0, 1, 1, 1, 1, 1)),
                         (1, (True, False, False, True, True, True, True, True)))
        self.assertEqual(return_announcement((0,) * 9), (0, (False,) * 8))

    def test_the_cursor_is_analog_or_stem(self):
        """The truth's words: 0 = analog, 1 = stem. A cursor of 2 used to
        pass and then broke the return's picture."""
        self.assertEqual(return_announcement_cursor((1,) + (1,) * 8), 1)
        self.assertIsNone(return_announcement_cursor((2,) + (1,) * 8))

    def test_a_damaged_return_announcement_is_none(self):
        from display_panel import return_announcement
        for args in ((), (1, 1), (1,) + (1,) * 7, (1,) + (1,) * 9,
                     (10,) + (1,) * 8, (1, 2) + (1,) * 7, ("a",) + (1,) * 8,
                     (1, True) + (1,) * 7):
            self.assertIsNone(return_announcement(args), args)


if __name__ == "__main__":
    unittest.main()
