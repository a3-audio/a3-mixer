#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Welche Displays am Pult hängen, und wie man sie beschriftet, ohne dass eines
die anderen mitnimmt.

Hardwarefrei mit Absicht: das Skript daneben lässt sich ohne luma, smbus und
TCA9548A nicht einmal importieren, und dann wäre an dieser Tabelle nichts zu
prüfen. Derselbe Schnitt wie bei a3_mixer_recall.

Es waren sechs fast gleiche Funktionen fuer fuenf Displays, und das ist die
ganze Geschichte des Ausfalls vom 2026-09-10: die sechste sprach ein Display
an, das es nicht gibt.

Drei Dinge sagten das schon im alten Skript, und alle drei standen unbeachtet
nebeneinander: der Kopf sagte "5 Oled Displays"; die Adresskonstanten hiessen
`SSD1306_I2C_ADDRESS_2` bis `_6`, also fuenf, benannt nach den
Multiplexer-Kanaelen 2 bis 6; und `disp_1` bis `disp_5` benutzten genau diese
Kanaele. Nur `disp_6` griff auf Kanal 7 -- ausserhalb der benannten Menge, mit
`port=0` und einem Zeichnen auf `device_dev_5`, einer Variablen aus der
Nachbarfunktion. Zwei kaputte Zeilen in einer Funktion, die nichts ansprach.

Vom Maintainer bestaetigt am 2026-09-18: *"es gibt keinen kanal 7 soweit ich
weiss"*.

Als Tabelle kann das nicht wiederkommen: fuenf Zeilen, die Kanaele stehen
einmal da, und ein Test besteht darauf, dass es die des Multiplexers sind.
"""

import math
import os
import sys
from collections import namedtuple

# The meter scale is the channel LEDs' (a3_mixer_meters, one directory up).
# a3-mixer.py runs from there; the boot script a3-mixer-set-display.py runs
# from here, so the directory is appended -- never ahead of this one.
_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)

from a3_mixer_meters import (CHANNEL_LED_THRESHOLDS_DB, RED_FROM_FRACTION,  # noqa: E402,F401
                             YELLOW_FROM_FRACTION, bar_fraction)

#: Ein Display: hinter welchem Kanal des Multiplexers es sitzt, auf welchem
#: I2C-Bus und unter welcher Adresse es antwortet, wie herum es eingebaut ist
#: und was draufsteht.
Panel = namedtuple("Panel", "channel port address rotate label")

#: Der Bus, auf dem der Multiplexer TCA9548A angesprochen wird
#: (`TCA9548A.I2C_setup` benutzt `SMBus(1)`). Ein Display *hinter* diesem
#: Multiplexer kann nur auf demselben Bus antworten -- deshalb steht die Zahl
#: einmal hier und nicht sechsmal verteilt.
I2C_BUS = 1

#: Die Kanaele des Multiplexers, an denen wirklich ein Display haengt.
#:
#: Fuenf: die vier Kanalzuege und der FX-Return. Vom Maintainer am 2026-09-18
#: aufgezaehlt -- *"es gibt 5 (kanal 1-4 und FX-Return)"*.
MULTIPLEXER_CHANNELS = (2, 3, 4, 5, 6)

PANELS = (
    Panel(channel=2, port=I2C_BUS, address=0x3D, rotate=2, label="Deck 1"),
    Panel(channel=3, port=I2C_BUS, address=0x3D, rotate=2, label="Deck 2"),
    Panel(channel=4, port=I2C_BUS, address=0x3C, rotate=2, label="Deck 3"),
    Panel(channel=5, port=I2C_BUS, address=0x3C, rotate=2, label="Deck 4"),
    Panel(channel=6, port=I2C_BUS, address=0x3C, rotate=0, label="FX Return"),
)


def draw_panels(panels, show, report):
    """Beschriftet jedes Display und gibt die zurück, die nicht geantwortet haben.

    `show(panel)` spricht die Hardware an und darf scheitern; `report(text)`
    bekommt eine Zeile je Ausfall.

    Ein Display, das nicht antwortet, ist eine Meldung wert und kein Grund,
    den Dienst zu beenden: vorher hat das erste stumme Display die übrigen
    fünf dunkel gelassen, und weil der Prozess mit Status 1 endete, stand in
    `systemctl` nur, dass *irgendetwas* schiefging -- nicht, dass fünf
    Displays in Ordnung waren.
    """
    failed = []

    for panel in panels:
        try:
            show(panel)
        except Exception as error:  # noqa: BLE001 -- jede Hardware-Ausrede zählt
            failed.append(panel)
            report(
                "display '%s' (mux channel %d, bus %d, address 0x%02x) "
                "did not answer: %s" % (panel.label, panel.channel, panel.port,
                                        panel.address, error)
            )

    return failed


#: Which display shows which strip. PANELS is in label order -- the four decks,
#: then the aux return -- and the desk's channel index 0..3 is deck 1..4.
CHANNEL_COUNT = 4


def panel_for_channel(index):
    """The display of channel `index` (0..3); anything else is a bug upstream."""
    if not 0 <= index < CHANNEL_COUNT:
        raise IndexError("the desk has channels 0..%d, not %d" % (CHANNEL_COUNT - 1, index))
    return PANELS[index]


def return_panel():
    """The aux return's display, the one after the four decks."""
    return PANELS[CHANNEL_COUNT]


PAIRS = 8


def _is_count(value, upper):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= upper


#: The largest stem mask: one bit per pair.
ALL_PAIRS = (1 << PAIRS) - 1


def channel_announcement(args):
    """The stem mask out of `/channel/{ch}/stem`'s arguments (bit 0 = pair
    1; 0 = the analog input), or None if damaged."""
    if len(args) != 1 or not _is_count(args[0], ALL_PAIRS):
        return None
    return args[0]


#: A channel's selector, in a3_core_stems' numbers: 0-7 the stem pairs 1-8
#: (D1's four, then D2's), 8 A, the channel's analog input (2026-10-07).
ANALOG_INPUT = PAIRS
#: Stems a deck has: D1 is pairs 1-4, D2 pairs 5-8.
STEMS_PER_DECK = 4
#: Headings over the channel's meters: the name, the first and the last
#: slot of the grid (_channel_columns) it spans. A heads the ninth slot.
CHANNEL_GROUPS = (("A", 0, 3), ("B", 4, 7), ("ST", ANALOG_INPUT, ANALOG_INPUT))


def channel_ring(index):
    """The cursors channel `index` (0-3) can take, left to right on its
    display: D1's stem n, D2's stem n, A. Stem n plays only on channel n
    (2026-10-25), so Core's selector there is a ring of these three."""
    return (index, STEMS_PER_DECK + index, ANALOG_INPUT)


def channel_slot(index, cursor):
    """The meter (0 D1, 1 D2, 2 A) under channel `index`'s cursor. A cursor
    outside the ring -- stored by an older Core -- is A, as Core takes it
    back."""
    ring = channel_ring(index)
    return ring.index(cursor) if cursor in ring else len(ring) - 1


def playing_slot(index, mask):
    """The meter (0 D1, 1 D2, 2 A) that plays on channel `index` with stem
    `mask`. D1 when the mask carries both of the channel's stems, and A when
    it carries neither: a foreign bit, from an older Core, is not this
    channel's."""
    d1, d2, _ = channel_ring(index)
    if mask & (1 << d1):
        return 0
    if mask & (1 << d2):
        return 1
    return 2

#: The FX Return, the master of the delay channel (P47): one mono meter under
#: its name, AUX-RTN (maintainer, 2026-10-28), DELAY since 2026-10-29, and its CUE field. It has no
#: source to choose, so no cursor and no active bracket.
RETURN_NAME = "DELAY"
CUE_TEXT = "CUE"

#: Steps a second: ten, decided 2026-10-04 and kept on 2026-10-07 although
#: the meter rule asks for 25 where a display can. It cannot: the desk draws
#: a panel in ~16 ms (journal, 2026-10-07: 14-20 ms mean, 44 ms worst), and
#: with music on every meter each panel moves on every step -- 50 draws a
#: second at ten steps is ~0.8 s of every second already; 25 steps would be
#: 125 draws, 2 s a second. A late step still falls right: the ballistics
#: run on the clock, not on the step count. What keeps the bus from drowning
#: is that only a panel whose pixels moved is redrawn (pixel_key). How a meter
#: moves -- rise, fall, hold -- is a3_mixer_meters.MeterBallistics on Core's
#: timing (2026-10-07), the same as the LEDs': the displays have no fall of
#: their own any more.
METER_STEPS_PER_SECOND = 10


#: Over full scale is a clip (maintainer, 2026-10-04): meter_level stops at
#: 0 dBFS, so without it a clean 0 dBFS and a +6 dB overload were the same
#: full bar. A step's held peak above this, linear, lights the clip.
CLIP_THRESHOLD = 1.0
#: How long a clip stays lit after the last over: long enough to be seen
#: from the decks, short enough to say "now", not "this set".
CLIP_HOLD_SECONDS = 1.0
# A hold run down in steps of 0.1 s leaves float dust above zero.
_CLIP_DUST = 1e-9


class ClipHold:
    """Whether one meter shows a clip: lit by a peak over CLIP_THRESHOLD,
    held CLIP_HOLD_SECONDS after the last one. `dt` is the time since the
    last feed, in seconds."""

    def __init__(self):
        self._left = 0.0

    def feed(self, peak, dt):
        """Whether the clip shows after `dt` seconds whose loudest peak was
        `peak`; anything odd is no over."""
        is_number = isinstance(peak, (int, float)) and not isinstance(peak, bool)
        if is_number and peak > CLIP_THRESHOLD:
            self._left = CLIP_HOLD_SECONDS
            return True
        self._left = max(0.0, self._left - dt)
        return self._left > _CLIP_DUST


def lit_rows(level, count):
    """How many of `count` rows `level` lights, half up -- Python's round()
    would light a row at 6.5 but not at 7.5."""
    return int(math.floor(level * count + 0.5))


class Meter(namedtuple("Meter", "box level clip hold", defaults=(False, 0.0))):
    """A meter: a filled bar at its level and, over it, a one-row line at
    its held peak (meter-ballistics, 2026-10-07) -- no mark of which input
    is assigned and no floor line: turning, the hands want the selector
    only (maintainer, 2026-10-04). While it clips (ClipHold) the bar is
    drawn hatched. `level` and `hold` are 0.0-1.0 of the bar."""

    def pixels(self):
        """Rows of the bar: what the painter draws, in pixels, so two levels
        in one row are one picture."""
        return lit_rows(self.level, self.box[3] - self.box[1] + 1)

    def hatched(self):
        """Whether the painter hatches the bar: a clip with no bar to show
        it on moves no pixel."""
        return self.clip and self.pixels() > 0

    def hold_row(self):
        """The panel row of the hold line: where a bar at the held peak has
        its top. None while the hold is inside the bar -- there it is the
        bar's own top row, and a line would mark nothing."""
        x0, y0, x1, y1 = self.box
        rows = lit_rows(self.hold, y1 - y0 + 1)
        if rows <= self.pixels():
            return None
        return y1 - rows + 1


class Toggle(namedtuple("Toggle", "box on text")):
    """The return's CUE field: on while the return is cued. (A channel's
    STEM toggle of 2026-10-04 was one too, until A came back on 2026-10-07.)"""

    def pixels(self):
        return self.on


def pixel_key(picture):
    """Everything `picture` paints, in pixels: equal keys paint equal
    pictures."""
    toggle = picture.toggle.pixels() if picture.toggle is not None else None
    return (tuple((meter.pixels(), meter.hatched(), meter.hold_row())
                  for meter in picture.meters),
            picture.cursor, toggle,
            picture.active, tuple(picture.headings), tuple(picture.marks),
            tuple(picture.rows))


#: What a panel shows: headings over meters, the cursor -- the box of the
#: down arrow over the selected slot --, divider lines, a channel's toggle,
#: and the box of the active bracket over the meter that plays, or None.
Heading = namedtuple("Heading", "box text")
#: The mode of the delay list in which the whole cursor row is inverted; the
#: other mode inverts its value only. The same word as the desk logic's SELECT
#: (a test says so): the display does not import the desk's logic.
SELECT_MODE = "select"

#: One row of the return's delay list: `name` at the left of `box`, `value`
#: at its right. `inverted` says what the encoder is standing on: "row" (the
#: whole box lit, dark letters -- select mode), "value" (only the value's
#: end of it -- edit mode) or None.
Row = namedtuple("Row", "box name value inverted")
Picture = namedtuple("Picture", "headings meters cursor dividers toggle active marks rows",
                     defaults=((), None, None, (), ()))

#: Gaps between meters, in pixels: inside a group, and between two groups --
#: wide enough for a divider line in its middle with three dark columns on
#: each side (D1 | D2 | A stand apart, maintainer 2026-10-04).
INNER_GAP = 2
GROUP_GAP = 7


def meter_level(peak):
    """0.0-1.0 for a linear peak on the channel LEDs' scale (bar_fraction):
    a peak that lights n of the 8 LEDs fills exactly n/8 of the bar
    (2026-10-07). Anything odd is silence."""
    if not isinstance(peak, (int, float)) or isinstance(peak, bool) or not peak > 0:
        return 0.0
    return bar_fraction(20 * math.log10(peak))


#: The heights marked beside every meter, as shares of the bar: the bottom
#: of the first yellow and of the first red LED's segment. The displays are
#: monochrome, so the colours are a place.
MARKED_FRACTIONS = (YELLOW_FROM_FRACTION, RED_FROM_FRACTION)
#: A mark is a horizontal tick in the gap left of its bar, a tenth of the
#: bar's width long (a pixel at least). Left only: ticks on both sides met
#: across a channel's 2-column gap and widened a bar standing at a mark
#: into a cap, which read as a level.
MARK_OF_METER = 0.1
#: Between two channel meters a tick leaves a dark column before the left
#: neighbour, so it belongs to the bar on its right and touches nothing.
CHANNEL_MARK_LENGTH = INNER_GAP - 1


def mark_length(box):
    """How long a tick beside a meter `box` wide is, in columns."""
    return max(1, round((box[2] - box[0] + 1) * MARK_OF_METER))


def meter_marks(box, length=None):
    """The marks beside a meter's `box`: one tick `length` columns long
    (mark_length unless given) per MARKED_FRACTIONS height, left of the
    bar, in the bottom row of the first segment of that colour -- the row
    just above a bar filled to that share, rounded as the bar is
    (lit_rows). The bar covers a mark exactly when an LED of its colour is
    lit."""
    x0, y0, _, y1 = box
    length = mark_length(box) if length is None else length
    rows = y1 - y0 + 1
    marks = []
    for fraction in MARKED_FRACTIONS:
        y = y1 - lit_rows(fraction, rows)
        marks.append((x0 - length, y, x0 - 1, y))
    return tuple(marks)


def _marks(meters, longest=None):
    """Every meter's marks, none longer than `longest` columns."""
    marks = []
    for meter in meters:
        length = mark_length(meter.box)
        if longest is not None:
            length = min(length, longest)
        marks.extend(meter_marks(meter.box, length))
    return tuple(marks)


#: The ninth slot's share of the row, in meters: two, so the return's CUE
#: field fits its letters there, and the stems keep their 10 pixels. A
#: channel's A meter stands in its middle, a stem's width.
LAST_SLOT_METERS = 2


#: Dark columns left of stem 1: the panel's edge is a gap too, so the
#: active bracket's left leg has a column there as it has between meters.
EDGE = 1


def _channel_columns(width):
    """(x0, x1) of the grid's eight stem slots and its ninth slot: the stem
    slots as wide as PAIRS + LAST_SLOT_METERS equal slots make them, the
    ninth slot the rest. A channel's headings and dividers stand on it, and
    the return's CUE field takes its ninth slot."""
    groups = len(CHANNEL_GROUPS) - 1
    gaps = EDGE + (groups * (GROUP_GAP - INNER_GAP)) + PAIRS * INNER_GAP
    meter = (width - gaps) // (PAIRS + LAST_SLOT_METERS)
    group_starts = {first for _, first, _ in CHANNEL_GROUPS[1:-1]}
    columns, x = [], EDGE
    for index in range(PAIRS):
        if index:
            x += GROUP_GAP if index in group_starts else INNER_GAP
        columns.append((x, x + meter - 1))
        x += meter
    columns.append((x + GROUP_GAP, width - 1))
    return columns


#: The cursor's arrow, in rows: a "^" turned over, a solid triangle
#: pointing down at the selected slot (maintainer, 2026-10-04). Each row is
#: a pixel narrower on either side than the one above, so it is twice as
#: wide as tall -- a channel meter's ten pixels at five rows.
ARROW_ROWS = 5
ARROW_WIDTH = 2 * ARROW_ROWS


def _bands(height):
    """(heading, arrow, meters) as (top, bottom) rows of the panel: the
    arrow between the headings and the meters, a row on either side of it
    -- dark above, so it stays clear of the letters, and below it the
    active bracket's top line --; the meters run to the bottom row."""
    heading = max(6, round(height * 0.19))
    arrow = heading + 1
    meters = arrow + ARROW_ROWS + 1
    return (0, heading - 1), (arrow, meters - 2), (meters, height - 1)


def _arrow(slot, rows):
    """The arrow's box: ARROW_WIDTH wide, centred over the slot's (x0, x1)."""
    x0 = (slot[0] + slot[1] + 1 - ARROW_WIDTH) // 2
    return (x0, rows[0], x0 + ARROW_WIDTH - 1, rows[1])


#: The active bracket's height in rows: its top line in the row above the
#: meters, and legs reaching that far down beside the meter's top.
BRACKET_ROWS = 4


def _bracket(meter):
    """The active bracket over `meter`'s box: a "]" turned 90 degrees
    counter-clockwise (maintainer, 2026-10-04), one column wider than the
    meter on either side, so its legs stand in the gaps and the meter
    stays whole beneath it."""
    x0, y0, x1, _ = meter
    return (x0 - 1, y0 - 1, x1 + 1, y0 + BRACKET_ROWS - 2)


def _divider(left, right, rows):
    """A vertical line in the middle of the gap between two columns, the
    meters' height: below the headings."""
    x = (left[1] + right[0]) // 2
    return (x, rows[0], x, rows[1])


def _meters(boxes, levels, clips, holds=()):
    """A meter per box; `clips` empty is no meter clipping, `holds` empty
    no held peak."""
    clips = tuple(clips) or (False,) * len(boxes)
    holds = tuple(holds) or (0.0,) * len(boxes)
    return tuple(Meter(box, level, bool(clip), hold)
                 for box, level, clip, hold in zip(boxes, levels, clips, holds))


def _centred(slot, width):
    """(x0, x1) of `width` columns in the middle of `slot`."""
    x0 = slot[0] + (slot[1] - slot[0] + 1 - width) // 2
    return (x0, x0 + width - 1)


def _channel_layout(width, height):
    """What both channel pictures stand on: the spans of the three headings,
    the three bar columns, and the heading, arrow and meter bands."""
    slots = _channel_columns(width)
    stem_width = slots[0][1] - slots[0][0] + 1
    spans = [(slots[first][0], slots[last][1]) for _, first, last in CHANNEL_GROUPS]
    columns = [_centred(span, stem_width) for span in spans]
    dividers = [(slots[first - 1], slots[first]) for _, first, _ in CHANNEL_GROUPS[1:]]
    return spans, columns, dividers, _bands(height)


def channel_picture(index, cursor, levels, mask, width, height, clips=(), holds=()):
    """Channel `index` (0-3): its stem of D1, its stem of D2 and its analog
    input, one bar each under D1 | D2 | A -- `levels`, `clips` and `holds`
    in that order, three each, hatched where one clips --, the cursor as the
    arrow over one of them (channel_slot), and the active bracket over what
    plays (playing_slot). Each bar is a stem's width, centred under its
    heading; the headings and dividers keep the grid of eight stems and A,
    so the return panel beside it reads the same. Pure layout; the painter
    draws it."""
    spans, columns, gaps, ((h0, h1), arrow, (m0, m1)) = _channel_layout(width, height)
    headings = tuple(Heading((x0, h0, x1, h1), name)
                     for (name, _, _), (x0, x1) in zip(CHANNEL_GROUPS, spans))
    meters = _meters([(x0, m0, x1, m1) for x0, x1 in columns], levels, clips, holds)
    dividers = tuple(_divider(left, right, (m0, m1)) for left, right in gaps)
    active = _bracket(meters[playing_slot(index, mask)].box)
    return Picture(headings, meters, _arrow(columns[channel_slot(index, cursor)], arrow),
                   dividers, None, active, _marks(meters, CHANNEL_MARK_LENGTH))


#: The ring in engine mode (Core's a3_core_decks), left to right: decks 1-4,
#: then the analog input -- analog last (maintainer, 2026-10-26). The decks are
#: bare digits: on the 128x64 OLED "D1" had to be drawn too small to read. Each entry
#: is the heading, the number `channel.source` carries (0 analog, k deck k)
#: and the first and last slot of the grid (_channel_columns) it spans: a
#: deck two stem slots, A the ninth slot as in the interim. A deck that is
#: not there keeps its letter and its place, dim: no bar and no scale marks
#: (maintainer, 2026-10-28: five fixed slots, nothing rescales).
ANALOG_SOURCE = 0
ENGINE_GROUPS = (("A", 1, 0, 1), ("B", 2, 2, 3), ("C", 3, 4, 5), ("D", 4, 6, 7),
                 ("ST", ANALOG_SOURCE, ANALOG_INPUT, ANALOG_INPUT))
ENGINE_SOURCES = tuple(source for _, source, _, _ in ENGINE_GROUPS)
#: Core numbers decks 1-4.
CORE_DECKS = 4
DECKS = CORE_DECKS
#: What an arrow box with no rows draws: nothing.
NO_ARROW = (0, 0, -1, -1)


def engine_slot(source):
    """The display slot (0-4) of a ring place (0 analog, k deck k)."""
    return ENGINE_SOURCES.index(source)


def _engine_layout(width, height):
    slots = _channel_columns(width)
    stem_width = slots[0][1] - slots[0][0] + 1
    spans = [(slots[first][0], slots[last][1]) for _, _, first, last in ENGINE_GROUPS]
    columns = [_centred(span, stem_width) for span in spans]
    # One divider, between the decks and A: two stem slots leave no room
    # for one between neighbouring decks.
    divider = (slots[ANALOG_INPUT - 1], slots[ANALOG_INPUT])
    return spans, columns, divider, _bands(height)


def engine_channel_picture(source, cursor, present, levels, width, height,
                           clips=(), holds=()):
    """A channel in engine mode: 1 2 3 4 A, `source` (0 analog, k deck
    k) under the active bracket, `cursor` (the same numbers) under the arrow.
    `levels`, `clips` and `holds` are in display order, five each; `present`
    says per deck (1-4) whether it is there -- an absent deck keeps its
    letter over an empty slot, no bar and no scale marks."""
    spans, columns, divider, ((h0, h1), arrow, (m0, m1)) = _engine_layout(width, height)
    there = tuple(bool(on) for on in present) + (True,)
    headings = tuple(Heading((x0, h0, x1, h1), name)
                     for (name, _, _, _), (x0, x1) in zip(ENGINE_GROUPS, spans))

    def shown(values, empty):
        values = values or (empty,) * len(there)
        return [value if on else empty for value, on in zip(values, there)]

    meters = _meters([(x0, m0, x1, m1) for x0, x1 in columns],
                     shown(levels, 0.0), shown(clips, False), shown(holds, 0.0))
    return Picture(headings, meters, _arrow(columns[engine_slot(cursor)], arrow),
                   (_divider(*divider, (m0, m1)),), None,
                   _bracket(meters[engine_slot(source)].box),
                   _marks([m for m, on in zip(meters, there) if on], CHANNEL_MARK_LENGTH))


#: The return's heading and its meter, each as a share of the panel's width.
#: The heading's box is as wide as its name needs at the displays' one text size
#: (DELAY: 43 of 45 columns at 128; AUX-RTN needed 58, so the box was 60 and
#: DELAY centred in it would have left the left margin); the meter is as slim as the channels' bars look beside their
#: neighbours -- 22 columns, the width it had under FX RTN.
RETURN_HEADING_OF_WIDTH = 0.35
RETURN_METER_OF_WIDTH = 0.17


#: The delay list's row names on the return, in the order they stand.
DELAY_NAMES = {"beat": "BEAT", "feedback": "FEEDBK", "color": "COLOR", "spread": "SPREAD",
               "cue": "CUE"}
#: What the longest name and the longest values of a row can be: the painter
#: sizes every row by them, so a digit does not grow or shrink between clicks.
LIST_NAME_SAMPLES = ("SPREAD", "FEEDBK")
LIST_VALUE_SAMPLES = ("HP 10", "LP 10", "100%", "180\u00b0", "1/8", "3/4", "OFF")
#: Dark columns between the meter and the list.
LIST_GAP = 3
#: Dark rows between the heading and the first row.
LIST_HEADING_GAP = 2

_BEATS = {0.125: "1/8", 0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def delay_text(row, value):
    """What a delay row's value reads on the display; `--` while it is not
    known. Beat in the fractions a deck's loop control shows, colour as
    filter steps from the centre: HP (high-pass) left of it, LP right. CUE is
    a switch: ON or OFF."""
    if row == "cue":
        return "--" if value is None else "ON" if value else "OFF"
    if not _number(value):
        return "--"
    if row == "beat":
        return _BEATS.get(value) or f"{value:g}"
    if row == "feedback":
        return f"{round(value * 100)}%"
    if row == "color":
        step = round(value * 10)
        return "0" if step == 0 else f"HP {-step}" if step < 0 else f"LP {step}"
    return f"{round(value)}\u00b0"


def _rows(mode, cursor, values, cue, heading_bottom, bottom, free):
    """The five rows, equal and stacked up to the panel's last row, under the
    heading, within `free` = (x0, x1) of columns. The one under the cursor is
    inverted: all of it while selecting, its value while editing."""
    x0, x1 = free
    names = tuple(DELAY_NAMES)
    top = heading_bottom + 1 + LIST_HEADING_GAP
    height = max(1, (bottom + 1 - top) // len(names))
    top = bottom + 1 - height * len(names)
    inverted = "row" if mode == SELECT_MODE else "value"
    rows = []
    for index, name in enumerate(names):
        value = cue if name == "cue" else values.get(name)
        y0 = top + index * height
        rows.append(Row((x0, y0, x1, y0 + height - 1), DELAY_NAMES[name],
                        delay_text(name, value), inverted if index == cursor else None))
    return tuple(rows)


def return_picture(cue, level, width, height, clip=False, hold=0.0, delay=None):
    """The FX Return: DELAY (once AUX-RTN) at the left margin, one mono meter under it,
    both at the left margin, left of the divider, and the CUE field behind it at the right edge -- on while the
    return is cued. No arrow and no bracket: there is nothing to choose.
    `delay` = (mode, cursor, values) turns the right of the panel into the
    delay list instead: five rows, CUE one of them (so no CUE field and no
    divider), beside the same heading and meter."""
    (h0, h1), _, (m0, m1) = _bands(height)
    # The CUE field takes the slot of a channel's A, so the two displays
    # side by side carry their last slot in the same place.
    channel = _channel_columns(width)
    last_meter, toggle_slot = channel[PAIRS - 1], channel[ANALOG_INPUT]
    heading = round(width * RETURN_HEADING_OF_WIDTH)
    meter = round(width * RETURN_METER_OF_WIDTH)
    # The name and its meter stand at the left margin, as a channel's first
    # heading and meter do (maintainer, 2026-10-28: "aux-rtn linksbündig",
    # "aux-rtn vu meter auch linksbündig").
    x0 = channel[0][0]
    x1 = x0 + heading - 1
    # Not at x0 itself: the scale marks stand in the column left of the bar.
    stem_width = channel[0][1] - channel[0][0] + 1
    left = _centred((channel[0][0], channel[1][1]), stem_width)[0]
    meters = _meters([(left, m0, left + meter - 1, m1)], (level,), (clip,), (hold,))
    headings = (Heading((x0, h0, x1, h1), RETURN_NAME),)
    if delay is not None:
        free = (left + meter - 1 + LIST_GAP + 1, width - 1)
        rows = _rows(*delay, cue, h1, height - 1, free)
        return Picture(headings, meters, None, (), None, None, _marks(meters), rows)
    toggle = Toggle((toggle_slot[0], m0, toggle_slot[1], m1), bool(cue), CUE_TEXT)
    divider = _divider(last_meter, toggle_slot, (m0, m1))
    return Picture(headings, meters, None, (divider,), toggle, None, _marks(meters))


def cursor_announcement(args):
    """The cursor out of `/channel/{ch}/stem/cursor` (0-8), or None."""
    if len(args) != 1 or not _is_count(args[0], ANALOG_INPUT):
        return None
    return args[0]


def source_announcement(args):
    """The ring place (0 = analog, k = deck k) out of `/channel/{ch}/source`
    or `/channel/{ch}/source/cursor`, or None if damaged."""
    if len(args) != 1 or not _is_count(args[0], CORE_DECKS):
        return None
    return args[0]


def present_announcement(args):
    """Whether the deck is there, out of `/stemdeck/{deck}/present` (1 or 0),
    or None if damaged."""
    if len(args) != 1 or not _is_count(args[0], 1):
        return None
    return args[0] == 1


def cue_announcement(args):
    """The return's cue out of `/aux-return/cue/led` -- True for 1.0, False
    for 0.0, as Core sends a lamp -- or None if damaged."""
    if len(args) != 1:
        return None
    value = args[0]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value not in (0, 1):
        return None
    return value == 1
