# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The calibration on the five displays (a3_mixer_calibration_run).

The display of the strip whose control is asked for -- the FX Return's for
the master section -- carries the question: the control's name, the end to
go to as a triangle and a word (UP, DOWN, CENTRE), the keys, and a bar of
where the control reads now, so the hand sees the desk register it. Every
other display says which one to look at and how far the run is.

Each display keeps, at its bottom, its own controls as a grid of short
labels: filled with dark letters once done (the CUE field's ON), outlined
while asked for, letters only while waiting.

Pure layout (calibration_picture) and a painter for the Pi's 1-bit image;
sizes are shares of the display's height and width.
"""

import math
from collections import namedtuple

from a3_mixer_calibration_run import (CANCELLED, CENTRE_END, DONE, DOWN,
                                      MASTER_PANEL, RUNNING, UP)

Text = namedtuple("Text", "box text")
Field = namedtuple("Field", "box text mark")
Arrow = namedtuple("Arrow", "box end")
#: `texts`, the grid's `fields`, the asked end's `arrow` (or None), and the
#: `reading` bar as (box, share 0..1) (or None).
CalibrationPicture = namedtuple("CalibrationPicture", "texts fields arrow reading")

#: The bands, top to bottom, as shares of the display's height.
TITLE = (0.0, 0.19)
QUESTION = (0.2, 0.45)
HINT = (0.47, 0.58)
READING = (0.61, 0.69)
GRID = (0.7, 1.0)

#: The keys, each in a share of the width by its length: as one line, the
#: small font ate the spaces between them.
HINT_TEXTS = ("PUSH OK", "TURN SKIP", "FX ESC")

#: Rows between the grid's two rows, and between a field's edge and its
#: letters, so an outline never touches the label above or inside it.
GRID_GAP = 1
FIELD_INSET = 1

WORDS = {UP: "UP", DOWN: "DOWN", CENTRE_END: "CENTRE"}
ENDED = {DONE: ("CALIBRATED", "SAVED"), CANCELLED: ("CANCELLED", "OLD KEPT")}


def _rows(band, height):
    return round(band[0] * height), round(band[1] * height) - 1


def _panel_name(panel):
    return "FX RETURN" if panel == MASTER_PANEL else f"CH{panel + 1}"


def _grid(marks, width, height):
    """Two rows of fields, as many columns as it takes."""
    top, bottom = _rows(GRID, height)
    if not marks:
        return ()
    columns = math.ceil(len(marks) / 2)
    middle = (top + bottom) // 2
    rows = ((top, middle - GRID_GAP), (middle + 1, bottom))
    fields = []
    for index, (text, mark) in enumerate(marks):
        row, column = divmod(index, columns)
        x0 = column * width // columns
        x1 = (column + 1) * width // columns - 2
        y0, y1 = rows[row]
        fields.append(Field((x0, y0, x1, y1), text, mark))
    return tuple(fields)


def _band(band, width, height):
    y0, y1 = _rows(band, height)
    return (0, y0, width - 1, y1)


def _asking(view, width, height):
    """The display whose control is asked for."""
    y0, y1 = _rows(QUESTION, height)
    side = y1 - y0
    margin = width // 8
    arrow = Arrow((margin, y0, margin + side, y1), view.end)
    texts = (Text(_band(TITLE, width, height), view.title),
             Text((margin + side + 2, y0, width - 1, y1), WORDS[view.end])) \
        + _hint(width, height)
    reading = None
    if view.reading is not None:
        reading = (_band(READING, width, height), view.reading)
    return texts, arrow, reading


def _hint(width, height):
    y0, y1 = _rows(HINT, height)
    letters = sum(len(text) for text in HINT_TEXTS)
    texts, before = [], 0
    for text in HINT_TEXTS:
        x0 = before * width // letters
        before += len(text)
        texts.append(Text((x0, y0, before * width // letters - 1, y1), text))
    return tuple(texts)


def _waiting(view, width, height):
    """Every other display while it runs."""
    return (Text(_band(TITLE, width, height), "CALIBRATION"),
            Text(_band(QUESTION, width, height), f"{view.number}/{view.total}"),
            Text(_band(HINT, width, height), "SEE " + _panel_name(view.panel)))


def calibration_picture(view, panel, width, height):
    """What display `panel` (0-3 the channels, 4 the FX Return) shows of
    `view`, laid out for a display of `width` x `height`."""
    fields = _grid(view.marks[panel], width, height)
    if view.state != RUNNING:
        title, word = ENDED[view.state]
        texts = (Text(_band(TITLE, width, height), title),
                 Text(_band(QUESTION, width, height), word))
        return CalibrationPicture(texts, fields, None, None)
    if view.panel == panel:
        texts, arrow, reading = _asking(view, width, height)
        return CalibrationPicture(texts, fields, arrow, reading)
    return CalibrationPicture(_waiting(view, width, height), fields, None, None)


def _triangle(draw, box, pointing_up):
    """A solid triangle filling `box`, its point up or down."""
    x0, y0, x1, y1 = box
    middle = (x0 + x1) / 2
    tip, base = (y0, y1) if pointing_up else (y1, y0)
    draw.polygon([(middle, tip), (x0, base), (x1, base)], fill="white")


def _centre_mark(draw, box):
    """A bar across the middle, with a tick above and below: the detent."""
    x0, y0, x1, y1 = box
    middle_y = (y0 + y1) // 2
    middle_x = (x0 + x1) // 2
    thickness = max(1, (y1 - y0) // 8)
    draw.rectangle((x0, middle_y - thickness, x1, middle_y + thickness), fill="white")
    draw.line((middle_x, y0, middle_x, y1), fill="white")


def _arrow(draw, arrow):
    if arrow.end == CENTRE_END:
        _centre_mark(draw, arrow.box)
    else:
        _triangle(draw, arrow.box, arrow.end == UP)


def _text(draw, box, text, colour):
    from a3_mixer_displays import TEXT_OF_HEADING, _fit
    x0, y0, x1, y1 = box
    font, at = _fit(draw, box, text, round((y1 - y0 + 1) * TEXT_OF_HEADING))
    draw.text(at, text, fill=colour, font=font)


def _field(draw, field):
    x0, y0, x1, y1 = field.box
    letters = (x0 + FIELD_INSET, y0 + FIELD_INSET, x1 - FIELD_INSET, y1 - FIELD_INSET)
    if field.mark == "done":
        draw.rectangle(field.box, fill="white")
        _text(draw, letters, field.text, "black")
        return
    if field.mark == "current":
        draw.rectangle(field.box, outline="white")
    _text(draw, letters, field.text, "white")


def _reading(draw, reading):
    (x0, y0, x1, y1), share = reading
    draw.rectangle((x0, y0, x1, y1), outline="white")
    filled = x0 + round(share * (x1 - x0))
    if filled > x0:
        draw.rectangle((x0, y0, filled, y1), fill="white")


def paint_calibration(image, picture):
    """Draw `picture` onto a 1-bit PIL image."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width - 1, image.height - 1), fill="black")
    for text in picture.texts:
        _text(draw, text.box, text.text, "white")
    if picture.arrow is not None:
        _arrow(draw, picture.arrow)
    if picture.reading is not None:
        _reading(draw, picture.reading)
    for field in picture.fields:
        _field(draw, field)
