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
#: display, each a mono meter under its name, the display's title between.
ANALOG_MODE, STEM_MODE = 0, 1
RETURN_OPTIONS = (STEM_MODE, ANALOG_MODE)
RETURN_NAMES = {STEM_MODE: "STEM", ANALOG_MODE: "ANALOG"}
RETURN_TITLE = "AUX"

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


def lit_rows(level, count):
    """How many of `count` rows `level` lights, half up -- Python's round()
    would light a row at 6.5 but not at 7.5."""
    return int(math.floor(level * count + 0.5))


class Meter(namedtuple("Meter", "box level")):
    """A meter: a plain filled bar at its level and nothing else -- no mark
    of which input is assigned, no peak and no floor line: turning, the
    hands want the selector only (maintainer, 2026-10-04)."""

    def pixels(self):
        """Rows of the bar: what the painter draws, in pixels, so two levels
        in one row are one picture."""
        return lit_rows(self.level, self.box[3] - self.box[1] + 1)


class Toggle(namedtuple("Toggle", "box on text")):
    """The channel's STEM switch: on while a stem plays on the channel. It
    says that one plays, never which (maintainer, 2026-10-04)."""

    def pixels(self):
        return self.on


def pixel_key(picture):
    """Everything `picture` paints, in pixels: equal keys paint equal
    pictures. The headings are in it because the return's playing mode is
    an inverted heading."""
    toggle = picture.toggle.pixels() if picture.toggle is not None else None
    return (tuple(meter.pixels() for meter in picture.meters), picture.cursor, toggle,
            tuple(picture.headings))


#: What a panel shows: headings over meters, the cursor -- the box of the
#: slot it inverts --, divider lines, and a channel's toggle.
Heading = namedtuple("Heading", "box text inverted", defaults=(False,))
Picture = namedtuple("Picture", "headings meters cursor dividers toggle", defaults=((), None))

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


#: The toggle's share of the row, in meters. With one meter's width a
#: selected ON toggle could only get a one-pixel light band and looked like
#: an unselected OFF one (snapshots, 2026-10-04); two leave room for a wide
#: band and for STEM's letters, and the meters keep 10 of their 11 pixels.
TOGGLE_METERS = 2


def _channel_columns(width):
    """(x0, x1) of the eight meters and the toggle: the meters as wide as
    PAIRS + TOGGLE_METERS equal slots make them, the toggle the rest."""
    gaps = (len(CHANNEL_GROUPS) * (GROUP_GAP - INNER_GAP)) + PAIRS * INNER_GAP
    meter = (width - gaps) // (PAIRS + TOGGLE_METERS)
    group_starts = {first for _, first, _ in CHANNEL_GROUPS[1:]}
    columns, x = [], 0
    for index in range(PAIRS):
        if index:
            x += GROUP_GAP if index in group_starts else INNER_GAP
        columns.append((x, x + meter - 1))
        x += meter
    columns.append((x + GROUP_GAP, width - 1))
    return columns


def _bands(height):
    """(heading, meters) as (top, bottom) rows of the panel. The meters run
    to the bottom row: the cursor is a column now, not a row of its own."""
    heading = max(6, round(height * 0.19))
    return (0, heading - 1), (heading + 1, height - 1)


def _divider(left, right, rows):
    """A vertical line in the middle of the gap between two columns, the
    meters' height: below the headings."""
    x = (left[1] + right[0]) // 2
    return (x, rows[0], x, rows[1])


def channel_picture(cursor, levels, stem_on, width, height):
    """A channel: the eight stems as plain bars under D1 | D2, the STEM
    toggle in the ninth slot, and the cursor as the inverted column of one
    of them. Pure layout; the painter draws it."""
    columns = _channel_columns(width)
    (h0, h1), (m0, m1) = _bands(height)
    headings = tuple(Heading((columns[first][0], h0, columns[last][1], h1), name)
                     for name, first, last in CHANNEL_GROUPS)
    meters = tuple(Meter((x0, m0, x1, m1), level) for (x0, x1), level in zip(columns, levels))
    toggle = Toggle((columns[STEM_TOGGLE][0], m0, columns[STEM_TOGGLE][1], m1),
                    bool(stem_on), TOGGLE_TEXT)
    dividers = tuple(_divider(columns[first - 1], columns[first], (m0, m1))
                     for first in [first for _, first, _ in CHANNEL_GROUPS[1:]] + [STEM_TOGGLE])
    x0, x1 = columns[cursor]
    return Picture(headings, meters, (x0, m0, x1, m1), dividers, toggle)


#: The return's heading over each meter as a share of the panel's width --
#: wide enough for ANALOG --, and its meter as a share of its heading: as
#: slim as the channels' bars look beside their neighbours.
RETURN_HEADING_OF_WIDTH = 0.34
RETURN_METER_OF_HEADING = 0.5


def return_picture(cursor, mode, levels, width, height):
    """The aux return: STEM and ANALOG as mono meters under their names, the
    playing mode's name inverted, AUX as the title between them, the cursor
    as the inverted column of one. `levels` are STEM, ANALOG."""
    (h0, h1), (m0, m1) = _bands(height)
    heading = round(width * RETURN_HEADING_OF_WIDTH)
    meter = round(heading * RETURN_METER_OF_HEADING)
    spans = ((0, heading - 1), (width - heading, width - 1))
    names = [Heading((x0, h0, x1, h1), RETURN_NAMES[option], option == mode)
             for option, (x0, x1) in zip(RETURN_OPTIONS, spans)]
    # The title stands between the two meters, in the middle of their
    # height: a heading in the row of STEM and ANALOG would read as a third
    # option to turn to.
    title = Heading((spans[0][1] + 1, m0, spans[1][0] - 1, m1), RETURN_TITLE)
    boxes = []
    for x0, x1 in spans:
        left = x0 + (x1 - x0 + 1 - meter) // 2
        boxes.append((left, m0, left + meter - 1, m1))
    meters = tuple(Meter(box, level) for box, level in zip(boxes, levels))
    return Picture((names[0], title, names[1]), meters,
                   boxes[RETURN_OPTIONS.index(cursor)])


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
