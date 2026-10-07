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

from a3_mixer_meters import (CHANNEL_LED_THRESHOLDS_DB, RED_FROM_DB,  # noqa: E402,F401
                             YELLOW_FROM_DB, bar_fraction)

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
    Panel(channel=6, port=I2C_BUS, address=0x3C, rotate=0, label="Aux Return"),
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


def return_announcement(args):
    """(cursor, plays) out of `/aux-return/stem`'s arguments -- the option
    the encoder is on (0 = analog, 1 = stem, 2 = cue), then for pairs 1-8
    whether it plays on the return -- or None if damaged."""
    if len(args) != 1 + PAIRS or not _is_count(args[0], CUE_CURSOR):
        return None
    if not all(_is_count(flag, 1) for flag in args[1:]):
        return None
    return args[0], tuple(bool(flag) for flag in args[1:])


#: A channel's selector: positions 0-7 the stem pairs 1-8, then A, the
#: channel's analog input -- a3_core_stems' numbers. Core's position 8 is
#: its stem on/off switch (2026-10-04); the display shows it as A with the
#: analog input's meter under it again (maintainer, 2026-10-07), in place
#: of the STEM toggle field.
ANALOG_INPUT = PAIRS
#: Headings over the channel's meters: the name, the first and the last
#: slot. A heads the ninth slot alone.
CHANNEL_GROUPS = (("D1", 0, 3), ("D2", 4, 7), ("A", ANALOG_INPUT, ANALOG_INPUT))

#: The aux return's modes -- a3_core_stems' numbers -- left to right on its
#: display, each a mono meter under its name and nothing between them: an
#: AUX title there irritated (maintainer, 2026-10-04).
ANALOG_MODE, STEM_MODE = 0, 1
RETURN_OPTIONS = (STEM_MODE, ANALOG_MODE)
RETURN_NAMES = {STEM_MODE: "STEM", ANALOG_MODE: "ANALOG"}
#: The return's third cursor position (2026-10-04): its CUE field, right
#: of the two modes. A cursor, never a mode.
CUE_CURSOR = 2
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
            picture.active, tuple(picture.headings), tuple(picture.marks))


#: What a panel shows: headings over meters, the cursor -- the box of the
#: down arrow over the selected slot --, divider lines, a channel's toggle,
#: and the box of the active bracket over the meter that plays, or None.
Heading = namedtuple("Heading", "box text")
Picture = namedtuple("Picture", "headings meters cursor dividers toggle active marks",
                     defaults=((), None, None, ()))

#: Gaps between meters, in pixels: inside a group, and between two groups --
#: wide enough for a divider line in its middle with three dark columns on
#: each side (D1 | D2 | A stand apart, maintainer 2026-10-04).
INNER_GAP = 2
GROUP_GAP = 7


def meter_level(peak):
    """0.0-1.0 for a linear peak on the channel LEDs' scale (bar_fraction):
    a peak that lights n of the 8 LEDs fills n/8 of the bar and less than
    (n+1)/8 (2026-10-07). Anything odd is silence."""
    if not isinstance(peak, (int, float)) or isinstance(peak, bool) or not peak > 0:
        return 0.0
    return bar_fraction(20 * math.log10(peak))


#: The levels marked beside every meter: where the channel LEDs turn yellow,
#: and red. The displays are monochrome, so the colours are a place.
MARKED_DB = (YELLOW_FROM_DB, RED_FROM_DB)
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
    (mark_length unless given) per MARKED_DB level, left of the bar, in the
    row where a bar at that level has its top -- the bar reaching a mark is
    the LED of that colour lighting."""
    x0, y0, _, y1 = box
    length = mark_length(box) if length is None else length
    rows = y1 - y0 + 1
    marks = []
    for db in MARKED_DB:
        y = y1 - lit_rows(bar_fraction(db), rows) + 1
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
    """(x0, x1) of the eight stem meters and the ninth slot: the meters as
    wide as PAIRS + LAST_SLOT_METERS equal slots make them, the ninth slot
    the rest."""
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


def playing_stem(mask):
    """The stem (0-7) that plays on a channel with stem `mask` -- its lowest
    bit, as Core plays it -- or None when none does."""
    if not mask:
        return None
    return (mask & -mask).bit_length() - 1


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


def channel_picture(cursor, levels, mask, width, height, clips=(), holds=()):
    """A channel: the eight stems as bars under D1 | D2 and the analog
    input's bar under A -- `levels`, `clips` and `holds` in that order, nine each,
    hatched where one clips --, the cursor as the arrow over one of them,
    and the active bracket over what plays: the stem `mask` plays, or A
    when it plays none. Pure layout; the painter draws it."""
    slots = _channel_columns(width)
    stem_width = slots[0][1] - slots[0][0] + 1
    columns = slots[:PAIRS] + [_centred(slots[ANALOG_INPUT], stem_width)]
    (h0, h1), arrow, (m0, m1) = _bands(height)
    headings = tuple(Heading((slots[first][0], h0, slots[last][1], h1), name)
                     for name, first, last in CHANNEL_GROUPS)
    meters = _meters([(x0, m0, x1, m1) for x0, x1 in columns], levels, clips, holds)
    playing = playing_stem(mask)
    dividers = tuple(_divider(slots[first - 1], slots[first], (m0, m1))
                     for _, first, _ in CHANNEL_GROUPS[1:])
    active = _bracket(meters[ANALOG_INPUT if playing is None else playing].box)
    return Picture(headings, meters, _arrow(columns[cursor], arrow), dividers, None, active,
                   _marks(meters, CHANNEL_MARK_LENGTH))


#: The return's heading over each meter as a share of the panel's width --
#: wide enough for ANALOG --, and its meter as a share of its heading: as
#: slim as the channels' bars look beside their neighbours.
RETURN_HEADING_OF_WIDTH = 0.34
RETURN_METER_OF_HEADING = 0.5


def return_picture(cursor, mode, cue, levels, width, height, clips=(), holds=()):
    """The aux return: STEM and ANALOG as mono meters under their names, the
    active bracket over the playing mode's meter, the CUE toggle behind a
    divider at the right edge -- on while the return is cued --, and the
    cursor as the arrow over one of the three. `levels`, `clips` and
    `holds` are STEM, ANALOG."""
    (h0, h1), arrow, (m0, m1) = _bands(height)
    # The CUE field takes the slot of a channel's A, so the two displays
    # side by side carry their last slot in the same place.
    channel = _channel_columns(width)
    last_meter, toggle_slot = channel[PAIRS - 1], channel[ANALOG_INPUT]
    room = last_meter[1] + 1
    heading = round(width * RETURN_HEADING_OF_WIDTH)
    meter = round(heading * RETURN_METER_OF_HEADING)
    spans = ((0, heading - 1), (room - heading, room - 1))
    names = tuple(Heading((x0, h0, x1, h1), RETURN_NAMES[option])
                  for option, (x0, x1) in zip(RETURN_OPTIONS, spans))
    boxes = []
    for x0, x1 in spans:
        left = x0 + (x1 - x0 + 1 - meter) // 2
        boxes.append((left, m0, left + meter - 1, m1))
    meters = _meters(boxes, levels, clips, holds)
    toggle = Toggle((toggle_slot[0], m0, toggle_slot[1], m1), bool(cue), CUE_TEXT)
    divider = _divider(last_meter, toggle_slot, (m0, m1))
    if cursor == CUE_CURSOR:
        selected = toggle_slot
    else:
        box = boxes[RETURN_OPTIONS.index(cursor)]
        selected = (box[0], box[2])
    active = _bracket(boxes[RETURN_OPTIONS.index(mode)])
    return Picture(names, meters, _arrow(selected, arrow), (divider,), toggle, active,
                   _marks(meters))


def cursor_announcement(args):
    """The cursor out of `/channel/{ch}/stem/cursor` (0-8), or None."""
    if len(args) != 1 or not _is_count(args[0], ANALOG_INPUT):
        return None
    return args[0]


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


def mode_announcement(args):
    """The return's mode out of `/aux-return/stem/mode`, or None."""
    if len(args) != 1 or not _is_count(args[0], 1):
        return None
    return args[0]
