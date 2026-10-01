#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The five encoders: which stem plays where (spec stem-routing-on-the-desk).

Hardware-free like a3_mixer_panel. The firmware reports an absolute position
per encoder; this turns positions into clicks and clicks into the truth's
words. Core decides what a click means (a3_core_stems).
"""

#: Encoder index -> what it chooses for. MEASURED ON THE DESK: <date, who>.
#: Not yet measured, assumed: the firmware's order, left to right.
ENCODER_TARGETS = {
    0: ("channel", 0),
    1: ("channel", 1),
    2: ("channel", 2),
    3: ("channel", 3),
    4: ("return", None),
}

#: Counts per detent. MEASURED ON THE DESK: <date, who>. Not yet measured,
#: assumed: quadrature encoders with the Encoder library usually report four.
COUNTS_PER_CLICK = 4


class Clicks:
    """Whole clicks from absolute positions, leftover counts carried.

    The grid is anchored at absolute 0, where the firmware starts counting at
    boot, so detents rest on multiples of `per_click`. A click is counted
    half-way between two of them: a knob resting on a detent and jittering by
    a count either way stays inside one step instead of crossing a boundary
    and back (which sent a stem away and back on the PA)."""

    def __init__(self, per_click=COUNTS_PER_CLICK):
        self._per_click = per_click
        self._sent = {}

    def feed(self, encoder, position):
        # Detents are fixed on the position axis, so going out and back
        # across one nets to zero clicks instead of leaking a count.
        total = (position + self._per_click // 2) // self._per_click
        # The first report only says where the knob is: the firmware prints
        # on a change, and nobody turned it towards anything yet.
        if encoder not in self._sent:
            self._sent[encoder] = total
            return 0
        clicks = total - self._sent[encoder]
        self._sent[encoder] = total
        return clicks


def encoder_message(osc, encoder, clicks):
    target = ENCODER_TARGETS.get(encoder)
    if target is None or clicks == 0:
        return None
    kind, index = target
    if kind == "channel":
        return osc.channel_address("channel.stem.turn", index), clicks
    return osc.address("fx-return.stem.turn"), clicks


def push_message(osc, encoder, pressed):
    if not pressed or ENCODER_TARGETS.get(encoder, (None,))[0] != "return":
        return None
    return osc.address("fx-return.stem.push"), 1


def parse_int(text):
    """An int from a serial field, None if the line was damaged in transit."""
    digits = text[1:] if text.startswith("-") else text
    if not (digits.isascii() and digits.isdigit()):
        return None
    return int(text)
