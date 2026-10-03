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
NOWHERE = [None] * 8


class ChannelMenu(unittest.TestCase):
    """Each channel encoder is a two-level menu (spec desk-stem-grid-2). The
    top level says which deck and which stem play: D1.3  D2.-  A
    (2026-10-03); a deck's level edits its field in place, the cursor only
    behind the dot (2026-10-03)."""

    def test_the_top_level_names_deck_and_stem(self):
        from display_panel import menu_items
        places = [None, None, 0, None] + [None] * 4    # pair 3 = D1 stem 3 on channel 1
        items = menu_items(0, (0, 1), places, W, H)
        self.assertEqual([i.text for i in items], ["D1.3", "D2.-", "A"])
        self.assertEqual([i.inverted for i in items], [False, True, False])

    def test_a_stem_of_each_deck_shows_both(self):
        from display_panel import menu_items
        places = [None, 1, None, None, None, None, 1, None]   # D1.2 and D2.3 on channel 2
        items = menu_items(1, (0, 0), places, W, H)
        self.assertEqual([i.text for i in items], ["D1.2", "D2.3", "A"])
        self.assertEqual([i.marked for i in items], [True, True, False])

    def test_analog_is_marked(self):
        from display_panel import menu_items
        self.assertEqual([i.marked for i in menu_items(0, (0, 0), NOWHERE, W, H)],
                         [False, False, True])

    def test_a_deck_level_keeps_the_three_fields(self):
        """2026-10-03: no sub-level screen -- the edit happens in the deck's
        own field, behind its dot; the other two stay as they are."""
        from display_panel import menu_items
        places = [None, None, 0, None, None, 0, None, None]   # D1.3 and D2.2 on channel 1
        items = menu_items(0, (1, 1), places, W, H)
        self.assertEqual([i.text for i in items], ["D1.2", "D2.2", "A"])
        self.assertEqual([i.box for i in items], [i.box for i in menu_items(0, (0, 0), places, W, H)])

    def test_the_cursor_is_only_behind_the_dot(self):
        from display_panel import menu_items
        items = menu_items(0, (2, 3), NOWHERE, W, H)
        self.assertEqual([i.text for i in items], ["D1.-", "D2.4", "A"])
        self.assertEqual([i.inverted for i in items], [False, False, False])
        self.assertEqual([i.cursor_from for i in items], [None, 3, None])

    def test_the_top_level_inverts_whole_fields(self):
        from display_panel import menu_items
        self.assertEqual([i.cursor_from for i in menu_items(0, (0, 1), NOWHERE, W, H)],
                         [None, None, None])

    def test_back_shows_behind_the_dot(self):
        from display_panel import menu_items
        items = menu_items(0, (1, 4), NOWHERE, W, H)
        self.assertEqual(items[0].text, "D1.<")
        self.assertEqual(items[0].cursor_from, 3)

    def test_back_is_marked_while_the_deck_plays_here(self):
        """'<' changes nothing: the field keeps the mark of what plays."""
        from display_panel import menu_items
        self.assertTrue(menu_items(0, (1, 4), [0] + [None] * 7, W, H)[0].marked)
        self.assertFalse(menu_items(0, (1, 4), NOWHERE, W, H)[0].marked)

    def test_the_stem_this_channel_plays_is_marked_one_elsewhere_crossed(self):
        from display_panel import menu_items
        places = [0, 3, None, 4] + [None] * 4          # pair 1 here, pair 2 on ch 4, pair 4 on AUX
        here = menu_items(0, (1, 0), places, W, H)[0]
        elsewhere = menu_items(0, (1, 1), places, W, H)[0]
        on_aux = menu_items(0, (1, 3), places, W, H)[0]
        self.assertTrue(here.marked and not here.crossed)
        self.assertTrue(elsewhere.crossed)
        self.assertFalse(elsewhere.marked)
        self.assertEqual(elsewhere.note, "4")
        self.assertFalse(on_aux.crossed)               # on the return: loadable

    def test_a_crossed_deck_2_stem_crosses_the_d2_field(self):
        from display_panel import menu_items
        places = [None] * 4 + [2, None, None, None]    # D2.1 on channel 3
        items = menu_items(0, (2, 0), places, W, H)
        self.assertEqual([i.crossed for i in items], [False, True, False])
        self.assertEqual(items[1].note, "3")

    def test_the_items_sit_in_the_upper_half_side_by_side(self):
        from display_panel import menu_items
        for menu in ((0, 0), (1, 0)):
            boxes = [i.box for i in menu_items(0, menu, NOWHERE, W, H)]
            self.assertTrue(all(0 <= x0 < x1 < W and 0 <= y0 < y1 < H // 2
                                for x0, y0, x1, y1 in boxes))
            self.assertTrue(all(a[2] <= b[0] for a, b in zip(boxes, boxes[1:])))

    def test_the_menu_follows_the_panel(self):
        from display_panel import menu_items
        self.assertTrue(all(i.box[3] < 16 for i in menu_items(0, (1, 0), NOWHERE, 128, 32)))


class TheReturn(unittest.TestCase):
    """The return knows stem and analog, and shows nine meters instead of a
    wave (spec desk-stem-grid-2)."""

    def test_two_fields_the_mode_marked_the_cursor_inverted(self):
        from display_panel import return_items
        items = return_items(1, 0, W, H)
        self.assertEqual([i.text for i in items], ["STEM", "ANALOG"])
        self.assertEqual([i.marked for i in items], [True, False])
        self.assertEqual([i.inverted for i in items], [False, True])

    def test_nine_bars_the_last_split_in_two(self):
        from display_panel import return_bars
        bars = return_bars([1.0] * 8, (1.0, 1.0), W, H)
        self.assertEqual(len(bars), 10)
        for x0, y0, x1, y1 in bars:
            self.assertTrue(H // 2 <= y0 <= y1 < H and 0 <= x0 <= x1 < W)
        left, right = bars[8], bars[9]
        self.assertLess(left[2], right[0])

    def test_a_silent_meter_has_no_bar(self):
        from display_panel import return_bars
        bars = return_bars([0.0] * 8, (0.0, 0.5), W, H)
        self.assertEqual([b is None for b in bars], [True] * 9 + [False])

    def test_a_louder_meter_is_taller(self):
        from display_panel import return_bars
        bars = return_bars([0.25, 1.0] + [0.0] * 6, (0.0, 0.0), W, H)
        self.assertLess(bars[1][1], bars[0][1])


class Waveform(unittest.TestCase):
    """StemDeck's style: a mirrored envelope, newest at the right edge."""
    BOX = (0, 32, 127, 63)

    def test_levels_map_in_db(self):
        from display_panel import wave_level
        self.assertEqual(wave_level(1.0), 1.0)
        self.assertEqual(wave_level(0.0), 0.0)
        self.assertEqual(wave_level(-1), 0.0)
        self.assertEqual(wave_level("x"), 0.0)
        self.assertAlmostEqual(wave_level(10 ** (-24 / 20)), 0.5, places=2)

    def test_the_newest_enters_at_the_right(self):
        from display_panel import Wave
        wave = Wave(128)
        wave.step(1.0)
        x, top, bottom = wave.columns(self.BOX)[-1]
        self.assertEqual((x, top, bottom), (127, 32, 63))

    def test_it_runs_right_to_left(self):
        from display_panel import Wave
        wave = Wave(128)
        wave.step(1.0)
        wave.step(0.0)
        tall = [x for x, top, bottom in wave.columns(self.BOX) if bottom - top > 1]
        self.assertEqual(tall, [124, 125])

    def test_the_history_is_capped_at_the_width(self):
        from display_panel import Wave
        wave = Wave(128)
        for _ in range(1000):
            wave.step(0.5)
        self.assertEqual(len(wave.columns(self.BOX)), 128)
        self.assertEqual(len(Wave(128).columns(self.BOX)), 128)

    def test_mirrored_about_the_middle(self):
        from display_panel import Wave
        wave = Wave(128)
        wave.step(0.5)
        x, top, bottom = wave.columns(self.BOX)[-1]
        self.assertEqual(top - 32, 63 - bottom)
        self.assertTrue(32 < top < bottom < 63)


class TheWaveStrip(unittest.TestCase):
    """The wave's picture is moved, not repainted (desk-stem-grid-2: the
    128 lines cost most of a 53 ms draw on the desk)."""

    def painted(self, wave, width, height):
        from PIL import Image, ImageDraw
        image = Image.new("1", (width, height))
        draw = ImageDraw.Draw(image)
        for x, top, bottom in wave.columns((0, 0, width - 1, height - 1)):
            draw.line((x, top, x, bottom), fill="white")
        return image

    def test_shifting_draws_what_a_full_repaint_draws(self):
        import random
        from display_panel import Wave, WaveStrip
        rng = random.Random(7)
        strip, wave = WaveStrip(128, 32), Wave(128)
        for _ in range(40):
            level = rng.choice([0.0, rng.random(), 1.0])
            strip.shift(level)
            wave.step(level)
            self.assertEqual(list(strip.image.getdata()),
                             list(self.painted(wave, 128, 32).getdata()))

    def test_a_silent_shift_is_no_change(self):
        from display_panel import WaveStrip
        strip = WaveStrip(128, 32)
        self.assertFalse(strip.shift(0.0))
        self.assertTrue(strip.shift(0.7))


class MenuAnnouncements(unittest.TestCase):
    def test_a_menu_is_a_level_and_a_cursor(self):
        from display_panel import menu_announcement
        self.assertEqual(menu_announcement((0, 2)), (0, 2))
        self.assertEqual(menu_announcement((2, 4)), (2, 4))
        for args in ((0, 3), (3, 0), (1, 5), (-1, 0), ("0", 1), (True, 0), (0,), ()):
            self.assertIsNone(menu_announcement(args), args)

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
