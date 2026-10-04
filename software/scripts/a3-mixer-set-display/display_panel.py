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


#: A channel's selector (2026-10-04): inputs 0-7 the stem pairs 1-8, then
#: the channel's analog input -- a3_core_stems' numbers.
INPUTS = PAIRS + 1
ANALOG_INPUT = PAIRS
#: Headings over the channel's meters: the name, the first and the last input.
CHANNEL_GROUPS = (("D1", 0, 3), ("D2", 4, 7), ("A", 8, 8))

#: The aux return's modes -- a3_core_stems' numbers. Its display is a stereo
#: meter (2026-10-04): SA, StemDeck's aux bus, then A, the analog return,
#: each a pair of bars L|R.
ANALOG_MODE, STEM_MODE = 0, 1
RETURN_OPTIONS = (STEM_MODE, ANALOG_MODE)
RETURN_GROUPS = (("SA", 0, 1), ("A", 2, 3))

#: Ten steps a second, decided 2026-10-04 after the desk carried five; what
#: keeps the bus from drowning is that only a panel whose pixels moved is
#: redrawn (pixel_key), not the rate.
METER_STEPS_PER_SECOND = 10
METER_FLOOR_DB = -48.0
#: A VU-like release: a meter falls 20 dB a second, so a level drop of
#: 20/48 of its height per second over the 48 dB range.
METER_FALL_DB_PER_SECOND = 20.0
#: The peak mark holds the highest level this long, then falls alike.
PEAK_HOLD_SECONDS = 1.0


class Ballistics:
    """How one meter moves: an instant rise, a fall of
    METER_FALL_DB_PER_SECOND, and a peak that holds PEAK_HOLD_SECONDS
    before it falls the same way. Levels are 0.0-1.0 as meter_level gives
    them; `dt` is the time since the last feed, in seconds."""

    def __init__(self):
        self._shown = 0.0
        self._peak = 0.0
        self._held = 0.0

    def feed(self, level, dt):
        """(shown, peak) after `dt` seconds that ended at `level`."""
        fall = METER_FALL_DB_PER_SECOND / -METER_FLOOR_DB
        self._shown = max(level, self._shown - fall * dt, 0.0)
        if level >= self._peak:
            self._peak, self._held = level, 0.0
        else:
            self._held += dt
            # Only the part of `dt` past the hold falls, so the mark leaves
            # exactly a second after the hit and not a step early or late.
            falling = min(dt, max(0.0, self._held - PEAK_HOLD_SECONDS))
            self._peak = max(0.0, self._peak - fall * falling)
        self._peak = max(self._peak, self._shown)
        return self._shown, self._peak


def lit_rows(level, count):
    """How many of `count` rows (or segments) `level` lights, half up --
    Python's round() would light a segment at 6.5 but not at 7.5."""
    return int(math.floor(level * count + 0.5))


#: Rows of a channel meter always lit: solid as a block for what plays, so
#: it shows in silence too; one row as the floor of the others.
SOLID_BASE = 2


class Meter(namedtuple("Meter", "box level solid peak")):
    """A channel's meter: a bar, solid or outlined, and a one-row peak mark."""

    def pixels(self):
        """(rows of the bar, row count of the peak mark or 0): what the
        painter draws, in pixels, so two levels in one row are one picture."""
        rows = self.box[3] - self.box[1] + 1
        reach = lit_rows(self.level, rows)
        if self.solid:
            bar = max(reach, SOLID_BASE)
        else:
            bar = reach if reach >= 2 else 0
        peak = lit_rows(self.peak, rows)
        return bar, peak if peak > max(bar, 1) else 0


#: A return bar's segments: rows each, and the dark rows between two.
SEGMENT_ROWS = 3
SEGMENT_GAP = 1


class Bar(namedtuple("Bar", "box level solid peak segments")):
    """A return meter's bar: `segments` stacked from the bottom of `box`."""

    def pixels(self):
        """(lit segments, the peak's segment count or 0); the playing pair
        always shows its lowest segment, the other its outline."""
        lit = max(lit_rows(self.level, self.segments), 1)
        peak = lit_rows(self.peak, self.segments)
        return lit, peak if peak > lit else 0


def segment_rows(bar, index):
    """(top, bottom) rows of segment `index` of `bar`, 0 at the bottom."""
    bottom = bar.box[3] - index * (SEGMENT_ROWS + SEGMENT_GAP)
    return bottom - SEGMENT_ROWS + 1, bottom


def pixel_key(picture):
    """Every meter of `picture` in pixels: equal keys paint equal meters."""
    return tuple(meter.pixels() for meter in picture.meters)


#: What a panel shows: headings over meters, the cursor under one meter, and
#: the return's scale marks (a channel has none).
Heading = namedtuple("Heading", "box text")
Picture = namedtuple("Picture", "headings meters cursor ticks", defaults=((),))
#: A scale mark: its label's box and text, and the row the mark sits on.
Tick = namedtuple("Tick", "box text row")

#: Gaps between meters, in pixels: inside a group, and between two groups.
INNER_GAP = 2
GROUP_GAP = 6


def meter_level(peak):
    """0.0-1.0 for a linear peak, in dB down to METER_FLOOR_DB; anything
    odd is silence."""
    if not isinstance(peak, (int, float)) or isinstance(peak, bool) or not peak > 0:
        return 0.0
    db = 20 * math.log10(peak)
    return max(0.0, min(1.0, (db - METER_FLOOR_DB) / -METER_FLOOR_DB))


def active_input(mask):
    """The input a channel plays: its lowest stem pair, or ANALOG_INPUT."""
    for index in range(PAIRS):
        if mask >> index & 1:
            return index
    return ANALOG_INPUT


def _columns(groups, width):
    """(x0, x1) of every input, the groups apart, centred on the panel."""
    count = groups[-1][2] + 1
    gaps = (count - 1) * INNER_GAP + (len(groups) - 1) * (GROUP_GAP - INNER_GAP)
    meter = (width - gaps) // count
    x = (width - (count * meter + gaps)) // 2
    group_starts = {first for _, first, _ in groups[1:]}
    columns = []
    for index in range(count):
        if index:
            x += GROUP_GAP if index in group_starts else INNER_GAP
        columns.append((x, x + meter - 1))
        x += meter
    return columns


def _bands(height):
    """(heading, meters, cursor) as (top, bottom) rows of the panel."""
    heading = max(6, round(height * 0.19))
    cursor = max(2, round(height * 0.07))
    return ((0, heading - 1), (heading + 1, height - cursor - 3),
            (height - cursor, height - 1))


def _silence(peaks, count):
    return (0.0,) * count if peaks is None else peaks


def channel_picture(cursor, mask, levels, width, height, peaks=None):
    """A channel: the eight stems and its analog input, what plays solid,
    the cursor under its meter. Pure layout; the painter draws it."""
    columns = _columns(CHANNEL_GROUPS, width)
    (h0, h1), (m0, m1), (c0, c1) = _bands(height)
    headings = [Heading((columns[first][0], h0, columns[last][1], h1), name)
                for name, first, last in CHANNEL_GROUPS]
    active = active_input(mask)
    meters = [Meter((x0, m0, x1, m1), level, index == active, peak)
              for index, ((x0, x1), level, peak)
              in enumerate(zip(columns, levels, _silence(peaks, INPUTS)))]
    x0, x1 = columns[cursor]
    return Picture(headings, meters, (x0, c0, x1, c1))


#: The return's layout, in pixels: between L and R of a pair, and the scale
#: column between the two pairs (the marks and their labels).
STEREO_GAP = 3
SCALE_WIDTH = 25
#: The dB values the scale marks, as their labels read.
SCALE_MARKS = ((0, "0"), (-18, "-18"))
#: Tiny-font label rows: a 3x5 glyph.
LABEL_ROWS = 5


def _return_bands(height):
    """(heading, meters, cursor) rows of the return: the heading a little
    lower than a channel's, so the meters fit whole segments."""
    heading = max(6, round(height * 0.16))
    cursor = max(2, round(height * 0.07))
    return ((0, heading - 1), (heading + 1, height - cursor - 3),
            (height - cursor, height - 1))


def _stereo_columns(width):
    """(x0, x1) of the four bars: SA L, SA R, the scale, A L, A R."""
    bar = (width - SCALE_WIDTH - 2 * STEREO_GAP - 4) // 4
    used = 4 * bar + 2 * STEREO_GAP + SCALE_WIDTH
    x = (width - used) // 2
    columns = []
    for index in range(4):
        columns.append((x, x + bar - 1))
        x += bar + (SCALE_WIDTH if index == 1 else STEREO_GAP)
    return columns


def _ticks(columns, bar):
    """The scale marks between the pairs, each on the segment that lights
    at its value, the label kept inside the meters' rows."""
    x0, x1 = columns[1][1] + 2, columns[2][0] - 2
    ticks = []
    for db, text in SCALE_MARKS:
        level = (db - METER_FLOOR_DB) / -METER_FLOOR_DB
        top, bottom = segment_rows(bar, lit_rows(level, bar.segments) - 1)
        middle = (top + bottom) // 2
        y0 = min(max(middle - LABEL_ROWS // 2, bar.box[1]), bar.box[3] - LABEL_ROWS + 1)
        ticks.append(Tick((x0, y0, x1, y0 + LABEL_ROWS - 1), text, middle))
    return ticks


def return_picture(cursor, mode, levels, width, height, peaks=None):
    """The aux return: SA L|R and A L|R as segmented bars, the mode that
    plays filled, the scale between the pairs, the cursor under its pair.
    `levels` and `peaks` are SA L, SA R, A L, A R."""
    columns = _stereo_columns(width)
    (h0, h1), (m0, m1), (c0, c1) = _return_bands(height)
    segments = (m1 - m0 + 1 + SEGMENT_GAP) // (SEGMENT_ROWS + SEGMENT_GAP)
    top = m1 - segments * (SEGMENT_ROWS + SEGMENT_GAP) + SEGMENT_GAP + 1
    headings = [Heading((columns[first][0], h0, columns[last][1], h1), name)
                for name, first, last in RETURN_GROUPS]
    playing = RETURN_OPTIONS.index(mode)
    bars = [Bar((x0, top, x1, m1), level, index // 2 == playing, peak, segments)
            for index, ((x0, x1), level, peak)
            in enumerate(zip(columns, levels, _silence(peaks, 4)))]
    _, first, last = RETURN_GROUPS[RETURN_OPTIONS.index(cursor)]
    return Picture(headings, bars, (columns[first][0], c0, columns[last][1], c1),
                   _ticks(columns, bars[0]))


def cursor_announcement(args):
    """The cursor out of `/channel/{ch}/stem/cursor` (0-8), or None."""
    if len(args) != 1 or not _is_count(args[0], ANALOG_INPUT):
        return None
    return args[0]


def mode_announcement(args):
    """The return's mode out of `/aux-return/stem/mode`, or None."""
    if len(args) != 1 or not _is_count(args[0], 1):
        return None
    return args[0]
