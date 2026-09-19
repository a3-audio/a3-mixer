# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Welche Taste am Kanalzug was tut, und welche Lampe dazu leuchtet.

Umgebaut am 2026-09-19 auf Ansage des Maintainers, und der Grund steht in der
Hardware: die drei Tasten eines Kanalzugs teilen sich **eine** RGB-Lampe, je
Taste ein Farbkanal -- rot PFL, gruen FX, blau 3D. In die rote Linie sind die
falschen Widerstaende geloetet, sie ist zu dunkel. Der 3D-Taster ist seit dem
2026-09-12 ausser Betrieb, seine blaue Linie also frei und hell.

Daraus folgt der Tausch: **PFL zieht auf die blaue Linie um**, weil eine
Cue-Lampe im Dunkeln gelesen werden muss, und die freigewordene rote bekommt
**Tap**, das nur blitzt. Alle vier Kanaele tragen dieselbe Tap-Funktion.

Die Tabellen stehen in einem eigenen Modul, weil `a3-mixer.py` sich ohne die
Pi-Hardware (board, neopixel, serial) nicht einmal importieren laesst -- derselbe
Schnitt wie bei a3_mixer_recall, a3_mixer_watchdog und display_panel.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from a3_mixer_panel import (CHANNEL_BUTTONS, LED_COLOUR, TAP, channel_button,
                            led_colour)


class WhatTheKeysDo(unittest.TestCase):
    def test_the_first_key_taps(self):
        self.assertEqual(TAP, channel_button("0"))

    def test_the_second_key_is_fx(self):
        self.assertEqual("fx", channel_button("1"))

    # Der ehemalige 3D-Taster. Er blieb am Panel, als seine Funktion am
    # 2026-09-12 wegfiel, und traegt jetzt PFL.
    def test_the_third_key_is_pfl(self):
        self.assertEqual("pfl", channel_button("2"))

    def test_pfl_is_no_longer_on_the_first_key(self):
        self.assertNotEqual("pfl", channel_button("0"))

    # Genau der Fehler, der am 2026-09-12 das ganze Pult taub gemacht hat:
    # eine Taste ohne Eintrag war ein blanker dict-Zugriff und damit ein
    # KeyError mitten im seriellen Leser.
    def test_a_key_with_no_entry_is_no_error(self):
        self.assertIsNone(channel_button("7"))
        self.assertIsNone(channel_button(""))

    def test_all_four_strips_share_one_table(self):
        # Die Tabelle ist nach dem Tastenindex geschluesselt, nicht nach Kanal
        # -- "alle 4 die gleiche Funktion" ist damit keine Absprache, sondern
        # Bauart.
        self.assertEqual(sorted(CHANNEL_BUTTONS), ["0", "1", "2"])


class WhichLampLights(unittest.TestCase):
    # Der eigentliche Grund des Umbaus: rot ist die Linie mit den falschen
    # Widerstaenden. Steht PFL wieder auf 0, ist die Cue-Lampe wieder zu dunkel
    # zum Lesen.
    def test_pfl_lights_the_blue_line_not_the_dim_red_one(self):
        self.assertEqual(2, led_colour("pfl"))

    def test_fx_keeps_its_green(self):
        self.assertEqual(1, led_colour("fx"))

    def test_two_lamps_never_share_a_colour(self):
        colours = list(LED_COLOUR.values())
        self.assertEqual(len(colours), len(set(colours)))

    def test_an_unknown_lamp_is_no_error(self):
        self.assertIsNone(led_colour("3d"))

    # Eine Lampe fuer jede Funktion, die eine hat. Tap hat keine: es sitzt auf
    # der roten Linie, die nichts mehr anzeigt, und blitzt nicht mit -- das
    # waere Arbeit an Core und wurde nicht bestellt.
    def test_tap_carries_no_lamp(self):
        self.assertIsNone(led_colour(TAP))


if __name__ == "__main__":
    unittest.main()
