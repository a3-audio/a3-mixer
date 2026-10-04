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

#: The aux return's modes -- a3_core_stems' numbers -- and its two meters,
#: left to right: SA, the stems on the return, then A, the analog return.
ANALOG_MODE, STEM_MODE = 0, 1
RETURN_OPTIONS = (STEM_MODE, ANALOG_MODE)
RETURN_GROUPS = (("SA", 0, 0), ("A", 1, 1))

METER_STEPS_PER_SECOND = 5   # measured on the desk first (smoke-test/scripts/desk-wave-bench.py)
METER_FLOOR_DB = -48.0

#: What a panel shows: headings over meters, and the cursor under one meter.
Heading = namedtuple("Heading", "box text")
Meter = namedtuple("Meter", "box level solid")
Picture = namedtuple("Picture", "headings meters cursor")

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


def selector_picture(groups, levels, active, cursor, width, height):
    """Meters under their groups' headings: `active` solid, the cursor under
    its meter. Pure layout; the painter draws it."""
    columns = _columns(groups, width)
    (h0, h1), (m0, m1), (c0, c1) = _bands(height)
    headings = [Heading((columns[first][0], h0, columns[last][1], h1), name)
                for name, first, last in groups]
    meters = [Meter((x0, m0, x1, m1), level, index == active)
              for index, ((x0, x1), level) in enumerate(zip(columns, levels))]
    x0, x1 = columns[cursor]
    return Picture(headings, meters, (x0, c0, x1, c1))


def channel_picture(cursor, mask, levels, width, height):
    """A channel: the eight stems and its analog input, what plays solid."""
    return selector_picture(CHANNEL_GROUPS, levels, active_input(mask), cursor, width, height)


def return_picture(cursor, mode, stems_level, analog_level, width, height):
    """The aux return: SA and A, the mode that plays solid."""
    return selector_picture(RETURN_GROUPS, (stems_level, analog_level),
                            RETURN_OPTIONS.index(mode), RETURN_OPTIONS.index(cursor),
                            width, height)


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
