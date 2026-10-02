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
    """(cursor, plays) out of `/aux-return/stem`'s arguments -- the pair the
    encoder is on, then for pairs 1-8 whether it plays on the return -- or
    None if damaged."""
    if len(args) != 1 + PAIRS or not _is_count(args[0], PAIRS):
        return None
    if not all(_is_count(flag, 1) for flag in args[1:]):
        return None
    return args[0], tuple(bool(flag) for flag in args[1:])


#: The stem selector's fields (spec desk-stem-selector, 2026-10-02): eight
#: stems (StemDeck A's on top, B's below) and the fifth column's field, bottom
#: right -- a channel's A, the return's empty field. A field shows the symbol
#: of the place its stem plays: channel 1-4, then the aux return.
SYMBOLS = ("circle", "square", "triangle", "diamond", "star")
RETURN_PLACE = 4

#: `box` is (x0, y0, x1, y1); `symbol` a name from SYMBOLS or None; `framed`
#: whether the place's selection stands here; `bar` the stem's level, a box
#: under the field, or None.
Field = namedtuple("Field", "box symbol framed bar")

STEMS_PER_DECK = 4
COLUMNS = STEMS_PER_DECK + 1   # the fifth column holds A / the empty field
FIELD_OF_CELL = 0.5            # the field's side, as a share of its cell's smaller side
BAR_HEIGHT_OF_CELL = 0.12      # the level bar's height, as a share of the cell's height
LEVEL_STEPS = 6                # a3_mixer_levels.STEPS: a full bar


def places_of(masks, plays):
    """Where each pair plays: the first channel index whose mask has it, else
    RETURN_PLACE if it plays on the return, else None."""
    places = []
    for pair in range(1, PAIRS + 1):
        on = [c for c, mask in enumerate(masks) if mask >> (pair - 1) & 1]
        places.append(on[0] if on else (RETURN_PLACE if plays[pair - 1] else None))
    return places


def channel_fields(index, places, selected, width, height, levels=None):
    """Channel `index`'s display: the stems, then A -- which shows the
    channel's own symbol while no stem plays there."""
    on_analog = index not in places
    return _stem_fields(places, selected, width, height, levels) + [
        _field(STEMS_PER_DECK, 1, SYMBOLS[index] if on_analog else None, selected == 0, 0,
               width, height)]


def return_fields(places, selected, width, height, levels=None):
    """The aux return's display: the stems, then the empty field (no stem on
    the return)."""
    return _stem_fields(places, selected, width, height, levels) + [
        _field(STEMS_PER_DECK, 1, None, selected == 0, 0, width, height)]


def _symbol(place):
    return None if place is None else SYMBOLS[place]


def _stem_fields(places, selected, width, height, levels):
    return [_field(i % STEMS_PER_DECK, i // STEMS_PER_DECK, _symbol(place), selected == i + 1,
                   (levels or {}).get(i + 1, 0), width, height)
            for i, place in enumerate(places)]


def _field(column, row, symbol, framed, step, width, height):
    """A field centred in its cell of the 5x2 grid with its bar below, sized
    by the cell, so any panel draws the same picture."""
    cell_w, cell_h = width / COLUMNS, height / 2
    side = round(min(cell_w, cell_h) * FIELD_OF_CELL)
    bar_h = max(1, round(cell_h * BAR_HEIGHT_OF_CELL))
    gap = max(1, bar_h // 2)
    x0 = round(column * cell_w + (cell_w - side) / 2)
    y0 = round(row * cell_h + (cell_h - side - gap - bar_h) / 2)
    bar = None
    length = round(side * min(step, LEVEL_STEPS) / LEVEL_STEPS)
    if length > 0:
        top = y0 + side + gap
        bar = (x0, top, x0 + length, top + bar_h)
    return Field((x0, y0, x0 + side, y0 + side), symbol, framed, bar)


#: How far a symbol keeps from its field's edge, as a share of the side.
SYMBOL_INSET = 0.2


def symbol_shape(symbol, box):
    """What the painter draws for `symbol` inside `box`: ("ellipse" or
    "rectangle", (x0, y0, x1, y1)) or ("polygon", (x, y, x, y, ...))."""
    x0, y0, x1, y1 = box
    inset = max(1, round((x1 - x0) * SYMBOL_INSET))
    left, top, right, bottom = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    cx, cy = (left + right) / 2, (top + bottom) / 2
    if symbol == "circle":
        return "ellipse", (left, top, right, bottom)
    if symbol == "square":
        return "rectangle", (left, top, right, bottom)
    if symbol == "triangle":
        return "polygon", (cx, top, right, bottom, left, bottom)
    if symbol == "diamond":
        return "polygon", (cx, top, right, cy, cx, bottom, left, cy)
    outer, inner = (right - left) / 2, (right - left) / 5
    points = []
    for corner in range(10):
        radius = outer if corner % 2 == 0 else inner
        angle = math.pi / 2 + corner * math.pi / 5
        points += [cx + radius * math.cos(angle), cy - radius * math.sin(angle)]
    return "polygon", tuple(points)


#: A cell of the stem grid (spec desk-stem-grid): `box` its square, `mark`
#: "dot", "ring" or None, `digit` "1"-"5" or None, `inverted` the cursor.
Cell = namedtuple("Cell", "box mark digit inverted")


GRID_COLUMNS = STEMS_PER_DECK + 1   # deck 1 then A; deck 2 then the return's spare place
A_CELL = PAIRS                      # grid_cells' index of A


def grid_cells(width, height):
    """The grid's squares in the upper half: pairs 1-8, then A, then the
    spare place under it. Two rows fill the half; neighbours share an edge,
    so the dots sit as close as the panel allows."""
    pitch = height // 4 - 1
    left = (width - GRID_COLUMNS * pitch) // 2
    order = [(i % STEMS_PER_DECK, i // STEMS_PER_DECK) for i in range(PAIRS)]
    order += [(STEMS_PER_DECK, 0), (STEMS_PER_DECK, 1)]
    return [(left + c * pitch, r * pitch, left + (c + 1) * pitch, (r + 1) * pitch)
            for c, r in order]


def wave_box(width, height):
    """The lower half, for the waveform."""
    return (0, height // 2, width - 1, height - 1)


def channel_cells(index, places, cursor, width, height):
    """Channel `index`'s grid: pairs 1-8, then A. A dot where the channel may
    choose, a ring where another channel plays, its own digit at what it
    plays (A while analog), the cursor (0 = A) inverted."""
    boxes = grid_cells(width, height)
    digit = str(index + 1)
    cells = []
    for i, place in enumerate(places):
        if place == index:
            cells.append(Cell(boxes[i], None, digit, cursor == i + 1))
            continue
        on_other = place is not None and place != RETURN_PLACE
        cells.append(Cell(boxes[i], "ring" if on_other else "dot", None, cursor == i + 1))
    analog = index not in places
    cells.append(Cell(boxes[A_CELL], None if analog else "dot", digit if analog else None,
                      cursor == 0))
    return cells


def return_cells(places, cursor, width, height):
    """The return's grid: at every stem the digit of where it plays (1-4 a
    channel, 5 the return), a dot where it plays nowhere; the cursor
    inverted (none for 0)."""
    boxes = grid_cells(width, height)
    return [Cell(boxes[i], "dot" if place is None else None,
                 None if place is None else str(place + 1), cursor == i + 1)
            for i, place in enumerate(places)]


WAVE_STEPS_PER_SECOND = 5   # measured on the desk first (smoke-test/scripts/desk-wave-bench.py)
WAVE_COLUMNS_PER_STEP = 2
WAVE_FLOOR_DB = -48.0


def wave_level(peak):
    """0.0-1.0 for a linear peak, in dB down to WAVE_FLOOR_DB; anything odd
    is silence."""
    if not isinstance(peak, (int, float)) or isinstance(peak, bool) or peak <= 0:
        return 0.0
    db = 20 * math.log10(peak)
    return max(0.0, min(1.0, (db - WAVE_FLOOR_DB) / -WAVE_FLOOR_DB))


class Wave:
    """One display's envelope history, a level per column, newest last.
    Always `width` columns: it starts silent and drops what scrolls out."""

    def __init__(self, width):
        self._levels = [0.0] * width

    def step(self, level):
        self._levels = self._levels[WAVE_COLUMNS_PER_STEP:] + [level] * WAVE_COLUMNS_PER_STEP

    def columns(self, box):
        """(x, top, bottom) per column inside `box`, mirrored about its
        middle; silence is the middle line."""
        x0, y0, x1, y1 = box
        half = (y1 - y0) / 2
        out = []
        for offset, level in enumerate(self._levels[-(x1 - x0 + 1):]):
            gap = int(half * (1.0 - level))
            out.append((x0 + offset, y0 + gap, y1 - gap))
        return out


def selected_announcement(args):
    """The selection out of `/channel/{ch}/stem/selected`'s arguments (0 = A,
    1-8 a stem), or None if damaged."""
    if len(args) != 1 or not _is_count(args[0], PAIRS):
        return None
    return args[0]
