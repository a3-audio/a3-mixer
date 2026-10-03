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


#: Where a stem plays (specs desk-stem-grid, desk-stem-grid-2): a channel
#: index 0-3, or the aux return. Pairs 1-4 are StemDeck deck 1, 5-8 deck 2.
RETURN_PLACE = 4
STEMS_PER_DECK = 4


def places_of(masks, plays):
    """Where each pair plays: the first channel index whose mask has it, else
    RETURN_PLACE if it plays on the return, else None."""
    places = []
    for pair in range(1, PAIRS + 1):
        on = [c for c, mask in enumerate(masks) if mask >> (pair - 1) & 1]
        places.append(on[0] if on else (RETURN_PLACE if plays[pair - 1] else None))
    return places


def wave_box(width, height):
    """The lower half, for the waveform."""
    return (0, height // 2, width - 1, height - 1)


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
        """Moves the wave on; False when it looks the same as before (a
        silent wave stays silent), so nothing needs drawing."""
        moved = self._levels[WAVE_COLUMNS_PER_STEP:] + [level] * WAVE_COLUMNS_PER_STEP
        changed = moved != self._levels
        self._levels = moved
        return changed

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


class WaveStrip:
    """A wave and its picture, `width` x `height`: a step moves the picture
    WAVE_COLUMNS_PER_STEP columns left and draws only the new columns --
    repainting all 128 lines cost most of a 53 ms draw on the desk
    (desk-stem-grid-2). Draws exactly what Wave.columns says."""

    def __init__(self, width, height):
        from PIL import Image, ImageDraw
        self._wave = Wave(width)
        self._box = (0, 0, width - 1, height - 1)
        self.image = Image.new("1", (width, height))
        draw = ImageDraw.Draw(self.image)
        for x, top, bottom in self._wave.columns(self._box):
            draw.line((x, top, x, bottom), fill="white")

    def columns(self, box):
        """The wave as (x, top, bottom) columns in any `box`."""
        return self._wave.columns(box)

    def shift(self, level):
        """Moves the wave on; False when its picture did not change."""
        from PIL import Image, ImageDraw
        if not self._wave.step(level):
            return False
        width, height = self.image.size
        n = WAVE_COLUMNS_PER_STEP
        moved = Image.new("1", (width, height))
        moved.paste(self.image.crop((n, 0, width, height)), (0, 0))
        draw = ImageDraw.Draw(moved)
        for x, top, bottom in self._wave.columns(self._box)[-n:]:
            draw.line((x, top, x, bottom), fill="white")
        self.image = moved
        return True


#: One entry of a menu in the upper half (spec desk-stem-grid-2): `inverted`
#: is the cursor, `marked` what plays. `cursor_from` is the cursor inside the
#: text -- the index where its inverted part starts (2026-10-03: behind the
#: dot of D1.3 while a deck is edited) -- or None.
MenuItem = namedtuple("MenuItem", "box text inverted marked cursor_from", defaults=(None,))

#: A channel menu's levels and entries -- a3_core_stems' numbers.
TOP_LEVEL = 0
TOP_ENTRIES = ("D1", "D2", "A")
BACK_ENTRY = "<"   # the default font has no arrow: "\u2190" drew an empty box


def _slots(count, width, height):
    """`count` boxes side by side across the upper half."""
    half = height // 2
    slot = width // count
    top, bottom = round(half * 0.15), round(half * 0.85)
    return [(i * slot + 1, top, (i + 1) * slot - 2, bottom) for i in range(count)]


def _sources(index, places):
    """What channel `index` plays from: {0} D1, {1} D2, both -- one stem of
    each deck may play (2026-10-02) -- or {2} A."""
    decks = {pair // STEMS_PER_DECK for pair, place in enumerate(places) if place == index}
    return decks or {2}


def _stem_here(deck, places, index):
    """The stem (0-3) of `deck` channel `index` plays, or None."""
    stems = [stem for stem in range(STEMS_PER_DECK)
             if places[deck * STEMS_PER_DECK + stem] == index]
    return stems[0] if stems else None


def _deck_label(deck, places, index):
    """'D1.3' -- the deck and the stem of it this channel plays -- or 'D1.-'."""
    stem = _stem_here(deck, places, index)
    return "D%d.%s" % (deck + 1, "-" if stem is None else stem + 1)


def _top_items(index, cursor, places, boxes):
    sources = _sources(index, places)
    texts = [_deck_label(0, places, index), _deck_label(1, places, index), "A"]
    return [MenuItem(box, text, cursor == i, i in sources)
            for i, (box, text) in enumerate(zip(boxes, texts))]


def _edit_item(index, deck, cursor, places, box):
    """The edited deck's field: the candidate behind the dot -- 'D1.2', or
    'D1.<' for back -- marked when it plays here. Always exactly one
    character changes, whatever channel the stem plays on: a longer label
    ('D1.2>4') shrank the font (maintainer, 2026-10-03)."""
    prefix = "D%d." % (deck + 1)
    if cursor == STEMS_PER_DECK:
        playing = _stem_here(deck, places, index) is not None
        return MenuItem(box, prefix + BACK_ENTRY, False, playing, len(prefix))
    place = places[deck * STEMS_PER_DECK + cursor]
    return MenuItem(box, prefix + str(cursor + 1), False, place == index, len(prefix))


def menu_items(index, menu, places, width, height):
    """Channel `index`'s menu. At the top: D1.3  D2.-  A -- which stem of
    each deck plays (2026-10-03), what plays marked, the cursor inverted.
    In a deck the same row, the deck's own field edited in place
    (2026-10-03: no sub-level screen): the candidate stem or '<' behind the
    dot, and only that part is the cursor."""
    level, cursor = menu
    boxes = _slots(3, width, height)
    if level == TOP_LEVEL:
        return _top_items(index, cursor, places, boxes)
    deck = level - 1
    items = _top_items(index, None, places, boxes)
    items[deck] = _edit_item(index, deck, cursor, places, boxes[deck])
    return items


#: The aux return's modes -- a3_core_stems' numbers.
ANALOG_MODE, STEM_MODE = 0, 1


def return_items(mode, cursor, width, height):
    """The return's two modes: the active one marked, the cursor inverted."""
    boxes = _slots(2, width, height)
    return [MenuItem(boxes[0], "STEM", cursor == STEM_MODE, mode == STEM_MODE),
            MenuItem(boxes[1], "ANALOG", cursor == ANALOG_MODE, mode == ANALOG_MODE)]


def return_bars(stem_levels, aux_levels, width, height):
    """Nine meters in the lower half: the eight stems, then the analog
    return as two thin halves (L, R). A box per bar, None where silent."""
    half = height // 2
    slot = width // 9
    bottom = height - 1

    def bar(x0, x1, level):
        reach = round(level * (half - 2))
        return (x0, bottom - reach, x1, bottom) if reach > 0 else None

    bars = [bar(i * slot + 1, (i + 1) * slot - 2, level) for i, level in enumerate(stem_levels)]
    left = 8 * slot + 1
    middle = left + (slot - 3) // 2
    bars.append(bar(left, middle - 1, aux_levels[0]))
    bars.append(bar(middle + 1, (9 * slot) - 2, aux_levels[1]))
    return bars


def menu_announcement(args):
    """(level, cursor) out of `/channel/{ch}/stem/menu`'s arguments, or None
    if damaged: level 0-2, cursor 0-2 at the top, 0-4 in a deck."""
    if len(args) != 2 or not all(_is_count(v, 4) for v in args):
        return None
    level, cursor = args
    if level > 2 or cursor >= (len(TOP_ENTRIES) if level == TOP_LEVEL else STEMS_PER_DECK + 1):
        return None
    return level, cursor


def mode_announcement(args):
    """The return's mode out of `/aux-return/stem/mode`, or None."""
    if len(args) != 1 or not _is_count(args[0], 1):
        return None
    return args[0]
