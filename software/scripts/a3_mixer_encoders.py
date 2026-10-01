#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The five encoders: which stem plays where (spec stem-routing-on-the-desk).

Hardware-free like a3_mixer_panel. The firmware reports an absolute position
per encoder; this turns positions into clicks and clicks into the truth's
words. Core decides what a click means (a3_core_stems).
"""

import time

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

#: How long an encoder switch has to be quiet before a press counts.
#: MEASURED ON THE DESK: <date, who>. Not yet measured, assumed: contacts of
#: this kind settle within a few milliseconds, and no hand presses twice in
#: fifty.
PUSH_HOLD_OFF_SECONDS = 0.05


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


class PushHoldOff:
    """A press from the raw switch edges, contact bounce ignored.

    The firmware reads the encoder switches with a bare digitalRead, unlike
    the panel keys (Bounce), and prints every change -- one press can arrive
    as several press edges. A press counts only after `hold_off` without any
    edge of that encoder. Any edge, not just the last accepted press: a
    release bounces too, and its stray press edge comes long after the press
    it belongs to."""

    def __init__(self, hold_off=PUSH_HOLD_OFF_SECONDS, clock=time.monotonic):
        self._hold_off = hold_off
        self._clock = clock
        self._last_edge = {}

    def feed(self, encoder, pressed):
        now = self._clock()
        previous = self._last_edge.get(encoder)
        self._last_edge[encoder] = now
        if not pressed:
            return False
        return previous is None or now - previous >= self._hold_off


def encoder_message(osc, encoder, clicks):
    target = ENCODER_TARGETS.get(encoder)
    if target is None or clicks == 0:
        return None
    kind, index = target
    if kind == "channel":
        return osc.channel_address("channel.stem.turn", index), clicks
    return osc.address("aux-return.stem.turn"), clicks


def push_message(osc, encoder, pressed):
    if not pressed or ENCODER_TARGETS.get(encoder, (None,))[0] != "return":
        return None
    return osc.address("aux-return.stem.push"), 1


def parse_int(text):
    """An int from a serial field, None if the line was damaged in transit."""
    digits = text[1:] if text.startswith("-") else text
    if not (digits.isascii() and digits.isdigit()):
        return None
    return int(text)
