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
    """A channel's display is an input selector: eight stem meters under
    D1 | D2 and, in the ninth slot, the STEM toggle (maintainer, 2026-10-04:
    the channel's analog meter is gone, Core makes position 8 a stem on/off
    switch). It shows what is selected -- the cursor -- and whether a stem
    plays, never which one."""

    def picture(self, cursor=8, levels=(0.5,) * 8, stem_on=False, width=W, height=H):
        from display_panel import channel_picture
        return channel_picture(cursor, levels, stem_on, width, height)

    def test_two_headings_over_the_stem_meters(self):
        p = self.picture()
        self.assertEqual([h.text for h in p.headings], ["D1", "D2"])
        meters = p.meters
        for heading, (first, last) in zip(p.headings, ((0, 3), (4, 7))):
            self.assertEqual(heading.box[0], meters[first].box[0])
            self.assertEqual(heading.box[2], meters[last].box[2])
            self.assertLess(heading.box[3], meters[first].box[1])
            self.assertFalse(heading.inverted)

    def test_eight_meters_and_no_analog_one(self):
        boxes = [m.box for m in self.picture().meters]
        self.assertEqual(len(boxes), 8)
        for (x0, y0, x1, y1), following in zip(boxes, boxes[1:] + [None]):
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)
            if following:
                self.assertLess(x1, following[0])

    def test_the_toggle_is_the_ninth_slot(self):
        from display_panel import STEM_TOGGLE
        self.assertEqual(STEM_TOGGLE, 8)
        p = self.picture()
        x0, y0, x1, y1 = p.toggle.box
        last = p.meters[-1].box
        self.assertGreater(x0, last[2])
        self.assertLess(x1, W)
        self.assertEqual((y0, y1), (last[1], last[3]))

    def test_the_toggle_reads_stem(self):
        self.assertEqual(self.picture().toggle.text, "STEM")

    def test_the_toggle_is_on_while_a_stem_plays(self):
        self.assertTrue(self.picture(stem_on=True).toggle.on)
        self.assertFalse(self.picture(stem_on=False).toggle.on)

    def test_the_toggle_is_two_meters_wide(self):
        """STEM does not fit across a meter; it stands letter over letter in
        a slot about two meters wide (snapshots, 2026-10-04)."""
        p = self.picture()
        meter = p.meters[0].box[2] - p.meters[0].box[0] + 1
        toggle = p.toggle.box[2] - p.toggle.box[0] + 1
        self.assertGreaterEqual(toggle, 2 * meter)

    def test_the_groups_stand_apart(self):
        p = self.picture()
        boxes = [m.box for m in p.meters]
        inner = boxes[1][0] - boxes[0][2]
        self.assertGreater(boxes[4][0] - boxes[3][2], inner)
        self.assertGreater(p.toggle.box[0] - boxes[7][2], inner)

    def test_the_groups_are_divided_by_lines(self):
        """D1 | D2 | the toggle stand apart: a vertical line in each gap,
        below the headings, the meters' height."""
        p = self.picture()
        slots = [m.box for m in p.meters] + [p.toggle.box]
        self.assertEqual(len(p.dividers), 2)
        for (x0, y0, x1, y1), (left, right) in zip(p.dividers, ((3, 4), (7, 8))):
            self.assertEqual(x0, x1)
            self.assertGreaterEqual(x0 - slots[left][2], 3)
            self.assertGreaterEqual(slots[right][0] - x0, 3)
            self.assertGreater(y0, p.headings[0].box[3])
            self.assertEqual((y0, y1), (slots[0][1], slots[0][3]))

    def test_the_meters_keep_their_width(self):
        boxes = [m.box for m in self.picture().meters]
        self.assertTrue(all(x1 - x0 + 1 >= 9 for x0, _, x1, _ in boxes))

    def test_a_meter_is_only_its_level(self):
        """No assignment and no peak travel with a meter."""
        from display_panel import Meter
        self.assertEqual(Meter._fields, ("box", "level"))

    def test_the_levels_are_the_meters(self):
        levels = tuple(i / 8 for i in range(8))
        self.assertEqual([m.level for m in self.picture(levels=levels).meters], list(levels))

    def assert_arrow_over(self, p, slot):
        """The cursor is a small arrow box between the headings and the top
        of the meters, centred over `slot`."""
        x0, y0, x1, y1 = p.cursor
        self.assertGreater(y0, max(h.box[3] for h in p.headings))
        self.assertLess(y1, slot[1])
        self.assertLessEqual(abs((x0 + x1) - (slot[0] + slot[2])), 1)

    def test_the_cursor_is_an_arrow_above_its_meter(self):
        """Maintainer, 2026-10-04: a "^" turned over, a small triangle
        pointing down at the selected meter -- the inverted column went."""
        p = self.picture(cursor=4)
        self.assert_arrow_over(p, p.meters[4].box)

    def test_the_arrow_is_as_wide_as_a_meter_and_a_few_rows_tall(self):
        p = self.picture(cursor=0)
        x0, y0, x1, y1 = p.cursor
        meter = p.meters[0].box
        self.assertEqual(x1 - x0, meter[2] - meter[0])
        self.assertIn(y1 - y0 + 1, (4, 5))

    def test_the_cursor_on_the_toggle_is_the_same_arrow_above_it(self):
        p = self.picture(cursor=8)
        self.assert_arrow_over(p, p.toggle.box)
        on_a_stem = self.picture(cursor=0).cursor
        self.assertEqual((p.cursor[2] - p.cursor[0], p.cursor[1], p.cursor[3]),
                         (on_a_stem[2] - on_a_stem[0], on_a_stem[1], on_a_stem[3]))

    def test_the_meters_stay_readable_under_the_arrow(self):
        p = self.picture()
        x0, y0, x1, y1 = p.meters[0].box
        self.assertGreaterEqual(y1 - y0 + 1, 40)
        self.assertEqual(y1, H - 1)

    def test_the_headings_keep_their_size(self):
        h = self.picture().headings[0].box
        self.assertEqual(h[3] - h[1] + 1, 12)

    def test_it_follows_the_panel(self):
        p = self.picture(width=128, height=32)
        boxes = [m.box for m in p.meters] + [h.box for h in p.headings]
        for box in boxes + [p.cursor, p.toggle.box]:
            self.assertTrue(box[3] < 32, box)


class ReturnMeter(unittest.TestCase):
    """The return is drawn like a channel (2026-10-04): two mono meters,
    STEM (StemDeck's aux bus) and ANALOG (the analog return), under their
    names and nothing else; the mode that plays has its heading inverted,
    and the cursor is the same down arrow, over STEM or ANALOG only."""

    def picture(self, cursor=None, mode=None, levels=(0.5, 0.5)):
        from display_panel import STEM_MODE, return_picture
        cursor = STEM_MODE if cursor is None else cursor
        mode = STEM_MODE if mode is None else mode
        return return_picture(cursor, mode, levels, W, H)

    def heading(self, picture, text):
        return next(h for h in picture.headings if h.text == text)

    def test_only_stem_and_analog_from_left_to_right(self):
        """Maintainer, 2026-10-04: the AUX title irritated and went; the
        return shows its two options and nothing between them."""
        p = self.picture()
        self.assertEqual([h.text for h in p.headings], ["STEM", "ANALOG"])
        lefts = [h.box[0] for h in p.headings]
        self.assertEqual(lefts, sorted(lefts))

    def test_two_mono_meters_under_their_headings(self):
        from display_panel import Meter
        p = self.picture(levels=(0.1, 0.4))
        self.assertEqual([m.level for m in p.meters], [0.1, 0.4])
        self.assertTrue(all(type(m) is Meter for m in p.meters))
        for text, meter in (("STEM", p.meters[0]), ("ANALOG", p.meters[1])):
            heading = self.heading(p, text).box
            self.assertTrue(heading[0] <= meter.box[0] and meter.box[2] <= heading[2], text)
            self.assertLess(heading[3], meter.box[1])

    def test_the_mode_that_plays_has_its_heading_inverted(self):
        from display_panel import ANALOG_MODE, STEM_MODE
        for mode, playing, other in ((STEM_MODE, "STEM", "ANALOG"),
                                     (ANALOG_MODE, "ANALOG", "STEM")):
            p = self.picture(mode=mode)
            self.assertTrue(self.heading(p, playing).inverted, playing)
            self.assertFalse(self.heading(p, other).inverted, other)

    def test_the_cursor_is_an_arrow_above_stem_or_analog(self):
        from display_panel import ANALOG_MODE, STEM_MODE
        for cursor, index in ((STEM_MODE, 0), (ANALOG_MODE, 1)):
            p = self.picture(cursor=cursor)
            x0, y0, x1, y1 = p.cursor
            meter = p.meters[index].box
            self.assertGreater(y0, max(h.box[3] for h in p.headings))
            self.assertLess(y1, meter[1])
            self.assertLessEqual(abs((x0 + x1) - (meter[0] + meter[2])), 1)

    def test_the_return_arrow_reads_like_the_channels(self):
        from display_panel import channel_picture
        channel = channel_picture(0, (0.0,) * 8, False, W, H).cursor
        ret = self.picture().cursor
        self.assertEqual((ret[1], ret[3]), (channel[1], channel[3]))
        self.assertGreaterEqual(ret[2] - ret[0], channel[2] - channel[0])

    def test_the_meters_stand_inside_the_panel(self):
        for x0, y0, x1, y1 in [m.box for m in self.picture().meters]:
            self.assertTrue(0 <= x0 < x1 < W and 0 <= y0 < y1 < H)

    def test_there_is_no_scale_any_more(self):
        from display_panel import Picture
        self.assertNotIn("ticks", Picture._fields)


class MeterBallistics(unittest.TestCase):
    """Decided 2026-10-04: instant rise and a VU-like fall of 20 dB/s. The
    peak mark went with the return's segments: no display draws one."""

    def ballistics(self):
        from display_panel import Ballistics
        return Ballistics()

    def fall(self, seconds):
        from display_panel import METER_FALL_DB_PER_SECOND, METER_FLOOR_DB
        return METER_FALL_DB_PER_SECOND / -METER_FLOOR_DB * seconds

    def test_the_constants(self):
        from display_panel import METER_FALL_DB_PER_SECOND, METER_STEPS_PER_SECOND
        self.assertEqual(METER_STEPS_PER_SECOND, 10)
        self.assertEqual(METER_FALL_DB_PER_SECOND, 20.0)

    def test_a_rise_is_instant(self):
        self.assertEqual(self.ballistics().feed(0.8, 0.1), 0.8)

    def test_it_falls_at_twenty_db_a_second(self):
        b = self.ballistics()
        b.feed(1.0, 0.1)
        shown = b.feed(0.0, 0.1)
        self.assertAlmostEqual(shown, 1.0 - self.fall(0.1))
        for _ in range(9):
            shown = b.feed(0.0, 0.1)
        self.assertAlmostEqual(shown, 1.0 - self.fall(1.0))

    def test_it_stops_at_the_level_it_is_fed(self):
        b = self.ballistics()
        b.feed(1.0, 0.1)
        for _ in range(30):
            shown = b.feed(0.5, 0.1)
        self.assertEqual(shown, 0.5)

    def test_it_never_falls_below_silence(self):
        b = self.ballistics()
        b.feed(0.1, 0.1)
        self.assertEqual(b.feed(0.0, 5.0), 0.0)


class InPixels(unittest.TestCase):
    """A panel is redrawn when its pixels change, not its floats: the bus
    carries ~17 draws a second, and a fall of less than a row is no draw."""

    def channel(self, cursor=8, level=0.0, stem_on=False):
        from display_panel import channel_picture
        return channel_picture(cursor, (level,) * 8, stem_on, W, H)

    def test_a_channel_meter_is_its_bar(self):
        p = self.channel(level=0.6)
        rows = p.meters[0].box[3] - p.meters[0].box[1] + 1
        self.assertEqual(p.meters[0].pixels(), round(0.6 * rows))

    def test_less_than_a_row_is_the_same_picture(self):
        from display_panel import pixel_key
        one, two, three = (self.channel(level=level) for level in (0.500, 0.505, 0.6))
        self.assertEqual(pixel_key(one), pixel_key(two))
        self.assertNotEqual(pixel_key(one), pixel_key(three))

    def test_a_silent_input_paints_nothing(self):
        self.assertEqual([m.pixels() for m in self.channel(cursor=0).meters], [0] * 8)

    def test_the_cursor_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(cursor=0)), pixel_key(self.channel(cursor=1)))
        self.assertNotEqual(pixel_key(self.channel(cursor=7)), pixel_key(self.channel(cursor=8)))

    def test_the_toggle_is_part_of_the_picture(self):
        from display_panel import pixel_key
        self.assertNotEqual(pixel_key(self.channel(stem_on=True)),
                            pixel_key(self.channel(stem_on=False)))

    def test_the_playing_mode_is_part_of_the_picture(self):
        from display_panel import ANALOG_MODE, STEM_MODE, pixel_key, return_picture
        self.assertNotEqual(pixel_key(return_picture(STEM_MODE, STEM_MODE, (0.0, 0.0), W, H)),
                            pixel_key(return_picture(STEM_MODE, ANALOG_MODE, (0.0, 0.0), W, H)))

    def test_the_return_in_rows(self):
        from display_panel import pixel_key, return_picture
        one = return_picture(1, 1, (0.500, 0.500), W, H)
        two = return_picture(1, 1, (0.505, 0.505), W, H)
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
