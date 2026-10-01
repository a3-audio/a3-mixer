# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The five OLED displays, drawn by the main process: what Core announces.

The drawing is a3-mixer-set-display's -- multiplexer select, ssd1306, canvas,
the same font -- and the table of which display sits where is
display_panel.PANELS, untouched. A wrong port or channel there took the desk
down from 2026-09-10 to 2026-09-18, so nothing here knows a channel, port or
address of its own.

The pure part (where each square sits, which strip has which display) is in
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

from display_panel import (channel_announcement, return_announcement,  # noqa: E402,F401
                           channel_squares, panel_for_channel, return_panel,  # noqa: E402
                           return_squares, PAIRS, PANELS)

MULTIPLEXER_ADDRESS = 0x70
FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def report(message):
    print(message, file=sys.stderr)


def _hardware():
    """The real multiplexer, device factory and drawing, from the Pi's libraries."""
    import TCA9548A
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
    from PIL import ImageFont

    fonts = {}

    def font_for(side):
        # The number fills about two thirds of its square, whatever the panel.
        size = max(6, round(side * 0.7))
        if size not in fonts:
            fonts[size] = ImageFont.truetype(FONT_PATH, size)
        return fonts[size]

    def make_device(panel):
        return ssd1306(i2c(port=panel.port, address=panel.address),
                       rotate=panel.rotate)

    def draw_squares(device, squares):
        with canvas(device) as draw:
            for square in squares:
                x0, y0, x1, y1 = square.box
                if square.frame:
                    draw.rectangle(square.frame, outline="white", fill="black")
                ink, paper = ("black", "white") if square.filled else ("white", "black")
                draw.rectangle(square.box, outline="white", fill=paper)
                draw.text(((x0 + x1) / 2, (y0 + y1) / 2), str(square.label),
                          font=font_for(x1 - x0), fill=ink, anchor="mm")

    return TCA9548A.I2C_setup, make_device, draw_squares


class Displays:
    """`select(multiplexer, channel)`, `make_device(panel)` and
    `draw_squares(device, squares)` are the hardware; tests pass fakes.

    A device is built once per panel and kept: luma registers a cleanup per
    device at process exit and each holds an SMBus, so building one per draw
    would grow without bound over a set. A failed draw drops the panel's
    device, so a display that comes back is initialised afresh.
    """

    def __init__(self, select, make_device, draw_squares, report=report):
        self._select = select
        self._make_device = make_device
        self._draw_squares = draw_squares
        self._report = report
        self._lock = threading.Lock()
        self._devices = {}
        self._silent = set()  # panels already reported as not answering

    def show_channel(self, index, pair):
        self._draw(panel_for_channel(index),
                   lambda width, height: channel_squares(pair, width, height))

    def show_return(self, cursor, plays):
        self._draw(return_panel(),
                   lambda width, height: return_squares(cursor, plays, width, height))

    def blank_all(self):
        """Until Core speaks: every square empty, nothing claimed to play."""
        for index in range(len(PANELS) - 1):
            self.show_channel(index, 0)
        self.show_return(0, (False,) * PAIRS)

    def _draw(self, panel, squares_for):
        """Never raises: a display that does not answer is a line on stderr.
        `squares_for(width, height)` lays the picture out for this display."""
        try:
            with self._lock:
                self._write(panel, squares_for)
        except Exception as error:  # noqa: BLE001 -- any I2C excuse counts
            self._devices.pop(panel, None)
            self._complain(panel, error)
            return
        self._silent.discard(panel)

    def _write(self, panel, squares_for):
        self._select(MULTIPLEXER_ADDRESS, panel.channel)
        device = self._devices.get(panel)
        if device is None:
            device = self._make_device(panel)
            # Without it luma blanks the display when the process ends; see
            # a3-mixer-set-display.py for the measurement.
            device.persist = True
            self._devices[panel] = device
        self._draw_squares(device, squares_for(device.width, device.height))

    def _complain(self, panel, error):
        # Once per outage: a dead display would otherwise fill the journal
        # with every announcement.
        if panel in self._silent:
            return
        self._silent.add(panel)
        self._report("display '%s' (mux channel %d, bus %d, address 0x%02x) "
                     "did not answer: %s" % (panel.label, panel.channel, panel.port,
                                             panel.address, error))


class NoDisplays:
    """Stands in when the display hardware cannot be set up at all.

    The desk's pots, keys and lamps do not depend on the displays, so a missing
    luma or multiplexer is a line on stderr, not a desk that will not start.
    """

    def show_channel(self, index, pair):
        pass

    def show_return(self, cursor, plays):
        pass

    def blank_all(self):
        pass


def open_displays():
    try:
        return Displays(*_hardware())
    except Exception as error:  # noqa: BLE001 -- ImportError, font, anything
        report("displays unavailable, the desk runs without them: %s" % error)
        return NoDisplays()
