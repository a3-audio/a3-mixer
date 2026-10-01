# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The five OLED displays, drawn by the main process: what Core announces.

The drawing is a3-mixer-set-display's -- multiplexer select, ssd1306, canvas,
the same font -- and the table of which display sits where is
display_panel.PANELS, untouched. A wrong port or channel there took the desk
down from 2026-09-10 to 2026-09-18, so nothing here knows a channel, port or
address of its own.

The pure part (what the text says, which strip has which display) is in
display_panel and is tested. This module needs the Pi's hardware, so luma, PIL
and TCA9548A are imported when the first Displays() is made, not when this
file is imported.

One lock guards select-and-draw: the multiplexer is shared state, and a draw
that is interrupted between the select and the write lands on the wrong
display.
"""

import os
import sys
import threading

# The set-display script lives in a subdirectory and imports its siblings by
# bare name. The unit starts a3-mixer.py from this directory, so the
# subdirectory is added here rather than moving files or touching the unit.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "a3-mixer-set-display")
)

from display_panel import (channel_text, panel_for_channel, return_panel,  # noqa: E402
                           return_text, PANELS)

MULTIPLEXER_ADDRESS = 0x70
FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def report(message):
    print(message, file=sys.stderr)


class Displays:
    def __init__(self):
        import TCA9548A
        from luma.core.interface.serial import i2c
        from luma.core.render import canvas
        from luma.oled.device import ssd1306
        from PIL import ImageFont

        self._select = TCA9548A.I2C_setup
        self._i2c = i2c
        self._canvas = canvas
        self._ssd1306 = ssd1306
        self._font = ImageFont.truetype(FONT_PATH, 14)
        self._lock = threading.Lock()
        self._silent = set()  # panels already reported as not answering

    def show_channel(self, index, pair):
        self._draw(panel_for_channel(index), channel_text(pair))

    def show_return(self, pair, muted):
        self._draw(return_panel(), return_text(pair, muted))

    def blank_all(self):
        for panel in PANELS:
            self._draw(panel, channel_text(0))

    def _draw(self, panel, text):
        """Never raises: a display that does not answer is a line on stderr."""
        try:
            with self._lock:
                self._write(panel, text)
        except Exception as error:  # noqa: BLE001 -- any I2C excuse counts
            self._complain(panel, error)
            return
        self._silent.discard(panel)

    def _write(self, panel, text):
        self._select(MULTIPLEXER_ADDRESS, panel.channel)
        device = self._ssd1306(self._i2c(port=panel.port, address=panel.address),
                               rotate=panel.rotate)
        with self._canvas(device) as draw:
            draw.rectangle(device.bounding_box, outline="white", fill="black")
            draw.text((15, 5), text, font=self._font, fill="white")

    def _complain(self, panel, error):
        # Once per outage: a dead display would otherwise fill the journal
        # with every announcement.
        if panel in self._silent:
            return
        self._silent.add(panel)
        report("display '%s' (mux channel %d, bus %d, address 0x%02x) "
               "did not answer: %s" % (panel.label, panel.channel, panel.port,
                                       panel.address, error))


class NoDisplays:
    """Stands in when the display hardware cannot be set up at all.

    The desk's pots, keys and lamps do not depend on the displays, so a missing
    luma or multiplexer is a line on stderr, not a desk that will not start.
    """

    def show_channel(self, index, pair):
        pass

    def show_return(self, pair, muted):
        pass

    def blank_all(self):
        pass


def open_displays():
    try:
        return Displays()
    except Exception as error:  # noqa: BLE001 -- ImportError, font, anything
        report("displays unavailable, the desk runs without them: %s" % error)
        return NoDisplays()
