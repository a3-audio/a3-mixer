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
#: then the FX return -- and the desk's channel index 0..3 is deck 1..4.
CHANNEL_COUNT = 4


def panel_for_channel(index):
    """The display of channel `index` (0..3); anything else is a bug upstream."""
    if not 0 <= index < CHANNEL_COUNT:
        raise IndexError("the desk has channels 0..%d, not %d" % (CHANNEL_COUNT - 1, index))
    return PANELS[index]


def return_panel():
    """The FX return's display, the one after the four decks."""
    return PANELS[CHANNEL_COUNT]


PAIRS = 8


def _is_count(value, upper):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= upper


def channel_announcement(args):
    """The pair out of `/channel/{ch}/stem`'s arguments, or None if damaged."""
    if len(args) != 1 or not _is_count(args[0], PAIRS):
        return None
    return args[0]


def return_announcement(args):
    """(cursor, plays) out of `/fx-return/stem`'s arguments -- the pair the
    encoder is on, then for pairs 1-8 whether it plays on the return -- or
    None if damaged."""
    if len(args) != 1 + PAIRS or not _is_count(args[0], PAIRS):
        return None
    if not all(_is_count(flag, 1) for flag in args[1:]):
        return None
    return args[0], tuple(bool(flag) for flag in args[1:])


#: One square per stem, plus the analog input on a channel: `box` is
#: (x0, y0, x1, y1), `label` what is written in it ("1"-"4", "A"), `mark` the
#: block behind the digit of the square the return's encoder is on, `bar` the
#: stem's level along the bottom edge -- each a box or None -- and `face` the
#: area above the bar's strip where the digit (and the block) sit.
Square = namedtuple("Square", "box label filled mark bar face")

STEMS_PER_DECK = 4
COLUMNS = STEMS_PER_DECK + 1   # the fifth column holds "A", bottom right
SQUARE_OF_CELL = 0.75   # the square's side, as a share of its cell
BAR_OF_SQUARE = 0.12    # the level bar's height, as a share of the square
BAR_INSET = 0.12        # its gap to the square's edges, as a share of the square
LEVEL_STEPS = 6         # a3_mixer_levels.STEPS: a full bar


def channel_squares(pair, width, height, levels=None):
    """A channel's display: the stem it plays filled, or "A" while it plays
    its analog input (pair 0). `levels` (pair -> step) draws a bar in each
    stem square; "A" has none."""
    squares = _stem_squares([p == pair for p in range(1, PAIRS + 1)], 0, width, height,
                            levels)
    return squares + [_square(STEMS_PER_DECK, 1, "A", pair == 0, False, 0, width, height)]


def return_squares(cursor, plays, width, height, levels=None):
    """The FX return's display: what plays there filled, the digit of the
    stem under the encoder (`cursor`) inverted, the stems' levels as bars.
    Its "A" place stays empty."""
    return _stem_squares(list(plays), cursor, width, height, levels)


def _stem_squares(filled, marked_pair, width, height, levels=None):
    """StemDeck 1's stems 1-4 on top, StemDeck 2's below, columns 1-4
    (2026-10-01: pairs 1-4 are deck A's stems, 5-8 deck B's)."""
    return [_square(index % STEMS_PER_DECK, index // STEMS_PER_DECK,
                    str(index % STEMS_PER_DECK + 1), is_filled,
                    index + 1 == marked_pair, (levels or {}).get(index + 1, 0),
                    width, height)
            for index, is_filled in enumerate(filled)]


def _square(column, row, label, filled, marked, step, width, height):
    """A square centred in its cell of the 5x2 grid, sized by the cell, so
    any panel draws the same picture."""
    cell_w = width / COLUMNS
    cell_h = height / 2
    side = round(min(cell_w, cell_h) * SQUARE_OF_CELL)
    x0 = round(column * cell_w + (cell_w - side) / 2)
    y0 = round(row * cell_h + (cell_h - side) / 2)
    inset = max(1, round(side * BAR_INSET))
    bar_height = max(1, round(side * BAR_OF_SQUARE))
    bottom = y0 + side - inset
    # The digit's area: above the bar's strip, whether a bar shows or not.
    face = (x0 + inset, y0 + inset, x0 + side - inset, bottom - bar_height - inset)
    mark = None
    if marked:
        # A square block, as tall as the face, centred on the digit.
        half = (face[3] - face[1]) // 2
        middle = (face[0] + face[2]) // 2
        mark = (middle - half, face[1], middle + half, face[3])
    bar = None
    length = round((side - 2 * inset) * min(step, LEVEL_STEPS) / LEVEL_STEPS)
    if length > 0:
        bar = (x0 + inset, bottom - bar_height, x0 + inset + length, bottom)
    return Square((x0, y0, x0 + side, y0 + side), label, filled, mark, bar, face)
