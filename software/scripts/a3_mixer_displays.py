# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The five OLED displays, drawn by the main process: what Core announces.

The displays are a3-mixer-set-display's -- the same multiplexer, ssd1306 and
font -- and the table of which display sits where is display_panel.PANELS,
untouched. A wrong port or channel there took the desk
down from 2026-09-10 to 2026-09-18, so nothing here knows a channel, port or
address of its own.

The pure part (where each square sits, which strip has which display) is in
display_panel and is tested, as is the partial update in a3_mixer_oled. This
module needs the Pi's hardware, so luma, PIL and smbus are imported when the
first Displays() is made, not when this file is imported.

One lock guards select-and-draw: the multiplexer is shared state, and a draw
that is interrupted between the select and the write lands on the wrong
display.
"""

import os
import sys
import threading
import time

# The set-display script lives in a subdirectory and imports its siblings by
# bare name. The unit starts a3-mixer.py from this directory, so the
# subdirectory is added here rather than moving files or touching the unit.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "a3-mixer-set-display")
)

from a3_mixer_levels import LevelGate  # noqa: E402
from display_panel import (channel_announcement, return_announcement,  # noqa: E402,F401
                           channel_squares, panel_for_channel, return_panel,  # noqa: E402
                           return_squares, PAIRS, PANELS)

MULTIPLEXER_ADDRESS = 0x70
FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def report(message):
    print(message, file=sys.stderr)


def _hardware():
    """The real multiplexer, device factory and drawing, from the Pi's libraries."""
    import smbus
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont

    from a3_mixer_oled import PartialSender

    fonts = {}
    sender = PartialSender()

    def font_for(face_height):
        # The digit fills its face (the square above the bar's strip).
        size = max(6, round(face_height * 1.1))
        if size not in fonts:
            fonts[size] = ImageFont.truetype(FONT_PATH, size)
        return fonts[size]

    def make_device(panel):
        return ssd1306(i2c(port=panel.port, address=panel.address),
                       rotate=panel.rotate)

    def draw_squares(device, squares):
        image = Image.new(device.mode, device.size)
        draw = ImageDraw.Draw(image)
        for square in squares:
            ink, paper = ("black", "white") if square.filled else ("white", "black")
            draw.rectangle(square.box, outline="white", fill=paper)
            if square.bar:
                draw.rectangle(square.bar, fill=ink)
            digit = ink
            if square.mark:
                # The return's cursor: the digit inverted on a block of ink.
                draw.rectangle(square.mark, fill=ink)
                digit = paper
            f0, g0, f1, g1 = square.face
            draw.text(((f0 + f1) / 2, (g0 + g1) / 2), square.label,
                      font=font_for(g1 - g0), fill=digit, anchor="mm")
        # Only the window that changed goes over the bus (a3_mixer_oled).
        sender.send(device, image)

    return Multiplexer(lambda: smbus.SMBus(1)), make_device, draw_squares


class Multiplexer:
    """Selects the TCA9548A's channel: one byte on a bus kept open.

    TCA9548A.I2C_setup opens a new SMBus, sleeps 1 ms, reads the channel back
    and prints it on every call -- per draw, that is. The one-shot boot script
    keeps using it; the live displays use this. A failed write closes the bus,
    and the next select opens it afresh.
    """

    def __init__(self, open_bus):
        self._open_bus = open_bus
        self._bus = None

    def __call__(self, address, channel):
        if self._bus is None:
            self._bus = self._open_bus()
        try:
            self._bus.write_byte(address, 1 << channel)
        except Exception:
            bus, self._bus = self._bus, None
            try:
                bus.close()
            except Exception:  # noqa: BLE001 -- a broken bus may not close either
                pass
            raise


class DrawTimer:
    """A line for the journal after every `every` draws: mean and worst time."""

    def __init__(self, every=50):
        self._every = every
        self._times = []

    def record(self, seconds):
        self._times.append(seconds)
        if len(self._times) < self._every:
            return None
        times, self._times = self._times, []
        return "displays: %d draws, mean %.1f ms, max %.1f ms" % (
            len(times), 1000 * sum(times) / len(times), 1000 * max(times))


RETRY_SECONDS = 2.0


def _later(seconds, then):
    timer = threading.Timer(seconds, then)
    timer.daemon = True
    timer.start()


class Displays:
    """`select(multiplexer, channel)`, `make_device(panel)` and
    `draw_squares(device, squares)` are the hardware; tests pass fakes.

    The OSC thread only posts what a panel should show; a thread of its own
    draws it (start()), and a panel always gets the latest of what was posted.
    Drawing in the OSC thread made a fast spin queue one draw per click, with
    the meters and lamps waiting behind them (2026-10-01).

    A device is built once per panel and kept: luma registers a cleanup per
    device at process exit and each holds an SMBus, so building one per draw
    would grow without bound over a set. A failed draw drops the panel's
    device and tries again RETRY_SECONDS later with the panel's latest
    picture, drawn whole on a fresh device -- with partial updates a panel
    would otherwise keep whatever it showed until its next change.
    """

    def __init__(self, select, make_device, draw_squares, report=report,
                 clock=time.monotonic, every=20, later=_later, gate=None):
        self._select = select
        self._make_device = make_device
        self._draw_squares = draw_squares
        self._report = report
        self._clock = clock
        self._timer = DrawTimer(every)
        self._lock = threading.Lock()
        self._devices = {}
        self._silent = set()  # panels already reported as not answering
        self._posted = set()  # panels to draw; each is drawn from its state
        # What each display shows, so a level redraw keeps it: the pair per
        # channel, the cursor and what plays on the return.
        self._channel_masks = [0] * (len(PANELS) - 1)
        self._return = (0, (False,) * PAIRS)
        self._cues = [False] * (len(PANELS) - 1)   # the C fields (2026-10-01)
        self._gate = gate or LevelGate()
        self._levels = {}
        self._later = later
        self._wake = threading.Condition()

    def note_level(self, pair, step):
        """A stem's level step, from the OSC thread: noted, never drawn here.
        The draw thread asks the gate at most every gate.interval seconds."""
        self._gate.update(pair, step)

    def start(self):
        threading.Thread(target=self._run, name="displays", daemon=True).start()

    def show_channel(self, index, mask):
        panel = panel_for_channel(index)
        with self._wake:
            self._channel_masks[index] = mask
        self._post(panel)

    def show_return(self, cursor, plays):
        with self._wake:
            self._return = (cursor, tuple(plays))
        self._post(return_panel())

    def show_cue(self, index, on):
        """A channel's cue: its display's C field."""
        with self._wake:
            self._cues[index] = bool(on)
        self._post(panel_for_channel(index))

    def blank_all(self):
        """Until Core speaks: every square empty, nothing claimed to play."""
        for index in range(len(PANELS) - 1):
            self.show_channel(index, 0)
        self.show_return(0, (False,) * PAIRS)

    def drain(self):
        """Draw everything posted so far, each panel once -- and every panel,
        when the gate hands out new levels.

        A posted panel (a turn, an announcement) always goes before the
        level redraws still waiting: a batch of five takes ~150 ms on the
        desk, and a turn that arrives meanwhile is drawn next."""
        levels = self._gate.due()
        with self._wake:
            if levels:
                self._levels = levels
        waiting = list(PANELS) if levels else []
        while True:
            panel = self._next_panel(waiting)
            if panel is None:
                return
            self._draw(panel, self._squares_for(panel))

    def _next_panel(self, waiting):
        """The next panel to draw: a posted one first (in table order), then
        the next level redraw. Each is taken off both lists."""
        with self._wake:
            posted = [panel for panel in PANELS if panel in self._posted]
            panel = posted[0] if posted else (waiting[0] if waiting else None)
            self._posted.discard(panel)
        if panel in waiting:
            waiting.remove(panel)
        return panel

    def _squares_for(self, panel):
        """The picture of `panel` from its state and the levels, laid out
        for whatever size the display turns out to be."""
        with self._wake:
            levels = dict(self._levels)
            if panel == return_panel():
                cursor, plays = self._return
                return lambda width, height: return_squares(
                    cursor, plays, width, height, levels)
            index = PANELS.index(panel)
            mask, cue = self._channel_masks[index], self._cues[index]
        return lambda width, height: channel_squares(mask, width, height, levels, cue=cue)

    def _post(self, panel):
        with self._wake:
            self._posted.add(panel)
            self._wake.notify()

    def _retry(self, panel):
        self._post(panel)

    def _run(self):
        while True:
            with self._wake:
                # Woken by a post at once; otherwise every gate interval,
                # to hand out levels that changed.
                self._wake.wait_for(lambda: self._posted, timeout=self._gate.interval)
            self.drain()

    def _draw(self, panel, squares_for):
        """Never raises: a display that does not answer is a line on stderr.
        `squares_for(width, height)` lays the picture out for this display."""
        began = self._clock()
        try:
            with self._lock:
                self._write(panel, squares_for)
        except Exception as error:  # noqa: BLE001 -- any I2C excuse counts
            self._devices.pop(panel, None)
            self._complain(panel, error)
            self._later(RETRY_SECONDS, lambda: self._retry(panel))
            return
        self._silent.discard(panel)
        line = self._timer.record(self._clock() - began)
        if line:
            self._report(line)

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

    def show_channel(self, index, mask):
        pass

    def show_return(self, cursor, plays):
        pass

    def show_cue(self, index, on):
        pass

    def note_level(self, pair, step):
        pass

    def blank_all(self):
        pass


def open_displays():
    try:
        displays = Displays(*_hardware())
    except Exception as error:  # noqa: BLE001 -- ImportError, font, anything
        report("displays unavailable, the desk runs without them: %s" % error)
        return NoDisplays()
    displays.start()
    return displays
