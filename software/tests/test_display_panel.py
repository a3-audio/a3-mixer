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
    def test_the_fifth_is_the_fx_return(self):
        self.assertEqual("FX Return", PANELS[-1].label)

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


class StemSquares(unittest.TestCase):
    """Five columns, two rows (maintainer, 2026-10-01): StemDeck 1's stems 1-4
    on top, StemDeck 2's below, and the analog input "A" at the bottom right.
    Filled while it plays. The return marks the square its encoder is on by
    inverting the digit: a block of the other colour behind it. Sizes follow
    the panel, so a 128x32 display draws the same picture smaller."""

    def test_a_channel_has_eight_stems_and_the_analog_input(self):
        from display_panel import channel_squares
        labels = [s.label for s in channel_squares(0, 128, 64)]
        self.assertEqual(labels, ["1", "2", "3", "4", "1", "2", "3", "4", "A"])

    def test_stemdeck_one_is_the_top_row(self):
        from display_panel import channel_squares
        squares = channel_squares(0, 128, 64)
        self.assertTrue(all(s.box[3] <= 32 for s in squares[:4]))
        self.assertTrue(all(s.box[1] >= 32 for s in squares[4:]))

    def test_the_stems_stand_in_columns_and_a_is_at_the_right(self):
        from display_panel import channel_squares
        squares = channel_squares(0, 128, 64)
        top = [s.box[0] for s in squares[:4]]
        bottom = [s.box[0] for s in squares[4:8]]
        self.assertEqual(top, bottom)
        self.assertEqual(top, sorted(top))
        self.assertGreater(squares[8].box[0], bottom[-1])

    def test_a_channel_on_its_analog_input_fills_a(self):
        from display_panel import channel_squares
        filled = [s.filled for s in channel_squares(0, 128, 64)]
        self.assertEqual(filled, [False] * 8 + [True])

    def test_a_channel_on_a_stem_fills_only_that_stem(self):
        from display_panel import channel_squares
        filled = [s.filled for s in channel_squares(6, 128, 64)]
        self.assertEqual(filled, [False] * 5 + [True] + [False] * 3)

    def test_a_channel_marks_nothing(self):
        from display_panel import channel_squares
        self.assertFalse(any(s.mark for s in channel_squares(3, 128, 64)))

    def test_the_return_has_the_stems_and_no_a(self):
        from display_panel import channel_squares, return_squares
        squares = return_squares(1, (True,) * 8, 128, 64)
        self.assertEqual([s.label for s in squares], ["1", "2", "3", "4"] * 2)
        self.assertEqual([s.box for s in squares],
                         [s.box for s in channel_squares(0, 128, 64)[:8]])

    def test_the_return_fills_what_plays_and_marks_the_cursor(self):
        from display_panel import return_squares
        plays = (True, False, False, True, True, True, True, True)
        squares = return_squares(2, plays, 128, 64)
        self.assertEqual([s.filled for s in squares], list(plays))
        self.assertEqual([bool(s.mark) for s in squares],
                         [False, True] + [False] * 6)

    def test_a_return_with_no_free_pair_marks_nothing(self):
        from display_panel import return_squares
        squares = return_squares(0, (False,) * 8, 128, 64)
        self.assertFalse(any(s.mark for s in squares))

    def test_the_mark_sits_inside_its_square(self):
        from display_panel import return_squares
        square = return_squares(1, (True,) * 8, 128, 64)[0]
        (x0, y0, x1, y1), (m0, n0, m1, n1) = square.box, square.mark
        self.assertTrue(x0 < m0 < m1 < x1 and y0 < n0 < n1 < y1)

    def test_squares_are_square_and_inside_the_panel(self):
        from display_panel import channel_squares
        for width, height in ((128, 64), (128, 32)):
            for s in channel_squares(0, width, height):
                x0, y0, x1, y1 = s.box
                self.assertEqual(x1 - x0, y1 - y0)
                self.assertTrue(0 <= x0 and 0 <= y0 and x1 < width and y1 < height,
                                (width, height, s))

    def test_the_squares_follow_the_panel_size(self):
        from display_panel import channel_squares
        def side(height):
            box = channel_squares(0, 128, height)[0].box
            return box[2] - box[0]
        self.assertGreater(side(64), side(32))


class StemPanels(unittest.TestCase):
    def test_channels_zero_to_three_are_the_four_decks(self):
        from display_panel import panel_for_channel
        self.assertEqual([panel_for_channel(i).label for i in range(4)],
                         ["Deck 1", "Deck 2", "Deck 3", "Deck 4"])

    def test_the_return_is_the_fx_return_panel(self):
        from display_panel import return_panel
        self.assertEqual(return_panel().label, "FX Return")

    def test_the_mapping_hands_out_the_table_rows_themselves(self):
        from display_panel import PANELS, panel_for_channel, return_panel
        self.assertIs(panel_for_channel(0), PANELS[0])
        self.assertIs(return_panel(), PANELS[4])

    def test_a_channel_the_desk_does_not_have_is_refused(self):
        from display_panel import panel_for_channel
        for index in (-1, 4, 5):
            with self.assertRaises(IndexError):
                panel_for_channel(index)


class StemAnnouncements(unittest.TestCase):
    def test_a_channel_announcement_is_one_pair(self):
        from display_panel import channel_announcement
        self.assertEqual(channel_announcement((3,)), 3)
        self.assertEqual(channel_announcement((0,)), 0)

    def test_a_damaged_channel_announcement_is_none(self):
        from display_panel import channel_announcement
        for args in ((), ("x",), (9,), (-1,), (None,), (1.5,), ("3",)):
            self.assertIsNone(channel_announcement(args), args)

    def test_a_return_announcement_is_cursor_and_eight_pairs(self):
        from display_panel import return_announcement
        self.assertEqual(return_announcement((2, 1, 0, 0, 1, 1, 1, 1, 1)),
                         (2, (True, False, False, True, True, True, True, True)))
        self.assertEqual(return_announcement((0,) * 9), (0, (False,) * 8))

    def test_a_damaged_return_announcement_is_none(self):
        from display_panel import return_announcement
        for args in ((), (2, 1), (2,) + (1,) * 7, (2,) + (1,) * 9,
                     (9,) + (1,) * 8, (2, 2) + (1,) * 7, ("a",) + (1,) * 8,
                     (2, True) + (1,) * 7):
            self.assertIsNone(return_announcement(args), args)


if __name__ == "__main__":
    unittest.main()
