# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The stem meters on the main VU's top 8x8 module (spec desk-stem-grid-2).

One column per stem, A1-A4 then B1-B4, a bar of 0-8 LEDs from the peak in dB
(display_panel.wave_level, the displays' own scale). The firmware draws an
`SVU:<column>:<leds>` line; a line goes out only when a stem's bar changed --
StemDeck sends each meter 25 times a second, and the serial line carries the
lamps and the other meters too. Pure.
"""

from display_panel import wave_level

LEDS = 8


class StemLeds:
    def __init__(self):
        self._shown = {}

    def line(self, pair, peak):
        """The SVU line for stem `pair` (1-8) at `peak`, or None if its bar
        is what the firmware already shows."""
        leds = round(wave_level(peak) * LEDS)
        if self._shown.get(pair) == leds:
            return None
        self._shown[pair] = leds
        return "SVU:%d:%d" % (pair - 1, leds)
