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


class Fields(unittest.TestCase):
    """The stem selector's fields (spec desk-stem-selector, 2026-10-02): the
    symbol of the place a stem plays, a frame for the selection, a level bar
    under each stem -- no labels, no C."""

    def test_every_stem_shows_the_symbol_of_its_place(self):
        from display_panel import channel_fields, places_of
        places = places_of([1 << 0, 1 << 5, 0, 0], [False, True] + [False] * 6)
        symbols = [f.symbol for f in channel_fields(0, places, 0, 128, 64)[:8]]
        self.assertEqual(symbols, ["circle", "star", None, None, None, "square", None, None])

    def test_every_stem_on_a_channel_shows_its_symbol(self):
        from display_panel import channel_fields, places_of
        places = places_of([0, 0, (1 << 1) | (1 << 6), 0], [False] * 8)
        symbols = [f.symbol for f in channel_fields(1, places, 0, 128, 64)[:8]]
        self.assertEqual(symbols.count("triangle"), 2)

    def test_a_shows_the_channels_own_symbol_while_it_plays_analog(self):
        from display_panel import channel_fields, places_of
        on_a = channel_fields(3, places_of([0] * 4, [False] * 8), 0, 128, 64)[8]
        on_stem = channel_fields(3, places_of([0, 0, 0, 1], [False] * 8), 0, 128, 64)[8]
        self.assertEqual((on_a.symbol, on_stem.symbol), ("diamond", None))

    def test_the_selection_is_framed(self):
        from display_panel import channel_fields, places_of
        fields = channel_fields(0, places_of([0] * 4, [False] * 8), 3, 128, 64)
        self.assertEqual([f.framed for f in fields], [False, False, True] + [False] * 6)
        self.assertTrue(channel_fields(0, places_of([0] * 4, [False] * 8), 0, 128, 64)[8].framed)

    def test_the_return_has_an_empty_field_instead_of_a(self):
        from display_panel import places_of, return_fields
        fields = return_fields(places_of([0] * 4, [False] * 8), 0, 128, 64)
        self.assertEqual(len(fields), 9)
        self.assertIsNone(fields[8].symbol)
        self.assertTrue(fields[8].framed)

    def test_the_bar_sits_under_its_field(self):
        from display_panel import channel_fields, places_of
        field = channel_fields(0, places_of([0] * 4, [False] * 8), 0, 128, 64, {1: 6})[0]
        self.assertGreater(field.bar[1], field.box[3])
        self.assertEqual(field.bar[2] - field.bar[0], field.box[2] - field.box[0])

    def test_no_level_no_bar_and_a_has_none(self):
        from display_panel import channel_fields, places_of
        fields = channel_fields(0, places_of([0] * 4, [False] * 8), 0, 128, 64, {1: 0})
        self.assertIsNone(fields[0].bar)
        self.assertIsNone(fields[8].bar)

    def test_fields_are_smaller_than_the_old_squares(self):
        from display_panel import channel_fields, places_of
        box = channel_fields(0, places_of([0] * 4, [False] * 8), 0, 128, 64)[0].box
        self.assertLessEqual(box[2] - box[0], round(min(128 / 5, 64 / 2) * 0.5))

    def test_the_fields_follow_the_panel_size(self):
        from display_panel import channel_fields, places_of
        def side(height):
            box = channel_fields(0, places_of([0] * 4, [False] * 8), 0, 128, height)[0].box
            return box[2] - box[0]
        self.assertGreater(side(64), side(32))

    def test_every_field_and_bar_stays_inside_the_panel(self):
        from display_panel import channel_fields, places_of
        fields = channel_fields(0, places_of([0] * 4, [False] * 8), 0, 128, 64,
                                {p: 6 for p in range(1, 9)})
        for f in fields:
            for x0, y0, x1, y1 in [f.box] + ([f.bar] if f.bar else []):
                self.assertTrue(0 <= x0 < x1 <= 128 and 0 <= y0 < y1 <= 64, f)


class SymbolShapes(unittest.TestCase):
    """What the painter draws for each symbol, inside the field (inset)."""

    def test_each_symbol_is_a_shape_inside_its_field(self):
        from display_panel import SYMBOLS, symbol_shape
        box = (10, 10, 30, 30)
        for symbol in SYMBOLS:
            kind, coords = symbol_shape(symbol, box)
            self.assertIn(kind, ("ellipse", "rectangle", "polygon"), symbol)
            xs, ys = coords[0::2], coords[1::2]
            self.assertTrue(min(xs) > 10 and max(xs) < 30 and min(ys) > 10 and max(ys) < 30,
                            (symbol, coords))

    def test_the_five_look_different(self):
        from display_panel import SYMBOLS, symbol_shape
        shapes = {symbol_shape(s, (0, 0, 20, 20)) for s in SYMBOLS}
        self.assertEqual(5, len(shapes))

    def test_the_star_has_ten_corners(self):
        from display_panel import symbol_shape
        kind, coords = symbol_shape("star", (0, 0, 20, 20))
        self.assertEqual((kind, len(coords)), ("polygon", 20))


W, H = 128, 64
NOWHERE = [None] * 8


class Grid(unittest.TestCase):
    """The stem grid (spec desk-stem-grid, 2026-10-02): dots packed close in
    the upper half, the waveform below."""

    def test_ten_square_adjacent_cells_in_the_upper_half(self):
        from display_panel import grid_cells
        boxes = grid_cells(W, H)
        self.assertEqual(len(boxes), 10)
        for x0, y0, x1, y1 in boxes:
            self.assertEqual(x1 - x0, y1 - y0)
            self.assertTrue(0 <= x0 and x1 < W and 0 <= y0 and y1 < H // 2)
        self.assertEqual(boxes[1][0] - boxes[0][0], boxes[0][2] - boxes[0][0])

    def test_the_grid_follows_the_panel(self):
        from display_panel import grid_cells
        self.assertTrue(all(y1 < 16 for _, _, _, y1 in grid_cells(128, 32)))

    def test_the_wave_has_the_lower_half(self):
        from display_panel import wave_box
        self.assertEqual(wave_box(W, H), (0, 32, 127, 63))


class ChannelCells(unittest.TestCase):
    def test_a_stem_on_another_channel_is_a_ring(self):
        from display_panel import channel_cells
        places = [1, None, 4, None, None, None, None, None]   # pair 3 on the return
        cells = channel_cells(0, places, 0, W, H)
        self.assertEqual(cells[0].mark, "ring")
        self.assertEqual(cells[2].mark, "dot")

    def test_the_own_digit_stands_at_what_is_loaded(self):
        from display_panel import channel_cells
        places = [None, 0, None, None, None, None, None, None]
        cells = channel_cells(0, places, 0, W, H)
        self.assertEqual([c.digit for c in cells], [None, "1"] + [None] * 7)
        self.assertIsNone(cells[1].mark)

    def test_analog_carries_the_digit_at_a(self):
        from display_panel import channel_cells
        self.assertEqual(channel_cells(2, NOWHERE, 0, W, H)[8].digit, "3")

    def test_the_cursor_is_inverted(self):
        from display_panel import channel_cells
        cells = channel_cells(0, NOWHERE, 5, W, H)
        self.assertEqual([c.inverted for c in cells].index(True), 4)
        self.assertTrue(channel_cells(0, NOWHERE, 0, W, H)[8].inverted)


class ReturnCells(unittest.TestCase):
    def test_every_stem_shows_where_it_plays(self):
        from display_panel import return_cells
        places = [0, 4, None, 2, None, None, None, None]
        cells = return_cells(places, 3, W, H)
        self.assertEqual([c.digit for c in cells], ["1", "5", None, "3", None, None, None, None])
        self.assertEqual(cells[2].mark, "dot")
        self.assertTrue(cells[2].inverted)

    def test_nothing_free_inverts_nothing(self):
        from display_panel import return_cells
        self.assertFalse(any(c.inverted for c in return_cells([0] * 8, 0, W, H)))

    def test_the_cells_sit_in_the_grid(self):
        from display_panel import grid_cells, return_cells
        self.assertEqual([c.box for c in return_cells(NOWHERE, 1, W, H)], grid_cells(W, H)[:8])


class SelectionAnnouncements(unittest.TestCase):
    def test_a_selection_announcement_is_zero_to_eight(self):
        from display_panel import selected_announcement
        self.assertEqual(selected_announcement((4,)), 4)
        self.assertEqual(selected_announcement((0,)), 0)
        for args in ((9,), (-1,), ("1",), (True,), ()):
            self.assertIsNone(selected_announcement(args), args)


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
        self.assertEqual(return_announcement((2, 1, 0, 0, 1, 1, 1, 1, 1)),
                         (2, (True, False, False, True, True, True, True, True)))
        self.assertEqual(return_announcement((0,) * 9), (0, (False,) * 8))

    def test_the_cursor_stops_at_eight(self):
        from display_panel import return_announcement
        self.assertEqual(return_announcement((8,) + (1,) * 8)[0], 8)
        self.assertIsNone(return_announcement((9,) + (1,) * 8))

    def test_a_damaged_return_announcement_is_none(self):
        from display_panel import return_announcement
        for args in ((), (2, 1), (2,) + (1,) * 7, (2,) + (1,) * 9,
                     (10,) + (1,) * 8, (2, 2) + (1,) * 7, ("a",) + (1,) * 8,
                     (2, True) + (1,) * 7):
            self.assertIsNone(return_announcement(args), args)


if __name__ == "__main__":
    unittest.main()
