# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The five OLED displays, drawn by the main process: what Core announces.

Each channel's display is an input selector (2026-10-04): eight plain bars
under D1 | D2, one per stem pair, and in the ninth slot the STEM toggle --
a filled box while a stem plays on the channel, an outline while none does.
The stem that plays -- the lowest bit of the channel's mask -- carries the
active bracket: a "]" turned 90 degrees counter-clockwise, a top line in
the dark row over the meter with a short leg down either side, standing in
the gaps beside the meter so the bar stays whole; no stem playing, no
bracket, and the toggle never gets one. The cursor is a small solid
triangle pointing down -- a "^" turned over -- between the headings and the
meters, centred over the selected slot, right above the bracket when both
mark one stem; nothing else marks a meter or the toggle.

The return's display is drawn the same way: two mono meters, STEM (StemDeck's
aux bus) and ANALOG (the analog return), the louder side of each, under
plain headings and nothing between them; the mode that plays carries the
same active bracket, and the cursor is the same arrow, over STEM or ANALOG.

Every meter has VU-like ballistics (display_panel.Ballistics), no display
draws a peak mark, and a panel is redrawn only when its pixels move.

Every meter shows a clip (2026-10-04): a step whose held peak is over full
scale (above 1.0 linear) lights it, and it stays lit a second after the
last over (display_panel.ClipHold). While lit, the bar is drawn hatched --
every third diagonal dark, fixed to the panel. A cap over the bar, or the
bar drawn hollow, were tried and dropped: a cap fuses with the active
bracket at a full bar and, once the bar falls during the hold, floats
under the arrow as if it were part of it; a hollow bar reads as empty. The
hatch stays inside the bar, so neither the arrow nor the bracket can be
mistaken for it, and a clean 0 dBFS bar stays solid beside a hatched
overload. A clip lighting or going out is one redraw: pixel_key carries it.

The displays are a3-mixer-set-display's -- the same multiplexer and ssd1306
-- and the table of which display sits where is display_panel.PANELS,
untouched. A wrong port or channel there took the desk down from 2026-09-10
to 2026-09-18, so nothing here knows a channel, port or address of its own.

The pure part (the layout) is in display_panel and is tested, as is the
partial update in a3_mixer_oled. This module needs the Pi's hardware, so
luma, PIL and smbus are imported when the first Displays() is made, not when
this file is imported.

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

from display_panel import (channel_announcement, return_announcement,  # noqa: E402,F401
                           cursor_announcement, mode_announcement, channel_picture,
                           return_picture, meter_level, panel_for_channel, return_panel,
                           pixel_key, playing_stem, Ballistics, ClipHold, STEM_TOGGLE,
                           STEM_MODE,
                           METER_STEPS_PER_SECOND, PAIRS, PANELS, Picture)

#: A meter not heard for this long is silence: StemDeck or the analyzer
#: stopped, and the last peak must not stand on the display for ever.
METER_STALE_SECONDS = 0.5

#: Text height as a share of its heading's box.
TEXT_OF_HEADING = 0.9


@functools.lru_cache(maxsize=8)
def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size)
    except TypeError:   # a Pillow before 10.1 has one bitmap size only
        return ImageFont.load_default()


def _fit(draw, box, text, size):
    """(font, at) of `text` centred in `box`, as large as `size` and no
    larger than fits."""
    x0, y0, x1, y1 = box
    size = max(6, size)
    while True:
        font = _font(size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        if size == 6 or (right - left <= x1 - x0 + 1 and bottom - top <= y1 - y0 + 1):
            break
        size -= 1
    at = (x0 + (x1 - x0 + 1 - (right - left)) // 2 - left,
          y0 + (y1 - y0 + 1 - (bottom - top)) // 2 - top)
    return font, at


@functools.lru_cache(maxsize=16)
def headings_image(headings, width, height):
    """The headings' picture, painted once per layout: text is the slow part."""
    from PIL import Image, ImageDraw

    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)
    for heading in headings:
        x0, y0, x1, y1 = heading.box
        font, at = _fit(draw, heading.box, heading.text, round((y1 - y0 + 1) * TEXT_OF_HEADING))
        draw.text(at, heading.text, fill="white", font=font)
    return image


#: The STEM letters sit this far inside the toggle's field, clear of its
#: one-pixel outline.
FRAME = 1
#: The toggle's field sits this far inside its slot, so it stands apart
#: from the divider beside it.
TOGGLE_INSET = 3


def _inset(box, pixels):
    x0, y0, x1, y1 = box
    return (x0 + pixels, y0 + pixels, x1 - pixels, y1 - pixels)


#: A clipping bar's hatch: every CLIP_HATCH-th diagonal of the panel is
#: dark, so a third of the bar goes out -- still a bar, plainly not a solid
#: one. Fixed to the panel, so the lines stand still while the bar falls.
CLIP_HATCH = 3


def _meter(draw, meter):
    """A meter: a filled bar, hatched while it clips, nothing when silent.
    Its rows and hatch are the meter's own pixels() and hatched(), so what
    is painted is what the redraw rule compares."""
    x0, y0, x1, y1 = meter.box
    bar = meter.pixels()
    if not bar:
        return
    top = y1 - bar + 1
    draw.rectangle((x0, top, x1, y1), fill="white")
    if meter.hatched():
        draw.point([(x, y) for x in range(x0, x1 + 1) for y in range(top, y1 + 1)
                    if (x + y) % CLIP_HATCH == 0], fill="black")


def _arrow(draw, box):
    """The cursor: a solid triangle pointing down, its top row the box's
    width and every row below a pixel narrower on either side."""
    x0, y0, x1, y1 = box
    for row, y in enumerate(range(y0, y1 + 1)):
        if x0 + row > x1 - row:
            break
        draw.line((x0 + row, y, x1 - row, y), fill="white")


def _bracket(draw, box):
    """The active bracket: the box's top row and its two side columns, open
    at the bottom."""
    x0, y0, x1, y1 = box
    draw.line((x0, y0, x1, y0), fill="white")
    draw.line((x0, y0, x0, y1), fill="white")
    draw.line((x1, y0, x1, y1), fill="white")


@functools.lru_cache(maxsize=8)
def letters_mask(text, box, width, height):
    """`text` letter over letter in `box`, as a mask the size of the panel:
    STEM does not fit across a slot a meter wide. Painted once per layout,
    then pasted in whichever colour the toggle has."""
    from PIL import Image, ImageDraw

    mask = Image.new("1", (width, height))
    draw = ImageDraw.Draw(mask)
    x0, y0, x1, y1 = box
    rows = (y1 - y0 + 1) // len(text)
    top = y0 + (y1 - y0 + 1 - rows * len(text)) // 2
    for index, letter in enumerate(text):
        cell = (x0, top + index * rows, x1, top + (index + 1) * rows - 1)
        font, at = _fit(draw, cell, letter, rows)
        draw.text(at, letter, fill="white", font=font)
    return mask


def _toggle(image, draw, toggle):
    """The STEM toggle: ON a filled box with dark letters, OFF an outline
    with light letters."""
    field = _inset(toggle.box, TOGGLE_INSET)
    if toggle.on:
        draw.rectangle(field, fill="white")
    else:
        draw.rectangle(field, outline="white")
    letters = letters_mask(toggle.text, _inset(field, FRAME), image.width, image.height)
    image.paste(0 if toggle.on else 1, (0, 0), letters)


def paint(image, picture):
    """Draw `picture` onto a 1-bit PIL image: headings (cached), dividers,
    meters, the toggle, the active bracket and the cursor's arrow."""
    from PIL import ImageDraw

    image.paste(headings_image(tuple(picture.headings), image.width, image.height), (0, 0))
    draw = ImageDraw.Draw(image)
    for divider in picture.dividers:
        draw.line(divider, fill="white")
    for meter in picture.meters:
        _meter(draw, meter)
    if picture.toggle is not None:
        _toggle(image, draw, picture.toggle)
    if picture.active is not None:
        _bracket(draw, picture.active)
    _arrow(draw, picture.cursor)


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
        self._meters_due = set()  # panels whose meters moved: drawn when nothing is posted
        # The meters of each panel as last drawn, in pixels (pixel_key): a
        # step that moves no pixel draws nothing -- the bus carries ~17
        # draws a second (2026-10-04), and ten steps on five panels is 50.
        self._drawn = {}
        # What the displays show: what plays on each channel, each channel's
        # cursor, the return's cursor and what plays there, and its mode.
        self._channel_masks = [0] * (len(PANELS) - 1)
        self._cursors = [STEM_TOGGLE] * (len(PANELS) - 1)
        self._return = (STEM_MODE, (False,) * PAIRS)
        self._return_mode = STEM_MODE
        # The meters: (loudest peak since the last step, when last heard)
        # per stem pair, per side of the analog return and per side of
        # StemDeck's aux bus; each meter's ballistics; and the levels each
        # panel shows, stepped on the displays' clock.
        self._stem_peaks = {}
        self._aux_peaks = {}
        self._stem_aux_peaks = {}
        self._ballistics = {}
        self._clip_holds = {}
        self._levels = {panel: None for panel in PANELS}
        self._clips = {panel: () for panel in PANELS}
        self._next_step = None
        self._last_step = None
        self._later = later
        self._wake = threading.Condition()

    def note_peak(self, pair, peak):
        """A stem's peak, from the OSC thread: noted, never drawn here.
        StemDeck sends a 40 ms peak 25 times a second; the loudest since the
        last step is held, so a hit between steps is not lost."""
        with self._wake:
            self._hold(self._stem_peaks, pair, peak)

    def note_aux(self, side, peak):
        """The analog return's peak, L (0) or R (1), from the OSC thread."""
        with self._wake:
            self._hold(self._aux_peaks, side, peak)

    def note_stem_aux(self, side, peak):
        """StemDeck's aux bus peak, L (0) or R (1), from the OSC thread.
        Only a truth with stem_aux_L/R sends it; once heard, it is STEM."""
        with self._wake:
            self._hold(self._stem_aux_peaks, side, peak)

    def _hold(self, peaks, key, peak):
        if not isinstance(peak, (int, float)) or isinstance(peak, bool):
            return
        held, _ = peaks.get(key, (0.0, None))
        peaks[key] = (max(held, peak), self._clock())

    def tick(self):
        """Steps the meters when a step is due (METER_STEPS_PER_SECOND)."""
        now = self._clock()
        if self._next_step is not None and now < self._next_step:
            return
        self._next_step = now + 1.0 / METER_STEPS_PER_SECOND
        self.step_meters()

    def step_meters(self):
        """Every meter takes the loudest peak since the last step through
        its ballistics; a panel whose pixels moved waits to be drawn behind
        anything posted."""
        with self._wake:
            dt = self._step_seconds()
            stems = [self._move(("stem", pair), self._fresh(self._stem_peaks, pair), dt)
                     for pair in range(1, PAIRS + 1)]
            ret = [self._move("stem return", self._stem_return_peak(), dt),
                   self._move("analog return", self._louder_side(self._aux_peaks), dt)]
            for panel in PANELS:
                levels_and_clips = ret if panel == return_panel() else stems
                self._levels[panel] = tuple(level for level, _ in levels_and_clips)
                self._clips[panel] = tuple(clip for _, clip in levels_and_clips)
                if self._pixels_now(panel) != self._drawn.get(panel):
                    self._meters_due.add(panel)
            for peaks in (self._stem_peaks, self._aux_peaks, self._stem_aux_peaks):
                for key, (_, heard) in peaks.items():
                    peaks[key] = (0.0, heard)
            self._wake.notify()

    def _step_seconds(self):
        """Seconds since the last step: the ballistics run on the clock, so
        a late step (a slow draw) falls as far as the time that passed."""
        now = self._clock()
        last, self._last_step = self._last_step, now
        if last is None:
            return 1.0 / METER_STEPS_PER_SECOND
        return min(max(0.0, now - last), 1.0)

    def _move(self, source, peak, dt):
        """(level, clip) of one meter after a step whose loudest peak was
        `peak`: the level through its ballistics, the clip through its
        hold."""
        ballistics = self._ballistics.setdefault(source, Ballistics())
        hold = self._clip_holds.setdefault(source, ClipHold())
        return ballistics.feed(meter_level(peak), dt), hold.feed(peak, dt)

    def _louder_side(self, peaks):
        """A mono meter of a stereo source: the louder of L and R, so a
        hard-panned signal still shows at its full level."""
        return max(self._fresh(peaks, side) for side in (0, 1))

    def _stem_return_peak(self):
        """STEM's raw peak: StemDeck's aux bus once the desk has heard it.
        A truth without stem_aux_L/R never sends it, and then STEM is the
        loudest stem playing on the return, so the desk works with either
        truth."""
        if self._stem_aux_peaks:
            return self._louder_side(self._stem_aux_peaks)
        plays = self._return[1]
        return max((self._fresh(self._stem_peaks, pair)
                    for pair, playing in zip(range(1, PAIRS + 1), plays) if playing),
                   default=0.0)

    def _pixels_now(self, panel):
        """The panel's meters in pixels, laid out for its display's size."""
        device = self._devices.get(panel)
        width, height = (device.width, device.height) if device else (128, 64)
        return pixel_key(self._picture_for(panel)(width, height))

    def _fresh(self, peaks, key):
        peak, heard = peaks.get(key, (0.0, None))
        if heard is None or self._clock() - heard > METER_STALE_SECONDS:
            return 0.0
        return peak

    def start(self):
        threading.Thread(target=self._run, name="displays", daemon=True).start()

    def show_channel(self, index, mask):
        """What plays on a channel. Its display shows the stem that plays --
        the mask's lowest bit, under the active bracket -- so only a change
        of that stem, or between none and some, is drawn: a stem added
        above it moves no pixel."""
        with self._wake:
            was = playing_stem(self._channel_masks[index])
            self._channel_masks[index] = mask
        if playing_stem(mask) != was:
            self._post(panel_for_channel(index))

    def show_cursor(self, index, cursor):
        """A channel's cursor: its own display."""
        with self._wake:
            self._cursors[index] = cursor
        self._post(panel_for_channel(index))

    def show_return(self, cursor, plays):
        with self._wake:
            self._return = (cursor, tuple(plays))
        self._post(return_panel())

    def show_return_mode(self, mode):
        with self._wake:
            self._return_mode = mode
        self._post(return_panel())

    def blank_all(self):
        """Until Core speaks: no stem on any channel, nothing on the return."""
        for index in range(len(PANELS) - 1):
            self.show_channel(index, 0)
        self.show_return(STEM_MODE, (False,) * PAIRS)
        self._post_all()

    def drain(self):
        """Draw everything posted and every panel whose meters moved, each
        once. A posted panel (a turn, an announcement) always goes before the
        meter redraws still waiting, so a turn during a batch is drawn next."""
        while True:
            with self._wake:
                posted = [panel for panel in PANELS if panel in self._posted]
                waiting = [panel for panel in PANELS if panel in self._meters_due]
                if not posted and not waiting:
                    return
                panel = (posted or waiting)[0]
                self._posted.discard(panel)
                self._meters_due.discard(panel)
            self._draw(panel, self._picture_for(panel))

    def _picture_for(self, panel):
        """The picture of `panel` from its state, laid out for whatever size
        the display turns out to be."""
        with self._wake:
            if panel == return_panel():
                cursor, mode = self._return[0], self._return_mode
                levels = self._levels[panel] or (0.0, 0.0)
                clips = self._clips[panel]
                return lambda width, height: return_picture(cursor, mode, levels, width,
                                                            height, clips)
            index = PANELS.index(panel)
            cursor = self._cursors[index]
            mask = self._channel_masks[index]
            levels = self._levels[panel] or (0.0,) * PAIRS
            clips = self._clips[panel]
        return lambda width, height: channel_picture(cursor, levels, mask, width, height,
                                                     clips)

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
                # meter step.
                self._wake.wait_for(lambda: self._posted or self._meters_due,
                                    timeout=1.0 / METER_STEPS_PER_SECOND)
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
        picture = picture_for(device.width, device.height)
        # Noted before the write: a failed draw is retried whole through
        # _retry, and meter steps must not hammer a display that is not there.
        with self._wake:
            self._drawn[panel] = pixel_key(picture)
        self._draw_fields(device, picture)

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

    def show_cursor(self, index, cursor):
        pass

    def show_return(self, cursor, plays):
        pass

    def show_return_mode(self, mode):
        pass

    def note_aux(self, side, peak):
        pass

    def note_stem_aux(self, side, peak):
        pass

    def note_peak(self, pair, peak):
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
