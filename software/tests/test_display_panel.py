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
    under D1 | D2 | A, the playing input solid, the cursor under its meter."""

    def picture(self, cursor=8, mask=0, levels=(0.5,) * 9, width=W, height=H):
        from display_panel import channel_picture
        return channel_picture(cursor, mask, levels, width, height)

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

    def test_analog_plays_when_no_stem_does(self):
        self.assertEqual([m.solid for m in self.picture(mask=0).meters], [False] * 8 + [True])

    def test_the_stem_on_the_channel_is_solid(self):
        solid = [m.solid for m in self.picture(mask=stem(6)).meters]
        self.assertEqual(solid, [False] * 5 + [True] + [False] * 3)

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


class ReturnSelector(unittest.TestCase):
    """The return shows two meters, SA (the stems on the return) and A (the
    analog return); the mode that plays is solid."""

    def picture(self, cursor=1, mode=1, sa=0.5, a=0.5):
        from display_panel import return_picture
        return return_picture(cursor, mode, sa, a, W, H)

    def test_sa_then_a(self):
        p = self.picture(sa=0.25, a=0.75)
        self.assertEqual([h.text for h in p.headings], ["SA", "A"])
        self.assertEqual([m.level for m in p.meters], [0.25, 0.75])

    def test_the_mode_that_plays_is_solid(self):
        from display_panel import ANALOG_MODE, STEM_MODE
        self.assertEqual([m.solid for m in self.picture(mode=STEM_MODE).meters], [True, False])
        self.assertEqual([m.solid for m in self.picture(mode=ANALOG_MODE).meters], [False, True])

    def test_the_cursor_is_under_its_option(self):
        from display_panel import ANALOG_MODE
        p = self.picture(cursor=ANALOG_MODE)
        self.assertEqual(p.cursor[0], p.meters[1].box[0])


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

    def test_the_input_of_a_mask(self):
        from display_panel import ANALOG_INPUT, active_input
        self.assertEqual(active_input(0), ANALOG_INPUT)
        self.assertEqual(active_input(stem(3)), 2)
        self.assertEqual(active_input(stem(2) | stem(7)), 1)


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
