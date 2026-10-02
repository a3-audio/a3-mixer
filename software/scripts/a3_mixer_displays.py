# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The five OLED displays, drawn by the main process: what Core announces.

The displays are a3-mixer-set-display's -- the same multiplexer and ssd1306
-- and the table of which display sits where is display_panel.PANELS,
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

import functools  # noqa: E402
from collections import namedtuple  # noqa: E402

from display_panel import (channel_announcement, return_announcement,  # noqa: E402,F401
                           menu_announcement, mode_announcement, menu_items, return_items,
                           return_bars, places_of, panel_for_channel, return_panel, wave_box,
                           wave_level, STEM_MODE, WAVE_STEPS_PER_SECOND, PAIRS, PANELS,
                           WaveStrip)

#: What a panel shows (spec desk-stem-grid-2): the menu's items in the upper
#: half; below, a channel's wave as (x, top, bottom) columns and -- the fast
#: path -- its picture to paste (WaveStrip), or the return's nine bars.
Picture = namedtuple("Picture", "items wave strip bars", defaults=(None, None))

#: The panel's wave half, as the SSD1306 has it: how much history a wave
#: keeps and the size of its picture. A panel of another size gets the
#: wave as columns instead of the picture.
WAVE_HISTORY = 128
WAVE_HEIGHT = 32

#: A meter not heard for this long is silence: StemDeck or the analyzer
#: stopped, and the last peak must not stand on the display for ever.
METER_STALE_SECONDS = 0.5

#: Text height as a share of its item's box; a note (a crossed stem's
#: channel) is smaller still.
TEXT_OF_ITEM = 0.75
NOTE_OF_ITEM = 0.45


@functools.lru_cache(maxsize=8)
def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size)
    except TypeError:   # a Pillow before 10.1 has one bitmap size only
        return ImageFont.load_default()


def _text(draw, box, text, size, ink, anchor):
    """`text` in `box`, as large as `size` and no larger than fits:
    ANALOG at the menu's size ran past the panel's edge."""
    x0, y0, x1, y1 = box
    size = max(6, size)
    while True:
        font = _font(size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        if size == 6 or (right - left <= x1 - x0 - 3 and bottom - top <= y1 - y0 - 2):
            break
        size -= 1
    if anchor == "centre":
        at = ((x0 + x1 - left - right) / 2, (y0 + y1 - top - bottom) / 2)
    else:   # top right
        at = (x1 - right, y0 - top)
    draw.text(at, text, fill=ink, font=font)


@functools.lru_cache(maxsize=64)
def upper_half(items, width, height):
    """The menu's picture: painted once per state, then taken from here --
    repainting it on every wave step cost 8 ms a draw on the desk."""
    from PIL import Image, ImageDraw

    image = Image.new("1", (width, height // 2))
    draw = ImageDraw.Draw(image)
    for item in items:
        x0, y0, x1, y1 = item.box
        ink = "white"
        if item.inverted:
            draw.rectangle(item.box, fill="white")
            ink = "black"
        size = round((y1 - y0) * TEXT_OF_ITEM)
        _text(draw, item.box, item.text, size, ink, "centre")
        if item.marked:
            # Under the box, always white: under the cursor's white box a
            # black line inside it vanished (final review, 2026-10-02).
            draw.line((x0 + 1, y1 + 2, x1 - 1, y1 + 2), fill="white")
        if item.crossed:
            draw.line((x0, y1, x1, y0), fill=ink)
            _text(draw, item.box, item.note, round((y1 - y0) * NOTE_OF_ITEM), ink, "top right")
    return image


def paint(image, picture):
    """Draw `picture` onto a 1-bit PIL image: the menu (cached), then the
    wave pasted or drawn, or the return's bars."""
    from PIL import ImageDraw

    image.paste(upper_half(tuple(picture.items), image.width, image.height), (0, 0))
    draw = ImageDraw.Draw(image)
    for bar in picture.bars or []:
        if bar:
            draw.rectangle(bar, fill="white")
    if picture.strip is not None:
        image.paste(picture.strip, (0, image.height - picture.strip.height))
        return
    for x, top, bottom in picture.wave:
        draw.line((x, top, x, bottom), fill="white")


MULTIPLEXER_ADDRESS = 0x70


def report(message):
    print(message, file=sys.stderr)


def _hardware():
    """The real multiplexer, device factory and drawing, from the Pi's libraries."""
    import smbus
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from PIL import Image

    from a3_mixer_oled import PartialSender

    sender = PartialSender()

    def make_device(panel):
        return ssd1306(i2c(port=panel.port, address=panel.address),
                       rotate=panel.rotate)

    def draw_picture(device, picture):
        image = Image.new(device.mode, device.size)
        paint(image, picture)
        # Only the window that changed goes over the bus (a3_mixer_oled).
        sender.send(device, image)

    return Multiplexer(lambda: smbus.SMBus(1)), make_device, draw_picture


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
    `draw_fields(device, picture)` are the hardware; tests pass fakes.

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

    def __init__(self, select, make_device, draw_fields, report=report,
                 clock=time.monotonic, every=500, later=_later):
        self._select = select
        self._make_device = make_device
        self._draw_fields = draw_fields
        self._report = report
        self._clock = clock
        self._timer = DrawTimer(every)
        self._lock = threading.Lock()
        self._devices = {}
        self._silent = set()  # panels already reported as not answering
        self._posted = set()  # panels to draw; each is drawn from its state
        self._wave_due = set()  # panels whose wave moved: drawn when nothing is posted
        # What the displays show, so a wave redraw keeps it: what plays on
        # each channel, each channel's menu, the return's cursor and what
        # plays there, and its mode (spec desk-stem-grid-2).
        self._channel_masks = [0] * (len(PANELS) - 1)
        self._menus = [(0, 0)] * (len(PANELS) - 1)
        self._return = (STEM_MODE, (False,) * PAIRS)
        self._return_mode = STEM_MODE
        # The meters: (loudest peak since the last step, when last heard)
        # per stem pair and per channel's analog input; each panel's wave,
        # stepped on the displays' clock.
        self._stem_peaks = {}
        self._analog_peaks = {}
        self._aux_peaks = {}
        channels = [panel for panel in PANELS if panel != return_panel()]
        self._waves = {panel: WaveStrip(WAVE_HISTORY, WAVE_HEIGHT) for panel in channels}
        self._return_levels = ((0.0,) * PAIRS, (0.0, 0.0))
        self._next_step = None
        self._later = later
        self._wake = threading.Condition()

    def note_peak(self, pair, peak):
        """A stem's peak, from the OSC thread: noted, never drawn here.
        StemDeck sends a 40 ms peak 25 times a second; the loudest since the
        last step is held, so a hit between steps is not lost."""
        with self._wake:
            self._hold(self._stem_peaks, pair, peak)

    def note_analog(self, index, peak):
        """A channel's analog input peak, from the OSC thread."""
        with self._wake:
            self._hold(self._analog_peaks, index, peak)

    def note_aux(self, side, peak):
        """The analog return's peak, L (0) or R (1), from the OSC thread."""
        with self._wake:
            self._hold(self._aux_peaks, side, peak)

    def _hold(self, peaks, key, peak):
        if not isinstance(peak, (int, float)) or isinstance(peak, bool):
            return
        held, _ = peaks.get(key, (0.0, None))
        peaks[key] = (max(held, peak), self._clock())

    def tick(self):
        """Steps the waves when a step is due (WAVE_STEPS_PER_SECOND)."""
        now = self._clock()
        if self._next_step is not None and now < self._next_step:
            return
        self._next_step = now + 1.0 / WAVE_STEPS_PER_SECOND
        self.step_waves()

    def step_waves(self):
        """Every channel's wave moves on by its source's level, and the
        return's meters take the latest peaks; a panel whose picture changed
        waits to be drawn behind anything posted."""
        with self._wake:
            places = places_of(self._channel_masks, self._return[1])
            for panel, wave in self._waves.items():
                if wave.shift(wave_level(self._source_peak(panel, places))):
                    self._wave_due.add(panel)
            levels = (tuple(wave_level(self._fresh(self._stem_peaks, pair))
                            for pair in range(1, PAIRS + 1)),
                      tuple(wave_level(self._fresh(self._aux_peaks, side)) for side in (0, 1)))
            if levels != self._return_levels:
                self._return_levels = levels
                self._wave_due.add(return_panel())
            for peaks in (self._stem_peaks, self._analog_peaks, self._aux_peaks):
                for key, (_, heard) in peaks.items():
                    peaks[key] = (0.0, heard)
            self._wake.notify()

    def _source_peak(self, panel, places):
        """A channel's wave: the louder of the stems it plays (one of each
        deck at most), else its analog input. Called with the lock held."""
        index = PANELS.index(panel)
        pairs = [pair for pair, place in enumerate(places, 1) if place == index]
        if pairs:
            return max(self._fresh(self._stem_peaks, pair) for pair in pairs)
        return self._fresh(self._analog_peaks, index)

    def _fresh(self, peaks, key):
        peak, heard = peaks.get(key, (0.0, None))
        if heard is None or self._clock() - heard > METER_STALE_SECONDS:
            return 0.0
        return peak

    def start(self):
        threading.Thread(target=self._run, name="displays", daemon=True).start()

    def show_channel(self, index, mask):
        """What plays on a channel: every display shows each stem's place."""
        with self._wake:
            self._channel_masks[index] = mask
        self._post_all()

    def show_menu(self, index, level, cursor):
        """A channel's menu: its own display only."""
        with self._wake:
            self._menus[index] = (level, cursor)
        self._post(panel_for_channel(index))

    def show_return(self, cursor, plays):
        with self._wake:
            self._return = (cursor, tuple(plays))
        self._post_all()

    def show_return_mode(self, mode):
        with self._wake:
            self._return_mode = mode
        self._post(return_panel())

    def blank_all(self):
        """Until Core speaks: every square empty, nothing claimed to play."""
        for index in range(len(PANELS) - 1):
            self.show_channel(index, 0)
        self.show_return(STEM_MODE, (False,) * PAIRS)

    def drain(self):
        """Draw everything posted and every moved wave, each panel once. A
        posted panel (a turn, an announcement) always goes before the wave
        redraws still waiting: a batch of five takes ~150 ms on the desk,
        and a turn that arrives meanwhile is drawn next."""
        while True:
            with self._wake:
                posted = [panel for panel in PANELS if panel in self._posted]
                waiting = [panel for panel in PANELS if panel in self._wave_due]
                if not posted and not waiting:
                    return
                panel = (posted or waiting)[0]
                self._posted.discard(panel)
                self._wave_due.discard(panel)
            self._draw(panel, self._picture_for(panel))

    def _picture_for(self, panel):
        """The picture of `panel` from its state, laid out for whatever size
        the display turns out to be."""
        with self._wake:
            cursor, plays = self._return
            places = places_of(self._channel_masks, plays)
            if panel == return_panel():
                mode, (stems, aux) = self._return_mode, self._return_levels
                return lambda width, height: Picture(
                    return_items(mode, cursor, width, height), [], None,
                    return_bars(stems, aux, width, height))
            index = PANELS.index(panel)
            menu, wave = self._menus[index], self._waves[panel]

        def picture(width, height):
            box = wave_box(width, height)
            fits = wave.image.size == (box[2] - box[0] + 1, box[3] - box[1] + 1)
            return Picture(menu_items(index, menu, places, width, height),
                           wave.columns(box), wave.image if fits else None)
        return picture

    def _post(self, panel):
        with self._wake:
            self._posted.add(panel)
            self._wake.notify()

    def _post_all(self):
        with self._wake:
            self._posted.update(PANELS)
            self._wake.notify()

    def _retry(self, panel):
        self._post(panel)

    def _run(self):
        while True:
            with self._wake:
                # Woken by a post at once; otherwise in time for the next
                # wave step.
                self._wake.wait_for(lambda: self._posted or self._wave_due,
                                    timeout=1.0 / WAVE_STEPS_PER_SECOND)
            self.tick()
            self.drain()

    def _draw(self, panel, picture_for):
        """Never raises: a display that does not answer is a line on stderr.
        `picture_for(width, height)` lays the picture out for this display."""
        began = self._clock()
        try:
            with self._lock:
                self._write(panel, picture_for)
        except Exception as error:  # noqa: BLE001 -- any I2C excuse counts
            self._devices.pop(panel, None)
            self._complain(panel, error)
            self._later(RETRY_SECONDS, lambda: self._retry(panel))
            return
        self._silent.discard(panel)
        line = self._timer.record(self._clock() - began)
        if line:
            self._report(line)

    def _write(self, panel, picture_for):
        self._select(MULTIPLEXER_ADDRESS, panel.channel)
        device = self._devices.get(panel)
        if device is None:
            device = self._make_device(panel)
            # Without it luma blanks the display when the process ends; see
            # a3-mixer-set-display.py for the measurement.
            device.persist = True
            self._devices[panel] = device
        self._draw_fields(device, picture_for(device.width, device.height))

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

    def show_menu(self, index, level, cursor):
        pass

    def show_return(self, cursor, plays):
        pass

    def show_return_mode(self, mode):
        pass

    def note_aux(self, side, peak):
        pass

    def note_peak(self, pair, peak):
        pass

    def note_analog(self, index, peak):
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
