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
from collections import namedtuple

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
    the encoder is on (0 = analog, 1 = stem), then for pairs 1-8 whether it
    plays on the return -- or None if damaged."""
    if len(args) != 1 + PAIRS or not _is_count(args[0], 1):
        return None
    if not all(_is_count(flag, 1) for flag in args[1:]):
        return None
    return args[0], tuple(bool(flag) for flag in args[1:])


#: A channel's selector (2026-10-04): positions 0-7 the stem pairs 1-8, then
#: the STEM toggle -- a3_core_stems' numbers. Core turns the channel's stem
#: on and off there; the analog input meter it replaced is gone.
STEM_TOGGLE = PAIRS
#: Headings over the channel's meters: the name, the first and the last stem.
CHANNEL_GROUPS = (("D1", 0, 3), ("D2", 4, 7))
TOGGLE_TEXT = "STEM"

#: The aux return's modes -- a3_core_stems' numbers -- left to right on its
#: display, each a mono meter under its name and nothing between them: an
#: AUX title there irritated (maintainer, 2026-10-04).
ANALOG_MODE, STEM_MODE = 0, 1
RETURN_OPTIONS = (STEM_MODE, ANALOG_MODE)
RETURN_NAMES = {STEM_MODE: "STEM", ANALOG_MODE: "ANALOG"}

#: Ten steps a second, decided 2026-10-04 after the desk carried five; what
#: keeps the bus from drowning is that only a panel whose pixels moved is
#: redrawn (pixel_key), not the rate.
METER_STEPS_PER_SECOND = 10
METER_FLOOR_DB = -48.0
#: A VU-like release: a meter falls 20 dB a second, so a level drop of
#: 20/48 of its height per second over the 48 dB range.
METER_FALL_DB_PER_SECOND = 20.0


class Ballistics:
    """How one meter moves: an instant rise and a fall of
    METER_FALL_DB_PER_SECOND. Levels are 0.0-1.0 as meter_level gives them;
    `dt` is the time since the last feed, in seconds."""

    def __init__(self):
        self._shown = 0.0

    def feed(self, level, dt):
        """The level shown after `dt` seconds that ended at `level`."""
        fall = METER_FALL_DB_PER_SECOND / -METER_FLOOR_DB
        self._shown = max(level, self._shown - fall * dt, 0.0)
        return self._shown


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
    last feed, in seconds, as for Ballistics."""

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


class Meter(namedtuple("Meter", "box level clip", defaults=(False,))):
    """A meter: a filled bar at its level and nothing else -- no mark of
    which input is assigned, no peak and no floor line: turning, the hands
    want the selector only (maintainer, 2026-10-04). While it clips
    (ClipHold) the bar is drawn hatched."""

    def pixels(self):
        """Rows of the bar: what the painter draws, in pixels, so two levels
        in one row are one picture."""
        return lit_rows(self.level, self.box[3] - self.box[1] + 1)

    def hatched(self):
        """Whether the painter hatches the bar: a clip with no bar to show
        it on moves no pixel."""
        return self.clip and self.pixels() > 0


class Toggle(namedtuple("Toggle", "box on text")):
    """The channel's STEM switch: on while a stem plays on the channel. It
    says that one plays; which one is the active bracket's (maintainer,
    2026-10-04)."""

    def pixels(self):
        return self.on


def pixel_key(picture):
    """Everything `picture` paints, in pixels: equal keys paint equal
    pictures."""
    toggle = picture.toggle.pixels() if picture.toggle is not None else None
    return (tuple((meter.pixels(), meter.hatched()) for meter in picture.meters),
            picture.cursor, toggle,
            picture.active, tuple(picture.headings))


#: What a panel shows: headings over meters, the cursor -- the box of the
#: down arrow over the selected slot --, divider lines, a channel's toggle,
#: and the box of the active bracket over the meter that plays, or None.
Heading = namedtuple("Heading", "box text")
Picture = namedtuple("Picture", "headings meters cursor dividers toggle active",
                     defaults=((), None, None))

#: Gaps between meters, in pixels: inside a group, and between two groups --
#: wide enough for a divider line in its middle with three dark columns on
#: each side (D1 | D2 | STEM stand apart, maintainer 2026-10-04).
INNER_GAP = 2
GROUP_GAP = 7


def meter_level(peak):
    """0.0-1.0 for a linear peak, in dB down to METER_FLOOR_DB; anything
    odd is silence."""
    if not isinstance(peak, (int, float)) or isinstance(peak, bool) or not peak > 0:
        return 0.0
    db = 20 * math.log10(peak)
    return max(0.0, min(1.0, (db - METER_FLOOR_DB) / -METER_FLOOR_DB))


#: The toggle's share of the row, in meters: two leave room for STEM's
#: letters inside its field, and the meters keep 10 of their 11 pixels.
TOGGLE_METERS = 2


#: Dark columns left of stem 1: the panel's edge is a gap too, so the
#: active bracket's left leg has a column there as it has between meters.
EDGE = 1


def _channel_columns(width):
    """(x0, x1) of the eight meters and the toggle: the meters as wide as
    PAIRS + TOGGLE_METERS equal slots make them, the toggle the rest."""
    gaps = EDGE + (len(CHANNEL_GROUPS) * (GROUP_GAP - INNER_GAP)) + PAIRS * INNER_GAP
    meter = (width - gaps) // (PAIRS + TOGGLE_METERS)
    group_starts = {first for _, first, _ in CHANNEL_GROUPS[1:]}
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


def _meters(boxes, levels, clips):
    """A meter per box; `clips` empty is no meter clipping."""
    clips = tuple(clips) or (False,) * len(boxes)
    return tuple(Meter(box, level, bool(clip))
                 for box, level, clip in zip(boxes, levels, clips))


def channel_picture(cursor, levels, mask, width, height, clips=()):
    """A channel: the eight stems as bars under D1 | D2 -- hatched where
    `clips` says one clips --, the STEM toggle in the ninth slot, the cursor
    as the arrow over one of them, and the active bracket over the stem
    `mask` plays. Pure layout; the painter draws it."""
    columns = _channel_columns(width)
    (h0, h1), arrow, (m0, m1) = _bands(height)
    headings = tuple(Heading((columns[first][0], h0, columns[last][1], h1), name)
                     for name, first, last in CHANNEL_GROUPS)
    meters = _meters([(x0, m0, x1, m1) for x0, x1 in columns[:PAIRS]], levels, clips)
    playing = playing_stem(mask)
    toggle = Toggle((columns[STEM_TOGGLE][0], m0, columns[STEM_TOGGLE][1], m1),
                    playing is not None, TOGGLE_TEXT)
    dividers = tuple(_divider(columns[first - 1], columns[first], (m0, m1))
                     for first in [first for _, first, _ in CHANNEL_GROUPS[1:]] + [STEM_TOGGLE])
    active = _bracket(meters[playing].box) if playing is not None else None
    return Picture(headings, meters, _arrow(columns[cursor], arrow), dividers, toggle, active)


#: The return's heading over each meter as a share of the panel's width --
#: wide enough for ANALOG --, and its meter as a share of its heading: as
#: slim as the channels' bars look beside their neighbours.
RETURN_HEADING_OF_WIDTH = 0.34
RETURN_METER_OF_HEADING = 0.5


def return_picture(cursor, mode, levels, width, height, clips=()):
    """The aux return: STEM and ANALOG as mono meters under their names, the
    active bracket over the playing mode's meter, the cursor as the arrow
    over one. `levels` and `clips` are STEM, ANALOG."""
    (h0, h1), arrow, (m0, m1) = _bands(height)
    heading = round(width * RETURN_HEADING_OF_WIDTH)
    meter = round(heading * RETURN_METER_OF_HEADING)
    spans = ((0, heading - 1), (width - heading, width - 1))
    names = tuple(Heading((x0, h0, x1, h1), RETURN_NAMES[option])
                  for option, (x0, x1) in zip(RETURN_OPTIONS, spans))
    boxes = []
    for x0, x1 in spans:
        left = x0 + (x1 - x0 + 1 - meter) // 2
        boxes.append((left, m0, left + meter - 1, m1))
    meters = _meters(boxes, levels, clips)
    selected = boxes[RETURN_OPTIONS.index(cursor)]
    active = _bracket(boxes[RETURN_OPTIONS.index(mode)])
    return Picture(names, meters, _arrow((selected[0], selected[2]), arrow), active=active)


def cursor_announcement(args):
    """The cursor out of `/channel/{ch}/stem/cursor` (0-8), or None."""
    if len(args) != 1 or not _is_count(args[0], STEM_TOGGLE):
        return None
    return args[0]


def mode_announcement(args):
    """The return's mode out of `/aux-return/stem/mode`, or None."""
    if len(args) != 1 or not _is_count(args[0], 1):
        return None
    return args[0]
